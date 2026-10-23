# OOS Execution Recovery Design

## Goal

Recover one already-revealed, failed OOS execution only when the missing
history is provably the freeze-bound Basic snapshot and the need for it is
derivable without OOS performance information. Prevent the same preflight
omission for every future OOS run.

## Audit Decision

The existing `freeze-e75b8568e30efb9a` is eligible in principle:

- `sma-150` requires 150 closes by definition.
- The first OOS decision session is 2023-01-31 and its OOS-only dataset has
  16 close observations through that session.
- Freeze `basic_snapshot_digest` is
  `sha256:99a2d581dc1c7fa82f04cd1d18774c4d2da87380b96d394de0a22fa0828aa0b7`.
- The resolved Basic snapshot has that same digest, ends on 2022-12-30, and
  was used by the selected Basic run before catalog sequence 66.

This establishes `CONTROL_PLANE_PREFLIGHT_OMISSION`, rather than a research
or OOS-performance outcome. It does not authorize a second recovery kind.

## Invariants

- `freeze.json`, `reveal.json`, and catalog sequence 67 remain byte-for-byte
  unchanged.
- A recovery artifact is create-new, immutable, append-only, and allowed only
  once per freeze.
- The only allowed warm-up digest equals the freeze's
  `basic_snapshot_digest`; its rows and sessions must end no later than
  `basic_end`.
- Strategy identity, parameters, implementation, kernel replay identity,
  benchmark, cost model, survivor gate, selected variant, and OOS dates are
  revalidated against the freeze. Any mismatch fails closed.
- A freeze with an OOS result, OOS verdict, or asset-class terminal outcome is
  ineligible.
- Recovery evidence is structural only. It neither reads nor records OOS
  returns, NAV, benchmark performance, trade results, future signal direction,
  or gate results.

## Architecture

### Deterministic history preflight

Add a pure history-requirement function to the OOS protocol. It constructs the
frozen strategy identity and reads `required_history_sessions`, then compares
that requirement with the maximum possible OOS-only observations available by
the first scheduled decision date. The calculation uses only frozen parameters,
decision-frequency calendar structure, and the Basic/OOS boundary. It never
opens an OOS snapshot.

For a deficit, regular `oos-run` requires `--warm-up-snapshot` before reveal.
The supplied snapshot is integrity-loaded and must match the freeze-bound
Basic digest and Basic boundary before the reveal is written. A short-lookback
candidate remains eligible without a warm-up snapshot.

### Recovery artifact and validator

Create one immutable `recovery.json` under the existing freeze directory and
one catalog entry of type `OOS_EXECUTION_RECOVERY`. The payload records schema
version, freeze identity, original reveal digest and sequence, the fixed reason
`OOS_HISTORY_INSUFFICIENT`, recovery kind
`ADD_FREEZE_BOUND_BASIC_WARMUP`, both Basic/warm-up digests, and a boolean
identity proof. It also records explicit unchanged-identity attestations for
strategy, parameters, kernel, benchmark, gates, and OOS window.

The recovery command accepts a warm-up manifest path and derives all artifact
fields itself. It validates no existing recovery/result/verdict/terminal
outcome, original reveal warm-up digest `null`, exact catalog provenance for
the original reveal, strict Basic boundary, freeze strategy identity, and
kernel replay identity. It independently requires the deterministic preflight
to prove that OOS-only history was insufficient. There is no `--force` option
and no user-supplied failure reason.

### Canonical retry

After a recovery is recorded, canonical `oos-run` may reuse the immutable
reveal only when the submitted warm-up digest equals the recovery artifact's
digest and all recorded identities still validate. It uses the existing OOS
snapshot and creates the normal OOS run, verdict, and terminal-outcome
artifacts. A later execution failure stops the lifecycle without another
recovery mechanism.

## Data Flow

```text
freeze + frozen strategy + calendar boundary
  -> history preflight
  -> (deficit) validate freeze-bound Basic warm-up
  -> persist reveal
  -> open OOS snapshot

existing reveal + freeze + Basic warm-up + structural proof
  -> validate recovery eligibility
  -> append immutable OOS_EXECUTION_RECOVERY
  -> canonical retry using existing OOS snapshot
```

## Tests

1. A long lookback without warm-up fails before reveal, catalog append, or OOS
   snapshot opening.
2. A matching freeze-bound Basic snapshot permits preflight and is recorded in
   the reveal.
3. A mismatched warm-up digest fails before reveal.
4. A warm-up snapshot containing rows after `basic_end` fails before reveal.
5. A short lookback remains runnable without a warm-up snapshot.
6. A sequence-67-style fixture receives one recovery only when all structural
   eligibility checks pass.
7. Drift in strategy identity, kernel profile, gates, or OOS dates refuses
   recovery.
8. A second recovery attempt refuses without changing the catalog.

Targeted tests run first, followed by research tests, CLI integration tests,
M0 regression, Ruff, strict mypy for `src/systematic_investing/research`, and
catalog verification. Acceptance reports remain unchanged unless a canonical
retry reaches an actual terminal OOS verdict.
