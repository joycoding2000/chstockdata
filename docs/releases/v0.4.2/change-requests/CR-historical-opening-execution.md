# CR-v0.4.2-HISTORICAL-OPEN-EXECUTION — 设计与契约独立审查

日期：2026-10-10（Asia/Shanghai）  
任务：DOCUMENT_ONLY / CHANGE_REQUEST_DESIGN_REVIEW  
状态：**PROPOSED — Owner Design Review；本文件不是已生效合同。**

## 1. Executive Summary

建议保留 Owner 的产品目标，修订五处关键表述后交 Owner 审议：明确“开盘分钟活动”只是日线开盘模型的代理资格；区分官方阻断与来源冲突；增加独立执行事实输入并在现有 engine 执行入口接入；显式注入上海市场时钟；正式替换原 mandatory live 中已经失效的历史状态假设，同时保全 actions/freshness 和全部其它门禁。

**原草案符合性结论为 REWORK。** 冻结日线模型明确不承诺队列成交，能够容纳被明确批准、版本化的分钟代理；但冻结 PIT tradability/09:15 activation 合同尚未允许事后执行事实。因此不能声称这只是 adapter 元数据修复，也不能把代理结论改名为历史全天 TRADABLE。采用该代理是本 CR 的实质合同变更，需要 Owner 决定。

**SIOS_ENGINE_CHANGE_REQUIRED = YES。** 冻结 engine.py:903–907 先按 activation 可知性过滤；execution.py:248–256 只接受过滤后的日级状态，没有独立执行事实参数。只改 adapter、只改 availability、只注入时钟或只绕过 live 断言均无法诚实完成目标。建议复用现有 _activate()/activate_pending_plans()，新增窄的执行资格输入及门禁；保留策略切片和全部成交算术，不建设新引擎。

已有源证据足以设计这个有限代理合同：四 ETF、临停反例、历史点和价格尺度错误均有保存记录。它不足以证明 09:30:00 确定可执行、集合竞价成交类别、所有历史覆盖或生产接入已经合格。A1–A11 的实现资格仍待授权后验证；当前 Release/SIOS Gate 保持 FAIL。

本轮只新增本文，不修改源码、测试、依赖、pin、原审计、wheel 或研究结果，不提交或发布。完成后停止在 Owner Design Review。

## 2. Original Frozen Contract

### 2.1 身份、权威和证据索引

| 标识 | 基线或证据 | 本轮核对与适用边界 |
|---|---|---|
| B1 | chstockdata HEAD 42bd44ef4d695aa3e88cfab4ebc3417660d0437a | 候选基底；不包含所有未提交正确性修复 |
| B2 | 捕获源码 tree 911d231646edc7d419d2e26ac91c95af5404c5c6 | 原候选内容身份；566 个 candidate-source.json 文件本轮逐个 SHA256 匹配，本文不加入或重定义该 tree |
| B3 | dist/v042-unified/chstockdata-0.4.2-py3-none-any.whl | SHA256 b76b065a06cd1d91868880a7b57584f598b6fd4cb42931e9a33700bc99a88c7a；39 个 runtime 成员与当前 src 逐字节一致 |
| B4 | SIOS 冻结 commit 84fd54fae0740bc06b1d250afa4578be29556956 | tree 979b5b33188931e2c78aa01026684ed72e064600；本轮直接读 Git blobs。旁边 SIOS 当前 HEAD 为 fafdb6d3942ba52baa9480da7c8674dab1487f5d，不能用当前文件替代冻结合同 |
| F1 | [v0.4.0 version-design](../../v0.4.0/version-design.md)，§3–7 | 该文件自称追溯重建、Owner review required，不能冒充当初的已签署原始设计；其中明确 additive API、真实来源/未知语义、消费者升级独立验收和保全 M0/M1 |
| F2 | SIOS docs/architecture/backtest-semantics.md:13–18、40、74–79、89–93、118–124 | T-close 决策与 sizing；NEXT_SESSION_OPEN；raw open+滑点/tick/费用；未知不成交；submitted all-or-none；新语义产生新运行身份 |
| F3 | SIOS docs/architecture/data-contracts.md:14、36–38、53–55、67–69、92、113–138 | PIT 与 retrieval 分离，typed failure、immutable snapshot、ETF subtype/capability gate；供应商抓取属于 chstockdata |
| F4 | SIOS engine.py:139–163、178–239、892–928、987–997、1132–1140；execution.py:248–256、259–279、317、391 | 决策与执行入口及 09:15/09:30 真实路径；完整路径见 §8 |
| F5 | SIOS provider.py:456–490、1029–1102、1244–1327 | 旧 suspension client、PIT 映射和错误的 historical availability fallback |
| E1 | [统一候选 Gate](../../../audits/2026-10-09-v0.4.2-unified-gate.md) 及 [candidate-source.json](../../../audits/evidence/2026-10-09-v0.4.2-unified-gate/candidate-source.json)、[final-integrity.json](../../../audits/evidence/2026-10-09-v0.4.2-unified-gate/final-integrity.json) | 身份及保存的 JUnit/exit 本轮核对；旧结果不是本轮重跑 |
| E2 | [历史恢复结论](../../../audits/2026-10-09-v0.4.2-history-recovery-conclusion.md) 及其 tdx-facts.json、disclosure-pages.json、pit-boundary.json | 日线不能证明开盘状态；688432/000002 的披露事实；fallback 诊断；其 activation 默认 09:30 的说法由 E3/冻结源码纠正为 09:15 |
| E3 | [官方历史与 SIOS 决策](../../../audits/2026-10-09-v0.4.2-official-history-and-sios-final-decision.md)，§2–6 | SSE/SZSE 事件及响应摘要/SHA；没有完整正常状态或目标 preopen 资格。部分官方原始响应当时只在内存核验，报告留字段和 hash，不声称本轮能离线重放全部原响应 |
| E4 | [TDX 历史开盘审计](../../../audits/2026-10-10-v0.4.2-tdx-historical-execution-feasibility.md) 及其四份 JSONL/manifest | 本轮离线解析原记录、复算 SHA、量价及时间字段；44 次既有查询未重跑 |

SIOS 路径/行号全部指 B4，chstockdata 源码指本轮受保护工作树。SIOS provider/engine/execution 冻结 blob SHA256 分别为 57a858be4c5e70b964d7d5f2290cf94b7d4243fe497828e5a7592eb24c259e3f、fb27c8be1f9b8068e422e9cb882d5b635ab075398c49c9d936df5023ef336521、f7d21c2e51a85a96850f0b6913baf37514fa8e5d0fad016f86aa7bda9208731e，本轮复算一致。冻结仓库未写入。

两仓均先尝试 CodeGraph：chstockdata 的检索片段未准确定位当前 suspension，SIOS 返回 unable to open database file。随后只读当前指定源码及 B4 Git blobs，用 AST/行号核对；未重建索引。

### 2.2 原合同不能被本 CR 悄悄改写的部分

- T 决策只能使用该会话及更早、cutoff 前可知的数据；T+1 活动不得进入 T 信号、目标、目标权重、universe 或 planned_quantity。
- T-close 锁定 sizing；T+1 用 raw 日线 open 加既有滑点、tick rounding、费用、资金/手数/可卖数量和批准规则。资金不足的既有 complete-lot submitted_quantity 调整仍允许，目标和 planned_quantity 不重算。
- 不确定执行资格、缺规则、明确停牌或 side 阻断均拒绝；没有日内部分成交、队列模型、复牌补单或隐式 carry/retry。
- calendar、Instrument Master、corporate actions、adjustment/freshness、Golden、snapshot/replay 的既有正确性要求保留。QDII 对照仅为数据源反例，不扩大 SIOS 三种已批准 ETF subtype。
- B4 具体实现额外把执行所用 tradability 绑定到 activation 前可知。这一部分需要正式修订，不能因日线模型不模拟队列便假定已经获准解除。

## 3. Confirmed Defects

| 编号 | 分类 | 事实与证据 | 本 CR 内的处理 |
|---|---|---|---|
| D1 | CONFIRMED_DEFECT | Eastmoney latest-event 集合不是完整历史 as-of；事件缺席的正常状态推论失效。当前 suspension.py:211–218 历史/未来 fail-closed，源语义测试保留 | 不恢复旧推论、不替换旧 API；新能力独立表达执行证据 |
| D2 | CONFIRMED_DEFECT | provider.py:1319–1325 在历史 observed_at 不同日时补造上海 09:30 EXCHANGE_RULE；不读取 payload.information_available_at | 改为只接受有依据的信息时间，否则 UNKNOWN；不得使用 effective/retrieved 冒充 |
| D3 | CONTRACT_CONFLICT | 真实事后活动不满足 F4 的 09:15 activation 信息门禁；诚实 availability 会被过滤。不是已发现策略实际泄漏的证据 | 增加独立执行输入；策略 PIT 门禁不放宽 |
| D4 | CONFIRMED_DEFECT | E4 使用 mootdx 0.11.7 / tdxpy 0.2.7 的 0x0fb5 ETF 价格为分钟值的十倍；四目标均重现 | 接入前必须固定版本/协议/已认证证券类别的尺度和永久回归；错误解析不得 success。与已修复 VIPDOC 日线无关 |
| D5 | CONTRACT_CONFLICT / UNRESOLVED_RISK | EngineClock 默认 UTC，runner.py:536、oos.py:1496、vertical smoke:115 直接 EngineClock()；记录时刻和可知性比较确有偏移 | 新语义入口注入 Shanghai clock；不改全局默认，不改历史结果。本轮未重跑研究，不能量化历史 target/NAV 受影响数量 |
| D6 | CONFIRMED_DEFECT（资格阻断） | E1 原 live JUnit 5 tests、1 failure、0 skipped；test_live_tradability_adjustment_and_freshness 在历史 is_success 失败，后续 actions/freshness 未执行 | 保持 mandatory；经批准后调整能力断言并独立执行其它断言。已有 offline PASS 不抵消本失败 |

