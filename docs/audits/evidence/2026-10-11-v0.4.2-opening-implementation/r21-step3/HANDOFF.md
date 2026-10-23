# Step3 implementation handoff — 2026-10-12

Status: DONE. Current phase is v0.4.2 FIX_ONLY / Step3. Local Step3 qualification
is PASS, pending independent fresh specification and quality reviews. Step4
was not executed; no wheel was built, commit created, push, merge, tag or release.

The isolated SIOS export is based on `84fd54fae0740bc06b1d250afa4578be29556956`
and has no `.git`. Step3 changed only the qualification helper, original ETF
qualification module, new orchestration regression module, and the existing R2.1
contract document. `step3-changes.diff` contains these changes. All 54 SIOS runtime
file hashes still match Step2 tree identity
`73376752616edc41b1560e0cea40a7cdb6190d2795c83dab34d19fdcffd4186f`.
The CH opening reader SHA256 remains
`8e48f46373f974f665807dc3e2db8d7b8520588b699c7bce9fbf8c20986061a8`.
Final runtime and qualification test/document before/after hashes are unchanged.

Evidence:

- `red.xml` / `red.log` / `red.exit`: initial 2 expected failures, missing
  capability collector and real 0.4.2 client admission in the old live helper.
- `engine-red.xml`: bond regression 1 failed / 4 passed, confirming an empty
  plan with insufficient test allocation.
- `local-repro-red/report.json`: all six real failed-run snapshots reproduce
  the helper's tuple-order assertion; full canonical content digests are equal.
- `local-repro-green/report.json`: all six actual inputs pass after the minimal
  helper correction. This is an offline diagnostic, never new live evidence.
- `final-green.xml` / log / exit: 17 passed and 5 original live tests skipped
  under the normal offline opt-in behavior. Root's older independent 16-case
  run belongs to the previous helper version and is superseded.
- `live.xml` / `live.log` / `live.exit`: all five original mandatory live names,
  5 passed, zero failures/errors/skips, exit 0; explicit class selector with no
  added deselection. This is the final actual source-code run.
- `all-capabilities.json`: 54 independent outcomes, all PASS. Four targets
  retain original bars/actions/calendar/freshness/unit/history requirements.
  Four OPEN facts produce positive planned orders and RAW daily-open-based
  fills through actual v3 snapshot replay and actual DailyBarEngine. Two
  official halt controls produce rejected nonempty orders and no fills.
- `all-calls-coverage.json` / `calls.json` / `raw/`: 111 observed calls;
  complete parser-returned TDX rows or actual HTTP bodies, all retained SHA256
  values verified. Six new official queries are independently successful and
  complete; known cached positive events supplement rather than replace them.
- `actual-imports.json`, `live-command.json`, `execution-journal.json`:
  actual import/version, executable, argv, cwd, environment, bounded policy
  and wrapper/source identities. Candidate 0.4.2 admission is explicit;
  default 0.3.0 pin still rejects it.

The new opening reader used the fixed certified host, finite pages and no
retry/discovery. Original calendar staleness and fallback were retained; the
final actual calendar route was `sina_sh000001`, stale false. Do not describe
the entire qualification run as a single-host run. QDII controls only isolate
source veto and engine rejection; no QDII corporate-action or product
qualification was added.

The qualification RunManifest uses the actual combined source-tree SHA256 in
its existing `code_commit` test identity field, not a Git commit; the frozen
baseline commit is recorded separately. Its actual v3 data snapshot binds full
execution facts, R2.1 and the Shanghai clock. This source run does not claim
new-wheel qualification.

Preserved prior outcomes: `invalid-observation-run/` is an interrupted observer
serialization failure and provides no qualification verdict;
`failed-live-run-1/` is the real 4-pass/1-fail run, retained intact. The latter
failure was confined to helper tuple equality; production runtime was not
changed. Final PASS is bound to the final helper hashes, not these earlier runs.

Unresolved Step3 blockers: none. No scope expansion. Remaining boundaries are
unchanged: full historical PIT/full-day suspension is still UNKNOWN/fail-closed;
[09:30,09:31) activity is an execution proxy and does not establish 09:15
knowledge, all-day trading or arbitrary-order fill at exactly 09:30.

Next minimum action: fresh independent Step3 specification review followed by
quality review. This handoff does not authorize a research phase or release.

## Optional-vendor P1 review correction

Fresh quality review returned REWORK: one unguarded offline regression imported
actual chstockdata and asserted 0.4.2, breaking optional-vendor absence and the
valid old 0.3.0 pin. The prior summary, diff, handoff and regression source are
preserved in `optional-vendor-rework/before-*`; this history is not overwritten.

Only that offline regression now injects minimal candidate/legacy library
objects into the existing client constructor. It proves explicit 0.4.2
admission, default rejection of that candidate and 0.3.0 compatibility. Actual
vendor import/version/default-rejection assertions remain in the original five
mandatory live tests, with no new skips.

Both simulated absence and 0.3.0 produced RED (1 failure each), then GREEN
(1 pass each). The complete relevant offline run passed 17 tests with only the
five original opt-in skips. Logs/JUnit/exit/argv/env and new regression hash are
under `optional-vendor-rework/`; `qualification-current.json` records current
test/document identities. No network was repeated: runtime, live helper, all
five live-test module bytes and contract document are unchanged from the
actual 5-pass run. Its original qualification before/after hashes remain
preserved; the sole newer hash belongs to the offline regression file.

P1 implementation status: fixed, pending the finite fresh specification and
quality re-review. Step4 remains unexecuted here.
