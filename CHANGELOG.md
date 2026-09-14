# Changelog

All notable changes to this project are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.2.0] - 2026-09-14

Reverse-ported selected upstream-unique endpoints from
[a-stock-data](https://github.com/simonlin1212/a-stock-data) v3.7.1
(Apache-2.0), plus the upstream ticker-routing fix. Scope and evidence:
`docs/planned-upstream-ports.md`.

### Added

- **ETF options** (`etf_options.py`, Sina): `list_etf_option_contracts`,
  `get_etf_option_tquote`, `get_etf_option_greeks`, `get_etf_option_chain`
  (50ETF / 300ETF / 科创50ETF / 500ETF; T-quote + exchange-computed greeks and IV).
- **Limit-up layer** (`limit_up.py`): `get_limit_up_pool` (zt/zb/dt/yzt topic
  pools with per-stock seal fund, seal times, board stats) and
  `get_limit_up_reasons` (THS limit-up reasons, seal success rate, board type).
- **CYQ chip distribution** (`chips.py`): pure
  `chip_distribution(df)` (profit ratio / average cost / cost ranges / chip
  peak, with the upstream seeding and triangular-distribution fixes) and
  `get_chip_distribution(ticker, start, end)` assembling the turnover input
  from the optional `baostock` extra (pre-adjustment prices, suspended days
  excluded, Beijing exchange rejected before login).
- **Market-wide dragon-tiger board**: `get_daily_dragon_tiger`.
- **Board fund flow** (`board_flow.py`): `get_board_fund_flow` using the
  non-push2 `bkzj` endpoint (industry/concept/region × today/5d/10d main net
  only; four-tier breakdown / net ratio / leader fields are not available and
  are disclosed in `limitations`).
- **Investor relations** (`investor_qa.py`): `get_investor_qa` (巨潮互动易).
- **Market sentiment** (`hot_rank.py`): `get_hot_rank` (THS), `get_em_hot_rank`
  (Eastmoney popularity list, name/price hydrated via the Tencent chain),
  `get_hot_concepts` (Eastmoney concept hits).
- `a_stock._em_post`: Eastmoney POST helper sharing the same serial throttle
  lock as `_em_get` (emappdata endpoints).
- Optional `baostock` extra; `numpy` is now an explicit runtime dependency
  (used by the CYQ module).
- MCP server exposes the new functions (`get_chip_distribution` rather than
  the DataFrame-input pure function).

### Fixed

- **Ticker routing (ported from a-stock-data v3.7.1)**: explicit market
  prefix/suffix must agree with the code range; conflicting notation
  (`SH000001.SZ`), wrong-market notation (`600519.SZ`) and Shanghai index
  notation (`000016.SH`, `sh000001`) now fail loud instead of silently
  querying another instrument.
- **`5x` ETFs route to Shanghai** (`tdx_bridge.market_for_code`): previously
  `510050` etc. fell through to the Shenzhen branch, so Tencent/Sina quote
  paths silently missed.
- Rebuilt `tests/test_data_layer_live_smoke.py` (the workflow referenced a
  file that did not exist in this repository) and extended the push2
  source-scan guard to every new data-plane module.

## [0.1.0] - 2026-09-14

Initial release, extracted from TradingAgents-astock `tradingagents/dataflows/`
(see MIGRATION.md and the source repo's
`docs/releases/v0.6.0/change-requests/CR-EXTRACT-FREE-DATA-LAYER.md`).

### Included

- 17 data-vendor modules (~13K lines): `a_stock.py` core (39 public
  functions), realtime 3-source fallback chain (Tencent → mootdx → Sina),
  zombie-quote detection, Eastmoney `_em_get` throttled access, mootdx
  canary server selection with exponential-backoff negative cache,
  TDX easy-tdx isolated bridge, local vipdoc daily-bar history layer,
  northbound (SSE/SZSE) trusted history, block trades, corporate actions,
  market breadth, trading calendar, policy news (models/registry/sources),
  point-in-time financial filtering, `safe_ticker_component` ticker safety.
- 360 regression tests migrated from the source repository (all derived
  from real production incidents).
- Optional MCP server entrypoint (`chstockdata-mcp`, extra `mcp`).
- vipdoc refresh tool entrypoint (`chstockdata-refresh-vipdoc`).
