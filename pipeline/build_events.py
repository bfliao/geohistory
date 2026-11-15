"""Clean + structure Wikidata rows into the event layer.

Steps: parse raw slices -> classify by P31 class ancestry -> fetch labels (cached) -> attach nearest modern
place (GeoNames cities1000, with admin1/admin2/country) -> write web/data/events.json (columnar, sorted by year)
and data/work/wd_settlements.json (settlements with inception, for the settlement layer).

Categories: 0 战争与冲突, 1 政治, 2 灾害与事故, 3 建城与建造, 4 文化与科技, 5 其他
Years: negative = BCE (no year 0).
"""
import csv
import glob
import json
import math
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from opencc import OpenCC
from scipy.spatial import cKDTree

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fetch_wikidata import sparql, Timeout  # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
RAW = os.path.join(ROOT, "data", "raw")
WORK = os.path.join(ROOT, "data", "work")
OUT = os.path.join(ROOT, "web", "data")
T2S = OpenCC("t2s")
TYPE_ZH = {
    "seat of the local council": "地方议会驻地", "rescue excavation": "抢救性考古发掘", "naval battle": "海战", "castle ruin": "城堡遗址",
    "constituent locality": "下辖聚落", "revolt": "起义", "unexplained disappearance": "不明失踪", "eastern orthodox monastery": "东正教修道院",
    "work settlement of Russia": "俄罗斯工人镇", "suicide bombing": "自杀式爆炸袭击", "village in Armenia": "亚美尼亚村庄",
    "monastery ruins": "修道院遗址", "sack": "洗劫", "Cistercian monastery": "熙笃会修道院", "city fire": "城市大火", "skirmish": "小规模战斗",
    "benedictine abbey": "本笃会修道院", "truck bombing": "卡车炸弹袭击", "military convoy": "军事护航", "ethnic riot": "族群骚乱",
    "friary": "托钵修会修道院", "Catholic parish church": "天主教堂区教堂", "underwater nuclear explosion": "水下核爆",
    "Lutheran cathedral": "路德宗主教座堂", "atmospheric nuclear test": "大气层核试验", "border incident": "边境事件",
    "international conference": "国际会议", "war phase": "战争阶段", "naval blockade": "海上封锁", "UFO sighting": "不明飞行物目击",
    "tailings dam failure": "尾矿坝溃坝", "train fire": "列车火灾", "witch trial": "女巫审判", "plague epidemic": "鼠疫疫情",
    "border conflict": "边境冲突", "level crossing collision": "道口相撞事故", "tram accident": "有轨电车事故", "storming": "攻占",
    "pronunciamiento": "军人政变宣言", "conference": "会议", "mine explosion": "矿井爆炸", "legendary battle": "传说中的战役",
    "crowd crush": "踩踏事故", "city": "城市", "village": "村庄", "massacre of civilians": "屠杀平民", "aerial bombing": "空袭轰炸",
    "smallpox epidemic": "天花疫情", "state in the Holy Roman Empire": "神圣罗马帝国邦国", "nunnery": "女修道院", "church ruin": "教堂遗址",
    "wooden church": "木教堂", "fortified house": "设防宅邸", "destroyed church": "被毁教堂", "coastal tower": "海岸塔楼",
    "defensive tower": "防御塔", "stronghold": "要塞", "former monastery": "前修道院", "tunnel fire": "隧道火灾",
    "stadium disaster": "体育场事故", "ground collision": "地面相撞事故", "commercial treaty": "通商条约", "Hellenistic kingdom": "希腊化王国",
    "Boer republic": "布尔共和国", "deserted castle site": "废弃城堡遗址", "naval bombing of a city": "海上炮击城市", "former convent": "前修道院",
    "demolished synagogue": "被拆毁的犹太会堂", "Franciscan friary": "方济各会修道院", "hermitage church": "隐修教堂",
    "Cistercian nunnery": "熙笃会女修道院", "Trappist monastery": "特拉普会修道院", "benedictine nunnery": "本笃会女修道院",
    "attack on church": "袭击教堂", "attack on mosque": "袭击清真寺", "train attack": "列车袭击", "university shooting": "校园枪击",
    "nuclear test series": "系列核试验", "Royal abbey": "王室修道院", "capitol building": "议会大厦", "district town": "县城",
    "urban-type settlement in Ukraine": "乌克兰城镇型聚落", "Roman Catholic metropolitan archdiocese": "天主教都主教区",
    "former municipality of Switzerland": "瑞士前市镇", "parish municipality": "堂区市镇", "township municipality": "镇区市镇",
}

