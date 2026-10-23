# M0 Test Plan

## 1. Quality objective

M0 optimizes for semantic correctness, reproducibility, and explainable differences—not feature count. Tests must prove observable financial/accounting outcomes from small, hand-auditable fixtures. Network availability and large historical backtests are not substitutes for correctness tests.

## 2. Test layers

| Layer | Purpose | Network | Required for normal CI |
|---|---|---:|---:|
| unit | value objects, invariants, rounding, fees, metrics, rule decisions | no | yes |
| contract | canonical schemas and adapter mapping/error behavior | no; recorded/synthetic provider fixtures | yes |
| component | portfolio conversion, backtest event loop, ledger/accounting | no | yes |
| golden | exact hand-calculated ledgers/NAV/reason codes | no | yes |
| integration | snapshot persistence/replay and adapter package compatibility | normally no | yes |
| qualification | live `chstockdata` ETF capabilities/freshness | yes, opt-in | release/provider-upgrade gate |
| parity | compare documented scenarios with independent engines/sources | separate legal/research environment | release evidence |
| architecture/security | import boundaries, secret/log redaction, manifest integrity | no | yes where automatable |

Tests use fixed calendars, timestamps, Decimal values, and sorted canonical outputs. They never depend on today’s date unless explicitly marked live qualification.

## 3. Canonical fixture design

Keep fixtures minimal and readable:

- 3–8 sessions per event-order case;
- Shanghai/Shenzhen A-share and approved domestic broad-based equity/gold/bond ETF representatives with explicit, effective-dated Instrument Master profiles;
- synthetic prices designed for exact arithmetic;
- separate raw bars, adjusted-factor facts, corporate actions, and tradability facts;
- expected orders, fills/rejections, cash ledger, holdings ledger, NAV, and metrics committed as golden artifacts;
- a manifest documenting the economic story and manual calculation.

Golden updates require an explanation and reviewer approval. A bulk “accept new snapshots” command must not be the normal workflow.

## 4. Required golden cases

### G01 — T-close sizing, T+1-open fill

Target generated after T close and quantity sized from finalized T close; verify no T fill, pending order creation, `NEXT_SESSION_OPEN` fill plus side-aware slippage/tick rounding, and separate sizing/realized price metadata.

### G02 — Insufficient cash and minimum commission

Start CNY 100,000, request an unaffordable target, reserve minimum commission, round down/skip according to the chosen policy, and prove cash never becomes negative.

### G03 — Lot rounding and residual cash

Use target amount not divisible by the instrument lot. Verify theoretical weight remains unchanged, executable quantity/weight differ, and residual cash is explicit.

### G04 — Stock fees and sell tax

Round-trip an A-share with separate effective-dated market fee/tax rules and broker-account fee configuration. Assert itemized buy/sell commission, minimums, sell tax, cash entries, provenance, and net NAV.

### G05 — ETF fee/tax profile

Run the same notional through each approved ETF subtype profile. Assert configured market-tax/fee and broker-fee behavior without inheriting stock defaults or approving another subtype.

### G06 — Suspension/non-tradable

Activate a pending order on a suspended/unknown-status session. Assert no fill, a typed rejection, unchanged holdings/cash, and unmet target.

### G07 — Limit-up rejected buy

Provide upper-limit tradability evidence. Verify buy rejection and no synthetic partial fill.

### G08 — Limit-down rejected sell

Provide lower-limit evidence. Verify sell rejection and retained position valuation.

### G09 — T+1 sellability

Buy a T+1 instrument and attempt same-session sale; assert rejection/reduction and next-session sellability. Pair with a configured ETF subtype case to prove rules are not globally hard-coded.

### G10 — No lookahead

Change T+1/T+2 bars while keeping information through T identical; the T decision and pending order must remain byte-normalized/digest-identical. Requesting a future slice must fail loudly.

### G11 — Corporate action / adjustment no double count

Apply a split or cash dividend and assert ledger quantities/cash and valuation. A derived adjusted analysis series must not cause a second account credit.

