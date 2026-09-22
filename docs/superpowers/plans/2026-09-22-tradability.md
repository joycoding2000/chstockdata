# Tradability Derived Fact Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `fetch_tradability(ticker, curr_date, *, root=None)` as a conservative derived capability composed only from the structured trading-calendar and suspension results.

**Architecture:** `tradability.py` calls `fetch_trading_calendar(root=root, today=curr_date)`, derives the calendar verdict with `is_trading_day`, and calls `fetch_suspension_info` only after a confirmed trading day. It returns the six-field verdict dict and creates one `FetchMetadata(capability="tradability")` by concatenating child attempts, providers, and limitations in execution order without recording a new capability-health observation.

**Tech Stack:** Python 3.10+ typing/dataclasses, existing `FetchResult`/`FetchMetadata` contracts, pytest and monkeypatch seams.

**Spec:** Current user request in this task.

## Global Constraints

- Version remains `0.3.0`.
- The only facts composed are Trading Calendar and Suspension.
- Do not call legacy JSON APIs, `get_delisting_info`, listing/delisting, corporate actions, GenericFallbackRouter, or consumer migration paths.
- Use `capability="tradability"`; never create a tradability provider, provider capability, capability-health observation, or `record_fetch_observation("tradability", ...)` call.
- Preserve child `attempts`, `providers_used`, and `limitations` in calendar-then-suspension order.
- A confirmed trading day plus confirmed no-suspension is the only `tradable=True` path; unknown facts remain `None`.

## Review Focus

- A holiday must short-circuit before Eastmoney suspension retrieval; covered by the holiday test.
- A date outside calendar coverage must not be treated as a holiday or open; covered by the calendar-unknown test.
- A suspension failure on an otherwise open day must not become `tradable=True`; covered by the failure test.
- A normal-empty suspension answer is a confirmed no-record answer, not a provider failure; covered by the no-suspension test.
- Combining child metadata must not invent a `tradability:*` health entry or reorder attempts; covered by the provenance test.

---

### Task 1: Lock the derived verdict and provenance contract with failing tests

**Files:**
- Create: `tests/test_tradability.py`

**Interfaces:**
- Consumes: `fetch_tradability`, `TradingCalendar`, `FetchAttempt`, `FetchMetadata`, and `FetchResult`.
- Produces: executable cases for all required verdict branches, short-circuit behavior, metadata order, and health isolation.

- [ ] **Step 1: Write the failing test**

  Build child `FetchResult` fixtures with literal attempts and a calendar containing the requested date either present, absent inside coverage, or outside coverage. Monkeypatch only `chstockdata.tradability.fetch_trading_calendar`, `is_trading_day` where needed, and `fetch_suspension_info`; assert the returned dict, calls, request status, and child metadata lists.

- [ ] **Step 2: Run the focused test to verify RED**

  Run: `.venv\Scripts\python.exe -m pytest tests/test_tradability.py -q`

  Expected: collection fails because the new public function/module does not yet exist.

### Task 2: Implement the minimal conservative derived capability

**Files:**
- Create: `src/chstockdata/tradability.py`

**Interfaces:**
- Consumes: `fetch_trading_calendar(root=..., today=...)`, `is_trading_day(calendar, curr_date)`, and `fetch_suspension_info(ticker, curr_date)`.
- Produces: `fetch_tradability(ticker: str, curr_date: str, *, root=None) -> FetchResult[dict]`.

- [ ] **Step 1: Implement child metadata composition**

  Copy child `metadata.attempts`, `metadata.providers_used`, and `metadata.limitations` into new lists, append suspension values only when suspension is actually called, and construct `FetchMetadata(capability="tradability", ...)` with `final_provider=None` unless the generic invariant can derive a sole provider. Do not import or call `record_fetch_observation`.

- [ ] **Step 2: Implement the decision table**

  Return `market_closed` with `(tradable=False, market_open=False, suspended=None)` for calendar `False`; return `calendar_unknown` with all three verdict facts `None` and a non-success supportive request status for calendar `None`; for calendar `True`, return `suspended` on a successful suspended child answer, `open_not_suspended` on suspension `normal_empty` or `suspended=False`, and `suspension_unknown` for any suspension hard failure or indeterminate answer.

- [ ] **Step 3: Run the focused test to verify GREEN**

  Run: `.venv\Scripts\python.exe -m pytest tests/test_tradability.py -q`

  Expected: all new tests pass and no `tradability:*` capability-health key is created.

### Task 3: Publish the additive API without changing the version

**Files:**
- Modify: `src/chstockdata/__init__.py`

**Interfaces:**
- Consumes: `fetch_tradability` from `chstockdata.tradability`.
- Produces: package-level import and `__all__` entry while `__version__` and `pyproject.toml` remain `0.3.0`.

- [ ] **Step 1: Add the import and `__all__` entry**

  Add `from .tradability import fetch_tradability` beside the structured fetch exports and add exactly `"fetch_tradability"` to the structured-result section of `__all__`.

- [ ] **Step 2: Re-run the focused test**

  Run: `.venv\Scripts\python.exe -m pytest tests/test_tradability.py -q`

  Expected: the public import and all derived behavior remain green.

### Task 4: Verify compatibility and stop at the requested boundary

**Files:**
- No additional production files.

- [ ] **Step 1: Run the full suite**

  Run: `.venv\Scripts\python.exe -m pytest tests/ -q`

  Expected: the existing calendar and suspension tests remain green along with the new tests.

- [ ] **Step 2: Check the final diff and version**

  Run: `git diff --check`; `Select-String -LiteralPath pyproject.toml -Pattern 'version = "0.3.0"'`; `git status --short`.

- [ ] **Step 3: Commit the scoped change**

  Run: `git add src/chstockdata/tradability.py src/chstockdata/__init__.py tests/test_tradability.py docs/superpowers/plans/2026-09-22-tradability.md`; `git commit -m "feat: add derived tradability capability"`.
