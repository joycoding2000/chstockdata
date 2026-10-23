# Personal Systematic Investing OS
## v0.6 Product-Complete Final Architecture Decision

> **版本**：v0.6 — M1–M3 Product Completeness Review
> **日期**：2026-09-15
> **状态**：在 v0.5 Product-First 基础上补齐 Investment Product Specification。M0 Design Gate 已通过且正在实施；**本版不重开、不修改 M0 scope**。
> **最高原则**：先交付一个真实可用、每天能给出明确操作指示的个人投资系统；AI Investor 保持 Shadow Research，除非未来有独立、长期、严格证据支持新的 Production Authority 决策。
> **M0 下位权威**：已批准的 `docs/architecture/*`、`docs/plans/M0-implementation-plan.md`、`OPEN_QUESTIONS.md` 继续控制 M0 的具体金融、数据、回测与执行语义。

---

# 0. Executive Decision

本项目不是量化开发框架，也不是“研究 AI 会不会炒股”的实验平台。

第一阶段产品必须直接回答：

> **今天该买什么、卖什么、持有什么、目标仓位是多少；没有足够证据时明确 HOLD / CASH / NO ACTION。**

因此，完整产品不能只有：

```text
Data + Backtest + Portfolio + Risk + Scheduler
```

还必须有一层过去没有定义完整的：

> **Investment Product Specification / 投资产品规格**

它回答：

```text
这个账户为谁管理？
目标和风险约束是什么？
哪些资产允许投资？
运行哪些策略？
多个策略如何组合？
什么证据允许策略进入 Production？
每天何时决策？
用户怎样执行？
没执行、部分执行、临时手工交易怎么办？
系统怎样判断过去的决策是否有效？
策略什么时候暂停、恢复、退休？
```

v0.6 将产品拆成四个不可混淆的层：

```text
Investment Mandate
      ↓
Approved Production Investment Bundle
      ↓
Deterministic Production Runtime
      ↓
Outcome / Strategy Health Loop
```

AI Copilot 服务于 Research。
AI Investor 只拥有独立 Shadow Portfolio。
正式交易通知只来自 Quant Production。

---

# 1. Investment Product Specification 不等于“激进 / 平衡 / 保守”

“激进、平衡、保守”属于 **Investment Mandate 的用户可读标签**，但不是完整产品规格。

真正需要持久化、版本化的是明确约束，而不是模糊标签。

## 1.1 InvestmentMandate

新增一等对象：

```text
InvestmentMandate
```

至少包含：

- `mandate_id / version`；
- 管理账户 / Managed Book 身份；
- base currency；
- 投资目标；
- 投资期限；
- 目标收益区间；
- 风险容忍与回撤目标；
- long-only / leverage / short / derivatives 权限；
- 允许资产类别；
- 禁止资产类别；
- 流动性需求；
- 允许的最大权益暴露；
- Stock Satellite 最大预算规则；
- 是否允许真实 CASH；
- turnover / rebalance 偏好；
- 手工执行约束；
- benchmark policy 引用；
- account fee / tax profile 引用；
- owner approval / effective date。

## 1.2 当前已经明确的 Owner Mandate

当前项目已有的方向：

```text
目标：长期复利 + 控制回撤
目标年化：10% ~ 15%（Portfolio Objective，不是保证）
希望 MDD：<= 10%（Release/Risk Evidence，不是优化目标）
频率：中低频，周到月为主，日线决策
资产：ETF Core + Stock Satellite
方向：Long-only
杠杆：不使用
做空：不使用
衍生品：MVP 不使用
执行：人工执行
正式指令：Quant Production
AI Investor：Shadow only
```

上述数值和限制应写进 `InvestmentMandate`，而不是散落在文档和代码常量里。

## 1.3 不在 v1 建三个独立产品

当前是单用户个人系统，不应立即实现：

```text
Conservative Product
Balanced Product
Aggressive Product
```

这会把研究、验证、策略组合数量直接乘三。

v1 应只有：

> **一个 Owner-approved active InvestmentMandate。**

未来若需要多风险档位，可以把“保守 / 平衡 / 激进”作为经过独立验证的 Mandate Templates，而不是简单把仓位乘 0.5 / 1.0 / 1.5。

---

# 2. Managed Book：系统到底管理哪一笔钱

这是 M3 前必须补齐的一等产品边界。

新增：

```text
ManagedBook
```

系统不能默认“用户全部证券资产都归系统管理”。

`ManagedBook` 至少定义：

