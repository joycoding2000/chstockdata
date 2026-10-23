# W5-H：Mishi 历史财务、逐日估值与 PIT 可行性裁决

2026-10-19，Asia/Shanghai。生产者只读调查，提交 Owner Review。

**唯一推荐：`SOURCE_FEASIBILITY_BLOCKED`。** 已找到真实原始披露、更正披露及逐日估值实物，不能将问题归结为“免费源没有历史数值”。但现有结构化财报路径不能交付受检报告期的原始版本，现有来源也没有证明其历史首次可得、完整修订链及估值历史版本。只增加数值出口无法满足 S07 已批准的真实历史回测底线。当前停止实施，返回 Owner 作供应或产品 Change Request 决策。

这是**受检既有来源与合同的交付资格阻断**，不是“互联网上所有免费原件均不存在”的断言，也不是永久技术不可行的证明。未推荐其他三个互斥结论；其中部分时间证据仍为 UNKNOWN，不据此降标。

## 1. 权威需求、基线与调查边界

| 权威输入 | 本轮适用结论 |
| --- | --- |
| [根 AGENTS.md](../../AGENTS.md) | 冻结范围、证据独立性、Gate 与下一阶段授权分开；保护三个仓库原有文件。docs/audits 下未发现更深适用规则。 |
| [双消费者规划](../plans/2026-10-19-dual-consumer-supply-plan.md) W5-C/W5-H、E1、F/B5 | 当前数值与历史版本独立裁决；先核已有来源；API 不能创造旧版本；免费来源不足即停止并回 Owner。规划中的 W0 未发行状态已由下述正式发行事实更新，其他包不自动获准。 |
| [Mishi R3.2](../MISHI_RADAR_V0_1_SPEC_R3_2_SCOPE_APPROVED_DATA_PENDING_2026-10-16.md) §0、§2–3、§5 | S07 为 S01–S08 八套首发必交之一；当前全市场筛选、单股历史检验、历史 Top N 现金组合均必交；目标近约一个交易年度另含规则及财务计算基期预热。不能删除 S07 或自行缩短历史。 |
| [DR01–DR06 请求](../MISHI_RADAR_TO_CHSTOCKDATA_DR01_DR06_CONSUMER_REQUEST_2026-10-16.md) DR05 | 当时已公告且当时版本的盈利、OCF、ROE 分子/分母及算法/单位；修订真实可知日期；指定交易日 PE 类型、数值、业务日；历史行业/金融分类。 |
| [DR02–DR06 差距报告](../DR02-DR06-consolidated-gap-report.md) DR05 | 文本/摘要不等正式无损合同；源端旧版、公告过滤和真实 PIT 分开；TTM/平均权益基期不足不可计算。既有同比/单位修复不重列待修缺陷。 |
| [v0.4.3 正式收口](2026-10-19-v0.4.3-release-closeout.md) | 已正式发行，tag target `30cc7c50e3971fe79bfd903a412b2b76a0338caa`；新增公开能力为已接受的 DR04-P，而非财报旧版或估值 as-of。 |

三个核心消费者文档的本仓副本与 Mishi 原件逐字节一致，包含差距报告在 Mishi outputs 下的原件。SHA-256 分别为 R3.2 `9b98641d4602fcd2a35c28520f9160a3fbf935ce1c43e89d466a473419e5bd62`、DR 请求 `35609c8cbf823dbb86a681ea15c27f7f598892b7ea73f46ecde5025e85ff8866`、差距报告 `21f62d51e2caf17e6cefa5deed6300c642f1a7e05765ff1c072c827f21eca118`。身份底稿见 [before.json](evidence/2026-10-19-w5h/before.json)。

Mishi `docs/2026-10-15-LAUNCH_STRATEGIES.md` 的 S07 提案为非金融、正 PE/盈利/OCF、ROE 与行业内排名等；**具体 PE 选择、ROE 算法、阈值、调仓参数尚未因此冻结**。本文核验这些必需输入类别，不把提案中的 ROE≥10% 或 20 日调仓变成新增验收标准。2025 年估值窗口与 2017 年更正案例只是固定来源样本，不替代最近一年商品窗口或全池覆盖。

## 2. 实际公开能力与可复用边界

先使用根 `.codegraph/` 的 `codegraph explore` 定位，再定向核对当前源码、AST 与既有测试。[代码清单](evidence/2026-10-19-w5h/code_inventory.json)记录真实签名、行号及文件身份；`a_stock.py` 与 `point_in_time.py` 从 v0.4.2 到 v0.4.3 的 tag diff 为空，本轮不重复旧发行 Gate。

