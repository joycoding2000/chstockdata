# M1 First Strategy Flight Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the smallest repeatable ETF/Stock research loop that produces real-data Basic Backtests early, physically withholds OOS data until freeze, and records either an honest OOS verdict or `NO_OOS_ELIGIBLE_CANDIDATE`.

**Architecture:** Add a Research-only package that adapts a typed `StrategyContract` to the existing M0 `DecisionContext`/`DailyBarEngine`. Freeze a pre-code `CandidateIntent`; bind implementation, code, actual snapshot, universe, benchmark and kernel identities later in `ResearchRunManifest`. Persist immutable run directories plus a thin append-only catalog. Basic and OOS are separate physical snapshots; only an owner-controlled materializer may expose OOS after freeze.

**Tech Stack:** Python 3.12+, standard-library dataclasses/Protocols/JSON/hashlib/argparse, existing M0 kernel, pytest, Ruff, strict mypy for new Research code.

---

## 0. Entry gate and non-negotiable rules

- Do not change frozen M0 financial semantics to improve a strategy result.
- Preserve the current M0 baseline: 553 offline tests; 25 qualification/parity passes with 5 explicit live-only skips; Ruff PASS.
- Do not refactor the 90 known whole-repository mypy findings. New `research` code must be strict-clean.
- Runtime dependencies remain empty; use canonical JSON and local immutable directories.
- Every Task starts with a failing test, records exact evidence, and ends with a focused commit.
- Research actor/Agent must not have the provider raw tree, cache, credential, or a snapshot containing OOS rows mounted before OOS freeze.
- If no candidate passes Basic, finish with `NO_OOS_ELIGIBLE_CANDIDATE`; do not add strategies until one “wins.”
- Generated market data and experiment artifacts live under `var/research/` and are not committed. CandidateIntent files and redacted acceptance summaries may be committed.

## Planned file map

```text
src/systematic_investing/research/
  __init__.py
  contracts.py          # CandidateIntent, StrategyEvaluation, identities
  universe.py           # fixed ETF view + annual PIT Stock schedules
  runner.py             # Strategy -> M0 adapter and Basic/OOS runner
  artifacts.py          # immutable run directories and canonical digests
  catalog.py            # thin append-only catalog
  benchmarks.py
  intake.py             # validates already-materialized canonical snapshots
  oos.py                # freeze/exposure/contamination verifier
  materializer.py        # owner-controlled Basic/OOS entry point
  reporting.py          # required yearly/subperiod summaries
  cli.py                # Research actor commands; no raw-provider fetch
  strategies/
    etf_absolute_trend.py
    etf_relative_momentum.py
    stock_relative_strength.py
    stock_breakout.py
research/candidates/
  m1-etf-absolute-trend-v1.json
  m1-etf-relative-momentum-v1.json
  m1-stock-relative-strength-v1.json
  m1-stock-breakout-v1.json
research/source-flights/m1-ai-source-flight-1.json
tests/research/
tests/integration/test_research_cli.py
tests/fixtures/research/
docs/reports/M1-acceptance-report.{json,md}
```

Create each file only when its Task first uses it.

## Task 1 — Typed StrategyContract and first ETF kernel flight

**Outcome:** A real absolute-trend algorithm reaches the M0 engine immediately, while insufficient history remains a typed no-decision rather than ambiguous `None`.

**Files:**

- Create: `src/systematic_investing/research/{__init__,contracts,universe,runner}.py`
- Create: `tests/research/smoke_strategies.py`
- Create: `tests/research/test_strategy_contract.py`
- Create: `tests/research/test_etf_absolute_trend_flight.py`
- Create: `tests/fixtures/research/etf_absolute_trend_smoke.json`

- [ ] **Step 1: Write failing typed-evaluation tests**

