# v0.4.2 historical opening execution — implementation audit

日期：2026-10-11，Asia/Shanghai。CURRENT_DECISION=FIX_ONLY；Owner 已批准 R1–R5 和两项能力边界，授权恢复有限实施。RELEASE_AUTHORIZED、PUBLISH_AUTHORIZED、NEXT_PHASE_AUTHORIZED 均为 NO。

本文件记录本轮实际实现和验证；以前的设计 REWORK、旧候选 Gate FAIL 不被覆盖。旧完整历史 PIT 停牌能力仍 UNKNOWN/fail-closed。新能力只用于显式选择的历史开盘执行模式，其 `[09:30,09:31)` 活动代理不承诺整点或具体订单必然成交。

## Step 0 — baseline protection

- chstockdata 原 HEAD：`42bd44ef4d695aa3e88cfab4ebc3417660d0437a`；分支 `codex/rh3-b5-candidate-freeze-preflight`；既有 10 项 tracked 修改及原审计/测试 untracked 保留。
- 旧候选 566 个文件 SHA256 与保护清单逐项一致，内存重建 Git tree 为 `911d231646edc7d419d2e26ac91c95af5404c5c6`。
- 旧 wheel SHA256：`b76b065a06cd1d91868880a7b57584f598b6fd4cb42931e9a33700bc99a88c7a`，没有覆盖。
- SIOS 当前 HEAD：`fafdb6d3942ba52baa9480da7c8674dab1487f5d`，原工作树 clean；实施基线采用冻结 commit `84fd54fae0740bc06b1d250afa4578be29556956`、tree `979b5b33188931e2c78aa01026684ed72e064600`，全部冻结文件逐字节匹配旧消费者清单。
- chstockdata 当前 tracked/nonignored 文件完整备份及清单保存于隔离目录。备份 ZIP SHA256：`f59d0889112f2e9983c3eab38e47591a6c08d5976f6864857b0377c81246a5d4`。

本轮实际实施根：`C:/Users/Administrator/.codex/visualizations/2026/10/10/01a125dd-33f2-78d3-abe7-45e0928975d0/v042-opening-implementation/`，分别使用 `chstockdata/` 与 `systematic-investing-os/`。根下 `baseline.json` 保存原文件清单、原 Git 状态、冻结源码身份和保护证据。注册的 `C:/Users/Administrator/.codex/worktrees/v042-opening-cr/chstockdata` 另存保护副本；实际修改使用有写入权限的隔离源快照。

导出过程发现 Git archive 自动转换冻结 SIOS 的 LF 为 CRLF（238 个文件哈希不符）。该导出未用于实施；已用 `git cat-file --batch` 直接读取冻结 blob、验证 Git 对象 SHA1，纠正生成目录后再次比对全部文件。默认沙箱读取原 dist wheel 被拒绝，保护检查在有界授权执行中完成，后续使用逐字节复制的隔离旧 wheel。以上过程均未改动原源码或旧工件。

```ini
BASELINE_PROTECTED = YES
APPROVED_SCOPE_IDENTIFIED = YES
OLD_CANDIDATE_IMMUTABLE = YES
```

## Current handoff

当前阶段：Step 1，新增窄的历史开盘证据能力及确定性回归。Step 2–4 尚未执行。两仓隔离源码尚无新提交；原 chstockdata 工作树仅追加 Owner 批准记录及本审计，旧正确性修复保持。

后续局部门禁、A1–A11 映射、文件清单、实际命令/退出码、来源及候选身份将在产生真实证据后追加；本记录不构成实现 PASS 或 Owner 验收。


## Step 1 — source prerequisite STOP

状态为 BLOCKED，产品实现 NOT_EXECUTED。按实施指令“不可验证的数据源前提”停止；没有新 reader、公共函数、schema、TDX 候选调用或源码/测试/依赖改动。Step 2–4 没有执行。

最小源前提核验：默认沙箱首请求 ConnectionError，脚本立即停止（exit 2）；有界提升权限批次固定 5 个请求、连接/读取超时 4/8 秒、TLS 校验开启、无自动重试、无重定向，共 5 个 HTTP 200（exit 0）。这是取证脚本完成，**不是来源语义或候选 Gate PASS**。原 bytes、解析 JSON、请求参数、aware UTC 请求/获取时间、计数和 SHA256 均保留于 [step1 evidence](evidence/2026-10-11-v0.4.2-opening-implementation/step1/)。没有重跑此前 44 次 TDX 调查。

| 输入 | 本轮实际结果 | 合同结论 |
|---|---|---|
| SSE 688432 / 2026-09-11 | 1/1，startStopDate=20260831、endStopDate=20260911、type=LXTP、stopTime 空 | 确认该查询返回此前开始的持续停牌区间；末停牌日不是精确复牌时刻 |
| SSE 688432 / 2026-09-14 | total=0、合法空 | 不能仅凭空事件推导复牌或完整正常状态 |
| 本轮构造的 SSE 复牌 PDF 路径 | HTTP 200、7373 bytes HTML，非 PDF；路径由旧报告文件名及目录结构构造，未由本轮官方列表认证 | 仅说明该指定请求没有取得合格 PDF；不能认定已认证附件不可访问、官方端整体故障或历史复牌事实缺失 |
| SZSE 159915 / 公告日期 2026-08-01–09-14 | announceCount=4，4 行 | 所选发布日期窗口的响应计数完整；未认证覆盖窗口前起始、目标日仍持续的二级市场停牌 |
| SZSE 159509 / 公告日期 2026-09-10–11 | announceCount=2，2 行，停复牌公告附件路径 | 能取得正向公告列表，尚未取得本轮有效时段正文/持续覆盖资格；不得将午夜 publishTime 当作生效时刻 |

**唯一足够的 STOP 依据：UNRESOLVED_RISK / INSUFFICIENT_EVIDENCE——当前 SZSE 有界查询的持续区间覆盖资格未认证。** 这是批准合同要求的必要有界检查，CR §6.3–6.4 明确禁止未知覆盖硬编码为完成；不要求完整历史正常状态认证。没有证据证明该源永远无法支持所需检查，也没有据此新增公告全集、通用路由或扩大窗口抓取工程。

688432 的历史明确复牌事实已有合格材料：E2 `issuer-resume-mirror.pdf`，SHA256 `026b42096af80856f7ae69fb81fc7166d2e805e7dacfd3ddd2566d5278f891ea`，第二页明确 2026-09-14 开市起复牌，旧 disclosure-pages 与批准 CR 已认可，fixture 可用。新构造路径的 HTML 不能否定它；本轮未认证该构造 locator 作为当前运行时 reader 输入。此项不是独立 STOP 的必要理由。

原响应 SHA256：