### G12 — Drawdown and underwater duration

Use a hand-authored NAV path containing recovery and an unrecovered tail. Assert peaks, drawdowns, maximum depth, session duration, and calendar duration.

### G13 — Terminal semantics

Compare mark-to-market termination with explicit forced-liquidation scenario. Assert fees/taxes/rejections occur only in the latter and report metadata states the mode.

### G14 — Multi-target capital competition

Make simultaneous T+1 candidates collectively unaffordable. Assert one global affordability pass using each side-aware-slippage-adjusted, tick-rounded execution price plus applicable market/broker fees; then reductions first, sleeve budgets before buys, descending absolute target-weight deficit, canonical InstrumentId tie-breaker, complete lots, explicit residual cash, and independence from map/input ordering.

### G15 — Target completeness and zero vs absent

For existing holdings, assert that explicit target zero creates an exit, an explicit unchanged target creates no delta, and a target missing any held instrument fails closed with `TARGET_INCOMPLETE` and no executable plans. Missing must not silently become SELL/HOLD; M0 has no carry-forward policy.

### G16 — Gap-up lot reduction without target mutation

Size simultaneous `planned_quantity` values from T close, then provide T+1 opens whose side-aware-slippage-adjusted, tick-rounded execution prices plus fees make the plan globally unaffordable. Verify the approved global priority produces deterministic complete-lot `submitted_quantity` reductions, all-or-none fills of submitted quantities, non-negative cash, per-order constraint reasons, and byte-identical theoretical targets/planned-quantity evidence before/after execution.

### G17 — PIT information time versus retrieval time

Give two facts the same `retrieved_at` but different `information_available_at`; verify historical accessibility differs at the decision cutoff. A fact with `availability_basis = UNKNOWN` must not acquire a fabricated exact time.

### G18 — Instrument Master authority conflict

Make provider candidate classification/rules conflict with the approved, effective-dated Instrument Master. Verify Production uses the approved authority when valid and fails closed when no approved profile covers the session; it never promotes provider metadata implicitly.

### G19 — Explicit sleeve aggregation and cap

Provide CORE and SATELLITE target contributions with explicit `SleeveId`. Verify per-sleeve aggregation, deterministic Satellite cap enforcement, contribution traceability, and no inference from strategy name or instrument type.

### G20 — Long suspension stale valuation

Hold an instrument through a long suspension. Verify last valid RAW close plus `STALE_MARK(age)`, explicit NAV/audit metadata, corporate-action ledger processing, and prohibition on risk increase. A paired truly unpriceable case—no defensible price, economically invalidated prior price, or unresolved identity—must produce incomplete portfolio NAV.

### G21 — Intervening quantity-changing corporate action

Create a T-close decision and then make a split, consolidation, distribution, or other quantity-changing corporate action effective before T+1 activation. Verify the affected pending execution is invalidated with `CORPORATE_ACTION_REPLAN_REQUIRED`, no rescaled/substitute order is submitted, holdings receive the normal ledger event, and the locked theoretical target/digest remains unchanged.

## 5. Data contract and gate tests

- provider symbol to exchange-qualified ID mapping;
- date/timezone and session-date conversion;
- distinct `information_available_at`, `retrieved_at`, and `availability_basis`, including `UNKNOWN`;
- units for volume/amount and Decimal conversion;
- required null versus genuine zero;
- duplicate key rejection;
- OHLC and pre-close consistency;
- open/closed calendar alignment;
- freshness using injected clock and purpose-specific cutoff;
- provider-versus-Instrument-Master authority conflict and unknown instrument/ETF subtype/rule profile fail closed;
- provider empty result differs from provider error/partial result;
- schema drift produces typed failure;
- manifest/checksum corruption is detected;
- identical normalized inputs yield identical snapshot ID;
- provider upgrade forces qualification evidence refresh.

Adapter contract tests must ensure domain/quant objects contain no vendor data-frame or vendor-specific enum/type.

## 6. ETF qualification suite

