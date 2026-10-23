# Personal Systematic Investing OS
## v0.9 Flight-Test-Driven Product Architecture

> **版本**：v0.9  
> **日期**：2026-09-15  
> **状态**：建议取代 v0.8 作为新的最高层产品/执行总纲，供人工审查。  
> **M0 状态**：M0 Design Gate 已通过且正在实施；**本版不重开、不修改 M0 scope，不覆盖 M0 已批准的详细语义文档。**
>
> **核心思想**：保留 v0.8 中已经确定的长期方向和金融正确性边界，但改变开发方法：  
> **不要先把未来投资平台设计完整；尽快把第一条可信策略送进 OOS / Paper，再用真实证据决定下一轮建设。**

---

# 0. 第一性原理

项目的最终目标不是：

- 建设一个漂亮的量化研究平台；
- 建设完整的 AI 投资实验室；
- 建设机构级资产管理系统；
- 完成一套“看起来专业”的架构。

真正目标只有一个：

> **每天基于可信数据和已经验证的策略，为个人投资者产生一个值得实际执行的 TargetPortfolio / ActionPlan。**

因此所有建设都接受一个问题：

> **这个工作是否明显缩短“策略思想 → 可信验证 → Paper → 每日真实决策”的距离？**

如果不能，默认后置。

---

# 1. 不变的产品定义

第一阶段目标产品仍然是：

```text
ETF CORE
+
STOCK SATELLITE
+
CASH
        ↓
TargetPortfolio
        ↓
ActionPlan
        ↓
ServerChan / 微信
        ↓
用户人工执行
```

这项裁决不再改变：

> **ETF Core 与 Stock Satellite 都属于第一阶段目标产品。**

但：

> 如果 Stock 策略没有通过验证，Production 中 SATELLITE 可以暂时为 0。

不能为了产品形态完整而强行上线失败策略。

---

# 2. 不变的金融“物理规律”

快速迭代不等于牺牲因果和交易真实性。

以下边界继续继承 M0 / v0.8，不能为了“快速”删除：

1. point-in-time / no-lookahead；
2. `information_available_at` 与 `retrieved_at` 分离；
3. T-close sizing 与 T+1 execution 分离；
4. 真实交易费用、税、滑点；
5. 停牌、涨跌停、lot、现金约束；
6. corporate action 正确性；
7. CORE / SATELLITE 强类型；
8. TargetPortfolio 是正式决策对象；
9. Plan ≠ Fill；
10. Research 与 Production 权限分离；
11. Production 不能直接运行未经批准的 AI / experimental code；
12. 失败实验必须保留；
13. LLM 输出不是 Ground Truth。

这些相当于火箭设计中的：

> **不能违反的物理定律。**

---

# 3. v0.8 中保留，但降级为“按需启用”的能力

下面这些设计本身有价值，不删除；但不再默认为 M1/M2 的完整建设任务。

## 3.1 Research Knowledge Plane

保留思想：

```text
Source
→ Claim
→ Hypothesis
→ Experiment
→ Evidence
```

但 M1 第一版不建设完整知识平台。

最小实现可以只是：

```yaml
hypothesis_id: H-001
source: ...
idea: ...
asset: ETF | STOCK
expected_horizon: ...
status: RESEARCH | REJECTED | SURVIVOR
result: ...
```

存 Markdown / SQLite / 简单 JSON 均可。

什么时候升级为完整 Knowledge Ledger？

> 当真实策略研究数量和来源已经使简单记录明显成为瓶颈时。

## 3.2 Hypothesis Registry

保留。

但第一版只需要：

```text
IDEA
TESTING
REJECTED
SURVIVOR
PAPER
APPROVED
```

不做复杂 workflow / approval engine。

## 3.3 Market Regime

保留：

```text
BULL
SIDEWAYS
BEAR
```

作为重要研究维度。

但 **第一阶段默认是 analysis-only**：

```text
Strategy
  ↓
分别统计 Bull / Sideways / Bear 表现
```

暂时不要先建设：

```text
Regime Classifier
  ↓
自动切 Strategy
```

只有证据表明 deterministic regime routing 明显优于不 routing，才把 Regime 升级为 Production 控制逻辑。

