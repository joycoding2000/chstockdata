# G17 — PIT information time versus retrieval time

Economic story: three 2026-09-11 facts share the same `retrieved_at`
(16:00). The CSI 300 ETF bar was knowable at 15:05 (before the 15:30
decision cutoff); the gold ETF bar became knowable at 16:00 (after the
cutoff); the bond ETF fact carries `availability_basis = UNKNOWN` with no
information time at all. Only the first is accessible to the T decision.
Retrieval time never substitutes for information availability, and an
UNKNOWN basis never acquires a fabricated exact time.

## Manual calculation

```text
510300 bar: information_available_at 15:05 <= 15:30 cutoff -> visible
518880 bar: information_available_at 16:00 >  15:30 cutoff -> not visible
511010 bar: availability_basis UNKNOWN, information_available_at None
            -> information_known_at() is None, never treated as known
```

The 2026-09-11 target addresses only 510300 (1% of 100,000 = 1,000 ->
200 shares at the 4.00 close), so the T decision is unaffected by the other
two facts; a probe that asks the decision context for either bar fails as an
unknown fact rather than returning a fabricated value.

2026-09-14 activation of the 200-share plan:

```text
price = 4.40 * 1.001 = 4.4044 -> ceil tick 0.001 = 4.405
cost = 881.00 + 5.00 = 886.00 -> cash 99,114.00
mark 4.50 = 900.00 -> equity 100,014.00 (NAV 1.00014)
```

## Asserted evidence

- the 2026-09-11 decision context contains the 510300 bar and neither the
  518880 bar (retrieved at the same timestamp but knowable later) nor the
  UNKNOWN-availability 511010 fact;
- probes for both unavailable facts raise `UnknownFactError`;
- the raw 511010 fact keeps `information_available_at = None` with basis
  `UNKNOWN` (dedicated test).
