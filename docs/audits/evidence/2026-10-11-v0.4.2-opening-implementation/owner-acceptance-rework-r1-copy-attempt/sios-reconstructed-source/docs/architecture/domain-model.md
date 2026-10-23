# Domain Model

## 1. Modeling principles

The model represents portfolio state and immutable facts. It does not model BUY/SELL as the investment decision. Identifiers, dates, currency, units, price basis, rule versions, and data availability must be explicit. Canonical objects are provider-neutral and serializable with versioned schemas.

Use immutable value objects where practical. `Decimal` (or integer minor units where appropriate) is required for money, prices, fee calculations, and weights that determine orders. Quantities are integers in the instrument’s trading unit. All timestamps are timezone-aware; exchange session dates are local calendar dates, not timestamps.

## 2. Identity and reference objects

### InstrumentId

Canonical identity is `(exchange, local_symbol)`, rendered in a stable form such as `XSHG:510300`. A six-digit symbol alone is not accepted at domain boundaries.

### Instrument / Instrument Master authority

Required fields:

- `instrument_id`, display name, currency;
- `instrument_type`: `A_SHARE` or `EXCHANGE_TRADED_FUND` for M0;
- optional `fund_subtype`, never inferred merely from symbol;
- list/delist dates;
- trading calendar ID;
- references to effective-dated lot, settlement, price-limit, market fee/tax, and corporate-action profiles;
- reference-data version and valid/effective interval.

`Instrument` describes identity. The system-owned, versioned Instrument Master is authoritative for approved classification, ETF subtype, and market/regulatory rule profiles. `chstockdata` may propose candidate reference fields but cannot override an approved profile. Changing market fee/tax or exchange rules creates/references a new effective-dated profile version rather than rewriting historical identity. Broker/account fees are not an Instrument reference.

### Instrument Master market/regulatory rule profiles

- `LotRule`: board-lot size, buy increment, and odd-lot sell policy.
- `SettlementRule`: when acquired quantity becomes sellable; configured per instrument/subtype.
- `PriceLimitRule`: limit calculation basis, rounding, exemptions, and effective dates.
- `MarketFeeTaxRule`: regulatory/exchange/tax truth such as stamp tax and exchange fees, with authoritative source and effective dates.

Unknown or unsupported rules are explicit states and cannot silently inherit an A-share default.

## 3. Market-data objects

### DailyBar

A canonical end-of-session observation with:

- `session_date`, `instrument_id`;
- raw/unadjusted `open`, `high`, `low`, `close`, `pre_close` unless the contract explicitly states otherwise;
- `volume` and `amount` with defined units;
- `adjustment_mode`, factor convention/version/as-of metadata;
- `information_available_at`, `retrieved_at`, and `availability_basis` (`OBSERVED`, `EXCHANGE_RULE`, `INFERRED`, or `UNKNOWN`);
- tradability/reference links and provider evidence;
- schema version.

The base bar and adjustment metadata must make it impossible to confuse an adjusted analysis series with an executable market price.

### TradingSession / MarketCalendar

Contains calendar ID, exchange-local session date, open/close status, optional special-session attributes, and calendar snapshot/version. `next_session(date)` is resolved from the snapshot, not by adding one weekday.

### TradabilityStatus

Point-in-time status for an instrument/session: tradable, suspended, not listed, delisted, buy blocked at upper limit, sell blocked at lower limit, or unknown. It contains `information_available_at`, `retrieved_at`, `availability_basis`, reason, and provenance. Unknown is not treated as tradable.

### CorporateAction

Versioned, effective-dated facts such as cash dividend, split/consolidation, or distribution, with ex-date, record/pay dates when available, ratios/amounts, `information_available_at`, `retrieved_at`, `availability_basis`, and provenance. The ledger applies dividends/splits/distributions only through cash/share events; an adjusted total-return series must never credit the account again.

### DataSnapshot

An immutable identity and manifest over canonical data:

- snapshot ID/content digest;
- provider name/version and adapter version;
- requested universe/date range/capabilities;
- canonical schema versions and adjustment policy;
- partition/file checksums;
- information-based knowledge cutoff and retrieval timestamps;
- quality report ID and status.

