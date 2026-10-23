# Personal Systematic Investing OS
## v0.7 Balanced Product-First Architecture Decision

> **版本**：v0.7  
> **日期**：2026-09-15  
> **状态**：建议作为新的最高层产品总纲，供人工审查。  
> **M0 状态**：M0 Design Gate 已通过且正在实施；**本版不重开、不修改 M0 scope**。  
> **最高原则**：**Retail First / Product First / Evidence First**。先做一个个人散户真正每天能用的投资决策系统；不过度收缩掉有价值的 Research/AI 能力，也不把产品膨胀成机构级资管平台。

---

# 0. 一句话产品定义

> **Personal Systematic Investing OS 是一个面向单个个人投资者的中低频投资决策系统：产品自带 10~20 个可解释、可验证的策略，并提供 AI Copilot 持续从论文、论坛、研报和 GitHub 中发现、实现和验证新策略；系统从中选择经过严格验证的策略组成 Production Strategy Pack，每天基于可信行情和用户真实持仓生成 BUY / SELL / HOLD / CASH / NO ACTION 指示，通过微信通知用户人工执行。**

AI Investor 是后续独立的 Shadow Research，不影响第一阶段产品可用性。

---

# 1. 这次范围纠偏

前几版出现过两个相反风险：

1. **过度收缩**：只做 1~2 个策略，会把产品做成一个单一策略 Demo，缺少研究和策略迭代能力。
2. **过度扩张**：把个人投资工具设计成机构级 Investment Platform，引入过多治理、权限、状态机和基础设施。

v0.7 采用中间路线：

```text
个人散户级产品
+
足够丰富的策略库
+
AI Copilot 研究能力
+
严格但不过度复杂的验证
+
简单可靠的每日生产链
```

不是：

```text
量化开发框架
```

也不是：

```text
基金公司级 OMS / 风控 / 研究平台
```

---

# 2. 第一阶段真正要解决的问题

系统每天只需要可靠回答几个问题：

```text
今天持有什么？
该买什么？
该卖什么？
目标仓位是多少？
没有足够优势时是否应该 HOLD / CASH / NO ACTION？
```

完整链路：

```text
Market Data
    +
Current Holdings
    +
Approved Strategy Pack
        ↓
Quant Decision
        ↓
TargetPortfolio
        ↓
ActionPlan
        ↓
ServerChan / 微信
        ↓
用户人工执行
        ↓
实际成交记录
        ↓
下一次决策
```

第一阶段成功的标准不是“架构多专业”，而是：

> **每天真的能稳定给出可信、可执行、可追踪的操作指示。**

---

# 3. 用户画像：先服务一个真实个人投资者

v1 只服务单用户、单主要投资账户/组合。

不做：

- 多租户；
- 多角色审批；
- 机构账户体系；
- 基金产品发行；
- 客户适当性系统；
- 复杂权限系统。

只需要一个简单的：

```text
InvestorProfile
```

例如：

```yaml
capital_reference: 100000 CNY
horizon: medium_long
target_return_reference: 10-15% CAGR
drawdown_preference: around 10% or lower
long_only: true
leverage: false
manual_execution: true
core_asset: ETF
satellite_asset: A-share stocks
```

“激进 / 平衡 / 保守”以后可以作为模板，但 **v1 不同时维护三套产品**。

---

# 4. 策略体系：10~20 个内置策略，但 Production 不同时跑 20 个

这是本版的重要澄清。

## 4.1 Strategy Library

产品第一阶段应自带约：

> **10~20 个策略实现**

它们构成：

```text
Built-in Strategy Library
```

目的不是让 20 个策略一起投票，而是：

- 提供足够丰富的候选；
- 覆盖不同经济逻辑；
- 允许比较、淘汰、组合；
- 给 AI Copilot 提供可学习和扩展的基线；
- 避免产品退化成单一策略 Demo。

## 4.2 Production Strategy Pack

真钱 Production 使用的不是全部策略，而是：

> **少量经过验证、互补的 Approved Strategies。**

例如最终可能只有：

