# G16 — Gap-up lot reduction without target mutation

Economic story: with CNY 3,000 the 2026-09-11 close asks for 80% in Ping An
Bank (`XSHE:000001`) and 15% in the CSI 300 ETF (`XSHG:510300`). Both plans
are whole-lot affordable at the T close. The stock then opens at double the
prior close on 2026-09-14, so the plan is collectively unaffordable; the
approved global affordability pass reduces `submitted_quantity` by complete
lots, each order remains all-or-none, cash stays non-negative, and the
T-close theoretical target and planned-quantity evidence are untouched.

## Manual calculation

T-close sizing (equity 3,000):

```text
000001: 0.80  * 3,000 = 2,400 -> 2,400 / 12.00 = 200 shares
510300: 0.15  * 3,000 =   450 ->   450 /  4.00 = 112.5 -> 100 shares
```

2026-09-14 activation (buys ranked by deficit 0.80 then 0.15):

```text
000001 price = 24.00 * 1.001 = 24.024 -> ceil tick 0.01 = 24.03
  planned 200: 4,806.00 + 5.05 fees = 4,811.05 > 3,000 -> reduce by lots
  100 shares: 2,403.00
    commission 0.72 + minimum 4.28 + transfer 0.02 = 5.02
    total 2,408.02 <= 3,000 -> submitted 100, cash 591.98
510300 price = 4.40 * 1.001 = 4.4044 -> ceil tick 0.001 = 4.405
  100 shares: 440.50 + (0.13 + 4.87) = 445.50 <= 591.98 -> submitted 100
  cash = 146.48
```

Close valuation 2026-09-14:

```text
market value = 100 * 24.03 + 100 * 4.405 = 2,403.00 + 440.50 = 2,843.50
equity = 146.48 + 2,843.50 = 2,989.98 (NAV 0.0298998)
```

The order keeps `planned_quantity` 200 and the `T_CLOSE` sizing price 12.00
even though the submitted quantity is 100; the alternative affordable-open
run (test-only override) produces the identical 2026-09-11 decision digest,
target, and plans.

## Asserted evidence

- complete-lot reduction with `REDUCED_TO_AFFORD_T1_GAP` and all-or-none
  fills;
- planned evidence and sizing basis retained on the order;
- non-negative cash (146.48) and identical T decision across both variants
  (dedicated test).
