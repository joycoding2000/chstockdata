# Personal Systematic Investing OS
## 从 0 开始的个人系统化投资决策系统：产品定位、架构、研究方法与 Codex 实施蓝图

> **版本**：v0.3 Final Architecture Decision（Decision Outcome & Controlled Learning Loop）  
> **日期**：2026-09-15
>
> **状态**：M0 Architecture Design Gate 已通过，可按已批准的 `M0-implementation-plan.md` 进入 M0 TDD 实施；本版新增 Decision Outcome & Controlled Learning Loop，总体边界不改变 M0 scope。  
> **用途**：作为新项目从 0 开始建设时的总纲，供 Codex / Claude Code / 其他开发 Agent 使用。  
> **重要约束**：不在现有 TradingAgents / Vibe-Trading / Vibe-Research 等项目上继续迭代；新建独立仓库。外部开源项目只允许经过审查后选择性集成、重写或 cherry-pick 小模块。

---

# 0. Executive Summary

本项目不做“AI 投资大师”，不让 LLM 凭叙事直接决定买卖。

项目定位：

> **Personal Systematic Investing OS / 个人系统化投资决策系统**

系统每天真正回答四个问题：

1. **今天有没有值得行动的机会？**
2. **如果有，买什么 / 卖什么 / 继续持有什么？**
3. **各资产目标仓位是多少？**
4. **如果证据不足或风险过高，明确输出 `NO ACTION / CASH`。**

最终用户看到的输出应接近：

```text
日期：2026-09-14
组合状态：Moderate Risk-On

BUY   510300   目标仓位 25%
HOLD  518880   目标仓位 15%
SELL  159915   目标仓位 0%
CASH           目标仓位 35%

Stock Satellite：
NO NEW SIGNAL

原因：
- ETF Trend Core v1.2
- Relative Momentum v1.1
- Portfolio Risk v1.0
- Evidence Gate: PASS
```

**不追求自动下单。**

第一阶段只要求：

> **可靠地产生、记录、解释并推送交易信号。**

系统长期运行后还必须回答第五个问题：

> **过去这些决策后来到底表现得怎样？哪些决策创造了价值，哪些决策造成了损失，哪些只是事后噪声？**

因此本项目还包含一条受控学习闭环：

```text
Production Decision
    ↓
Decision Episode
    ↓
Forward Evaluation
    ↓
Counterfactual / Attribution
    ↓
Strategy Health
    ↓
Research Proposal
    ↓
New Strategy Version
    ↓
Validation / Paper / Owner Approval
    ↓
Production
```

注意：**系统可以自动评估自己，但不能自动修改 Production 策略、参数或仓位规则。**

实盘执行由人完成；以后是否接 QMT / PTrade / vn.py，仅作为可选扩展，不属于核心目标。

---

# 0.1 Final Architecture Decisions（已裁决）

以下内容不再作为开放问题，后续 Codex 应按此执行。

1. **产品范围**
   - 正式支持 `ETF Core + Stock Satellite`。
   - ETF Core 与 Stock Satellite 都属于目标产品，而非“先做 ETF、以后再决定是否做股票”。
   - 工程实施仍按基础设施依赖顺序推进：`Quant Kernel → ETF Core → Evidence/Paper → Stock Satellite`。

2. **运行节奏**
   - `EOD Decision Run`：每天收盘数据完整后运行，生成**下一交易日 Target Portfolio**。
   - `Pre-open Execution Confirmation Run`：每天开盘前运行，加载昨晚已锁定的 Target Portfolio，完成持仓对账、数据/交易日/可交易性/风险检查，生成**当日 Action Plan**。
   - Pre-open v1 **不重新计算基础 Alpha**，避免同一套日线策略在没有新 bar 的情况下产生相互冲突的信号。
   - 后续如增加隔夜市场、公告、政策、集合竞价等信息，必须通过单独版本化的 `Overnight Risk Overlay` 接入。

3. **核心投资对象**
   - 系统核心不是 `BUY / SELL`，而是 `Target Portfolio`。
   - `BUY / SELL / HOLD / CASH / NO ACTION` 只是“当前组合”与“目标组合”之间差值的执行表达。
   - 必须同时保留：
     - theoretical target weight
     - executable target weight
     - current weight
     - target amount
     - executable quantity
     - residual cash

4. **初始资金**
   - Backtest / Paper 默认初始资金：**100,000 RMB**。
   - 所有研究必须真实考虑整手、最低佣金、剩余现金、仓位离散化和多信号资金竞争。

5. **数据路线**
   - 首批主数据层确定为独立仓库 **`joycoding2000/chstockdata`**，作为本项目的第一数据 Provider。
   - 本项目不再重复实现 Tencent / TDX / mootdx / Sina / Eastmoney / SSE/SZSE 等免费数据源抓取、降级、限流、PIT 过滤和本地 vipdoc 历史层。
   - 不把付费 Tushare 作为项目依赖。
   - `systematic-investing-os` 仍保持 Provider-neutral：核心只依赖 `DataProviderPort`，首个实现为 `ChStockDataProvider`。
   - Production Quant Runtime **直接调用 Python package API**，不通过 MCP；MCP 只可作为未来 AI / Research 工具入口。
   - `chstockdata` 的 v1 原始返回契约不得泄漏进入 Quant Domain。Adapter 必须转换为本项目自己的 canonical contracts。
   - 至少保留一个**独立于 chstockdata 的校验来源**做 Golden / 抽样校验；chstockdata 内部多 vendor fallback 属于 Provider 内部冗余，不能替代独立校验。
   - Production 主源异常、数据过期、关键字段不一致或 ETF 资格验证失败时，Data Quality Gate 必须阻止新交易信号。
   - ETF Core 是正式产品范围，因此 M0 必须单独完成 `chstockdata` 对目标 ETF 的数据能力资格测试；在资格测试通过前，不默认“A股股票数据能力 = ETF 数据能力”。

6. **通知**
   - 第一通知渠道确定为**个人微信**。
   - 首版采用 **Server酱 / ServerChan** 方式实现。
   - 这是一个“个人系统 → 通知服务 → 自己的微信”的单用户通知链路，**不复制 JoinQuant 的公众号账号绑定模式**。
   - 本项目不自建公众号体系，不实现微信 OAuth、用户 OpenID 绑定、模板消息用户管理等平台型能力。
   - 核心定义统一 `NotificationPort`，ServerChan 只是首个 Adapter，未来可替换为企业微信、邮件、Bark 等。
   - 不采用个人微信模拟登录、客户端 Hook、逆向协议等高风险方案。
   - 正常情况下每天仅发送两类主通知：
     1. `Pre-open Action Plan`：开盘前的当日执行确认；
     2. `EOD Decision Summary`：收盘后的下一交易日目标组合摘要。
   - 只有真正异常时额外发送 `DATA ERROR`、`RISK KILL SWITCH`、`STRATEGY SUSPENDED` 等告警。
   - 通知必须具备幂等、去重、失败重试和可审计能力，不能因为重跑任务重复发送相同交易指令。
   - ServerChan 的 SendKey 只能通过环境变量或本地 Secret Store 注入，禁止写入 Git、配置样例或普通日志。

7. **自动交易**
   - 当前产品**不追求自动下单**。
   - Production 目标是：
     `Target Portfolio → Action Plan → 微信推送 → 人工执行 → Actual Fill Reconciliation`。
   - 未来如接 QMT / PTrade / vn.py，只作为可选 Execution Adapter，不改变策略与组合核心。

8. **受控自我迭代 / Decision Outcome Learning Loop**
   - 系统必须能够对历史 Production / Paper 决策做**事后 Forward Evaluation**，但不得把“自我学习”解释为运行时自动调参。
   - 决策评价的最小单位不是“每天的 BUY/SELL/HOLD 文本”，而是发生实质目标变化的 `DecisionEpisode`。
   - 每个 Episode 在决策发生时必须记录预先声明的 `primary_evaluation_horizon`，禁止事后挑选最有利的评价窗口。
   - 系统自动生成 `ForwardEvaluation`，至少支持 5D / 20D / 60D 与策略主评价周期，并记录 return、benchmark/excess、MAE、MFE、risk outcome 等。
   - 评价不能只看“买后涨没涨”，应至少区分：
     - Direction
     - Alpha / Counterfactual Value Add
     - Risk / Drawdown Avoidance
     - Execution Drag
   - 决策结果允许输出 `GOOD / MIXED / BAD / INCONCLUSIVE`，但 verdict 必须来自版本化的 deterministic evaluation policy，而不是 LLM 自由判断。
   - `StrategyHealthSnapshot` 基于一段时间的 Forward Evidence 更新 `HEALTHY / WATCH / DEGRADED / SUSPENDED / RETIRED` 状态。
   - AI 可以基于失败模式提出新 Hypothesis / Strategy vNext，但任何新版本仍必须重新经过 Backtest → OOS → Walk-forward → Paper Forward → Owner Approval，禁止 AI 直接写回 Production。


