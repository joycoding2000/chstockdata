# G19 — Explicit sleeve aggregation and cap

Economic story: four predetermined contributions carry explicit sleeve
fields. CORE holds the CSI 300 ETF (40%) and Kweichow Moutai (5%) — the
latter deliberately contributed under a strategy named
"satellite-looking-name" to prove that strategy names never decide the
sleeve. SATELLITE holds the gold ETF (8%) and the bond ETF (7%). The approved
risk transformation caps SATELLITE at 10% and reduces deterministically to
8% + 2%, so the executable bond ETF target is the capped weight, not the
theoretical 7%. Aggregation and caps come only from explicit `SleeveId`
fields.

## Manual calculation

Theoretical aggregation at the 2026-09-11 closes (equity 100,000):

```text
CORE:      510300 0.40 + 600519 0.05 = 0.45
SATELLITE: 518880 0.08 + 511010 0.07 = 0.15
cash weight = 1 - 0.60 = 0.40
```

Approved transformation — SATELLITE cap 0.10, descending weight with
canonical InstrumentId tie-break:

```text
518880 0.08 <= remaining 0.10 -> approved 0.08 (remaining 0.02)
511010 0.07 -> approved 0.02
```

2026-09-14 activation (buys by descending deficit 0.40, 0.08, 0.05, 0.02;
all execution prices land exactly on their ticks):

```text
510300: 10,000 @ 4.004 -> 40,040.00 + 12.01 fees = 40,052.01 (cash 59,947.99)
518880:  2,000 @ 4.004 ->  8,008.00 +  5.00 fees =  8,013.00 (cash 51,934.99)
600519:    100 @ 50.05 ->  5,005.00 +  5.05 fees =  5,010.05 (cash 46,924.94)
511010:  1,000 @ 2.002 ->  2,002.00 +  5.00 fees =  2,007.00 (cash 44,917.94)
market value at 4.004 / 50.05 / 4.004 / 2.002 = 55,055.00
equity = 44,917.94 + 55,055.00 = 99,972.94 (NAV 0.9997294)
```

## Asserted evidence

- per-sleeve aggregation 0.45 / 0.15 from explicit sleeve fields, and the
  Moutai contribution stays CORE despite its strategy name (dedicated test);
- the deterministic cap reduces the bond ETF approved weight from 0.07 to
  0.02 while the theoretical contribution remains 0.07;
- the gold and bond ETF positions are sellable on the trade date under their
  approved same-day trading profiles;
- every executable order preserves the approved weights and complete lots.
