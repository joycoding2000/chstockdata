"""Structured daily-bars routing engine (tdx_vipdoc → mootdx → Sina).

v0.4.0 Phase 2 vertical slice: the raw/D historical daily-bars fallback chain
is the second real data path rebuilt on the generic structured core.  Layering::

    fetch_daily_bars()               structured FetchResult (this module)
        ↓
    a_stock.get_stock_data()         legacy compatibility renderer (unchanged
                                     output contract)

Provider health vs routing health are separated exactly as in
:mod:`chstockdata.quote_chain`: every provider attempt produces a
:class:`~chstockdata.fetch_result.FetchAttempt` and one capability-health
observation through the single ``fetch_status_to_health_status`` mapping, so
``mootdx:bars`` failing is visible even when the Sina fallback saves the
chain — and it never touches ``mootdx:finance``/``mootdx:xdxr``.

Canonical schema (locked by tests, see ``tests/test_daily_bars_schema.py``):

- Required columns: ``Date, Open, High, Low, Close, Volume``.
- Optional column: ``pre_close`` — present only when the contributing
  provider actually supplies it (today: ``tdx_vipdoc``'s ``.day`` file
  semantics = previous trading day's raw close **as recorded in the file**;
  never synthesized by this engine, never ``previous row close`` of another
  provider).  Rows merged from providers without it carry ``NaN``.
- ``Amount`` is deliberately NOT carried: no provider path in the legacy
  raw/D output ever exposed it (vipdoc's reader column is dropped exactly as
  before), and carrying it would leak a new column into the legacy CSV.
- Date: ``datetime64[ns]`` normalized to daily granularity (midnight,
  exchange business date, no timezone).  One row per trading date; no
  duplicate dates after a merge.
- Ordering: single-provider base frames keep the provider's native row order
  (vipdoc/sina ascend; mootdx keeps wire order) — the legacy output contract
  is frozen, and this engine does not reorder what the provider returned.
  Merged (supplement) frames are deduped keep-last and sorted ascending by
  the legacy ``_merge_ohlcv`` semantics (supplement rows win on overlap).
- Units: provider-native passthrough at the adapter boundary — values are
  never scaled.  Documented units: vipdoc ``Volume`` in 股, sina ``Volume``
  in 股; mootdx keeps the TDX wire ``vol``.  The project red line
  (``adjusted_bars``) stands: cross-source absolute volume comparison is
  unsupported.  A unit regression test locks "no scaling introduced".

Routing policy (THIS engine's, not the generic model's):

- vipdoc normal_empty / not_configured → try mootdx → then sina;
- ``not_configured`` (local layer disabled / package or file missing) is a
  fact, not a hard failure — it never marks the result degraded;
- first provider producing usable rows wins the base frame (no cross-provider
  history stitching beyond the legacy tail supplement);
- after a base frame exists, the legacy supplement contract runs verbatim:
  when the base's last bar is behind the requested end date, Sina is fetched
  over the full requested window and merged (supplement rows win on
  overlapping dates); a failed supplement keeps the base frame;
- window filtering (inclusive both ends) happens after the supplement step,
  exactly where the legacy renderer filtered;
- stale-coverage policy stays with the caller-visible contract: a frame whose
  coverage lags the requested end by more than ``_OHLCV_MAX_STALENESS_DAYS``
  is still returned as a successful result with ``metadata.stale=True`` —
  the legacy renderer turns that into the historical_ohlcv_stale marker.

``data_as_of`` is derived from the returned bars themselves (the last
business date inside the requested window) — this is the bars' own business
date and is reliably derivable.  ``observed_at`` stays ``None``: no provider
in this chain reports an observation timestamp, and none is fabricated.
"""

from __future__ import annotations

import time
from typing import Callable

import pandas as pd