# 1. 已经确定的产品裁决

以下方向已经达成一致，应视为本项目的基础约束。

## 1.1 AI 是副驾驶，不是基础信号源

AI 可以：

- 阅读论文 / 论坛帖子 / 研报 / GitHub 策略
- 抽取投资命题
- 生成 Strategy Spec
- 写研究代码
- 调用回测
- 分析失败
- 解释量化信号
- 检查新闻、政策、产业风险
- 寻找反例
- 复盘错误决策
- 读取 deterministic Forward Evaluation / Counterfactual 结果并归因
- 聚类长期失败模式与 regime 失配
- 提出新的研究假设

AI 不可以：

```text
LLM：“我觉得新能源今天不错”
          ↓
         BUY
```

Production 中的基础交易信号必须来自：

> **确定性程序 + 已批准策略 + 风险规则 + 可追踪 Evidence**

---

## 1.2 资产路线：ETF Core + Stock Satellite

### ETF Core

负责：

- 基础收益
- 大类风险暴露
- 趋势跟随
- 相对动量
- 风险预算
- 回撤控制
- 现金 / 防御仓位切换

### Stock Satellite

负责：

- 在风险环境允许时寻找额外 Alpha
- 高流动性股票优先
- 中低频 / 中长线
- 总风险预算受 ETF Core / Portfolio Risk 控制

系统应允许：

```text
Risk-Off:
Stock Satellite = 0%

Neutral:
Stock Satellite <= 10%~20%

Risk-On:
Stock Satellite 可逐步提高，但仍受组合风险上限约束
```

---

## 1.3 收益与风险目标

长期研究目标：

```text
目标年化收益：10% ~ 15%
希望最大回撤：<= 10%
```

**这两个数字是 Release Gate / Portfolio Objective，不是回测调参目标。**

禁止：

```text
让 Agent 一直调参数
直到 CAGR > 12% && MDD < 10%
```

否则极易历史过拟合。

---

## 1.4 中长线优先

本项目不和机构竞争：

- 高频
- 毫秒级延迟
- Level-2 微结构
- 算力套利
- 高频盘口
- 超低延迟执行

主要研究周期：

> **数周 ~ 数月**

每日数据可以用于信号确认，但不是日内交易系统。

---

## 1.5 实盘路线

```text
Backtest
   ↓
Robustness
   ↓
Walk-forward
   ↓
Final Holdout
   ↓
Paper Forward
   ↓
Small Capital Canary
   ↓
Scale
```

当前项目不追求自动交易，只追求：

> **信号推送 + 人工执行 + 事后对账与验证**

---

# 2. 为什么不能继续做“多 Agent 投资委员会”

原 TradingAgents 一类架构：

```text
行情 / 基本面 / 新闻
       ↓
   多个 Analyst
       ↓
    Bull / Bear
       ↓
      RM / PM
       ↓
 BUY / HOLD / SELL
```

最大问题不是软件工程，而是：

> **增加角色不等于增加信息。**

多个模型围绕同一批输入反复讨论，可能减少遗漏，但不会凭空制造 Alpha。

真正新增信息的是：

- 新数据
- 新统计证据
- 新历史样本
- 新回测结果
- 新 Regime 信息
- 新前向验证结果

因此本项目的主决策链必须：

```text
Data
 ↓
Strategy
 ↓
Evidence
 ↓
Portfolio / Risk
 ↓
Action
```

LLM 放在外围做：

> Research / Challenge / Explanation

---

# 3. 总体架构

系统分成两个严格隔离的世界：

## 3.1 Research Plane

允许大量实验：

```text
JoinQuant / GitHub / Papers / Books / Reports
                      ↓
               Research Knowledge
                      ↓
               AI Hypothesis Miner
                      ↓
              Hypothesis Registry
                      ↓
                Strategy Spec
                      ↓
                  Code / DSL
                      ↓
             Research Backtest
                      ↓
     Robustness / OOS / Walk-forward
                      ↓
                Paper Forward
                      ↓
                Strategy Gate
                      ↓
               APPROVED / REJECTED
```

## 3.2 Production Plane

必须极其保守：

```text
                  Market Data
                      ↓
               Data Quality Gate
                      ↓
              Approved Strategies
                      ↓
                Signal Engine
                      ↓
              Portfolio Engine
                      ↓
                 Risk Engine
                      ↓
               Target Portfolio
                      ↓
        BUY / SELL / HOLD / NO ACTION
                      ↓
                  Notification
                      ↓
               Manual Execution
                      ↓
               Reconciliation
                      ↓
               Decision Episode
                      ↓
              Forward Evaluation
                      ↓
      Counterfactual / Attribution
                      ↓
            Strategy Health Snapshot
                      ↓
          Research Feedback Proposal
```

---

# 4. 新增的关键原则：Research 与 Production 绝对隔离

这是本轮复盘后需要明确补充的制度。

Research 环境允许：

- 快速写新策略
- 参数探索
- 新数据
- 新指标
- AI 自动生成代码
- 临时实验

Production 环境只允许：

- 已批准 Strategy Version
- 已批准 Data Contract
- 已批准 Portfolio Rule
- 已批准 Risk Rule

任何策略升级必须：

```text
New Hypothesis
    ↓
New Strategy Version
    ↓
Backtest
    ↓
Robustness
    ↓
OOS
    ↓
Paper
    ↓
Approval
    ↓
Production
```

禁止 AI 运行时修改 Production 参数。

另外，Production Outcome 可以**单向回流**到 Research：

```text
Immutable Production Decision / Fill / Outcome
                ↓
        Read-only Evidence Export
                ↓
              Research
```

Research 可以基于这些证据提出新版本，但不能反向直接修改 Production。

---

# 5. Research Knowledge Plane：如何利用 JoinQuant 大神帖子和外部经验

这是本项目区别于传统量化框架的重要能力。

## 5.1 不做“大 V 人格模仿”

错误路径：

```text
1000篇帖子
  ↓
RAG
  ↓
“请告诉我今天买什么”
```

得到的仍然是：

> 语言模型生成的投资叙事。

正确路径：

```text
帖子 / 论文 / 策略说明
        ↓
Claim Extraction
        ↓
Hypothesis
        ↓
Strategy Spec
        ↓
Backtest / Evidence
```

---

## 5.2 Investment Knowledge Ledger

每条有价值的人类经验都存成结构化记录。

示例：

```yaml
source_id: JQ-2023-0182

source:
  author: xxx
  platform: JoinQuant
  published_at: 2023-06-18
  url: xxx
  type: forum_post

claim:
  raw: >
    小盘强势环境中，创20日新高且成交量放大的股票，
    后面通常还有趋势。

  normalized: >
    small_cap + 20d_breakout + volume_expansion
    predicts positive forward return

universe:
  market: A-share
  cap: small

horizon:
  expected: 10-30d

conditions:
  - small_cap_relative_strength_positive
  - market_risk_on

entry:
  - close >= high_20d
  - volume_5d / volume_20d > threshold

exit:
  - close < ma20
  - holding_days >= 20

unknowns:
  - small_cap 的定义
  - volume threshold 未定义
  - 是否排除 ST 未说明

falsifiable: true
```

核心原则：

> AI 不得擅自填补作者没有说明的关键条件。

模糊项必须显式记录为：

```text
UNKNOWN
```

---

## 5.3 人类经验分三类

### A. 可量化命题

例如：

> 放量突破后具有趋势延续。

进入：

```text
Strategy Hypothesis → Backtest
```

### B. 市场环境经验

例如：

> 缩量熊市不要做小盘突破。

进入：

```text
Regime Rule / Risk Rule Hypothesis
```

### C. 难量化判断

例如：

> 某产业政策发生结构改变。

进入：

```text
AI Risk Review
```

不要强行把所有经验变成策略。

---

# 6. Hypothesis Registry

长期最有价值的资产之一不是“策略代码数量”，而是：

> **我们研究过哪些命题，它们为什么成功或失败。**

生命周期：

```text
IDEA
 ↓
SPECIFIED
 ↓
BACKTESTED
 ↓
ROBUSTNESS_PASS
 ↓
OOS_PASS
 ↓
PAPER
 ↓
APPROVED
 ↓
PRODUCTION
 ↓
DEGRADED
 ↓
RETIRED
```

示例：

| ID | Hypothesis | 来源 | 状态 | 主要结论 |
|---|---|---|---|---|
| H001 | 小盘突破 | JoinQuant A | REJECTED | OOS失效 |
| H002 | ETF绝对动量 | 论文 | PAPER | 稳定 |
| H003 | 放量新高 | JoinQuant B | VALIDATING | 参数稳定 |
| H004 | RSI超卖 | GitHub | REJECTED | 成本后无Alpha |
| H005 | Risk-off 降仓 | 经典资产配置 | APPROVED | Core |

