# chstockdata

Free China A-share market data toolkit — direct HTTP/TCP access to public
quote vendors, **no API keys, no mandatory third-party market-data SDK in
the core path** (akshare-free by design). Optional integrations are
available for specific capabilities: `[mootdx]` unlocks the TCP K-line
primary source, `[baostock]` historical turnover for CYQ chips.
Battle-tested in production by
[TradingAgents-astock](https://github.com/joycoding2000/TradingAgents-astock).

```bash
pip install chstockdata          # core (pandas/requests only)
pip install "chstockdata[mootdx]"    # + mootdx TCP K-line source (optional)
pip install "chstockdata[baostock]"  # + historical turnover for CYQ chips (optional)
```

```python
from chstockdata import get_stock_data, get_realtime_snapshot, resolve_ticker

resolve_ticker("贵州茅台")            # -> "600519" (Chinese name -> 6-digit code)
df = get_stock_data("600519", 365)    # daily OHLCV, vipdoc/mootdx/Sina chain
get_realtime_snapshot("600519")       # realtime quote, Tencent -> mootdx -> Sina
```

## Structured API（v0.4.0 development）

The structured surface is additive and returns `FetchResult` objects. The
quote route keeps its provider functions injectable; `quote_fetchers` below is
a mapping whose values accept the existing `fetcher(codes, fallback_from=...)`
shape, and `to_finite_number` is the caller's numeric coercion helper.

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

Consumer-facing status guide:

| Field | Meaning |
|---|---|
| `metadata.final_status` | Attempt-derived provider/routing conclusion. |
| `metadata.request_status` | Request-level result consumers should branch on. |
| `metadata.outcome_status` | Optional engine-declared request override; otherwise `None`. |
| `metadata.providers_used` | Providers that actually contributed the returned payload. |
| `metadata.limitations` | Coverage, staleness, partial-data, or validation caveats. |

Cache-only results intentionally have `attempts=[]` and
`final_status="skipped"`, while `request_status` may be
`"success"` or `"normal_empty"`. Do not mechanically treat
`succeeded=False` or `final_status="skipped"` as unusable cache data; use
`request_status` for the request decision. A `tradable=True` result only means
the currently covered calendar, delisting-date, and suspension facts support
that verdict; it does not promise complete IPO or listing-lifecycle
eligibility.

The public surface combines legacy callables, structured result types,
constants, and compatibility exports; `__all__` is not a count of functions.
It covers K-lines, realtime quotes, fundamentals / three financial
statements, valuation history, margin trading, dragon-tiger board (per-stock
seats and whole-market daily), lockup expiry, northbound flow, fund flow, board
fund flow, industry comparison, concept blocks, block trades, market breadth,
limit-up / failed-board / limit-down / previous-day limit-up pools, CYQ chip
distribution, ETF option chains (T-quote + greeks + IV), investor Q&A (互动易),
hot rank / popularity rank / concept hits, insider transactions, shareholder
pledge / buyback, corporate actions, earnings forecast, research reports, news
wires, policy news, macro indicators, trading calendar, delisting / suspension
info, and more. See `chstockdata/__init__.py` for the full export list. The
package remains `0.4.0 development`; its compatibility version is still
`0.3.0` and this README does not announce a release.

## Data sources

| Source | Protocol | Data |
|---|---|---|
| mootdx | TCP 7709 | OHLCV K-lines, realtime snapshots, financial snapshots, F10 text |
| TDX official after-market archive | HTTP (`data.tdx.com.cn/vipdoc`) | Full SH/SZ/BJ daily-bar archive → local vipdoc tree (primary history source) |
| Tencent Finance | HTTP (`qt.gtimg.cn`) | Realtime quotes (primary), PE/PB/market cap/turnover |
| easy-tdx (isolated process) | TCP 7709 | L1 fund-flow reconstruction, TDX industry/concept board rankings |
| Eastmoney datacenter / F10 / emappdata / bkzj | HTTP | Dragon-tiger (per-stock + market-wide), lockup, holders, concept blocks, news, announcements, limit-up pools (push2ex), board fund flow, popularity rank, concept hits |
| Sina Finance | HTTP | Realtime fallback, K-line fallback, daily fund flow, financial statements, ETF option contracts / T-quote / greeks + IV |
| baostock (optional extra) | TCP | Historical daily turnover + ST/suspension flags for CYQ chip distribution (no Beijing exchange) |
| 同花顺 10jqka | HTTP | Consensus EPS, hot stocks, limit-up reasons, hot rank |
| 财联社 cls.cn | HTTP | Global news wire |
| SSE / SZSE official | HTTP | Northbound daily turnover (trusted), delisting list |
| 巨潮 cninfo | HTTP | Investor Q&A (互动易) |

All Eastmoney requests go through a module-level serial throttle
(`EM_MIN_INTERVAL`, default 1.0s) with jitter and a shared keep-alive session
— do not bypass it, do not fan out concurrent full-market scans. `push2` /
`push2his` are deliberately not used (see `tests/test_astock_push2_source_scan.py`).

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
(Apache-2.0, itself a fork of [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents)).
Starting with 0.2.0, selected upstream-unique endpoints of
[a-stock-data](https://github.com/simonlin1212/a-stock-data) (Apache-2.0) were
reverse-ported: ETF options (contracts / T-quote / greeks + IV), limit-up pools
(including the previous-day pool and THS limit-up reasons), CYQ chip
distribution, market-wide dragon-tiger board, board fund flow, investor Q&A
(互动易), hot rank / popularity rank / concept hits, and the upstream ticker
routing fix (market identifier conflicts fail loud; `5x` ETFs route to
Shanghai).

This package is still **not** a full superset of a-stock-data. Deliberately not
included: intraday anomaly pools (product hard boundary in the source project),
Shenwan industry history, minute/tick order flow, and any `push2`/`push2his`
dependency (board fund flow uses the non-push2 `bkzj` endpoint with a reduced
field set — no four-tier breakdown). See MIGRATION.md and
`docs/planned-upstream-ports.md`.

## License

Apache-2.0 — see [LICENSE](LICENSE) and [NOTICE](NOTICE).