## 4. Strategy and portfolio objects

### SleeveId and target contribution

`SleeveId` is a strong value/enum with M0 values `CORE` and `SATELLITE`. A `TargetContribution` binds contributing strategy version, sleeve, instrument, proposed weight/amount, evidence, and information cutoff. Sleeve is never inferred from a strategy-name prefix or instrument type.

### Signal

A deterministic, time-bounded strategy output. Fields include signal ID, strategy version, explicit `SleeveId`, instrument, generated-at session/timestamp, information cutoff, direction/score or desired exposure contribution, evidence IDs, and data snapshot ID. A signal cannot directly mutate positions.

M0 defines the contract and test fixtures only; it does not implement Alpha logic.

### TargetPosition

Represents the desired state for one instrument and retains:

- theoretical target weight;
- executable target weight;
- current weight at a declared valuation basis;
- target amount;
- executable quantity;
- delta quantity/amount;
- constraint/reason codes and contributing strategy versions.
- explicit sleeve and per-strategy target contributions.

Unset is distinct from zero. Zero explicitly targets exit; absence means the portfolio builder did not address the instrument and is invalid for a complete M0 target. M0 defines no carry-forward policy.

### TargetPortfolio

An immutable aggregate for an account/book and a future trade date:

- target ID and revision;
- `decision_for_trade_date`, generated time, information cutoff;
- account currency and valuation equity;
- theoretical and executable positions;
- theoretical and executable cash weights/amounts plus residual cash;
- source snapshot, strategy versions, portfolio/risk rule versions, evidence IDs;
- sleeve aggregates for CORE, SATELLITE, and CASH;
- sizing reference basis/prices, fixed to finalized T close for M0;
- lifecycle state and content digest.

Invariants:

- unique instrument IDs;
- non-negative long-only weights in v1;
- theoretical instrument weights plus cash equal 1 within declared decimal tolerance;
- executable quantities satisfy lot rules and never assume negative cash;
- executable target exposure cannot exceed the approved risk-transformed theoretical bounds;
- all price/valuation bases and rule versions are present;
- sleeve is explicit for every non-cash contribution and sleeve budgets are satisfied before buy allocation;
- locked content is immutable; corrections create a superseding revision with reason and audit identity.

Executable conversion processes reductions/exits first, then approved portfolio/sleeve budgets, then buys ordered by descending absolute target-weight deficit with canonical InstrumentId as tie-breaker. It accepts complete lots, reserves fees, retains residual cash, and never renormalizes or mutates the theoretical target.

### PortfolioSnapshot

An as-of valuation of actual or simulated holdings: cash buckets, positions, unsettled/sellable quantities, prices and price basis, total equity/NAV, accrued receivables if modeled, source IDs, and timestamp/session. It is a fact, not a target.

### Position

Contains instrument, total quantity, sellable quantity, average cost (for attribution only), market value, valuation price/as-of, and settlement lots. “Sellable” is derived from dated acquisition lots and settlement rules, not assumed equal to total.

## 5. Execution objects

### ActionPlan

An immutable pre-open view derived from a locked target and reconciled portfolio. It records checks/gates, T-close sizing price basis/value, planned quantity/target/notional, intended future execution model, per-instrument deltas, estimated costs, action labels, reason codes, and generation revision. It does not contain an observed next-session open or realized gap adjustment. Labels are projections:

- positive executable delta: BUY;
- negative executable delta: SELL;
- zero material delta with continuing target: HOLD;
- no permissible risk-increasing delta: NO NEW ACTION;
- cash is a target allocation, not a security order.

### Order

Intent to change quantity with order ID, parent target/action-plan IDs, side, T-close-sized `planned_quantity`, activation-time `submitted_quantity`, order type supported by the simulator, submission/effective session, sizing price basis/value, fill-price model, status, and rule/configuration versions. At T+1 Backtest activation, the global affordability guard prices every simultaneous candidate using open plus side-aware slippage, tick rounding, and applicable fees, then applies the approved deterministic sleeve/priority order to derive legal complete-lot submitted quantities. This does not resize the theoretical target. Once submitted, each M0 order is all-or-none. M0 backtests generate simulated orders only.

