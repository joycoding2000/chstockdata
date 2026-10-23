# Personal Systematic Investing OS
## v0.8 Consolidated Product Architecture Decision

> **版本**：v0.8  
> **日期**：2026-09-15  
> **定位**：整合 v0.2 rev2、v0.3、v0.4、v0.5、v0.6、v0.7 中仍然有效、且用户没有明确否定的设计；修正 v0.7 中“ETF 先行、Stock Satellite 后置”和固定策略数量等不再成立的假设。  
> **M0 状态**：M0 Design Gate 已通过且正在实施。**本版不重开、不修改 M0 scope，也不覆盖已批准的 M0 详细语义文档。**  
> **最高原则**：**先做一个真正有用的个人投资决策系统；保留完整的量化研究与验证核心；AI Copilot 从早期即参与研究；AI Investor 后置为独立 Shadow Research。**

---

# 0. Executive Summary

本项目不是量化开发框架，也不是机构资管平台，更不是“让 AI 随口推荐股票”的聊天应用。

它首先是：

> **一个面向单个个人投资者、每天能够给出可执行投资操作指示的系统化投资决策系统。**

系统每天要回答：

1. 今天组合应该持有什么？
2. 哪些资产需要买入？
3. 哪些资产需要卖出？
4. 各资产目标仓位是多少？
5. 当前证据不足或风险过高时，是否应该 `HOLD / CASH / NO ACTION`？

第一阶段正式 `TargetPortfolio` **同时支持 ETF Core 与 Stock Satellite**。

```text
                 TargetPortfolio

        CORE                      SATELLITE
   ETF / defensive                A-share stocks
        │                              │
        └──────────── CASH ────────────┘
                       │
                  ActionPlan
                       │
           BUY / SELL / HOLD / CASH
                       │
                 微信通知
                       │
                 用户人工执行
```

这里必须恢复并坚持 v0.3 已经明确的裁决：

> **ETF Core 与 Stock Satellite 都属于目标产品。**

它们在投资角色上有主次，但不是“先把 ETF 产品做完，未来再决定做不做股票”。

本版进一步裁定：

> **M1 起 ETF 与 Stock 的策略研究同步进行；M3 的目标产品模型就是包含 CORE + SATELLITE + CASH 的 TargetPortfolio。**

如果某个阶段 Stock Satellite 没有任何策略通过验证，则真实 Production 中 `SATELLITE` 可以为 0。  
**不能为了“第一阶段必须有股票”而把失败策略强行上线。**

---

# 0.1 v0.8 对前几版的继承与修正

## 保留，不应丢失

以下前期讨论成果继续有效：

- TargetPortfolio 是正式决策对象；
- ETF Core + Stock Satellite；
- Research / Production 隔离；
- Research Knowledge Plane；
- Investment Knowledge Ledger；
- Hypothesis Registry；
- `knowledge_available_at` / point-in-time discipline；
- Source Quality；
- 来源、版权、数据授权记录；
- 自建窄而可信的 A 股 / ETF daily-bar Quant Kernel；
- Backtest / OOS / Walk-forward / Final Holdout / Paper；
- Multiple Testing 意识和失败实验留档；
- Signal Evidence Card；
- Portfolio / Risk Engine；
- DecisionEpisode / ForwardEvaluation / Counterfactual / Strategy Health；
- 人工执行与 Fill Reconciliation；
- ServerChan 微信通知；
- chstockdata 作为第一 Data Provider；
- Provider-neutral canonical contracts；
- Instrument Master 与 provider / broker fee 权威分离；
- Reproducibility / Strategy Versioning；
- Strategy Decay / Kill Switch；
- AI Copilot；
- 5 个核心产品页面；
- AI Investor + Private Memory 的长期 Shadow Research；
- AI 不能自己产生 Ground Truth。

## 本版明确修正

### 1. 不再规定“必须有 10~20 个可用策略”

可以收集、实现大约这个量级的候选策略，但：

> **候选策略数量不是成功标准。**

完全可能：

```text
实现 15 个
通过验证 3 个
```

也完全可能：

```text
实现 15 个
通过验证 0 个
```

后者虽然令人失望，但研究系统必须接受这个结果。

### 2. 不再规定 Production 必须是 2~5 个策略

Production 到底用几个，由：

- 策略证据；
- 市场环境覆盖；
- 策略相关性；
- 组合效果；
- 风险；
- 实盘可执行性；

共同决定。

没有人为数量配额。

### 3. Stock Satellite 不后置到 M4

Stock 与 ETF 从 M1 起同步研究。

第一阶段最终产品就是：

```text
ETF Core
+
Stock Satellite
+
CASH
```

### 4. 用户公开 Strategy SDK 不是 M1 必备

为了内置策略和 AI Copilot，内部必须存在稳定 `StrategyContract`。

但“给用户做完整量化开发 SDK”不是 M1 目标。

以后仍保留：

- 用户写 Python Strategy；
- 用户自然语言描述策略，AI 帮助实现；

的接口空间，但不让它阻塞第一阶段产品。

### 5. AI Copilot 从 M1 开始

AI Copilot 不是后置锦上添花功能，而是：

> **Strategy Acquisition + Research 的核心生产力工具。**

### 6. AI Investor 继续后置

AI Investor 仍然有价值，但第一阶段正式交易通知只来自 Quant Production。

---

# 1. 产品定位与边界

## 1.1 首要目标

> **可靠地产生每天可执行的投资决策。**

例如：

```text
2026-xx-xx 明日操作

Market Regime: BULL

ETF CORE
BUY   510xxx   Target 25%
HOLD  518xxx   Target 15%

STOCK SATELLITE
BUY   600xxx   Target 4%
HOLD  300xxx   Target 3%

CASH
Target 28%

Risk Gate: PASS
Decision ID: ...
```

不是输出一篇市场评论。

不是要求用户自己打开回测平台再研究半天。

而是：

> **系统已经完成研究、验证、组合和风险计算，用户最终看到确定性的操作计划。**

---

## 1.2 个人散户级，而不是投资公司级

v1 明确：

