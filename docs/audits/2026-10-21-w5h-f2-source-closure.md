# W5-H-F2 Source Closure：剩余官方原件资格闭环

裁决：**SOURCE_CLOSED_WITH_NAMED_UNKNOWN**。固定 23 份候选均已取得并检查；12 份可解除本集合的阻断或区分会计基准，11 份仍有具名认证缺口。下载完成不能替代版本资格通过。

本轮保留免费程序化路线，连续修复实际期间、列、开放边框和跨页行缺陷。新增已证实的金额修订事件为 0；扫描表及六份回复的 OCF 主体身份仍未认证。这些是当前有限规则的具体缺口，不能推导为免费自动化不可行、必须人工或必须付费。

## 授权与基线

- CURRENT_DECISION=CONTINUE；本轮是 F2 工作包的受控延续。HEAD/main 为 92d85ef7edc10a7663cce329589c5a0c8eb4bebd，没有 commit/push。
- 已恢复 AGENTS、Mishi R3.2、DR05、R4/R5/R6/F1/F2、F2 索引/分类/事件/账本/测试及预算记录。输入 SHA 见本目录 authority_inputs.json。
- 网络身份唯一取自既存 F2 索引。六个证券历史窗和必要财务基期未变，没有新增证券、日期窗或元数据发现。
- A/B/C 优先级在任何新请求前冻结，见 preregistration.json。获取前 23 份均没有足以排除正文的证据；按原序访问，没有依结果改序或换样本。
- 原归档及全部 1,304 个已跟踪文件按开始时 SHA 复核；原 62 条未跟踪状态保留。详见 final_integrity.json。仅新增本报告和本轮 evidence。
- 使用既有 Python、pdfplumber/pypdf/Pillow 和系统 Windows.Media.Ocr 中文/英文引擎；未安装环境、生产依赖或 Provider。未创建临时 venv。原件、OCR 图像与测量底稿作为持久证据保存。

下文 evidence 文件均位于：
D:/Dev/Projects/chstockdata/docs/audits/evidence/2026-10-21-w5h-f2-source-closure/

## 完整文件分母

互斥结论：NEW_VERIFIED_VERSION_FACT=0，VERIFIED_DUPLICATE_OF_EXISTING_DISCLOSURE=8，VERIFIED_NO_TARGET_FIELD_EFFECT=3，DIFFERENT_ACCOUNTING_BASIS=1，UNRESOLVED_REQUIRES_EVIDENCE=11，合计23。

“重复”仅覆盖实际披露且完成比较的目标事实；不是整份 PDF、所有期间或所有版本完全等价。没有披露的 EQ 不由比率倒算。数字相等不替代主体、期间、单位及版本依据。粗精度旁证也不能排除小于其披露精度的修订，不能据此认证完整修订召回。source_qualification.json 保存各项来源页、实际金额、单位、引用身份与 SHA。

