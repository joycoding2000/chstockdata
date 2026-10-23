# R2-1 ETF Relative Momentum Persistence — Research Design (DRAFT)

Status: `DESIGN DRAFT`; Owner Review Gate pending. No new CandidateIntent, strategy implementation, Basic run, OOS freeze, or OOS run is authorized by this document. The initial R2-1 review was based on `main` at `c2999f0166daabab94a92a7489ae5608d0bfc704`. R2-1A review was performed on `main` at `9e1d44fc4052fb6366ff49008b1436e1d29010f1` with a clean worktree before these documentation edits. Evidence root: `var/research/task9-experiments-v2`.

## 1. Research Question

Does month-to-month top-rank switching in the existing four-ETF relative momentum rule create avoidable turnover and trading cost? Can a predeclared two-consecutive-effective-month-end leader requirement reduce ineffective replacement trades while retaining the original rotation mechanism? Lower cost, higher return, alpha, and product suitability are separate empirical questions, not assumptions.

## 2. Parent Evidence

Parent lineage: `m1-etf-relative-momentum`. Parent experiment: frozen `research/candidates/m1-etf-relative-momentum-v1.json`, persisted `var/research/task9-experiments-v2/m1-etf-relative-momentum/intent.json`, and all three immutable Basic runs. The parent intent prioritizes `momentum-126`, then `momentum-252`, then `momentum-126-gate`; its selection artifact is `NO_BASIC_PASS` and retains all three `REJECTED_BASIC` attempts. The proposed revision starts with `momentum-126` because it was first in that *pre-result* priority, not because it won on observed return or turnover.

| Parent variant / run | Parameters | Basic window | Cumulative turnover | Cost drag / modeled costs | Fills (= reported trades) | Net total return / benchmark / excess | Max drawdown | Basic verdict |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| `momentum-126` / `run-8ba3748926242d1c` | `return_sessions=126` | 2016-01-04..2022-12-30 | 22.91508141052391526604183280 | 0.0134168 / CNY 1341.68 | 49 | 0.4977242 / 0.2294432 / 0.2682810 | -0.2176079238790001787614737323 | `REJECTED_BASIC`: turnover 22.9151 > 12 |
| `momentum-252` / `run-2a217352ba073d65` | `return_sessions=252` | 2016-01-04..2022-12-30 | 13.30439882803119987405459109 | 0.0094987 / CNY 949.87 | 30 | 1.0427683 / 0.2294432 / 0.8133251 | -0.2275461175301268892504006762 | `REJECTED_BASIC`: turnover 13.3044 > 12 |
| `momentum-126-gate` / `run-41d08375e3c92776` | `return_sessions=126`, `trend_gate_sma_sessions=200` | 2016-01-04..2022-12-30 | 20.73729655882552145890142888 | 0.0124805 / CNY 1248.05 | 44 | 0.4814025 / 0.2294432 / 0.2519593 | -0.2181595779911745472197480242 | `REJECTED_BASIC`: turnover 20.7373 > 12 |

Each row was matched to its own `runs/<run-id>/report.json` `variant_id`, metrics, gate verdicts, and its `result.json` parameters, rather than inferred from a summary. All have 1703 NAV observations; the other three original Basic gates passed. The gate failure is evidence of excessive *measured* trading, not proof that persistence will fix it. The gated variant had one rejected order; its 44 trades are fills, not submitted orders.

`metrics.performance.turnover` computes `0.5 × (sum of absolute BUY_CONSIDERATION and SELL_PROCEEDS) / arithmetic mean of observed total equity`. Costs are excluded from traded notional. `runner.py` supplies NAV points and cash ledger entries from Basic start onward; this is one cumulative Basic-window ratio, neither an annualized rate nor a sum of monthly rates. An initial purchase executed during Basic counts. The engine does not force terminal liquidation: each parent report has a nonzero final ETF position. Thus no terminal forced sale is included. `trade_count` is the number of engine fills, whereas the turnover numerator uses settled buy/sell ledger consideration. `cost_drag` compares gross and net performance under the same fills; it is not identical to `total_costs / initial_capital`. The legacy `max_turnover=12` definition must stay fixed.

## 3. Economic Hypothesis and Counter-Hypothesis