| 文件 | SHA256 |
|---|---|
| sse_688432_interval.bin | 33147724bcee2f692e3de7a637c2490017a86c1399183c7f8ccf1f7fe017d924 |
| sse_688432_resume_session.bin | ab1fa084a62ae34d98a76d46c9029d3bea698e84d59ca4b7200fa0ac7f347e4b |
| sse_688432_resume_pdf.bin | 186f5ee5d558e601677cde30d55998b9e53098da13900986d7b55988f31dcc88 |
| szse_159915_announcements.bin | 13c652bf1ce25aeaec1c58d705053fb10bf37d09128a3dd2b11c4585f24a9797 |
| szse_159509_announcements_control.bin | 1c799d8c18359ac482465556350b9b889e1c36689eda35f3d033edb5ec3a9813 |

## Actual verification and commands

探针与旧安全测试均只读使用既有 Python 3.12.14 环境；没有安装、替换或修改该环境。实际导入版本：pytest 9.1.1、requests 2.34.2、pandas 3.0.6、mootdx 0.11.7、tdxpy 0.2.7。源前提 probe 使用既有 requests；没有新 TDX 解析器运行，不能将这些版本声明当作 A5 通过。

解释器 P：`C:/Users/Administrator/.codex/visualizations/2026/10/09/01a11feb-cbea-7790-a83e-57b1dd555e13/v042-unified/sios-candidate/Scripts/python.exe`。

| 实际命令 | cwd / 环境 | exit / 结果 |
|---|---|---|
| P `-B evidence/step1/probe_source_prerequisites.py sandbox` | 本轮隔离实施根 | 2；首请求传输失败，停止；不当作来源空 |
| P `-B evidence/step1/probe_source_prerequisites.py live` | 本轮隔离实施根；有界提升权限 | 0；5 响应，语义资格不等于 PASS |
| P `-B evidence/step1/check_evidence.py` | 本轮隔离实施根 | 1；5 份原响应/解析一致，758 项隔离基线只 CR Owner 批准追加不同。准确保留治理差异，不是产品失败 |
| P `-m pytest tests/test_suspension_source_semantics.py tests/test_suspension_structured.py -q --tb=short -rA -p no:cacheprovider --basetemp=<隔离根>/legacy-safety-tmp --junitxml=<隔离根>/evidence/step1/legacy-safety.xml` | 隔离 chstockdata；PYTHONPATH=<隔离 chstockdata>/src，PYTHONDONTWRITEBYTECODE=1、PYTHONUTF8=1、PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 | 0；**19 passed、0 failed、0 error、0 skipped** |

完整旧安全测试 argv/cwd/env 在 `step1/legacy-safety-command.json`，日志和 JUnit 同目录；探针请求合同、参数、原响应身份在 `step1/live/requests.json`、manifest。初始化保护用 Git rev-parse/status/ls-files/ls-tree/cat-file 对比真实文件：保护副本批次最初因 Git archive 换行不符 exit 1、默认 wheel 读取拒绝 exit 1，随后冻结 blob 导出与保护 tree 内存重建核验 exit 0；没有改写原文件。最终保护复核脚本 `verify_final.py` 的实际退出码与输出另存 `final-verification.exit/.log/.json`。

独立 spec 复核：SPEC_COMPLIANT_STOP；独立证据质量复核：APPROVED，仅针对停止依据及取证脚本。原始字节、JSON 副本与 SHA 均一致；不能把实现代理声明当候选资格。复核纠正了 688432 既有复牌正文边界。所谓 +08 时间疑点来自 PowerShell ConvertFrom-Json 自动呈现，原请求文件均 +00 UTC，不是证据转换。未增网络或产品改动。

## Approved clauses, files and acceptance mapping

| 条款 | 本轮落实 | 未完成 / 实施门禁 |
|---|---|---|
| R1 | 批准记录保留分钟代理边界；旧调查材料保留 | 新 reader/09:30 活动判定及候选 live 未执行，BLOCKED |
| R2 | 原始官方字段及持续覆盖缺口留证，不把公告空视为正常 | 官方 parser/合成门禁未实现，BLOCKED |
| R3 | SIOS 冻结 blob 和原工作树保护 | 专用执行输入、PIT 隔离接线未执行，BLOCKED |
| R4 | 上海模型时钟及旧 UTC 身份边界记录保留 | runner/OOS/qualification 注入未执行，BLOCKED |
| R5 | 正式合同调整及旧能力边界追加，不改原 REWORK | mandatory live 及断言修订未执行，BLOCKED |

| ID | 本轮验收结果 | 未完成的正式验收 |
|---|---|---|
| A1 | BLOCKED | 四 ETF 新 reader/adapter 实际资格无实现 |
| A2 | BLOCKED | 两临停候选控制及消费者无 Fill 未执行 |
| A3 | BLOCKED | 既有持续/复牌事实可作 fixture，候选解析/执行未验证 |
| A4 | BLOCKED | 2016/2022 新候选 reader 未调用，旧样本不替代 |
| A5 | BLOCKED / NOT_EXECUTED | ×10 修复及永久回归未实施 |
| A6 | BLOCKED | 新失败/冲突契约未实施；旧安全回归 19 项不替代它 |
| A7 | BLOCKED / NOT_EXECUTED | SIOS 新模式未实施 |
| A8 | BLOCKED / NOT_EXECUTED | 实际 Shanghai clock 接线未实施 |
| A9 | BLOCKED / NOT_EXECUTED | 原算术未改；新模式 Ledger 等价验证未执行 |
| A10 | BLOCKED / NOT_EXECUTED | 原五 mandatory live 未启动；没有以 skip/fixture 代替 |
| A11 | BLOCKED / NOT_EXECUTED | 无新候选 source/wheel、安装 profiles 或消费者统一验证 |

本轮原仓库改变仅为：CR 文档追加批准/本轮停止交接；新增本 implementation audit 及同名 evidence 目录。隔离目录新增保护清单/完整备份、Owner 请求身份、源前提取证脚本与原响应、旧安全测试日志、最终核验脚本。**产品 src、tests、pyproject、正式 pin、旧 wheel、SIOS 引擎/策略及冻结研究产物没有修改；没有新 commit。** 这次停止发生在新源码实现前，因而没有 TDD red/green，不伪造实现变化清单。最终 SHA256 清单列在 evidence 的 `SHA256SUMS.json`。

## Final handoff

```ini
CURRENT_DECISION = FIX_ONLY
CR_IMPLEMENTATION = BLOCKED
R1_OPEN_ACTIVITY_PROXY = BLOCKED
R2_OFFICIAL_SUSPENSION = BLOCKED
R3_SIOS_EXECUTION_ISOLATION = BLOCKED
R4_SHANGHAI_CLOCK = BLOCKED
R5_MANDATORY_LIVE_CONTRACT = BLOCKED
LEGACY_SUSPENSION_FAIL_CLOSED = PASS
MOOTDX_0X0FB5_PRICE_REGRESSION = FAIL
A1_A11_ACCEPTANCE = A1:BLOCKED,A2:BLOCKED,A3:BLOCKED,A4:BLOCKED,A5:BLOCKED,A6:BLOCKED,A7:BLOCKED,A8:BLOCKED,A9:BLOCKED,A10:BLOCKED,A11:BLOCKED
PACKAGE_TESTS = 19_LEGACY_PASSED;FULL_SUITE_NOT_EXECUTED
SIOS_OFFLINE = NOT_EXECUTED
SIOS_MANDATORY_LIVE = NOT_EXECUTED
TRADINGAGENTS_COMPATIBILITY = NOT_EXECUTED
CANDIDATE_SOURCE_SHA = NOT_BUILT
CANDIDATE_WHEEL_SHA256 = NOT_BUILT
SCOPE_EXPANSION = NO
UNRESOLVED_BLOCKERS = SZSE_BOUNDED_PERSISTENT_INTERVAL_COVERAGE_NOT_CERTIFIED
READY_FOR_OWNER_ACCEPTANCE = NO
RELEASE_GATE = BLOCKED
RELEASE_AUTHORIZED = NO
PUBLISH_AUTHORIZED = NO
TAG_CREATED = NO
PYPI_UPLOAD = NO
```