## 3.4 Strategy × Regime Matrix

保留为研究报告。

不需要先建设独立服务 / 数据库 / UI。

## 3.5 Signal Evidence Card

保留目标。

第一阶段可以直接输出：

```text
JSON / Markdown / CLI Report
```

等每日系统已经真正使用，再决定是否制作精美 UI Card。

## 3.6 Decision Outcome / Counterfactual

Decision Outcome 保留为重要能力。

第一版优先记录：

- decision；
- future return；
- benchmark；
- actual fill；
- basic plan-vs-actual。

以下可以等有足够真实 Forward 数据以后逐步增加：

- 完整 MAE/MFE；
- avoided loss；
- missed upside；
- elaborate counterfactual attribution；
- complex Strategy Health state machine。

## 3.7 5 个完整页面

保留长期产品愿景：

- 今日行动；
- 机会池；
- 我的组合；
- 策略实验室；
- 交易复盘。

但 M3 v1 不要求一次做齐。

第一版 UI 只需优先覆盖：

```text
今日行动
我的组合
简单历史 / 运行状态
```

策略实验室可以继续使用 CLI / Markdown / Notebook。

---

# 4. Strategy Acquisition：第一阶段真正的价值创造

M0 完成以后，项目主要工程资源不再继续扩基础设施，而是投入：

```text
策略发现
→ 策略实现
→ 策略验证
→ 策略淘汰
→ Paper
```

策略来源继续包括：

1. 经典论文 / 学术策略；
2. 投资书籍；
3. JoinQuant / 论坛 / 博主；
4. GitHub；
5. 研报；
6. AI Copilot 提出的 hypothesis；
7. 用户自己的想法（保留，不作为 M1 主任务）。

目标不是“收集多少策略”。

目标是：

> **尽快找到少量经得住验证的策略。**

---

# 5. AI Copilot：早做，但不要先造“大 AI 平台”

AI Copilot 仍从 M1 开始。

第一版最合理的形态是：

```text
ChatGPT / Codex / GLM / other agent
        ↓
读取论文 / GitHub / 论坛 / 研报
        ↓
输出 strategy_spec.md
        ↓
生成 / 修改 Python Strategy
        ↓
调用本项目 CLI / pytest / backtest
        ↓
读取结果
        ↓
分析失败
        ↓
下一轮实验
```

也就是说：

> **先让现成强 Agent 使用我们的研究工具。**

而不是 M1 先开发：

- Agent runtime；
- Tool planner；
- Memory platform；
- Job queue；
- Prompt management platform；
- complicated AI orchestration。

只需要保留一个薄的 `AIModelPort` 边界，以免未来绑定供应商。

---

# 6. ETF 与 Stock：同步研究，但都走窄路径

## ETF 第一阶段候选

优先研究：

- Absolute Trend；
- Time-Series Momentum；
- Relative Momentum；
- Rotation；
- Tactical / Defensive Allocation；
- Gold / Bond / Cash switching。

## Stock 第一阶段候选

只从低数据复杂度、高可验证性的策略开始：

- Trend；
- Breakout；
- Momentum；
- Relative Strength；
- Liquidity filter。

第一阶段不为了 Stock Satellite 提前建设：

- 完整财务因子库；
- 全量 PIT fundamentals；
- 数十因子平台；
- ML prediction；
- 深度学习；
- 复杂形态库。

如果以后某个策略明确需要 PIT 财务数据，再做对应能力。

---

# 7. Validation Funnel：不要让每个 Idea 都跑最昂贵的验证

完整验证链仍然保留：

```text
Backtest
→ OOS
→ Walk-forward
→ Robustness
→ Final Holdout
→ Paper Forward
```

但它是一条 **漏斗**，不是每个 Idea 的固定全套流程。

示例：

```text
大量 Idea
    ↓
Cheap Screening
    ↓
少量值得实现的 Strategy
    ↓
Basic Backtest
    ↓
Survivors
    ↓
OOS + Cost
    ↓
Strong Survivors
    ↓
Walk-forward + Robustness
    ↓
Finalists
    ↓
Final Holdout
    ↓
Paper Forward
```

