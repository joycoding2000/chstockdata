# W5-H-R2：免费历史财务与估值替代来源资格裁决

2026-10-20，Asia/Shanghai。只读调查完成，提交 Owner Review；市场来源观测时间以请求账本为准。

**主裁决：`ACCESS_OR_EVIDENCE_INSUFFICIENT`。** 本轮实际覆盖了通达信、BaoStock、AKShare 的同花顺/百度上游及聚宽、QMT、RQData 对照，不能从新浪和东财两个旧入口推断所有免费来源失败。新实物证明同花顺可提供历史报告期的三表原值，百度可提供估值序列；但同花顺的受检旧版仍缺失，百度 TTM 与当时披露基期不相容，通达信数据访问及 BaoStock 数据连接仍未解锁。当前**没有实际证据充分的合格免费交付路径**，同时也**不能判定未取到目标实物的通达信/BaoStock 在技术上不支持**。

**单一优先方向：已有合法增强通达信客户端/已取得专业财务文件的固定案例资格核验。** 这是最值得保留的下一来源资格路径，尚不是合格供应组合或工程实施建议。需要访问、版本及时间证据共同成立，不能包装成“只缺一个出口”或“只差一项已确定可完成的实证”。本文仅提出一个有输入条件的后续包，不自动启动，不默认改产品或购买数据。

## 1. 权威需求及本轮基线

已读取[根规则](../../AGENTS.md)、[双消费者规划 W5-C/W5-H、E1、F/B5](../plans/2026-10-19-dual-consumer-supply-plan.md)、[W5-H 审计](2026-10-19-w5h-historical-financial-pit-feasibility.md)、[Mishi R3.2](../MISHI_RADAR_V0_1_SPEC_R3_2_SCOPE_APPROVED_DATA_PENDING_2026-10-16.md)、[DR01–DR06/DR05](../MISHI_RADAR_TO_CHSTOCKDATA_DR01_DR06_CONSUMER_REQUEST_2026-10-16.md)及既有代码、测试证据。两个核心消费者副本与 Mishi 当前原件仍逐字节一致，见 [analysis.json](evidence/2026-10-20-w5h-r2/analysis.json)。

S07 为首发必交；当前全市场扫描、历史单股规则检验与历史 Top N 现金组合均必交；目标近约一个交易年度，另含规则预热和财务基期。不得把未来修订值回填为过去已知。**PE 具体选型、ROE 算法/阈值、调仓参数、精确商品窗口尚未因 Scope Approval 冻结**；不能因本轮静态 PE 单点较好就自行把 S07 改为静态 PE。

chstockdata HEAD 为 `69957a58bcfd258f011c9c80250b58704fe0d784`，正式包基线 v0.4.3、tag target `30cc7c50e3971fe79bfd903a412b2b76a0338caa`。本轮开始时 Mishi 为 `76012c0db977d21832378c473638c271d8c1a554`，SIOS 为 `554012d1746a0c7476d1db668fb97ceec193578d`，不沿用上一轮旧 Mishi HEAD。原工作树见 [before.json](evidence/2026-10-20-w5h-r2/before.json)。

W5-H 的康美原报、更正披露及 **729 行估值直接复用，网络重取 0**；旧 manifest 中 **30 项产物重新验证散列通过**。现有 `a_stock.py` 与 W5-H 记录身份一致，公共三表/公告过滤、ROE 期对齐、估值摘要边界不变；既有 36 个财务/估值离线测试结果只作既有行为证据，本轮没有重跑发行 Gate 或把旧测试数当新源资格。

## 2. 方法、预算、来源治理与停止

使用 `firecrawl-deep-research` 的分方向研究流程，两名研究子代理分别核对 AKShare 血缘及其他授权路径；二者均只读官方文档/源码，市场数据请求、安装及写文件均为 0。生产者统一执行实际探针。Firecrawl 沿用上一轮账户信息 fetch failed 的记录，未修复账号或重复预检；网页工具作为等效只读文档渠道。

### 2.1 事前限制与实际账本

[audit_tools.py](evidence/2026-10-20-w5h-r2/audit_tools.py)在探针前规定总 HTTP 上限 **28**、同源前次完成后至少 **3 秒**、单次连接/读取超时 10/15 秒、响应体上限、自动重试 0、自动重定向 0。每批命令在执行前固定来源、证券、表/指标、日期用途及请求数；资格成功才继续必要字段。通达信只请求目录和一个固定报告期文件，不遍历报告期；其他市场记录均限 600518/600519。

实际直接 HTTP **22/28**，保存 **1,820,914 字节**；同源完成后最小间隔实核 **3.000091 秒**。全部串行，没有复现 W5-H 的节流偏差。通过现有 `source_context.call_source` 执行；独立进程没有安装宿主 SourceGovernor 上下文，故使用上述更保守的本地预算/停止守卫，**不声称已运行宿主 Governor 的全套策略**。未修改其源码、配置或冷却状态。