```python
def test_insufficient_history_is_typed_no_decision() -> None:
    evaluation = strategy.evaluate(short_context, etf_universe)
    assert evaluation.status is StrategyEvaluationStatus.NO_DECISION
    assert evaluation.reason_codes == ("INSUFFICIENT_HISTORY",)
    assert evaluation.contributions == ()


def test_explicit_cash_target_is_not_no_decision() -> None:
    evaluation = strategy.evaluate(downtrend_context, etf_universe)
    assert evaluation.status is StrategyEvaluationStatus.TARGETS
    assert evaluation.contributions[0].target_weight == Decimal("0")
```

Add a hand-audited smoke test proving a `TARGETS` evaluation becomes M0 planned order, T+1 fill, fee, NAV and metric. Expected amounts live in the fixture and are reviewed independently of engine output.

- [ ] **Step 2: Run and verify RED**

```powershell
python -m pytest tests/research/test_strategy_contract.py tests/research/test_etf_absolute_trend_flight.py -v -p no:cacheprovider
```

Expected: import/collection failure because the Research package does not exist.

- [ ] **Step 3: Implement the minimal contract and adapter**

```python
@dataclass(frozen=True)
class StrategyEvaluation:
    status: StrategyEvaluationStatus
    contributions: tuple[TargetContribution, ...]
    reason_codes: tuple[str, ...]
    evidence_ids: tuple[str, ...] = ()


class StrategyContract(Protocol):
    @property
    def identity(self) -> StrategyIdentity: ...

    def evaluate(
        self, context: DecisionContext, universe: UniverseView
    ) -> StrategyEvaluation: ...
```

`StrategyTargetSource` maps `TARGETS` to M0 contributions and typed `NO_DECISION` to M0 `None`, while retaining every evaluation in the Research result. Invalid/future access remains an exception/run failure. Implement close-above-N-session-SMA as a test-only smoke strategy in `tests/research/smoke_strategies.py`; do not duplicate execution/accounting. Smoke strategies prove the seam but cannot enter canonical Basic/OOS.

- [ ] **Step 4: Verify GREEN and M0 regression**

```powershell
python -m pytest tests/research/test_strategy_contract.py tests/research/test_etf_absolute_trend_flight.py -q -p no:cacheprovider
python -m pytest tests/unit tests/contract tests/component tests/golden tests/integration -q -p no:cacheprovider
python -m ruff check src/systematic_investing/research tests/research
python -m mypy --strict src/systematic_investing/research
```

Expected: focused tests PASS; M0 baseline remains PASS; Ruff/mypy PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/systematic_investing/research tests/research tests/fixtures/research/etf_absolute_trend_smoke.json
git commit -m "feat(m1): fly typed ETF strategy on M0 kernel"
```

## Task 2 — Stock kernel flight and annual PIT universe seam

**Outcome:** Stock follows immediately, with a universe interface capable of annual PIT reconstitution rather than a seven-year stale cohort.

**Files:**

- Create: `tests/research/test_stock_relative_strength_flight.py`
- Create: `tests/research/test_stock_universe_schedule.py`
- Create: `tests/fixtures/research/stock_relative_strength_smoke.json`
- Modify: `src/systematic_investing/research/universe.py`
- Modify: `src/systematic_investing/research/runner.py`

- [ ] **Step 1: Write failing annual-reconstitution and Stock flight tests**

```python
def test_future_records_cannot_change_prior_year_cohort() -> None:
    schedule_a = form_annual_schedule(records_through_2020, policy)
    schedule_b = form_annual_schedule(records_through_2020 + records_from_2021, policy)
    assert schedule_a.view_for(date(2021, 6, 1)) == schedule_b.view_for(date(2021, 6, 1))


def test_newly_eligible_stock_can_enter_next_year() -> None:
    assert NEW_STOCK not in schedule.view_for(date(2021, 6, 1)).instrument_ids
    assert NEW_STOCK in schedule.view_for(date(2022, 6, 1)).instrument_ids
