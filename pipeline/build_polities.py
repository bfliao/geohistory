"""Build the polity layer from Cliopatria (3400 BCE - 2024 CE) -> web/data/polities.json

One GeoJSON file; every feature carries the years it is valid for (f..t), so the page filters by exact year
instead of loading snapshots. Before 3400 BCE the five prehistoric snapshots of historical-basemaps are kept.

Usage: python3 pipeline/build_polities.py [path to mapshaper-xl]
Feature properties: n Chinese name, e English name, f first year, t last year, q Wikidata id, w Wikipedia title,
  lx/ly label point, sp label span in degrees, s source (0 Cliopatria, 1 historical-basemaps).
"""
import glob
import json
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_events import fetch_labels, clean  # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
EXT = os.path.join(ROOT, "data", "raw", "ext")
WORK = os.path.join(ROOT, "data", "work")
OUT = os.path.join(ROOT, "web", "data")
PRE = [(-123000, -10001), (-10000, -8001), (-8000, -5001), (-5000, -4001), (-4000, -3401)]


def label_point(geom):
    polys = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
    best, area = None, -1
    for pg in polys:
        xs = [p[0] for p in pg[0]]
        ys = [p[1] for p in pg[0]]
        a = (max(xs) - min(xs)) * (max(ys) - min(ys))
        if a > area:
            area = a
            best = (sum(xs) / len(xs), sum(ys) / len(ys), min(max(xs) - min(xs), (max(ys) - min(ys)) * 1.6))
    return best


def sample_years():
    ys = list(range(-3400, -1000, 100)) + list(range(-1000, 1500, 25))
    return ys + list(range(1500, 1800, 10)) + list(range(1800, 2025, 5))


def thin(fs):
    """Cliopatria has one row per entity and period, often yearly. Keep the rows that cover a sample year and
    stretch them to the next sample; an entity that falls between samples keeps its longest row."""
    import bisect
    ys = sample_years()
    kept, by_name, life = [], {}, {}
    for f in fs:
        p = f["properties"]
        by_name.setdefault(p["Name"], []).append(f)
        a, b = life.get(p["Name"], (p["FromYear"], p["ToYear"]))
        life[p["Name"]] = (min(a, p["FromYear"]), max(b, p["ToYear"]))
    for name, rows in by_name.items():
        # never stretch a row beyond the entity's own first and last year
        first, last = life[name]
        rows.sort(key=lambda r: r["properties"]["FromYear"])
        mine = []
        for f in rows:
            p = f["properties"]
            i = bisect.bisect_left(ys, p["FromYear"])
            j = bisect.bisect_right(ys, p["ToYear"])
            if i < j:
                p["FromYear"] = max(first, ys[i]) if mine else first
                p["ToYear"] = min(last, (ys[j] - 1) if j < len(ys) else 2024)
                mine.append(f)
        if mine:
            mine[-1]["properties"]["ToYear"] = last
        else:  # falls between two sample years: keep its longest row for its whole lifetime
            f = max(rows, key=lambda r: r["properties"]["ToYear"] - r["properties"]["FromYear"])
            f["properties"]["FromYear"], f["properties"]["ToYear"] = first, last
            mine = [f]
        kept += mine
    print("rows", len(fs), "-> after temporal thinning", len(kept))
    return kept


def main():
    ms = (sys.argv[1] if len(sys.argv) > 1 else None) or shutil.which("mapshaper-xl") or shutil.which("mapshaper")
    src = glob.glob(os.path.join(EXT, "cliopatria", "*.geojson"))[0]
    simp = os.path.join(WORK, "cliopatria_simplified.geojson")
    if not os.path.exists(simp):
        subprocess.run([ms, "6gb", src, "-filter", 'Type=="POLITY" && !MemberOf', "-simplify", "dp", "interval=18000", "-filter-slivers",
                        "-o", "precision=0.05", "format=geojson", simp], check=True)
    fs = json.load(open(simp, encoding="utf-8"))["features"]
    zh_dict = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "polity_zh.json"), encoding="utf-8"))
    qids = sorted({f["properties"]["Wikidata"] for f in fs if (f["properties"].get("Wikidata") or "").startswith("Q")})
    labels = fetch_labels(qids)
    fs = thin(fs)
    out, named = [], 0
    for f in fs:
        p = f["properties"]
        if p.get("Type") != "POLITY" or p.get("MemberOf") or not f.get("geometry"):
            continue  # members are drawn through the composite entity they belong to
        en = p["Name"].strip("()")
        q = p.get("Wikidata") or ""
        lab = (labels.get(q) or [""])[0]
        # the hand-made dictionary wins: some Wikidata ids in the source point to a neighbouring entity
        zh = zh_dict.get(en) or (clean(lab, 24) if lab and any("\u4e00" <= ch <= "\u9fff" for ch in lab) else "")
        named += 1 if zh else 0
        lp = label_point(f["geometry"])
        out.append({"type": "Feature", "geometry": f["geometry"],
                    "properties": {"n": zh or en, "e": en, "f": p["FromYear"], "t": p["ToYear"], "q": q, "w": p.get("Wikipedia") or "",
                                   "lx": round(lp[0], 2), "ly": round(lp[1], 2), "sp": round(lp[2], 1), "s": 0}})
    print("cliopatria features", len(out), "with Chinese name", named)
    pre = 0
    for (a, b) in PRE:  # prehistoric culture areas from historical-basemaps
        path = os.path.join(WORK, "basemaps_pre", f"{a}.json")
        if not os.path.exists(path):
            continue
        for f in json.load(open(path, encoding="utf-8"))["features"]:
            if not f.get("geometry") or not f["properties"].get("NAME"):
                continue
            en = f["properties"]["NAME"]
            lp = label_point(f["geometry"])
            out.append({"type": "Feature", "geometry": f["geometry"],
                        "properties": {"n": zh_dict.get(en, en), "e": en, "f": a, "t": b, "q": "", "w": "",
                                       "lx": round(lp[0], 2), "ly": round(lp[1], 2), "sp": round(lp[2], 1), "s": 1}})
            pre += 1
    print("prehistoric features", pre)
    path = os.path.join(OUT, "polities.json")
    json.dump({"type": "FeatureCollection", "features": out}, open(path, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print("wrote", path, os.path.getsize(path) // 1024, "KB", len(out), "features")


if __name__ == "__main__":
    main()
