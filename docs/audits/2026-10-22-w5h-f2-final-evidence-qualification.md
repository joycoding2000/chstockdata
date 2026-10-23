# chstockdata — W5-H-F2 最终自动化证据资格裁决

日期：2026-10-22（Asia/Shanghai）。Owner 决策：`FIX_ONLY / FREE_ONLY / NEW_NETWORK_REQUESTS=NO`。

**固定窗口裁决：`FIXED_WINDOW_PARTIAL_WITH_PROVEN_GAPS`。产品裁决：`MISHI_S07_HISTORICAL_GATE=NOT_PASSED`。**

本次对固定 11 份既存原件完成有界结构调查、局部识别、主体认证、字段/期间资格和历史 T 连接。六份回复的 FY2022 OCF 主体闭合；原 24 项来源字段检查由 22 PASS/2 UNKNOWN 转为 24 PASS。全扫描第二轮审计回复可排除目标影响。四份扫描财务包仍有 **18 个文档—期间—字段必要缺口**，继续拒绝；没有将材料判为永久需要人工，也没有认定这些原件客观不可读。

只新增本文及 [对应 evidence 目录](evidence/2026-10-22-w5h-f2-final-evidence-qualification/)。未改归档原件、旧失败结果、生产代码、消费者、数据库或合同；不 commit、push、release。

## 1. 权威恢复与执行边界

实际 HEAD 为 `5584f5fcacccef9a9531a7a32b8463ea6771d312`，与 Owner 指定基线一致。开始时 tracked 无修改，既有未跟踪内容全部保留。`before.json` 对既有 **15,620 个文件**保存字节 SHA；终检结果见 `final_integrity.json`，交付身份见 `manifest.json`。

权威输入为 AGENTS.md、Mishi R3.2 已批准范围、DR05 历史要求、R4/R5/R6/F1/F2 结论及 2026-10-21 Source Closure；文件身份和最新 Owner 原文见 `authority_inputs.json`、`owner_request.md`。R3.2 的 S07、真实历史版本、约一年另含预热、全池/估值/行业资格均未缩减；较早报告中的付费路线建议不覆盖本次 FREE_ONLY 指令。日期级可用规则仍是实验候选，没有成为产品时间合同。

直接复用 11 原件共 **62,644,479 字节**，新增网络请求 **0**。Python 研究程序安装拒绝 socket 连接的审计钩子；OCR 使用现有 Windows 本地引擎，未安装或下载模型。没有创建 venv 或临时运行环境；图像、OCR、失败输出与底稿作为持久 evidence 保留，无自动清理旧数据。

## 2. 五份扫描件：先结构、后字段，按证据停止

`inspect_structure.py` 在 19 份相关既存文件的 **3,064 页**调查 XObject、尺寸、过滤器和流身份，识别五份受检文件中 130 个含大图像的页面。这里的 DCT 解码流摘要仍可能是 JPEG 流身份，不能冒称解码后像素身份；后续另用整页渲染验证。

`1217078313` 与 `1217949874` 的 p8—16、p202—206，共 **14 对整页**在固定渲染尺寸下 RGB 像素 SHA 完全相同。p202—206 包含资格证件等内容，不能把 14 对都称为财务表。FY2022 目标表 p10—12 的页面相同得到证明，但这两个尚未获得完整金额资格的扫描副本不能互相担保。未取得与已认证数字原报的直接图像流身份映射；审计号相同也未作为金额放行依据。

尾部实际结构与旧定位不同：

- `1216741269` p207—210 是另一套 FY2022 报表，p211—214 是横置权益变动表，并非 Q1；本包不因标题包含“最近一期”就被赋予 Q1 数字资格。
- `1217078313` 的 Q1 目标页为 p208—210；`1217949874` 的 H1 目标页也为 p208—210，分别独立判定。
- `1216869640` FY2022 目标页为 p10/p13/p16；Q1 为 p201/p203/p206。
- H1 p208 的比较列明确是 **2023-01-01 期初**，没有改写为 2022-12-31 期末。误归属失败测试 `red_h1_opening.txt` 和修正前结果均保留。

