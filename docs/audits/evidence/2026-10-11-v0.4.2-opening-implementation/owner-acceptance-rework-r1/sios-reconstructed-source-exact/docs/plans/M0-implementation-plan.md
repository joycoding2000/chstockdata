# M0 Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a narrow, reproducible daily-bar quant foundation whose provider-neutral data, Target Portfolio, accounting, and backtest semantics pass hand-calculated golden tests for CNY 100,000.

**Architecture:** Use a Python 3.12+ modular monolith with a dependency-free domain core, a system-owned effective-dated Instrument Master, ports for market data/persistence, a single `chstockdata` adapter, and deterministic sleeve-aware policies for portfolio conversion and daily event simulation. Research and Production share only stable core APIs and are guarded by simple owner approval, immutable digests, audit records, and separate authority.

**Tech Stack:** Python 3.12+, pytest, dataclasses/Enums/Protocols, Pydantic only at external serialization boundaries, Decimal arithmetic, Parquet plus DuckDB only where immutable analytical snapshots justify them.

---

## 0. Entry gate

OQ-01 through OQ-10 and P0-01 through P0-04 are approved and encoded in the architecture documents. Do not execute this plan until the owner approves this architecture revision. Deferred OQ-11–OQ-20 and OQ-22–OQ-24 are enforced at their named milestone gates.

## Planned repository map

```text
pyproject.toml
src/systematic_investing/
  domain/{identifiers,money,instruments,market,portfolio,execution,ledger,runs}.py
  instrument_master/{models,repository}.py
  data/{ports,contracts,quality,snapshots}.py
  adapters/chstockdata/provider.py
  portfolio/{validation,allocation}.py
  risk/{ports,decisions}.py
  backtest/{engine,execution,accounting}.py
  metrics/performance.py
  boundaries/import_rules.py
tests/{unit,contract,component,golden,integration,qualification,parity}/
tests/fixtures/golden/
third_party/SOURCES.yaml
```

Each file owns one cohesive responsibility. Production scheduling, Web/API, strategies, notifications, and live execution are absent.

## Task 1 — Bootstrap the offline quality harness

**Files:** Create `pyproject.toml`, `src/systematic_investing/__init__.py`, `tests/conftest.py`, `third_party/SOURCES.yaml`; update only documentation if owner decisions require it.

- [ ] Create package metadata requiring Python 3.12+, pytest configuration, formatting/type-check configuration, and the smallest approved dependency set with exact lock strategy.
- [ ] Seed `third_party/SOURCES.yaml` with a schema/version and the approved `chstockdata` dependency record only after exact commit/license review; do not copy its code.
- [ ] Add a smoke test that imports the package and asserts the default initial-capital constant/value object is exactly `Decimal("100000")` CNY.
- [ ] Run `python -m pytest tests/unit/test_package_contract.py -q`; expect one passing test.
- [ ] Commit only bootstrap files with a focused foundation message.

## Task 2 — Domain primitives and effective-dated instrument rules

**Files:** Create `domain/identifiers.py`, `money.py`, `instruments.py`, `instrument_master/models.py`, `instrument_master/repository.py`; tests `tests/unit/test_identifiers.py`, `test_money.py`, `test_instrument_rules.py`, `test_instrument_master_authority.py`.

- [ ] Write failing tests for exchange-qualified IDs, timezone/session-date distinction, Decimal/rounding rules, explicit `SleeveId`, unsupported ETF subtype, effective-date profile selection, and provider-candidate conflict with approved Instrument Master.
- [ ] Define immutable `InstrumentId`, `Money`, `Instrument`, `SleeveId(CORE, SATELLITE)`, `LotRule`, `SettlementRule`, `PriceLimitRule`, and `MarketFeeTaxRule`; make unknown rule selection a typed error. Instrument references only Instrument Master market/regulatory profiles, never broker/account fees.
- [ ] Build the system-owned Instrument Master authority with source/effective-date provenance. Add standard Shanghai/Shenzhen A-share and domestic broad-based equity/gold/bond ETF profile fixtures only; cross-border/QDII, money-market, and other subtypes fail closed.
- [ ] Run the three unit modules; expect all pass with no network.
- [ ] Commit domain primitives independently.