- account/book ID；
- 该系统管理的现金和证券范围；
- 当前实际 equity；
- external cash flow；
- external/manual trades；
- reconciliation status；
- active InvestmentMandate；
- active ProductionBundle。

## 2.1 100,000 RMB 的含义

保持已批准原则：

- Backtest / Goldens 默认 100,000 RMB；
- Paper inception 默认 100,000 RMB；
- Live Production 使用 **reconciled actual equity**；
- 可额外展示 normalized CNY 100,000 model portfolio。

## 2.2 存取款不是收益

Deposit / Withdrawal 必须是 explicit external cash flow。

它：

- 改变 account equity；
- 不算策略 P&L；
- 触发 reconciliation；
- 后续 TargetPortfolio 基于新实际 equity 计算。

---

# 3. Strategy Acquisition：策略从哪里来

产品默认 **自带策略**。

用户不需要自己写策略才能使用本系统。

策略来源分为四类：

```text
A. Built-in Curated Strategies       ← M1 主路径
B. Papers / Books / GitHub / Reports ← Research source
C. User Ideas                         ← 可选高级 source
D. AI Hypotheses                      ← Research source
```

所有来源进入同一条验证链：

```text
Source
  ↓
Hypothesis
  ↓
Strategy Spec
  ↓
Implementation
  ↓
Research Backtest
  ↓
Robustness
  ↓
OOS
  ↓
Walk-forward
  ↓
Paper Forward
  ↓
Approval
  ↓
ApprovedStrategyRegistry
```

## 3.1 Built-in 是默认产品体验

第一次安装产品后不能出现：

> “请先编写你的量化策略。”

默认必须已经存在产品维护的策略候选与批准版本。

用户策略和 AI 生成策略属于扩展能力，不是使用前置条件。

## 3.2 Strategy Registry

新增：

```text
StrategyRegistry
```

每个 immutable StrategyVersion 至少记录：

- strategy ID / version；
- source / provenance；
- economic thesis；
- intended universe；
- signal horizon；
- primary evaluation horizon；
- parameters；
- preregistered parameter research range；
- benchmark；
- known failure regimes；
- backtest evidence；
- robustness evidence；
- OOS / walk-forward evidence；
- paper evidence；
- status；
- approval digest。

状态建议：

```text
IDEA
SPECIFIED
RESEARCH
ROBUSTNESS_PASS
OOS_PASS
PAPER
APPROVED
DEGRADED
SUSPENDED
RETIRED
REJECTED
```

Production 只能加载 `APPROVED` 版本。

---

# 4. Production Investment Bundle：真正每天在跑的是什么

这是 v0.6 最重要的新对象。

有若干好策略仍然不足以构成产品。

新增：

```text
ProductionInvestmentBundle
```

它是一个完整、冻结、经过整体验证的投资政策版本。

例如：

```text
ETF_CORE_BUNDLE_v1.0

Mandate
  = OWNER_MANDATE_v1

Universe
  = ETF_CORE_UNIVERSE_v1

Strategies
  = AbsoluteTrend_v1.1
  + RelativeMomentum_v1.0
  + DefensiveAllocation_v1.0

StrategyCompositionPolicy
  = ...

PortfolioPolicy
  = ...

RiskPolicy
  = ...

RebalancePolicy
  = ...

BenchmarkPolicy
  = ...

CashPolicy
  = ...

ExecutionPolicy
  = ...

EvidencePackage
  = ...

status
  = APPROVED
```

## 4.1 Production 不加载“仓库中的策略”

Production 只加载：

```text
Owner-approved ProductionInvestmentBundle
```

而不是动态扫描：

```text
strategies/*.py
```

## 4.2 Bundle 的任何实质变化都产生新版本

以下变化都不是“普通配置修改”：

- Strategy version；
- Strategy parameter；
- Universe；
- Strategy composition；
- Risk cap；
- Rebalance cadence；
- Benchmark；
- Cash semantics；
- Execution semantics。

任何影响投资行为的变化都生成新的 Bundle version，并重新走适用验证 Gate。

---

# 5. ETF Core v1：M1 必须实际交付的 Strategy Pack

M1 不再定义为模糊的 “ETF Core Quant”。

正式定义：

> **M1 — ETF Core Strategy Pack & Investment Policy**

第一代策略保持少而清晰。

## 5.1 Absolute Trend

回答：

> 是否应该承担该风险资产暴露？

候选机制：

- long-term moving-average trend；
- 6/12M absolute momentum；
- 其他有明确经济逻辑并预注册的简单版本。

