"""Parse the non-Wikidata sources (downloaded by fetch_external.py) into normalised records.

Outputs (data/work):
  ext_events.json  events to merge into the event layer (build_events.py)
  ext_sites.json   dated sites to merge into the settlement layer (build_settlements.py)
and web/data/lines.json: roads, routes and ship tracks with a validity period.

Event record: n name, d note, y year, e end year (0 = same), md month*100+day, lon, lat, c category,
  t type label, s importance (same scale as Wikipedia language count), src source key, u id at the source,
  pr position precision (0 own point, 1 place-level), np 1 = prefix the name with the modern place name.
Years: negative = BCE.
"""
import ast
import csv
import io
import json
import math
import os
import re
import sqlite3
import sys
import zipfile

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
EXT = os.path.join(ROOT, "data", "raw", "ext")
WORK = os.path.join(ROOT, "data", "work")
OUT = os.path.join(ROOT, "web", "data")
csv.field_size_limit(10**9)

# key -> (display name, licence note, link template; {u} = id at the source)
SOURCES = {
    "wd": ("Wikidata", "CC0", "https://www.wikidata.org/wiki/Q{u}"),
    "cnwar": ("《中国历代战争年表》（Warfare of Imperial China 数字化）", "原书版权归解放军出版社", "https://chinawarfare.pages.dev/"),
    "hced": ("HCED 历史冲突事件数据集", "CC0", "https://doi.org/10.7910/DVN/6ZFC0V"),
    "noaa_eq": ("NOAA NCEI 重大地震数据库", "美国政府公开数据", "https://www.ngdc.noaa.gov/hazel/view/hazards/earthquake/event-more-info/{u}"),
    "noaa_ts": ("NOAA NCEI 历史海啸数据库", "美国政府公开数据", "https://www.ngdc.noaa.gov/hazel/view/hazards/tsunami/event-more-info/{u}"),
    "noaa_vo": ("NOAA NCEI 重大火山喷发数据库", "美国政府公开数据", "https://www.ngdc.noaa.gov/hazel/view/hazards/volcano/event-more-info/{u}"),
    "gvp": ("史密森尼学会全球火山计划（GVP）", "GVP 使用条款，需署名", "https://volcano.si.edu/volcano.cfm?vn={u}"),
    "plague": ("欧洲鼠疫暴发数据（Büntgen & Ginzler，据 Biraben）", "ODbL", "https://doi.org/10.16904/envidat.181"),
    "ucdp": ("UCDP 地理参照事件数据集 GED 26.1", "需署名", "https://ucdp.uu.se/"),
    "reaches": ("REACHES（据《中国三千年气象记录总集》）", "NOAA 古气候数据中心公开数据", "https://www.ncei.noaa.gov/pub/data/paleo/historical/asia/china/reaches/"),
}


def E(n, y, lon, lat, c, t, src, u="", d="", e=0, md=0, s=1, pr=0, np_=0):
    return {"n": n[:70], "d": d[:110], "y": int(y), "e": int(e or 0), "md": int(md or 0), "lon": round(float(lon), 4),
            "lat": round(float(lat), 4), "c": c, "t": t, "s": int(s), "src": src, "u": str(u), "pr": pr, "np": np_}


def ok_pt(lon, lat):
    return lon is not None and lat is not None and -180 <= lon <= 180 and -85 <= lat <= 85 and not (lon == 0 and lat == 0)


def title(s):
    return re.sub(r"\s+", " ", " ".join(w.capitalize() if w.isupper() else w for w in re.split(r"(\W+)", s or ""))).replace(" :", ":").strip()