## Task 3 — Canonical market data and provider port

**Files:** Create `domain/market.py`, `data/contracts.py`, `data/ports.py`; tests `tests/contract/test_canonical_market_contracts.py`, `test_provider_port.py`.

- [ ] Write failing construction tests for DailyBar OHLC/pre-close invariants, null-versus-zero, explicit units, RAW execution basis, distinct `information_available_at`/`retrieved_at`, `availability_basis` including `UNKNOWN`, calendar identity, tradability `UNKNOWN`, and corporate-action revisions.
- [ ] Define immutable `DailyBar`, `TradingSession`, `TradabilityStatus`, `CorporateAction`, `AvailabilityBasis`, `ProviderEvidence`, and typed provider result/error contracts. PIT access uses only information availability.
- [ ] Define a narrow `DataProviderPort` Protocol returning canonical results, never vendor frames.
- [ ] Add serialization round-trip tests that preserve Decimal/date/time/enum/schema values.
- [ ] Run contract tests; expect all pass offline.
- [ ] Commit canonical contracts and port.

## Task 4 — Immutable snapshots and Data Quality Gate

**Files:** Create `data/snapshots.py`, `data/quality.py`, `domain/runs.py`; tests `tests/unit/test_data_quality.py`, `tests/integration/test_snapshot_replay.py`.

- [ ] Write failing tests for duplicates, missing required fields, OHLC/pre-close inconsistency, closed-session bars, injected-clock freshness, same retrieval/different information time, unknown availability, provider-versus-Instrument-Master conflict, unknown classification/rules, checksum corruption, and purpose-specific gate status.
- [ ] Define versioned `DataSnapshotManifest`, `GateResult`, check result/reason codes, and content-digest normalization.
- [ ] Implement approved scoped gates: critical decision-data failure blocks a new target; pre-open critical failure blocks risk increase; reduction requires independently reliable identity, holding, sellability, tradability, and conservative price/cost evidence or emits no order plus urgent manual-review alert.
- [ ] Persist a tiny canonical fixture in the selected immutable format; replay and verify checksums in a temporary directory.
- [ ] Run unit/integration tests twice and assert identical manifest/output digests.
- [ ] Commit snapshot and quality behavior.

## Task 5 — ChStockDataProvider anti-corruption adapter

**Files:** Create `adapters/chstockdata/provider.py`; tests `tests/contract/test_chstockdata_provider.py`, recorded/synthetic fixtures under `tests/fixtures/chstockdata/`.

- [ ] Pin and record the reviewed `chstockdata` version/commit; document exact supported package methods and raw shapes in the provenance record.
- [ ] Write failing tests for symbol/date/unit/information/retrieval-time mapping, missing fields, empty success, partial result, provider exception, schema drift, provider evidence/checksum creation, and conflicting provider rule candidates.
- [ ] Implement explicit mapping to canonical market/reference candidate contracts. Keep the optional dependency import inside adapter construction so core tests run without it; never promote provider classification, ETF subtype, or trading rules into Instrument Master authority.
- [ ] Add an architecture test proving no other package imports `chstockdata`.
- [ ] Run adapter contract tests offline using fixtures; expect no network access.
- [ ] Commit adapter and provenance record together.

## Task 6 — Target Portfolio and deterministic risk contracts

**Files:** Create `domain/portfolio.py`, `portfolio/validation.py`, `portfolio/allocation.py`, `risk/ports.py`, `risk/decisions.py`; tests `tests/unit/test_target_portfolio.py`, `test_allocation.py`, `test_risk_decisions.py`.

- [ ] Write failing tests for theoretical weights plus cash, zero versus absent targets, explicit strategy/sleeve contributions, CORE/SATELLITE aggregation and caps, held-instrument completeness, long-only limits, immutable lock/revision identity, T-close sizing contract, and risk not increasing upstream exposure.
- [ ] Define `TargetContribution`, theoretical/risk-approved/executable target types retaining strategy, sleeve, theoretical/current/executable weights, T-close sizing price basis/value, target amount/quantity, residual cash, source IDs, versions, and reason codes.
- [ ] Implement reductions/exits first, then approved portfolio/sleeve budgets, then buys by descending absolute target-weight deficit and canonical InstrumentId tie-breaker; accept complete lots, reserve separated market/broker fees, keep residual cash, and do not renormalize.
- [ ] Prove input ordering does not change output and CNY 100,000 fixtures never create negative cash.
- [ ] Run portfolio/risk unit tests; expect exact Decimal equality.
- [ ] Commit portfolio/risk contracts and allocation.