数字不预设。

原则：

> **越昂贵的验证，只给越有希望的候选。**

---

# 8. Stage 0 — Cheap Screening

AI Copilot 或研究者先回答：

- 经济逻辑是什么？
- 适用资产是什么？
- horizon 是什么？
- 数据是否可获得？
- 是否明显存在未来信息？
- 交易频率是否适合个人散户？
- 成本是否可能吞噬收益？
- 是否只是把多个高度相关指标叠加？
- 是否值得写代码？

明显不合理：

```text
REJECTED_BEFORE_IMPLEMENTATION
```

这样可以避免“AI 很会写代码，所以什么垃圾 idea 都实现一遍”。

---

# 9. Stage 1 — Basic Backtest

对值得实现的 Strategy：

- exact StrategyVersion；
- 固定 Universe；
- realistic costs；
- M0 execution semantics；
- CAGR；
- MDD；
- turnover；
- trade count；
- benchmark；
- yearly / regime breakdown。

明显没有价值：

```text
REJECTED
```

不要继续做 expensive validation。

---

# 10. Stage 2 — OOS

只有 Basic Backtest 有希望的策略进入。

冻结：

- StrategyVersion；
- parameters；
- Universe；
- benchmark；
- cost model。

运行真正未参与开发的 OOS。

OOS 崩掉：

```text
REJECTED
```

---

# 11. Stage 3 — Robustness / Walk-forward

只针对 OOS survivor。

检查：

- parameter neighborhood；
- cost / slippage stress；
- subperiod stability；
- Bull / Sideways / Bear breakdown；
- rolling / walk-forward；
- 是否依赖极少数交易。

---

# 12. Stage 4 — Final Holdout

只给 finalist。

一旦看过，并因为 Holdout 修改 Strategy：

> 旧 Holdout 已被污染。

新版本重新进入验证。

---

# 13. Stage 5 — Paper Forward

只有最终候选进入。

Paper：

```text
T 日产生决策
→ freeze
→ 市场未来发生
→ 再计算结果
```

这是第一阶段最接近真实世界的 verifier。

Paper 不需要漂亮 UI。

---

# 14. Multiple Testing：只先记录，不先造统计研究平台

AI 会加快策略搜索，因此第一阶段至少保存：

```text
hypothesis count
strategy versions
parameter attempts
experiments
rejected results
```

暂时不要求实现复杂：

- Deflated Sharpe Ratio；
- PBO；
- FDR engine。

需要时再增加。

---

# 15. ActiveStrategyPack：只在有 survivor 后再设计具体组合

M1 不提前把组合规则设计得非常复杂。

当真正有 survivor 后，才回答：

- 哪几个策略同时存在？
- 是否相关？
- ETF / Stock 如何竞争资金？
- Satellite cap 应是多少？
- 是否真的需要 Regime routing？
- 如何 rebalance？

形成：

```text
ActiveStrategyPack v0.x
```

没有有效 survivor 时：

> 不强行生成 ActiveStrategyPack。

---

# 16. M0 — Foundation：继续完成，不重开

正在实施：

- Domain；
- Data；
- ETF data qualification；
- Backtest semantics；
- Portfolio / Risk kernel；
- reproducibility；
- golden / parity；
- tests。

M0 完成后：

> **不要再继续做 Foundation Expansion。**

立即进入策略试飞。

---

# 17. M1 — First Strategy Flight

M1 不再定义为“建设完整 Strategy Research System”。

唯一目标：

> **尽快让 ETF 与 Stock 候选真正跑通 Idea → Code → Backtest → OOS。**

最小建设：

1. 薄 `StrategyContract`；
2. 薄 Experiment Log；
3. ETF candidate universe；
4. Stock candidate universe；
5. AI Copilot workflow；
6. 第一批 Strategy implementations；
7. Basic Backtest；
8. 第一批 OOS。

M1 Exit：

> **至少有一批策略完成真实 OOS；项目已经能够快速重复“发现 → 实现 → 证伪”的循环。**

不要求：

- 完整 Knowledge Platform；
- 完整 Regime Router；
- 完整 UI；
- ActiveStrategyPack；
- Paper；
- AI Investor。

