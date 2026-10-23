## Owner Acceptance REWORK r2 — 2026-10-14


CURRENT_DECISION=FIX_ONLY。Owner 指出的 SIOS 二次区间校验错误为 **CONFIRMED_DEFECT**：`HistoricalOpeningEvidence.__post_init__()` 在正向事实中把旧 `effective_end=None` 事件永久延长，推翻未变 r1 wheel 的认证日期适用结论。本节追加独立新证据，不覆盖 r1 PASS_CANDIDATE、旧测试、旧 source/wheel/ZIP 身份；Owner Acceptance 仍 PENDING。

仅在本次可写隔离 `C:/Users/Administrator/.codex/visualizations/2026/10/13/01a135d1-a42d-73a3-b19f-dc0968e4ca6c/owner-rework-r2/systematic-investing-os` 修改两个文件：`src/systematic_investing/domain/historical_opening.py` 和新增 `tests/component/test_owner_r2_interval_contract.py`。未修改原 SIOS 仓库或 r1 隔离源码。交付相对 r1 的完整增量 `owner-acceptance-rework-r2/sios-source-vs-r1.patch`；原冻结 commit → r1 的已验证补丁继续有效，r1 → r2 实际 `git apply --check`/`git apply` 均 exit0，重建 257 文件逐字节等于受测 manifest。

最小消费者修复以既有认证事件的**完整 canonical SHA256** `803a5a1041d7736734a286db66994f9dc65a9428318375f23288d8b4b56960fe` 为本地信任锚。该身份来自 r1 packaged `OfficialOpeningEvent` 的完整序列化，绑定证券/市场、原停牌和复牌来源 URL/原始 bytes SHA、日期、认证依据、有效区间和全部原始字段；不根据调用方自称的 resume_date、verified 或 source 标签认证。只有该事件完整身份相等时，认证复牌日之后才不再沿用旧停牌否决；复牌日仍拒绝正向事实，既不合成 effective_end，也不推断开盘钟点。其余空结束区间继续逐个否决，包括同证券新停牌和任何修改后的“认证”事件。精确复制既有认证事实不会认证另一个事件。信任锚只记录现有单项认证证据身份，不新增历史库、来源或数据合同；核心不引入 vendor import，snapshot/replay 不依赖外部安装包或网络。将来来源内容改变时会保守拒绝，不能自动放宽此身份。

确定性测试经过真实 r1 wheel 的 `chstockdata.fetch_historical_opening_evidence`，注入 TDX 交易/分钟返回及官方 HTTP 请求后，再经真实 `LibraryChStockDataClient → HistoricalOpeningEvidence → ChStockDataProvider`。没有 mock 掉产品区间判断，也不把注入活动宣称为对应日期的真实联网认证。2015-12-18 正向、2016-01-04 UNKNOWN/冲突阻断、2016-07-04 UNKNOWN、2016-07-05 与2022-12-30正向，完整 payload/evidence_hash 保持相等；真实 engine 回归证明前者下午停牌不追溯取消开盘、复牌日无 Fill、复牌后资格可产生全量模拟 Fill，LEGACY 对上述历史 gap 仍无 Fill。官方失败或 TDX 无活动仍 UNKNOWN；伪造正向 payload 重封 hash 仍不能越过来源条件/新停牌/认证身份，原上市生命周期、side restriction、PIT、时钟和交易算术回归通过。

RED 先得到 **3 FAIL / 13 PASS**，失败精确位于两个复牌后 Provider MALFORMED_DATA 和因此无法进行的 snapshot；再增加成交/旧模式回归后以未变旧消费者做负对照，**7 FAIL / 19 PASS**（新增四项也止于同一 provider 拒绝），恢复修复文件逐字节后 GREEN **26 PASS**。两次中间 GREEN 尝试分别发现新测试缺少必需 daily bar、测试 calendar 缺少 T+1 后继 session，均只修测试 fixture，失败日志原样保留；未为测试放宽产品 snapshot/calendar 规则。全量 offline 首轮 **998 PASS / 6 skip** 中新增 skip 为隔离目录缺少原 smoke snapshot；复制原六文件冻结 snapshot、记录各文件 SHA 后重跑，恢复原 mandatory 验证范围。