---

# 7. 一个非常重要的新增字段：Knowledge Available Date

如果某策略在 2024 年公开：

```text
2010~2023 回测表现很好
```

这只能证明：

> 这个规律历史上存在过。

真正更有价值的证据是：

> **2024 年发布之后的 Forward Performance。**

所以所有外部知识必须保存：

```yaml
published_at: 2024-03-22
knowledge_available_at: 2024-03-22
```

并将：

```text
post-publication forward performance
```

作为单独 Evidence。

---

# 8. Source Quality：大神不是 Ground Truth

来源的“权威性”只影响：

> **研究优先级**

不能直接影响：

> **策略是否获批。**

建议来源质量分级：

### A

- 长期公开记录
- 有失败记录
- 时间点可核查
- 条件明确
- 观点有持续演进

### B

- 长期作者
- 逻辑清楚
- Track Record 不完整

### C

- 热门帖子
- 收益截图
- 单次案例

### D

- 事后神预测
- 无明确规则
- 不能证伪

A 类优先测试。

---

# 9. 版权与数据授权：之前讨论中遗漏的重要问题

这是必须补入设计的内容。

## 9.1 JoinQuant / 论坛文章

允许本地研究时，应优先保存：

- URL
- 作者
- 时间
- 自己的摘要
- Claim
- Hypothesis
- 必要短摘录

不应默认：

> 批量复制、公开再分发完整文章。

如果未来商业化：

> 不应把别人帖子全文直接作为产品内容重新售卖。

---

## 9.2 付费策略代码

如果代码需要积分 / 付费获得：

- 正常购买
- 遵守平台授权
- 不绕过访问限制
- 不重新分发

可以从中提取：

> 策略思想

但能否复制源码必须看授权。

---

## 9.3 行情数据

如果未来商业化：

> 数据“能调用”不等于“可以重新分发”。

架构上应：

```text
Data Provider Adapter
```

与产品逻辑解耦。

避免把商业数据强绑定进产品。

---

# 10. Quant Kernel：为什么从 0 自建，但只做很窄

不重新造 Backtrader / Qlib / vn.py。

只自建：

> **A 股 / ETF + Daily Bar + 中低频 Quant Kernel**

原因：

1. 回测正确性是核心 IP。
2. 规模足够小，可真正理解每一笔成交。
3. 可以用多方结果验证。
4. 不受 GPL / 非商业许可约束。
5. 以后更容易商业化。

---

# 11. Backtest Kernel v1 Scope

必须支持：

## 11.1 时间语义

```text
T 收盘数据 finalized
   ↓
T 计算信号 / TargetPortfolio
   ↓
使用 T_CLOSE 计算 planned quantity
   ↓
T+1 activation
   ↓
NEXT_SESSION_OPEN + side-aware slippage + tick rounding 成交
```

信号、Sizing 与 Fill 严格分离。

- `sizing_reference_price = T_CLOSE`；
- `fill_price_model = NEXT_SESSION_OPEN`；
- T+1 gap 只能改变 executable/submitted quantity，不能反向修改 T 时刻 theoretical target；
- 多个同时 BUY 的 T+1 affordability 必须进行**全局确定性计算**，按已批准 sleeve/risk budget → target deficit → InstrumentId 顺序分配，并计入 slippage-adjusted price 与费用；
- 如果在 T-close 决策与 T+1 activation 之间发生拆股、合股、送股等数量变化型 corporate action，M0 使用 `CORPORATE_ACTION_REPLAN_REQUIRED` 使受影响 pending execution fail closed，不自动重缩放订单。

---

## 11.2 A 股 / ETF 基础规则

至少：

- A股 T+1
- ETF 交易规则按具体类别区分
- 涨跌停
- 停牌
- ST
- IPO / 新上市过滤
- 100 股整手
- 现金不足
- 交易费用
- 印花税
- ETF 与股票费用差异
- 滑点
- 分红
- 拆并股 / 复权
- Order reject
- 无法成交
- NAV
- Benchmark

---

## 11.3 禁止未来函数

必须有自动检查和 Golden Test 覆盖：

- `shift(-1)`
- 当日未来价格
- 后复权误用
- 未来财务数据
- Survivorship Bias
- 当天收盘信号当天成交
- 全样本 percentile 回看历史

---

# 12. 为什么 RQAlpha / JoinQuant 是“验证参照”，不是产品依赖

我们自己的 Kernel 必须用：

```text
人工手算
+
JoinQuant
+
RQAlpha（在许可允许的研究环境）
+
其他可信引擎
```

建立 Golden Parity Cases。

目标不是所有小数完全一致，而是：

> 每个差异都有可解释原因。

特别是：

- 成交时点
- 费用
- ETF 类型
- 滑点
- 复权
- 停牌
- 涨跌停
- 分红

---

# 13. Strategy Philosophy

第一代策略数量必须少。

不是：

```text
33因子
14策略
450 Alpha
```

而是：

> **少量能一句话说清楚、经济意义明确、容易证伪的策略。**

---

# 14. ETF Core v1

建议仅研究三类核心机制：

## 14.1 Absolute Trend

回答：

> 当前这个资产值得持有吗？

示例候选：

- Price > MA200
- MA20 > MA200
- 6/12M Absolute Momentum

---

## 14.2 Relative Momentum

回答：

> 多个可投资资产里，目前谁更强？

例如：

```text
沪深300
中证500
中证1000
创业板
红利
黄金
债券
```

按照中长期 Relative Strength 排序。

---

## 14.3 Risk / Defensive

回答：

> 应该承担多少风险？

输入可包括：

- Trend
- Volatility
- Breadth
- Liquidity
- Drawdown State

输出：

```text
Risk-On
Neutral
Risk-Off
```

最终影响：

> 权益总风险预算

---

# 15. Stock Satellite v1

不要第一阶段就扫描所有复杂策略。

建议最初只有 3~5 个族：

- Trend
- Breakout
- Momentum
- Quality / Fundamental Filter
- Liquidity / Risk Filter

技术形态、筹码、K线：

> 暂时作为 Feature / Confirmation

而不是直接变成正式独立策略。

---

# 16. Signal Evidence Card

生产系统每个交易信号应附带确定性 Evidence。

示例：

```text
Strategy: Trend Breakout v1.3
Symbol: XXXX

Today
────────────────────
Price > 60d high
20d momentum: Top 8%
Volume: 1.42x
Market regime: Risk-On

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
Period: 2022-2026
CAGR: ...
MDD: ...
Turnover: ...

Portfolio Risk
────────────────────
Sector exposure after trade: 18%
Correlation with current book: 0.74
Target weight: 4%
```

AI 可以解释这个卡片。

但卡片里的数字必须来自程序。

---

# 17. Portfolio Engine：之前讨论中需要进一步补强的模块

“单个策略表现好”不等于“组合好”。

必须独立设计 Portfolio Engine。

至少支持：

- Max position weight
- Max equity exposure
- Max Stock Satellite exposure
- Cash floor
- Sector concentration
- Correlation control
- Volatility target
- Drawdown throttle
- Risk budget by strategy
- Risk budget by asset

---

# 18. 最大回撤 <= 10% 的真正实现手段

这不是靠“选股准确率”实现。

主要靠：

```text
资产分散
+
风险预算
+
趋势退出
+
波动率控制
+
回撤降仓
+
现金
```

建议把目标理解为：

> **Portfolio Risk Objective**

而不是：

> 某一只策略自身 MDD 必须 < 10%。

---

# 19. 新增：Underwater Duration

仅看 MDD 不够。

需要记录：

> 组合从前高跌下来后多久不能创新高。

建议核心指标增加：

- CAGR
- MDD
- Calmar
- Sharpe
- Sortino
- Volatility
- Underwater Duration
- Turnover
- Cost drag
- Rolling 1Y Return
- Rolling MDD
- Benchmark Excess Return

---

# 20. Backtest Validation Gate

一个策略进入 Paper 前必须至少通过：

```text
1. Research / Validation / Final Holdout 分离
2. Walk-forward 多窗口
3. 参数 ±10~20% 不崩溃
4. Transaction cost x2 仍可接受
5. 明确 Regime 表现
6. OOS 不严重坍塌
7. 样本数足够
8. 不依赖极少数交易
9. 不依赖单一年份
10. Paper Forward
```

---

# 21. Multiple Testing：之前讨论中需要补充的统计问题

AI 可以快速测试成千上万个想法，因此：

> **AI 越强，过拟合风险越大。**

研究数据库必须保存：

- tested hypothesis count
- parameter search count
- all rejected experiments
- experiment lineage

以后可逐步引入：

