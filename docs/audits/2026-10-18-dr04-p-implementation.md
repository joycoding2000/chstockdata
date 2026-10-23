# DR04-P 实施与离线验收交接

- CURRENT_SHA: `0dc85e3e43588c5781771486a3c6f80c4be7714f`，与实施前一致。
- IMPLEMENTATION_SCOPE: DR04-P 公共数值能力、P01–P12 离线验收；实施已落入工作树，最终回归出现失败后按 Owner 停止条件停止。未提交、推送、发布或进入 DR04-M。
- PUBLIC_API: `get_sina_daily_fund_flow`、`FundFlowCalendar`、`FundFlowBudget`、`DailyFundFlowResult` 均由包级公开导出。调用及状态说明见[消费文档](../dr04-p-daily-fund-flow.md)。
- SOURCE_AND_FIELD: 固定新浪 `MoneyFlow.ssl_qsfx_zjlrqs` / `r0_net`，CNY/元；不调用 TDX 或合成其他资金定义。
- PRECISION_AND_MISSING: 原始类型/值及字节证据保留；JSON 数值 token 不经 float，金额为 Decimal 可精确解释的字符串。原始零、缺日、缺字段、null/空串、非法数值、冲突及请求未决分开。零的经济语义 UNKNOWN。
- HISTORY_AND_PAGINATION: 调用方提供有来源/版本及覆盖边界的合格日历；五日逐日对齐、历史闭区间分页；页/请求/重试/墙钟预算及停止原因明确。多页以额外第一页复核检查观测锚；不能据此证明源端冻结快照。两只真实年度 fixture 各243/243目标日，额外17旧日单列。
- P01_P12_RESULTS: 12组均通过，共41个参数化合同实例；另有4个身份/fixture完整性实例通过，模块合计45项通过。
- REGRESSION_RESULTS: 最终合并运行 **132 passed, 2 failed**，退出码1。45项为新增测试，既有测试87项通过、2项失败。新模块/测试 Ruff 通过；按CRLF仓库设置检查的 tracked diff 无空白错误。
- LEGACY_COMPATIBILITY: `a_stock.py`、既有 `get_fund_flow(...)->str`、通用 FetchResult、依赖及版本均未修改；既有资金流及接口相关回归通过。不能因这些通过而忽略最终2项失败。
- SCOPE_DEVIATION: 无产品范围扩展。没有持久化原文库、修订事件账本或新缓存平台。`previous_observation` 只携带同请求旧观测证据，不把旧数据当成本次成功。首次可知、源修订及终局维持 UNKNOWN。
- DR04_P_VERDICT: **BLOCKED_TEST_FAILURE**；不形成 PASS_CANDIDATE，不宣布 Owner Acceptance。
- NEXT_GATE: **Owner Review**。建议决定是否单独授权继续排查下面2项Git临时仓库测试失败；本轮不修改其测试或静态门禁脚本，不擅自降低条件。下一阶段未获授权。

## 合同与证据身份

Owner 指定合同（只读）：`D:\Dev\Projects\mishi-radar\outputs\dr04-minimum-consumer-contract-2026-10-17\dr04-minimum-consumer-contract-owner-review.md`，SHA-256 `1c7c37b1514032ef08d9714fe8cfa4f722c0f730af1e58608dbc6b45eaffeba1`。已完整读取 REQUIRED_FIELDS、ERROR_AND_STALENESS、HISTORY_AND_TIME_LIMITS 和 ACCEPTANCE_CASES；Owner 本会话批准及后续两项限定覆盖提案文档原有“待批准”状态。

只读重算原清单70项及请求日志43份原文哈希，全部匹配；其中测试复制30份资金响应及原日历，原件不变，新市场请求0。复制身份、原始时间及哈希见 [fixture manifest](../../tests/fixtures/daily_fund_flow/manifest.json)。异常输入均在内存构造，不改真实原文、不声称在线发生。

已发布 v0.4.2 tag 为 `17af23fe8183f740150dc01dd877473afe3911b7`；实施前HEAD相对该tag仅有README及发行记录差异，无发行代码差异。原有未跟踪审计资料全部保留。

## P01–P12 原表映射