| 证券 | 公告 ID / 原件 | 公告日 | 页数 | PDF 字节 | 结论 | 实际比较字段 |
|---|---|---|---:|---:|---|---|
| 000961 | [1216741269](D:/Dev/Projects/chstockdata/docs/audits/evidence/2026-10-21-w5h-f2-source-closure/originals/1216741269.pdf) | 2023-05-04 | 214 | 7,724,169 | UNKNOWN | NP/OCF/EQ |
| 000961 | [1216814161](D:/Dev/Projects/chstockdata/docs/audits/evidence/2026-10-21-w5h-f2-source-closure/originals/1216814161.pdf) | 2023-05-15 | 81 | 3,941,629 | 重复目标事实 | NP/OCF |
| 000002 | [1216869640](D:/Dev/Projects/chstockdata/docs/audits/evidence/2026-10-21-w5h-f2-source-closure/originals/1216869640.pdf) | 2023-05-22 | 208 | 12,381,989 | UNKNOWN | NP/OCF/EQ |
| 000961 | [1217078313](D:/Dev/Projects/chstockdata/docs/audits/evidence/2026-10-21-w5h-f2-source-closure/originals/1217078313.pdf) | 2023-06-16 | 214 | 9,100,462 | UNKNOWN | NP/OCF/EQ |
| 000961 | [1217949874](D:/Dev/Projects/chstockdata/docs/audits/evidence/2026-10-21-w5h-f2-source-closure/originals/1217949874.pdf) | 2023-09-26 | 218 | 15,852,778 | UNKNOWN | NP/OCF/EQ |
| 000961 | [1216741271](D:/Dev/Projects/chstockdata/docs/audits/evidence/2026-10-21-w5h-f2-source-closure/originals/1216741271.pdf) | 2023-05-04 | 81 | 4,494,304 | 重复目标事实 | NP/OCF |
| 000002 | [1216869636](D:/Dev/Projects/chstockdata/docs/audits/evidence/2026-10-21-w5h-f2-source-closure/originals/1216869636.pdf) | 2023-05-22 | 304 | 6,919,814 | 重复目标事实 | NP/OCF |
| 000961 | [1217078318](D:/Dev/Projects/chstockdata/docs/audits/evidence/2026-10-21-w5h-f2-source-closure/originals/1217078318.pdf) | 2023-06-16 | 83 | 3,738,354 | 重复目标事实 | NP/OCF |
| 000961 | [1217949875](D:/Dev/Projects/chstockdata/docs/audits/evidence/2026-10-21-w5h-f2-source-closure/originals/1217949875.pdf) | 2023-09-26 | 82 | 4,144,145 | 重复目标事实 | NP/OCF |
| 600518 | [1205169602](D:/Dev/Projects/chstockdata/docs/audits/evidence/2026-10-21-w5h-f2-source-closure/originals/1205169602.pdf) | 2018-07-17 | 202 | 5,470,591 | 重复目标事实 | NP/OCF/EQ |
| 600518 | [1205465511](D:/Dev/Projects/chstockdata/docs/audits/evidence/2026-10-21-w5h-f2-source-closure/originals/1205465511.pdf) | 2018-09-26 | 201 | 5,792,786 | 重复目标事实 | NP/OCF/EQ |
| 000961 | [1216741268](D:/Dev/Projects/chstockdata/docs/audits/evidence/2026-10-21-w5h-f2-source-closure/originals/1216741268.pdf) | 2023-05-04 | 141 | 2,578,479 | UNKNOWN | NP/OCF |
| 000961 | [1216741273](D:/Dev/Projects/chstockdata/docs/audits/evidence/2026-10-21-w5h-f2-source-closure/originals/1216741273.pdf) | 2023-05-04 | 109 | 1,446,302 | UNKNOWN | NP/OCF |
| 000961 | [1217078312](D:/Dev/Projects/chstockdata/docs/audits/evidence/2026-10-21-w5h-f2-source-closure/originals/1217078312.pdf) | 2023-06-16 | 122 | 1,668,977 | UNKNOWN | NP/OCF |
| 000961 | [1217078316](D:/Dev/Projects/chstockdata/docs/audits/evidence/2026-10-21-w5h-f2-source-closure/originals/1217078316.pdf) | 2023-06-16 | 176 | 2,638,788 | UNKNOWN | NP/OCF |
| 000961 | [1217170564](D:/Dev/Projects/chstockdata/docs/audits/evidence/2026-10-21-w5h-f2-source-closure/originals/1217170564.pdf) | 2023-06-30 | 20 | 796,736 | 无目标字段影响 | 无目标金额 |
| 000961 | [1217170566](D:/Dev/Projects/chstockdata/docs/audits/evidence/2026-10-21-w5h-f2-source-closure/originals/1217170566.pdf) | 2023-06-30 | 22 | 1,270,048 | 无目标字段影响 | 无目标金额 |
| 000002 | [1217321905](D:/Dev/Projects/chstockdata/docs/audits/evidence/2026-10-21-w5h-f2-source-closure/originals/1217321905.pdf) | 2023-07-19 | 322 | 9,301,301 | 不同会计基准 | NP/OCF/EQ |
| 000961 | [1217361564](D:/Dev/Projects/chstockdata/docs/audits/evidence/2026-10-21-w5h-f2-source-closure/originals/1217361564.pdf) | 2023-07-22 | 23 | 1,035,810 | 重复目标事实 | NP/OCF |
| 000961 | [1217949872](D:/Dev/Projects/chstockdata/docs/audits/evidence/2026-10-21-w5h-f2-source-closure/originals/1217949872.pdf) | 2023-09-26 | 133 | 1,898,579 | UNKNOWN | NP/OCF |
| 000961 | [1217949876](D:/Dev/Projects/chstockdata/docs/audits/evidence/2026-10-21-w5h-f2-source-closure/originals/1217949876.pdf) | 2023-09-26 | 194 | 2,660,112 | UNKNOWN | NP/OCF |
| 000961 | [1218110511](D:/Dev/Projects/chstockdata/docs/audits/evidence/2026-10-21-w5h-f2-source-closure/originals/1218110511.pdf) | 2023-10-21 | 22 | 4,693,844 | UNKNOWN | NP/OCF/EQ |
| 000961 | [1218110512](D:/Dev/Projects/chstockdata/docs/audits/evidence/2026-10-21-w5h-f2-source-closure/originals/1218110512.pdf) | 2023-10-21 | 24 | 1,299,578 | 无目标字段影响 | 无目标金额 |

