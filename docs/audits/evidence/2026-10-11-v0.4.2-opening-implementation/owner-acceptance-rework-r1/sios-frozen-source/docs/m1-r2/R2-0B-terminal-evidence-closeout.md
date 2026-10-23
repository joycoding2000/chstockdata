# R2-0B Terminal Evidence Close-out

## Scope and conclusion

This is an evidence close-out for M1-R2, not a reopening of M1 engineering,
an OOS rerun, or an M2 entry decision.  The only experiment root used for the
terminal conclusions is `var/research/task9-experiments-v2`.

The immutable terminal artifacts support the already recorded M1 conclusion:

```text
ETF                  = REJECTED_OOS
STOCK                = NO_OOS_ELIGIBLE_CANDIDATE
AI source flight     = SCREEN_PASS
SURVIVOR_COUNT       = 0
M2_ENTRY_GATE        = BLOCKED
```

The catalog is independently verifiable as `PASS`.  A fresh, derived
acceptance JSON/Markdown pair could **not** be generated from the current
checkout because its actual CLI does not contain the documented
`acceptance-report` or `render-report` subcommands.  This is a report
regeneration capability gap, not a failure of the immutable terminal
artifacts.  No source code, test, raw snapshot, candidate, freeze, reveal,
result, verdict, or prior report was changed to conceal that gap.

## Checkout and inputs

| Item | Observed value |
| --- | --- |
| Branch | `main` |
| HEAD | `c2999f0166daabab94a92a7489ae5608d0bfc704` |
| Worktree before this documentation change | clean |
| Frozen baseline named for the review | `c2999f0` |
| Actual evidence root | `var/research/task9-experiments-v2` |
| ETF OOS directory | `m1-etf-absolute-trend/oos/freeze-e75b8568e30efb9a` |

The terminal OOS result itself records execution commit
`4bccda490173debcd576125939b8b5c42fde13db`; this is the historical code
identity bound to that immutable OOS run, not a claim that the current HEAD
was used to rerun it.

## ETF terminal lifecycle

The required lifecycle is present, append-only, and catalogued in sequence.
All listed SHA-256 values were recomputed by the current `verify` command as
part of catalog validation.

| Stage | Catalog sequence | Reference | Status | Artifact digest |
| --- | ---: | --- | --- | --- |
| `OOS_FREEZE` | 66 | `m1-etf-absolute-trend/oos/freeze-e75b8568e30efb9a/freeze.json` | `OOS_FROZEN` | `sha256:fffb92ce53cae3606ab50ef6d58cb7c7d7b2a017ed86c551f82acd65bec0993c` |
| `OOS_REVEALED` | 67 | `m1-etf-absolute-trend/oos/freeze-e75b8568e30efb9a/reveal.json` | `OOS_REVEALED` | `sha256:c6e010c56c8392cfd076475d06a80e15b7fab0db101e67c1e5deab82193c6c09` |
| constrained recovery | 68 | `m1-etf-absolute-trend/oos/freeze-e75b8568e30efb9a/recovery.json` | `ADD_FREEZE_BOUND_BASIC_WARMUP` | `sha256:66b274aedc6371d75a23064dc98da7d39cfc94a76c1a80a0cea2459367fe1654` |
| `OOS_RUN` | 69 | `m1-etf-absolute-trend/oos/freeze-e75b8568e30efb9a/result.json` | `REJECTED_OOS` | `sha256:1d8d76e6226dc839a71eb52a5086cb65474f000b75f42a0d964b3eee9e5eefdb` |
| `OOS_VERDICT` | 70 | `m1-etf-absolute-trend/oos/freeze-e75b8568e30efb9a/verdict.json` | `REJECTED_OOS` | `sha256:b1238017ce65de434375a0b19e247ed92983fdedae767062f20da1924420b4f8` |
| `ASSET_CLASS_OUTCOME` | 71 | `outcomes/ETF.json` | `REJECTED_OOS` | `sha256:08ca0d4ee8ed938b84e819991f0ab25fdb747041574791aa8c0ae30c429cf0a0` |

The freeze is `freeze-e75b8568e30efb9a`; its immutable identity is
`freeze_digest=sha256:016a8fb6bb4899e15ce45b8e3e26911b98810d2de6834365d1eca1670b909303`.
It binds intent `m1-etf-absolute-trend-v1`, selected variant `sma-150`,
Basic snapshot `sha256:99a2d581dc1c7fa82f04cd1d18774c4d2da87380b96d394de0a22fa0828aa0b7`,
and legacy replay identity
`sha256:30b502997484a2ec42b3cda41152efd871ad1b722fb9151cfcc7c88f327cf60e`.
The result binds OOS snapshot
`sha256:276cc9e69fe729917fef7373a0f81822f6ddd59491676df1f0269fba5617a264`.