- Deflated Sharpe Ratio
- Probability of Backtest Overfitting
- Bootstrap
- Monte Carlo
- False Discovery Control

MVP 不必一次做完。

但实验历史必须先保存，否则以后无法校正。

---

# 22. Paper Account

Paper 不是漂亮 UI。

它必须成为：

> **Forward Evidence Generator**

每天记录不可变决策事实，并在未来数据成熟后追加 Outcome：

```yaml
date:
decision_id:
episode_id:
strategy_version:
market_regime:
signal:
previous_target_weight:
new_target_weight:
primary_evaluation_horizon:
benchmark_policy_version:
expected_return:
expected_risk:
actual_fill_assumption:
forward_5d:
forward_20d:
forward_60d:
strategy_horizon_outcome:
```

重要的是：

> 当时系统真实知道什么。

禁止事后重写历史记录，也禁止看到未来结果后修改当时的评价周期、benchmark 或 verdict policy。

---

# 22.1 Decision Outcome & Controlled Learning Loop

这是本版新增的一等子系统。

目标不是让系统“自动变聪明”，而是让系统能够持续回答：

> **过去的决策后来是否创造了价值？如果没有，问题出在 Alpha、Risk、Execution 还是市场 Regime？**

## 22.1.1 DecisionEpisode：评价的最小单位

不能把每天重复输出的 `HOLD` 当作独立样本，否则长期持仓会制造大量虚假“正确决策”。

Episode 应在目标发生**实质变化**时创建，例如：

```text
510300
Current 15% → Target 25%
```

建议字段：

```text
episode_id
decision_id
strategy_version
instrument_id
sleeve
reason_code
previous_target_weight
new_target_weight
decision_time
sizing_reference_price
market_regime
evidence_ids
primary_evaluation_horizon
benchmark_policy_version
evaluation_policy_version
```

Episode 必须 immutable；后续结果只能追加。

## 22.1.2 ForwardEvaluation

未来数据成熟后，由确定性程序自动生成：

```text
ForwardEvaluation
├─ 5D return / excess return
├─ 20D return / excess return
├─ 60D return / excess return
├─ primary-horizon outcome
├─ MAE
├─ MFE
├─ drawdown contribution
├─ realized execution drag
└─ data/evaluation version
```

`primary_evaluation_horizon` 必须在决策发生时预先声明。

例如：

```text
ETF Trend Core      → primary horizon = 60 trading days
Stock Momentum      → primary horizon = 20 trading days
```

系统可以同时记录 5D / 20D / 60D，但不能事后因为某个窗口表现更好而改变主评分周期。

## 22.1.3 “正确 / 错误”必须多维评价

禁止只用：

```text
BUY 后涨 = 正确
SELL 后涨 = 错误
```

至少评价四个维度：

```text
Direction
Alpha / Counterfactual Value Add
Risk / Drawdown Avoidance
Execution Drag
```

最终 verdict 可以是：

```text
GOOD
MIXED
BAD
INCONCLUSIVE
```

但 verdict 由版本化 deterministic policy 计算，LLM 只能解释。

## 22.1.4 Counterfactual Evaluation

最有价值的问题不是“买后涨了多少”，而是：

> **如果当时没有执行这次 TargetPortfolio 变化，账户后来会怎样？**

例如：

```text
Actual decision:
510300 15% → 25%

Counterfactual:
维持 15%
```

计算：

```text
Decision Value Add
= Actual path P&L - No-change Counterfactual P&L
```

同样可以评估：

```text
BUY contribution
SELL avoided loss
CASH contribution
Risk throttle contribution
Satellite contribution
```

Counterfactual 必须使用预先声明的 baseline 和相同费用/可交易性语义，禁止事后为某次决策选择有利对照。

## 22.1.5 StrategyHealthSnapshot

系统应周期性聚合 Episode 结果：

```text
strategy_version
window_start / window_end
episode_count
good / mixed / bad / inconclusive
primary_horizon_excess_return
win_rate
MAE / MFE distribution
regime breakdown
decision_value_add
risk_value_add
execution_drag
health_state
```

状态：

```text
HEALTHY
WATCH
DEGRADED
SUSPENDED
RETIRED
```

Health 变化必须保留 evidence，不得由 LLM 文本直接修改。

## 22.1.6 Learning Loop 的权限边界

允许：

```text
Outcome Evidence
    ↓
AI / deterministic analytics 发现失败模式
    ↓
Research Proposal
    ↓
New Hypothesis
    ↓
Strategy vNext
```

禁止：

```text
最近几笔亏损
    ↓
AI 自动修改参数
    ↓
明天直接进入 Production
```

Strategy vNext 必须重新通过完整 Gate：

```text
Backtest
→ Robustness
→ OOS
→ Walk-forward
→ Final Holdout
→ Paper Forward
→ Owner Approval
→ Production
```

因此本项目的目标是：

> **系统会学习，但不会擅自改自己。**

## 22.1.7 Evaluation Run

Forward Evaluation 不属于交易关键路径，可以作为独立的非阻塞任务运行：

```text
Latest finalized market data
        ↓
Find matured DecisionEpisodes
        ↓
Compute ForwardEvaluation
        ↓
Update StrategyHealthSnapshot
        ↓
Emit Research Feedback Candidate
```

Evaluation Run：

- 不生成新的交易目标；
- 不修改已经锁定的 Decision；
- 不修改 Production strategy/config；
- 失败只影响 evidence freshness，不应改变当天交易指令。

---

# 23. Manual Execution Reconciliation

因为本项目不自动下单，所以需要新增一个以前讨论较少的关键功能：

> **人工成交对账**

信号：

```text
BUY 510300 target 25%
```

用户执行后记录：

```text
actual_price
actual_quantity
actual_time
```

系统比较：

```text
Plan vs Actual
```

这样才能知道：

> 策略表现差，还是人工执行偏差导致。

---

# 24. Notification Engine

第一版通知的目标不是“资讯推送”，而是：

> **把已经通过 Production Gate 的执行计划，以低噪声、可追踪的方式送到个人微信。**

## 24.1 技术路线

正式采用：

```text
Personal Systematic Investing OS
              ↓
       NotificationPort
              ↓
      ServerChanAdapter
              ↓
        Server酱 / ServerChan
              ↓
          个人微信
```

明确不采用 JoinQuant 那种：

```text
平台公众号
   ↓
用户扫码绑定平台账号
   ↓
平台按 OpenID / 用户体系推送
```

原因：

- 本项目首先是个人系统，不需要平台级公众号账户体系；
- 不需要 OAuth / OpenID / 用户绑定；
- 不需要承担公众号运营和平台消息管理复杂度；
- 能避免把开发资源浪费在与投资核心无关的微信生态能力上。

## 24.2 主通知节奏

正常交易日只需要两类主消息。

### A. Pre-open Action Plan

建议时间：

```text
08:45 ~ 09:10
```

用途：

> 告诉用户“今天真正需要执行什么”。

必须包含：

```text
trade_date
decision_id
generated_at
risk_state
data_gate
risk_gate
current_portfolio
target_portfolio
BUY / SELL / HOLD / CASH / NO ACTION
target_weight
estimated_amount
executable_quantity
strategy_version
evidence_id
```

示例：

```text
【今日交易计划 2026-09-15】

组合状态：Moderate Risk-On
账户权益：¥100,000

SELL 159915
当前 10%
目标 0%
原因：Trend Exit

BUY 510300
当前 15%
目标 25%
预计增持：约 ¥10,000

HOLD 518880
目标 15%

CASH
目标 35%

Data Gate: PASS
Risk Gate: PASS
Decision ID: 20260914-EOD-001
```

### B. EOD Decision Summary

建议时间：

```text
收盘数据完整并完成 EOD Decision Run 后
```

用途：

> 告诉用户系统对下一交易日的目标组合已经发生什么变化。

示例：

```text
【明日组合决策 2026-09-16】

ETF Core
510300  25%
518880  15%

Stock Satellite
XXXXXX   5%

Cash
55%

变更：
+ XXXXXX 新增 5%
- 159915 退出

明早开盘前将再次进行执行确认。
```

## 24.3 异常通知

异常通知必须独立于正常交易消息。

首批类型：

```text
DATA_ERROR
DATA_STALE
RISK_KILL_SWITCH
STRATEGY_SUSPENDED
PRODUCTION_RUN_FAILED
NOTIFICATION_RETRY_EXHAUSTED
```

异常消息必须说明：

- 是否阻止交易；
- 哪个 Gate 失败；
- 哪个策略 / 数据源受影响；
- 用户当天应该采取什么动作。

如果关键数据或风险 Gate 失败，默认：

```text
NO NEW TRADE
```

而不是继续使用旧数据猜测。

## 24.4 NotificationPort

核心层只依赖抽象接口，例如：

