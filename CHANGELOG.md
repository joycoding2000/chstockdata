# Changelog

All notable changes to this project are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased] — 0.4.0 development

Consumer compatibility baseline remains **0.3.0** (commit `143eb5a`);
nothing below changes the public API. Scope and rationale:
`docs/architecture.md`, `docs/provider-capability-matrix.md`.

### Phase 2.1.1 — Supplement Canonicalization Closure (hotfix)

#### Fixed

- **The Sina tail supplement no longer bypasses the canonicalization
  boundary** (`daily_bars._supplement_with_sina`): Phase 2.1 enforced
  canonical validation on base routing and probes, but a supplement frame
  that returned non-empty rows was recorded as `success` (attempt + health)
  and merged *before* any validation — a malformed supplement could leak
  NaN/missing-column rows into the final payload while claiming a clean
  Sina success.  The supplement now passes the SAME
  `canonicalize_daily_bars_frame()` gate before any success is recorded:
  a malformed supplement is a `failed_structure` attempt (health
  `failed`), is never merged, the base payload stands untouched, routing
  stays `succeeded` with `degraded=True`, `providers_used` excludes Sina
  ("received a response" ≠ "contributed canonical payload"), the legacy
  `# Data source` label stays base-only, and `volume_unit` keeps
  resolving from the base contributors only.
- **Payload type guard in the canonicalizer**: a provider payload that is
  not a `pd.DataFrame` (list/dict/tuple) now raises a clear `ValueError`
  (`"<provider> bars payload must be a pandas DataFrame"`) classified as
  `failed_structure` — previously an `AttributeError` from such payloads
  fell through the shared classification into `failed_network`,
  misreporting a shape bug as a transport failure.  The guard automatically
  covers base routing, probes, and the supplement through the single
  shared boundary.

### Phase 2.1 — Daily Bars Contract Stabilization

#### Fixed

- **Canonical schema is now enforced, not just declared**
  (`daily_bars.canonicalize_daily_bars_frame`): every provider frame passes
  a single canonicalization boundary — shared by the routing chain AND the
  single-provider probe — before it may be recorded as `success`.  A
  non-empty frame missing a required column (`Date/Open/High/Low/Close/
  Volume`), carrying an unparseable `Date`, or carrying a non-null
  non-numeric required field is a `failed_structure` attempt (health
  `failed`) and the chain falls through to the next provider — malformed
  payloads can no longer masquerade as usable data.  Valid numeric strings
  (`"10.25"`) are converted; duplicate business dates are deduplicated
  keep-last deterministically in the provider's native row order (no
  re-sorting).  This also exposed and fixed a latent test issue: the legacy
  vipdoc-chain test fixture returned a non-canonical frame shape that had
  been silently masked by real Sina HTTP fallback (test network dependency
  removed).
- **`providers_used` is now truthful about supplement contributions**: the
  Sina tail supplement contributes rows whenever it returns any (its
  keep-last rows take over overlapping dates), so it is listed in
  `providers_used` even when it does not advance the last bar date —
  previously only the "advanced" case was recorded, under-reporting real
  mixed-source payloads.  `final_provider` stays `None` for mixed payloads
  and dedupes when the base provider IS Sina.
- **Legacy `# Data source` label decoupled from structured provenance**:
  the `+ sina HTTP supplement` suffix rule (advance-only) is now keyed off
  the explicit `sina_supplement_advanced_end` limitation sentinel instead
  of being re-derived from `providers_used`; an overlap-only contribution
  is recorded as `sina_supplement_overlap_only`.  Structured truth and
  legacy wording no longer contaminate each other.
- **Request outcome is explicit, not guessed**: `FetchMetadata` gains a
  generic, consumer-neutral `outcome_status` (explicit request-level
  override; `None` keeps the attempt-derived `final_status` — quote and
  every other existing chain are behaviorally unchanged) plus the derived
  `request_status`; `FetchResult.is_normal_empty` resolves through
  `request_status` and both fields are serialized.  When providers
  succeeded but the requested window filtered all bars away,
  `fetch_daily_bars` declares `outcome_status="normal_empty"` so consumers
  never have to infer emptiness from a bare dataframe or limitation
  strings.

#### Added

- **Volume unit semantics without guessing**: the resolved unit travels on
  the returned frame (`frame.attrs["volume_unit"]`) and as a
  `volume_unit:<value>` limitation — `shares` for `tdx_vipdoc`/`sina`,
  `provider_native_unknown` for `mootdx` (TDX wire `vol` unit is NOT
  verified; requires a reachable TDX TCP environment — no ×100/÷100
  scaling is introduced), `mixed_provider_native` when contributing
  providers carry different unit classes.
- **pre_close merge regression**: a Sina row that takes over an overlapped
  date carries no `pre_close` (NaN) — it never inherits the vipdoc value
  while masquerading as Sina data; non-overlapped vipdoc rows keep theirs.

### Phase 2 — Daily Bars Structured Vertical Slice

#### Added

