# W5-H-R6-F1：自动财务解析最小修复与历史版本回放复核

2026-10-21，Asia/Shanghai。`CURRENT_DECISION = FIX_ONLY`。仅修复离线研究脚本，使用已保存的免费官方原件；不提交、不推送。

## 1. 裁决与直接回答

**`R6_F1_VERDICT = AUTOMATED_PARTIAL_WITH_NAMED_GAPS`。** R6 已确认的跨表单位污染已被实物回归解决：万科 2024Q1 的 NP、OCF、EQ 均恢复为原表“元”，三个 10,000 倍错误全部通过；R6 原有 **24 个本期字段全部正确**。不得再由该原型缺陷推导“免费自动化应停止”或“这些值必需人工处理”。本轮遵从 Owner 撤回这项路线推论，既有 R6 归档保持原样。

在事先冻结的 **89 个字段/期间/列检查项**中，程序先根据单位、位置与列证据接受 **87 项**、拒绝 **2 项为 UNKNOWN**；独立评分确认 **87 项全部与原件真值一致，FAIL=0**。不存在先用真值剔除错数、再将剩余数值报成成功的做法：一旦有任何程序接受值不符，整个批次不得进入版本回放。

已保存目录上的版本顺序、金额差异与历史 T 选择也可程序执行：**16 个案例、46 个字段输出的来源 ID、值及 UNKNOWN 行为均通过冻结预期**。其中 7 个字段输出只是“已知账本”演示；严格检查现有目录的 39 个输出中，18 个有正向原件锚，21 个 UNKNOWN。它们均不是全市场或完整真实历史 PIT 认证。

**尚未解决两类问题。** 一是茅台 Q1 权益表跨页后改变列结构，当前规则不能证明单位继承，两个受检值仍 UNKNOWN；二是中间报告正文、独立基期原报及公告发现完整性仍有明确来源缺口。固定成功不能证明未知修订已经全部发现。没有证据证明这些缺口必须改用人工或付费来源。

## 2. 恢复、授权与冻结

读取根 AGENTS、R4/R5/R6 报告及相应证据、R6 `experiment_v1.py`、`exploratory_v2.py`、`v2_validation_failure.json`、`field_truth_and_scores.json`，以及仓库中的 Mishi R3.2 已批准范围与 DR05 历史需求。条款与内容身份见 [context_recovery.json](evidence/2026-10-21-w5h-r6-f1/context_recovery.json)。

S07 仍为首发必交，历史目标仍是近约一交易年度另含规则预热和财务基期、当时真实证券池、当时已披露版本。**PE/ROE 计算定义与公告日期到可用时点政策未由本轮冻结**；没有计算估值、ROE 或策略回测，也没有改变金融股适用范围。

工作基线为 `main / 975a75f6717e1d8a3bd39fe34b3096d917b80066`。开始时记录 **977 个 tracked 文件**的内容 SHA 和既有未跟踪状态，见 [before.json](evidence/2026-10-21-w5h-r6-f1/before.json)。既有 V1、V2、首次结果及三项失败证据均未改写。

输入冻结见 [dataset.json](evidence/2026-10-21-w5h-r6-f1/dataset.json)、[expected.json](evidence/2026-10-21-w5h-r6-f1/expected.json)、[freeze.json](evidence/2026-10-21-w5h-r6-f1/freeze.json)：

- 六只既有证券，**18 份 PDF：14 份定期报告、4 份通知/审核/监管材料**；没有新增证券、下载或网络请求。
- R5 的 75 个已核字段出现位置；中南 FY2022 原版/更新版 6 项；康美 FY2017 原值/后续调整值 6 项；工行集团/本行 OCF 2 项，合计 **89**。比较列出现位置不等于独立原版数量。
- 真值取自旧轮已核物理页和列，本轮再核关键原件；真值与解析器分离。没有独立真人签核，也没有将这些已知案例称为全市场盲测。
- 回放先冻结 16 个案例的状态与来源 ID，再从冻结的原件真值生成独立数值预期；均保留 SHA，见 [replay_expected.json](evidence/2026-10-21-w5h-r6-f1/replay_expected.json)、[replay_value_truth.json](evidence/2026-10-21-w5h-r6-f1/replay_value_truth.json)。

## 3. 缺陷复现及最小修复

