# Portfolio and Risk Semantics

## 1. Core rule

`TargetPortfolio` is the first-class decision. Signals are inputs; BUY/SELL/HOLD/CASH/NO ACTION are derived from the difference between an actual/reconciled portfolio and an executable target. This distinction applies equally to backtest, paper, and future Production.

## 2. Transformation pipeline

```text
strategy intents/signals
  -> portfolio aggregation
  -> TheoreticalTargetPortfolio
  -> deterministic risk transformation/veto
  -> RiskApprovedTargetPortfolio
  -> lot/cash/tradability conversion
  -> ExecutableTargetPortfolio
  -> delta against current PortfolioSnapshot
  -> ActionPlan
```

Every stage persists input/output IDs, rule versions, constraint deltas, and reason codes. Risk may reduce or veto exposure but must not invent Alpha or increase an instrument beyond the upstream theoretical target unless a future, explicitly approved policy says otherwise. Every contribution has an explicit `SleeveId` of `CORE` or `SATELLITE`; CASH is aggregated separately. Sleeve is never inferred from strategy names or instrument types.

## 3. Weight and cash semantics

- Weight denominator is the declared portfolio equity at the target’s valuation point.
- Theoretical weights are decimal fractions before lot/cash constraints.
- Cash is explicit and makes theoretical weights sum to one.
- Executable weights are recomputed from whole quantities and the declared price basis; they are observations of the discrete target, not renormalized wishes.
- Residual cash is the executable cash remaining after estimated consideration and costs; it is never silently redistributed.
- Current weights use a timestamped `PortfolioSnapshot` and its valuation prices.
- Target amount and delta amount retain `sizing_reference_price_basis = T_CLOSE` and the exact finalized T-close price used to derive them. Pre-open publishes these planned values without observing the future open. Realized fills use the separate `NEXT_SESSION_OPEN` model in Backtest or actual manual execution facts in Production.

Long-only M0 rejects negative weights, leverage, and a total theoretical exposure above 100%. The exact decimal tolerance and residual allocation policy are versioned.

## 4. Capital competition and order generation

Reductions/exits are evaluated before increases so released risk/cash can be considered under the configured settlement rule. Portfolio and sleeve budgets are then enforced. Within each available budget, buys are ranked by descending absolute target-weight deficit with canonical InstrumentId as tie-breaker. Buys reserve market fees/taxes and account-specific minimum commissions. Quantities round by side-specific lot rules; odd-lot liquidation behavior is profile-driven.

When all desired lots do not fit CNY 100,000, only complete legal lots are accepted. Residual cash remains explicit and is not renormalized. Simultaneous T+1 gap affordability is evaluated globally in Backtest activation using slippage-adjusted/tick-rounded execution prices plus fees and the approved sleeve/priority order. Future Production reduction occurs only during manual execution or an approved execution-time confirmation, never in Pre-open. Neither fill prices nor reductions flow backward into the T-time theoretical target.

Tiny deltas below a configured materiality/lot threshold become HOLD with a constraint reason, not a misleading failed BUY/SELL.

## 5. Portfolio constraints

The architecture must support versioned deterministic rules for:

- maximum instrument weight;
- maximum equity exposure;
- maximum Stock Satellite exposure conditioned on regime;
- minimum cash allocation;
- sector/issuer concentration;
- correlation and asset/strategy risk budgets;
- volatility target;
- drawdown throttle;
- strategy health/kill-switch state.

M0 defines rule interfaces, composition order, decisions, explicit CORE/SATELLITE aggregation, and fixtures. It does not select regime-specific Satellite cap values or implement ETF/stock strategies.

Rule output is one of pass, cap/transform, or block, with before/after values and a reason code. Rule order is explicit and versioned; non-commutative transforms require a golden example.

## 6. Risk states and fail-safe behavior

Portfolio risk states such as Risk-On/Neutral/Risk-Off are deterministic, versioned strategy/risk outputs in later milestones. M0 treats them as fixture inputs.

Data-quality, strategy-health, and operational kill switches have separate scope. “Gate failed” cannot be a single Boolean with ambiguous consequences. A gate result specifies whether it blocks:

- all action-plan generation;
- risk-increasing orders only;
- one instrument/provider capability;
- one strategy;
- notification/delivery only.

Critical decision-data failure blocks creation of a new target. A critical pre-open failure blocks every risk-increasing order. A risk-reducing order proceeds only when instrument identity, current holding, sellable quantity, current tradability, and a conservative price/cost basis are independently reliable. If any required fact is unavailable, produce no order and an urgent manual-review alert.

## 7. Target completeness and NO ACTION

A complete M0 target explicitly addresses every held instrument. M0 has no carry-forward policy: omitting a current holding makes the target invalid and blocks every plan from that decision. Zero explicitly exits; an explicit unchanged weight retains the holding with no delta. Physical holdings may remain unchanged after a blocked decision, but that fail-closed outcome is not an implicit HOLD target.

`NO ACTION` is an execution conclusion, not a portfolio state. It can mean:

- current executable holdings already match target within tolerance;
- desired change is below one executable lot/materiality threshold;
- a gate blocks actions (with scope/reason);
- a target exists but the instrument is not tradable.

These meanings use distinct reason codes. CASH remains an explicit target allocation.

## 8. EOD versus pre-open authority

EOD owns the theoretical/risk-approved target for the next trading session and locks it. Pre-open may:

- reconcile current positions/cash;
- check calendar, freshness, corporate actions, tradability, and risk kill switches;
- derive T-close-sized planned complete-lot quantities, notionals, and action deltas from the locked target using only information available before open;
- emit T-close-sized planned quantities, targets, and notionals without observing `NEXT_SESSION_OPEN`;
- block or reduce actions under approved execution/risk policies.

Pre-open may not recompute base daily Alpha, change strategy parameters, or silently replace theoretical weights. Any reduction/blocked action retains the locked theoretical target and records the overlay/check responsible.

## 9. Accounting and reconciliation

Backtest uses a deterministic ledger; future Production accepts manually entered/imported fill facts. Reconciliation never rewrites the action plan. It appends actual time, price, quantity, itemized fees, and attribution to plan/order IDs, then creates a new actual `PortfolioSnapshot`.

Plan-versus-actual attribution separates target construction, constraint/rounding, market slippage, fees, missed/partial manual execution, and subsequent market movement.

## 10. Risk objective

The desired 10–15% annual return and maximum drawdown at or below 10% are portfolio objectives/release evidence, not optimizer targets and not guarantees. They cannot be used as a parameter-search stopping rule. Risk evaluation includes drawdown depth and underwater duration, diversification, regime dependence, cost stress, and forward performance.

## 11. Invariants for tests

- risk cannot increase an unapproved theoretical exposure;
- theoretical weights plus cash sum to one;
- executable orders do not create negative available cash;
- instrument/Stock Satellite/global caps hold after discretization;
- CORE and SATELLITE exposures are aggregated from explicit sleeve fields and Satellite caps are deterministic;
- a next-session gap changes only executable quantity/fill, never the theoretical target;
- an intervening quantity-changing corporate action invalidates the affected pending execution with `CORPORATE_ACTION_REPLAN_REQUIRED` rather than silently rescaling it;
- rule order and versions appear in output;
- identical inputs create identical targets and reason codes;
- every held instrument has explicit target/carry treatment;
- locked targets are immutable and amendments are auditable;
- action labels are reproducible projections of deltas, not stored discretionary opinions.
