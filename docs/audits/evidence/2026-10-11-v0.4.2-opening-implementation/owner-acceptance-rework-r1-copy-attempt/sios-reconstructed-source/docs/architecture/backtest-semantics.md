# Backtest Semantics v1

## 1. Scope

The M0 kernel is deterministic, daily-bar, long/cash, target-weight driven, and designed for A-shares and exchange-listed ETFs. It is a correctness kernel, not a general-purpose trading engine. Strategy fixtures provide predetermined target portfolios; no investment strategy is implemented in M0.

Default initial account state is CNY 100,000 cash, no positions. Currency conversion, leverage, shorting, derivatives, intraday bars, margin, automatic live execution, and multi-currency accounting are out of scope.

## 2. Information-time rule

For session T:

1. The strategy view may observe canonical facts whose `information_available_at` is no later than the configured T decision cutoff under the run's availability policy. `retrieved_at` is never used as a PIT substitute; `UNKNOWN` remains explicit.
2. It produces a theoretical target after T closes.
3. The earliest eligible execution session is `calendar.next_session(T)`.
4. No fill may use a T price or any T+1 value while computing the T target.

The kernel enforces this with separate decision and execution phases and dataset slices. A test strategy cannot request future rows; a run manifest records the information cutoff.

## 3. Daily event order

The M0 deterministic order is:

```text
start of session T
  1. apply effective corporate actions/settlement transitions to holdings;
     invalidate affected pending executions when an intervening action changes quantity
  2. activate surviving plans created from T-1 close decisions
  3. evaluate listing, suspension, price-limit and other tradability facts
  4. derive slippage-adjusted, tick-rounded execution prices and applicable fees;
     evaluate affordability globally and submit legal complete-lot quantities
  5. price/fill the submitted all-or-none order with the next-bar execution model
  6. post fills, fees, taxes, cash and holdings movements
  7. value the account at T close using unadjusted executable prices
  8. expose data available through the T decision cutoff
  9. accept predetermined/strategy target for T+1 and create a pending plan
 10. persist ledger/NAV/checksums
```

M0 fixes `sizing_reference_price_basis = T_CLOSE` and `execution_price_model = NEXT_SESSION_OPEN`. Target quantities are sized only from finalized T-close prices and T-known facts. At T+1 activation, candidate execution prices are open plus side-aware slippage and explicit tick rounding. Affordability uses those execution prices plus applicable market/broker fees. Other models are explicitly versioned scenarios with no implicit fallback.

## 4. Price and adjustment semantics

- Execution, fees, cash accounting, price-limit checks, and end-of-day market value use raw/unadjusted prices.
- Research indicators may use a declared point-in-time adjusted series, but that series is a derived input with factor version/as-of metadata.
- Corporate actions enter the ledger as cash/share events. If a total-return adjusted series is used for analysis, it must not also credit the account.
- If a split, consolidation, distribution, or other quantity-changing corporate action becomes effective after the T-close decision and before T+1 activation, invalidate the affected pending execution with `CORPORATE_ACTION_REPLAN_REQUIRED`. Do not rescale the order or mutate the locked theoretical target in M0.
- `pre_close` is a canonical field with declared vendor/exchange semantics and is used with the effective `PriceLimitRule`.
- Missing or inconsistent adjustment metadata is a blocking data error for tests that need it.

## 5. From target weights to orders

At decision time, theoretical target weights include explicit cash and sum to 1. The executable conversion uses a declared equity/price basis and performs, in order:

1. validate target completeness and risk-approved bounds;
2. value current holdings and determine sellable quantities;
3. generate reductions/exits before increases;
4. enforce approved portfolio and sleeve budgets (`CORE`, `SATELLITE`, `CASH`);
5. rank buys within each available budget by descending absolute target-weight deficit, breaking ties by canonical InstrumentId;
6. round quantities according to side-specific lot rules and accept only complete lots;
7. reserve estimated market fees/taxes and account-specific broker commission/minimums;
8. emit executable targets, pending orders, residual cash, and constraint reason codes.

No order may make available cash negative. Market/regulatory fee rules and account-specific broker fees are separately effective-dated. Residual cash is explicit and is not renormalized into theoretical weights.

## 6. Settlement and sellability

Settlement is profile-driven. For an A-share configured as T+1, quantity acquired on T is part of total holdings but cannot be sold until the profile-defined subsequent session. ETF sellability is determined by the instrument/fund subtype profile; the kernel has no global ETF default.

A sale request exceeding sellable quantity is rejected or reduced only according to an explicitly selected order policy. It may not silently pretend total quantity is sellable.

## 7. Tradability and price limits

- Suspended, not-yet-listed, delisted, or unknown-status instruments do not fill.
- A buy blocked at the upper limit is rejected; a sell blocked at the lower limit is rejected, using deterministic fixture facts rather than attempting to infer a limit event solely from OHLC when source evidence is available.
- ST and IPO/new-listing behavior is expressed by reference/rule profiles and eligibility gates, not hard-coded symbol logic.
- Expected market rejections are ledger events and leave the target unmet; subsequent retry/carry policy must be explicit.

