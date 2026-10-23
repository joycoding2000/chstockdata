# M0 Foundation Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove and harden the approved M0 immutability, PIT, digest, deterministic execution, and accounting invariants without adding product functionality or resuming M1 Task 3.

**Architecture:** Keep the existing modular-monolith boundaries and public M0 contracts. Add narrowly scoped adversarial tests to the existing pytest layers, apply only test-proven P0/P1 fixes, and record owner-controlled real-data/qualification blockers rather than bypassing them.

**Tech Stack:** Python 3.14.5 executing a Python >=3.12 project, pytest 9.1.1, Ruff 0.16.6, mypy 2.3.1, standard-library frozen dataclasses and canonical SHA-256 digests.

**Execution outcome:** Tasks 1–8 were executed through final verification.
Offline M0 finished at 645 passed; the real-data smoke is owner-blocked by the
missing Basic snapshot. The final verdict is `DESIGN_CONFLICT` because the
documented complete-target rule conflicts with G15/current absent-target
behavior and no versioned carry-forward policy exists in the target contract.

---

### Task 1: Freeze the pre-change baseline

**Files:**
- Create: `docs/reports/M0-foundation-hardening-report.md`
- Read: `docs/reports/M0-acceptance-report.md`
- Read: `tests/qualification/reports/m0-etf-qualification-offline-v1.json`
- Read: `tests/parity/reports/m0-parity-offline-v1.json`

- [x] **Step 1: Record immutable baseline identity**

Run `git rev-parse HEAD`, `python --version`, hash `pyproject.toml`, and record the dirty working tree without staging or changing owner files.

- [x] **Step 2: Run the required M0 offline suite**

Run `python -m pytest tests/unit tests/contract tests/component tests/golden tests/integration -q -p no:cacheprovider`.

Expected baseline: `597 passed`.

- [x] **Step 3: Run static and type baselines**

Run `python -m ruff check src tests` and strict mypy over the M0 correctness-sensitive packages.

Expected baseline: Ruff clean; mypy reports the existing 90 errors in 11 files without configuration relaxation.

### Task 2: Deep immutability and PIT isolation regressions

**Files:**
- Create: `tests/unit/test_foundation_immutability.py`
- Modify: `src/systematic_investing/backtest/engine.py`
- Modify: `src/systematic_investing/data/snapshots.py`
- Modify: `src/systematic_investing/data/quality.py`
- Modify: `src/systematic_investing/domain/runs.py`
- Modify: `src/systematic_investing/domain/portfolio.py`
- Modify: `src/systematic_investing/domain/execution.py`

- [ ] **Step 1: Write failing shallow-freeze tests**

Construct `DecisionContext`, `DataSnapshotManifest`, `GateResult`, `RunManifest`, `TargetContribution`, and `Order` from caller-owned lists/dicts/sets. Capture their visible content and digest where available, mutate the caller collections, and assert the domain objects and digests are unchanged.

- [ ] **Step 2: Verify RED**

Run `python -m pytest tests/unit/test_foundation_immutability.py -q -p no:cacheprovider`.

Expected: failures show post-construction mutation changing the context, object content, or digest; failures must not be caused by malformed fixtures.

- [ ] **Step 3: Apply minimal defensive canonicalization**

At each affected frozen boundary, copy sequences to tuples, sets to frozensets, and mappings to read-only copies during `__post_init__`. Preserve existing accepted values and public semantics; do not introduce a new abstraction layer.

- [ ] **Step 4: Verify GREEN and PIT compatibility**

Run the new module plus `tests/component/test_no_lookahead.py`, `tests/integration/test_snapshot_replay.py`, `tests/unit/test_target_portfolio.py`, and `tests/integration/test_manifest_identity.py`.

- [ ] **Step 5: Commit only Task 2 files**

Commit message: `fix: enforce deep immutability at M0 boundaries`.

### Task 3: Bind replay digests to complete semantic content

**Files:**
- Create: `tests/integration/test_foundation_digest_binding.py`
- Modify: `src/systematic_investing/data/snapshots.py`
- Modify: `src/systematic_investing/domain/ledger.py`
- Modify: `src/systematic_investing/backtest/engine.py`