```text
ETF Core Strategy Pack
├─ Trend / Absolute Momentum
├─ Relative Momentum / Rotation
├─ Defensive Allocation
└─ Risk / Volatility Control
```

所以：

```text
Strategy Library = 10~20 个候选
Production Pack  = 2~5 个经过验证并且互补的策略/策略组件
```

这是“策略丰富”和“生产简单可靠”之间的平衡。

---

# 5. 第一批内置策略的来源与方向

不要求发明全新 Alpha。

优先收集、实现和重新验证已有长期研究基础、逻辑清楚的策略思想。

候选策略族可以覆盖：

### 趋势 / Absolute Momentum

- 单均线趋势；
- 双均线趋势；
- 6M / 12M absolute momentum；
- 多周期 trend confirmation。

### Relative Momentum / Rotation

- 3M / 6M / 12M relative momentum；
- 多周期加权 momentum；
- Top-N ETF rotation；
- momentum + trend filter。

### Tactical Asset Allocation

- equity / gold / bond / cash rotation；
- dual momentum 类；
- diversified TAA 类；
- risk-on / defensive switching。

### Risk / Allocation

- volatility targeting；
- inverse-volatility allocation；
- 简化 risk parity；
- drawdown throttle；
- defensive cash/bond allocation。

具体进入 Library 的 10~20 个实现，在 M1 形成正式清单。

原则：

> 每个策略必须有明确来源、经济命题和可解释逻辑，而不是随机拼技术指标。

---

# 6. Strategy Sources：不只靠内置策略

系统长期允许四种策略来源：

```text
1. Built-in curated strategies
2. Papers / books / forums / reports / GitHub
3. User-written or user-proposed strategies
4. AI Copilot hypotheses
```

统一进入 Research：

```text
Source
  ↓
Hypothesis
  ↓
Strategy Spec
  ↓
Implementation
  ↓
Backtest
  ↓
Robustness / OOS / Walk-forward
  ↓
Paper
  ↓
Approved / Rejected
```

Production 不能直接运行刚生成的策略。

---

# 7. AI Copilot：不是后期功能，而是 M1 同期能力

AI Copilot 是这个产品非常有价值的一部分，应与 Strategy Library 同期建设，而不是等产品做完才加。

## 7.1 AI Copilot 可以做什么

沿用前面已经认可的范围：

- 阅读论文；
- 阅读论坛帖子；
- 阅读研报；
- 阅读 GitHub 策略代码与 README；
- 抽取投资命题；
- 形成 Strategy Spec；
- 生成研究代码；
- 调用回测；
- 比较参数；
- 做 robustness / OOS 分析；
- 分析失败原因；
- 解释 Quant 信号；
- 检查新闻、政策、行业风险；
- 寻找反例；
- 复盘错误决策；
- 提出新的研究假设。

典型工作流：

```text
AI Copilot
   ↓
发现一个策略思想
   ↓
记录来源与 Hypothesis
   ↓
生成 Strategy Spec
   ↓
写策略代码
   ↓
调用本系统 Backtest
   ↓
查看失败 / 成功证据
   ↓
形成 Research Report
   ↓
进入 Strategy Library 或 REJECTED
```

## 7.2 AI Copilot 不拥有真钱决策权

它可以：

```text
建议研究什么
```

不能：

```text
直接修改 Production Strategy Pack
```

所有进入 Production 的策略仍然必须经过验证和用户确认。

---

# 8. 保留“用户自己写策略”的口子

产品不能强迫用户写策略，但必须允许高级用户扩展。

提供一个简单稳定的：

```text
Strategy Protocol / Strategy SDK
```

用户可以：

1. 自己写 Python 策略；
2. 给 AI Copilot 一段自然语言描述，由 AI 帮助实现；
3. 导入第三方策略思想后重新实现。

示意：

```python
class Strategy:
    def generate_signal(context) -> Signal:
        ...
```

真正接口以 M0 Domain Contracts 为准。

用户策略与内置策略接受完全相同的 verifier。

---

# 9. Strategy Registry：保持简单但必须有

