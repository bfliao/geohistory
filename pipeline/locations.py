"""Collect what is needed to judge how trustworthy each event pin is.

1. For every event-like item: its P276 locations (with coordinates) and P17 countries.
2. For every location entity seen: P31 classes, area (km2) and ISO country code (P297, for countries).
3. For every location class: which granularity roots it descends from.

Output (data/work): item_locs.json, loc_info.json, loc_classes.json. Re-runnable (cached).
"""
import csv
import glob
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fetch_wikidata import sparql, Timeout  # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
RAW = os.path.join(ROOT, "data", "raw", "wikidata")
WORK = os.path.join(ROOT, "data", "work")

LOC_ROOTS = """Q6256 Q3624078 Q3024240 Q7275 Q48349 Q5107 Q82794 Q1620908 Q9430 Q165 Q10864048 Q35657 Q34876 Q107390
Q46831 Q4022 Q8514 Q34763 Q3502482 Q33837 Q23442 Q39594 Q1322134 Q37901 Q23397 Q355304 Q15324 Q1048835
Q486972 Q515 Q41176 Q811979 Q839954 Q123705 Q79007 Q174782 Q22698 Q1248784 Q55488 Q44782 Q12280 Q23413 Q57821
Q16970 Q4989906 Q24398318 Q3918 Q483110 Q17350442 Q8502 Q133056 Q54050 Q4895393 Q13226383 Q34442 Q728937
Q56061 Q13220204 Q13221722 Q14757767 Q15284 Q28575 Q149621""".split()


def rows(txt):
    return list(csv.DictReader(txt.splitlines()))


def qid(u):
    q = (u or "").rsplit("/", 1)[-1]
    return q if re.fullmatch(r"Q\d+", q) else None


def pt(s):
    m = re.match(r"^Point\(([-\d.eE]+) ([-\d.eE]+)\)$", s or "")
    return [float(m.group(1)), float(m.group(2))] if m else None


def load(name):
    p = os.path.join(WORK, name)
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}


def save(name, obj):
    json.dump(obj, open(os.path.join(WORK, name), "w", encoding="utf-8"), ensure_ascii=False)


def batched(todo, size, fn, label, cache, name):
    for i in range(0, len(todo), size):
        batch = todo[i:i + size]
        for attempt in range(3):
            try:
                cache.update(fn(batch))
                break
            except Timeout:
                time.sleep(5)
        if (i // size) % 10 == 0:
            save(name, cache)
            print(f"  {label} {i}/{len(todo)}", flush=True)
        time.sleep(0.2)
    save(name, cache)


def event_items():
    """Event items (with --all: also items that only have an inception date), plus raw location rows from the loc jobs."""
    items, raw_locs = set(), {}
    for f in glob.glob(os.path.join(RAW, "*.csv")):
        job = os.path.basename(f).split("_")[0]
        for r in csv.DictReader(open(f, encoding="utf-8")):
            q = qid(r.get("item"))
            if not q:
                continue
            if job != "p571" or "--all" in sys.argv:
                items.add(q)
            if job.startswith("loc"):
                l, c = qid(r.get("loc")), pt(r.get("c"))
                if l and c:
                    raw_locs.setdefault(q, {})[l] = c
    return items, raw_locs


def main():
    os.makedirs(WORK, exist_ok=True)
    only = None
    p = os.path.join(ROOT, "web", "data", "events.json")
    if "--kept-only" in sys.argv and os.path.exists(p):
        only = {"Q%d" % q for q in json.load(open(p, encoding="utf-8"))["q"]}
    items, raw_locs = event_items()
    if only:
        items &= only
    print("event items", len(items), flush=True)

    # 1. locations + countries per item
    item_locs = load("item_locs.json")

    def f_items(batch):
        vals = " ".join("wd:" + q for q in batch)
        q = f"""SELECT ?item ?loc ?c ?country WHERE {{ VALUES ?item {{ {vals} }}
  {{ ?item wdt:P276 ?loc . OPTIONAL {{ ?loc wdt:P625 ?c }} }} UNION {{ ?item wdt:P17 ?country }} }}"""
        res = {k: {"locs": {}, "countries": []} for k in batch}
        for r in rows(sparql(q)):
            k = qid(r["item"])
            if k not in res:
                continue
            l = qid(r.get("loc"))
            if l:
                c = pt(r.get("c"))
                if c or l not in res[k]["locs"]:
                    res[k]["locs"][l] = c
            c2 = qid(r.get("country"))
            if c2 and c2 not in res[k]["countries"]:
                res[k]["countries"].append(c2)
        return res

    batched([q for q in sorted(items) if q not in item_locs], 400, f_items, "items", item_locs, "item_locs.json")

    # 2. location entities: classes, area, ISO code
    locs = set()
    for q in items:
        v = item_locs.get(q)
        if v:
            locs.update(v["locs"])
            locs.update(v["countries"])
        locs.update(raw_locs.get(q, {}))
    loc_info = load("loc_info.json")

    def f_locs(batch):
        vals = " ".join("wd:" + q for q in batch)
        q = f"""SELECT ?l ?cls ?area ?iso WHERE {{ VALUES ?l {{ {vals} }}
  {{ ?l wdt:P31 ?cls }} UNION {{ ?l p:P2046/psn:P2046/wikibase:quantityAmount ?area }} UNION {{ ?l wdt:P297 ?iso }} }}"""
        res = {k: {"cls": [], "area": None, "iso": None} for k in batch}
        for r in rows(sparql(q)):
            k = qid(r["l"])
            if k not in res:
                continue
            c = qid(r.get("cls"))
            if c and c not in res[k]["cls"]:
                res[k]["cls"].append(c)
            if r.get("area"):
                try:
                    a = float(r["area"]) / 1e6  # normalized value is m2
                    res[k]["area"] = a if res[k]["area"] is None else max(res[k]["area"], a)
                except ValueError:
                    pass
            if r.get("iso"):
                res[k]["iso"] = r["iso"]
        return res

    print("locations", len(locs), flush=True)
    batched([q for q in sorted(locs) if q not in loc_info], 400, f_locs, "locs", loc_info, "loc_info.json")

    # 3. class ancestry for location classes
    classes = set()
    for q in locs:
        classes.update(loc_info.get(q, {}).get("cls", []))
    loc_classes = load("loc_classes.json")
    rootlist = ", ".join("wd:" + r for r in LOC_ROOTS)

    def f_cls(batch):
        vals = " ".join("wd:" + q for q in batch)
        q = f"""SELECT ?c ?r WHERE {{ VALUES ?c {{ {vals} }} ?c wdt:P279* ?r . hint:Prior hint:gearing "forward" . FILTER(?r IN ({rootlist})) }}"""
        res = {k: [] for k in batch}
        for r in rows(sparql(q)):
            k, rt = qid(r["c"]), qid(r["r"])
            if k in res and rt not in res[k]:
                res[k].append(rt)
        return res

    print("location classes", len(classes), flush=True)
    batched([c for c in sorted(classes) if c not in loc_classes], 100, f_cls, "classes", loc_classes, "loc_classes.json")
    print("DONE", len(item_locs), len(loc_info), len(loc_classes), flush=True)


if __name__ == "__main__":
    main()
