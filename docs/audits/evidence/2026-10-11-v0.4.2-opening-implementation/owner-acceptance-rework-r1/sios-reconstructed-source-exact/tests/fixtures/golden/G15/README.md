# G15 — Target completeness: explicit zero, explicit unchanged, missing

Owner-approved M0 semantics require every current holding to receive an
explicit treatment in every actual TargetPortfolio. There is no implicit or
versioned carry-forward policy in M0.

The account initially holds three instruments: CNY 12,000 stock, CNY 4,000
broad equity ETF, and CNY 4,000 gold ETF, for equity of CNY 20,000.

## Run `complete`: explicit zero and explicit unchanged

The 2026-09-11 target addresses all three holdings:

```text
XSHE:000001 -> 0.0   explicit exit
XSHG:510300 -> 0.2   explicit unchanged treatment
XSHG:518880 -> 0.2   explicit unchanged treatment
cash weight = 1 - (0 + 0.2 + 0.2) = 0.6
```

Only the stock produces a SELL plan. The two explicit unchanged positions
produce no delta and therefore no order.

The 2026-09-14 exit calculation is hand-checked:

```text
fill price = floor_tick(12.00 * 0.999) = 11.98
consideration = 1,000 * 11.98 = 11,980.00
fees = 3.59 commission + 1.41 minimum adjustment
     + 5.99 stamp tax + 0.12 transfer fee = 11.11
cash = 11,980.00 - 11.11 = 11,968.89
ETF marks = 1,000 * 4.10 + 1,000 * 4.10 = 8,200.00
equity = 11,968.89 + 8,200.00 = 20,168.89
nav = 0.2016889
```

## Run `missing_target`: typed fail-closed result

The target explicitly addresses the stock at zero and the broad ETF at 20%,
but omits the held gold ETF. The target is evidence of an invalid incomplete
decision and records `TARGET_INCOMPLETE`; it produces no executable plan.

No HOLD or SELL is synthesized for the missing instrument. The real account
therefore receives no order at all. Its positions remain physically unchanged
because the decision failed closed, not because absence was interpreted as a
retain target. At the 2026-09-14 close:

```text
market value = 1,000 * 12.00 + 1,000 * 4.10 + 1,000 * 4.10
             = 20,200.00
cash = 0
equity = 20,200.00
nav = 0.202
```

The expected JSON is manually written from these calculations; it is not
generated from kernel output.