# ------------------------------------------------------------------ events
def hced():
    out = []
    for r in csv.DictReader(open(os.path.join(EXT, "hced", "hced_v3.csv"), encoding="utf-8", errors="replace")):
        try:
            lat, lon = float(r["Latitude"]), float(r["Longitude"])
        except ValueError:
            continue
        m = re.fullmatch(r"(-?\d+)(?:-(\d+))?", r["Year"].strip())
        if not m or not ok_pt(lon, lat):
            continue
        y = int(m.group(1))
        e = int(m.group(2)) if m.group(2) else 0
        if y < 0 and e:
            e = -e
        name = r["Battle"].strip()
        if not name:
            continue
        if not re.search(r"\b(Battle|Siege|Sack|Raid|Massacre|Capture|Fall|War|Revolt|Rebellion|Campaign)\b", name, re.I):
            name += " 之战"

        def lst(v):
            try:
                x = ast.literal_eval(v)
                return "、".join(str(i) for i in x) if isinstance(x, list) else str(x)
            except (ValueError, SyntaxError):
                return v

        d = []
        if r.get("War") and r["War"] not in ("[]", "NA"):
            d.append("所属战争：" + lst(r["War"]))
        if r.get("Winner") and r["Winner"] != "NA":
            d.append("胜方：" + r["Winner"] + (("；负方：" + r["Loser"]) if r.get("Loser") and r["Loser"] != "NA" else ""))
        try:
            scale = int(float(r.get("Lehmann Zhukov Scale") or 0))
        except ValueError:
            scale = 0
        t = "屠杀" if r.get("Massacre") == "Yes" else ("海战" if r.get("Theatre") == "Sea" else "战役")
        out.append(E(name, y, lon, lat, 0, t, "hced", r["ID"], "；".join(d), e=e, s=1 + 2 * scale))
    return out


def chinawar():
    import openpyxl
    wb = openpyxl.load_workbook(os.path.join(EXT, "chinawar", "battles-master.xlsx"), read_only=True)
    ws = [w for w in wb.worksheets if w.title.startswith("All Battles")][0]
    out, started = [], False
    conf = {"high": "高", "medium": "中", "low": "低"}
    for r in ws.iter_rows(values_only=True):
        if not started:
            started = bool(r and r[0] == "Battle")
            continue
        if not r or not r[0]:
            continue
        d = str(r[1]).strip()
        nums = [int(x) for x in re.findall(r"\d+", d)]
        if not nums:
            continue
        bc = d.startswith("前")
        if "世纪" in d:
            y, e = (-(nums[0] * 100 - 50) if bc else nums[0] * 100 - 50), 0
        else:
            y = -nums[0] if bc else nums[0]
            e = (-nums[1] if bc else nums[1]) if len(nums) > 1 else 0
        try:
            lon, lat = float(r[7]), float(r[8])
        except (TypeError, ValueError):
            continue
        if not ok_pt(lon, lat):
            continue
        note = "、".join(str(x) for x in (r[2], r[4]) if x)
        note += f"；《中国历代战争年表》{'上' if str(r[5]) == '1' else '下'}卷第{r[6]}页；定位可信度：{conf.get(str(r[9]), '中')}"
        out.append(E(str(r[0]), y, lon, lat, 0, "战役", "cnwar", "", note, e=e, s=4 if str(r[9]) == "high" else 3, pr=1))
    return out


DEATH_ORDER = {1: "少量（1–50 人）", 2: "51–100 人", 3: "101–1000 人", 4: "千人以上"}
TS_CAUSE = {1: "地震", 2: "疑似地震", 3: "地震与滑坡", 4: "火山与地震", 5: "火山、地震与滑坡", 6: "火山", 7: "火山与滑坡",
            8: "滑坡", 9: "气象", 10: "爆炸", 11: "天文潮"}


def deaths(x):
    if x.get("deaths"):
        return f"死亡约 {x['deaths']} 人"
    o = x.get("deathsAmountOrder")
    return "死亡：" + DEATH_ORDER[o] if o in DEATH_ORDER else ""


