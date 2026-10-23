# Architecture Decision and Open-Question Register

## Status

The product/architecture authority remains `docs/personal-systematic-investing-os-v0.2-final-architecture-decision-rev2.md`. The Architecture Review decision dated 2026-09-14 approved OQ-01 through OQ-10 with the refinements recorded below. Those items are no longer open and must not be re-presented as choices during M0 implementation.

## A. Resolved owner decisions

### OQ-01 — ETF qualification matrix and independent validation — RESOLVED

M0 qualification is capability-scoped to domestic broad-based equity ETFs, gold ETFs, and bond ETFs. Cross-border/QDII, money-market, and every other unverified subtype are unsupported. Golden edge-event fixtures are manually frozen from public exchange rules/data. Independent parity may use legally accessed JoinQuant in validation-only Research or another lawful independent source, recording source, access date, semantics, and tolerance. Passing one subtype never approves another.

### OQ-02 — Next-bar execution model and sizing/fill separation — RESOLVED

M0 uses `sizing_reference_price_basis = T_CLOSE` and `execution_price_model = NEXT_SESSION_OPEN`, plus side-aware slippage and explicit tick rounding. Sizing uses only T-known facts. Pre-open publishes planned quantity/target/notional and cannot observe the future open. In Backtest, T+1 activation performs global affordability using slippage-adjusted/tick-rounded execution prices plus fees and may reduce complete-lot submitted quantities; future Production reduction belongs to manual execution or execution-time confirmation. Neither path may mutate/re-optimize the theoretical target. Other execution models are explicit versioned scenarios; future `PREOPEN_REFERENCE_PRICE` is outside the M0 default.

### OQ-03 — Residual cash and capital competition — RESOLVED

Process reductions/exits first, enforce approved portfolio/sleeve budgets, then allocate buys within each budget by descending absolute target-weight deficit with canonical InstrumentId tie-breaker. At simultaneous T+1 activation, affordability is one global calculation using slippage-adjusted/tick-rounded execution prices plus applicable fees and the same priority. Accept complete executable lots and preserve residual cash without renormalizing or altering the theoretical target.

### OQ-04 — Gate failure and risk-reducing actions — RESOLVED

Gate results are scoped. Critical decision-data failure blocks creation of a new target; critical pre-open failure blocks all risk-increasing orders. A risk-reducing order proceeds only when instrument identity, current holding, sellable quantity, current tradability, and conservative price/cost basis are independently reliable. If any necessary fact is unavailable, emit no order plus an urgent manual-review alert.

### OQ-05 — Raw price, adjustment, and corporate actions — RESOLVED

RAW/unadjusted prices are execution/accounting truth. Adjustment factors and corporate actions are stored separately. Research-derived point-in-time adjusted series carry factor convention, version, as-of, and information-availability metadata. Dividends, splits, and distributions enter accounting only as ledger events; adjusted total-return data and ledger credits cannot both recognize the same value. A quantity-changing action effective between T-close decision and T+1 activation invalidates the affected pending execution with `CORPORATE_ACTION_REPLAN_REQUIRED` and does not mutate the locked theoretical target.

### OQ-06 — Terminal valuation — RESOLVED

Default backtest termination is mark-to-market at the final session with no fictional liquidation. Forced liquidation is a separately named/versioned scenario producing real simulated orders, fees, taxes, tradability constraints, and possible rejection. Reports and manifests state terminal mode.

### OQ-07 — Metric conventions — RESOLVED

M0 defaults are daily close-to-close periodic returns, 252-session annualization, zero risk-free rate, zero Sortino target, sample standard deviation, actual-calendar-day CAGR, turnover of `0.5 * gross traded notional / average equity`, and underwater duration in both trading sessions and calendar days. All conventions are versioned in `RunManifest`; changes create new run identity and never rewrite history.

### OQ-08 — Effective-dated market rules and account fees — RESOLVED

M0 profiles cover standard Shanghai A-shares, standard Shenzhen A-shares, and OQ-01 ETF scopes; unsupported profiles fail closed. Instrument Master market/regulatory truth (settlement, lot, price limits, tax/exchange fees, listing/ST rules) is effective-dated and backed by exchange/regulator/tax provenance. Account-specific commission/minimums belong to backtest/account run configuration as separate `AccountFeeConfig`/`BrokerFeeProfile`; they are not Instrument identity/reference or exchange truth.

### OQ-09 — Suspended/missing-close valuation — RESOLVED

Use the last valid RAW close plus `STALE_MARK(age)` for a suspended/missing-close position, expose staleness in NAV/report/audit, process corporate actions, and prohibit increased exposure. Long suspension alone does not invalidate portfolio metrics. Valuation becomes incomplete only when no defensible price exists, a corporate action makes the prior price economically invalid, or instrument identity/reference is unresolved; only then are complete-portfolio metrics blocked.

### OQ-10 — Partial order policy — RESOLVED

During `TargetPortfolio -> ExecutableTargetPortfolio` conversion, quantity may fall to the maximum legal complete lot with a constraint reason and non-negative cash. After entry to the M0 daily-bar simulator, submitted quantity is all-or-none. M0 does not simulate intraday partial-liquidity fills.

## B. Resolved P0 architecture requirements

### P0-01 — Instrument Master authority is separate from chstockdata

`chstockdata` supplies market data, calendar/suspension/corporate-action facts, provenance, and candidate reference information. The system-owned versioned Instrument Master is Production authority for classification, ETF subtype, lot, settlement, price limits, market fee/tax rules, and effective dates, with authoritative-source provenance. Provider conflicts use the approved Instrument Master or fail closed.