Medium-horizon relative leadership across broad equity, ChiNext equity, gold, and bond ETFs may persist longer than one monthly ranking fluctuation. Requiring a challenger to lead at two successive valid month-end observations may avoid short reversals and lower gross trading and cost. The counter-hypothesis is that confirmation delays useful rotation, retains a declining ETF, misses turns, and reduces return or worsens drawdown; concentration and trading constraints can also offset any saved cost. This is one revision to the parent hypothesis, not an independent discovery.

## 4. Detailed Trading Rules

Use the parent fixed M0-qualified set `XSHG:510300`, `XSHE:159915`, `XSHG:518880`, `XSHG:511010`; monthly last open session; `return_sessions=126`; top one; no trend gate, volatility filter, stop, defensive substitution, or position optimizer. On each eligible T-close, compute each rankable ETF's trailing return exactly as the parent implementation: `(last_close - close[-126]) / close[-126]` over its 126 known closes. Sort by descending return, then ascending `InstrumentId`; the first is the leader. An ETF without 126 known closes is excluded from that month's ranking as in the parent. If none are rankable, return typed `NO_DECISION(INSUFFICIENT_HISTORY)`.

- **First entry:** with no positive ETF holding, target today's leader at weight 1. A previous leader is unnecessary.
- **Hold:** with one positive ETF holding, if today's leader is the holding, or a different leader lacks an identical leader on the immediately preceding scheduled month-end, explicitly target the held ETF at weight 1 and explicit zero targets for other currently held ETFs. A valid hold is `TARGETS`, not `NO_DECISION` or cash.
- **Replace:** with one positive ETF holding and a different ETF ranked first at both T and the immediately preceding scheduled month-end, target the new leader at weight 1 and the old holding at weight 0. Confirmation concerns the same ETF identity, not merely “a challenger.” If leaders are A, B, A across three months, no replacement is confirmed at the last month unless the existing holding is already A.
- **Missing prior evidence:** a missing/non-rankable preceding scheduled month-end does not count as a confirming observation. With an existing holding, keep it explicitly. Do not skip over the missing month to make a nonconsecutive pair. If today's ranking itself has no valid leader, use `NO_DECISION(INSUFFICIENT_HISTORY)`; this means no valid decision, even if the engine operationally leaves a position untouched.
- **Exit:** this ungated top-one variant has no signal-driven cash exit. An explicit exit is `TARGETS` with weight 0 for every held instrument, as in the existing gated parent rule; it must never be encoded as `NO_DECISION`. Existing M0 tradability, lot, risk, order and cash constraints can prevent an intended replacement fill. A rejected order does not authorize the strategy to assume it holds the proposed target next month.

The authoritative incumbent is the position actually held in `DecisionContext` after the previous execution, never a cached intended target. If there are multiple positive ETF holdings because of partial/rejected execution, the single-incumbent assumption fails; see Owner decision below. Do not silently choose one by position size or infer it from prior targets.

## 5. PIT / No-lookahead Design

At T-close, `DecisionContext` exposes only market facts known by its information cutoff, current positions, and `bars_for()` history. The frozen market calendar's `month_end_sessions` gives T and its immediately previous scheduled month-end; reconstruct that earlier leader from bars dated at or before that earlier close, applying the earlier PIT information cutoff and the same rank/tie rule. A bar learned only after the earlier cutoff must not retroactively establish that earlier leader. The candidate must not use current T prices to rank the earlier month. The prior month's leader may be computed afresh from PIT history; a mutable per-run leader counter is unnecessary if those historical facts and cutoffs are reproducibly available. If the current `DecisionContext` does not preserve the earlier cutoff's knowability for a late-retrieved/corrected bar, this is a **minimal contract/evidence issue to resolve before implementation**, not permission for hidden state.

Decision at T-close produces a target for T+1, with execution, suspension, minimum lots, fees, slippage, and accounting handled by M0 `DailyBarEngine`. Changing T+1 or later facts must not change T's evaluation. Month-end dates come from the frozen calendar rather than an inferred last date in a truncated price series. M0 handles infeasible orders; the strategy does not inspect future tradability.

## 6. Baseline Comparison and Historical Data Exposure

