# Personal Systematic Investing OS
## v0.5 Product-First Final Architecture Decision

> **版本**：v0.5 — Production Quant First, AI Copilot + AI Shadow Research  
> **日期**：2026-09-15  
> **状态**：产品范围修正后的最高层总纲。M0 Design Gate 已通过，正在实施；本版**不重开 M0、不改变 M0 scope**。  
> **适用对象**：Codex / Claude Code / 其他开发 Agent，以及后续产品、研究、架构评审。  
> **下位权威**：M0 具体金融/数据/回测语义继续以已批准的 `docs/architecture/*`、`docs/plans/M0-implementation-plan.md`、`OPEN_QUESTIONS.md` 为准；本总纲不得被解释为覆盖已批准的 M0 细节。

---

# 0. Executive Decision

本项目首先是一个**实际可用的个人系统化投资决策产品**，不是一个以“证明 AI 会投资”为首要目的的科研项目。

产品 North Star：

> **每天可靠地告诉用户：今天应该买什么、卖什么、持有什么、目标仓位是多少；证据不足时明确 `HOLD / CASH / NO ACTION`。**

真钱 Production 的决策权威在可预见阶段固定为：

```text
Trusted Data
   ↓
Approved Quant Strategies
   ↓
Portfolio + Risk
   ↓
Locked TargetPortfolio
   ↓
Pre-open ActionPlan
   ↓
User Notification
   ↓
Manual Execution
   ↓
Fill Reconciliation
```

**所有面向用户的正式交易操作通知，只能来自已批准的 Quant Production 决策链。**

AI 在产品中有两个完全不同的角色，必须严格分开：

1. **AI Copilot — 实用产品能力**  
   服务于研究、验证、解释、风险挑战和复盘；它帮助把 Quant 系统做得更好，但不直接生成真钱指令。

2. **AI Investor — 长期独立研究课题**  
   它可以像真正的投资者一样独立形成完整投资判断和 Shadow TargetPortfolio，但只运行在独立影子账户中。它不能影响 Production Target、ActionPlan 或交易通知，除非未来已经出现足够强、足够长、严格归因后的确切证据，并经过新的 Owner Architecture Decision。

因此，本项目采用：

> **Product-first, Research-second.**

AI Investor 很重要，但它不能改变项目的首要成功标准：**先做出一个可靠、有用、每天能指导实际投资的个人投资系统。**

---

# 1. 产品范围优先级

所有开发任务按以下优先级判断是否值得做。

## P0 — 必须先做成的实际产品

P0 是项目存在的理由：

- 可靠的 A 股 / ETF 数据；
- Data Quality Gate；
- 正确的交易日、PIT、复权、公司行动、可交易性语义；
- 可信的日线 Backtest Kernel；
- 少而可靠的 Quant Strategies；
- `ETF Core + Stock Satellite` Portfolio；
- 风险控制；
- `TargetPortfolio`；
- EOD Decision Run；
- Pre-open ActionPlan；
- 个人微信通知；
- 人工执行；
- Actual Fill Reconciliation；
- Forward Evidence / Strategy Health；
- 可解释、可审计、可复现。

如果一个功能不能明显帮助以上目标，就不能挤占 P0 的开发资源。

## P1 — 提升 P0 质量的研究与智能工具

包括：

- Research Knowledge Ledger；
- Hypothesis Registry；
- Strategy Spec；
- OOS / Walk-forward / Holdout；
- DecisionEpisode / ForwardEvaluation / Counterfactual；
- Strategy Health / Kill Switch；
- AI Copilot；
- 自动研究辅助；
- 失败策略沉淀；
- 信号解释与风险反例。

这些功能的目的不是“展示 AI”，而是**提高 Quant Production 的可靠性和迭代效率**。

## P2 — 长期研究：AI Investor

包括：

- AI Shadow Portfolio；
- AIAdvisorVersion；
- GroundTruthMemory；
- CognitiveMemory；
- AI-no-memory vs AI-with-memory；
- AI Learning Curve；
- 与 Quant-only 的长期比较；
- model / prompt / memory / tool policy 实验。

P2 **不得阻塞 P0/P1 发布，不得成为真钱链路依赖，不得让产品架构为研究实验付出不必要复杂度。**

---