- [ ] **Step 1: Write failing digest sensitivity tests**

Prove that changing snapshot quality receipt identity/status, acquisition-lot settlement schedule, order/fill/rejection trace identity, or ledger source/session content changes the corresponding snapshot/portfolio/backtest normalized digest. Preserve explicit exclusions for wall-clock retrieval/creation timestamps only where the approved semantics declare them non-identity metadata.

- [ ] **Step 2: Verify RED**

Run `python -m pytest tests/integration/test_foundation_digest_binding.py -q -p no:cacheprovider` and confirm each collision is reproducible on the baseline implementation.

- [ ] **Step 3: Extend existing canonical renderers minimally**

Include every replay- or finance-sensitive field in stable, sorted canonical digest lines. Do not hash object `repr` when an explicit canonical field representation exists.

- [ ] **Step 4: Verify GREEN and golden replay**

Run the new digest tests, `tests/integration/test_reproducibility.py`, `tests/integration/test_snapshot_replay.py`, and `tests/golden`.

- [ ] **Step 5: Commit only Task 3 files**

Commit message: `fix: bind M0 digests to semantic state`.

### Task 4: Adversarial contract-boundary matrix

**Files:**
- Create: `tests/component/test_foundation_adversarial_boundaries.py`
- Read/modify only if a regression is RED: the smallest M0 module responsible for that invariant

- [ ] **Step 1: Add PIT and data boundary attacks**

Cover post-T mutation invariance, retrieval-time non-substitution, UNKNOWN fail-closed behavior, future corporate-action/tradability exclusion, full-table/precomputation rejection, checksum corruption, typed duplicate/partial/malformed outcomes, and empty-success versus provider-failure distinction. Reuse existing fixtures when they already prove the exact invariant and add only missing attacks.

- [ ] **Step 2: Add Instrument Master attacks**

Cover provider-conflict authority, unknown rule/profile/subtype fail-closed behavior, broker-fee exclusion from identity, and effective-date selection on both sides of a boundary.

- [ ] **Step 3: Add portfolio/risk/execution attacks**

Cover zero versus absent, explicit sleeves, no risk-created exposure, caps after discretization, stable tie-breaking, negative-cash refusal, T-close/T+1 separation, all-or-none submission, sellability, typed tradability rejects, and corporate-action replan without target mutation.

- [ ] **Step 4: Run RED→GREEN only for newly discovered defects**

For any failing approved invariant, keep the minimal failing test, change only the owning implementation, and rerun the focused module before broader suites.

- [ ] **Step 5: Commit cohesive boundary changes**

Commit message: `test: harden adversarial M0 contract boundaries`, unless a production fix warrants a separate `fix:` commit.

### Task 5: Deterministic accounting state sequences

**Files:**
- Create: `tests/component/test_foundation_state_sequences.py`
- Modify only on a proven RED: `src/systematic_investing/backtest/accounting.py`, `src/systematic_investing/backtest/execution.py`, or `src/systematic_investing/backtest/engine.py`

- [ ] **Step 1: Add fixed short sequences**

Implement deterministic parameterized sequences for buy→sellability→sell; simultaneous buys under gap/cash pressure; pending order→quantity-changing action; suspension→stale mark→resume; CORE/SATELLITE limited-cash allocation; and minimum commission→lot rounding→residual cash.

- [ ] **Step 2: Assert cross-sequence conservation**

For every sequence assert non-negative cash/holdings, sellable not above total, fill/order/rejection consistency, exact fee cash entries, no repeated minimum commission, no double-counted corporate action, raw-price accounting truth, locked-target immutability, ledger reconstruction, and repeated normalized digest equality.

- [ ] **Step 3: Verify RED or GREEN honestly**

Run `python -m pytest tests/component/test_foundation_state_sequences.py -q -p no:cacheprovider`. If all tests pass on baseline, record that the attack found no defect; do not alter production code.

- [ ] **Step 4: Commit sequence tests and any separately proven fix**

Commit message: `test: add deterministic M0 accounting sequences`.

