# Mishi S07 真实历史窗口与数据依赖准入审查

日期：2026-10-22，Asia/Shanghai。`CURRENT_DECISION=INVESTIGATE`。基线：`5584f5fcacccef9a9531a7a32b8463ea6771d312`。

**结论：真正缺少的是近期 252 个净值日所需的“历史池 × 行业 × 当时财务版本 × 指定日 PE × 执行事实”的合格交集。旧六证券研究证明了一部分免费原件处理和拒绝机制，既不能提供这个交集，也没有证明它不可取得。** 最短路径是按已接受规则绑定真实日期、证券分母及财务期间，再做一次有界免费供数资格验证；不再以旧扫描件全部转绿为前置条件。

本轮没有联网、下载、新增证券样本、修改生产/消费者代码、计算真实选股收益、安装环境、提交或推送。仅新增本文和[精简依赖矩阵](2026-10-22-mishi-s07-real-window-dependencies.json)。既有 F2 最终报告和未跟踪 evidence 原样保留。

## 1. 权威恢复：范围批准、规则接受、完整冻结与来源资格分别判断

| ID | 本轮实际读取的依据 | 权威及采用方式 |
|---|---|---|
| A0 | [AGENTS.md](../../AGENTS.md) | 遵守冻结范围、证据优先、Gate 晋级须 Owner 授权和独立交接要求。无适用于新增文件的更深 AGENTS。发现 `.codegraph/` 后先执行 CodeGraph，再定位当前源码。 |
| A1 | [R3.2 已批准范围](../MISHI_RADAR_V0_1_SPEC_R3_2_SCOPE_APPROVED_DATA_PENDING_2026-10-16.md) §0、§2–3、§5、§8 | S07 独立必交；当期全池、真实单股和 Top N 现金回测；最近约一交易年度另含预热。不可自行删策略、缩窗、用最新股票池回填或改成研究演示。AND、训练择参 WF、分钟逐笔模拟不属本轮必交。 |
| A2 | [DR01–DR06](../MISHI_RADAR_TO_CHSTOCKDATA_DR01_DR06_CONSUMER_REQUEST_2026-10-16.md)，尤其 DR05 | 原始盈利/OCF、ROE 分子分母和基期、PE 类型/业务日、当时公告版本与修订日期；同时需要 DR01/02/03/06。不是 NP/OCF/EQ 三字段实验合同。 |
| A3 | [双消费者供应计划](../plans/2026-10-19-dual-consumer-supply-plan.md) B–D、G3/W5-H；[综合差距报告](../DR02-DR06-consolidated-gap-report.md) DR05/06 | 调查与建议，非产品冻结/实施授权；原始价量额与历史资格可独立复用。发行状态及 Mishi 后续规则按更新证据覆盖旧叙述。 |
| A4 | [Mishi 当前运行规格](D:/Dev/Projects/mishi-radar/docs/MISHI_RADAR_R3_2_PRODUCT_OPERATING_SPEC_CANDIDATE_2026-10-19.md) §1.2、§2–4.7、§7、§9.5；[Owner 决策记录](D:/Dev/Projects/mishi-radar/docs/MISHI_RADAR_R3_2_OWNER_DECISIONS_2026-10-19.md) | 实际状态为 `RULE_BASELINE_ACCEPTED / FULL_DESIGN_NOT_FROZEN`。Owner 记录明确接受 OD-1/OD-2，包含默认窗口、TTM 归母利润/平均归母权益 ROE、S07 20 日调仓、日频现金模型。§1.2 明确正文“继承/补充候选”标签保留提案来源，不能只读标签而漏掉后续限定接受。 |
| A5 | [Owner Decision Addendum](D:/Dev/Projects/mishi-radar/docs/MISHI_RADAR_R3_2_OWNER_DECISION_ADDENDUM_2026-10-21.md) §3–6；[X01 局部 CR](D:/Dev/Projects/mishi-radar/docs/MISHI_RADAR_R3_2_X01_LOCAL_CR_2026-10-21.md) | 记录 Owner 在 2026-10-22 确认 2026-10-21 五项批准；记录稿仍待 Owner Review。U1 明确日期公告/归一化可用日期区别；X01 限定晚到提案的一次顺延；U2 独立执行资格；U3 唯一适用费表与逐 Lot 税绑定。不是代码合格或下一阶段授权。 |
| E1 | [R4](2026-10-20-w5h-r4-tdx-revision-root-cause-and-archival-pit.md)、[R5](2026-10-20-w5h-r5-historical-disclosure-scale-cost-screen.md)、[R6](2026-10-21-w5h-r6-version-exception-qualification.md)、[F1](2026-10-21-w5h-r6-f1-parser-correction.md) | 来源与原型实验事实。R6 跨表单位问题及由此引出的停止免费路线推论已被 F1/F2 后续处理；不得继续作为必须付费/逐项人工的依据。 |
| E2 | [F2](2026-10-21-w5h-f2-automated-pit-vertical-slice.md)、[Source Closure](2026-10-21-w5h-f2-source-closure.md)、[最新最终资格报告](2026-10-22-w5h-f2-final-evidence-qualification.md)及其原始账本 | 采用最新字段级处置；保留旧失败和分母。固定目录、选定原件、数值及拒绝测试资格不等于真实 S07 全市场资格。 |
| E3 | [v0.4.3 发行关闭](2026-10-19-v0.4.3-release-closeout.md)、[公共能力矩阵](../provider-capability-matrix.md)与当前源码 | v0.4.3 已发行，tag target `30cc7c50e3971fe79bfd903a412b2b76a0338caa`，不能沿用双消费者计划的“P 尚未发行”。DR04-P 不构成 S07 必需输入或历史 PIT PASS。 |

**本轮没有冻结 PE、ROE 或公告政策。** 本文恢复 A4/A5 已记录的限定批准；没有把 E1/E2 的实验规则升级为合同。完整 Design Freeze、真实数据资格、OD-3 的 SLA/预算/使用窗和产品实施授权仍未取得。历史报告中“PE/ROE 尚未由本轮冻结”不能反向抹去 A4 的 Owner 规则接受；F2 文件内 `product_date_rule_owner_frozen=false` 保持原值，不改档案。

关键文件身份（字节 SHA-256；跨仓库按实际工作树原件读取，不凭旧 HEAD 推断文本）：