Compare the single proposed variant to **both** the original `momentum-126` parent and the original four-ETF inception equal-weight buy-and-hold benchmark. Pair the two strategies on 2016-01-04..2022-12-30 with the same PIT universe, physical Basic snapshot digest (`sha256:99a2d581dc1c7fa82f04cd1d18774c4d2da87380b96d394de0a22fa0828aa0b7`), warm-up, calendar, M0 kernel, CNY 100000 initial capital, commission/slippage, benchmark, and metric code. Report paired changes in cumulative turnover, cost drag and total costs, fill count, net return, benchmark-relative total return, maximum drawdown, and failed/rejected orders. Retain every attempt and manifest identity. Do not choose a different parent variant after seeing the comparison.

The Basic history is `EXPLORATORY / PREVIOUSLY_OBSERVED`, even when run under a newly frozen candidate. The project has directly exposed ETF 2023-01-03..2025-12-31 OOS results from another lineage; R2-0B therefore finds `PROJECT_OOS_EXPOSURE=PROSPECTIVE_DATA_REQUIRED`. That interval is not automatically `CLEAN_OOS` for this revision. There is no clean historical ETF OOS established, and this design makes no OOS freeze. A future independently isolated prospective interval requires a separately approved pre-registration, exact data boundary, no prior tuning/exposure, controlled reveal, and a sufficient predeclared observation/trade sample. Basic PASS would be research triage, not independent validation.

## 7. Reusable Architecture and Expected Change Scope

`StrategyContract` and `StrategyEvaluation` can express explicit hold, replace, and typed no-decision. `DecisionContext` provides the current actual holdings and PIT bars. `UniverseView` supplies the same fixed set. `ResearchRunManifest` binds version, parameters, snapshot, benchmark, cost and kernel identities at run time. `DailyBarEngine` handles T+1 execution and ledger accounting; Artifact Catalog retains immutable attempts. The minimal later code scope is a versioned candidate-local ETF strategy and focused tests for first entry, holds, two-month confirmation, ties, missing earlier/current history, failed execution, and future-data invariance. No generic state manager or Research Platform expansion is proposed.

One narrow unresolved interface question is whether the earlier month-end PIT cutoff can be reconstructed exactly from the current context plus frozen calendar when bars have later availability/corrections. Verify that before implementation; if unavailable, propose only the smallest auditable PIT history access for this variant. Multiple positive holdings after an incomplete switch likewise need an explicit policy before freeze.

## 8. Known Limitations and Falsification Criteria

The confirmation period is a single economically motivated hypothesis, not an optimized grid. It adds lag, does not diversify the top-one holding, and cannot fix market risk, data gaps, rejected orders, or the already observed sample's selection bias. A lower fill count need not mean lower turnover or lower cost; position values, partial fills, and minimum commissions matter. The historical Basic interval cannot demonstrate new independent alpha. The product aspiration of 10%–15% annual return and maximum drawdown within 10% remains separate from the original Basic gate and is unproven by a Basic PASS.

Falsify the *turnover/cost mechanism* if paired Basic cumulative turnover fails to fall versus `momentum-126`, or falls without a meaningful reduction in modeled cost, while documenting why. Fail original Basic promotion if any pre-registered gate fails: at least 1500 NAV observations, benchmark-relative total return at least -0.05, maximum drawdown at least -0.40, and cumulative turnover at most 12. Do not recast a gate failure as success because return improves. A future independent OOS verdict needs a separate approved protocol; no historical comparison here is a Survivor claim.

## 9. Owner Review Gate

Review the candidate identity and exact one-variant rule, treatment of multiple actual holdings/partial fills, historical PIT cutoff reconstruction, unchanged four Basic thresholds, and prospective OOS sample/availability protocol. Any threshold change requires an independent economic and risk case, owner approval, and freeze *before* a new run; previously observed results cannot supply that rationale. No runnable CandidateIntent JSON or Basic execution is authorized yet.

## 10. R2-1A Review Addendum

This addendum records the execution, point-in-time, anomalous-holdings, and version-dispatch review. It does not authorize implementation or a run.

### Hold / Rebalance Semantics