“全部免费源不可用”“所有分钟数据不可信”“必须建设完整 PIT 数据库”均无证据，不转为工程要求。完整状态全集、09:30:00/竞价类别证明为 INSUFFICIENT_EVIDENCE；在明确接受分钟代理的前提下，秒级/队列不足属于 NON_BLOCKING_LIMITATION。

## 4. Owner Proposed CR

以下逐字保留任务输入第二部分（仅统一换行并加引用标记）。其 PROPOSED 和全部 A1–A11、non-goals、停止条件仍为原提案。修正意见在后续章节独立列出，未覆盖、删除或视为已批准。

<!-- OWNER_PROPOSED_CR_BEGIN -->
> # 第二部分：OWNER_PROPOSED_CR — 完整待审查草案
>
> **以下内容是 Owner 提出的正式设计审查输入。**
>
> 必须在最终文档中逐项保留、分析或明确说明为何需要修改。
>
> 不得将其标记为已经批准实施。
>
> ---
>
> ## CR-v0.4.2-HISTORICAL-OPEN-EXECUTION
>
> ### 历史开盘执行资格的可信数据与 PIT 隔离
>
> 状态：**PROPOSED — Owner Design Review**
>
> 关联项目：
>
> - chstockdata v0.4.2
> - systematic-investing-os
>
> 变更性质：
>
> 已确认数据正确性缺陷的有限跨仓契约修复。
>
> ### 1. 原始目标
>
> 修复 chstockdata 历史停复牌状态错误，允许 SIOS 安全升级至 v0.4.2，并维持原定的 T-close 决策、NEXT_SESSION_OPEN 成交模型和无前视约束。
>
> ### 2. 已确认的问题
>
> - Eastmoney 原接口不能提供可靠、完整的历史停牌状态；缺少记录不能解释为正常交易。
> - SIOS historical adapter 会把缺乏真实时间依据的历史状态回填为交易日 09:30 已知。
> - SIOS 执行激活还要求交易资格事实满足 09:15 的 information_known_at 检查。
> - 免费 TDX `0x0fb4` / `0x0fb5` 已取得四只 ETF 的历史开盘活动样本，并与官方临停样本交叉验证。
> - mootdx 0.11.7 历史 ETF 逐笔价格存在样本确认的十倍解析错误。
> - 原冻结日线回测不要求订单队列、日内部分成交或精确重建撮合。
>
> ### 3. 拟议业务契约
>
> #### 3.1 策略决策不变
>
> T 日决策只能读取 T 日决策截止时已经可知的信息。
>
> T+1 日成交活动不得进入 T 日策略决策、信号、目标权重或仓位计算。
>
> #### 3.2 历史执行资格独立判断
>
> 对 T+1 的 NEXT_SESSION_OPEN 模拟执行：
>
> - 交易所官方记录明确覆盖执行时刻的停牌区间：禁止成交。
> - 官方查询未发现冲突，且可信 TDX 历史记录证明开盘分钟存在真实交易活动：允许进入原有日线模拟成交规则。
> - 来源缺失、异常、价格/时间含义未认证，或证据冲突：UNKNOWN，拒绝成交。
> - 后续才开始的临停不能追溯取消此前已经模拟完成的成交。
> - 复牌后不得自动补做原本在 09:30 被拒绝的订单。
>
> **模型限制：**
>
> 开盘分钟真实成交是既有日线开盘成交模型的执行资格代理证据，不承诺 09:30:00 某笔特定订单必然成交。
>
> 正式设计必须记录这一近似及时间粒度边界。
>
> #### 3.3 两种时间语义分离
>
> - `information_available_at`：历史参与者当时能够知道信息的时间。
> - `execution_effective_at/window`：真实交易状态或成交活动生效的历史时间。
> - `retrieved_at`：系统事后获取数据的时间。
>
> 三者不能相互冒充。
>
> 执行事实可以参与历史执行模拟，但不能通过伪造 `information_available_at` 进入策略决策。
>
> 中国 A 股及 ETF 的交易时钟必须采用明确的 Asia/Shanghai 时区。
>
> 既有 UTC 默认行为的影响需要纳入契约评估，禁止静默重写冻结历史结果。
>
> ### 4. chstockdata 最小变更范围
>
> 新增一个明确的**历史开盘执行证据能力**，不替换、不重新定义旧 `get_suspension_info()`。
>
> 建议输出概念字段：
>
> - 证券、交易日期、交易所、目标执行时间
> - 开盘活动证据：时间窗口、成交量、必要时的价格
> - 官方停复牌事件：有效区间、事件类型、来源
> - 来源覆盖、请求结果及异常
> - 时间字段的明确含义与时区
> - 获取时间、来源身份、证据摘要
> - `OPEN_ACTIVITY_CONFIRMED / BLOCKED_CONFIRMED / UNKNOWN` 等可区分的事实结论
>
> 上述名称是设计草案，不预先锁定 Python 函数签名。
>
> 实现应尽量复用既有 TDX 协议和交易所接口，不引入通用多源框架。
>
> 保留既有历史停牌 fail-closed 行为。
>
> 不能因官方接口返回空列表，就自动派生 `suspended=False`。
>
> ### 5. SIOS 最小变更范围
>
> 仅审查和修改必要的：
>
> - chstockdata 消费者 adapter
> - 历史执行资格输入及其时间语义
> - activation 与 execution 的事实使用边界
> - 直接受影响的合同测试和消费者资格测试
>
> 保留以下冻结业务语义：
>
> - T-close 生成目标
> - NEXT_SESSION_OPEN
> - T-close sizing
> - 开盘价加滑点
> - 交易费用、交易规则、手数约束
> - all-or-none
> - 不得引入未来信息
> - 不确定时拒绝成交
>
> 不得扩展到策略、Portfolio、订单簿、日内部分成交、复牌后自动重试或完整 PIT 数据库。
>
> 既有 M0/M1 结果不可覆盖；受新执行规则影响的后续回测必须具有独立语义版本和证据身份。
>
> ### 6. 强制验收条件
>
> **A1 — 四 ETF 开盘活动**
>
> 四只目标 ETF 在 2026-09-11 的开盘成交活动得到真实数据支持。
>
> **A2 — 官方临停拒绝**
>
> 513100、159509 在官方临停至 10:30 的情况下，09:30 必须禁止成交。
>
> **A3 — 历史停牌与盘中边界**
>
> 688432 持续停牌及复牌样本正确；000002 盘中临停不会追溯否定早盘成交。
>
> **A4 — 历史覆盖**
>
> 2022、2016 历史数据覆盖与支持边界有实际证据，未覆盖日期继续 UNKNOWN。
>
> **A5 — 逐笔价格正确性**
>
> TDX 逐笔 ETF 十倍价格错误被回归测试捕获；错误价格不得进入成功结果。
>
> **A6 — 失败与缺失安全性**
>
> 官方空事件、TDX 空响应、零量、网络失败、数据冲突分别得到正确处理。
>
> **A7 — 策略 PIT**
>
> T+1 历史执行事实变化不能改变 T 日策略目标、信号或 sizing。
>
> **A8 — 时区**
>
> 中国市场 09:15/09:30 时间语义正确；UTC 和上海时间不会被混用。
>
> **A9 — 原成交合同**
>
> 原有费用、价格、手数、资金、all-or-none 及 UNKNOWN 拒绝行为保持。
>
> **A10 — 消费者 live 等价覆盖**
>
> SIOS 原强制 live 验证被等价或更严格的消费者合同覆盖；ETF corporate actions 和 freshness 验证不得丢失。
>
> **A11 — 统一候选 Gate**
>
> chstockdata package、SIOS offline/Golden/ETF/live、TradingAgents 兼容及构建安装 Gate 使用同一候选工件并通过。
>
> ### 7. 明确 Non-goals
>
> - 不建设真实订单簿或队列成交概率模型。
> - 不引入付费数据源。
> - 不扩大至全市场历史分钟数据仓库。
> - 不要求恢复全部历史事件公告数据库。
> - 不修订冻结 M0/M1 策略研究结果。
> - 不全面重构 SIOS 回测引擎。
> - 不要求借此解决所有免费数据源稳定性问题。
>
> ### 8. 准入与停止条件
>
> 本 CR 首先进入设计审查。
>
> 在批准实施之前，必须明确：
>
> 1. 开盘分钟成交证据在日线执行模型中的适用规则和不足。
> 2. 官方停复牌正向事件与 TDX 成交证据冲突时的优先级。
> 3. 旧 historical suspension 合同与新 execution evidence 合同的边界。
> 4. SIOS 最小代码影响及必须调整的冻结测试。
> 5. UTC/上海时区问题的最小解决方案。
> 6. 既有消费者 Gate 如何在不降低严格程度的条件下恢复。
>
> 设计审查未通过则不得实施。
>
> 实施完成不等于 Release Gate PASS；只有全部强制资格通过且 Owner 独立验收，才能进入发布授权。
>
> 当前状态：
>
> ```ini
> CR_DESIGN = PROPOSED
> IMPLEMENTATION_AUTHORIZED = NO
> SIOS_UPGRADE_QUALIFIED = NO
> RELEASE_GATE = FAIL
> PUBLISH_AUTHORIZED = NO
> ```
>
> ---

