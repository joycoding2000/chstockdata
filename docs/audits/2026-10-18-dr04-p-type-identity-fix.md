# DR04-P 原始类型身份碰撞最小修复

- CURRENT_SHA: `0dc85e3e43588c5781771486a3c6f80c4be7714f`，未变；暂存区为空，既有Owner改动保留。
- ROOT_CAUSE_FIXED: **YES**。原有展示用 `raw_record` 不再用于身份判断；局部 `_raw_identity` 对每个JSON节点标明number/string/object/array/boolean/null，容器递归保留类型。源端对象或数组不能伪装成内部数值标签。记录去重及既有页/锚相等检查均使用该身份。
- CHANGED_FILES: 业务修复仅 `src/chstockdata/daily_fund_flow.py`，回归仅 `tests/test_daily_fund_flow.py`；另新增本报告与确定性采证材料。所有原有测试保持原样，仅追加8项实例。
- NEW_REGRESSION_RESULTS: 修复前 **6 failed、2 passed**，失败均复现身份碰撞；修复后 **8 passed**，退出0。
- P01_P12_RESULTS: 原12组41个合同实例及4个辅助实例全部通过，共45项。
- FULL_REGRESSION_RESULTS: 既定134项逐项匹配最终JUnit且全部通过；新增8项亦通过，合计 **142 passed in 9.73s**，0失败、0错误、0跳过。新增模块及测试Ruff检查通过。
- COVERAGE_SEMANTICS: 合法数值与非法对象同日出现时，正反顺序均保留两种原始类型及出处，规范金额为空、DUPLICATE_CONFLICT、PARTIAL，数值完整及语义可用均为0/1。完全相同合法记录仍合并为一variant、保留两份出处，覆盖只计一次。数值1与字符串"1"身份不同但金额含义一致，保留两variant而覆盖为1/1。number/string/object/array/boolean/null同日混合时六种身份均保留，不吞并非法信息。
- LEGACY_COMPATIBILITY: 公开函数签名、原值展示格式、金额/质量/覆盖判定规则不变；既有文本接口、FetchResult、公开导出、HTTP调用和预算逻辑不变，相关回归通过。
- SCOPE_DEVIATION: **NONE**。没有改冻结合同、分页流程、请求/重试预算、其他能力、依赖或部署配置，没有新增数据库/持久缓存。页和锚的调整仅替换有碰撞的身份表示，相应停止策略保持。
- DR04_P_VERDICT: **PASS_CANDIDATE**，停在Owner Review，不代表Owner Acceptance。

## 修复和最小验证

原缺陷是展示编码把JSON number `1` 转成 `{"json_number":"1"}`，随后仅比较该展示结构，误将源端非法对象当作相同记录。新身份只在当前调用内部使用，不增加公共结果字段，也不改已公开的 `raw_record`/`raw_type`/`raw_value` 格式。非法对象通过现有 `_value` 保留 INVALID_VALUE/INVALID_TYPE；现有同日冲突汇总逻辑将规范金额置空。

新增8个实例全部经过公共 `get_sina_daily_fund_flow`，仅隔离HTTP响应，不绕过解析、身份或覆盖路径：

| 检查 | 实例数 | 结果 |
|---|---:|---|
| number与对象 `{"json_number":"1"}`，正反顺序 | 2 | 两variant、非法原因及出处保留、冲突金额空、有效覆盖0/1 |
| 六种JSON原始类型混合，正反顺序 | 2 | 六variant无身份碰撞，PARTIAL，有效覆盖0/1 |
| number与等值数字字符串 | 1 | 两种身份均保留，数值覆盖只计1 |
| 完全相同的合法数值记录 | 1 | 正确去重、两份出处、覆盖只计1 |
| 第一页/锚复核间的同类碰撞，正反顺序 | 2 | ANCHOR_DRIFT/UNKNOWN、保留两版本、规范金额空，五日数值/语义覆盖4/5 |

所有异常均为内存合成，不修改原始fixture或发起市场请求。

## 命令与证据

仓库根目录实际运行：

```text
.venv\Scripts\python.exe docs\audits\evidence\2026-10-18-dr04-p-type-identity-fix\verify.py prepare
.venv\Scripts\python.exe docs\audits\evidence\2026-10-18-dr04-p-type-identity-fix\verify.py red
.venv\Scripts\python.exe docs\audits\evidence\2026-10-18-dr04-p-type-identity-fix\verify.py focused
.venv\Scripts\python.exe docs\audits\evidence\2026-10-18-dr04-p-type-identity-fix\verify.py full
.venv\Scripts\python.exe -m ruff check src/chstockdata/daily_fund_flow.py tests/test_daily_fund_flow.py
.venv\Scripts\python.exe docs\audits\evidence\2026-10-18-dr04-p-type-identity-fix\finalize.py
```

red在生产修复前执行，退出1符合预期；其余命令退出0。每次pytest精确命令、临时目录和退出码见各 `*-command.json`，未覆盖旧证据：

- [red.stdout.txt](evidence/2026-10-18-dr04-p-type-identity-fix/red.stdout.txt)、[red-command.json](evidence/2026-10-18-dr04-p-type-identity-fix/red-command.json)
- [focused.stdout.txt](evidence/2026-10-18-dr04-p-type-identity-fix/focused.stdout.txt)、[focused-command.json](evidence/2026-10-18-dr04-p-type-identity-fix/focused-command.json)
- [full.stdout.txt](evidence/2026-10-18-dr04-p-type-identity-fix/full.stdout.txt)、[full.xml](evidence/2026-10-18-dr04-p-type-identity-fix/full.xml)、[full-command.json](evidence/2026-10-18-dr04-p-type-identity-fix/full-command.json)
- [summary.json](evidence/2026-10-18-dr04-p-type-identity-fix/summary.json)：逐组结果、134原用例映射及保护文件哈希
- [module.diff](evidence/2026-10-18-dr04-p-type-identity-fix/module.diff)、[tests.diff](evidence/2026-10-18-dr04-p-type-identity-fix/tests.diff)：仅本轮相对操作前的必要修改，包含原先未跟踪文件的差异

finalize独立核对：既有tracked diff未变、其他保护源码及合同/配置哈希未变、原45项测试文本完整保留、公开签名及展示函数未变、HTTP/预算fetch函数AST未变。既定134项全部存在于本轮142项成功记录中。

## 交接

当前阶段/步骤：DR04-P原始类型身份碰撞修复及确定性验收完成，供Owner Review。HEAD未变，工作区保留既有未提交改动及本轮两个文件的修改；未暂存、提交、推送或发布。

当前范围无未解决阻断，无范围扩展。建议Owner审阅本轮差异与RED/GREEN证据。首次可知、终局及修订仍UNKNOWN；P候选通过不证明全市场、历史PIT或S08资格，不进入DR04-M。