[test_legacy_units.py](evidence/2026-10-21-w5h-r6-f1/test_legacy_units.py)调用未改动的旧提取函数，重现 V2 的两物理页拼接方式，三个断言全部失败，见 [red_legacy.txt](evidence/2026-10-21-w5h-r6-f1/red_legacy.txt)。旧结果没有覆盖。

新脚本 [parser_f1.py](evidence/2026-10-21-w5h-r6-f1/parser_f1.py)使用环境已有 **pdfplumber 0.11.9** 的物理表格、单元格和文字坐标；pypdf 6.10.0 用于独立文件页数账本。使用已有 bundled Python 3.12.14，没有安装依赖或修改 `pyproject.toml`。

| 已确认问题 | 修复及拒绝规则 | 实测证据 |
| --- | --- | --- |
| 下一页万元污染前表元 | 单位只取本字段标签，或本表之前且上一表之后的单位行；不向后搜索 | 万科三个字段倍率均为 1；下页万元表不参与 |
| 标签换行与扣非/每股混淆 | 在真实单元格/同一财务行内重组标签；使用完整别名；不匹配扣非或每股净资产 | 中南原/更新版 EQ、宁德跨页 EQ 均读出 |
| 调整前后方向及期末/期初 | 根据单元格横向覆盖读取日期、相对期间、调整前/后；列身份无法定位则 UNKNOWN | 万科“前→后”、茅台/康美“后→前”、银行前后列均有正确身份 |
| 括号负数 | Decimal 解析括号及常见负号，空白/横杠不填零 | 万科 NP/OCF 为负，康美 OCF 原正后负 |
| 无框银行表及集团/本行 | 增加有界的位置分支；要求年份、数值列对齐及明确主体分组 | 工行百万元、集团与本行 OCF 分别认证 |
| 跨页延续 | 必须相邻页、前表到页尾、后表在页首、左右/列边界对齐、没有新章节；保存连续性证据 | 万科年报 EQ、宁德 Q1 EQ、康美原报 EQ；茅台结构变化时拒绝 |
| 同原件不同展示精度 | 仅在同 PDF、同字段/期间/列的两个直接值按各自披露精度相容时保留更精确原值；不计算替代数字 | 万科 OCF 元表与万元舍入表相容；越界差异仍报冲突 |

每个成功值保留原标签、原始金额文本、物理页、单元格/表格位置、单位原文与页、倍率、期间、列、合并口径、公告日期/ID、文件 SHA。年度流量标记全年累计；Q1 标记 YTD 且恰等于单季；权益标记期末时点。没有将年报分季度表误充全年，也没有推导未取得的 Q2/Q3 单季值。

**解析运行不读取 `expected.json`。** [run_parse.py](evidence/2026-10-21-w5h-r6-f1/run_parse.py)只提供 PDF 和来源身份，运行前后解析源码 SHA 一致。[validate_values.py](evidence/2026-10-21-w5h-r6-f1/validate_values.py)才读取独立预期：对冻结查询先产生程序接受/UNKNOWN 决定，再评分；全部被接受值正确后，才输出不含预期金额的 [certified_facts.json](evidence/2026-10-21-w5h-r6-f1/certified_facts.json)。额外原始候选没有因此取得认证，所有记录的完整 PIT 资格均保持 false。

## 4. 数值回归完整分母

逐项原字段、原数/倍率、实际结果、独立真值、PASS/FAIL/UNKNOWN 及原因见 [value_validation.json](evidence/2026-10-21-w5h-r6-f1/value_validation.json)。下表不把通知算作三字段缺失财报。

| 原件/公告 ID | 受检项 | PASS | FAIL | UNKNOWN |
| --- | ---: | ---: | ---: | ---: |
| 茅台 FY2023 / 1219506510 | 9 | 9 | 0 | 0 |
| 茅台 2024Q1 / 1219875828 | 6 | 4 | 0 | 2 |
| 万科 FY2023 / 1219487237 | 9 | 9 | 0 | 0 |
| 万科 2024Q1 / 1219913619 | 6 | 6 | 0 | 0 |
| 宁德 FY2023 / 1219313047 | 9 | 9 | 0 | 0 |
| 宁德 2024Q1 / 1219619642 | 6 | 6 | 0 | 0 |
| 工行 FY2023 / 1219429144 | 9 | 9 | 0 | 0 |
| 工行 2024Q1 / 1219922891，含集团/本行额外两项 | 8 | 8 | 0 | 0 |
| 中南 FY2023 / 1219747877 | 9 | 9 | 0 | 0 |
| 中南 2024Q1 / 1219909136 | 6 | 6 | 0 | 0 |
| 中南 FY2022 原版 / 1216561621 | 3 | 3 | 0 | 0 |
| 中南 FY2022 更新版 / 1217386817 | 3 | 3 | 0 | 0 |
| 康美 FY2017 原报 / 1204793690 | 3 | 3 | 0 | 0 |
| 康美后续年报的 FY2017 调整列 / 1206168292 | 3 | 3 | 0 | 0 |
| **合计** | **89** | **87** | **0** | **2** |