### Task 6: Real canonical-data vertical smoke

**Files:**
- Create: `tests/integration/test_m0_real_data_vertical_smoke.py`
- Read only: `var/research/snapshots/basic-etf-v1`

- [ ] **Step 1: Resolve the owner snapshot without mutation**

Require an existing immutable snapshot at `var/research/snapshots/basic-etf-v1`; never create, overwrite, or commit market data from this test.

- [ ] **Step 2: Implement the smallest predetermined-target smoke**

Load and checksum-verify the manifest/artifacts, run the Data Quality Gate against the approved Instrument Master, select very few instruments/sessions, feed an explicitly named predetermined target fixture through the M0 engine, ledger, NAV, and metrics, then repeat and compare normalized digests.

- [ ] **Step 3: Execute or record the exact owner blocker**

Run `python -m pytest tests/integration/test_m0_real_data_vertical_smoke.py -q -p no:cacheprovider`. If the canonical snapshot is absent, record `OWNER_ACTION_REQUIRED` with the exact Task 3 materialization command discovered from the current M1 CLI; do not substitute synthetic data and do not declare PASS.

- [ ] **Step 4: Commit the smoke harness only**

Commit message: `test: add real-data M0 vertical smoke`.

### Task 7: Correctness-sensitive typing audit

**Files:**
- Modify only test-proven correctness-sensitive files among the M0 core packages
- Record non-blocking categories in `docs/reports/M0-foundation-hardening-report.md`

- [ ] **Step 1: Classify all 90 baseline findings**

Separate Optional/Any/enum/return/date/money/provider-result findings that can change behavior from annotation-only and third-party-boundary noise.

- [ ] **Step 2: Fix only correctness-sensitive findings**

Use focused runtime or static regression evidence before each change. In particular, correct the `Order.rejected` return contract and any unsafe Optional narrowing discovered in accounting/execution/engine paths; do not pursue repository-wide zero errors.

- [ ] **Step 3: Re-run strict core mypy**

Report baseline count, fixed correctness-sensitive count, and remaining findings by non-blocking category without changing mypy configuration.

- [ ] **Step 4: Commit focused typing corrections**

Commit message: `fix: narrow correctness-sensitive M0 types`.

### Task 8: Evidence impact and final gate report

**Files:**
- Create: `docs/reports/M0-foundation-hardening-report.md`
- Optionally create: `docs/reports/M0-foundation-hardening-report.json`

- [ ] **Step 1: Audit live qualification evidence**

Record exact command, time, provider pin, adapter version, result, artifact digest, and whether any hardening change invalidates qualification-sensitive code. Never use owner credentials.

- [ ] **Step 2: Audit Task 3 artifacts**

State `VALID`, `INVALIDATED`, or `OWNER_ACTION_REQUIRED` separately for live qualification and `basic-etf-v1`; state whether Basic research must rerun after any backtest/accounting/fee/portfolio/metrics change.

- [ ] **Step 3: Run final verification fresh**

Run all hardening tests; the complete required M0 offline suite; golden and replay; import/boundary tests; relevant M1 Task 1/2 regressions; Ruff; and strict core mypy. Record exact counts and exits.

- [ ] **Step 4: Write the required report and verdict**

Populate Baseline, audited-invariant table, findings by severity, every workstream, Task 3 impact, known limitations, deferred debt, commits, and exactly one allowed verdict: `PASS`, `FAIL`, `OWNER_ACTION_REQUIRED`, or `DESIGN_CONFLICT`.

- [ ] **Step 5: Commit the report**

Commit message: `docs: record M0 foundation hardening gate`.

## Self-review

- Spec coverage: Tasks 1–8 cover baseline, all six audit workstreams, typing, real-data smoke, qualification evidence, Task 3 impact, final verification, reporting, and focused commits.
- Scope: no Strategy, Alpha, UI, scheduler, broker, M2/M3, or architecture expansion is introduced.
- TDD: every P0/P1 production change is preceded by a focused failing regression and observed RED.
- Stop condition: after the report and gate verdict, stop for owner review; do not resume M1 Task 3 or begin later milestones.