价格回归字段的 FAIL 表示尚未满足验收，实际执行状态为 NOT_IMPLEMENTED / NOT_EXECUTED，**不是运行了一个失败的价格测试**。Step 1 四局部门禁：HISTORICAL_OPEN_EVIDENCE_CONTRACT=BLOCKED；TDX_ETF_PRICE_REGRESSION=NOT_EXECUTED；OFFICIAL_STOP_CONTROLS=BLOCKED；LEGACY_SUSPENSION_SAFETY=PASS（19 项现行安全合同回归）。禁止以最后一项 PASS 推进后续步骤。

当前阶段/步骤：Step 0 通过，Step 1 源前提阻断；原 chstockdata HEAD `42bd44ef4d695aa3e88cfab4ebc3417660d0437a`，原未提交修复保留，本轮文档/evidence 新增；SIOS 原 HEAD `fafdb6d3942ba52baa9480da7c8674dab1487f5d`、工作树 clean，冻结源未修改。Gate 支持证据为本次有界响应字段与覆盖缺口，不是旧调查/候选 PASS。无范围变化，无下一 Phase 或发布授权。

推荐的下一最小动作：补齐/认证 SZSE 必要有界持续停牌检查的输入合同，具体证明目标日之前开始、仍有效的二级市场停牌如何被查询覆盖；在该范围内证据足够后才恢复 Step 1。既有 688432 公告可以用于 fixture，不能把未认证 locator 或空列表冒充当前来源资格。不要求扩大到完整 PIT 历史库。

学习交接：原问题为已批准代理能否安全进入当前实现；本次确认公告日期窗口计数完整不等于持续有效区间覆盖，且已认证旧复牌正文不能被新构造 URL 失败否定。剩余未知限于当前有界官方检查资格。下一决策为保持阻断、补齐这个具体前提，避免以补偿性架构代替来源事实。


## R2.1 resume authorization — 2026-10-11

Owner 已批准 R2.1，当前官方有界查询的证券/日期/结构/范围、返回事件的二级市场及时间语义、当前分页和已知正向阻断仍必须认证；不再要求 SZSE 公告库覆盖所有此前开始的历史持续停牌作为真实开盘成交代理的必要前提。精确正式合同追加于 CR §14.5。

```ini
PREVIOUS_STOP = VALID_UNDER_ORIGINAL_R2
R2_1_OWNER_APPROVAL = YES
PREVIOUS_STOP_AS_GLOBAL_PREREQUISITE = SUPERSEDED
R2_1_AUTHORIZED = YES
MOOTDX_0X0FB5_PRICE_REGRESSION = NOT_EXECUTED
RELEASE_AUTHORIZED = NO
PUBLISH_AUTHORIZED = NO
```

纠正历史交接中的价格回归 FAIL：此前没有实现或执行该测试，正确状态为 NOT_IMPLEMENTED / NOT_EXECUTED；旧原文保留作为审计历史，不再用 FAIL 代表尚未达成验收。此状态纠正不构成 Step 1 PASS。

仅必要身份复核：原 HEAD 保持42bd44ef4d695aa3e88cfab4ebc3417660d0437a，隔离路径、保护清单、冻结SIOS commit/tree与上轮一致，隔离src/tests尚未有新增实现。复用已完成的Step 0和原响应；不重新运行44次TDX探索。接下来按TDD完成新 reader与永久价格回归，然后新reader有界live验证；不能只改停止标签。后续实际结果逐项追加。


## R2.1 Step 1 local Gate accepted — 2026-10-12

本节替代此前 Step 1 尚未实施/来源前提阻断的当前状态；原记录保留。最终 reader SHA256 为 `8e48f46373f974f665807dc3e2db8d7b8520588b699c7bce9fbf8c20986061a8`。产品实现位于受保护的隔离副本，原 chstockdata 和 SIOS 产品源码、旧 wheel 及研究结果没有被覆盖。

新增 `opening_evidence.py`、带出处的已知官方区间 JSON、公共导出、optional `opening-pdf` extra、package-data、必要真实 fixture 和 50 项合同回归。旧 suspension/tradability/VIPDOC 实现保留。只把认证的 mootdx0.11.7/tdxpy0.2.7 ETF 逐笔价格在新输出边界除以十；股票、未知版本/类别及二次规范输入有回归。0x0fb4 与 09:25+09:30 量/末价交叉核验，活动量和价格不参与日线成交算术。

当前官方有界查询、完整分页、所有已知区间与 TDX 活动分别记录；信息时间仍 UNKNOWN，retrieval 为真实 aware 时间。688432 有明确复牌公告；000002 仅复牌日期精度，effective_end=null，不能推断复牌整点。513100/159509 已知区间不能被合法空查询抹掉。旧完整历史 PIT 状态能力仍 fail-closed；本能力仅支持明确选择的新历史开盘代理模式。

TDD 和独立审查发现并修复两类真实缺陷：SSE ETF 的陈旧/跨日日期不能套用单日停复牌语义，日期核验移至非二级事件筛除之前；SSE 股票严格解析八位 ASCII 日期、日历有效性及区间顺序，复牌兼容性比较使用 date，禁止尾随字符被截断解锁。每类 RED/GREEN 保留，两个 fresh reviewer 最终均 APPROVED，仅限 Step 1。

证据目录为本 audit 同名 evidence 下 `r21-step1/`。`green-stock-interval-dates.{command.json,log,xml,exit}` 实际 128 passed、exit 0；根代理独立 `independent-stock-final-green.*` 亦为 128 passed（50 新合同、19 旧停牌安全、59 VIPDOC 价格精度），0 skip/xfail。`live/manifest.json`、`live/requests.json` 为新 public reader 的 12 个真实有界点、74 条原始响应，实际 exit 0；TDX 原始材料是完整 parser-returned rows，未声称 raw TCP。根代理独立校验 74 份 bytes/SHA、12 payload evidence_hash、真实 aware 时间和当前官方查询完整性，见 `independent-live-identity.json`。

