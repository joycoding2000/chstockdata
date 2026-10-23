# G06 — Suspension and unknown tradability

Economic story: after the 2026-09-11 close the predetermined target asks for
1% in the CSI 300 ETF (`XSHG:510300`) and 1.2% in Ping An Bank
(`XSHE:000001`). On 2026-09-14 the ETF is suspended and the stock has no
tradability fact at all. Both pending buys are rejected with typed reason
codes, nothing fills, cash and holdings are unchanged, and the locked target
stays unmet.

## Manual calculation

T-close sizing at the 2026-09-11 closes:

```text
510300: 0.01  * 100,000 = 1,000 -> 1,000 /  4.00 = 250 -> 200 shares
000001: 0.012 * 100,000 = 1,200 -> 1,200 / 12.00 = 100 -> 100 shares
```

2026-09-14 activation facts:

```text
510300 tradability = SUSPENDED            -> reject SUSPENDED, no fill
000001 tradability = absent (no fact)     -> reject TRADABILITY_UNKNOWN, no fill
cash stays 100,000.00; no positions; equity 100,000.00; NAV 1.0
```

A missing tradability fact is never treated as tradable: unknown status
blocks every exposure-increasing action.

## Asserted evidence

- two typed rejections (`SUSPENDED`, `TRADABILITY_UNKNOWN`) and no fills;
- both orders are REJECTED with `submitted_quantity` null and the reason
  code recorded;
- cash/holdings/NAV are unchanged and the unmet 2026-09-11 target is not
  silently retried.
