"""Download the non-Wikidata sources into data/raw/ext/<source>/ (skips files that already exist).

Each source keeps its own directory. See pipeline/external.py for how they are parsed.
"""
import json
import os
import sys
import time

import requests

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
EXT = os.path.join(ROOT, "data", "raw", "ext")
S = requests.Session()
S.headers["User-Agent"] = "GeoHistoryAtlas/0.2 (educational mapping project; python-requests)"


def get(url, path, **kw):
    path = os.path.join(EXT, path)
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return path
    os.makedirs(os.path.dirname(path), exist_ok=True)
    for attempt in range(4):
        try:
            with S.get(url, stream=True, timeout=120, **kw) as r:
                r.raise_for_status()
                with open(path + ".part", "wb") as f:
                    for chunk in r.iter_content(1 << 20):
                        f.write(chunk)
            os.replace(path + ".part", path)
            print("ok ", path, os.path.getsize(path), flush=True)
            return path
        except requests.RequestException as e:
            print("retry", url, e, flush=True)
            time.sleep(3 * (attempt + 1))
    print("FAILED", url, flush=True)
    return None


def paged(base, path, per=200):
    """NOAA HazEL API: collect all pages into one JSON list."""
    full = os.path.join(EXT, path)
    if os.path.exists(full):
        return
    os.makedirs(os.path.dirname(full), exist_ok=True)
    items, page, total = [], 1, 1
    while page <= total:
        r = S.get(base, params={"page": page, "itemsPerPage": per}, timeout=120)
        r.raise_for_status()
        d = r.json()
        items += d["items"]
        total = d.get("totalPages", 1)
        page += 1
        time.sleep(0.2)
    json.dump(items, open(full, "w", encoding="utf-8"))
    print("ok ", full, len(items), "items", flush=True)


SOURCES = {
    "noaa": lambda: [
        paged("https://www.ngdc.noaa.gov/hazel/hazard-service/api/v1/earthquakes", "noaa/earthquakes.json"),
        paged("https://www.ngdc.noaa.gov/hazel/hazard-service/api/v1/tsunamis/events", "noaa/tsunamis.json"),
        paged("https://www.ngdc.noaa.gov/hazel/hazard-service/api/v1/volcanoes", "noaa/volcanoes.json"),
    ],
    "gvp": lambda: get("https://webservices.volcano.si.edu/geoserver/GVP-VOTW/ows?service=WFS&version=1.0.0&request=GetFeature"
                       "&typeName=GVP-VOTW:Smithsonian_VOTW_Holocene_Eruptions&outputFormat=application/json", "gvp/eruptions.json"),
    "plague": lambda: get("https://www.envidat.ch/dataset/2a2b8c5f-c60c-4902-871b-564869addd07/resource/"
                          "2b3fba3b-34e0-4202-8fe4-e3056e6719d0/download/historicalplagueoutbreaks.zip", "plague/plague.zip"),
    "ucdp": lambda: get("https://ucdp.uu.se/downloads/ged/ged261-csv.zip", "ucdp/ged261-csv.zip"),
    "chinawar": lambda: get("https://chinawarfare.pages.dev/data/battles-master.xlsx", "chinawar/battles-master.xlsx"),
    "itinere": lambda: get("https://zenodo.org/api/records/17122148/files/itinere_roads.gpkg/content", "itinere/itinere_roads.gpkg"),
    "aadr": lambda: get("https://dataverse.harvard.edu/api/access/datafile/13994515", "aadr/v66.p1_1240K.aadr.PUB.anno"),
    "hced": lambda: get("https://dataverse.harvard.edu/api/access/datafile/13390255?format=original", "hced/hced_v3.csv"),
    "reaches": lambda: [get("https://www.ncei.noaa.gov/pub/data/paleo/historical/asia/china/reaches/" + f, "reaches/" + f)
                        for f in ("reachesv3.1data.txt", "reachesv3.1codes-haz.txt", "reachesv3.1codes-met.txt",
                                  "reachesv3.1codes-other.txt", "readme-reaches.txt")],
    "cliwoc": lambda: get("https://www.historicalclimatology.com/downloads/cliwoc21-data.zip", "cliwoc/cliwoc21-data.zip"),
    "itinere_geojson": lambda: get("https://zenodo.org/api/records/17122148/files/itinere_roads.geojson/content", "itinere/itinere_roads.geojson"),
    "cbdb": lambda: get("https://huggingface.co/datasets/cbdb/cbdb-sqlite/resolve/main/latest.zip", "cbdb/latest.zip"),
    "slave": lambda: [get("https://www.slavevoyages.org/documents/download/tastdb-exp-2020.sav", "slave/tastdb-exp-2020.sav"),
                      get("https://www.slavevoyages.org/documents/download/I-Am1.0.csv", "slave/I-Am1.0.csv")],
}

if __name__ == "__main__":
    for name in (sys.argv[1:] or SOURCES):
        try:
            SOURCES[name]()
        except Exception as e:  # keep going: one unreachable source must not block the others
            print("ERROR", name, e, flush=True)
    print("DONE", flush=True)
