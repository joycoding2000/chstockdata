# Frozen Historical Kernel Replay Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an explicit, fail-closed replay profile for the historical `m0-accounting-1` kernel, keep `m0-accounting-2` as the default, validate replay support before persisting future freezes, and resume the existing controlled ETF OOS freeze only after synthetic compatibility tests pass.

**Architecture:** `AccountingSemantics` is an explicit engine input. `KernelReplayProfile` describes the engine, risk composition, execution convention, accounting semantics, and exact identity derivation; the legacy profile reproduces the pre-`9789c55` identity lines without inventing a new digest. Basic wiring always selects the current profile, while OOS identity verification resolves a supported profile from the freeze-bound digest before reveal and passes that profile into the engine.

**Tech Stack:** Python 3.12, dataclasses/`StrEnum`, pytest, mypy strict, Ruff, the existing research CLI/catalog and `DailyBarEngine`.

---

## Audit facts and global constraints

- Selected ETF Basic evidence is `var/research/task9-experiments-v2/m1-etf-absolute-trend/runs/run-b5380f4544a38754/manifest.json`, variant `sma-150`, code commit `f786b8e3bd90118a436625654103695366d189c8+worktree:2bebb01d8330f393`.
- The retained Basic and freeze-bound kernel digest is `sha256:30b502997484a2ec42b3cda41152efd871ad1b722fb9151cfcc7c88f327cf60e`.
- The current default digest is `sha256:e4038c1ba724231d32183053a4a4d276f0ce710bf4d2b8747f222901f1f9b309`.
- The legacy digest algorithm is the pre-`9789c55` canonical lines: kernel schema, engine, risk composition, and execution model; it has no `accounting_semantics` line. The legacy accounting behavior rejects any non-integral share grant.
- Never read `var/research/oos/freeze-e75b8568e30efb9a/artifacts/*.jsonl` or any OOS bars, corporate actions, returns, or other research content during compatibility work. Metadata already audited may be used.
- Do not recreate Basic evidence, create a replacement freeze, rematerialize the OOS snapshot, alter the intent/variant/window, weaken `OOS_FREEZE_KERNEL_MISMATCH`, or open the real OOS snapshot before all pre-OOS checks pass.
- Preserve the user's existing `.gitignore` modification and stage only files belonging to this plan.

## Task 1: Add profile-based identity derivation

**Files:**
- Create: `src/systematic_investing/research/kernel_replay.py`
- Test: `tests/research/test_kernel_replay.py`

- [ ] **Step 1: Write failing identity tests.**

Add tests that construct `ExecutionModel(slippage_rate_buy=Decimal("0.0005"), slippage_rate_sell=Decimal("0.0005"))` and assert:

```python
def test_legacy_profile_reproduces_the_frozen_basic_digest() -> None:
    assert legacy_kernel_replay_profile.identity_digest(model) == (
        "sha256:30b502997484a2ec42b3cda41152efd871ad1b722fb9151cfcc7c88f327cf60e"
    )


def test_current_profile_preserves_the_current_digest() -> None:
    assert current_kernel_replay_profile.identity_digest(model) == (
        "sha256:e4038c1ba724231d32183053a4a4d276f0ce710bf4d2b8747f222901f1f9b309"
    )


def test_unknown_digest_has_no_replay_profile() -> None:
    with pytest.raises(UnsupportedKernelReplayError):
        resolve_kernel_replay_profile("sha256:" + "0" * 64, model)
```

- [ ] **Step 2: Run the focused tests and verify the expected RED failure.**

Run: `pytest tests/research/test_kernel_replay.py -q`

Expected: collection fails because `systematic_investing.research.kernel_replay` and its profile symbols do not yet exist.

- [ ] **Step 3: Implement the profile and canonical algorithms.**

Define a frozen `KernelReplayProfile` with explicit `profile_id`, `identity_scheme`, `accounting_semantics`, `engine`, `risk_composition`, `execution_semantics`, and `include_accounting_semantics_in_identity` fields. Define `current_kernel_replay_profile` and `legacy_kernel_replay_profile` constants, enumerate only those two in `SUPPORTED_KERNEL_REPLAY_PROFILES`, derive the digest by hashing the profile's canonical lines, and make `resolve_kernel_replay_profile` compare generated digests rather than whitelisting a literal digest.