# 2. 产品核心定义

产品定义：

> **Personal Systematic Investment Decision System / 个人系统化投资决策系统**

长期可以拥有越来越强的投资智能，但产品价值首先体现在：

```text
可信数据
+ 经验证的策略
+ 组合与风险
+ 明确目标仓位
+ 稳定每日运行
+ 可执行通知
+ 真实结果反馈
```

而不是：

```text
Agent 数量
Prompt 复杂度
多角色辩论
漂亮的 AI 分析文章
```

系统的一等决策对象仍然是：

> **TargetPortfolio**

而不是 `BUY / SELL` 文本。

执行表达由：

```text
Current Portfolio
vs
TargetPortfolio
```

推导为：

```text
BUY / SELL / HOLD / CASH / NO ACTION
```

---

# 3. Production Authority：Quant 是真钱决策源

这是 v0.5 的重要产品边界。

## 3.1 Quant Production

Quant Production 是正式投资指令的唯一来源。

必须满足：

- Strategy 已批准；
- 版本固定；
- 数据通过 Gate；
- 可回测；
- OOS / Walk-forward / Paper 有证据；
- Portfolio / Risk 可复现；
- 所有决策有版本和 evidence；
- EOD 锁定；
- Pre-open 不重算 base Alpha；
- 通知仅投影 locked target 与 reconciled position 的差值。

## 3.2 AI Investor Shadow

AI Investor 也被视为**一级投资决策者**，但这里的“一级”指：

> 它可以独立完成一整套投资决策，而不是只能评论 Quant。

它可以独立输出：

- BUY / SELL / HOLD / CASH；
- target weights；
- expected horizon；
- thesis；
- invalidation conditions；
- confidence；
- portfolio-level target。

但它的 authority namespace 固定为：

```text
AI_SHADOW
```

而不是：

```text
PRODUCTION
```

因此：

```text
Quant Production Target
        ↓
正式用户通知

AI Shadow Target
        ↓
Shadow Ledger / Research UI / Evidence
```

两条路径独立并行，互不污染。

## 3.3 正式通知规则

交易通知只能来自 Quant Production：

```text
EOD Quant Decision Summary
Pre-open Quant Action Plan
```

AI Shadow 的 BUY/SELL 不得出现在正式操作通知中，也不得使用容易让用户误认为正式指令的通知格式。

AI Shadow 结果可以存在于：

- Research 页面；
- Shadow Portfolio 页面；
- 周/月研究报告；
- 事后对比分析。

但它不是当天操作依据。

---

# 4. AI Copilot：恢复并保留 v0.2 的实用定位

AI Copilot 是实际产品的一部分，而且它非常有价值。

AI 可以：

- 阅读论文 / 论坛帖子 / 研报 / GitHub 策略；
- 抽取投资命题；
- 生成 `Strategy Spec`；
- 写研究代码；
- 调用回测；
- 分析失败；
- 解释量化信号；
- 检查新闻、政策、产业风险；
- 寻找反例；
- 复盘错误决策；
- 提出新的研究假设。

还可以：

- 把自然语言投资经验转成可证伪 Hypothesis；
- 检查 Strategy 是否有 look-ahead / survivorship / data snooping 风险；
- 生成 sensitivity / stress / ablation 实验计划；
- 阅读 ForwardEvaluation，聚类失败模式；
- 为策略健康恶化提出解释候选；
- 为用户解释“为什么今天没有交易”；
- 为 Quant 决策提供 news/policy/industry challenger。

但 AI Copilot **不能**：

- 修改 locked TargetPortfolio；
- 用叙事直接制造 BUY；
- 绕过 Strategy Promotion Gate；
- 自己改 Production 参数；
- 因一条新闻临时覆写 Quant Alpha；
- 把自己的解释当成 Ground Truth。

AI Copilot 的价值判断标准是：

> **它是否帮助我们更快发现好策略、更早淘汰坏策略、更好理解风险、更少犯工程和研究错误。**

---

# 5. AI Investor：长期研究轨，而不是近期产品主线

长期研究命题保留：

> **强基础模型 + 私有长期投资记忆 + 真实市场反馈 + 外部 verifier，是否能够逐渐形成长期优于用户本人、甚至优于纯规则 Quant 的投资决策者？**