| 来源/用途 | 实际请求 | 原始结果与处理 |
| --- | --- | --- |
| 通达信官方说明、目录、2017 年末文件资格 | 3 | 说明和目录有效；目标 ZIP 请求 HTTP 200 但为 985 字节 script/HTML，**不是财务数据成功或正常空**；立即停止该数据路径，不执行脚本、造 cookie、换主机或走镜像。 |
| 同花顺 600518 利润、现金流、资产负债三表 | 3 | 均业务 `status_code=0`，各 50 个报告期，共 150 条表×报告期记录；不是 150 个独立期间。 |
| 百度固定证券 TTM/静态 PE/市值及路由定位 | 7 | 初始域名 2 个 301（含一次不带证券参数的路由定位）；据公开 Location 手动选规范域名后取得 5 份有效图表。无自动跟随，无数据失败后换股。 |
| 同一 600518 的 2019 三季报原件 | 1 | HTTP 200。仅为核实既定 2020 年 TTM 所必需的财务基期，不是新增股票或寻优年份。 |
| BaoStock 官方目录及必要文档 | 8 | 一次 GET 目录为 405；复用旧官网账本确认 POST 方法后，取得目录及 6 份文档。文档方法纠正不等数据连接恢复。 |

HTTP 统计为 19 个 200、2 个 301、1 个 405；200 中包含通达信非数据响应，不能把 19 全记为市场数据成功。没有 401/403/429、TCP 数据连接或登录消息，没有验证码/权限绕过；也没有重新请求旧新浪/东财目标接口。网页工具为主代理 **8** 次、两子代理各 **6** 次，共 **20 次文档调用**，工具内部 HTTP/缓存选择不可观测，不与直接请求伪合并。部分通达信文档链接返回工具 Internal Error，未当成已取得实物。

完整请求参数、方法、时间、状态、长度与 SHA-256 见 [requests.json](evidence/2026-10-20-w5h-r2/requests.json)；官方文档/血缘记录见 [source_research.json](evidence/2026-10-20-w5h-r2/source_research.json)。所有新证据仅在[本轮有界目录](evidence/2026-10-20-w5h-r2/)；最终 [manifest.json](evidence/2026-10-20-w5h-r2/manifest.json)列明产物身份。原始响应、网页观察摘记与计算结果分开，不以今天的散列冒充历史首见时间。

### 2.2 BaoStock 为什么没有再次登录

复用 [DR01 原失败记录 §4](../DR01-current-free-data-feasibility-2026-10-19.md)：2026-10-19 两次公共节点连接各发一条 login，分别 8 秒、15 秒接收超时，错误 `10002007`，数据查询 0。两次已有外网访问条件，不是仅沙箱拒绝。

本机仍是既有 SDK 0.9.3，公共入口仍为 `public-api.baostock.com:10030`；未发现新出口、新可用公共节点或现成成功会话。官网文档 HTTPS 可达不等于 TCP 服务可达。**时间过去、任务改名或换财务函数不是实质新测试条件**，故本轮新 TCP 连接、login、金融数据查询均为 **0**，状态 `ACCESS_BLOCKED`。不配置 key、不转 vip、不搜索凭据、不重试碰运气，也不把访问失败判为财务数据错误。

## 3. 通达信优先调查

### 3.1 官方能力与真实使用条件

