# R2-1 Candidate Pre-registration Draft — ETF Relative Momentum Persistence

**DESIGN DRAFT / NOT AN APPROVED OR EXECUTABLE `CandidateIntent`.** Owner Review Gate is required before creating a final JSON identity or running Basic. No OOS freeze is proposed.

## 1. Candidate identity, lineage, attempt history

| Field | Draft proposal |
| --- | --- |
| `intent_id` | `m1-etf-relative-momentum-persistence-v1` (new identity; reserve only after approval) |
| `lineage_id` | `m1-etf-relative-momentum` (same economic hypothesis family) |
| `strategy_id` / version | `etf-relative-momentum` / proposed `v2`; implementation digest unknown until code exists |
| Asset / sleeve / cadence | ETF / CORE / `MONTHLY_LAST_SESSION` |
| Parent experiment | `m1-etf-relative-momentum-v1`, `var/research/task9-experiments-v2/m1-etf-relative-momentum` |
| Parent Basic outcome | `NO_BASIC_PASS`; `momentum-126`, `momentum-252`, `momentum-126-gate` all `REJECTED_BASIC` on turnover > 12 |
| Previous OOS exposure | Parent lineage has no OOS run; project-level ETF 2023-01-03..2025-12-31 was revealed and run in the absolute-trend lineage. `PROSPECTIVE_DATA_REQUIRED`. |
| New attempt history | One proposed persistence variant only. On later approval, retain all parent attempts and every new screen/Basic/error record append-only; never overwrite parent results. |

Revision reason: test whether a two-effective-month-end leader confirmation prevents costly reversals without discarding medium-horizon relative rotation. Original parent intent and failed evidence remain immutable. The parent `momentum-126` is the predeclared first-priority base; no parameter was selected for its observed performance.

## 2. Exact rule pseudocode (proposal)

```text
Inputs: T-close DecisionContext, frozen month-end schedule, fixed UniverseView.
At every session, validate any pending-execution assertion against actual positive
ETF positions before any month-end check. On mismatch, raise typed
PersistenceExecutionStateError; never use the assertion as an incumbent.
If actual positive ETF holdings are multiple or outside the current universe:
    raise PersistenceExecutionStateError with actual IDs and quantities.
If not a scheduled decision session: NO_DECISION(NOT_DECISION_SESSION).

rank_at(D, cutoff_D):
    For each of the four fixed ETFs, take only bars dated <= D and
    information_available_at <= cutoff_D.
    If fewer than 126 known closes, exclude that ETF.
    r = (last_close - close[-126]) / close[-126].
    Sort by (-r, InstrumentId); return first ETF or NONE.

leader_T = rank_at(T, cutoff_T).
If leader_T is NONE: NO_DECISION(INSUFFICIENT_HISTORY).

held = actual positive ETF positions in DecisionContext, not prior targets.
If len(held) == 0:
    TARGETS(leader_T = 1).
    retain a diagnostic pending-execution assertion for the intended singleton.

incumbent = only held ETF.
If incumbent == leader_T:
    TARGETS(incumbent = 1)  # M0 handles possible same-instrument rebalancing.
Else:
    P = immediately preceding scheduled month-end (never skip a month).
    leader_P = rank_at(P, cutoff_P) using only facts knowable then.
    If leader_P == leader_T:
        TARGETS(leader_T = 1, incumbent = 0).
        retain a diagnostic pending-execution assertion for the intended singleton.
    Else:
        TARGETS(incumbent = 1).
No other positive holding is accepted; anomalous holdings fail closed above.
Do not create a signal-driven cash exit. A valid hold uses the owner wording:
“未确认新的连续领先者时，继续维持原 ETF 为唯一目标标的，目标权重 100%，由 M0 处理可能的再平衡。”
T-close target is executed by M0 no earlier than T+1.
```

`rank_at` uses the parent formula and tie-break, including parent behavior of excluding an ETF with insufficient history. An invalid preceding month cannot confirm a replacement. `TARGETS(incumbent=1)` is an explicit hold, distinct from `NO_DECISION` and from `TARGETS(incumbent=0)` cash exit. Actual holdings remain authoritative; a pending-execution assertion is diagnostic only and cannot substitute for them. Historical month-end cutoffs must be provably reconstructed; see the R2-1A addendum.

## 3. Proposed parameters and rationale

