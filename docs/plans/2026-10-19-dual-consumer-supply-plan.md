# chstockdata 双消费者供给能力审查与最小交付规划

日期：2026-10-19，Asia/Shanghai。阶段：生产者只读调查与规划，**READY_FOR_OWNER_REVIEW**。

本文同时纳入原 DR01–DR06/P2 请求和本轮 H01/H04 增量指令；唯一新增交付物为本文。工作包、Gate 名称和交付顺序均为建议，不是已批准版本范围、实施任务或发行授权。

## A. Executive Decision

**CURRENT_DECISION = INVESTIGATE。先使已验收的 DR04-P 具备独立发行条件；复用既有原始价量额入口；尽早裁决 Mishi 历史底线的高风险来源。SIOS 按独立数据包处理，不要求经过同一 SDK。**

| 决策项 | 本轮裁决 |
| --- | --- |
| 原始目标 | 消除重复供应规划，为两消费者的必要输入逐项给出复用路径、最小缺口、可验收工作包和停止出口；本轮不开发。 |
| 正式消费基线 | v0.4.2，发布提交 `17af23fe8183f740150dc01dd877473afe3911b7`。main 是 `9543d03310b25be9963227a2a226366de04276ec`；main 的版本字符串仍为 0.4.2，不能据此将新增 P 视为已发行。 |
| DR04-P | Owner Acceptance PASS、已在 main、尚未发行；数值合同与验收证据身份匹配。不重开 P，不将其扩大为 M、PIT 或 S08 PASS。 |
| Mishi 当前 | 完整资格未通过。DR01 深市指定日全量停复牌事实仍阻断；DR03 缺完整行业成员公共合同；DR05 当前 S07 数值及全池口径未合格；DR04-M 未授权。DR02 有可复用原始 Amount 路径。 |
| Mishi 历史 | 完整资格未通过。原始价量额有有限实物，历史池/状态、行业有效区间、旧版财报/逐日估值、资金当时版本和执行事实仍有必要缺口。与 G1 同期裁决可行性，不等 G2。 |
| SIOS H01 | **BLOCKED**：RAW 可有限供应，但三 ETF 的完整总回报、份额事件和历史 T 可得性未证实；`ASOF = UNKNOWN / NOT_ACCEPTED`。不能用最新复权序列补作历史资格。 |
| SIOS P2 | **EXTERNAL_SOURCE_PREFERRED**：复用已有生产者响应，优先已有权限的成熟供应商直接导出；当前无合格完整包/可用认证入口，不能恢复实验。 |
| SIOS H04 | 总回报输入 PARTIAL / NOT_ACCEPTED；历史归因输入 NOT_AVAILABLE（现有公共能力）/ UNKNOWN（外部现成包）。维持 **STOP_CURRENT_INSTANCE**，两类必要缺口独立。 |
| 已确认与未确认 | 已确认公开合同边界、来源失败和候选输入异常；没有确认“所有免费来源永远不可行”，也没有新增已发布代码缺陷或经济机制失败结论。 |
| 路线与授权 | 不修改 Mishi 八策略、全市场或一年另含预热底线；不改 SIOS 三个实例。无平台扩建、采购、版本号/日期/工期承诺。下一实施/发行阶段 **NO**；停在 Owner Review。 |

最小下一决定是：Owner 是否授权 **W0：DR04-P 独立发行就绪验收**，只形成可审的发行候选证据，不直接发布。SIOS 内部优先级 H01 ＞ P2 ＞ H04 保留；这不覆盖 Mishi G0–G3，也不自动重排整体工程。

## B. Baseline & Source Authority

### B1. 三仓库真实身份与适用规则

| 仓库 | HEAD / 分支 | 开始时工作树及规则 |
| --- | --- | --- |
| chstockdata | `9543d03310b25be9963227a2a226366de04276ec` / `main` | tracked diff 为空；`status --untracked-files=normal` 有 57 条既有未跟踪文件/目录，包括四份 Mishi 输入、P2 ZIP 和审计材料。适用根 `AGENTS.md`；本文所在 docs/plans 无更深规则。 |
| mishi-radar | `678872568c7425b773a0059ae551adc55b3040a3` / `main` | 已修改 README、PRODUCT_DISCUSSION、PRODUCT_NAMING、CURRENT_STATE 四文件；另有未跟踪需求/候选设计/outputs，normal 状态共 13 条。根及所读文档目录未发现项目 AGENTS，遵守本次用户级规则。 |
| systematic-investing-os | `554012d1746a0c7476d1db668fb97ceec193578d` / `codex/v010-owner-product-clarification` | 已修改 AGENTS、R2-global-exposure-opportunity-map；另有既存研究材料，normal 状态共 19 条。读取工作树 AGENTS 的研究/准入/停止纪律；所读目录无更深规则。 |

以上条数包含目录合并表示，**不是实际文件总数**。其他仓库的 Git 所有权检查通过命令局部 `-c safe.directory=<该仓库>` 读取，没有修改全局配置。原有全局 ignore/部分超长路径枚举警告不影响本轮所用定向文件；不声称审计了全部深层未跟踪目录。

CodeGraph 已优先使用：chstockdata 可返回部分相关源码，具体公共签名与行号另由当前源码 AST 核验；SIOS explore 返回 `unable to open database file` 后定向只读，没有修复索引。Mishi 无 `.codegraph/`。

**SIOS 权威恢复有一处必要时间差：**当前 checkout 的 v0.10 文本头仍是 Draft；实际读取既有 Git 对象 `7beb892cebc6bebd422d13c759ed2118c82b92c8:docs/personal-systematic-investing-os-v0.10-global-markets-research-direction-draft.md`，头部为 Owner Approved / Design Frozen，批准实质设计 `6913281145404fcb20d1057e04ac1599b135cba5`。采用该批准身份，不以旧 checkout 的 Draft 覆盖它；冻结 M0/M1 不因此扩成期货运行合同，M2 仍 BLOCKED。

### B2. 权威输入及内容身份

下表路径以本文所在目录为基准；跨仓库原件另标绝对路径。四份 Mishi 核心文档及 P2 包内四原件已完整读取；H01/H04 报告完整读取，特别核对 §3–§6。

| ID | 文件 / 权威级别 | 本轮核验的 SHA-256 / 差异 |
| --- | --- | --- |
| A1 | [R3.2](../MISHI_RADAR_V0_1_SPEC_R3_2_SCOPE_APPROVED_DATA_PENDING_2026-10-16.md)：Owner 批准产品范围，数据/全部运行参数未冻结 | `9b98641d4602fcd2a35c28520f9160a3fbf935ce1c43e89d466a473419e5bd62`；与 Mishi docs 原件逐字节一致。 |
| A2 | [DR01–DR06 请求](../MISHI_RADAR_TO_CHSTOCKDATA_DR01_DR06_CONSUMER_REQUEST_2026-10-16.md)：消费者字段/验收边界 | `35609c8cbf823dbb86a681ea15c27f7f598892b7ea73f46ecde5025e85ff8866`；与 Mishi docs 一致。 |
| A3 | [DR02–DR06 差距报告](../DR02-DR06-consolidated-gap-report.md)：待 Owner Review 的调查 | `21f62d51e2caf17e6cefa5deed6300c642f1a7e05765ff1c072c827f21eca118`；与 Mishi outputs 原件一致。副本内原相对链接按原仓库解释，不能当成本仓库有效链接。 |
| A4 | [DR01 免费来源可行性](../DR01-current-free-data-feasibility-2026-10-19.md)：来源调查，非实施批准 | `ba6162d8a50f26683cc1ad60152b135821c8395f2716874aa161f9f31157a01d`；与本仓库 audits 同名件一致。 |
| A5 | [DR04 最小合同提案](../dr04-minimum-consumer-contract-owner-review.md)、[P 公共合同](../dr04-p-daily-fund-flow.md)、[Owner Acceptance](../audits/2026-10-18-dr04-p-owner-acceptance.md) | 原合同 `1c7c37b1514032ef08d9714fe8cfa4f722c0f730af1e58608dbc6b45eaffeba1` 匹配。原提案的 P 已被后续接受事实更新，M 预算/SLA/连续批次数仍待审。 |
| A6 | [P2 交接 ZIP](../SIOS-P2-to-chstockdata-handoff-2026-10-19.zip)：需求草案和研究证据，非生产者实施授权 | ZIP `b60d242f870d69789d9e322eea53b3b444d1dced3f611c87d30035a3586975b9`。直接内存读取，未解压、未生成第二套附件。 |
| A7 | [既有 P2 生产者响应](../audits/2026-10-19-sios-p2-producer-response.md)：当日已完成的有界来源实测 | `327610beb4fa1d2c8a133cc6b5aa67fe05369c7a11ebf44422fce163115ea645`；43 项产物清单全部匹配。只使用 analysis-r2，旧 analysis/NOT_ACCEPTED 的结果不参与资格。 |
| A8 | [H01/H04 消费者报告](D:/Dev/Projects/systematic-investing-os/docs/m1-r2/R2-H01-H04-parallel-exploratory-admission-2026-10-19.md)：研究与增量数据请求 | `c8834096f005c29e9d8733e74a391bca0adc91f823544068357052286d9ae57d`。当前 checkout 可访问，不需寻找替代交接；本文不批准报告内待审实验数值。 |

