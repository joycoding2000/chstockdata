# Resolve M0 Target Completeness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enforce owner-approved complete targets and fail-fast Basic ETF materialization reference checks, leaving only owner-controlled live/data evidence outstanding.

**Architecture:** Validate target completeness once in `DailyBarEngine._decide`, after an actual target exists and before risk/allocation. Add a provider-free static materializer preflight that validates the frozen shared scope and effective-dated Instrument Master coverage before provider construction; retain the full gate after acquisition.

**Tech Stack:** Python 3.14, pytest, Ruff, mypy, immutable dataclasses, existing M0 engine/Instrument Master/Data Quality Gate.

---

### Task 1: Complete-target engine boundary and G15

**Files:**
- Modify: `src/systematic_investing/backtest/engine.py`
- Modify: `src/systematic_investing/portfolio/validation.py`
- Modify: `tests/fixtures/golden/G15/{scenario.json,expected.json,README.md}`
- Modify: `tests/golden/test_golden_scenarios.py`
- Test: `tests/component/test_foundation_adversarial_boundaries.py`

- [ ] Add RED tests proving an actual target that omits a holding yields typed `TARGET_INCOMPLETE`, while explicit zero exits and explicit unchanged produces no delta.
- [ ] Run focused tests and confirm the missing-target assertion fails for the expected reason.
- [ ] Add `DecisionBlockReason.TARGET_INCOMPLETE` and call the existing validator exactly once immediately after target construction.
- [ ] Update G15's manually calculated complete and incomplete runs; do not derive expected JSON from implementation output.
- [ ] Run G15, target, engine, risk, allocation, and adversarial tests GREEN.
- [ ] Commit the cohesive completeness change.

### Task 2: M1 `NO_DECISION` compatibility

**Files:**
- Test/modify only if RED: `tests/research/test_strategy_contract.py`
- Test/modify only if RED: `src/systematic_investing/research/runner.py`

- [ ] Add a regression proving typed `NO_DECISION` returns no M0 target and does not become CASH, zero, or `TARGET_INCOMPLETE`.
- [ ] Add a regression proving a TARGETS result missing a held instrument reaches M0 and fails completeness.
- [ ] Run RED/GREEN; change the adapter only if the approved behavior is not already present.
- [ ] Commit the M1 compatibility tests/fix.

### Task 3: Reproduce and close historical Instrument Master coverage

**Files:**
- Modify/stage in-scope existing work: `src/systematic_investing/instrument_master/repository.py`
- Modify/stage in-scope existing work: `tests/unit/test_instrument_master_authority.py`
- Test: `tests/unit/test_materializer_gate_receipt.py`

- [ ] Add/retain RED evidence that the old `2022-01-04` seed fails all four ETF IDs on `2015-01-05`.
- [ ] Assert exact approved subtype, listing identity, profile family, and continuous effective-date coverage for all four instruments.
- [ ] Verify canonical IDs match candidate/shared scope and provider request parsing.
- [ ] Run Instrument Master and materializer diagnostic tests GREEN.
- [ ] Commit the approved historical-reference correction separately.

### Task 4: Provider-free materializer preflight

**Files:**
- Modify: `src/systematic_investing/research/materializer.py`
- Modify: `tests/unit/test_materializer_gate_receipt.py`
- Modify: `tests/integration/test_research_cli.py`

- [ ] Write RED tests for scope expansion, invalid ID, subtype/profile/date gaps, existing output, zero provider calls, and no output directory.
- [ ] Add `preflight_materialization(plan, output_dir, master)` with deterministic typed diagnostics across the requested interval.
- [ ] Call preflight before `_provider()` in normal materialization.
- [ ] Add `--preflight-only`; it prints a deterministic PASS receipt and never constructs the provider.
- [ ] Run focused unit/integration tests GREEN and Ruff the touched files.
- [ ] Commit the preflight change.

### Task 5: Documentation and final gate

**Files:**
- Modify: `docs/architecture/{domain-model,portfolio-risk-semantics,test-plan}.md`
- Modify: `docs/reports/M0-foundation-hardening-report.md`

- [ ] Remove M0 carry-forward alternatives and record owner-approved fail-closed semantics.
- [ ] Record exact Phase-4 IDs/date/root cause, declared shared scope, preflight behavior, and owner-only commands.
- [ ] Run hardening-focused tests, full M0 offline, golden/replay, M1 Task 1/2, qualification/parity offline, Ruff, and strict core mypy.
- [ ] Set verdict to `OWNER_ACTION_REQUIRED` unless owner-controlled evidence has appeared; never claim PASS.
- [ ] Commit the report/docs, retain the branch, and stop without running live qualification/materialization or resuming M1 Task 3.