```python
class NotificationPort(Protocol):
    def send(self, message: NotificationMessage) -> NotificationResult:
        ...
```

ServerChan 实现：

```text
ServerChanAdapter
```

未来如果替换为：

- 企业微信
- Email
- Bark
- Telegram

不应修改 Quant / Portfolio / Risk 代码。

## 24.5 幂等与去重

通知必须以稳定业务键去重，例如：

```text
notification_key =
    trade_date
    + run_type
    + decision_id
    + message_type
```

同一个 EOD Decision 或 Pre-open Action Plan 被任务重跑时：

> 不得重复推送同一条交易指令。

允许：

- 第一次发送失败后重试；
- 内容真正变化并产生新 Decision ID 后重新发送。

## 24.6 Secret 管理

ServerChan 凭据：

```text
SERVERCHAN_SENDKEY
```

必须：

- 通过环境变量或 Secret Store 注入；
- 不写入源码；
- 不提交 Git；
- 不出现在普通日志；
- 错误日志只能记录脱敏信息。

## 24.7 通知不是 Ground Truth

微信消息只是：

> Production Decision 的展示与传输层。

真正 Ground Truth 存在系统数据库中：

```text
Decision Snapshot
Target Portfolio
Action Plan
Evidence
```

即使微信推送失败：

> 决策本身仍然必须可查询、可重放、可审计。


# 24.8 First Data Provider Decision：chstockdata

本项目的数据获取层不从零重写。已存在独立项目：

```text
https://github.com/joycoding2000/chstockdata
```

它来源于 TradingAgents-astock 中经过长期迭代的数据层，并已抽成独立 Python 包。对本项目而言，它属于：

> **first-party sibling dependency / 第一方兄弟项目**

而不是要 cherry-pick 进主仓的源码目录。

## 24.8.1 职责边界

### chstockdata 负责

```text
Vendor Access
Vendor Fallback
Rate Limit / Backoff
Realtime Quote Routing
Historical OHLCV Acquisition
Local vipdoc History
Trading Calendar Source
Corporate / Suspension / Delisting Source
Point-in-time Source Filtering
Provider Provenance
```

### systematic-investing-os 负责

```text
Canonical Quant Data Contract
Instrument Master
ETF / Stock Classification
Fee / Trading-rule Profiles
Data Snapshot Identity
Data Quality Gate
Research Dataset Freeze
Backtest Input Semantics
Portfolio / Risk / Signal
Production Decision
```

这两个边界不得重新混合。

## 24.8.2 Adapter / Anti-corruption Layer

推荐接口：

```text
DataProviderPort
      │
      └── ChStockDataProvider
              │
              └── chstockdata package
```

`quant/`、`portfolio/`、`risk/` 不允许直接 `import chstockdata`，只能依赖本项目 Domain / Data contracts。

原因：

- chstockdata v1 为兼容既有生产调用冻结了当前函数和返回形状；
- 本项目需要稳定、类型化、可版本化的 Quant Contract；
- 将来 chstockdata v2 或其他 Provider 出现时，只替换 Adapter。

建议首批 canonical models：

```text
DailyBar
TradingCalendar
TradabilityStatus
CorporateAction
InstrumentReference
DataSnapshot
ProviderEvidence
```

## 24.8.3 Production 不通过 MCP

虽然 chstockdata 提供 MCP server，但确定性 Quant Runtime 应：

```text
Python package call
    ↓
ChStockDataProvider
    ↓
Canonical Data Contract
```

MCP 只允许未来用于 AI Research Copilot、人工查询和 hypothesis research，不能成为 Backtest / Production Decision 的关键链路。

## 24.8.4 Data Quality Gate 继续保留

chstockdata 已经解决大量 Vendor correctness 问题，但外部免费端点仍可能改字段、限流、返回空值或陈旧行情。

因此本项目仍保留消费侧 Gate：

```text
Freshness
Completeness
Calendar Alignment
Duplicate
OHLC Consistency
Pre-close Consistency
Adjusted-bar Consistency
Tradability
Instrument Type
Snapshot Reproducibility
```

失败默认：

```text
NO NEW TRADE
```

## 24.8.5 ETF Qualification Gate

ETF Core 不能因为底层接口“大概率可用”就直接进入 Production。

M0 增加：

```text
ETF-DATA-GATE
```

至少对首批 ETF Universe 验证：

```text
symbol routing
daily OHLCV
pre_close
volume / amount
trading calendar
suspension / tradability
adjustment semantics
corporate action semantics
source freshness
history completeness
```

如果某类 ETF 不能可靠支持，先从 Universe 排除，而不是在 Quant Kernel 中偷偷增加另一套数据抓取代码。

## 24.8.6 Independent Validation Source

chstockdata 内部多 Vendor fallback 属于 **Provider-internal redundancy**。

Golden / parity 验证仍应保留系统外独立参照，例如 JoinQuant、人工交易所数据核对或其他独立合法来源。

## 24.8.7 Version Pin

Production 不依赖 floating `main`。

开发期可用精确 commit / local editable；稳定后 pin release / version range。每次升级 chstockdata 必须重新跑：

```text
Data Contract Tests
ETF Qualification Tests
Golden Cases
Production Smoke
```

全部通过后才能升级 Production pin。


# 25. Data Plane：chstockdata 之后仍由本项目掌握的消费侧数据治理

`chstockdata` 已经负责免费 Vendor 获取与正确性工程，本项目不重复造这一层。

但一个实战系统最大的风险之一仍然是：

> 策略没错，数据错了。

因此这里的 Data Plane 重点不是“再次抓行情”，而是**消费侧标准化、快照、质量门和可复现性**。

必须有 Data Quality Gate：

```text
Freshness
Completeness
Duplicate
Calendar
Price anomaly
Corporate action
Suspension
Adjusted-price consistency
```

如果 Data Gate FAIL：

```text
NO SIGNAL
```

而不是：

> 用不完整数据继续交易。

---

# 26. Instrument Master

必须单独维护系统自有、版本化、effective-dated 的 Instrument Master。

核心字段 / 规则：

```text
symbol / InstrumentId
exchange
instrument_type
fund_subtype
list_date
delist_date
calendar_id
LotRule
SettlementRule
PriceLimitRule
MarketFeeTaxRule
effective_date / provenance
```

权威边界：

```text
chstockdata
→ market facts / candidate reference

Instrument Master
→ approved classification / market & regulatory rules

AccountFeeConfig / BrokerFeeProfile
→ 账户级佣金、最低佣金等执行配置
```

`BrokerFeeProfile` 不是 Instrument identity，也不是交易所规则，不能放入 Instrument Master。

尤其 ETF：

> 不能简单当普通股票处理，也不能让未知 subtype 静默继承 A 股默认规则。

---

# 27. Reproducibility

每次研究必须可以完全重放。

Experiment 必须记录：

```text
strategy_version
git_commit
data_snapshot
data_provider
parameters
universe
start
end
market_fee_tax_rule_version
account_fee_config_version
slippage
benchmark_policy_version / benchmark_identity
random_seed
```

在 OQ-22 / M1 正式裁决真实 benchmark 前，M0 `RunManifest` 只允许：

```text
NONE
SYNTHETIC_TEST_BENCHMARK
```

不得由 M0 偷偷选定真实投资 benchmark。

---

# 28. Strategy Versioning

禁止：

```text
TrendStrategy
```

应使用：

```text
trend_core_v1.0.0
trend_core_v1.1.0
```

任何规则变化：

> 新版本。

旧版本保留历史。

---

# 29. Strategy Decay / Kill Switch

Production Strategy 不能批准后永久运行。

Strategy Health 应主要由 `DecisionEpisode → ForwardEvaluation → StrategyHealthSnapshot` 的确定性证据驱动。

需要持续监控：

- rolling return / excess return
- rolling Sharpe
- expected vs actual
- Decision Value Add
- drawdown / underwater duration
- hit rate / verdict distribution
- MAE / MFE distribution
- regime mismatch
- execution drag
- signal frequency
- episode sample size / evidence maturity

状态：

```text
HEALTHY
WATCH
DEGRADED
SUSPENDED
RETIRED
```

出现明显异常时：

> 自动停止产生新 BUY 信号，或进入 WATCH / SUSPENDED，但不得自动发明替代策略。

具体降级阈值必须版本化并预先声明，不能在看到坏结果后临时改口径。

---

# 30. AI Copilot

AI 应作为一个服务层，而不是 Runtime Core。

主要能力：

### Research

- source → claim
- claim → hypothesis
- hypothesis → spec
- spec → code draft

### Review

- 分析回测失败
- 比较策略版本
- 找潜在数据泄漏
- 检查经济逻辑
- 提出反例

### Production Explanation

- 解释为什么今天有 / 没有信号
- 查重大新闻 / 政策
- 告诉用户风险
- 生成日报

### Postmortem / Learning