Only one proposed variant, tentatively `momentum-126-persistence-2`: `return_sessions=126`, `leader_confirmation_month_ends=2`, `top_n=1`, no `trend_gate_sma_sessions`. The 126-session lookback is the parent's original first-priority rule. Two consecutive effective monthly leaders express a minimal persistence hypothesis; they are not chosen from a confirmation-length grid or from prior observed returns. Monthly decision frequency and stable `(-return, InstrumentId)` rank order remain unchanged. First entry uses today's leader immediately; confirmation is only for replacing an actual holding.

## 4. Universe, benchmark, cost and data

- Fixed `ETF_FIXED_QUALIFIED_V1`: `XSHG:510300`, `XSHE:159915`, `XSHG:518880`, `XSHG:511010`, with the original PIT qualification and no reconstitution.
- Benchmark: `ETF_UNIVERSE_EQUAL_WEIGHT`, same four instruments, `INCEPTION` equal-weight buy-and-hold under the same M0 kernel. The original `momentum-126` is a second, paired mechanism baseline; it does not replace the benchmark.
- Initial capital: CNY 100000. Commission rate `0.00025`, minimum commission CNY `5`, slippage rate `0.0005`; retain original M0 cost, tradability, lot, and accounting semantics. Zero-yield `CASH_0` is an explicit exit destination only, not a defensive ETF substitution.
- Warm-up start `2015-01-05`. Basic interval `2016-01-04..2022-12-30`, return basis `DAILY_CLOSE_TO_CLOSE`, annualization sessions `252`. Use the same physically bounded Basic snapshot, calendar, PIT universe, execution kernel, benchmark and metric definitions as the parent paired comparison. This interval is `EXPLORATORY / PREVIOUSLY_OBSERVED` and cannot supply independent validation.

## 5. Proposed Basic promotion criteria

Retain the parent values and metric semantics unchanged for comparability:

| Gate | Threshold | Rule |
| --- | ---: | --- |
| `min_nav_observations` | 1500 | `>=` |
| `min_excess_total_return_vs_benchmark` | -0.05 | `>=`, net strategy minus same-kernel benchmark total return |
| `max_drawdown_floor` | -0.40 | `>=`, negative drawdown convention |
| `max_turnover` | 12 | `<=`, cumulative `0.5 × (absolute buy + sell consideration) / mean observed equity` over Basic |

These are suitable as *unchanged exploratory triage gates*, because the mechanism remains the same top-one ETF rotation and the original comparison is required. They are **not** fresh statistically independent thresholds: all parent results are known, including the failing turnover values. A PASS would indicate that this revised candidate clears the legacy Basic gate on observed history, not new OOS evidence or achievement of the final product target. Do not adjust the thresholds to rescue it. Any proposed change needs separate economic and risk grounds, explicit owner approval, and pre-run freeze. Product aspiration: 10%–15% annual return and maximum drawdown within 10%; this is not a Basic gate and is not a demonstrated capability.

## 6. OOS availability and later validation

`CLEAN_OOS_AVAILABLE=NO`. The parent lineage has no OOS attempt, but the project directly revealed ETF results for 2023-01-03..2025-12-31. That range cannot be silently reused as clean R2 OOS. Future independent testing requires prospective data after candidate/rules/gates/sample are pre-registered, physical isolation, a controlled reveal, and enough predeclared observations and trades. No exact future OOS dates, sample threshold, survivor gate, or freeze identity is asserted by this draft. Basic execution and OOS execution remain unauthorized.

## 7. Source and provenance

Primary sources: `docs/personal-systematic-investing-os-v0.9-flight-test-driven-product-architecture.md`; `docs/m1/strategy-research-protocol.md`; `docs/m1/M1-architecture.md`; `docs/m1/M1-test-plan.md`; `docs/m1/OPEN_QUESTIONS.md`; original frozen `research/candidates/m1-etf-relative-momentum-v1.json`; current strategy and tests; each original Basic `runs/<run-id>/report.json`, `result.json`, and `manifest.json`; `basic-selection/40ec177849142acf.json`; `docs/m1-r2/R2-0B-terminal-evidence-closeout.md`; `docs/m1-r2/R2-0B-oos-exposure-audit.md`. Experiment root is `var/research/task9-experiments-v2`. The persistence rule is a project-local revision motivated by recorded parent turnover failure; no external code or text is incorporated. Source identity and attempt/exposure declarations must be copied into the later approved CandidateIntent and research record without overwriting originals.

`StrategyContract`, `StrategyEvaluation`, `UniverseView`, `ResearchRunManifest`, `DailyBarEngine`, and Artifact Catalog are reusable. The future smallest implementation is a versioned candidate strategy plus focused tests and an approved frozen intent. No general state framework or CLI report-command repair belongs to this candidate design.