---

# 18. M2 — Survivor Validation & Paper

M2 只处理 M1 survivors。

目标：

> **找出是否真的有值得进入 Paper 的 Strategy / Strategy combination。**

主要任务：

- OOS 复核；
- robustness；
- walk-forward；
- cost stress；
- regime analysis；
- final holdout；
- combination tests；
- Paper Forward。

当已有足够 survivor 后，才设计：

```text
ETF CORE
+
STOCK SATELLITE
+
CASH
```

的 `ActiveStrategyPack candidate`。

M2 允许：

```text
0 survivor
```

如果如此：

> 回 M1 继续找策略，而不是继续造平台。

---

# 19. M3 — First Usable Daily Product

M3 只做真实使用闭环。

```text
EOD
↓
TargetPortfolio
↓
Pre-open ActionPlan
↓
ServerChan
↓
用户人工执行
↓
Fill / Reconcile
↓
继续下一交易日
```

M3 v1 最小交付：

- ActiveStrategyPack；
- daily scheduler；
- current holdings / cash；
- TargetPortfolio；
- ActionPlan；
- ServerChan；
- manual fill input；
- reconciliation；
- simple performance history；
- minimal UI / CLI；
- basic backup / missed-run detection。

UI 优先：

```text
今日行动
我的组合
简单运行历史
```

不要让 M3 因为“必须做完整 5 页产品”延期。

---

# 20. M4+ — 由真实使用问题驱动

M3 真正每天运行以后再决定优先级。

可能增加：

- richer Knowledge Ledger；
- better Research UI；
- full Strategy Lab；
- Opportunity Pool；
- richer Decision Outcome；
- Counterfactual；
- Strategy Health；
- regime routing；
- user-defined strategy experience；
- more data sources；
- richer Stock fundamentals；
- automated research reports。

原则：

> **用户真实使用中出现的问题，比今天架构师预测的问题优先级更高。**

---

# 21. AI Investor — 后置 Shadow Research

保持 v0.8 长期研究目标。

但它不影响：

```text
M1
M2
M3
```

只有可用 Quant 产品形成后，再投入：

- Private Investment Memory；
- AI Shadow Account；
- AIAdvisorVersion；
- Quant vs AI；
- memory vs no-memory；
- Forward Learning Curve。

正式交易通知仍然只来自 Quant Production。

---

# 22. Documentation Strategy：仍然使用软件工程流程，但采用滚动设计

本项目仍应严格使用软件工程方法。

但不是：

```text
今天
↓
把 M1 / M2 / M3 / M4 全部写成详细 Architecture + Implementation Plan
↓
未来几年照图施工
```

而是：

```text
总纲
↓
当前 Milestone 详细设计
↓
当前 Milestone 实施计划
↓
实现 / 测试
↓
真实 Evidence
↓
更新下一 Milestone 设计
```

也就是：

> **Milestone 内严格工程化，Milestone 间滚动设计。**

---

# 23. 当前文档权威关系

## 已冻结

M0 继续以现有详细文档为准：

```text
architecture.md
backtest-semantics.md
data-contracts.md
domain-model.md
portfolio-risk-semantics.md
production-runtime.md
test-plan.md
third-party-intake-policy.md
M0-implementation-plan.md
```

v0.9 不覆盖这些已经批准的 M0 语义。

## 新总纲

```text
personal-systematic-investing-os-v0.9-flight-test-driven-product-architecture.md
```

负责：

- 产品方向；
- M1+ scope；
- 快速迭代原则；
- milestone roadmap；
- 什么现在做 / 什么后做。

---

# 24. M1 文档包：现在应该让 Codex 设计什么

M0 接近完成以后，让 Codex 基于：

- v0.9 总纲；
- M0 真实代码；
- M0 已批准 docs；
- 当前测试结果；

只设计 **M1**。

建议只产出以下核心文档：

```text
docs/m1/
├─ M1-architecture.md
├─ strategy-research-protocol.md
├─ M1-test-plan.md
└─ OPEN_QUESTIONS.md

docs/plans/
└─ M1-implementation-plan.md
```

不要复制 M0 的九份文档模式机械地再造九份。

