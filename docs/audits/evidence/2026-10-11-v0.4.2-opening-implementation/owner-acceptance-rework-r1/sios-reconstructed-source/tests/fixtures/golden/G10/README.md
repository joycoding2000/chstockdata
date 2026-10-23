# G10 — No lookahead: future data cannot change the T decision

Economic story: a buy is decided after the 2026-09-11 close. The 2026-09-14
and 2026-09-15 bars are mutated (roughly doubled) in a second run while every
fact through the 2026-09-11 decision cutoff stays identical. The T decision
and its pending order must remain digest-identical, while the fills differ.
Requesting the future bars at the decision session must fail loudly.

## Manual calculation

Baseline run, 2026-09-11 decision at close 4.00:

```text
sizing = 0.02 * 100,000 = 2,000 -> 2,000 / 4.00 = 500 -> 500 shares (5 board lots)
plan: BUY 500 at the T-close sizing price 4.00
```

2026-09-14 activation at open 4.40:

```text
price = 4.40 * 1.001 = 4.4044 -> ceil tick 0.001 = 4.405
consideration = 500 * 4.405 = 2,202.50
fees = 0.66 commission + 4.34 minimum = 5.00
cash = 100,000.00 - 2,207.50 = 97,792.50
mark 4.50 = 500 * 4.50 = 2,250.00 -> equity 100,042.50 (NAV 1.000425)
```

Mutated run (test-only `bar_overrides`): 2026-09-14 open 4.80 / close 5.20
and 2026-09-15 open/close 5.50. The fill becomes 500 * 4.805 =
2,402.50 + 5.00 and equity changes, so the normalized output digest changes;
the 2026-09-11 decision digest, target, and pending order stay
byte-identical.

## Asserted evidence

- `context.require_bar(instrument, future_session)` raises
  `FutureDataAccessError` for the 2026-09-14 and 2026-09-15 bars at the
  2026-09-11 decision session;
- the 2026-09-11 `decision_digest`, target record, and pending plan are
  identical between the baseline and mutated runs;
- the full normalized output digests differ, proving the mutation really
  changed post-decision behavior.
