# v0.4.0 Phase 3 — Trading Calendar Audit

## Audited legacy behavior

The current route before Phase 3 was:

```text
vipdoc `load_vipdoc_daily("000001", market="sh")`
    -> mootdx `index(symbol="000001", frequency=9, offset=2000)`
    -> Sina `sh000001, scale=240, ma=no, datalen=2000`
```

The explicit Shanghai market argument is required: six-digit `000001` without
`market="sh"` can resolve to `sz000001`. Local data is zero-network.
Local staleness is `(today - local_last_bar).days >
vipdoc_history_max_staleness_days`; `today` is only the comparison date.

The legacy process memo is keyed by `(str(root) or "", resolved_today)` and
stores `TradingCalendar | None`. Consumers are market breadth, vipdoc
staleness confirmation, the mootdx probe-window decision, cached OHLCV
market-session freshness, and `_calendar_reference_last_bar()`. They continue
to use `load_trading_calendar()`, `local_is_trading_day()`, and
`latest_trading_day_on_or_before()` with their existing fallbacks.

## Structured route

```text
tdx_vipdoc:index_bars -> mootdx:index -> sina:index_bars
        -> canonicalize_trading_days()
        -> FetchResult[TradingCalendar | None]
        -> load_trading_calendar() compatibility wrapper
```

The structured layer reuses `TradingCalendar`; it does not define a second
calendar payload model. Each real provider call creates one `FetchAttempt` and
one health observation at the same operation identity. The local adapter keeps
the explicit `market="sh"` address. The online adapters keep the existing
mootdx request and Sina endpoint parameters.

## Status and provenance

- `success` means a provider returned at least one canonical day. A stale
  local calendar is still a successful observation.
- `normal_empty` means a provider answered with no rows.
- `not_configured` means the local package/file is unavailable.
- `failed_structure` means an unreadable or malformed payload, including an
  invalid-only date payload.
- Mixed valid/invalid dates preserve the valid canonical set and expose
  candidate quality. `metadata.partial=True` and
  `invalid_calendar_dates_dropped` are exposed only when that candidate
  contributes the final calendar payload; discarded fallback candidates do not
  contaminate the result. With no final payload, `partial=False`.
- `failed_network` means an online transport/HTTP failure.
- `providers_used` lists only providers contributing to the final calendar;
  `attempts` includes all providers actually called.
- `TradingCalendar.source` remains exactly `vipdoc_sh000001`,
  `mootdx_sh000001`, or `sina_sh000001`.
- `TradingCalendar.as_of` is the staleness evaluation date;
  `FetchMetadata.data_as_of` is the final calendar's actual last bar date;
  `observed_at` is not fabricated.

## Routing cases

- Fresh local: return local and stop before online calls.
- Stale local plus newer/equal mootdx or Sina: online calendar wins; local
  success attempt remains visible but is not in `providers_used`.
- Stale local plus older online: preserve stale local and the existing
  older-online limitation.
- Stale local plus online hard failures: preserve stale local and mark the
  structured result degraded.
- No local: mootdx then Sina; a hard failure followed by a successful fallback
  is degraded, while local `not_configured` alone is not.
- All providers unusable: structured `data=None`, complete attempts, no routing
  exception; legacy `load_trading_calendar()` returns `None`.

The local single-provider probe applies the same staleness calculation and
limitation as the route. A stale local probe is still a `success` attempt and
health observation; staleness is a payload data-quality attribute, not a
provider failure. Online probes keep `stale=False` without a new freshness gate.

## Compatibility boundary

`load_trading_calendar()` retains its signature and cache value type. The
structured API performs a real route and does not read the legacy memo.
`local_is_trading_day()` and `local_latest_index_bar()` remain local-only and
never call the structured online route. No consumer repository is changed, and
the package versions remain `0.3.0`.
