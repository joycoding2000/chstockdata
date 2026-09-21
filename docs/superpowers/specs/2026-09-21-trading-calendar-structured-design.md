# Trading Calendar Structured Vertical Slice Design

**Date:** 2026-09-21  
**Scope:** v0.4.0 development, Phase 3 only

## Audit baseline

The current implementation is in `src/chstockdata/trading_calendar.py` and already
owns the public `TradingCalendar` dataclass. Its route is:

```text
load_vipdoc_daily("000001", market="sh", root=root)
    -> _mootdx_call("index", symbol="000001", frequency=9, offset=2000)
    -> Sina sh000001, scale=240, ma=no, datalen=2000
```

The local helper explicitly passes `market="sh"`; removing it would allow
`000001` to resolve to `sz000001`. Local data is read without network access.
Local staleness is calculated as `(today - local_last_bar).days >
vipdoc_history_max_staleness_days`; `today` never extends coverage. A fresh local
calendar stops the route. A stale local calendar permits online fallback, but is
kept when the online last bar is older or all online providers fail. If no source
is usable, the legacy function returns `None`.

The process memo is `_CALENDAR_CACHE[(str(root) or "", resolved_today.isoformat())]`
and stores `TradingCalendar | None`. Current consumers are market breadth,
vipdoc staleness confirmation, the mootdx probe-window decision, cached OHLCV
market-session freshness, and `a_stock._calendar_reference_last_bar()`.

## Selected architecture

Keep `TradingCalendar` as the only calendar domain payload. Add the generic
structured types already used by quote and daily-bars routes:

```text
provider adapters
    -> canonicalize_trading_days()
    -> fetch_trading_calendar() -> FetchResult[TradingCalendar | None]
    -> load_trading_calendar() compatibility wrapper
```

The calendar module owns the route because its policy is calendar-specific. It
does not introduce `TradingCalendarResult`, `CanonicalCalendar`, or a generic
fallback router.

Provider capability identity is operation-level and remains isolated:

```python
TRADING_CALENDAR_PROVIDERS = (
    ("tdx_vipdoc", "tdx_vipdoc:index_bars"),
    ("mootdx", "mootdx:index"),
    ("sina", "sina:index_bars"),
)
```

The existing payload source labels remain exactly `vipdoc_sh000001`,
`mootdx_sh000001`, and `sina_sh000001`.

## Provider boundary and classification

Each adapter returns a usable sequence of dates or raises a typed/vendor or
shape exception. The route records exactly one `FetchAttempt` and one health
observation per provider actually called. It never calls a helper that has
already converted an exception to `None` and then guesses the status.

- local missing package/file or an explicitly unavailable local source:
  `not_configured`;
- local file exists but contains no usable rows: `normal_empty`;
- unreadable/malformed provider payload or all dates invalid:
  `failed_structure`;
- mootdx transport failure: `failed_network`;
- Sina HTTP/network failure: `failed_network`;
- valid provider response with no rows: `normal_empty`;
- a valid row set is `success`, including a stale local observation.

The three providers pass through one canonicalization boundary. A success
payload is a tuple of unique, ISO `YYYY-MM-DD` strings in ascending order with
at least one valid day. Invalid rows are dropped compatibly when valid rows
remain; the result records a limitation/partial indication when the boundary
can observe that loss. An all-invalid payload is `failed_structure`, a truly
empty payload is `normal_empty`, and a missing date field or wrong payload shape
is `failed_structure`.

## Routing policy

1. Fresh local success returns immediately; mootdx and Sina produce no attempt.
2. Stale local success continues online. If online data is at least as new as
   local, it becomes the final calendar and the online provider contributes the
   payload. The local success attempt remains visible, but `providers_used` is
   only the online provider.
3. If online data is older than local, the stale local payload remains final and
   keeps the existing limitation `在线回落返回的日线不新于本地包，保留本地（陈旧）日历`.
4. If both online providers hard-fail, the stale local payload remains final,
   `metadata.stale=True`, and `metadata.degraded=True`, with the existing
   stale-online-failure limitation.
5. If local is unavailable/empty, mootdx then Sina are tried. A hard failure
   followed by a later success produces a degraded structured result; local
   `not_configured` alone does not degrade it.
6. If no provider produces a calendar, the structured result has `data=None`
   and complete attempts; it does not raise a calendar routing exception. The
   legacy wrapper extracts `data` and therefore returns `None`.

`providers_used` lists only payload contributors. `final_provider` is the sole
contributor when there is one. `metadata.data_as_of` is the final calendar's
`last_bar_date`; `metadata.retrieved_at` is the current fetch time;
`observed_at` stays `None`. `TradingCalendar.as_of` remains the staleness
evaluation date.

## Compatibility and probes

`load_trading_calendar(root=None, today=None, use_cache=True)` keeps its exact
signature and cache key/value semantics. Cache hits do not pretend to be fresh
structured observations; `fetch_trading_calendar()` performs a real route and
does not read `_CALENDAR_CACHE`. `use_cache=False` always calls the new route.
`local_is_trading_day()` and `local_latest_index_bar()` remain local-only and do
not call the structured route.

`probe_trading_calendar_provider()` executes exactly one adapter and updates
only that provider capability. It supports mootdx and Sina (and may support the
local adapter for deterministic tests); it never records unrelated providers as
`not_configured`. The existing non-blocking live capability workflow may add
the two online calendar probes.

## Verification

Add unit tests for canonicalization, all routing branches, provenance/health
isolation, explicit Shanghai local addressing, cache semantics, and single
provider probes. Keep `tests/test_calendar_consumers.py` unchanged. Run its
targeted tests, the new structured-calendar tests, cached OHLCV regressions,
then the full offline suite. Network-marked live probes are reported separately
and are not run as part of the offline acceptance gate.

## Explicit non-goals

This slice does not migrate suspension/tradability, corporate actions,
qfq/hfq/W/M, consumer repositories, or a generic fallback router, and does not
change either package version from `0.3.0` or publish `v0.4.0`.