## 版本依据与例外

**康美两份债券募集书。** 1205169602 p118、1205465511 p117 明确给出 FY2017 审计身份“广会审字[2018]G17034190036”，区分合并和母公司报表。FY2017 合并 NP 4,100,926,148.57 元、OCF +1,842,794,237.84 元、EQ 32,032,959,807.76 元均与原报1204793690一致。母公司现金流及增幅列单独排除。募集书只在各自公告日以后可见，不倒签到原报前；2019修订数不覆盖2018当时公开的原报。匹配对象是当时原件所载值，并不声称它们是事后查明的真实经营数。

**万科后发材料不构成 EQ 回退。** 1217321905 p154 明确说明财务分析采用各审计年度“当期期末”数据，并列出 FY2022 审计号2302617。p156 的 EQ 24,269,134.22万元与原审计数242,691,342,204.55元按印刷精度一致；此前1216686497已披露调整后比较列243,325,374,922.33元。程序保留原审计引用身份，不因募集书公告较晚而覆回旧数。p162母公司OCF -1,996,053.18万元也不进入合并账本。1216869636 p35/p95的NP/OCF及p117的审计引用形成另一组有限旁证；不从财务投资比率反推EQ。

**中南募集书与年报回复。** 四份募集书按照各自“报告期”定义比较FY2022 NP/OCF；“财务数据更新”“半年报更新”的标题没有被当成金额修订。1217361564 p2明确引用110A014431审计，NP -91.71亿元及p6 OCF 62.53亿元与原报在粗精度范围内一致。亿元、原文与精度均保留，没有替换成原报更精细数值；这些段落没有提供目标EQ。

**三份第二轮回复可排除目标影响。** 1217170564、1217170566、1218110512完整正文围绕同一问题1：债务重组、预售资金使用、教育投资及产业政策；目录、核查结论和尾页一起核验。十月公司回复的三个图像尾页为签章或法定代表人声明，没有目标金额替换。全扫描配套审计回复1218110511没有因共享问询号而被自动宣布等价。

**真实源内差异保持显式。** 六份首轮公司/会计师回复的文字把FY2021 OCF列为1,677,198.08万元，而同组表格/募集书为1,677,198.05万元，相差300元。位置为1216741268 p53、1216741273 p28、1217078312 p38、1217078316 p64、1217949872 p43、1217949876 p73。未静默修正，也未把这种差异认证为历史重述。FY2022 OCF数值对得上原报，不代替主体身份和源内差异的独立处理。

## 连续修复与金额认证

所有扩展均在本轮离线 evidence 内；未改归档脚本、runtime、消费者或冻结合同。解析器没有证券代码、公告ID或预期金额修补表，也不读取真值文件。