最终保守日期修复没有再发网络请求，`final-replay-stock-interval-dates/manifest.json` 对已存的 74 条原始新 live 响应逐请求/SHA 重放，12/12 预期结果、exit 0，明确披露 actual-live-source 与 final-source 身份。不能把重放称为最终源码的新 live，也不能把旧 44 次调查或旧候选 PASS 当作本次新实现资格。

```ini
CURRENT_DECISION = FIX_ONLY
R2_1_AUTHORIZED = YES
STEP_1 = PASS
HISTORICAL_OPEN_EVIDENCE_CONTRACT = PASS
TDX_ETF_PRICE_REGRESSION = PASS
OFFICIAL_STOP_CONTROLS = PASS
LEGACY_SUSPENSION_SAFETY = PASS_19
STEP_2 = IN_PROGRESS
STEP_3 = NOT_EXECUTED
STEP_4 = NOT_EXECUTED
NEW_SOURCE_SHA = NOT_BUILT
NEW_WHEEL_SHA256 = NOT_BUILT
READY_FOR_OWNER_ACCEPTANCE = NO
RELEASE_AUTHORIZED = NO
PUBLISH_AUTHORIZED = NO
TAG_CREATED = NO
PYPI_UPLOAD = NO
```

A1–A6 来源层取得局部证据；A1–A3 的真实消费者/engine 部分以及 A7–A11 仍待 Step 2–4，不把来源测试冒充完整验收。尚无新候选 package 全套或消费者统一 Gate。范围变化仅为 Owner 已正式批准的 R2.1，无额外扩展。

交接：当前 v0.4.2 FIX_ONLY / Step 1 局部门禁通过，进入已授权 Step 2。原 CH commit `42bd44ef4d695aa3e88cfab4ebc3417660d0437a`，预存未提交修改保留；隔离副本无 .git、无新 commit。SIOS 实施基底为冻结 `84fd54fae0740bc06b1d250afa4578be29556956`，原工作树未写入。已确认 Step 1 缺陷均修复；有界范围、parser 价格及未知信息时间限制公开。推荐按既有授权完成独立执行输入、上海时钟和 snapshot/replay，逐步骤审查；这不代表下一 Phase 或发布获准。


## R2.1 Step 2 local Gate accepted — 2026-10-12

SIOS 隔离候选完成 R3/R4 接入，fresh 规格和质量审查均 APPROVED。运行源码 54 个文件的 manifest SHA256 为 `73376752616edc41b1560e0cea40a7cdb6190d2795c83dab34d19fdcffd4186f`，这是源码内容身份，不是新 Git commit。原冻结基底仍为 `84fd54fae0740bc06b1d250afa4578be29556956`；原仓和旧研究工件没有被改写。

独立 immutable `HistoricalOpeningEvidence` 保存规范化完整 JSON 和 hash，明确 `LEGACY` 与 `HISTORICAL_OPENING_R21`。仅精确 vendor `historical_suspension_unavailable` typed failure/helper 提供带来源、请求 digest 的 UNKNOWN 停牌覆盖缺口，旧 `fetch_tradability()` 仍失败。普通失败、absence/UNKNOWN、NOT_LISTED/DELISTED、side block、缺 master/规则不能被开盘正量覆盖；new mode 也检查 approved Master 的上市生命周期。旧 effective 09:30 不再冒充历史 information_available_at，未知保持 UNKNOWN。

执行事实只接入 `_activate → activate_pending_plans`，不进入策略 DecisionContext；T-close/PIT 过滤、raw open、滑点、费用、现金、手数、all-or-none 和 corporate action 算术保留。上海 09:15/09:30/15:30 时钟真实接入 Basic/OOS engine；旧 default UTC 和旧 kernel identity 保持。既有三个 CLI 入口增加窄、默认 LEGACY 的显式模式选择，旧 freeze/new mode 和新 freeze/legacy mode 双向错配均拒绝；没有重算原研究。

CanonicalDataset 的执行集合默认为 empty，旧 digest 不变；v2 默认、文件完整字节、snapshot ID 和 reader 双向兼容有冻结源码独立证明。新增 `v3-historical-opening` 独立分区保存完整证据，policy/clock/模式和全部 artifact checksum 在解析前核验；新 mode 不接受缺必要身份的旧 artifact。freeze kernel 只绑定 mode/policy/clock，避免冻结前读取未来 OOS execution facts；完整 facts digest 通过实际 v3 snapshot/data_snapshot_digest 进入 RunManifest identity。wiring 核对 dataset/facts 与 receipt，一项事实变化会改变真实 run identity。

证据在同名 evidence 的 `r21-step2/`：`source-vs-frozen.diff` 和 `summary.json` 列出 11 个 runtime、4 个测试、12 个 full-payload fixture、1 个合同文档的变化。`final.{json,log,xml,exit}` 实际 472 passed（39 新回归、433 旧受影响回归）、exit 0、零 failure/error/skip；根代理独立 `independent-final.*` 重跑也是 472 passed、exit 0，受测源码起止 hash 相同。初始失败和最小修复历史保留，包括移除误传的 corporate action 参数、修正 availability 旧断言，以及新 mode 的上市生命周期拒绝回归。

无 .git 导出所需的 code identity 仅在测试进程公开注入 runner/oos 的 resolver，值为实际 `source_tree_sha256:` 内容 hash；注入点、命令与起止身份留证，生产 `resolve_code_commit` 未改，也不把 frozen commit 当作新源码 commit。`replay-adapter-final.json` 是 12 点/74 原始响应经过真实 CH 0.4.2 函数、Library client、provider、domain 的离线重放，实际版本/import/path 和最终 hash 一致，不能称为新 live。`frozen-compat.json` 保留 v2 字节/digest/ID/reader 验证。

```ini
CURRENT_DECISION = FIX_ONLY
R2_1_AUTHORIZED = YES
STEP_1 = PASS
STEP_2 = PASS
STEP_3 = IN_PROGRESS
STEP_4 = NOT_EXECUTED
R3_SIOS_EXECUTION_ISOLATION = PASS_LOCAL
R4_SHANGHAI_CLOCK = PASS_LOCAL
NEW_SOURCE_SHA = NOT_BUILT
NEW_WHEEL_SHA256 = NOT_BUILT
READY_FOR_OWNER_ACCEPTANCE = NO
RELEASE_AUTHORIZED = NO
PUBLISH_AUTHORIZED = NO
TAG_CREATED = NO
PYPI_UPLOAD = NO
```

交接：v0.4.2 FIX_ONLY / Step 2 局部门禁通过，进入原已授权 Step 3。原 CH HEAD `42bd44ef4d695aa3e88cfab4ebc3417660d0437a`、原预存未提交修改保留；原 SIOS HEAD `fafdb6d3942ba52baa9480da7c8674dab1487f5d`，无本轮产品写入；隔离 export 无 .git、无新 commit。无已确认 Step 2 阻断或额外范围扩展。下一最小动作是按 R5 正式修订并真实验证 mandatory live，随后统一候选；局部通过不代表统一 Gate、Owner Acceptance、下一 Phase 或发布获准。

