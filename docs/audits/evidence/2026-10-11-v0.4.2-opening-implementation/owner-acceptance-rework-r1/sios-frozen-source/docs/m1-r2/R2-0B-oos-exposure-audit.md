# R2-0B Project-level OOS Exposure Audit

## Decision

```text
PROJECT_OOS_EXPOSURE = PROSPECTIVE_DATA_REQUIRED
```

The project does not currently prove a clean historical OOS interval for an
R2 ETF candidate.  This is not a claim that every future research datum is
contaminated: it is a conservative conclusion about the evidence available to
this review.  The known 2023--2025 ETF OOS window has been directly revealed,
executed, reported, and made researcher-visible; the already-used Basic
history is validation evidence, not a new independent holdout.  A future,
pre-registered prospective period can create new independent evidence, but a
short forward observation is not automatically sufficient for full OOS
qualification.

## Method and boundary

The audit used only metadata, immutable catalog entries, intents, freeze,
reveal, recovery, result, verdict, outcome, retained reports, and research
records under `var/research/task9-experiments-v2`.  It did not open a raw OOS
market snapshot, materialize data, run a backtest, create a freeze, reveal
data, or alter evidence.

The audit focus is `2023-01-03` through `2025-12-31`.  All four M1 candidate
intents request this same OOS range.  Their Basic ranges end on `2022-12-30`:

| Lineage | Asset | Basic range | Requested OOS range |
| --- | --- | --- | --- |
| `m1-etf-absolute-trend` | ETF | 2016-01-04 .. 2022-12-30 | 2023-01-03 .. 2025-12-31 |
| `m1-etf-relative-momentum` | ETF | 2016-01-04 .. 2022-12-30 | 2023-01-03 .. 2025-12-31 |
| `m1-stock-breakout` | STOCK | 2019-01-02 .. 2022-12-30 | 2023-01-03 .. 2025-12-31 |
| `m1-stock-relative-strength` | STOCK | 2019-01-02 .. 2022-12-30 | 2023-01-03 .. 2025-12-31 |

## Exposure map

### Lineage-level evidence

| Lineage | Formal OOS status | Exposed dates / information | Classification |
| --- | --- | --- | --- |
| `m1-etf-absolute-trend` | Freeze 66, reveal 67, recovery 68, run 69, verdict 70, outcome 71 | Full 2023-01-03 .. 2025-12-31 OOS performance and rule verdict. Result reports total return `-0.2127979`, benchmark return `0.2060281`, excess return `-0.4188260`, maximum drawdown `-0.3712689904098194154054474008`, 12 trades, and `REJECTED_OOS`. | Directly exposed |
| `m1-etf-relative-momentum` | `NO_BASIC_PASS`; no freeze, reveal, run, verdict, or asset outcome | Its OOS date request is present in the frozen intent, but no OOS snapshot or performance record was opened for this lineage. | No lineage-level OOS exposure proven |
| `m1-stock-breakout` | `NO_BASIC_PASS`; no OOS lifecycle | OOS request exists in the intent only. Basic report result dates end no later than 2022-12-30. | No lineage-level OOS exposure proven |
| `m1-stock-relative-strength` | `NO_BASIC_PASS`; no OOS lifecycle | OOS request exists in the intent only. Basic report result dates end no later than 2022-12-30. | No lineage-level OOS exposure proven |

The recovery is not a second OOS disclosure.  Its structural payload binds the
already-known freeze to the Basic warm-up digest and contains no OOS returns or
signals.  It remains material evidence that the original ETF lineage was
operationally exposed before its terminal run.

### Project-level and researcher-visible exposure

| Interval / information | Evidence | Exposure class | R2 implication |
| --- | --- | --- | --- |
| ETF 2023-01-03 .. 2025-12-31 performance | ETF `result.json`, `verdict.json`, `outcomes/ETF.json`, catalog 69--71 | Direct | Cannot be an independent historical ETF OOS for a new R2 candidate. |
| ETF conclusion and gate anatomy | OOS result names the failed excess-return gate and reports drawdown, returns, turnover, observations, cost, and benchmark return | Direct | A researcher can favor or avoid rules, assets, parameters, cadence, or risk-off behavior based on that outcome. |
| Terminal acceptance conclusion | Historical recovered report on reachable branch `codex/m1-recovery-final`, plus the retained pre-terminal failure reports | Indirect-to-direct conclusion exposure | Even without opening raw bars, the terminal conclusion can influence candidate selection and evaluation expectations. |
| ETF Basic history through 2022-12-30 | Immutable Basic manifests/results/reports and selections | Previously used research/selection data | Usable only as Basic or exploratory historical validation; not new independent OOS. |
| Stock Basic history through 2022-12-30 | Immutable stock runs/reports/selections | Previously used research/selection data | Usable only as Basic or exploratory historical validation; not new independent OOS. |
| Stock 2023-01-03 .. 2025-12-31 raw performance | No stock reveal/result/verdict/outcome record in the actual root | Insufficient evidence | The audit cannot call it clean: there is no evidence of complete project-wide non-exposure, isolated snapshots, pre-registration, or cross-lineage selection independence. |
| Data after 2025-12-31 | Not present as a materialized/revealed R2 holdout in this audit | Not yet evidenced | May support prospective validation only after a new pre-registration, a physical isolation boundary, and adequate observation/trade sample. |