1. 严格区分2023年1-3月和完整日期，消除误读为2023-01-03。
2. 按同一表格行的物理y范围补读开放的左右边缘，仍要求显式日期列头；修复六份回复的NP漏读。
3. 日期组下面的增幅/同比子列不作为金额；修复把22.77、21.17百分比误当万元的候选错误。
4. 只有明确的上一页末母公司现金流表标题及单位，与相邻页首表连续时才延续身份；万科p162保持母公司口径。
5. 显式年度序列在同一句内绑定期间与金额，不跨页猜接募集书季度现金流。保留元/万元/百万元/亿元、印刷精度、年度/Q1累计与单季等价/H1累计/期末身份；期初标签不混成期末。
6. 修复目标页预筛跨行漏检。1217078312的金额在p97，“净额”标签在p98。只有相邻、页底/页首位置与列边界连续且有真实标签尾部时才拼标签；金额和单位仍来自p97，不继承下一张无关表格单位。
7. 同日未认证配套候选仍阻断对应字段；“已取得文件”和“字段已认证”分开。相应合成安全断言明确标为测试数据。

最终 **176条候选记录**：62条获得主体/期间/单位及前序已认证原件的精度内旁证；12条母公司口径排除；34条主体UNKNOWN；68条无本轮独立认证，不接受。包含重复位置及非目标旧期间，不能当作176个独立金融样本。

另外冻结的 **24项原件字段检查：22 PASS、2 UNKNOWN、0 FAIL**。两个UNKNOWN为1216741273 p88、1217078312 p97的FY2022 OCF：数值/单位可读，当前规则未证实合并主体身份，不认证。source_value_validation.json逐项保存真值、原文、实际金额/单位/倍率、页与状态。这不是24项金额全部通过，也不是全市场盲测。

四份财务包和全扫描审计回复已尝试系统OCR：152张物理页各中文/英文识别一次，另对一份包的四页执行24个放大条带探针。图像SHA、原文、坐标和引擎耗时均保留。OCR非空、审计号相同或恒等式相容均不构成金额正确性的充分证据；没有从这些OCR输出认证货币事实。

## 历史版本回放

source_aware_ledger.json保留原有 **127条认证事实**，旁列62条前序事实旁证及未认证候选。新增可认证金额修订0，因此没有把原审计引用或四舍五入误差写成新修订，也没有人为移动旧日期。0不证明未知修订不存在，更不证明F2所见日期是最早公开日期。

保留原118个查询，新增23项时序断言，合计141个输出：**84 SELECTED_KNOWN_SOURCE、57 UNKNOWN**；新增断言23/23通过。原查询只有f2-115变化：康美FY2017 OCF在2018-07-18，经债券正文核验解除UNKNOWN，选择原报+1,842,794,237.84元。其余旧查询状态/金额不变。

- 首次原报前UNKNOWN；康美修订前正OCF、2019修订后负OCF及FY2018 Q1比较期分别回放。
- 万科2023-07-20的known-documents演示保留Q1调整后EQ；strict仍因5月22日扫描财务包UNKNOWN。8月31日原件的正向比较列锚点以后可选已证实值。
- 中南5月、9月、10月相应区间继续具名UNKNOWN；7月26日更新原报及后续普通年报比较列按真实时序区分。
- 茅台、工行、宁德金额/主体及EPS对照保留完整回归，不把EPS变化当成三项金额修订。

日期映射仍为候选DATE_ONLY_NEXT_OBSERVED_SH_INDEX_SESSION_CLOSE_NOT_OWNER_FROZEN，未冻结产品时序规则。原F2其他未决通知范围与索引快照限制继续存在。见closure_replay_validation.json；本轮没有将它们全盘清除。

## 具名认证缺口