- 单用户；
- 单主要 Managed Book；
- 默认研究 / Paper 起始资金 100,000 RMB；
- 中低频；
- 日线决策；
- 周到月级持有为主；
- Long-only；
- 不使用杠杆；
- 不做空；
- 不做期权 / 复杂衍生品；
- 不做高频；
- 不接券商自动交易；
- 用户人工执行。

不建设：

- 多租户；
- 多级审批；
- 机构 OMS / EMS；
- 合规工作流平台；
- 微服务；
- Kafka；
- Kubernetes；
- 分布式 Agent 平台。

---

## 1.3 收益 / 风险目标

长期参考目标：

```text
CAGR：约 10% ~ 15%
希望 MDD：约 <= 10%
```

它们是：

> **Product Objective / Release Reference**

不是：

> “让优化器不断调参数，直到满足两个数字。”

简单、稳健、OOS 可存活的策略，优先于漂亮但脆弱的回测。

---

# 2. 总体架构：四个世界，但只有一条真钱权威链

```text
┌───────────────────────────────────────────────────────┐
│  A. Research Knowledge + AI Copilot                   │
│  论文 / 论坛 / GitHub / 研报 / 书籍 / 历史复盘          │
└──────────────────────────┬────────────────────────────┘
                           ↓
┌───────────────────────────────────────────────────────┐
│  B. Quant Research + Verifier                         │
│  Hypothesis → Strategy → Backtest → OOS → Paper      │
└──────────────────────────┬────────────────────────────┘
                           ↓ approved only
┌───────────────────────────────────────────────────────┐
│  C. Quant Production                                  │
│  Data → StrategyPack → Portfolio/Risk → Target       │
│  → ActionPlan → 微信 → 人工执行                         │
└──────────────────────────┬────────────────────────────┘
                           ↓
               Outcome / Forward Evidence
                           ↓
                 回流 Research，不改历史

┌───────────────────────────────────────────────────────┐
│  D. AI Investor Shadow（后期）                         │
│  独立 AI TargetPortfolio + Private Memory            │
│  只模拟，不进入正式交易通知                             │
└───────────────────────────────────────────────────────┘
```

正式真钱权威始终只有：

```text
Quant Production
```

AI Copilot 与 AI Investor 都不能直接覆写 Production Target。

---

# 3. 资产架构：ETF Core + Stock Satellite 同属第一阶段目标产品

## 3.1 ETF Core

主要负责：

- 基础市场暴露；
- 大类资产配置；
- 趋势；
- 相对动量；
- 风险预算；
- 防御资产 / 现金切换；
- 控制整体回撤。

候选资产包括：

- 宽基权益 ETF；
- 风格 / 行业 ETF（只有研究证明有价值时）；
- 黄金 ETF；
- 债券 ETF；
- CASH。

ETF 数据范围必须受 M0 ETF Qualification Gate 约束。

---

## 3.2 Stock Satellite

主要负责：

- 在允许的市场环境中寻找额外 Alpha；
- 高流动性 A 股；
- 中低频 / 中长线；
- 单股仓位小于 Core 资产；
- 总风险受 Portfolio / Regime 约束。

第一批候选策略族仍优先：

- Trend；
- Breakout；
- Momentum；
- Liquidity filter；
- Quality / Fundamental Filter（仅在有可靠 PIT 基本面数据以后启用）。

技术形态、筹码、K 线等：

> 可以作为 feature / confirmation hypothesis，但不因为名称热门就直接升格为生产策略。

---

## 3.3 CORE / SATELLITE 是组合角色，不只是资产类型

M0 已经把：

```text
SleeveId = CORE | SATELLITE
```

定义为强类型概念。

因此后续策略必须明确自己产生的 TargetContribution 属于哪个 Sleeve。

CORE 和 SATELLITE 最终一起进入一个 TargetPortfolio，而不是形成两个互不相干账户。

---

# 4. Market Regime：至少先解决牛市 / 震荡市 / 熊市

用户当前认可的粗粒度市场环境是：

```text
BULL
SIDEWAYS
BEAR
```

v0.8 把它正式作为第一版研究框架。

但必须注意：

> **Regime 不是事后给行情贴标签，然后挑当时最好的策略。**

如果 Regime 参与 Production，它必须：

- 由确定性规则生成；
- 只使用当时已知数据；
- 版本化；
- 可回测；
- 不使用未来信息；
- 自己也接受 OOS / Forward 验证。

---

## 4.1 Strategy × Regime Coverage Matrix

Strategy Library 不按“凑够 20 个”建设，而按：

> **是否覆盖不同经济逻辑与市场环境。**

研究期维护：

| Strategy | Asset | BULL | SIDEWAYS | BEAR | Status |
|---|---|---:|---:|---:|---|
| Trend A | ETF | strong? | weak? | defensive? | RESEARCH |
| Momentum B | Stock | strong? | poor? | off? | RESEARCH |
| Breakout C | Stock | strong? | mixed? | off? | RESEARCH |
| Defensive D | ETF | low | medium | strong? | RESEARCH |
| Rotation E | ETF | good? | good? | defensive? | RESEARCH |

问号代表：

> **待证伪的 Hypothesis，而不是已知事实。**

---

## 4.2 每个大环境应有多个候选思路，但不保证最终能通过

M1 Research 目标：

- Bull：有多个趋势 / 动量 / breakout / relative-strength 候选；
- Sideways：有多个 rotation / defensive / mean-reversion 等候选，仅在证据支持时采用；
- Bear：有多个降风险 / trend exit / defensive allocation / cash / gold / bond 候选。

Stock Satellite 在 Bear 环境下：

```text
可能 = 0
```

这是完全合法的策略结果。

---

## 4.3 “熊市策略”不等于必须熊市赚钱

对于 Long-only 的个人系统：

> **在熊市成功减少亏损、及时降低股票仓位、转向 CASH / defensive assets，本身就是有效策略。**

系统不需要为了“每个 Regime 都赚正收益”引入做空和复杂衍生品。

---

# 5. Strategy Acquisition：策略到底从哪里来

这是第一阶段核心能力。

策略来源分为：

