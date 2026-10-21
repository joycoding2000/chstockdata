# W5-H-R4：TDX 混合修订根因与历史披露 PIT 重建

日期：2026-10-20，Asia/Shanghai。`CURRENT_DECISION=INVESTIGATE`；任务为只读根因调查和固定案例可行性验证。

## 1. 决策

**最终互斥裁决：`PARTIAL_RECONSTRUCTION_WITH_NAMED_GAPS`。**

本轮完成了两项实质推进：

1. **混合已定位到收到的 DAT 字段内容层。** FN98/100/102/105 已是修订值，FN101/106/107 仍是原值。小计减小计能够勾稽，但分项加总对不上小计；不是仅有一个 OCF 字段孤立错误，也不能因顶层勾稽通过而认证整行。现有证据支持“选择性字段修订”的内容表现，**不能证明由 TDX 哪个更新环节、哪家上游或哪次历史更新造成**。
2. **历史原件确能恢复两个具名披露版本的四个目标字段。** 取得并保存巨潮正式原年报、后续年报及更正审核报告，官方目录提供日期与公告 ID。仅使用官方 PDF 直接数值，按明确标注为候选的日期级可用规则，三历史 T 离线演示为 **`PASS_BOUNDED`**：T0 无该年报；T1 原版；T2 修订版，包含 **负 OCF**。没有用今天的新浪、THS 或 TDX 值补过去。

之所以不将总体裁决上调为完整档案重建可行，是因为**截至 T2 的全部影响材料链仍 UNKNOWN、独立 2016 原件未认证、完整财务预热/最终 ROE 方法未合格，时间规则也不是本任务有权冻结的合同**。四字段的有限信息集合成功，不等于完整历史财务输入或 S07 通过。不是 ARCHIVAL_RECONSTRUCTION_BLOCKED：官方原件已经实际取得，不存在据本轮证据否决 PDF/HTML 路线的理由。

## 2. 权威、证据恢复与保护

沿用并核对 AGENTS、双消费者供给计划、W5-H/R2/R3、Mishi R3.2 已批准范围及 DR05 历史要求；另读取最新运行规格候选，身份为规则基线已接受但整体设计/实施未授权。遵从本轮 Owner：S07 必交、当前和历史独立、约一交易年度另含预热、不冻结 PE/ROE/阈值。候选中的“公告日后首个交易日收盘可用”仅用于下述诊断，不提升为正式供给合同。

| 仓库 | 本轮真实 HEAD / 分支 | 保护方式 |
| --- | --- | --- |
| chstockdata | `69957a58bcfd258f011c9c80250b58704fe0d784` / main | 与预期相同；688 个 tracked 文件内容 SHA、完整 tracked/untracked 状态 |
| Mishi | `76012c0db977d21832378c473638c271d8c1a554` / main | 272 个 tracked 内容 SHA；开始时工作树干净，保留实际分支领先状态 |
| SIOS | `f06e7d8e342133a02beb20a4b310580a633ba9cb` / codex/v010-owner-product-clarification | 251 个 tracked 内容 SHA；已有并行研究文件全部保留，终检允许观察并记录他任务增量 |

[before.json](evidence/2026-10-20-w5h-r4/before.json)记录本次基线。必要旧证据优先按三个已有 manifest 验证，**145 项全部匹配**，见 [prior_manifest_checks.json](evidence/2026-10-20-w5h-r4/prior_manifest_checks.json)。包括原 HTML、修订披露、结构化响应、R3 ZIP 与分析文件；没有重取这些旧 URL 或改写旧文件。2026 文件只沿用已保存的读取证据，本轮根因计算集中于 2017 实物，没有寻找新的 GPCW 地址或下载报告期。

新增官方 PDF 是原先镜像 HTML/网页观察的**官方源对照件**，用于补齐权威身份和比较列；不是替换旧证据。旧“2018 摘要”实际上包含网页观察而非本地完整官方 PDF，这一等级差异本轮明确保留，不能因任务描述称已有原件而跳过核实。

普通执行沙箱先拒绝消费者目录读取和网络套接字，随后在已授权范围内通过受控只读执行完成；没有绕过站点认证、登录或读取凭据。前置脚本对无权限和超时的失败没有当作来源无数据。未改 runtime、测试、公共 API、消费者、通达信目录；未运行发行 Gate。