| 证券 | 公告ID | 公告日 | 主要受检财务期 | 阻断字段 | 来源物理页 | 缺口 |
|---|---|---|---|---|---|---|
| 000961 | 1216741269 | 2023-05-04 | 2022-12-31 | NP/OCF/EQ | 3, 9, 10, 11, 12, 203 | 扫描财务表金额/列未认证 |
| 000002 | 1216869640 | 2023-05-22 | 2022-12-31 | NP/OCF/EQ | 3, 9, 10, 13, 15, 189 | 扫描财务表金额/列未认证 |
| 000961 | 1217078313 | 2023-06-16 | 2022-12-31 | NP/OCF/EQ | 3, 9, 10, 11, 12, 203 | 扫描财务表金额/列未认证 |
| 000961 | 1217949874 | 2023-09-26 | 2022-12-31 | NP/OCF/EQ | 3, 9, 10, 11, 12, 203 | 扫描财务表金额/列未认证 |
| 000961 | 1216741268 | 2023-05-04 | 2022-12-31 | OCF | 46, 53, 108 | OCF主体未认证；文字/表格差异保留 |
| 000961 | 1216741273 | 2023-05-04 | 2022-12-31 | OCF | 21, 88 | OCF主体未认证；文字/表格差异保留 |
| 000961 | 1217078312 | 2023-06-16 | 2022-12-31 | OCF | 24, 30, 38, 97, 98 | OCF主体未认证；文字/表格差异保留 |
| 000961 | 1217078316 | 2023-06-16 | 2022-12-31 | OCF | 50, 56, 64, 126 | OCF主体未认证；文字/表格差异保留 |
| 000961 | 1217949872 | 2023-09-26 | 2022-12-31 | OCF | 28, 36, 43, 107 | OCF主体未认证；文字/表格差异保留 |
| 000961 | 1217949876 | 2023-09-26 | 2022-12-31 | OCF | 57, 65, 73, 138 | OCF主体未认证；文字/表格差异保留 |
| 000961 | 1218110511 | 2023-10-21 | 2022-12-31 | NP/OCF/EQ | 2, 3, 4, 22 | 全扫描回复全文排除未认证 |

财务包还包含2023Q1/H1附表，不能仅凭FY2022审计号确认附表或所有比较列相同；这些扫描页也未获金额资格。六份回复的NP有限对照成立，但不能替OCF证明主体。原件可得与版本可认证是两个结果。

## 实测成本与预算

cost_ledger.json逐文件列出下载、体积、页数、全文文本、最终表格解析、OCR与缺口；requests.json保存每次身份及起止时间。

| 项目 | 实测或上限 |
|---|---:|
| 新请求 / 上限 | 23 / 25；重试0；新增元数据0 |
| 累计请求 / 上限 | 179 / 181 |
| 新PDF身份 | 23 / 23固定身份 |
| 累计新增PDF / 上限 | 43 / 43（F2新增20+本轮23） |
| 本轮PDF字节 / 页数 | 110,849,575 / 3,196 |
| 累计新增PDF字节 / 上限 | 163,702,093 / 200,000,000 |
| 最大单份 / 上限 | 15,852,778 / 25,000,000字节 |
| HTTP处理 | 15.268秒 |
| 显式限速等待 | 59.775秒；相邻请求间隔检查≥3秒 |
| 新文件全文文本解析 | 119.309秒 |
| 20份既存参照文本解析 | 173.563秒，2,922页；未重复下载或复制原件 |
| 最终成功一轮表格/叙述解析 | 60.461秒 |
| OCR引擎记录 | 328次，85.705秒 |
| 语义审查、真值准备 | NOT_SEPARATELY_MEASURED |

以上是可观测阶段时间，不是整轮交付工时；不含未计时渲染、部分失败调试、启动及语义审查，不混成“无人维护成本”。失败前结果保留在red_*、source_test_attempt*、parsed_*及closure_package_attempt1等文件。F2元数据136/130、超6次记录与修复证据原样保留，未重写历史账本。43份是新增下载预算口径，不将更早R4–F1原件重算成本轮下载。

免费获取不等于商业分发许可；审计回复的用途限制原文保留在底稿。本轮没有开展新许可专项或授予商业供应权限。

## 回归、路线与交接