The direct ETF disclosure creates project-level selection-contamination risk
for R2 ETF work even if a new candidate, lineage, or freeze ID is assigned.
Those identifiers create artifact identity, not information independence.  The
evidence does **not** establish that all stock returns or every future period
were viewed, so it would be equally unsupported to label the entire project
permanently contaminated.

## New-OOS availability assessment

| Status | Assessment | Basis |
| --- | --- | --- |
| `CLEAN_OOS_AVAILABLE` | Not established | No interval in the audit has evidence for all of a defined data range, non-use in selection/tuning, no relevant cross-lineage researcher exposure, effective physical isolation, and sufficient pre-registered observation/trade sample. |
| `HISTORICAL_VALIDATION_ONLY` | 2015-01-05/2016-01-04 through 2022-12-30 Basic material; and 2023-01-03 through 2025-12-31 for historical descriptive analysis after disclosure | These intervals are already visible to the researcher.  They may support screening, Basic, or exploratory work, but no independent OOS claim. |
| `PROSPECTIVE_DATA_REQUIRED` | Current project-level decision | No evidenced clean historical R2 ETF OOS exists.  Future daily data can become independent only after R2 candidate/parameters/gates and required sample are pre-registered before it is observed. |
| `INSUFFICIENT_EVIDENCE` | Applies to unshown stock OOS non-exposure and any assertion about unseen data outside the audit root | Absence of a stock result is not proof of full project-level non-exposure or of a physically isolated, adequate holdout. |

For a future candidate, `CLEAN_OOS_AVAILABLE` requires documented proof of all
five conditions, not merely a new `candidate_id`, `lineage_id`, or `freeze_id`:

1. Exact date range and snapshot population;
2. No use in R2 candidate selection, implementation choices, or parameter/gate tuning;
3. No relevant cross-lineage report or researcher-visible performance exposure;
4. Effective physical snapshot separation and controlled reveal; and
5. Pre-registered observation and trade-sample sufficiency.

## Existing isolation controls

The current Research CLI and materialized-snapshot contracts already provide
the controls required for R2; this audit finds no evidence that a new OOS
platform is needed.

```text
NO_NEW_OOS_INFRASTRUCTURE_REQUIRED
```

| Control | Current evidence |
| --- | --- |
| Pre-freeze Basic boundary | `validate_basic_snapshot` refuses rows after `basic_end`, requires the physical endpoint and warm-up coverage, constrains asset authority, and checks snapshot quality. |
| Physical OOS boundary | Current OOS verifier tests and retained frozen split/snapshot digests protect the requested OOS interval from Basic access. |
| Frozen candidate identity | Freeze binds intent, implementation, parameters, universe, benchmark, cost specification, split, Basic selection, and kernel identity. |
| Canonical single verdict | `require_no_existing_verdict`, result/verdict persistence, and the catalog's sequence 69/70 prevent a second canonical OOS conclusion for the freeze. |
| Reveal persistence before execution | Catalog sequence 67 and the OOS design require the persisted reveal before OOS snapshot opening/execution. |
| Controlled recovery | Sequence 68 permits exactly the freeze-bound Basic warm-up with equality proof, preserving the original reveal and refusing a new recovery kind. |
| Tamper detection | `verify --root var/research/task9-experiments-v2` freshly returned `PASS` with `findings=[]`; 36 focused OOS/basic-boundary tests passed. |

These controls prevent new hidden data access; they cannot make information
already seen by researchers unseen.  R2 should retain them and add only a
research-protocol exposure declaration/pre-registration record, not a new
data-permission platform or database.

## Reusable R2 capability and genuine blockers

| Capability | Reuse assessment |
| --- | --- |
| `CandidateIntent`, `StrategyContract`, cheap screen, Basic backtest, pre-registration, immutable experiment directories, artifact catalog | Reusable for a new ETF R2 candidate. |
| Deterministic replay, OOS freeze, controlled materialization, historical kernel replay, no-lookahead/boundary verification | Reusable; focused verification passed. |
| Reporting | Existing historical reporting format exists on an unmerged branch, but current `main` lacks `acceptance-report` / `render-report`; this blocks fresh close-out report regeneration, not ETF Basic research. |
| Stock identity | `docs/m1/M1_STOCK_PIT_IDENTITY_WAIVER.md` remains a separate historical PIT identity limitation.  It is not a reason to build a full stock identity platform before ETF R2, but it blocks treating a stock R2 result as fully identity-clean without additional owner-approved evidence. |

The only true blocker to a credible **ETF R2 independent OOS** is the absence
of an evidenced clean historical holdout; use a sufficiently long,
pre-registered prospective window.  It does not block ETF R2 Basic/exploratory
research.

## Review gate

```text
PROJECT_OOS_EXPOSURE = PROSPECTIVE_DATA_REQUIRED
ETF_R2_BASIC_READINESS = READY
ETF_R2_OOS_READINESS = BLOCKED
STOCK_R2_READINESS = BLOCKED
SURVIVOR_COUNT = 0
M2_ENTRY_GATE = BLOCKED
```

`ETF_R2_OOS_READINESS` is blocked until a candidate-specific prospective
protocol proves the five clean-OOS conditions and reaches its declared sample.
`STOCK_R2_READINESS` is blocked by both the lack of proven project-level clean
OOS and the retained PIT identity limitation; it does not authorize a stock
platform expansion in this task.
