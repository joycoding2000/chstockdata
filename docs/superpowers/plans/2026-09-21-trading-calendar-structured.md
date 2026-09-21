# Trading Calendar Structured Vertical Slice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an additive structured trading-calendar route while preserving the existing `TradingCalendar`, fail-soft legacy API, local-only seams, consumers, and cache semantics.

**Architecture:** Extend `trading_calendar.py` with a single date canonicalization boundary, truthful local/mootdx/Sina adapters, a calendar-specific routing engine returning `FetchResult[TradingCalendar | None]`, and an isolated single-provider probe. Keep `load_trading_calendar()` as the only owner of `_CALENDAR_CACHE`; it calls the structured route on a miss and returns `result.data`.

**Tech Stack:** Python 3.10+, dataclasses, pandas, pytest, existing `fetch_result`, `capabilities`, `vendor_errors`, and the repository's late-import provider seams.

---

### Task 1: Establish failing structured-calendar contracts

**Files:**
- Create: `tests/test_trading_calendar_structured.py`
- Read-only reference: `tests/test_calendar_consumers.py`

- [ ] **Step 1: Write tests for the public shape and canonicalization.**

Add tests that import `fetch_trading_calendar`, `probe_trading_calendar_provider`, and `TRADING_CALENDAR_PROVIDERS`; assert provider identities are `tdx_vipdoc:index_bars`, `mootdx:index`, and `sina:index_bars`; assert unordered duplicate dates become an ascending unique tuple; assert empty, invalid-only, missing-date, and mixed-valid/invalid payloads get the required statuses and limitations.

- [ ] **Step 2: Run the new tests before implementation.**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_trading_calendar_structured.py -q
```

Expected: collection or assertion failures because the structured calendar API and canonicalization boundary do not exist yet.

- [ ] **Step 3: Add routing tests before implementation.**

Use injected adapter seams or monkeypatched internal provider calls to lock these behaviors: fresh local stops; stale local plus newer mootdx selects mootdx; stale local plus older online keeps local; stale local plus online hard failures returns stale local and degraded metadata; unavailable local falls through mootdx then Sina; all unusable providers returns structured `data=None` and legacy `None`; source labels, `providers_used`, `final_provider`, `stale`, `data_as_of`, `as_of`, and exact limitations are asserted.

- [ ] **Step 4: Add zero-network and health-isolation tests.**

Assert `local_is_trading_day()` never invokes mootdx or HTTP; assert a mootdx index failure writes only `mootdx:index` and leaves `mootdx:bars`, `mootdx:quote`, `mootdx:finance`, and `mootdx:xdxr` untouched; assert a Sina index failure leaves `sina:bars` and `sina:quote` untouched; assert a single-provider probe records only its own capability.

### Task 2: Implement canonical date and truthful provider adapters

**Files:**
- Modify: `src/chstockdata/trading_calendar.py`
- Test: `tests/test_trading_calendar_structured.py`

- [ ] **Step 1: Add capability constants and the canonicalization boundary.**

Define `TRADING_CALENDAR_CAPABILITY = "trading_calendar"` and:

```python
TRADING_CALENDAR_PROVIDERS = (
    ("tdx_vipdoc", "tdx_vipdoc:index_bars"),
    ("mootdx", "mootdx:index"),
    ("sina", "sina:index_bars"),
)
```

Implement `canonicalize_trading_days(values, *, provider) -> tuple[str, ...]` so it rejects wrong shape/missing dates/all-invalid payloads with `ValueError`, drops invalid rows only when valid dates remain, deduplicates, sorts ascending, and guarantees at least one ISO day. Keep `TradingCalendar` unchanged.

- [ ] **Step 2: Add a local adapter without changing local-only helpers.**

Create an internal local adapter that calls exactly:

```python
load_vipdoc_daily("000001", market="sh", root=root)
```

Classify missing file/configuration as `VendorNotConfiguredError`, empty/no usable rows as `VendorNoDataError`, and local read/shape errors as `ValueError`. Do not call online code from this adapter or alter `local_is_trading_day()` / `local_latest_index_bar()`.

- [ ] **Step 3: Add the mootdx adapter at the real operation boundary.**

Use the existing late import and exact call:

```python
_mootdx_call("index", symbol="000001", frequency=9, offset=2000)
```

Normalize the returned frame into date values without swallowing exceptions. Preserve tolerant mixed-valid-date behavior, classify empty as `VendorNoDataError`, classify wrong shape/all-invalid as `ValueError`, and never create `mootdx:trading_calendar`.

- [ ] **Step 4: Add the Sina adapter at the current HTTP boundary.**

Use `_source_http_get("sina", _SINA_KLINE_URL, params={"symbol": "sh000001", "scale": "240", "ma": "no", "datalen": 2000}, timeout=15, fallback_from="trading_calendar")`, call `raise_for_status()` when available, parse JSON, validate list/mapping/date shape, and classify HTTP/network exceptions separately from malformed JSON/payload shape. Empty list is `VendorNoDataError`; malformed/non-list/all-invalid is `ValueError`.

- [ ] **Step 5: Run the canonicalization and adapter tests.**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_trading_calendar_structured.py -q
```