这个问题值得研究，但它不能反客为主。

## 5.1 AI Investor 的默认状态

```text
SHADOW_ONLY
```

它必须：

- 使用与 Quant 同一信息 cutoff；
- 不使用未来信息；
- 有自己的不可变 Decision Record；
- 有自己的模拟账户和交易成本；
- 接受相同 verifier；
- 有固定 `AIAdvisorVersion`；
- 区分 model / prompt / memory / tool 版本；
- 能重放或至少明确标记 `MODEL_UNPINNED`。

## 5.2 不设“自动升级真钱权限”的产品路线

v0.5 不再把：

```text
SHADOW → ADVISORY → CAPPED_SLEEVE → HYBRID_CO_DECISION
```

当作默认产品 roadmap。

是否让 AI Investor 进入 Production，是**未来可能发生的新产品裁决**，不是当前计划内的自然下一步。

只有当已经存在确切证据，例如：

- 足够长的 forward history；
- 多 regime 覆盖；
- 统计上稳定；
- 风险调整后优于 Quant baseline；
- selection alpha / Decision Value Add 不是单纯 Beta；
- memory 增量被隔离验证；
- model upgrade / leakage / data advantage 被审计；
- 没有通过事后调评分规则制造优势；

才值得重新开启：

> **“AI 是否进入 Production？”**

到那时另做 ADR 和新的 Design Gate。

在此之前：

> **AI Investor 永远是 Shadow Research。**

---

# 6. 总体架构：Production 主线与 Research 支线分离

```text
                        Trusted Data Plane
                               │
                 ┌─────────────┴─────────────┐
                 │                           │
                 ▼                           ▼
        Quant Production Plane        AI Research Plane
                 │                           │
        Approved Strategies              AI Copilot
                 │                      AI Investor Shadow
        Portfolio + Risk                    │
                 │                     Shadow Portfolio
                 ▼                           │
        Locked TargetPortfolio              │
                 │                           │
        Pre-open ActionPlan                  │
                 │                           │
        User Notification                    │
                 │                           │
        Manual Execution                     │
                 │                           │
        Actual Fill / Portfolio              │
                 └──────────────┬────────────┘
                                ▼
                      Outcome / Evidence Plane
                                │
                  Forward / Counterfactual / Health
                                │
                  Research Knowledge & Memory
```

关键点：

- `Quant Production Plane` 是真钱产品主链；
- `AI Research Plane` 永远不能成为 Production 的运行依赖；
- AI 失败、模型 API 不可用、Memory Backend 故障时，Quant Production 仍应正常工作；
- AI Shadow scheduler 不能延迟 Quant EOD / Pre-open；
- AI Shadow persistence 不能写 Production target namespace。

---

# 7. Quant 产品路线：ETF Core + Stock Satellite

## 7.1 ETF Core

负责：

- 基础资产配置；
- 趋势；
- 相对动量；
- 防御 / 现金；
- 回撤与风险预算；
- 低换手。

第一代应保持简单、可解释、可验证。

## 7.2 Stock Satellite

负责有限 Alpha：

- 高流动性 A 股；
- Trend / Breakout / Momentum；
- Quality / Liquidity filters；
- regime-conditioned allocation；
- Satellite risk cap。

Stock Satellite 永远受 Portfolio Risk 控制，不独立扩大总风险。

## 7.3 收益与风险目标

目标：

```text
长期年化：10%~15%
希望 MDD：<=10%
```

它们是 portfolio objective / release evidence，不是参数搜索停止条件。

---

# 8. 数据、回测、组合和风险：产品可信度的根基

沿用已批准架构：

- 首个 Provider：`joycoding2000/chstockdata`；
- Quant Domain provider-neutral；
- Production 直接使用 Python package API，不通过 MCP；
- Instrument Master 与 provider authority 分离；
- `information_available_at != retrieved_at`；
- RAW price 是 execution/accounting truth；
- `T_CLOSE sizing != NEXT_SESSION_OPEN fill`；
- Pre-open 不观察未来 open；
- `CORE / SATELLITE` 是强类型 sleeve；
- 100,000 RMB 是默认 backtest/paper initial capital；
- whole-lot / min commission / fees / residual cash / settlement / suspension / price limit 必须真实建模；
- Golden Cases 是 correctness oracle；
- Data Quality Gate 可以 fail closed。

