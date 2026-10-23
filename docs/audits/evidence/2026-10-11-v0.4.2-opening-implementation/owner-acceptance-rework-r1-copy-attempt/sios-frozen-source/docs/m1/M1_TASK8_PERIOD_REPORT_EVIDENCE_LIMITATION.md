# M1_TASK8_PERIOD_REPORT_EVIDENCE_LIMITATION

## Scope

The Task 8 reporting implementation is present in the forward-looking Basic
runner.  New retained Basic reports include deterministic `yearly` and
`subperiods` fields produced from the run's Basic-window NAV and cash ledger.

## Historical M1 evidence

The accepted M1 Basic artifacts are immutable and contain aggregate metrics in
their `report.json` files, but they do not retain the per-session NAV/cash
series required to derive yearly or half-year metrics.  The accepted ETF OOS
lifecycle (sequences 66–71) therefore cannot be backfilled with a truthful
`PERIOD_REPORT` without rerunning Basic, which is prohibited by the M1 evidence
immutability contract.

No fabricated historical period values are added.  The limitation has no
effect on the accepted selection, OOS verdict, catalog sequences, or M1
acceptance outcome.  Future Basic runs are required to retain the Task 8
period fields at run creation time.

## Replacement milestone

An M2 evidence-retention change may add a derived `PERIOD_REPORT` artifact when
the immutable run includes the full NAV/cash inputs and binds the derived
artifact to the original result digest.  That change must not rewrite the M1
accepted evidence.