## 5.2 Relative Momentum

回答：

> 在允许承担风险时，哪些资产更值得配置？

不是简单增加更多技术指标，而是资产之间做相对选择。

## 5.3 Defensive / Risk Allocation

回答：

> 当前组合应该承担多少风险？

可以基于经过验证的：

- trend state；
- volatility；
- drawdown state；
- breadth / liquidity（只有数据和证据支持时）。

它影响 portfolio risk budget，而不是自由创造新的 Alpha。

## 5.4 不做高度相关指标投票

不以：

```text
MA + MACD + RSI + KDJ + Bollinger majority vote
```

作为第一代核心策略设计。

优先保证三个机制回答不同问题：

```text
值得持有吗？
持有什么？
持多少？
```

---

# 6. ETF Universe 与 Historical Proxy Policy

M1 以前必须明确。

## 6.1 ETF Universe

只从 M0 通过资格的 subtype 中选择：

- domestic broad-based equity ETF；
- gold ETF；
- bond ETF。

第一版 Universe 必须：

- 小；
- 流动性足够；
- 经济暴露不同；
- 避免同质化；
- 具备足够数据质量；
- 记录 AUM / liquidity / listing-age eligibility policy（具体阈值 M1 决定）。

## 6.2 ETF 生命周期

Universe 不能假设 ETF 永远存在。

必须处理：

- 新上市；
- 流动性恶化；
- 停牌；
- 清盘 / 退市；
- 跟踪标的变化；
- 基金合并/重大合同变化。

产品不得在 Production 中静默替换成“类似 ETF”。

替换是 Universe / Bundle version change。

## 6.3 Historical Proxy Policy

如果 ETF 自身历史不足，不允许为了长回测事后拼接一个有利指数。

必须预先规定：

```text
DIRECT_ETF_HISTORY_ONLY
```

或明确版本化的：

```text
INDEX_PROXY_BEFORE_ETF_INCEPTION
```

如果使用 proxy：

- proxy 与 investable ETF 必须分开标识；
- proxy 只用于研究信号/历史 regime，不假装当时 ETF 可交易；
- 不把 ETF tracking error、费用、流动性倒填到历史；
- 报告中明确真实可投资区间；
- Holdout / Paper 仍使用真实可交易资产。

---

# 7. Strategy Composition：多个策略如何变成一个 TargetPortfolio

必须在 M1 的 Bundle 中预注册。

不能让策略“各自给一个 BUY”后再临时人工判断。

可能的结构必须明确选择一种并验证，例如：

```text
1. Hierarchical
   Trend eligibility
      ↓
   Relative Momentum selection
      ↓
   Defensive / Risk scaling

2. Sleeve / Risk-budget composition
   Strategy A budget
   Strategy B budget
   Strategy C budget
```

第一版更倾向 **hierarchical / economically interpretable composition**，而不是无约束信号加权。

无论选择哪种：

- composition order 固定；
- strategy contribution 可追踪；
- non-commutative rules 有测试；
- 不能看到结果以后再改组合权重。

---

# 8. Investment Mandate → Portfolio/Risk Policy

“平衡 / 保守 / 激进”最终必须落到可执行约束。

例如不是：

```text
profile = BALANCED
```

然后程序自己猜。

而是：

```text
max_equity_exposure = versioned rule
max_instrument_weight = versioned rule
satellite_cap = versioned rule
cash_floor = versioned rule
volatility_target = versioned rule
portfolio_drawdown_throttle = versioned rule
```

v1 只有一份 active Owner Mandate，因此只需验证一个正式 Policy，不需要一次做三套风险档位。

---

# 9. Validation & Promotion Gate：什么叫“策略验证通过”

M2 必须把“通过”变成机器和人工都可检查的 Gate。

至少覆盖：

- Research / Validation / Final Holdout 隔离；
- parameter preregistration；
- 参数扰动不过度崩溃；
- cost/slippage stress；
- multi-window walk-forward；
- OOS performance；
- benchmark excess；
- regime breakdown；
- sample sufficiency；
- profit concentration；
- turnover / capacity；
- drawdown depth + underwater duration；
- Paper Forward；
- operational completeness。

## 9.1 允许“不发布”

产品时间表不能强迫研究结果。

如果 M1/M2 的候选策略没有通过：

> **M3 Production Release 延期。**

不能为了“必须有产品”从失败策略中挑一个最好看的上线。

## 9.2 Bundle 也必须整体验证

单策略 APPROVED 不等于 Bundle APPROVED。

组合必须重新验证：