不因为 AI 研究线存在而降低这些要求。

---

# 9. Decision Outcome & Controlled Learning Loop

这个能力属于**产品本身**，不仅服务 AI。

系统应知道自己过去的 Quant 指令后来表现怎样。

核心对象：

```text
DecisionEpisode
ForwardEvaluation
CounterfactualEvaluation
StrategyHealthSnapshot
```

## 9.1 DecisionEpisode

评价实质性 target change，而不是每天重复 HOLD。

必须冻结：

- decision time；
- strategy/version；
- before/after target；
- market regime；
- evidence；
- `primary_evaluation_horizon`；
- benchmark policy；
- counterfactual policy。

## 9.2 Forward Evaluation

至少记录：

- 5D / 20D / 60D；
- primary horizon；
- raw return；
- benchmark/excess；
- MAE / MFE；
- drawdown / risk result；
- execution drag。

## 9.3 不把“涨了”简单等于“判断正确”

至少拆分：

```text
Direction
Alpha / Counterfactual Value Add
Risk
Execution
```

必要时输出：

```text
GOOD / MIXED / BAD / INCONCLUSIVE
```

由 deterministic, versioned evaluator 判定，不由 LLM 自由解释决定。

## 9.4 产品价值

这套机制首先用于：

- Strategy Health；
- Kill Switch；
- 策略复盘；
- 研究优先级；
- 用户理解系统为什么有效/失效；
- 区分策略问题与执行问题。

AI Investor 只是它的另一个受测对象。

---

# 10. Research Knowledge Plane

外部知识进入系统的路径：

```text
Paper / Book / JoinQuant / GitHub / Report / Forum
                    ↓
             Source & Provenance
                    ↓
               Claim Extraction
                    ↓
              Hypothesis Registry
                    ↓
                Strategy Spec
                    ↓
       Backtest / Robustness / OOS
                    ↓
               Paper Forward
                    ↓
            Approved Strategy Registry
```

原则：

- 大 V / 论文 / GitHub star 不是 Ground Truth；
- popularity 只能影响研究优先级；
- AI 不得补齐作者没有给出的关键参数并假装是原策略；
- `knowledge_available_at` 必须保留；
- 失败 Hypothesis 也要保存；
- 避免 retrospectively cherry-pick 文章和策略。

---

# 11. AI Memory：只为 AI Research 服务，不侵入 Production Core

AI Investor 的长期记忆分两层。

## GroundTruthMemory

事实层：

- AI DecisionEpisode；
- Shadow Fill；
- Market Context；
- ForwardEvaluation；
- Counterfactual；
- Advisor Version；
- Shadow Portfolio Performance。

不可由 LLM 改写。

## CognitiveMemory

认知层：

- Postmortem；
- Lesson；
- Belief；
- FailurePattern；
- Similar Episode summary；
- Research Hypothesis。

允许修订，但有 provenance。

Memory backend 通过 `InvestmentMemoryPort` 替换，可研究 Graphiti、Mem0、Letta 等实现；本项目自己掌握事实 schema。

**如果 Memory 系统完全删除，Quant Production 仍必须完整可运行。**

---

# 12. AI Model Access

模型接入使用 `AIModelPort`，不把供应商商业模式写入 Domain。

允许：

```text
METERED_API
SUBSCRIPTION_PROGRAMMATIC
SUBSCRIPTION_INTERACTIVE (research/manual only)
LOCAL
```

规则：

- 自动 Shadow Runtime 只使用官方支持、可审计的程序化接口；
- 如果官方订阅允许程序化调用，可优先利用订阅；
- 不抓网页 Cookie；
- 不模拟 ChatGPT UI；
- 不伪装 Coding Tool；
- 不能为了节省 API 费用让系统依赖脆弱、违规接入。

---

# 13. Notification Product

首版：

```text
NotificationPort
    ↓
ServerChanAdapter
    ↓
个人微信
```

正式通知只有 Quant：

1. `Pre-open Action Plan`
2. `EOD Decision Summary`

异常：

- DATA_ERROR
- DATA_STALE
- RISK_KILL_SWITCH
- STRATEGY_SUSPENDED
- PRODUCTION_RUN_FAILED
- NOTIFICATION_RETRY_EXHAUSTED