For domestic broad-based equity, gold, and bond ETF representative matrices, run live/recorded checks over normal sessions and known edge events. Verify routing, OHLCV/pre-close, units, coverage, calendar, tradability/suspension, adjustment/corporate-action meaning, information timing/freshness, and independent-source tolerances. Golden edge evidence is manually frozen from public exchange rules/data; JoinQuant or another lawful independent source is validation-only.

The report is capability-scoped: passing one approved subtype does not approve another. Cross-border/QDII, money-market, and every other unverified subtype remain unsupported. Record exact `chstockdata`/adapter versions, information/retrieval timing, upstream evidence, independent source/access date/semantics, tolerance, and every excluded instrument/subtype.

## 7. Portfolio/risk property tests

Property-based tests are useful only for invariants with bounded generated cases:

- theoretical long-only weights plus cash equal one;
- CORE/SATELLITE contributions aggregate from explicit sleeves and obey sleeve budgets/caps;
- executable quantities respect lot rules;
- cash never becomes negative after reserved/final fees;
- risk transformations do not increase unapproved exposure;
- repeated identical inputs are deterministic;
- input ordering does not change output under the chosen allocation policy;
- serialization round-trips preserve IDs, Decimal values, dates, and digests.

Each property suite retains a small fixed regression fixture for any discovered counterexample.

## 8. Metrics tests

Use direct hand-calculated series for total return, calendar-day CAGR, sample volatility, Sharpe, Sortino, max drawdown, Calmar, underwater duration, turnover, and zero-denominator/short-history behavior. Defaults are daily close-to-close returns, 252-session annualization, zero risk-free/Sortino target, `0.5 * gross traded notional / average equity`, and both underwater units. Long-suspension `STALE_MARK` NAV remains reportable; only truly incomplete portfolio NAV causes typed refusal.

Until OQ-22 is decided before M1, manifest tests accept only benchmark identity `NONE` or `SYNTHETIC_TEST_BENCHMARK`. They reject any real investment benchmark in M0 and prove benchmark identity participates in run identity.

## 9. Reproducibility tests

Run the same manifest twice in isolated temporary directories and compare normalized ledger, orders, fills/rejections, NAV, metrics, and output digest. Then mutate one input at a time (data checksum, fee version, calendar, execution policy) and assert the manifest/output identity changes.

Verify replay never writes to Production namespaces and that a missing commit/dependency/snapshot identity prevents a claim of exact reproducibility.

## 10. Research/Production boundary tests

- static import test: Production and core packages cannot import research/LLM or `chstockdata` outside the adapter;
- approved-bundle digest mismatch blocks runtime;
- experimental config cannot deserialize as Production-approved config without promotion metadata;
- Research storage credentials/paths cannot target Production defaults;
- locked decision types are immutable; supersession creates a separate revision/audit event.

## 11. Parity protocol

For each external comparison, freeze the scenario, source commit/version, license/use context, data, adjustment mode, calendar, price timing, fees, slippage, corporate actions, and terminal policy. Compare event ledgers first, NAV second, metrics last. Record every delta as expected/explained or defect; never tune the kernel merely to match an opaque result.

RQAlpha is allowed only as a non-core, legally compliant research reference. Backtrader GPL code is not copied. Human-calculated cases remain the primary oracle.

## 12. CI and release gates

Normal CI runs offline unit/contract/component/golden/integration/architecture tests on the pinned Python/dependency set. Provider qualification and parity run explicitly with controlled credentials/data rights and publish immutable reports.

M0 release requires:

- all offline tests pass;
- zero unexplained golden/parity differences in accepted scope;
- ETF qualification passes for the approved representative scope;
- deterministic replay digest passes;
- no future-data access in golden cases;
- dependency/license/provenance review passes;
- all approved OQ-01–OQ-10 and P0 requirements are encoded as versioned policy; remaining deferred questions are milestone-gated.

Coverage percentage is diagnostic, not the release criterion. Critical semantic branches require explicit cases even if line coverage is already high.