# (root class, category) in priority order
KEEP = [
    ("Q7944", 2), ("Q7692360", 2), ("Q8068", 2), ("Q8070", 2), ("Q8081", 2), ("Q8092", 2), ("Q167903", 2), ("Q7935", 2),
    ("Q44512", 2), ("Q168247", 2), ("Q744913", 2), ("Q1078765", 2), ("Q906512", 2), ("Q1550225", 2), ("Q9687", 2),
    ("Q3199915", 0), ("Q2223653", 0), ("Q21480300", 0), ("Q41397", 0), ("Q3882219", 0), ("Q750215", 0),
    ("Q178561", 0), ("Q188055", 0), ("Q1261499", 0), ("Q198", 0), ("Q831663", 0), ("Q2001676", 0), ("Q467011", 0), ("Q645883", 0),
    ("Q131569", 1), ("Q625298", 1), ("Q10931", 1), ("Q45382", 1), ("Q124734", 1), ("Q209715", 1), ("Q1072326", 1),
    ("Q124757", 1), ("Q273120", 1), ("Q175331", 1), ("Q49776", 1),
    ("Q210112", 4), ("Q2401485", 4), ("Q5916", 4), ("Q51645", 4), ("Q111161", 4), ("Q172754", 4), ("Q159821", 4), ("Q82414", 4),
    ("Q132821", 0), ("Q149086", 0), ("Q1174599", 0),
    ("Q7625093", 2), ("Q179057", 2), ("Q8065", 2), ("Q3839081", 2), ("Q171558", 2),
    ("Q350604", 0), ("Q180684", 0),
]
OLYMPIC = {"Q159821", "Q82414"}
DROP = {"Q27020041", "Q13406554", "Q16510064", "Q40231", "Q43109", "Q3887", "Q132241", "Q182832", "Q4504495",
        "Q27968055", "Q2020153", "Q18608583", "Q500834"}
SETTLE = {"Q486972", "Q515", "Q15661340"}
STATE = {"Q3024240", "Q6256"}
BUILT = {"Q23413", "Q16970", "Q44613", "Q3918", "Q24398318", "Q41176", "Q811979", "Q12280", "Q57821", "Q4989906", "Q33506", "Q839954"}
GENERIC = {"Q1190554", "Q1656682", "Q43229", "Q56061"}
KW_DROP = re.compile(r"championship|draft|season|tournament|\bcup\b|olympic|paralympic|contest|league|grand prix|rally|\brace\b|"
                     r"match|\bgame|sport|election|referendum|census|television|concert|festival|award|wikimedia|edition|"
                     r"football|basketball|cycling|racing|eurovision|competition|\bplay\b|rivalry|eclipse|transit|"
                     r"exhibition|salon|biennale|wiki|hockey|roller coaster|sat congress|catchment|album|film|episode|painting|photograph|song|\bbook\b|written work|artwork|stage|grand slam|marathon", re.I)
KW_CAT = [
    (0, re.compile(r"\bwar\b|warfare|battle|siege|raid|attack|bombing|massacre|killing|shooting|murder|terror|genocide|crime|"
                   r"violence|uprising|mutiny|conflict|skirmish|military|invasion|occupation|pogrom|lynching|execution|"
                   r"kidnapping|hijack|ambush|assassination|repression|disappearance|fusillade|persecution|deportation", re.I)),
    (1, re.compile(r"treaty|agreement|convention|accord|congress|coup|revolution|protest|riot|strike|crisis|trial|declaration|"
                   r"inauguration|coronation|abdication|summit|conference|ceasefire|armistice|sovereignty|independence|"
                   r"annexation|proclamation|constitution|demonstration|rebellion|parliament|diet|capitulation|surrender|"
                   r"partition|unification|negotiation|boundary", re.I)),
    (2, re.compile(r"earthquake|eruption|flood|storm|cyclone|hurricane|typhoon|tornado|fire|accident|crash|disaster|explosion|"
                   r"collapse|derailment|sinking|shipwreck|epidemic|pandemic|outbreak|famine|landslide|avalanche|tsunami|"
                   r"drought|heat wave|cold wave|blizzard|nor'easter|cyclogenesis|collision|spill|meteor|bolide|fireball|impact", re.I)),
    (4, re.compile(r"expedition|exploration|voyage|flight|launch|nuclear|discovery|experiment|council|synod|exhibition|"
                   r"fair|pilgrimage|wedding|funeral|apparition|miracle|ceremony|excavation|mission|landing|circumnavigation", re.I)),
]


