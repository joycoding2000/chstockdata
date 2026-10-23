# M0 Target Completeness and Materializer Preflight Design

**Status:** Owner-approved by the Option 1 decision dated 2026-09-17.

## Goal

Resolve the M0 target-completeness conflict by making every produced target
explicitly address every current holding, and make Instrument Master/reference
failures stop the owner materializer before any historical provider acquisition.
Do not add carry-forward semantics and do not resume M1 Task 3.

## Considered approaches

1. **Validate in allocation.** Rejected: allocation sees approved weights and
   holdings but cannot distinguish an invalid incomplete target from an
   upstream policy. The prior attempt also broke G15 at the wrong layer.
2. **Validate in each strategy adapter.** Rejected: this duplicates an M0
   invariant in every caller and leaves non-Research target sources unsafe.
3. **Validate once in `DailyBarEngine._decide` immediately after target
   construction.** Selected: this is the first boundary that has both the
   final `TheoreticalTargetPortfolio` instrument set and the current
   `PortfolioSnapshot` holdings. It applies to every target source before risk
   and allocation without changing `NO_DECISION`.

For materialization, provider-calendar-first preflight was rejected because it
still performs provider work before discovering reference gaps. A static
plan/reference preflight over every requested calendar date is selected. It
runs before provider construction, followed by the existing provider and full
data-quality checks.

## Target-completeness behavior

- Add `DecisionBlockReason.TARGET_INCOMPLETE`.
- If the target source returns `None`, preserve `NO_DECISION`: no target exists,
  so the complete-target boundary is not entered.
- Otherwise construct the immutable theoretical target, then call the existing
  `validate_target_completeness` with all positive current holdings.
- On `TargetNotCompleteError`, retain the invalid target as evidence, produce
  no plans, bind the blocked decision digest, and record
  `TARGET_INCOMPLETE`. No HOLD or SELL is synthesized.
- Explicit zero remains an exit. An explicit current weight remains a no-delta
  retain result. Risk continues to be unable to drop or create exposure keys.

G15 will have a complete run containing an explicit zero, an explicit
unchanged weight, and an explicit unchanged treatment for the third holding;
and an incomplete run that omits that third holding and records
`TARGET_INCOMPLETE` with no plan. Expected numbers remain hand-calculated.
The actual account position remains untouched under fail-closed execution, but
that is an operational consequence of producing no order, not a synthesized
HOLD target.

## M1 compatibility

`StrategyEvaluation.NO_DECISION` remains distinct from CASH, zero, and an
incomplete target. `StrategyTargetSource` continues returning `None` only for
typed `NO_DECISION`; any actual `TARGETS` evaluation enters the M0 completeness
boundary. Existing relative-momentum behavior already emits explicit zero for
held non-winners. Callers that want no delta must emit the current target
weight explicitly.

## Phase-4 root cause and reference correction

The failed Basic ETF request starts on `2015-01-05` and materializes the
declared shared ETF asset-class scope:
`XSHG:510300`, `XSHE:159915`, `XSHG:518880`, and `XSHG:511010`.
All four canonical IDs were identical across the candidate constants, adapter
requests, canonical facts, and Instrument Master. The materializer passed the
same `default_m0_master()` to its gate and did not accept provider
classification as authority.

The concrete failure was effective-date coverage: every seeded instrument and
ETF rule family was valid only from `2022-01-04`, so the first requested date
`2015-01-05` raised `UnknownInstrumentError` for all four instruments and the
gate reported `UNKNOWN_INSTRUMENT_CLASSIFICATION`. The scope was a deliberate,
documented four-instrument shared asset-class snapshot, not a provider-driven
expansion, but its equality to the approved shared scope was not independently
preflighted.

The approved reference correction gives the four ETFs and their ETF-specific
lot, settlement, price-limit, and fee families continuous coverage from
`2015-01-05`. It retains fail-closed behavior, approved subtype authority,
same-day settlement for the approved gold/bond ETFs, and the effective-dated
ChiNext ETF price-limit change.

## Materializer preflight

Add one `preflight_materialization` boundary that runs before `_provider()`:

- reject an existing output directory;
- require the frozen plan scope to equal the declared M1 shared ETF scope;
- require the candidate universe to be a subset of that scope;
- parse and round-trip every canonical `InstrumentId`;
- resolve approved classification and subtype for every requested date;
- resolve all effective-dated rule families for every requested date;
- return typed diagnostics naming instrument, date, lookup, and reason;
- create no output directory and make no provider calls on failure.

Expose `--preflight-only` to print a deterministic PASS receipt without
constructing the provider. Normal materialization performs the same static
preflight, then constructs the pinned provider (cheap configuration/version
check), then acquires calendar/history and runs the full Data Quality Gate.
Local raw-tree completeness cannot be proven without touching the provider;
that remains a controlled-environment prerequisite and is reported explicitly.

## Verification

Use RED/GREEN tests for engine completeness, G15, M1 `NO_DECISION`, reference
coverage, preflight diagnostics/order, CLI preflight, and output immutability.
Then run the complete M0 offline suite, hardening tests, golden/replay, M1 Task
1/2 regressions, offline qualification/parity, Ruff, and strict M0 core mypy.
Live qualification and multi-hour materialization remain owner-only.
