# DR04-P 两项回归失败根因调查

- CURRENT_SHA: `0dc85e3e43588c5781771486a3c6f80c4be7714f`，调查前后不变；既有 DR04-P 未暂存/未跟踪变更保留。本轮仅新增调查报告与证据。
- FAILED_TESTS: `tests/test_rh1_git_line_endings.py::test_crlf_preserves_added_line_discrimination[False]`、`[True]`。
- FAILURE_SIGNATURES: 两项均在测试第43行调用门禁 `_added_line_ranges()`，由 `scripts/check_rh1_static.py:116` 抛 `RuntimeError`。本轮捕获底层 Git 退出129，pytest退出1；CRLF判别断言尚未执行。
- BASELINE_RESULTS: 已发布 `v0.4.2` 提交 `17af23fe8183f740150dc01dd877473afe3911b7` 的独立干净源码快照，**2 failed**；与候选逐项具有相同调用、错误及所有权拒绝根因。
- CANDIDATE_RESULTS: 当前 DR04-P 工作区只运行指定两项，**2 failed**。
- ENVIRONMENT_DIFFERENCES: 同一 Python 3.14.5、pytest 9.1.1、Git 2.53.0.windows.1、解释器及 Git 可执行文件、继承环境和配置。两边仅源码根及独立临时目录不同；已证实 baseline 加载 baseline/src 包，candidate 加载当前 src 包，没有串用候选产品代码。
- CHANGE_RELATION: 失败测试、门禁脚本、conftest及pyproject在两边逐字节相同。DR04-P 仅新增数值模块及公开导出/文档/独立测试fixture；没有修改本失败链。失败来自既有测试与当前 Git 仓库所有权检查的交互，不由本次 DR04-P 引入。
- ROOT_CAUSE_CLASSIFICATION: **ENVIRONMENT_OR_TEST_DEFECT**，并有 **BASELINE_REPRODUCED（同根因）** 证据；不是仅凭“两边都失败”归类。
- MINIMUM_CORRECTIVE_ACTION: 后续若获授权，仅使测试调用的门禁 Git 读取继承测试已有的、限定到该临时目录的信任上下文，然后只复验这两项，保持CRLF断言。本轮没有修复、修改配置、豁免或验证修复后结果。
- DR04_P_GATE_RECOMMENDATION: 提交 **Owner Review**。两项属于基线测试/环境阻断，不能据此归咎于 DR04-P 产品变更；原失败状态保留，Owner决定后续最小修复与再验。本调查不宣布 DR04-P PASS/PASS_CANDIDATE、不授予下一阶段权限。

## 原始失败定位

原[regression.txt](evidence/2026-10-18-dr04-p-implementation/regression.txt)第4–10行与140–146行分别对应False/True；第277–279行是两项失败汇总与 `2 failed, 132 passed`。原日志未记录底层 Git 数字退出码，129来自本次同签名复现；原轮pytest退出1见实施执行记录，本轮另独立捕获1。

原执行命令完整保存在[实施报告](2026-10-18-dr04-p-implementation.md)的“审查与验证”部分，本轮未重跑其中其余测试。

报错链：

```text
test_rh1_git_line_endings.py:43 -> gate._added_line_ranges()
check_rh1_static.py:104 -> _run("git", "diff", "--no-ext-diff",
    "--ignore-cr-at-eol", "--unified=0", <临时库初始提交>, "--", "src", "tests")
check_rh1_static.py:116 -> RuntimeError: git diff failed:
warning: Limiting comparison with pathspecs is only supported if both paths are directories.
usage: git diff --no-index ...
```

原轮保留的两个临时库也分别进行了 `git rev-parse --show-toplevel` 只读探测，均退出128并直接报告 `detected dubious ownership`。详见 [original-signatures.json](evidence/2026-10-18-dr04-p-failure-investigation/original-signatures.json)，包括原日志哈希、精确行号及探测结果。

## 同根因证据链

1. 两边每个用例的原测试helper均使用 `git -c safe.directory=<tmp> -c core.autocrlf=false ...`。`init`、两次本地fixture身份配置、`add`、`commit`、`rev-parse HEAD`、CRLF更新后的第二次`add`全部退出0；每例随后门禁的裸 `git diff` 退出129。每边退出码序列均为 `[0,0,0,0,0,0,0,129]` 重复两次。
2. 测试创建的 `.git`、HEAD、初始提交均实际存在。每份 `src/sample.py` 都是6个LF且全部为CRLF。初始化及CRLF字节写入已完成，异常发生于门禁的Git命令执行，不是换行断言或产品取数代码。
3. 门禁 `_run` 没有携带helper的目录限定 `safe.directory`。原轮两个临时库、本轮candidate两个临时库、baseline两个临时库，裸 `git rev-parse --show-toplevel` 全部以128退出并指出：目录所有者为 `BUILTIN/Administrators` 组，当前进程为Administrator用户，因所有权不匹配拒绝信任。Git diff输出同时显示no-index模式的usage及pathspec限制；其外部症状掩盖了仓库信任问题。所有权拒绝由直接诊断证实，Git内部转入no-index的路径依据该错误输出推断。
4. 同一临时库中，带测试原有目录限定信任参数的helper可识别HEAD，而未带参数的门禁不能完成仓库读取；这一上下文差异解释了初始化成功但diff失败。
5. 两边测试、脚本、conftest、pyproject逐字节一致，调用参数结构/阶段、129错误全文、128所有权拒绝原因一致。原轮失败位置、签名以及原临时库所有权诊断也一致。因此确认同根因复现，而非独立的两种失败。

