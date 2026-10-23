# S07 免费供给两项关键资格验证

2026-10-22，Asia/Shanghai。`CURRENT_DECISION=INVESTIGATE`。

**真实日期已绑定；免费历史 PE 的 PIT、完整历史 U 与行业成员均未获得资格。结论是具名缺证，不是证明所有免费路径不可行。** 两证券逐日估值和官方生命周期候选数据确实取得；数值覆盖不能替代历史版本和全量成员证明。S07 历史 Gate 保持 `NOT_PASSED`，停止在 Owner Review。

## 1. 合同与证据身份

依据 [AGENTS.md](../../AGENTS.md)、[R3.2 范围](../MISHI_RADAR_V0_1_SPEC_R3_2_SCOPE_APPROVED_DATA_PENDING_2026-10-16.md)、[DR01–DR06](../MISHI_RADAR_TO_CHSTOCKDATA_DR01_DR06_CONSUMER_REQUEST_2026-10-16.md)、DR01 当前调查、DR02–06 综合差距及[双消费者计划](../plans/2026-10-19-dual-consumer-supply-plan.md)，并只读恢复 Mishi 当前运行规格、Owner Decisions、Addendum、X01。沿用[真实窗口准入审查](2026-10-22-mishi-s07-real-window-admission-preflight.md)和[依赖矩阵](2026-10-22-mishi-s07-real-window-dependencies.json)；旧 PE 反例、R2 和最终 F2 仅在各自证据粒度内复用。

上述 15 份文件的实际路径、大小和 SHA 见 [authority-identities.json](evidence/2026-10-22-s07-free-supply-decisive-screen/authority-identities.json)，终检再次比对一致。恢复的是 `RULE_BASELINE_ACCEPTED / FULL_DESIGN_NOT_FROZEN`：252 个完成市场净值日、65 日统一预热、S07 每 20 日调仓且每日检查退出、归母 TTM/合并 OCF/平均归母权益 ROE、指定日 PE_TTM 和当时全池规则继续有效。具体行业 taxonomy 未由本轮冻结；OD-3 其余使用窗等未被本轮批准。

Owner 在本聊天明确答复“授权上述预算”后才开始网络探针。[registration.json](evidence/2026-10-22-s07-free-supply-decisive-screen/registration.json)先冻结预算、证券、日期选择算法、边界选择及停止条件；每次请求另存不可覆盖的 `plan-*.json`，中心预算检查先于发送。没有生产、消费者、Provider、数据库、产品规则或依赖改动，没有新建 venv、下载财报 PDF、批量重建、commit 或 push。

## 2. 真实产品日期

现有[新浪指数日线入口](https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData)的 SH:000001 与 SZ:399001 各取得 1,023 个唯一、递增市场日期，日期集合完全一致；末日均为 **2026-10-22**，获取时为当日 **20:53（收盘后）**。两者属于同一供应商，不能声称两个独立上游认证；本资格限定于现有免费指数日历路由的实际观察窗口。上交所所试日历网页返回 404，未被计为官方节假日文件认证。

| 项目 | 实际绑定 |
|---|---|
| `e` | 2026-10-22 |
| `s`，含首尾 252 个净值日 | 2025-10-09 |
| `s-1`，首次收盘信号 | 2025-09-30 |
| `s-65…s-1`，65 个共同预热日 | 2025-07-02…2025-09-30 |
| S07 首次 20 日成交额窗口 | 2025-09-03…2025-09-30 |
| 日级 PE/池观察分母 | `s-1…e`，253 个市场日；不是仅 13 次调仓日 |

全部日期及原响应身份见 [calendar.json](evidence/2026-10-22-s07-free-supply-decisive-screen/calendar.json)、`calendar-*-retry.raw`。本地指数仍截至 **2026-09-22**，距离真实 e 缺 **16 个已观察市场日**，不作为产品末日。本地各市场文件数 SH 5,951、SZ 5,864、BJ 611，仅是文件库存，含非普通 A 股，不能当 U 或正式生命周期。

## 3. 历史 PE：取得数值，未取得 PIT