学习记录：当前问题是事后执行事实如何进入历史模拟且不变成早知策略数据。证据支持独立通道、精确缺口标识和版本化快照能保留该边界；仍未验证新候选的 mandatory live 和统一安装/消费者资格。下一决策为继续已授权的 Step 3 有界验证，无收益或策略资格结论。


## R2.1 Step 3 local Gate accepted — 2026-10-12

R5 的正式 mandatory 合同修订在隔离 SIOS 完成，fresh 规格和质量审查均 APPROVED。旧完整历史 PIT 停牌能力仍失败/UNKNOWN、information_available_at 未补造；新增事实只用于显式 HISTORICAL_OPENING_R21 执行模式。模型窗口为上海 `[09:30,09:31)`，不承诺全天正常、09:15 已知或整点具体委托成交。发布与下一 Phase 均未授权。

保留原五个 live test 名称、原四目标及日期范围，显式启用后实际 **5 PASS、0 failure/error/skip/xfail/deselect，exit 0**。54 个独立 capability outcome 全 PASS，包含四目标真实 corporate actions、RAW、freshness/stale 拒绝、calendar/units/history/pre_close、版本与原 pin 拒绝。四目标真实 opening 事实经 v3 snapshot/reader/full payload/digest/RunManifest 后进入实际 engine，各有正量 plan 和原 RAW-open/slippage/tick 规则的一个 Fill。513100/159509 仅是官方否决与执行拒绝对照，各有非空订单、SUSPENDED 拒绝、零 Fill，无 10:30 重试，不扩大 QDII 产品资格。

本步只改 `tests/qualification/live_qualification.py`、`test_chstockdata_etf_gate.py`、新增 `test_live_r21_contract.py` 及 `docs/contracts/historical-opening-execution-r21.md`；SIOS 的 54 个 runtime 文件逐项 hash 仍等于 Step 2 源码树 `73376752616edc41b1560e0cea40a7cdb6190d2795c83dab34d19fdcffd4186f`。新 opening reader 仍固定单主站、分页有界、无发现/重试；原 calendar 保留默认 freshness 和既有在线 fallback，最终实际 Sina 路由、stale=false，不能将整体 live run 称为所有来源均单主站。

证据位于同名 evidence 的 `r21-step3/`：`live-command.json`、`live.{log,xml,exit}`、`summary.json`、`all-capabilities.json`、`all-calls-coverage.json` 和 `step3-changes.diff`。最终111个实际观测调用的完整 HTTP/解析器返回数据均保留；根代理独立逐份验证 SHA/字节数，全部匹配，runtime 与资格源码起止一致。根代理最终离线验证17 PASS、5个原默认 live opt-in skip、exit 0；离线 skip 不算 mandatory live 豁免或成功。

先前 observer 序列化工具无效 run、真实4 PASS/1 FAIL run 均原样保留。六份真实 snapshot 本地 RED 定位 helper 的输入 tuple 顺序比较错误，canonical content_digest 实际相同；另补 bond 回归发现测试预定资金目标不足一手。仅修 helper 为完整 canonical digest 身份校验、统一明确足量目标，保留非空计划与原执行断言；六真实输入本地 GREEN 是诊断，不冒充新 live。最终5 PASS是再次真实执行结果，并绑定最终 helper hash。早先16-case根代理验证被最终17-case验证取代。

fresh quality 首次 REWORK 确认新离线测试直接要求实际 optional vendor 0.4.2，导致缺 vendor/合法旧 pin CI 失败；仅该离线测试改用既有 library= fake 注入。两环境各 RED 1 failure→GREEN 1 pass，根代理再次独立17 PASS/5原 opt-in skip。runtime、live helper、原五项 live 和合同文件字节不变，资格当前身份明确区分唯一更新的 offline 文件与原5 PASS所绑定 live 字节，无需重复网络。REWORK 历史与修复证据保留在 optional-vendor-rework/；同 reviewers 有限复核批准后才接受本步。

```ini
CURRENT_DECISION = FIX_ONLY
R2_1_AUTHORIZED = YES
STEP_1 = PASS
STEP_2 = PASS
STEP_3 = PASS
STEP_4 = IN_PROGRESS
R5_MANDATORY_LIVE_CONTRACT = PASS_LOCAL
NEW_SOURCE_SHA = NOT_BUILT
NEW_WHEEL_SHA256 = NOT_BUILT
READY_FOR_OWNER_ACCEPTANCE = NO
RELEASE_AUTHORIZED = NO
PUBLISH_AUTHORIZED = NO
TAG_CREATED = NO
PYPI_UPLOAD = NO
```

交接：当前 v0.4.2 FIX_ONLY / Step 3 局部门禁通过，按 Owner R2.1 已授权顺序进入 Step 4。原 CH HEAD `42bd44ef4d695aa3e88cfab4ebc3417660d0437a`、原预存修改与旧 wheel 保留；SIOS 冻结基底 `84fd54fae0740bc06b1d250afa4578be29556956`，隔离导出无 .git、无新 commit。无已确认 Step 3 阻断、无范围扩展。下一动作是构建独立新工件并实际重跑统一候选 Gate，不能把本步源码 live 成功当作 wheel 或统一候选成功。


## R2.1 Step 4 final candidate Gate accepted — 2026-10-12

当前为 v0.4.2 FIX_ONLY / Step 4 统一候选收口，fresh 规格与最终有限质量/整合审查均 APPROVED；根代理独立核验实际证据与工件后接受 **PASS_CANDIDATE**。已完成已授权 R1–R5 + R2.1 实施，停在 Owner Acceptance，Owner 正式验收仍 PENDING。实现完成、局部与统一候选 Gate 通过不构成发布或下一 Phase 授权。

正式能力边界保持：旧完整历史 PIT 停牌查询仍 UNKNOWN/fail-closed；新增历史开盘执行事实仅供显式 `HISTORICAL_OPENING_R21` 模式的冻结日线 `NEXT_SESSION_OPEN` 模拟使用。上海 `[09:30:00,09:31:00)` 的认证真实正成交活动、当前官方有界成功查询及全部已知官方停牌否决共同约束资格，官方阻断/冲突/错误/partial/未知继续安全拒绝。该结果只证明分钟内实际活动，不证明全天正常、完整历史状态、09:15 已知或09:30:00任意具体订单必然成交。R5 是 Owner 正式批准的验收合同调整，不是豁免，也不能称为“原完整历史停牌能力恢复”。

实际源码与可审查累计差异在隔离 `C:\Users\Administrator\.codex\visualizations\2026\10\10\01a125dd-33f2-78d3-abe7-45e0928975d0\v042-opening-implementation`，新 CH reader/known events/导出/可选 PDF parser、SIOS 独立事实/精确 typed gap/provider/engine/Shanghai clock/v3 snapshot/Basic-OOS 显式模式，以及永久回归和合同文档均保留。原价格/滑点/费用/资金/手数/all-or-none、T-close 与策略 PIT 不变。新模式不覆盖普通 UNKNOWN、上市生命周期、缺 master/规则或 side block。两 QDII halt 对照仅用于来源否决和执行拒绝，没有产品扩围。