| 文件 | SHA-256 |
|---|---|
| R3.2 / DR 请求 | `9b98641d4602fcd2a35c28520f9160a3fbf935ce1c43e89d466a473419e5bd62` / `35609c8cbf823dbb86a681ea15c27f7f598892b7ea73f46ecde5025e85ff8866` |
| A4 运行规格 | `2c2ce07bddc85c3a91f19bfe2d27635484d14ce8e0717c67a18f3ef558ad5834` |
| A4 Owner 决策记录 | `509bc02e4e1fb7634503fffa26a4c187a921bfef38a5d4edfec7afeb99747435` |
| A5 Addendum / X01 CR | `e540a9509877b4f34b0ec6bf4bf500248aa1c838219059be46d51b233dbfb2f5` / `432651816666ef965d5042785a22c79d2d2f857ee668b2f771c746ee4199ec49` |
| F2 最新最终报告 | `0e3237f58cbcfe1e27f92dd53255ce4de2c8c5caa111d67a5a468fd7430cf0e5` |

Mishi Git 跨目录命令在沙箱内被拒绝；上述原件可正常只读，已逐件记录 SHA。本文不声称重新验证了 Mishi 当前 Git HEAD；不需为读取合同升级权限或改其仓库。

## 2. 真正的历史目标及尚未绑定的实参

### 2.1 窗口、预热、股票池和执行时点

| 问题 | 已接受定义 / 明确缺口 |
|---|---|
| 起止日期 | A4 §7.1：结束日 `e` 默认为最新合格历史日；`s…e` 是 **252 个已完成市场交易日的净值日**，即 `s` 为 `e` 前第 251 个市场日。不是自然年、252 条个股记录或任意现成旧区间。尚无批准并具备供应证据的具体 `s/e`；不能把报告日、旧六股窗口或缓存末日填成产品日期。 |
| 末日滞后 | `e` 若不是最新已完成日须显著披露；无法提供完整 252 日要报告缺口并交 Owner，不自动缩短。接受相对窗口算法不等于接受任意滞后商品承诺。 |
| 首笔信号与预热 | 初始选择用 `s-1` 收盘信号，`s` 开盘尝试。八策略共同默认技术输入为 `s-65…s-1` 共 65 个市场收盘；配置变化机械增加。**S07 自身不使用 MA60/收益率排序；其共同 AVG_A20 最早只需要 `s-20…s-1` 的真实成交额。** 65 日是统一交付包约定，不是 S07 财务预热上限，也不意味着要在这 65 日每日跑财务信号。 |
| 财务预热 | 最早需要计算信号的 T 所知最新、可对齐报告期 `q(T)`，以及下节列出的上年年报、上年同期流量/权益；每个后续 T 的新披露/修订继续扩展。无统一“多取四季/两年就够”常数，不能用技术预热截断财务基期。 |
| 历史股票池 | A4 §3：每个 D 的沪深主板/创业板/科创板普通 A 股 `U(D)`，排除 B 股/CDR/北交所/ETF/基金/指数，包含当时存在而后来退市证券。`security_id=exchange:ticker`。数量来自证据，不用今日存活列表或 VIPDOC 文件名集代替。 |
| 基础资格 | `E0(D)`：非 ST/风险警示、非退市整理、非全天停牌；上市以来已完成市场日不少于 120；AVG_A20 ≥ 3000 万元。默认及白名单承接 OD-1。上市日期用于成熟度，不要求额外 120 条个股行情冒充成熟度证据；状态未知不算正常剔除。 |
| S07 信号与排名频率 | 使用同日已知财务/估值及行业重建日终信号/排序，日终检查条件失效和止损；默认**每 20 个市场日调仓**，锚定 s，不因空榜/未成交重置。不能将 20 日调仓误解为只需要 13 个 PE 快照；日终退出和 X01 下一完整批次窗口仍需要日级覆盖。 |
| 价格时点 | T 收盘形成信号，成交不早于后续开盘且必须晚于全部必要信息可用时刻；用当时原始开盘成交、原始收盘估值，分析复权另列。默认 10 万元/Top10/等权目标、佣金/滑点为已接受模型假设，真实交易单位/费税须另有生效证据。 |
| 晚到信息 | A5：同作用域下一完整合格批次替代旧买入提案，完整空榜也替代；无发布与 UNKNOWN 不同，覆盖未知阻断。不新增固定 TTL。原调仓提案因信息晚到而错过开盘时，尚有效才可在首个后续合格开盘作一次非调仓日顺延；不能重新排名或反复追买。 |
| 末日处理 | e 收盘保留持仓并计市值，不虚构强平；退出标待区间外执行。净值、基准、现金/股数、费用、应收应付、失败尝试必须可对账。单股也需重建其行业比较池，不能只算一只股票财务比率。 |

**仅用于验证窗口算法的现存实物例，不是批准日期：** 本轮只读 `.rh3a2-vipdoc/sh/lday/sh000001.day`，8,731 条、1990-12-19 至 2026-09-22。若显式以缓存末日作诊断锚，252 个净值日为 **2025-09-09…2026-09-22**，首个信号日 2025-09-08，共同 65 日预热 **2025-06-10…2025-09-08**，S07 首次 AVG_A20 为 **2025-08-12…2025-09-08**。此算例没有证明交易所日历全覆盖，也没有批准将滞后末日作为首版承诺；不得外推缓存末日之后的交易日。

### 2.2 实际财务公式、期间闭包和估值口径

依据 A4 §4.7 及 OD-1 接受记录，实际 S07 使用：

- NP：**归母净利润**；OCF：**合并经营活动现金流量净额**；EQ：**归母权益**。三者均为实际必需原值，须按同一决策 T 的可知版本及相容会计口径绑定；它们仍不是全部供应合同。
- 非年末：`NP_TTM(q)=NP_YTD(q)+NP_FY(y-1)-NP_YTD(q-4)`，OCF 同式；年末直接全年累计。`q-4` 指上年同一季度末，不是当前响应中向前数四条。
- `ROE_TTM=NP_TTM / ((EQ_q+EQ_(q-4))/2)`，平均权益须正；年报用当年末与上年末。不是披露加权 ROE、扣非 ROE、期末单点权益 ROE 或简单季度年化。
- 估值使用 **T 对应业务日的 PE_TTM**，正 PE；NP_TTM > 0、OCF_TTM > 0、ROE_TTM ≥ 10%，非金融。E07 中已知利润/OCF/ROE 不达门槛者仍按已接受定义参加适用的行业比较；缺值不能伪装成亏损剔除。
- 同业 `score07=(Q-(PE_TTM)+Q+(ROE_TTM))/2`；分降序、ROE 降序、PE 升序、证券 ID 升序。完整同业分母、分类版本、全序与缺失账都是依赖，不可用全市场 PE 分位摘要替代。