分层计数：R5 本期 29/30 正确、比较位置 44/45 正确；R6 两份新增年度原件 6/6；康美正向原件版本 6/6；银行主体附加 2/2。R6 原有八份定期报告的 24 个本期字段，现为 **24/24 正确**，不把本轮 89 项全部说成 89 个独立财务版本。

万科已知三错误的修复结果，人民币元：

| 字段 | 新程序直接值＝独立原件 | 旧 V2 直接输出 |
| --- | ---: | ---: |
| NP | -361,967,511.52 | -3,619,675,115,200.00 |
| OCF | -9,421,419,428.01 | -94,214,194,280,100.00 |
| EQ | 250,633,266,316.32 | 2,506,332,663,163,200.00 |

宁德万元与工行百万元分别保留 10,000/1,000,000 倍率及原披露精度。工行 Q1 OCF 集团为 **1,367,252 百万元**、本行为 **1,166,485 百万元**，未混配。康美 OCF 原报 **+1,842,794,237.84 元**、后续 2017 调整列 **-4,840,052,606.46 元**，没有取错 2018 当前列。

**两项 UNKNOWN 的具体原因：** 茅台 Q1 物理第 1 页流量表为三列，第 2 页权益表为四列；本页权益表没有重述单位。现有连续性要求不允许跨这种列结构变化继承单位；后续完整资产负债表的“归属于母公司所有者权益（或股东权益）合计”也尚未纳入现有别名。因此，239,731,785,910.55 与 215,668,571,607.43 只保留为独立真值，程序没有用它们补 UNKNOWN。这是明确、可继续修复的局部程序缺口，不能据此判定必须人工抄数。

R5 的“比较列原样”没有区分调整身份时，评分同时检查程序匹配到的前/后列；只有一致才可归为该泛称比较项，不会选择恰好符合预期的一列。宁德受检比较金额相等，EPS 调整没有被扩张为 NP/OCF/EQ 修订。

## 5. 自动版本重建的有限复核

[version_f1.py](evidence/2026-10-21-w5h-r6-f1/version_f1.py)复用已保存的六证券目录，去重得到 **85 个公告身份**，18 份实物的发行人/ID/日期与目录逐项对应。目录仍是旧轮过滤查询的快照，不能作为全部公告集合。解析数值资格通过后生成 **67 条**用于有界回放的已核事实，见 [version_evidence.json](evidence/2026-10-21-w5h-r6-f1/version_evidence.json)。

程序将以下情况分开输出：

1. **同期间文档更新：** 中南 FY2022 原版→更新版按发行人、期间、日期排序，SHA 不同，NP/OCF/EQ 三金额全相等。补充件正文命中“处罚及整改/其他内容不变”的限定叙述，不创建新金额事件。
2. **普通年报比较列金额变化：** R5 五份年报的 15 个前后比较，识别 **8 个金额差异**，分布在茅台、万科、工行、中南的 NP/EQ；宁德三金额相等。发现条件不依赖“更正”标题。R6 特指的中南/万科两报告合计四个变化字段包含其中。
3. **跨文档正向版本：** 自动比较中南更新版与后续年报的 FY2022 列，以及康美原年报与后续年报的 FY2017 列；得到中南两项变化、康美三项变化。这与同页前后比较有重叠，不能相加为总体修订发生率，也不证明最早调整日。
4. **通知与扫描件：** 万科更正被标为治理内容候选、无目标金额替换；这不是通用的自动语义清除器。康美审核扫描件 11 页无文本，返回 `UNKNOWN_NO_TEXT_LAYER`；监管函影响范围仍 UNKNOWN，不生成金额。本轮目标数值已有正式年报文本作为可验证替代，因此未开发 OCR，也不将扫描分支解释为免费自动化总体阻断。