[专业财务官方下载说明](https://www.tdx.com.cn/article/stockfin.html)限定适用于具增强功能集的券商版及个人收费版，包解压至 `vipdoc/cw`。这允许“已有增强券商端可能已有合法权限”，**不证明所有免费客户端有此权限，更不证明本机具备**。

[TdxQuant 财务文档](https://help.tdx.com.cn/quant/docs/markdown/TdxQuant.md/mindoc-1h10m001ic888.html)有 `get_financial_data(stock_list,field_list,start_time,end_time,report_type)`，区分 `announce_time` 与报告期 `tag_time`；有盈利、OCF、权益、ROE、股本及财报公告日字段，例如 FN232/FN234/FN271/FN314。文档还存在签名默认 `report_time` 与参数表 `tag_time` 等版本表述差异，须以实际合法客户端版本核定，不能据猜测参数调用失败裁定来源不存在。

FN314 的 YYMMDD 与输出 announce_time 的 YYYYMMDD 要分清；文档字段单位同时出现元、万元及比率，不能按统一倍率处理。公告日期查询只是日期筛选能力，**未证明保留同报告期原版与更正版**。

[股票交易数据按日期入口](https://help.tdx.com.cn/quant/docs/markdown/TdxQuant.md/mindoc-1h2pci5gh6h7k.html)也要求预先下载股票数据包。本文未取得可核的指定日 PE 字段/方法及原始行，标 `NOT_VERIFIED`，不从“股票数据”四字推断每日 PE 已可交付。当前 mootdx `finance()`/F10 快照也不替代专业包或历史估值。

### 3.2 本机与文件实际结果

[local_inventory.json](evidence/2026-10-20-w5h-r2/local_inventory.json)记录限定位置检查：

| 项目 | 实际结果 | 限制 |
| --- | --- | --- |
| `C:/new_hxzq_hc`、`C:/zd_zxzq_gm` | 两个通达信客户端目录存在，`vipdoc/cw` 均存在但文件数为 0 | 安装目录不证明增强功能、授权或下载能力；未登录/操作客户端。 |
| 当前 Python 环境 | mootdx 0.11.7、AKShare 1.18.64、BaoStock 0.9.3 已有；TdxQuant/tdxquant/tqcenter/tqserver/tdxaidata/xtquant/jqdatasdk/rqdatac 未发现 | 仅当前解释器和具名客户端根目录，不是全磁盘/全部账号不存在的声明。 |
| 既有 VIPDOC 日线 | 仍可复用既有 RAW 价格能力 | 明确不是专业财务包或每日 PE 库；不拿其存在证明财务资格。 |
| 官方财务目录 | 匿名 HTTP 取得目录，含 `gpcw20171231.zip`、声明长度 4,206,396 字节及 MD5 | 只证明当前目录列有文件，不证明其原始版、覆盖、许可或内容。 |
| 该固定文件 | 实际收到 HTTP 200、text/html、985 字节，开头非 ZIP 标志，含脚本/跳转特征 | 未取得可解析包，未解压、未取出任何证券财务行；原因未判定为收费、限流或文件不存在。 |

已装 mootdx 读取器的静态格式是报告日期/记录大小等头、股票代码/偏移索引、float32 数值字段；它读出按期间命名的文件，不自行带来历史获取快照。因真实文件未取得，本文**不据静态 reader 声称通达信全部数据只留最新值**，也不将文件日期当公告日或当时可得版本。

结论：`DOCUMENTED`，目录可访问；**目标财务数据 ACCESS_BLOCKED/RAW_SAMPLE_NOT_OBTAINED**。已有权限、免费取得条件及三状态旧版资格仍未知，不能上调为合格，也没有足够证据永久否决这一方向。

## 4. BaoStock 财务与每日 PE

除了用户给出的 [SDK 文档](https://github.com/zxygithub/baostock/blob/master/docs/pythonAPI.md)，本轮实际取得现行官网[盈利](https://www.baostock.com/mainContent?file=seasonProfit.md)、[现金流](https://www.baostock.com/mainContent?file=seasonCashFlow.md)、[偿债](https://www.baostock.com/mainContent?file=seasonBalance.md)、[每日估值](https://www.baostock.com/mainContent?file=valuationDaily.md)与[调整记录](https://www.baostock.com/mainContent?file=modifyRecord.md)原文。

| 入口 | 文档实际字段/语义 | 对 S07 的边界 |
| --- | --- | --- |
| `query_history_k_data_plus` | 日频 `peTTM/pbMRQ/tradestatus/isST`；PE 文档以指定日价格、截至当日总股本与归母 TTM 利润解释 | **有具体逐日路线，不是摘要**；但没有本轮真实目标行、旧分母/历史修订资格，不能从公式文字判 PIT。 |
| `query_profit_data` | 年/季参数，文档称 2007 至今；`pubDate/statDate/netProfit/roeAvg/epsTTM/MBRevenue/totalShare` 等 | 发行日期与报告期分开；净利润/归母/累计或单季、ROE 数值比例与字段原值仍须实物核定，不由示例推全覆盖。 |
| `query_cash_flow_data` | `CFOToOR/CFOToNP/CFOToGr` 等比率及日期 | **不是已证实的 OCF 绝对值出口**；不能用舍入比率反推原始 OCF 并称无损。 |
| `query_balance_data` | `currentRatio/quickRatio/cashRatio/liabilityToAsset/assetToEquity` 等 | **不是已证实的归母权益原值出口**；不能以倍率/ROE 倒推必要分母。 |
| `query_operation_data`、杜邦等 | 营运/派生指标及日期；已有 SDK 可定位 | 不能仅因函数数量多，补写成完整三表、历史版本或首见字段。 |

官方调整记录明确曾在 **2019-11-23** 修正 2019 二、三季若干财务比例的百倍格式差异，涉及 ROE、CFO 比率等。它证明服务会调整历史数据，也提供部分全局调整日期；**不是康美原报/更正版逐记录档案，不证明原数值仍可查询**。`pubDate` 是公司发布日，不能冒充平台入库/首见时间。

现有 SDK 单证券/年/季请求与分页形态可复用，但没有足够证据说所有函数只返一版或绝不保留原版。财务和每日 PE 分别为 **DOCUMENTED/PARTIAL_FIELDS + ACCESS_BLOCKED**；不是财务服务经实测失败，也不是可交付 PASS。

## 5. AKShare：实际不同上游与固定更正案例

AKShare 是封装层。已核对本机 1.18.64 的定向源码与[官方 THS 源码](https://github.com/akfamily/akshare/blob/main/akshare/stock_fundamental/stock_finance_ths.py)、[百度源码](https://github.com/akfamily/akshare/blob/main/akshare/stock_feature/stock_zh_valuation_baidu.py)。再次调用同一新浪/东财上游的别名不计独立来源，本轮未重跑那些路径。

### 5.1 同花顺新版三表

直接上游 `basic.10jqka.com.cn/basicapi/finance/index/v1/app_data/`，600518、market=17、page=1、size=50、period=0，分别 `client_stock_benefit/cash/debt`。这是与旧新浪/东财**不同的直接请求入口**；更深供应商是否共享仍 UNKNOWN。没有账号/token 参数，实际可访问不等长期免费/商业授权。

三表各 50 个报告期，实见 **2014-03-31—2026-06-30**；provider total 分别 105/100/104，未追其余页。2017 年末每表均只出现一条目标记录；元数据为报告期、报告名称、季度名称等，未给原报公告日、修订 ID、首见时间或历史 T 参数。必要基期如 2016 年末权益行存在，但仍是今天返回的状态。

| 2017 年字段，人民币元 | W5-H 已保存原报 | 已保存更正披露 | 本轮 THS 原始字符串 |
| --- | --- | --- | --- |
| 营业收入 | 26,476,970,977.57 | 17,578,618,640.06 | `17578618640.0600` |
| 归母净利润 | 4,100,926,148.57 | 2,149,836,281.41 | `2149836281.4100` |
| OCF | 1,842,794,237.84 | -4,840,052,606.46 | `-4840052606.4600` |
| 归母权益 | 32,032,959,807.76 | 28,413,344,515.00 | `28413344515.0000` |

四项均匹配已保存的修订披露，不匹配原报。原始字符串有四位小数，但披露对应的是元/分精度；不能宣称四位经济精度。此证据补齐了上轮未解析权益响应的数值对照，**没有补齐旧版或首见身份**。现有代码的平均权益 ROE、披露的加权 ROE及消费者最终公式仍分开，不在此计算策略评分。

### 5.2 三个历史状态的资格检验

本轮没有把一个缺失 as-of 参数的接口重复请求三次或人为塞入日期。一次固定响应即可核对它能否表达要求：

| 历史 T / 受检 2017 年报 | 应有信息状态（沿用原件） | 替代结构化来源实际证据 |
| --- | --- | --- |
| 2018-04-24 | 不使用此原报及更正值 | THS 无公告/版本时间，不能证明当时的不可见性；TDX/BaoStock 未取到目标行。 |
| 2018-04-27 | 能识别 2018-04-26 已披露原版 | THS 受检同期间仅有修订值，**原版不可交付**；不能按报告期过滤冒充原版。TDX/BaoStock UNKNOWN。 |
| 2019-05-06 | 能识别 2019-04-30 更正披露 | THS 当前值与该更正数值相符，**但没有证据证明该版在该 T 已由源端可得**；不记 as-of PASS。 |

因此 THS 的 `HISTORICAL_VALUE_VERIFIED` 仅指受检修订值与披露一致；`ASOF_VERSION_VERIFIED` 为 **NO**。不能把原件中有原值误写成 THS 已提供原版；同样不能把 TDX/BaoStock 访问不足误写成“不保存原版”。

## 6. 百度历史估值：原始序列、回填检查及正反证据

### 6.1 入口与实际序列形态

已装封装仍指向 `gushitong.baidu.com/opendata`，实际 301 指向公开规范域名 `finance.baidu.com/opendata`。本轮保留该路由事实及两次 301，未把它记为正常空。规范域名响应业务 ResultCode=0，包含证券、指标、chart 类型、单位和 `date/value` 数组。

| 固定响应 | 真实点数/范围 | 频率、单位与局限 |
| --- | --- | --- |
| 600518 TTM / 全部 | 624 点，2001-03-19—2026-10-19 | **每 15 日一个点**，含 178 个周末点；不是指定历史年度的逐交易日序列。 |
| 600518 TTM / 近一年 | 366 点，2025-10-19—2026-10-19 | 每自然日一点，105 个周末点，118 个负值；与正式交易日历仍需联验。 |
| 600519 TTM / 近一年 | 同期 366 点 | 105 个周末点、负值 0；固定盈利对照。 |
| 600518 静态 PE / 全部 | 同期跨度 624 点，每 15 日 | 正负值均保留；原始 PE unit 为空，按比值理解而非百分数，源显示两位小数，具体分母合同仍待核。 |
| 600518 总市值 / 全部 | 同期跨度 624 点，每 15 日 | 原始 `unit=亿元`、两位小数；不能直接当无损元值或历史股本原值。 |

序列均无受检空值，但这不是所有证券/日期缺失语义的认证。`releaseDate` 在此是图表给出的 2001 年起始日期，不能解释成每条 PE 当时的初次发布。`data_source=AE` 含义未核明，不从这个码推断“独立于东财”或具体供应商。

两个近一年 TTM 响应各与旧东财 2025 数据相交 **53 个交易日**（2025-10-20—12-31），按百度两位小数舍入后各 **53/53 一致**。2025-12-31 分别为 600518 **1587.29**、600519 **19.16**。这是数值/日期的交叉对账，不能证明血缘独立、2025 全年逐日覆盖或历史当时版本。全年旧东财 243 行仍仅作为旧证据复用。

### 6.2 2020 年固定案例：静态 PE 的有利证据

“全部”图表没有 2020-01-02 点，不能插值或用邻日冒充。选定同一 **2020 年窗口**内实际返回且旧估值包也有的 **2020-01-09** 作诊断，不替换证券、年份或掩盖缺失。

| 原始行/对照 | 数值 |
| --- | --- |
| 百度静态 PE | **16.56** |
| 百度市值 | **188.01 亿元** |
| 旧东财该日市值 / 静态 PE | 18,801,197,131.50 元 / **-4.03400730** |
| 已保存 2019-04-30 原披露的 2018 归母年度利润 | **1,135,188,498.44 元** |

按百度原始市值换为元除以上述当时年度利润，约 **16.5620**，与 16.56 在其显示精度内相符；旧东财负静态 PE 则不同。**这是新来源确有不同历史处理且该静态单点与当时原报相容的正面证据**，不能把百度整体说成旧接口别名或所有历史估值都错。它仍不证明完整日序列、全部修订时点及源首次可得。

### 6.3 TTM 必要基期核验：不能因静态单点正确就升级

为检查同日 **TTM**，仅新增读取同一证券的[2019 三季报原件](https://vip.stock.finance.sina.com.cn/corp/view/vCB_AllBulletinDetail.php?id=5717789&stockid=600518)，公告日期 **2019-10-30**，保留 raw 和 SHA。理由是 TTM 需要当年累计、上年年报及上年同季比较；未换股票、未运行回测，也未重取已有 2018 年报摘要。

该原件的归母净利润列为 2019 年 1–9 月 **33,173,948.69 元**、2018 年 1–9 月比较值 **689,158,719.06 元**。与已保存 2018 年报的年度利润组合：

`1,135,188,498.44 + 33,173,948.69 − 689,158,719.06 = +479,203,728.07 元`

使用百度同日原市值，按这组已披露基期得 PE TTM 约 **+39.23**；百度该日 TTM 却为 **-7.02**，旧东财为 **-66.79112414**。符号差异无法由两位精度或元/亿元换算解释。THS 今天 2018 年度利润又为修订后的 **374,492,320.9700**，显示跨基期版本选择确实会改变 TTM，不能混合今天各期值回推原信号。

**裁决边界：**受检百度 TTM 未能通过与这组当时披露归母基期的口径/年代一致性检验；不能供 S07 作为已合格 TTM。尚未核完 2019-10-30 至该 T 的全部临时更正/快报链，也没有源端分母身份和历史公式合同，故不把不一致原因擅自定为已查清的回填算法。静态 PE 的有利单点与 TTM 的矛盾分别保留；不因 S07 PE 选型未冻结，自动替 Owner 选择较方便的方法。

## 7. 其他现实路径及公开档案重建

| 候选 | 官方能力与实际条件 | 当前资格 / 最小工程边界 |
| --- | --- | --- |
| [聚宽 JQData 官方 SDK](https://github.com/JoinQuant/jqdatasdk/blob/master/jqdatasdk/api.py) | `get_valuation` 有 code/day、TTM PE、股本/市值；`get_history_fundamentals(watch_date=...)` 描述观察日以前披露记录，stat_date 是报告期且二者互斥；均有认证前置 | 未发现已安装 SDK 或已证明的现成授权，不搜索账号/密码。当前[试用规则](https://www.joinquant.com/help/api/doc?name=logon&id=9830)文档访问受地区限制，历史免费额度不能当 2026 权限。若已有合法账号可作固定三状态核验；本轮无数据实物，UNKNOWN。 |
| [QMT/xtquant](https://dict.thinktrader.net/nativeApi/xtdata.html) | Balance/Income/CashFlow/Capital 与 `announce_time/report_time`，下载按 m_anntime 筛选；需对应终端及数据权限 | 本次当前环境未发现 xtquant/已确认终端缓存；未证明账号或权限。公告日筛选不等保留修订前版本。不能把部分特色服务收费推为所有三表必收费，亦不能把券商软件一概免费。 |
| [RQData 能力对照](https://www.ricequant.com/doc/rqdata/python/stock-mod) | `get_pit_financials_ex(date=T,statements='all')` 文档明确同报告期多条记录及 info_date；if_adjusted 是比较期身份，不是错误更正标志 | [许可证/配额](https://www.ricequant.com/doc/rqdata/python/manual.html)需有效授权，未建立本机已有权益，价格 UNKNOWN。只作成熟服务对照，**不计免费合格来源**、不试用注册/购买。 |
| 交易所/巨潮公告档案 | W5-H 原件及本轮三季报已证明若干不同历史版本原值真实存在，可作独立核对 | 只有在结构化路径不足后才评估重建；本轮没实现爬虫/财务库。AKShare 巨潮股本接口需 JS 签名及外围元数据核对，本轮没有必要为已取得市值诊断安装依赖或展开新采集。 |

公开档案重建在**字段事实层面有局部可行证据**，不是免费数据完全不存在。但完整用途需要每证券每期间原报/更正/比较期关联、原件日期/版本、合并/母公司与累计口径、单位、权益基期及历史股本/价格；手工/自动解析和版本覆盖均有成本。原文存在不能独立证明某平台当时首见时刻；没有完整清单分母、异常比例和解析成功率，不给固定人日、SLA 或完整商品日期承诺。本轮不把它预设为首选实施方案。

## 8. 八层资格矩阵与 S07 字段差距

以下每层按目标能力单独计，不能从文档或局部数值跳级。Y=该局部层有实证，P=部分，U=未知/未取得，B=数据访问阻断，N=目标必要检验未通过。RAW 的 N 表示未取得，不表示来源不存在。

| 来源 | DOCUMENTED | ACCESSIBLE（目标数据） | RAW_SAMPLE_OBTAINED | HISTORICAL_VALUE_VERIFIED |
| --- | --- | --- | --- | --- |
| 通达信专业财务/股票包 | Y | B；文档/目录可达 | N | U |
| BaoStock 财务 | Y | B；沿用两次登录失败 | N | U |
| BaoStock 每日 PE | Y | B；没有新条件 | N | U |
| THS 三表（AKShare 路径） | Y | Y | Y；150 表×期记录 | Y；受检修订值，不含原版 |
| 百度估值（AKShare 路径） | Y | Y；规范域名 | Y；5 份图表 | P；2025 交集/静态单点，TTM 有矛盾 |
| 聚宽 | Y | U；权益未建立 | N | U |
| QMT | Y | U；终端/权限未建立 | N | U |
| RQData，非免费对照 | Y | U；授权未建立 | N | U |
| 公告原件 | Y | Y；选定原件 | Y；沿用+必要基期 | Y；选定字段及公告日期 |

| 来源 | ASOF_VERSION_VERIFIED | REQUIRED_FIELDS_VERIFIED（完整 S07） | COVERAGE_FEASIBLE（一年全池+基期） | DELIVERY_READY |
| --- | --- | --- | --- | --- |
| 通达信 | U | U；文档有字段 | U；当前包版本/退市覆盖未核 | N |
| BaoStock 财务 / PE | U | P；财务多为比率，原 OCF/权益未证 | U；文档跨度不替代实物 | N |
| THS 三表 | N；固定原版缺失 | P；数值/基期在，历史版本/公告缺 | N；不能用最新值满足 PIT | N |
| 百度 | N；完整版本未证，TTM 未过 | P；估值值而非完整财务/股本 | P 仅数值路径；受检全历史降采样 | N |
| 聚宽 / QMT | U | U | U | N |
| RQData | U；尚未实测 | U | U | N |
| 公告原件重建 | P；仅选定披露身份 | P；未取得完整链及全部基期 | U；无完整证券×版本分母 | N |

| 必需项 | 本轮增加的证据 | 仍缺少 / 首版影响 |
| --- | --- | --- |
| 盈利、OCF、归母权益 | THS 四项修订原值与披露一致；原始字符串保存 | 当时原版和修订时间链未交付，无法可靠重建原版后的 S07 判断。 |
| ROE 分子/分母与基期 | THS 存在多期权益与利润，TDX 文档具必要类别；BaoStock 有派生 ROE | 不把派生比率反推无损分母；同一 T 的基期版本、累计/TTM及消费者算法未核齐。 |
| 报告期、公告日期 | THS 有期间；原件有日粒度披露；TDX/BaoStock 文档有公告字段 | 财报期间、公告、平台首次可得、修订回填仍不是同一时间。无候选通过完整首次可得资格。 |
| 原版/更正版身份 | 固定原件继续成立；THS只交修订数值；TDX/BaoStock 未取目标行 | 无完整免费结构化版本路径实证，不能用新 API/字段名弥补。 |
| 指定日 PE/单位/精度 | 百度原始数组与市值单位；2025 各 53 日与旧源对账，2020 正反例 | 完整 TTM 资格、任意历史年逐日出口及每条修订身份未过；相近数值不证明独立源。 |
| 历史股本/价格核验 | 百度/旧东财同日市值数量级相符；TDX/QMT/聚宽有股本相关文档 | 尚无来源合格的历史股本原值/变更与股价整链。市值诊断不能冒充独立历史股本认证。 |
| 全池/行业/交易资格 | 无新增相应资格 | DR01/03/06 独立阻断保留，不能从两证券成功推广 Top N 全池，也不能以单股回测绕过。 |

## 9. 组合路径、全市场可行性与成本边界

### 9.1 组合不是简单相加

| 组合 | 可复用/机会 | 必要缺口与裁决 |
| --- | --- | --- |
| 通达信财务 + BaoStock PE | 不同服务接口、字段类别互补，有条件保留 | 两端目标数据访问及历史版本均未验；不能记覆盖或交付就绪。 |
| 通达信财务 + 百度估值 | 现有通达信客户端线索，百度确有数值；静态单点有利 | 财务旧版未知，TTM 矛盾/静态全链未证；不能自行改选 PE 方法使组合“通过”。 |
| BaoStock 财务 + 独立估值 | 有免费公共服务文档 | 财务原 OCF/权益未证，旧版/接入阻断；百度深层血缘也未知。 |
| THS 财务 + 任意另一 PE | 当前修订原值覆盖类别较好 | **单纯换 PE 不能恢复已缺失原报版本**，不是可验收历史组合。 |
| THS + 公告更正覆盖 + 历史价/股本自算估值 | 已有原件证明部分旧事实能获得 | 属公告重建/版本装配工程与原件覆盖任务；需要独立授权/成本，不是轻量接口 CR。 |
| 已有授权聚宽/QMT 等一体数据 + 公告锚 | 理论减少跨源口径拼接 | 尚无实际权益、固定样本或首见链；不能以 SDK/文档取代资格。 |

THS/Baidu 的直接域名和请求确与旧接口不同，且 2020 静态 PE 实际处理不同；但共同引用披露、共享更深供应链或独立重算均可能。2025 舍入后一致不证明两票独立来源，`AE` 不解码成已知供应商。组合须保留 code/市场、报告期、公告/版本、币种、金额倍率、合并/归母、累计/TTM、PE 分母/股本/日历及缺失状态，不能静默拼接。

### 9.2 数量级可以评估，交付率不能编造

设 N 为**未来已批准、含退市证券的历史池分母**，F 为规则所需财务期间数，D 为目标交易日另含预热；本轮不冻结它们。

- **TDX：**按期间/股票数据包批量获得的形态，可能降低逐股网络次数；本次目录对单个 2017 包标称约 4.21 MB。未取得实际包、字段格式/退市成员/版本或合法访问条件，不能外推 K 个包就齐备，也没有真实导出速度。
- **THS：**按受检入口三表初始取得约 `3×N` 请求，每次最多 50 期，F 超过上限还要分页；本证券三表约 **1.36 MB**，其他股票异质性未量化。若仅机械按本轮 ≥3 秒守卫计算，请求间隔本身至少约 `3×(3N−1)` 秒，再加网络时间；这是单次全量刷新下界示意，**不是源允许频率、吞吐或 SLA**，也不能解决版本缺陷。
- **百度：**单指标/证券的受检形式约 N 次请求，TTM、静态 PE、市值各取则约 3N 次；近一年各 366 个自然日点。超一年/预热与指定 2020/2025 的逐日覆盖不能由“全部”624 点补足；退市证券没有本轮实物。请求、精度、日历与期限限制须先定，不承诺完整历史。
- **BaoStock：**按单证券/季度/函数，财务约 `N×F×必要函数数` 的逻辑查询，日频 PE 还要区间/分页及成功传输对账；SDK 页面数不等请求条数。连接失败时没有可用吞吐，文档更新时刻不是实测 SLA。
- **公告重建：**至少要 N×F 的披露集合、全部相关更正/比较期和必要股本事件；解析、手工歧义与版本关联的成本没有可推成功率。**1 个更正案例被固定选入，不可用来估计全市场更正比例**。取得该比例需要合法完整披露分母或之后预声明有界样本，本轮无必要再扫市场。

退市覆盖、无分类与金融股排除、源稳定性/允许自动请求额度、历史异常比例及对外商业展示/再分发权均未合格。免费网页可取、软件 MIT、券商端已安装分别不是数据商业授权；本轮没有进行法律专项或认定收费必需，也没有报价/人日承诺。

## 10. 最终建议、一个后续包与 Owner 决策

**选择 ACCESS_OR_EVIDENCE_INSUFFICIENT 的原因：**已有明确失败的是受检 THS 原版出口、百度 TTM 的基期一致性及部分图表逐日覆盖；**通达信/BaoStock 是访问/实物不足，聚宽/QMT 是权限未建立**，尚不能区分其底层不可行和当前环境不足。因此不选 QUALIFIED，不以多重未知冒充“只缺一项”的 PROMISING，也不把部分候选失败扩大成全部免费路径均已证伪。

**对“有没有值得下一项最小验证的路径”的直接答复：有条件保留通达信专业财务路径；目前没有可直接进入交付实现的合格免费路径。**优先它的理由是本机已有客户端线索、官方字段类别和批量文件合同覆盖所需数值，且关键版本问题仍未被实物否决；相较已受检丢失原版的 THS，下一次固定测试更能改变决定。但“已有客户端”不替代合法增强权限，当前不初始化客户端或安装 SDK。

唯一后续候选 **`W5-H-R3-TDX-LOCAL`**：仅在 Owner 指定一个**现成合法增强终端或可解析专业财务文件**后，对 600518/2017 固定三截止日进行一次本地/既有权限导出核验；要求原收入/归母利润/OCF/权益与必要基期、原/更正公告身份及源实际能提供的版本/更新时间证据。若已有股票数据能提供所选 PE，再限定原两证券、2020/2025 锚点核其方法；没有相应事实不得扩大下载。资格包不接 runtime、不开发 Provider/API、不重建数据库或运行收益回测。

该包的输入不到位就不派发；**不是让 Owner 批准再做一轮普通文档调查**。若合法现成文件仍只有修订值/日期过滤，或没有可核版本/时间依据，即对该路径停止并报告不足；若依赖购买、注册新权益、全市场补库、绕过脚本防护或超固定预算，也停止。即使固定版本样例通过，估值方法、完整一年全池/基期及消费者 Gate 仍独立验收，不自动进入下一 Phase。

比较后的现实备选保留顺序如下，**未自动实施任何一项，也不默认选择 D**：

| 备选 | Owner 可作的真实决定 |
| --- | --- |
| A 替代免费供应 | 优先上述通达信现成合法输入资格；BaoStock 仅在具名新可达条件出现后可受控测试。百度静态估值仅作为方法待定、资格未全的局部线索，不能借此改规则。 |
| B 已有权益的成熟服务 | 若 Owner 已有合法聚宽/QMT/RQData 导出，可交固定原件包核验，无需生产 SDK；本轮未证实任何该项权益，不采购或搜凭据。 |
| C 公开档案重建 | 在结构化路径仍不能满足后，可另评固定范围原件/版本装配及价股本自算的成本与数据用途；不是现成轻量出口，不把今天抓取当历史首见。 |
| D 供应成本、时间或产品 CR | 只有 Owner 显式选择，才能改变供应安排、发布承诺或消费者范围。本文不删 S07、不缩一年、不先发仅当前版，也不默认转付费。 |

## 11. 验证、分类与独立交接

[analyze_evidence.py](evidence/2026-10-20-w5h-r2/analyze_evidence.py)仅离线读已保存响应，校验本轮每份 raw 长度/SHA、旧 30 项产物、同源间隔、THS 修订原值、图表频率/周末/精度、2025 两组 53 日对账及 2020 分母计算，退出码 **0**。没有合成原报、构造旧值或策略运算。本轮实际代码/公共接口复用边界沿 W5-H，不从对其他库的研究暗中新增生产能力。

- **CONFIRMED_DEFECT（受检供应能力/口径）：**THS 单一报告期记录没有所需旧原版；百度“全部”不是逐日序列；百度 TTM 与选定已披露归母基期不相容。最后一项的实际原因及完整中间披露链尚未查清，不能扩大为全部历史/全部 PE 错误。
- **UNRESOLVED_RISK：**TDX 目标文件/增强权限、BaoStock TCP 可达及版本、其他服务权益、所有候选的完整首见链、PE/ROE 方法、退市与全池交集。TTM 不同不能自动判为独立血缘。
- **SPECULATIVE_CONCERN：**未采样证券可能更多错误、未来负载/限流可能变化；不据此追加工程或市场扫描。
- **FUTURE_ENHANCEMENT：**新 Provider、正式 PIT API、长期版本库、公告解析系统、全池采集、付费采购，均未授权。

**交接：**当前 W5-H-R2 调查/资格裁决完成，停 Owner Review；S07 历史 Gate **NOT_PASSED**。chstockdata HEAD、Mishi/SIOS 本轮起始身份见 §1；[verification.json](evidence/2026-10-20-w5h-r2/verification.json)记录本轮前后三仓库既有 tracked/未跟踪非 ignored 文件、HEAD、diff/index 对比，包含旧 W5-H 报告及证据的保护。仅新增本文及有界证据，无消费者/冻结合同/runtime/依赖修改，未暂存、提交、推送、发行；ignored 缓存不作全盘保护声明。剩余阻断与建议已收敛至上面**一个有输入条件的来源资格包**，不宣称下一阶段获授权。

```ini
CURRENT_DECISION = INVESTIGATE
W5_H_R2_VERDICT = ACCESS_OR_EVIDENCE_INSUFFICIENT

TDX_FINANCIAL_STATUS = DOCUMENTED / CATALOG_ACCESSIBLE / TARGET_DATA_ACCESS_BLOCKED
BAOSTOCK_FINANCIAL_STATUS = DOCUMENTED_PARTIAL_FIELDS / ACCESS_BLOCKED / NO_NEW_LOGIN
BAOSTOCK_DAILY_PE_STATUS = DOCUMENTED / ACCESS_BLOCKED / TARGET_VALUES_NOT_VERIFIED
AKSHARE_INDEPENDENT_UPSTREAM_STATUS = THS_AND_BAIDU_RAW_OBTAINED / ULTIMATE_LINEAGE_UNKNOWN / ASOF_NOT_PASSED
OTHER_FREE_SOURCE_STATUS = JQ_QMT_ENTITLEMENT_NOT_ESTABLISHED / RQDATA_NOT_COUNTED_AS_FREE

ORIGINAL_REVISION_CASE = ORIGINAL_REFERENCES_REUSED / ALTERNATIVE_STRUCTURED_PATH_NOT_PASSED
HISTORICAL_PE_ASOF = TTM_BASE_CONTRADICTION / STATIC_POINT_CONSISTENT / NOT_QUALIFIED
S07_REQUIRED_FIELDS = RAW_VALUES_PARTIAL / HISTORICAL_VERSIONS_AND_FIRST_KNOWN_UNQUALIFIED
FULL_UNIVERSE_FEASIBILITY = INSUFFICIENT_EVIDENCE / NO_FULL_MARKET_COLLECTION
SOURCE_ACCESS_AND_COST = PARTIAL_PUBLIC_ACCESS / ENTITLEMENTS_LIMITS_AND_COMMERCIAL_TERMS_UNKNOWN
SOURCE_LINEAGE_INDEPENDENCE = DIRECT_ENDPOINTS_DIFFER / ULTIMATE_INDEPENDENCE_NOT_PROVEN

RECOMMENDED_SUPPLY_PATH = TDX_EXISTING_LAWFUL_PROFESSIONAL_DATA / QUALIFICATION_FIRST
NEXT_MINIMUM_QUALIFICATION = CONDITIONAL_W5_H_R3_TDX_LOCAL_FIXED_CASE / NOT_STARTED
MISHI_S07_HISTORICAL_GATE = NOT_PASSED

PRODUCT_SCOPE_CHANGED = NO
IMPLEMENTATION_AUTHORIZED = NO
OWNER_REVIEW_REQUIRED = YES
```
