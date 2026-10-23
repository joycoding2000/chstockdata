# G02 — Insufficient cash and minimum commission

Economic story: after the 2026-09-11 close the predetermined target asks for
99% of a CNY 100,000 account in Ping An Bank (`XSHE:000001`) and 1% in the
CSI 300 ETF (`XSHG:510300`). Both are whole-lot affordable at the T close,
but the stock gaps up 1.67% at the T+1 open, so the plan is collectively
unaffordable and one global affordability pass reduces the stock by complete
lots. The ETF fill is small enough that the broker minimum commission binds,
and cash never becomes negative.

## Manual calculation

T-close sizing at the 2026-09-11 closes (stock 12.00, ETF 4.00):

```text
000001: 0.99 * 100,000 = 99,000 -> 99,000 / 12.00 = 8,250.00 -> 8,200 shares
510300: 0.01 * 100,000 = 1,000  ->  1,000 /  4.00 =   250.00 ->   200 shares
```

T+1 activation at the 2026-09-14 opens (stock 12.20, ETF 4.40):

```text
000001 raw = 12.20 * 1.001 = 12.2122   -> ceil tick 0.01 = 12.22
510300 raw =  4.40 * 1.001 =  4.4044   -> ceil tick 0.001 = 4.405

000001 planned 8,200: 8,200 * 12.22 = 100,204.00
  + commission 30.06 + transfer 1.00 = 100,235.06 > 100,000 -> reduce by lots
000001 8,100: 8,100 * 12.22 = 98,982.00
  commission = 98,982.00 * 0.0003 = 29.6946 -> 29.69 (no minimum adjustment)
  transfer   = 98,982.00 * 0.00001 = 0.98982 -> 0.99
  total      = 98,982.00 + 29.69 + 0.99 = 99,012.68 -> submitted 8,100
  cash left  = 100,000 - 99,012.68 = 987.32

510300 200: 200 * 4.405 = 881.00
  commission = 881.00 * 0.0003 = 0.2643 -> 0.26
  minimum adjustment = 5.00 - 0.26 = 4.74 (minimum commission binds)
  stamp/transfer = 0 (FEE:TAX-ETF-EQUITY)
  total = 881.00 + 5.00 = 886.00 <= 987.32 -> submitted 200
  cash left = 987.32 - 886.00 = 101.32
```

2026-09-14 close valuation:

```text
market value = 8,100 * 12.22 + 200 * 4.405 = 98,982.00 + 881.00 = 99,863.00
equity       = 101.32 + 99,863.00 = 99,964.32
NAV          = 0.9996432
```

## Asserted evidence

- the stock's `planned_quantity` 8,200 and the T-close sizing price 12.00 are
  retained while `submitted_quantity` becomes 8,100 with the reason
  `REDUCED_TO_AFFORD_T1_GAP`;
- the ETF keeps its planned 200 and carries the minimum-commission
  adjustment 4.74;
- both quantities are complete board lots;
- final cash is 101.32 — never negative — and all costs are itemized.
