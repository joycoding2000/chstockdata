# G07 — Upper-limit rejected buy

Economic story: after the 2026-09-11 close the predetermined target asks for
1.2% in Ping An Bank (`XSHE:000001`). On 2026-09-14 the stock is locked at
the +10% upper price limit (pre_close 12.00, limit 13.20) and the exchange
tradability fact says buys are blocked. The pending buy is rejected with the
typed code and no synthetic partial fill is invented.

## Manual calculation

```text
sizing: 0.012 * 100,000 = 1,200 -> 1,200 / 12.00 = 100 shares (one board lot)
2026-09-14 fact: BUY_BLOCKED_UPPER_LIMIT (buy side blocked)
-> rejection BUY_BLOCKED_UPPER_LIMIT, submitted_quantity null
cash stays 100,000.00; no position; equity 100,000.00; NAV 1.0
```

## Asserted evidence

- the order is REJECTED with the typed code and no fill;
- cash and holdings are unchanged; the target stays unmet.