<!-- OWNER_PROPOSED_CR_END -->

## 5. Independent Conformance Review

### 5.1 逐项追溯

“待 Owner”适用于本表所有建议；测试栏是授权后验收设计，不是本轮执行结果。

| Owner CR 条款 | 冻结代码/文档 | 已有证据 | 审查结论 | 最小建议 | 验收测试 |
|---|---|---|---|---|---|
| 标题/性质：有限跨仓 correctness 修复 | F1–F3；AGENTS Gate discipline | E1–E4 | 产品目标一致；跨仓执行资格语义超出已授权 FIX_ONLY，必须 CR | 明列 eligibility/clock/schema 版本及 Owner 决定，不叫纯 metadata 修复 | A11、身份隔离 |
| §1 原始目标 | F2:13–18、40、74–79 | E1 live 阻断 | 保留目标；新证据不能使旧历史状态合同自动恢复 | 用新执行能力恢复消费者升级，旧 suspension 仍安全拒绝 | A7、A9、A10 |
| §2 Eastmoney 缺席/错误回填/09:15 | F5；F4:903–907 | E2/E3、当前安全源码 | D1–D3 CONFIRMED；09:15 为真，09:30 是执行/错误回填时间 | 取消无依据回填，独立执行输入；不改 cutoff 来迁就 | A6–A8 |
| §2 TDX/价格/无需队列 | F2:79、89、128 | E4 原 JSONL、四目标和控样 | 数据可取、价格缺陷确认；队列不足不迫使建设日内模型 | 有界接入 0x0fb4/0x0fb5，价格先验证 | A1–A5 |
| §3.1 策略不变 | F4 DecisionContext、_known_tradability_through；quality.py:549–575 | 冻结 no-lookahead 测试 | 符合，必须完整保留 | 执行集合不暴露给策略，不并入 PIT tradability | A7；原未来变异测试 |
| §3.2 官方区间覆盖时禁止 | F2:74–79；旧状态无区间 | E3 513100/159509/688432 | 支持正向阻断；需界定区间和冲突标签 | 上海 [start,resume)，末停牌日按会话覆盖，未知边界不猜 | A2、A3、A6 |
| §3.2 官方无冲突+TDX 开盘活动 | F2:40、79、128；F3 PIT port | E4 09:30 正量与首点量 | CONTRACT_CONFLICT：支持分钟活动，不是严格整点状态/任意订单保证 | 批准 §6.1 代理；两源有界请求完成且字段认证，无冲突才允许原日线规则继续 | A1、A4、A6、A9 |
| §3.2 来源缺失/异常/冲突 UNKNOWN | F1 unknown 不转布尔；F3 typed error | E3 HTML/错误体、E4 空/零量 | 符合；“官方无事件”与“官方失败”必须不同 | 官方合法空+TDX正量可为代理；失败/partial/含义不明或真冲突 UNKNOWN | A6 |
| §3.2 后发临停不追溯、复牌不补做 | F2:77、89 | E2/E4 000002、两 ETF 10:30 | 符合；同一开盘分钟内的边界仍不够细 | W 外后发事件不撤销既有 fill；W 内模糊边界安全拒绝；不 retry | A2、A3 |
| §3.2 模型限制 | F2:79、128 | 旧逐笔 HH:MM，无 status/秒 | 原披露方向正确，须进一步区分四种开盘语义 | OPEN_ACTIVITY_CONFIRMED 只证明 W 内活动；不声称 09:25 正式竞价或 09:30:00 必成交 | A1、A9 |
| §3.3 三种时间与上海时区 | F3:36–38；F4 clock；F5 availability | E3 午夜字段；本轮 clock 单例 | 符合目标；实际默认 UTC 不符合中国市场当地钟点 | 信息时间未知保留空；effective/window 与 retrieval 分开；新入口显式上海注入 | A7、A8 |
| §4 新历史开盘能力、不改旧 API | 当前 a_stock.py:5845–5881、suspension.py:193–298、tradability.py:107–333 | source-semantics 回归；E1 runtime 身份 | additive 方向符合 F1；不存在已认证完整历史接口 | 复用 FetchResult/attempt/provenance 和现有协议调用方式，新增窄能力；不通用路由 | A5、A6、A11 |
| §4 概念字段/事实结论 | F3 evidence/typed error；旧 bool schema | E3/E4 字段精度不同 | 名称可以保留；必须补 scope/粒度/版本/冲突标记 | §7 字段下限；事实结论与订单许可分开，不提前锁函数名 | A1–A6 |
| §5 adapter/输入/activation/execution 最小影响 | F4/F5；domain.market.py:330–375 | 真实调用链及 late-at-activation 测试 | engine 最小修改不可避免；schema/快照/clock wiring 也直接受影响 | 仅现有模块加执行集合/接线；不改策略、Portfolio 和算术 | A7–A11 |
| §5 保留 sizing/费用/手数/all-or-none | F2:40、83–93；execution.py:329–335、403–423 | 原 component/Golden | 符合；活动量不是订单流动性配额 | TDX 价格/量只认证资格，不替换日线 open、不限量/部分成交 | A9 |
| §5 M0/M1 不覆盖、新版本身份 | F2:118–124；F3:92、134；runs.py:36–119 | 冻结 manifest/Golden/snapshot | 符合；只 version 一个函数名称不够 | 新 evidence 分区、clock/policy/version/digest 进入 identity；旧 replay 按旧 reader/mode | A8、A11、replay |
| §6 A1–A5 | E4 样本；F3 subtype 资格 | 四目标、控样、2016/2022、十倍价格 | 数据支持设计；还不是新实现验收 PASS | §11 明确每项可证伪预期和未覆盖 UNKNOWN | A1–A5 |
| §6 A6–A9 | F2–F5、原安全/未来/算术测试 | 原源码、失败和量价记录 | 条款保留，新增细分冲突/时区/隔离验证 | 见 §10/11，不改原核心业务断言 | A6–A9 |
| §6 A10 live 等价 | F3 ETF gate；live.py:242–261 | E1 失败发生在首个历史请求 | CONTRACT_CONFLICT：旧 historical is_success 不能继续靠补造布尔恢复；不是豁免 | 保留原测试为 mandatory 编排，正式替换历史资格断言；逐项保全 actions/freshness，增加失败/空/未知检查 | A10 |
| §6 A11 同一候选 | F1 G5–G7；F3 upgrade qualification | E1 B3 绑定及 TA 基线七失败 | 符合；旧候选 PASS 不适用于未来新代码 | 新工件统一复验；TA 按原相对兼容，保留基线失败，不偷换为全仓全绿 | A11 |
| §7 七项 non-goals | F1/F2 范围边界 | 当前目标只需有界代理 | 全部保留 | §12；不要求 0x056a/0x0fc6 作为接受代理的隐性前置 | A9、范围检查 |
| §8 六项设计准入、Owner/Release 停止 | AGENTS；F1 release 授权 | E1 Gate FAIL | 完整保留；本文件定义推荐方案不代表授权 | §14；本轮停止，无产品实施 Prompt | 文档完整性/授权核对 |

### 5.2 需要正式批准的最小修正文案

