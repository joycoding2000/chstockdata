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