在图像结构基础上执行：原有 OCR 坐标候选与列网格定位 → 有限字段/列裁剪 → 修复已证实的金额基线错位、边缘截字和无留白 → 数字整列去横线 OCR → 不读财务真值的系统字体逐字形探针 → 独立原件比较。新增 OCR 为 **480 次**，引擎记录合计 **29.162 秒**；没有无条件重跑此前整页中英文流程。定位计划含 Agent 辅助几何选择，不声称通用自动页发现或盲测。

最后另做一次整字段影像等价探针：29 个既存原件参考值探测、**3,354 个 TEST_ONLY 单字/符号/倍率负控**；固定阈值下没有通过者，没有继续调阈值。该模型无法可靠排除近似错字，**未用于放行任何金额**。这与识别器输出不一致、字符合并、表格线干扰和裁剪失败一起保存，证明当前方法的具体证据不足，而不是证明原件永久不能程序化处理。

只接受以下三处由 Windows OCR 与逐字形识别一致、并与更早独立原件精确对应的单元格；期间、合并主体、元单位、当前列和负号均核验，未向解析器填入正确金额。

| 扫描来源 | 页/期间/字段 | 原件所载值（元） | 独立原件依据 |
|---|---|---:|---|
| 1216869640 | p203，2023Q1 NP | 1,445,811,341.87 | 1216686497；早于本扫描包披露 |
| 1217078313 | p209，2023Q1 NP | -665,649,652.02 | 1216696970；早于本扫描包披露 |
| 1217949874 | p209，2023H1 NP | -798,112,292.31 | 1217710575；早于本扫描包披露 |

不据单个相同金额认证整表。每笔保留页、列、原图坐标、原文、源 SHA、原件版本及比较依据，见 `scan_field_qualification.json`。`image_identity_and_reply_scope.json` 保存完整页像素证据。

原始 **72 个扫描目标行/列探针单元格全部保留**，其中：

- 27 个重点定位点仍全部在账；严格期间纠正后，26 个属于固定必要字段，**3 认证、23 未认证**；另 1 个显式期初列继续记未认证但对本组固定查询不具必要依赖。
- 24 个公司/母公司列排除于合并目标，其中 NP 在独立公司列不适用；不把空白 NP 当作零。
- 22 个未认证比较/期初单元格不被固定直接查询使用，明确保留为 `UNRESOLVED_NON_MATERIAL_FOR_FIXED_T`；这不认证实际 S07 的 ROE/TTM 预热。

停止原因是：有限结构、行列、两种识别和带负控的影像等价尝试已经完成，尚不足以认证其余精确数字；没有依据再以同一识别器重复调参换取 PASS。不存在“所有扫描文件必须人工”的结论，也没有用新生产架构来替代本次资格证据。

## 3. 六份回复：OCF 合并主体与 2021 年差异

主体证明没有使用“OCF 恰好相同”作为唯一依据。程序定位同文“公司现金流量状况／公司的现金流量表简要情况”及明确日期、万元单位，以已取得原报 `1216561621` p80 **合并及公司现金流量表**作独立矩阵参照：每份回复有 **16 个非 OCF 单元格**（8 类现金流入/流出及投资/筹资行、2021/2022 两期）在印刷精度内匹配合并列，且不匹配母公司列。封面发行人、章节说明、日期、单位和多行身份共同支持归属。身份是原件矩阵对应，不伪造这些回复直接引用同一审计报告编号。

开放左右边界复用已有修复。`1217078312` p97 的 OCF 金额与 p98 的“净额”标签按原有相邻页/列边界连续证据连接；其他跨页表要求相同列头、左边界和相邻页首。修复没有证券代码或公告 ID 的数值补丁。见 `reply_scope_qualification.json`。

| 来源 | FY2022 OCF 主体证据页 | 2021 差异文字页 | 资格 |
|---|---|---|---|
| 1216741268 | p108—109 | p53 | FY2022 合并 OCF 既存版本 |
| 1216741273 | **p88** | p28 | FY2022 合并 OCF 既存版本 |
| 1217078312 | **p97—98** | p38 | FY2022 合并 OCF 既存版本 |
| 1217078316 | p126—127 | p64 | FY2022 合并 OCF 既存版本 |
| 1217949872 | p107 | p43 | FY2022 合并 OCF 既存版本 |
| 1217949876 | p138 | p73 | FY2022 合并 OCF 既存版本 |

