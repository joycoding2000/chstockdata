# G03 — Lot rounding and residual cash

Economic story: after the 2026-09-11 close the predetermined target asks for
5% of a CNY 100,000 account in Ping An Bank (`XSHE:000001`, board lot 100).
The target amount is not divisible by the lot, so the executable quantity is
rounded down to a complete lot. The theoretical weight is never renormalized
and the residual cash stays explicit.

## Manual calculation

T-close sizing at the 2026-09-11 close 12.00:

```text
target amount     = 0.05 * 100,000 = 5,000.00 CNY
unrounded shares  = 5,000.00 / 12.00 = 416.666... -> floor to lot = 400
executable weight = 400 * 12.00 / 100,000 = 0.048 (0.002 residual)
```

T-close executable draft (the explicit residual-cash record):

```text
consideration      = 400 * 12.00 = 4,800.00
commission         = 4,800.00 * 0.0003 = 1.44
minimum adjustment = 5.00 - 1.44 = 3.56
transfer fee       = 4,800.00 * 0.00001 = 0.048 -> 0.05
reserved costs     = 5.05
residual cash      = 100,000.00 - 4,800.00 - 5.05 = 95,194.95
```

T+1 activation at the 2026-09-14 open 12.00:

```text
raw execution price = 12.00 * 1.001 = 12.012 -> ceil tick 0.01 = 12.02
consideration       = 400 * 12.02 = 4,808.00
fees                = 1.44 commission + 3.56 minimum + 0.05 transfer = 5.05
cash after fill     = 100,000.00 - 4,808.00 - 5.05 = 95,186.95
```

2026-09-14 close 12.00:

```text
market value = 400 * 12.00 = 4,800.00
equity       = 95,186.95 + 4,800.00 = 99,986.95
NAV          = 0.9998695
```

## Asserted evidence

- the plan carries the theoretical `target_weight` 0.05 and the whole-lot
  `planned_quantity` 400 (never 417 or 416);
- the executable draft reports executable weight 0.048 and residual cash
  95,194.95 explicitly;
- the settlement fill keeps the residual cash explicit (95,186.95) and cash
  never becomes negative.
