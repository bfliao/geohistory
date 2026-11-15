# 世界历史大事记（geohistory）

地图 + 时间轴的世界历史浏览器。点击地图任意位置，列出该地周边在各个时期发生的事件、存在过的聚居地与遗址、当时所属的政权、途经的道路，以及与此地有关的人物。

线上地址：https://bfliao.github.io/geohistory/

## 图层与数据来源

| 图层 | 来源 | 规模 | 许可 |
|---|---|---|---|
| 事件 | Wikidata | 116,960 | CC0 |
| 事件 | REACHES（据《中国三千年气象记录总集》，明清县级旱、水、蝗、疫、饥记录） | 86,446 | NOAA 古气候数据中心公开数据 |
| 事件 | 欧洲鼠疫暴发数据（Büntgen & Ginzler，据 Biraben） | 6,927 | ODbL |
| 事件 | NOAA NCEI 重大地震、海啸、火山喷发数据库 | 4,686 | 美国政府公开数据 |
| 事件 | 《中国历代战争年表》（Warfare of Imperial China 数字化） | 3,319 | 原书版权归解放军出版社；数字化文件未标许可 |
| 事件 | HCED 历史冲突事件数据集 | 3,182 | CC0 |
| 事件 | UCDP 地理参照事件数据集 GED 26.1（死亡 ≥50 人的事件） | 1,557 | 需署名 |
| 事件 | 史密森尼学会全球火山计划（VEI ≥3 的喷发） | 1,452 | GVP 使用条款，需署名 |
| 聚居地与遗址 | Wikidata（有建立年代的聚落） | 48,965 | CC0 |
| 聚居地与遗址 | p3k14c 碳十四测年库 | 39,639 | CC BY 4.0 |
| 聚居地与遗址 | Pleiades | 21,385 | CC BY 3.0 |
| 聚居地与遗址 | CHGIS V6 县级治所 | 10,512 | 见下文“许可提示” |
| 聚居地与遗址 | AADR 古 DNA 资源库（按出土地点汇总） | 3,784 | CC0 |
| 聚居地与遗址 | al-Ṯurayyā 早期伊斯兰世界地名库 | 1,857 | CC BY 4.0 |
| 政权疆域 | Cliopatria（Seshat，前 3400–2024 年） | 6,024 | CC BY 4.0 |
| 政权疆域 | historical-basemaps（前 3400 年以前的 5 个快照） | 89 | GPL-3.0 |
| 道路与航迹 | Itiner-e 罗马道路 | 14,769 段 | 开放获取，需署名 |
| 道路与航迹 | CLIWOC 航海日志 1750–1850 | 5,171 条航迹 | 开放 |
| 道路与航迹 | al-Ṯurayyā 路线 | 2,053 段 | CC BY 4.0 |
| 人物 | Wikidata（维基百科语言版本 ≥25 的人物，出生与逝世地） | 54,472 | CC0 |
| 人物 | CBDB 中国历代人物传记资料库（有生卒年和籍贯坐标者） | 75,185 | CC BY-NC-SA 4.0 |
| 迁徙与远征路线 | 手工整理的近似示意 | 149 | — |
| 现代地名、底图 | GeoNames、Natural Earth | — | CC BY 4.0、公有领域 |

外部事件源并入时做了去重：同类事件、年份相差不超过 1 年且位置相近（战役 30 km、地震 150 km、海啸 300 km、火山 40 km）视为同一事件，只保留先有的一条。例如 HCED 的 8,866 场战役中有 5,684 场已存在，NOAA 的 6,635 次地震中有 2,712 次已存在。明细见 `data/work/ext_stats.json`。

## 目录

- `web/index.html`：前端页面（MapLibre GL + deck.gl，纯静态，无后端）
- `web/data/`：页面读取的数据文件（由 pipeline 生成）
- `pipeline/`：数据采集与清洗脚本（Python）
- `serve.js`：本地预览服务器
- `build_site.js`、`deploy.sh`：打包静态站点并发布到 GitHub Pages
- `data/raw/`、`data/work/`：原始下载数据和中间缓存（体积大，不入库）

## 本地运行

```bash
node serve.js 8080
```

打开 http://localhost:8080 。页面从 unpkg 加载 MapLibre GL 4.7.1 和 deck.gl 9.1.14，需要联网。

## 部署到 GitHub Pages

```bash
./deploy.sh
```

脚本先运行 `node build_site.js` 把 `web/` 打包成完整静态站点（`_site/`），再提交到 `gh-pages` 分支并推送。

## 重建数据

```bash
pip install requests numpy scipy pyshp shapely opencc-python-reimplemented openpyxl pyreadr
python3 pipeline/fetch_wikidata.py        # Wikidata 事件，分时段抓取，可断点续跑
python3 pipeline/classes.py               # 事件类别的上位类
python3 pipeline/geonames_zh.py           # GeoNames 中文地名
python3 pipeline/locations.py --all       # 事件登记的所在地、国家及其粒度（用于位置核对）
python3 pipeline/fetch_external.py        # 其余事件、遗址、道路、航迹等数据源
python3 pipeline/external.py              # 解析上述数据源 -> data/work/ext_*.json、web/data/lines.json
python3 pipeline/build_events.py          # 分类、位置核对、并入外部事件、挂接现代市县 -> web/data/events*.json
python3 pipeline/build_settlements.py     # 聚居地与遗址 -> web/data/settlements.json
python3 pipeline/build_polities.py        # Cliopatria 疆域 -> web/data/polities.json（需要 mapshaper）
python3 pipeline/fetch_people.py          # Wikidata 人物
python3 pipeline/build_people.py          # 人物 -> web/data/people.json
python3 pipeline/routes_src.py            # 手工整理的迁徙路线 -> web/data/routes.json
```