六份文字均为 FY2021 OCF **1,677,198.08 万元**，相应表格为 **1,677,198.05 万元**，印刷差额 **300 元**。原报合并精确数为 **16,771,980,470.34 元**：它与表格精度相容，文字与之差 **329.66 元**。两种万元表达的最小单位同为 100 元，舍入区间不相交；没有证据支持这是合并/母公司口径差异。确定属于**源文件内部不一致，原因未定**，不能直接断言笔误、直接替换文字或制造新重述。

六处差异完整保留。原 141 个固定查询无 000961/FY2021/OCF 直接依赖，也没有派生指标计算；新增测试证明一旦请求显式引入该基期依赖，就返回 UNKNOWN。实际 S07 公式、预热和目标窗尚未冻结，因此这里的“非必要”仅针对固定测试集合，不能推广至产品。

## 4. 11 份来源的字段资格及未解分母

| 公告 ID | 证券/日期 | 受检期间及结果 | 仍阻断的必要字段 |
|---|---|---|---|
| 1216741269 | 000961 / 2023-05-04 | FY2022；p10—12、p208—210 未完整认证 | FY2022 NP/OCF/EQ（3 槽） |
| 1216869640 | 000002 / 2023-05-22 | FY2022 与 Q1 独立；Q1 NP 已认证 | FY2022 三字段；Q1 OCF/EQ（5 槽） |
| 1217078313 | 000961 / 2023-06-16 | FY2022 与 Q1 独立；Q1 NP 已认证 | FY2022 三字段；Q1 OCF/EQ（5 槽） |
| 1217949874 | 000961 / 2023-09-26 | FY2022 与 H1 独立；H1 NP 已认证；期初独列 | FY2022 三字段；H1 OCF/EQ（5 槽） |
| 1218110511 | 000961 / 2023-10-21 | **VERIFIED_NO_TARGET_EFFECT**，22 页完整保留 | 无本回复新增目标字段阻断 |
| 1216741268 | 000961 / 2023-05-04 | FY2022 NP/OCF 既存事实，2021 OCF 冲突保留 | 本次 FY2022 OCF 主体阻断解除 |
| 1216741273 | 000961 / 2023-05-04 | 同上 | 同上 |
| 1217078312 | 000961 / 2023-06-16 | 同上 | 同上 |
| 1217078316 | 000961 / 2023-06-16 | 同上 | 同上 |
| 1217949872 | 000961 / 2023-09-26 | 同上 | 同上 |
| 1217949876 | 000961 / 2023-09-26 | 同上 | 同上 |

全扫描审计回复 `1218110511` 复用既存 OCR，并核验全部 22 页原图身份、目录、问题、正文范围、核查结论与末页用途声明。正文限定债务重组、项目预售资金、教育投资及产业政策，未提供三项目标金额替换；不是因共享问询号或另一份回复相似而自动宣布重复，也不认证其中所有债务或项目金额。Agent 原图范围复核与程序门槛共同支撑该限定结论，不包装成通用扫描语义自动化。

完整 [字段账本](evidence/2026-10-22-w5h-f2-final-evidence-qualification/final_source_qualification.json) 有 **91 行处置记录**：15 行既存事实资格、23 行必要单元格未解、28 行固定 T 非必要未解、24 行不同主体排除、1 行无目标影响。28 行非必要未解由 **22 个扫描比较/期初单元格＋6 份回复的同一 FY2021 源冲突位置**构成。

23 个必要单元格合并为 **18 个文档—期间—字段槽**，都落在原有四份扫描财务包；这些不是新增 18 份未知文档。91 行、72 个探针、跨文件相同事实和六处重复冲突也都不是独立金融样本。没有借改变分母制造通过；原有 24 项字段检查、旧失败和原始金额证据全部保留。

每行提供 `document_id / affected_security / affected_period / affected_field / accounting_scope / source_version / disclosure_date / evidence_page / qualification_status / historical_T_impact`。全部六种约定状态保留，`VERIFIED_NEW_FINANCIAL_FACT` 本轮为 0。

## 5. 历史 PIT 连接

原 **127 条认证事实**的金额、原件身份和 vintage 日期保持不变。三处扫描 NP 和六份 FY2022 OCF 是既存事实的旁证，没有发现可认证的更早事实或新金额修订，未倒签最早可用日期。**新增修订 0 不等于未知修订召回率 100%**。