def noaa():
    out = []
    md = lambda x: (x.get("month") or 0) * 100 + (x.get("day") or 0) if x.get("month") and x.get("day") else 0
    for x in json.load(open(os.path.join(EXT, "noaa", "earthquakes.json"))):
        lon, lat = x.get("longitude"), x.get("latitude")
        if not ok_pt(lon, lat) or x.get("year") is None:
            continue
        mag = x.get("eqMagnitude")
        do = x.get("deathsAmountOrder") or 0
        d = "；".join(v for v in (deaths(x), "并引发海啸" if x.get("tsunamiEventId") else "", f"烈度 {x['intensity']}" if x.get("intensity") else "") if v)
        s = 2 + 4 * do + (4 if (mag or 0) >= 7.5 else 2 if (mag or 0) >= 6.5 else 0)
        out.append(E(title(x.get("locationName") or x.get("country") or "") + " 地震" + (f"（M{mag}）" if mag else ""),
                     x["year"], lon, lat, 2, "地震", "noaa_eq", x["id"], d, md=md(x), s=s))
    for x in json.load(open(os.path.join(EXT, "noaa", "tsunamis.json"))):
        lon, lat = x.get("longitude"), x.get("latitude")
        if not ok_pt(lon, lat) or x.get("year") is None or x.get("earthquakeEventId") or (x.get("eventValidity") or 0) < 3:
            continue
        d = "；".join(v for v in ("成因：" + TS_CAUSE[x["causeCode"]] if x.get("causeCode") in TS_CAUSE else "", deaths(x)) if v)
        out.append(E(title(x.get("locationName") or x.get("country") or "") + " 海啸", x["year"], lon, lat, 2, "海啸", "noaa_ts",
                     x["id"], d, md=md(x), s=3 + 4 * (x.get("deathsAmountOrder") or 0)))
    for x in json.load(open(os.path.join(EXT, "noaa", "volcanoes.json"))):
        lon, lat = x.get("longitude"), x.get("latitude")
        if not ok_pt(lon, lat) or x.get("year") is None:
            continue
        vei = x.get("vei")
        d = "；".join(v for v in (x.get("location") or "", deaths(x)) if v)
        out.append(E(f"{x.get('name')} 火山喷发" + (f"（VEI {vei}）" if vei is not None else ""), x["year"], lon, lat, 2, "火山喷发",
                     "noaa_vo", x["id"], d, md=md(x), s=4 + 2 * (vei or 0) + 3 * (x.get("deathsAmountOrder") or 0)))
    return out


def gvp(have):
    out = []
    for f in json.load(open(os.path.join(EXT, "gvp", "eruptions.json")))["features"]:
        p = f["properties"]
        vei, y = p.get("ExplosivityIndexMax"), p.get("StartDateYear")
        if p.get("Activity_Type") != "Confirmed Eruption" or vei is None or vei < 3 or y is None or not f.get("geometry"):
            continue
        lon, lat = f["geometry"]["coordinates"][:2]
        name = p["Volcano_Name"]
        if any((name.lower(), y + k) in have for k in (-1, 0, 1)) or not ok_pt(lon, lat):
            continue
        md = p["StartDateMonth"] * 100 + p["StartDateDay"] if p.get("StartDateMonth") and p.get("StartDateDay") else 0
        e = p.get("EndDateYear") if p.get("EndDateYear") and p["EndDateYear"] > y else 0
        out.append(E(f"{name} 火山喷发（VEI {vei}）", y, lon, lat, 2, "火山喷发", "gvp", p["Volcano_Number"], "", e=e, md=md, s=vei * 3 - 4))
    return out


def plague():
    z = zipfile.ZipFile(os.path.join(EXT, "plague", "plague.zip"))
    txt = z.read(z.namelist()[0]).decode("latin-1")
    out = []
    for r in csv.DictReader(io.StringIO(txt)):
        try:  # the two WGS84 columns are swapped in the published file
            lon, lat, y = float(r["Lat_WGS84"]), float(r["Lon_WGS84"]), int(r["Year_of_Outbreak"])
        except ValueError:
            continue
        if ok_pt(lon, lat):
            out.append(E(r["Location"].strip() + " 鼠疫暴发", y, lon, lat, 2, "鼠疫暴发", "plague", "", "据 Biraben 的欧洲鼠疫暴发清单", s=1, pr=1))
    return out


def ucdp(min_deaths=50):
    z = zipfile.ZipFile(os.path.join(EXT, "ucdp", "ged261-csv.zip"))
    kinds = {"1": "武装冲突事件", "2": "非国家武装冲突事件", "3": "针对平民的暴力事件"}
    out = []
    with z.open(z.namelist()[0]) as f:
        for r in csv.DictReader(io.TextIOWrapper(f, encoding="utf-8")):
            try:
                best = int(r["best"])
                if best < min_deaths or r["where_prec"] not in ("1", "2", "3"):
                    continue
                lon, lat = float(r["longitude"]), float(r["latitude"])
            except ValueError:
                continue
            if not ok_pt(lon, lat):
                continue
            ds, de = r["date_start"][:10], r["date_end"][:10]
            y, md = int(ds[:4]), int(ds[5:7]) * 100 + int(ds[8:10])
            where = (r.get("where_coordinates") or r.get("adm_2") or r.get("adm_1") or r["country"]).strip()
            out.append(E(f"{where}：{r['dyad_name']}", y, lon, lat, 0, kinds.get(r["type_of_violence"], "武装冲突事件"), "ucdp", r["id"],
                         f"死亡约 {best} 人（最佳估计）；{r['conflict_name']}", e=int(de[:4]) if de[:4] != ds[:4] else 0, md=md,
                         s=2 + min(20, int(math.log10(best) * 5)), pr=0 if r["where_prec"] == "1" else 1))
    return out