The daily OHLC model cannot reliably reconstruct queue availability at a locked limit. M0 models a conservative binary tradability fact and documents this limitation.

## 8. Slippage and fees

An execution model returns an unrounded reference fill price and a side-aware slippage adjustment. Exchange tick rounding and monetary rounding are explicit policies. Fees are itemized at least as commission, minimum commission adjustment, sell-side stamp tax where applicable, transfer/other fee where configured, and total.

Profiles are instrument/action/effective-date specific. Market/regulatory truth (settlement, lot, price limits, tax and exchange fees) comes from the approved Instrument Master with authoritative provenance; broker commission/minimum comes from account configuration. ETF treatment is proven by subtype fixtures and never inherited from stock defaults.

## 9. Insufficient cash and partial execution

Cash availability includes existing available cash and proceeds whose same-day reuse is permitted by the configured accounting rule. The simulator reserves estimated costs before accepting buys. At target conversion, quantity falls to the largest affordable legal complete lot with a reason code. Active M0 daily-bar orders are all-or-none; intraday partial-liquidity fills are not simulated.

Multiple buy candidates never depend on dictionary iteration: enforce risk/sleeve budgets first, then descending absolute target-weight deficit and canonical InstrumentId tie-breaker.

At T+1 activation, affordability is solved globally across all simultaneous candidates—not order-by-order against raw open. Use each slippage-adjusted, tick-rounded execution price plus applicable fees, process reductions/exits first, enforce sleeve/risk budgets, then rank buys by descending absolute target-weight deficit and canonical InstrumentId. If a gap makes planned quantities collectively unaffordable, deterministically reduce `submitted_quantity` by complete lots without negative cash and record each constraint. Submitted orders are all-or-none. This never recalculates or mutates the T-time theoretical `TargetPortfolio` or its `planned_quantity` evidence.

## 10. Valuation and NAV

After execution and ledger posting, positions are valued at the session close when a valid price is available. A suspended/missing-close position uses its last valid RAW close plus `STALE_MARK(age)`, remains explicit in NAV/reporting, receives corporate-action ledger updates, and cannot gain exposure. NAV is total marked equity divided by CNY 100,000, adjusted only for explicit external cash flows (none in M0 fixtures unless a test says otherwise).

Incomplete valuation occurs only when no defensible price exists, a corporate action makes the prior price economically invalid, or instrument identity/reference is unresolved. Only then are complete-portfolio metrics blocked; long suspension by itself does not invalidate the history.

## 11. Terminal semantics

The default report preserves the final portfolio and marks it to market at the final session. Forced liquidation is a separately named/versioned scenario that creates real simulated orders, constraints, fees, taxes, and possible rejections. Metrics and `RunManifest` state the terminal mode.

## 12. Metrics definitions

- **Total return:** ending equity / beginning equity - 1, after modeled costs and corporate actions.
- **CAGR:** geometric annualization over actual calendar-day span; short-span behavior is defined and tested.
- **Volatility:** sample standard deviation of daily close-to-close returns annualized by 252 sessions.
- **Sharpe:** daily close-to-close excess-return statistic annualized by 252, with M0 risk-free rate 0 and explicit zero-volatility handling.
- **Sortino:** daily return over downside deviation, annualized by 252, with M0 target return 0.
- **Maximum drawdown:** minimum of `NAV / running_peak - 1`.
- **Calmar:** CAGR / absolute maximum drawdown with zero-drawdown handling.
- **Underwater duration:** maximum elapsed sessions and calendar days from falling below a prior peak until recovery; an unrecovered episode runs through the final observation.
- **Turnover:** `0.5 * gross traded notional / average equity`.
- **Cost drag:** gross-versus-net performance difference under the same fills before/after modeled costs.

All metric conventions, including both trading-session and calendar-day underwater duration, are versioned in the `RunManifest`. A convention change creates a new run identity and never rewrites history.

## 13. Reproducibility

A replay requires the exact code commit, dependency lock digest, canonical data snapshot/checksums, adapter/schema versions, Instrument Master and run-owned account-fee profiles, initial account, predetermined target/strategy version and sleeves, parameters, universe, period, T-close sizing basis/prices, `NEXT_SESSION_OPEN` execution model, costs, benchmark identity, terminal mode, metric conventions, and random seed. Until OQ-22 is decided in M1, M0 benchmark identity is explicitly `NONE` or `SYNTHETIC_TEST_BENCHMARK`; no real investment benchmark is selected. M0 is deterministic; a seed is still recorded for contract continuity.

Two runs with identical manifests and input digests must produce identical normalized ledger, NAV, and metric digests.

## 14. Explicit limitations

- Daily bars cannot prove intraday path or limit-queue fill probability.
- Free data has no SLA; successful download is not evidence of correctness.
- Point-in-time universe membership and corporate-action knowledge need availability metadata to avoid leakage.
- Cross-engine parity is semantic, not blind decimal equality; every difference needs a written attribution.