[pe-controls.json](evidence/2026-10-22-s07-free-supply-decisive-screen/pe-controls.json)在读取 PE 前登记 SH:600519、SZ:000002，每股 8 个日期和检查项，后续保留全部原控制，未换股或删除失败样本。披露边界来自现有东财 `RPT_PUBLIC_BS_APPOIN` 的 `ACTUAL_PUBLISH_DATE`，属于聚合源日期级记录，未冒充公告原件时刻。

| 控制 | 起点/末端 | 2025Q3 日期级公告边界/首个可用收盘 | 2025FY 日期级公告边界/首个可用收盘 |
|---|---|---|---|
| SH:600519 | 2025-09-30、10-09；2026-10-21、10-22 | 2025-10-30 / 10-31 | 2026-04-17 / 04-20 |
| SZ:000002 | 同上 | 2025-10-31 / 11-03 | 2026-04-01 / 04-02 |

日期映射有一项显式修复：原精确登记使用“公告日期收盘 / 首个可用收盘”，并非严格公告日前收盘；保留原 16 个控制，按最初规则机械补列严格前日 **2025-10-29、2026-04-16（600519）及 2025-10-30、2026-03-31（000002）**。补列在取数后完成，单列为诊断，不能冒称事前登记的成功案例，也不增加任何 PIT PASS。

实物及全部数值见 [pe-analysis.json](evidence/2026-10-22-s07-free-supply-decisive-screen/pe-analysis.json)：

