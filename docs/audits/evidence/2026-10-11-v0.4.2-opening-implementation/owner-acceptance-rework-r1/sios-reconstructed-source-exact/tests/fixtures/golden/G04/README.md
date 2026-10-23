# G04 — Stock fees and sell tax

Economic story: a Shenzhen A-share round trip. The 2026-09-11 target buys 15%
of CNY 100,000; the 2026-09-14 close target explicitly exits; the exit fills
on 2026-09-15. Buy and sell costs are itemized with the effective-dated
market rules (stamp duty 0.05% on sells since 2023-08-28, CSDC transfer fee
0.001% per side) and the run-owned broker profile (0.03%, minimum CNY 5).

## Manual calculation

Buy, decided 2026-09-11 at close 12.00, activated 2026-09-14 at open 12.10:

```text
sizing: 0.15 * 100,000 = 15,000 -> 15,000 / 12.00 = 1,250 -> 1,200 shares
execution price = 12.10 * 1.001 = 12.1121 -> ceil tick 0.01 = 12.12
consideration   = 1,200 * 12.12 = 14,544.00
commission      = 14,544.00 * 0.0003 = 4.3632 -> 4.36
minimum adj     = 5.00 - 4.36 = 0.64
stamp tax       = 0 (buy side only)
transfer fee    = 14,544.00 * 0.00001 = 0.14544 -> 0.15
buy fees total  = 4.36 + 0.64 + 0.15 = 5.15
cash after buy  = 100,000.00 - 14,544.00 - 5.15 = 85,450.85
mark 12.50      = 15,000.00 -> equity 100,450.85 (NAV 1.0045085)
```

Sell, decided 2026-09-14 at close 12.50, activated 2026-09-15 at open 12.60:

```text
execution price = 12.60 * 0.999 = 12.5874 -> floor tick 0.01 = 12.58
consideration   = 1,200 * 12.58 = 15,096.00
commission      = 15,096.00 * 0.0003 = 4.5288 -> 4.53
minimum adj     = 5.00 - 4.53 = 0.47
stamp tax       = 15,096.00 * 0.0005 = 7.548 -> 7.55 (sell side)
transfer fee    = 15,096.00 * 0.00001 = 0.15096 -> 0.15
sell fees total = 4.53 + 0.47 + 7.55 + 0.15 = 12.70
net proceeds    = 15,096.00 - 12.70 = 15,083.30
cash after sell = 85,450.85 + 15,083.30 = 100,534.15 (NAV 1.0053415)
```

The 1,200 shares acquired on 2026-09-14 are not sellable until 2026-09-15, so
the exit planned after the 2026-09-14 close can only fill on 2026-09-15.

## Asserted evidence

- itemized buy fees (4.36 commission, 0.64 minimum, 0.15 transfer, no stamp);
- itemized sell fees (4.53 commission, 0.47 minimum, 7.55 stamp tax, 0.15
  transfer);
- cash entries follow the fill categories, holdings go flat, and net NAV is
  1.0053415.