## 3. A：TDX 现金流内部表现与可定位根因

### 3.1 输入身份和字段定义

原始输入为 R3 保存的 `http_gpcw20171231.response`，ZIP SHA-256：

`e393c139a78eef736e8fa25a9226ad73480c8393afdffdd1fbf5a33033065086`

唯一成员 `gpcw20171231.dat`，SHA：

`b95f860bcb129d17eac7d02e240aa732000958071b22c8122485c45d426c0513`

报告期 20171231、4,595 条索引、584 个 float32。600518 唯一索引序号 2969、数据偏移 6,986,149。只读内存解析，不解压覆盖。FN98—FN107 再经已装 mootdx 纯 DAT 解析分支独立对账，**10/10 相同**，不初始化配置或下载器。

先核查 R3 已保存且本轮哈希匹配的官方财务文档镜像及 stock-analysis 字段表：FN101=经营活动现金流入小计，FN106=经营活动现金流出小计，FN107=经营活动净现金流。再以发行人原报和修订比较表的实际数值确认这些位置。原报 PDF **106—107 页**及后续年报 **115—116 页**均明确为**合并现金流量表、1—12 月累计、人民币元**。不是从本轮 Prompt 的候选编号直接认定映射，也没有套用 F10 的 0.1 元快照尺度。

定义摘录、头/索引和旧原件定位见 [tdx_reconciliation.json](evidence/2026-10-20-w5h-r4/tdx_reconciliation.json)；现金流矩阵和独立解析结果见 [cashflow_comparison.json](evidence/2026-10-20-w5h-r4/cashflow_comparison.json)。

### 3.2 原报、2019 修订比较列与 DAT

所有直接披露值单位为元，原报来自官方 2017 年报本期列；修订值来自 2019-04-30 官方 2018 年报的 **2017 上期/调整后列**。没有把缺失小计按调整额推算后冒充原文。

| 字段 | 2018 原报直接值 | 2019 修订比较列直接值 | DAT float32 | 舍入一致性 |
| --- | ---: | ---: | ---: | --- |
| FN98 销售商品/劳务收现 | 28,766,131,827.76 | 18,466,271,669.25 | 18,466,271,232 | 修订 |
| FN100 其他经营收现 | 943,030,295.93 | 1,080,698,100.20 | 1,080,698,112 | 修订 |
| **FN101 流入小计** | **29,709,162,123.69** | **19,546,969,769.45** | **29,709,162,496** | **原报** |
| FN102 采购/劳务付现 | 24,324,394,786.49 | 17,023,054,128.73 | 17,023,053,824 | 修订 |
| FN103 职工付现 | 808,059,122.44 | 808,059,122.44 | 808,059,136 | 两版相同，不能据此识别版本 |
| FN104 税费付现 | 1,809,254,833.22 | 1,809,254,833.22 | 1,809,254,784 | 两版相同 |
| FN105 其他经营付现 | 924,659,143.70 | 4,746,654,291.52 | 4,746,654,208 | 修订 |
| **FN106 流出小计** | **27,866,367,885.85** | **24,387,022,375.91** | **27,866,368,000** | **原报** |
| **FN107 OCF** | **1,842,794,237.84** | **-4,840,052,606.46** | **1,842,794,240** | **原报** |

FN99 在 DAT 为 0，原件税费返还栏为空；证据中保留“空栏”，没有将其擅自认证为经济意义的零。原报合并表之外还有母公司表，原母公司 OCF **326,227,725.66**，明显不是本次 FN107；不能用合并/母公司差异解释上述混合。单季字段与年报累计槽也分开处理。

### 3.3 勾稽检查及 float32

| 检查 | 残差/结果，元 | 判断 |
| --- | ---: | --- |
| FN101−FN106−FN107 | **256** | 三个独立 float32 半 ULP 合计边界 **2,112**，可由量化解释 |
| FN98+FN99+FN100−FN101 | **-10,162,193,152** | 半 ULP 边界约 **2,112**，不能由量化解释 |
| FN102+FN103+FN104+FN105−FN106 | **-3,479,346,048** | 半 ULP 边界 **1,888**，不能由量化解释 |
| 只用 DAT 经营分项诊断重算 OCF | **-4,840,052,608** | 与官方修订直接值差 **-1.54**，仅为计算证据，不是新原件、不输入 PIT 回放 |