| 来源 | 实际覆盖与方法 | 年代/口径资格 |
|---|---|---|
| 现有东财 `RPT_VALUEANALYSIS_DET` | 两股各 **253/253** 日，合计 **506/506** 槽；返回总数、页数、证券身份及日期完整性一致；无 PE 缺值。000002 的 **253 个负 PE** 原样保留 | 原行无分母期间、公告身份、财务版本、首次可得或修订政策；顶层不透明 `version` 不是已核财务 vintage。16 个原控制 **0 个获 PIT 认证** |
| [东财估值页面](https://data.eastmoney.com/gzfx/detail/600519.html)及其实际加载脚本 | 页面以股价相对前四季度 EPS 解释 TTM，脚本直接消费源字段 | 未说明历史 EPS 调整、归母范围、重述回填和股本变动规则，不能仅凭名称认定 S07 归母 TTM 相容 |
| 百度规范 `finance.baidu.com/opendata`，近一年 | 两股各 366 个自然日点，2025-10-22…2026-10-22，含 104 个周末点；各覆盖 **243/253** 必需日，缺 10 日；重叠日各 **243/243** 与东财两位舍入一致 | 无可核输入版本与完整逐市场日窗口；一致不证明独立血缘/PIT。10 个缺日包含首个信号及 9 个净值日，未填值或缩窗 |
| BaoStock 现有可选路线 | 本轮重新取得[日频估值官方说明](https://www.baostock.com/helpdocs/api/markdown/valuationDaily.md)的原始文档，确认字段及日频查询形态 | 本轮仅 HTTP 文档取证，TCP 登录/数据查询为 0；没有当前真实 PE 行或版本链。沿用 DR01/R2 的旧访问受阻事实，不能写成本轮服务实测失败，也不能判来源不存在 |

百度缺的 10 日完整列在 JSON，未将“全部”稀疏图表用作缺日补齐。600519 与旧 2025 东财实物重叠 61 日，PE 值均未变化；两次今天获取结果稳定，不证明 2025 当时提供过这些值。

**实际财务分母交叉核验：**复用已存 `600519_ths_benefit.json`，并只取既有财务控制证券 000002 的一份当前利润表，新增深挖证券为 **0**（000002 已在旧 F2 中）。两份都是今天的单版本聚合表，无历史原件/首次可知绑定；明确只作算术诊断。

- 600519 起点三基期归母值为 `45,402,962,298.10 + 86,228,146,421.62 − 41,695,610,983.37 = 89,935,497,736.35` 元；2025-10-09 市值除以该值为 `20.0058580293`，源 PE 为 `20.00585803`，数值相容。
- 600519 在 2025-10-30，源市值/PE 已隐含约 **90,027,341,015.76** 元，接近当前记录的 2025Q3 TTM **90,027,341,015.29**；按日期级披露政策该日仍对应先前 TTM **89,935,497,736.35**。2026-04-17 同样已隐含 FY2025，而日期级政策最早 04-20 可使用。这是实测的**期间/可用日对齐风险**；聚合披露日及当前财务表没有完整原件版本链，不能据此宣布真实未来信息泄漏已查清。
- 000002 起点当前记录归母 TTM 为 **−51,572,503,301.24** 元，2025-10-09 源 PE 为 **−1.57078893**；年度首个可用日 2026-04-02 对应当前 FY2025 **−88,556,470,495.64** 元、源 PE **−0.52811930**。负值和未知版本分列，不用“该股亏损不入选”掩盖供数资格。
- 全部 506 行均满足源内 `市值 = 收盘价 × 总股本`（误差≤0.02 元）；600519 起点/末端股本分别 1,252,270,215 / 1,250,081,601，源并非简单套用一份今日股本。但这仍未独立认证股本生效/可知历史、EPS 方法或重述策略。

**旧反例单列回归：**600518 / 2020-01-09，既有证据的归母基期给出 TTM **479,203,728.07** 元，百度市值相除约 **+39.23**；百度 TTM 实际 **−7.02**，旧东财 **−66.79112414**。旧百度静态 PE **16.56** 与原年报利润算术相容，不能因 TTM 不相容而抹去该正面样例。2019Q3 原响应与数值位置重新核对；2018FY 值在本轮仍依赖既有结构化网页观察，未新增下载其原响应，也未闭合全部中间更正链。该回归不能扩展为真实目标窗或所有免费估值已被否决。

**PE 互斥裁决：`INSUFFICIENT_EVIDENCE_WITH_NAMED_BLOCKER`。**具名阻断是两控制目标期间的原报/更正链及所选 PE 的分母、EPS/股本版本与截至 T 的可用性；不是没有历史 PE 数值。依现有免费原件正向装配同一归母 TTM、配合历史市值/股本的路线仍可保留，但本轮只证明部分输入存在，**没有认证重建可行，更未实施替代 Provider**。

## 4. 历史 U、退出与全日分母

[沪市当前官方清单](https://www.sse.com.cn/assortment/stock/list/share/)、[深市当前官方清单](https://www.szse.cn/market/product/stock/list/index.html)及[深市终止上市清单](https://www.szse.cn/market/stock/suspend/index.html)的实际原响应均保留，规范化身份、排除项及缺口见 [universe.json](evidence/2026-10-22-s07-free-supply-decisive-screen/universe.json)。

| 实际官方导出 | 原始行数 | 完整性证据 |
|---|---:|---|
| SSE 当前主板 / 科创板 | 1,700 / 618 | 各单页完整，`result=pageHelp.data`，行数等于服务端 total |
| SSE 终止上市，股票类型 1/8 | 148 | 同上；不是暂停/退市整理状态全历史 |
| SZSE 当前 A 列表 | 2,907 | 完整 XLSX 导出；没有另行取得历史日全量总数 |
| SZSE 终止上市 | 209 | 完整 XLSX 导出，含 B 股，不能直接全收 |

候选构造保留交易所身份与上市/终止日期，排除沪市 689009、深市号段待核的 302132 及 22 条深 B 股。前两项保留仪器身份/历史类型尚需核实的限制，不声称号段已替代正式类型证明。北交所、基金、指数不从 VIPDOC 混入；无同 ID 冲突。按“上市日起、终止日暂作排他端点”的**诊断区间**得到：

- 窗口相关 **5,248 个不同候选证券**；首次净值日 **5,157**，末日 **5,223**。
- 目标窗内 **91 个上市事件、25 个终止事件**；`5157 + 91 − 25 = 5223`。这证明今日存活池倒推会漏掉至少这 25 个来源中可见的退出证券，不能认证其遗漏为正常剔除。
- [daily-coverage.csv](evidence/2026-10-22-s07-free-supply-decisive-screen/daily-coverage.csv)列全 **252 个净值日及额外 s-1** 的来源候选分母、现存/退市来源行、今日行业缺失和历史未知数。`certified_U_size=UNKNOWN`，完整历史 U 的资格为 **0/252 日**；真 U 的未观测缺口总数仍未知，没有伪造覆盖率。

尚缺历史类型/板块变化、曾退出又恢复上市的中间区间完整性、原始生效公告及其 known_at、终止日端点定义的原件依据；今日清单的日期字段不能独自闭合这些事实。历史 ST、风险警示、退市整理、停复牌也未认证，不能把状态 UNKNOWN 改成 INELIGIBLE。以上不否认官方清单作为生命周期候选起点的价值。

[boundary-controls.json](evidence/2026-10-22-s07-free-supply-decisive-screen/boundary-controls.json)按事前“最早事件、再按证券 ID”选择：新上市 **SH:601026 道生天合 / 2025-10-17**；退出 **SZ:300280 紫天退 / 2025-10-14**。目前证据是官方清单所载业务日期，尚未升级为原始公告可知时间或开盘状态资格。行业迁移控制为 **UNKNOWN**：没有取得完整可核的事件集合，不能声称窗内不存在迁移或记 NOT_APPLICABLE。

## 5. 行业与金融分类

| 免费候选 | 实物/方法证据 | 资格限制 |
|---|---|---|
| SSE `CSRC_CODE/DESC`、SZSE `所属行业` | 当前成员有大类标签，金融 J 有源文字依据 | 未给标准年份/版本及历史成员有效/可知区间；今日 J 不能倒签历史金融排除。当前 broad 大类不与东财细行业隐式拼接 |
| 东财逐日 `BOARD_NAME` | 固定两股分别有白酒Ⅱ、房地产开发标签 | 两股标签不是全市场成员矩阵或迁移完整性证明，不能构建同业分位分母 |
| [BaoStock 行业官方说明](https://www.baostock.com/helpdocs/api/markdown/stockIndustry.md) | 真实文档说明 date 参数、每周一更新，返回 updateDate、行业及分类名；例中退市证券也可行业空白 | 是**存在但尚未核实**的历史候选；本轮未取得数据、标准版本、生效/已知语义或迁移完整性，不能凭文档判 PASS |
| 巨潮 `p_stock2110` 历史行业变更候选 | 已装解析器可定位分类标准、变更日期、行业字段；本轮 HTTP 200 的业务响应实际 `resultcode=401`、未授权 | **访问受限**，已登记停止该主机；没有生成加密键、修改参数绕过限制或把失败当空成员 |

首次净值日的来源候选中，有 **11 只**来自深市退市导出且没有任何行业字段，含 000004、000638、000851、002231、002808、002898、300029、300280、300344、300379、300391；完整 ID/日期均在 JSON。其余 5,146 条带有今日标签也没有历史资格。故该日 **5,157 个候选的历史成员资格全部 UNKNOWN**；不得将 11 只静默剔除后声称行业比较池完整，更不能把其状态认作“已知非金融”或“已知未分类”。末日 5,223 个今日标签完整同样不能证明过去成员完整。

这已直接影响必要分母：目标历史日无法把缺标签退出证券分配到任何已认证行业，亦无法证明现有标签当时有效；真实行业百分位不能认证。本轮未计算正式百分位，也没有编造迁移实例。一个可消费候选至少须提供标准/层级/版本、证券身份、成员状态（含明确未分类与 UNKNOWN）、生效区间、可知日期/精度和全量/迁移完成依据；金融映射随同版本提交 Owner，不能本轮自冻。

```ini
HISTORICAL_UNIVERSE_SOURCE = SSE_SZSE_CURRENT_AND_TERMINATED_OBSERVED_CANDIDATE
DELISTED_SECURITIES_COVERAGE = 25_WINDOW_EXITS_OBSERVED; TRUE_HISTORICAL_TOTAL_UNKNOWN
LISTING_LIFECYCLE_QUALIFICATION = PARTIAL_BUSINESS_DATES; HISTORY_AND_KNOWN_AT_NOT_QUALIFIED
HISTORICAL_INDUSTRY_SOURCE = CANDIDATES_DOCUMENTED_NOT_VERIFIED; CNINFO_ACCESS_RESTRICTED
TAXONOMY_AND_VERSION_IDENTITY = CANDIDATE_ONLY; VERSION_UNVERIFIED; OWNER_NOT_FROZEN
INDUSTRY_MEMBERSHIP_COVERAGE = 0_OF_252_DAYS_QUALIFIED; TRUE_HISTORICAL_DENOMINATOR_UNKNOWN
FULL_UNIVERSE_QUALIFICATION = INSUFFICIENT_EVIDENCE_WITH_NAMED_BLOCKER
```

## 6. 网络账本与停止依据

[requests.json](evidence/2026-10-22-s07-free-supply-decisive-screen/requests.json)逐次保存方法、公开 URL/参数、前置计划、时间、状态、原件 SHA、响应体字节、错误类型和重试关联。累计 **32/120 次尝试，4,765,834/100,000,000 字节**；单次实际最大 **1,944,405/20,000,000 字节**。字节统计为已读取响应体，不包括 HTTP 头/网络封装；失败/错误响应体同样计入。

- 3 次沙箱连接失败（0 响应体），在相同预算下各重试一次并取得响应；全部 3 次失败仍计请求尝试。
- 7 次显式重试 = 上述 3 次 + 4 次文档 GET 405 后按既有证据改用只读 POST；各原请求重试≤1。另有 2 次百度空路由按既存账本修正规范接口，全部计数，无自动重定向/重试。
- 最终 22 次响应保存、6 次 HTTP 失败、1 次业务未授权、3 次连接失败；29 次有 HTTP 响应。HTTP 404 只说明所试页面/文档路径未命中，**不说明整个来源或对应服务不存在**。
- 财务 PDF 0，新增深挖证券 0，TCP 登录/数据查询 0，付费来源 0。临时测试目录已清理；原始/失败和复现证据保留。

预算尚有余量，未声称预算耗尽。现有直接 HTTP 估值/主表的更多同类当前行不能填补分母 vintage、历史生效/可知和全行业迁移完成依据；巨潮路径明确受限即停止。BaoStock 历史成员本体保持 NOT_VERIFIED，不能从未实取外推免费路径不存在；若继续该服务，需先形成其数据本体/传输及历史语义的具体核验输入，而非直接宣布免费全市场可运行。

## 7. 分类、下一项最小动作与交接

- **CONFIRMED_DEFECT / 来源覆盖限制：**受检百度近一年缺每股 10 个必需市场槽；SZSE 终止导出不含行业，目标起点 11 只无法由该来源分配行业；巨潮业务明确拒绝访问。旧 TTM 与既存归母基期的符号矛盾保留其不完整更正链边界。精确控制日期映射的修复透明保留，未用其制造新成功样本。
- **UNRESOLVED_RISK：**PE 实际分母 vintage/首次可得、聚合财务与公告原件连接、披露日跨期切换、股本/EPS 历史方法；完整 U 生命周期及状态；行业标准版本/成员迁移和金融历史映射。均对应必要输入，继续阻断。
- **SPECULATIVE_CONCERN：**未采样证券可能还有其他修订问题、未来吞吐/限流；不据此扩建平台或追加扫描。
- **FUTURE_ENHANCEMENT：**来源合格后再讨论正式公共出口；本轮不实现、不作为通过条件。

**路线决定：保留免费路线，但暂停把现有 PE/今日行业包装成历史合格输入。优先解决“一个完整历史行业成员档案能否实际取得”的阻断，再投入全市场财务供给。**

下一项最小动作是向 Owner 提交**一个具体验收输入要求**：现有免费候选须提供真实 s−1 的完整同标准成员基点及覆盖 s…e 的完整变更目录/快照版本，显式处置本轮 25 个退出证券，说明 effective 与 known_at；来源受限或没有版本/完成依据即拒收该候选，并由 Owner 决定下一条免费来源路线或必要 taxonomy 裁决。PE 独立保留两控制的原报/更正及分母可用日连接缺口；不用批量财报取数掩盖它。没有默认开启下一轮泛化研究或下一 Phase。

验证：现有环境执行 `python -B docs/audits/evidence/2026-10-22-s07-free-supply-decisive-screen/verify.py`；网络连接被禁用，检查真实窗口、拒绝陈旧末日、32 次计划/原件身份与预算、重试/限制负控、固定样本不替换、旧回归边界、253 行分母守恒、离线字节一致重放和权威/工作树保护。结果见 [verification.json](evidence/2026-10-22-s07-free-supply-decisive-screen/verification.json)、[verification.txt](evidence/2026-10-22-s07-free-supply-decisive-screen/verification.txt)。生产代码未改，因此未重跑无关的全仓发行 Gate。

交接：当前阶段 **S07_FREE_SUPPLY_DECISIVE_SCREEN / A 日期已绑定、B/C 来源资格裁决待 Owner Review**；HEAD **5584f5fcacccef9a9531a7a32b8463ea6771d312**。tracked 工作树/index 无变化，原有大量 untracked 报告和证据保留；本轮仅新增本文和对应 evidence。研究校验通过不等于 S07 Gate，通过依据粒度见上文；产品 Gate **NOT_PASSED**。无范围变更、提交或推送；下一阶段未授权。

```ini
CURRENT_DECISION = INVESTIGATE
REAL_S07_E = 2026-10-22
REAL_S07_S = 2025-10-09
CALENDAR_QUALIFICATION = QUALIFIED_FOR_OBSERVED_WINDOW_VIA_EXISTING_SINA_SH_SZ_INDEX_ROUTE
FREE_PE_TTM_PIT_VERDICT = INSUFFICIENT_EVIDENCE_WITH_NAMED_BLOCKER
PE_METHOD_AND_VINTAGE_EVIDENCE = EPS_TTM_DESCRIPTION_AND_CURRENT_PARENT_TTM_DIAGNOSTICS; HISTORICAL_VINTAGE_NOT_PROVEN
FREE_PE_RECONSTRUCTION_FEASIBILITY = INPUTS_PARTIALLY_OBSERVED; NOT_QUALIFIED; NOT_IMPLEMENTED
HISTORICAL_U_VERDICT = SOURCE_CANDIDATE_PARTIAL; COMPLETE_HISTORY_NOT_QUALIFIED
HISTORICAL_INDUSTRY_VERDICT = INSUFFICIENT_EVIDENCE; CANDIDATES_NOT_VERIFIED_OR_ACCESS_RESTRICTED
DELISTING_AND_STATUS_BOUNDARY = 25_WINDOW_EXITS_OBSERVED; HISTORICAL_STATUS_AND_KNOWN_AT_UNKNOWN
REQUEST_BUDGET_USED = 32_OF_120_ATTEMPTS; 4765834_OF_100000000_BODY_BYTES; 7_EXPLICIT_RETRIES
ACTUAL_COVERAGE = CALENDAR_252_NAV_DAYS; PE_506_OF_506_NUMERIC_SLOTS; PIT_0_OF_16_REGISTERED_CASES; COMPLETE_U_AND_INDUSTRY_0_OF_252_DAYS
UNRESOLVED_REQUIRED_INPUTS = PE_DENOMINATOR_VINTAGE_AND_AVAILABILITY; HISTORICAL_LIFECYCLE_STATUS; TAXONOMY_VERSION_AND_COMPLETE_HISTORICAL_MEMBERSHIP
RECOMMENDED_FREE_SUPPLY_ROUTE = OFFICIAL_LIFECYCLE_CANDIDATE_PLUS_VERIFIED_HISTORICAL_INDUSTRY_ARCHIVE; RETAIN_PE_ORIGINAL_VERSION_ROUTE
NEXT_MINIMUM_ACTION = OWNER_REVIEW_ONE_COMPLETE_HISTORICAL_INDUSTRY_BASELINE_AND_CHANGE_ARCHIVE_REQUIREMENT
PRODUCTION_ENTRY_RECOMMENDATION = DO_NOT_ENTER
MISHI_S07_HISTORICAL_GATE = NOT_PASSED
PRODUCTION_IMPLEMENTATION_AUTHORIZED = NO
PRODUCT_SCOPE_CHANGED = NO
GIT_COMMIT = NO
GIT_PUSH = NO
OWNER_REVIEW_REQUIRED = YES
```