The current execution path is `StrategyEvaluation` → `TheoreticalTargetPortfolio` → `RiskTransformation` → `ExecutableTargetPortfolio` → `PendingPlan` → next-session activation and fills/rejections. The research Basic runner constructs the engine with the default identity risk transformation. Target completeness is checked against every positive actual holding before allocation; a missing held-instrument target blocks planning. Allocation sizes from current equity and T-close prices, rounds to the instrument's buy increment, estimates fees including minimum commission, and creates plans only for nonzero quantity deltas. At activation, sells run before buys; buys may be reduced by complete lots to available cash or rejected, while a sell order fills as planned or is rejected.

For the exact single-holding case (positive A only, nonnegative cash, theoretical and approved target A=100%, identity risk transformation), the planned A quantity cannot be below its current quantity. There is therefore no A sell in this narrow state. A BUY for A can still be planned when residual cash is enough for another complete lot plus estimated fees. If it is below one lot or the minimum commission/other fees make the lot unaffordable, no buy is planned; a T+1 price gap can further reduce the submitted buy quantity or cause rejection. Minimum commission is charged per filled order and can consume the cash that appeared sufficient at T-close. This target is not a zero-fill promise.

In this exact single-A state, no B order can be created: neither the theoretical target nor the approved/executable portfolio adds unheld universe members, and the plan builder only visits approved positions and actual holdings. A currently positive B would be a different state; the v2 policy below fails closed on multiple positive ETF holdings before constructing a target. A downstream risk cap can reduce an approved weight and produce a sale in pipelines that install such a rule, but that is not the current Basic runner's identity-risk path.

The hold wording is fixed to: “未确认新的连续领先者时，继续维持原 ETF 为唯一目标标的，目标权重 100%，由 M0 处理可能的再平衡。” This means `TARGETS(A=1)`, never `NO_DECISION` as a zero-trade device.

Current reports already expose total fills (`trade_count`), rejections, cumulative turnover, cost drag, and total modeled costs. They do not classify a fill as an ETF replacement or same-instrument rebalance. The minimum candidate-local derived analysis is to retain a decision label (`FIRST_ENTRY`, `HOLD`, or `REPLACE`) and old/new instrument IDs keyed by target ID, then join existing plans, orders, fills, and rejections by target ID. Count fills belonging to the old/new pair as replacement fills, and fills in the retained incumbent during `HOLD` as same-instrument rebalance fills. Continue reporting total fills, turnover, and costs from the existing metrics. Do not change M0 ledgers or create a general trade-analysis subsystem.

### Historical PIT Reconstruction Proof

1. **P cutoff:** the current engine API is `EngineClock.decision_cutoff(P)`. Basic wiring currently creates `EngineClock()` with its default UTC timezone and 15:30 decision time. There is no separate `DecisionClock` type. `month_end_sessions` derives scheduled month ends from the frozen open-session calendar; it does not provide a historical cutoff record.
2. **Later-known facts:** `DecisionContext` is built from bars with `session_date <= T` and `availability.information_known_at(cutoff_T) is True`. `bars_for()` returns this T-known slice. A candidate-local `rank_at(P)` can additionally require `session_date <= P` and `availability.information_known_at(cutoff_P) is True`; `UNKNOWN` must be rejected, not treated as known.
3. **Corrections:** `Availability` can exclude a current bar whose recorded availability time is after P. However, `DailyBar` has no revision history/as-of-value selector and the engine rejects two bars for the same instrument/session as ambiguous. If the T snapshot contains a corrected close but not the pre-correction value available at P, filtering removes the corrected row and cannot recover the old close. A T snapshot digest proves the bytes at T, not the earlier vintage. Exact reconstruction therefore remains blocked for corrected-history cases.
4. **126 known closes:** for each fixed ETF, select 126 distinct close records ending at P that are both in the frozen calendar's session range and known by `cutoff_P`; the 126th most recent eligible close is the base, matching the existing `(last_close - close[-126]) / close[-126]` formula. Any missing or unknown close leaves that instrument unrankable. Ranking uses only eligible instruments and the existing `(-return, InstrumentId)` tie break.
5. **History extent:** `DecisionContext` carries the known bars supplied to the run, through T; it does not truncate history to one lookback. The fixed Basic snapshot's 2015-01-05 warm-up precedes the 2016-01-04 Basic start by about one trading year, enough for the first prior-month window, provided the snapshot actually contains those rows. The generic contract alone does not prove completeness for every P.
6. **Required history declaration:** keep `return_sessions=126`; declare the identity's required history as 126 closes plus the maximum open-session index distance `T_index - P_index` between adjacent scheduled month ends in the frozen calendar. This covers reconstruction at P from a T context. Bind the calendar digest and this value into strategy identity; reject a context that lacks the full range rather than silently shortening it.
7. **Proof of equality:** for every scheduled month end, retain candidate-local evidence containing P, reconstructed cutoff timestamp/timezone, snapshot/vintage digest, sorted instrument IDs, the 126 selected bar identities and per-bar availability decisions, computed returns, tie-break order, and resulting leader. At a later T, recomputation of P must yield the same evidence digest as the evidence retained when P was evaluated live. This proves deterministic replay only when the cited digest identifies the actual P-time price vintage.