选择器按文档、期间、字段判定阻断：局部 NP 认证不清除该包的 OCF/EQ；FY2022 年度身份不替代 Q1/H1；2023-01-01 期初不变成 FY2022 期末；2021 冲突若成为直接或派生必要依赖则拒绝。目录窗外限制和继承通知限制也保留。新修复让目录覆盖提前拒绝时仍列出同时存在的具名来源缺口，没有放松拒绝。

- 原 141 个查询完整保留：**84 SELECTED_KNOWN_SOURCE、57 UNKNOWN**，状态/金额变化 0；UNKNOWN 并未清零。
- 新增 21 个实际查询：3 个已认证季度 NP 的时点选择、18 个具名必要字段拒绝。另有 12 项基期依赖断言；合计 **33/33** 通过。
- 实际查询共 162 输出：87 选择、75 UNKNOWN；依赖断言与实际查询输出分别计数。
- [field_T_impact.json](evidence/2026-10-22-w5h-f2-final-evidence-qualification/field_T_impact.json) 将 91 行来源处置逐项连接到实际受检 query_id、T、结果、来源及是否列为阻断。非必要记录没有直接匹配依赖，但不解除产品基期资格。

实验日期规则仍为 `DATE_ONLY_NEXT_OBSERVED_SH_INDEX_SESSION_CLOSE_NOT_OWNER_FROZEN`。康美旧正 OCF/后来负修订、未来值拒绝、万科单位污染、茅台权益和宁德 EPS 对照全部保留。

## 6. 回归和复现

`run_regressions.py` 重新执行原程序和断言，生成物全部重定向到本目录 regression，未写回归档。复用代码 SHA 绑定且原件身份受保护的旧解析输入，没有声称重新解析全部历史 PDF。

| 检查 | 本轮结果 |
|---|---|
| F1 金额 | 89/89 PASS |
| F2 金额 | 70 项：68 PASS、2 正确 UNKNOWN |
| F2 EPS | 3/3 PASS |
| F1 / F2 历史回放 | 46/46、118/118 PASS |
| Source Closure 原时序 | 23/23 PASS，旧输入语义保留 |
| 原安全/身份/目录 / Closure 测试 | 36/36、10/10 PASS |
| 既有实际质量 | 91/91＋70/70 PASS |
| 原来源字段检查，新增主体证据后 | 24/24 PASS；原 22 PASS/2 UNKNOWN 文件不变 |
| 本轮新增单元测试 | **19/19 PASS**，含真实三处扫描单元格的错误列、倍率、主体、缺头拒绝；伪重复、期初和依赖分支 |
| 新时序/依赖 | 33/33 PASS |
| 新原件/OCR/账本完整性检查 | 542/542 PASS；这是完整性检查数，不是金融样本数 |

红/绿测试和失败底稿包括 `red_qualification.txt`、`red_h1_opening.txt`、`reply_scope_attempt1.log`、`scan_fields_before_opening_fix.json`、`final_replay_attempt1.json`，未改写成成功。`package_run.json` 保存最终各阶段 exit、代码首尾 SHA 和日志；`regression_run.json` 保存旧完整回归。受检错误接受为 **0**，范围限于上述受检分母；不将未认证候选计为成功值。

完整离线重现：

```powershell
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -X utf8 -B docs/audits/evidence/2026-10-22-w5h-f2-final-evidence-qualification/run_package.py
```

默认连同旧回归重跑；已保存的 480 次局部 OCR 输入/输出逐一核对源/图像 SHA，不在包内联网或重新训练。结构/字形/影像负控原始探针脚本和计划均在 evidence 中。OCR 引擎秒数不含全部调试、定位、模型推理和文档工作；真人独立复核工时未测，不据此估计全市场成本或人工比例。

## 7. 分类、停止与交接

| 分类 | 本轮事实 |
|---|---|
| CONFIRMED_DEFECT | 开放表格边界、双行标签/金额基线与裁剪；期间起初/期末误归属；目录拒绝隐藏具名缺口。可验证修复已在本工作包完成，失败证据保留 |
| UNRESOLVED_RISK | 四扫描包 18 必要字段槽未认证；六处 FY2021 冲突原因为未定；目录窗外链、首次可知、实际 S07 依赖和全池/估值资格未闭合 |
| SPECULATIVE_CONCERN | “所有扫描件必须手抄”“原件永远不能程序化”“本轮无新修订即发现完整”均无证据，不据此追加工程或放行 |
| FUTURE_ENHANCEMENT | 仅准备真实 S07 目标窗、财务预热依赖和准入证据要求；新 Provider、数据库、生产采集或全市场实施未授权 |