Mishi 另有 2026-10-19 `MISHI_RADAR_R3_2_OWNER_DECISIONS`，实际头部为 `OWNER_REVIEW_PENDING / NOT_FROZEN / NO_IMPLEMENTATION_AUTHORIZATION`。其中规则、现金模型与运行数字不被本文升级为已批准供应标准。

P2 ZIP 身份明细如下；README 所列五份散列全部匹配，四份研究原件与 SIOS 当前文件逐字节一致。消费者请求仅以包内身份使用，不假定已有独立落库原件。

| 包内成员 | SHA-256 |
| --- | --- |
| `00-consumer-request/SIOS-P2-chstockdata-consumer-data-request.md` | `5063c687cd4223366cc2dcaf4ea425b57046f185f1470e1e5ede5b496795097a` |
| `01-evidence/R2-p2-directional-carry-minimal-falsification-design-2026-10-18.md` | `bf5ee4f5be19dbbf18411392be11e7656ce72f0078ebb06137d0a096c09bd0eb` |
| `01-evidence/R2-p2-final-exploratory-feasibility-verdict-2026-10-18.md` | `c706ca2ba68cfa7875d92cc9db3a441bd9c8c75eb407121a7b4e4072716042f2` |
| `01-evidence/R2-p2-first-exploratory-economic-falsification-2026-10-19.md` | `4b718773e93998580fe588507fcd6108575ebf47c966ce641dd5bf80537430a9` |
| `01-evidence/attempt-01/run_status.json` | `35bc86cfdde8817a04b330a86bc0dae2d70fd402536f7c7e59db2ae25ba92c39` |

### B3. 四种发行/批准状态

| 状态 | 本仓库实际内容 | 可否当作正式包消费 |
| --- | --- | --- |
| 正式已发行 | [v0.4.2 发行记录](../releases/v0.4.2.md)，发布提交 `17af23f…`，既有公共股票/ETF 合同 | 可以在其已认证范围内消费，不等于全市场/新消费者资格。A4 保存了当日 GitHub/PyPI 响应；本文未再次请求发行元数据。 |
| main 合入未发行 | DR04-P 入口、模型、fixture/test 及必要文档；main `9543d03…` | 不可声称已进入 PyPI v0.4.2。 |
| Owner 已接受、发行独立决策 | DR04-P Acceptance PASS；本次复算 final-check 的 20 项代码/证据身份全部匹配，原合同匹配，读取原 JUnit 为 142 tests、0 failures/errors/skips | 接受证明数值合同，不提供发布授权。上述 142 是旧验收结果，本轮不重跑 P。 |
| 设计/调查/来源资格阶段 | DR01 候选、DR04-M、DR03/05/06 增量、SIOS 三方向数据请求 | 不可作为已供应、已实现、已批准版本范围。 |

`git diff v0.4.2 HEAD -- src` 的运行源码变化只有 `__init__.py` 和新增 `daily_fund_flow.py`。DR02/03/05/06 既有实现未被 P 改写；没有现成商品期货历史公共出口。这里“main 合入”和“Owner 已接受”是两种不同资格，DR04-P 同时具备，发行资格仍未具备。

## C. Combined Demand-Capability Matrix

### C1. 公共入口、源码与测试证据目录

以下入口均核对包级 `src/chstockdata/__init__.py` 的实际导出。未发行的只有 E9；其余为 v0.4.2 已有入口。内部函数不作为可消费公共 API。