最终 wheel `C:\Users\Administrator\.codex\visualizations\2026\10\10\01a125dd-33f2-78d3-abe7-45e0928975d0\v042-opening-implementation\dist\r21-qualified\chstockdata-0.4.2-py3-none-any.whl` SHA256 `3fd4f0b7334e310851495b8b13d4c7c55d21cde719acf9e00ff880ccb822f42e`，sdist SHA256 `306c07dd3a9534720cd2f93c6edb5b1a7a0e4a4a1f1d40ca3a71ba42d5bbf88b`。source-only SHA256 `5a5c9097abe4703d9bd709b55d824b7d41a954b89a1f053e6fd6385e7a18516c` 为765项文件内容 manifest，不是新 Git commit；构建前 envelope SHA256 `3c3c28fd696c9e4f66149cd3cf386b645ba603c03736cb9fab31ab863474779c` 保留。source-only 每个文件逐字节等于构建前 envelope 子集，并等于当前受测源；9项生成缓存/嵌入旧工件剔除、2项缓存漂移单独留证。身份范围修正没有改源码或工件；完整映射在 `source-only-identity.json` 和 `artifacts.json`。

最终所有资格使用同一新 wheel，六 profiles 每个41个安装包成员实际等于 wheel；sdist 的9个 test fixture 与源码精确相等。真实 package **774 PASS、1原 optional MCP skip、15原 network deselect**；独立 MCP profile 的 build_server/exports 通过。SIOS 全量 offline **973 PASS、5原默认 live opt-in skip**；provider67 PASS，Golden/ETF/parity165 PASS/5原skip。原五个 mandatory live 在独立 `final-live/` 实际 **5 PASS、零skip/xfail/deselect、exit0**，54项独立能力与四目标真实 actions、RAW、calendar、freshness/stale拒绝全部通过，111完整HTTP/解析器返回数据保留。四目标非空正量计划按原 RAW-open 规则各一个 Fill，两 halt controls 非空订单 SUSPENDED拒绝、零 Fill，无复牌自动补单。六actualv3snapshot/full facts/digest/RunManifest/policy/clock身份绑定留证；TDX raw是parser returned rows，不是TCP wire bytes。

四 ETF 原 native VIPDOC/day SHA、OHLC/pre_close Decimal零容差、SHARE/CNY/RAW/provenance **4/4**。最终安装 wheel 通过74个保存raw、12个有界点的离线重放，包含688432/000002及2016/2022样本；这是最终 reader 身份的确定性重放，不能冒充本步新的12点网络成功，未知日期/类型仍拒绝。原19项 historical suspension安全回归通过。

TA 原冻结九文件矩阵实际 **123 PASS、7个失败身份与消息和冻结baseline精确相同**，五项legacy probe通过，所以相对兼容PASS，不是全仓绿灯。**UNRESOLVED_RISK**：额外实际TA pipcheck exit1，继承的tradingagents-astock0.6 metadata仍要求chstockdata>=0.2,<0.3；原批准有限矩阵不含TA pipcheck，此既有依赖环境边界没有被抹除、修改formalpin或扩为新修复工程。完整历史PIT能力仍不提供，有限来源覆盖和模型假设继续作为明确合同边界。

本步必要源码修改只有 `MANIFEST.in` 递归打包fixtures，以及reader/对应test的12项最小lint修正。公开ValueError异常语义、Source观察与cleanup catch-all保留精确noqa合同理由；不是放宽运行时fail-closed。真实局部128 PASS、根代理独立128 PASS。原RH1 static24structured PASS、新增行0违规、287历史债务仍可见；无.git runner只公开注入真实RH1 baseline blob与candidate added ranges，生产脚本/ROOT/规则未改。compile/version/install/pipcheck（TA限制除外）/exports及core-sdist两console scripts真实help通过。SIOS source identity仅在测试进程公开注入，生产resolver不改，不将frozencommit冒充新源码commit。

失败/无效历史原样保留：首轮sdist漏fixture未验收工件、并行journal工具损坏、旧候选12lintFAIL、sandbox网络拒绝的真实4PASS/1FAIL、111来源成功但复用旧immutable snapshot目录导致的真实4PASS/1FAIL。修复路径/runner后在全新final-live目录重跑原5，未降低产品immutable规则或取消必需能力。新opening来源仍固定单主站/4秒/TDX最多9页/官方最多4页，无发现/重试；原calendar保留默认freshness与既有fallback，整体run不能称全部来源单主站。

根代理 `independent-final-verification.*` 实际exit0，独立核验765源文件、six×41安装成员、9fixture、全部JUnit真实counts、53必需零退出命令的log/exit/同source/wheel绑定和最终111raw SHA。fresh reviews留在 `spec-review.md`、`quality-review.md`。6007 frozen var before/after一致。原保护直接核验：CH758仅批准附加CR不同，SIOS244与TA986文件/head/status不变；原旧wheel SHA256 b76b065a06cd1d91868880a7b57584f598b6fd4cb42931e9a33700bc99a88c7a不变。旧wheel初次sandbox读取PermissionError后，用已授权scoped只读权限复核成功，没有覆盖原修改或研究。

```ini
CURRENT_DECISION = FIX_ONLY
R2_1_AUTHORIZED = YES
STEP_1 = PASS
STEP_2 = PASS
STEP_3 = PASS
STEP_4 = PASS_CANDIDATE
R1_OPEN_ACTIVITY_PROXY = PASS_APPROVED_MINUTE_MODEL
R2_OFFICIAL_SUSPENSION = PASS_BOUNDED_QUERY_AND_KNOWN_VETO
R2_1_BOUNDED_SOURCE_RULE = PASS
R3_SIOS_EXECUTION_ISOLATION = PASS
R4_SHANGHAI_CLOCK = PASS
R5_MANDATORY_LIVE_CONTRACT = PASS_FORMAL_CONTRACT_ADJUSTMENT
MOOTDX_0X0FB5_PRICE_REGRESSION = PASS
LEGACY_SUSPENSION_FAIL_CLOSED = PASS_19
A1 = PASS_CANDIDATE
A2 = PASS_CANDIDATE
A3 = PASS_CANDIDATE
A4 = PASS_CANDIDATE
A5 = PASS_CANDIDATE
A6 = PASS_CANDIDATE
A7 = PASS_CANDIDATE
A8 = PASS_CANDIDATE
A9 = PASS_CANDIDATE
A10 = PASS_CANDIDATE
A11 = PASS_CANDIDATE
PACKAGE_TESTS = 774_PASS_1_OPTIONAL_MCP_SKIP_15_ORIGINAL_NETWORK_DESELECT
SIOS_OFFLINE = 973_PASS_5_ORIGINAL_LIVE_OPTIN_SKIP
SIOS_GOLDEN_ETF_PARITY = 165_PASS_5_ORIGINAL_LIVE_OPTIN_SKIP
SIOS_PROVIDER_CONTRACT = 67_PASS
SIOS_MANDATORY_LIVE = 5_PASS_0_SKIP_XFAIL_DESELECT
TRADINGAGENTS_COMPATIBILITY = PASS_RELATIVE_123_PASS_7_IDENTICAL_BASELINE_FAILURES
NEW_SOURCE_SHA = 5a5c9097abe4703d9bd709b55d824b7d41a954b89a1f053e6fd6385e7a18516c
NEW_WHEEL_SHA256 = 3fd4f0b7334e310851495b8b13d4c7c55d21cde719acf9e00ff880ccb822f42e
UNRESOLVED_BLOCKERS = NONE_IN_APPROVED_MANDATORY_SCOPE
SCOPE_EXPANSION = NO
READY_FOR_OWNER_ACCEPTANCE = YES
OWNER_ACCEPTANCE = PENDING
RELEASE_AUTHORIZED = NO
PUBLISH_AUTHORIZED = NO
NEXT_PHASE_AUTHORIZED = NO
TAG_CREATED = NO
PYPI_UPLOAD = NO
```