The canonical identity lines must be:

```python
[
    "research_kernel_identity_v1",
    "engine=systematic_investing.backtest.engine.DailyBarEngine",
    f"risk_composition={IDENTITY_RISK_COMPOSITION_VERSION}",
    # current profile only:
    f"accounting_semantics={AccountingSemantics.CURRENT.value}",
    f"execution_model={execution_model.version}",
]
```

The legacy profile omits the accounting line exactly as the pre-`9789c55` source did. Reject an execution model whose version differs from the profile's declared execution convention.

- [ ] **Step 4: Run the focused tests and verify GREEN.**

Run: `pytest tests/research/test_kernel_replay.py -q`

Expected: 3 passing tests, including exact legacy and current digests.

- [ ] **Step 5: Commit the profile and identity tests.**

```powershell
git add src/systematic_investing/research/kernel_replay.py tests/research/test_kernel_replay.py docs/superpowers/plans/2026-09-21-frozen-kernel-replay.md
git commit -m "feat(m1): add historical kernel replay profiles"
```

## Task 2: Make accounting semantics explicit and executable

**Files:**
- Modify: `src/systematic_investing/backtest/accounting.py:1-235`
- Modify: `src/systematic_investing/backtest/engine.py:39-45,576-633,791-853`
- Test: `tests/research/test_kernel_replay.py`
- Test: `tests/component/test_corporate_actions.py:446-580`

- [ ] **Step 1: Write failing behavior tests.**

Add a synthetic `m0-accounting-1` test using the existing `CorporateAction`/`Position` fixture and call `apply_corporate_action(..., accounting_semantics=AccountingSemantics.LEGACY_M0_ACCOUNTING_1, fraction_price=Decimal("10.00"))`; assert `CorporateActionAccountingError` for `432 * 1.2`. Add the paired current-profile assertion for the same input: 518 shares, `quantity_delta == 86`, and `cash_delta == Money(Decimal("4.00"))`. Add an integral split assertion for both semantics and assert the same 600-share result.

- [ ] **Step 2: Run the new behavior tests and verify RED.**

Run: `pytest tests/research/test_kernel_replay.py tests/component/test_corporate_actions.py -q`

Expected: the new tests fail because the accounting function and engine do not accept an explicit semantics selector.

- [ ] **Step 3: Implement explicit accounting selection.**

Add `AccountingSemantics(StrEnum)` with `LEGACY_M0_ACCOUNTING_1 = "m0-accounting-1"` and `CURRENT_M0_ACCOUNTING_2 = "m0-accounting-2"`, retain `ACCOUNTING_SEMANTICS_VERSION` as the current string for compatibility, and add `accounting_semantics: AccountingSemantics = AccountingSemantics.CURRENT_M0_ACCOUNTING_2` to `apply_corporate_action`.

For the legacy value, preserve the pre-`9789c55` branch exactly: any fractional or non-positive scaled lot raises `CorporateActionAccountingError`; never floor and never pay cash in lieu. For the current value, retain existing floor/cash-in-lieu behavior. Reject an unknown semantics value with `AccountingError`.

Add `accounting_semantics` to `DailyBarEngine.__init__`, default it to current semantics, validate it, store it, and pass it into `apply_corporate_action`. Only calculate the current profile's fraction price when the selected semantics is current; legacy replay must not silently use the current compensation behavior.

- [ ] **Step 4: Run the behavior and existing M0 tests and verify GREEN.**

Run: `pytest tests/research/test_kernel_replay.py tests/component/test_corporate_actions.py tests/component/test_event_order.py tests/component/test_tradability.py -q`

Expected: all targeted tests pass and existing accounting-2 behavior remains unchanged.

- [ ] **Step 5: Commit the explicit accounting seam.**

```powershell
git add src/systematic_investing/backtest/accounting.py src/systematic_investing/backtest/engine.py tests/research/test_kernel_replay.py tests/component/test_corporate_actions.py
git commit -m "feat(m0): make accounting semantics selectable"
```