### P0-02 — Information availability is separate from retrieval

Canonical historical facts carry `information_available_at`, `retrieved_at`, and `availability_basis` (`OBSERVED`, `EXCHANGE_RULE`, `INFERRED`, `UNKNOWN`). PIT/no-lookahead and snapshot `knowledge_cutoff` use information semantics only. Unknown availability remains explicit.

### P0-03 — Sizing reference price is separate from fill price

Targets and pre-open Action Plans retain T-close sizing basis/value and planned quantity/target/notional. They may declare the intended `NEXT_SESSION_OPEN` model but cannot contain an observed open or realized gap adjustment. Backtest activation Orders retain planned/submitted quantities and modeled execution price; Production manual Fills retain actual quantity and realized fill price. T+1 prices can constrain executable lots only at execution/activation and cannot alter the T-time theoretical target.

### P0-04 — CORE/SATELLITE is a strong portfolio concept

`SleeveId` initially contains `CORE` and `SATELLITE`; CASH is separately aggregated. Portfolio contributions retain strategy, sleeve, instrument, and target contribution. Risk computes sleeve exposure/caps directly. Strategy-name prefixes and instrument-type guesses cannot determine sleeve. Regime-specific Satellite cap values are deferred.

## C. Open questions deferred to later milestones

These questions do not block M0 Foundation. Each becomes blocking only at its named gate.

### OQ-11 — Meaning of fixed CNY 100,000 in live Production

**Recommendation:** Keep CNY 100,000 fixed for default backtests, paper inception, and goldens. Production targets use reconciled actual equity; reports may additionally show a normalized CNY 100,000 model portfolio.

**Gate:** M3 Paper/Production.

### OQ-12 — Target lock amendment authority and cutoff

**Recommendation:** Only explicit owner-authorized supersession may amend a target before the pre-open plan is locked; afterward cancel/supersede the plan with a new revision. Automated retries cannot supersede. Retain prior/new digests and reason.

**Gate:** M3/M4 runtime.

### OQ-13 — Position reconciliation source and trigger

**Recommendation:** Automatically carry forward a prior reconciled state when there are no unresolved fills, external/manual trades, deposits/withdrawals, or detected mismatches. Require human reconciliation only after an executed/unresolved trade, external trade, cash movement, or position mismatch. Every snapshot retains source, as-of, digest, and balance checks.

**Gate:** M3/M4.

### OQ-14 — Research/Production promotion authority and isolation

**Recommendation:** Share only versioned core libraries; use separate entry points, environments/credentials, and storage authority. Promotion requires explicit owner approval, immutable content digest, and audit record. Do not introduce multi-person approval, external signing services, or complex PKI for this single-user product.

**Gate:** M2/M3.

### OQ-15 — ETF Core first universe

**Recommendation:** Select a small, liquid, economically distinct universe from ETF subtypes that passed M0 qualification; avoid redundant exposures and newly listed funds.

**Gate:** M1.

### OQ-16 — ETF Core parameter research ranges

**Recommendation:** Pre-register a small economically motivated grid for absolute trend, relative momentum, and defensive allocation, including perturbation bands, before viewing holdout results.

**Gate:** M1.

### OQ-17 — Paper Forward duration and promotion gate

**Recommendation:** Require both minimum calendar duration and minimum signal/regime coverage, operational completeness, and pre-registered statistical/portfolio evidence rather than a single return threshold.

**Gate:** M2/M3.

### OQ-18 — ServerChan format, severity, and dedupe policy

**Recommendation:** Use one compact normal template per EOD/pre-open run, stable business-key dedupe, severity mapped to required user action, bounded exponential retry, and audit receipt. Do not resend unchanged normal messages.

**Gate:** M4.

### OQ-19 — Stock Satellite universe and first strategy families

**Recommendation:** Decide liquidity, listing age, ST/suspension, sector, and survivorship-safe universe rules before choosing 3–5 simple strategy families. Pre-register risk caps under ETF Core regimes.

**Gate:** M6.

### OQ-20 — Canary capital and per-strategy budget

**Recommendation:** Decide after Paper Forward evidence and an operational incident drill; establish loss/risk limits before return targets and keep execution manual.

**Gate:** post-M4 live canary.

### OQ-22 — Benchmark policy

**Recommendation:** Pre-register ETF Core benchmark, whole-portfolio benchmark, and cash/risk-free comparator. Version them in `RunManifest`; do not select a favorable benchmark after seeing strategy performance.

**M0 interim rule:** Until this is decided, every M0 `RunManifest` declares benchmark `NONE` or `SYNTHETIC_TEST_BENCHMARK`. M0 does not select a real investment benchmark.

**Gate:** before M1.

### OQ-23 — Economic meaning of CASH versus defensive asset

**Recommendation:** Define CASH as true zero-return cash for the initial comparison unless the owner explicitly selects a versioned interest/accrual rule. A money-market, bond, or repo-like defensive asset is an investable position, not CASH, and must not be substituted after observing results.

**Gate:** before M1.

### OQ-24 — Stock Satellite dividend-tax semantics

**Recommendation:** Model effective-dated personal-investor dividend tax as a dedicated corporate-action/tax policy, not a normal transaction `FeeProfile` field.

**Gate:** before Production-grade Stock Satellite backtesting/M6.

## D. Current M0 blocking status

No unresolved semantic question in this register blocks M0 coding after this Architecture Revision is approved. Coding remains administratively blocked until the owner completes the next human review and explicitly authorizes M0 implementation.