## Task 7 — Orders, fills, settlement, fees, and ledgers

**Files:** Create `domain/execution.py`, `domain/ledger.py`, `backtest/execution.py`, `backtest/accounting.py`; tests `tests/unit/test_fees.py`, `test_settlement.py`, `tests/component/test_execution_accounting.py`.

- [ ] Write failing tests for run-owned account minimum commission versus Instrument Master market fee/tax rules, stock sell tax, approved ETF subtype profiles, tick/monetary rounding, available versus total quantity, side-specific lot behavior, simultaneous T+1 gap cash pressure, stale marks, cash reservation, and typed rejection.
- [ ] Define immutable `AccountFeeConfig`/`BrokerFeeProfile` in execution/run configuration plus Order, Fill, Rejection, cash/holding ledger entries, Position, PortfolioSnapshot, and NavPoint. Instrument identity and Instrument Master must not reference broker fees.
- [ ] Implement effective-dated Instrument Master market rules separately from `AccountFeeConfig`/`BrokerFeeProfile`; never branch on “is ETF” alone.
- [ ] At T-close target conversion compute `planned_quantity` as the largest valid complete lot. At T+1 Backtest activation, compute every candidate's open plus side-aware slippage, tick rounding, and applicable fees, then evaluate affordability globally under the approved sleeve/priority order and reduce `submitted_quantity` by complete lots. Once submitted, each M0 daily-bar quantity is all-or-none. Value suspension at last valid RAW close with `STALE_MARK(age)` unless no defensible valuation exists, a corporate action invalidates the price, or identity/reference is unresolved.
- [ ] Run unit/component tests; expect exact itemized costs and holdings.
- [ ] Commit execution and accounting layer.

## Task 8 — Deterministic daily-bar engine

**Files:** Create `backtest/engine.py`; tests `tests/component/test_event_order.py`, `test_tradability.py`, `test_corporate_actions.py`, `test_no_lookahead.py`.

- [ ] Write failing tests for the documented ten-step daily event order and strict separation of finalized T-close sizing from T+1 activation and `NEXT_SESSION_OPEN` fill plus side-aware slippage/tick rounding.
- [ ] Implement a small event loop over frozen canonical inputs and predetermined target fixtures. Simultaneous T+1 gaps change activation-time `submitted_quantity` through one global affordability pass, not T-close `planned_quantity` or the theoretical target, and submitted orders fill all-or-none.
- [ ] Add suspension/unknown, upper-limit buy, lower-limit sell, T+1 sellability, and corporate-action/no-double-count cases. If a quantity-changing action is effective between decision and activation, invalidate the affected pending execution with `CORPORATE_ACTION_REPLAN_REQUIRED`, submit no rescaled substitute, and preserve the locked target.
- [ ] Add metamorphic no-lookahead test: mutate all data after T and prove the T decision/pending order digest is unchanged.
- [ ] Run component tests; expect deterministic ledgers over repeated runs.
- [ ] Commit the kernel without any investment strategy.

## Task 9 — Performance metrics

**Files:** Create `metrics/performance.py`; tests `tests/unit/test_performance_metrics.py`.

- [ ] Write hand-calculated failing tests for daily close returns, total return, calendar-day CAGR, sample volatility, 252-session Sharpe/Sortino with zero rates, drawdown, Calmar, both underwater units, half-gross-notional/average-equity turnover, terminal mode, and convention-version identity. M0 manifests accept benchmark `NONE` or `SYNTHETIC_TEST_BENCHMARK` only and include it in run identity.
- [ ] Implement pure functions that retain `STALE_MARK` NAV, reject only truly incomplete portfolio NAV, and return values plus convention metadata recorded in `RunManifest`.
- [ ] Add gross-versus-net cost-drag calculation from matched ledgers.
- [ ] Run metric tests; expect Decimal/tolerance assertions declared per statistic.
- [ ] Commit metrics independently.