| 修订 | 保留的 Owner 原提案 | 冲突依据 | 推荐增补文本（待 Owner） |
|---|---|---|---|
| R1 代理的准确含义 | “开盘分钟真实成交…执行资格代理证据” | F2 日线限制，E4 HH:MM；09:25 中性字段无事件类别 | “OPEN_ACTIVITY_CONFIRMED 仅表示经过验证的 09:30 本地分钟 W 内有实际正量活动。允许版本化日线模型继续以 raw 日线 open 模拟；不证明严格 09:30:00、竞价成交类别、某订单或数量必成交。只接受 09:25 行或无时间的首分钟正量仍不足。” |
| R2 官方优先级与冲突 | “官方覆盖禁止；证据冲突 UNKNOWN” | 两句若合并为无条件官方优先会掩盖冲突；E3区间/E4分钟 | “官方阻断具有不可绕过的否决权；无冲突时为 BLOCKED_CONFIRMED。确有同一时间范围的正量矛盾时最终 UNKNOWN/source_conflict，仍保留 official_block_at_target=true 并拒绝，不能用优先级消除矛盾或改为可交易。” |
| R3 SIOS 时间/隔离 | “仅必要 adapter、输入与 activation/execution 边界” | F4过滤+F5回填；现有入口无独立参数 | “新增专门的历史开盘执行事实集合，仅在明确选择的新执行资格模式使用；_activate/现有执行门禁接入，策略 PIT 集合与过滤保持。晚知/未知信息时间不妨碍已经认证的执行事实在该模式下用于回放，执行事实本身 UNKNOWN 仍拒绝。” |
| R4 时区及结果保护 | “采用明确 Asia/Shanghai；禁止静默重写历史” | runner/oos/default UTC实际路径 | “中国市场新语义运行显式注入上海时钟，旧默认与旧运行保持；时钟、资格政策与执行证据 digest 均进入新身份。旧冻结结果只披露钟点偏移风险，不重算。” |
| R5 旧 live 的恢复方法 | “等价或更严格覆盖…不得直接删除/跳过” | 原断言索取不成立的完整历史状态；actions/freshness被短路 | “保留 mandatory 编排与四 ETF 覆盖，将 historical PIT 成功断言正式改为新开盘资格与端到端拒绝/成交合同；旧 historical 请求必须继续失败/未知，时间不伪造。原 actions/RAW/availability/freshness 断言逐项继续强制，子能力均执行并分别汇总失败。” |

R1–R5 保留业务目标，改变的是必要的资格/时间/测试假设；不是本轮已实施的 scope expansion。若 Owner 不接受任何修订，本 CR 维持 REWORK，不能直接按草案写代码。

## 6. Source Evidence and Time Semantics

### 6.1 四种开盘含义与本次代理

| 含义 | 已有证据能否证明 | 本 CR 推荐用途 |
|---|---|---|
| 开盘集合竞价实际撮合 | 09:25 正量、中性侧记录存在，但无事件 status；0x056a/0x0fc6 未真实验证 | 不宣称已认证正式竞价类别；不以虚拟匹配量代替实际成交 |
| 09:30 分钟内实际活动 | 0x0fb5 的 HH:MM=09:30、vol>0；四目标的量与 0x0fb4 首点交叉吻合 | 本代理唯一正向开盘输入；W = [D 09:30:00, D 09:31:00)，Asia/Shanghai |
| 09:30:00 整点必可交易/某订单可成交 | 无秒/队列/精确临界状态，无法证明 | 不作为事实结论；不得写成 exact-open 资格 |
| 日线 NEXT_SESSION_OPEN 近似 | 冻结模型已有 raw open/滑点及二元资格、无队列承诺；却未批准事后资格 | Owner 批准后用分钟活动为资格代理，执行时间标签仍为 09:30，执行价格仍取日线 open。这是模型标签，不是认证成交发生于整点 |

0x0fb4 解析返回没有行时间，首点又合并了样本中的 09:25 与 09:30 量。不能仅凭首点>0 推导 W 内成交，不能把首点价格当开盘第一笔。活动量仅作存在性/内部一致性证据，不按量计算可成交委托、不填入订单部分成交。策略目标及 sizing 不读取这些量价。

F2:79、128 没有要求严格队列证明，因此上述近似无需扩张为订单簿；F3/F4 的 activation 信息合同仍需正式修订。若 Owner 要求严格 09:30:00，则当前证据 INSUFFICIENT，需一项精确输入：指定目标日执行边界的实际成交/状态响应及秒级事件分类。该要求不属于本推荐代理，不能自动启动新调查。

### 6.2 已复核的真实点与原始资产身份

单位为手；值保留原证据语义。分钟浮点显示的尾数不被宣称为精确 Decimal 价格。最终合格价格需按认证协议尺度和 tick 表达验证。

| 证券/日期 | 原逐笔文件/sequence/start | 09:25量 | 09:30正量行数/量 | 分钟首点量 | 分钟首点价 / 逐笔末条原价 |
|---|---|---:|---:|---:|---|
| 510300 / 2026-09-11 | final / 1 / 4000 | 77516 | 20 / 352580 | 430096 | 4.576 / 45.76 |
| 159915 / 2026-09-11 | followup / 2 / 4000 | 95647 | 20 / 557149 | 652796 | 3.339 / 33.39 |
| 518880 / 2026-09-11 | final / 2 / 4800 | 52465 | 20 / 106411 | 158876 | 8.910 / 89.10 |
| 511010 / 2026-09-11 | opening_page / 4 / 800 | 46 | 17 / 289 | 335 | 141.177 / 1411.77 |
| 510300 / 2022-12-30 | final / 3 / 4000 | 20974 | 20 / 124260 | 145234 | 3.941 / 39.41 |
| 510300 / 2016-12-30 | followup / 7 / 1600 | 2372 | 13 / 8157 | 10529 | 3.361 / 33.61 |
| 688432 / 2026-09-14 | final / 4 / 4000 | 17109 | 20 / 26531 | 43640 | 40.90 / 40.90 |
| 000002 / 2015-12-18 | followup / 5 / 1600 | 0 | 18 / 101856 | 101856 | 22.40 / 22.40 |

每一行均为有限页，不是完整日逐笔归档；不同 offset 页可能重叠，未来汇总不能重复计量。正向存在性不需要扫描全天；未取到开盘不能凭晚页/空页认定停牌。四 ETF 的分钟首点价也不是原日线 open（例如 510300 日线 open=4.592）。

以下 SHA256 本轮复算一致，原文件不改写。文件均在 [E4 原证据目录](../../../audits/evidence/2026-10-10-v0.4.2-tdx-historical-execution/)：

| 原资产 | SHA256 |
|---|---|
| tdx_history_responses.jsonl（24请求） | 2644ce583796b412d18c5b4730356e2df95691085dbf0080dfa728ecac08a228 |
| tdx_opening_page_responses.jsonl（9请求） | 03c727b674a5233d873e90da234879c60dc0b222f548c2ec3e5f97298d347dbd |
| tdx_opening_page_followup_responses.jsonl（7请求） | 9989c8a427a4a82fb921fef127b50d7f52a111c9feb033d833ed7842f5aa0ccf |
| tdx_opening_page_final_responses.jsonl（4请求） | 5875d32c619d59f18f3bf5f448f1bc8d5f027fc6ce012409e6ab7fb5659a3a34 |

四份 manifest 均记录 mootdx 0.11.7、tdxpy 0.2.7、固定单主站、4秒超时、无发现/自动重试/心跳、count=800；共44次 status=response、0请求异常。JSONL 是解析器返回原记录，不是 TCP wire bytes，不是独立于 TDX 的第二行情源。无需重复44次查询；代码接入资格需另外记录实际候选调用/版本，不能拿调查样本代替集成测试。

官方证据复用 E3：513100 的 SSE LSTP/stopTime=915 由实际前端映射为 09:15–10:30，响应 SHA256 b0c084336ced5abfd30e2d1ac3b0e2d46c0b35758934e75651f9ae6ad216fd02；159509 官方 PDF 正文为 9/11 开市停牌、10:30起复牌，PDF SHA256 18cf4d821cd8f4de15d515ce0ceef828be5aff3beea30128d4b2049d39647fcd。688432 区间响应 SHA256 1b4980cc2d46993a052a5b3e5a11f4c9186cc0e4787d307cae8534b9f8dd62fb。官方正向区间能用于阻断，不能把空公告、分页计数完整或网站可访问提升为历史状态全集完整。

513100/159509 分钟前60点零量，索引60分别为130484/114141手，取得的逐笔页从10:30开始，与官方区间相容。688432/8月31日分钟全零、逐笔仅15:00 vol=0；其停牌来自官方/发行人，不来自零量。000002/2016-01-04 两接口为空；空值单独 UNKNOWN，已有披露才支持阻断。

### 6.3 三类时间与区间边界

| 字段/概念 | 推荐规范 |
|---|---|
| information_available_at / availability_basis | 当时市场参与者的可知时间及依据；无认证时刻则 null/UNKNOWN。只有来源日期的午夜、事件生效、现在获取、源端参数日期均不能补造为历史09:15或09:30 |
| execution_effective_at/window | 官方状态的生效区间，或成交记录的分钟精度窗口；不转换成 availability |
| retrieved_at | 系统实际事后获取的 aware 时刻；UTC表示可以，与本地 session_date 分开 |
| target_execution_at | D 09:30+08:00；必须与证券/市场/交易日一致；不是请求取回时间 |
| 时间精度 | 日期、分钟、秒分别声明；旧0x0fb5只能声明分钟；官方午夜时间只声明日期，除非真实发布钟点已认证 |

暂停区间推荐为 **[停牌生效, 已认证复牌生效)**。513100 用 [09:15,10:30)，159509 用 [本地开市09:30,10:30)，所以09:30阻断、10:29:59阻断、10:30不再被该区间阻断；后一个结论不授权补做09:30订单，也不承诺没有新事件。

