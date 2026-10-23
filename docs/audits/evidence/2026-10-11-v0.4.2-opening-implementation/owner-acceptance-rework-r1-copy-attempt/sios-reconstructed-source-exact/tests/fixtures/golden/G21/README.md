# G21 — Intervening quantity-changing corporate action invalidation

Economic story: after the 2026-09-10 close the predetermined target exits the
1,000-share Ping An Bank position. A 2:1 split is announced at 20:00 that
evening (after the decision cutoff, before the next activation) and is
effective on 2026-09-11. At activation the engine applies the split to the
holdings and invalidates the pending sell with
`CORPORATE_ACTION_REPLAN_REQUIRED`; it submits no rescaled substitute and the
locked 2026-09-10 theoretical target/digest is unchanged. A paired variant
without the split proves the decision-time evidence is identical and that
the exit would otherwise have filled.

## Manual calculation

With the split:

```text
2026-09-10 close 12.00: market value 12,000.00; equity 13,000.00 (NAV 0.13)
plan: SELL 1,000 sized at the T close 12.00
2026-09-11 activation:
  split 2.0 applies first: lots 1,000 -> 2,000, cost 12.00 -> 6.00
  quantity-changing action -> invalidate the pending sell
  planned_quantity 1,000 retained, submitted_quantity null, no fill
2026-09-11 close 6.00: market value 2,000 * 6.00 = 12,000.00
equity = 1,000.00 + 12,000.00 = 13,000.00 (NAV 0.13)
```

Without the split (variant): the same 1,000-share plan fills at the
2026-09-11 open 6.00:

```text
price = 6.00 * 0.999 = 5.994 -> floor tick 0.01 = 5.99
consideration = 5,990.00
fees = 1.80 commission + 3.20 minimum + 3.00 stamp + 0.06 transfer = 8.06
cash = 1,000.00 + 5,981.94 = 6,981.94 (NAV 0.0698194)
```

The announcement at 20:00 on 2026-09-10 was not knowable at the 15:30
decision cutoff, so both runs share the identical 2026-09-10 target and
pending-order digest (asserted in the dedicated test).

## Asserted evidence

- the pending execution is INVALIDATED with
  `CORPORATE_ACTION_REPLAN_REQUIRED` and no substitute order exists;
- the holdings ledger receives the normal split event (quantity delta
  +1,000) and the position remains fully sellable;
- the locked target digest at 2026-09-10 equals the no-action variant's.