- correlation；
- capital competition；
- turnover；
- overall MDD；
- risk budget；
- benchmark；
- regime interaction；
- costs。

---

# 10. Onboarding：用户第一次启用产品怎么办

M3 之前必须有正式 onboarding semantics。

## 10.1 创建 Managed Book

首次使用时：

1. 选择 / 确认 InvestmentMandate；
2. 确认 Managed Book 的账户范围；
3. 输入 / 导入真实现金与持仓；
4. 进行 initial reconciliation；
5. 绑定 active ProductionInvestmentBundle；
6. 生成首次 `PortfolioAdoptionPlan`。

## 10.2 PortfolioAdoptionPlan

如果用户已有非目标持仓，不能自动假设：

> 第一天全部清仓再建仓。

Adoption Plan 需要明确：

- 哪些资产属于 Managed Book；
- 哪些现有持仓需要退出；
- 是否允许分批迁移；
- 迁移期间如何计算风险；
- 迁移未完成时下一日 Target 如何处理。

MVP 可以选择保守简单政策，例如：

> 先人工确认初始持仓与迁移计划，再进入正常 Production 状态。

但不能没有政策。

---

# 11. Daily Product Lifecycle：用户一天如何使用系统

## 11.1 EOD

收盘后：

```text
Finalized T Data
      ↓
Data Quality Gate
      ↓
Approved ProductionInvestmentBundle
      ↓
Quant Strategies
      ↓
Portfolio + Risk
      ↓
Locked TargetPortfolio for T+1
      ↓
EOD Decision Summary
```

## 11.2 Pre-open

开盘前：

```text
Locked Target
   +
Reconciled Portfolio
   +
Calendar / Tradability / Corp Action / Kill Switch
      ↓
T-close-sized ActionPlan
      ↓
正式微信通知
```

Pre-open：

- 不重算 base Alpha；
- 不观察未来 open；
- 不因 AI 新闻叙事修改 target；
- 只做允许的执行 / 风险确认。

## 11.3 Market hours

用户人工执行。

系统不自动券商下单。

## 11.4 Post-execution

用户记录 / 导入 actual fills：

```text
actual time
actual price
actual quantity
fees
```

系统：

- append Fill；
- reconciliation；
- 更新 actual PortfolioSnapshot；
- 计算 Plan-vs-Actual attribution。

---

# 12. Manual Execution Protocol：通知以后用户到底怎么做

M3 前必须定义，而不能只写“人工执行”。

至少需要：

- ActionPlan 有效 trade date；
- 建议执行时段；
- 未成交如何处理；
- 部分成交如何处理；
- 用户主动放弃如何记录；
- 实际价格偏离计划时如何处理；
- 当天错过是否允许第二天执行旧指令；
- 手工外部交易如何标记。

第一版原则：

> **旧 ActionPlan 不自动跨交易日继续有效。**

如果用户未执行：

- 不假设成交；
- 保留实际 holdings；
- 次日系统基于真实 reconciled portfolio 与最新 locked target 重新生成 delta。

## 12.1 不默认给“目标价”

本产品的核心输出是：

```text
Target Weight / Planned Quantity / Action
```

不是主观 analyst price target。

只有某个 Approved Strategy 明确定义且验证了：

- stop；
- limit；
- price-based invalidation；

才允许其进入执行政策。

不由 AI 或 UI 临时生成“目标价”。

---

# 13. Reconciliation：用户没有完全照做怎么办

真实状态永远优先于计划。

以下事件触发 reconciliation：

- executed fill；
- unresolved fill；
- partial manual execution；
- 外部手工交易；
- deposit / withdrawal；
- broker statement mismatch；
- position mismatch。

如果没有上述事件，可以 carry forward 最近一次 reconciled state。

Notification 不是执行事实。
Plan 不是 holding。
只有 actual fill / reconciled account state 改变真实 PortfolioSnapshot。

---

# 14. Decision Outcome & Strategy Health

保留 v0.5 的一等产品能力：

```text
DecisionEpisode
ForwardEvaluation
CounterfactualEvaluation
StrategyHealthSnapshot
```

这首先用于 Quant Production，而不是 AI 研究。

## 14.1 评价对象

只对实质性 Target change 形成 DecisionEpisode，避免每天 HOLD 造成虚假样本膨胀。

## 14.2 预注册评价窗口

策略在决策时已经知道其：

```text
primary_evaluation_horizon
```

事后不得挑一个最好看的 5D / 20D / 60D 作为“正确答案”。

## 14.3 Strategy Health Policy

