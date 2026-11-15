# 世界历史大事记（history-atlas）

地图 + 时间轴的世界历史事件浏览器。点击地图任意位置，列出该地周边在各个时期发生的事件和存在过的聚居地。

## 目录

- `web/index.html`：前端页面（MapLibre GL + deck.gl，纯静态，无后端）
- `web/data/`：页面读取的数据文件（由 pipeline 生成）
- `pipeline/`：数据采集与清洗脚本（Python）
- `serve.js`：本地预览服务器
- `data/raw/`：原始下载数据（体积大，不随包分发；按下文命令可重新获取）

## 本地运行

```bash
node serve.js 8080
```

打开 http://localhost:8080 。页面从 unpkg 加载 MapLibre GL 4.7.1 和 deck.gl 9.1.14，需要联网。

## 重建数据

```bash
pip install requests numpy scipy pyshp opencc-python-reimplemented
python3 pipeline/fetch_wikidata.py        # Wikidata 分时段抓取，可断点续跑
python3 pipeline/classes.py               # 解析事件类别的上位类
python3 pipeline/geonames_zh.py           # GeoNames 中文地名
python3 pipeline/build_events.py          # 分类、取标签、挂接现代市县 -> web/data/events.json
python3 pipeline/build_settlements.py     # Pleiades + CHGIS + Wikidata 聚居地 -> web/data/settlements.json
python3 pipeline/routes_src.py            # 迁徙路线 -> web/data/routes.json
```

原始数据位置：`data/raw/geonames`（cities1000、admin1/admin2、alternateNamesV2）、`data/raw/pleiades`（GitHub isawnyu/pleiades.datasets 的 data/gis）、`data/raw/chgis`（Harvard Dataverse doi:10.7910/DVN/Q9VOF5）、`data/raw/naturalearth`、`data/raw/basemaps`（aourednik/historical-basemaps）。底图和疆域用 mapshaper 简化。

## 数据模型

事件（`events.json`，列式存储，按年份排序）：名称 `n`、简述 `d`、起始年 `y`、结束年 `e`、月日 `md`、经纬度 `x`/`la`、大类 `c`、知名度（维基语言版本数）`s`、现代市县索引 `p`、Wikidata 编号 `q`、细分类型 `t`。年份为负表示公元前。

事件大类：0 战争与冲突，1 政治，2 灾害与事故，3 建城与建造，4 文化与科技，5 其他。

现代市县归属：取事件坐标 40 km 内最近的 GeoNames 聚居点（人口 ≥1000），附带其二级、一级行政区和国家。这是近似做法，未使用行政区多边形。

## 数据来源与许可

- Wikidata（CC0）
- Pleiades（CC BY 3.0）
- CHGIS V6 县级点（Harvard Dataverse 标注 CC0；数据包内 README 写明仅限学术研究、不得再分发。公开分享前请核实）
- GeoNames（CC BY 4.0）
- Natural Earth（公有领域）
- historical-basemaps（GPL-3.0），疆域为若干年份的近似快照
- 迁徙与远征路线：手工整理，途经点和年代为近似值