Expected: canonicalization and adapter boundary tests pass; routing tests may still fail until Task 3.

### Task 3: Implement structured routing, probe, and legacy wrapper

**Files:**
- Modify: `src/chstockdata/trading_calendar.py`
- Modify: `src/chstockdata/__init__.py`
- Test: `tests/test_trading_calendar_structured.py`

- [ ] **Step 1: Add shared attempt/health recording helpers.**

Use `exception_to_fetch_status()` for adapter exceptions, create one `FetchAttempt` per called provider with elapsed time and record count, and pass that exact status through `fetch_status_to_health_status()` to `record_capability_health(ProviderCapability(...), ...)`. Do not record attempts for providers skipped by fresh-local stop.

- [ ] **Step 2: Add `fetch_trading_calendar(root=None, today=None)`.**

Resolve `today` with the existing `_coerce_day()` semantics. Build a local `TradingCalendar` with the existing source label and staleness calculation. Stop immediately for fresh local. For stale local, continue online and apply the newer/older/failure policies from the design. For online success, build a non-stale calendar with `as_of=today.isoformat()` and the exact source label. Return `FetchResult(data=None, metadata=...)` when no source is usable; do not raise a calendar-specific routing exception.

- [ ] **Step 3: Populate metadata exactly.**

Set `capability="trading_calendar"`, `retrieved_at` to an actual UTC fetch completion timestamp, `observed_at=None`, `data_as_of` to the final calendar `last_bar_date` or `None`, `stale` from the final payload, `partial` when canonicalization dropped invalid rows, `limitations` from the existing domain limitations plus structured route limitations, `attempts` to all real calls, `providers_used` to final payload contributors only, and `final_provider` to the sole contributor.

- [ ] **Step 4: Add `probe_trading_calendar_provider()`.**

Accept one provider and an injectable adapter or use the registered adapter. Execute only that provider, canonicalize through the same boundary, record only its capability, and return a structured result with a `TradingCalendar` payload on success or `None` on unusable output. Do not write health for unrelated providers.

- [ ] **Step 5: Convert `load_trading_calendar()` into the compatibility wrapper.**

Keep its signature unchanged. Preserve `(str(root) if root is not None else "", resolved_today.isoformat())` and `TradingCalendar | None` cache values. On a miss call `fetch_trading_calendar()`, extract `result.data`, store it when `use_cache=True`, and return it. `use_cache=False` must bypass the cache.

- [ ] **Step 6: Export the additive API.**

Import and list `fetch_trading_calendar`, `probe_trading_calendar_provider`, and `TRADING_CALENDAR_PROVIDERS` in `src/chstockdata/__init__.py`; retain `TradingCalendar`, `load_trading_calendar`, and `local_is_trading_day` availability.