688432 返回的 endStopDate=20260911 是末停牌日，不是9/11零点复牌；8/31至9/11会话都阻断。9/14复牌来自明确公告与成交控制，不由9/14空列表推导。跨日持续区间应按本地交易会话解释，不能把中间周末记为可交易。事件只有日期、结束含义未知或可能延长而未能验证时，不能编造闭合秒级区间。

000002 已认证13:00起停牌不与 W 相交，不撤销开盘模拟成交。官方事件若只在 W 内后半分钟开始、而成交记录只有分钟，无法认证活动先后；推荐 UNKNOWN 拒绝该分钟代理。对 W 之后的后发事件，不追溯修改此前 fill。未知/失效的结束边界不能因“预计复牌”自动允许。

### 6.4 事实合成及失败真值表

新能力是“有界事件检查+真实活动”的资格代理。官方 absence 只表示本次约定证券/日期及区间查询无冲突；**不要求取得全市场空事件完整性认证，也不声称正常状态已获认证**。但约定查询本身失败、部分页、仅查首页、不能查询持续区间或匹配证券/时间含义未认证，均不能假称完成。查询范围/覆盖限制必须保存，未知覆盖不能被硬编码为“无冲突”。

| 官方输入 | TDX输入 | 结论/处理 |
|---|---|---|
| 已认证区间覆盖目标，活动无矛盾 | 缺失、零量或相容的后续活动 | BLOCKED_CONFIRMED；目标时点禁止。已有完整正向阻断足够安全拒绝，无须以TDX成功为前提 |
| 已认证区间覆盖整段W | 同一W有已认证正量活动 | UNKNOWN/source_conflict；保存官方否决与双方证据，拒绝。不得只信TDX |
| 区间覆盖目标，但W内随后已认证复牌 | W正量可发生在复牌后 | 不是必然冲突；目标仍 BLOCKED_CONFIRMED，不延后执行 |
| 有界查询成功、合法空事件或所有事件与W不冲突 | 已认证09:30正量活动，价格/时间/来源合格 | OPEN_ACTIVITY_CONFIRMED；仅进入原日线成交规则，其它资格未通过仍不fill |
| 有界查询成功/无阻断 | 空响应、仅晚页、零量、只有09:25行、只有无时间首分钟正量 | UNKNOWN；不派生停牌，也不允许开盘 |
| 网络失败、HTML挑战页、错误体、截断/partial、覆盖/事件含义未知 | 即使TDX有正量 | UNKNOWN；保留网络/结构/覆盖原因，不记正常空结果 |
| 官方无已知冲突 | TDX网络失败、日期/证券错配、未认证尺度、坏时间、矛盾量价 | UNKNOWN；错误值不进入成功数据 |
| 后发区间起点在W之后 | W活动已认证 | 保持开盘资格；后发停牌不修改已完成模拟订单 |

UNKNOWN 是事实结论，不等于传输失败：应分别报告 source request outcome（success/normal_empty/failed_network/failed_structure/partial/unsupported 等）和 verdict/reason。所有原始子源结果留痕，失败不能因另一源成功被改写为green。冲突的官方否决并未失效，UNKNOWN只是拒绝的最终安全标签。

## 7. Minimal chstockdata Changes

### 7.1 新能力的概念字段下限（待批准，不冻结函数签名）

复用现有 FetchResult/FetchMetadata/FetchAttempt 和 operation/capability 观察方式，不建设通用多源路由。旧 get_suspension_info()/fetch_suspension_info()/fetch_tradability() 的历史 fail-closed、当前日和 legacy envelope 不重定义。

| 分组 | 必需信息 |
|---|---|
| 请求身份 | 规范证券/交易所、instrument类别、市场当地session_date、target_execution_at、资格政策/输出schema版本 |
| TDX活动 | protocol command、解析库/版本、源身份、请求参数及页/覆盖范围；原HH:MM、精度、正量行/活动窗口、量及单位；若返回价格则明确尺度/币种/tick验证和原值 |
| 官方事件 | 二级市场事件类型、start/resume或日会话区间、包含关系、交易所/发行人来源、查询覆盖、分页完整性与已知限制；申赎事件不可当二级停牌 |
| 请求/事实结论 | 每源request outcome/异常类别/正常空结果、OPEN_ACTIVITY_CONFIRMED/BLOCKED_CONFIRMED/UNKNOWN、reason、conflict及官方目标否决；不输出代表全天正常的suspended=False |
| 三类时间 | 真实或UNKNOWN信息时间及basis、effective窗口/精度、aware retrieved_at；不得互相复制 |
| 证据身份 | 原/规范payload checksum、来源/adapter/normalization版本、能力覆盖、引用记录、limitations；缓存命中不伪造请求或改写retrieval |

生产不能为四目标/日期硬编码成功记录；认证范围可以窄且明确，运行时必须取得/回放对应证据。未认证证券、日期、主站或字段组合不通过。本任务不承诺全市场任意历史资格，也不把两个历史点扩张为2016年以来连续覆盖。

### 7.2 协议接入及尺度边界

现有 a_stock.py 有 mootdx client/call 和局部可选导入模式；E4 是调用 client.client 的历史0x0fb4/0x0fb5。现有 tdx_bridge.py/_easy_tdx_bridge.py 是另一 easy-tdx 进程接口，不是已经认证这两个历史命令的bridge；不能仅因名字相同就宣称可直接复用。批准后的 reader 应复用已认证的协议调用方式与现有结果/异常工具，有界请求、无全主站发现/全天扫描，缺可选依赖为明确配置/unsupported失败，不新增必需依赖或全局 monkeypatch 第三方库。

归一化只作用于新能力的0x0fb5返回边界，条件包括经认证的解析器/版本、command、市场及证券类别/支持范围。mootdx 0.11.7 / tdxpy 0.2.7 的四目标样本原价按已确认基金尺度换算；股票688432/000002保持原尺度。**禁止所有证券无条件除10；禁止把VIPDOC基金前缀尺度名单照搬到历史逐笔；未知版本/类别不猜。** 不用“与分钟差十倍就自动除10”作为通用启发式。

原值、转换规则和规范价同时留证据。永久回归冻结四目标真实原字段/期望尺度、来源SHA和分钟对照；保留股票不除10、未知版本/类别拒绝、已规范值不重复换算的负例。当前资产不是wire bytes，所以该回归首先证明adapter对既有第三方解析返回的纠正；不能声称已覆盖上游二进制解码全部字段。未来若换库/升级，重新认证其输出边界，不默认继续应用旧纠正规则。

分钟浮点尾数须在明确证券tick/协议精度下规范比较，不能以宽松容差掩盖十倍错误。未经校验或冲突价格即使不用于fill也不能随OPEN_ACTIVITY成功结果返回。保持VIPDOC现有精确Decimal合同及四目标OHLC/pre_close零容差回归不动。

官方reader只需既有已认证接口/事件字段的最小接入。各交易所能力和持久停牌区间语义按已获得的资格保存；不新建历史公告全集，不引入付费源、不再调查BaoStock。来源性质和非商业可读边界沿用E3，不把一次公开请求推成SLA或再分发许可认证；本轮无新的法律判断。

## 8. Minimal SIOS Changes

### 8.1 已核对的真实路径与不可回避的 engine seam

1. LibraryChStockDataClient.suspension()（F5:456–490）调用旧 get_suspension_info；failed_structure 转SCHEMA_DRIFT。fetch_tradability()（1029–1102）collect/map，_map_tradability()（1244–1287）要求同日snapshot_date、布尔suspended和source，映射成日级TradabilityStatus。
2. _tradability_availability()（1291–1327）仅同本地日期observed_at采用OBSERVED，否则无依据补上海09:30；不使用payload已有information_available_at。新执行能力不能塞进这个布尔映射。
3. EngineClock 给activation09:15和execution09:30；_activate()（892–928）用09:15信息cutoff筛选 self._tradability_by_session，再调用activate_pending_plans()。
4. execution.py:_tradability_gate()（248–256）只看dict的status.permits；SELL/BUY在317/391行调用。没有支持旁路的独立执行事实入口。用UTC默认恰好让上海09:30早于UTC09:15，只会掩盖混用，不构成合法方案。
5. DecisionContext（178–239）及 _known_tradability_through（1132–1140）同时限制session<=T和信息cutoff；quality.py:549–575对late/UNKNOWN为blocking。这些策略PIT限制完整保留。

因此仅利用目前公开入口而不改engine不可行。外部wrapper伪造早知的TradabilityStatus、修改activation钟点、把事后数据当09:15预先可知、子类偷偷改过滤，都不是更小而正确的方案。

推荐最小路径：在现有数据port/adapter增加独立历史开盘事实；以独立集合进入现有engine构造/按session索引；_activate()把该会话和目标执行时点的专用事实传给现有activate_pending_plans()/门禁。该函数已经把激活与日线模拟成交合并计算，应在文档明确：09:15仍是需要早知信息的cutoff，事后事实只认证随后模拟执行，不能解释为真实09:15交易者已经看到它。无需新增执行调度器或逐分钟事件循环。