```text
A. 经典 / 学术 / 长期公开策略
B. 论坛 / 博主 / 研报中的可检验策略思想
C. GitHub 开源策略思想
D. AI Copilot 新提出的 Hypothesis
E. 用户自己的策略想法（保留入口，不作为 M1 主任务）
```

目标不是“策略代码数量”。

目标是：

> **持续发现值得验证的投资命题。**

---

# 6. Research Knowledge Plane —— 恢复并保留 v0.3 的核心设计

这是本项目区别于普通个人回测工具的重要能力，不能因为“Product First”而删除。

错误路径：

```text
1000 篇大神帖子
    ↓
RAG
    ↓
“今天买什么？”
```

正确路径：

```text
Source
   ↓
Claim Extraction
   ↓
Investment Knowledge Ledger
   ↓
Hypothesis
   ↓
Strategy Spec / Regime Rule / Risk Review
   ↓
Experiment
   ↓
Evidence
```

---

## 6.1 Investment Knowledge Ledger

每条重要经验保存为结构化知识。

示例：

```yaml
source_id: JQ-2026-0012

source:
  author: xxx
  platform: JoinQuant
  published_at: 2026-03-18
  knowledge_available_at: 2026-03-18
  url: ...
  type: forum_post

claim:
  raw: >
    小盘强势环境中，创20日新高且成交量放大的股票，
    后面通常还有趋势。

  normalized: >
    small_cap + breakout + volume_expansion
    may predict positive forward return

intended_universe:
  market: A-share

expected_horizon:
  10-30 sessions

conditions:
  - market_risk_on
  - small_cap_relative_strength_positive

unknowns:
  - small_cap exact definition
  - volume threshold
  - ST / IPO exclusions

falsifiable: true
```

关键原则：

> **来源没说清楚的条件，AI 不得擅自补成“事实”。**

用：

```text
UNKNOWN
```

明确保存。

---

## 6.2 人类投资经验分三类

### A. 可量化命题

例如：

> 放量突破后存在趋势延续。

进入：

```text
Hypothesis → Strategy → Backtest
```

### B. 市场环境经验

例如：

> 熊市缩量时，小盘 breakout 的失败率高。

进入：

```text
Regime / Risk Hypothesis
```

### C. 难直接量化判断

例如：

> 某产业政策出现结构性变化。

进入：

```text
AI Copilot Risk Review
```

不要求把所有知识都强制转成策略代码。

---

## 6.3 Knowledge Available Date

必须保存：

```text
published_at
knowledge_available_at
```

如果一个策略在 2025 年才公开，却展示：

```text
2010~2024 的优秀回测
```

不能把 2010~2024 当成真正的公开后 Forward Evidence。

需要单独观察：

```text
post-publication forward performance
```

这对防止“事后策略幸存者偏差”很重要。

---

## 6.4 Source Quality

来源等级只影响：

> **研究优先级。**

不能影响：

> **策略是否通过。**

建议简单标记：

```text
A = 条件明确、长期记录、时间可核查、有失败案例
B = 逻辑清楚，但 track record 不完整
C = 热门帖子、收益截图、案例
D = 事后神预测、不可证伪
```

A 优先测试。

D 可以不浪费时间。

---

## 6.5 来源、版权和许可

论坛 / 研报 / 论文：

保存：

- URL；
- 作者；
- 日期；
- 摘要；
- Claim；
- Hypothesis；
- 必要短摘录。

不默认批量复制完整文章。

GitHub：

- 先看 License；
- 策略思想可以研究；
- 代码是否可以复用取决于具体许可；
- GPL / AGPL / Non-commercial / unclear license 不复制进核心；
- 所有外部代码 intake 保留 provenance。

---

# 7. Hypothesis Registry：真正长期积累的是“研究历史”

Strategy Library 只是代码集合。

更重要的是：

> **我们研究过哪些命题、为什么通过、为什么失败。**

建议生命周期：

```text
IDEA
 ↓
SPECIFIED
 ↓
TESTING
 ↓
OOS_PASS / OOS_FAIL
 ↓
PAPER
 ↓
APPROVED / REJECTED
 ↓
ACTIVE
 ↓
WATCH / PAUSED / RETIRED
```

不需要在 v1 做复杂审批系统。

但每次实验都必须能够关联：

```text
source
hypothesis
strategy_version
experiment
result
```

失败不删除。

---

# 8. AI Copilot —— 从 M1 开始，与策略研究同步建设

AI Copilot 是第一阶段正式能力。

它不是最终交易权威，但它可以极大提高：

> **发现策略 → 形式化 → 写代码 → 验证 → 复盘**

的速度。

---

## 8.1 AI Copilot 的核心工作

### Source Research

- 搜论文；
- 读论文；
- 搜各大论坛；
- 读 JoinQuant / 公开投资帖子；
- 读 GitHub；
- 读研报 / 策略说明；
- 找经典策略及后续 replication / critique。

### Claim & Hypothesis

- 抽取投资命题；
- 区分事实 / 作者观点 / 未定义参数；
- 建立 Knowledge Ledger；
- 生成 Hypothesis；
- 标记适用市场、horizon、regime。

### Strategy Engineering

- 形成 Strategy Spec；
- 生成研究代码；
- 写测试；
- 调用统一 Backtest Kernel；
- 修复策略实现 bug；
- 保存 Experiment Manifest。

### Verification Assistant

- 运行 IS / OOS；
- 运行 walk-forward；
- 参数敏感性；
- 成本 stress；
- Regime breakdown；
- 找未来函数和数据泄漏风险；
- 分析为什么失败。

### Product Explanation

- 解释 Quant Signal；
- 解释 TargetPortfolio 变化；
- 检查新闻、政策、行业风险；
- 寻找反例。

### Postmortem

- 读取 DecisionEpisode；
- 读取 ForwardEvaluation；
- 分析 GOOD / BAD / MIXED；
- 提出 Strategy vNext Hypothesis。

---

## 8.2 AI Copilot 的权限边界

AI 可以：

```text
Research Proposal
Strategy Draft
Experiment Plan
Postmortem
```

AI 不能：