## Task 3: Thread replay profiles through Basic and OOS wiring

**Files:**
- Modify: `src/systematic_investing/research/runner.py:35-40,360-369,372-400,419-540,582-805`
- Modify: `src/systematic_investing/research/oos.py:25-105,1114-1360,1441-1538`
- Test: `tests/research/test_kernel_replay.py`
- Test: `tests/research/test_oos_verifier.py`

- [ ] **Step 1: Write failing wiring tests.**

Add assertions that `BasicWiring` and `OosWiring` default to `current_kernel_replay_profile`, that `kernel_identity_digest(model)` is exactly the current digest, and that `oos_kernel_identity_digest(intent, profile=legacy_kernel_replay_profile)` returns the frozen `30b502…` digest.

- [ ] **Step 2: Run the wiring tests and verify RED.**

Run: `pytest tests/research/test_kernel_replay.py tests/research/test_oos_verifier.py -q`

Expected: the profile keyword/fields are not yet available.

- [ ] **Step 3: Implement profile threading without changing current defaults.**

Keep `runner.kernel_identity_digest(execution_model)` as a compatibility wrapper that delegates to the current profile, and add an optional `profile` keyword. Add a `kernel_profile` field to `BasicWiring` and `OosWiring`, defaulting to the current profile in normal builders. Use `wiring.kernel_profile.accounting_semantics` when constructing `DailyBarEngine`, and use the same profile for the manifest kernel digest. Add an optional `kernel_profile` keyword to `oos_kernel_identity_digest` and `build_oos_wiring`; existing callers without the keyword must remain current-profile calls.

- [ ] **Step 4: Run the wiring and research regression tests and verify GREEN.**

Run: `pytest tests/research/test_kernel_replay.py tests/research/test_oos_verifier.py tests/research/test_etf_absolute_trend_flight.py tests/research/test_stock_relative_strength_flight.py -q`

Expected: all pass, with current Basic/OOS identity behavior unchanged.

- [ ] **Step 5: Commit profile propagation.**

```powershell
git add src/systematic_investing/research/runner.py src/systematic_investing/research/oos.py tests/research/test_kernel_replay.py tests/research/test_oos_verifier.py
git commit -m "feat(m1): thread replay profiles through research wiring"
```

## Task 4: Resolve legacy identity before reveal and validate at freeze time

**Files:**
- Modify: `src/systematic_investing/research/oos.py:145-175,739-805`
- Modify: `src/systematic_investing/research/cli.py:781-830,896-980`
- Test: `tests/research/test_oos_verifier.py`
- Test: `tests/integration/test_research_cli.py`

- [ ] **Step 1: Write failing gate tests.**

Add these synthetic tests:

```python
def test_supported_legacy_freeze_resolves_before_snapshot_open() -> None:
    payload = _resign_freeze({**_current_freeze_payload(),
                              "kernel_identity_digest": FROZEN_LEGACY_DIGEST})
    assert resolve_freeze_kernel_replay_profile(payload, _intent()) is legacy_kernel_replay_profile
```

Add an integration test that changes a retained Basic manifest's kernel digest to `sha256:` plus 64 zeroes, runs `oos-freeze`, asserts `OOS_FREEZE_KERNEL_UNSUPPORTED`, asserts the lineage has no `oos/<freeze-id>/freeze.json`, and asserts the catalog has no new `OOS_FREEZE` entry. Add an unknown-digest OOS-run test that confirms no `reveal.json`, `result.json`, or `verdict.json` is written and the supplied snapshot reader is never called.

- [ ] **Step 2: Run the gate tests and verify RED.**

Run: `pytest tests/research/test_oos_verifier.py tests/integration/test_research_cli.py -q`

Expected: legacy freeze resolution is unavailable and freeze currently persists an unsupported kernel before runtime verification.

- [ ] **Step 3: Implement fail-closed profile resolution and freeze validation.**