def parse_year(s):
    m = re.match(r"^(-?)(\d{1,6})-(\d\d)-(\d\d)T", s or "")
    if not m:
        return None
    y = int(m.group(2))
    if m.group(1):
        y = -y
    hist = y if y > 0 else y - 1  # astronomical -> historical (no year 0)
    mo, da = int(m.group(3)), int(m.group(4))
    md = 0 if (mo == 1 and da == 1) or mo == 0 or da == 0 else mo * 100 + da
    return hist, md


def parse_pt(s):
    m = re.match(r"^Point\(([-\d.eE]+) ([-\d.eE]+)\)$", s or "")
    if not m:
        return None
    lon, lat = float(m.group(1)), float(m.group(2))
    if not (-180 <= lon <= 180 and -85 <= lat <= 85):
        return None
    return lon, lat


def read_raw():
    items = {}
    files = sorted(glob.glob(os.path.join(RAW, "wikidata", "*.csv")))
    for f in files:
        job = os.path.basename(f).split("_")[0]
        for r in csv.DictReader(open(f, encoding="utf-8")):
            q = (r.get("item") or "").rsplit("/", 1)[-1]
            if not re.fullmatch(r"Q\d+", q):
                continue
            d = parse_year(r.get("d"))
            pt = parse_pt(r.get("c"))
            if not d or not pt or d[0] < -12000 or d[0] > 2026:
                continue
            it = items.get(q)
            if it is None:
                it = items[q] = {"y": d[0], "md": d[1], "e": None, "pt": pt, "own": not job.startswith("loc"),
                                 "sl": 0, "cls": set(), "jobs": set(), "diss": None}
            it["jobs"].add(job)
            if d[0] < it["y"] and job != "p571":
                it["y"], it["md"] = d
            if not it["own"] and not job.startswith("loc"):
                it["pt"], it["own"] = pt, True
            try:
                it["sl"] = max(it["sl"], int(r.get("sl") or 0))
            except ValueError:
                pass
            c = (r.get("cls") or "").rsplit("/", 1)[-1]
            if re.fullmatch(r"Q\d+", c):
                it["cls"].add(c)
            e = parse_year(r.get("e"))
            if e:
                if job == "p571":
                    it["diss"] = e[0] if it["diss"] is None else max(it["diss"], e[0])
                else:
                    it["e"] = e[0] if it["e"] is None else max(it["e"], e[0])
    return items


def classify(items, classes):
    """Returns {qid: (cat, type_class, is_settlement)}"""
    order = {r: i for i, (r, _) in enumerate(KEEP)}
    catof = dict(KEEP)
    out = {}
    stats = {}
    for q, it in items.items():
        roots = {}  # root -> class that carries it
        en_labels = []
        for c in it["cls"]:
            info = classes.get(c)
            if not info:
                continue
            en_labels.append((c, info.get("en") or ""))
            for r in info["roots"]:
                roots.setdefault(r, c)
        only_inception = it["jobs"] == {"p571"}
        res = None
        if not only_inception:
            if OLYMPIC & roots.keys():
                r = next(iter(OLYMPIC & roots.keys()))
                res = (4, roots[r], False)
            elif DROP & roots.keys() or any(KW_DROP.search(l) for _, l in en_labels):
                res = None
            else:
                hit = [r for r in roots if r in order]
                if hit:
                    r = min(hit, key=order.get)
                    res = (catof[r], roots[r], False)
                else:
                    for cat, rx in KW_CAT:
                        m = [c for c, l in en_labels if rx.search(l)]
                        if m:
                            res = (cat, m[0], False)
                            break
                    if res is None and it["sl"] >= 5 and not (roots.keys() & (SETTLE | BUILT | STATE)) and "p571" not in it["jobs"]:
                        res = (5, en_labels[0][0] if en_labels else None, False)
        if res is None:
            if any(KW_DROP.search(l) for _, l in en_labels) or DROP & roots.keys():
                res = None
            elif SETTLE & roots.keys():
                r = next(iter(SETTLE & roots.keys()))
                res = (3, roots[r], True)
            elif STATE & roots.keys():
                r = next(iter(STATE & roots.keys()))
                res = (1, roots[r], False)
            elif BUILT & roots.keys() and it["sl"] >= (3 if it["y"] < 1500 else 6):
                r = min(BUILT & roots.keys(), key=lambda x: 1 if x in ("Q41176", "Q811979") else 0)
                res = (3, roots[r], False)
            elif "Q56061" in roots and it["sl"] >= 10:
                res = (3, roots["Q56061"], True)
        if res:
            out[q] = res
            stats[res[0]] = stats.get(res[0], 0) + 1
    print("classified", len(out), "of", len(items), "by cat", dict(sorted(stats.items())), flush=True)
    return out