没有执行Git错误信息中建议的global safe.directory写入命令。未修改宿主、当前仓库的Git配置；原测试仅按既有代码在自己创建的临时fixture仓库中写入身份，这是运行原测试的必要步骤。

## 对照方法和精确命令

基线通过 `git archive --format=zip 17af23fe8183f740150dc01dd877473afe3911b7` 在独立新目录解包，不复制当前改动，不创建产品提交，不增加worktree元数据。当前 `core.autocrlf=true` 导致部分归档文本使用CRLF；四个关键文件与候选工作区逐字节一致，按LF规范化后与发布提交blob一致，身份记录见 [setup.json](evidence/2026-10-18-dr04-p-failure-investigation/setup.json)。基线源码快照无需自身.git：受测函数的ROOT与BASELINE_SHA按原测试重定向到其新建fixture仓库。

可审阅的[旁路观测脚本](evidence/2026-10-18-dr04-p-failure-investigation/observe.py)在独立子进程中运行原pytest用例，只记录 `subprocess.run` 原实参/返回值/异常，不更改它们；不修改测试、产品或门禁源码。每个标签只运行一次两项测试，无缓存写入插件、无新增pytest豁免。

父执行命令：

```powershell
.\.venv\Scripts\python.exe docs/audits/evidence/2026-10-18-dr04-p-failure-investigation/observe.py
```

两个子进程均使用同一绝对解释器 `D:\Dev\Projects\chstockdata\.venv\Scripts\python.exe`。以下pytest参数完全相同，仅label对应的basetemp和输出文件不同：

```text
tests/test_rh1_git_line_endings.py::test_crlf_preserves_added_line_discrimination[False]
tests/test_rh1_git_line_endings.py::test_crlf_preserves_added_line_discrimination[True]
-vv --tb=short -p no:cacheprovider
--basetemp=D:\Dev\Projects\chstockdata\.pytest_cache\dr04-p-investigation-d6edb4b21fba\<candidate或baseline>-pytest-temp
--junitxml=D:\Dev\Projects\chstockdata\docs\audits\evidence\2026-10-18-dr04-p-failure-investigation\<candidate或baseline>.xml
```

实际cwd及逐个未省略的pytest参数、加载包路径分别见 [candidate-environment.json](evidence/2026-10-18-dr04-p-failure-investigation/candidate-environment.json) 和 [baseline-environment.json](evidence/2026-10-18-dr04-p-failure-investigation/baseline-environment.json)。两个子进程退出1；父观测脚本完成采证后退出0，不代表测试通过。

精确命令/输出/退出码和fixture提交SHA：

- [candidate-git-calls.json](evidence/2026-10-18-dr04-p-failure-investigation/candidate-git-calls.json)、[baseline-git-calls.json](evidence/2026-10-18-dr04-p-failure-investigation/baseline-git-calls.json)
- [candidate.stdout.txt](evidence/2026-10-18-dr04-p-failure-investigation/candidate.stdout.txt)、[baseline.stdout.txt](evidence/2026-10-18-dr04-p-failure-investigation/baseline.stdout.txt)
- [diagnostics.json](evidence/2026-10-18-dr04-p-failure-investigation/diagnostics.json)：四个复现临时库的所有权错误、HEAD、配置和CRLF字节统计
- [summary.json](evidence/2026-10-18-dr04-p-failure-investigation/summary.json)：结果及归属汇总
- [candidate-tracked.diff](evidence/2026-10-18-dr04-p-failure-investigation/candidate-tracked.diff)：调查前实际产品/README diff

## 停止与交接

当前为DR04-P两项失败根因调查，已定位后停止；没有执行修复或扩大测试范围。产品源码、测试、pyproject、相关Git配置文件调查前后SHA-256一致；HEAD和暂存区不变，既有未提交文件未清理。新报告和证据未提交，临时对照目录保留以供审阅。

Gate仍停在Owner Review。已确认本次两项阻断的基线/环境归属；修复后断言是否通过尚未执行，不能推定。推荐Owner决定是否授权上述最小测试上下文修复及两项复验；不进入DR04-M。
