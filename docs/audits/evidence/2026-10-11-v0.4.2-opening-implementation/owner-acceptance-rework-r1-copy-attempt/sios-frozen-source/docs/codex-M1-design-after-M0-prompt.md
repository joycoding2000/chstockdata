# Codex Prompt — Design M1 After M0

你正在继续开发 `personal-systematic-investing-os`。

## 权威文档

产品/执行总纲：

`docs/personal-systematic-investing-os-v0.9-flight-test-driven-product-architecture.md`

M0 已批准的详细设计继续保持权威，不得重开：

- `docs/architecture.md`
- `docs/backtest-semantics.md`
- `docs/data-contracts.md`
- `docs/domain-model.md`
- `docs/portfolio-risk-semantics.md`
- `docs/production-runtime.md`
- `docs/test-plan.md`
- `docs/third-party-intake-policy.md`
- `docs/plans/M0-implementation-plan.md`

## 任务

**只设计 M1。不要设计完整 M2/M3 implementation plan，也不要开始写 M1 production code。**

先完整检查：

1. 当前 repo tree；
2. M0 实际实现状态；
3. M0 tests / latest evidence；
4. 上述权威文档；
5. 与 v0.9 是否存在冲突。

如果 M0 尚未完成，先报告 M0 remaining status，不得提前修改 M0 scope。

如果 M0 已达到可开始 M1 design 的状态，输出以下文档：

```text
docs/m1/
├─ M1-architecture.md
├─ strategy-research-protocol.md
├─ M1-test-plan.md
└─ OPEN_QUESTIONS.md

docs/plans/
└─ M1-implementation-plan.md
```

## M1 唯一目标

> 尽快让 ETF 与 Stock 候选策略真正跑通：
> `Idea → Strategy Code → Basic Backtest → OOS`
> 并形成可以快速重复“发现 → 实现 → 证伪”的循环。

M1 不是建设完整 Quant Research Platform。

## 强制 scope

M1 应包含：

- 最薄 `StrategyContract`；
- ETF candidate research；
- Stock candidate research；
- simple experiment log / lineage；
- failed experiment retention；
- Cheap Screening；
- Basic Backtest；
- fixed OOS；
- AI Copilot 使用现有强 Agent + 本项目 CLI/测试工具的 workflow；
- Strategy version / digest / reproducibility；
- no-lookahead / OOS contamination tests。

M1 不应包含：

- 完整 Knowledge Management Platform；
- 完整 Regime Router；
- 复杂 AI Agent Runtime；
- Private Investment Memory；
- AI Investor；
- 完整 5-page Web UI；
- Production scheduler；
- ServerChan；
- broker integration；
- complex multiple-testing statistics；
- complete user-facing Strategy SDK；
- M2/M3 production implementation。

## First-principles rule

每提出一个 subsystem，都回答：

> “没有它，能否仍然让第一个真实策略更快进入可信 OOS？”

若答案为“能”，且该 subsystem 不属于金融正确性边界，默认后置。

## Validation Funnel

M1 设计必须体现：

```text
Idea
→ Cheap Screening
→ Strategy Implementation
→ Basic Backtest
→ OOS
→ Survivor / Rejected
```

不要让每个 Idea 一开始就跑完整 Walk-forward / Holdout / Paper。

这些属于 M2 的 survivor validation。

## ETF + Stock

二者从 M1 同步研究。

但 Stock 第一阶段限于低数据复杂度策略优先：

- Trend
- Breakout
- Momentum
- Relative Strength
- Liquidity

不要为了 Stock 提前建设复杂 PIT fundamentals / factor platform。

## Market Regime

BULL / SIDEWAYS / BEAR 在 M1 作为：

> analysis dimension

而不是 Production router。

可以输出 strategy × regime breakdown。

不要先建设自动 Regime switching。

## AI Copilot

M1 优先采用：

> 现有 ChatGPT / Codex / GLM Agent 调用本项目 Research CLI / tests / backtest。

不要先开发大型 agent orchestration framework。

## Implementation Plan 要求

`M1-implementation-plan.md` 必须：

- task-by-task；
- TDD；
- 每 Task 先 failing test；
- 每 Task 有 exact commands / expected evidence；
- focused commit；
- 避免 unrelated refactor；
- 前几个 Task 尽快让第一个真实 Strategy 在 M0 kernel 上跑起来；
- 不允许先连续十几个 infrastructure Task 才看到 Strategy result。

## 输出前自检

最后增加：

### Scope Audit

列出：

- M1 必须做；
- 明确后置 M2；
- 明确后置 M3；
- 长期后置；
- 是否存在 over-engineering。

### Design Conflict

若 v0.9 与当前 M0 approved semantics 冲突：

```text
DESIGN_CONFLICT
```

停止，不擅自修改 M0。

### Final recommendation

明确回答：

> “按照当前设计，最早在哪一个 Task 我们能看到第一个真实 ETF 或 Stock 策略的 backtest result？”