The recovery evidence is retained rather than erased.  It states
`OOS_HISTORY_INSUFFICIENT`, permits only
`ADD_FREEZE_BOUND_BASIC_WARMUP`, proves equality with the freeze-bound Basic
digest, and attests unchanged strategy, parameters, kernel, benchmark, gates,
and OOS window.  It does not replace the original reveal.

The result covers `2023-01-03` through `2025-12-31` (727 observations), has
`MIN_EXCESS_TOTAL_RETURN` = `FAIL` with observed `-0.4188260` versus `-0.05`,
and has `MAX_DRAWDOWN_FLOOR` = `PASS` with observed
`-0.3712689904098194154054474008` versus `-0.40`.  The sole terminal verdict
is therefore `REJECTED_OOS`.

## Other terminal evidence

| Subject | Evidence | Verified conclusion |
| --- | --- | --- |
| Stock | Catalog sequences 34, 44, 54, and 64 are `BASIC_SELECTION` records with `NO_BASIC_PASS`; no stock OOS lifecycle was opened. | `NO_OOS_ELIGIBLE_CANDIDATE` |
| AI source flight | Catalog sequence 65, `source-flights/m1-ai-source-flight-1/db56f5a6ae03be66.json`, digest `sha256:db56f5a6ae03be66032a4276d473eab9fbac4fa28ebb0f565a424bfcfcc4133b`. | `SCREEN_PASS` |
| Catalog | Current CLI verification of the actual root. | `PASS`, `findings=[]` |

The Stock status is supported by durable failed/selection evidence rather
than a stock OOS reveal or result: there was no eligible candidate to reveal.
No missing stock OOS artifact is represented as an OOS run.

## Old-report discrepancy and regeneration status

The retained old reports at
`var/research/M1-acceptance-report-cli-check.json` and
`var/research/M1-acceptance-report-after-oos-attempt.json` both report
`acceptance_status=FAIL`, `acceptance_findings=[ETF_OUTCOME_INVALID]`, ETF
`OOS_PENDING`, and `MISSING_OOS_OUTCOME`.  They only include catalog sequence
66 (`OOS_FREEZE`) and omit sequences 67--71.  Their findings are therefore
explained by their pre-terminal input state; they are not evidence against the
subsequently persisted terminal lifecycle.

A reachable but unmerged historical commit,
`e1d2dc3d2504931c6ded34e44a3a7a0970f72ee8` on
`codex/m1-recovery-final`, contains a derived report whose findings are empty
and whose ETF conclusion is `REJECTED_OOS`.  It is useful corroboration of
the above evidence, but it is not presented as a fresh report from current
HEAD.

The actual `main` CLI help at `c2999f0` exposes only `screen`,
`source-screen`, `basic-backtest`, `verify`, `oos-freeze`, `oos-run`,
`select-oos`, and `no-oos-eligible`; it has no `acceptance-report` or
`render-report`.  Because this review forbids changing research source code
or hand-editing acceptance JSON, a new report containing the requested
`input_root`, `generated_at`, `code_commit`, source identities, and old-report
relationship cannot truthfully be generated in this checkout.  This document
is the transparent close-out record for that limitation; restoring or
authorizing a compatible reporting command is an Owner Review decision.

## Commands and fresh verification

```powershell
python -m systematic_investing.research.cli --help
# current help: no acceptance-report or render-report subcommands

python -m systematic_investing.research.cli verify --root var/research/task9-experiments-v2
# {"command":"verify","findings":[],"schema_version":"research-cli-output-1","status":"PASS"}

python -m pytest tests/research/test_oos_verifier.py tests/research/test_basic_snapshot_boundary.py -q -p no:cacheprovider
# 36 passed
```

The commands used `PYTHONPATH=src`, disabled bytecode writes, and did not run
an OOS command or open an unapproved raw OOS snapshot.

## Close-out gate

```text
M1_TERMINAL_EVIDENCE = PASS
CATALOG_VERIFICATION = PASS
ACCEPTANCE_REPORT_REGENERATION = BLOCKED
```

| Check | Status | Evidence |
| --- | --- | --- |
| Immutable ETF terminal lifecycle | PASS | Sequences 66--71 and listed digests |
| `artifact_catalog_status` | PASS | fresh `verify`, `findings=[]` |
| `physical_oos_gate_status` | PASS in the retained report; no fresh acceptance command is available | old report field plus immutable freeze/reveal/result chain |
| ETF outcome | PASS | `outcomes/ETF.json`: `REJECTED_OOS` |
| Stock outcome | PASS | durable `NO_BASIC_PASS` selections; no OOS candidate |
| AI source flight | PASS | sequence 65: `SCREEN_PASS` |
| Fresh `acceptance_findings == []` / acceptance JSON | BLOCKED | current CLI lacks the two required report commands |