最小期间闭包如下；**所有组成值都要截至使用 T 的版本，不是各期今天的最新数值**：

| q | NP/OCF 原始流量依赖 | EQ 依赖 |
|---|---|---|
| yQ1 | yQ1 YTD、FY(y−1)、(y−1)Q1 YTD | yQ1 期末、(y−1)Q1 期末 |
| yH1 | yH1 YTD、FY(y−1)、(y−1)H1 YTD | yH1 期末、(y−1)H1 期末 |
| yQ3 | yQ3 YTD、FY(y−1)、(y−1)Q3 YTD | yQ3 期末、(y−1)Q3 期末 |
| FYy | FYy 全年累计 | FYy 期末、FY(y−1) 期末 |

若以单季度来源装配累计，H1 需 Q1+Q2、Q3 需 Q1+Q2+Q3、全年需四季；每项期间、累计/单季、单位、版本均须可核。**现合同已有 YTD 公式，不要求为此开发新的单季计算路线。** 单季 OCF 原件空白不自动阻断已有完整累计列；缺必要累计基数则仍拒绝。2023-01-01 期初 EQ 不自动等于 2022-12-31 期末，尤其不能忽略期初调整。

例如 `q=2025H1` 时需要 H1 2025、FY2024、H1 2024 的 NP/OCF 和 H1 2025/H1 2024 的 EQ；`q=2026Q1` 时需要 Q1 2026、FY2025、Q1 2025 以及对应权益。**这是公式代入的条件性数据需求，不宣称这些就是某历史日实际最新报告。** 最终年度/季度清单必须由每个 T 的 q(T) 与版本资格展开，不能只凭“现在是 2026 年”指定。

PE 类型与 ROE 规则已有限定接受；尚未合格的是具体供应 PE 的分母期间/归母范围、TTM 方法、股本/EPS 变更和历史回填策略，以及与 S07 q 的兼容性。若源 PE 需要 EPS/历史股本解释，这些是**条件性来源认证依赖**；不能预先要求全量 EPS/股本平台，也不能改用静态 PE/自造 PE 公式求通过。收入、毛利率、同比增长、PB/PS/PEG 没有成为本 S07 规则必需字段；F3 的 OCF/NP 使用同一对 TTM 原值，不新增收入依赖。

### 2.3 公告可用性与合同剩余边界

1. A4/A5 的产品规则：已核时刻的值仅在 `available_at≤T收盘` 可用；原始日期级公告 D 最早于 **D 后首个合格市场交易日收盘**使用。已归一化为“某市场日首次可收盘使用”的日期映射该日收盘，不再延后一天。
2. A5 U1：内核时间约定为 Asia/Shanghai 本地 ISO 日时，接入层仅在源时区可靠已知时转换，保留源时间/精度/转换版本。午夜目录编码、PDF 创建/签署日、今天获取时间均不能冒充历史首次可知时刻。
3. 保守日期映射解决日内精度的规则选择，**不能恢复缺失原版、修订影响范围、首次修订日或供应延迟证据**。官方原件披露与某个聚合供应商当时实际可交付的时点要分别认证；以后可以从原件正向重建，不能凭今天聚合行假造历史首见。
4. OD-3 的实际日终使用窗、延迟/修订可用判据、访问/运行预算及服务承诺仍未冻结；源可知性完全未知且影响执行时必须 BLOCKED。金融行业分类的具体 taxonomy/版本及正式历史 U 仍待供应证据，不由本轮命名。

## 3. 最小数据依赖及真实 Gate 矩阵

[JSON 矩阵](2026-10-22-mishi-s07-real-window-dependencies.json)逐项包含 `product_requirement / required_field / source_requirement / decision_timestamp / financial_period_or_market_date / asof_availability_requirement / calculation_dependencies / existing_chstockdata_capability / existing_qualification_evidence / missing_evidence / gate_status`。以下按实际产品路径汇总，**状态只对该行所述粒度成立，不汇总成虚假的全市场通过率**。

五维分别是：①来源可取得，②数值/语义，③历史时点可回放，④真实证券×日期覆盖，⑤产品/消费者合同。代码存在不等于①已实取；样本数值对得上不等于③④；⑤规则接受不等于完整 Design Freeze。