M2 必须定义：

```text
HEALTHY
WATCH
DEGRADED
SUSPENDED
RETIRED
```

以及：

- 最小样本；
- warning condition；
- suspension condition；
- data/operation failure 与 strategy failure 的区别；
- 恢复 / re-approval 规则。

不能因短期两三笔亏损自动优化参数。

---

# 15. Benchmark 与 CASH：M1 前的两个硬 Gate

## 15.1 BenchmarkPolicy

M1 前必须预注册：

- ETF Core benchmark；
- whole-portfolio benchmark；
- cash/risk-free comparator；
- benchmark version / data source。

不能策略跑完后挑一个容易打败的 benchmark。

## 15.2 CashPolicy

必须明确：

```text
CASH
```

是：

- 真正 idle cash，还是
- 带利息现金。

债券 ETF / 货币基金 / repo-like asset 是 **investable position**，不是 CASH。

不能事后把“现金”替换成表现好的防御资产。

---

# 16. Rebalance & Materiality Policy

“每天运行”不等于“每天交易”。

Bundle 必须定义：

- strategy signal cadence；
- portfolio rebalance cadence；
- target-change materiality threshold；
- minimum executable lot；
- turnover controls。

微小变化应变成：

```text
HOLD / NO ACTION
```

而不是为了精确追踪小数点目标权重产生无意义交易。

---

# 17. Owner Controls：用户必须拥有的人工控制权

M3 至少提供：

```text
PAUSE_NEW_RISK
RESUME
MARK_EXTERNAL_TRADE
RECONCILE
CANCEL/SUPERSEDE allowed plan（按锁定规则）
```

Owner override 必须：

- 显式；
- 有 timestamp；
- 有 reason；
- 有 audit trail；
- 不反写历史 target。

“人工不听系统的建议”不是系统错误，但必须能被正确记录和归因。

---

# 18. Production Reliability：系统自己挂了怎么办

“每天可靠给操作指示”要求不仅是代码正确，还包括运行可靠。

M3 前需要明确 Deployment Profile。

可选：

- local always-on machine；
- NAS / home server；
- low-cost VPS / cloud host。

但必须达到：

- scheduler reliability；
- persistence；
- backup / restore；
- missed-run detection；
- provider outage handling；
- proxy/network failure handling；
- secret recovery；
- clock/calendar correctness。

## 18.1 独立 Watchdog

如果主 Production process 整体死亡，它无法自己发送：

> PRODUCTION_RUN_FAILED

因此 M3 应有独立 heartbeat/watchdog，至少能发现：

- expected EOD run 没出现；
- expected pre-open plan 没出现；
- notification pipeline 长时间无回执。

Watchdog 应尽量独立于主 runtime failure domain。

---

# 19. Notification Product：正式交易权威必须单一

只有 Quant Production 进入正式交易通知：

```text
EOD Decision Summary
Pre-open Action Plan
```

正式 ActionPlan 应优先提供 deterministic 内容：

- trade date；
- current vs target；
- BUY / SELL / HOLD / CASH / NO ACTION；
- target weight；
- planned complete-lot quantity；
- estimated notional；
- reason code / strategy version；
- data/risk gate；
- decision ID。

AI Copilot 的解释放在独立 Research / Explanation 区域，不把“强烈看好”“建议积极买入”等生成式语言混入正式指令权威。

---

# 20. Reporting：至少要同时看到三种结果

产品不能只展示一个回测净值。

长期至少区分：

```text
Model / Target Portfolio Performance
Paper / Simulated Execution Performance
Actual Managed Book Performance
```

并拆解：

- strategy contribution；
- portfolio/risk transformation；
- lot/constraint drag；
- slippage；
- fees/taxes；
- missed manual execution；
- external trades；
- external cash flows。

否则用户无法知道：

> 策略错了，还是执行偏差造成的？

---

# 21. Change Management：系统不能“边跑边调”

以下全部需要版本化：

- InvestmentMandate；
- StrategyVersion；
- Universe；
- ProductionInvestmentBundle；
- PortfolioPolicy；
- RiskPolicy；
- BenchmarkPolicy；
- CashPolicy；
- ExecutionPolicy；
- Evaluator / StrategyHealthPolicy。

Research 可以自由实验。
Production 只接受 approved immutable artifact。

任何事后发现的新想法：

```text
New Hypothesis
  ↓
New Version
  ↓
Revalidation
```

而不是编辑旧版本。

---

# 22. AI Copilot 与 AI Investor 的最终边界

