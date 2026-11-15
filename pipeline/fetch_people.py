"""Fetch well-known people from Wikidata with dated, located births and deaths.

One CSV per birth-year slice in data/raw/wikidata_people/ (resumable; slices that time out are split).
Only people with at least MIN_SL Wikipedia language versions are fetched.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fetch_wikidata import sparql, Timeout, lit  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "raw", "wikidata_people")
MIN_SL = 25


def query(a, b):
    return f"""SELECT ?p ?b ?bc ?d ?dc ?sl WHERE {{
  ?p wdt:P569 ?b . hint:Prior hint:rangeSafe true .
  FILTER(?b >= {lit(a)} && ?b < {lit(b)})
  ?p wikibase:sitelinks ?sl . FILTER(?sl >= {MIN_SL})
  ?p wdt:P31 wd:Q5 .
  OPTIONAL {{ ?p wdt:P19 ?bp . ?bp wdt:P625 ?bc }}
  OPTIONAL {{ ?p wdt:P570 ?d }}
  OPTIONAL {{ ?p wdt:P20 ?dp . ?dp wdt:P625 ?dc }}
}}"""


def run(a, b):
    path = os.path.join(OUT, f"people_{a}_{b}.csv")
    if os.path.exists(path):
        return
    t = time.time()
    try:
        txt = sparql(query(a, b))
    except Timeout:
        if b - a <= 1:
            print("GIVE UP", a, b, flush=True)
            open(path + ".failed", "w").close()
            return
        m = (a + b) // 2
        print(f"  timeout {a}..{b} -> split at {m}", flush=True)
        run(a, m)
        run(m, b)
        return
    open(path, "w", encoding="utf-8").write(txt)
    print(f"people {a}..{b}: {max(0, txt.count(chr(10)) - 1)} rows in {time.time() - t:.1f}s", flush=True)
    time.sleep(1)


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    bs = [-3500, -500, 0, 500, 1000, 1200, 1400, 1500, 1600, 1700, 1750, 1800, 1820, 1840, 1860, 1870, 1880, 1890, 1900]
    bs += list(range(1902, 2012, 2))
    for a, b in zip(bs, bs[1:]):
        run(a, b)
    print("DONE", flush=True)