要求：

- idempotency；
- dedupe；
- retry；
- audit；
- notification 不是 Ground Truth；
- `SERVERCHAN_SENDKEY` 仅 secret/env。

AI Shadow 不进入上述正式交易通知链。

---

# 14. Product UI

近期 MVP 只需要真正帮助用户行动和理解系统的页面：

1. **今日行动** — Quant ActionPlan；
2. **我的组合** — current vs target；
3. **机会 / 目标** — Quant signals + evidence；
4. **交易复盘** — fills, episodes, outcome；
5. **策略实验室** — approved / paper / research strategy status。

AI Shadow 页面是研究功能，后加：

6. **AI Investor Research** — Shadow portfolio、decision、memory evidence、Quant comparison。

AI Research 页面不能比“今日行动”更早成为 MVP release blocker。

---

# 15. Milestones — 产品优先重排

## M0 — Foundation（正在实施，禁止 scope creep）

目标：

> Domain + Data + Backtest correctness

沿用已批准 `M0-implementation-plan.md`。

本版任何 AI / Memory / UI 调整都不得进入 M0。

## M1 — ETF Core Quant

目标：

> 做出第一个可信的 Quant Core。

包含：

- Buy & Hold baseline；
- Trend；
- Relative Momentum；
- Defensive/Cash；
- Portfolio allocation；
- benchmark policy；
- preregistered parameter ranges；
- OOS / walk-forward 初步证据。

## M2 — Evidence & Paper Validation

目标：

> 证明 Quant Core 不只是漂亮回测。

包含：

- OOS；
- Walk-forward；
- sensitivity；
- cost stress；
- Strategy Registry；
- DecisionEpisode；
- ForwardEvaluation；
- Counterfactual contracts；
- Strategy Health；
- Paper Forward protocol。

## M3 — Usable Daily Investment Product

这是第一阶段真正的产品里程碑。

目标：

> **每天稳定给用户可执行的 Quant 操作指示。**

包含：

- EOD Decision Run；
- Pre-open Execution Confirmation；
- locked TargetPortfolio；
- Quant ActionPlan；
- NotificationPort；
- ServerChan；
- Manual Fill Reconciliation；
- run/audit/observability；
- 最小 UI/CLI；
- failure runbook。

达到 M3 后，即使 AI Investor 永远没有研究成功，项目也已经是一个有用的个人投资产品。

## M4 — Stock Satellite + Portfolio Improvement

包含：

- survivorship-safe A-share universe；
- high-liquidity filter；
- Trend / Breakout / Momentum；
- Quality / Liquidity；
- dividend tax；
- Satellite cap；
- Quant Portfolio attribution。

目标：

> 在 ETF Core 之上增加有限、可控、可验证的股票 Alpha。

## M5 — AI Copilot & Research Workbench

这是 AI 的首个正式产品化阶段，但仍不让 AI 下真钱决策。

实现：

- Source / Claim / Hypothesis；
- AI literature/forum/report ingestion；
- Strategy Spec generation；
- research code generation；
- backtest orchestration；
- failure analysis；
- signal explanation；
- news/policy/industry risk challenger；
- counterexample search；
- postmortem；
- new research hypothesis generation。

目标：

> **提高策略研发效率和风险认知，而不是展示 Agent。**

## M6 — AI Investor Shadow Research

只有在产品主线已经稳定后进入。

实现：

- AIAdvisorVersion；
- AIModelPort；
- GroundTruthMemory；
- CognitiveMemory；
- InvestmentMemoryPort；
- AI-no-memory baseline；
- AI-with-memory Shadow Portfolio；
- shared verifier；
- Quant vs AI attribution；
- learning curve。

目标：

> 长期回答“AI Investor 到底有没有稳定增量价值”。

## Future — AI Production Authority（**不是当前 roadmap 承诺**）

只有当 M6 已经产生足够确切的长期证据时，才重新立项：

> AI 是否进入 Production？

必须单独 Architecture Review + Owner Decision。

在此之前不存在默认的 M7 “自动资本授权”。

---

# 16. Release Success Criteria

项目第一阶段成功，不要求 AI Investor 成功。

