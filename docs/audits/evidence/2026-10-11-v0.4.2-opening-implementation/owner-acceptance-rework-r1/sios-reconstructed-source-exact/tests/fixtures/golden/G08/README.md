# G08 — Lower-limit rejected sell

Economic story: the account holds 1,000 shares of Ping An Bank
(`XSHE:000001`) and the 2026-09-11 close target explicitly exits. On
2026-09-14 the stock is locked at the -10% lower price limit (pre_close
12.00, limit 10.80) and the exchange tradability fact blocks sells. The
pending sell is rejected and the position is retained at its raw close
valuation.

## Manual calculation

```text
2026-09-11 close 12.00: market value 1,000 * 12.00 = 12,000.00
equity = 100,000.00 + 12,000.00 = 112,000.00 (NAV 1.12)
plan: SELL 1,000 at the T-close sizing price 12.00
2026-09-14 fact: SELL_BLOCKED_LOWER_LIMIT
-> rejection SELL_BLOCKED_LOWER_LIMIT, no fill, cash unchanged
2026-09-14 close 10.80: market value 1,000 * 10.80 = 10,800.00
equity = 100,000.00 + 10,800.00 = 110,800.00 (NAV 1.108)
```

## Asserted evidence

- the sell is REJECTED with the typed lower-limit code and no fill;
- the 1,000-share position is retained and valued at the raw close 10.80;
- cash is unchanged at 100,000.00.