只有遇到真正新的复杂语义，才额外拆文档。

## 24.1 `M1-architecture.md`

回答：

- 最薄 StrategyContract；
- ETF / Stock candidate structure；
- experiment record；
- AI Copilot 如何调用研究工具；
- Strategy code 与 M0 kernel 如何连接；
- 什么属于 Research；
- 什么明确不属于 M1。

## 24.2 `strategy-research-protocol.md`

回答：

- Idea 如何进入；
- Cheap Screening；
- Basic Backtest；
- OOS；
- survivor definition；
- rejection rules；
- experiment versioning；
- failed experiment retention。

这是 M1 最重要的金融研究流程文档。

## 24.3 `M1-test-plan.md`

重点不是测试“Alpha 一定赚钱”。

而是：

- StrategyContract correctness；
- no lookahead；
- deterministic rerun；
- exact strategy version；
- experiment reproducibility；
- AI-generated Strategy 不能绕过 verifier；
- ETF / Stock sample strategies 正确连接 kernel；
- OOS split 不被污染。

## 24.4 `M1-implementation-plan.md`

必须：

- task-by-task；
- TDD；
- focused commits；
- 每个 Task 有 exit evidence；
- 避免一口气实现整个 Research Platform。

M1 Implementation Plan 的早期 Task 应尽快达到：

> **第一个真实策略可以在 M0 kernel 上跑出结果。**

而不是先做十几个 infrastructure tasks。

---

# 25. M2 / M3 文档现在怎么处理

现在只保留：

```text
M2 high-level objective
M3 high-level objective
```

**不要现在生成完整 M2 / M3 implementation plan。**

原因：

M2 的真正设计取决于 M1 的实际 survivor：

- 是 ETF trend？
- Stock breakout？
- Momentum？
- 一个都没有？

不知道这些事实，就无法合理设计组合和验证工作。

同样，M3 的 Production 细节应该基于：

```text
真实 ActiveStrategyPack
真实 turnover
真实 signal cadence
真实 holdings workflow
真实 Paper 结果
```

来设计。

---

# 26. Rolling Design Gate

推荐：

```text
M0 complete
    ↓
M1 Design Review
    ↓
M1 Implementation
    ↓
M1 Evidence Review
    ↓
M2 Design Review
    ↓
M2 Implementation
    ↓
M2 Paper Evidence Review
    ↓
M3 Design Review
    ↓
M3 Implementation
```

每个 Gate 都问：

1. 前一阶段真实发现了什么？
2. 原有假设哪些错了？
3. 下阶段最小必须建设什么？
4. 哪些功能继续后置？

---

# 27. 给 Codex 的开发原则

Codex 后续必须遵守：

> **Design to learn, not design to cover every future possibility.**

每个 milestone：

1. 先读取实际代码与测试；
2. 先读取上一个 milestone evidence；
3. 识别当前最大的未知；
4. 设计最短能获得答案的 implementation；
5. 保留金融 correctness；
6. 实现；
7. 运行；
8. 用真实结果修改下一步。

---

# 28. 最终 Roadmap

```text
M0
可信 Kernel
    ↓
M1
第一批 ETF / Stock 策略真正跑到 OOS
    ↓
M2
对 survivors 深度验证 + Paper
    ↓
M3
每天真实生成 TargetPortfolio / ActionPlan
    ↓
M4+
根据真实使用和策略研究瓶颈迭代
    ↓
Later
AI Investor Shadow
```

---

# 29. Final Decision

v0.9 的开发哲学是：

> **长期方向可以设计，短期实现必须由试飞数据决定。**

保留 v0.8 的宝贵成果，但不把所有成果一次性工程化。

第一阶段真正需要造出的不是：

> 一个完整的 Quant / AI Research Platform。

而是：

> **一条能够持续把投资思想变成可证伪策略、把幸存策略变成 Paper 决策、最终每天变成真实 ActionPlan 的流水线。**

每当出现两个选择：

```text
A. 再建设一个以后可能很有用的平台能力
B. 让一个真实策略更早接受 OOS / Paper / 实际使用检验
```

在不违反金融正确性的前提下：

> **优先 B。**
