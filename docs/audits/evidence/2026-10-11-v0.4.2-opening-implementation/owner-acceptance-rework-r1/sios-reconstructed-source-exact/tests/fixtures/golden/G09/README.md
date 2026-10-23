# G09 — Settlement sellability and deferred exit

Economic story: buys fill on 2026-09-11 for Ping An Bank (`XSHE:000001`,
approved T+1 settlement) and for a test-only overlay ETF (`XSHG:510500`,
declared two-session settlement). The 2026-09-11 close explicitly exits both.
On 2026-09-14 the stock's lot is sellable and fills, while the ETF's lot is
not sellable yet and is rejected; the ETF exit is re-addressed at the
2026-09-14 close and fills on 2026-09-15 once sellable. Settlement is
profile-driven — nothing about it is globally hard-coded.

## Manual calculation

Buys, decided 2026-09-10, activated 2026-09-11 at the opens:

```text
000001: 0.012 * 100,000 = 1,200 -> 100 shares
  price = 12.00 * 1.001 = 12.012 -> ceil tick 0.01 = 12.02
  fees = 0.36 commission + 4.64 minimum + 0.01 transfer = 5.01 -> 1,207.01
510500: 0.004 * 100,000 = 400 -> 100 shares
  price = 4.00 * 1.001 = 4.004 (exactly on the 0.001 tick, no rounding up)
  fees = 0.12 commission + 4.88 minimum = 5.00 -> 405.40
cash = 100,000 - 1,207.01 - 405.40 = 98,387.59
mark = 100*12.00 + 100*4.00 = 1,600.00 -> equity 99,987.59 (NAV 0.9998759)

sellability dates:
  000001 lot acquired 2026-09-11 -> sellable 2026-09-14 (T+1 profile)
  510500 lot acquired 2026-09-11 -> sellable 2026-09-15 (two-session test profile)
```

Sells, decided 2026-09-11, activated 2026-09-14 at the opens:

```text
000001 sellable 100 -> price = 12.00 * 0.999 = 11.988 -> floor 0.01 = 11.98
  proceeds = 1,198.00 - (0.36 + 4.64 + 0.60 stamp + 0.01 transfer) = 1,192.39
  cash = 98,387.59 + 1,192.39 = 99,579.98
510500 sellable 0 -> reject INSUFFICIENT_SELLABLE_QUANTITY (no fill)
mark = 100 * 4.00 = 400.00 -> equity 99,979.98 (NAV 0.9997998)
```

ETF exit re-addressed at the 2026-09-14 close, activated 2026-09-15:

```text
price = 4.00 * 0.999 = 3.996 -> floor 0.001 = 3.996
proceeds = 399.60 - (0.12 + 4.88) = 394.60
cash = 99,579.98 + 394.60 = 99,974.58 (NAV 0.9997458)
```

The two-session settlement rule is a test-only overlay fixture declared in
the approved authority; it is not a claim about any real ETF settlement
cycle. It exists to prove that sellability comes from the effective-dated
profile, not from a global assumption.

## Asserted evidence

- the ETF sell is rejected with `INSUFFICIENT_SELLABLE_QUANTITY` while the
  stock sell fills on the same session;
- the deferred ETF exit fills on the next session once the lot is sellable;
- the dedicated test asserts the two lots' `sellable_from` dates differ per
  profile (2026-09-14 vs 2026-09-15).