```text
直接把 Strategy 改成 APPROVED
直接修改 Production StrategyPack
直接改变 TargetPortfolio
```

---

## 8.3 AI Copilot 与模型供应商解耦

保留：

```text
AIModelPort
```

支持：

- Metered API；
- 官方允许的 subscription programmatic access；
- Local Model。

如果某种 ChatGPT / Coding Plan 订阅只允许交互 / coding 场景：

> 用于 Research / Coding，不通过模拟网页登录等方式绕开限制。

---

# 9. Strategy Library：候选池，不是荣誉榜

第一阶段需要形成一个有一定广度的 Candidate Library。

但不规定：

```text
必须通过 10 个
```

更合理的目标是：

> **每个主要 Asset / Regime / Strategy Family 都有几个独立候选进入验证。**

实际实现数量可能大约 10~20，也可能更多或更少。

这只是研究工作量参考，不是 Release Gate。

---

## 9.1 ETF Candidate Families

优先：

- Absolute Trend；
- Time-Series Momentum；
- Relative Momentum；
- Rotation；
- Tactical Asset Allocation；
- Defensive Allocation；
- Volatility Control；
- Drawdown Throttle；
- Cash / Gold / Bond switching。

---

## 9.2 Stock Candidate Families

优先：

- Trend；
- Breakout；
- Momentum；
- Relative Strength；
- Liquidity；
- simple quality filters（PIT data available only）；
- regime-conditioned satellite exposure。

第一阶段不要一上来：

- 几十个因子；
- 复杂 ML；
- 黑盒预测；
- 形态识别大全。

---

# 10. 内部 Strategy Contract 必须有；公开开发框架可以后做

为了让内置策略和 AI Copilot 能够统一开发、回测和验证，M1 必须存在：

```text
StrategyContract
```

概念上类似：

```python
signal = strategy.evaluate(context)
```

它至少统一：

- StrategyVersion；
- Universe；
- required data；
- information cutoff；
- signal / target contribution；
- SleeveId；
- reason / evidence；
- primary evaluation horizon。

但：

> **M1 不要求做面向最终用户的完整 Strategy SDK。**

后续仍可开放：

- 用户 Python Strategy；
- 用户自然语言 → AI Copilot → Strategy Draft。

---

# 11. Quant Development Core：本项目必须有完整“量化开发闭环”

虽然本项目不是量化开发平台，但没有量化开发核心就无法判断策略是不是垃圾。

因此必须保留：

```text
Hypothesis
   ↓
Strategy Spec
   ↓
Implementation
   ↓
Backtest
   ↓
Research / IS
   ↓
Validation / OOS
   ↓
Walk-forward
   ↓
Robustness
   ↓
Final Holdout
   ↓
Paper Forward
```

这是投资产品的内部研发流程，而不是给用户卖一个通用 Quant IDE。

---

# 12. 如何验证策略 —— v1 使用“足够严格、但不过度学术化”的 Gate

用户无需先成为专业量化研究员。

系统把验证流程固化成默认标准。

---

## 12.1 第一层：实现正确

必须先证明：

- 没有未来函数；
- `T close → T+1 execution` 等时间语义正确；
- Point-in-time 数据正确；
- 费用 / 税 / 滑点存在；
- 涨跌停 / 停牌 / lot / cash 等规则被处理；
- corporate action 不重复记账；
- Universe 没有明显 survivorship bias。

这些能力主要由 M0 提供。

---

## 12.2 第二层：Research / In-Sample

Research 区间用于：

- 理解策略；
- 选择少量经济上合理的参数范围；
- debug；
- 初步排除明显无效策略。

允许看结果、修改策略。

但所有尝试必须记录。

---

## 12.3 第三层：固定 OOS

在看 OOS 结果前冻结：

- Strategy Version；
- 参数；
- Universe；
- benchmark；
- cost model；
- evaluation horizon。

如果看到 OOS 后改策略：

> 新版本重新验证。

---

## 12.4 第四层：Walk-forward

检查：

> 策略是否只能在某一个历史切片有效。

使用多个滚动训练 / 验证窗口。

不要求构建复杂自动优化器。

---

## 12.5 第五层：Robustness

至少检查：

- 参数附近 ±10%~20% 是否立即崩掉；
- 交易费用 / 滑点提高后是否仍可接受；
- 是否只靠少数几笔交易；
- 是否只靠单一年份；
- Bull / Sideways / Bear 表现；
- 不同子样本表现。

---

## 12.6 第六层：Final Holdout

保留真正最后一段不碰的数据。

一旦：

> 看过 Holdout，并根据结果修改策略，

它就不再是 Final Holdout。

---

## 12.7 第七层：Paper Forward

策略真正上线真钱前：

```text
今天产生决策
↓
冻结
↓
未来市场发生
↓
再判卷
```

Paper 的核心不是 UI，而是：

> **生成不可回写的 Forward Evidence。**

---

# 13. Multiple Testing：AI 越强，这个问题越重要

AI Copilot 可以一天测试大量策略。

所以必须保存：

```text
tested hypothesis count
parameter search count
experiment lineage
all rejected experiments
```

第一版不要求立即实现：

- Deflated Sharpe Ratio；
- Probability of Backtest Overfitting；
- 复杂 False Discovery Control。

但必须先把实验历史保留下来。

否则未来无法判断：

> 这个“优秀策略”是不是从几千次失败中碰巧挑出来的。

---

# 14. Strategy × Regime Evidence，而不是“牛市就人工切策略”

每个 Strategy Version 要记录：

```text
intended_regimes
observed_regime_performance
known_failure_regimes
```

但 Production 不允许：

> 用户看行情像牛市，于是手动打开一个回测最好看的牛市策略。

如果采用 regime routing，必须作为：

```text
versioned deterministic StrategyCompositionPolicy
```

与策略一起回测和验证。

---

# 15. Active StrategyPack：Production 每天到底运行什么

Strategy Library 可以很大。

Production 只能运行一个明确的：

```text
ActiveStrategyPack
```

它包含：

```text
approved ETF strategies
approved Stock strategies
universe rules
regime policy
strategy composition
portfolio rules
risk rules
rebalance / materiality rules
benchmark
cash semantics
version
```