from .capabilities import (
    ProviderCapability,
    fetch_status_to_health_status,
    record_capability_health,
)
from .fetch_result import (
    FETCH_FAILED_NETWORK,
    FETCH_FAILED_RATE_LIMIT,
    FETCH_FAILED_STRUCTURE,
    FETCH_NOT_CONFIGURED,
    FETCH_NORMAL_EMPTY,
    FETCH_SUCCESS,
    FetchAttempt,
    FetchMetadata,
    FetchResult,
)
from .vendor_errors import (
    VendorNetworkError,
    VendorNoDataError,
    VendorNotConfiguredError,
    exception_to_fetch_status,
)

__all__ = [
    "DAILY_BARS_CAPABILITY",
    "DAILY_BAR_PROVIDERS",
    "CANONICAL_REQUIRED_COLUMNS",
    "CANONICAL_OPTIONAL_COLUMNS",
    "ADAPTERS",
    "fetch_daily_bars",
    "probe_daily_bars_provider",
    "legacy_source_label",
    "DailyBarsRoutingError",
]

DAILY_BARS_CAPABILITY = "daily_bars"

# Explicit free-source order: local official vipdoc package → TDX (mootdx) →
# Sina.  This mirrors the audited legacy raw/D route (issues/023 方案 A).
DAILY_BAR_PROVIDERS: tuple[tuple[str, str], ...] = (
    ("tdx_vipdoc", "tdx_vipdoc:daily_bars"),
    ("mootdx", "mootdx:bars"),
    ("sina", "sina:bars"),
)

CANONICAL_REQUIRED_COLUMNS = ("Date", "Open", "High", "Low", "Close", "Volume")
CANONICAL_OPTIONAL_COLUMNS = ("pre_close",)


class DailyBarsRoutingError(RuntimeError):
    """All daily-bars providers failed; no usable bars could be routed.

    Mirrors the sanitized-error contract of the quote chain: the message
    never carries vendor URLs, exception details or internals (those live in
    ``attempts`` for diagnostics).
    """

    def __init__(self, attempts: list[FetchAttempt]):
        self.attempts = list(attempts)
        super().__init__("日线数据不可用：本地vipdoc、mootdx、新浪均未返回有效日线数据")


# ---------------------------------------------------------------------------
# Provider adapters (raise structured vendor errors; return frames on success)
# ---------------------------------------------------------------------------


def _vipdoc_public_columns(frame: pd.DataFrame) -> pd.DataFrame:
    """Keep the reader's ``pre_close``; drop ``Amount`` as the legacy path did."""
    columns = [
        column
        for column in (*CANONICAL_REQUIRED_COLUMNS[:5], "pre_close", "Volume")
        if column in frame.columns
    ]
    return frame[columns].reset_index(drop=True)


def fetch_vipdoc_daily_bars(
    code: str, start_date: str, end_date: str
) -> pd.DataFrame:
    """Local official TDX vipdoc package adapter (read-only, zero network).

    Outcome classification for a *local* source deliberately avoids network
    semantics: configuration-disabled / missing package or file →
    ``VendorNotConfiguredError``; unreadable/corrupt file → ``ValueError``
    (structure); requested window empty or the local package lags the
    requested end beyond ``vipdoc_history_max_staleness_days`` (and the
    trading calendar cannot confirm the market has no newer session,
    DEC-P1-27) → ``VendorNoDataError`` with the reason in the message.
    """
    from . import a_stock

    try:
        from .config import get_config

        cfg = get_config()
    except Exception as exc:  # pragma: no cover - config failure must not kill the chain
        raise VendorNotConfiguredError("vipdoc history configuration unavailable") from exc
    if not cfg.get("vipdoc_history_enabled", True):
        raise VendorNotConfiguredError("vipdoc history disabled by configuration")
    try:
        max_staleness = float(cfg.get("vipdoc_history_max_staleness_days", 5))
    except (TypeError, ValueError):
        max_staleness = 5.0

    try:
        from .vipdoc_history import load_vipdoc_daily

        frame = load_vipdoc_daily(code, start_date, end_date)
    except Exception as exc:  # noqa: BLE001 - local read failure must degrade
        raise ValueError(
            f"vipdoc day file unreadable ({type(exc).__name__})"
        ) from exc
    if frame is None:
        # Layer enabled but nothing installed for this code.
        raise VendorNotConfiguredError("vipdoc day file missing")
    if frame.empty:
        raise VendorNoDataError("no vipdoc rows in the requested window")
    last = a_stock._last_ohlcv_date(frame)
    if last is None:
        raise VendorNoDataError("vipdoc rows carry no valid dates")
    target = pd.to_datetime(end_date).normalize()
    if (target - last).days > max_staleness:
        reference = a_stock._calendar_reference_last_bar(end_date)
        if reference is not None:
            try:
                reference_stamp = pd.to_datetime(reference).normalize()
            except (TypeError, ValueError):
                reference_stamp = None
            if reference_stamp is not None and last >= reference_stamp:
                return _vipdoc_public_columns(frame)
        raise VendorNoDataError(
            f"vipdoc package ends {last.date()}, more than {max_staleness:g} "
            f"days behind requested {pd.Timestamp(target).date()}"
        )
    return _vipdoc_public_columns(frame)