## 8. `OWNER_DECISION_REQUIRED` before a runnable freeze

1. Approve the proposed new candidate ID, `v2` strategy identity, single `126 × 2` variant and unchanged parent Basic gate. A changed gate must have an independent economic/risk rationale and be frozen before any run.
2. The R2-1A design resolves multiple actual holdings with a candidate-local typed fail-closed policy; implementation and synthetic execution-path tests remain required before freeze. No incumbent repair or generic state manager is proposed.
3. PIT reconstruction is currently blocked for corrected bars when the P-time value is not retained. Prove historical vintages and cutoff equality, or approve the minimal candidate-local cutoff/vintage evidence described below before creating a formal intent.
4. Define a separate candidate-specific prospective OOS interval, observation/trade sufficiency, and survivor gates when future data is available. The known 2023–2025 period is already exposed; no OOS freeze is authorized here.

After Owner Review Gate, create and freeze a new CandidateIntent before implementation or Basic, then bind implementation/data/kernel digests in `ResearchRunManifest` at run time. This Markdown draft is not a substitute for those controls.

## 9. R2-1A Review Addendum — DRAFT ONLY

This review does not create or authorize a runnable CandidateIntent. The current `main` HEAD reviewed was `9e1d44fc4052fb6366ff49008b1436e1d29010f1`; the worktree was clean before these documentation changes.

### Hold / Rebalance Semantics

Under the current Basic wiring, a single actual A holding with nonnegative cash and approved target A=100% cannot produce an A sell: M0's target quantity is based on total equity and cannot be below the existing quantity in that state. It can produce an A buy when residual cash covers a complete lot plus estimated fees. Lot rounding may suppress a buy below one increment, minimum commission can make a lot unaffordable, and a T+1 price gap may reduce a buy to fewer complete lots or reject it. M0 runs sells before buys, but the exact single-A state contains no B sell or buy: unheld universe members are not added to the executable portfolio. So `TARGETS(A=1)` does not guarantee zero fills, and the accepted rule allows normal same-instrument M0 processing.

The current summary report distinguishes total fills, rejection count, cumulative turnover, cost drag, and total costs. It does not distinguish ETF replacement from same-instrument rebalance. A narrow post-run analysis should join a candidate-local `FIRST_ENTRY`/`HOLD`/`REPLACE` decision record and old/new symbols to existing plans, orders, fills, and rejections using `target_id`. It should report replacement fills, same-instrument rebalance fills, all fills, cumulative turnover, and modeled costs without changing M0 or creating an analysis platform.

### Historical PIT Reconstruction Proof

The earlier decision cutoff is computed as `EngineClock.decision_cutoff(P)` from the run's frozen clock configuration; current Basic wiring uses the default UTC 15:30 cutoff. `month_end_sessions` identifies P from the frozen open-session calendar. At T, `DecisionContext` only guarantees facts were available by T. For reconstruction, candidate-local `rank_at(P)` must also require `bar.session_date <= P` and `bar.availability.information_known_at(cutoff_P) is True`; unknown availability fails closed. Use the 126 latest eligible closes for each instrument and the original return formula/tie-break. The identity history declaration must cover 126 closes plus the maximum open-session index distance `T_index - P_index` between adjacent scheduled month ends.

Current `DataSnapshotManifest` binds one snapshot-level knowledge cutoff and artifact digest. `DailyBar` carries availability but no historical revision selector, and M0 rejects duplicate bars per instrument/session. A corrected value learned after P can be filtered out, but if the older P-time value is absent from an immutable vintage, filtering cannot restore it. Therefore the equality proof against the ranking recorded at P is not currently available for corrected history. Before a formal intent, provide candidate-local versioned evidence binding P, exact cutoff/timezone, calendar digest, P-time snapshot/vintage digest, the selected 126 bar identities/availability, scores, ranking, and leader. Reconstruct P at later T and assert the evidence digest equals the one recorded at P. If the P-time price vintage cannot be produced, keep `PIT_RECONSTRUCTION=BLOCKED` and do not create the formal intent.

The fixed Basic history begins its warm-up on 2015-01-05 for a 2016-01-04 Basic start and should contain enough range for the first two-month comparison if all snapshot rows are present. `DecisionContext` carries all supplied bars through T, but this extent and completeness are not established solely by `required_history_sessions`; the proposed identity value and snapshot coverage must be checked explicitly.

### Multiple Holdings Fail-Closed Policy