不需要机构级策略治理系统，但需要最基本的 Registry。

每个 Strategy Version 至少记录：

```text
strategy_id
version
source
economic_thesis
parameters
universe
code_digest
backtest_result
OOS_result
paper_result
status
```

状态可以先简化为：

```text
RESEARCH
PAPER
APPROVED
PAUSED
REJECTED
```

不需要第一版就设计十几个生命周期状态。

---

# 10. ETF Core 是第一条 Production 主线

第一阶段真钱决策聚焦：

> **ETF Core**

原因：

- 更适合个人中低频；
- 个股特有风险更低；
- Universe 小；
- 数据和执行更简单；
- 更容易建立可信 verifier；
- 更适合先做出每天真正可用的产品。

第一版可覆盖：

```text
宽基权益 ETF
+
黄金 ETF
+
债券 ETF
+
现金
```

具体 Universe 在 M1 决定，只选：

- 流动性好；
- 规模合理；
- 历史数据可靠；
- 经济暴露有差异；
- M0 数据资格验证通过的 ETF。

---

# 11. Strategy Pack：Production 到底每天跑什么

为了避免“仓库里有 20 个策略但不知道生产用哪个”，引入一个简单对象：

```text
StrategyPack
```

例如：

```yaml
name: etf_core_v1

universe:
  - equity_etf_A
  - equity_etf_B
  - gold_etf
  - bond_etf

strategies:
  - trend_v1
  - relative_momentum_v2
  - defensive_allocation_v1

rebalance: weekly

risk:
  max_equity_exposure: ...
  max_single_asset_weight: ...
  cash_floor: ...
```

Production 只运行：

```text
active StrategyPack
```

而不是扫描所有 Strategy Library。

修改 StrategyPack 会生成新版本并重新验证。

---

# 12. 多策略组合：第一版保持可解释

第一版不做复杂 Ensemble / ML Meta Model。

优先采用：

```text
Trend eligibility
      ↓
Relative Momentum selection
      ↓
Allocation / Risk scaling
      ↓
TargetPortfolio
```

或者非常简单的 risk-budget 组合。

关键要求：

- 每一步能解释；
- 每个策略贡献能追踪；
- 不看结果以后再临时改权重；
- 不用十几个高度相关技术指标投票。

---

# 13. 验证：严格，但不要做成学术实验平台

核心事实仍然不变：

> Backtest 不是 pytest。

但第一版也不需要几十种统计检验。

策略进入 Production 前至少过：

```text
Backtest
  ↓
Parameter robustness
  ↓
Out-of-sample
  ↓
Walk-forward
  ↓
Realistic costs
  ↓
Paper forward
```

至少检查：

- CAGR；
- MDD；
- Sharpe / Calmar 等辅助指标；
- turnover；
- underwater duration；
- benchmark comparison；
- 参数附近是否立即崩掉；
- 是否依赖少数几笔交易；
- 是否有明显未来函数 / survivorship / data leakage；
- 真实交易费用后是否仍成立。

保持一个 final holdout，查看以后再修改策略就视为污染。

---

# 14. 不为目标收益强行调参

现有目标：

```text
长期 CAGR 约 10%~15%
希望 MDD <= 10%
```

作为：

> **Product Objective / Release Reference**

不是优化器的硬目标函数。

如果：

```text
Strategy A
CAGR 9.5%
MDD 7%
结构简单
OOS 稳定
```

而另一个：

```text
Strategy B
CAGR 15%
MDD 9%
参数非常多
OOS 不稳定
```

第一版更可能选择 A。

优先级：

```text
可解释
→ 无数据作弊
→ OOS 存活
→ 风险可接受
→ 能真实执行
→ 再看收益
```

---

# 15. 每日生产链保持简单

## 收盘后

```text
更新数据
  ↓
Data Quality Gate
  ↓
active StrategyPack
  ↓
计算信号
  ↓
Portfolio / Risk
  ↓
TargetPortfolio
  ↓
保存 Decision
```

## 次日开盘前