## 22.1 AI Copilot — 实用 Research 能力

保持 v0.2 定义：

AI 可以：

- 阅读论文 / 论坛帖子 / 研报 / GitHub 策略；
- 抽取投资命题；
- 生成 Strategy Spec；
- 写研究代码；
- 调用回测；
- 分析失败；
- 解释量化信号；
- 检查新闻、政策、产业风险；
- 寻找反例；
- 复盘错误决策；
- 提出新的研究假设。

AI Copilot 可以提高 Strategy Acquisition / Research 的效率。

但它不能绕过 Strategy / Bundle Promotion Gate。

## 22.2 AI Investor — Shadow Research

AI Investor 与 Quant 同为完整投资决策者，但 authority 不同：

```text
Quant       → PRODUCTION
AI Investor → AI_SHADOW
```

AI Investor：

- 独立 Shadow Account；
- 独立 TargetPortfolio；
- 独立长期记忆；
- 同一 information cutoff；
- 同一 verifier；
- 不进入正式交易通知；
- 不影响 Quant Production。

只有未来出现确切、长期、严格归因证据后，才另立 Architecture Decision 讨论是否进入 Production。

这不是当前 M1–M3 交付目标。

---

# 23. M1–M3 Product Completeness Review

本次从“真实用户第一次启用 → 每日使用 → 执行 → 复盘 → 异常恢复”的生命周期审查，结论如下。

| # | 产品问题 | v0.5 状态 | v0.6 处理 | Gate |
|---|---|---|---|---|
| 1 | 用户投资目标/风险倾向是什么 | Partial | `InvestmentMandate` | Before M1 Bundle approval |
| 2 | 系统管理哪部分资产 | Missing | `ManagedBook` | Before M3 |
| 3 | 策略从哪里来 | Missing | Strategy Acquisition + Registry | M1 |
| 4 | Product 默认是否需要用户写策略 | Missing | No，产品自带 Strategy Pack | M1 |
| 5 | Production 每天究竟运行什么 | Missing | `ProductionInvestmentBundle` | M1/M2 |
| 6 | ETF Universe 如何定 | Deferred | Universe Policy | M1 |
| 7 | ETF 历史不足如何回测 | Missing | Historical Proxy Policy | M1 |
| 8 | 多策略如何组合 | Partial | StrategyCompositionPolicy | M1 |
| 9 | 什么叫策略/Bundle 验证通过 | Partial | Explicit Promotion Gate | M2 |
|10 | 所有策略都失败怎么办 | Missing | 允许延迟 M3，不强上 | M2 |
|11 | 用户首次已有持仓怎么办 | Missing | PortfolioAdoptionPlan | M3 |
|12 | 100k 与真实资金关系 | Deferred | Model/Paper fixed, live actual equity | M3 |
|13 | 用户实际怎么执行通知 | Partial | Manual Execution Protocol | M3 |
|14 | 没成交/部分成交/错过怎么办 | Missing | No assumed fill, next-day replan | M3 |
|15 | 外部手工交易/存取款怎么办 | Partial | Reconciliation + external flow | M3 |
|16 | Strategy 什么时候暂停/恢复 | Partial | StrategyHealthPolicy | M2/M3 |
|17 | Benchmark / CASH 是什么 | Deferred | Hard Gate | Before M1 |
|18 | 每天运行但是否每天交易 | Missing | Rebalance/Materiality Policy | M1/M2 |
|19 | 用户怎样暂停系统风险 | Missing | Owner Controls | M3 |
|20 | 主进程死掉谁报警 | Partial | Independent Watchdog | M3 |
|21 | 正式通知与 AI 解释是否混权威 | Partial | Quant-only deterministic notification | M3 |
|22 | 实际收益与理论收益如何区分 | Partial | Three-layer reporting/attribution | M3 |
|23 | 参数/策略变更如何治理 | Partial | Immutable version + revalidation | M1 onward |
|24 | AI Investor 是否影响首版产品 | Risk in v0.4 | Shadow-only; not M1–M3 blocker | M6 |

结论：

> v0.5 的主要缺口不是 M0 技术内核，而是 **Investment Product Specification** 没有形成完整的一等模型。

v0.6 补齐后，M1–M3 的逻辑首次形成完整产品闭环。

---

# 24. Revised Milestones

## M0 — Foundation（正在实施，不改变）

目标：

> 正确、可复现的 Domain / Data / Backtest / Portfolio 基础。

严格按已批准 M0 Plan。

v0.6 不得向 M0 注入 Strategy、Mandate、UI、Notification、AI 等 scope。

