# G18 — Instrument Master authority conflict and fail-closed scope

Economic story: two runs exercise the authority boundary. In the first, a
provider candidate proposes a conflicting lot size for an instrument that has
an approved effective-dated profile: the approved profile governs and the
candidate is ignored, so the kernel sizes with board lot 100 (not the
candidate's 200). In the second, an unlisted, unapproved ETF symbol
(`XSHG:588000`) is addressed by a target while a provider candidate proposes
rules for it: the approved authority does not cover the session, so the
decision fails closed (`MISSING_INSTRUMENT_RULES`) and no order is created.
Provider metadata is never promoted implicitly.

## Manual calculation

Run `approved_profile_governs` — 2026-09-11 close 12.00, approved lot 100:

```text
0.012 * 100,000 = 1,200 -> 1,200 / 12.00 = 100 shares (approved board lot 100)
the candidate's board lot 200 is ignored; adjudication returns
APPROVED_PROFILE_GOVERNS with the approved bundle
2026-09-14 price = 12.00 * 1.001 = 12.012 -> ceil 0.01 = 12.02
cost = 1,202.00 + (0.36 + 4.64 + 0.01) = 1,207.01 -> cash 98,792.99
mark 12.20 = 1,220.00 -> equity 100,012.99 (NAV 1.0001299)
```

Run `fail_closed_unknown_profile` — 2026-09-11:

```text
target addresses XSHG:588000 at 5% (valuation 100,000)
needed instruments = {XSHG:588000} -> no approved classification/profile
-> decision blocked MISSING_INSTRUMENT_RULES, no plan, no order
the locked theoretical target is still recorded (cash weight 0.95)
```

## Asserted evidence

- the approved profile's board lot 100 is used and the candidate cannot
  override it (adjudication `APPROVED_PROFILE_GOVERNS`, dedicated test);
- the uncovered symbol fails closed: blocked decision, empty plans, and the
  candidate adjudicates to `FAIL_CLOSED_NO_APPROVED_PROFILE`;
- the Data Quality Gate on the same dataset reports a blocking
  `UNKNOWN_INSTRUMENT_CLASSIFICATION` for the uncovered symbol (dedicated
  test).