def fetch_mootdx_daily_bars(
    code: str, start_date: str, end_date: str
) -> pd.DataFrame:
    """mootdx TCP daily bars adapter.

    Reuses ``a_stock._fetch_mootdx_bars`` verbatim, so the Phase 1.1/1.1.1
    readiness semantics (``_get_mootdx_client`` bars readiness, negative
    cache tiering, bounded bypass isolation for other capabilities) apply
    unchanged.  The provider contract is the most recent 800 daily bars —
    no date-window filtering happens here (legacy behavior; window filtering
    belongs to the engine/renderer).
    """
    from . import a_stock

    return a_stock._fetch_mootdx_bars(code, offset=800)


def fetch_sina_daily_bars(
    code: str, start_date: str, end_date: str
) -> pd.DataFrame:
    """Sina HTTP daily K-line adapter (unchanged request semantics).

    Same endpoint, parameters, units and window filtering as the audited
    legacy ``a_stock._sina_kline_fallback``; an empty answer is surfaced as
    ``VendorNoDataError`` (normal_empty) instead of an empty frame.
    """
    from . import a_stock

    frame = a_stock._sina_kline_fallback(code, start_date, end_date)
    if frame is None or frame.empty:
        raise VendorNoDataError("no sina kline rows in the requested window")
    return frame


# Provider name → adapter.  Resolved at call time from this module-level
# registry so tests can stub single providers via ``monkeypatch.setitem``.
ADAPTERS: dict[str, Callable[..., pd.DataFrame]] = {
    "tdx_vipdoc": fetch_vipdoc_daily_bars,
    "mootdx": fetch_mootdx_daily_bars,
    "sina": fetch_sina_daily_bars,
}


# ---------------------------------------------------------------------------
# Routing engine
# ---------------------------------------------------------------------------


def _empty_canonical_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Date": pd.Series(dtype="datetime64[ns]"),
            "Open": pd.Series(dtype="float64"),
            "High": pd.Series(dtype="float64"),
            "Low": pd.Series(dtype="float64"),
            "Close": pd.Series(dtype="float64"),
            "Volume": pd.Series(dtype="float64"),
        }
    )


def _capability_for(capability_id: str) -> ProviderCapability:
    return ProviderCapability(*capability_id.split(":", 1))


def _observe_health(
    capability: ProviderCapability, status: str, *, error_summary: str | None = None
) -> None:
    record_capability_health(
        capability,
        fetch_status_to_health_status(status),
        error_summary=error_summary,
    )


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def _attempt(
    provider: str,
    capability_id: str,
    status: str,
    started_at: str,
    elapsed_ms: int,
    *,
    record_count: int | None = None,
    error_type: str | None = None,
    message: str | None = None,
) -> FetchAttempt:
    return FetchAttempt(
        provider=provider,
        capability=capability_id,
        status=status,
        started_at=started_at,
        elapsed_ms=elapsed_ms,
        record_count=record_count,
        error_type=error_type,
        message=message,
    )