- 读取 `DecisionEpisode` / `ForwardEvaluation` / `StrategyHealthSnapshot`
- 失败交易分析
- 比较 GOOD / MIXED / BAD Episode 的共同特征
- Strategy decay 与 regime mismatch 分析
- 区分 Alpha failure、Risk failure、Execution drag
- 对 Counterfactual 结果做自然语言归因
- 提出新的研究问题与 Strategy vNext 候选

AI 只消费确定性评价结果，不负责生成“正确/错误” Ground Truth。

---

# 31. LLM 输出永远不是 Ground Truth

必须保证：

```text
LLM text
```

无法直接修改：

```text
target_position
```

LLM 可以提交：

```text
Research Proposal
```

正式策略规则必须经过人批准和 Strategy Gate。

---

# 32. 开源项目角色定位

## 32.1 Vibe-Trading / Vibe-Research

用途：

- 学 backtest 结构
- 学 causality / lookahead 防护
- 学 evidence / gate 思路
- 可以 cherry-pick 小型 MIT 模块

不做：

> 整体运行时依赖。

---

## 32.2 RQAlpha

用途：

- A股 / ETF correctness 参照
- transaction cost
- simulation semantics
- Golden parity

注意：

> 非商业许可，不应作为未来商业产品核心代码依赖。

---

## 32.3 Backtrader

用途：

- Broker / Order / Position / Commission / Sizer 架构参考

注意：

> GPLv3，不直接复制进闭源商业项目。

---

## 32.4 vn.py

用途：

- Paper / execution / trading infrastructure 参考
- 以后如果接真实交易可重点评估

不需要现在引入。

---

## 32.5 Qlib

用途：

- Alpha / ML / factor research
- 未来 Phase 2/3
- 大规模研究参考

第一阶段太重。

---

## 32.6 QuantResearch / quanttrader

用途：

- 经典策略
- TAA
- event-driven 架构
- Strategy Cookbook

其中 ETF / TAA 思想尤其值得进入第一批 Hypothesis。

---

## 32.7 KHunter / InStock

用途：

- Stock Satellite 的策略种子
- Feature
- Pattern
- Cheap Scan
- Strategy registry 思想

不直接相信其历史收益。

---

## 32.8 ABu / quant-trading

用途：

- Architecture / Strategy Cookbook

不作为运行时核心。

---

# 33. Source Intake Gate：任何 cherry-pick 前必须执行

新项目必须建立：

```text
third_party/SOURCES.yaml
```

每个外部代码片段记录：

```yaml
source:
  repo: ...
  commit: ...
  path: ...
  license: ...
  author: ...

integration:
  destination: ...
  method: cherry_pick | rewrite | inspiration
  modified: true
  tests_added:
    - ...

reason:
  ...
```

原则：

> **能重写就不盲目整仓复制。**

---

# 34. License Policy

### 可以优先考虑

- MIT
- Apache-2.0
- BSD

但仍必须：

- 保留 copyright
- 保留 license / notice
- 记录来源

### 谨慎 / 禁止直接复制

- GPL
- AGPL
- 非商业许可
- 不明授权
- 付费私有代码

对于这类项目：

> 可以学习公开思想，但不要复制代码。

---

# 35. Product UI：MVP 只做 5 个页面

## 35.1 今日行动

核心页面。

显示：

- BUY
- SELL
- HOLD
- NO ACTION
- 目标仓位
- 当前仓位
- 风险状态

---

## 35.2 机会池

显示：

- ETF / Stock Candidate
- Strategy
- Evidence
- Regime
- Ranking

---

## 35.3 我的组合

显示：

- 当前持仓
- 目标持仓
- 偏差
- 资产暴露
- 风险
- Drawdown

---

## 35.4 策略实验室

显示：

- Backtest
- OOS
- Walk-forward
- Sensitivity
- Cost Stress
- Evidence

---

## 35.5 交易复盘

显示：

- Signal
- Manual Fill
- Plan vs Actual
- Forward Result
- Attribution
- Strategy Health

不要复制 QuantX Pro 那种几十个菜单的 Feature Factory。

---

# 36. 商业化与合规：之前讨论中遗漏但必须提前知道

如果系统只是：

> 自己使用

问题较简单。

如果未来公开出售并明确向用户输出：

> “买入 XX / 卖出 XX”

不同司法辖区可能涉及：

- 投资顾问
- 投资建议
- 金融信息服务
- 风险披露
- 数据许可

因此：

> 商业化前必须做专业法律 / 合规审查。

产品技术架构应预留：

```text
research_only
signal_assistance
execution_disabled
```

等边界。

---

# 37. Security

第一阶段即使不接券商，也需要：

- API Key local secret store
- 不写进 Git
- Provider Credentials encryption
- Log redaction
- Local-first strategy/data cache
- Audit log

---

# 38. Observability

每次 Production Run 都应记录：

```text
data_status
strategy_status
signal_count
portfolio_status
risk_status
notification_status
errors
runtime
```

任何失败：

> 可追踪。

---

# 39. 推荐仓库结构

```text
systematic-investing-os/

├─ apps/
│  ├─ api/
│  └─ web/
│
├─ src/
│  ├─ domain/
│  │  ├─ instruments/
│  │  ├─ orders/
│  │  ├─ positions/
│  │  ├─ portfolio/
│  │  ├─ signals/
│  │  ├─ evidence/
│  │  ├─ outcomes/              # DecisionEpisode / ForwardEvaluation
│  │  └─ strategies/
│  │
│  ├─ data/
│  │  ├─ providers/
│  │  │  ├─ base.py                 # DataProviderPort
│  │  │  └─ chstockdata_provider.py # first provider adapter
│  │  ├─ quality/
│  │  ├─ calendar/
│  │  └─ corporate_actions/
│  │
│  ├─ research/
│  │  ├─ knowledge/
│  │  ├─ claims/
│  │  ├─ hypotheses/
│  │  ├─ experiments/
│  │  └─ registry/
│  │
│  ├─ quant/
│  │  ├─ backtest/
│  │  ├─ strategies/
│  │  ├─ regime/
│  │  ├─ portfolio/
│  │  ├─ risk/
│  │  ├─ evidence/
│  │  └─ metrics/
│  │
│  ├─ production/
│  │  ├─ scheduler/
│  │  ├─ signal_engine/
│  │  ├─ paper/
│  │  ├─ evaluation/            # forward outcome / health snapshots
│  │  ├─ reconciliation/
│  │  └─ notification/
│  │
│  ├─ ai/
│  │  ├─ hypothesis_miner/
│  │  ├─ risk_review/
│  │  ├─ postmortem/
│  │  └─ explanation/
│  │
│  └─ third_party/
│
├─ tests/
│  ├─ unit/
│  ├─ integration/
│  ├─ golden/
│  └─ parity/
│
├─ docs/
│  ├─ architecture/
│  ├─ research/
│  ├─ strategies/
│  └─ decisions/
│
├─ experiments/
├─ data_local/
├─ reports/
├─ third_party/
│  └─ SOURCES.yaml
│
└─ README.md
```

---

# 40. 技术栈建议

第一阶段：

```text
Python 3.12+
FastAPI
Pydantic
Polars / Pandas
DuckDB
Parquet
SQLite / PostgreSQL
React + Vite（Web UI）
pytest
```

研究数据优先：

```text
Parquet + DuckDB
```

原因：

- 本地
- 快
- 简单
- 无需复杂服务

---

# 41. 第一阶段不要引入

暂不需要：

- Kafka
- Redis Cluster
- Kubernetes
- Spark
- GPU
- LLM Fine-tune
- Agent Swarm
- Microservices
- 高频数据库
- 自动交易接口

---

# 41.1 Production Daily Runtime

## EOD Decision Run

建议时间：

```text
收盘数据完整后运行（例如 15:30~16:30）
```

流程：

```text
Market Data
    ↓
Data Quality Gate
    ↓
Approved Strategy Signals
    ↓
Portfolio Engine
    ↓
Risk Engine
    ↓
Target Portfolio
    ↓
Decision Snapshot Lock
```

输出必须持久化：

```text
decision_id
decision_for_trade_date
generated_at
data_snapshot_id
strategy_versions
market_regime
target_weights
risk_state
evidence_ids
```

EOD Decision 一旦锁定，Pre-open 不得无原因覆盖。

## Pre-open Execution Confirmation Run

建议时间：

```text
开盘前（例如 08:45~09:10）
```

流程：

```text
Load Locked EOD Target
        ↓
Current Position Reconciliation
        ↓
Trading Calendar Check
        ↓
Tradability / Suspension / Corporate Action Check
        ↓
Data Health Check
        ↓
Risk Kill-switch Check
        ↓
T-close-sized Planned Quantity / Notional
        ↓
Action Plan
        ↓
WeChat Notification
```

