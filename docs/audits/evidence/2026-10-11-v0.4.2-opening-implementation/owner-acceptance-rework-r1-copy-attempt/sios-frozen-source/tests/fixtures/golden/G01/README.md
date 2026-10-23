# G01 — T-close sizing and T+1-open fill

Economic story: after the 2026-09-11 close the predetermined target asks for
1% of a CNY 100,000 account in the Huatai-PineBridge CSI 300 ETF
(`XSHG:510300`, broad-based equity ETF). Nothing fills at T. The plan is
activated at the 2026-09-14 open with side-aware slippage and tick rounding,
and the account is marked at the 2026-09-14 close.

## Manual calculation

Account at the 2026-09-11 decision cutoff: cash CNY 100,000, no positions;
valuation equity CNY 100,000.

T-close sizing (only T-close facts: close 4.00):

```text
target amount       = 0.01 * 100,000 = 1,000.00 CNY
unrounded shares    = 1,000.00 / 4.00 = 250
board lot           = 100 (approved LOT:CN-STANDARD)
planned_quantity    = floor(250 / 100) * 100 = 200 shares
executable weight   = 200 * 4.00 / 100,000 = 0.008 (theoretical 0.01 unchanged)
```

T+1 activation at the 2026-09-14 open 4.40 (ETF tick 0.001, slippage 0.001):

```text
raw execution price = 4.40 * 1.001 = 4.4044
tick rounding       = ceil to 0.001 = 4.405
consideration       = 200 * 4.405 = 881.00 CNY
commission          = 881.00 * 0.0003 = 0.2643 -> 0.26 (ROUND_HALF_UP)
minimum adjustment  = 5.00 - 0.26 = 4.74
stamp tax           = 0 (ETF market fee/tax profile FEE:TAX-ETF-EQUITY)
transfer fee        = 0
total fees          = 5.00
cash after fill     = 100,000.00 - 881.00 - 5.00 = 99,114.00
```

2026-09-14 close valuation:

```text
market value = 200 * 4.50 = 900.00
equity       = 99,114.00 + 900.00 = 100,014.00
NAV          = 100,014.00 / 100,000 = 1.00014
```

Settlement: the acquisition on 2026-09-14 becomes sellable on the next open
session 2026-09-15, so the final session snapshot reports sellable 0 (the
calendar declares 2026-09-15 so the rule can resolve; the run stops at
2026-09-14).

## Asserted evidence

- no order, fill, or position exists on 2026-09-11;
- the pending plan carries the T-close sizing price 4.00 and quantity 200;
- the order keeps `planned_quantity` 200 and `sizing_reference_price_basis`
  `T_CLOSE` while the fill uses the separate `NEXT_SESSION_OPEN` model at
  4.405; the order's `execution_session` is the trade date 2026-09-14 while
  its `decision_for_trade_date` field carries the decision session 2026-09-11
  (the upstream plan/order contract records the originating decision, and the
  target record separately carries the trade date);
- itemized fees are commission 0.26, minimum adjustment 4.74, stamp 0,
  transfer 0 (total 5.00);
- cash never becomes negative and residual cash stays explicit (99,114.00).
