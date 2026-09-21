# Changelog

All notable changes to this project are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased] — 0.4.0 development

Consumer compatibility baseline remains **0.3.0** (commit `143eb5a`);
nothing below changes the public API. Scope and rationale:
`docs/architecture.md`, `docs/provider-capability-matrix.md`.

### Phase 1.1 — Structured Core Stabilization (hardening round)

No new capabilities; fixes the semantic gaps found in Phase 1 before
extending to daily bars.

#### Fixed

- **mootdx operational capability isolation** (`a_stock._get_mootdx_client`):
  Phase 1 recorded capability-specific health but the runtime gate was still
  provider-global — a full-table bars-readiness canary failure wrote the
  global negative cache, which fast-failed `finance`/`xdxr`/`quote` calls
  that were never attempted. Readiness is now layered: transport-level
  failure (no candidate can even construct a client) still gates all
  capabilities, while a bars-canary-derived negative cache only constrains
  bars requests; other capabilities may run a **bounded bypass** selection
  (factory-only over the already-known reachable candidates — no TCP
  re-scan, no canary) and validate themselves via their real call. All
  historical protections are preserved (tool-context probe budget, disk
  negative cache + backoff, bounded scan, candidate reselection, BESTIP
  preservation, call lock/min-interval). The persisted negative cache now
  records the verdict layer (`transport_ok`); legacy files without the
  field are treated conservatively (transport-level, as before).
- **Live capability probe pollution**: single-provider probes ran through
  the full routing chain, recording `not_configured` for un-injected
  providers and overwriting other capabilities' health. The new
  `quote_chain.probe_quote_provider` owns a single-provider execution path:
  probing one provider updates only its own capability health
  (`tests/test_live_capability_probes.py` now uses it).
- **FetchAttempt ↔ CapabilityHealth status consistency**: one provider
  observation could yield `FetchAttempt=normal_empty` while
  `CapabilityHealth=failed` (e.g. `VendorNoDataError`). A single mapping,
  `capabilities.fetch_status_to_health_status`, is now the only place the
  two vocabularies meet; `record_capability_health` accepts either
  vocabulary.
- **FetchMetadata multi-provider semantics**: per-code fallback can mix
  sources, but `final_provider` was picked from the first result, falsely
  claiming one provider owned the whole result. New `providers_used` field
  lists every contributing provider (first-contribution order);
  `final_provider` is the sole provider only when exactly one contributed,
  else `None` (invariant enforced at construction; both fields serialize).
- **Generic `normal_empty` no longer encodes routing policy**:
  `FetchAttempt.is_terminal()` (which asserted "no fallback needed") was
  removed — attempts describe facts (`is_success` / `is_failure`), and
  whether an empty result ends a route is capability-policy owned by each
  routing engine. `FetchMetadata.final_status` now derives the whole
  request's outcome by priority (any success → success; else first hard
  failure; else normal-empty; else not-configured; else skipped) instead of
  mechanically reading the last attempt.
- **Health clock seam** (`capabilities.set_health_clock`): the seam existed
  but `record_capability_health` ignored it (`datetime.now`). It now drives
  `observed_at` via `datetime.fromtimestamp(_clock(), ...)` so tests are
  deterministic.
- Module docstring: capability ids described as "dotted identifiers" while
  the contract is colon-separated `provider:capability` — wording fixed,
  id contract unchanged.

### Phase 1 — capability health + structured result foundation

#### Added

- **Capability-specific provider health** (`capabilities.py`): health is
  now observed per `provider + capability` (`mootdx:bars`,
  `mootdx:finance`, `tencent:quote`, ...). One capability failing never
  marks the other capabilities of the same provider unhealthy (isolation
  regression tests). `a_stock._mootdx_call` records per-method
  capability health; `_tdx_client_works` (bars canary) is re-scoped to
  server-selection connectivity verification only.
- **Generic structured result foundation** (`fetch_result.py`):
  consumer-neutral `FetchAttempt` / `FetchMetadata` / `FetchResult[T]`
  with `success` / `normal_empty` / `failed_network` /
  `failed_rate_limit` / `failed_structure` / `not_configured` / `skipped`
  statuses. `retrieved_at` (when we fetched) is kept separate from
  `observed_at` / `data_as_of` (when the data is valid). Naming is
  deliberately distinct from the TradingAgents-compatibility
  `provenance.ProviderAttempt` / `EvidenceEnvelope`, which stay unchanged.