## Product Success

- 每交易日可靠运行；
- 数据错误会 fail closed；
- 交易指令明确；
- Target / Action / Reason 可解释；
- 微信通知稳定；
- 用户能按通知人工执行；
- 成交后可以对账；
- 历史决策可追溯；
- 真正知道过去策略在 forward 中表现怎样。

## Quant Research Success

- Golden correctness；
- no look-ahead；
- OOS / walk-forward；
- holdout discipline；
- transaction costs；
- strategy decay detection；
- portfolio risk control。

## AI Copilot Success

- 缩短研究周期；
- 提升 Hypothesis/Strategy Spec 质量；
- 更早发现坏策略和风险；
- 解释 Quant signal；
- 对新闻/政策/行业风险提出有价值反例；
- 复盘帮助产生可检验的新假设。

## AI Investor Research Success

只属于长期研究：

- AI decisions 可冻结；
- Shadow portfolio 可复现/审计；
- memory/no-memory 可公平比较；
- 结果不被 Beta / style / leakage 伪装；
- 有足够长 forward history；
- learning curve 可统计。

它不是产品上线前置条件。

---

# 17. 非目标 / 防止范围失控

近期明确不做：

- 自动券商下单；
- 高频 / Level-2 / tick alpha；
- 多 Agent 角色秀；
- 为 AI Shadow 建复杂分布式基础设施；
- 因 AI research 需要引入 Kafka / Redis / K8s；
- 自动 fine-tune 私人模型；
- AI 自我修改 Production；
- AI 自己决定资本权限升级；
- 为证明 AI 有效而延迟 Quant 产品上线；
- 大而全金融 RAG；
- 一开始导入几万篇资料；
- 自动推荐“今天最值得买的股票”作为未经验证的真钱功能。

---

# 18. 架构不变量

后续 Agent 不得违反：

1. **M0 已批准，不因 v0.5 重开。**
2. **TargetPortfolio 是一等决策对象。**
3. **Quant Production 是正式用户交易通知的唯一来源。**
4. **AI Investor Shadow 永远不能写 Production Target。**
5. **AI Copilot 可以影响 Research，不可以绕过 Promotion Gate。**
6. **AI 研究基础设施故障不能影响 Quant Production。**
7. **Data / Instrument Master / PIT / Execution / Accounting 语义保持已批准定义。**
8. **真实未来市场 + deterministic verifier 是 outcome Ground Truth。**
9. **任何策略版本变化必须重新验证。**
10. **不要把产品做成科研展示。先让用户每天真正能用。**

---

# 19. 对 v0.4 的纠偏说明

v0.4 的重要贡献应保留：

- AI Investor 可以独立形成完整投资判断；
- Private Investment Memory；
- AI Shadow Portfolio；
- Forward verifier；
- AI-no-memory / AI-with-memory 对比；
- AI learning curve；
- AIModelPort / AIAdvisorVersion。

但 v0.4 存在一个产品范围风险：

> **把“长期 AI Investor 研究问题”放得过于接近产品主线，容易让 Personal Investing OS 从“每天真正帮助投资”的系统漂移成“研究 AI 是否会投资”的实验平台。**

v0.5 的修正是：

```text
真钱产品主线 = Quant Production

AI 实用价值 = Copilot

AI 独立投资 = Shadow Research
```

三者都保留，但权威、优先级和 milestone 完全分开。

---

# 20. 最终原则

本项目最终首先应该是：

> **一个可靠、可执行、可验证、每天真正帮助用户做投资决策的个人系统化投资系统。**

Quant 是当前真钱 Production 的决策核心，因为它可以被严格回测、验证、版本化和审计。

AI 在近期产品中最有价值的角色，是一个强大的 Copilot：

> 阅读、抽取、研究、写代码、回测、解释、挑战、找反例、复盘、提出新假设。

同时，我们保留一个长期、独立、严谨的 AI Investor Shadow 实验：

> **让强基础模型拥有完整投资决策权，在模拟账户中积累自己的长期记忆和真实市场反馈，最终用事实回答它是否真的比 Quant 更强。**

但在证据出现以前：

> **研究归研究，生产归生产。**

不要因为 AI 很有潜力，把一个应该先解决真实投资需求的产品变成科研课题。
