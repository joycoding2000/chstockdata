# G12 — Drawdown and underwater duration

Economic story: a hand-authored NAV path with an early peak, a recovered
drawdown, and an unrecovered tail. The path is not produced by the kernel;
the expected drawdowns and underwater durations are hand-calculated from the
declared equity values.

## Manual calculation

| session | equity | NAV | running peak | drawdown |
|---|---|---|---|---|
| 2026-09-09 | 100,000 | 1.00 | 1.00 | 0 |
| 2026-09-10 | 125,000 | 1.25 | 1.25 | 0 |
| 2026-09-11 | 100,000 | 1.00 | 1.25 | -0.20 |
| 2026-09-14 | 125,000 | 1.25 | 1.25 | 0 (recovered) |
| 2026-09-15 | 95,000 | 0.95 | 1.25 | -0.24 |
| 2026-09-16 | 95,000 | 0.95 | 1.25 | -0.24 |
| 2026-09-17 | 95,000 | 0.95 | 1.25 | -0.24 |

```text
episode 1 (recovered): below peak on 2026-09-11, recovery 2026-09-14
  sessions      = 3 - 2 = 1
  calendar days = 2026-09-14 - 2026-09-11 = 3
episode 2 (unrecovered tail): below peak from 2026-09-15 through 2026-09-17
  sessions      = 6 - 4 = 2
  calendar days = 2026-09-17 - 2026-09-15 = 2
maximum underwater: sessions 2, calendar days 3
max drawdown = min(0, 0, -0.20, 0, -0.24, -0.24, -0.24) = -0.24
total return = 0.95 / 1.00 - 1 = -0.05
turnover/cost drag = 0 (no traded entries in the declared series)
```

## Asserted evidence

- the per-observation drawdown series, maximum depth -0.24, and both
  underwater units (2 sessions, 3 calendar days);
- total return -0.05 and observation count 7;
- zero turnover/cost drag for an untraded path; no stale marks.
