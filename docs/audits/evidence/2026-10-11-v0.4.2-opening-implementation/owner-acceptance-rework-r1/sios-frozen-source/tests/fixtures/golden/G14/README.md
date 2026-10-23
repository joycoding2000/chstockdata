# G14 — Multi-target capital competition

Economic story: the account holds 1,000 Ping An Bank shares (CNY 12,000 at
the 2026-09-11 close, no cash). The predetermined target reduces the stock to
35%, buys 55% in the CSI 300 ETF, and asks for 10% in the gold ETF under the
SATELLITE sleeve, which the approved risk cap limits to 5%. On 2026-09-14 the
ETF opens gap up, so after the reduction settles the remaining cash cannot
fund both buys at the same size; one global affordability pass keeps the
higher-deficit buy whole and reduces the lower-deficit buy by complete lots.
No theoretical or approved weight changes.

## Manual calculation

Approved target after the SATELLITE cap (equity 12,000; whole lots only):

```text
CORE:      000001 0.35 -> 4,200 CNY -> 4,200 / 12.00 = 350 -> floor lot = 300
           executable target 300 -> sell 700
CORE:      510300 0.55 -> 6,600 CNY -> 6,600 /  4.00 = 1,650 -> floor lot = 1,600
SATELLITE: 518880 0.10 -> capped to 0.05 -> 600 CNY -> 600 / 2.00 = 300 -> buy 300
```

2026-09-14 activation (sell first, then buys by descending deficit 0.55 >
0.05):

```text
sell 700 @ 12.00*0.999 = 11.988 -> floor tick 0.01 = 11.98
  consideration = 8,386.00
  fees = 2.52 + 2.48 minimum + 4.19 stamp + 0.08 transfer = 9.27
  proceeds = 8,376.73 -> available cash 8,376.73
buy 1,600 @ 4.82*1.001 = 4.82482 -> ceil tick 0.001 = 4.825
  cost = 7,720.00 + 5.00 = 7,725.00 -> cash 651.73
buy 518880 planned 300 @ 2.20*1.001 = 2.2022 -> ceil tick 0.001 = 2.203
  300 shares: 660.90 + 5.00 = 665.90 > 651.73 -> reduce by lots
  200 shares: 440.60 + 5.00 = 445.60 <= 651.73 -> submitted 200
  cash = 651.73 - 445.60 = 206.13
final positions: 300 000001, 1,600 510300, 200 518880
close 2026-09-14: market value = 3,600 + 7,720 + 440 = 11,760.00
equity = 11,966.13 (NAV 0.1196613)
```

## Asserted evidence

- the SATELLITE plan carries the approved 0.05 weight (not the theoretical
  0.10) and the target still aggregates CORE 0.90 / SATELLITE 0.10;
- the reduction settles first, then the 510300 buy fills whole and the 518880
  buy keeps its planned 300 while submitting 200 with
  `REDUCED_TO_AFFORD_T1_GAP`;
- residual cash 206.13 is explicit and never negative;
- the gold ETF position is sellable on the trade date under its approved
  same-day trading profile;
- a dedicated test proves input (map/fact) ordering does not change the
  normalized output.