If a quantity-changing corporate action becomes effective after the T-close decision and before activation, no adjusted order is synthesized. The affected pending execution is invalidated with `CORPORATE_ACTION_REPLAN_REQUIRED`; the locked theoretical target remains unchanged.

### Fill

An execution fact: order ID, instrument, side, quantity, realized fill price, timestamp/session, itemized market fees/taxes and broker-account fees, slippage attribution, and source (`SIMULATED` or later `MANUAL_RECONCILIATION`). A fill is append-only.

### Rejection

First-class execution outcome with order ID, code (cash, lot, suspension, price limit, settlement, missing rule/data), message, and evaluated facts. Rejection is not an exception if it is an expected market outcome.

## 6. Accounting objects

### CashLedgerEntry

Double-entry-inspired immutable movement with currency, amount, category (deposit, buy consideration, sell proceeds, fee, tax, dividend), event time/session, and source order/fill/action. Cash available and total cash must be distinguishable if settlement rules require it.

### Run/account execution configuration

`AccountFeeConfig` / `BrokerFeeProfile` owns account- or backtest-specific commission rate, minimum commission, agreement/source, and effective dates. It is referenced by `RunManifest` and execution/accounting services, never by `Instrument` identity or Instrument Master. Execution composes it with effective `MarketFeeTaxRule` without merging their authority or provenance.

### HoldingsLedgerEntry

Immutable quantity movement linked to fill or corporate action, including acquisition session and sellable-from session.

### NavPoint

Valuation session, cash, market value, receivables if supported, total equity, NAV relative to initial CNY 100,000, benchmark identity/value when present, terminal mode, and valuation completeness/status details. A suspended instrument normally uses its last valid RAW close plus `STALE_MARK(age)`, remains visible in NAV, and cannot gain exposure. Valuation is incomplete only when no defensible price exists, a corporate action invalidates the prior price, or identity/reference is unresolved; incomplete portfolio NAV cannot silently enter metrics.

## 7. Gate and audit objects

### GateResult

Generic persisted decision with gate name/version, status (`PASS`, `FAIL`, `WARN`), evaluated-at, input IDs/digests, individual checks, blocking scope, and reason codes. A warning never substitutes for a required pass.

### RunManifest

Captures run ID/type, code commit, environment/package lock digest, strategy and rule versions, snapshot ID, parameters, universe, date interval, separate market/broker costs and account fee configuration ID, benchmark identity, random seed, sizing-price basis, fill model, terminal mode, metric convention version (daily close returns, 252 annualization, zero risk-free/Sortino target, sample standard deviation, calendar-day CAGR, half-gross-notional/average-equity turnover, both underwater units), input/output digests, start/end times, and outcome. Before OQ-22 is decided in M1, M0 benchmark identity is explicitly `NONE` or `SYNTHETIC_TEST_BENCHMARK`; M0 never selects a real investment benchmark.

### AuditEvent

Append-only record of actor/process identity, action, object/version, time, previous/new digest where applicable, reason, and correlation/run ID. Secrets and raw credentials are excluded.

## 8. Aggregate ownership and state transitions

```text
DataSnapshot -> Quality Gate -> eligible immutable input
PortfolioSnapshot + signals -> TheoreticalTargetPortfolio
TheoreticalTargetPortfolio + risk rules -> risk-approved target
risk-approved target + prices/rules/cash -> ExecutableTargetPortfolio
Locked TargetPortfolio + reconciled PortfolioSnapshot -> ActionPlan
ActionPlan -> simulated/manual Orders -> Fills/Rejections -> PortfolioSnapshot
```

Each arrow is a pure transformation or an application transaction that persists input/output identifiers. No downstream label can mutate an upstream fact.

## 9. Schema evolution

Every persisted contract has a schema version. Readers reject unknown major versions. Migrations create verifiable derived artifacts while retaining source snapshots/manifests. Provider schema changes are absorbed by the adapter and contract tests; they do not ripple into portfolio or risk code.