```text
读取昨天 Target
+
当前实际持仓
+
交易日 / 停牌 / 公司行动等必要检查
  ↓
ActionPlan
  ↓
ServerChan 微信通知
```

## 用户执行后

用户只需记录：

```text
成交代码
买卖方向
成交数量
成交价
费用（可选自动计算/修正）
```

系统更新真实持仓。

不接券商自动交易是 v1 的明确边界。

---

# 16. 正式通知只来自 Quant Production

这一点保持不变：

```text
Quant Production
    ↓
正式 BUY / SELL / HOLD / CASH / NO ACTION
```

AI Copilot 可以解释：

```text
为什么这个策略产生这个信号
```

但 AI 生成文字不构成第二套交易权威。

通知应尽量简单：

```text
2026-xx-xx 明日操作

BUY  510xxx  1000 股
SELL 159xxx   500 股
HOLD 518xxx
预计现金 18,200 元

StrategyPack: etf_core_v1
Decision ID: ...
```

---

# 17. 真实账户处理：个人版只做必要能力

不做复杂 OMS。

只需要：

```text
PortfolioSnapshot
```

包含：

- 现金；
- 持仓；
- 可卖数量；
- 成本可选；
- 最近一次对账时间。

出现：

- 用户成交；
- 用户自己额外买卖；
- 存取款；

用户做一次简单 reconciliation 即可。

Plan 不等于 Fill。

系统绝不能因为发过 BUY 通知就假设用户已经买入。

---

# 18. Decision Outcome：保留，因为它直接提高产品价值

策略上线以后，系统应该知道过去指令后来怎样。

保留：

```text
DecisionEpisode
ForwardEvaluation
StrategyHealth
```

但 v1 简化。

例如：

```text
Decision
2026-10-01
BUY 510xxx

20D:
+4.2%

60D:
+8.0%

Benchmark:
+3.1%

Result:
GOOD
```

Strategy Health 第一版只需要：

```text
ACTIVE
WATCH
PAUSED
```

不用一开始构建复杂企业级风险生命周期。

这套数据以后同时服务：

- Quant Strategy 复盘；
- AI Copilot；
- AI Investor 长期记忆。

---

# 19. AI Investor：明确后置，但长期保留

AI Investor 仍然是一个值得长期验证的方向：

> **强基础模型 + 私有投资记忆 + 真实市场反馈 + verifier**

但它不是 M1~M3 的 Production 阻塞项。

未来：

```text
Same Market Data
      ├──────── Quant Production
      │
      └──────── AI Investor Shadow
                    ↓
              Shadow Portfolio
```

AI Investor：

- 独立模拟账户；
- 独立完整投资判断；
- 私有长期记忆；
- 不进入正式微信交易通知；
- 不影响 Quant target。

只有长期明确证据证明：

```text
AI Investor > Quant
```

才另做 Architecture Decision。

---

# 20. 技术架构：够用即可

继续采用：

> **Python modular monolith + ports/adapters**

M0 已经确定的金融正确性和数据边界保持不变。

第一阶段优先：

```text
Python
SQLite / DuckDB
Parquet
CLI / minimal Web UI
ServerChan
```

不因为“未来可能需要”提前引入：

- Kubernetes；
- Kafka；
- Redis 集群；
- 微服务；
- 分布式 Agent 平台；
- 多租户 IAM；
- 机构级审批流。

---

# 21. Data：继续复用 chstockdata

保持现有边界：

```text
chstockdata
    ↓
Provider Adapter
    ↓
Canonical Investing Domain
```

chstockdata 负责：

- 数据获取；
- provider fallback；
- 底层数据源细节。

Investing OS 负责：

- Canonical contracts；
- data quality；
- point-in-time correctness；
- 策略；
- backtest；
- portfolio；
- production decision。

Production 不依赖 MCP 调数据。

---

# 22. AI 接入方式

继续使用：

```text
AIModelPort
```

允许：

- Metered API；
- 官方允许的 Subscription programmatic access；
- Local Model。

不绑定某一家模型。

