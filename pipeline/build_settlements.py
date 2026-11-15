"""Build time-sliced settlement layer from Pleiades + CHGIS (+ Wikidata settlements if present).

Output: web/data/settlements.json (columnar)
  n name, x lon, y lat, a first year, b last year, s source (0 Pleiades, 1 CHGIS, 2 Wikidata),
  t type label, d short note, id source id
Years: negative = BCE.
"""
import collections
import csv
import json
import os

import shapefile

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
RAW = os.path.join(ROOT, "data", "raw")
OUT = os.path.join(ROOT, "web", "data")
csv.field_size_limit(10**9)

PLEIADES_TYPES = {
    "settlement": "聚落", "urban": "城市", "villa": "庄园", "fort": "要塞", "fort-2": "要塞",
    "station": "驿站", "port": "港口", "sanctuary": "圣所", "temple": "神庙", "temple-2": "神庙",
    "mine": "矿场", "mine-2": "矿场", "church": "教堂", "church-2": "教堂", "monastery": "修道院",
    "archaeological-site": "遗址", "architecturalcomplex": "建筑群", "theatre": "剧场",
    "amphitheatre": "圆形剧场", "bath": "浴场", "cemetery": "墓地", "tomb": "陵墓", "tumulus": "坟丘",
    "bridge": "桥梁", "aqueduct": "水道", "quarry": "采石场", "palace": "宫殿", "citadel": "卫城",
    "townhouse": "宅邸", "monument": "纪念物",
}
# types that count as places where people lived (kept at higher priority)
LIVED = {"settlement", "urban", "villa", "fort", "fort-2", "station", "port", "citadel"}


def pleiades():
    base = os.path.join(RAW, "pleiades")
    types = collections.defaultdict(list)
    for r in csv.DictReader(open(os.path.join(base, "places_place_types.csv"), encoding="utf-8-sig")):
        types[r["place_id"]].append(r["place_type"])
    span = {}

    def add(pid, a, b):
        try:
            a = int(float(a)); b = int(float(b))
        except (TypeError, ValueError):
            return
        if pid in span:
            span[pid] = (min(span[pid][0], a), max(span[pid][1], b))
        else:
            span[pid] = (a, b)

    for fn in ("location_points.csv", "names.csv"):
        for r in csv.DictReader(open(os.path.join(base, fn), encoding="utf-8-sig")):
            add(r["place_id"], r["year_after_which"], r["year_before_which"])
    out = []
    for r in csv.DictReader(open(os.path.join(base, "places.csv"), encoding="utf-8-sig")):
        pid = r["id"]
        if r["location_precision"] != "precise" or pid not in span:
            continue
        ts = [t for t in types.get(pid, []) if t in PLEIADES_TYPES]
        if not ts:
            continue
        lived = [t for t in ts if t in LIVED]
        t = (lived or ts)[0]
        try:
            lat = float(r["representative_latitude"]); lon = float(r["representative_longitude"])
        except ValueError:
            continue
        a, b = span[pid]
        desc = " ".join(r["description"].split())
        if len(desc) > 160:
            desc = desc[:157] + "…"
        out.append((r["title"], lon, lat, a, b, 0, PLEIADES_TYPES[t], desc, pid, 1 if lived else 0))
    return out


def chgis():
    r = shapefile.Reader(os.path.join(RAW, "chgis", "cnty", "v6_time_cnty_pts_utf_wgs84"), encoding="utf-8")
    names = [f[0] for f in r.fields[1:]]
    out = []
    for rec in r.iterRecords():
        d = dict(zip(names, rec))
        lon, lat = d["X_COOR"], d["Y_COOR"]
        if not lon or not lat:
            continue
        note = "今" + d["PRES_LOC"].lstrip("今") if d["PRES_LOC"] else ""
        chg = "／".join(x for x in (d["BEG_CHG_TY"], d["END_CHG_TY"]) if x)
        if chg:
            note = (note + "；" if note else "") + "沿革：" + chg
        out.append((d["NAME_CH"], float(lon), float(lat), int(d["BEG_YR"]), int(d["END_YR"]), 1,
                    d["TYPE_CH"] or "县级治所", note, str(d["SYS_ID"]), 1))
    return out


def main():
    rows = pleiades()
    print("pleiades", len(rows))
    c = chgis()
    print("chgis", len(c))
    rows += c
    wd = os.path.join(ROOT, "data", "work", "wd_settlements.json")
    if os.path.exists(wd):
        w = json.load(open(wd, encoding="utf-8"))
        print("wikidata settlements", len(w))
        rows += [tuple(x) for x in w]
    rows.sort(key=lambda x: x[3])
    types = sorted({x[6] for x in rows})
    tix = {t: i for i, t in enumerate(types)}
    data = {
        "n": [x[0] for x in rows],
        "x": [round(x[1], 4) for x in rows],
        "y": [round(x[2], 4) for x in rows],
        "a": [x[3] for x in rows],
        "b": [x[4] for x in rows],
        "s": [x[5] for x in rows],
        "t": [tix[x[6]] for x in rows],
        "d": [x[7] for x in rows],
        "id": [x[8] for x in rows],
        "types": types,
    }
    os.makedirs(OUT, exist_ok=True)
    p = os.path.join(OUT, "settlements.json")
    json.dump(data, open(p, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print("wrote", p, os.path.getsize(p) // 1024, "KB", len(rows))


if __name__ == "__main__":
    main()
