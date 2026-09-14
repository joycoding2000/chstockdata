# Changelog

All notable changes to this project are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

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
