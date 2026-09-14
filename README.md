# chstockdata

Free China A-share market data toolkit — direct HTTP/TCP access to public
quote vendors, **no API keys, no third-party data SDKs** (akshare-free by
design), battle-tested in production by
[TradingAgents-astock](https://github.com/joycoding2000/TradingAgents-astock).

```bash
pip install chstockdata          # core (pandas/requests only)
pip install "chstockdata[mootdx]"  # + mootdx TCP K-line source (optional)
```

```python
from chstockdata import get_stock_data, get_realtime_snapshot, resolve_ticker

resolve_ticker("贵州茅台")            # -> "600519" (Chinese name -> 6-digit code)
df = get_stock_data("600519", 365)    # daily OHLCV, vipdoc/mootdx/Sina chain
get_realtime_snapshot("600519")       # realtime quote, Tencent -> mootdx -> Sina
```

39 public functions: K-lines, realtime quotes, fundamentals / three financial
statements, valuation history, margin trading, dragon-tiger board, lockup
expiry, northbound flow, fund flow, industry comparison, concept blocks,
block trades, market breadth, insider transactions, shareholder pledge /
buyback, corporate actions, earnings forecast, research reports, news wires,
policy news, trading calendar, delisting / suspension info, macro indicators,
and more. See `chstockdata/__init__.py` for the full export list.

## Data sources

| Source | Protocol | Data |
|---|---|---|
| mootdx | TCP 7709 | OHLCV K-lines, realtime snapshots, financial snapshots, F10 text |
| TDX official after-market archive | HTTP (`data.tdx.com.cn/vipdoc`) | Full SH/SZ/BJ daily-bar archive → local vipdoc tree (primary history source) |
| Tencent Finance | HTTP (`qt.gtimg.cn`) | Realtime quotes (primary), PE/PB/market cap/turnover |
| easy-tdx (isolated process) | TCP 7709 | L1 fund-flow reconstruction, TDX industry/concept board rankings |
| Eastmoney datacenter / F10 | HTTP | Dragon-tiger, lockup, holders, concept blocks, news, announcements |
| Sina Finance | HTTP | Realtime fallback, K-line fallback, daily fund flow, financial statements |
| 同花顺 10jqka | HTTP | Consensus EPS, hot stocks |
| 财联社 cls.cn | HTTP | Global news wire |
| SSE / SZSE official | HTTP | Northbound daily turnover (trusted), delisting list |

All Eastmoney requests go through a module-level serial throttle
(`EM_MIN_INTERVAL`, default 1.0s) with jitter and a shared keep-alive session
— do not bypass it, do not fan out concurrent full-market scans.

## Hardening carried over from production

This package is not a scraper starter kit; it is an extraction of a data layer
that survived months of live A-share analysis runs:

- **Realtime fallback chain** Tencent → mootdx → Sina, with zombie-quote
  detection (zero-amount + price == prev-close) so suspended/legacy tickers
  cannot silently poison valuations.
- **mootdx canary server selection**: TCP reachability is not enough — every
  candidate must serve one real K-line bar before adoption; dead pools get an
  exponential-backoff negative cache (5min → 6h, immediate 6h outside trading
  hours).
- **Local vipdoc history layer**: after the official TDX archive is refreshed
  (via `chstockdata-refresh-vipdoc`), historical daily bars are read from disk
  with zero network and never trigger full server-pool probing.
- **Point-in-time filtering** for historical analyses (financial records are
  clipped to the analysis date).
- **Known pitfall fixes verified against live data**: Tencent total/float
  market-cap fields swapped, static-PE wrong slot, BJ-exchange 920-prefix
  routing, Eastmoney lockup column renames, block-trade premium-ratio unit
  (decimal → percent), northbound SSE holiday `result:[null]` handling, and
  more — each guarded by regression tests ported from the incidents.

## Configuration

Zero-config works out of the box. Optional overrides, in priority order:

```python
from chstockdata import configure
configure(cache_dir="...", vipdoc_dir="...", vipdoc_enabled=True,
          vipdoc_max_staleness_days=5, northbound_store_path="...")
```

Environment variables (both prefixes accepted): `CHSTOCKDATA_CACHE_DIR`,
`CHSTOCKDATA_VIPDOC_HISTORY_DIR`, ... or the legacy
`TRADINGAGENTS_VIPDOC_HISTORY_*` / `TRADINGAGENTS_DATA_CACHE_DIR` names.
Tuning knobs: `EM_MIN_INTERVAL` (Eastmoney throttle seconds),
`TDX_MIN_INTERVAL`, `TDX_TOOL_PROBE_BUDGET_SECONDS`,
`EASY_TDX_PYTHON` (path to an isolated venv python with `easy-tdx==1.20.6`).

## MCP server (for AI agents)

```bash
pip install "chstockdata[mcp]"
chstockdata-mcp
```

Then register in any MCP client (Claude Code, etc.):

```json
{ "mcpServers": { "chstockdata": { "command": "chstockdata-mcp" } } }
```

## Risk & usage notes

- All endpoints are **public, unofficial interfaces** of the respective
  vendors. Rate-limit thresholds cited anywhere in the docs are community
  observations, **not vendor guarantees**; endpoints can break or change at
  any time without notice.
- Built-in throttling must be kept as-is. For heavy or commercial workloads
  use official paid feeds (Eastmoney Choice, exchange data services).
- Data is provided for research/educational purposes, as-is, with no
  warranty of accuracy or fitness for trading decisions.

## Relationship to upstream projects

Extracted from [TradingAgents-astock](https://github.com/joycoding2000/TradingAgents-astock)
(Apache-2.0, itself a fork of [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents)),
with selected correctness fixes ported from
[a-stock-data](https://github.com/simonlin1212/a-stock-data) (Apache-2.0).
This package is **not** a superset of a-stock-data: it does not include ETF
option greeks/IV, limit-up/down pools, or CYQ chip distribution. See
MIGRATION.md.

## License

Apache-2.0 — see [LICENSE](LICENSE) and [NOTICE](NOTICE).