因此“流入小计−流出小计=净额”在误差内成立只说明**三个原版聚合字段相互一致**。结合分项和原件，反而定位出**分项已修订、聚合仍旧**的编码内容。四个核心字段的本轮重新对账另见 [financial_core_comparison.json](evidence/2026-10-20-w5h-r4/financial_core_comparison.json)：收入/归母利润/归母权益对应修订版，OCF 对应原版，重现 R3 观察。

### 3.4 五类解释的证据边界

| 解释 | 最小支持/反证 | 分类与结论 |
| --- | --- | --- |
| 字段映射或解码错误 | 官方名称、两个解析器、原报/修订具体金额逐槽对应；边界、报告期、符号正常 | 受检槽位 **不支持该解释**；不宣称全部 584 字段永久正确 |
| 合并/母公司、累计/单季混用 | 合并表标题/年度单位明确；母公司净额不同；年度小计精确对应原报 | 受检九字段 **不支持该解释** |
| TDX 对个别字段选择性修订 | 四个已改变分项均匹配修订，三个聚合字段均匹配原报；主表三核心字段也已修订 | **CONFIRMED_DEFECT：收到的文件内容呈选择性修订混合**；形成机制仍未确认 |
| 上游已提供不一致数据，TDX 原样保留/合并 | 本轮官方 SSE 现金流 JSON 仍保留完整原报数值，说明现实中存在旧结构化状态；但没有 TDX 供应血缘/更新日志 | **UNRESOLVED_RISK**，不能据数值相同证明 TDX 使用该接口或责任归属 |
| 其他未知环节 | 只有今天取得的一份期间包，没有当年 GPCW 快照、生成器日志或修订事件 ID | **UNKNOWN**，不臆造缓存、延迟或内部系统架构 |

能确定的是**混合在解码之前已存在于文件数值**；不能证明 TDX 历次更新过程。不能把“分项可重算”当作“已知更新机制”，也不能给所有旧包定性。

```ini
TDX_FN_MAPPING = VERIFIED_FOR_SELECTED_CORE_AND_FN98_FN107; NOT_ALL_584_FIELDS
TDX_OCF_COMPONENTS = REVISED_DETAILS_WITH_ORIGINAL_SUBTOTALS_AND_NET
TDX_INTERNAL_RECONCILIATION = TOP_LEVEL_WITHIN_FLOAT32; DETAIL_TO_SUBTOTAL_FAIL
TDX_ORIGINAL_DISCLOSURE_PARITY = FN101_FN106_FN107_MATCH; SOME_DETAILS_DO_NOT
TDX_REVISED_DISCLOSURE_PARITY = FN98_FN100_FN102_FN105_MATCH; AGGREGATES_DO_NOT
TDX_MIXED_VERSION_OBSERVATION = CONFIRMED_IN_RECEIVED_DAT_BYTES
TDX_MIXED_VERSION_ROOT_CAUSE = CONTENT_LAYER_SELECTIVE_FIELD_PATTERN_CONFIRMED; UPSTREAM_UPDATE_MECHANISM_UNKNOWN
TDX_ASOF_REPLAY_CAPABILITY = NOT_QUALIFIED
```

## 4. B：实际取得的官方历史档案

### 4.1 公告身份与时间

巨潮公开证券检索返回 `600518 / orgId=gssh0600518`，再按该身份对原年报、更正标题及后续年报分别查一页。实际结果为 3、3、2 条，均 `hasMore=false`；原年报搜索还包含券商督导报告，已按标题/发行人筛掉，未当财务原版。

