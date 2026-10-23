# G13 — Terminal semantics: mark-to-market versus forced liquidation

Economic story: the same account (1,000 CSI 300 ETF shares plus CNY 1,000
cash) is terminated two ways. The default `MARK_TO_MARKET` report preserves
the final portfolio and creates no liquidation costs. A separately named
`FORCED_LIQUIDATION` scenario creates a real simulated exit order whose fees
occur only there, and the run convention metadata states the mode.

## Manual calculation

Mark-to-market run (no target at all):

```text
2026-09-11 close 4.00: market value 4,000.00 -> equity 5,000.00 (NAV 0.05)
2026-09-14 close 4.10: market value 4,100.00 -> equity 5,100.00 (NAV 0.051)
no order, no fill, no fee; the 1,000-share position is preserved
```

Forced-liquidation run (2026-09-11 close target weight 0):

```text
plan: SELL 1,000 sized at the T close 4.00
activation 2026-09-14 open 4.10:
  price = 4.10 * 0.999 = 4.0959 -> floor tick 0.001 = 4.095
  consideration = 1,000 * 4.095 = 4,095.00
  fees = 1.23 commission + 3.77 minimum = 5.00 (ETF stamp/transfer zero)
  proceeds = 4,090.00 -> cash 1,000.00 + 4,090.00 = 5,090.00
  positions flat; equity 5,090.00 (NAV 0.0509)
```

`MetricConventions(terminal_mode=...)` participates in run identity, so the
two modes have different convention digests.

## Asserted evidence

- the mark-to-market run has no fills and no fees, and keeps the position;
- the forced-liquidation run has the real SELL fill with itemized costs and
  flattens the position;
- the convention digest differs between the two terminal modes (asserted in
  the dedicated test).