| 证据 ID | 精确公共入口与当前代码位置 | 合同/测试/实物及限制 |
| --- | --- | --- |
| E1 原始价量额 | `load_vipdoc_daily(code, start_date=None, end_date=None, *, root=None, market=None)`：[vipdoc_history.py:171](../../src/chstockdata/vipdoc_history.py#L171)；解析器 :98 | Date/OHLC/pre_close/Volume/Amount。股票价整数÷100；SH50/51、SZ15/16 基金价÷1000；Amount 源 float32 元，Volume 源 uint32，合同 shares，ETF 需按证券份额理解并核对来源。保留源格式精度，不声称无限精度。缺文件 None、空窗口空帧；不自动认证新鲜度。`pre_close` 为文件上一原始 Close，不是除息参考价。测试 `test_vipdoc_history.py:42,113`、`test_vipdoc_price_scale.py:43,54,84`。 |
| E2 默认日线 | `fetch_daily_bars(code, start_date, end_date, *, adapters=None, clock=time.monotonic)`：[daily_bars.py:655](../../src/chstockdata/daily_bars.py#L655) | 默认 VIPDOC adapter 的 canonical 化在 :294 删除 Amount；路由来源、状态可复用。mootdx 量为 provider_native_unknown，混源可为 mixed_provider_native。测试 `test_daily_bars_schema.py:90,140`、`test_daily_bars_contract.py:443,487,510`；有路由成功不等于 S05/S08 合格。 |
| E3 复权/指数/日历 | `get_adjusted_bars(symbol,start_date,end_date,*,adjust='qfq',period='daily',daily_bars=None,daily_source=None)`：[adjusted_bars.py:553](../../src/chstockdata/adjusted_bars.py#L553)；`fetch_trading_calendar(*,root=None,today=None,adapters=None,clock=time.monotonic)`：[trading_calendar.py:588](../../src/chstockdata/trading_calendar.py#L588)；另有公开 `load_trading_calendar(*,root=None,today=None,use_cache=True)` | 可传原始帧；raw/qfq/hfq、锚信息，量额不缩放。因子取当前新浪 hfq.js，QFQ 使用最新锚，**无历史 as-of 版本参数**。日历从 sh000001 指数及在线回落派生，非 SHFE/DCE 日历。指数必须带 `market='sh'`，裸 000001 默认是深股。测试 `test_trading_calendar_structured.py:102,206,543`、VIPDOC 价格测试；具体标的/区间独立验。 |
| E4 当前行情 | `get_realtime_snapshot(ticker)`：[a_stock.py:1574](../../src/chstockdata/a_stock.py#L1574) | Tencent→mootdx→Sina；价格、OHLC、amount_wan、PE/PB、涨跌停参考等。公开 snapshot 无累计 Volume、无源行情时间；observed_at 是获取时刻。`fetch_realtime_quotes(codes,fetchers,*,quote_number,clock=...)` 也是导出，但必须显式注入 fetchers，不是自动全市场主表。测试 `test_astock_quote_fallback.py`。 |
| E5 身份/状态 | `resolve_ticker(user_input)`：[a_stock.py:408](../../src/chstockdata/a_stock.py#L408)；`fetch_suspension_info(ticker,curr_date)`：[suspension.py:281](../../src/chstockdata/suspension.py#L281)；`fetch_delisting_status(ticker)`：[delisting.py:422](../../src/chstockdata/delisting.py#L422)；`fetch_tradability(ticker,curr_date,*,root=None)`：[tradability.py:107](../../src/chstockdata/tradability.py#L107) | 名称解析非主表；停牌仅当前自然日，历史/未来 fail closed；退市名单未命中不证明在市。tradable 仅覆盖既定日历/退市/停牌，不保证 IPO/ST/全部价格限制。测试 `test_suspension_source_semantics.py:32,42,56,63,73`、`test_delisting_structured.py`、`test_tradability.py:505,541`。 |
| E6 开盘代理 | `fetch_historical_opening_evidence(ticker,session_date,*,known_events=(),tdx_reader=None,official_reader=None)`：[opening_evidence.py:425](../../src/chstockdata/opening_evidence.py#L425) | R2.1 `[09:30,09:31)` 正活动+官方否决。:42 认证 510300/159915/518880/511010/513100/159509 六 ETF 与 688432/000002 两股控制；**不含 H01/H04 五 ETF**。有日期/来源边界，不证明盘前 PIT、全市场状态或任意委托成交。测试 `test_historical_opening_evidence.py:106,124,199`。 |
| E7 行业/板块资金 | `get_concept_blocks(ticker)`：[a_stock.py:7113](../../src/chstockdata/a_stock.py#L7113)；`get_industry_comparison(ticker,trade_date,top_n=20)`：:8030；`get_board_fund_flow(board_type='industry',period='today',top_n=20)`：[board_flow.py:61](../../src/chstockdata/board_flow.py#L61) | 前两者是当前背景/榜单文本，不是成员矩阵；trade_date 不使当前行业榜变历史。TDX/东财分类不等价。板块资金返回 dict、原始元值、total_count/count/source/observed_at，top_n≤200，industry/concept/region×today/5d/10d；无独立业务日或历史 as-of。测试 `test_board_flow.py:34,55,78`。 |
| E8 财务/估值 | `get_balance_sheet/get_cashflow/get_income_statement(ticker,freq='quarterly',curr_date=None,historical_review=None)`：[a_stock.py:3461,3497,3533](../../src/chstockdata/a_stock.py#L3461)；`get_free_financial_indicators(ticker,curr_date=None,historical_review=None)`：:3568；`get_fundamentals(ticker,curr_date=None,historical_review=None)`：:3058；`get_valuation_history(ticker)`：:5214 | 三表/指标多为格式化字符串，可做报告期/公告过滤；未证明保留修订前版本。估值 JSON 公开返回最新 metrics、percentiles、history 起止/行数摘要，**未输出逐日原始行，且无 as-of 参数**（实际 return :5415）。不能受误导性“series”描述影响。测试 `test_astock_financial_yoy_alignment.py:84,205`、`test_astock_margin_valuation.py:245,288,312,344`。A 股财务入口不支持港股归因。 |
| E9 日度资金 P | `get_sina_daily_fund_flow(exchange,ticker,*,target_date=None,start_date=None,end_date=None,calendar=None,budget=None,allow_requests=True,previous_observation=None)`：[daily_fund_flow.py:237](../../src/chstockdata/daily_fund_flow.py#L237)；公开 `FundFlowCalendar` :33、`FundFlowBudget` :51、`DailyFundFlowResult` :62 | main/Owner Accepted、未发行。同源新浪 r0_net，Decimal/十进制字符串，逐日状态、分页、预算、旧观测证据。P01–P12 测试 `test_daily_fund_flow.py:78–349`，身份冲突修复用例 :392 起；20项验收证据身份本轮匹配。COMPLETE 非 PIT/终局；原始零经济语义 UNKNOWN，日历 qualified 是调用方证据声明。旧 `get_fund_flow(ticker,curr_date,include_history=True)->str` 在 a_stock.py:7339，不替代 P。 |
| E10 公司行动 | `get_corporate_actions(ticker,announcement_start,announcement_end,as_of_date='',page=1,page_size=50)`：[a_stock.py:6646](../../src/chstockdata/a_stock.py#L6646)；`get_fund_corporate_actions(code,start,end,as_of_date='',page=1,page_size=50)`：:6670，基金实现 [corporate_actions.py:595](../../src/chstockdata/corporate_actions.py#L595) | 股票与基金合同分开。基金仅现金分红规范化，来源 FHSP+FHGG，per_10_shares；公告匹配缺失为 partial。as_of_date 只是公告日截止，不是保存历史版本；payment_date 不等于账户现金实际可用时刻，stock_dividend/transfer 为 None 不证明没有所有份额事件。测试 `test_fund_corporate_actions.py:64,106,132`；[已有说明](../fund-corporate-actions-and-vipdoc-contract.md)的旧 ETF 样本不能代替 H01/H04。 |
| E11 期货 | **无商品期货历史公共导出**；核对 __all__、源码及 A7 定向库存 | ETF 期权链不等于商品期货。现有 `.day` 证券包没有结算/持仓/真实月份法定身份。A7 的有限研究 CSV 不属于 SDK 公共合同，不能将其当完整 P2 包。 |

本轮最小验证仅为：7 个既有离线 DR02 用例通过（1.26s），四股+指数文件原始 Amount/Volume 与末条 struct 值一致；再对 H01 固定窗口作无收益的原始字段/日历对账。没有重跑完整发布 Gate、DR04-P Gate 或任何策略实验。

### C2. 跨消费者统一矩阵

状态只评价声明粒度：`ALREADY_SUPPORTED / SUPPORTED_WITH_BOUNDS / REQUIRES_SEPARATE_PROPOSAL / NOT_AVAILABLE / UNKNOWN`。SUPPORTED_WITH_BOUNDS 不表示该 DR 的完整 Gate PASS。Gate 中 BLOCKED 指必要事实/合同缺口；INSUFFICIENT_EVIDENCE 指证据不足，均不能进入实施或交付晋级。

| 消费者 | 需求 ID / 用途 | 必要事实/字段 | 已有公共入口 | 可用发行 | 供应状态/实际来源证据 | 时间/PIT | 缺口 | 公共 API 变更 | 建议方式 | 真实依赖 | 验收 Gate | 阻断/下一决定 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Mishi | DR01 当前 | 四板普通 A 股身份、上市/ST/退市整理/停复牌、分母 | E5（非全表） | 0.4.2 有局部 | REQUIRES_SEPARATE_PROPOSAL；A4 已有沪/深身份与沪状态，深全状态无实返 | 明确目标 D，非当天事件套过去 | 深市 D 全量状态；公共聚合合同 | 来源通过后才可能新增 | W1 窄事实快照候选 | 合格日历、同 D 官方集合；不依赖其余 DR 开发 | SOURCE=INSUFFICIENT_EVIDENCE；实施 BLOCKED | 新的可达证据/完整状态文件才可开一次验证 |
| Mishi | DR01 历史 | 当日含退市股票池、生命周期/ST/停牌有效区间 | E5/E6 不能补全 | 0.4.2 无完整项 | NOT_AVAILABLE；有当前官方事实，无一年历史全池 | 历史业务日与首次可知分开 | 幸存者/历史状态与版本 | 条件性独立提案 | W6 历史共用事实可行性 | 历史官方全集、有效日证据 | HISTORICAL_REPLAY BLOCKED | 限定一次完整性裁决，失败回 Owner CR |
| Mishi | DR02 当前 | OHLCV/Amount、基准、单位、当前报价 | E1/E2/E3/E4 | 0.4.2 | SUPPORTED_WITH_BOUNDS；四股+指数原始实物，最新全池未验 | RAW日/源/获取分开；报价源时点未知 | 新鲜全池、吞吐/基准；盘中触发另缺累计量 | **先不改**，默认路由无 Amount 可用 E1 | W2 复用 reader+字段映射 | 正式全池验收等 DR01；局部不等 | 局部合同证据可复用；全池 INSUFFICIENT_EVIDENCE | 批准更新/全池覆盖验证，先不加接口 |
| Mishi | DR02 历史 | 一年+预热原始/复权/基准价量额 | E1/E3 | 0.4.2 | SUPPORTED_WITH_BOUNDS；四股多年数据止 2026-09-22 | 当前因子回溯≠历史可知；分析/执行价分开 | 池×日覆盖、复权锚/事件版本 | 现路可先验证 | W2 历史覆盖+W6 | 历史池；执行依 DR06；预热由规则确定 | INSUFFICIENT_EVIDENCE | 冻结实际日期交集，不缩一年底线 |
| Mishi | DR03 当前 | 单分类ID/版本、完整双向成员/未分类 | E7 仅背景/榜单 | 0.4.2 无成员合同 | REQUIRES_SEPARATE_PROPOSAL；BaoStock证监会分类 DOCUMENTED | updateDate非成员生效/首次可知日 | 全量成员实物、分母、分类版 | 若来源合格需最小数值出口 | W3-C 来源资格后窄提案 | 局部不等 DR01；全池等其分母 | 当前成员 BLOCKED | 一套候选一次验证，不拼分类 |
| Mishi | DR03 历史 | 成员迁移/退市及分类有效区间 | 无 | 无 | NOT_AVAILABLE；日期查询有文档，无实物 | 当前回填/每周更新非历史PIT | 历史有效日、已知版本、一年覆盖 | 单独审议，不能借当前API承诺 | W3-H 有界可行性 | 历史池；分类版本 | HISTORICAL_REPLAY BLOCKED | 不可得则记录范围并 Owner CR |
| Mishi | DR04-P 当前/历史数值 | 同源金额、符号/元、逐日状态/原文/预算 | E9 | **未发行，main only** | ALREADY_SUPPORTED（仅已验收P合同） | 抓取时间非首次可知；零语义未知 | 发行；不含全池/PIT | 已批准增量在 main，不重设计 | W0 独立发行准备 | 不等 DR01/M/其他DR | P Owner PASS；Release未授权 | Owner 先决定发行就绪验收 |
| Mishi | DR04-M 当前 | 全池×五个完整市场日净额、覆盖/日期/恢复/成本 | E9 待发行 | 无正式M资格 | UNKNOWN；20股旧样本18股五日完整，非全池 | 数值完整/语义可用/过期分列 | 实际分母、预算/源允许频率、更新窗/连续批次 | 不预设；先复用P | W4-M 条件性受控资格 | DR01、合格日历、事前M授权；金额比率联验DR02 | M=NOT_AUTHORIZED/INSUFFICIENT_EVIDENCE | Owner先冻结预算与判据，禁止自行95%门槛 |
| Mishi | DR04 历史 | 一年同源序列、空洞、修订/当时版本 | E9 闭区间模式 | P尚未发行 | SUPPORTED_WITH_BOUNDS（历史数值）；两股各243目标日原文 | 历史数值≠历史as-of；PIT UNKNOWN | 历史全池/资金版本/零语义 | 不先增平台/API | W4-H 复用样本并判PIT边界 | 历史DR01；比率DR02；执行DR06 | HISTORICAL_REPLAY INSUFFICIENT_EVIDENCE | 不无限翻页换取名义PASS |
| Mishi | DR05 当前 | PE类型、ROE分子分母、利润/OCF/权益、报告/公告日 | E8 | 0.4.2 局部 | SUPPORTED_WITH_BOUNDS；三表/指标文本与估值摘要 | 报告期/公告日/取数日分列 | S07可核数值/全池口径/吞吐 | 先核现出口，仅数值不足才提最小补充 | W5-C 必需数值核对 | 独立核原值；排名等DR01/03 | CURRENT_SCAN INSUFFICIENT_EVIDENCE | 不将舍入文本当无损数值合同 |
| Mishi | DR05 历史 | 逐日估值、原版/修订财报及首次可知 | E8 不提供完整所需 | 无完整项 | REQUIRES_SEPARATE_PROPOSAL；公开逐日序列缺失，旧版实物未知 | 公告过滤不能恢复旧版 | 一年+财务基期的PIT交集 | 仅批准后窄出口；源缺口非API可修复 | W5-H 高风险先裁决 | 历史行业/池用于S07；不妨碍独立来源核对 | HISTORICAL_REPLAY BLOCKED | 原版+修订+真实日期无证据即停止/CR |
| Mishi | DR06 当前 | DR01状态+板块限制/涨跌停参考 | E4/E5 | 0.4.2 局部 | SUPPORTED_WITH_BOUNDS | 生效日不能用获取日替代 | 全池限制/已知与未知 | 与DR01共用事实，禁止第二主表 | W6-C 窄补充 | DR01身份；价格限制联验DR02 | INSUFFICIENT_EVIDENCE | 不把tradable当订单保证 |
| Mishi | DR06 历史 | 历史ST/停复牌/制度、公司行为、执行正反证据 | E5/E6/E10 | 0.4.2 有界 | SUPPORTED_WITH_BOUNDS（局部）；完整回放 NOT_AVAILABLE | 历史有效规则、事件版本、资金可用时间 | 全池一年状态/制度/公司行为链 | 若必要单独提案 | W6-H 共用事实与制度覆盖 | 历史DR01/02；策略成交引擎属Mishi | HISTORICAL_REPLAY BLOCKED | 不扩R2.1到全市场，不开发撮合 |
| Mishi | F4/DR03–04 板块资金 | 榜单ID/金额/周期/时点及行业映射 | E7 get_board_fund_flow | 0.4.2 | SUPPORTED_WITH_BOUNDS；有原始元值合同/离线测试 | current observed_at，业务日/PIT未知 | 当前完整覆盖/同分类映射 | 不先改 | 复用榜单；随W3/W4联核 | 行业联动需分类映射；非P前置 | 当前快照局部可用，联合资格未过 | 不用板块榜代替成员/逐股资金 |
| SIOS | H01 固定历史总回报信号包 | 三ETF RAW/Amount、现金及份额事件、全部日期/时点、≥200合格信号预热 | E1/E3/E10，**无现成TR/as-of出口** | 0.4.2/main相同边界 | SUPPORTED_WITH_BOUNDS（RAW）；完整包 UNKNOWN/NOT_ACCEPTED | 最新因子回算≠历史T可知 | 完整事件/版本/实际可用时间/独立TR对账 | 无证据不申请API；有现成事实才可能离线CR | W-H01 现成能力答复，当前BLOCKED | SIOS旧pin另行接收；不依赖Mishi/P2 | H01输入 BLOCKED；as-of UNKNOWN | 把明确不能交付的边界反馈消费者，需大工程则建议停止实例 |
| SIOS | P2 2020预热/2021–2025探索 | RB/BU/C/CS/PP真实月份、OHLC/结算/量仓、合约/规则/日历质量 | E11；A7研究样本 | 无期货公共能力 | NOT_AVAILABLE（完整包）；有限样本SAMPLE_ACCESSED | PIT_INFERRED/UNVERIFIED，非正式PIT | DCE全月份、元数据、全覆盖、实际供应权限 | **无需生产API**；条件离线CR | W-P2 外部直接导出优先 | 实际文件/权限；不等DR01或Mishi | 最早/完整输入均INSUFFICIENT_EVIDENCE | 沿用EXTERNAL_SOURCE_PREFERRED；无入口停止 |
| SIOS | H04-A 总回报 | 513530/513990 RAW、分红/份额、日期/可得性 | E1/E3/E10 | 0.4.2 局部 | SUPPORTED_WITH_BOUNDS（RAW）；事件请求失败，TR未知 | 无历史as-of/实际现金可用证明 | 完整事件+TR；不能将request_error算无分红 | 当前不提生产API | 仅现成能力答复，保持STOP | 即使A齐仍须独立B | TR PARTIAL/NOT_ACCEPTED | 无原始失败响应，具体原因UNKNOWN，不重试寻源 |
| SIOS | H04-B 历史归因 | 930914与513990指数各自母池、方法/权重/行业/价值质量/市场利率 | 无合格公开入口 | 无 | NOT_AVAILABLE（公共能力）；现成外部包UNKNOWN | 方法生效/权重可知时点必须独立证明 | 两个不同母池的2024–2025历史事实 | 不批准API/数据库 | 输出缺口，DEFERRED/STOP | A不能替代B；不依赖Mishi全池 | ATTRIBUTION NOT_ACCEPTED；实例STOP | 不新建港股因子库，不由两基金差额识别纯股息 |

### C3. 真实复用与责任界线

1. DR01/DR06 共用**同一份证券身份、上市/退市/ST/停复牌有效事实**，不同的是资格用途；不重复采集或建立冲突主表。股票历史覆盖不能由当前名称表反推。
2. Mishi DR02、SIOS H01/H04 都可复用 E1 的 RAW/Amount、基金价格尺度和 E10 的事件字段/失败语义；股票与 ETF 的公司行动来源和覆盖必须分别验。E3 的境内日历可作为历史对账候选，不自动证明 QDII 可执行时段，更不用于期货夜盘。
3. 两消费者共同需要来源身份、单位、业务日、获取日、缺失/失败和文件摘要。这些是交付事实要求，不要求新增统一 schema、市场框架或通用 Provider。
4. E6 仅维持已发行范围，不为满足 H01/H04 或 Mishi 自动扩认证集合。P2 的结算、持仓、月份/乘数/夜盘是另一个合同，不把它塞入证券日线。
5. Mishi 保存策略/参数版本、真实发布排名、自选/H1/日报快照、缓存编排及现金组合；chstockdata 提供合格事实。不要求供应方补造过去排名或开发成交引擎。SIOS 独立负责研究、费用/执行、信号/收益及金融准入，供应答复不能修改这些 Gate。

## D. Minimal Work Packages

P0 指本轮需要 Owner 作出的决定；P1 指另获授权后可独立启动的工作。BLOCKED 必须等待具名事件；DEFERRED 当前不做。技术可并行不等于全部立即开工。下列包均未获本轮实施授权。

### W0 — G0：DR04-P 独立发行就绪验收（首个建议）

- **服务需求/已有证据：**A2 DR04 无损数值入口；main、A5 Owner PASS、20/20身份与原142测试记录已核。P范围无遗留实现阻断。
- **唯一问题/复用或实施：**让已接受代码形成可正式消费的发行候选；复用 P，不开发 M、不重开 P。现在 P0 决定是否单独授权准备；授权后 P1。
- **依赖/并行：**不等 DR01、DR04-M、Mishi G1/G2/G3 或 SIOS。只需明确允许纳入的已接受差异、发行元数据与既有发布流程；可与只读历史来源裁决并行。
- **最小交付物：**拟发行差异白名单、代码/合同身份、Owner 指定的版本元数据方案、从干净候选构建的 wheel/sdist 与校验和、隔离安装的新增导出证据、必要 Gate 结果、准确发行说明。当前不指定版本号。
- **必要 Gate：**既有 `.github/workflows/publish.yml` 的离线 tests、RH1 静态检查、编译、版本/tag一致、build/twine、wheel/sdist/core/MCP隔离安装/pip check；对新增 P 导出/fixture 包含及旧契约兼容给出发行产物证据。冻结消费者接口/价格合同保持，所需消费者接收资格独立。旧142结果不是新包 Gate，也不要求重做已完成P来源调查。
- **停止/授权：**候选与接受身份不符、既有发行 Gate 失败或存在未批准差异则停止，报告 FIX_ONLY/具体阻断；不搭售源能力修复。Owner 接受候选后，tag/PyPI/GitHub Release和发布后安装验证仍须**独立发行授权**。不得覆盖既有0.4.2来伪装新P已发行。
- **不做：**M、PIT平台、数据库、其他DR实现、重跑完整市场源调查；本轮不构建、不发布。

### W1 — G1：DR01 当前来源解锁，再决定窄快照提案（BLOCKED）

- **服务/证据：**A2 当前四板身份与停复牌；A4及Mishi补链124项摘要匹配。D=2026-10-16普通股票观察集合5,225，深A2,906；这不是已合格可筛选分母。
- **最小问题：**深市该D全量含持续停牌/复牌事实可否完整、可追溯取得。BaoStock两次login超时（8s/15s，SDK10002007），数据查询0、状态行0；文档不证明来源合格。
- **解锁后交付/Gate：**仅在新的可检验条件出现时申请**一次**有界验证：例如已证明可达的免费公共环境，或D全状态文件/准上市本表上游及全量完成凭证。使用已核官方集合，验响应D/全部页/目标证券逐一状态、六只持续停牌和D-1→D复牌对照；附重复/缺失/冲突及最新实际发布窗口的有限证据。预算、截止与至多一次显式复核事前批准；登录再失败即停止。
- **复用/依赖：**沿用官方身份/风险/沪状态及日历；不重抓已合格来源，不靠零成交/闭市码/同源列表交集。来源通过后才提交一个最小事实快照合同，DR06共用；是否新API由Owner另批。
- **停止/不做：**没有新条件就不重试；深状态缺任一必需事实、日期/分页无法对齐、需付费或预算内无法完成，则保持BLOCKED并交Owner供应/时间或显式CR决定。不创建空壳API，不改名称解析，不建历史库。

### W2 — G1/G3：DR02 复用原始 reader 的消费与覆盖资格（P1候选）

- **服务/已有：**S01–S08量价/Amount/基准；E1–E4。四股实际首日为2001-08-27/1991-04-03/2018-06-11/2020-07-16，均止2026-09-22；指数sh000001首日1990-12-19、同尾日。末条Amount/Volume与原文件一致，不能据旧包宣布当前全池通过。
- **最小问题/方式：**先明确公共reader字段映射和源单位/日期/质量，使用E1输入E3；不要求E2新增Amount。局部合同验证可独立；当前全池/历史池覆盖必须等对应DR01分母。
- **最小交付物/验收：**固定包身份、代码/市场明确的股票与基准、业务日×证券覆盖/预热/缺口、原始与分析价格分离、量/额单位及源精度、无记录/陈旧/失败统计。实际全池验证须另批来源更新和成本预算；历史锚日及预热按消费者规则确定，保持一年底线。
- **停止/授权：**有reader但无法更新或覆盖不足，交付准确缺口；mootdx未知量单位/混源不能标合格。仅明确证实公共路径不能提供必要事实时申请最小API补充。新源/全池采集及接口变更需Owner另批。
- **不做：**以Close×Volume或amount_wan舍入值替代真实Amount、以当日存活池回填历史、S02盘中自动放量确认。日终S02不因缺累计量而自动阻断；声称盘中触发才须真实累计量及源时点。

### W3-C / W3-H — G1/G3：一套行业分类的当前成员与历史边界（分开验收）

- **服务/已有：**S06/S07，E7仅背景。本轮选定**BaoStock 输出的“证监会行业分类”**为单一比较候选，尚非Owner批准产品分类；不混申万/TDX/东财。
- **有界来源结论：**[官方行业文档](https://www.baostock.com/mainContent?file=stockIndustry.md)列`query_stock_industry(code='',date='')`、每周更新和updateDate/code/code_name/industry/industryClassification。公开免费路径已有调查依据；全量返回、遗漏比例及历史有效区间未取得实物。updateDate不是法律/分类生效日或首次可知时刻；日期参数也不证明保存历史版本。此前公共login失败，本轮没有重新登录。
- **当前最小交付/Gate：**有新可达条件或同分类已存文件才做一次全表资格：保留分类标签/版、逐股映射与逆向成员、重复/未分类及分母。固定集合可独立核；正式完整性等DR01。源合格且现有公共入口确不足时，另提最小数值出口，不先建分类平台。
- **历史最小交付/Gate：**同一分类下迁移前后、退市/未分类的真实记录和有效时间；明确可支持起止/盲区。当前/Historical各自PASS或不足，不能以每周快照直接填满历史日。不能取得必需区间则立即返回G3/Owner CR。
- **依赖/授权/停止：**不以DR01阻断局部研究；最终行业完整分母需DR01，S06联DR02、S07联DR05。共享BaoStock可达性是资源事实，不使DR03合同依赖DR01实现。来源无实物时保持UNKNOWN，不沿既有失败无条件重复；Owner另批验证/接口。
- **不做：**多分类、概念平台、未来快照补造过去成员。

### W5-C / W5-H — G1/G3：S07 当前最小数值与历史 PIT 可行性（分支独立）

- **服务/已有：**A2 DR05/S07/F3，E8 三表、报告期对齐、PE摘要；没有已合格S07全池数值合同或逐日估值公共序列。
- **当前唯一问题：**所选PE类型、归母利润/OCF/权益原值、ROE分子分母/基期/单位及公告时点能否可靠消费。先复用现入口核对盈利/亏损/基期不足和金融股识别；只有舍入文本/缺必要分母确实不足时，提出窄数值补充。ROE具体算法按消费者后续冻结，不将新候选公式当已批准。
- **历史关键裁决：**优先申请一次**原版财报+修订版+两次真实公告依据**及指定日估值行的只读资格包，覆盖所需财务基期并列实际历史区间；不是重新宽泛列供应商。没有旧版原文/可知日期或逐日数据出口，则精确回答不支持/UNKNOWN，停止工程化，进入Owner CR登记。
- **最小交付/Gate：**原值/单位/报告期/公告/版本、当前缺失与源时点、逐日估值覆盖、修订前后截止查询对账；至少能证明公告前不见、原版后见原版、修订后见修订。fixture只能核行为，不代替真实旧版与全池证据。
- **依赖/授权：**来源/原值可独立于DR01/03；S07正式横截面需相应池/行业。历史可行性与当前同时裁决，不等G2；只读核验、新API和采集分别需Owner授权。
- **停止/不做：**免费原件不可得/现成路径不能界定成本即停止，不能用当前值/公告过滤/最新PE分位反推历史；不搭财务PIT库、不撤S07、不悄改付费方案。既有同比修复不重列为待修缺陷。

### W6-C / W6-H — G1/G3：共享证券事实、历史制度与公司行动边界

- **服务/已有：**A2 DR01/06及全部现金组合；E4–E6/E10，当前官方状态和有界事件可复用。
- **最小问题/方式：**在W1同一身份事实上补对应时点制度/限制/股票公司行动；历史分支给一年+必要基期的实际可得区间及缺失。先核有效日/来源，不实现消费者成交模型。
- **最小交付/Gate：**上市/退市/ST/停复牌区间、板块交易制度生效、价格限制事实、公司行动公告/登记/除权/支付与现金股数单位；新上市/历史ST/持续停牌/制度切换/除权及UNKNOWN的正反样本。原始价格、复权与现金/股数事件可独立对账，禁止重复计算；支付日不是自动到账日。
- **依赖/并行：**全池完整性依历史DR01；价格限制/执行价依DR02，日历按适用范围验证。局部事件/制度可以独立只读；R2.1仅维持原范围，不要求Mishi建设严格一分钟模型。
- **停止/授权/不做：**必需生效版本或历史事实不可得即返回G3缺口/Owner CR；接口/采集另批。无第二主表，无港股库、券商权限引擎或撮合服务。私有chips BaoStock过滤了停牌行，不能当公共状态输出。

### W4-M / W4-H — G2前置 / G3：P的全池资格与历史可知性

- **服务/已有：**S08、F3任意股、F4、自选/H1/退出/日报；P已接受。旧20股100槽为90非零/10缺日，18股完整、2股过期；两股完整年度原文各243目标日，零值与当时版本未认证。
- **最小问题：**M是实际供给资格而非重写P；H是历史数值与真正as-of差异，二者独立。P发行不等M，H研究不等M通过。
- **P0必决/最小交付：**Owner事前冻结正式池/合格日历、目标日、源允许访问条件、总请求/页数/重试/墙钟/并发预算、发布时间、零/覆盖可用判据、连续批次数；批准后才采集真实槽位清单、终态/原文、滚动更新、源故障/恢复、吞吐成本。原提案“至少五个不同目标日批次”仍只是建议，不能自动成为标准。
- **依赖/Gate：**M正式全池依DR01及M授权；五个目标日由合格日历决定，缺日不借第六日。DR02只在资金/Amount比例联验时必需，不阻断单独资金来源资格；DR03只在行业归集时必需。W4-H须披露历史分页覆盖与版本缺口，不因COMPLETE给PIT PASS。
- **停止/不做：**403/429、日期不一致、预算触顶、必需规则未冻结即停止并保留部分结果。不能仅采S08入围包络：F3/F4/自选/H1仍需集合并集。旧3.98小时/年度48.29–51.71小时机械算例及41.08%减幅不是SLA/授权频率，本文不复测。无缓存/调度/数据库工程授权。

### W-G2 — 当前全市场联合资格（BLOCKED，条件就绪后独立授权）

- **服务/已有：**八策略共同输入，不是新软件层。局部合同与旧样本不能代替联合验收。
- **唯一问题/前置：**正式DR01分母、合格日历、各当前原子能力、P可消费身份及M预算/可用判据全部具备，才安排同日同池验证；不把其中任何一项推迟到结果后补标准。
- **最小交付/验收：**实际市场分母与逐证券/字段质量；成功、正常空、缺失、失败、过期各计数与总分母对账；来源/业务日/批次日/完成时刻；连续更新与源故障/恢复；请求及墙钟/存储成本；DR04全池最近五市场日完整槽位。规则所需字段、基准、行业/金融排除保持同批/同源定义。
- **停止/授权/不做：**前提或预算不足、失败恢复不成立即BLOCKED/INSUFFICIENT_EVIDENCE；不以单股、固定样本、一次HTTP200或“任务跑完”判PASS。不新增95%等阈值，不绕过源限制；完整工程/运行验证另批。

### W-H01 — SIOS三地域ETF现成交付性答复（本轮已完成，输入BLOCKED）

- **服务/已有：**A8 §3/5/6；固定513500/513030/513520、2024-01-02..2025-09-30、此前至少200合格TR信号观察。E1/E3/E10可复用，详见E节新增答复。
- **唯一问题/最小交付：**是否已有同窗、可核TR且历史T可知的包。当前答案否：只可供应有边界RAW；完整事件、份额及as-of证据不足。不以接口存在申请新生产API。
- **可解锁条件/Gate：**Owner已存的三ETF完整事件原件、版本及可得时间/实际现金可用依据到位，且无需新Provider/补库时，可另授权一次离线装包与独立消费验收：原始/信号价格分开，固定窗口/预热/共同日历对账，事件前后非策略小样本核现金和份额、逐T信息截止，输出SHA/缺口。达到200条RAW不等200条合格TR。消费者独立决定接受与实验审阅。
- **停止/授权/不做：**现成证据仍缺即反馈NOT_ACCEPTED；必须新增Provider、大规模补库或不成比例工程，建议SIOS停止当前H01实例。仅事实齐备但缺离线装配时才可另提窄CR；当前未达到提实施CR条件。不改窗口/ETF/信号，不运行收益、不调整旧pin、不宣称QDII/费用/OOS通过。

### W-P2 — SIOS独立历史期货包（EXTERNAL_SOURCE_PREFERRED，入口未就绪）

- **服务/已有：**A6/A7固定五品种2020预热、2021–2025探索；119样本、42字段交叉校核、125非正结算异常已存在，本轮复算身份/CSV计数，不重新取数。
- **最小问题/方式：**先有实际合格文件或可用供应商入口，再验收。优先消费者直接复用已有权限RQData导出，合格Tushare权限可优先于重新开账户；不要求经chstockdata生产API。
- **前置/交付/Gate：**只需Owner具名提供文件/授权研究入口，不依赖Mishi。字段、目录和三指定日/全历史Gate见E节；完整合格后由SIOS给ACCEPTED_FOR_EXPLORATION，仍不自动恢复实验。
- **停止/授权/不做：**无入口保持BLOCKED，不空token请求/搜索凭证/采购，不重做免费源综述。A/B不足且存在可访问上游却不能直接导出时，才考虑E节有条件离线CR；若上游缺事实，工程不能解锁。无通用期货SDK/Provider/实时服务/长期库。

### W-H04 — SIOS港股红利现成能力答复（本轮已完成，STOP）

- **服务/证据：**A8 §4–6，A=513530/513990总回报、B=930914及另一指数不同母池归因。RAW实物在，两个基金2024分红查询request_error；B无已接收入口。
- **最小交付/Gate：**分别给A/B现成边界、来源/时点/缺口；本轮已给出。若未来两类合格现成输入同时到位，Owner才决定是否重新审阅；单补A不满足B。
- **停止/授权/不做：**保持STOP_CURRENT_INSTANCE；不新建港股成分、估值、因子/行业/利率数据库，不自动修请求或多轮寻源。没有新工程或实验授权。

## E. Proposed Delivery Sequence 与 SIOS 独立应答

### E1. Mishi G0–G3 建议顺序

1. **G0先作独立发行准备决定：**W0只承接已验收P；不捆绑DR01/M/历史来源。真正发布仍需独立批准及实际发行Gate。
2. **G1当前原子能力与G3历史可行性同期：**W2优先复用；W3-C/H、W5-C/H、W6-C/H按独立事实交付。优先取得W5-H旧版/PIT及W3-H历史成员的有界可行性裁决，以免当前扫描完成后才发现首版回测不可交付。W1只在具名新条件出现后补证，不阻断独立包。
3. **G2最后联合验收当前供给：**正式分母、日历、原子能力和M预算均就绪才启动W-G2；各局部PASS不得外推。
4. **G3交付按证券×日期×版本交集：**约一年+各规则/财务基期预热，兼顾历史池、量额/基准、成员、资金、财务、状态与公司行动。锚日/预热须显式确定；不能只比较各源首末日期。

这不是“当前先上线即可取消历史”。八策略的当前全市场和真实单股/Top N现金组合两底线始终保留。实际免费源无法满足时只回Owner裁定供应计划、时间或显式消费者CR；本文不选择降级方案。

历史免费来源的四类证据状态如下；同一DR可同时有“没有完整公共实现”和“局部数据已取得”。

| DR | 已确认无合格实现 | 有路径未取到 | 有限数据已取得 | 可按有界设计验收/出口 |
| --- | --- | --- | --- | --- |
| DR01 | 无完整历史股票池/状态公共合同 | 指定日状态/证券基本信息候选，尚无所需一年链 | 官方当前身份/风险/沪状态 | W6-H核历史含退市集合与有效区间；无法得则停止/CR，不要求先建库。 |
| DR02 | 默认E2不交Amount，但E1已有，**不能记作必须新增接口** | 新鲜全池及选定基准同窗待验 | 四股+指数多年RAW，源float32额 | W2对真实历史分母、预热与缺口验收；复权/PIT另列。 |
| DR03 | 无历史成员及有效区间公共实现 | BaoStock日期接口仅文档 | 本轮无合格历史成员实物 | W3-H迁移/退市/未分类边界一次裁决，不用当前倒填。 |
| DR04 | 无全池历史版本/PIT合格交付 | 首次可知/修订版本尚无证据 | 两股243目标日完整原文；固定样本有空洞/零 | W4-H验证数值与未知边界；没有原历史版本不能因分页完整过PIT。 |
| DR05 | 无公共逐日估值输出、旧版财报库 | 源内部历史估值/公告旧版是否可核待证 | 当前报表/估值摘要，不是旧版PIT实物 | W5-H原版/修订及日期案例为最小决策证据；免费不可得回Owner。 |
| DR06 | 无全池历史停复牌/ST/制度/公司行动整链 | 历史有效规则和逐股事件覆盖待证 | 当前状态、局部事件/R2.1限定集合 | W6-H有效日、不可成交及现金股数事件边界；不能扩大R2.1认证。 |

### E2. H01：现有输入确切可交付边界

**SIOS_H01_DATA_STATUS = BLOCKED；SIOS_H01_ASOF_EVIDENCE = UNKNOWN / NOT_ACCEPTED。**这是生产者输入裁决；消费者原`INVESTIGATE_ONE_BLOCKER`保留，是否据此停止实例由SIOS/Owner决定。

无需重新调查ETF代码或供应商。A8 §5文件身份本轮匹配；进一步仅作RAW非收益对账，网络禁用。对账日历来自同包`sh000001.day`，是有限本地参照，不冒称独立交易所资格。

| RAW事实 | 513500 | 513030 | 513520 |
| --- | --- | --- | --- |
| 全文件记录/首日/尾日（A8身份） | 3,086 / 2014-01-15 / 2026-09-22 | 2,928 / 2014-09-05 / 2026-09-22 | 1,761 / 2019-06-25 / 2026-09-22 |
| 固定2024-01-02..2025-09-30 | 425行/425本地日历日 | 425/425 | 425/425 |
| 相对该日历缺日/多日 | 0/0 | 0/0 | 0/0 |
| OHLCV/Amount空值；非正OHLC | 均0 | 均0 | 均0 |
| 零Volume/Amount | 0/0 | **2025-01-23各1行**，原样保留，不推断停牌/可成交 | 0/0 |
| 观察段前RAW记录 | 2,425 | 2,267 | 1,100 |
| 最近200条RAW起日 | 2023-03-09 | 2023-03-09 | 2023-03-09 |

三文件32字节对齐、无原始重复日期。上述200仅RAW计数，**不证明200个合格总回报观察**；预热内事件/可知性及消费者共同合格日还未验。价格按v0.4.2已认证SH51 ÷1000、Amount元/源float32、Volume按reader shares合同保留原值；不进行复权成交、未来时点填充或量额换算。文件完整SHA在A8 §5，可按其原件复核，本文不复制新数据包。

| H01必要项 | 现成能力与明确不足 |
| --- | --- |
| RAW/日历/缺口 | E1能读且上述窗口有实际数据。日历与价格/Volume/Amount源语义如上；raw pre_close不是除息参考价。 |
| 现金分红日期 | E10可规范化公告、登记、除息、支付及每10份金额，但**未取得这三ETF全窗口/预热的合格事件实物**；旧510300等样例不能替代。 |
| 份额变化 | 基金实现是cash-distribution，不交付完整拆分/合并/份额折算历史。字段None不是“无事件”的来源证明。 |
| 历史T实际可知 | as_of_date仅对今天取到的记录做公告日过滤，缺原版/修订版、历史首次可得、日内发布时间与账户实际现金可用时点；当前源也可能回填。**UNKNOWN/NOT_ACCEPTED**。 |
| 总回报信号 | 无已接受的三ETF TR包/公共TR计算合同；当前hfq/qfq是今日因子回溯，最新锚/全样本因子不得直接当历史T信号。数学恒等式不能补足历史来源资格。 |
| 对账与执行分离 | 在事实齐备后，沿消费者冻结定义区分分红权利、应收现金、支付及实际可再投资、份额折算；用单一事件前后价格/份数/现金与无事件对照作独立非策略对账。信号TR与未复权执行价分别输出；不能提前把应收款作可交易现金，不能分红及复权重复计入。当前无真实事件证据，不能声称对账已通过。 |
| 消费发行身份 | RAW/E3/E10在0.4.2，main无新增TR/as-of能力。SIOS当前来源登记/适配器仍pin0.3.0，升级/接收需消费者独立合同/Golden/资格，不由本规划改pin。 |

**出口：**本轮已经给出明确不能完整交付的答复，不再追加市场源调查。若Owner能提供现成完整事件/历史可知依据，才按W-H01作一次有界文件装配/消费者验收；事实本身不存在时不写TR脚本冒充解决。若必须新Provider或大规模历史库，建议STOP_CURRENT_INSTANCE，不替换ETF、不缩窗口。费用、QDII可交易性、执行、策略和OOS均未PASS。

### E3. P2：复用既有三路径裁决，不重新调查

**SIOS_P2_SUPPLY_VERDICT = EXTERNAL_SOURCE_PREFERRED。交付就绪状态仍BLOCKED，未达到READY_TO_DELIVER。**

| 路径 | 本轮结论与决策出口 |
| --- | --- |
| A 现有能力/现成导出 | 无期货公共入口；A7定向库存和SIOS原停止证据中未发现合格完整包，非全磁盘“不存在”断言。本地119行是来源探针，不是可验收六年输入。Owner提供实际完整包即可直接进入文件验收，无需开发。 |
| B 消费者直接用成熟供应商 | **推荐。**已有权限的RQData导出真实合约/交易所日线与历史乘数；Tushare合格权限是备选。官方当前文档核对不替代认证/全覆盖实测。无已提供权限或实际包，停在入口，不采购、不联系供应商、不搜索凭证。 |
| C 生产者最小变更 | 当前无证据证明生产SDK必要。A/B不足且**有可访问上游但不能直接产出合格离线文件**时，才可提交`CR-P2-OFFLINE-01`供审；上游事实/权限不存在时不能用工程CR绕过。 |

候选成熟度如下；层级必须逐项成立，不能跳级。SHFE“可交付有限探针”不等“完整P2 DELIVERABLE”。

| 实际候选 | DOCUMENTED | SAMPLE_ACCESSED | AUTHENTICATED | REQUIRED_HISTORY_VERIFIED | DELIVERABLE / 成本和许可 |
| --- | --- | --- | --- | --- | --- |
| RQData | 是；[交易所日线/历史乘数](https://www.ricequant.com/doc/rqdata/python/futures-mod)，历史实际月份清单依既有研究 | 目标认证样本未取得 | 未证明；先前受检标准入口未配置 | 否 | 否；可能需账户/数据授权或费用，未取得权限，价格UNKNOWN；商业再分发UNKNOWN。 |
| Tushare | 是；[fut_basic](https://tushare.pro/document/2?doc_id=135)、[fut_daily](https://tushare.pro/document/2?doc_id=138) | 未取得带认证目标样本 | 未证明；不能由SDK存在推定 | 否 | 否；文档权限/积分门槛与实际账号分开，未购买。标准个人用途限制据A6旧研究记录为RESTRICTED，具体研究/商业项目授权仍UNKNOWN。 |
| SHFE原始日记录 | 公开路径 | A7已取2020-01-02及三个指定日，RB/BU共104行 | 公共访问，不适用账号认证 | 仅四日，非全历史 | 仅样本可交付；免费公开请求，商业再分发UNKNOWN。 |
| DCE原始日记录 | 路径已定位 | A7三个指定日均ConnectionError，0有效响应 | 不适用/未取得 | 否 | 否；请求失败不是无合约，其他官方下载路线不能未经证据认定失效。许可UNKNOWN。 |
| 新浪真实月份 | 公开请求路径 | A7十五合约片段，指定锚15行；窗口内125非正结算 | 公共访问，不适用 | 否，尤其DCE全月份未知 | 仅交叉核对片段，不是主源完整包；免费可访问不等商业许可，后者UNKNOWN。 |

关键已有实物：A7共119导出行，SHFE104+新浪15；跨源6合约×7字段=42/42一致；新浪目标窗125条非正结算（前三DCE合约各41条在2020预热，另RB2310/BU2309各1）。官方三条零成交月份O/H/L为空，保留原值，不按错误补齐。完整六年分母未建立，不能将样本覆盖率推广。

本轮复算A7 `artifact_manifest.json` **43/43**，读回daily_sample=119、anchor=15、crosscheck=42、anomalies=125；没有重跑其网络或收益代码。A7原始请求及单位/元数据局限保持，包括SHFE update_date只是来源更新时间而非历史首次发布、DCE九个指定行无官方独立锚。

最终最小文件包可直接交SIOS：`daily.csv/parquet`、`contracts.csv`、`contract_terms.csv`、`calendar.csv`、`coverage.csv`、`gaps.csv`、`quality_flags.csv`、`manifest.json`及README。该包**尚不存在**，不能把样本目录改名视为交付。覆盖窗口内存续全部实际月份，包括已到期及交割月在2025之后的合约（A7实见BU2712），法定上市日可早于2020。

最早Gate是实际入口/文件、2021-01-04/2023-06-30/2025-12-31五品种当时全月份及OHLC/原结算/量仓、单位和元数据；SHFE与独立来源校核，DCE官方受限如实列替代/风险。完整Gate是2020预热及2021–2025全部目标日/合约/关键字段、上市/最后交易/交割年月、历史乘数/tick/计量/规则有效日、两交易所日历/夜盘归属、来源/修订/缺口/SHA与可复现条件。未知关键行不记现金、不用收盘补结算、不跨选择节点前填；允许按消费者已有D→T滞后披露PIT_INFERRED/UNVERIFIED，不追加正式PIT库门禁。

备选CR的必要约束：缺失能力只限固定五品种2020–2025**离线导出/核对**，无法复用现成文件的具体证据必须附上；只动单独研究导出目录/脚本，交付上述CSV/Parquet及质量清单，不改src/依赖/股票ETF契约/生产Provider。三个指定日真实样本先通过，再做全覆盖；权限失败、关键事实无现成来源、超批准请求/墙钟/人工预算或需要平台补洞即停。工作量只按待核请求规模、文件量及验收动作评估，本规划不继承A7人日估计为承诺工期，不指定版本/日期。SIOS最后独立判ACCEPTED_FOR_EXPLORATION/REJECTED_WITH_REASONS；新实验须Owner另批。

### E4. H04：两类现成输入分别答复，继续停止

| 项目 | 当前可用 | 独立缺口/判断/停止 |
| --- | --- | --- |
| A 总回报与基金事件 | E1可读取513530/513990；A8两文件SHA本轮匹配；价格尺度SH51可复用。E10有现金分红规范化合同。 | `TR_STATUS = PARTIAL / NOT_ACCEPTED`。A8记录16:35对两ETF的2024年查询均failed/unavailable/request_error，未存供应商原响应，本文不能独立重放或确定具体网络/HTTP原因。实现:658与正常空:666分支不同，故失败绝不是无分红证明。2025/全事件、份额变化、TR定义、历史版本与实际可用时点仍UNKNOWN；不重试或新建来源。 |
| B 历史归因事实 | 已有研究定位930914方法入口和披露片段，非完整历史数据。现有A股行业/财务不能覆盖港股。 | `ATTRIBUTION_STATUS = NOT_AVAILABLE / NOT_ACCEPTED`（本仓库现成合同）；外部现成包UNKNOWN。缺2024–2025各自历史方法版/生效日、母池/成分权重、同分类行业聚合、价值/质量及市场/利率风险的实际来源/时点/缺失。没有现成可交付样本，不开港股数据库任务。 |

930914的母池为中证香港300中的港股通符合者，513990跟踪上证港股通指数，**二者不是同一母池**。该事实沿用A8已有研究；两基金表现差异不能识别纯股息效应。当前权重、2026披露的2025季报和最新方法不能倒填历史可知状态。

`SIOS_H04_INSTANCE = STOP_CURRENT_INSTANCE`。只有A与B同时有低成本合格现成输入，才可申请重新审阅；即使A后续可交付也不升级READY。本轮不再次查询公司行动、不取指数PDF、不建成分/因子/利率/归因库、不运行静态配对收益。商业用途、执行与OOS仍属消费者独立验收。

## F. Blocker & Owner Decision Register

| ID / 分类 | 已知事实 | 缺少的最小证据 | 责任方 / 具体解锁事件 | 不足时停止 / 是否CR |
| --- | --- | --- | --- | --- |
| B0 / UNRESOLVED_RISK（交付资格） | P已接受而未发行，非P实现缺陷 | 可消费新候选产物及既有发行Gate | chstockdata Owner授权W0准备，随后独立批准发行 | 不发布；无必要消费者范围CR，发行不能捆绑M。 |
| B1 / UNRESOLVED_RISK | DR01深D全状态未取到；BaoStock两次登录超时 | 新可达条件下全表、传输结束/日期/逐证券状态，或可追溯完整文件 | Owner给新条件/文件；生产者一次有界资格核验 | 没新条件不重试；失败BLOCKED。改用活动代理/降低标准须消费者CR。 |
| B2 / UNRESOLVED_RISK | DR02有原始Amount路径，旧本地包非最新全池 | 正式分母、合格包更新窗、实际池×日×字段/吞吐 | 生产者+Owner批准数据更新/预算；DR01分母到位 | 仅陈旧/局部可用；不先改API，不自动缩历史。 |
| B3 / UNRESOLVED_RISK | DR03只有背景，候选全量/历史未实取 | 同分类全表、未分类分母及历史迁移生效证据 | 生产者W3，Owner批准一次具名条件验证 | 当前/历史分开不足；免费历史不可得回Owner供应/日期/显式范围CR。 |
| B4 / UNRESOLVED_RISK | M未授权，预算/SLA/覆盖与零可用未冻结 | 正式池/日历、源允许频率、请求/墙钟上限、覆盖/连续批次及时间判据 | Owner与Mishi确认待审运行条件，另授权W4-M | 不采全池、不设95%；P不代M，无条件PASS不可授权。 |
| B5 / UNRESOLVED_RISK | S07旧版PIT及逐日估值输出未合格 | 原版/修订版真实公告证据、估值逐日行及区间 | 生产者W5-H只读核验；Owner裁决来源不足 | 不能靠API封装创造旧版；停止并提交精确首版影响CR，S07不删除。 |
| B6 / UNRESOLVED_RISK | 历史池/ST/制度/公司行为整链未合格 | 含退市全集、有效日与具体不可成交/事件样本 | 生产者W6；消费者定义日频执行/会计假设 | 不扩大E6或假定可成交；范围/时间变更须Owner CR。 |
| B7 / UNRESOLVED_RISK | H01三ETF有RAW，无已接收TR/as-of包 | 完整事件/份额/历史版本、T可得与现金可用证据及非策略对账 | Owner若已有文件可具名提供；生产者仅核现成证据，SIOS独立接收 | 当前BLOCKED/NOT_ACCEPTED；需新Provider/大补库则建议停实例。只有事实齐备但缺装包才审最小离线CR。 |
| B8 / UNRESOLVED_RISK | P2无合格完整包/可用供应入口；DCE全月份/元数据缺 | 具名可访问外部导出/权限、三日全月份及全期覆盖 | Owner/有权限研究使用者提供文件；SIOS按合同接受 | EXTERNAL_SOURCE_PREFERRED但未ready；不再宽泛调查/采购。仅满足E3条件才审离线CR。 |
| B9 / CONFIRMED_DEFECT（候选数据） | 新浪125条非正结算 | 原来源可核合法结算，或明确关键节点不合格 | 现成供应商文件交叉校核，消费者评价受影响输入 | 不用close/前填修补、不删期记现金；不是已发布代码缺陷或机制失败。 |
| B10 / UNRESOLVED_RISK | H04事件request_error、两母池归因事实缺，彼此独立 | A完整TR及B历史方法/权重/行业风险现成包 | 未来Owner同时提供两类可验收输入后才决定重开 | 当前STOP，不据单个请求修复建港股平台。 |
| B11 / UNRESOLVED_RISK（用途） | 技术可取不等商业授权 | 实际用途/展示/再分发条款或授权依据 | Owner在正式商业决策前独立核对 | 本轮技术调查不因UNKNOWN否决，也绝不默许上线；Mishi免费约束不改变。 |

许可登记：交易所公开记录、VIPDOC、东财/新浪/BaoStock的免费可访问性与商业分发许可分别记录；本轮对其商业/再分发一律 **UNKNOWN**。Tushare标准许可按既有研究记录 **RESTRICTED**，具体项目新授权 **UNKNOWN**；RQData实际权利 **UNKNOWN**。本轮没有核实出新的VERIFIED商业许可，不作法律结论、不联系第三方、不购数。

SPECULATIVE_CONCERN：未采样日可能更多异常、未来负载可能变化，不能据此扩工程。FUTURE_ENHANCEMENT：统一市场数据平台、通用期货/港股Provider、长期PIT库、分钟执行、M2/Paper、多分类/三年扩展、DR07/WF；均DEFERRED，不能作本轮前置。

## G. First Executable Task Recommendation

**只推荐一个最值得立即授权的下一项任务：W0，DR04-P独立发行就绪验收。** 它将已接受能力转为可审的正式交付候选，范围最明确，没有未通过来源资格前置，不与DR01/M串行；收益也不依赖两个消费者是否立即完整通过。授权对象是候选准备和既有必要Gate，**不含实际发行**。

最多两个额外并行候选，不生成实施Prompt：

1. **W5-H：历史财务原版/修订版与逐日估值的一次只读可行性裁决。**高风险且可能直接否决Mishi首版回测承诺，与W0不争夺发布前置资源；没有实物就给明确缺口/CR出口，不递归调查。
2. **W-P2：已有外部文件/权限到位后的独立包验收。**当前仍BLOCKED，不因列为候选立即开工；H01现成交付性已先答复为不足，保留SIOS内部H01＞P2＞H04关系。没有具名输入就不派发第二轮来源调查。

W2虽然便于复用，也仍只列P1候选，不为“可并行”而全开。H01尚无现成as-of事实，不推荐新Provider或TR工程。H04保持STOP。Owner可改变推荐顺序，但本文不默认所有P1获准。

### G1. 本轮验收与独立交接

- **当前阶段/步骤：**双消费者只读供应审查与单文档规划，含H01/H04增量整合，停止Owner Review。
- **Git身份/工作树：**chstockdata `9543d03310b25be9963227a2a226366de04276ec`，只新增本文；已有未跟踪证据保留。Mishi与SIOS HEAD/既有tracked diff保持B1身份；未暂存/提交/推送/tag/发布。
- **规划证据：**四份核心Mishi输入/副本身份、P2包五项身份及四原件一致、DR01两清单48+76项匹配、DR04-P20项匹配/旧142 JUnit、P2产物43项匹配和CSV计数；本轮执行的7个既有DR02离线用例通过，H01固定RAW425×3窗口/缺口与原文件身份对账。没有新增测试，也未将这些核验宣称为市场完整资格。
- **交付边界核验：**本文严格UTF-8无BOM，28个本地文件链接均存在、Markdown表格列数一致；对选定的chstockdata源码/测试/根规则及既有文档共118文件、Mishi根文档18文件、SIOS根文档12文件进行前后散列比较，全部保持不变。三仓库HEAD与tracked diff均不变；normal状态仅chstockdata新增docs/plans目录，目录内仅本文，另两仓库状态不变。已有深层未跟踪目录未作全量内容审计。
- **有界外部核验：**本轮市场来源数据请求0、BaoStock登录0、P2/H04重试0。外部网页工具仅两次调用，含一项行业文档定位、四项官方文档open及三项文档内find；仅使用主站证据，网页工具内部HTTP次数不可观测。Firecrawl沿用A7既有无效凭据记录，未重复账户预检；未保存新网络原文或新增证据文件。
- **Gate裁决：**规划可交Owner Review；Owner Acceptance未取得。Mishi完整CURRENT/HISTORICAL均NOT_PASSED；H01 ASOF NOT_ACCEPTED；P2完整输入INSUFFICIENT_EVIDENCE；H04 STOP；SIOS M2仍BLOCKED。没有下一阶段授权。
- **遗留阻断/范围变化：**见F登记；无消费者范围变更、无新增Provider/API/依赖/生产实现。H01/H04是本次Owner明确要求的调查增量，不是生产版本范围扩大。
- **建议下一动作：**Owner审阅本文并决定是否单独授权W0；其他包按具名前置和独立Gate逐项批准，不自动推进。

```ini
CURRENT_DECISION = INVESTIGATE
CHSTOCKDATA_RELEASE_BASE = v0.4.2 / 17af23fe8183f740150dc01dd877473afe3911b7
CHSTOCKDATA_MAIN_SHA = 9543d03310b25be9963227a2a226366de04276ec
DR04_P_STATUS = OWNER_ACCEPTANCE_PASS / MERGED_MAIN / UNRELEASED
MISHI_CURRENT_STATUS = NOT_QUALIFIED / DR01_SOURCE_BLOCKED / DR04_M_NOT_AUTHORIZED
MISHI_HISTORICAL_STATUS = NOT_QUALIFIED / REQUIRED_HISTORY_AND_PIT_GAPS
SIOS_H01_DATA_STATUS = BLOCKED / RAW_PARTIAL_SUPPLY_ONLY
SIOS_H01_ASOF_EVIDENCE = UNKNOWN / NOT_ACCEPTED
SIOS_P2_SUPPLY_VERDICT = EXTERNAL_SOURCE_PREFERRED / INPUT_NOT_READY
SIOS_H04_TR_STATUS = PARTIAL / NOT_ACCEPTED
SIOS_H04_ATTRIBUTION_STATUS = NOT_AVAILABLE / NOT_ACCEPTED
SIOS_H04_INSTANCE = STOP_CURRENT_INSTANCE
REUSE_OPPORTUNITIES = VIPDOC_RAW_AMOUNT; ADJUSTED_BARS_WITH_BOUNDS; STOCK_ETF_ACTION_CONTRACTS; SECURITY_FACTS_DR01_DR06; ACCEPTED_DR04_P; EXISTING_P2_EVIDENCE
CONFIRMED_BLOCKERS = SZ_D_FULL_STATUS_UNVERIFIED; FULL_MARKET_AND_M_BUDGET_UNQUALIFIED; INDUSTRY_AND_FINANCIAL_HISTORY_PIT_GAPS; H01_TR_ASOF_NOT_ACCEPTED; P2_INPUT_ACCESS_NOT_READY; H04_TR_AND_ATTRIBUTION_GAPS
PROPOSED_FIRST_WORK_PACKAGE = W0_DR04_P_INDEPENDENT_RELEASE_READINESS_ACCEPTANCE
PARALLEL_WORK_PACKAGES = W5_H_BOUNDED_HISTORY_FEASIBILITY; W_P2_ONLY_AFTER_ACTUAL_INPUT_AVAILABLE
SCOPE_EXPANSION = NO_PRODUCER_ENGINEERING_EXPANSION / H01_H04_INVESTIGATION_ADDED_BY_OWNER
CONSUMER_SCOPE_CHANGED = NO
ENGINEERING_AUTHORIZED = NO
RUNTIME_IMPLEMENTATION_AUTHORIZED = NO
RELEASE_AUTHORIZED = NO
NEXT_PHASE_ALLOWED = NO
OWNER_REVIEW_REQUIRED = YES
```
