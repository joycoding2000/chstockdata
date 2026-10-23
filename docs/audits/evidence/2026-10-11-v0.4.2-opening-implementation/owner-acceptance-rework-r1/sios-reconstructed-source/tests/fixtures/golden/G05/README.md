# G05 — ETF fee/tax profile per approved subtype

Economic story: the same CNY 1,000 buy notional and 200-share round trip
through each approved ETF subtype — domestic broad-based equity
(`XSHG:510300`, `FEE:TAX-ETF-EQUITY`), gold (`XSHG:518880`,
`FEE:TAX-ETF-GOLD`), and bond (`XSHG:511010`, `FEE:TAX-ETF-BOND`). All three
use their own effective-dated market fee/tax rule family: no securities
stamp duty (it applies to stock transfer documents, not fund trades) and no
CSDC transfer fee. Broker commission/minimum still comes from the run-owned
account configuration.

## Manual calculation

Buys, decided 2026-09-11 at close 4.00, activated 2026-09-14 at open 4.40:

```text
sizing (each): 0.01 * 100,000 = 1,000.00 -> 1,000 / 4.00 = 250 -> 200 shares
execution price = 4.40 * 1.001 = 4.4044 -> ceil tick 0.001 = 4.405
consideration (each) = 200 * 4.405 = 881.00
commission (each)    = 881.00 * 0.0003 = 0.2643 -> 0.26
minimum adjustment   = 5.00 - 0.26 = 4.74
stamp tax            = 0 for every ETF subtype
transfer fee         = 0 for every ETF subtype
buy fee total (each) = 5.00 -> cash after three buys = 100,000 - 3 * 886.00 = 97,342.00
mark 4.40            = 3 * 880.00 = 2,640.00 -> equity 99,982.00 (NAV 0.99982)
```

Sells, decided 2026-09-14 at close 4.40, activated 2026-09-15 at open 4.40:

```text
execution price = 4.40 * 0.999 = 4.3956 -> floor tick 0.001 = 4.395
consideration   = 200 * 4.395 = 879.00
commission      = 0.2637 -> 0.26; minimum adjustment 4.74; stamp 0; transfer 0
net proceeds    = 879.00 - 5.00 = 874.00 each
cash after all  = 97,342.00 + 3 * 874.00 = 99,964.00 (NAV 0.99964)
```

Passing one subtype never approves another: the scenario uses only the three
approved subtypes, and the dedicated test additionally resolves each
instrument's market fee/tax profile id from the approved Instrument Master.

## Asserted evidence

- every buy and sell fill has stamp tax 0 and transfer fee 0 with commission
  0.26 and minimum adjustment 4.74 — no stock default is inherited;
- the three market fee/tax families are distinct approved profiles with zero
  rates;
- cash/NAV follow from the itemized costs.