def reaches():
    """County-level hazard records for Ming-Qing China: one event per place, year and hazard type."""
    kinds = {"30": "旱灾", "31": "水灾", "32": "蝗灾", "34": "疫病", "35": "饥荒"}
    agg = {}
    with open(os.path.join(EXT, "reaches", "reachesv3.1data.txt"), encoding="utf-8", errors="replace") as f:
        cols = None
        for line in f:
            if line.startswith("#"):
                continue
            p = line.rstrip("\n").split("\t")
            if cols is None:
                cols = {c: i for i, c in enumerate(p)}
                continue
            try:
                y = int(p[cols["year_greg_st"]])
                lon, lat = float(p[cols["place_longit"]]), float(p[cols["place_latitu"]])
            except (ValueError, IndexError):
                continue
            if y < 0 or not ok_pt(lon, lat):
                continue
            mo, da = p[cols["mon_greg_st"]], p[cols["date_greg_st"]]
            for code in p[cols["event_code"]].split(";"):
                code = code.strip()
                if len(code) != 9 or code[:2] not in kinds or code[7] == "8":  # 8 = "did not happen"
                    continue
                k = (y, round(lon, 2), round(lat, 2), code[:2])
                a = agg.setdefault(k, [0, 0, 0])
                a[0] += 1
                a[1] = max(a[1], 1 if code[7] == "2" else 0)
                if not a[2] and mo.isdigit() and da.isdigit() and 0 < int(mo) < 13 and 0 < int(da) < 32:
                    a[2] = int(mo) * 100 + int(da)
    out = []
    for (y, lon, lat, k), (n, heavy, md) in agg.items():
        out.append(E(kinds[k], y, lon, lat, 2, kinds[k], "reaches", "", f"史料记载 {n} 条" + ("，程度重" if heavy else "") + "；坐标为今县级治所",
                     md=md, s=2 if heavy else 1, pr=1, np_=1))
    return out


# ------------------------------------------------------------------ sites
C14 = [(0, 0), (1000, 930), (2000, 1950), (3000, 3200), (4000, 4480), (5000, 5730), (6000, 6840), (7000, 7840), (8000, 8870),
       (9000, 10190), (10000, 11480), (12000, 13870), (15000, 18250), (20000, 24050), (30000, 34500), (50000, 52000)]


def cal_year(bp):
    """Rough IntCal20 conversion of an uncalibrated 14C age to a calendar year (negative = BCE)."""
    bp = max(0.0, min(50000.0, bp))
    for (a0, c0), (a1, c1) in zip(C14, C14[1:]):
        if bp <= a1:
            return int(round(1950 - (c0 + (c1 - c0) * (bp - a0) / (a1 - a0))))
    return -50050


def thurayya():
    kinds = {"metropoles": "都会", "capitals": "首府", "towns": "城镇", "villages": "村落", "waystations": "驿站", "sites": "遗址"}
    d = json.load(open(os.path.join(EXT, "althurayya.github.io", "master", "places.geojson"), encoding="utf-8"))
    out = []
    for f in d["features"]:
        c = f["properties"].get("cornuData", {})
        if c.get("top_type_hom") not in kinds:
            continue
        lon, lat = f["geometry"]["coordinates"][:2]
        name = c.get("toponym_translit") or c.get("toponym_search") or ""
        if name and ok_pt(lon, lat):
            out.append([f"{name}（{c.get('toponym_arabic', '')}）", lon, lat, 650, 1000, 3, kinds[c["top_type_hom"]],
                        f"早期伊斯兰世界地名；{c.get('region_spelled', '')}", c.get("cornu_URI", ""), 1])
    return out