```

The Stock smoke fixture also asserts SATELLITE contributions reach M0 lot, affordability, T+1 settlement, stamp-tax and suspension behavior.

- [ ] **Step 2: Run and verify RED**

```powershell
python -m pytest tests/research/test_stock_universe_schedule.py tests/research/test_stock_relative_strength_flight.py -v -p no:cacheprovider
```

Expected: FAIL because annual schedule and Stock strategy do not exist.

- [ ] **Step 3: Implement the minimal annual PIT schedule**

At each year-end cutoff, use only known listing age, ST/identity/tradability and trailing 60-session median amount; rank by `(-median_amount, InstrumentId)`, take top 50, require at least 20 for a real run, and freeze that view for the next calendar year. Implement the relative-strength algorithm only as a test smoke strategy; it cannot enter canonical Basic/OOS. The smoke fixture may use a smaller explicit test policy.

- [ ] **Step 4: Verify GREEN and strict checks**

```powershell
python -m pytest tests/research/test_stock_universe_schedule.py tests/research/test_stock_relative_strength_flight.py -q -p no:cacheprovider
python -m ruff check src/systematic_investing/research tests/research
python -m mypy --strict src/systematic_investing/research
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/systematic_investing/research tests/research tests/fixtures/research/stock_relative_strength_smoke.json
git commit -m "feat(m1): add annual PIT Stock strategy flight"
```

## Task 3 — Early real ETF Basic vertical slice

**Outcome:** The first decision-useful historical Basic result appears now, before building OOS machinery.

**Files:**

- Create: `src/systematic_investing/research/{artifacts,catalog,benchmarks,intake,materializer,cli}.py`
- Create: `src/systematic_investing/research/strategies/{__init__,etf_absolute_trend,etf_relative_momentum}.py`
- Create: `research/candidates/m1-etf-absolute-trend-v1.json`
- Create: `research/candidates/m1-etf-relative-momentum-v1.json`
- Create: `tests/research/test_candidate_intent.py`
- Create: `tests/research/test_basic_snapshot_boundary.py`
- Create: `tests/research/test_etf_candidate_specs.py`
- Create: `tests/integration/test_research_cli.py`

- [ ] **Step 1: Write failing lifecycle, parameter-selection, snapshot-boundary and CLI tests**

Assert:

- `CandidateIntent` contains hypothesis/rules/parameter variants/priority list/universe policy/splits/benchmark/gates, but rejects implementation/code/snapshot digests;
- `ResearchRunManifest` requires those runtime digests;
- among multiple `BASIC_PASS` variants, predeclared priority wins even when another return is higher;
- Basic snapshot maximum session equals Basic end and any later row fails;
- immutable run directories/catalog entries cannot be overwritten;
- CLI has `screen`, `basic-backtest`, `verify`, and no bypass flag.

- [ ] **Step 2: Run and verify RED**

```powershell
python -m pytest tests/research/test_candidate_intent.py tests/research/test_basic_snapshot_boundary.py tests/research/test_etf_candidate_specs.py tests/integration/test_research_cli.py -v -p no:cacheprovider
```

Expected: FAIL because lifecycle/artifact/intake/CLI code is absent.

- [ ] **Step 3: Freeze intents, then implement only the Basic vertical-slice capabilities**

First write the two CandidateIntent JSON files, validate them, and record their digests before creating either canonical strategy module. Then implement those exact rules. Use immutable `runs/<run_id>/{manifest,result,report}.json` and create-new catalog entries. Add candidate-local `CASH_0`, same-ETF buy-and-hold, and equal-weight ETF benchmark. `intake.py` only validates an already-materialized canonical Basic snapshot; Research CLI must not fetch provider/raw data.

- [ ] **Step 4: Verify code GREEN offline**

Run Step 2 again.

Expected: PASS; mutation/overwrite and post-Basic rows are rejected.

- [ ] **Step 5: Owner materializes the Basic-only ETF snapshot outside the Agent workspace**

In a controlled data environment with the pinned provider and raw data mounted, run existing qualification and an owner intake command that is not available to the Research actor:

```powershell
$env:SIOS_CHSTOCKDATA_LIVE_QUALIFICATION='1'
python -m pytest tests/qualification -q -p no:cacheprovider
python -m systematic_investing.research.materializer --mode BASIC --asset ETF --start 2015-01-05 --end 2022-12-30 --request research/candidates/m1-etf-absolute-trend-v1.json --output var/research/snapshots/basic-etf-v1
```

Expected: live-only tests execute and PASS; snapshot reports `max_session=2022-12-30`. Copy/mount only the canonical output read-only into the Research workspace; do not expose raw provider data. The same narrow materializer is reused later, but `--mode BASIC` refuses dates after the CandidateIntent Basic end.

- [ ] **Step 6: Run real ETF screen and Basic**

```powershell
python -m systematic_investing.research.cli screen --intent research/candidates/m1-etf-absolute-trend-v1.json --root var/research/experiments
python -m systematic_investing.research.cli basic-backtest --intent research/candidates/m1-etf-absolute-trend-v1.json --snapshot var/research/snapshots/basic-etf-v1/manifest.json --root var/research/experiments
python -m systematic_investing.research.cli screen --intent research/candidates/m1-etf-relative-momentum-v1.json --root var/research/experiments
python -m systematic_investing.research.cli basic-backtest --intent research/candidates/m1-etf-relative-momentum-v1.json --snapshot var/research/snapshots/basic-etf-v1/manifest.json --root var/research/experiments
```

Expected: two immutable Basic reports or typed failures; every parameter attempt retained; selection follows priority list. Zero `BASIC_PASS` is valid.

- [ ] **Step 7: Commit code/specs, not generated data**

```powershell
git add src/systematic_investing/research research/candidates/m1-etf-absolute-trend-v1.json research/candidates/m1-etf-relative-momentum-v1.json tests/research tests/integration/test_research_cli.py
git commit -m "feat(m1): produce first real ETF Basic evidence"
```

## Task 4 — Early real Stock Basic with annual PIT schedules

**Outcome:** Stock produces real Basic evidence before OOS infrastructure, without fundamentals or stale membership.

**Files:**

- Create: `src/systematic_investing/research/strategies/{stock_relative_strength,stock_breakout}.py`
- Create: `research/candidates/m1-stock-relative-strength-v1.json`
- Create: `research/candidates/m1-stock-breakout-v1.json`
- Create: `tests/research/test_stock_candidate_specs.py`
- Modify: `tests/research/test_basic_snapshot_boundary.py`
- Modify: `src/systematic_investing/research/intake.py`

- [ ] **Step 1: Write failing real-Stock policy tests**

Assert annual formation, >=250 listed sessions, trailing 60-session median amount, non-ST/non-unknown, top-50 stable ties, minimum 20, same-schedule benchmark, SATELLITE sleeve, predeclared parameter priority, and `DIVIDEND_TAX_NOT_MODELED`.

- [ ] **Step 2: Run and verify RED**

```powershell
python -m pytest tests/research/test_stock_candidate_specs.py tests/research/test_basic_snapshot_boundary.py -v -p no:cacheprovider
```

Expected: FAIL because Stock intents/breakout/real intake checks are absent.

- [ ] **Step 3: Freeze Stock intents, then implement Stock-only additions**

First write and validate both Stock CandidateIntent files and record their digests; only then implement the canonical Stock strategy modules. Reuse canonical bars/reference/tradability/actions and Instrument Master authority. Add no index membership service, factors, fundamentals, ML, sectors or dynamic optimizer.

- [ ] **Step 4: Verify code GREEN**

```powershell
python -m pytest tests/research/test_stock_candidate_specs.py tests/research/test_stock_universe_schedule.py tests/research/test_basic_snapshot_boundary.py -q -p no:cacheprovider
```

Expected: PASS.

- [ ] **Step 5: Owner materializes Basic-only Stock data**

```powershell
python -m systematic_investing.research.materializer --mode BASIC --asset STOCK --start 2017-01-03 --end 2022-12-30 --request research/candidates/m1-stock-relative-strength-v1.json --output var/research/snapshots/basic-stock-v1
```

Expected: snapshot maximum session `2022-12-30`; annual 2019–2022 schedules each contain 20–50 instruments or a typed year-level failure. Only canonical output is mounted read-only for Research.

- [ ] **Step 6: Run real Stock screen and Basic**

```powershell
python -m systematic_investing.research.cli screen --intent research/candidates/m1-stock-relative-strength-v1.json --root var/research/experiments
python -m systematic_investing.research.cli basic-backtest --intent research/candidates/m1-stock-relative-strength-v1.json --snapshot var/research/snapshots/basic-stock-v1/manifest.json --root var/research/experiments
python -m systematic_investing.research.cli screen --intent research/candidates/m1-stock-breakout-v1.json --root var/research/experiments
python -m systematic_investing.research.cli basic-backtest --intent research/candidates/m1-stock-breakout-v1.json --snapshot var/research/snapshots/basic-stock-v1/manifest.json --root var/research/experiments
```

Expected: complete immutable Basic evidence or typed failures; zero eligible Stock candidates is valid.

- [ ] **Step 7: Commit**

```powershell
git add src/systematic_investing/research/strategies/stock_relative_strength.py src/systematic_investing/research/strategies/stock_breakout.py src/systematic_investing/research/intake.py research/candidates/m1-stock-relative-strength-v1.json research/candidates/m1-stock-breakout-v1.json tests/research
git commit -m "feat(m1): produce annual PIT Stock Basic evidence"
```

## Task 5 — Failure retention and deterministic replay hardening

**Outcome:** The early real results become reproducible and auditable without building an event-sourcing framework.

**Files:**

- Create: `tests/research/test_artifact_retention.py`
- Create: `tests/research/test_research_reproducibility.py`
- Create: `tests/research/test_benchmarks.py`
- Modify: `src/systematic_investing/research/{artifacts,catalog,benchmarks,runner}.py`

- [ ] **Step 1: Write failing retention/replay tests**

Cover create-new semantics, catalog sequence uniqueness, artifact digest mutation, provider empty/failure/partial distinctions, compile/kernel/report-persistence failures, attempt counts, complete ResearchRunManifest mutation matrix, same-kernel benchmark and isolated rerun digest equality.

- [ ] **Step 2: Run and verify RED**

```powershell
python -m pytest tests/research/test_artifact_retention.py tests/research/test_research_reproducibility.py tests/research/test_benchmarks.py -v -p no:cacheprovider
```

Expected: at least the injected failure/replay cases FAIL.

- [ ] **Step 3: Implement minimal hardening**

Keep one focused artifact module and one thin catalog module. Do not add previous-event hash links, reducers, projections, a workflow DSL or database. Every failure gets an immutable result and catalog entry; every successful run records normalized output digest.

- [ ] **Step 4: Verify GREEN plus no-lookahead regression**

```powershell
python -m pytest tests/research/test_artifact_retention.py tests/research/test_research_reproducibility.py tests/research/test_benchmarks.py tests/component/test_no_lookahead.py -q -p no:cacheprovider
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/systematic_investing/research tests/research
git commit -m "test(m1): harden failed-run retention and replay"
```

## Task 6 — Physical OOS freeze and controlled materialization

**Outcome:** OOS protection controls data exposure, not merely labels and hashes.

**Files:**

- Create: `src/systematic_investing/research/oos.py`
- Modify: `src/systematic_investing/research/materializer.py`
- Create: `tests/research/test_oos_exposure_gate.py`
- Create: `tests/research/test_oos_verifier.py`
- Modify: `src/systematic_investing/research/cli.py`

- [ ] **Step 1: Write failing physical-exposure and two-phase identity tests**

Test:

- Basic snapshot with rows after Basic end is rejected;
- pre-freeze OOS path/provider mount evidence yields `HISTORICAL_VALIDATION`, not controlled OOS;
- Basic PASS is required for freeze;
- freeze binds intent/implementation/parameters/requested scope/universe policy/benchmark/cost/kernel but not nonexistent OOS snapshot digest;
- materializer refuses missing/mismatched freeze and writes only the requested scope;
- OOSRunManifest binds actual snapshot/schedule digests after materialization;
- reveal intent persists before the runner opens OOS data;
- overlap, mutation and repeated verdict fail closed.

- [ ] **Step 2: Run and verify RED**

```powershell
python -m pytest tests/research/test_oos_exposure_gate.py tests/research/test_oos_verifier.py -v -p no:cacheprovider
```

Expected: FAIL because OOS gate/materializer are absent.

- [ ] **Step 3: Implement the narrow boundary**

Research CLI gets `oos-freeze`, `oos-run`, and `no-oos-eligible`; it never fetches data. Owner materializer accepts one freeze artifact, has provider/raw access only in the controlled environment, writes a freeze-specific immutable snapshot plus receipt, and exits. No service, user system, PKI or scheduler.

- [ ] **Step 4: Verify GREEN and no bypass flags**

```powershell
python -m pytest tests/research/test_oos_exposure_gate.py tests/research/test_oos_verifier.py tests/integration/test_research_cli.py -q -p no:cacheprovider
python -m systematic_investing.research.cli --help
```

Expected: PASS; no `--force`, `--ignore-contamination`, raw-provider fetch, or rewrite command.

- [ ] **Step 5: Commit**

```powershell
git add src/systematic_investing/research/oos.py src/systematic_investing/research/materializer.py src/systematic_investing/research/cli.py tests/research/test_oos_exposure_gate.py tests/research/test_oos_verifier.py tests/integration/test_research_cli.py
git commit -m "feat(m1): gate physical OOS data exposure"
```

## Task 7 — Canonical OOS when eligible; honest no-candidate outcome otherwise

**Outcome:** ETF and Stock each end with either one canonical OOS verdict selected by predeclared priority or `NO_OOS_ELIGIBLE_CANDIDATE`.

**Files:**

- Create: `tests/research/test_asset_class_outcomes.py`
- Modify: `src/systematic_investing/research/oos.py`
- Create: `src/systematic_investing/research/reporting.py`

- [ ] **Step 1: Write failing asset-class outcome tests**

Assert zero Basic passes produces `NO_OOS_ELIGIBLE_CANDIDATE` without materialization; one/multiple passes select by CandidateIntent priority; OOS produces exactly one `SURVIVOR` or `REJECTED_OOS`; no code path loops to add candidates.

- [ ] **Step 2: Run and verify RED**

```powershell
python -m pytest tests/research/test_asset_class_outcomes.py -v -p no:cacheprovider
```

Expected: FAIL until aggregate outcome logic exists.

- [ ] **Step 3: Implement and run ETF outcome**

```powershell
$etf = python -m systematic_investing.research.cli select-oos --asset ETF --root var/research/experiments | ConvertFrom-Json
if ($etf.status -eq 'NO_OOS_ELIGIBLE_CANDIDATE') {
  python -m systematic_investing.research.cli no-oos-eligible --asset ETF --root var/research/experiments
} else {
  $etfFreeze = python -m systematic_investing.research.cli oos-freeze --candidate-id $etf.candidate_id --root var/research/experiments | ConvertFrom-Json
}
```

If freeze was produced, the owner—not the Research Agent—runs:

```powershell
python -m systematic_investing.research.materializer --mode OOS --freeze var/research/experiments/$($etfFreeze.lineage_id)/oos/$($etfFreeze.freeze_id)/freeze.json --output var/research/oos/$($etfFreeze.freeze_id)
```

After the read-only snapshot is mounted:

```powershell
python -m systematic_investing.research.cli oos-run --freeze-id $etfFreeze.freeze_id --snapshot var/research/oos/$($etfFreeze.freeze_id)/manifest.json --root var/research/experiments
```

Expected: canonical verdict, or honest no-eligible outcome without any OOS rows exposed.

- [ ] **Step 4: Run the identical Stock outcome flow**

Repeat Step 3 with `--asset STOCK` and `$stock`. Expected: canonical verdict or `NO_OOS_ELIGIBLE_CANDIDATE`; `DIVIDEND_TAX_NOT_MODELED` remains visible.

- [ ] **Step 5: Verify and commit**

```powershell
python -m pytest tests/research/test_asset_class_outcomes.py tests/research/test_oos_exposure_gate.py tests/research/test_oos_verifier.py -q -p no:cacheprovider
python -m systematic_investing.research.cli verify --root var/research/experiments
git add src/systematic_investing/research/oos.py src/systematic_investing/research/reporting.py tests/research/test_asset_class_outcomes.py
git commit -m "feat(m1): record honest ETF and Stock OOS outcomes"
```

Expected: tests/catalog verification PASS.

## Task 8 — AI Copilot Source Flight and minimal reporting

**Outcome:** Verify the real discovery path, not merely that an Agent can invoke CLI. Formal regime labels remain deferred.

**Files:**

- Create: `research/source-flights/m1-ai-source-flight-1.json`
- Modify: `src/systematic_investing/research/reporting.py`
- Create: `tests/research/test_ai_source_flight.py`
- Create: `tests/research/test_reporting.py`
- Modify: `src/systematic_investing/research/cli.py`

- [ ] **Step 1: Write failing source-record and report tests**

Require URL, title, author/publisher, accessed date, license/rights posture, short project-authored summary, hypothesis, asset/horizon/data requirements and Cheap Screen verdict. Report tests require yearly/subperiod metrics and prohibit a required Regime classifier/router.

- [ ] **Step 2: Run and verify RED**

```powershell
python -m pytest tests/research/test_ai_source_flight.py tests/research/test_reporting.py -v -p no:cacheprovider
```

Expected: FAIL because the source flight/report schema is absent.

- [ ] **Step 3: Conduct one real source flight**

Use an existing strong Agent with lawful web access to find one real primary paper, author-maintained repository, or attributable forum/research post. Record provenance and extract one falsifiable hypothesis without copying implementation. Run:

```powershell
python -m systematic_investing.research.cli source-screen --source-record research/source-flights/m1-ai-source-flight-1.json --root var/research/experiments
```

Expected: `SCREEN_PASS` or `REJECTED_BEFORE_IMPLEMENTATION`; either is successful workflow evidence. Only a pass may become a later CandidateIntent, and M1 acceptance does not require implementing it.

- [ ] **Step 4: Implement minimal yearly/subperiod reporting**

Do not create formal `BULL/SIDEWAYS/BEAR` labels in M1. If a pre-existing PIT label artifact is supplied, it may be attached as optional analysis and must not change targets/fills.

- [ ] **Step 5: Verify and commit**

```powershell
python -m pytest tests/research/test_ai_source_flight.py tests/research/test_reporting.py -q -p no:cacheprovider
git add research/source-flights/m1-ai-source-flight-1.json src/systematic_investing/research/reporting.py src/systematic_investing/research/cli.py tests/research/test_ai_source_flight.py tests/research/test_reporting.py
git commit -m "feat(m1): verify real-source AI research flight"
```

## Task 9 — M1 acceptance gate

**Outcome:** Publish redacted evidence and stop before M2.

**Files:**

- Create: `tests/research/test_m1_acceptance.py`
- Create: `docs/reports/M1-acceptance-report.json`
- Create: `docs/reports/M1-acceptance-report.md`
- Modify: `.gitignore` only to exclude generated `var/research/`

- [ ] **Step 1: Write the failing acceptance test**

```python
assert report["etf"]["basic_run_count"] >= 1
assert report["stock"]["basic_run_count"] >= 1
assert report["etf"]["outcome"] in {"SURVIVOR", "REJECTED_OOS", "NO_OOS_ELIGIBLE_CANDIDATE"}
assert report["stock"]["outcome"] in {"SURVIVOR", "REJECTED_OOS", "NO_OOS_ELIGIBLE_CANDIDATE"}
assert report["physical_oos_gate_status"] == "PASS"
assert report["artifact_catalog_status"] == "PASS"
assert report["ai_source_flight"]["screen_verdict"] in {"SCREEN_PASS", "REJECTED_BEFORE_IMPLEMENTATION"}
```

- [ ] **Step 2: Verify RED**

```powershell
python -m pytest tests/research/test_m1_acceptance.py -v -p no:cacheprovider
```

Expected: FAIL because reports do not exist.

- [ ] **Step 3: Generate acceptance reports**

```powershell
python -m systematic_investing.research.cli acceptance-report --root var/research/experiments --output docs/reports/M1-acceptance-report.json
python -m systematic_investing.research.cli render-report --input docs/reports/M1-acceptance-report.json --output docs/reports/M1-acceptance-report.md
```

Expected: reports list all Basic attempts/failures, asset-class outcomes, OOS exposure receipts where applicable, digests, limitations and AI source provenance.

- [ ] **Step 4: Run final verification**

```powershell
python -m pytest tests/research tests/integration/test_research_cli.py -q -p no:cacheprovider
python -m pytest tests/unit tests/contract tests/component tests/golden tests/integration -q -p no:cacheprovider
python -m ruff check src tests
python -m mypy --strict src/systematic_investing/research
python -m systematic_investing.research.cli verify --root var/research/experiments
python -m pytest tests/research/test_m1_acceptance.py -v -p no:cacheprovider
```

Expected: all M1 tests PASS; M0 regression PASS; Ruff PASS; new package strict mypy PASS; artifact/catalog verification PASS; acceptance test PASS.

- [ ] **Step 5: Commit and stop**

```powershell
git add .gitignore docs/reports/M1-acceptance-report.json docs/reports/M1-acceptance-report.md tests/research/test_m1_acceptance.py
git commit -m "docs(m1): publish first strategy flight evidence"
```

Stop. Do not start formal regime labels, robustness, walk-forward, final holdout, Paper, ActiveStrategyPack, scheduler, notification, UI, broker, or M2/M3 implementation.

## Task ordering rationale

Task 1 and Task 2 prove ETF/Stock algorithms traverse M0. Task 3 then produces the first real ETF Basic result and Task 4 the first real Stock Basic result—before OOS infrastructure. Task 5 hardens replay/retention after value is visible. Tasks 6–7 add physical OOS protection and accept no-eligible outcomes. Task 8 verifies a real-source AI discovery flight. Task 9 closes the milestone.

## Scope Audit

### M1 must ship

- typed StrategyEvaluation and thin StrategyContract adapter;
- pre-code CandidateIntent and run-time ResearchRunManifest;
- ETF/Stock Cheap Screen and real Basic evidence;
- annual PIT Stock universe schedule;
- immutable run directories, thin catalog, failure retention and replay;
- physical Basic/OOS separation and contamination tests;
- OOS verdict only for eligible candidates, otherwise `NO_OOS_ELIGIBLE_CANDIDATE`;
- real-source AI Copilot flight and yearly/subperiod reporting.

### Deferred to M2

- formal BULL/SIDEWAYS/BEAR label semantics and strategy × regime analysis;
- robustness, parameter neighborhood, cost stress, walk-forward and final holdout;
- Paper Forward, combinations and ActiveStrategyPack candidate;
- operational Research-to-Production promotion.

### Deferred to M3

- EOD/pre-open scheduler/runtime, holdings/cash reconciliation and ActionPlan;
- manual fills, ServerChan and minimal daily-use UI.

### Long-term deferred

- Knowledge Platform, Agent Runtime, Private Investment Memory, AI Investor;
- complete Strategy SDK/5-page UI, factor/ML platform, broker automation and complex multiple-testing statistics.

### Over-engineering verdict

The retention design is intentionally limited to immutable directories plus a thin catalog. The OOS boundary is one owner-controlled materializer, not a permissions platform or service. Adding a database, event-sourcing framework, scheduler, LLM SDK, generic workflow engine or regime router exceeds M1.

## Design Conflict

`NO_DESIGN_CONFLICT`

These revisions strengthen M1 research validity without changing M0 semantics.

## Final recommendation

**Task 1** still gives the earliest real ETF algorithmic backtest on a frozen smoke fixture. The first decision-useful qualified historical result moves forward from old Task 6 to **Task 3**. Stock real Basic follows in Task 4. Canonical OOS appears in Task 7 only when a candidate honestly passes Basic; otherwise Task 7 records `NO_OOS_ELIGIBLE_CANDIDATE` and M1 may still complete.