交接：当前Step4完成并停Owner Acceptance。原CH HEAD `42bd44ef4d695aa3e88cfab4ebc3417660d0437a`，预存未提交修改保留，原仓本轮只追加CR/审计证据；隔离source export无.git、无新commit。SIOS冻结 `84fd54fae0740bc06b1d250afa4578be29556956`，原SIOS HEAD `fafdb6d3942ba52baa9480da7c8674dab1487f5d`未变；TA冻结 `14673992b9cd1d8a74e514027843be3298e029c7`，原TA HEAD `3f2704f3af572bf3f1b70fe0dc4ddd1c9972908c`及用户修改未变。所有已批准mandatory scope无残留阻断，无范围扩张；TA依赖限制和七项旧失败如实保留。建议下一动作是独立Owner验收本候选，未获得发布/合并/下一Phase授权。


## Owner Acceptance minimal REWORK — CONFIRMED_INTERVAL_DEFECT

Owner 独立验收发现最终候选000002持续停牌区间在已认证2016-07-04复牌日期之后仍错误否决：effective_end=None表示精确结束时刻未知，但此前适用判断将其无限延长。此前PASS_CANDIDATE历史保留，OwnerAcceptance仍PENDING；不能据旧live或审查PASS宣称本次新候选通过。当前重新进入FIX_ONLY最小REWORK，仅修该区间适用、补实际SIOS完整差异并重跑原同工件矩阵，无发布或下一Phase授权。

旧source manifest5a5c9097abe4703d9bd709b55d824b7d41a954b89a1f053e6fd6385e7a18516c、旧wheel3fd4f0b7334e310851495b8b13d4c7c55d21cde719acf9e00ff880ccb822f42e及旧r21-step4证据/ZIP完整保留。本轮新源位于隔离chstockdata-owner-rework，新证据owner-acceptance-rework-r1。停止条件为最小修复、完整SIOS差异和新候选实际验证证据完成后待Owner独立验收；不merge/push/tag/PyPI。

已补sios-source-vs-frozen.patch：实际Step4隔离SIOS相对84fd54fae0740bc06b1d250afa4578be29556956，31变化文件含18新增文件完整内容。256-file完整source/config/test/docs manifest SHA256为573c8540e094e2c2c1d82788541a65d42424c707fa307a06c73d330483c75eb5，patch SHA256 cbf403397631eed42fe542364587c3f75eb6150b88017c7390da2828644d4873。真实git apply --check与apply均exit0，explicit core.autocrlf=false后重建全部256文件逐字节等于真实受测manifest，54runtime仍为原73376752616edc41b1560e0cea40a7cdb6190d2795c83dab34d19fdcffd4186f。提供完整sios-tested-source.zip补充源码快照；未修改SIOS。首次工具继承autocrlf造成三个资格测试LF→CRLF的重建失败留证，不冒充重建成功。

```ini
CURRENT_DECISION = FIX_ONLY
OWNER_REVIEW_FINDING = CONFIRMED_INTERVAL_DEFECT
INTERVAL_REWORK = IN_PROGRESS
SIOS_SOURCE_DIFF_COMPLETE = YES
NEW_UNIFIED_GATE = NOT_EXECUTED
SCOPE_EXPANSION = NO
OWNER_ACCEPTANCE = PENDING
RELEASE_AUTHORIZED = NO
PUBLISH_AUTHORIZED = NO
NEXT_PHASE_AUTHORIZED = NO
```


### Owner REWORK r1 local interval and source-evidence Gate

fresh规格与质量均APPROVED，根代理独立150项确定性回归exit0。新增22项先RED13failed/9passed再GREEN22passed，旧原128项内容保留，包含19项旧停牌fail-closed及ETF十倍/VIPDOC精度；RH1实际24structured/新增行PASS，287旧债务可见。恰好修改opening_evidence.py、opening_known_events.json及对应回归test；对旧765源码与旧wheel逐项复核未变。内部packaged对象获得认证日期适用资格，setdefault保留其先入身份；caller/current自称verified或日期/来源字段不能自行结束其他区间。复牌日精确时刻仍UNKNOWN，之后旧区间不再否决但官方当前query/pagination/TDX/其它资格仍需满足；原effective_end=None及来源/provenance保留。SIOS全256源码与真实受测/重建/snapshot一致，31差异含18新增完整内容，未修改SIOS。

本步INTERVAL_REWORK=PASS_LOCAL，SIOS_SOURCE_DIFF_COMPLETE=YES；新统一候选尚未通过，READY_FOR_OWNER_REVIEW=NO。当前按Owner已授权范围构建独立新工件并实际重跑原统一矩阵，旧live不能作为本次新候选PASS。


### Owner REWORK r1 final candidate and evidence closeout — 2026-10-13

CURRENT_DECISION 保持 FIX_ONLY。Owner 指出的持续区间缺陷已确认并作最小修复；此前 Step4 PASS_CANDIDATE、旧 source/wheel/live/ZIP 历史保留。本节为本次独立新候选的实际验证结果，Owner Acceptance 仍 PENDING。

仅修改隔离候选的 `src/chstockdata/opening_evidence.py`、`src/chstockdata/opening_known_events.json`、`tests/test_historical_opening_evidence.py`。对内部加载的认证事件，2016-07-04 之后不再沿用旧停牌否决；复牌日精确时刻未知，仍返回 UNKNOWN。未合成 effective_end 或开盘时间；原始事件、来源 SHA、完整 provenance 保留。调用方自称的 resume_date/verified/来源字段不能自行解除官方阻断。后续日期仍逐项经过原当前官方查询、有效分页/来源语义、真实合格 TDX 开盘活动及其它门禁；复牌日期本身不能证明正常交易。

