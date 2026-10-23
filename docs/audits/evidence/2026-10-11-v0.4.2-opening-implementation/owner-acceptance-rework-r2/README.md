# Owner Acceptance REWORK r2

Apply `sios-source-vs-r1.patch` to the previously byte-verified 256-file SIOS r1 source. The prior frozen-to-r1 patch and unchanged chstockdata wheel remain in the r1 delivery. The r2 patch adds the complete new regression file and changes only domain/historical_opening.py. `delta-verification.json` proves the 257-file reconstruction. `sios-source-manifest.json` records the full tested identity; this is not a Git commit.

`independent-verification.json` checks byte identities, JUnit counts, 54 live capabilities and 129 new raw outputs. `red*` and all intermediate failed GREEN attempts remain visible. Offline transports are deterministic tests, not live certification of those historical dates. `live/` contains the five freshly executed mandatory tests against the changed SIOS and unchanged real r1 wheel.

The complete canonical event hash is a narrow trust anchor for the already authenticated r1 fact. No caller verification flags or source labels are trusted, no interval end is synthesized, and new null-ended events retain veto. Snapshot replay requires no vendor imports or network. Tests intentionally use synthetic stock rules/calendar to isolate eligibility; they do not qualify historical exchange rules.

Old package and TradingAgents evidence is reused only because the actual wheel, 765 CH source files and r1 delivery identity are unchanged. No phase/release authorization, merge, push, tag or publication was performed. See handoff.md and owner-review-status.ini.
