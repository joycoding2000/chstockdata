# SIOS H01 优先数据交付：部分交付，提交 Owner Review

日期：2026-10-22，Asia/Shanghai。**H01_DELIVERY_VERDICT = H01_PARTIAL_DELIVERY_WITH_NAMED_GAPS**。
**SIOS_H01_DATA_GATE = BLOCKED_WITH_NAMED_GAPS**。已交付真实行情、权益核验和可复算导出；没有将事后核验升级为历史 PIT 资格。

交付：[实际 ZIP](evidence/2026-10-22-sios-h01-priority-delivery/H01-delivery.zip)、
[包内说明及复现命令](evidence/2026-10-22-sios-h01-priority-delivery/H01-delivery/README.md)、
[独立接收结果](evidence/2026-10-22-sios-h01-priority-delivery/H01-delivery/validation_report.json)。

## 已交付事实

| 项目 | 实际结果 |
| --- | --- |
| 固定证券/观察期 | 513500、513030、513520；2024-01-02 至 2025-09-30，各 425 日 |
| 独立预热 | 2023-03-09 至 2023-12-29，各 200 日；不是观察段内前 200 日 |
| RAW | 共 1,875 行；源文件 32 字节对齐，日期严格递增，必要日无缺失；保留完整三个 `.day` 文件及 SHA |
| 单位 | SH51 价格原整数 ÷1000 元/份；Volume 保留原 uint32 SHARE；Amount 保留 float32 的精确人民币元值；正成交日独立 VWAP 与 OHLC 对账通过 |
| 基金权益 | 三基金 2023、2024、2025 共九份管理人官方年报均支持无收益分配、无拆分变动；与实际 F10 `normal_empty` 交叉核验。不是因为接口空数组推断“从未分红” |
| 总回报/信号输入 | 1,875 条事后无事件指数及窗口身份；126 个观察值对应 125 个间隔，SMA200 包含当日；没有排名、选股、仓位或收益实验 |
| PIT 合格观察 | **0**。PIT 指数、126 输入、SMA200 和可得时点均为 null；不允许消费 retrospective 字段代替合格历史信号 |
| 实物规模 | ZIP 8,607,260 字节，99 个文件；含原始行情、官方原文、失败响应、提取结果、schema、manifest、独立复算工具及冻结合同副本 |

三份原始行情文件身份与旧 H01 交接一致：

| 文件 | SHA256 |
| --- | --- |
| sh513500.day | `0d5033b5ac2b2704e1e2488b75fcefcedda683af3d277ae1403849d10c5ef5b6` |
| sh513030.day | `90271330201f787c2400b88c0e0d635bb4902fcd8276cd8a360fb0e484a0b27e` |
| sh513520.day | `96a617c03c1e631a9b1ace2db2f2c99ed435d8d467f157b946454ba99f3049a3` |

管理人原文、公告日期、每份原文 SHA、PDF 页码/Word body block 定位在
`fund_actions.json`；原文在 `sources/`，结构化提取在 `extracted/`。
九份年报只作 **ex_post_fact_reconciliation**，没有把 2026 年报内容赋予历史可得时间。
真实区间无实施事件，因此事件日前后实样对账为 N/A，改用真实无事件链核验；回归使用的未来/UNKNOWN payload 明确为测试数据，不写入基金事件集。

## 四项具名必要缺口

1. `H01-513500-EVENT-ASOF`：2023-03-09 至 2025-09-30 的权益索引历史覆盖/first-known 或版本证明未取得，影响全部 425 个观察日的 126/SMA200 资格。
2. `H01-513030-EVENT-ASOF`：相同历史覆盖时序缺口，影响全部 425 日。
3. `H01-513520-EVENT-ASOF`：相同历史覆盖时序缺口，影响全部 425 日。
4. `H01-513030-2025-01-23-NO-TRADE`：该日源 OHLC 均为 1.815，量额均为 0；明确保留 `NO_TRADE_RECORDED`，没有填补或伪造交易。官方停牌原因和消费者无成交观察纳入规则未认证。影响 126 输入的日期为 2025-01-23 至 2025-08-01（126 日），影响本观察期 SMA200 的日期为 2025-01-23 至 2025-09-30（168 日）。完整逐日清单在 coverage 文件。