新模式仅把历史停牌/开盘活动资格从“必须预先可知的状态”中分离；保留T决策和其它确需提前可知的规则。不把OPEN_ACTIVITY映射成整个TradabilityStatus的TRADABLE，也不让它覆盖已确认NOT_LISTED/DELISTED/side阻断/缺规则/其它未知资格。旧PIT状态缺失，只有在缺失明确属于被新开盘能力替代的历史停牌信息要求时才可由合格专用事实补足；无来源范围或未知原因的缺失仍拒绝。真实官方目标停牌永远否决；历史日级SUSPENDED若没有有效区间，不能随意用盘中事件标签阻断整日或任意用成交覆盖，须按新事实来源认证目标时点。

这个模式不是在旧UNKNOWN结果上无条件加一个“有量就通行”分支。需要旧模式无专用事实时原行为不变、新模式必需专用事实时不fallback为允许、两模式输入不混用的测试。资格通过后只继续现有原价/费用/资金/卖出规则；不用TDX活动价格、活动量重算target或订单配额。

### 8.2 跨仓影响表

| 仓库 | 模块 | 必要变更 | 是否改变冻结语义 | 现有测试影响 | 风险 |
|---|---|---|---|---|---|
| chstockdata | a_stock.py现有TDX调用方式、FetchResult相关工具及新能力导出边界 | 有界历史活动/官方事件组合和真实provenance；新功能的具体函数/落文件由批准实施时按现有结构决定 | additive；旧接口不变 | 新能力合同/异常/依赖缺失；旧API全部保留 | 时间、覆盖、请求失败被误当空 |
| chstockdata | 新历史0x0fb5输出边界 | 条件归一化和永久价格回归 | 不影响VIPDOC/旧日线 | A5加真实四目标及股票负例 | 错尺度、双重换算、未知解析版本 |
| SIOS | adapters/chstockdata/provider.py；data/ports.py | 独立执行request/client/map/evidence；修复旧availability fallback | historical 早知假设正式变更；旧port仍PIT | provider旧历史fallback测试修订，旧bool映射条件保留 | 把新事实伪装成旧状态 |
| SIOS | domain/market.py；data/contracts.py | 窄的执行事实类型/编解码，明确window/结论/身份；函数名不预锁 | 新schema，不重定义Availability/TradabilityStatus | canonical/port合同新增 | side或全天含义被夸大 |
| SIOS | data/quality.py | 独立执行用途的覆盖、字段、时间/冲突检查；既有PIT检查保持 | 新用途政策需版本；不能全局放宽UNKNOWN | 既有INFORMATION_TIME保留；新增执行用途验证 | 以隔离为名跳过其它质量门禁 |
| SIOS | data/snapshots.py现有分区/serializer/manifest reader/writer | 新版本执行事实分区及checksum；旧reader/快照仍可按旧模式replay | 新schema/identity；旧快照不迁移覆盖 | snapshot/replay/digest binding新增 | 不落盘导致不可复现 |
| SIOS | backtest/engine.py、backtest/execution.py | 独立执行集合接线，_activate/门禁按有效窗口验证；保持原算术 | 执行资格改变，晚知真实事实可影响fill | legacy late/missing/UNKNOWN原样；新模式隔离/拒绝及A9 | bypass掉其它交易限制 |
| SIOS | research/runner.py:536、research/oos.py:1496现有clock/dataset wiring；本次资格入口 | 只在选择新语义的中国市场运行接线专用事实并注入Shanghai clock | 新运行时钟/资格版本；旧模式继续原版本 | 新接线测试；旧smoke/研究结果不覆盖 | 当前默认UTC导致误资格/时间标签 |
| SIOS | domain/runs.py既有RunManifest及当前运行manifest生成边界 | 使用既有execution_model_version/rule_versions/data_snapshot_digest绑定资格政策、clock、执行证据 | 身份变更；无需泛化RunManifest框架 | manifest identity/reproducibility | 仅描述“上海”但digest不变 |
| SIOS | tests/contract、component、qualification、integration中直接受影响用例及对应架构文档 | §10列出的假设修订和新增验收 | 测试/合同正式修订，强制范围不减 | A7–A11，全部原mandatory仍强制 | 只改断言制造green |
| TradingAgents | 既有兼容资格选择/安装探针 | 无产品修改；同一新候选按E1原选择验证 | 否 | 原相对基线兼容Gate | 七项基线失败不能写成全绿 |

上述均是已存在模块的直接影响说明，不指定新框架或一串新文件。当前FIX_ONLY没有这些跨仓改动授权；全部待Owner决定。

现有CanonicalDataset（quality.py:122–165）只有PIT tradability等集合，snapshots.py:256–273的serializer/records-kind固定；不能把执行事实混入旧tradability分区来省代码。最小版本化分区扩展须支持旧snapshot reader/mode，知识cutoff只筛决策信息，执行证据按其用途保留事后获取时间。决策质量若声明需要某项PIT状态而无法取得，仍BLOCKING；新执行分区不是“全数据PIT已通过”的替代声明。

RunManifest（runs.py:36–119）已有execution_model_version、rule_versions和data_snapshot_digest进入identity_digest。优先在既有身份容器编码本次资格政策/市场clock及快照摘要，不另造manifest体系；读写验证必须确保缺必要身份的“新模式”拒绝，不凭可选文字字段重放。

### 8.3 最小时区合同及真实入口影响

保持EngineClock默认UTC用于旧语义及原fixtures；新中国市场模式显式EngineClock(timezone=Asia/Shanghai)。实现表达可按现有tzinfo模式，输出必须有+08:00及市场时区身份，禁止naive钟点。现有runner/oos没有注入市场timezone，故只在provider里转换时间还不够，运行入口接线也直接受影响；此处不全局重写默认。

本轮从B4提取EngineClock原类只在内存执行单例，得到：

| 本地用途 | 正确上海时刻 | 等价UTC绝对时点 | 旧默认UTC同钟点转换成上海 |
|---|---|---|---|
| activation | 2026-09-11 09:15+08:00 | 2026-09-11 01:15Z | 17:15+08:00 |
| execution | 2026-09-11 09:30+08:00 | 2026-09-11 01:30Z | 17:30+08:00 |
| decision | 2026-09-11 15:30+08:00 | 2026-09-11 07:30Z | 23:30+08:00 |

这是实际clock行为证据，不是完整研究重跑。后续测试用相同UTC绝对时点表示事件，须得到相同包含关系/资格；“UTC09:30”与“上海09:30”必须被识别为不同目标。上海15:31才可知的T事实在新15:30 cutoff拒绝，而旧默认23:30可能纳入；必须披露这一风险，不能自动重算M0/M1去改旧结论。新模式以新clock/policy/digest生成新身份。

## 9. Backward Compatibility

旧get_suspension_info历史失败、安全修复和current-day兼容继续；旧fetch_tradability保守逻辑、日历/退市date guard、UNKNOWN不转布尔继续。新能力不承诺恢复完整historical suspension，消费者也不能把新代理的success当旧PIT port成功。

修正SIOS availability会改变错误的historical EXCHANGE_RULE输出，属于必要显式契约变更，不伪称完全行为兼容。原冻结源码/fixtures/研究结果保持只读；旧mode和旧schema按原版本replay，不能用修正代码回写已有M0/M1结果。新数据/政策/时钟影响Fill、现金、持仓、NAV和后续决策可能正常发生；A7的隔离比较锁定同一T已形成的目标与planned sizing，并不要求后续所有会话仓位和收益不变。

新能力默认不得被旧消费者隐式选择；没有新schema、合格执行证据及明确模式的新运行拒绝。候选资格只沿用受控版本准入的做法，不更新正式0.3.0 pin，不用保留旧pin作为升级目标达成。统一新候选Gate/Owner放行后才讨论正式版本变更。

## 10. Test Impact Matrix

### 10.1 三类测试