不要把它做成机构级配置系统。

它只需要回答：

> **今天系统究竟依据哪些冻结规则生成 TargetPortfolio？**

---

## 15.1 策略数量不预设

可能：

```text
Bull:
  Strategy A
  Strategy B

Sideways:
  Strategy C

Bear:
  Defensive Strategy D
```

也可能：

```text
一个策略跨多个 Regime 工作
```

也可能：

```text
某个 Regime 没有任何 Alpha Strategy
→ CASH / defensive
```

数量由证据决定。

---

## 15.2 单策略通过不等于组合通过

ActiveStrategyPack 还要整体检查：

- strategy correlation；
- capital competition；
- turnover；
- MDD；
- Stock Satellite cap；
- benchmark；
- costs；
- regime interaction。

---

# 16. Signal Evidence Card —— 保留

每个重要交易信号应能查看程序生成的 Evidence。

示例：

```text
Strategy: Stock Breakout v1.3
Symbol: XXXX

Today
────────────────────
Breakout: PASS
20D momentum: Top 8%
Volume expansion: 1.42x
Market regime: BULL

Historical Evidence
────────────────────
Historical events: 286
Forward 20D median: +4.8%
Win rate: 61.2%
P25: -3.1%
P75: +10.4%
MAE: -5.2%
MFE: +12.7%

OOS
────────────────────
Period: ...
Excess Return: ...
MDD: ...
Turnover: ...

Portfolio Risk
────────────────────
Satellite exposure after trade: ...
Sector exposure: ...
Target weight: 4%
```

AI 可以解释。

数字由程序生成。

---

# 17. Portfolio / Risk：系统最终管理的是组合，不是策略排行榜

至少支持：

- Max position weight；
- Max total equity exposure；
- Max Stock Satellite exposure；
- Cash floor；
- Sector concentration；
- Correlation awareness；
- strategy / sleeve risk budget；
- Volatility control（如果验证有效）；
- Drawdown throttle（如果验证有效）。

核心逻辑：

```text
Strategy Signals
    ↓
Target Contributions
    ↓
Portfolio Construction
    ↓
Risk Transform / Veto
    ↓
TargetPortfolio
```

Risk 可以降低 / veto exposure。

Risk 不能凭空创造 Alpha。

---

# 18. Market Regime 与 Stock Satellite 风险联动

第一版可以研究类似以下结构：

```text
BULL:
  Satellite cap = higher

SIDEWAYS:
  Satellite cap = medium / selective

BEAR:
  Satellite cap = low or zero
```

但具体数值不是现在拍脑袋决定。

必须：

> **进入 M1 Research → M2 Validation。**

Regime 不是“用户感觉牛市了”的人工开关。

---

# 19. Data：继续使用 chstockdata，但 Quant Domain 自己掌握语义

保持：

```text
systematic-investing-os
        ↓
DataProviderPort
        ↓
ChStockDataProvider
        ↓
chstockdata
```

chstockdata 负责：

- vendor access；
- fallback；
- 数据抓取；
- 底层 provider 细节。

Investing OS 负责：

- canonical contracts；
- snapshot；
- data quality；
- point-in-time correctness；
- Instrument Master；
- strategy / backtest / portfolio / risk。

Production 不通过 MCP 获取关键行情。

---

## 19.1 保留 M0 四个重要权威边界

### Instrument Master 与 provider 分离

Provider 给 market facts / candidate reference。

系统自己的 Instrument Master 才是：

- instrument classification；
- ETF subtype；
- lot；
- settlement；
- price-limit；
- effective-dated market/tax rules；

的 Production authority。

### Information availability 与 retrieval time 分离

历史事实必须区分：

```text
information_available_at
retrieved_at
availability_basis
```

不能因为今天 API 能返回一个历史值，就假设当时市场参与者已经知道。

### Sizing 与 Fill 分离

```text
T_CLOSE
→ sizing reference

NEXT_SESSION_OPEN
→ backtest execution model
```

Pre-open Production 不能看到未来 Open。

### CORE / SATELLITE 强类型

Strategy contribution 必须显式声明 CORE / SATELLITE。

---

# 20. Stock Universe：第一阶段同步研究，但先保持简单

第一版 Stock Satellite 不需要覆盖全部 A 股复杂逻辑。

Universe 至少研究并冻结：

- 流动性；
- listing age；
- ST；
- suspension；
- delisted / not-listed；
- limit states；
- 是否需要 sector filter；
- survivorship-safe membership；
- 可交易性。

如果缺少可靠 PIT 基本面数据：

> **先不要让“质量因子”偷偷使用今天才能知道的数据。**

可以先从：

```text
Price / Volume / Liquidity / Trend / Momentum / Breakout
```

类策略研究起步。

---

# 21. ETF Universe：与 Stock 同期研究

ETF Universe 第一阶段应：

- 流动性足够；
- 经济暴露不同；
- 避免高度重复；
- ETF subtype 已过数据资格；
- 明确历史长度；
- 明确是否允许 index proxy。

如果用历史指数 proxy：

- proxy 和真实 ETF 必须分开；
- 不能假装 ETF 当年可交易；
- 报告明确真实可投资区间。

---

# 22. Benchmark 与 CASH：M1 必须确定，但保持简单

需要：

```text
ETF / whole portfolio benchmark
cash comparator
```

Benchmark 必须在看策略最终结果前决定。

`CASH` 与：

- bond ETF；
- money-market fund；
- repo-like asset；

不是同一个东西。

防御资产仍是资产仓位。

---

# 23. Daily Production Runtime

继续沿用已经批准的两阶段运行思想。

---

## 23.1 EOD Decision Run

收盘数据完整后：

```text
Market Data
    ↓
Data Quality
    ↓
Regime
    ↓
ActiveStrategyPack
    ↓
ETF + Stock Target Contributions
    ↓
Portfolio
    ↓
Risk
    ↓
TargetPortfolio
    ↓
Decision Lock
```

基础日线 Alpha 在这里完成。

---

## 23.2 Pre-open Execution Confirmation

开盘前：