| 本轮受影响 Gate | 实际结果 |
| --- | --- |
| 跨仓合同、payload/hash/snapshot、成交及旧模式 | 26 PASS |
| SIOS provider 原67项 + opening provider6项 | 73 PASS |
| SIOS 全量 offline | 999 PASS，5原默认 live opt-in skip |
| Golden/ETF/parity | 165 PASS，5原默认 live opt-in skip |
| 全量中 snapshot/PIT/replay/opening 相关 | 67 PASS，零 skip |
| 原五项 mandatory live | 5 PASS，零 skip/xfail/deselect；54能力 PASS |
| live 原始证据核验 | 129份 raw 长度/SHA一致，source/资格测试前后不变 |
| r1 → r2 完整增量重建 | 257文件逐字节相等，apply/check exit0 |

本轮 live 于2026-10-14实际执行，约118秒，使用修改后的 SIOS、同一 SHA 的受控 r1 wheel 和原 VIPDOC 路径。六个 actual snapshot、RAW fill、actions/calendar/freshness、halt 否决及旧PIT拒绝沿原测试真实执行，不能沿用旧 SIOS live PASS。观测 runner 保留原请求/返回，仅更改路径、工件身份核对和证据输出；新 opening 仍固定既有有界/no-retry 参数，原 calendar 的既有 fallback/freshness 规则不改。初次读取旧 wheel 沙箱拒绝后，只读复制工件/256源文件到可写目录，核对全部 wheel 包成员；live 网络按 Owner 授权执行，没有扩大来源探索。

独立 `verify_evidence.py` 实际 exit0，验证新257文件、原SIOS256文件、原CH765文件、r1交付ZIP、RED/GREEN/全量/专门JUnit、129raw与54能力一致。新 SIOS full manifest SHA256 **`cf848bff60618c1a9a8f48e433420b6db557627fec7d00c05707891357a02d08`**；runtime54文件 canonical SHA256 `12c7c6a289958a824920cb2e2122d533910ad8c6eec8e2ec63bbf11d28057d17`，均为内容身份，不是新 Git commit。无.git受测快照的代码身份仅在测试进程明确注入真实 runtime hash，生产 resolver 未改。

CH wheel SHA256 **`1dd58350678fbb07d3b545165708d814f93fb94f965dc2da33bad2fab7ff779c`** 和765源文件不变，沿用同身份 r1 package796 PASS/原 optional skip 与 TradingAgents123 PASS/7相同基线失败的相对兼容证据，未重跑或修复 TA 基线。原 r1 ZIP SHA256 `5e8eb1fa522cac82a00e0cbc246905e529d4fe1a3fb7d27d21d7f6a6d078759b` 实际复核不变，不重复交付14MiB。当前批准必需范围无残留阻断；两个原能力边界、TA依赖限制及七项基线失败保留，未宣称完整历史停牌/PIT覆盖。

```ini
CURRENT_DECISION = FIX_ONLY
OWNER_REWORK_R2 = PASS
CHSTOCKDATA_INTERVAL_REWORK_R1 = PASS
SIOS_INTERVAL_CONTRACT = PASS
SIOS_PROVIDER_INTEGRATION = PASS
OFFICIAL_VETO_PRESERVED = PASS
PIT_AND_SNAPSHOT_REGRESSION = PASS
CH_WHEEL_CHANGED = NO
SIOS_SOURCE_SHA256 = cf848bff60618c1a9a8f48e433420b6db557627fec7d00c05707891357a02d08
SIOS_OFFLINE = 999_PASS_5_ORIGINAL_LIVE_OPTIN_SKIP
SIOS_MANDATORY_LIVE = 5_PASS_0_SKIP_XFAIL_DESELECT_54_CAPABILITIES
SCOPE_EXPANSION = NO
READY_FOR_OWNER_ACCEPTANCE = YES
OWNER_ACCEPTANCE = PENDING
RELEASE_AUTHORIZED = NO
PUBLISH_AUTHORIZED = NO
NEXT_PHASE_AUTHORIZED = NO
```

交接：v0.4.2 / Owner Acceptance REWORK r2最小修复及受影响验证完成，Gate为PASS_CANDIDATE待Owner验收。CH HEAD仍`42bd44ef4d695aa3e88cfab4ebc3417660d0437a`，原预存tracked修改保留，仅追加本审计和r2证据；SIOS基线冻结`84fd54fae0740bc06b1d250afa4578be29556956` → 已交付r1 → 本轮两文件增量，隔离源码无.git/无新commit。无范围变更或必需Gate阻断，推荐下一动作仅Owner独立验收增量和新证据；不merge、push、tag、发布或自动进入下一Phase。