v1 不重新生成基础日线 Alpha，也**不观察尚未发生的下一交易日 Open**。实际跳空导致的数量缩减只能发生在人工执行或未来单独批准的 execution-time confirmation 中，并通过 Fill Reconciliation 记录。

输出示例：

```text
2026-09-15 08:55
Decision: VALID
Risk Check: PASS
Data Check: PASS

BUY  510300
Current 15%
Target 25%
Estimated Amount ¥10,000

SELL 159915
Current 10%
Target 0%

HOLD 518880
Target 15%

CASH Target 35%
```

人工执行后录入：

```text
actual_time
actual_price
actual_quantity
fees
```

系统保存：

```text
Plan vs Actual
```

用于后续归因。

## Forward Evidence Evaluation Run（非交易关键路径）

在未来数据成熟后，系统周期性处理历史 `DecisionEpisode`：

```text
Matured Episodes
    ↓
Forward Evaluation
    ↓
Counterfactual / Attribution
    ↓
Strategy Health Snapshot
    ↓
Research Feedback Candidate
```

该 Run 不改变当天 TargetPortfolio，也不能修改 Production 策略/参数。


# 42. Milestone 设计

## M0 — Foundation

目标：

> Domain + Data + Backtest correctness

包含：

- Instrument Master
- Daily OHLCV Contract
- Calendar
- MarketFeeTaxRule + AccountFeeConfig 权威分离
- T_CLOSE sizing / NEXT_SESSION_OPEN fill
- Backtest Kernel
- Golden Cases

---

## M1 — ETF Core Research

实现：

- Buy & Hold
- Trend
- Relative Momentum
- Defensive / Cash
- Portfolio Allocation

目标：

> 能完整回测一个 ETF Portfolio。

---

## M2 — Evidence & Validation

实现：

- OOS
- Walk-forward
- Sensitivity
- Cost Stress
- Event Study
- Strategy Registry
- Decision Outcome evaluation contracts
- 预注册 `primary_evaluation_horizon`
- Counterfactual baseline / verdict policy versioning

目标：

> 在进入 Paper 前，先定义“未来怎么判卷”，避免看到结果后再改评分标准。

---

## M3 — Paper Forward & Learning Loop

实现：

- 每日 Run
- Target Portfolio
- Signal Record
- Paper Account
- `DecisionEpisode`
- `ForwardEvaluation`
- 5D / 20D / 60D / primary-horizon Outcome
- Counterfactual / Decision Value Add
- `StrategyHealthSnapshot`
- Forward Evidence Evaluation Run
- Research Feedback Candidate

目标：

> 形成“过去决策 → 未来结果 → 策略健康 → 新研究假设”的闭环，但不允许自动修改 Production。

---

## M4 — Signal Product

实现：

- 今日行动
- 机会池
- 组合
- `NotificationPort`
- ServerChan / Server酱微信 Adapter
- Pre-open Action Plan
- Manual Fill Reconciliation

---

## M5 — Research Knowledge

实现：

- Source
- Claim
- Hypothesis
- Strategy Spec
- AI Extraction

先人工导入 50~100 篇高质量资料。

---

## M6 — Stock Satellite

实现：

- High-liquidity Stock Universe
- Trend / Breakout / Momentum
- Quality / Liquidity filters
- Evidence Gate

---

# 43. 初始成功标准

系统不是因为：

> 推荐过一只涨停股

而成功。

第一阶段真正要证明：

### Engineering

- 回测可复现
- 无未来函数
- Golden Parity 可解释
- Production Run 稳定

### Research

- 能拒绝坏策略
- Holdout 严格
- Experiment history 完整

### Portfolio

- 风险规则确实降低回撤
- 不依赖单一资产 / 单一年份
- 收益来源可解释

### Forward / Learning

- Paper / Production 决策完整记录
- 真实未来数据持续验证
- Signal calibration 可统计
- 每个实质性目标变化都可追踪到 `DecisionEpisode`
- 能区分 Direction / Alpha / Risk / Execution 四类结果
- 能计算预注册窗口下的 Forward Evaluation
- 能回答“如果当时不改变仓位会怎样”的 Counterfactual
- 能区分策略失效与人工执行偏差
- Strategy Health 有可审计证据，不依赖 AI 主观打分

---

# 44. 已裁决事项与剩余开放问题

## 已裁决

- 产品资产范围：`ETF Core + Stock Satellite`
- Production 主循环：EOD Decision + Pre-open Execution Confirmation
- 初始资金：100,000 RMB
- 数据：首个主 Provider 确定为 `joycoding2000/chstockdata`；通过 `ChStockDataProvider` Adapter 接入，Quant Core 保持 Provider-neutral
- 通知：个人微信，首版 Server酱 / ServerChan；不自建公众号/OAuth/OpenID 用户绑定体系；正常每日两条主通知（Pre-open + EOD），异常事件单独告警
- 自动交易：不做；只做可靠信号、目标仓位和人工执行对账
- 组合模型：`Target Portfolio` 为一等核心对象
- M0 Design Gate：**PASS（2026-09-15）**；M0 可按批准计划进入 TDD Implementation
- Instrument Master 权威与 `chstockdata` 分离；broker/account fee 属于 run/account execution config
- PIT：`information_available_at != retrieved_at`，未知可用时间不得伪造
- Execution：`T_CLOSE sizing != NEXT_SESSION_OPEN fill`；Pre-open 不观察未来 Open
- Portfolio Sleeve：`CORE / SATELLITE` 为强类型概念
- 数量变化型 corporate action 位于 decision 与 activation 之间时，受影响 pending execution fail closed：`CORPORATE_ACTION_REPLAN_REQUIRED`
- 自我迭代边界：允许自动 Forward Evaluation / Strategy Health / Research Feedback；禁止运行时自动修改 Production 策略与参数
- 决策评价：以 `DecisionEpisode` 为最小单元，评价周期与 benchmark/counterfactual/verdict policy 必须预注册并版本化

## 仍需后续阶段裁决

以下问题**不阻塞 M0**，应在进入对应 Milestone 前决定：

1. ETF Core 第一批具体 Universe
2. Stock Satellite 第一批股票池定义与流动性阈值
3. ETF Core 初始策略具体参数范围（只定义研究区间，不以目标收益反向调参）
4. Stock Satellite 首批 3~5 个策略族的具体实现
5. chstockdata 的 ETF-DATA-GATE 代表 ETF 清单，以及独立校验源的最终选择
6. ServerChan 消息格式、严重等级与去重策略
7. Paper Forward 最短观察周期与 Strategy Promotion Gate
8. 小资金 Canary 阶段实际投入金额与单策略风险预算
9. **Benchmark Policy（M1 前）**：ETF Core benchmark、whole-portfolio benchmark、cash/risk-free comparator
10. **CASH 的经济含义（M1 前）**：真正零收益现金，还是明确持有某种 Defensive Asset；两者不得事后混用
11. 各 Strategy Family 的 `primary_evaluation_horizon`
12. Decision Outcome 的 deterministic verdict policy（GOOD / MIXED / BAD / INCONCLUSIVE）
13. Counterfactual baseline 的正式定义（默认 no-change / previous target，哪些场景允许其他 baseline）
14. Strategy Health 的 WATCH / DEGRADED / SUSPENDED 阈值与最小成熟 Episode 数
15. Forward Evaluation / Strategy Health 的运行频率与人工 Review cadence
16. **Stock Satellite dividend-tax semantics（M6 前）**：个人投资者股息税单独建模，不混入普通 transaction fee

# 45. 本轮独立复盘后补充出的主要遗漏

相对于前面讨论，本次正式补上了以下重要内容：

1. **Research / Production 隔离**
2. **Decision Outcome & Controlled Learning Loop：系统能持续判卷，但不能自动改 Production**
3. **Instrument Master**
4. **ETF 与股票不同交易/费用语义**
5. **Data Quality Gate**
6. **Knowledge Available Date**
7. **Source Quality**
8. **Multiple Testing 记录**
9. **Portfolio Engine 独立设计**
10. **Underwater Duration**
11. **Strategy Decay / Kill Switch**
12. **Manual Execution Reconciliation**
13. **Notification Reliability**
14. **Reproducibility / Data Snapshot**
15. **Open-source Source Intake Gate**
16. **数据授权 / 帖子版权**
17. **未来商业化的投资建议合规风险**
18. **Security / Secrets**
19. **Observability**

这些都属于真正从“Demo”走向“能长期用真钱运行”的关键能力。

---


# 46. Codex 第一轮工作提示词（历史基线，M0 Design Gate 已于 2026-09-15 通过）

> 本节保留为设计阶段历史基线。当前实际状态已进入 M0 Implementation；后续实施以已批准的 `docs/plans/M0-implementation-plan.md` 为准。


下面内容可以直接给 Codex。

