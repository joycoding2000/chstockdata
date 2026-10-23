# SIOS H01 零 PIT 信号根因复核与数据交付最小修复

日期：2026-10-22。Owner 决策：`FIX_ONLY`。本轮完成离线资格修复、数据重建和接收验证；结论为 `H01_DATA_PACKAGE_READY_FOR_CONSUMER_ACCEPTANCE`，等待 Owner 验收。没有执行策略、回测、生产集成、提交或推送。

## 真实根因与各证券阻断

`CONFIRMED_DEFECT`：原交付目录中 `build_delivery.py:196-208` 在无事件审计成功后，仍无条件将每条记录写成 `HISTORICAL_EVENT_ASOF_COVERAGE_NOT_ATTESTED`、`pit_signal_qualified=False`，并清空 PIT 总回报和指标字段。原 `receive_delivery.py:100,105-106` 又要求这些空值、固定四项缺口及零资格结果存在，因而其“通过”只能说明失败包内部一致，不能证明数据不可用。

| 证券 | 原始记录 | 原程序共同阻断 | 另一个真实问题 |
| --- | ---: | --- | --- |
| 513500 | 625 | 无条件 NOT_ATTESTED / False / null | 未发现必要事件覆盖缺口 |
| 513030 | 625 | 无条件 NOT_ATTESTED / False / null | 2025-01-23 的真实零成交需要停牌原件认证 |
| 513520 | 625 | 无条件 NOT_ATTESTED / False / null | 未发现必要事件覆盖缺口 |

实际代码没有逐日寻找“官方无分红证明”的循环，也没有按年报发布日期比较历史 T 的有效资格判断；过严解释直接被写成全量失败常量。不能将这个缺陷描述成三只基金实际发生了权益来源请求失败。513030 的单个零成交记录也不能解释其余 1,874 条被清空。

根因定位先于实现修改。完整机器记录见 [root_cause.json](evidence/2026-10-22-sios-h01-final-repair/root_cause.json)。原始报告、ZIP、接收器、87 项测试和原证据保持原样，本轮对 197 份受保护原件逐一复核 SHA256。

## 九份官方年报与认证边界

九份原件全部复用本地官方缓存，再从原始 PDF 或 OOXML 正文重新提取，并与旧包固化的提取结果核对。校验基金主代码、正文报告期间、分配披露及基金份额变动表；不是仅凭文件名或下载成功认定无事件。

| 基金 | 年报及正文期间 | 披露日期（只有日期精度） | 现金分配 / 持有人单位变化 |
| --- | --- | --- | --- |
| 513500 | 2023-01-01—2023-12-31 | 2024-03-29 | 无 / 无 |
| 513500 | 2024-01-01—2024-12-31 | 2025-03-31 | 无 / 无 |
| 513500 | 2025-01-01—2025-12-31 | 2026-03-31 | 无 / 无 |
| 513030 | 2023-01-01—2023-12-31 | 2024-03-27 | 无 / 无 |
| 513030 | 2024-01-01—2024-12-31 | 2025-03-31 | 无 / 无 |
| 513030 | 2025-01-01—2025-12-31 | 2026-03-31 | 无 / 无 |
| 513520 | 2023-01-01—2023-12-31 | 2024-03-28 | 无 / 无 |
| 513520 | 2024-01-01—2024-12-31 | 2025-03-31 | 无 / 无 |
| 513520 | 2025-01-01—2025-12-31 | 2026-03-31 | 无 / 无 |

每只基金三个连续完整年度覆盖冻结预热 2023-03-09—2023-12-29，以及观察期 2024-01-02—2025-09-30。无现金分配结论来自利润分配披露；无持有人单位变化结论来自基金拆分变动份额栏及相关实收基金披露。513030 还明确列示拆分/份额折算调整为空；513520 的拆分、折算文字属于通用会计政策，不能当作实际事件。普通申购赎回使基金总份额改变，不改变既有持有人每单位权益，未被计作拆分。

认证范围严格限定为上述期间已实施的基金现金分配，以及影响持有人单位权益的拆分、合并或折算。既有事件材料未出现与这些年报冲突的已实施正事件，也未发现指向该期间正事件的具名未决公告。这里不声称已取得所有拟议、取消公告的完整目录，不将结论外推至窗口外或未来。