| 依赖 ID / 实际需求 | 来源与数值证据 | as-of / 实际覆盖 | 合同身份与最小缺证 | gate_status |
|---|---|---|---|---|
| D01 日历、252 日锚与预热 | 本地指数和公共日历入口；诊断日期可机械导出 | 缓存到 2026-09-22，目标 e 和其后日历未核；非交易所全覆盖认证 | 窗口算法已接受；需目标锚、合格日历及所有必要日期账 | PARTIALLY_QUALIFIED |
| D02–04 历史 U、上市成熟度、基础/开盘资格 | 现有代码解析、当前停牌/退市、官方当前身份缓存有局部证据 | 无目标年每日包含退市股的 U/ST/停复牌有效区间及 known_at 全量账 | 范围/120日已接受；需 U/E0/UNKNOWN 守恒及状态变更边界 | MISSING_SOURCE_EVIDENCE |
| D05 AVG_A20 / 流动性 | `load_vipdoc_daily` 保留真实 Amount/Volume；已有单位测试与本地原始包 | 部分实物确定，目标全池缺口、缺交易与停牌衔接未核 | 3000万元已接受；不能用 C×V，默认路由可能丢 Amount | PARTIALLY_QUALIFIED |
| D06 原始开收盘、估值价 | 原始 reader/行情链可复用，四股＋指数有本地实物 | 目标窗口全池和事件缺口未核；缺价不能自动填停牌或0 | 日频原始开盘模型已接受；需按身份、交易日逐槽证明 | PARTIALLY_QUALIFIED |
| D07–09 NP、OCF、EQ 及基期 | 127 条原件事实；近期 THS 缓存有值 | 旧事实最晚 2024H1；近期缓存无公告/版本绑定，目标期版本链不齐 | 三字段口径已接受；需逐 T 展开期间闭包和当时版本 | SOURCE_PRESENT_NOT_ASOF_QUALIFIED |
| D10 ROE_TTM | 数学定义已接受，已有派生代码仅可部分复用 | 无目标年度完整归母原值/基期/版本交集 | 现公共指标优先“净利润”、文本舍入，不能直接证明符合归母合同；不在本轮修复 | PARTIALLY_QUALIFIED |
| D11 财报原版、修订与可用时点 | 官方索引/原件、字段位置和选择/拒绝机制有固定实证 | 目录窗外、首次修订、未核通知范围仍未知；非目标全市场 | 日期规则有后续批准；源时间/完整性仍需证据 | SOURCE_PRESENT_NOT_ASOF_QUALIFIED |
| D12–13 指定日 PE_TTM / 分母身份 | 729 条真实旧估值行；源码确有逐日源字段 | 公共输出无逐日行；源无 vintage，旧样本有具体回填/方法风险；近期年度覆盖不齐 | PE_TTM 已接受；源算法/分母相容性未证，不能静态 PE 替换 | SOURCE_PRESENT_NOT_ASOF_QUALIFIED |
| D14 行业、金融排除 | 当前行业文本/榜单不是完整成员矩阵 | 无目标期 taxonomy 成员有效区间及分类迁移覆盖 | 具体分类未绑定；需一个一致的可消费分类及金融映射 | BLOCKED_BY_UNFROZEN_CONTRACT |
| D15 E07/同业百分位和全序 | Q 定义/排序已接受，可使用未来纯计算逻辑 | 所有同业输入和资格分母未齐；单股测试也依赖它 | 不许只在赢家或成功抓取子集算行业分位 | MISSING_SOURCE_EVIDENCE |
| D16 分析复权与已生效公司行为 | 公共复权基础存在 | 当前因子/最新 QFQ 锚无历史 as-of 参数；目标事件版本未核 | S07 本身不需新增 MA；共用分析/退出衔接须隔离未来事件 | SOURCE_PRESENT_NOT_ASOF_QUALIFIED |
| D17–19 执行限制、公司行为、税费 | 当前状态、股票公司行为和有限开盘活动接口可复用 | 无目标全池历史状态/有效价格限制/实施权益/费税唯一适用覆盖 | 日频模型及 U2/U3 已接受；真实法定事实缺证，不默用统一100股/10%/税0 | MISSING_SOURCE_EVIDENCE |
| D20 基准 | SH:000001 原始开收盘在本地 | 诊断窗有实物，真正 s/e 及逐日缺口未核 | 上证综指价格基准已接受；s 开盘缺失不能换昨收 | PARTIALLY_QUALIFIED |
| D21 批次及晚到输入 | A5 的替代、空榜/无发布/UNKNOWN 契约已记录 | 无真实发布历史及目标期完整可用性轨迹，历史模型也需来源覆盖 | 运行使用窗/源延迟与正式批次资格仍待核 | BLOCKED_BY_UNFROZEN_CONTRACT |
| D22 净值/现金/订单输出定义 | A4/A5 是可核的已接受规则证据 | 产品实际账本/联算未在本轮执行；不能由规则接受推 PASS | 本行仅确认规则身份，不索要供应方策略/用户账本 API | QUALIFIED_WITH_EVIDENCE |
| D23 收入增长、PB/静态PE、额外因子、L2/WF | 与已接受 S07 公式无必要路径 | 不作为本资格分母；EPS/股本如为 PE 认证所需已列 D13 | 增加这些指标/改 PE 须另行裁决 | NOT_REQUIRED |

矩阵中的 `MISSING_SOURCE_EVIDENCE` 表示现有材料没有证明目标覆盖，**不是已证明免费原始数据不存在**。`BLOCKED_BY_UNFROZEN_CONTRACT` 不抹去该行同时存在的历史来源缺口；D14/D21 即使获合同裁决也仍要验源。D22 的通过仅限规则身份，不能当作算法实现或真实回测 Gate。

## 4. 旧研究缺口对真实 S07 的影响

判定顺序：先得到目标 T、U/E0/行业及 q(T)，展开字段/基期闭包，再把文档的主体、期间、版本和生效可用日连接到它。`DIRECT_DEPENDENCY` 为当前 q/当日来源；`PREWARM_DEPENDENCY` 为计算基期；`INDIRECT_DEPENDENCY` 为版本发现/方法认证等支撑链；`NOT_REQUIRED_FOR_VERIFIED_SCOPE` 须有已验证的排除路径；实参未绑定则 `UNDETERMINED`。本文没有把“年份旧”作为排除依据。

### 4.1 四扫描包的 18 个槽

直接复算[字段账本](evidence/2026-10-22-w5h-f2-final-evidence-qualification/final_source_qualification.json)，23 个未解必要单元格去重为以下 18 个文档—期间—字段槽：

| 公告 ID / 证券 | 具体槽 | 数量 | 真实依赖路径及当前判断 |
|---|---|---:|---|
| 1216741269 / 000961 | FY2022 NP/OCF/EQ | 3 | 若 q=FY2022 可为直接依赖；2023 非年末 TTM 的 FY2022 NP/OCF，或 q=FY2023 ROE 的 FY2022 EQ 可为基期依赖。当前目标实参未闭合：UNDETERMINED。 |
| 1216869640 / 000002 | FY2022 NP/OCF/EQ；2023Q1 OCF/EQ | 5 | 年度路径同上；Q1 可直接使用，或成为 2024Q1 的同期 TTM/平均权益基期。仅 Q1 NP 认证不能清除这些槽：UNDETERMINED。 |
| 1217078313 / 000961 | FY2022 NP/OCF/EQ；2023Q1 OCF/EQ | 5 | 同类期间路径，版本选择还须考虑更早原件与后续直接锚：UNDETERMINED。 |
| 1217949874 / 000961 | FY2022 NP/OCF/EQ；2023H1 OCF/EQ | 5 | H1 可直接使用，或成为 2024H1 同期基期；H1 NP 已认证不等整包合格：UNDETERMINED。 |

这些槽不等于 18 个缺失经济事实或 18 份缺失文件，原件已在。已有独立原报可认证部分同期间值；但只有证明扫描候选未改变所需事实、或后来的直接版本锚能覆盖目标使用时点，才可解除相应时间区间阻断，不能用“另有相同数字”清整包。

**可证明的条件性排除：** 如果真正目标各信号/退出所用 q 均不早于 FY2024、所有必要期间都不早于 FY2023，且版本链证明旧文档不延续影响这些必要事实，则上述 FY2022/2023Q1/H1 金额槽不在计算闭包；在这个已经核实的子范围才可标 `NOT_REQUIRED_FOR_VERIFIED_SCOPE`。本轮没有目标全池 q(T) 和版本继承证据，故不提前给出此产品级标签。诊断锚 2026-09-22 下也不能假设所有发行人的报告都正常及时、直接删掉仍缺数据的证券。