```text
Load Locked Target
     ↓
Current Holdings / Cash
     ↓
Calendar / Tradability / Corporate Action
     ↓
Risk / Data Checks
     ↓
ActionPlan
     ↓
ServerChan
```

Pre-open 不重新运行基础日线 Alpha。

---

## 23.3 正式通知只来自 Quant Production

正式交易通知只包含 deterministic 结果：

```text
BUY
SELL
HOLD
CASH
NO ACTION
current weight
target weight
planned quantity
reason code
decision id
```

AI Copilot 可以在 UI / Research 页解释原因。

但不在正式指令中额外发一套 AI 买卖意见。

---

# 24. Manual Execution + Reconciliation

v1 不自动下单。

用户实际成交后，记录：

```text
actual_time
actual_price
actual_quantity
fees
```

系统形成：

```text
Plan vs Actual
```

原则：

> **Plan 不等于 Fill。**

发过 BUY 通知，不代表用户已经持有。

只有：

```text
actual fill / reconciled state
```

才能改变真实 PortfolioSnapshot。

---

# 25. Decision Outcome & Controlled Learning Loop —— 继续保留

这首先服务 Quant Production，不是 AI Research 的附属品。

---

## 25.1 DecisionEpisode

不要每天重复 HOLD 都生成独立样本。

当出现：

- 实质 target 变化；
- 新开仓；
- 明显减仓；
- 清仓；
- regime / thesis 发生实质变化；

创建或更新 Episode。

---

## 25.2 评价周期必须预注册

每个 Strategy 在决策时就有：

```text
primary_evaluation_horizon
```

可以同时记录：

```text
5D
20D
60D
```

但不能事后挑最好看的周期宣布“当时判断正确”。

---

## 25.3 ForwardEvaluation

至少记录：

- return；
- benchmark return；
- excess return；
- MAE；
- MFE；
- drawdown；
- execution drag；
- counterfactual value。

---

## 25.4 Counterfactual

最重要的对照之一：

> **如果当时维持原仓位不变，结果会怎样？**

用于估算：

```text
Decision Value Add
```

SELL 还可以区分：

- avoided loss；
- missed upside。

---

## 25.5 Strategy Health 第一版保持简单

先使用：

```text
ACTIVE
WATCH
PAUSED
```

以后确有需要再加：

```text
DEGRADED / RETIRED
```

不能两三次亏损就自动调参数。

---

## 25.6 Learning Loop 的权限边界

```text
Outcome
  ↓
AI Copilot Postmortem
  ↓
New Hypothesis
  ↓
New Strategy Version
  ↓
重新验证
```

不是：

```text
Outcome 不好
  ↓
AI 直接改参数
  ↓
Production 明天继续跑
```

---

# 26. Reporting：分清策略问题与执行问题

至少长期区分：

```text
Model / Target Performance
Paper / Simulated Performance
Actual Portfolio Performance
```

并尽量拆解：

- strategy contribution；
- portfolio / risk effect；
- fees；
- slippage；
- lot / cash drag；
- missed execution；
- external trades / cash flows。

否则无法判断：

> 策略错了，还是人执行偏了。

---

# 27. Product UI：恢复 v0.3 的 5 个核心页面

M3 的 UI 不必复杂。

可以先 CLI + 简单 Web。

目标页面仍保留：

## 27.1 今日行动

- BUY；
- SELL；
- HOLD；
- CASH；
- NO ACTION；
- current / target；
- Market Regime；
- Risk state。

## 27.2 机会池

- ETF / Stock candidates；
- Strategy；
- Evidence；
- Regime；
- Ranking。

## 27.3 我的组合

- 当前持仓；
- 目标持仓；
- CORE / SATELLITE / CASH；
- 风险；
- Drawdown。

## 27.4 策略实验室

- Backtest；
- OOS；
- Walk-forward；
- Sensitivity；
- Cost Stress；
- Regime breakdown；
- Experiment history。

## 27.5 交易复盘

- Decision；
- Fill；
- Plan vs Actual；
- Forward Outcome；
- Counterfactual；
- Strategy Health。

---

# 28. Production Reliability：只做到个人真钱系统需要的程度

不要做企业级高可用。

但真钱使用至少需要：

- scheduler；
- durable persistence；
- idempotent rerun；
- backup；
- missed-run detection；
- provider failure handling；
- secret management；
- Asia/Shanghai trading calendar correctness。

可以使用：

```text
single local / home-server / VPS deployment
```

只要稳定即可。

如果主程序完全死亡，最好有一个很简单的外部 heartbeat / expected-run check。

不建设完整 observability platform。

---

# 29. Security：简单但不能没有

至少：

- API key 不进 Git；
- secret 用环境变量 / local secret store；
- log redaction；
- 数据 / 决策备份；
- AI 没有 Production target write permission。

---

# 30. AI Investor —— 长期研究，后置于可用产品

长期研究目标继续保留：

> **验证“强基础模型 + 私有长期投资记忆 + 真实市场反馈 + 外部 verifier”能否形成优于用户本人、甚至优于纯规则 Quant 的投资决策者。**

但它不阻塞 M1~M3。

---

## 30.1 AI Investor Shadow

未来：

```text
Same DataSnapshot
      ├── Quant Production
      └── AI Investor Shadow
              ↓
        Shadow TargetPortfolio
              ↓
        Shadow Performance
```

AI Shadow：

- 独立模拟账户；
- 独立 TargetPortfolio；
- 与 Quant 相同 information cutoff；
- 同一 verifier；
- 不进入正式交易通知；
- 不改变 Quant Production。

---

## 30.2 Private Investment Memory

保留两层概念：

### Ground Truth Memory

来自确定性系统：

- DecisionEpisode；
- ForwardEvaluation；
- Fill；
- PortfolioSnapshot；
- market regime；
- strategy evidence。

### Cognitive Memory

允许 AI 生成：

- lessons；
- postmortem；
- thesis；
- failure pattern；
- similar historical cases。

AI 可以修改 Cognitive Memory。

不能修改 Ground Truth。

---

## 30.3 AI 是否进入 Production

不是当前 Roadmap 承诺。