def _run_adapter(
    provider: str,
    capability_id: str,
    adapter: Callable[..., pd.DataFrame],
    code: str,
    start_date: str,
    end_date: str,
    attempts: list[FetchAttempt],
    *,
    clock: Callable[[], float],
) -> pd.DataFrame | None:
    """Run one provider adapter, append its attempt + health observation.

    Returns the provider frame on success, ``None`` otherwise (the attempt
    list always carries the factual outcome).
    """
    capability = _capability_for(capability_id)
    start = clock()
    started_at = _now_iso()
    try:
        frame = adapter(code, start_date, end_date)
    except Exception as exc:  # noqa: BLE001 - classified below
        elapsed = int((clock() - start) * 1000)
        status = exception_to_fetch_status(exc)
        attempts.append(
            _attempt(
                provider,
                capability_id,
                status,
                started_at,
                elapsed,
                error_type=type(exc).__name__,
                message=str(exc),
            )
        )
        _observe_health(capability, status, error_summary=str(exc))
        return None

    elapsed = int((clock() - start) * 1000)
    if frame is None or (hasattr(frame, "empty") and frame.empty):
        attempts.append(
            _attempt(
                provider,
                capability_id,
                FETCH_NORMAL_EMPTY,
                started_at,
                elapsed,
                record_count=0,
                message="provider returned no rows",
            )
        )
        _observe_health(capability, FETCH_NORMAL_EMPTY)
        return None

    attempts.append(
        _attempt(
            provider,
            capability_id,
            FETCH_SUCCESS,
            started_at,
            elapsed,
            record_count=int(len(frame)),
        )
    )
    _observe_health(capability, FETCH_SUCCESS)
    return frame


def _supplement_with_sina(
    code: str,
    start_date: str,
    end_date: str,
    base_frame: pd.DataFrame,
    adapters: dict[str, Callable[..., pd.DataFrame]],
    attempts: list[FetchAttempt],
    *,
    clock: Callable[[], float],
) -> tuple[pd.DataFrame, bool, bool]:
    """Legacy tail-supplement contract, verbatim.

    When the base frame's last bar is behind the requested end date, Sina is
    fetched over the full requested window and merged (supplement rows win on
    overlapping dates; dedupe keep-last; ascending).  A failed or empty
    supplement keeps the base frame — it never fails the routing (legacy
    behavior), but hard supplement failures remain visible as failed attempts
    (and hence as a degraded routing result).
    """
    from . import a_stock

    if not a_stock._needs_sina_supplement(base_frame, end_date):
        return base_frame, False, False

    adapter = adapters.get("sina")
    provider, capability_id = "sina", "sina:bars"
    capability = _capability_for(capability_id)
    start = clock()
    started_at = _now_iso()
    if adapter is None:
        attempts.append(
            _attempt(
                provider,
                capability_id,
                FETCH_NOT_CONFIGURED,
                started_at,
                0,
                message="sina adapter not available in this chain",
            )
        )
        _observe_health(capability, FETCH_NOT_CONFIGURED)
        return base_frame, False, False
    try:
        supplement = adapter(code, start_date, end_date)
    except Exception as exc:  # noqa: BLE001 - supplement failure must not kill the base
        elapsed = int((clock() - start) * 1000)
        status = exception_to_fetch_status(exc)
        attempts.append(
            _attempt(
                provider,
                capability_id,
                status,
                started_at,
                elapsed,
                error_type=type(exc).__name__,
                message=str(exc),
            )
        )
        _observe_health(capability, status, error_summary=str(exc))
        return base_frame, False, status in (
            FETCH_FAILED_NETWORK,
            FETCH_FAILED_RATE_LIMIT,
            FETCH_FAILED_STRUCTURE,
        )

    elapsed = int((clock() - start) * 1000)
    if supplement is None or supplement.empty:
        attempts.append(
            _attempt(
                provider,
                capability_id,
                FETCH_NORMAL_EMPTY,
                started_at,
                elapsed,
                record_count=0,
                message="supplement returned no rows",
            )
        )
        _observe_health(capability, FETCH_NORMAL_EMPTY)
        return base_frame, False, False

    attempts.append(
        _attempt(
            provider,
            capability_id,
            FETCH_SUCCESS,
            started_at,
            elapsed,
            record_count=int(len(supplement)),
        )
    )
    _observe_health(capability, FETCH_SUCCESS)
    merged = a_stock._merge_ohlcv(base_frame, supplement)
    supplemented = a_stock._last_ohlcv_date(merged) != a_stock._last_ohlcv_date(
        base_frame
    )
    return merged, supplemented, False