另需手动放入 `data/raw/` 的数据：GeoNames（cities1000、admin1/admin2、alternateNamesV2）、Pleiades（GitHub isawnyu/pleiades.datasets 的 data/gis）、CHGIS 县级点（Harvard Dataverse doi:10.7910/DVN/Q9VOF5）、Natural Earth；以及克隆到 `data/raw/ext/` 的 Cliopatria、al-Ṯurayyā、p3k14c 三个仓库和 CBDB 的 SQLite 文件。

## 数据模型

事件按年份排序、列式存储，拆成三个文件：`events.json`（起始年 `y`、结束年 `e`、月日 `md`、经纬度 `x`/`la`、大类 `c`、位置精度 `pr`、重要度 `s`、现代市县索引 `p`、Wikidata 编号 `q`、细分类型 `t`、来源索引 `src`，以及 `types`、`places`、`sources` 三张表）、`events_n.json`（名称 `n`、来源内编号 `u`）、`events_d.json`（简述 `d`）。年份为负表示公元前。

事件大类：0 战争与冲突，1 政治，2 灾害与事故，3 建城与建造，4 文化与科技，5 其他。

重要度 `s`：Wikidata 事件取维基百科语言版本数；其他来源按伤亡规模、震级、火山爆发指数等折算到相近的量级。

现代市县归属：取事件坐标 40 km 内最近的 GeoNames 聚居点（人口 ≥1000），附带其二级、一级行政区和国家。这是近似做法，未使用行政区多边形。

政权疆域是一个文件，每个多边形带有效年份 `f`–`t`，页面按当前年份过滤。Cliopatria 原始数据常逐年给出边界，这里按抽样年份（公元 1500 年前每 25 年、1500–1800 年每 10 年、之后每 5 年）合并，并把边界简化到约 18 km。隶属于更大政治体的成员不单独画出。

## 位置精度与核对

Wikidata 的事件要么自带坐标（P625），要么只登记“所在地”（P276）。管线对每个落点做如下处理（`build_events.py` 的 `fix_positions`）：

| 情况 | 处理 | 条数 |
|---|---|---|
| 自带坐标，落在登记的国家内 | 保留 | 73,358 |
| 自带坐标，与登记的所在地相距 150 km 内 | 保留 | 23,997 |
| 无自带坐标，所在地是城市、建筑或县市级区域 | 落在所在地上，标注“位置取自所在地” | 14,651 |
| 自带坐标，但既无所在地也无国家可对照 | 保留，未核对 | 7,861 |
| 所在地只有国家、大洲、海洋、省级大区 | 不标点，按时段列在侧栏（`events_nogeo.json`） | 5,926 |
| 坐标远离登记的国家（多为殖民地、海上事件） | 保留，列入报告 | 152 |
| 坐标有笔误证据（正负号、经纬互换、单个坐标错位） | 自动修正 | 29 |
| 坐标与所在地相距 500 km 以上且无法判断哪个对 | 不标点 | 19 |

所在地粒度按其类别和面积判定：聚落、建筑、遗址为点级；面积不超过 2 万平方公里的行政区、岛屿、湖泊为县市级；其余为大区域。战争、战役行动、疫情、政权建立等“范围性事件”即使有坐标也只是代表点，前端用空心圆显示（`pr = 2`）。

核对明细写在 `data/work/position_report.json`。未核对和“远离登记国家”的条目里仍可能有错误坐标。

其他来源的位置精度：《中国历代战争年表》和 REACHES 的坐标是地名对应的治所，鼠疫数据是城镇，均标为“位置取自所在地”（`pr = 1`）。p3k14c 在美国和加拿大的坐标被原数据方模糊到县一级；其碳十四年代在这里只做了粗略校正。

## 未接入的来源

| 来源 | 原因 |
|---|---|
| SlaveVoyages | 数据只有港口编码和名称，没有坐标；可靠定位需要港口地名表 |
| ACLED | 许可禁止再分发和衍生产品 |
| GDELT | 新闻机器编码，1979 年至今数亿条，噪声大 |
| EventKG | 12 GB，主体与 Wikidata 重合 |
| OpenHistoricalMap | 需处理整份 planet 文件 |
| Getty TGN、World Historical Gazetteer、日本历史地名大系 | 地名没有年代，无法放到时间轴上 |
| IKCEST 中国历史地震、历史城市人口（NASA SEDAC）、EM-DAT | 下载需要登录 |
| 中研院 CCTS | 仅限注册的学术用户 |
| DARMC 沉船库 | Dataverse 上只有摘要文件 |
| 史书原文抽取（二十四史、《资治通鉴》） | 需要另建大模型抽取管线 |

## 许可提示

- CHGIS V6 县级点：Harvard Dataverse 标注 CC0；数据包内 README 写明仅限学术研究、不得再分发。
- CBDB：CC BY-NC-SA 4.0，非商业使用，衍生数据需同方式共享。
- 《中国历代战争年表》：原书有版权，这里只使用了战事名称、年代和定位。
- 欧洲鼠疫数据：ODbL，衍生数据库需同方式共享。
- historical-basemaps：GPL-3.0。