ChatGPT Plus / Coding Plan 如果供应商不允许通用程序化调用，则只用于交互式 Research/Coding，不用非官方方式模拟网页接口。

AI Copilot 的 provider 可以随时替换，而 Strategy / Backtest / Production Domain 不受影响。

---

# 23. Revised Roadmap

## M0 — Foundation（正在实施，完全不动）

交付：

- Domain contracts；
- provider-neutral data；
- M0 ETF qualification；
- daily-bar backtest；
- portfolio/risk kernel；
- metrics；
- golden/parity tests；
- reproducibility。

**不加入策略、AI、通知、UI。**

---

## M1 — Strategy Library + AI Copilot Research

目标：

> **让系统拥有真正的投资研究能力，而不是只有一个空回测框架。**

交付：

- 10~20 个 Built-in Strategy candidates；
- Strategy Registry；
- Strategy Protocol；
- 用户自定义策略入口；
- AI Copilot；
- Source → Hypothesis → Strategy Spec 流程；
- AI-assisted strategy implementation；
- 自动调用 Backtest；
- Research Reports；
- ETF Core Universe 候选；
- 第一轮策略筛选。

M1 不要求这 10~20 个全部通过。

失败策略必须保留为 evidence，而不是删除历史。

---

## M2 — ETF Core Strategy Pack + Validation

目标：

> **从 Strategy Library 中选出真正值得 Production 使用的少量策略。**

交付：

- ETF Core Universe v1；
- 2~5 个互补 Approved Strategy / Component；
- active `StrategyPack: etf_core_v1`；
- parameter robustness；
- OOS；
- walk-forward；
- realistic cost/slippage；
- benchmark；
- final holdout；
- Paper Forward；
- Strategy Pack 整体验证。

如果没有候选通过：

```text
不发布真钱 StrategyPack
```

继续 Research。

---

## M3 — Daily Investment Product

目标：

> **形成真正每天能用的个人投资系统。**

交付：

- EOD daily run；
- Pre-open ActionPlan；
- TargetPortfolio；
- ServerChan 微信通知；
- 当前持仓维护；
- 手工成交录入 / reconciliation；
- BUY / SELL / HOLD / CASH / NO ACTION；
- basic reporting；
- DecisionOutcome；
- ACTIVE / WATCH / PAUSED strategy health；
- backup / simple failure recovery；
- minimal CLI / Web UI。

到 M3，产品第一阶段即成功。

---

## M4 — Stock Satellite + Strategy Library Expansion

增加：

- A 股高流动性 Universe；
- Trend / Breakout；
- Momentum；
- Quality / Liquidity；
- Stock Satellite 风险上限；
- 更多 AI Copilot 收集策略。

ETF Core 仍是组合基础。

---

## M5 — AI Investor Shadow

增加：

- AIAdvisorVersion；
- private long-term investment memory；
- Ground Truth + Cognitive Memory；
- AI Shadow Account；
- Quant vs AI 对照；
- no-memory vs memory 对照；
- learning curve；
- Forward verifier。

仍然不进入 Production。

---

# 24. M1 最关键的实际工作

M0 完成后，不要继续做基础设施。

立刻转到：

```text
1. 定 ETF Universe
2. 收集 20~30 个高质量候选策略思想
3. 筛成第一批 10~20 个 Built-in Strategy
4. AI Copilot 辅助逐个实现
5. 用统一 Backtest Kernel 跑
6. 记录失败和成功
7. 做 OOS / robustness
8. 从中选择互补策略
9. 形成 ETF Core StrategyPack
10. Paper Forward
```

这才是项目最核心的价值创造阶段。

---

# 25. 什么暂时不做

除非未来需求明确，否则第一阶段不做：

- 自动券商下单；
- 高频 / 日内；
- 衍生品；
- 做空 / 杠杆；
- 多用户 SaaS；
- 策略市场；
- 社交；
- 机构多账户；
- 多级审批；
- 复杂合规系统；
- 分布式计算平台；
- AI 自动修改 Production 策略；
- AI Investor 真钱决策；
- 100 个策略大仓库；
- 黑盒深度学习预测股价。

