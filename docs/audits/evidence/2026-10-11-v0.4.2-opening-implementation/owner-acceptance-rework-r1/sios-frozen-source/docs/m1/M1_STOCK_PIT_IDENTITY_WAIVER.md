# M1_STOCK_PIT_IDENTITY_WAIVER

M1 Stock annual universe formation is point-in-time for liquidity, tradability,
cohort membership, and formation schedules. It is not a complete historical
identity service for ST status transitions, delistings, or historical naming.

The current materializer uses `StockIdentityStatus.NORMAL` as an explicit
assumption and records the limitation in the owner-attested instrument
reference. That proxy must not be used for claims about historical ST status,
delisting survivorship, historical names, or any production eligibility
decision that requires those identities.

This limitation does not invalidate the M1 protocol acceptance: Stock has no
eligible canonical OOS candidate and its accepted outcome is
`NO_OOS_ELIGIBLE_CANDIDATE`; no Stock OOS verdict depends on this assumption.

Future work must replace the assumption with a provider-backed historical
identity model before Stock OOS eligibility or production universe decisions
rely on those fields.