def fetch_labels(qids):
    path = os.path.join(WORK, "labels.json")
    cache = json.load(open(path, encoding="utf-8")) if os.path.exists(path) else {}
    todo = [q for q in qids if q not in cache]
    print("labels: cached", len(cache), "todo", len(todo), flush=True)
    B = 400
    batches = [todo[i:i + B] for i in range(0, len(todo), B)]

    LP = {"zh-hans": 0, "zh-cn": 1, "zh": 2, "zh-hant": 3, "zh-tw": 4, "en": 5}
    langs = ",".join('"%s"' % l for l in LP)

    def work(batch):
        vals = " ".join("wd:" + q for q in batch)
        q = f"""SELECT ?item ?l ?ll ?d ?dl ?s WHERE {{ VALUES ?item {{ {vals} }}
  {{ ?item rdfs:label ?l . BIND(LANG(?l) AS ?ll) FILTER(?ll IN ({langs})) }}
  UNION {{ ?item schema:description ?d . BIND(LANG(?d) AS ?dl) FILTER(?dl IN ({langs})) }}
  UNION {{ ?w schema:about ?item ; schema:isPartOf ?s . FILTER(?s IN (<https://zh.wikipedia.org/>, <https://en.wikipedia.org/>)) }} }}"""
        for attempt in range(3):
            try:
                txt = sparql(q)
            except Timeout:
                time.sleep(5)
                continue
            best = {k: [None, None, 0] for k in batch}  # (prio,label), (prio,desc), wiki
            for r in csv.DictReader(txt.splitlines()):
                k = r["item"].rsplit("/", 1)[-1]
                if k not in best:
                    continue
                b = best[k]
                if r.get("l"):
                    pr = LP.get(r["ll"], 9)
                    if b[0] is None or pr < b[0][0]:
                        b[0] = (pr, r["l"])
                elif r.get("d"):
                    pr = LP.get(r["dl"], 9)
                    if b[1] is None or pr < b[1][0]:
                        b[1] = (pr, r["d"])
                elif r.get("s"):
                    b[2] = 1 if "zh.wikipedia" in r["s"] else (b[2] or 2)
            return {k: [v[0][1] if v[0] else "", v[1][1] if v[1] else "", v[2]] for k, v in best.items()}
        return {}

    done = 0
    with ThreadPoolExecutor(1) as ex:
        for res in ex.map(work, batches):
            cache.update(res)
            done += 1
            if done % 10 == 0:
                json.dump(cache, open(path, "w", encoding="utf-8"), ensure_ascii=False)
                print("  labels", done, "/", len(batches), flush=True)
    json.dump(cache, open(path, "w", encoding="utf-8"), ensure_ascii=False)
    return cache


def load_places():
    gn = os.path.join(RAW, "geonames")
    zh = {}
    p = os.path.join(WORK, "geonames_zh.json")
    if os.path.exists(p):
        zh = json.load(open(p, encoding="utf-8"))
    iso = json.load(open(os.path.join(WORK, "iso_zh.json"), encoding="utf-8")) if os.path.exists(os.path.join(WORK, "iso_zh.json")) else {}
    a1, a2, cn = {}, {}, {}
    for line in open(os.path.join(gn, "admin1CodesASCII.txt"), encoding="utf-8"):
        k, name, _, gid = line.rstrip("\n").split("\t")
        a1[k] = zh.get(gid, name)
    for line in open(os.path.join(gn, "admin2Codes.txt"), encoding="utf-8"):
        k, name, _, gid = line.rstrip("\n").split("\t")
        a2[k] = zh.get(gid, name)
    for line in open(os.path.join(gn, "countryInfo.txt"), encoding="utf-8"):
        if line.startswith("#"):
            continue
        c = line.rstrip("\n").split("\t")
        cn[c[0]] = {"CN": "中国", "TW": "台湾", "HK": "中国香港", "MO": "中国澳门"}.get(c[0]) or iso.get(c[0]) or zh.get(c[16]) or c[4]
    rows = []
    for line in open(os.path.join(gn, "cities1000.txt"), encoding="utf-8"):
        c = line.rstrip("\n").split("\t")
        if c[7] in ("PPLX", "PPLH", "PPLQ", "PPLW"):
            continue
        cc = c[8]
        rows.append((zh.get(c[0], c[1]), a2.get(f"{cc}.{c[10]}.{c[11]}", ""), a1.get(f"{cc}.{c[10]}", ""), cn.get(cc, cc),
                     float(c[5]), float(c[4]), int(c[14] or 0)))
    return rows


