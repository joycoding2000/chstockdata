# DR04-P 回归阻断最小修复 — 验证准备受阻

- CURRENT_SHA: `0dc85e3e43588c5781771486a3c6f80c4be7714f`，未提交，暂存区为空，Owner既有改动保留。
- ROOT_CAUSE_FIXED: 已应用测试局部修复，**尚未验证通过**。动态门禁 `_run` 仅在执行Git时增加 `-c safe.directory=<当前tmp_path>`，仍调用原 `_run`、真实diff及行号判别。
- CHANGED_FILES: 本轮测试修改仅 `tests/test_rh1_git_line_endings.py`（增加monkeypatch参数及局部包装）；另新增本报告、采证脚本和日志。生产门禁、DR04-P代码、接口、依赖、消费合同、Git宿主配置未修改。
- FOCUSED_TEST_RESULTS: 两项均为setup ERROR，pytest退出1；测试体及三个CRLF断言都未执行，不能声称修复成功。
- P01_P12_RESULTS: 本轮未运行；按前置两项须通过的顺序停止。历史通过证据仍保留，不替代本轮验证。
- REGRESSION_RESULTS: 本轮未运行。
- LEGACY_COMPATIBILITY: 产品源码、公共导出及生产门禁SHA-256与本轮操作前一致；未重新验证兼容性。
- SCOPE_DEVIATION: 无产品范围扩展；新增采证脚本的临时目录准备错误导致验证阻断。
- DR04_P_VERDICT: **BLOCKED_VALIDATION_SETUP**，不报告PASS_CANDIDATE。
- OWNER_ACCEPTANCE_READY: **NO**，停在Owner Review。

## 修复差异

测试增加局部 `run_with_repo_trust`，通过monkeypatch作用于当前用例动态加载的门禁模块；非Git调用保持原样，未修改生产门禁。三个原始判别断言的AST与修复前完全一致，见[断言采证结果](evidence/2026-10-18-dr04-p-regression-fix/assertion-execution.json)。差异见[test-fix.diff](evidence/2026-10-18-dr04-p-regression-fix/test-fix.diff)。

## 新阻断及停止

采证脚本 `verify.py prepare` 记录了新的临时父目录路径，却未创建该父目录。随后 `focused` 使用其子目录作为pytest `--basetemp`；pytest初始化该目录时抛出：

```text
FileNotFoundError: [WinError 3]
D:\Dev\Projects\chstockdata\.pytest_cache\dr04-p-git-fix-642ab812aa7f\focused
```

这是本轮新增采证脚本的准备错误，不能归因于产品或原CRLF断言。两个用例均未进入测试体；`assertion-execution.json`记录两例执行的断言行均为空，不能以“断言未改”推断断言通过。按Owner“出现不同新失败即停止”的条件，未修正脚本、未重跑或扩大测试。

## 实际命令与证据

在仓库根目录执行：

```text
.venv\Scripts\python.exe docs\audits\evidence\2026-10-18-dr04-p-regression-fix\verify.py prepare
.venv\Scripts\python.exe docs\audits\evidence\2026-10-18-dr04-p-regression-fix\verify.py focused > docs\audits\evidence\2026-10-18-dr04-p-regression-fix\focused.stdout.txt 2> docs\audits\evidence\2026-10-18-dr04-p-regression-fix\focused.stderr.txt
```

prepare退出0，focused退出1；focused内部仅选择 `[False]`、`[True]` 两项，精确pytest参数见[assertion-execution.json](evidence/2026-10-18-dr04-p-regression-fix/assertion-execution.json)。

- [focused.stdout.txt](evidence/2026-10-18-dr04-p-regression-fix/focused.stdout.txt)：完整两项setup错误
- [focused.xml](evidence/2026-10-18-dr04-p-regression-fix/focused.xml)：JUnit结果
- [summary.json](evidence/2026-10-18-dr04-p-regression-fix/summary.json)：HEAD、受保护文件/配置哈希核对及结果
- [before.diff](evidence/2026-10-18-dr04-p-regression-fix/before.diff)：操作前已存在的tracked变更

当前步骤为DR04-P回归测试最小修复及验证，HEAD未变，本次补丁保留为未暂存改动。后续最小动作是Owner允许修正采证临时父目录准备并重跑同两项；仅两项通过且确认全部原断言执行后，才运行既定合同及回归集合。没有提交、推送、发布、豁免或进入DR04-M。