- **`chstockdata.daily_bars`** — the raw/D historical daily-bars fallback
  chain (local TDX vipdoc package → mootdx TCP → Sina HTTP) is now the
  second real data path built on the structured core
  (`FetchAttempt` / `FetchMetadata` / `FetchResult[pd.DataFrame]` /
  `ProviderCapability` + capability health).  `fetch_daily_bars()` is the
  single authoritative provider orchestration for daily bars; additive
  public export (`DAILY_BAR_PROVIDERS`, `fetch_daily_bars`,
  `probe_daily_bars_provider`).
- **Provider capability ids for bars**: `tdx_vipdoc:daily_bars`,
  `mootdx:bars`, `sina:bars` — every real provider call produces a
  `FetchAttempt` and one capability-health observation through the single
  `fetch_status_to_health_status` mapping.  `mootdx:bars` reuses the
  Phase 1.1/1.1.1 readiness semantics unchanged (bars readiness canary,
  negative-cache tiering, bounded bypass isolation for finance/xdxr).
- **Local-source status semantics for `tdx_vipdoc`**: configuration-disabled
  or missing package/file → `not_configured`; unreadable file →
  `failed_structure`; empty requested window or staleness-policy rejection
  (`vipdoc_history_max_staleness_days`, DEC-P1-27 calendar confirmation
  preserved) → `normal_empty`.  No network semantics forced onto the local
  path.
- **Canonical bars schema** (locked by tests): required columns
  `Date/Open/High/Low/Close/Volume` (`Date` normalized to daily granularity);
  optional `pre_close` carried only when the contributing provider really
  supplies it (vipdoc `.day` file semantics — never synthesized, never
  "previous row close" invented by the engine); `Amount` intentionally not
  carried (the legacy raw/D output never exposed it).  Units are
  provider-native passthrough — no ×100/÷100 scaling is introduced
  (regression-tested); documented units: vipdoc Volume 股, Sina Volume 股,
  mootdx keeps the TDX wire `vol` (cross-source absolute comparison remains
  unsupported per the `adjusted_bars` red line).
- **Legacy tail-supplement contract preserved verbatim**: when the base
  frame's last bar lags the requested end date, Sina is fetched over the
  full requested window and merged (supplement rows win on overlapping
  dates, dedupe keep-last, ascending); a failed supplement keeps the base
  frame and marks the routing result `degraded`.
- **`data_as_of`** is now realized for bars: the last business date of the
  returned bars within the requested window (the bars' own business date);
  `observed_at` stays unset (no provider observation timestamp in this
  chain — none fabricated).
- **Live bars capability probes** (`tests/test_live_capability_probes.py`):
  isolated `sina:bars` / `mootdx:bars` probes via
  `probe_daily_bars_provider` (observability, non-blocking); a red
  individual probe must stay visible even when the routing smoke is green.

#### Changed

- **`get_stock_data` (raw/D) now routes through the structured engine**; the
  tool itself is a compatibility renderer.  Public contract frozen and
  regression-tested line-by-line: signature, accepted tickers, inclusive
  date window, column order `Date,Open,High,Low,Close,Volume`, `# Data
  source` wording (including the `+ sina HTTP supplement` suffix rule),
  empty-result / both-sources-down / stale-coverage error envelopes.
  Non-raw / non-D (qfq/hfq/W/M) paths keep the legacy mootdx→Sina chain
  unchanged this round.
- **`_get_close_on_date` reads the structured bars directly** (same
  authoritative chain, same [date, date] window, same round(2) value) and
  no longer parses the formatted `get_stock_data` text output.
- **Empty mootdx answers are now `VendorNoDataError`** (classified
  `normal_empty` by adapters) instead of a bare `ValueError`; shape errors
  stay `ValueError` (`failed_structure`).  Behavior of every existing
  caller is unchanged (both flow to the Sina fallback exactly as before).
- **`vendor_errors.exception_to_fetch_status`** is the single shared
  exception→fetch-status classification; `quote_chain._classify_status`
  delegates to it so the quote and bars engines can never diverge.

### Phase 1.1.1 — Mixed Transport Verdict Fix (hotfix)

#### Fixed

- **`_get_mootdx_client` transport verdict used a universal instead of an
  existential check**: the final verdict fired `transport_ok=False` when
  *any* candidate's `Quotes.factory()` failed, discarding the transport
  evidence already proven by another candidate that constructed a client
  successfully (mixed: A factory-fail + B factory-ok/bars-canary-fail →
  transport downgraded → finance/xdxr blocked globally). The verdict is now
  the existential invariant `factory_successes > 0` (counted on both the
  named-candidate and the bare-factory fallback path), so mixed failures
  yield `transport_ok=True` with a bars-readiness cause, while
  `factory_successes == 0` still yields the transport-level verdict. The
  bounded bypass also tries the bare factory (user-persisted BESTIP) before
  downgrading transport evidence. All four semantics preserved: all-factory-
  fail → global gate; all-factory-ok/canary-fail → bars-only gate; mixed →
  bars-only gate; canary success → client selected, cache cleared.

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