- [ ] **Step 7: Run all structured-calendar tests.**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_trading_calendar_structured.py -q
```

Expected: all new structured route, probe, cache, provenance, and local-only tests pass.

### Task 4: Preserve consumers and cached OHLCV behavior

**Files:**
- Modify only if a test exposes a real compatibility defect: `src/chstockdata/a_stock.py`, `src/chstockdata/market_breadth.py`
- Test: existing `tests/test_calendar_consumers.py`, `tests/test_cached_ohlcv_structured.py`

- [ ] **Step 1: Run the locked consumer regression suite unchanged.**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_calendar_consumers.py -q
```

Expected: the existing consumer file remains unmodified and all tests pass, including holiday handling, staleness confirmation, probe-window fallback, and historical cutoff semantics.

- [ ] **Step 2: Run the cached OHLCV regression suite.**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_cached_ohlcv_structured.py -q
```

Expected: Friday/Sunday cache behavior, holiday coverage, and calendar-unavailable fallback remain green.

- [ ] **Step 3: Fix only proven compatibility defects.**

If the wrapper changes a locked behavior, preserve the consumer boundary rather than changing its tests: local-only helpers must remain zero-network; `_calendar_reference_last_bar()` must keep its request-cutoff and beyond-coverage semantics; no consumer should call the structured route directly.

### Task 5: Update public documentation and non-blocking observability

**Files:**
- Modify: `docs/architecture.md`
- Modify: `docs/provider-capability-matrix.md`
- Modify: `CHANGELOG.md`
- Modify if the existing workflow remains suitable: `tests/test_live_capability_probes.py`
- Modify if needed: `.github/workflows/live-data-gate.yml`

- [ ] **Step 1: Document the third structured vertical slice.**

Update architecture diagrams and routing sections to show calendar as the third slice, distinguish `TradingCalendar.as_of` from `FetchMetadata.data_as_of`, and state that `load_trading_calendar()` is fail-soft while `fetch_trading_calendar()` is structured.

- [ ] **Step 2: Document capability identities and provenance.**

Add `tdx_vipdoc:index_bars`, `mootdx:index`, and `sina:index_bars`; retain exact `TradingCalendar.source` labels; state that local stale is a successful observation, `providers_used` is payload contribution only, and index capability failure does not affect bars/quote/finance/xdxr.

- [ ] **Step 3: Add an Unreleased changelog entry.**

Record the additive APIs, canonical day contract, route semantics, fail-soft compatibility, unchanged version `0.3.0`, and explicit non-goals. Do not publish or bump a release version.

- [ ] **Step 4: Add non-blocking online probes only if consistent with the current live workflow.**

Use the isolated probe for mootdx and Sina and assert their individual health. Do not include local vipdoc in hosted live probes; do not make the workflow blocking.

### Task 6: Full verification and commit

**Files:**
- Verify all changed files with `git diff --check` and status.

- [ ] **Step 1: Run the full offline suite.**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/ -q
```

Record passed, failed, skipped/deselected counts and explicitly state that network-marked tests were not run by this command.

- [ ] **Step 2: Verify scope and versions.**

Run:

```powershell
git diff --check
git status --short
git diff --name-only
rg -n '__version__|version\s*=' src/chstockdata/__init__.py pyproject.toml
```

Confirm no consumer repository changes, no suspension/tradability/corporate-actions/qfq/hfq/W/M migration, no generic router, and both versions remain `0.3.0`.

- [ ] **Step 3: Commit the verified implementation.**

Use:

```powershell
git add src/chstockdata/trading_calendar.py src/chstockdata/__init__.py tests/test_trading_calendar_structured.py docs/architecture.md docs/provider-capability-matrix.md CHANGELOG.md tests/test_live_capability_probes.py .github/workflows/live-data-gate.yml
git commit -m "feat: add structured trading calendar route"
```

Include only files actually changed, then report the full commit SHA, commit message, and branch. Stop after the acceptance criteria are met.