def fetch_daily_bars(
    code: str,
    start_date: str,
    end_date: str,
    *,
    adapters: dict[str, Callable[..., pd.DataFrame]] | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> FetchResult[pd.DataFrame]:
    """Fetch canonical daily bars through the structured routing chain.

    Providers are tried in ``DAILY_BAR_PROVIDERS`` order; the first usable
    frame becomes the base (single source of truth — no cross-provider
    history stitching beyond the legacy Sina tail supplement).  Every real
    provider call produces a ``FetchAttempt`` plus one capability-health
    observation; routing outcomes are expressed by ``FetchMetadata``
    (``final_status`` / ``degraded`` / ``providers_used``).

    ``adapters`` replaces the whole provider chain (tests inject fakes);
    by default the module-level ``ADAPTERS`` registry is used.
    """
    from . import a_stock

    chain = ADAPTERS if adapters is None else adapters
    attempts: list[FetchAttempt] = []

    base_frame: pd.DataFrame | None = None
    base_provider: str | None = None
    for provider, capability_id in DAILY_BAR_PROVIDERS:
        adapter = chain.get(provider)
        if adapter is None:
            attempts.append(
                _attempt(
                    provider,
                    capability_id,
                    FETCH_NOT_CONFIGURED,
                    _now_iso(),
                    0,
                    message="provider not available in this chain",
                )
            )
            _observe_health(_capability_for(capability_id), FETCH_NOT_CONFIGURED)
            continue
        frame = _run_adapter(
            provider,
            capability_id,
            adapter,
            code,
            start_date,
            end_date,
            attempts,
            clock=clock,
        )
        if frame is not None:
            base_frame = frame
            base_provider = provider
            break

    if base_frame is None:
        if any(a.is_failure() for a in attempts):
            # Chain-level failure: providers broke and nothing usable arrived.
            raise DailyBarsRoutingError(attempts)
        limitations = ["all_sources_normal_empty"]
        if any(a.status == FETCH_NOT_CONFIGURED for a in attempts) and not any(
            a.status == FETCH_NORMAL_EMPTY for a in attempts
        ):
            limitations = ["all_sources_not_configured"]
        metadata = FetchMetadata(
            capability=DAILY_BARS_CAPABILITY,
            final_provider=None,
            retrieved_at=_now_iso(),
            data_as_of=None,
            limitations=limitations,
            attempts=attempts,
        )
        return FetchResult(data=_empty_canonical_frame(), metadata=metadata)

    # Legacy tail-supplement contract (see _supplement_with_sina).
    base_frame, supplemented, supplement_failed = _supplement_with_sina(
        code,
        start_date,
        end_date,
        base_frame,
        chain,
        attempts,
        clock=clock,
    )

    # Window filter (inclusive both ends), applied after the supplement step
    # exactly where the legacy renderer filtered.  Comparison values mirror
    # the legacy expression (un-normalized to_datetime) so datetime-bearing
    # arguments keep their historical semantics.
    start_dt = pd.to_datetime(start_date)
    end_dt = pd.to_datetime(end_date)
    frame = a_stock._normalize_ohlcv_dates(base_frame)
    frame = frame[(frame["Date"] >= start_dt) & (frame["Date"] <= end_dt)]
    frame = frame.reset_index(drop=True)

    providers_used = [base_provider]
    if supplemented:
        providers_used.append("sina")

    limitations: list[str] = []
    stale = False
    data_as_of: str | None = None
    if frame.empty:
        limitations.append("no_bars_in_requested_window")
    else:
        data_as_of = frame["Date"].max().strftime("%Y-%m-%d")
        coverage = a_stock._ohlcv_coverage(frame, end_date)
        if coverage["stale"]:
            # Bars-staleness policy: still a successful result (legacy never
            # hard-fails here); the flag travels in metadata and the legacy
            # renderer emits the historical_ohlcv_stale marker.
            stale = True
            limitations.append(
                "stale_coverage:"
                f"requested_end={coverage['requested_end']}"
                f",observed_max={coverage['observed_max']}"
                f",gap_days={coverage['gap_days']}"
            )
    if supplement_failed:
        limitations.append("sina_supplement_failed")

    metadata = FetchMetadata(
        capability=DAILY_BARS_CAPABILITY,
        final_provider=None,
        retrieved_at=_now_iso(),
        data_as_of=data_as_of,
        stale=stale,
        partial=False,
        limitations=limitations,
        attempts=attempts,
        providers_used=providers_used,
    )
    return FetchResult(data=frame, metadata=metadata)


# ---------------------------------------------------------------------------
# Isolated single-provider probe (live capability observability)
# ---------------------------------------------------------------------------


def probe_daily_bars_provider(
    provider: str,
    code: str,
    start_date: str,
    end_date: str,
    adapter: Callable[..., pd.DataFrame],
    *,
    clock: Callable[[], float] = time.monotonic,
) -> FetchResult[pd.DataFrame]:
    """Probe ONE provider bars capability in isolation.

    Live capability probes use this instead of the routing chain so that
    probing ``mootdx`` updates only ``mootdx:bars`` — never any other
    capability's health entry — and providers not part of the probe are NOT
    recorded as ``not_configured``.  Provider-level policies still apply
    inside the adapter (a stale vipdoc package is a policy rejection, not a
    hard failure); the probe reports the attempt's factual outcome.
    """
    capability_id = dict(DAILY_BAR_PROVIDERS)[provider]
    capability = _capability_for(capability_id)
    attempts: list[FetchAttempt] = []
    result = _run_adapter(
        provider,
        capability_id,
        adapter,
        code,
        start_date,
        end_date,
        attempts,
        clock=clock,
    )
    if result is not None:
        metadata = FetchMetadata(
            capability=DAILY_BARS_CAPABILITY,
            final_provider=None,
            retrieved_at=_now_iso(),
            data_as_of=result["Date"].max().strftime("%Y-%m-%d"),
            attempts=attempts,
            providers_used=[provider],
        )
        return FetchResult(data=result, metadata=metadata)
    metadata = FetchMetadata(
        capability=DAILY_BARS_CAPABILITY,
        final_provider=None,
        retrieved_at=_now_iso(),
        attempts=attempts,
        limitations=[f"probe_unusable:{provider}"],
    )
    return FetchResult(data=_empty_canonical_frame(), metadata=metadata)


# ---------------------------------------------------------------------------
# Legacy renderer support
# ---------------------------------------------------------------------------

_SOURCE_LABELS = {
    "tdx_vipdoc": "vipdoc local (TDX official hsjday package)",
    "mootdx": "mootdx (TCP)",
    "sina": "sina HTTP (fallback)",
}


def legacy_source_label(metadata: FetchMetadata) -> str:
    """Map the routing metadata onto the frozen legacy ``# Data source`` label.

    The supplement suffix appears only when Sina actually advanced the last
    bar date (the historical ``supplemented`` semantics) — overlap-only
    contributions keep the base label, exactly as before.
    """
    providers = list(metadata.providers_used)
    if not providers:
        return _SOURCE_LABELS["mootdx"]
    base = _SOURCE_LABELS.get(providers[0], providers[0])
    if any(extra == "sina" for extra in providers[1:]):
        return f"{base} + sina HTTP supplement"
    return base
