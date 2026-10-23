# G20 — Long suspension stale mark versus truly unpriceable holding

Economic story: two runs contrast a long suspension with a valuation that has
no defensible price at all. In the stale-mark run the account holds Ping An
Bank through a suspension; the position is valued at its last valid RAW close
plus an explicit `STALE_MARK(age)`, receives a cash-dividend ledger event
during the suspension, and cannot gain exposure because no finalized T close
exists (the decision is blocked). In the unpriceable run the account holds an
ETF with no bar anywhere; the portfolio NAV is incomplete and the decision is
blocked, and metrics over that NAV series refuse.

## Manual calculation

Stale-mark run (1,000 shares, cash 1,000):

```text
2026-09-11 close 12.00: market value 12,000.00 -> equity 13,000.00 (NAV 0.13)
2026-09-14: dividend 1,000 * 0.50 = 500.00 -> cash 1,500.00
  no 2026-09-14 bar -> STALE_MARK at 12.00, last valid 2026-09-11, age 1
  market value 12,000.00 -> equity 13,500.00 (NAV 0.135)
  target asks 15% while suspended: no finalized T close
  -> decision blocked MISSING_T_CLOSE_PRICE, no plan (no risk increase)
2026-09-15: STALE_MARK age 2; equity unchanged at 13,500.00
```

Unpriceable run (1,000 shares, cash 1,000, no bar for the holding):

```text
valuation: no defensible price -> INCOMPLETE (NO_DEFENSIBLE_PRICE)
equity = cash 1,000.00 (NAV 0.01); decision blocked INCOMPLETE_VALUATION
the holding stays explicit in the snapshot; metrics over this series refuse
```

## Asserted evidence

- `STALE_MARK` price/age on both suspended sessions with complete valuation;
- the dividend ledger entry during the suspension;
- the suspended session's target attempt is blocked without a plan;
- the unpriceable holding produces incomplete NAV with
  `NO_DEFENSIBLE_PRICE`, blocks the decision, and a dedicated test proves
  `compute_metrics` raises `IncompleteNavError` (stale-mark NAV, by contrast,
  stays reportable).