即使上述金额槽在新窗口被排除，旧文件仍可能作为解析器/版本拒绝的 **INDIRECT_DEPENDENCY** 控制证据保留；保留控制不要求继续 OCR，也不要求再下载旧股文件。

### 4.2 28 条旧固定查询非必要记录

本轮按实际账本归组，保留全部记录，不能沿用“非必要”作产品结论：

| 记录组 | 条数 | 按已接受 S07 公式的条件影响 | 当前真实范围分类 |
|---|---:|---|---|
| 000961 FY2021 NP/EQ/OCF 扫描比较列 | 4+4+4=12 | NP/OCF 可为 2022 非年末 TTM 的上年全年基数；EQ 可为 FY2022 平均权益基数；较早 q 也可能直接使用 | UNDETERMINED；条件满足为 PREWARM_DEPENDENCY/DIRECT_DEPENDENCY |
| 000002 FY2021 NP/EQ/OCF 比较列 | 1+1+1=3 | 同上，不能因源文档于2023披露就忽略其所载2021比较期 | UNDETERMINED |
| 000002/000961 2022Q1 NP/OCF | 2+2=4 | 若 q=2023Q1，直接进入减去上年同期 YTD 的 TTM 基期；不是可丢的附表 | UNDETERMINED；该条件下 PREWARM_DEPENDENCY |
| 000961 2022H1 NP/OCF | 2 | 若 q=2023H1，同期 YTD 基数 | UNDETERMINED；该条件下 PREWARM_DEPENDENCY |
| 000961 2023-01-01 EQ 期初 | 1 | 当前 ROE 要求 q/q−4 期末，不直接用此期初替代；若它解释必要期间重述/开账变化，可进入版本支撑链 | 原金额列不是已接受公式的直接输入；实际版本支撑影响 UNDETERMINED，条件下 INDIRECT_DEPENDENCY |
| 六份回复 FY2021 OCF 冲突位置 | 6 | 下节单列；与上面四处扫描比较列不是十个独立冲突事件 | UNDETERMINED |
| **合计** | **28** | **22 个比较/期初单元格＋6 个冲突位置** | 不将固定查询非必要升级为产品非必要 |

### 4.3 六处 FY2021 OCF 源内差异

六份回复涉及同一证券 000961、同一 FY2021 OCF：文字 1,677,198.08 万元、表格 1,677,198.05 万元，相差 300 元；独立原报精确数 16,771,980,470.34 元与表格舍入相容。单位/精度相同，不能解释为舍入或已证合并/母公司差异；原因仍未定，不改字、不造新重述。

- **会影响**：q 为 2022Q1/H1/Q3 时，该 FY2021 OCF 是 OCF_TTM 的全年基数；若直接计算 FY2021 OCF 也需要它。应按冲突发生/可知时点与必要基期连接并拒绝，不能在 OCF>0 的门槛之外静默裁掉冲突。
- **不会仅因 ROE 而需要**：ROE 分子是 NP，分母是 EQ；FY2021 OCF 不参与 ROE。q=FY2022 时 OCF_TTM 直接为 FY2022 OCF，也不因计算年度 ROE 而额外引入 FY2021 OCF。
- **当前结论**：真实窗口是否触及这些 q/证券尚未核实，分类 `UNDETERMINED`，不是“整个真实 S07 不能运行”。若实际全部必要 OCF 期间晚于 FY2021 且无继承影响，可在核实的范围作排除。本轮 12 个条件依赖断言验证了有此依赖才拒绝的边界，未把它添加为实际公式的新基数。

### 4.4 完整版本发现、首次修订与公告规则

完整发现和首次修订日对真实必要字段是 **INDIRECT_DEPENDENCY**，逐 T 选中的值/版本/可用日是 **DIRECT_DEPENDENCY**。F2 六个固定索引窗闭合不等目标年度所有证券正文及通知影响已核齐；`unknown_revision_recall=NOT_ESTABLISHED` 不是全市场不可行证明。

最小证明范围应是目标必要事实的完整影响集合、正向原报/比较期锚、每次变化可知时点和中间无未处置候选，**不要求为无依赖旧期间研究所有公告**。较晚直接锚可以从其可用时点支持选择，不能反证较早空白期，也不能把首次观察到的修订日当首次披露日。A5 日期规则的批准只解决映射语义，未解决这些来源证据。

## 5. 当前免费能力：已有实物、可复用代码及尚未证明之处