---

# 26. 开发判断规则

以后任何新功能先问：

> **它是否直接改善下面至少一项？**

```text
策略质量
数据可信度
回测可信度
风险控制
每日决策质量
执行可用性
复盘学习能力
```

如果都不是，默认后置。

同时，不用“能不能没有它就运行”作为唯一标准，因为这样会过度收缩 AI Copilot、Strategy Library 这类长期价值很高的能力。

更准确的原则：

> **第一阶段可以做“明显提升投资决策质量”的能力，但不做“只提升架构完整性”的能力。**

---

# 27. 核心不变量

后续开发 Agent 必须遵守：

1. **M0 已批准并正在实施，不改变 M0 scope。**
2. **目标是个人投资决策产品，不是机构平台。**
3. **产品自带 10~20 个策略候选，不要求用户自己写策略。**
4. **用户仍然可以自定义策略。**
5. **AI Copilot 与 Strategy Library 同期建设。**
6. **Strategy Library 丰富，但 Production Strategy Pack 保持少量、互补、可解释。**
7. **Production 只运行经过验证和用户确认的 StrategyPack。**
8. **TargetPortfolio 是正式决策对象。**
9. **正式交易通知只来自 Quant Production。**
10. **AI Copilot 可以研究和解释，但不能直接写 Production Target。**
11. **AI Investor 后置为独立 Shadow Research。**
12. **Backtest / OOS / Walk-forward / Paper 是策略进入 Production 的基本验证链。**
13. **失败策略保留，不删除负面 evidence。**
14. **不为了 10~15% CAGR 目标过度调参。**
15. **Plan 不等于 Fill，真实持仓必须以人工成交/对账为准。**
16. **系统可以复杂到足以提升投资决策，但不能复杂到变成机构级平台。**

---

# 28. 最终产品形态

第一阶段最终应是这样的：

```text
                    ┌─────────────────────┐
                    │   Strategy Library   │
                    │   10~20 built-ins    │
                    └──────────┬──────────┘
                               │
 Papers / Forums / GitHub ── AI Copilot
                               │
 User Strategy ────────────────┤
                               ↓
                       Research / Backtest
                               ↓
                      Approved Strategies
                               ↓
                        ETF Core StrategyPack
                               ↓
                    ┌──────────┴───────────┐
                    │                      │
               Market Data          Current Holdings
                    │                      │
                    └──────────┬───────────┘
                               ↓
                         TargetPortfolio
                               ↓
                          ActionPlan
                               ↓
                       ServerChan / 微信
                               ↓
                          用户人工执行
                               ↓
                          Reconciliation
                               ↓
                      Decision Outcome
                               ↓
                         AI Copilot 复盘
```

未来再平行增加：

```text
AI Investor Shadow
        ↓
Private Memory
        ↓
Forward Verifier
```

但不干扰 Quant Production。

---

# 29. 本版希望人工重点审查的 8 个问题

为了避免文档继续无限扩张，本版只建议你重点审查下面 8 点：

1. **10~20 个 Built-in Strategy 的数量是否合适？**
2. **Production Pack 只选 2~5 个互补策略是否合理？**
3. **AI Copilot 是否应从 M1 开始，与策略库同步建设？**
4. **第一阶段是否继续只以 ETF Core 为真钱主线？**
5. **用户自定义 Strategy Protocol 是否作为 M1 必备能力？**
6. **M2 的验证强度是否足够，但没有过度学术化？**
7. **M3 是否已经足以构成一个真正每天可用的个人投资产品？**
8. **哪些现有 v0.6 设计你认为应该恢复，而本版收缩过头？**

---

# 30. Final Decision

v0.7 的平衡点是：

> **策略库要丰富，Production 要克制；AI Copilot 要早做，AI Investor 要后做；验证要严格，治理不要机构化；架构要支持长期演进，但第一阶段必须让个人投资者每天真正用起来。**

这应成为后续 `personal-systematic-investing-os` 开发的最高层方向。