`ResearchRunManifest` binds a snapshot digest and code/kernel identities, while `DataSnapshotManifest` binds one snapshot-level `knowledge_cutoff` and artifact digests. Neither supplies a sequence of historical cutoffs plus historical price vintages to `DecisionContext`. The minimum blocker-resolution artifact is a candidate-local, versioned historical-cutoff evidence manifest bound to the calendar digest, exact `EngineClock` cutoff profile, and an immutable P-time snapshot/vintage digest for every ranked month. Where a snapshot does not preserve the pre-correction value, that vintage must be obtained from the immutable source archive; a digest over the current corrected value is insufficient. Until this evidence is available and passes the equality test, `PIT_RECONSTRUCTION = BLOCKED`; do not create a formal CandidateIntent.

### Multiple Holdings Fail-Closed Policy

At every engine evaluation, inspect actual positive CORE ETF positions first. The only state used as incumbent is the actual `DecisionContext.positions` set. If more than one fixed-universe ETF is positive, or any positive CORE ETF is outside the current universe, raise a candidate-local typed `PersistenceExecutionStateError` with a stable reason code and sorted actual instrument/quantity evidence. Never pick the largest holding, infer an incumbent from a prior target, or emit a cash target.

To distinguish a rejected/partial switch from a clean first entry, v2 may keep only a candidate-local pending-execution assertion (`expected_instrument_set`, target ID, and decision label) after a first-entry or replacement target as a diagnostic. After every subsequent engine activation, compare actual positions with that assertion before making another strategy decision. Clear it only when actual positive ETF membership equals the intended singleton. A mismatch raises the same typed failure; the assertion is never used to choose an incumbent or to fabricate holdings. This detects (D) A sold/B buy rejected (zero actual ETFs), (E) A sale rejected/B buy filled (A and B both positive), and (F) a residual A plus reduced B buy (multiple positions or a set mismatch). M0 activation sells the complete planned quantity or rejects it; it does not partially fill a sell order. A synthetic F fixture must model an executable lot-constrained reduction that leaves A positive, not fabricate a partial sell fill. It also fails (G) pre-existing multiple holdings and (H) a positive ETF outside the current universe. The D–H failure aborts the variant at the next post-activation evaluation, is retained as `RUN_FAILED_KERNEL` with the exception/reason in Research evidence, and cannot produce `BASIC_PASS`. A `NO_DECISION` is not used for these cases.

(A) No holding is a first entry and targets today's leader at 100%. (B) With only A held and B leading for one month, A remains the sole 100% target. (C) With only A held and B leading at both consecutive month ends, request replacement to B; actual holdings after execution are checked by the pending-switch assertion. (I) If today's ranking has no eligible ETF, retain `NO_DECISION(INSUFFICIENT_HISTORY)` and its evidence; if only P's rank is unavailable, do not confirm replacement and explicitly target the actual incumbent at 100%. A missing P is not skipped. Report these typed no-decision reasons separately from holds and execution-state failures.

### Version Dispatch Design

Current `build_canonical_strategy` dispatches on `strategy_id` only. `CandidateIntent` has no strategy-version field, and the current ETF relative-momentum module declares `v1`; thus the current interface cannot select two implementations for the same ID. The minimal extension is an optional pre-code `strategy_version` field on a newly authored intent. Legacy payloads that omit it resolve explicitly to `v1` without rewriting their JSON bytes or digest; the new R2 intent declares `v2`, which is covered by its own canonical intent digest.

