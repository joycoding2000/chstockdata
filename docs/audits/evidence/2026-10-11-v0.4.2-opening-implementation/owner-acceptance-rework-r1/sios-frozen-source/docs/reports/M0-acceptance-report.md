# M0 Foundation Acceptance Report

**Acceptance evidence date:** 2026-09-17
**Scope:** M0 Foundation only; no M1 strategy work is included.

## Offline acceptance

- Required offline suite:
  `python -m pytest tests/unit tests/contract tests/component tests/golden tests/integration -q`
  (executed with pytest cache disabled because the managed workspace denies its cache directory):
  **597 passed, 0 failed, 0 skipped**.
- Task 11 offline qualification and parity regression:
  **28 passed, 0 failed, 5 live-only tests skipped by their explicit opt-in gate**.
- Repository-wide offline suite (excluding the separately controlled Google API
  key check): **712 passed, 0 failed, 5 live-only tests skipped**.
- Ruff static check over `src` and `tests`: **PASS**.
- Strict mypy check over the Task 12 boundary and run-identity code: **PASS (3 source files)**.
- The import-boundary audit found no vendor import outside
  `adapters/chstockdata`, no core dependency on provider adapters, and no
  Research/LLM import in trusted core or Production namespaces.
- The package audit found no Web/UI, scheduler, notification, strategy, LLM,
  broker-routing, or microservice package in M0.

## Qualification and independent parity evidence

- ETF qualification report ID: `m0-etf-qualification-report-1`
  - matrix: `m0-etf-matrix-1`
  - digest: `sha256:4943bf64685482a5cc1e380ae3553e5f140e36198c89286ec07d7e3be1c9aee3`
  - approved recorded/offline scope: domestic broad-based equity, gold, and
    bond ETFs; cross-border/QDII, money-market, and other unverified subtypes
    remain unsupported.
- Independent parity report ID: `m0-parity-report-1`
  - cases: `m0-parity-2` (12 passed, 0 failed)
  - digest: `sha256:d8b9cde55cfeb6eccd504ba23895d1b2f89000aa453a60199eec70930aa4b5c2`

## Foundation hardening findings

- **P2 — historical reference-data coverage and diagnostics:** all four approved
  ETF identifiers (`XSHG:510300`, `XSHE:159915`, `XSHG:511010`, and
  `XSHG:518880`) first failed Instrument Master classification/profile lookup
  on 2015-01-05 because their approved records started only on 2022-01-04.
  The provider, request, snapshot, and Instrument Master identifiers were
  canonical and identical. The materializer passed the approved master into
  the gate correctly, but did not preflight that coverage before expensive
  provider work. The approved ETF profiles now cover the Basic window and a
  typed preflight reports the check, reason, identifier, session date, and
  failed lookup while preserving the final fail-closed gate.
- **P0 — financially incorrect rule seeds:** the approved gold and bond ETFs
  incorrectly inherited T+1 sellability, and ChiNext ETF `XSHE:159915`
  incorrectly retained a 10% price limit after 2020-08-24. Effective-dated
  system-owned profiles now encode same-day sellability for the gold/bond
  ETFs and the 159915 10%-to-20% transition. Provider classification remains
  candidate evidence only; unapproved instruments and rule gaps still fail
  closed.
- The four-instrument materialization scope is the deliberately shared M1
  approved ETF Basic snapshot, not an undeclared provider-driven expansion.
  Candidate-specific universes remain subsets of that approved scope.

## Reproducibility evidence

The 21 golden scenarios contain 25 named runs. Their normalized ledger,
order/fill/rejection, NAV, metric, and probe evidence was canonically sorted,
serialized, and hashed independently of the golden expected files:

`sha256:c50f21fc4450cc88d89eb47eb3b45ce822e1dbdf33d26a0fca84841e2651841f`

The integration suite also persisted each applicable scenario twice in
isolated directories, verified snapshot checksums, replayed it, and compared
normalized outputs and digests.

## Dependency, provenance, and credential audit

- `pyproject.toml` declares no core runtime dependency. Development tools are
  exactly pinned (`mypy==2.3.1`, `pytest==9.1.1`, `ruff==0.16.6`).
- `third_party/SOURCES.yaml` contains the sole domain-specific provider intake:
  `chstockdata` 0.3.0 at commit
  `143eb5a3c0e02a95b1c11a2e7c61e8ac470b5f77`, Apache-2.0, imported lazily
  only through its anti-corruption adapter. It remains optional so offline
  core tests do not require the vendor package.
- No external source code, vendor object, raw credential, API key, private key,
  bearer token, or proxy credential was found in tracked M0 source, tests,
  fixtures, reports, or provenance records. Credential prerequisites record
  names and conditions only, never secret values.

## Known limitations

- Live ETF qualification remains an opt-in controlled-release check requiring
  the pinned provider and local market-data tree. This local acceptance run
  validated the immutable recorded/offline report; its five live-only tests
  were not enabled.
- Repository-wide strict mypy currently reports 90 pre-existing findings in
  11 Task 2–11 source files. Task 12 code is strict-clean; correcting upstream
  annotations and narrowing issues would be a separate cross-layer change and
  was not hidden by relaxing type-check settings.
- Daily bars cannot prove intraday path or limit-queue fill probability. Free
  provider data has no SLA, and only the three approved ETF subtype scopes are
  qualified.
- M0 contains contracts and static controls for Research/Production separation,
  not a Production runtime, promotion service, broker integration, scheduler,
  notification system, Web UI, or investment strategy.

## Deferred milestone questions

- **OQ-11 (M3):** meaning of fixed CNY 100,000 in live Production.
- **OQ-12 (M3/M4):** target-lock amendment authority and cutoff.
- **OQ-13 (M3/M4):** position reconciliation source and trigger.
- **OQ-14 (M2/M3):** operational Research/Production promotion authority and isolation.
- **OQ-15 (M1):** first ETF Core universe.
- **OQ-16 (M1):** ETF Core parameter-research ranges.
- **OQ-17 (M2/M3):** Paper Forward duration and promotion gate.
- **OQ-18 (M4):** ServerChan format, severity, and deduplication policy.
- **OQ-19 (M6):** Stock Satellite universe and first strategy families.
- **OQ-20 (post-M4):** canary capital and per-strategy budget.
- **OQ-22 (before M1):** benchmark policy; M0 remains `NONE` or
  `SYNTHETIC_TEST_BENCHMARK` only.
- **OQ-23 (before M1):** economic meaning of CASH versus a defensive asset.
- **OQ-24 (before Production-grade M6):** Stock Satellite dividend-tax semantics.

## Owner review gate

Task 12 stops here for owner review. This report does not authorize M1,
Production deployment, merge, push, release, or publication.