```text
你现在要从 0 开始创建一个全新的项目。

项目暂名：
Personal Systematic Investing OS

不要基于现有 TradingAgents、Vibe-Trading、Vibe-Research 项目继续开发。
新建独立仓库。

目标：
建设一个面向个人投资者的中低频 / 中长线系统化投资决策系统。

核心产品不是 AI 荐股。
AI 只是 Research Copilot。
Production 的 BUY / SELL / HOLD / NO ACTION 必须来自确定性策略、组合与风险规则。

已裁决的全局约束：
- 目标产品同时支持 ETF Core + Stock Satellite
- 默认初始资金 100,000 RMB
- 数据首版主 Provider 已确定为 `joycoding2000/chstockdata`，通过 `ChStockDataProvider` Adapter 接入；核心必须 Provider-neutral
- 不在本项目重新实现 chstockdata 已负责的 vendor 抓取 / fallback / throttle / vipdoc / PIT 逻辑
- Production Quant Runtime 使用 chstockdata Python API，不通过 MCP
- M0 必须增加 ETF-DATA-GATE
- 每日有两个 Production run：
  1) EOD Decision Run：生成下一交易日 Target Portfolio
  2) Pre-open Confirmation Run：不重新算基础 Alpha，只做执行确认与风险检查
- Target Portfolio 是核心模型，BUY/SELL/HOLD 是差值结果
- 第一通知渠道：个人微信，首版 ServerChan / Server酱
- 不做自动交易，人工执行后必须支持 Fill Reconciliation

当前阶段只实施 M0 Foundation。
不要实现 Web UI。
不要实现 AI Agent。
不要实现自动交易。
不要实现 Stock Satellite。
不要实现参数优化。

==============================
M0 OBJECTIVES
==============================

1. Domain Model
- Instrument
- InstrumentType
- FeeProfile
- MarketCalendar
- Bar
- Signal
- TargetPosition
- Order
- Fill
- Position
- PortfolioSnapshot

2. Instrument Master
至少支持：
- China A-share
- Exchange-listed ETF

2.1 chstockdata Provider Adapter
- 定义 `DataProviderPort`
- 实现 `ChStockDataProvider`
- Adapter 负责把 chstockdata 原始返回转换为 canonical contracts
- Quant / Portfolio / Risk 层禁止直接 import chstockdata
- Production 不使用 MCP 获取行情
- 增加 ETF-DATA-GATE

必须允许按 instrument type / fund subtype 配置：
- lot size
- T+0/T+1
- fee profile
- price limit profile

3. Daily Market Data Contract
字段至少：
- date
- symbol
- open
- high
- low
- close
- volume
- amount
- pre_close
- adjustment metadata

4. Data Quality Gate
检查：
- date freshness
- duplicate bars
- missing required fields
- price consistency
- calendar alignment

Gate FAIL 时不得产生 Production Signal。

5. Backtest Kernel v1
仅支持：
- daily bars
- long / cash
- target position weights
- next-bar execution
- configurable slippage
- configurable transaction fees

必须保证：
T close 计算出来的信号只能 T+1 执行。

6. A-share / ETF execution semantics
先设计配置化接口。
不要硬编码所有 ETF 都和 A股股票一样。

7. Metrics
实现：
- total return
- CAGR
- volatility
- Sharpe
- Sortino
- max drawdown
- Calmar
- underwater duration
- turnover

8. Reproducibility
每次 run 保存：
- git commit
- strategy version
- data version / snapshot id
- parameters
- universe
- start/end
- cost config
- benchmark

9. Golden Tests
至少覆盖：
- T close signal / T+1 fill
- insufficient cash
- lot rounding
- transaction fee
- sell tax
- ETF tax profile
- suspension / non-tradable stub
- limit-up rejected buy
- limit-down rejected sell
- no lookahead
- drawdown calculation
- terminal liquidation semantics

10. Third-party provenance
创建：
third_party/SOURCES.yaml

任何复制 / cherry-pick / adaptation 的代码都必须记录：
- repo
- commit
- source path
- license
- integration method
- modifications
- tests

==============================
ENGINEERING RULES
==============================

- Python 3.12+
- 强类型优先
- Pydantic / dataclass 合理使用
- pytest
- 模块化，但禁止过度工程
- 不上微服务
- 不上 Kafka
- 不上 Redis
- 不上 GPU
- 不引入 LLM
- 不引入大型量化框架作为核心运行时
- 可以阅读开源项目学习设计
- cherry-pick 必须单独评估 License 和来源
- GPL / 非商业许可证代码不得复制进核心
- 核心回测代码必须可以被我们自己完全理解和测试

==============================
REFERENCE PROJECTS
==============================

数据依赖（不是参考项目）：

- joycoding2000/chstockdata
  - 本项目第一数据 Provider
  - 通过 Adapter 依赖 package，不复制进主仓
  - 版本必须 pin，升级必须跑 Data Contract / ETF Qualification / Golden tests

可参考但不要整包引入：

- HKUDS/Vibe-Trading
- simonlin1212/Vibe-Research
- ricequant/rqalpha
- mementum/backtrader
- vnpy/vnpy
- microsoft/qlib
- letianzj/QuantResearch
- letianzj/quanttrader
- ling-0729/KHunter
- myhhub/stock
- bbfamily/abu
- je-suis-tm/quant-trading

参考原则：
- 学设计
- 学测试
- 学执行语义
- 学策略思想
- 不相信宣传结果
- 不把 README 当生产证据

==============================
WORKFLOW
==============================

第一步：
只做代码库审查和实施计划。

输出：
1. architecture.md
2. domain-model.md
3. backtest-semantics.md
4. test-plan.md
5. third-party-intake-policy.md
6. M0 implementation plan

先不要写业务代码。

等人工 review 并批准 plan 后，再开始实现。

最终目标不是最快写完，
而是打造一个未来可以真的拿真钱长期运行、
每一笔交易都可解释、可复现、可审计的系统。
```

---

# 46.1 ADR：chstockdata 成为第一数据 Provider

**Decision**

```text
systematic-investing-os
        ↓
DataProviderPort
        ↓
ChStockDataProvider
        ↓
chstockdata
```

不复制 TradingAgents dataflows，不在本项目再次维护免费数据抓取代码。

**理由**

- 数据层已经被独立为单一事实源；
- 已积累真实生产 bug 的回归测试资产；
- 本项目可以把工程资源集中到 Quant correctness、Portfolio、Risk、Evidence 和 Forward Verification；
- Adapter 防止 chstockdata v1 历史契约污染 Quant Domain；
- 独立版本 pin + qualification tests 控制跨仓升级风险。

**保留风险**

- 免费公开接口无 SLA；
- ETF 能力必须单独验证；
- chstockdata 内部多源不等同于系统外独立校验；
- 如果未来数据能力不足，应替换 Provider，而不是污染 Quant Core。


# 46.2 v0.3 新增裁决：Decision Outcome & Controlled Learning Loop

**Decision**

系统长期运行后，必须具备自动判卷能力：

```text
DecisionEpisode
→ ForwardEvaluation
→ Counterfactual / Attribution
→ StrategyHealthSnapshot
→ Research Feedback
```

**核心边界**

- 评价由 deterministic policy 产生；LLM 只做解释与 Hypothesis 生成；
- 主评价周期、benchmark、counterfactual baseline、verdict policy 必须预注册并版本化；
- Outcome 可以回流 Research，但 Research/AI 无权直接修改 Production；
- Strategy 改进只能形成新的 immutable version，并重新通过完整 Gate；
- Learning Loop 属于 M2/M3，不改变已经批准的 M0 scope。

**目标**

让系统在半年、一年后能够回答：

> 哪些策略、哪些 regime、哪些 BUY/SELL/Risk 动作真正创造了价值？
> 哪些失败来自 Alpha、Risk、Execution，哪些只是样本噪声？

而不是只保留一串无法学习的历史买卖记录。


# 47. 最终原则

这个项目真正的核心不应该是：

> “AI 有多聪明？”

而应该是：

> **我们的投资假设是否靠谱？**
>
> **我们的验证是否可信？**
>
> **我们的风险控制是否有效？**
>
> **我们的实际未来表现是否支持这个策略继续运行？**

长期护城河不是 LLM 权重。

而是：

```text
Research Knowledge
+
Hypothesis History
+
Reliable Quant Kernel
+
Strategy Evidence
+
Forward Track Record
+
Decision Outcome History
+
Strategy Health Evidence
+
Risk Discipline
```

最终系统要做到：

> **AI 帮你研究。**
>
> **程序帮你判卷。**
>
> **风险系统决定你能承担多少。**
>
> **市场用未来数据做最后裁决。**
>
> **系统可以从历史 Outcome 中学习，但任何改进都必须以新 Strategy Version 重新通过验证与人工批准。**