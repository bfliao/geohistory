"""Resolve Wikidata classes (P31 values) seen in raw data: labels + which root classes they descend from.

Output: data/work/classes.json  {qid: {"zh":..., "en":..., "roots":[...], "n": count}}
Re-runnable: only fetches classes not cached yet.
"""
import csv
import re
import glob
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fetch_wikidata import sparql, Timeout  # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
RAW = os.path.join(ROOT, "data", "raw", "wikidata")
WORK = os.path.join(ROOT, "data", "work")

ROOTS = """Q178561 Q188055 Q198 Q645883 Q350604 Q180684 Q831663 Q1261499 Q2001676 Q467011
Q3199915 Q2223653 Q21480300 Q132821 Q750215 Q3882219 Q1174599 Q41397 Q149086
Q131569 Q625298 Q10931 Q124734 Q45382 Q273120 Q124757 Q209715 Q1072326 Q49776 Q175331
Q7944 Q3839081 Q8065 Q7692360 Q8068 Q8070 Q8081 Q8092 Q167903 Q7935 Q44512 Q168247
Q744913 Q1078765 Q906512 Q7625093 Q179057 Q1550225 Q171558 Q9687
Q2401485 Q210112 Q5916 Q51645 Q111161 Q172754 Q159821 Q82414 Q464980
Q486972 Q515 Q15661340 Q839954 Q3024240 Q6256 Q56061
Q23413 Q16970 Q44613 Q3918 Q24398318 Q41176 Q811979 Q12280 Q57821 Q4989906 Q33506
Q27020041 Q13406554 Q16510064 Q40231 Q43109 Q3887 Q132241 Q182832 Q4504495 Q27968055 Q2020153
Q18608583 Q500834 Q43229 Q1190554 Q1656682""".split()


def collect():
    cnt = {}
    for f in glob.glob(os.path.join(RAW, "*.csv")):
        seen = set()
        for r in csv.DictReader(open(f, encoding="utf-8")):
            c = (r.get("cls") or "").rsplit("/", 1)[-1]
            q = (r.get("item") or "").rsplit("/", 1)[-1]
            if re.fullmatch(r"Q\d+", c) and (q, c) not in seen:
                seen.add((q, c))
                cnt[c] = cnt.get(c, 0) + 1
    return cnt


def rows(txt):
    return list(csv.DictReader(txt.splitlines()))


def main():
    os.makedirs(WORK, exist_ok=True)
    path = os.path.join(WORK, "classes.json")
    cache = json.load(open(path, encoding="utf-8")) if os.path.exists(path) else {}
    cnt = collect()
    todo = [c for c in cnt if c not in cache]
    print("classes", len(cnt), "todo", len(todo), flush=True)
    rootlist = ", ".join("wd:" + r for r in ROOTS)
    B = 100
    for i in range(0, len(todo), B):
        batch = todo[i:i + B]
        vals = " ".join("wd:" + c for c in batch)
        res = {c: {"zh": "", "en": "", "roots": []} for c in batch}
        q1 = f"""SELECT ?c ?zh ?en WHERE {{ VALUES ?c {{ {vals} }}
  OPTIONAL {{ ?c rdfs:label ?zh FILTER(LANG(?zh)="zh") }}
  OPTIONAL {{ ?c rdfs:label ?en FILTER(LANG(?en)="en") }} }}"""
        q2 = f"""SELECT ?c ?r WHERE {{ VALUES ?c {{ {vals} }} ?c wdt:P279* ?r . hint:Prior hint:gearing "forward" . FILTER(?r IN ({rootlist})) }}"""
        try:
            for r in rows(sparql(q1)):
                c = r["c"].rsplit("/", 1)[-1]
                if c in res:
                    res[c]["zh"] = r["zh"]; res[c]["en"] = r["en"]
            for r in rows(sparql(q2)):
                c = r["c"].rsplit("/", 1)[-1]
                if c in res:
                    res[c]["roots"].append(r["r"].rsplit("/", 1)[-1])
        except Timeout:
            print("timeout batch", i, flush=True)
            continue
        cache.update(res)
        if (i // B) % 5 == 0:
            json.dump(cache, open(path, "w", encoding="utf-8"), ensure_ascii=False)
        print(i, "/", len(todo), flush=True)
        time.sleep(0.5)
    for c, n in cnt.items():
        if c in cache:
            cache[c]["n"] = n
    json.dump(cache, open(path, "w", encoding="utf-8"), ensure_ascii=False)
    print("saved", len(cache))


if __name__ == "__main__":
    main()