| ID / 官方原件 | 官方目录日期 | 实际内容/用途 | SHA-256 |
| --- | --- | --- | --- |
| [1204793690：2017年年度报告](https://static.cninfo.com.cn/finalpage/2018-04-26/1204793690.PDF) | **2018-04-26** | 完整 PDF，251 页、3,886,671 B；四字段原值、合并/母公司现金流及 2016 比较数据 | `15b3b15df2dfd3310cc16e1e345e8950e8a9cb047bdad38d1263e2b55cfd2985` |
| [1206168283：2018年度前期会计差错更正专项说明的审核报告](https://static.cninfo.com.cn/finalpage/2019-04-30/1206168283.PDF) | **2019-04-30** | 完整扫描 PDF，11 页、4,526,309 B；审核号广会专字[2019]G18029861609，明确涉及 2017 报表；无文本层，按图核查，不伪装为自动结构化读取 | `ca22aa1858f56e2cd9181d15c88fde83312afb94701898a2de74c378c7c41bab` |
| [1206168292：2018年年度报告](https://static.cninfo.com.cn/finalpage/2019-04-30/1206168292.PDF) | **2019-04-30** | 完整 PDF，252 页、4,252,218 B；p6 的 2017 调整前后四字段、p115—116 的修订后 2017 现金流明细 | `9f47aa0dc0a8838ffd21e600d7eca194052d91cf867d8e22a4ba56dee2b9f60a` |
| [1206201352：收到上交所监管工作函的公告](https://static.cninfo.com.cn/finalpage/2019-05-01/1206201352.PDF) | **2019-05-01** | 完整 PDF，2 页、95,768 B；临2019-032，引用上证公函[2019]20190571，要求继续核查，不是另一套完整替换财务数值 | `eb418f8ef428841839577bc82f2812167092b65c4bcaa928fe38c30faf099ed8` |

同页索引还列出正式更正公告 **1206168278**，日期 2019-04-30，对应已保存的新浪 `5335860 / 临2019-026` 文本；没有再下载其旧镜像或用它替换官方比较表。两份直接进入回放的官方 PDF 值，与旧原报和旧修订观察交叉吻合。

发行人、期间、标题、日期、原 URL、抓取时刻、内容 SHA、全文/扫描属性及目录身份集中保存于 [official_document_identities.json](evidence/2026-10-20-w5h-r4/official_document_identities.json)；原始官方目录响应、请求正文/参数和源字节见 [requests.json](evidence/2026-10-20-w5h-r4/requests.json)、[cninfo_index_summary.json](evidence/2026-10-20-w5h-r4/cninfo_index_summary.json)。

**时间分层：**官方目录 `announcementTime` 只认证公告日期；其午夜编码不证明实际发布时分。PDF CreationDate、审核报告签署日也不是公告时间。`retrieved_at_utc` 是本轮获取时间，第三方首次采集时间 UNKNOWN；没有将任一今天时间戳倒填为历史首见时间。

### 4.2 XBRL：具体入口、真实结果和未取得的版本

没有因为页面介绍 XBRL 就宣称存在目标实例。实际读取上交所 [XBRL 页面](https://english.sse.com.cn/markets/dataservice/xbrl/)及其公开 `search_xbrl.js`，只审查源码，不执行网页脚本：

- 列表真实入口为 `commonSoaQuery.do / COMMON_SSE_PL_XBRL_YJGL`，参数包括 stockId/startYear/endYear/reportPeriodId；固定 600518、2017、年报 5000 的一次查询返回 **HTTP 200、result=[]、total=0**。这是该查询正常空，不是网络失败，也不是全部历史档案不存在的证明。
- 详情真实入口为 `commonQuery.do / COMMON_MAP_CASHFLOW_C`。按相同证券/年度/年报参数，实际取得 **一行官方机器可读 JSON**：`STOCK_ID=600518.SS`，`REPORT_YEAR=2017`，S2030_0140/0240/0250 分别为 **29,709,162,123.69 / 27,866,367,885.85 / 1,842,794,237.84**；分项也全为原报值，精确勾稽。
- 这证明目标期间的**官方结构化现金流等价输出仍可取得**；**没有取得原始 XML/XBRL 实例包，也没有取得可区分的修订后实例**。JSON 没有披露 ID、版本 ID、历史截止参数或 first_available_at；今天得到原值不能自动认证它在历史 T 的源端交付状态。

真实响应保存为 [sse_xbrl_2017_index.json](evidence/2026-10-20-w5h-r4/sse_xbrl_2017_index.json)、[sse_xbrl_2017_cashflow.json](evidence/2026-10-20-w5h-r4/sse_xbrl_2017_cashflow.json)，字段/请求逻辑保存在 `sse_search_xbrl.js`。本轮不猜造 XML URL、不变换镜像碰运气。**XBRL 原始实例/更正版本能力为未取得/未认证，不能宣布技术永久不可用**；PDF 已足以支撑下面有限四字段演示。

### 4.3 更正链、原件等级与 ROE 边界

已检查原报、正式更正索引、审核报告、后续年报比较列及 T2 前监管函。2019-05-01 函件明确要求核查是否涉及更早年度或其他未披露调整，**它没有提供新的完整四字段替换行**，所以不会按较晚日期覆盖 04-30 的财务数值。

更正标题查询覆盖 2018-04-26—2019-05-06，但不是所有可能公告标题或全文的穷尽检索；未全面认证可能不含“更正”的答复/补充材料。因此：

`VERSION_CHAIN_COMPLETENESS = UNKNOWN`

不能将 `hasMore=false` 的关键词结果当作全链完整，不能把未发现别的调整当作证明没有。2019Q3 原件和 2020 后续更正不进入 T2 信息集合；本任务不展开它们的数值。

另有一个可以缩小的旧风险：**本轮官方扫描审核报告 PDF 第6页（印刷第5页）和官方后续年报第7页均给出 2017 修订后加权 ROE=7.68%**；旧新浪更正公告镜像为7.20%。这是官方 PDF 与旧镜像的来源差异，**不能继续表述为这两份官方 PDF 互相矛盾**，但未取得官方更正公告 PDF 本体，不替旧镜像擅改值。仍不冻结 S07 的 ROE 算法、不把披露加权 ROE 与自算平均权益 ROE等同。

## 5. C：三历史 T 的真实披露重建

### 5.1 事件账本和可用时间规则

[build_replay.py](evidence/2026-10-20-w5h-r4/build_replay.py)从两个官方 PDF 的提取文本定位具体页/列，读取十进制原值；没有把 R3 表格或今天接口值作为回放输入。原件页文本、完整 PDF、渲染图、源 SHA、目录日期分别保留。规则为：

> 只有日期的公告，从公告日之后第一个观察到的上证指数交易日收盘起可用于本次诊断。

日历只读已有 `.rh3a2-vipdoc/sh/lday/sh000001.day`，内容 SHA 记入 [disclosure_events.json](evidence/2026-10-20-w5h-r4/disclosure_events.json)。固定样本下，2018-04-26 的下一交易日为 **04-27**；2019-04-30 的下一交易日为 **05-06**。不把工作日/自然日当交易日。该规则是**未冻结的保守候选**，不是获批 SLA/历史日内首发认证，也不认证整个市场日历。

### 5.2 四字段结果

| 字段，人民币元 | T0：2018-04-24 | T1：2018-04-27 | T2：2019-05-06 | 直接原件 |
| --- | --- | ---: | ---: | --- |
| 营业收入 | UNKNOWN：此年报未披露 | 26,476,970,977.57 | 17,578,618,640.06 | 原报 p6 / 后续年报 p6 调整后列 |
| 归母净利润 | UNKNOWN：此年报未披露 | 4,100,926,148.57 | 2,149,836,281.41 | 同上 |
| OCF | UNKNOWN：此年报未披露 | **+1,842,794,237.84** | **-4,840,052,606.46** | 原报 p6、107 / 后续年报 p6、116 |
| 归母权益 | UNKNOWN：此年报未披露 | 32,032,959,807.76 | 28,413,344,515.00 | 原报 p7 / 后续年报 p6 |

T0 的 UNKNOWN 仅指该年报及受检修订链，不声称当时没有业绩快报、预告或其他财务事实。T1 的收入/利润/权益没有采用2019更正；T2 的 OCF 没有保留 TDX 旧正值，也没有使用分项重算诊断值。两期均取自发行人对应披露状态，**重建的是当时公开的信息，不认证这些被披露财报在经济上不存在差错或造假**。

每一条记录都具备 Owner 要求的 13 个字段：security_id、financial_period、field_name、value、unit、accounting_basis、disclosure_id、disclosure_date、version_identity、decision_date、availability_rule、provenance、quality_status。见 [three_date_information_sets.json](evidence/2026-10-20-w5h-r4/three_date_information_sets.json)。版本 ID 是明确标注的审计派生身份（正式公告 ID＋内容 SHA＋比较期列），不是伪造的供应商修订编号。

原件直接值、确定性计算和 UNKNOWN 分开保存：回放四字段为 `OFFICIAL_PDF_DIRECT_VALUE`；DAT 分项 OCF 只在诊断文件；完整 ROE/缺失预热为 UNKNOWN。这个演示是离线审计产物，不是新供应商响应、数据库、公共 API 或策略输入包。

### 5.3 前期基数与泄漏断言

原报 p7 给出当时披露的 2016 比较期归母权益 **29,115,570,378.99**；后续年报 p6 给出其调整后比较值 **27,714,601,608.54**。账本分别保留对应披露日，**不能用后一数值填 T1**。本轮没有独立认证 2016 原年报，没有认证所有所需季度/TTM基期，也没有计算或选择 S07 ROE 公式；不能把两行比较数据包装成完整财务预热合格。

[offline_assertions.json](evidence/2026-10-20-w5h-r4/offline_assertions.json)记录真实资料驱动的断言：

- T0 四值均 UNKNOWN，原报及更正版均不放行；T1 全部选择 CNINFO:1204793690；T2 全部选择 CNINFO:1206168292。
- T1 OCF 为原始正值；T2 明确为负值 `-4840052606.46`，与实际 TDX 旧 OCF 不同。
- 所有已填数值来自官方 PDF 直接单元格；披露日期/候选可用日均满足对应 T；没有注入今天结构化响应或 T2 之后披露数值。
- 缺失全套基期/ROE 不填零、不借用今天修订值。现金流内部顶层可勾稽与分项不勾稽同时被断言，避免只测有利等式。

**`FIXED_CASE_ASOF_RECONSTRUCTION=PASS_BOUNDED` 的范围仅为这四字段、两个已识别版本、三个 T 与候选日期规则。** 它不认证版本链完备或“任意 T 的最新全部事实”，因此总体保留 PARTIAL_WITH_NAMED_GAPS。

## 6. 三个必须回答的方案问题

### 6.1 通达信能否原地修复？

这是受检包的**数据内容一致性缺陷**，不是现有证据支持的单一字段映射错误。这个固定案例的现金流分项可以诊断重算，并由已取得官方修订表核对；但不能保证全部 584 槽、其他证券/期间都能如此修复。修好某个净额仍没有历史原版/修订链，也没有每次修订的真实可知时间；FN314 仍是 180426，不是三项修订值的2019公告日期。

故不建议修改原 DAT 或据今天 GPCW 直接构建任意历史 T。可以保留“原值＋原件核验后的派生诊断”供研究；不能把它变为本轮生产修复。

### 6.2 公开档案能否解决版本问题？

**对本例四字段和已取得的两个披露状态，可以。** 巨潮正式目录有稳定具名公告 ID、日期、附件 URL；两份完整 PDF 同时保留原值和修订比较值，数字型 PDF 可定位提取，扫描审核报告可作人工核对。无需依赖目标原始 XBRL 包即可演示无未来值回填。

**对完整 S07 所需事实，尚未证明。** 完整修订链、独立基期、季度连续性、金融类/合并口径差异、最终 ROE/PE方法、历史估值/股本、行业/历史池和全市场覆盖各有独立资格。XBRL 当前 JSON 仅提供一套原值，不代替这些版本事实。

### 6.3 是否值得下一项最小验证？

**值得继续有限的来源资格验证，尚不值得进入 Provider/数据库实现。** 已有具体可复用机制，不再停留在网站介绍：issuer orgId → 有界历史公告索引 → 正式附件 → 版本/列定位 → 十进制值/日期 → 离线截止选择。当前两份年报共 **503 页、8,138,889 字节**；仅检查四字段仍需跨页和分清比较列，扫描审核报告需要人工，这些是实际维护成本的样本，不是全市场吞吐承诺。

**唯一最小下一动作：Owner Review 后，若授权继续，只做一个“来源链与财务预热闭合”的资格包。** 先补本例截至 T2 可能影响2017字段的完整具名披露清单（包括不含“更正”标题的答复/补充材料）、独立前期原件，并确认日期级可用规则。以字段/版本差异及缺口账本为验收，不运行收益回测、不开发接口。

该包若成立，才可提出一沪一深、事前固定证券和目标年度另含必要财务预热的最小扩样；600518 保留为离线修订反例。下一次应量测原件获取成功/缺失、原/修订身份、字段/单位完整度、人工处理页/耗时及与既有结构化值的差异；未冻结公式所需期间不擅定，不能据两公司样例宣称全市场可行。本报告**不授权这一扩样或任何下一实施阶段**。

如具名链/必要基期确实无法取得，届时才能据具体事实裁决成熟历史版本服务需求；本轮不能用暂未取得 XML 或查询正常空，提前宣布档案路线永久失败或必须购买。

## 7. 请求、验证与终止

事前预算见 [budget.json](evidence/2026-10-20-w5h-r4/budget.json)：直接尝试16、网页批次8、单体20 MB/总60 MB、15秒、同主机完成后至少3秒、自动重试0、重定向0。本轮实际 **16 次直接尝试：3 次本地 WinError10013 套接字权限失败、13 份成功响应**；仅初始三个未到源端的访问在权限条件明确改变后受控各重发一次，均计入预算，没有自动重试或站点权限绕过。网页工具3批，底层请求/缓存选择不可观测，不与直接账本伪合并。

预算用完即停止访问；不继续猜 XBRL 链接或搜更多 TDX 地址。失败和正常空分开记录，见 [research_summary.json](evidence/2026-10-20-w5h-r4/research_summary.json)。PDF 页数/提取结果、原图与渲染告警保留，见 `pdf_extraction_inventory.json`、`render_log.json`、[visual_qa.json](evidence/2026-10-20-w5h-r4/visual_qa.json)。Poppler 字体回落告警未隐藏，受检中文标签、金额和负号经图像核对可读；未检查的页不冒称全部验证。扫描件未安装 OCR 或新生产依赖。

终检为 [verify_delivery.py](evidence/2026-10-20-w5h-r4/verify_delivery.py)，结果见 [final_verification.json](evidence/2026-10-20-w5h-r4/final_verification.json)及 [manifest.json](evidence/2026-10-20-w5h-r4/manifest.json)。仅验证本调查的真实原件、列选择、断言、证据链接/SHA及三仓库保护；没有修改或重跑生产测试/发行 Gate，没有策略回测。

| 分类 | 本轮结果 |
| --- | --- |
| CONFIRMED_DEFECT | 受检 DAT 的修订分项与原版聚合混用，分项残差远超 float32；不归为 chstockdata runtime 新缺陷 |
| UNRESOLVED_RISK | TDX 实际上游/更新机制、完整修订链、独立基期/预热、可用时间合同、完整字段与全池资格 |
| SPECULATIVE_CONCERN | “TDX一定从SSE原JSON混合”“所有旧包都相同”“无XBRL就不能PIT”均未被证明，不据此追加工程 |
| FUTURE_ENHANCEMENT | 仅有条件提出小规模来源资格包；无 Provider/数据库设计或实施授权 |

## 8. 机器可读交接

```ini
CURRENT_DECISION = INVESTIGATE
W5_H_R4_VERDICT = PARTIAL_RECONSTRUCTION_WITH_NAMED_GAPS

TDX_FILE_IDENTITY = R3_ORIGINAL_ZIP_AND_DAT_SHA_REVERIFIED
TDX_FN_FIELD_MAPPING = VERIFIED_SELECTED_CORE_AND_FN98_FN107_NOT_ALL_FIELDS
TDX_OCF_COMPONENT_RECONCILIATION = SUBTOTAL_NET_PASS_FLOAT32; COMPONENT_SUBTOTAL_FAIL
TDX_MIXED_VERSION_CONFIRMED = YES_RECEIVED_DAT_CONTENT
TDX_MIXED_VERSION_ROOT_CAUSE = SELECTIVE_FIELD_RESTATEMENT_PATTERN_CONFIRMED; EXACT_TDX_OR_UPSTREAM_UPDATE_HISTORY_UNKNOWN
TDX_REPAIRABILITY = FIXED_CASHFLOW_DIAGNOSTIC_RECOMPUTABLE; NO_COMPLETE_IN_PLACE_OR_PIT_FIX
TDX_ASOF_SOURCE_CAPABILITY = NOT_QUALIFIED

ORIGINAL_DISCLOSURE_ARCHIVE = OFFICIAL_CNINFO_1204793690_PDF_OBTAINED_AND_HASHED; OLD_SINA_ORIGINAL_PRESERVED
REVISED_DISCLOSURE_ARCHIVE = OFFICIAL_CNINFO_1206168292_AND_1206168283_OBTAINED; OLD_NOTICE_PRESERVED
OFFICIAL_XBRL_AVAILABILITY = REAL_ORIGINAL_2017_CF_JSON_OBTAINED; XML_INSTANCE_AND_REVISED_VINTAGE_NOT_OBTAINED
DISCLOSURE_VERSION_IDENTITY = OFFICIAL_IDS_AND_CONTENT_SHA_WITH_EXPLICIT_AUDIT_DERIVED_VERSION_LABELS
DISCLOSURE_TIME_EVIDENCE = OFFICIAL_CATALOG_DATE_ONLY; DOWNLOAD_AND_PDF_CREATION_TIMES_SEPARATE
VERSION_CHAIN_COMPLETENESS = UNKNOWN

T0_2018_04_24 = THIS_REPORT_FAMILY_EXCLUDED; VALUES_UNKNOWN
T1_2018_04_27 = ORIGINAL_FOUR_FIELDS_ONLY; FUTURE_RESTATEMENT_EXCLUDED
T2_2019_05_06 = VERIFIED_REVISED_FOUR_FIELDS_WITH_NEGATIVE_OCF; NO_LATER_DISCLOSURES
FIXED_CASE_ASOF_RECONSTRUCTION = PASS_BOUNDED
FUTURE_DATA_LEAKAGE_TEST = PASS_FOR_BOUNDED_LEDGER_AND_CANDIDATE_DATE_RULE
REQUIRED_FINANCIAL_FIELD_COVERAGE = FOUR_SELECTED_FIELDS_DIRECT; NOT_COMPLETE_S07_FINANCIAL_INPUT
FINANCIAL_WARMUP_COVERAGE = COMPARATIVES_AVAILABLE; INDEPENDENT_PRIOR_ORIGINAL_AND_FULL_PERIOD_SET_NOT_QUALIFIED

RECOMMENDED_HISTORICAL_SUPPLY_PATH = VERSIONED_OFFICIAL_PDF_OR_HTML_DISCLOSURES; XBRL_OPTIONAL; TDX_FOR_CROSSCHECK_NOT_HISTORICAL_VINTAGE_AUTHORITY
NEXT_MINIMUM_ACTION = OWNER_REVIEW_THEN_ONLY_IF_AUTHORIZED_CLOSE_FIXED_CASE_DISCLOSURE_CHAIN_PRIOR_BASE_AND_AVAILABILITY_RULE

MISHI_S07_HISTORICAL_GATE = NOT_PASSED
MISHI_PRODUCT_SCOPE_CHANGED = NO
NEXT_PHASE_IMPLEMENTATION_ALLOWED = NO

RUNTIME_CHANGED = NO
GIT_COMMIT = NO
GIT_PUSH = NO
OWNER_REVIEW_REQUIRED = YES
```

## 9. ChatGPT handoff

- 当前阶段/步骤：W5-H-R4 根因与历史档案可行性调查完成，等待 Owner Review。
- 提交与工作树：chstockdata `69957a58bcfd258f011c9c80250b58704fe0d784`；本任务只新增本报告和 `evidence/2026-10-20-w5h-r4/`。原有 tracked/untracked 工作保留，消费者并行增量按终检实况记录，不清理、不 reset；无 commit/push。
- Gate 与证据：DAT 混合及分项/小计不一致已确认；官方原件取得及有限四字段回放 `PASS_BOUNDED`，总体 `PARTIAL_RECONSTRUCTION_WITH_NAMED_GAPS`；cashflow_comparison、official_document_identities、three_date_information_sets、offline_assertions 为决定性证据。S07 历史 Gate 未通过。
- 未解阻断与范围变化：实际 TDX 更新血缘、完整更正链、独立基期/完整预热、时间规则和完整 S07 其他输入未认证；没有产品范围变化或工程实施。
- 推荐下一动作：Owner 审阅后再裁决一个固定案例来源链/基期/时间规则闭合包；不自动扩市场、不开发 Provider，不将下一阶段视为已授权。