- 原金额89/89 PASS；F2金额70项（68 PASS、2正确UNKNOWN）；EPS 3/3。
- 原回放46/46、F2回放118/118；实际质量91+70项；原36个unittest方法通过，所有原分母保留。
- 本轮10个unittest方法通过；24字段检查22 PASS/2 UNKNOWN；23时序断言通过。
- closure_package_run.json保存最终包及代码起止SHA；regression_run.json保存旧完整回归。旧输出重定向至本轮regression目录，未写回旧归档。
- 使用现有Python执行本目录run_closure.py可离线复现，默认连同旧回归重跑。不要使用旧F2目录的写入式package入口覆盖归档。

建议保持免费组合路线：已绑定公告身份的结构化/文本事实供应普通数值，官方原件验证版本与例外；扫描件需可验证的图像/列定位规则。不能把原型未覆盖的扫描件推为永久人工任务。现有证据尚不能宣布全市场免费PIT可交付，也不能证明它不经济；本轮不比较付费方案，不从固定候选推断总体错误率、召回率、人工比例或总交付成本。

下一最小动作仍在同一材料集合：核对四份扫描财务包和全扫描审计回复的图像字段/列，建立六份回复OCF主体证据，并保留六处FY2021文本差异。不得为了绿色状态丢弃候选、倒填精细真值或默认修订已全部发现。统一提交Owner复核本次限定结论，不自动授权下一阶段。

交接：W5-H-F2 Source Closure限定close-out；main/HEAD 92d85ef；已跟踪文件无修改，工作树保留原未跟踪材料及本轮报告/evidence。来源闭环存在具名UNKNOWN，S07历史Gate未通过，无产品范围变化。SHA/状态及完整清单见final_integrity.json、manifest.json。

~~~ini
CURRENT_DECISION = CONTINUE
SOURCE_CLOSURE_VERDICT = SOURCE_CLOSED_WITH_NAMED_UNKNOWN
FREE_SOURCE_POLICY = ENFORCED
ADDITIONAL_PDF_ACCESSES = 23_OF_23_FIXED_IDENTITIES
ADDITIONAL_BYTES = 110849575
REQUEST_BUDGET = 23_OF_25_ADDITIONAL__179_OF_181_CUMULATIVE__0_METADATA__0_RETRY
FINANCIAL_CANDIDATES_RESOLVED = 12_OF_23
TRUE_FINANCIAL_REVISION_EVENTS = 0_NEW_CERTIFIED__EXISTING_F2_EVENTS_PRESERVED
VERIFIED_DUPLICATES = 8
VERIFIED_NO_TARGET_EFFECT = 3
DIFFERENT_ACCOUNTING_BASIS = 1
UNRESOLVED_CANDIDATES = 11
FIXED_WINDOW_SOURCE_CLOSURE = NOT_COMPLETE__NAMED_FIELD_AND_DOCUMENT_GAPS
UNKNOWN_REVISION_RECALL = NOT_ESTABLISHED
HISTORICAL_T_REPLAY = 23_OF_23_NEW_ASSERTIONS_PASS__141_OUTPUTS__84_SELECTED_57_UNKNOWN
ACCEPTED_INCORRECT_VALUES = 0_WITHIN_CHECKED_DENOMINATORS__UNSCORED_NOT_ACCEPTED
REGRESSION_TESTS = OLD_DENOMINATORS_PRESERVED_AND_PASS__10_NEW_UNITTESTS_PASS__24_FIELDS_22_PASS_2_UNKNOWN
REMAINING_SOURCE_BLOCKERS = 4_SCANNED_FINANCIAL_BUNDLES__1_SCANNED_AUDITOR_REPLY__6_OCF_SCOPE_GAPS__6_INTERNAL_TEXT_DIFFERENCES
NEXT_MINIMUM_ACTION = SAME_SAVED_ORIGINALS_ONLY__VERIFY_IMAGE_COLUMNS_AND_OCF_SCOPE__PRESERVE_SOURCE_CONFLICTS
FULL_MARKET_PIT_GATE = NOT_PASSED
MISHI_S07_HISTORICAL_GATE = NOT_PASSED
PRODUCTION_IMPLEMENTATION_AUTHORIZED = NO
PRODUCT_SCOPE_CHANGED = NO
GIT_COMMIT = NO
GIT_PUSH = NO
OWNER_REVIEW_REQUIRED = YES
~~~