Change the canonical registry key to `(strategy_id, strategy_version)`. Keep `("etf-relative-momentum", "v1")` bound to the existing `etf_relative_momentum.py` builder and do not edit that file. Add an independent `etf_relative_momentum_v2.py` implementation for the v2 builder and digest the bytes at that canonical source path. Unknown pairs fail closed; never fall back from an unknown version to the only registered version. Keep the strategy ID and version in `StrategyIdentity` and `ResearchRunManifest`. The existing source-identity test should prove that the old intent resolves to the exact v1 module digest; the new test should prove v2 resolves to the new file digest. Historical stored artifacts remain unchanged, and replaying a legacy intent must preserve v1 target/fill/ledger behavior; the new code commit naturally gives any newly created replay manifest a new run identity.

### Implementation Test Matrix

R2-2 must test complete state transitions through `StrategyTargetSource` and `DailyBarEngine`, including actual positions, targets, pending plans, fills/rejections, and retained run evidence. A strategy-return-symbol assertion alone is insufficient.

| Case | Synthetic setup and required assertion |
| --- | --- |
| 1. First entry | No positive ETF position → current leader targeted at 100% → actual first fill/position checked. |
| 2. Leader persists | A is held and remains leader → target A=100%; verify no ETF replacement and allow any M0 same-instrument rebalance. |
| 3. Leader changes once | A held; B leads at T but not P → target remains A; no B order. |
| 4. Two consecutive leaders | A held; B leads at P and T → plans/fills/rejections and resulting actual positions establish replacement outcome. |
| 5. A→B→A reversal | No two consecutive B leaders at the final A observation → no confirmed replacement to A; test against actual incumbent. |
| 6. Missing prior month | P absent or unrankable → no confirmation; incumbent remains explicit A=100%. |
| 7. Future-bar mutation | Change bars after T; T evaluation, target digest, and plan stay identical. |
| 8. Late availability / corrected history | Later-known bar excluded at P; corrected old value without a retained vintage yields typed PIT blocker, never a guessed rank. |
| 9. Multiple holdings | Seed A+B or an out-of-universe positive ETF → typed fail-closed evidence; no target, orders, or Basic pass. |
| 10. Rejected / reduced quantities | Exercise D/E via real activation rejections/fills and F via lot-constrained residual A plus a reduced B buy; assert sell fills are all-or-none and the pending-execution assertion detects zero, multiple, and residual/mismatched positions. |
| 11. Target completeness | Every positive actual holding is explicitly addressed on an ordinary single-holding path; incomplete targets block before planning. |
| 12. v1/v2 dispatch | Legacy intent → v1; explicit v2 intent → v2; unknown version → fail closed. |
| 13. Immutable identity | Legacy intent bytes/digest and v1 implementation digest are unchanged; v2 digest equals its source file bytes. |
| 14. Deterministic replay | Repeated synthetic run yields identical decision evidence, target/plan digests, fills, rejections, and ledgers. |

Current offline M0/contract tests verify existing availability filtering, target completeness, risk conversion, lot/fee handling, and activation behavior, but they do not implement or prove the proposed v2 transitions. The focused command and result are recorded in the paired pre-registration draft. No raw market snapshot, new OOS data, or real backtest was opened or run for this review; only the prescribed existing research documents and report evidence were read.

## 11. R2-1A Gate

```text
R2_1A_HOLD_SEMANTICS = PROVEN
R2_1A_PIT_RECONSTRUCTION = BLOCKED
R2_1A_MULTIPLE_HOLDINGS_POLICY = RESOLVED
R2_1A_VERSION_ISOLATION = BLOCKED
R2_1A_DESIGN_GATE = BLOCKED
CANDIDATE_INTENT = DRAFT_ONLY
BASIC_EXECUTION_AUTHORIZED = NO
CLEAN_OOS_AVAILABLE = NO
M2_ENTRY_GATE = BLOCKED
```

The remaining blockers are historical corrected-price vintages plus cutoff evidence, and implementation/tests for version-aware dispatch and the candidate-local execution-state assertion. Proceed only with that minimum local evidence/implementation scope after Owner Review; do not create an executable intent before PIT reconstruction is proven.
