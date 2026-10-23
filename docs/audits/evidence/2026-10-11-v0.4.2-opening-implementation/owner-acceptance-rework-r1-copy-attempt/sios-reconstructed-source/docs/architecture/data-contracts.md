# Data Contracts

## 1. Purpose

These contracts isolate the quant domain from `chstockdata` and future providers. Canonical data has explicit identity, units, information timing, retrieval timing, adjustment, provenance, and schema version. A tabular shape alone is not a contract.

## 2. Provider port

`DataProviderPort` should expose narrow market-data capability methods for:

- instrument/reference records;
- exchange calendars;
- daily bars;
- point-in-time tradability/suspension state;
- corporate actions and adjustment metadata;
- provider capability/version evidence.

Each request declares universe, date range/as-of, adjustment request, and required fields/capabilities. Each response returns canonical market/reference candidates plus provider evidence or a typed failure. Empty success and provider failure are distinct results. Provider classification or trading-rule candidates never become Production authority without approval into the system-owned Instrument Master.

The port does not expose pandas/Polars frames, vendor column names, MCP payloads, HTTP details, or fallback routing. Batch/tabular conversion may exist inside an adapter but canonical records/Arrow-compatible schemas are the boundary.

## 3. Canonical daily-bar schema

| Field | Meaning / invariant |
|---|---|
| `schema_version` | semantic contract version |
| `instrument_id` | exchange-qualified canonical ID |
| `session_date` | exchange-local trading session |
| `open/high/low/close` | positive unadjusted executable prices; `low <= open, close <= high` |
| `pre_close` | prior reference close with declared semantics; positive when required |
| `volume` | non-negative quantity in declared unit |
| `amount` | non-negative traded currency amount in declared unit |
| `currency` | CNY in M0 |
| `adjustment_mode` | `RAW` for canonical execution bar; derived adjusted series declares its mode |
| `adjustment_factor` | optional decimal plus factor convention/version/as-of |
| `information_available_at` | earliest historical time a market participant could know the fact; may be unknown |
| `retrieved_at` | current-system acquisition timestamp; never substitutes for PIT availability |
| `availability_basis` | `OBSERVED`, `EXCHANGE_RULE`, `INFERRED`, or `UNKNOWN` |
| `provider_evidence_id` | trace to adapter/provider response |

Nullability is capability-specific. A required-field null fails conversion or quality gating; it is never converted to zero. Volume and amount units must be named in metadata and normalized once in the adapter.

## 4. Reference-data schemas

### InstrumentReference

Includes canonical/provider IDs, exchange, candidate type/subtype, list/delist dates, currency, calendar, timing fields, and provenance. It is provider evidence, not the approved Instrument Master. Production rule profiles are a separate versioned contract with authoritative exchange/regulator/tax source and effective dates.

### CalendarRecord

Includes calendar ID, date, session/open status, source, `information_available_at`, `retrieved_at`, `availability_basis`, and snapshot version. Cross-exchange assumptions are forbidden even if current sessions usually align.

### TradabilityRecord

Includes instrument, session/as-of, status/reason, permitted side if known, suspension details, the three availability fields, and provenance. `UNKNOWN` is a real value and blocks exposure-increasing actions.

### CorporateActionRecord

Includes action type, ex/record/pay dates as available, cash/share ratio, currency, the three availability fields, revision, and provenance. Corrections supersede prior records; they do not mutate a frozen snapshot.

### InstrumentRuleProfile

The system-owned Instrument Master publishes approved classification, ETF subtype, `LotRule`, `SettlementRule`, `PriceLimitRule`, and `MarketFeeTaxRule`, each with effective dates and authoritative exchange/regulator/tax provenance. Broker/account fee configuration is not Instrument identity, Instrument Master data, or a provider data contract; it belongs to the backtest/Production run configuration.

## 5. Provider evidence and errors

Every provider call produces evidence containing provider/adapter name and version, capability, request digest, `retrieved_at`, upstream source identity if exposed safely, record count, raw payload checksum or stable normalized checksum, and warnings. Record-level `information_available_at` and its basis remain separate.

Typed error categories include authentication/configuration, unavailable/rate-limited, schema drift, malformed data, partial result, unsupported capability, and internal adapter error. Logs redact credentials and sensitive request values. Provider-internal fallback is evidence, not an independent validation source.

## 6. Snapshot contract

A frozen snapshot manifest contains:

```yaml
snapshot_id: content-derived-or-immutable-id
created_at: timezone-aware timestamp
knowledge_cutoff: information-semantics cutoff, not retrieval time
provider: {name: chstockdata, version: exact-version-or-commit}
adapter_version: semantic-version
schemas: {daily_bar: v1, instrument: v1, calendar: v1}
scope: {instrument_ids: [...], start: ..., end: ...}
adjustment_policy: RAW_WITH_POINT_IN_TIME_FACTORS
availability_policy: {allowed_bases: [OBSERVED, EXCHANGE_RULE, INFERRED], unknown_handling: explicit}
retrieved_at: timezone-aware timestamp
artifacts:
  - {logical_partition: ..., checksum: ..., row_count: ...}
quality_report_id: ...
quality_status: PASS
```

Snapshots are immutable and self-validating. `knowledge_cutoff` is evaluated against `information_available_at`; equal download times do not make historically unavailable facts accessible. `UNKNOWN` remains explicit and is accepted or rejected only by a versioned purpose policy. Changing data, metadata, availability semantics, or rule profiles yields a new ID. A research run may only claim reproducibility when its full input is reachable by immutable manifest and checksums.

## 7. Data Quality Gate

Checks are capability- and run-type aware but deterministic:

- required fields and schema versions;
- unique `(instrument_id, session_date)` keys;
- expected calendar coverage and no bars on closed sessions;
- freshness relative to the intended decision session;
- OHLC, positivity, volume/amount, and pre-close consistency;
- provider reference coherence plus approved Instrument Master classification/rule-profile availability; conflicts use the approved Instrument Master or fail closed, never provider override;
- corporate-action/adjustment coherence;
- tradability coverage where required;
- snapshot manifest/checksum integrity;
- optional independent-source tolerance checks.

Each check returns status, severity, affected scope, observed/expected values, reason code, and evidence IDs. Aggregate PASS requires all blocking checks to pass. Thresholds and exemptions are versioned configuration, never undocumented constants.

The gate controls eligibility for a declared purpose. A dataset can pass historical research coverage but fail a same-day Production freshness requirement.

## 8. ETF-DATA-GATE

Qualification is by ETF subtype/capability. M0 scope is domestic broad-based equity ETFs, gold ETFs, and bond ETFs. It verifies symbol routing, history coverage, finalized daily OHLCV/pre-close, calendar alignment, volume/amount units, suspension/tradability, adjustment/corporate-action semantics, information timing/freshness, and independent sample parity. Cross-border/QDII, money-market, and every other unverified subtype are unsupported.

Output is an immutable qualification report with provider version, adapter version, instruments/subtypes, dates and edge cases, independent evidence, tolerances, failures, and approved capability scope. Only the qualified scope may be used. Provider upgrades invalidate the prior Production qualification until contract, ETF, golden, and smoke suites pass again.

Golden edge-event evidence is manually frozen from public exchange rules/data. Independent parity may use JoinQuant as a legal validation-only research reference or another independent lawful source; reports record source, access date, semantics, and tolerance. Passing one subtype never approves another.

## 9. ChStockDataProvider anti-corruption rules

- Pin an exact compatible version/commit; never follow floating `main` in Production.
- Import `chstockdata` only inside the adapter package.
- Map provider symbols, dates, units, nulls, classifications, and exceptions explicitly.
- Treat provider classification/rule data as candidates; Production consumes only approved Instrument Master profiles.
- Reject unknown columns/enum values when they affect semantics; harmless additive fields may be recorded and ignored under a compatibility policy.
- Keep raw provider evidence/checksums for diagnosis without making raw shapes part of domain APIs.
- Test with recorded/synthetic fixtures; network calls belong only to opt-in qualification tests.
- Do not recreate Tencent/TDX/mootdx/Sina/Eastmoney/exchange scraping or provider fallback in this repository.

## 10. Schema compatibility

Major versions break readers; minor versions add optional, semantically compatible fields. Consumers declare supported versions. Adapter upgrades run contract tests before snapshot creation. Historical manifests retain their original schema and are migrated only by a new, checksum-linked derived artifact.

## 11. Independent validation

Independent validation must be legally usable and operationally separate from `chstockdata`’s internal vendors. Manually frozen public exchange rules/data validate immutable golden edge events. JoinQuant may provide broader parity outside the core runtime when legally used, as may another independent lawful source. Source, access date, permissible use, information semantics, transformation, and tolerances must be documented.