---

## M1 — ETF Core Strategy Pack & Investment Policy

目标：

> **明确产品“怎么投资”，并形成第一套可验证的候选投资政策。**

必须完成：

- `InvestmentMandate_v1`；
- BenchmarkPolicy；
- CashPolicy；
- ETF Core Universe v1；
- Historical Proxy Policy；
- Strategy Acquisition / Registry；
- Absolute Trend candidate；
- Relative Momentum candidate；
- Defensive/Risk candidate；
- StrategyCompositionPolicy；
- Portfolio/Risk Policy values；
- Rebalance/Materiality Policy；
- `ETF_CORE_BUNDLE` candidate；
- preregistered parameter ranges；
- initial research/backtest evidence。

### M1 Exit

至少形成：

```text
ETF_CORE_BUNDLE_vX
status = RESEARCH_CANDIDATE / OOS_CANDIDATE
```

且所有关键投资规则已经被冻结到版本化 artifact。

M1 不要求为了赶进度批准失败策略。

---

## M2 — Evidence, Promotion & Paper Forward

目标：

> **证明候选 Bundle 不只是漂亮的历史回测。**

必须完成：

- OOS；
- walk-forward；
- robustness；
- cost/slippage stress；
- regime analysis；
- final holdout discipline；
- Bundle-level portfolio evidence；
- Paper protocol；
- DecisionEpisode；
- ForwardEvaluation；
- Counterfactual contracts；
- StrategyHealthPolicy；
- Paper Forward observation；
- Promotion Gate evidence package。

### M2 Exit

若证据通过：

```text
ETF_CORE_BUNDLE_vX
status = PRODUCTION_CANDIDATE
```

若未通过：

```text
NO APPROVED PRODUCTION BUNDLE
```

然后继续 Research；M3 不得强行上线。

---

## M3 — Usable Daily Investment Product

目标：

> **每天稳定、可靠、低噪声地给用户真正可执行的 Quant 操作指示。**

必须完成：

- approved `ProductionInvestmentBundle`；
- `ManagedBook`；
- onboarding / PortfolioAdoptionPlan；
- EOD Decision Run；
- Pre-open Execution Confirmation；
- locked TargetPortfolio；
- Manual Execution Protocol；
- Fill Reconciliation；
- external trade / cash-flow handling；
- NotificationPort + ServerChan；
- Owner Controls；
- minimal UI/CLI；
- model vs actual performance reporting；
- independent watchdog；
- backup / restore / failure runbook；
- Production Readiness Gate。

### M3 Exit

用户能够完成一个完整真实循环：

```text
初始化账户
  ↓
系统每日决策
  ↓
微信收到 ActionPlan
  ↓
人工执行
  ↓
录入/导入成交
  ↓
系统对账
  ↓
后续自动评估结果
```

达到这一点，产品第一阶段成功。

---

## M4 — Stock Satellite

在 ETF Core 稳定以后增加有限 A 股 Alpha。

需单独定义：

- survivorship-safe universe；
- liquidity/listing age/ST filters；
- Trend / Breakout / Momentum；
- Quality / Liquidity；
- dividend tax；
- Satellite cap；
- portfolio interaction。

---

## M5 — AI Copilot & Research Workbench

把目前人工借助外部 AI 完成的研究流程产品化：

- source ingestion；
- hypothesis extraction；
- Strategy Spec；
- code/research assistance；
- backtest orchestration；
- failure analysis；
- signal explanation；
- news/policy/industry challenger；
- counterexample search；
- postmortem；
- new hypothesis generation。

AI Copilot 不具有 Production Target authority。

---

## M6 — AI Investor Shadow Research

只有产品主线稳定后进入：

- AIAdvisorVersion；
- AIModelPort；
- GroundTruthMemory；
- CognitiveMemory；
- AI-no-memory baseline；
- AI-with-memory Shadow；
- same-cutoff verifier；
- Quant vs AI attribution；
- learning curve。

AI Investor 不进入正式通知。

---

# 25. M1 Before-Code Decision Gate

M0 可以继续实施，不等待以下问题。

但 **开始 M1 Strategy Implementation 前**，必须至少裁决：

1. `InvestmentMandate_v1` 的明确数值约束；
2. ETF Core Universe v1；
3. BenchmarkPolicy；
4. CashPolicy；
5. Historical Proxy Policy；
6. Strategy families 与经济命题；
7. parameter research ranges；
8. StrategyCompositionPolicy；
9. Portfolio/Risk Policy 的首版实际值；
10. Rebalance/Materiality Policy。