历史 T 继续采用 R4/R6 的**候选**政策：日期级公告在下一观察到的上证指数交易日收盘可用，日历只复用本地旧文件。没有将今天抓取时间、PDF 创建时间或目录午夜编码当历史首发钟点。完整日历与时序产品合同未认证。

| 历史案例 | 程序结果 | 限定含义 |
| --- | --- | --- |
| 康美 FY2017：2018-04-24 / 04-27 / 2019-05-06 | 未披露 UNKNOWN → 原版三值 → 调整三值，OCF 变负 | 只有已知原件与日期的有限回放；完整链未知 |
| 中南 FY2022：2023-04-24 / 04-26 | UNKNOWN → 原版三值 | 无未来回填 |
| 同上：2023-07-27 | 已知账本演示保留更新版相同三值；严格检查 UNKNOWN | 2023Q1 正文缺失，全文更新不能证明中间未改变基期 |
| 同上：2024-04-23 / 04-24 | 新年报尚不可用时 UNKNOWN；次日选 FY2023 中的调整列 | 不将新年报日倒推为首次调整日 |
| 万科 FY2022：2023-04-26 / 2024-04-01 | 独立原报缺失 UNKNOWN → 后续正式比较列 | 后续“调整前”列不会倒签为独立原报 |
| 万科 FY2023：更正前后 | 已知账本 NP/OCF 不变；严格 2024-10-08 UNKNOWN | 无关治理通知不覆盖金额，但已知缺失半年报不能被忽略 |
| 宁德 FY2022：2024-03-15 / 03-18 | UNKNOWN → 后续年报已披露金额比较列 | EPS 重算不产生三金额变化 |

[replay_validation.json](evidence/2026-10-21-w5h-r6-f1/replay_validation.json)保存全部 **46/46** 状态、来源及数值断言。**39 个严格字段输出＝18 个正向选择＋21 个 UNKNOWN**；另 7 个已知账本字段输出不计真实历史合格。21 个 UNKNOWN 分为 12 个无可用原报/版本、9 个已知中间报告缺口。本轮比 R6 更明确地拒绝忽略万科 2024 半年报，不沿用旧演示作全历史放行。

具名中间缺口：中南 `1216696970`（2023Q1）、`1217710575`（2023 半年）、`1218204096`（2023Q3）；万科 `1221084198`（2024 半年）。万科 FY2022 独立原报也未取得。没有为闭合它们追加下载；其他基期、全年度覆盖仍未认证。

## 6. 质量检查与实际工作账本

[test_parser.py](evidence/2026-10-21-w5h-r6-f1/test_parser.py)、[test_versions.py](evidence/2026-10-21-w5h-r6-f1/test_versions.py)的 **15 项测试通过**；包括单位不向后借用、未知/冲突拒绝、期末/期初、显式母公司、跨页不连续拒绝、负号、其他主体/期间不混入、未来版本排除、缺原版/中间件拒绝、同一时点来源冲突拒绝。合成冲突均使用 `TEST_ONLY` 身份，不冒充实际观察到的来源冲突。

[quality_checks.json](evidence/2026-10-21-w5h-r6-f1/quality_checks.json)的 **91 项实际输出检查全部通过**。87 个成功值的原文、倍率、单位来源页、金额、范围和 SHA 可追溯；两个未知值没有认证。真实同版本来源冲突未观察到；万科不同精度表达按原披露精度相容处理，不掩盖真正冲突。

另直接读取 R5 中南 THS 三张原响应：FY2022 的 NP/EQ 与 F1 自动读出的原版仍有两项差异；OCF 相同。**三行都因缺独立公告/版本绑定而拒绝作为历史原版**，没有用“金额相同”认证 OCF 的版本，更没有让今日 NP/EQ 覆盖早期 T。这是实际旧版本反例；不把不同版本差异误报成同一版本源冲突。

七张关键物理页重新渲染并由 Agent 目视核对，见 [render_log.json](evidence/2026-10-21-w5h-r6-f1/render_log.json)、[visual_qa.json](evidence/2026-10-21-w5h-r6-f1/visual_qa.json)。没有真人独立签核，也没有向解析器录入正确金额。

实物及耗时完整账本见 [cost_ledger.json](evidence/2026-10-21-w5h-r6-f1/cost_ledger.json)：