## Task 10 — Golden suite and normalized replay

**Files:** Create scenario manifests and expected outputs under `tests/fixtures/golden/G01` through `G21`; tests `tests/golden/test_golden_scenarios.py`, `tests/integration/test_reproducibility.py`.

- [ ] Encode G01–G21 from `docs/architecture/test-plan.md`, including T-close sizing/next-open fill, globally prioritized gap affordability using adjusted/rounded prices plus fees, PIT information versus retrieval time, Instrument Master authority conflict, explicit sleeve cap, stale-versus-unpriceable valuation, and intervening corporate-action invalidation.
- [ ] Create a test-only predetermined-target driver; its name and docs must state that it is not a strategy.
- [ ] Run every scenario twice in isolated temporary directories and compare normalized digests.
- [ ] Review every expected number manually; do not regenerate goldens from kernel output as the oracle.
- [ ] Run `python -m pytest tests/golden tests/integration/test_reproducibility.py -q`; expect all pass.
- [ ] Commit goldens separately so semantic review is clear.

## Task 11 — ETF qualification and independent parity

**Files:** Create `tests/qualification/test_chstockdata_etf_gate.py`, qualification matrix/expected evidence fixtures, `tests/parity/test_reference_cases.py`, and a generated report path excluded from core package imports.

- [ ] Encode domestic broad-based equity, gold, and bond ETF matrices. Explicitly reject cross-border/QDII, money-market, and other unverified subtypes; passing one subtype never approves another.
- [ ] Add opt-in live tests for routing, OHLCV/pre-close, units, calendar, history, tradability/suspension, adjustment/actions, freshness, and provider-version evidence.
- [ ] Freeze golden edge-event evidence from public exchange rules/data. Compare samples with legally used JoinQuant validation-only research evidence or another lawful independent source and emit an immutable capability-scoped report; record source, access date, semantics, tolerance, and excluded/failed scope.
- [ ] Record the exact commands, credentials prerequisites without secret values, source rights, versions, dates, and report digest.
- [ ] Run offline parity in normal CI and live qualification in the controlled release environment; require PASS for approved scope.
- [ ] Commit only non-sensitive fixtures/config and the approved report/provenance evidence.

## Task 12 — Research/Production boundary and release audit

**Files:** Create `boundaries/import_rules.py`, `tests/unit/test_import_boundaries.py`, `tests/integration/test_manifest_identity.py`; update the listed architecture docs only if implementation revealed an approved semantic correction.

- [ ] Add static/import tests forbidding vendor imports outside the adapter, provider rule authority, and research/LLM imports from core/Production namespaces. Promotion needs explicit owner approval, immutable digest, separate authority, and audit record—no enterprise signing service or PKI.
- [ ] Test manifest identity changes for data, fee, calendar, execution model, dependency lock, or rule version changes.
- [ ] Run the complete offline suite: `python -m pytest tests/unit tests/contract tests/component tests/golden tests/integration -q`; expect zero failures/skips in required scope.
- [ ] Run type/static checks and verify no Web/UI, scheduler, notification, strategy, LLM, broker, or microservice package entered M0.
- [ ] Review `third_party/SOURCES.yaml` against resolved dependencies and scan for secrets/raw credentials.
- [ ] Produce an M0 acceptance report listing test counts, qualification/parity report IDs, reproducibility digest, known limitations, and all deferred later-milestone questions.
- [ ] Stop for owner review; do not begin M1 strategy work.

## Implementation order rationale

The order locks semantic primitives before adapters, proves data identity before backtesting, defines targets before orders, and builds accounting before metrics. Golden cases come only after focused unit/component tests but remain independently hand-calculated. Live ETF qualification is late because it depends on stable canonical contracts, yet it remains mandatory for M0 acceptance.

## Explicit stop condition

After Task 12 and owner-visible acceptance evidence, stop. M1 ETF strategy research, M2 evidence promotion, M3 paper/runtime, M4 notifications/UI, and M6 Stock Satellite are outside this plan and require separate approval.
