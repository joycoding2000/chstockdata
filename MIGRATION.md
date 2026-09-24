# Migration notes

`chstockdata` was extracted from
[TradingAgents-astock](https://github.com/joycoding2000/TradingAgents-astock)
on 2026-09-14. The extraction plan, dependency-boundary audit and acceptance
gates live in the source repository as
`docs/releases/v0.6.0/change-requests/CR-EXTRACT-FREE-DATA-LAYER.md`.

## What moved

| Source (TradingAgents-astock) | Destination (this repo) |
|---|---|
| `tradingagents/dataflows/{a_stock,utils,vendor_errors,point_in_time,tdx_bridge,vipdoc_history,northbound_data,northbound_store,block_trades,corporate_actions,market_breadth,trading_calendar,adjusted_bars,policy_news,policy_news_models,policy_news_registry,policy_news_sources}.py` | `src/chstockdata/` (same file names) |
| `tradingagents/dataflows/evidence.py` (pure envelope core) | `src/chstockdata/provenance.py` |
| `scripts/refresh_vipdoc_history.py` | `src/chstockdata/refresh_vipdoc.py` (console script) |
| 32 regression test files (360 tests) | `tests/` |

## What stayed in the source repository

LLM tool orchestration (`tool_plan*`, `prefetch_*`, `interface.py`,
`source_governor`, `quota_manager`, `evidence` capability decoration), the
US-market data path (`y_finance`, `alpha_vantage_*`, `stockstats_utils`), and
framework config. TradingAgents consumes this package via thin re-export
shims that keep `from tradingagents.dataflows.a_stock import ...` working.

## Known intentional duplication

`tests/test_data_layer_live_smoke.py` (network-marked live sentinel) exists in
both repositories on purpose: the source repo's copy validates the full
shim→package chain, this repo's copy validates the package directly.

## v0.4.1 structured API（release candidate）

The six structured entry points are additive. Existing legacy functions keep
their signatures and output envelopes; consumers may migrate one capability at
a time without replacing the legacy surface.

```python
from chstockdata import (
    fetch_realtime_quotes,
    fetch_daily_bars,
    fetch_trading_calendar,
    fetch_suspension_info,
    fetch_delisting_status,
    fetch_tradability,
)

quotes = fetch_realtime_quotes(
    ["600519"], quote_fetchers, quote_number=to_finite_number
)
bars = fetch_daily_bars("600519", "2026-01-01", "2026-09-22")
calendar = fetch_trading_calendar(today="2026-09-22")
suspension = fetch_suspension_info("600519", "2026-09-22")
delisting = fetch_delisting_status("600519")
tradability = fetch_tradability("600519", "2026-09-22")
```

`quote_fetchers` is the real `fetch_realtime_quotes` injection argument: its
values use the existing `fetcher(codes, fallback_from=...)` shape;
`to_finite_number` is the required numeric coercion callback. The other calls
above use the actual public signatures and return `FetchResult` values.

For a result, consumers should inspect:

- `metadata.final_status`: attempt-derived provider/routing conclusion;
- `metadata.request_status`: request-level result used for branching;
- `metadata.outcome_status`: optional request-level override, otherwise `None`;
- `metadata.providers_used`: providers that contributed the payload;
- `metadata.limitations`: coverage, staleness, partial-data, and validation caveats.

Cache-only results can intentionally expose `attempts=[]`,
`final_status="skipped"`, and `request_status="success"` or
`"normal_empty"`. Use `request_status` rather than mechanically treating
`succeeded=False` as unusable data. `tradable=True` is only a verdict supported
by the covered calendar, delisting-date, and suspension facts; it is not a
complete IPO or listing-lifecycle eligibility claim.

The v0.4.1 release candidate does not add a `GenericFallbackRouter` and does
not complete the `a_stock.py` decomposition. The candidate package version is
`0.4.1`; publication requires separate RH3-B Owner authorization.