def xyz(lon, lat):
    lon = np.radians(lon); lat = np.radians(lat)
    return np.column_stack([np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)])


def assign_places(pts, places):
    P = np.array([(p[4], p[5]) for p in places])
    pop = np.array([p[6] for p in places])
    tree = cKDTree(xyz(P[:, 0], P[:, 1]))
    Q = np.array(pts)
    chord = lambda km: 2 * math.sin(km / 6371.0 / 2)
    dist, idx = tree.query(xyz(Q[:, 0], Q[:, 1]), k=8, distance_upper_bound=chord(40))
    out = np.full(len(pts), -1, dtype=np.int64)
    for i in range(len(pts)):
        d, ix = dist[i], idx[i]
        if not np.isfinite(d[0]):
            continue
        lim = max(chord(6), d[0] * 1.5)
        ok = np.isfinite(d) & (d <= lim)
        cand = ix[ok]
        out[i] = cand[np.argmax(pop[cand])]
    return out


def clean(s, n=None):
    s = T2S.convert(" ".join((s or "").split()))
    if n and len(s) > n:
        s = s[: n - 1] + "…"
    return s


def main():
    os.makedirs(WORK, exist_ok=True)
    classes = json.load(open(os.path.join(WORK, "classes.json"), encoding="utf-8"))
    items = read_raw()
    print("raw items", len(items), flush=True)
    cl = classify(items, classes)
    if "--no-labels" in sys.argv:
        return
    labels = fetch_labels(sorted(cl))
    rows = []
    for q, (cat, tcls, is_settle) in cl.items():
        lab = labels.get(q)
        if not lab or not lab[0] or re.fullmatch(r"Q\d+", lab[0]):
            continue
        it = items[q]
        rows.append((q, it, cat, tcls, is_settle, clean(lab[0], 60), clean(lab[1], 90), lab[2]))
    rows.sort(key=lambda r: (r[1]["y"], -r[1]["sl"]))
    print("events with labels", len(rows), flush=True)

    places = load_places()
    pidx = assign_places([r[1]["pt"] for r in rows], places)
    used = {}
    ptab = []
    pcol = []
    for i in pidx:
        if i < 0:
            pcol.append(-1)
            continue
        if i not in used:
            used[i] = len(ptab)
            p = places[i]
            ptab.append([p[0], p[1], p[2], p[3], round(p[4], 3), round(p[5], 3)])
        pcol.append(used[i])

    types, tix = [], {}

    def tlabel(c):
        if not c or c not in classes:
            return ""
        info = classes[c]
        return clean(info.get("zh") or TYPE_ZH.get(info.get("en") or "") or info.get("en") or "", 30)

    tcol = []
    for r in rows:
        t = tlabel(r[3])
        if t not in tix:
            tix[t] = len(types)
            types.append(t)
        tcol.append(tix[t])

    data = {
        "n": [r[5] for r in rows],
        "d": [r[6] for r in rows],
        "y": [r[1]["y"] for r in rows],
        "e": [(r[1]["e"] if (r[1]["e"] and r[1]["e"] > r[1]["y"] and r[1]["jobs"] != {"p571"}) else 0) for r in rows],
        "md": [r[1]["md"] for r in rows],
        "x": [round(r[1]["pt"][0], 4) for r in rows],
        "la": [round(r[1]["pt"][1], 4) for r in rows],
        "c": [r[2] for r in rows],
        "s": [min(r[1]["sl"], 60000) for r in rows],
        "p": pcol,
        "q": [int(r[0][1:]) for r in rows],
        "w": [r[7] for r in rows],
        "t": tcol,
        "types": types,
        "places": ptab,
    }
    desc = {"d": data.pop("d")}
    json.dump(desc, open(os.path.join(OUT, "events_d.json"), "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    path = os.path.join(OUT, "events.json")
    json.dump(data, open(path, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print("wrote", path, os.path.getsize(path) // 1024, "KB;", len(rows), "events;", len(ptab), "places;", len(types), "types")

    # settlements with inception -> settlement layer rows (name, lon, lat, a, b, src, type, note, id, lived)
    ws = []
    for r in rows:
        if r[4]:
            it = r[1]
            end = it["diss"] or it["e"]
            end = end if end and end >= it["y"] else 2025
            ws.append([r[5], it["pt"][0], it["pt"][1], it["y"], end, 2, tlabel(r[3]) or "聚落", r[6], r[0], 1])
    json.dump(ws, open(os.path.join(WORK, "wd_settlements.json"), "w", encoding="utf-8"), ensure_ascii=False)
    print("wd settlements", len(ws))


if __name__ == "__main__":
    main()