| 公开入口 | 当前实际交付及限制 |
| --- | --- |
| [get_balance_sheet](../../src/chstockdata/a_stock.py#L3461)、[get_cashflow](../../src/chstockdata/a_stock.py#L3497)、[get_income_statement](../../src/chstockdata/a_stock.py#L3533) | 签名均为 `(ticker, freq='quarterly', curr_date=None, historical_review=None) -> str`。返回标题加 CSV；部分原始数值字符串可保留，不是一概舍入文本。但无正式版本身份、原件/单位元数据与首次可得合同。内部新浪请求固定 page=1/num=20，最终最多 8 期；不是任意报告期、任意旧版本出口。 |
| [get_free_financial_indicators](../../src/chstockdata/a_stock.py#L3568) | `(ticker, curr_date=None, historical_review=None) -> str`。三表共同最新报告期、各公告日，七项金额及派生指标文本；金额/比例通常两位小数。年报 ROE 使用利润/两期平均归母权益，非年报需要 TTM 基期；不能由一条当前值补齐历史输入。利润取值优先 `净利润`，另有归母字段，不自动等于消费者最终所选口径。 |
| [get_fundamentals](../../src/chstockdata/a_stock.py#L3058) | `(ticker, curr_date=None, historical_review=None) -> str`。历史模式排除实时估值、mootdx/F10 等当前快照，不能作为缺失的历史财报版本或每日 PE 替代入口。 |
| [get_valuation_history](../../src/chstockdata/a_stock.py#L5214) | `(ticker) -> str`，JSON 文本。内部读取东财 `RPT_VALUEANALYSIS_DET`，最多 4 页/3000 行；逐日数值只参与计算，最终输出最新 metrics、percentiles、history 首尾/计数/截断摘要，**无逐日 rows、指定区间或历史版本参数**。docstring 的 series 字样不等交付实际序列。 |
| [filter_financial_records](../../src/chstockdata/point_in_time.py#L77) | 对传入记录的公告日做截止过滤，同期选最近可见公告；不存储/取得旧版本。`FinancialObservation.observed_at` 在此路径未填，内部 `point_in_time_safe` 仅依据公告日比较，不能当来源 PIT 认证。 |

这些函数均在包公共导出中；私有桥不作为 Mishi 可消费接口。复用现有三表/公告过滤、报告期对齐与估值字段映射合理，**复用不等资格通过**。本轮没有新增公共 API 或改写现有行为。

## 3. 有界请求、原始证据与执行限制

### 3.1 事前预算及实耗

固定直接来源预算 8 次，单请求 15 秒、响应体 2,000,000 字节上限，不重试、不追页、不自动跟随重定向；网页工具最多 6 次定向调用。固定案例：600518 的 2017 年原报及 2019 年更正；600518/600519 的 2025 年估值；同一更正案例证券 600518 的 2020 年负 PE 对照。无失败后更换股票、年份寻优。

实际直接请求 **8/8**：新浪两份三表响应、三份估值响应、两份披露 HTML 成功保存，共 **3,379,309 字节**；资产负债表请求收到 HTTP 200 后超过单体预算，中止读取，记 `request_failed/ValueError`，未保留完整响应、未解析、未重试，**不是正常空或无资产负债表的证据**。执行程序的唯一该异常分支为 body budget exceeded。

实际网页工具 **4/6** 次调用：两次定向 search（共 4 条查询），一次 open（3 页），一次 find（4 项）；用于同案例披露及东财标签，底层 HTTP 次数/缓存选择不可观测。Firecrawl `--status` 的账户信息请求返回 fetch failed，未修凭据、安装依赖或执行 Firecrawl 数据请求。没有 BaoStock 登录、全市场抓取、策略或收益回测。

**执行偏差必须保留：**本轮独立 requests 探针未通过生产 `_em_get`/SourceGovernor；东财三次请求开始间隔实为 **0.711455s、0.278839s**，未沿用源码默认 `_EM_MIN_INTERVAL=1.0` 的节流。没有发生 403/429 或自动重试，现已停止全部外部请求，不通过重取“修饰”记录。这是调查执行纪律偏差，不是消费者范围变更。原始实物可供复核，但不能据此认证生产访问路径、吞吐、稳定性或合规频率；以后任何重新授权探针应复用既有治理且总尝试数为 1。请求账本保留实际时间，不追认该偏差合格。

### 3.2 证据索引与身份

所有新证据只在 [本轮目录](evidence/2026-10-19-w5h/)；[requests.json](evidence/2026-10-19-w5h/requests.json)保留无凭据公共 URL、完整固定参数、请求时间、响应状态、长度与 SHA。以下为收到并保存的源响应字节，不是合成 fixture：

| 文件 | 字节 | SHA-256 |
| --- | --- | --- |
| [sina_600518_lrb.json](evidence/2026-10-19-w5h/sina_600518_lrb.json) | 1172164 | `6cb84e68b918b274b994f69732c0c957430db58bad1d665477c31f549d612591` |
| [sina_600518_llb.json](evidence/2026-10-19-w5h/sina_600518_llb.json) | 1080118 | `023c5712e3ed875ec4c88a74c1585aee829f23fd614e58ad3b5ac9a9ab6d1345` |
| [eastmoney_600518_2025.json](evidence/2026-10-19-w5h/eastmoney_600518_2025.json) | 141250 | `973c2a8d0ac4a01b058ef570f510909f93fa512a2ff9e75bf4a764f1cc81b81a` |
| [eastmoney_600519_2025.json](evidence/2026-10-19-w5h/eastmoney_600519_2025.json) | 140379 | `cab28b33c788920a8e410f77ef55bb38674a6037d517b05404b5203a70f0c515` |
| [eastmoney_600518_2020.json](evidence/2026-10-19-w5h/eastmoney_600518_2020.json) | 138455 | `780c380d9d26b6a4b607f98c100d4a84b4395f0c196813a3a76d6e2d135e1cc4` |
| [original_2017.html](evidence/2026-10-19-w5h/original_2017.html) | 669806 | `f3bc0297c76a492b7ec0cb04a2eacb0f134c16ffa57fcd215d1632865835a626` |
| [correction_2019.html](evidence/2026-10-19-w5h/correction_2019.html) | 37137 | `32401bcbc41c30a95754300455a12f3e2e0e0668ac303d70b2db6573ffd9af90` |

[web_evidence.json](evidence/2026-10-19-w5h/web_evidence.json)为网页工具观察的结构化摘记，明确不是另行下载的完整原响应；其散列只证明本次摘记身份。全部本地证据的最终长度与 SHA 见 [manifest.json](evidence/2026-10-19-w5h/manifest.json)，不将今天哈希时间当历史首次发布证明。

## 4. A：真实原始财报与更正版本

### 4.1 同一证券、同一期间的可见实物

证券 **600518 康美药业**，财务期间 **2017-01-01 至 2017-12-31**。本轮保存的新浪公司披露镜像中，[2017 年年报原文](https://vip.stock.finance.sina.com.cn/corp/view/vCB_AllBulletinDetail.php?id=4346342&stockid=600518)公告日期为 **2018-04-26**；[前期会计差错更正公告](https://vip.stock.finance.sina.com.cn/corp/view/vCB_AllBulletinDetail.php?id=5335860&stockid=600518)为 **2019-04-30、临2019-026**。公告 ID、标题、日期和响应散列构成受检披露版本身份，不把报告期末、董事会批准日当实际发布日。

原报 HTML 可直接读到主要会计数据，但未认证全部 251 页内容；更正公告明确列出原值、调整额和更正后值。另一次网页工具只读取得的[2018 年年报摘要 §3.1](https://vip.stock.finance.sina.com.cn/corp/view/vCB_AllBulletinDetail.php?id=5335851&stockid=600518)同于 2019-04-30 披露，列明 2017 年调整前/后汇总值，独立于今天财报 API。单位人民币元，所列归母口径明确。

| 2017 年字段 | 2018-04-26 原报实物 | 2019-04-30 更正披露实物 | 今天结构化源对照 |
| --- | --- | --- | --- |
| 营业收入 | 26,476,970,977.57 | 17,578,618,640.06（更正公告直接双列） | `lrb/BIZINCO = 17578618640.060000`，一致 |
| 归母净利润 | 4,100,926,148.57 | 2,149,836,281.41（年报摘要调整后列） | `lrb/PARENETP = 2149836281.410000`，一致 |
| 经营活动现金流量净额 | 1,842,794,237.84 | -4,840,052,606.46（年报摘要调整后列） | `llb/MANANETR = -4840052606.460000`，一致 |
| 归母权益 | 32,032,959,807.76 | 28,413,344,515.00（年报摘要调整后列） | 本轮资产负债表预算中止，**未交叉验证** |

原值均来自旧披露实物，没有用当前值减调整额生成原版。原始营业收入与更正双列相符，修订利润/OCF 与当时披露摘要及当前 API 数值相符。`rCurrency=CNY`、金额与披露元值吻合；`item_value` 字符串有 6 位小数，`item_precision=f2`，不因此宣称六位经济精度或所有字段都经单位认证。

**来源差异保留：**更正公告列示原加权 ROE 14.02%、修订后 7.20%；同日年报摘要修订后为 7.68%。本轮不挑选较方便数值，也不把它们等同现有代码的平均权益 ROE；原因 UNKNOWN。该差异是受检披露的口径/数值待解风险，不能据此改 S07 公式或新增一轮寻源。

以上证明**必要旧事实并非一概不存在，选定字段的两个披露状态可以读取**。未取得/认证两个版本的完整三表、全部财务基期、全市场全部更正链。另[2020-06-18 更正公告](https://vip.stock.finance.sina.com.cn/corp/view/vCB_AllBulletinDetail.php?id=6376590)还涉及 2018/2017 期间，说明两个版本不是终局完整链；本轮仅记录该边界，未展开更多版本采集。

### 4.2 三个信息状态与既有过滤器的实际表现

下表仅讨论**2017 年该年报版本**，不是当日所有财报/业绩快报集合，也不是策略信号。选用非边界日避免把只有公告日期的证据擅自解释成盘前/收盘前可得；日内首发时间仍 UNKNOWN。

| 决策日 T | 披露档案能支持的版本状态 | 对今天返回的真实 2017 行执行既有截止过滤 |
| --- | --- | --- |
| 2018-04-24，原报公告前 | 不能使用本次原报或后来修订版；不否认可能另有更早快报 | 原报期行不可见，排除 1 条 |
| 2018-04-27，原报公告后、更正前 | 原版年报数值可从旧披露实物识别；更正版不可回填 | **仍无该报告期行**，排除 1 条；没有恢复原值 |
| 2019-05-06，更正公告后 | 受检更正披露字段可以按该披露日排序；不是源端首次可得认证 | 修订行可见，营业收入/OCF 为上述更正值 |

受检新浪 `CompanyFinanceService.getFinanceReport2022`，`paperCode=sh600518/source=lrb或llb/type=0/page=1/num=60`，两响应各 **60 个报告期**（2011-09-30 至 2026-06-30；源 report_count 分别 104/100，未翻其余页）。每份 `report_list` 中只有一个 `20171231` 键，该行 `publish_date=20190430`，未同时提供 2018 原值行、独立版本 ID 或 first_available_at。默认公共 num=20 更不能据此声称能访问任意 2017 期间。

[analysis.json](evidence/2026-10-19-w5h/analysis.json)和[离线复核脚本](evidence/2026-10-19-w5h/replay_evidence.py)使用**源响应原有记录**验证上述过滤，不插入/改写原版或公告时间。额外将捕获的 60 期响应注入既有公开财报函数，确认输出类型与修订值；这比默认 20 期更宽，明确是离线行为核验，**不是线上公共接口实际提供 60 期的承诺**。

因此：源码的公告过滤可避免把这一修订行提前展示，却产生原版已公开期间的历史数据空洞；扩大返回数目或调整日期过滤均不能创造缺失版本。仅本次受检现有请求合同不能交付旧版；不推断新浪全部未测试入口永远没有档案。

## 5. B：逐日估值实物、PE 口径与时间边界

### 5.1 实际响应及指定交易日数值

现有源端点为 `https://datacenter-web.eastmoney.com/api/data/v1/get`，同一既有 `reportName=RPT_VALUEANALYSIS_DET`。仅增加固定证券与 TRADE_DATE 闭区间过滤，`columns=ALL/pageSize=500/pageNumber=1`，无新供应商或采集系统。三次均 `success=true/pages=1/count=243`，分别返回 **243 个唯一日期**、证券 ID 唯一正确，共 **729 行**。

| 证券 / 固定窗口 | 实际首尾 | PE_TTM 非正 / 缺失 | 认证边界 |
| --- | --- | --- | --- |
| 600518 / 2025 全年 | 2025-01-02—2025-12-31 | 0 / 0 | 单证券单年的当前历史数值，不是全池或当时版本 |
| 600519 / 2025 全年 | 2025-01-02—2025-12-31 | 0 / 0 | 事先固定盈利对照，不由 600518 的成败换股 |
| 600518 / 2020 全年 | 2020-01-02—2020-12-31 | 243 / 0 | 同证券固定亏损/非正 PE 处理对照 |

| 证券 | 交易日 | 原始 Close | 原始 PE_TTM | 原始 PE_LAR |
| --- | --- | --- | --- | --- |
| 600518 | 2025-01-02 | 2.30 | 124.77952158 | 3719.16815382 |
| 600518 | 2025-12-31 | 1.91 | 1587.28984950 | 2557.43593929 |
| 600519 | 2025-01-02 | 1488 | 22.60643568 | 21.67763548 |
| 600519 | 2025-12-31 | 1377.18 | 19.15641932 | 20.94995249 |
| 600518 | 2020-01-02 | 3.76 | -66.43773195 | -4.01266335 |
| 600518 | 2020-12-31 | 2.68 | -1.88665634 | -0.48060198 |

表中补零只为排版，原 JSON bytes 为精度权威；Decimal 复读保留源数值精度，样本 PE 最大 8 位小数，不把 float 转换结果当无损合同。[东财估值页面](https://data.eastmoney.com/gzfx/)明确分别标示 PE(TTM)、PE(静)、总市值(元)、股本(股)；现代码映射 `PE_TTM→pe_ttm`、`PE_LAR→pe_static`。PE/PB 是比值倍数，不是百分数或亿元；价格按人民币元/股解释并保留源值，样本没有独立源单位字段。市值原行单位元，不采用公开摘要转换后的亿元四位舍入值作为原值。未核验历次股本、分母利润、复权/重述算法与版本合同，不能仅凭列名认定恰好等于最终 S07 PE 方法。

亏损样本返回负 PE，未把它们换成零或缺失。既有公开函数对最新非正 PE 将分位记 `unavailable`；正 PE 样本与负 PE 样本分开核对。该逻辑不证明所有损益转折/零分母/极小利润的源方法，S07 排除规则及缺失规则仍由消费者冻结。

日期结论仅为上述原始日期集、唯一性和源 count 自洽；没有独立完整市场日历/停牌集对账，不能宣称每个应有交易日均齐备。未验证全市场、2026 最近一年交集、财务基期预热或退市证券；源码称老股可自 2018 起，本轮没有验证该全区间，不转述为已合格首日。

### 5.2 “有原始行”与“公共出口没有行”分别成立

以三份真实估值响应分别替换 `_em_get` 返回值，运行**未经修改**的 `get_valuation_history`；禁止 socket 连接。三个结果均 success，history 都反映 243 条、首尾和 count，但 JSON 顶层只有 metrics/percentiles/history 等摘要，**均无 daily rows/series/data 数组**。600518 2020 结果的 PE 分位为 unavailable，两个正样本为 limited_samples。实际输入及输出留在本轮目录，详见 analysis.json。

这是公共接口遗漏逐日出口的直接工程证据，不是底层没有逐日值。若目标仅为“查询今天源端保存的历史数值”，一个保留交易日/原值/类型/来源/单位/状态/截断标记的窄数值出口可能足够；**本任务的目标还包括历史版本与真实可知性，不能据此推荐整体 MINIMAL_INTERFACE_CR_CANDIDATE**。离线回放没有重新请求最新全历史，也不把 2025 数据回放称为今天的实时 API 观测。

### 5.3 具体的回溯分母风险

2020-01-02 的 600518 原行：总市值 `18,701,719,898` 元、`PE_LAR=-4.01266335`。按市值/该静态 PE 反算的**诊断分母**约 `-4,660,675,034.70` 元，与本次新浪 `20191231/PARENETP=-4,660,675,038.43` 元仅差约 **3.73 元**，相对差 `8.00e-10`。该财报行现在的 `publish_date=20210428`。这不是用当前利润计算历史 PE；PE 是东财原始行，反算仅用于检查其可能的分母年代。

据这些数值作出的**推断**是该历史静态 PE 使用了后来年度/重述利润；来源没有给历史公式和分母 vintage，因此不把数值吻合夸大为已查清全部计算链。它已构成不能直接接纳为历史可知估值的具体风险，而不只是泛泛担忧。2019 年原披露的 2018 归母利润仍为正 `1,135,188,498.44` 元，也不能解释此负静态 PE 为彼时该原报的简单市值/利润。最终方法/回填时间 UNKNOWN，禁止用最新序列宣称 as-of。

## 6. C：五种时间身份与能证明/不能证明的事实

| 时间身份 | 现有证据 | 不能推出的结论 / 对历史 T 的处理 |
| --- | --- | --- |
| 财务报告期 | 新浪 report key、2017 原报/修订期间；估值独立 TRADE_DATE | 报告期末不是发布时间；交易日标签不是该 PE 当时已可查询的证明。 |
| 披露公告日期 | 原报 2018-04-26、更正 2019-04-30；摘要同日。来源今天返回 publish_date | 披露档案的日粒度身份已核；精确盘前/盘后、最早上线时刻和各源接入时刻 UNKNOWN。不得假定公告当天收盘前可用。 |
| 来源实际首次可得 | **没有历史获取日志、不可变首见快照或源端 first_available_at** | 今天 queried_at 只证明本次获得；按公告日期过滤不补此证据。也未要求另外建长期库作为本轮任务。 |
| 后续修订/回填时间 | 两次披露身份；新浪单行 publish_date/update_time；估值无对应修订字段 | 2017 lrb update_time 若按 Unix 秒解释为 2020-03-13 16:00:40+08，llb 为同日 14:58:48；字段未有首见定义，不能当 2019 版首次可得。2018 lrb update_time 仍同值而 publish_date 为 20200618，更不能据此建立版本发布全序。 |
| 决策日 T 允许信息集 | 有旧披露选定字段，可验证其公告日排序；现有过滤器只过滤今天行 | 全面资格需要证券×报告期×版本×所需基期及其可得依据的交集。不能把修订值填回原报后、也不能把原版空洞当当时无财报。当前不能生成完整 S07 T 信息集合。 |

这不是要求超出消费者合同的新数据库架构；缺少的是已有必需历史事实/版本/时间证据。即使未来采用保守次交易日规则，也只处理日内未知，不恢复原版与源端历史版本；本轮不替 Owner 批准该政策或降低历史验收。

## 7. S07 必需字段与来源/工程独立裁决

| 必要能力/字段 | 现公开 API 能否交付 | 既有底层实物 | 所缺类别 | 对 S07 首版直接影响 / 是否只需最小出口 |
| --- | --- | --- | --- | --- |
| 证券、报告期、累计/年度及人民币单位 | 部分：三表 CSV、期对齐/公告文本 | 600518 两表 60 期、披露单位可核 | 完整单位元数据、版本及全池覆盖 | 可复用局部字段，不能认证所有报告/证券；数值出口只能解决合同部分。 |
| 原始当时盈利、OCF、权益 | **不能完整交付**受检旧版 | 披露中选定原值存在；结构化受检同期仅一版 | **历史版本与完整字段**，不是纯 API 缺陷 | 原版盈利/OCF 与修订后不同，OCF 甚至变号；不能据今天值重算当时入选/排除。 |
| 更正后数值及版本身份 | 部分修订值可读，无完整版本链 | 更正公告/摘要、API 修订收入/归母利润/OCF相互印证 | 后续链、每版完整三表、源版本 ID | 单个修订样例成立不等任意 T 可重建；不能只增一个 version 字段解决。 |
| 原报/修订真实公告日期 | 部分：源行日期与披露档案 | 两日已核、日内 UNKNOWN | 发布时间粒度及公告与版本正确绑定 | 日粒度局部可用；最终边界规则未冻结。 |
| 来源历史首次可得/回填 | **不能** | 未取得首见/历史获取证据；update_time 含义不足 | **时间身份 / 来源证据** | 无法证明当时源实际可交付该数值；不是增加 observed_at 的工程问题。 |
| 指定日 PE(TTM)/静态 PE 原值 | **无公开逐日出口** | 729 行；两年受检日期、正负样本 | **接口**与 PE 方法/vintage 两类缺口 | 原始值数值出口可成窄 CR 组件；对 PIT 仍不充分。 |
| 亏损、缺失、零分母、精度 | 摘要可区分最新非正/样本不足；无每日正式状态 | 243 条负 PE；raw 数值与精度保存 | 部分源方法及每日质量合同 | 不把亏损变正常正 PE/0；样本不覆盖所有边界。 |
| ROE 分子/分母、前期权益与 TTM 基期 | 当前派生文本部分提供；不是任意历史原值完整包 | 原报/修订部分利润及权益；完整 fzb 本轮未验 | **字段、基期、方法和版本** | ROE 可复算依赖同一当时信息集；披露加权 ROE 与代码平均权益不混用，差异待 Owner/消费者定义。 |
| 历史行业/金融排除及全池 | 本轮沿用原差距，不重新调查 | 本轮没有新增资格证据 | DR01/03 独立历史来源 | 即使财报/PE单点改善，S07 行业内排序和 Top N 仍不能宣布通过。 |
| 近一年另含预热、历史交易资格 | 未认证目标交集 | 固定年度及古早版本例，不是正式输入包 | 全期证券×日×版本覆盖与 DR02/06 | 单股真实规则检验也受影响，不能只承诺 Top N 暂缓来规避底线。 |

### 7.1 Findings 分类

- **CONFIRMED_DEFECT（对本需求的供给缺口，非新发行回归）：**公开估值返回没有逐日行；受检结构化财报记录不能交付 2018 原报后应可见的 2017 原版。两项有代码和真实数据离线复核。更正披露间 ROE 数值差异也已观察到，但成因未判为代码缺陷。
- **UNRESOLVED_RISK（阻断资格）：**源首次可得、完整修订链、估值年代/算法、ROE 口径差异、权益及财务预热不足、正式一年全池交集。尤其具体分母吻合支持回填推断，不能把接口修好视为风险消失。
- **SPECULATIVE_CONCERN：**未经采样证券/年份可能还有何种问题、未来频率与稳定性如何；不据此新增调查或改工程。
- **FUTURE_ENHANCEMENT：**长期财务版本库、正式 PIT API、全市场采集/调度、额外 Provider、付费来源。全部未授权，不是本轮实现内容。

## 8. 潜在最小 CR、不可解决风险与停止点

**现有能力可直接复用的部分：**三表报告期/公告过滤、原有失败语义、估值原字段映射、已核披露及本次 729 行原始证据。它们可供后续 Owner 审核来源，不构成完整消费者交付。

**有条件的最小数值出口组件：**若后续授权仅需现源的“今天查询到的历史估值值”，可单独审议窄出口，显式带证券、指定日期/区间、PE 类型/原值与精度、单位/方法、源、获取时间、质量/失败/截断，历史 first-known/vintage 缺失明确 UNKNOWN；财务必要原字段出口同理。该组件不得宣称 historical PIT，也不得由 Mishi 私接 `_em_get` 或另建第二源绕过公共合同。

**当前不能据此启动 CR 实现。**本次整体推荐仍是 SOURCE_FEASIBILITY_BLOCKED：缺少的完整旧版本与时间证据不能靠新增 API/字段/日期过滤解决。本轮未证明“现成完整原事实已经齐备，只缺轻量封装”，也未证明完整原事实永远不存在；因此不批准财务数据库、抓取更多公告或采购。

**最小必要下一步只有一项：Owner 审阅此报告，作供应或产品 CR 决策。**若选择保留现有 S07 历史承诺，需要先指定可验的既有版本/时点原件或合法供应入口及边界，再另行授权一个固定输入包核验；若无法提供，则由 Owner 显式决定供应计划、发布时间或消费者范围变更。本文不选择缩窗、删除 S07、以修订后研究代替真实历史、改用付费或先发布当前扫描。

停止条件现已达到：受检现成路径不能交付必要原版/时间身份；解决需要新的输入事实或超出授权的工程/供应决策。**停止外部请求与实施，不继续寻优，不执行策略，不自动推进 W5-C、其他工作包或发布。**商业展示/再分发许可本轮仍 UNKNOWN，未核条款、不作法律结论，不用该未知项扩大本轮技术结论。

## 9. 验证、保护与独立交接

- **本轮离线验证：**现有 `test_astock_fundamentals_fix.py`、`test_astock_financial_yoy_alignment.py`、`test_astock_margin_valuation.py` 共 **36 passed**；命令含 `-p no:cacheprovider`，无新增产品测试。[测试日志](evidence/2026-10-19-w5h/focused.stdout.txt)、[JUnit](evidence/2026-10-19-w5h/focused.junit.xml)保留本次结果。测试证明既有解析/口径/摘要行为，不证明市场数据或 S07 PIT 资格。
- **真实响应复核：**`replay_evidence.py` socket 禁止联网，原报/更正日期与原值存在性、真实当前记录三截止过滤、真实估值响应经既有公共函数后缺每日行、Decimal 精度及分母诊断均保存到 analysis.json；回放退出码 0，网络调用 0。HTML 只作原文读取，无伪造版本。
- **保护核验：**[verify_local.py](evidence/2026-10-19-w5h/verify_local.py)比较三个仓库 Git 可见的既有 tracked/未跟踪且非 ignored 文件散列，以及 HEAD、tracked diff 与 index 身份。本轮之前分别 14255/277/271 文件；最终结果见 [verification.json](evidence/2026-10-19-w5h/verification.json)。仅新增本文与有界证据目录。未对 ignored 缓存或整个磁盘作全量保护声明；未改 Git 配置，仅命令级 safe.directory 读取消费者身份。
- **当前阶段/步骤：**W5-H 一次性来源调查与可行性裁决完成，停 Owner Review；实施及 Gate Acceptance 尚未取得。
- **Commit 与工作树：**chstockdata HEAD `69957a58bcfd258f011c9c80250b58704fe0d784`，v0.4.3 tag target 如 §1；Mishi HEAD `678872568c7425b773a0059ae551adc55b3040a3`；SIOS HEAD `554012d1746a0c7476d1db668fb97ceec193578d`。既有未跟踪资料保留，原 tracked diff/index 不变，本轮未暂存、提交、推送、打 tag 或发行。
- **Gate verdict 与证据：**W5-H 推荐 SOURCE_FEASIBILITY_BLOCKED；S07 HISTORICAL_REPLAY **NOT_PASSED**。依据 §4 的真实旧版空洞、§5 的每日出口/年代风险、§6 的首次可得缺口，而非实施者自述 PASS。局部旧披露及数值通过真实性检查不构成完整 Gate 接受。
- **阻断与偏差：**缺完整旧版/版本链、来源首次可得和估值历史身份；权益请求预算中止；完整一年全池/行业/执行交集未认证。无 runtime、冻结合同、消费者范围或新 Provider/依赖变更；存在 §3.1 已披露的探针节流执行偏差。
- **建议下一动作：**Owner 对供应/产品 CR 作一次决定；不存在下一阶段默认授权。无需为凑完整报告补抓全表、重跑市场或重做发布验收。

```ini
W5_H_VERDICT = SOURCE_FEASIBILITY_BLOCKED
ORIGINAL_FINANCIAL_VERSION = REAL_DISCLOSURE_SELECTED_FIELDS_VERIFIED / NOT_DELIVERED_BY_TESTED_STRUCTURED_FEED
REVISED_FINANCIAL_VERSION = REAL_DISCLOSURE_AND_CURRENT_VALUES_CORROBORATED / FULL_VERSION_CHAIN_NOT_VERIFIED
ANNOUNCEMENT_TIMING = ORIGINAL_2018_04_26_AND_CORRECTION_2019_04_30_VERIFIED_AT_DATE_LEVEL / INTRADAY_UNKNOWN
FIRST_KNOWN_EVIDENCE = HISTORICAL_SOURCE_FIRST_AVAILABLE_UNKNOWN
DAILY_VALUATION_ROWS = 729_REAL_ROWS_IN_THREE_FIXED_WINDOWS / PUBLIC_DAILY_EXPORT_ABSENT
HISTORICAL_PIT_QUALIFICATION = NOT_QUALIFIED
EXISTING_API_REUSE = PARTIAL / FILTERING_AND_SUMMARIES_DO_NOT_RECOVER_VINTAGES
SOURCE_BLOCKERS = COMPLETE_ORIGINAL_REVISION_CHAIN; FIRST_AVAILABLE_TIMING; VALUATION_VINTAGE_AND_METHOD
MINIMAL_CR_REQUIRED = NUMERIC_EXPORT_ONLY_CONDITIONAL / INSUFFICIENT_TO_RESOLVE_SOURCE_BLOCKERS
MISHI_S07_HISTORICAL_READINESS = BLOCKED / NOT_PASSED
SCOPE_DEVIATION = NO_PRODUCT_OR_RUNTIME_EXPANSION / PROBE_THROTTLE_EXECUTION_DEVIATION_DISCLOSED
NEXT_MINIMUM_ACTION = OWNER_SUPPLY_OR_PRODUCT_CR_DECISION / STOP_IMPLEMENTATION
IMPLEMENTATION_AUTHORIZED = NO
OWNER_REVIEW_REQUIRED = YES
```
