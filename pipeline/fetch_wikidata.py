"""Fetch dated + located items from Wikidata (WDQS) in time slices.

Output: data/raw/wikidata/<job>_<from>_<to>.csv  (one file per slice, resumable)

Jobs
  p585   items with point in time (P585) and own coordinates (P625)
  p580   items with start time (P580) and own coordinates
  loc585 items with P585, no own coordinates, located (P276) at a place with coordinates
  loc580 same with P580
  p571   items with inception (P571) and own coordinates (settlements, monuments, institutions), up to 1900

Years are astronomical in WDQS (year 0 = 1 BCE); conversion happens in build step.
"""
import csv
import io
import os
import sys
import time

import requests

OUT = os.path.join(os.path.dirname(__file__), "..", "data", "raw", "wikidata")
URL = "https://query.wikidata.org/sparql"
UA = "HistoryAtlasPrototype/0.1 (educational mapping project; python-requests)"
S = requests.Session()
S.headers.update({"User-Agent": UA, "Accept": "text/csv"})


class Timeout(Exception):
    pass


def sparql(query, tries=4):
    for i in range(tries):
        try:
            r = S.post(URL, data={"query": query}, timeout=90)
        except requests.RequestException as e:
            time.sleep(5 * (i + 1))
            continue
        if r.status_code == 200:
            if "java.util.concurrent.TimeoutException" in r.text[-3000:]:
                raise Timeout()
            return r.text
        if r.status_code == 429:
            wait = int(r.headers.get("Retry-After", "30"))
            print("  429 retry-after", wait, flush=True)
            time.sleep(min(wait, 120) + 1)
            continue
        if r.status_code in (500, 502, 503, 504):
            # 500 with timeout text or 504 gateway timeout => query too heavy
            if r.status_code == 504 or "TimeoutException" in r.text:
                raise Timeout()
            time.sleep(10 * (i + 1))
            continue
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:300]}")
    raise Timeout()


def lit(year):
    y = int(year)
    s = f"{abs(y):04d}"
    return f'"{"-" if y < 0 else ""}{s}-01-01T00:00:00Z"^^xsd:dateTime'


def q_direct(prop, a, b, minsl):
    slf = f"FILTER(?sl >= {minsl})" if minsl else ""
    extra = "OPTIONAL { ?item wdt:P576 ?e }" if prop == "P571" else "OPTIONAL { ?item wdt:P582 ?e }"
    return f"""SELECT ?item ?d ?e ?c ?sl ?cls WHERE {{
  ?item wdt:{prop} ?d . FILTER(?d >= {lit(a)} && ?d < {lit(b)})
  ?item wdt:P625 ?c .
  ?item wikibase:sitelinks ?sl . {slf}
  OPTIONAL {{ ?item wdt:P31 ?cls }}
  {extra}
}}"""


def q_loc(prop, a, b, minsl):
    slf = f"FILTER(?sl >= {minsl})" if minsl else ""
    return f"""SELECT ?item ?d ?e ?c ?sl ?cls ?loc WHERE {{
  ?item wdt:{prop} ?d . FILTER(?d >= {lit(a)} && ?d < {lit(b)})
  ?item wdt:P276 ?loc . ?loc wdt:P625 ?c .
  FILTER NOT EXISTS {{ ?item wdt:P625 ?own }}
  ?item wikibase:sitelinks ?sl . {slf}
  OPTIONAL {{ ?item wdt:P31 ?cls }}
  OPTIONAL {{ ?item wdt:P582 ?e }}
}}"""


def run_slice(job, a, b, depth=0):
    path = os.path.join(OUT, f"{job}_{a}_{b}.csv")
    if os.path.exists(path):
        return
    if job == "p585":
        q = q_direct("P585", a, b, 0)
    elif job == "p580":
        q = q_direct("P580", a, b, 0)
    elif job == "p571":
        q = q_direct("P571", a, b, 1 if a < 1500 else (3 if a < 1800 else 8))
    elif job == "loc585":
        q = q_loc("P585", a, b, 1 if a < 1900 else 2)
    elif job == "loc580":
        q = q_loc("P580", a, b, 1 if a < 1900 else 2)
    else:
        raise ValueError(job)
    t = time.time()
    try:
        txt = sparql(q)
    except Timeout:
        if b - a <= 1:
            print(f"  GIVE UP {job} {a}..{b}", flush=True)
            open(path + ".failed", "w").close()
            return
        m = (a + b) // 2
        print(f"  timeout {job} {a}..{b} -> split at {m}", flush=True)
        run_slice(job, a, m, depth + 1)
        run_slice(job, m, b, depth + 1)
        return
    n = max(0, txt.count("\n") - 1)
    with open(path, "w", encoding="utf-8") as f:
        f.write(txt)
    print(f"{job} {a}..{b}: {n} rows in {time.time() - t:.1f}s", flush=True)
    time.sleep(1.0)


def bounds(job):
    b = [-12000, -1000, 0, 500, 1000, 1200, 1400, 1500, 1600, 1700, 1750, 1800, 1825, 1850, 1875, 1900]
    if job == "p571":
        return b
    b += list(range(1910, 2021, 10)) + [2027]
    return b


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    jobs = sys.argv[1:] or ["p585", "p580", "loc585", "loc580", "p571"]
    for job in jobs:
        bs = bounds(job)
        for a, b in zip(bs, bs[1:]):
            run_slice(job, a, b)
    print("DONE", jobs, flush=True)