| 类别 | 现有测试/业务目的 | 处理与等价边界 |
|---|---|---|
| 原样保留 | chstockdata tests/test_suspension_source_semantics.py；test_suspension_structured.py、test_astock_listing_status.py已有安全/分页/当前日/envelope合同 | 历史fail-closed、空/未知区分、当前复牌、未来事件、cache不冒充新请求；新能力不改这些业务断言 |
| 原样保留 | tests/test_vipdoc_price_scale.py及四ETF精确价格合同 | VIPDOC八类尺度、OHLC/pre_close精确Decimal继续；不借逐笔缺陷重改日线 |
| 原样保留 | SIOS tests/component/test_no_lookahead.py:127、160、203、227、267、293 | 未来变异不改变T目标；next open只影响fill；未来/晚知行不能进DecisionContext。新执行集合加变异测试，不重写原断言 |
| 原样保留 | tests/component/test_tradability.py:75、102、126、142、171、207；test_execution_accounting.py、test_event_order.py、test_corporate_actions.py | legacy的late/UNKNOWN/missing/suspended/side阻断，以及费用、滑点、T-close、资金、手数、all-or-none、corporate-action replan全部保留 |
| 原样保留 | tests/component/test_foundation_adversarial_boundaries.py；Golden/parity、integration/test_snapshot_replay.py、test_manifest_identity.py、test_reproducibility.py及研究结果 | 原不变量和历史artifact/digest不覆盖；新模式另加必要情景 |
| 正式变更假设 | tests/contract/test_chstockdata_provider.py:796 test_historical_session_uses_the_exchange_rule_open_time | 该用例明确断言无依据历史09:30回填；改为真实时间保留/未知/日期粒度不补造，保留retrieved_at验证。旧冻结测试仍作为历史基线，不在本轮修改 |
| 正式变更假设（限前提） | 同文件:825 test_absent_suspension_record_is_tradable；Library client suspension说明 | 当前测试实际上输入已给出的suspended=False，而非证明事件缺席完整性；可保留布尔映射本身。其“历史缺席可推出False”的源资格假设必须撤回/加专门拒绝测试，不能仅重命名绕过 |
| 正式增加模式 | test_tradability.py:142 late-at-activation | 原PIT路径晚知拒绝保持；新模式晚知/未知信息时间且执行事实合格可以继续模拟，另立合同。不能把原断言直接改成所有晚知都可交易 |
| 正式变更假设 | qualification/test_chstockdata_etf_gate.py:242 原mandatory live历史成功断言 | 按§10.2调整为执行能力实际合同；原测试保留为mandatory，不删/skip、不单靠mock替代live |
| 新增必要 | 四ETF和两临停、持续停牌/复牌、13:00边界、2016/2022、逐笔尺度、异常/冲突/范围 | A1–A6；固定真实数据SHA+当前候选reader真实调用；禁止按ticker/日期硬编码结论 |
| 新增必要 | port/schema/quality、engine输入隔离、上海clock接线、序列化/replay/identity | A7–A9、A11；执行分区不穿过策略PIT、篡改证据导致digest/重放失败、旧reader行为继续 |
| 新增必要 | live逐能力执行及四ETF corporate actions/freshness | A10，不得因某项提前assert失败让其它能力未执行却标PASS |

### 10.2 原 mandatory live 逐断言追溯与保全

原test_live_tradability_adjustment_and_freshness（242–261）对matrix_requests的每只ETF顺序执行如下。窗口、证券和ETF instrument_kind继续使用冻结matrix；本轮不能修改。

| 原断言/调用 | 业务目的 | 原假设为何需要改变/真实覆盖边界 | 推荐的新强制覆盖 |
|---|---|---|---|
| fetch_tradability(...); assert is_success（247–248） | 目标历史执行日具备可信停复牌/交易资格 | 旧port索取PIT布尔，Eastmoney能力和09:30回填都不成立；现在安全失败是正确行为 | 旧历史PIT查询必须失败或显式UNKNOWN且不伪造时间；新开盘能力实际请求四ETF均OPEN_ACTIVITY_CONFIRMED；带该证据跑真实consumer执行入口，确定可进入原日线规则。官方两临停和异常/未知仍无fill |
| assert tradability.records（249） | 成功结果有真实记录，不接受空success | 原断言只非空，未验证请求身份/状态 | 新记录按四个请求一一匹配证券、日期、目标、source/hash/时区/结论，拒绝空/错配/unknown。不得只assert新is_success |
| fetch_corporate_actions(...); assert is_success（251–252） | ETF公司行为与adjustment供应能力 | 原逻辑被前一失败短路；其正确性目的仍成立 | 真实ETF请求保留success；合法空actions仍按coverage判定，不要求强行非空。保留原offline partial/missing ex-date/不支持rights及ETF kind路由合同 |
| fetch_daily_bars（254） | 供RAW与时间/freshness验证的数据 | 原测试未先assert bars.is_success/nonempty，失败且空records可能使循环不检查 | 增强为success、非空、范围/coverage合格；保留其它live routing/OHLC/pre_close/units/calendar/history断言 |
| assert adjustment_mode == RAW（256） | 防执行价格被复权；避免公司行为重复入账 | 无需改变 | 每只ETF每条bar原样强制；现有corporate-action账本测试继续 |
| assert retrieved_at is not None（257） | 实际获取时刻留痕 | 仅非空不等于数据新鲜；不能把测试名字视为完成所有freshness | 原断言保持，并验证aware获取时间；对既有quality策略执行freshness/覆盖检查及stale/missing反例。历史研究用既有 intended-session政策，不误要求目标日等于今天 |
| available_at非空则<=retrieved_at（258–261） | 可知与获取先后合理 | 原条件式检查允许未知，且不证明preopen可知 | 原检查保持；UNKNOWN保持明确。新执行事实有效窗口与retrieval独立，策略晚知仍拒绝；不能按execution time补造available_at |

建议保留原测试名称作为mandatory编排，内部子能力独立收集结果、最后统一断言，或拆成明确全部mandatory的子测试并由原编排验证覆盖集合。失败不得让actions/freshness不执行后被计作PASS。最终资格记录四ETF×每一子能力结果；mandatory selector若改变，冻结新清单并验证无deselected/skip遗漏。其余四项原live仍需执行，recorded tests仅作确定性回归，不能替代实际源/实际候选live。

这是“正确性目的等价或更严格”的设计映射，不声称旧完整历史PIT能力已经恢复。旧历史能力缺口仍公开；替代的是Owner本次提出的开盘执行目标。若Owner坚持旧live必须证明完整历史PIT状态而不批准这一变更，A10仍不足，本方案无法宣称升级合格。

## 11. Acceptance Criteria A1–A11

以下保留Owner编号和目标，加可证伪的证据要求。**当前均不是新实现验收PASS。** 已有证据可复用作fixtures/设计依据，未来候选接入与消费者链路必须另有证据。

| 条件 | 授权后必须取得的验收证据/失败条件 | 当前支持与缺口 |
|---|---|---|
| A1 四ETF开盘活动 | 四目标×2026-09-11，保留真实0x0fb5 09:30正量、0x0fb4量一致及协议/尺度；经新reader和真实adapter得代理资格；无TDX价格替换raw日线open | 原记录4/4已复核；新reader/consumer资格未实现。仅09:25或首分钟不能通过 |
| A2 官方临停拒绝 | 513100/159509上述官方区间，上海09:30无fill；09:15/09:30起点含、10:30结束不含；原09:30订单10:30不补做 | 官方/TDX相容样本具备；端到端门禁未实现 |
| A3 持续停牌与盘中边界 | 688432 8/31、9/11阻断、9/14公告+活动恢复；000002 2015-12-18开盘活动与13:00停牌共存，早盘fill不撤销；日期结束不当午夜复牌 | 正向事件及E2/E4活动具备；精度模糊区间/延长需UNKNOWN |
| A4 历史覆盖 | 510300/2022-12-30及2016-12-30两点成功有明确单主站/范围；未取得或未认证证券/日期/页继续UNKNOWN；报告支持边界，不声明连续全历史 | 两历史点已取得；任意日期连续覆盖未经认证，不要求全市场库 |
| A5 逐笔价格 | mootdx0.11.7/tdxpy0.2.7/0x0fb5四目标真实错误字段必须先触发错误/校验失败；认证归一化后符合固定期望与分钟对照；688432/000002不除10、未知版本/类别拒绝、已规范输入不重复换算；错误值不能success | 四目标真实十倍缺陷和原SHA具备；永久回归未写；不改变VIPDOC已通过精确测试 |
| A6 失败/缺失 | 官方合法空+TDX正量可为代理；官方空+TDX空/零/仅竞价为UNKNOWN；网络/错误体/HTML/partial/错日期/坏时区分别typed outcome；官方覆盖W+TDX正量为UNKNOWN冲突带否决；任何不合格均无fill | 原空/零量、分页、格式错误/挑战页支持设计；故障/冲突注入和集成待实施 |
| A7 策略PIT | 锁同一T数据/初始状态，变异T+1执行集合的活动、信息时间、retrieval/区间，只能改变T+1 fill/拒绝，不改变T signal/target/权重/universe/planned_quantity；捕获DecisionContext确认无该集合；需要PIT信息的策略晚知/UNKNOWN照旧拒绝 | 冻结隔离合同和测试存在；新集合隔离待验证，不比较后续全部NAV不变 |
| A8 时区 | 三用途本地/UTC等价表；边界等值包含/排除、UTC09:30错目标拒绝、naive时间拒绝；runner/oos/新qualification实际注入Shanghai；旧default保持；clock身份变化导致新runID | 本轮B4原clock单例已执行；接线/identity永久测试待实施 |
| A9 原成交合同 | 原component/Golden费用、滑点/tick、RAW、T-close、global affordability、手数/卖出规则、corporate-action replan、all-or-none/UNKNOWN拒绝原样过；相同合格资格下ledger一致；改变活动量不改变订单配额或fill价格；无复牌retry | 原离线结果已核对；新模式不能用旧PASS替代 |
| A10 消费者live等价 | §10.2四ETF全部能力真调用且各自有结果；旧historical fail-closed/PIT诚实、新执行4/4及临停反例、actions/RAW/availability/freshness/stale全部强制；五项原live与新增mandatory零skip/遗漏，失败完整汇总 | 原强制live失败、后续断言未执行；设计映射齐全但待Owner批准/实际验证 |
| A11 统一候选Gate | 一个新源码快照/新wheel SHA绑定package/构建安装/core及可选profiles、SIOSprovider/offline/Golden/ETF/全部live、TA原相对兼容；真实import/version、受控版本准入和新schema/policy/clock/证据digest留痕；旧B3及M0/M1不覆盖 | E1旧B3部分通过、live仍FAIL；本轮不构建或复跑。新候选全部通过且Owner独立接受之前不能发布 |