前三项不是具名分红金额/除息日缺失，也不声称基金存在未处理的实施事件；官方报告支持**事后零事件事实**，缺口是其历史可得覆盖认证。消费者既有 RAW `EXCHANGE_RULE` 仍保留为当日境内 15:00，抓取时间另列；没有将该规则扩展为对事后权益公告索引的认证。原始快照的 observed vintage 也诚实标为 `NOT_ATTESTED`，未新增生产版本库。

现金经济权益、实际支付、回测可用时间字段分别保留；本数据没有实施现金事件，适用状态为 `NOT_APPLICABLE_NO_IMPLEMENTED_CASH_EVENT`，不合并三个时间。当前预案/取消公告全索引未认证，不能把实施事件的正常空覆盖描述为所有公告状态完整。

这些是 `UNRESOLVED_RISK`，不是已确认的投资机制失败。不裁定所有免费来源永远不能提供历史版本；本次既有来源与有界免费核验未取得必要认证，停止扩源并提交 Owner Review。

## 连续修复、验证及 Gate

修复限于本任务离线程序：识别 PDF/OOXML 附件，拒绝伪 PDF/不明确容器；按 Word 真实段落/表格定位负面证据；日历只使用指数日期，避免被不相关的早期指数价格字段阻断。均保留真实源文件，没有改生产 Provider、公共 API 或 SIOS。

- 新增 12 项研究包回归；格式、126 观察值语义、零量额、重复/截断、九份真实报告定位、未来公告及 UNKNOWN 实际篡改包拒绝均覆盖。红/绿阶段实际执行。
- 最终定向回归 **87 passed in 6.13s**，包括已有基金公司行动、VIPDOC 单位与历史读取测试；[JUnit](evidence/2026-10-22-sios-h01-priority-delivery/focused.xml)及 stdout/stderr 已保存。新脚本 AST 解析通过；环境无可用 Ruff 二进制，未新增安装或声称 lint 通过。
- 三只基金现有 `get_fund_corporate_actions` 对捕获 F10 的离线重放均为 `normal_empty/complete`，原结果保留于 `public_api_offline_replay.json`，额外说明它不等于历史 PIT 覆盖。
- 独立接收代码不导入导出程序、不导入/执行 SIOS，完成 **24,241** 项文件身份、单位、日期、预热和 126/SMA200 复算检查，错误 **0**。
- 接收程序实际退出码 **2**：完整性与事后复算 **PASS**，消费者金融输入接收 **BLOCKED_WITH_NAMED_GAPS**。后续只靠包内文件离线重建，manifest 逐字节一致。
- 归档 CRC、归档内 manifest 身份验证通过；没有将测试 PASS 宣称为 H01 数据 Gate PASS。

| 强制验收项 | 裁决 |
| --- | --- |
| 三 ETF 观察期及预热 | RAW 完整；合格 PIT 预热仍阻断 |
| 原价、量额、身份单位 | PASS |
| 历史必要分红/份额实施事实 | 官方交叉核验 normal_empty；历史 asof 覆盖未认证 |
| 126/SMA200 兼容 | 数学及输入窗口复算 PASS；PIT 信号未合格 |
| 有限事件对账/未来信息拒绝 | 实际无事件对账和拒绝回归 PASS；真实事件转换 N/A |
| 无影响信号的必要 UNKNOWN | FAIL：上述四项 |
| 数据包/schema/manifest/SHA/命令 | PASS |
| 独立离线接收 | 已执行，BLOCKED_WITH_NAMED_GAPS |

## 网络及环境边界

Owner 在本会话明确授权 80 次 HTTP / 60,000,000 字节 / 每请求最多重试一次。
实际 **63 次，9,715,675 字节**（响应体，不含头部）；60 次传输成功、1 次初始沙箱 ProxyError、2 次重定向。相同 URL 最多两次，无隐含重试，未绕过访问限制、未付费或全市场抓取。