At every engine evaluation, use actual positive CORE ETF holdings as the only possible incumbent. More than one positive ETF, or any positive ETF outside the current universe, raises candidate-local `PersistenceExecutionStateError` with stable reason code and sorted actual IDs/quantities. Do not select a largest position, substitute a previous expected target, emit cash, or call it a hold.

For execution diagnostics only, v2 may retain a pending-execution assertion keyed by target ID (intended singleton, decision kind) after first entry or replacement. On each post-activation evaluation, compare it with actual positive positions and clear it only after the actual singleton matches. It never supplies the incumbent. A sold-A/buy-rejected-B outcome is zero actual ETFs; a rejected A sale plus filled B buy yields multiple. M0 activation sells the full planned quantity or rejects it; it does not partially fill a sell order. Model F as a lot-constrained planned reduction that leaves positive A while B is reduced to affordable lots, not as a fabricated partial sell fill. Each D–H case therefore raises the typed failure at the next post-activation evaluation, aborts the one-variant run as `RUN_FAILED_KERNEL`, is retained in Research evidence, and cannot produce `BASIC_PASS`. Do not encode these failures as `NO_DECISION`.

Synthetic state table required before R2-2 freeze:

| Case | State and outcome |
| --- | --- |
| A | No holding: target the current leader at 100%; verify the actual entry fill/position. |
| B | Only A held, B leads for one month: target A at 100%; verify no B order. |
| C | Only A held, B leads at P and T: request B replacement; verify actual positions after execution. |
| D | A sale succeeds, B buy fails: zero actual ETFs mismatches the pending singleton; typed failure. |
| E | A sale fails, B buy succeeds: A+B actual holdings; typed failure. |
| F | Lot-constrained plan leaves A positive while B is reduced to affordable lots: residual/multiple set mismatch; typed failure. |
| G | Multiple positive actual ETFs at evaluation start: typed failure. |
| H | Positive holding is outside current universe: typed failure. |
| I | Current ranking insufficient: retain `NO_DECISION(INSUFFICIENT_HISTORY)` with evidence; missing/unrankable P cannot confirm a switch and keeps the actual incumbent at 100%. |

### Version Dispatch Design

The current canonical builder dispatches only by strategy ID, and CandidateIntent carries no strategy version. Add an optional pre-code `strategy_version` field to new intents, with legacy payloads that omit it resolving to v1 without changing their stored bytes or canonical digest. The proposed new intent explicitly declares v2 and includes that field in its new digest. Dispatch by the exact `(strategy_id, strategy_version)` pair: legacy ETF relative momentum v1 remains mapped to the untouched `etf_relative_momentum.py`; v2 maps to an independent `etf_relative_momentum_v2.py`, whose actual bytes supply its implementation digest. Unknown pairs fail closed. Stored v1 artifacts remain untouched; replay under a new code commit gets a new manifest identity but must reproduce v1 decisions/fills/ledgers exactly on the same inputs.

### Implementation Test Matrix

R2-2 synthetic tests must drive `StrategyTargetSource` and `DailyBarEngine` through full position → evaluation → target → plan → activation → fill/rejection transitions. Add the following beyond the A–I exception/transition cases above:

1. First entry; leader persists with a possible same-instrument rebalance; one-month leader change; two consecutive leaders; A→B→A reversal; missing prior month.
2. Future-bar mutation invariance; late availability and corrected-history vintage behavior; multiple holdings; rejected/reduced quantities (sell all-or-none, buy reduced by lots); target completeness.
3. Legacy v1/v2 dispatch; immutable legacy intent and v1 digest; deterministic replay of evaluation evidence, target/plan digests, fills, rejections, and ledgers.

The current offline tests were run with:

```text
python -m pytest tests/component/test_no_lookahead.py tests/research/test_etf_candidate_specs.py tests/research/test_strategy_source_identity.py tests/component/test_execution_accounting.py tests/unit/test_allocation.py tests/unit/test_risk_decisions.py tests/unit/test_target_portfolio.py -q
85 passed in 0.25s
```

These existing tests exercise current M0 and contract behavior only. They do not instantiate v2 or prove its transition matrix; that requires the focused implementation tests before a future Owner Review.

## 10. R2-1A Gate — DRAFT ONLY

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

Remaining blockers: no proven archive for corrected P-time price vintages; version-aware dispatch and the candidate-local post-activation assertion are proposed but not implemented/tested. The minimal future scope is the local PIT evidence interface, isolated v2 module, version-keyed dispatch, candidate-local execution-state diagnostics, report-derived trade classification, and the listed synthetic tests. Do not create an executable JSON until PIT reconstruction is proven and Owner Review is complete.