| 能力 | 已有事实 / 当前可复用入口 | 不能据此声称 |
|---|---|---|
| 原始价格、量、成交额 | [vipdoc_history.py:98](../../src/chstockdata/vipdoc_history.py#L98)、[公共 reader:171](../../src/chstockdata/vipdoc_history.py#L171)。`.rh3a2-vipdoc` manifest 含 12,219 个代码键，含多类证券/历史文件，非只有四股。元/股及价格尺度有既有测试；本轮只复读四股和指数。 | 12,219 不是 A 股历史池数，也非全部文件本轮验收。000961 本地末条 2024-05-08，不能仅据末条推退市日/停牌日。默认 [daily_bars.py](../../src/chstockdata/daily_bars.py) canonical 路由不保留 Amount 的边界仍在；原始 reader 可复用，不必为调查先开发 Provider。 |
| 日历/基准 | `fetch_trading_calendar/load_trading_calendar` 与显式 `market='sh'` 的指数 reader；本地指数 1990-12-19…2026-09-22。 | 指数观测日历不自动认证完整交易所日历；SH:000001 INDEX 不能与 SZ:000001 股票混淆。 |
| 三表与指标 | [a_stock.py:3461](../../src/chstockdata/a_stock.py#L3461) 三表、[3568](../../src/chstockdata/a_stock.py#L3568) 指标、[point_in_time.py:77](../../src/chstockdata/point_in_time.py#L77) 公告过滤可复用。R5 THS 两股三表各50期有缓存，最新到2026H1。 | 公告过滤只筛现有记录，不能创造被覆盖原版。公共指标 [3658](../../src/chstockdata/a_stock.py#L3658)、[3763](../../src/chstockdata/a_stock.py#L3763) 优先取“净利润”；即使公式结构类似，也未证明始终是 S07 归母利润。文本两位小数不是用于精确行业排序的无损原值合同。 |
| 近期财务来源存在性 | 本轮对既存 600519 THS 三表，检查2024Q1/H1/Q3/FY、2025Q1/H1/Q3/FY、2026Q1/H1，共 **30/30 字段—期间槽有数值**。 | 没有独立核验这30个近期值的原报正确性；行内无公告/版本身份，不能当30个PIT合格点。它证明“缺近期PIT资格”与“完全没有免费近期数值”不同。没有新增样本。 |
| 官方原件及离线解析 | 原件身份、表/列/单位、归母/合并、累计/单季、源内冲突和按字段拒绝可复用。最终127条事实最晚报告期2024-06-30、公告2024-08-31。 | 127不是127个独立版本；没有 FY2024/2025/2026 的目标原件认证，不能支持近期252日。扫描未认证不是原件客观不可读，也未证明所有数值必须手工。 |
| 历史估值 | [a_stock.py:5214](../../src/chstockdata/a_stock.py#L5214) 内部读取 PE_TTM/PE_LAR 等；[5415](../../src/chstockdata/a_stock.py#L5415) 实际公共返回仅最新 metrics/percentiles/history摘要，无每日数组和 as-of参数。W5-H 有两股2025及一股2020共729原始行。 | “尚无公共逐日出口”是接口能力事实，不是源无法取得；暴露行也不解决 as-of。两股2025不等2025–2026全池。 |
| 估值回填/方法风险 | W5-H 2020-01-02 600518 静态 PE 诊断分母与后来2019年度行只差约3.73元，该行当前公告日为2021-04-28；R2 同股2020-01-09当时披露TTM利润为正，源 TTM PE 却为负。 | 前者是有数值支持的回填推断，非全部源算法查清；静态反例也不直接等同当前 S07 的 PE_TTM，但与 TTM 反例共同要求核分母 vintage。不得用最新净利倒算历史PE求“修好”；源逐日值正确/可知性必须单独证明。 |
| TDX 专业财务文件 | R3/R4 的 DAT 可读，已观察同一行分项修订、小计/OCF仍原版混合。 | 不能把“有免费批量包”当历史单一版本；这是已观测来源内容缺陷，非所有包永久不可用的定理。 |
| 行业/身份/交易事实 | `resolve_ticker`、当前停牌/退市/`fetch_tradability`、行业背景、股票公司行为入口已有；历史开盘证据为限定集合的正活动及官方否决。 | 名称表≠历史U；当前状态≠历史状态；行业文本≠完整历史成员；一分钟有活动≠日频任意订单必成交。Baostock 私有线索/访问失败只属未资格来源，不能记成已供应或免费永久不可得。 |
| 复权与公司行为 | `get_adjusted_bars`、`get_corporate_actions` 有基础；原始价与因子、权益事件可分别检查。 | 最新因子锚/公告截止不是完整历史版本；现金/送转/可售日/支付日/逐批税费仍需事实。S07 价值信号无需新增技术因子，不因共享工具存在而扩大指标范围。 |

历史估值的下一证明可以是来源已有且可核的指定日版本及算法说明；若只能提供今天重算历史值，则这一路不通过。官方财报版本可恢复并不自动恢复 PE 的历史分母/股本规则；需要自算 PE 或增加来源时必须另有明确合同/授权，本轮不开发。

## 6. 一次性下一工作包与最小准入条件

**只推荐一个后续包：`S07_REAL_WINDOW_FREE_SUPPLY_QUALIFICATION`，真实窗口免费供数资格验证。** 消除的实际阻断是“近期真实年度依赖与可供输入未绑定、财务/PE/历史池/行业/执行交集未资格”，不是让旧六股 OCR 全绿。不是生产实施 Prompt，不默认派生 W5-H 新阶段。

规则依赖已足够具体，无需 Owner 重新选择 TTM、ROE 或20日调仓。**但现在还不能无条件派发真实取数验收：** 必须先固定实际日期锚和供应分母、分类及执行可用判据，批准后续任务的网络/访问预算；本次 `NEW_NETWORK_FETCH=NO` 不延伸为后续取数权限。准备工作与正式资格结论分开。

### 6.1 最小 Owner/供应合同裁决单

| 项 | 本轮已完成 / 仍需什么 | 不需要重开 |
|---|---|---|
| O1 实际验证锚与承诺 | 在后续启动时，以已完成日和合格日历明确写出 e、s、s−1、s−65、默认及所验白名单；若拟采用缓存诊断区间2025-09-09…2026-09-22，须 Owner 明确接受其滞后身份，不能自动作为近期商品窗口。若坚持最新目标，则由新合格日历机械导出，不能在本轮无证据列出具体起止日。 | 252净值日、65共同技术预热及S07独立财务闭包已有规则。日历导出本身不需再发明窗口算法。 |
| O2 历史分母和分类绑定 | 供应方提交目标U的身份/生命周期证据及一个一致 taxonomy/version、金融映射；Owner/消费者确认其可消费合同。没有这些输入可先形成带缺口的供应清单，不能宣称正式横截面通过。 | 沪深普通A股范围、金融排除与同业比较要求。不能为验证方便选今天存活股。 |
| O3 可用性、PE来源方法与预算 | 明确可核原件/结构化值的版本绑定、使用窗/晚到证据判据，及受控访问的请求/字节/墙钟/重试上限；指定现有免费 PE 入口及其方法证据。无法证明既有PE_TTM与已接受口径相容时，携具体反例请求Owner决定，不能先开发另一个PE。 | A5 日期规则/时区、U2/U3输入约定；不重新批准旧实验的保守日期映射，不把未知源首次可得改成已知。 |

没有以“整体 Design Freeze 未完成”为理由中止本轮依赖调查。O1–O3 是绑定真实实参和来源/运行验收条件；其余 UI、价格、权益配额等 OD-3 数值不应被加成此次供数资格调查的前置审批。

### 6.2 该一个包的最小范围、证据和连续修复边界

| 项目 | 最小充分约束 |
|---|---|
| 日期范围 | 正式分母必须是绑定后的完整 s…e 252净值日、s−1信号及s−65…s−1统一技术预热；S07财务按q(T)闭包另向前延伸。可直接复用的具体离线诊断日期见§2.1；它不是替代正式窗口的较短成功区间。 |
| 证券范围 | 首先对 **目标历史U(D)并集** 作元数据/来源可得性、覆盖/失败清单；不能用六股替代。数值与版本穿透的最小固定控制使用已有 **SH:600519、SZ:000002**，要求目标期真实原报/基期/PE；它们是已有样本复用而非宣称代表全市场。金融排除复用SH:601398控制；旧000961/600518仅作退休/版本/冲突拒绝控制，不为旧PDF再扩链。若目标历史U存在新上市/退市/状态变更，须从该U按事前规则选实际边界控制，另明确批准新增样本及预算；没有边界证据则覆盖不通过，不事后换成功股票。 |
| 已有数据 | 复用VIPDOC价量额/指数及原始单位合同、THS/Sina缓存普通值、现有官方索引/原件/位置和版本拒绝脚本、729估值原行、现存当前身份/状态事实。只对目标依赖缺口考虑未来免费官方原报/公告身份及现有免费估值/状态路径，不要求另建Provider/数据库。 |
| 最先要解决的来源问题 | 在目标年检验 **PE_TTM的分母/版本是否可证明当时可知**，同时绑定两控制股q(T)所需原报和同期基期；有价无vintage不得通过。来源只有最新历史重算值时准确拒绝该路径，不无限尝试别的股票或继续旧OCR。历史U/行业必须给全分母缺口清单，不能以两股穿透成功覆盖它。 |
| 独立可核的局部通过 | 控制股每个必需字段、期间、版本、日期、金额/单位有原件位置与SHA；全部组成值≤决策截止，原版/修订切换和公告前拒绝正确；未来版本变化不影响过去。PE类型/分母期间/源方法及历史回填身份明确，能与当时信息集核对。未知值不变0或亏损；错误接受为0。失败、正常空、已知不适用分别计数。 |
| 全窗口供应资格通过 | 对每个必要T/证券/字段有值或经独立证据支持的排除/不适用处置，U/E0/E07/行业分母守恒，无未处置必要UNKNOWN、无中间日期/版本洞；执行资格、原始价、公司行为/税费/基准满足模型输入。仅局部控制通过仍为PARTIALLY_QUALIFIED，不称全市场/产品PASS。不自设95%阈值。 |
| 明确失败/证据不足 | 原件/必要旧版不可取得，或PE只能今天重算且无vintage/方法证据，或历史U/行业/状态缺口无法分辨，或访问/预算不足：对受影响路径给FAIL/INSUFFICIENT_EVIDENCE及具名槽。范围分母保持原状；不能缩窗、删证券、换静态PE、把来源失联当无记录。一次失败不提前停止其它独立离线项。 |
| Codex可连续修复 | 经该包单独授权后，可在任务自有离线资格程序内修复已复现的字段/单位/列/期间/版本连接与拒绝缺陷，复用同原件重放，保留首次失败及固定分母。网络仅在新批准预算内补目标依赖；不逐个普通解析bug再次请示。不得修改归档、消费者规则、公共生产API、Provider、数据库或引入付费源。临时环境如确需创建须在任务目录、证据导出后清理自己拥有的环境；不清理原件/既有evidence。 |
| 何时回Owner | 绑定O1–O3及授权该包时一次审查；执行中只有需要突破证券/日期/预算、改变公式/来源合同或商品承诺、必要来源证据确定不可满足时携准确影响回报。普通离线修复在范围内连续完成；达到固定通过/失败条件即结束，不自动生产或无限新研究。 |

这是一个供应资格工作包；最终产品现金账本验收仍属于消费者 Gate。若供应资格数据输入全部通过，也不自动授予生产实现、消费者联算、上线或下阶段授权。

## 7. 本轮实际离线复核与限制

使用现有 `.venv/Scripts/python.exe -X utf8 -B -`，仅内存读取 JSON、原件和5个DAY文件，未创建环境或中间证据副本。重放程序安装 socket/connect/getaddrinfo/bind 拒绝钩子，实际网络尝试0；未执行会覆盖归档的 `run_package.py`。没有重跑数万文件哈希、全量OCR或发行Gate。

| 本轮检查 | 新鲜结果 / 证据边界 |
|---|---|
| 关键归档身份 | 最新F2 manifest内8项：字段资格、最终账本、回放输出/验证、质量、字段T连接、资格规则与选择器，**8/8 SHA匹配**。另外实际原报1216273938、1216281757两份PDF与账本SHA匹配。不是整库完整性重新认证。 |
| 真实处置分母 | 91行＝23必要未解＋28固定查询非必要未解＋24不同主体＋15既存版本＋1无目标影响；23必要单元格去重18槽、四包3/5/5/5。六种允许状态中“新事实”0，不删除状态或分母。 |
| 保存结果复算 | 127条账本；最晚财务期2024-06-30、最晚公告2024-08-31。162个实际输出＝87选择＋75 UNKNOWN；未把UNKNOWN计成取数成功。 |
| 选择器新重放 | 直接调用既存 `replay_final.select`，21个来源查询＝3选择＋18拒绝，全部符合保存断言；未调用其写文件入口。 |
| FY2021条件依赖 | 6处冲突各测“未请求该基期不因该冲突拒绝 / 显式必要基期时UNKNOWN并列冲突ID”，**12/12**。这些是拒绝边界测试，不添加真实S07公式依赖。 |
| 近期缓存存在性 | 既有600519 THS三表各10报告期，30/30有值、0行具公告/版本键；仅证明来源存在，不认证数值或PIT。 |
| 历史估值缓存 | 三份原响应各243行，总729；2020/2025实际首尾重读；无历史vintage/公告身份/可用时点字段。不重新取数或调用网络公共API。 |
| 市场文件小样本 | 指数8,731条；600519/000002/300750各到2026-09-22；000961到2024-05-08。按32字节struct复读日期、正Close与窗口索引；不将这个小样本冒充全池正确性或状态资格。 |
| 文件安全 | 写入前tracked diff和staged diff为空；对28个直接使用的关键合同/代码/evidence文件保存SHA作终检基线。完整逐文件Git状态在工具传输时被截断，不把可见行数当实际文件分母或声称完成整库逐文件保护审计；另核紧凑状态和关键原件。没有给15,620旧文件作新一轮全量hash。 |

交付终检：28/28关键文件SHA未变，31个本地文档链接存在，JSON的23项均具11个必需字段且状态合法；HEAD未变，tracked/staged修改均为0。紧凑Git状态为66项（含既有未跟踪材料和本轮两文件），不是实际文件总数；本轮没有对整个未跟踪目录作字节不变的全量声明。

复核关键输入分别为最新F2的 `final_source_qualification.json / source_aware_ledger_final.json / final_replay_results.json / final_replay_validation.json`，R5的 `600519_ths_{benefit,cash,debt}.json` 和W5-H的三份 `eastmoney_*.json`。上述相对名均位于本仓库 `docs/audits/evidence/` 下相应日期目录；原始文件不复制。独立复核可直接读取这些JSON分母，并按 `replay_final.py` 的 `select(...)` 输入连接重放；不得调用旧写入式入口覆盖证据。

本轮没有重验全部官方原报金额、完整市场池或法律费率，不将旧测试数量表述为本轮新测试。结论置信边界是已读取的合同、当前代码和上述有界实物；没有新市场取数，实际近期数据缺口保持如实记录。

## 8. Findings 与交接

| 分类 | 本轮判定 |
|---|---|
| CONFIRMED_DEFECT | 对本产品需求，公共历史估值出口无逐日行；既有财务派生利润取值/文本精度不能直接证明满足S07归母无损合同。TDX混合内容、历史估值分母反例及源内OCF冲突复用既有事实，不把旧已修单位bug再列待修。没有本轮新增生产回归结论。 |
| UNRESOLVED_RISK | 真实日期锚、每日历史U/状态/行业、近期财务闭包和完整版本/首次变化、PE vintage/方法、执行/权益/税费及使用窗未资格。旧18槽/28记录实际依赖尚需连接；不假定全部无影响或全部致命。 |
| SPECULATIVE_CONCERN | 所有免费数据都不可得、所有扫描件必须人工、固定六股成功可推全市场、2023文件必然不影响预热、未知修订意味着全部年份不可运行，均无本轮充分证据。 |
| FUTURE_ENHANCEMENT | 新Provider/数据库/生产采集、通用OCR/财务平台、重造指标、自算未批准PE、三年/WF/额外策略均不在授权内。必要最小数值出口若未来确需实现，也须另行授权，不与源可得性混为一谈。 |

交接：当前阶段/步骤为 **S07_REAL_WINDOW_DEPENDENCY_ADMISSION 调查与离线复核完成，等待Owner Review**。HEAD保持 `5584f5fcacccef9a9531a7a32b8463ea6771d312`，原有tracked/staged状态和未跟踪材料保留；本轮仅新增本文及JSON矩阵。Gate为 **INSUFFICIENT_EVIDENCE / MISHI_S07_HISTORICAL_GATE=NOT_PASSED**；依据是§3真实依赖矩阵、§4条件路径和§7实际复核，不是实施者PASS声明。范围无变化；推荐下一动作仅为审核O1–O3并决定是否授权一个真实窗口免费供数资格包，**下一阶段尚未授权**。

```ini
CURRENT_DECISION = INVESTIGATE

S07_APPROVED_WINDOW = RULE_BASELINE_ACCEPTED_252_COMPLETED_NAV_SESSIONS__EXACT_S_E_NOT_BOUND__FULL_DESIGN_NOT_FROZEN
S07_REQUIRED_PREWARM = COMMON_65_CLOSES__S07_AVG_AMOUNT_20__Q_DEPENDENT_FY_PRIOR_YTD_AND_PRIOR_EQUITY_VINTAGES
S07_FIELD_DEPENDENCIES = PARENT_NP_CONSOLIDATED_OCF_PARENT_EQ__TTM_ROE__DATED_PE_TTM__HISTORICAL_U_INDUSTRY_STATUS_PRICE_EXECUTION_EVENTS_FEES_BENCHMARK
S07_PIT_TIME_RULE_STATUS = OWNER_RULE_RECORDS_RECOVERED_INCLUDING_U1__F2_EXPERIMENT_UNCHANGED__SOURCE_AVAILABILITY_AND_OPERATIONAL_WINDOW_UNQUALIFIED

FINANCIAL_ASOF_COVERAGE = PARTIAL_FIXED_OLD_FACTS__RECENT_VALUES_PRESENT_WITHOUT_VERSION_BINDING__REAL_WINDOW_NOT_QUALIFIED
HISTORICAL_VALUATION_COVERAGE = SOURCE_PRESENT_NOT_ASOF_QUALIFIED__729_OLD_ROWS__PUBLIC_DAILY_EXPORT_ABSENT__DENOMINATOR_RISK
HISTORICAL_UNIVERSE_COVERAGE = MISSING_TARGET_DAILY_U_LIFECYCLE_STATE_AND_INDUSTRY_EVIDENCE
MARKET_AND_EXECUTION_DATA_COVERAGE = RAW_PRICE_AMOUNT_CALENDAR_REUSABLE_PARTIAL__TARGET_COVERAGE_AND_EXECUTION_FACTS_NOT_QUALIFIED

OLD_SCAN_GAPS_REAL_S07_IMPACT = UNDETERMINED_UNTIL_TARGET_Q_VERSION_AND_UNIVERSE_JOIN__18_SLOTS_NOT_A_UNIVERSAL_BLOCKER
FY2021_OCF_CONFLICT_REAL_S07_IMPACT = CONDITIONAL_DIRECT_OR_2022_NONANNUAL_TTM_BASE_DEPENDENCY__NOT_A_ROE_INPUT__REAL_TARGET_JOIN_UNDETERMINED

EXISTING_FREE_CAPABILITIES = VIPDOC_RAW_BARS_AMOUNT_INDEX__CURRENT_IDENTITY_STATUS_APIS__STRUCTURED_FINANCIAL_CACHES__OFFICIAL_ORIGINALS_AND_BOUNDED_VERSION_SELECTOR__VALUATION_SOURCE_ROWS
REAL_S07_BLOCKERS = TARGET_DENOMINATOR_AND_WINDOW_BINDING__RECENT_FINANCIAL_VINTAGES_AND_BASES__DATED_PE_ASOF_METHOD__HISTORICAL_INDUSTRY_STATE_EXECUTION_AND_AVAILABILITY_INTERSECTION
UNFROZEN_OWNER_DECISIONS = EXACT_RUN_ANCHOR_AND_STALENESS_IF_ANY__TAXONOMY_BINDING__SOURCE_USE_AND_ACCESS_BUDGET_CRITERIA__FULL_DESIGN_ACCEPTANCE_NOT_GRANTED

NEXT_MINIMUM_WORK_PACKAGE = S07_REAL_WINDOW_FREE_SUPPLY_QUALIFICATION__ONE_PACKAGE_AFTER_O1_O3_BINDING_AND_SEPARATE_AUTHORIZATION
NEXT_GATE_ADMISSION_READY = NO_UNCONDITIONAL_DISPATCH__DEPENDENCIES_RECOVERED__TARGET_INPUTS_AND_BUDGET_MUST_BE_BOUND

MISHI_S07_HISTORICAL_GATE = NOT_PASSED
PRODUCTION_IMPLEMENTATION_AUTHORIZED = NO
PRODUCT_SCOPE_CHANGED = NO
GIT_COMMIT = NO
GIT_PUSH = NO
OWNER_REVIEW_REQUIRED = YES
```