- **Structured realtime-quote chain** (`quote_chain.py`) — first vertical
  slice: `fetch_realtime_quotes()` runs the Tencent → mootdx → Sina chain
  on the structured core, recording per-provider attempts (provider
  health) plus the derived routing outcome (routing health), while
  `a_stock._get_realtime_quotes` becomes a compatibility wrapper with an
  unchanged legacy contract.
- **Live gate split**: `tests/test_data_layer_live_smoke.py` remains the
  routing-chain gate; the new `tests/test_live_capability_probes.py`
  reports each provider capability separately (non-blocking), so a
  mootdx capability outage can no longer hide behind a successful Sina
  fallback.
- Docs: `docs/architecture.md` (providers / capabilities / routing /
  structured result / legacy compatibility / consumer boundary) and
  `docs/provider-capability-matrix.md`.

### Fixed

- **`configure()` value validation + atomic commit**: non-boolean values
  for boolean settings (e.g. `vipdoc_enabled="false"`) are rejected
  instead of being accepted as truthy; all settings are validated before
  any is committed, so an invalid call cannot partially pollute the
  global config. Unknown-key validation is unchanged.
- **Name-map warmup retry**: a failed first `_build_name_code_map()`
  warmup no longer permanently disables retries for the process
  lifetime (the one-shot flag is reset on failure; idempotency on
  success is unchanged).
- README / package metadata wording: "no third-party data SDKs" corrected
  to "no mandatory third-party market-data SDK in the core path; optional
  integrations are available for specific capabilities".

## [0.3.0] - 2026-09-17

### Added

- Added ETF/fund distribution actions from Eastmoney F10 (`FHSP` + `FHGG`),
  including announcement/ex-dividend/record/payment dates and normalized
  per-10-share cash amounts.
- Added bounded pagination and per-date in-process caching for the market-wide
  suspension snapshot.
- Added raw file-derived `pre_close` to local VIPDOC daily frames.

## [0.2.1] - 2026-09-15

Financial report-period alignment (handover from TradingAgents-Astock
P2-5): the Free data plane understated growth rates by 100× and the mootdx
F10 snapshot had no report-period label. Evidence and probe tables:
`docs/pending-financial-period-alignment.md` (appendix). Label names and
value formats consumed downstream (`营收同比增长率`, `净利润同比增长率`,
`report_period_end`, `announcement_date`) are unchanged.

### Fixed

- **Sina `item_tongbi` unit normalization** (`a_stock._get_financial_report_sina`):
  the vendor field is a decimal fraction (0.10791 = +10.79%), but was stored
  verbatim and rendered as a percentage (0.11%) — a 100× understatement that
  produced the P2-5 contradictory readings. `{项目}同比` columns are now
  normalized to percent at the parse boundary (behavior change for raw
  statement CSV consumers).
- **Self-computed same-period YoY** (`get_free_financial_indicators`):
  `营收同比增长率` / `净利润同比增长率` are derived from raw `item_value`
  against the prior-year same period (`report_period − 1 year`; denominator
  `|prior|`, matching Tushare `or_yoy` / `netprofit_yoy` handling of negative
  bases). Revenue uses `营业收入`; net profit prefers `归属于母公司所有者的净利润`
  (official announcement caliber). The normalized `item_tongbi` column is only
  a fallback when the prior-year row is missing. 300452 2026H1 now reads
  +10.79% / +3.39% (was +0.11% / +0.04%).
- **YoY basis disclosure (T3)**: growth lines carry their base period and
  cumulative semantics, e.g. `- 营收同比增长率: 10.79%（2026H1累计，较2025H1）`;
  when unavailable the same basis is still disclosed.

### Added

- **F10 snapshot report-period labeling** (`get_fundamentals`): TDX F10
  finance carries `updated_date` (announcement/update date, live-verified
  600519 = 20260815 = 2026 interim announcement) and `ipo_date`, but no
  report-period-end field. The snapshot now emits a report-period reference
  resolved from the latest Sina statement period (explicitly disclosed as a
  reference, not snapshot-native), cross-checked against `updated_date`, plus
  the `updated_date` / IPO date. If the reference cannot be fetched, the
  output states 报告期不可用 instead of printing undated absolute amounts.
- `tests/test_astock_financial_yoy_alignment.py`: offline fixture cases for
  self-computed YoY, negative base, normalized fallback, unavailable basis
  disclosure, `item_tongbi` conversion, and F10 period labeling.

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