HTTP 200 不自动算数据成功：三次缺 type 参数的旧公告请求正文 ErrCode=4/404、两次空通用公告索引、九次伪 PDF 访问挑战均单独记录于 provenance 和完整请求账本。随后使用网页真实参数修正研究请求，并取得管理人原文；没有改生产接口。免费网络预算没有耗尽，停止原因是必要时序/无成交资格尚未证实，未无限换源。

复用既有 `.venv`，未创建新运行环境。pytest 临时文件使用本任务受控 `.h01-task-tmp`；诊断/JUnit/复现证据已导出，任务结束清理该明确拥有目录，保留源数据、研究证据和所有旧文件。

## 完整交接

```ini
CURRENT_DECISION = OWNER_REVIEW
CURRENT_PHASE = SIOS_H01_PRIORITY_DATA_DELIVERY
CURRENT_STEP = OFFLINE_PACKAGE_AND_INDEPENDENT_RECEIPT_COMPLETE_WITH_GAPS
H01_DELIVERY_VERDICT = H01_PARTIAL_DELIVERY_WITH_NAMED_GAPS
SECURITIES = 513500,513030,513520
OBSERVATION_WINDOW = 2024-01-02_TO_2025-09-30
RAW_MARKET_COVERAGE = 625_PER_ETF; 1875_TOTAL; NO_MISSING_DATES
FUND_ACTIONS_COVERAGE = NORMAL_EMPTY_VERIFIED_EX_POST; HISTORICAL_ASOF_NOT_ATTESTED
TOTAL_RETURN_SIGNAL_COVERAGE = RETROSPECTIVE_1875; QUALIFIED_PIT_0
REQUIRED_WARMUP = 200_PRIOR_OBSERVATIONS; 2023-03-09_TO_2023-12-29
PIT_AVAILABILITY_QUALIFICATION = RAW_EXCHANGE_RULE_ONLY; EVENT_ASOF_NOT_ATTESTED
DELIVERABLE_PATH = docs/audits/evidence/2026-10-22-sios-h01-priority-delivery/H01-delivery
MANIFEST_SHA256 = 68ca0d4facc72b03f4828aae1b254fbd10beec4b456d7aa1ff80cea0e89f1dd0
CONSUMER_RECEIPT_CHECK = INTEGRITY_RECOMPUTATION_PASS; ACCEPTANCE_BLOCKED; EXIT_2
UNRESOLVED_REQUIRED_GAPS = 3_EVENT_ASOF_GAPS; 513030_2025-01-23_NO_TRADE_ELIGIBILITY
NETWORK_BUDGET_USED = 63_OF_80_REQUESTS; 9715675_OF_60000000_BYTES
SIOS_H01_DATA_GATE = BLOCKED_WITH_NAMED_GAPS
SIOS_H01_STRATEGY_EXPERIMENT_AUTHORIZED = NO
SIOS_H04 = DEFERRED
SIOS_P2 = DEFERRED
PRODUCTION_IMPLEMENTATION_AUTHORIZED = NO
PRODUCT_SCOPE_CHANGED = NO
GIT_COMMIT = NO
GIT_PUSH = NO
OWNER_REVIEW_REQUIRED = YES
```

- chstockdata HEAD：`5584f5fcacccef9a9531a7a32b8463ea6771d312`，tracked diff 为空；新增仅本任务证据、测试和本报告，原有未跟踪材料保留。
- SIOS HEAD：`a46500441ff29c9c7807fdfef155c22cedb72b88`，tracked diff 为空，原有两条 untracked 状态与任务初始记录完全一致；只读检查。
- 指定 H01 合同在当前 SIOS checkout 缺失，已从既有归档提交 `d75867d3f4c297452d6ff4777aac631bb66edc8c` 恢复为包内证据，没有更改该 checkout。
- 验证报告 SHA256：`c6ebe5dc5e6d324ad72ac9f6b14ec7ff16e6fb1ef6688951a5857e030c6456c8`。
- ZIP SHA256：`18b3025a7380f4d1f7e510b41af435f08b5e8788314e1278c99c2429c4df7877`。
- 下一最小动作：Owner Review 本包、明确历史权益时序认证及该零成交观察的必要最小补证；可决定接收部分事实、授权最小修复或维持阻断。没有下一阶段、H04/P2 或策略实验授权。