只有未来存在：

- 足够长期 Forward Evidence；
- 风险调整后结果更好；
- 排除明显 beta / style illusion；
- 多 Regime 稳定；
- private memory 确实贡献增量；

才另立 Architecture Decision。

---

# 31. 技术形态：Modular Monolith，够用即可

建议：

```text
Python 3.12+
Pydantic / dataclasses
Pandas or Polars（内部统一一种主路径即可）
DuckDB
Parquet
SQLite / embedded transactional store
pytest
ServerChan
minimal Web UI（M3）
```

M0 已批准的 canonical schemas 不绑定 dataframe library。

不要为了未来可能性提前引入：

- Kafka；
- Redis Cluster；
- Kubernetes；
- Spark；
- GPU；
- Microservices；
- Agent Swarm；
- 大型 workflow platform。

---

# 32. 推荐的高层模块

不把仓库拆得过度细碎，但长期边界应支持：

```text
src/
├─ domain/
├─ data/
├─ instrument_master/
├─ backtest/
├─ research/
│  ├─ knowledge/
│  ├─ hypotheses/
│  ├─ experiments/
│  └─ registry/
├─ strategies/
│  ├─ etf/
│  └─ stock/
├─ regime/
├─ portfolio/
├─ risk/
├─ evidence/
├─ outcomes/
├─ production/
│  ├─ decision/
│  ├─ reconciliation/
│  └─ notification/
└─ ai/
   ├─ copilot/
   ├─ postmortem/
   └─ investor_shadow/   # later
```

实现时允许比这个更简单。

架构边界比目录数量重要。

---

# 33. Revised Roadmap

---

## M0 — Foundation（正在实施，不动）

继续严格执行已经批准的 M0 Implementation Plan。

目标：

> **建立可信的 Data / Domain / Backtest / Portfolio / Risk 基础。**

M0 不加入：

- Alpha strategies；
- AI；
- UI；
- Notification；
- Strategy Research workflow。

---

## M1 — Strategy Research System：ETF + Stock + AI Copilot 同步

这是 M0 以后最重要的阶段。

目标：

> **让系统真正开始“研究投资”，而不是继续扩基础设施。**

M1 同时建设：

### Research Knowledge

- Investment Knowledge Ledger；
- Source provenance；
- `knowledge_available_at`；
- Hypothesis Registry。

### AI Copilot

- Source → Claim；
- Claim → Hypothesis；
- Hypothesis → Strategy Spec；
- Strategy code draft；
- Backtest orchestration；
- failure analysis。

### ETF Research

- ETF Universe；
- Trend；
- Absolute / Relative Momentum；
- Rotation；
- Defensive / risk candidates。

### Stock Research

- Survivorship-safe candidate universe；
- Trend；
- Breakout；
- Momentum；
- Relative Strength；
- Liquidity filters；
- simple PIT-safe quality hypothesis where data supports.

### Regime Research

- BULL / SIDEWAYS / BEAR v1 definition；
- Strategy × Regime Matrix；
- several candidate ideas per major regime。

### Strategy Infrastructure

- internal StrategyContract；
- Strategy Registry；
- Experiment history；
- failed experiment retention。

### M1 Exit

不是：

```text
“已经有 20 个策略”
```

而是：

> **已经形成可持续的策略发现 / 实现 / 回测体系，并有一批 ETF 与 Stock 候选进入正式验证。**

---

## M2 — Evidence, Validation & Active StrategyPack

目标：

> **决定哪些策略有资格进入 Paper / Production。**

完成：

- IS / OOS；
- walk-forward；
- sensitivity；
- cost/slippage stress；
- Regime breakdown；
- benchmark；
- final holdout；
- multiple-testing history；
- combination testing；
- Paper Forward；
- TargetPortfolio-level evidence；
- DecisionEpisode / ForwardEvaluation contracts。

形成：

```text
ActiveStrategyPack candidate
```

它可以同时包含：

```text
ETF CORE
+
Stock SATELLITE
```

但只包含真正通过验证的策略。

### M2 允许的结果

可能：

```text
ETF PASS
Stock PASS
```

也可能：

```text
ETF PASS
Stock FAIL
→ SATELLITE = 0
```

也可能：

```text
全部 FAIL
→ 不进入真钱 Production
```

研究结果不能被产品排期强迫。

---

## M3 — Usable Daily Investment Product

目标：

> **每天给出真正可执行的 ETF + Stock 组合决策。**

交付：

- ActiveStrategyPack；
- Market Regime；
- EOD Decision Run；
- TargetPortfolio；
- CORE / SATELLITE / CASH；
- Pre-open confirmation；
- ActionPlan；
- ServerChan；
- holdings / cash；
- manual fill reconciliation；
- basic owner controls；
- DecisionOutcome；
- 5 core pages 或足够完成同样任务的 minimal UI。

M3 成功标准：

> 用户不需要懂回测细节，也能每天知道该怎么操作；同时所有决策背后仍然可以追溯到策略和证据。

---

## M4 — Research Loop & Strategy Expansion

M3 可用以后再增强：

- 更多策略来源；
- 更多 regime evidence；
- deeper postmortem；
- Strategy decay；
- 自动 Research report；
- 用户自定义 Strategy experience；
- Stock / ETF universe expansion。

这不是让 Production 变复杂，而是提高研究质量。

---

## M5 — AI Investor Shadow

开始：

- Private Investment Memory；
- AIAdvisorVersion；
- Shadow Portfolio；
- Quant vs AI；
- memory vs no-memory；
- Forward Learning Curve。

仍然：

```text
Shadow only
```

---

# 34. 第一阶段“不做什么”

继续排除：

- 自动券商交易；
- 高频；
- 做空；
- 杠杆；
- 衍生品；
- 多用户 SaaS；
- Strategy Marketplace；
- 社交；
- 机构级审批；
- 复杂多账户；
- ML 黑盒选股；
- AI 自动改 Production；
- AI Investor 真钱权限。

---

# 35. 开发优先级判断规则

以后新增功能，不再用两个极端标准：

错误标准 A：

> “以后可能有用，所以现在都设计进去。”

