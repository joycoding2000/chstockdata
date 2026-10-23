# G11 — Corporate action and adjustment no double count

Economic story: the account holds 1,000 shares of Ping An Bank
(`XSHE:000001`) through a CNY 0.50/share cash dividend effective
2026-09-11. The 2026-09-11 bar also carries a declared total-return
adjustment factor (0.99). The dividend is credited exactly once through the
ledger; the derived adjusted analysis series is never allowed to credit the
account a second time, and holdings are unchanged.

## Manual calculation

```text
2026-09-10 close 12.00: market value 1,000 * 12.00 = 12,000.00
equity = 1,000.00 cash + 12,000.00 = 13,000.00 (NAV 0.13)

2026-09-11 dividend: 1,000 * 0.50 = 500.00 credited once (DIVIDEND ledger entry)
cash = 1,000.00 + 500.00 = 1,500.00
RAW close 11.75: market value 1,000 * 11.75 = 11,750.00
equity = 1,500.00 + 11,750.00 = 13,250.00 (NAV 0.1325)

2026-09-14 RAW close 11.50: market value 11,500.00
equity = 1,500.00 + 11,500.00 = 13,000.00 (NAV 0.13)
```

The adjustment factor 0.99 is metadata on the analysis series only; valuation
and accounting use the RAW close and the ledger event, so there is no second
credit.

## Asserted evidence

- exactly one DIVIDEND cash entry of 500.00 exists across the run;
- the quantity effect is 0 and holdings stay at 1,000 shares;
- the 2026-09-11 bar carries the declared adjustment factor while NAV values
  the RAW close.