新增22项确定性回归先 RED（13 failed / 9 passed）再 GREEN（22 passed），根代理直接相关150项独立回归 PASS，保留原19项历史停牌 fail-closed 与 ETF十倍价格/VIPDOC 精度回归。RH1 24项结构约束/新增行检查 PASS，287项既有债务保留。未改变 R1–R5、R2.1、策略 PIT、日线 NEXT_SESSION_OPEN 的 [09:30:00,09:31:00) Asia/Shanghai 分钟近似或交易算术；该窗口证明实际交易活动，不承诺09:30:00整点/具体订单成交。旧完整历史 PIT 停牌查询仍 UNKNOWN/fail-closed，R5仍为 Owner批准的验收合同调整。

独立新 wheel/sdist 已实际构建并通过原 package Gate、SIOS offline/Golden/ETF、原五项 mandatory live、冻结 TA相对兼容矩阵及 A1–A11 原定证据映射。结果如下：

| 本轮验证 | 实际结果 |
| --- | --- |
| package | 796 PASS，1原 optional MCP skip，15原 network deselect |
| SIOS provider | 67 PASS |
| SIOS Golden/ETF parity | 165 PASS，5默认 live opt-in skip |
| SIOS offline | 973 PASS，5默认 live opt-in skip |
| 五项原 mandatory live | 5 PASS，0 skip/xfail/deselect；54能力 PASS；129份本轮新 raw |
| 新安装 wheel 区间回归 / ETF Decimal exact | 22 PASS / 4 PASS |
| TradingAgents 相对冻结基线 | 123 PASS + 7 FAIL；失败节点与 message 同基线，legacy 5 PASS |
| 12点/74 raw 保存数据回放 | 新安装 wheel offline PASS，不能作为本轮新增 live 资格 |

73条实际命令保留，65条 mandatory 零退出；TA实际exit1及工具/换行/沙箱失败尝试保留，未隐藏。构建/twine、compile、静态、core/sdist/MCP/baostock/SIOS profiles、两 CLI、MCP server 等原检查通过。TA既有七项失败及正式依赖限制保留，未修改 TA 源码或依赖，TA pip check 为原非mandatory项，本轮未重跑。`gate/A1-A11-evidence-map.json`绑定同一工件与原测试，未扩张范围或改变成功标准。

本轮根代理独立只读复核：765文件源码、6 profiles各41个包成员、sdist 9 fixtures、六组JUnit/73命令与日志/退出/引用文件 SHA、129份实际live raw长度/哈希、source-before/after均一致。新的Gate规格与质量审查均 APPROVED，仅支持 PASS_CANDIDATE。旧live PASS未用于新候选PASS。原6007文件冻结var不变。

SIOS完整 `sios-source-vs-frozen.patch` 相对冻结commit `84fd54fae0740bc06b1d250afa4578be29556956`，31变化文件含18新增文件全文。真实 frozen 238文件 + 补丁可重建全部256个实际受测 source/config/test/docs 文件；patch apply/check均exit0，完整manifest、实际源码、重建目录和 `sios-tested-source.zip` 逐字节一致。source canonical SHA `573c8540e094e2c2c1d82788541a65d42424c707fa307a06c73d330483c75eb5`，runtime SHA `73376752616edc41b1560e0cea40a7cdb6190d2795c83dab34d19fdcffd4186f`，patch SHA `cbf403397631eed42fe542364587c3f75eb6150b88017c7390da2828644d4873`。本轮未修改 SIOS；实际组合受测身份已绑定，未用原GitHub HEAD或冻结源码替代。

新 CH canonical source SHA256（765文件映射）为 `d81fb0a62a9fa4cc9823ca9ad1920f380a110d50351dd0b7b465f735d3021572`；`rework-source-manifest.json` 文件本身SHA `07c0abadfd48ad5d6ef0f9410136486c3c5d71e09b0d0b00a2b78e911640e1f7`，两者范围不同，NEW_SOURCE_SHA256使用前者。新 wheel SHA `1dd58350678fbb07d3b545165708d814f93fb94f965dc2da33bad2fab7ff779c`；新 sdist SHA `6bd99e8c3b513c9ac0676b46ef8a0edf7e1f2a98d880c931db3036a7da884fa2`。新工件位于 `dist/owner-rework-r1`，六环境位于 `profiles/owner-rework-r1`，均独立于旧候选。交付 ZIP 包含新 wheel/sdist、完整765文件CH源码快照、SIOS完整快照/补丁/重建、全部实际证据及本审计副本。

保护复核：原CH HEAD `42bd44ef4d695aa3e88cfab4ebc3417660d0437a`，早期758基线文件仅既有CR追加不同；用户预存产品修改保留。原SIOS HEAD `fafdb6d3942ba52baa9480da7c8674dab1487f5d`未变；同期原仓一份决策文档修改及一份新增research文档与早期基线不同，本轮未写入原SIOS，已保留并如实记录，隔离受测256文件不变。原TA HEAD `3f2704f3af572bf3f1b70fe0dc4ddd1c9972908c`，986文件及原工作树状态未变。旧765文件source、旧wheel `3fd4f0b7334e310851495b8b13d4c7c55d21cde719acf9e00ff880ccb822f42e`、旧Step4 ZIP `a94de2c4ce72a4e98ffad9b0fa2dfdb93833623832078dcb5d2373b23d7e8b8d`未变。

```ini
CURRENT_DECISION = FIX_ONLY
OWNER_REVIEW_FINDING = CONFIRMED_INTERVAL_DEFECT
INTERVAL_REWORK = PASS
SIOS_SOURCE_DIFF_COMPLETE = YES
SCOPE_EXPANSION = NO
PACKAGE_TESTS = PASS_796_PLUS_1_ORIGINAL_OPTIONAL_SKIP_15_ORIGINAL_NETWORK_DESELECT
SIOS_OFFLINE = PASS_973_PLUS_5_DEFAULT_LIVE_OPTIN_SKIP
SIOS_MANDATORY_LIVE = PASS_ACTUAL_5_ZERO_SKIP_54_CAPABILITIES
TRADINGAGENTS_RELATIVE_COMPAT = PASS_RELATIVE_123_PLUS_7_IDENTICAL_BASELINE_FAILURES
NEW_WHEEL_SHA256 = 1dd58350678fbb07d3b545165708d814f93fb94f965dc2da33bad2fab7ff779c
NEW_SOURCE_SHA256 = d81fb0a62a9fa4cc9823ca9ad1920f380a110d50351dd0b7b465f735d3021572
READY_FOR_OWNER_REVIEW = YES
OWNER_ACCEPTANCE = PENDING
RELEASE_AUTHORIZED = NO
PUBLISH_AUTHORIZED = NO
NEXT_PHASE_AUTHORIZED = NO
```

交接：v0.4.2 / R2.1，Owner minimum REWORK r1，新统一Gate PASS_CANDIDATE。原CH基线commit不变，工作树有原用户修改及本轮审计/证据追加；候选为无.git的隔离源码快照，无新commit。已确认缺陷修复、完整SIOS差异、新候选重新验证全部完成，mandatory批准范围无残留阻断，scope expansion NO；TA基线失败/依赖限制和来源能力边界保持可见。推荐下一动作仅Owner独立验收；到此停止，不merge、push、tag、PyPI或进入下一Phase。
