"""Build the people layer -> web/data/people.json

Sources: Wikidata (well-known people: place and year of birth and death) and CBDB (Chinese historical figures:
home place (籍贯) and index year). A CBDB record is dropped when the same name and birth or death year is already
there from Wikidata.

Columns. Persons: n name, d note, by/dy birth and death year (0 = unknown), s Wikipedia language count,
  q Wikidata id, cb CBDB person id, w Wikipedia flag (1 zh, 2 en only).
Points (sorted by year): pp person index, pk kind (0 born, 1 died, 2 home place), py year, px/pl lon/lat.
"""
import csv
import glob
import json
import os
import re
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_events import fetch_labels, clean, parse_year, parse_pt, T2S  # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
RAW = os.path.join(ROOT, "data", "raw")
OUT = os.path.join(ROOT, "web", "data")
MIN_SL = 25


def wikidata():
    people = {}
    for f in glob.glob(os.path.join(RAW, "wikidata_people", "people_*.csv")):
        for r in csv.DictReader(open(f, encoding="utf-8")):
            q = (r.get("p") or "").rsplit("/", 1)[-1]
            if not re.fullmatch(r"Q\d+", q):
                continue
            p = people.setdefault(q, {"by": None, "bc": None, "dy": None, "dc": None, "sl": 0})
            b, d = parse_year(r.get("b")), parse_year(r.get("d"))
            if b and p["by"] is None:
                p["by"] = b[0]
            if d and p["dy"] is None:
                p["dy"] = d[0]
            p["bc"] = p["bc"] or parse_pt(r.get("bc"))
            p["dc"] = p["dc"] or parse_pt(r.get("dc"))
            try:
                p["sl"] = max(p["sl"], int(r.get("sl") or 0))
            except ValueError:
                pass
    return {q: p for q, p in people.items() if p["sl"] >= MIN_SL and (p["bc"] or p["dc"]) and p["by"] is not None}


def cbdb():
    path = glob.glob(os.path.join(RAW, "ext", "cbdb", "*.sqlite3"))
    if not path:
        return []
    con = sqlite3.connect(path[0])
    q = """select m.c_personid, m.c_name_chn, m.c_index_year, m.c_birthyear, m.c_deathyear, a.c_name_chn, a.x_coord, a.y_coord, d.c_dynasty_chn
           from BIOG_MAIN m join ADDR_CODES a on m.c_index_addr_id = a.c_addr_id left join DYNASTIES d on m.c_dy = d.c_dy
           where a.x_coord is not null and a.x_coord <> 0 and a.y_coord <> 0 and m.c_index_year is not null and m.c_index_year <> 0
             and ((m.c_birthyear is not null and m.c_birthyear <> 0) or (m.c_deathyear is not null and m.c_deathyear <> 0))
             and m.c_name_chn is not null"""
    out = []
    for pid, name, iy, by, dy, addr, x, y, dyn in con.execute(q):
        if not (-180 <= x <= 180 and -85 <= y <= 85):
            continue
        out.append({"id": pid, "n": T2S.convert(name), "iy": int(iy), "by": int(by or 0), "dy": int(dy or 0),
                    "addr": T2S.convert(addr or ""), "pt": (float(x), float(y)), "dyn": T2S.convert(dyn or "")})
    return out


def main():
    wd = wikidata()
    print("wikidata people", len(wd), flush=True)
    labels = fetch_labels(sorted(wd))
    P = {k: [] for k in ("n", "d", "by", "dy", "s", "q", "cb", "w")}
    pts = []
    seen = set()
    for q, p in sorted(wd.items(), key=lambda kv: kv[1]["by"]):
        lab = labels.get(q)
        if not lab or not lab[0] or re.fullmatch(r"Q\d+", lab[0]):
            continue
        i = len(P["n"])
        name = clean(lab[0], 40)
        P["n"].append(name); P["d"].append(clean(lab[1], 70)); P["by"].append(p["by"]); P["dy"].append(p["dy"] or 0)
        P["s"].append(min(p["sl"], 60000)); P["q"].append(int(q[1:])); P["cb"].append(0); P["w"].append(lab[2])
        seen.add((name, p["by"]))
        if p["dy"]:
            seen.add((name, p["dy"]))
        if p["bc"]:
            pts.append((p["by"], i, 0, p["bc"]))
        if p["dc"] and p["dy"]:
            pts.append((p["dy"], i, 1, p["dc"]))
    nwd = len(P["n"])
    dropped = 0
    for c in cbdb():
        if (c["by"] and (c["n"], c["by"]) in seen) or (c["dy"] and (c["n"], c["dy"]) in seen):
            dropped += 1
            continue
        i = len(P["n"])
        P["n"].append(c["n"][:40]); P["d"].append(f"{c['dyn']}；籍贯：{c['addr']}"); P["by"].append(c["by"]); P["dy"].append(c["dy"])
        P["s"].append(0); P["q"].append(0); P["cb"].append(c["id"]); P["w"].append(0)
        pts.append((c["iy"], i, 2, c["pt"]))
    print("persons: wikidata", nwd, "cbdb", len(P["n"]) - nwd, "(cbdb duplicates of wikidata dropped:", dropped, ")")
    pts.sort(key=lambda x: x[0])
    data = dict(P)
    data.update({"py": [x[0] for x in pts], "pp": [x[1] for x in pts], "pk": [x[2] for x in pts],
                 "px": [round(x[3][0], 3) for x in pts], "pl": [round(x[3][1], 3) for x in pts]})
    path = os.path.join(OUT, "people.json")
    json.dump(data, open(path, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print("wrote", path, os.path.getsize(path) // 1024, "KB;", len(P["n"]), "persons;", len(pts), "points")


if __name__ == "__main__":
    main()