每份原件的官方 URL、SHA256、正文页码/块号、原文摘录、份额变化上下文及认证期间，均在新包 [fund_actions.json](evidence/2026-10-22-sios-h01-final-repair/H01-delivery-repaired/fund_actions.json)；原件和完整提取文本一并保留，可逐条复核。

证据角色明确分开：

- `HISTORICAL_SIGNAL_INPUT`：历史 T 可用的原始市价，以及已发生且按合同可用的权益事件。原始价格使用现有消费者 `EXCHANGE_RULE` 收盘可用性规则，不升级成历史下载时点的实际观测证明。
- `EX_POST_COMPLETENESS_AUDIT`：后来取得的官方报告验证历史窗口有无遗漏事件。年报的发布日期保留为日期，`published_at=null`，不会输入历史指标或伪装成历史 T 已知的消息。

本窗口经正面官方披露认证无权益事件，持有单位数和现金分配均不变，因此原始市价比值与该窗口持有总回报一致。后来验证“没有遗漏事件”不向历史输入未来分红金额、未来除息结果或未来拆分比例。仅凭年报晚于 T 发布，不能否定这一条件成立时的原始价格总回报。

## 513030 全天停牌、观察与估值

[上交所官方 PDF](https://www.sse.com.cn/disclosure/fund/announcement/c/new/2025-01-23/513030_20250123_HU9P.pdf) 的基金代码为 513030，公告主体为华安基金，落款为 2025-01-23，明确记载当日开市起停牌至收市。原始文件保存在新包 `sources-repair/001-513030-20250123-sse-official-halt.raw`。

```text
SHA256 = be01b505d9c05cf5c7bc58a231849379321d519d154f789b2ad3c5ae5bd81c28
```

| 日期 | Open | High | Low | Close | Volume | Amount |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 2025-01-22 | 1.778 | 1.834 | 1.752 | 1.815 | 2253657500 | 4023045120 |
| 2025-01-23 | 1.815 | 1.815 | 1.815 | 1.815 | 0 | 0 |
| 2025-01-24 | 1.869 | 1.889 | 1.790 | 1.838 | 926965498 | 1725613312 |

该日是有原始行情记录、官方原件认证的全天停牌，不是行情缺失，也不是仅由零成交推测的停牌。保留原始价格 1.815 作为既有估值记录，其与前收一致；成交资格为否，不生成交易或虚构 VWAP。

SMA200 的观察合同已能从未修改的消费者实现确定：`DailyBar` 接受真实零成交；`DecisionContext.bars_for`（`backtest/engine.py:251`）及 `_known_bars_through`（同文件 `:1124`）按日期和可知时刻提供记录，没有按成交量或停牌剔除；`etf_relative_momentum.py:117,120,140,141` 从该序列读取 closes、126 观察和最近 200 个值。故该日既有可用日线占一个观察位，执行资格独立处理。没有修改 SIOS 观察、交易日、126 日或 SMA200 规则，也没有运行消费者策略。源文件快照、SHA 和静态路径记录见 [observation_policy.json](evidence/2026-10-22-sios-h01-final-repair/H01-delivery-repaired/observation_policy.json)。

公告只有日期精度，实际发布时间为未知。沿既有消费者日期规则，保守可用时间为当日 23:59:59+08:00，并明确标记为规则推定而非观测；不宣称盘前已经知道停牌。当天 15:00 的原始行情观察沿原 RAW 合同处理，停牌事实属于事后审计，不提前输入信号。见 [suspension_evidence.json](evidence/2026-10-22-sios-h01-final-repair/H01-delivery-repaired/suspension_evidence.json)。

## 最小离线修复与数据结果

新增代码仅位于本轮 evidence 目录及 `tests/test_sios_h01_final_repair.py`。`qualify_repair.py` 负责证据身份、期间连续性、观察资格及未来事件检查；`rebuild_delivery.py` 复用原包原始数据和数值结果，按实际认证恢复 PIT 字段；`receive_repaired.py` 保留原接收器的原始记录、单位、VWAP、预热、126/SMA200 数值与事件检查，替换强制失败的固定断言，并独立核验新证据。

认证显式区分五种状态：

| 状态 | 处理 |
| --- | --- |
| `CONFIRMED_NO_EVENT_IN_SCOPE` | 仅官方身份、完整期间和无事件披露成立时允许本轮无事件导出 |
| `QUALIFIED_POSITIVE_EVENT` | 必须有实际实施、有效日期、金额/比例、明确单位和来源；不套用无事件计算 |
| `SOURCE_COVERAGE_INCOMPLETE` | 保留缺口并阻断相应资格 |
| `EVENT_IDENTITY_AMBIGUOUS` | 保留身份歧义并阻断 |
| `SOURCE_ACCESS_FAILED` | 与正常空结果分开，阻断 |

没有将空列表直接视为无事件，没有移除 fail-closed。公告晚于截止时刻、未知时刻、未来事件以及缺字段正事件仍被拒绝。生产 `get_fund_corporate_actions` 的正常空结果和请求失败语义保持原实现。

| 项目 | 513500 | 513030 | 513520 | 合计 |
| --- | ---: | ---: | ---: | ---: |
| 原始记录及合格总回报观察 | 625 | 625 | 625 | 1875 |
| 冻结观察期前合格预热 | 200 | 200 | 200 | 600 |
| 观察期 126/SMA200 输入完整证券日 | 425 | 425 | 425 | 1275 |
| 缺失日期 | 0 | 0 | 0 | 0 |

1,875 是包括预热的总回报观察数，不代表全部预热日已经具备 126/SMA200 指标；预热起点尚不足期的指标仍为空。观察期内 1,275 个证券日均满足冻结规则。126 观察使用 `current / observation[-126] - 1`，即 125 个间隔；SMA200 为含当日的最近 200 个观察算术平均。原始价、成交量、成交额、整数编码、float32 编码、源记录定位、SHA 和行情可用时刻逐字段与旧包一致。没有截取方便的子区间，没有扩大基金或时间窗，也没有重写总回报数值算法。

## 回归和独立接收

| 验证 | 结果 | 证据 |
| --- | --- | --- |
| 原 87 项测试 | 87 passed；测试 ID 集合与原 JUnit 完全一致，原测试未改 | `old-87-tests.xml`、stdout |
| 新增回归 | 14 passed | `new-repair-tests.xml`、stdout |
| 原接收器独立接收原包 | exit 2，重现原包阻断 | `original-receiver-original-package.json` |
| 原接收器独立接收新包 | exit 1，仅固定失败断言触发 | `original-receiver-new-package.json`、`root_cause.json` |
| 修订接收器独立进程接收新包 | exit 0，29,986 checks，errors=[]，accepted=true | 新包 `validation_report.json` |
| 九份原件重新提取 | 全部匹配已存正文并重新认证 | `final-reaudit-and-rebuild.*` |
| 离线再重建 | manifest 字节完全一致 | `offline-reproduction.*` |
| 原件和行情保全 | 197 原件 SHA 一致，1,875 行指定原始字段一致 | `completion.json`、`baseline.json` |
| 新 ZIP | CRC 通过，包内 manifest 与目录一致，123 文件 | `completion.json` |

新增测试覆盖报告晚于 T 仅作审计、真实九份期间与身份、错误基金、来源失败/期间缺口/身份歧义、正事件字段和单位、未来事件拒绝、日期精度、停牌与普通零成交及缺行的区别、停牌事实冲突、原始数值资格恢复及实际接收。现金分配和拆分采用条件性模拟验证财富关系，并区分应收、支付和现金可用时刻；模拟事件没有混入真实事件账本。红阶段失败和绿阶段结果均已导出。

原接收器在新包上的 1,878 个错误精确分为：1,875 个“历史资格必须为空”断言、1 个旧零成交未知标签断言、1 个“必须保留四缺口”断言、1 个“必须不能 PASS”断言。修订只纠正这些条件及其必要证据核验，原脚本仍独立保存、独立运行，没有把旧失败隐藏成旧脚本通过。

## 独立身份、预算与复现

| 包 | ZIP SHA256 | manifest SHA256 |
| --- | --- | --- |
| 原 `H01-delivery.zip` | `18b3025a7380f4d1f7e510b41af435f08b5e8788314e1278c99c2429c4df7877` | `68ca0d4facc72b03f4828aae1b254fbd10beec4b456d7aa1ff80cea0e89f1dd0` |
| 新 `H01-delivery-repaired.zip` | `82dd2f7258a410285f6be27be7232d35fa31b1fba32ad0bd0a31f7d903873c19` | `8d2f2400b011891f17f6e9c9e2950c6608ab12d1759044cc06e04040e02be79a` |

新 ZIP 为 8,971,030 字节。原 manifest SHA 与 Owner 给定值完全一致。新包保留 parent identity、旧 manifest 和旧失败产物的独立副本；原目录没有覆盖。

本轮独立预算经 Owner 明确接受。先检查缓存，九份年报和原行情全复用，仅取得具名上交所停牌 PDF：**1 / 12 次请求，76,987 / 15,000,000 字节，0 次重试**。独立新账本未继承旧任务余额，未使用收费数据、新 ETF、全市场搜索或新提供者。新旧网络账本分别保留。

解压新 ZIP，在 `H01-delivery-repaired` 中执行：

```powershell
python tools/rebuild_delivery.py --package .
python tools/receive_repaired.py . --report validation_report.json
```

重建复用缓存；PDF 核验使用已有可选 `pypdf`，接收器仅使用标准库。完整仓库验证入口为 `evidence/2026-10-22-sios-h01-final-repair/verify_repair.py`，测试日志、命令、JUnit、网络账本和保全清单均已持久导出。本任务临时 pytest 目录在验证、导出及校验后清理；研究证据继续保留。

## Gate 与交接

```ini
CURRENT_DECISION = FIX_ONLY
H01_FIX_VERDICT = H01_DATA_PACKAGE_READY_FOR_CONSUMER_ACCEPTANCE

ORIGINAL_1875_RAW_ROWS = PRESERVED
FUND_ACTIONS_QUALIFICATION = CONFIRMED_NO_EVENT_IN_SCOPE
EX_POST_NO_EVENT_AUDIT = PASS_NINE_OFFICIAL_REPORTS_2023_2025
HISTORICAL_INFORMATION_LEAKAGE = NOT_INTRODUCED_BY_EX_POST_NO_EVENT_AUDIT
513030_2025_01_23_STATUS = VERIFIED_FULL_DAY_SUSPENSION
SMA200_OBSERVATION_POLICY = INCLUDE_KNOWN_REPORTED_DAILY_BAR_EXISTING_CONSUMER
TOTAL_RETURN_QUALIFIED_ROWS = 1875
SIGNAL_WARMUP_QUALIFICATION = PASS_200_PRIOR_PER_ETF

OLD_TESTS = 87_PASS_ORIGINAL_TEST_IDS_UNCHANGED
NEW_TESTS = 14_PASS
CONSUMER_RECEIPT = PASS_REPAIRED_INDEPENDENT_RECEIVER_29986_CHECKS
PACKAGE_MANIFEST_SHA256 = 8d2f2400b011891f17f6e9c9e2950c6608ab12d1759044cc06e04040e02be79a

REMAINING_NAMED_GAPS = NONE_REQUIRED_FOR_THIS_H01_RESEARCH_INPUT
SIOS_H01_DATA_GATE = PASS_FOR_RESEARCH_CONSUMER_ACCEPTANCE
H01_READY_FOR_OWNER_ACCEPTANCE = YES_OWNER_ACCEPTANCE_PENDING

SIOS_H04 = DEFERRED
SIOS_P2 = DEFERRED
SIOS_EXPERIMENT_AUTHORIZED = NO
PRODUCTION_IMPLEMENTATION_AUTHORIZED = NO
GIT_COMMIT = NO
GIT_PUSH = NO
```

当前阶段为 H01 数据交付最小修复，离线调查、修复、复测及新包交付完成。chstockdata HEAD 为 `5584f5fcacccef9a9531a7a32b8463ea6771d312`，SIOS HEAD 为 `a46500441ff29c9c7807fdfef155c22cedb72b88`；两者 tracked diff 均为空且与基线一致。chstockdata 新增本报告、本轮 evidence 和新回归测试，既有未跟踪材料保留；SIOS 工作树状态与基线完全一致，仅有其原有两项未跟踪材料。完整状态见 `completion.json`；其中生产者状态是临时目录清理前的时间点快照。

本研究输入范围内没有剩余必需具名数据缺口。历史 RAW 可用时刻仍是原合同的交易所规则推定，不声称获得历史下载版本的实际观测证明；停牌公告盘前可知性仍未认证，未用于盘前信号或虚构成交。生产适配器未集成，成本、执行和更广 QDII 研究不属于此次修复。没有范围变更。建议下一步由 Owner 验收新数据包；Gate 通过不构成策略实验、H04、P2 或生产实施授权。
