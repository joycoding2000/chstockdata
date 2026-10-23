# Historical opening execution eligibility (R2.1)

This is an explicit historical replay execution mode. Legacy mode and its UTC
clock remain the defaults. This does not authorize a research phase or release.

## Separate inputs and the legacy gap

`HistoricalOpeningRequest(instrument_ids, session_date)` is served by the optional
`HistoricalOpeningProviderPort.fetch_historical_opening_evidence`. The library
client uses the actual `chstockdata.fetch_historical_opening_evidence` result;
metadata success is never treated as permission. `HistoricalOpeningEvidence`
retains the complete immutable canonical JSON payload and validates its
`evidence_hash`, policy, purpose, identity, target window, and positive source
contract. Its information availability may remain UNKNOWN.

The original `fetch_tradability` still returns a typed failure for missing
historical suspension coverage. Only the vendor's exact
`historical_suspension_unavailable` failure becomes
`HistoricalSuspensionUnavailableError`. For a single instrument,
`provider.historical_suspension_gap(request, failure)` verifies the failure's
request digest and provenance, and produces an UNKNOWN constraint whose explicit
reason is `HISTORICAL_SUSPENSION_COVERAGE_UNAVAILABLE`. This is not a PIT success.
Generic failures, partial results, future coverage, and missing facts cannot be
converted to that reason.

## Execution boundary

Pass `ExecutionEligibilityMode.HISTORICAL_OPENING_R21`, independent
`historical_opening_evidence`, and `EngineClock.shanghai()` to `DailyBarEngine`.
The engine uses these facts only in pending-order activation. DecisionContext,
strategy data filtering, T-close targets and sizing, and required PIT quality
checks remain unchanged. The new evidence may replace only the explicit legacy
gap. NOT_LISTED, DELISTED, side blocks, general UNKNOWN, missing facts or approved
rules still refuse execution. UNKNOWN or conflicting opening evidence refuses
execution; official target-time blocks retain their veto. No intraday retry is
added.

The new clock requires equivalent aware instants for Shanghai 09:15 activation,
09:30 execution, and 15:30 decision. An equivalent UTC instant is valid; naive
times and UTC 09:30 targets are invalid. RAW daily open, existing slippage, ticks,
fees, cash, lots, all-or-none and T+1 arithmetic are unchanged. Activity volume
and evidence prices never supply a fill quota or a fill price.

## Snapshot, identity, and public research entry points

`CanonicalDataset.historical_opening_evidence` defaults to an empty tuple.
Empty legacy content retains the frozen dataset digest. Legacy snapshot version
`v2` is unchanged, including manifest bytes and snapshot identity. A fact-bearing
snapshot uses `v3-historical-opening` with a separate full-payload partition,
R2.1 policy, Shanghai clock identity, and full evidence digest. The reader verifies
all artifact hashes before parsing any record. Explicit new-mode loading rejects
old snapshots or missing policy, clock, partition or evidence identity.

`build_basic_wiring` and `build_oos_wiring` accept an explicit
`execution_eligibility_mode`; their verified intake receipts bind the actual
execution facts and inject the actual Shanghai engine clock. CLI
`basic-backtest`, `oos-freeze` and `oos-run` expose
`--execution-eligibility-mode HISTORICAL_OPENING_R21` and default to LEGACY.

Kernel/freeze identity binds mode, R2.1 and the Shanghai clock. The actual v3
snapshot digest binds the complete execution facts in the RunManifest. Execution
fact changes therefore change run identity without reading OOS evidence before
freeze. Freeze replay requires an explicit matching mode: old freezes cannot
silently become new-mode runs, and new-mode freezes cannot silently become legacy
runs. Existing immutable M0/M1 artifacts are not rewritten.

The pinned library version remains 0.3.0 by default. Only a caller explicitly
constructing `LibraryChStockDataClient(historical_opening_candidate=True)` can
admit the current 0.4.2 candidate for qualification. This is not general new
version admission or a release qualification.

## Owner-approved R5 mandatory live contract

The five original live test names and the frozen four-ETF matrix and history
windows remain mandatory. The opt-in switch remains
`SIOS_CHSTOCKDATA_LIVE_QUALIFICATION=1`; normal offline CI may skip these five,
but a qualification run must execute all five without skips or deselection.
The controlled qualification client explicitly admits actual version 0.4.2;
default clients still reject that candidate under the unchanged 0.3.0 pin.

Each security's original historical PIT call must retain its actual typed
failure and explicit UNKNOWN provenance. The revised assertion then requires a
real R2.1 request, complete identity/hash/window validation, and a real v3
snapshot replay through `DailyBarEngine` with nonempty T-close plans and a RAW
daily-open-based fill. Official 513100/159509 halt cases are source controls
only; a test-local master isolates their event veto without qualifying QDII.
Both controls require rejected orders and no intraday retry.

Corporate actions, RAW bars, aware retrieval and information timestamps,
routing, OHLCV, pre-close, units, calendar and complete history coverage remain
mandatory. Freshness uses the existing `DatasetPolicy` relative to the intended
historical session, with stale and missing-pre-close negative controls. Every
independent capability is attempted and records its own outcome before aggregate
failure, so an old PIT or opening-source failure cannot hide actions or freshness.
Deterministic orchestration regressions are separate from actual live evidence.

This is a formal Owner-approved replacement of the invalid historical success
assumption, not a waiver or a claim of recovered full historical suspension
coverage. The proxy establishes activity in Shanghai [09:30,09:31), not 09:15
knowledge, all-day normality, or guaranteed arbitrary-order execution at 09:30.
Source-code qualification precedes the independently built candidate artifact
Gate and does not authorize Step4 acceptance, publishing or phase advancement.