本次 A 的部分资格裁决已经形成；这不等于固定来源 Gate 接受。停止重复研究旧六证券案例，将四包具体缺口及依赖拒绝边界作为已知限制交给 Owner。下一最小动作是 **Owner Review 后准备实际 S07 窗口、公式/基期、全市场历史财务覆盖和指定日估值的准入评估**，而不是默认再开旧案例 OCR 轮次或启动获取。产品级 Gate 仍未通过。

交接：当前阶段/步骤为 **W5-H-F2 最终离线证据资格处理，等待 Owner Review**；HEAD `5584f5fcacccef9a9531a7a32b8463ea6771d312`，tracked 维持原状，既有未跟踪内容保留，只新增本报告/evidence。Gate 为 `FIXED_WINDOW_PARTIAL_WITH_PROVEN_GAPS / INSUFFICIENT_EVIDENCE`；数值回归、时序、具名缺口和原件身份是支持证据。未解项为上述 18 必要槽及受限非必要未知；产品范围无变化。推荐动作仅为提交本次裁决、准备真实窗口准入材料，不宣称下一阶段或生产获得授权。

```ini
CURRENT_DECISION = FIX_ONLY
FINAL_SOURCE_QUALIFICATION_VERDICT = FIXED_WINDOW_PARTIAL_WITH_PROVEN_GAPS

SCANNED_DOCUMENTS = 5
SCANNED_FIELD_QUALIFICATION = 3_OF_26_CRITICAL_CELLS_VERIFIED__27_PROBED_SITES_AND_72_CELLS_RETAINED__1_REPLY_NO_TARGET_EFFECT
OCF_SCOPE_DOCUMENTS = 6
OCF_SCOPE_QUALIFICATION = 6_OF_6_CONSOLIDATED_VERIFIED_FY2022__24_OF_24_SOURCE_CHECKS_PASS
FY2021_OCF_CONFLICT = 6_LOCATIONS_PRESERVED__SOURCE_INTERNAL_INCONSISTENCY_CAUSE_UNDETERMINED

REMAINING_MATERIAL_UNKNOWN = 18_DOCUMENT_PERIOD_FIELD_SLOTS_IN_4_SCAN_BUNDLES
REMAINING_NON_MATERIAL_UNKNOWN = 28_RECORDS__22_SCAN_COMPARATIVE_OPENING_CELLS_AND_6_CONFLICT_LOCATIONS__FIXED_TESTS_ONLY
FIXED_WINDOW_FINANCIAL_SOURCE_GATE = INSUFFICIENT_EVIDENCE__NAMED_GAPS_FAIL_CLOSED
FIXED_CASE_ASOF_REPLAY = 141_PRESERVED_84_SELECTED_57_UNKNOWN__33_NEW_ASSERTIONS_PASS
ACCEPTED_INCORRECT_VALUES = 0_WITHIN_CHECKED_DENOMINATORS__UNQUALIFIED_NOT_ACCEPTED
FULL_REGRESSION = PASS_ALL_FROZEN_DENOMINATORS__19_NEW_TESTS_AND_542_INTEGRITY_CHECKS_PASS

FREE_SOURCE_POLICY = ENFORCED
NEW_NETWORK_REQUESTS = 0

NEXT_MINIMUM_ACTION = OWNER_REVIEW_THEN_PREPARE_REAL_S07_WINDOW_DEPENDENCY_AND_ADMISSION_ASSESSMENT__NO_MORE_OLD_SIX_CASE_RESEARCH
S07_REAL_WINDOW_QUALIFICATION_READY = SCOPE_AND_DEPENDENCY_ASSESSMENT_PREPARATION_ONLY__DATA_QUALIFICATION_NOT_READY

MISHI_S07_HISTORICAL_GATE = NOT_PASSED
PRODUCTION_IMPLEMENTATION_AUTHORIZED = NO
PRODUCT_SCOPE_CHANGED = NO
GIT_COMMIT = NO
GIT_PUSH = NO
OWNER_REVIEW_REQUIRED = YES
```