这应形成：

```text
M1 INVESTMENT POLICY GATE
```

没有通过该 Gate，不写生产意义上的 ETF Core 策略代码。

---

# 26. M2 Promotion Gate

进入 Paper / Production Candidate 前必须回答：

- holdout 如何保持未污染；
- 最低 evidence 是什么；
- Paper 至少需要多长时间 / 多少有效 decision episodes / 哪些 regime；
- 什么情况下判为失败；
- StrategyHealthPolicy 如何暂停和恢复；
- Bundle-level 证据是否通过；
- benchmark attribution 是否合理；
- multiple testing 记录是否完整。

不得用“回测 CAGR 很高”单独作为批准理由。

---

# 27. M3 Production Readiness Gate

真钱/真实人工执行前必须通过：

- active approved InvestmentMandate；
- active approved ProductionInvestmentBundle；
- reconciled ManagedBook；
- onboarding/adoption 完成；
- paper-forward evidence；
- Data / ETF qualification；
- scheduler / idempotency / crash tests；
- reconciliation tests；
- missed execution behavior；
- external trade/cash flow behavior；
- notification failure drill；
- watchdog test；
- backup/restore drill；
- provider outage/stale-data drill；
- secret/log redaction；
- owner runbook approval。

---

# 28. Product Success Criteria

第一阶段成功不要求 AI Investor 成功。

成功定义为：

- 用户不需要自己写策略；
- 系统有明确、经验证的 Production Investment Bundle；
- 每个交易日可靠运行；
- 没有动作时敢于 NO ACTION；
- 数据问题会 fail closed；
- Target/Action/Reason 可追踪；
- 用户能理解当前组合与目标组合；
- 用户能按通知人工执行；
- 没执行时系统不会假装成交；
- 外部交易/存取款可以正确对账；
- 实际组合收益与理论模型收益可拆分；
- 系统知道过去的决策后来表现如何；
- 策略退化能被检测而不是悄悄调参；
- AI 故障不影响 Quant Production。

---

# 29. Architecture Invariants

后续开发 Agent 不得违反：

1. **M0 已批准并正在实施；v0.6 不改变 M0 scope。**
2. **产品默认自带策略，用户无需写策略。**
3. **InvestmentMandate 是用户投资目标/风险约束的权威对象。**
4. **ManagedBook 明确系统管理的真实资产边界。**
5. **Production 运行 Approved ProductionInvestmentBundle，不运行任意策略文件。**
6. **TargetPortfolio 仍是一等投资决策对象。**
7. **Quant Production 是正式交易通知的唯一来源。**
8. **AI Copilot 只能影响 Research；AI Investor 只进入 AI_SHADOW。**
9. **任何影响投资行为的策略/参数/Universe/Policy 变化必须版本化并重新验证。**
10. **没有通过证据 Gate 时，允许不发布；绝不为了里程碑强上失败策略。**
11. **Plan 不等于 Fill，Notification 不等于 Execution。**
12. **真实 reconciled portfolio 是下一次 ActionPlan 的执行状态基准。**
13. **Forward market + deterministic verifier 是 outcome Ground Truth。**
14. **正式交易通知不得混入 AI 自由叙事形成第二套权威。**
15. **系统首要目标始终是一个真实、可靠、每天可用的个人投资产品。**

---

# 30. Final Product Definition

最终第一阶段产品可以用一句话描述：

> **用户先明确自己的 Investment Mandate；系统使用一套经过研究、OOS、Walk-forward、Paper 和整体验证后批准的 Production Investment Bundle，每天基于可信市场数据和真实当前持仓生成唯一的 TargetPortfolio 与 ActionPlan，通过微信给出明确操作指示；用户人工执行后系统对账，并长期验证过去的决策和策略是否真正有效。**

这条链路完整以后，才是一个投资产品：

```text
Investment Mandate
      ↓
Approved Strategy Pack
      ↓
Approved Production Investment Bundle
      ↓
Trusted Daily Data
      ↓
TargetPortfolio
      ↓
ActionPlan
      ↓
User Execution
      ↓
Reconciliation
      ↓
Outcome / Strategy Health
      ↓
Research Improvement
```

AI Copilot 可以加速最后一段 Research Improvement。

AI Investor 可以在旁边独立跑 Shadow Account，长期接受同一个 verifier 的检验。

但两者都不能改变当前产品的核心事实：

> **先把 Quant 投资产品做完整、做可靠、做得每天真的能用。**