def p3k():
    import pyreadr
    df = list(pyreadr.read_r(os.path.join(EXT, "p3k_p3k14c", "data", "p3k14c_data.rda")).values())[0]
    sites = {}
    for r in df.itertuples(index=False):
        try:
            lon, lat, age = float(r.Long), float(r.Lat), float(r.Age)
        except (TypeError, ValueError):
            continue
        if not ok_pt(lon, lat) or not (0 < age <= 50000):
            continue
        name = str(r.SiteName).strip() if r.SiteName is not None and str(r.SiteName) != "nan" else ""
        k = (name, round(lon, 3), round(lat, 3))
        s = sites.setdefault(k, [age, age, 0, str(r.Country), str(r.SiteID)])
        s[0], s[1], s[2] = min(s[0], age), max(s[1], age), s[2] + 1
    out = []
    for (name, lon, lat), (young, old, n, country, sid) in sites.items():
        fuzz = "；坐标已模糊到县一级" if country in ("USA", "Canada", "United States") else ""
        out.append([name or "未命名遗址", lon, lat, cal_year(old), cal_year(young), 4, "考古遗址",
                    f"{n} 个碳十四测年，年代为粗略校正值；{country}{fuzz}", sid if sid != "nan" else "", 0])
    return out


def aadr():
    sites = {}
    with open(os.path.join(EXT, "aadr", "v66.p1_1240K.aadr.PUB.anno"), encoding="utf-8", errors="replace") as f:
        f.readline()
        for line in f:
            p = line.rstrip("\n").split("\t")
            try:
                mean, sd, lat, lon = float(p[10]), float(p[11] or 0), float(p[17]), float(p[18])
            except (ValueError, IndexError):
                continue
            if mean <= 0 or not ok_pt(lon, lat):
                continue  # present-day individuals
            k = (p[15].strip(), round(lon, 2), round(lat, 2))
            s = sites.setdefault(k, [1e9, -1e9, 0, set(), p[16].strip()])
            s[0], s[1], s[2] = min(s[0], 1950 - mean - sd), max(s[1], 1950 - mean + sd), s[2] + 1
            s[3].add(p[14].split(".")[0])
    out = []
    for (loc, lon, lat), (a, b, n, groups, pol) in sites.items():
        g = "、".join(sorted(groups)[:3])
        out.append([loc or "未命名地点", lon, lat, int(a), int(b), 5, "古人类遗骸", f"{n} 个古 DNA 样本；{pol}；人群标签：{g}", "", 0])
    return out


# ------------------------------------------------------------------ lines
def gpkg_geom(blob):
    from shapely import wkb
    flags = blob[3]
    env = {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}[(flags >> 1) & 7]
    return wkb.loads(bytes(blob[8 + env:]))


def line_feats(geom, props, tol):
    g = geom.simplify(tol, preserve_topology=False) if tol else geom
    parts = list(g.geoms) if g.geom_type.startswith("Multi") else [g]
    feats = []
    for part in parts:
        if part.geom_type != "LineString" or len(part.coords) < 2:
            continue
        feats.append({"type": "Feature", "properties": props,
                      "geometry": {"type": "LineString", "coordinates": [[round(x, 2), round(y, 2)] for x, y, *_ in part.coords]}})
    return feats


def merc_to_ll(x, y, z=None):
    """EPSG:3395 (World Mercator on WGS84) -> longitude, latitude."""
    a, e = 6378137.0, 0.0818191908426215
    ts = math.exp(-y / a)
    phi = math.pi / 2 - 2 * math.atan(ts)
    for _ in range(6):
        phi = math.pi / 2 - 2 * math.atan(ts * ((1 - e * math.sin(phi)) / (1 + e * math.sin(phi))) ** (e / 2))
    return (math.degrees(x / a), math.degrees(phi))