错误标准 B：

> “没有它今天也能跑，所以全部删除。”

正确标准：

> **这个能力是否明显提高投资决策质量、验证可信度、每日可用性，或者为已经确定的长期目标保留必要边界？**

优先做：

```text
策略发现
策略验证
数据可信
组合与风险
每日决策
执行可用性
复盘学习
```

后置：

```text
只提升架构完整性、
但对个人投资结果没有近期价值的基础设施。
```

---

# 36. v0.8 Architecture Invariants

后续 Codex / Agent 必须遵守：

1. **M0 已通过 Design Gate并正在实施；不得用 v0.8 重开 M0。**
2. **这是个人投资决策产品，不是机构平台。**
3. **ETF Core + Stock Satellite 都属于第一阶段目标产品。**
4. **M1 起 ETF 与 Stock 策略研究同步进行。**
5. **M3 TargetPortfolio 的模型原生支持 CORE + SATELLITE + CASH。**
6. **若 Stock Strategy 没有通过，SATELLITE 可以为 0；不能强行上线。**
7. **策略候选数量不等于策略质量，不设置“必须通过 N 个”的配额。**
8. **每个主要 Regime 要研究多个候选机制，但没有可用策略时 CASH / defensive 是合法输出。**
9. **AI Copilot 从 M1 开始，是 Research 核心能力。**
10. **Research Knowledge Plane、Investment Knowledge Ledger、Hypothesis Registry 不得删除。**
11. **内部 StrategyContract 必须有，但用户级 Strategy SDK 不阻塞 M1。**
12. **Quant Development Loop 必须完整：Backtest → OOS → Walk-forward → Holdout → Paper。**
13. **所有失败实验保留，不只保存赢家。**
14. **Production 只运行已验证的 ActiveStrategyPack。**
15. **TargetPortfolio 是正式决策；BUY/SELL 是当前与目标的差值表达。**
16. **正式买卖通知只来自 Quant Production。**
17. **AI Copilot 可以解释 / 研究，不能写 Production Target。**
18. **Decision Outcome / Forward Evaluation 是产品核心，不是 AI 附属功能。**
19. **Plan 不等于 Fill，真实持仓来自 reconciliation。**
20. **AI Investor 后置为 Shadow，除非未来证据足以支持新的 Authority ADR。**
21. **chstockdata 是第一 Provider，但 canonical domain 与 Instrument Master 归本项目。**
22. **LLM 输出不是 Ground Truth。**
23. **收益目标不是自动调参目标。**
24. **简单、稳健、可解释、可执行优先于复杂漂亮的历史回测。**

---

# 37. 需要后续人工裁决，但现在不阻塞 M0 的问题

本版不替用户拍脑袋决定以下投资细节。

它们在 M1/M2 逐步裁决：

1. BULL / SIDEWAYS / BEAR 的具体 deterministic 定义；
2. 第一批 ETF Universe；
3. 第一批 Stock Universe；
4. 每个 Regime 优先研究哪些策略族；
5. Benchmark；
6. CASH 具体收益语义；
7. CORE / SATELLITE 风险预算；
8. 单股最大仓位；
9. Stock Satellite 最大占比；
10. Rebalance / materiality；
11. Paper Forward 至少需要怎样的时间与信号覆盖；
12. ActiveStrategyPack 的具体 StrategyCompositionPolicy；
13. M3 的实际部署位置：Windows 常开机 / NAS / VPS；
14. 是否在 M3 就做完整 5 页 Web UI，还是先以 CLI + 简洁页面上线。

这些问题需要证据和研究，不应该现在凭直觉全部定死。

---

# 38. 给后续开发 Agent 的一句话

> **不要再扩大基础设施，也不要为了“简单”把研究能力砍掉。M0 完成后，把主要工程资源投入到：Research Knowledge + AI Copilot + ETF/Stock Strategy Research + Verifier；让策略经过真实证据筛选后组成 ActiveStrategyPack，再把它变成每天稳定输出 TargetPortfolio 和 ActionPlan 的个人投资产品。**

---

# 39. Final Product Vision

最终形成：

```text
       Papers / Forums / GitHub / Reports
                    │
                    ↓
          Research Knowledge Plane
                    │
                    ↓
               AI Copilot
                    │
                    ↓
            Hypothesis Registry
                    │
                    ↓
             Strategy Library
             /              \
          ETF                Stock
           │                  │
           └──── Quant Verifier ────┐
                     │               │
             Approved Strategies     │
                     │               │
               Market Regime         │
                     │               │
               ActiveStrategyPack    │
                     │               │
          ┌──────────┴──────────┐    │
          │                     │    │
       ETF CORE           STOCK SATELLITE
          │                     │
          └──────────┬──────────┘
                     ↓
               TargetPortfolio
                     ↓
                 Risk / Cash
                     ↓
                 ActionPlan
                     ↓
                ServerChan
                     ↓
               用户人工执行
                     ↓
              Reconciliation
                     ↓
              Decision Outcome
                     ↓
           Forward / Counterfactual
                     ↓
               AI Copilot 复盘
                     ↓
              New Hypothesis
```

后期再增加：

```text
AI Investor Shadow
      +
Private Investment Memory
      +
Same External Verifier
```

而不改变第一阶段真钱主链：

> **Quant Strategy → TargetPortfolio → ActionPlan → 用户。**

---

# 40. 最终原则

这个项目既不能被做成：

> “只有一个均线策略的简单 Demo”

也不能被做成：

> “一个个人永远做不完的基金公司级投资平台”。

v0.8 的平衡点是：

> **研究可以丰富，Production 必须克制。**  
> **ETF 与股票都做，但只上线通过验证的。**  
> **AI Copilot 要尽早发挥知识和编程优势，AI Investor 要接受长期 Shadow 验证。**  
> **量化开发流程必须专业到足以识别过拟合和数据作弊，但系统工程只做到个人真钱投资需要的程度。**  
> **系统长期积累的真正资产，是 Research Knowledge、Hypothesis History、Strategy Evidence、Forward Track Record 和真实 Decision Outcome，而不是策略文件数量。**