A1–A6的未知/拒绝不是“降级成功”；资格报告必须保存原因。A11的TA“通过”按原冻结相对兼容准则：原选择123 passed/7相同基线失败及五探针，不要求未经批准全仓修复，也不把七失败隐藏。

## 12. Non-goals

完整保留Owner§7，并保留本次任务第四部分：

- 不建设订单簿、队列概率、竞价撮合重建、高频或通用分钟回测引擎。
- 不实现日内部分成交、活动量分配、限价队列或复牌后自动补单/重试。
- 不引入付费源、全市场历史分钟仓库、完整历史公告全集、完整PIT数据库。
- 不扩大ETF产品资格（两只QDII仅source控样），不把股票负例推广为所有ETF。
- 不全面重构SIOS引擎、策略、Portfolio或新建通用多源路由。
- 不重算/覆盖冻结M0/M1，不重跑研究，不改变正式pin。
- 不借此解决所有免费源稳定性，不再调查已否决BaoStock，不重跑44次TDX查询，不无边界搜索GitHub。
- 不把0x056a/0x0fc6文档能力当运行时证据，不为本分钟代理自动增加其资格调查。
- 本轮不实现、不改测试/依赖、不构建/替换wheel、不合并/提交/推送/tag/发布，不生成实施Prompt。

## 13. Risks and Unresolved Decisions

| 决策/风险 | 分类 | Owner需要决定或保留的明确边界 |
|---|---|---|
| O1 分钟代理是否可接受 | CONTRACT_CONFLICT；严格整点为INSUFFICIENT_EVIDENCE | 审批R1及§6.1；可接受则无需队列/竞价新能力。拒绝代理则当前方案不达标，不能悄悄升格数据能力 |
| O2 事后执行事实通道 | CONTRACT_CONFLICT | 审批R3及§8窄改动；该事实不早知但可用于历史模拟，执行UNKNOWN仍拒绝。不能仅授权adapter却让实现暗改engine |
| O3 官方查询与覆盖 | UNRESOLVED_RISK | 审批有界无已知冲突+真实活动的代理，而非完整负向状态认证；读取持续区间/分页须符合当前源能力。不能认证必要查询范围则该请求UNKNOWN，不扩张全事件库 |
| O4 live能力替代 | CONTRACT_CONFLICT | 审批R5逐断言映射及新mandatory清单；完整历史PIT能力未恢复的限制继续披露。若仍要求旧完整状态，则A10无法通过 |
| O5 Shanghai clock与运行身份 | CONTRACT_CONFLICT / UNRESOLVED_RISK | 审批R4仅新运行入口；旧UTC偏移影响未量化，不重算旧研究；新结果采用独立版本/证据身份 |
| O6 上游解析/连续获取 | UNRESOLVED_RISK | 旧解析记录非wire bytes、只有一主站/有限点；版本或格式变化须拒绝/再认证，免费来源没有稳定覆盖保证。不是本轮新架构理由 |
| O7 实际接入仍未验收 | INSUFFICIENT_EVIDENCE | A1–A11尚无新产品实现证据；源样本支持设计不承诺Gate恢复，后续失败应修正阻断而非豁免 |
| O8 原证据保留边界 | NON_BLOCKING_LIMITATION（设计），未来集成待证 | 官方部分原response只保存摘要/hash；TDX保存parsed rows。未来资格要保存可重放对应输入，不得把缺失wire/raw说成已经捕获 |

原腾讯上游血缘未认证、TA七项基线失败和其原依赖环境边界沿用E1，不扩大为本CR新工程。全市场归档/交易队列是FUTURE_ENHANCEMENT；没有任何SPECULATIVE_CONCERN被转换成必做架构。

当前不需要新的无界来源调查。若未来必要的单一字段/命令尚未认证，只提出“指定证券/日期、指定返回字段及可证伪预期”的一次证据需求；不得以完善设计为由重开此前调查。Owner审批对象就是本文件R1–R5、§6–11的推荐规范及这些明确限制。

## 14. Gate and Owner Authorization

### 14.1 当前报告字段

以下PASS/DEFINED如出现只描述设计的边界，不是实现/Release资格。本次原草案仍需R1–R5正式修订，live覆盖仍待批准，故两处REWORK保留。

~~~ini
CURRENT_DECISION = CHANGE_REQUEST
OWNER_PROPOSED_CR_REVIEWED = YES
DESIGN_CONFORMANCE = REWORK
SOURCE_EVIDENCE = SUFFICIENT_FOR_DESIGN
EXECUTION_EVIDENCE_SEMANTICS = DEFINED
SIOS_ENGINE_CHANGE_REQUIRED = YES
SIOS_TIMEZONE_CONTRACT = DEFINED
MOOTDX_PRICE_REGRESSION_REQUIRED = YES
TEST_COVERAGE_EQUIVALENCE = REWORK
SCOPE_EXPANSION = NO
READY_FOR_OWNER_DESIGN_REVIEW = YES
READY_FOR_IMPLEMENTATION_AUTHORIZATION = NO
SIOS_UPGRADE_QUALIFIED = NO
RELEASE_GATE = FAIL
PUBLISH_AUTHORIZED = NO
~~~

SOURCE_EVIDENCE足以设计有限代理；不表示来源全集/严格整点或新实现已认证。TEST_COVERAGE_EQUIVALENCE的REWORK表示原live假设要经正式变更并实现本覆盖映射；不是要求删除原mandatory。推荐方案已经完整可审议，但没有Owner approval记录。

### 14.2 Gate顺序与停止

1. Owner审议原草案和R1–R5，明确批准或要求修订；审查者不能代签。
2. 只有Owner正式批准并另行授权实施，才可能执行窄的跨仓合同/产品/测试改动。本文件不授权该动作。
3. 实施完成后按A1–A11以一个新候选取得独立证据；任一强制项失败或证据不足分别FAIL/INSUFFICIENT_EVIDENCE。
4. Release Gate全部满足仍须Owner独立验收和明确发布授权；不自动升级阶段或发布。

**本轮结束于第1步前的可审议文档交付。** 不生成产品实施Prompt，不启动下一Phase。

### 14.3 本轮文档核验与交接

本轮核验是只读源码/原证据核对、B4原EngineClock内存单例和文档完整性检查，不运行产品测试、网络查询、构建或策略研究。原保存结果经JUnit/exit直接核对：package 724 passed/1 skipped；SIOS provider 67 passed、offline 929 passed/5 skipped、ETF/Golden/smoke 160 passed/5 skipped；mandatory live 4 passed/1 failed；TA原选择123 passed/7 failed。它们属于原统一候选执行，不能标为本轮新测或新模式资格。

收口核对：Owner原文引用完整、14个必需章节、逐项追溯/跨仓影响/三类测试/A1–A11齐备；git diff --check及新增文档的whitespace检查通过。进入本轮的759个chstockdata文件（含wheel/sdist）逐字节SHA256未变，新增文件只有本文；566个原候选文件继续匹配。SIOS本轮保护清单244个tracked/non-ignored文件及当前HEAD未变；冻结B4的核心blob/tree身份保持。SIOS现有Git环境的status命令返回“must be run in a work tree”，故不声称其工作树clean；用进入/收口文件哈希核对无本轮写入。没有Git提交、暂存或消费者源码修改。

- 当前phase/step：v0.4.2 FIX_ONLY阻断下，CHANGE_REQUEST_DESIGN_REVIEW文档交付；未推进Phase。
- Commit与工作树：chstockdata HEAD 42bd44ef4d695aa3e88cfab4ebc3417660d0437a，无新commit；原未提交源码/测试/文档/证据保留，本轮仅新增本文。原候选tree和wheel身份见B2/B3。
- Gate与依据：Release/SIOS FAIL；E1真实mandatory live失败，当前仅设计，无新的A1–A11集成证据；原草案REWORK，推荐语义可供Owner审议。
- 未解决阻断/范围：Owner尚未批准R1–R5；来源/解析/时钟/消费者新模式未实现或资格验证。无本轮实施范围扩大。
- 推荐下一动作：Owner对本文作正式设计审议，尤其分钟代理、执行隔离、上海clock及mandatory live替代；不是下一Phase或实施授权。

学习交接：本次问题是分钟级真实活动能否支持冻结日线执行目标并保持PIT。原记录支持有界代理、暴露价格尺度错误，真实调用链证明需engine窄接线；它不支持严格整点或完整状态全集。下一决策是Owner选择是否接受明确近似与合同修订，不能以文档完成声称升级或发布已合格。