Add `REASON_FREEZE_KERNEL_UNSUPPORTED = "OOS_FREEZE_KERNEL_UNSUPPORTED"`. Implement `resolve_freeze_kernel_replay_profile(freeze_payload, intent)` by deriving the intent's exact `ExecutionModel`, resolving the digest through `resolve_kernel_replay_profile`, and translating unsupported/incompatible profiles into `OosFreezeError` with the existing `OOS_FREEZE_KERNEL_MISMATCH` reason for OOS-run. In `command_oos_freeze`, resolve and validate the retained Basic manifest's kernel before `build_freeze_payload`, `persist_freeze`, or `append_entry`; translate an unsupported profile to `OOS_FREEZE_KERNEL_UNSUPPORTED`.

In `command_oos_run`, call the strategy identity check and resolve the profile before optional warm-up loading, `record_reveal`, and any OOS `SnapshotReader.load`. Pass the resolved profile into `build_oos_wiring`. Keep the exact order `freeze verification -> intent/strategy identity -> kernel replay identity -> optional warm-up/snapshot open -> reveal -> OOS execution`, and keep both mismatch/unsupported paths fail closed.

- [ ] **Step 4: Run the gate tests and verify GREEN.**

Run: `pytest tests/research/test_oos_verifier.py tests/integration/test_research_cli.py -q`

Expected: supported legacy identity resolves and passes, unknown identity fails before reveal/open, and unsupported freeze creation leaves no freeze file or catalog append.

- [ ] **Step 5: Commit the OOS gate changes.**

```powershell
git add src/systematic_investing/research/oos.py src/systematic_investing/research/cli.py tests/research/test_oos_verifier.py tests/integration/test_research_cli.py
git commit -m "fix(m1): validate executable replay before OOS reveal"
```

## Task 5: Pre-OOS verification and controlled continuation

**Files:**
- No new production files; only test/report artifacts created by approved commands may be generated under `var/`.

- [ ] **Step 1: Run all compatibility and pre-OOS checks.**

Run the smallest checks first:

```powershell
pytest tests/research/test_kernel_replay.py tests/research/test_oos_verifier.py tests/component/test_corporate_actions.py -q
pytest tests/research -q
pytest tests/integration/test_research_cli.py -q
pytest tests/component -q
ruff check src tests
mypy src
```

Expected: all pass; no command in this task opens `var/research/oos/freeze-e75b8568e30efb9a/artifacts`.

- [ ] **Step 2: Check the real CLI help and existing artifact metadata.**

Run: `pytest tests/integration/test_research_cli.py -q -k 'oos'` and the repository's actual CLI `--help` command. Confirm the root is `var/research/task9-experiments-v2`, the freeze is `freeze-e75b8568e30efb9a`, and the snapshot manifest is `var/research/oos/freeze-e75b8568e30efb9a/manifest.json`. Do not create a new Basic run or freeze.

- [ ] **Step 3: Run the existing freeze only when all pre-OOS checks pass.**

Use the repository's actual `oos-run` options shown by `--help`, with the existing freeze root and materialized snapshot. If exact legacy replay raises a typed `CorporateActionAccountingError` or another kernel failure, stop and retain that evidence; never retry with current accounting-2.

- [ ] **Step 4: Only after a terminal OOS outcome, run acceptance reporting.**

Run the repository's existing `acceptance-report` and `render-report` commands only after `OOS_REVEALED`, `OOS_RUN`, `OOS_VERDICT`, and `ASSET_CLASS_OUTCOME` are durably recorded. Verify `acceptance_findings == []`, `artifact_catalog_status == PASS`, `physical_oos_gate_status == PASS`, ETF outcome is `SURVIVOR` or `REJECTED_OOS`, Stock is `NO_OOS_ELIGIBLE_CANDIDATE`, AI source flight is `SCREEN_PASS`, and `acceptance_status == PASS` without editing any PASS artifact.

- [ ] **Step 5: Record final evidence and leave M2 untouched.**

Capture the historical identity audit, root defect, replay design, changed files, test commands/results, `snapshot opened during tests = NO`, real lifecycle sequence/ref/digests, honest ETF result or typed failure, M1 acceptance findings, and:

```powershell
git status --short
git diff --stat
git log -5 --oneline
```