| 成本类别 | 实际观测 | 不能推导的结论 |
| --- | --- | --- |
| 复用原件 | 18 份、70,396,140 B、2,500 页；SHA 全核 | 不代表全部原件已按页自动理解 |
| 本轮下载/重试 | 0 请求、0 B、0 秒、0 重试 | 未测源端本轮网络成本或容量 |
| 最终数值解析 | 14 定期报告，最多各前 30 页，共 337 页文本/位置处理；**68.572 秒** | 不外推全市场成功率或生产吞吐 |
| 通知范围筛查 | 4 文件、16 页，包含 11 页无文本扫描件；计入版本脚本进程 | 不声称 OCR 完成 |
| 最终校验进程墙钟 | 数值评分 0.134 秒；版本及回放评分 0.820 秒；实际质量检查 0.141 秒；安全测试 0.227 秒 | 含启动/文件读写，不作纯算法 CPU 或人时 |
| 调试成本 | 首次修复试验 66.860 秒；另有有界诊断/重新运行，首次 70 PASS/19 UNKNOWN 与原始 V2 失败均保存 | 不把最终 68.572 秒当全部研发成本；未测完整人类劳动 |
| 人工 | 数值手工修补 0；参考真值有旧轮及本轮 Agent 辅助定位/目视核验 | 独立真人复核耗时 `NOT_MEASURED`，不能据此计算必须人工比例 |

本轮没有估计全市场错误率、人工比例、整年交付总成本；六证券已知案例不具备这类推断能力。原始候选 **169 个**，只有冻结查询受检值取得局部资格，其余不自动认证。

## 7. 程序化免费路线的能力边界

**已实证具备：** 在固定已取得原件中，以位置和单位作用域自动读取必要数值，保存可追溯列身份；识别本轮已知的普通比较列变化与同期间无金额变化更新；在正向版本证据和候选日期政策下选择历史值，并对已知缺口拒绝。已确认单位缺陷的修复成本可由实际脚本与耗时复核，不能再把该缺陷算成必须人工处理的证据。

**仍未具备：** 所有已存格式全部自动认证、扫描正文自动读取、任意通知的语义清除、未知公告/修订完整发现、各期首次可知链、完整财务基期和一年全市场 PIT。尤其 UNKNOWN_REVISION_RECALL 不能随单位修复改成 PASS。Mishi 的历史证券池、行业、估值、成交状态等资格也未由本轮取得。

| 分类 | 事实与下一步边界 |
| --- | --- |
| CONFIRMED_DEFECT | 旧 V2 三金额串用单位，已修复；茅台 Q1 列结构变化/替代权益别名尚未覆盖，两个 UNKNOWN |
| UNRESOLVED_RISK | 有界目录之外的发现完整性、具名中间正文、独立原报、首次可知、扫描/其他格式、未知市场错误率 |
| SPECULATIVE_CONCERN | “免费自动化不可能”“所有异常必须人工”“必须转向付费”“六样本通过即可供给全市场”均未成立 |
| FUTURE_ENHANCEMENT | 通用财报平台、OCR 框架、数据库、Provider、生产或消费者实施均未授权 |

**推荐路线：继续保留免费、程序化、正向原件版本绑定路线。** 普通结构化数字只能在原件版本锚下辅助核对，不能直接回填过去。本轮没有付费服务比较、采购或接入，也没有新许可专项；免费访问本身仍不等于商业分发许可。

**下一最小动作：Owner 审阅本次局部资格与剩余缺口。** 若另行授权继续，只先验证已有茅台权益表的局部连续性/别名修复；需验证历史链时，限定到已列明的中间正文及其目标比较字段。不得默认扩大证券池、全市场抓取或建立平台，也不宣称下一阶段已获授权。

## 8. 复核方式与交接

以下命令使用本任务环境已有 bundled Python；按顺序运行，全部输出限定在本证据目录。旧缺陷复现另行运行 `test_legacy_units.py`，预期为三个 FAIL；它不纳入修复后正常测试集合。

```powershell
$py = 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$ev = 'D:\Dev\Projects\chstockdata\docs\audits\evidence\2026-10-21-w5h-r6-f1'
Push-Location $ev
& $py -X utf8 -B run_parse.py
& $py -X utf8 -B -m unittest test_parser test_versions
& $py -X utf8 -B validate_values.py
& $py -X utf8 -B version_f1.py
& $py -X utf8 -B check_quality.py
& $py -X utf8 -B summarize_cost.py
Pop-Location
```