| 组 | 通过实例数 | 关键证据 |
|---|---:|---|
| P01 | 1 | 600000原始正负值、49.0000小额、超float精度的JSON数值token |
| P02 | 1 | 688432的09-11原始0.0000；数值完整1、语义可用0 |
| P03 | 1 | 五日内存副本缺中间日；4/5，不借更早记录、不补零 |
| P04 | 2 | 000004/000005旧响应；HTTP成功同时STALE、五日0/5 |
| P05 | 9 | 缺字段、null、空串、abc、NaN、±Infinity、布尔/数组、非法日期 |
| P06 | 2 | 300750/688981各13页，闭区间243日、17额外旧日、五日跨页 |
| P07 | 1 | 相同记录跨页重复，保留2份出处、覆盖只计一次 |
| P08 | 5 | 同日冲突、重复页、页漂移、锚复核漂移及目标日金额冲突置空 |
| P09 | 10 | 网络/HTTP/解析、空数组、禁请求；403/429即使允许重试也只尝试一次 |
| P10 | 7 | 页/请求/墙钟上限、重试、部分返回及解析耗时越限 |
| P11 | 1 | 原文格式哈希与值哈希分开、两观测保留、旧观测+新失败、UTC及UNKNOWN时间 |
| P12 | 1 | 同源无TDX、无日历UNKNOWN、主要状态与分母对账、零不计语义可用 |

完整JUnit数据：[results.xml](evidence/2026-10-18-dr04-p-implementation/results.xml)；机器摘要及本次关键文件哈希：[summary.json](evidence/2026-10-18-dr04-p-implementation/summary.json)。

## 最小阻断

**UNRESOLVED_RISK**：既有 `tests/test_rh1_git_line_endings.py::test_crlf_preserves_added_line_discrimination[False]` 和 `[True]` 失败。调用 `scripts/check_rh1_static.py::_added_line_ranges` 时，临时Git仓库中的 `git diff` 返回错误：

```text
RuntimeError: git diff failed: warning: Limiting comparison with pathspecs
is only supported if both paths are directories.
usage: git diff --no-index ...
```

根因尚未确认，未将其归咎于产品缺陷或宣称只是环境问题；按Owner停止条件没有继续修复、删测、跳过或改验收标准。失败全文保存在[最终回归日志](evidence/2026-10-18-dr04-p-implementation/regression.txt)。

## 审查与验证

先由公共入口缺失测试确认RED，再实施；新增测试最终45项通过。独立只读审查发现一项 CONFIRMED_DEFECT：锚复核发现目标日金额变化时，原规范金额仍可消费。已补公共入口RED复现，并修复为两版本留存、规范金额为空及覆盖不完整；同组回归通过。墙钟解析越限亦经RED复现并修复。CodeRabbit CLI为signed out，未调用远程审查、未要求登录；使用一次独立只读审查完成代码核查。

最终命令（PowerShell，当前仓库根目录）：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_daily_fund_flow.py tests/test_astock_tdx_fallback.py tests/test_astock_interface_fix.py tests/test_astock_silent_failure_sentinel.py tests/test_fetch_result_core.py tests/test_trading_calendar_structured.py tests/test_config_and_warmup_regression.py tests/test_release_version.py tests/test_rh1_git_line_endings.py -q --tb=short --basetemp=D:\Dev\Projects\chstockdata\.pytest_cache\dr04-p-final-20261018 --junitxml=docs/audits/evidence/2026-10-18-dr04-p-implementation/results.xml
.\.venv\Scripts\python.exe -m ruff check src/chstockdata/daily_fund_flow.py tests/test_daily_fund_flow.py
git -c core.whitespace=cr-at-eol diff --check
```

Git证据：[tracked.diff](evidence/2026-10-18-dr04-p-implementation/tracked.diff)、[新增模块diff](evidence/2026-10-18-dr04-p-implementation/new-module.diff)、[新增测试diff](evidence/2026-10-18-dr04-p-implementation/new-tests.diff)。这些为未提交工作树差异；新增文件未被普通 `git diff --stat` 计入，因此另存显式new-file diff。保留现有文件CRLF，没有全文件格式化。

## 修改文件与工作树交接

- 新增 `src/chstockdata/daily_fund_flow.py`、`tests/test_daily_fund_flow.py`。
- 修改 `src/chstockdata/__init__.py`（7行公开导出）、`README.md`（5行未发行入口说明）。
- 新增 `tests/fixtures/daily_fund_flow/`（30份原文、calendar、manifest、README），消费文档及本报告/测试证据。
- 先前预检报告只追加阻断已解决的历史说明；Owner既存未跟踪资料不变。
- 当前阶段/步骤：DR04-P 实施与离线验收，因最终回归失败停止。HEAD未变，工作树有本次未暂存/未跟踪变更，未创建产品提交。
- Gate：BLOCKED_TEST_FAILURE；合同测试通过与Owner Acceptance严格分开。待Owner Review，不进入DR04-M或Mishi开发。
