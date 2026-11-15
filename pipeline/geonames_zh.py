"""Extract Chinese names for GeoNames places (cities1000 + admin1/admin2 + countries) from alternateNamesV2.zip.

Output: data/work/geonames_zh.json {geonameid: simplified-Chinese name}
"""
import io
import json
import os
import zipfile

from opencc import OpenCC

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
GN = os.path.join(ROOT, "data", "raw", "geonames")
PRI = {"zh-CN": 0, "zh-Hans": 1, "zh": 2, "zh-SG": 3, "zh-TW": 4, "zh-Hant": 5, "zh-HK": 6}


def main():
    want = set()
    for line in open(os.path.join(GN, "cities1000.txt"), encoding="utf-8"):
        want.add(line.split("\t", 1)[0])
    for fn in ("admin1CodesASCII.txt", "admin2Codes.txt"):
        for line in open(os.path.join(GN, fn), encoding="utf-8"):
            want.add(line.rstrip("\n").split("\t")[3])
    for line in open(os.path.join(GN, "countryInfo.txt"), encoding="utf-8"):
        if not line.startswith("#"):
            p = line.split("\t")
            if len(p) > 16:
                want.add(p[16])
    best = {}
    z = zipfile.ZipFile(os.path.join(GN, "alternateNamesV2.zip"))
    with z.open("alternateNamesV2.txt") as f:
        for raw in io.TextIOWrapper(f, encoding="utf-8"):
            p = raw.rstrip("\n").split("\t")
            lang = p[2]
            if lang not in PRI or p[1] not in want:
                continue
            if (len(p) > 6 and p[6] == "1") or (len(p) > 7 and p[7] == "1"):
                continue  # colloquial / historic
            name = p[3]
            if not any("一" <= ch <= "鿿" for ch in name):
                continue
            score = PRI[lang] * 2 - (1 if len(p) > 4 and p[4] == "1" else 0)
            if p[1] not in best or score < best[p[1]][0]:
                best[p[1]] = (score, name)
    cc = OpenCC("t2s")
    out = {k: cc.convert(v[1]) for k, v in best.items()}
    os.makedirs(os.path.join(ROOT, "data", "work"), exist_ok=True)
    json.dump(out, open(os.path.join(ROOT, "data", "work", "geonames_zh.json"), "w", encoding="utf-8"), ensure_ascii=False)
    print("zh names", len(out), "of", len(want))


if __name__ == "__main__":
    main()