执行结果见 [validation_runs.json](evidence/2026-10-21-w5h-r6-f1/validation_runs.json)，保护与交付终检见 [final_verification.json](evidence/2026-10-21-w5h-r6-f1/final_verification.json)，产物身份见 [manifest.json](evidence/2026-10-21-w5h-r6-f1/manifest.json)。没有运行生产测试、消费者测试、策略回测或发布 Gate。

- 阶段/步骤：W5-H-R6-F1 离线最小修复及有界复核完成，等待 Owner Review。
- Commit/工作树：HEAD 保持 `975a75f6717e1d8a3bd39fe34b3096d917b80066`；仅新增本文及 F1 evidence，原有 tracked 内容和未跟踪研究保留；无暂存、commit、push。
- Gate/证据：89 项中 87 正确、2 UNKNOWN；已知三错误及 R6 24 本期字段通过；46 个回放断言、15 安全测试、91 实际质量检查通过。完整 S07 历史 Gate 仍 **NOT_PASSED**。
- 未解/范围：两权益项程序缺口、具名来源缺失及未知召回；产品、合同、runtime、消费者、架构无变化。
- 推荐动作：Owner 审阅后再裁决上述一个局部修复或具名来源验证；不自动进入生产或下一调查。

```ini
CURRENT_DECISION = FIX_ONLY
R6_F1_VERDICT = AUTOMATED_PARTIAL_WITH_NAMED_GAPS
DATA_SOURCE_POLICY = FREE_ONLY
PAID_PROVIDER = PROHIBITED

V2_UNIT_CONTAMINATION = FIXED_3_OF_3_KNOWN_ERRORS; R6_CURRENT_FIELDS_24_OF_24_CORRECT
CROSS_PAGE_TABLE_BOUNDARY = VERIFIED_ADJACENCY_ALIGNMENT_NO_NEW_SECTION; CHANGED_STRUCTURE_FAILS_CLOSED
UNIT_SCOPE_VALIDATION = LOCAL_FIELD_OR_TABLE_ONLY; NO_FOLLOWING_TABLE_UNIT_INHERITANCE
FIELD_AND_COLUMN_IDENTITY = VERIFIED_FOR_87_ACCEPTED_FIXED_CHECKS; 2_EQ_CHECKS_UNKNOWN

AUTOMATED_VALUE_CORRECTNESS = 87_PASS_0_FAIL_2_UNKNOWN_OF_89; ZERO_INCORRECT_PROGRAM_ACCEPTED_VALUES
UNKNOWN_FAIL_CLOSED = VERIFIED_VALUE_COLUMN_SOURCE_VERSION_AND_INTERVENING_REPORT_BRANCHES
FIXED_CASE_VERSION_SELECTION = 46_OF_46_ASSERTIONS_PASS; 18_STRICT_POSITIVE_21_STRICT_UNKNOWN_7_KNOWN_LEDGER_ONLY
UNKNOWN_REVISION_RECALL = NOT_ESTABLISHED

REMAINING_PARSER_DEFECTS = MOUTAI_Q1_CHANGED_COLUMN_CONTINUITY_AND_ALTERNATIVE_EQ_LABEL; NOTICE_SEMANTICS_AND_SCAN_AUTOMATION_NOT_QUALIFIED
REMAINING_SOURCE_GAPS = NAMED_INTERVENING_REPORTS; INDEPENDENT_BASE_ORIGINALS; COMPLETE_DISCOVERY_AND_FIRST_AVAILABILITY
AUTOMATED_QUALIFICATION = FIXED_VALUES_AND_BOUNDED_REPLAY_PARTIAL; NOT_FULL_HISTORICAL_PIT
HUMAN_REVIEW_REQUIRED_BY_EVIDENCE = OWNER_REVIEW_YES; MANDATORY_FIELD_BY_FIELD_HUMAN_SHARE_NOT_ESTABLISHED

MISHI_S07_HISTORICAL_GATE = NOT_PASSED
PRODUCTION_IMPLEMENTATION_AUTHORIZED = NO
PRODUCT_SCOPE_CHANGED = NO
GIT_COMMIT = NO
GIT_PUSH = NO
OWNER_REVIEW_REQUIRED = YES
```