def lines():
    from shapely.geometry import LineString, shape
    from shapely.ops import transform
    feats = []
    it = json.load(open(os.path.join(EXT, "itinere", "itinere_roads.geojson"), encoding="utf-8"))
    n0 = len(feats)
    for f in it["features"]:
        if not f.get("geometry"):
            continue
        p = f["properties"]
        cert = p.get("Segment_s") or p.get("Segment_ce") or ""
        g = transform(merc_to_ll, shape(f["geometry"]).simplify(2500, preserve_topology=False))  # source is EPSG:3395, metres
        feats += line_feats(g, {"k": 0, "a": -300, "b": 600, "n": p.get("Name") or "", "c": 0 if cert == "Certain" else 1}, 0)
    print("  itiner-e segments", len(feats) - n0)
    n0 = len(feats)
    ro = json.load(open(os.path.join(EXT, "althurayya.github.io", "master", "routes.json"), encoding="utf-8"))
    for f in ro["features"]:
        if f.get("geometry") and f["geometry"]["type"] == "LineString":
            feats += line_feats(shape(f["geometry"]), {"k": 1, "a": 650, "b": 1000, "n": ""}, 0.01)
    print("  al-Thurayya routes", len(feats) - n0)
    n0 = len(feats)
    p = os.path.join(EXT, "cliwoc", "cliwoc21.gpkg")
    if not os.path.exists(p):
        zipfile.ZipFile(os.path.join(EXT, "cliwoc", "cliwoc21-data.zip")).extract("cliwoc21.gpkg", os.path.join(EXT, "cliwoc"))
    con = sqlite3.connect(p)
    cols = [r[1] for r in con.execute('pragma table_info("CLIWOC21")')]
    pick = lambda *names: next((c for c in names if c in cols), None)
    ship, vfrom, vto, vini, nat = pick("ShipName"), pick("VoyageFrom"), pick("VoyageTo"), pick("VoyageIni"), pick("Nationality")
    q = f'select "{ship}", "{vfrom}", "{vto}", "{vini}", "{nat}", YR, MO, DY, latitude, longitude from CLIWOC21 ' \
        f'where latitude is not null and longitude is not null order by "{ship}", "{vini}", YR, MO, DY'
    cur, pts, key = None, [], None

    def flush():
        if key is None or len(pts) < 4:
            return
        seg = [pts[0]]
        segs = []
        for a, b in zip(pts, pts[1:]):
            if abs(b[0] - a[0]) > 12 or abs(b[1] - a[1]) > 12:  # date-line crossing or a bad position: break the track
                segs.append(seg)
                seg = []
            seg.append(b)
        segs.append(seg)
        nm = f"{key[0]}：{key[1] or '?'} → {key[2] or '?'}（{key[4] or ''}）"
        for sg in segs:
            if len(sg) >= 3:
                feats.extend(line_feats(LineString([(x, y) for x, y, _ in sg]), {"k": 2, "a": sg[0][2], "b": sg[-1][2], "n": nm}, 0.25))

    for s, vf, vt, vi, na, yr, mo, dy, lat, lon in con.execute(q):
        k = (s, vf, vt, vi, na)
        if k != key:
            flush()
            key, pts = k, []
        if ok_pt(lon, lat) and yr:
            pts.append((lon, lat, int(yr)))
    flush()
    print("  CLIWOC tracks", len(feats) - n0)
    path = os.path.join(OUT, "lines.json")
    json.dump({"type": "FeatureCollection", "features": feats}, open(path, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print("wrote", path, os.path.getsize(path) // 1024, "KB", len(feats), "features")


def main():
    os.makedirs(WORK, exist_ok=True)
    what = sys.argv[1:] or ["events", "sites", "lines"]
    if "events" in what:
        ev = []
        for name, fn in (("cnwar", chinawar), ("hced", hced), ("noaa", noaa), ("plague", plague), ("ucdp", ucdp), ("reaches", reaches)):
            try:
                r = fn()
                print(f"  {name}: {len(r)}", flush=True)
                ev += r
            except Exception as e:
                print(f"  {name}: FAILED {type(e).__name__}: {e}", flush=True)
        try:
            have = {(re.sub(r" 火山喷发.*", "", x["n"]).lower(), x["y"]) for x in ev if x["src"] == "noaa_vo"}
            r = gvp(have)
            print(f"  gvp: {len(r)}", flush=True)
            ev += r
        except Exception as e:
            print("  gvp: FAILED", e, flush=True)
        json.dump({"sources": SOURCES, "events": ev}, open(os.path.join(WORK, "ext_events.json"), "w", encoding="utf-8"), ensure_ascii=False)
        print("ext_events.json", len(ev))
    if "sites" in what:
        st = []
        for name, fn in (("thurayya", thurayya), ("p3k14c", p3k), ("aadr", aadr)):
            try:
                r = fn()
                print(f"  {name}: {len(r)}", flush=True)
                st += r
            except Exception as e:
                print(f"  {name}: FAILED {type(e).__name__}: {e}", flush=True)
        json.dump(st, open(os.path.join(WORK, "ext_sites.json"), "w", encoding="utf-8"), ensure_ascii=False)
        print("ext_sites.json", len(st))
    if "lines" in what:
        lines()


if __name__ == "__main__":
    main()
