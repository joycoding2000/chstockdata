"""Trading-day calendar derived from the official vipdoc package (DEC-P1-27).

Primary path is zero-network: ``vipdoc/sh/lday/sh000001.day`` (the Shanghai
composite index daily file shipped in the official after-hours package) is
read with an **explicit market address** — ``000001`` alone would route to
``sz000001`` (Ping An Bank) and silently produce a wrong calendar.  Every bar
in that file is a trading day inside the file's covered range.

When the local file is missing or its latest bar is older than
``vipdoc_history_max_staleness_days``, the calendar falls back online
(mootdx Shanghai index daily bars -> Sina) and labels the source.  Outputs
always carry ``source`` / ``covered_range`` / ``last_bar_date`` / ``stale``;
dates outside the covered range are *unknown* (``None``), never inferred as
non-trading days.  No holiday table is hardcoded: ad-hoc closures cannot be
enumerated and any static table goes stale.

This is a supportive capability: every failure returns ``None`` and consumers
must fall back to their existing heuristics.  The calendar must never fail an
analysis.
"""

from __future__ import annotations

import bisect
import json
import logging
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any

import pandas as pd

from .fetch_result import (
    FETCH_NORMAL_EMPTY,
    FETCH_NOT_CONFIGURED,
    FETCH_SUCCESS,
    FetchAttempt,
    FetchMetadata,
    FetchResult,
)
from .routing_observation import (
    elapsed_ms,
    record_fetch_observation,
    utc_now_iso,
)
from .vendor_errors import (
    VendorNoDataError,
    VendorNotConfiguredError,
    exception_to_fetch_status,
)
from .vipdoc_history import load_vipdoc_daily

logger = logging.getLogger(__name__)

CALENDAR_INDEX_CODE = "000001"
CALENDAR_INDEX_MARKET = "sh"

SOURCE_LOCAL = "vipdoc_sh000001"
SOURCE_MOOTDX = "mootdx_sh000001"
SOURCE_SINA = "sina_sh000001"

TRADING_CALENDAR_CAPABILITY = "trading_calendar"
TRADING_CALENDAR_PROVIDERS: tuple[tuple[str, str], ...] = (
    ("tdx_vipdoc", "tdx_vipdoc:index_bars"),
    ("mootdx", "mootdx:index"),
    ("sina", "sina:index_bars"),
)

_SOURCE_BY_PROVIDER = {
    "tdx_vipdoc": SOURCE_LOCAL,
    "mootdx": SOURCE_MOOTDX,
    "sina": SOURCE_SINA,
}

# ~8 years of daily bars: enough for week/season-level consumers without
# making the fallback payload large.
_ONLINE_INDEX_BARS = 2000
_SINA_KLINE_URL = (
    "http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/"
    "CN_MarketData.getKLineData"
)

_MARKET_TZ = timezone(timedelta(hours=8))

# Process-local memo: one derivation per (root, day).  The calendar changes at
# most once per trading day, so this keeps repeated consumers (vipdoc staleness
# checks across prefetched tools) from re-parsing the index file or repeating
# the online fallback inside one run.
_CALENDAR_CACHE: dict[tuple[str, str], TradingCalendar | None] = {}


@dataclass(frozen=True)
class TradingCalendar:
    """One derivation of the trading-day set with its provenance."""

    trading_days: tuple[str, ...]
    source: str
    covered_range: tuple[str, str] | None
    last_bar_date: str | None
    stale: bool
    as_of: str
    limitations: tuple[str, ...] = ()


def _clear_calendar_cache() -> None:
    """Drop the process-local calendar memo (tests and explicit refreshes)."""

    _CALENDAR_CACHE.clear()


def _market_today() -> date:
    return datetime.now(_MARKET_TZ).date()


def _normalize_day(value: Any) -> str | None:
    text = str(value or "").strip()[:10].replace("/", "-")
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError:
        return None


def _coerce_day(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    normalized = _normalize_day(value)
    return date.fromisoformat(normalized) if normalized else _market_today()


def _max_staleness_days() -> float:
    try:
        from .config import get_config

        cfg = get_config()
    except Exception:  # noqa: BLE001 - config failure keeps the default
        return 5.0
    try:
        value = float(cfg.get("vipdoc_history_max_staleness_days", 5))
    except (TypeError, ValueError):
        return 5.0
    return value if value >= 0 else 5.0


def _frame_days(frame: Any) -> tuple[str, ...] | None:
    if frame is None or getattr(frame, "empty", True):
        return None
    try:
        dates = pd.to_datetime(frame["Date"], errors="coerce").dropna()
    except (KeyError, TypeError, ValueError):
        return None
    days = sorted({item.date().isoformat() for item in dates})
    return tuple(days) if days else None


def _calendar_values(values: Any, *, provider: str) -> list[Any]:
    if isinstance(values, pd.DataFrame):
        if "Date" not in values.columns:
            raise ValueError(f"{provider} calendar payload missing Date column")
        values = values["Date"].tolist()
    elif values is None or isinstance(values, (str, bytes, Mapping)):
        raise ValueError(f"{provider} calendar payload must contain date rows")
    else:
        try:
            values = list(values)
        except TypeError as exc:
            raise ValueError(
                f"{provider} calendar payload must be iterable"
            ) from exc

    if not values:
        raise ValueError(f"{provider} calendar payload has no date rows")
    return values


def _canonicalize_trading_days_with_quality(
    values: Any, *, provider: str
) -> tuple[tuple[str, ...], bool]:
    """Return canonical days and whether invalid rows were dropped."""

    values = _calendar_values(values, provider=provider)

    normalized_values = [_normalize_day(value) for value in values]
    days = {value for value in normalized_values if value is not None}
    if not days:
        raise ValueError(f"{provider} calendar payload has no valid dates")
    return tuple(sorted(days)), any(value is None for value in normalized_values)


def canonicalize_trading_days(values: Any, *, provider: str) -> tuple[str, ...]:
    """Normalize one provider's raw date values at the calendar boundary.

    Valid rows are retained when a payload also contains malformed dates, which
    preserves the legacy ``errors="coerce"`` tolerance.  A payload with no
    valid rows is a shape/structure failure; the adapter boundary classifies a
    truly empty response as ``normal_empty`` before calling this helper.
    """

    days, _partial = _canonicalize_trading_days_with_quality(
        values,
        provider=provider,
    )
    return days


# ── structured provider adapters ───────────────────────────────────────────


def _fetch_local_index_days(*, root: Any = None) -> Any:
    """Read the official Shanghai index file without converting failures to None."""

    try:
        frame = load_vipdoc_daily(
            CALENDAR_INDEX_CODE,
            market=CALENDAR_INDEX_MARKET,
            root=root,
        )
    except (VendorNoDataError, VendorNotConfiguredError):
        raise
    except Exception as exc:
        raise ValueError(
            f"vipdoc calendar file unreadable ({type(exc).__name__})"
        ) from exc

    if frame is None:
        raise VendorNotConfiguredError("vipdoc calendar file missing")
    if not isinstance(frame, pd.DataFrame):
        raise ValueError(  # noqa: TRY004 - structure failures use ValueError taxonomy
            "vipdoc calendar payload must be a pandas DataFrame"
        )
    if frame.empty:
        raise VendorNoDataError("vipdoc calendar file has no usable rows")
    if "Date" not in frame.columns:
        raise ValueError("vipdoc calendar payload missing Date column")
    return frame["Date"].tolist()


def _fetch_mootdx_index_days(
    *,
    root: Any = None,
    _observe_capability_health: bool = True,
) -> Any:
    """Read index bars through the existing ``mootdx:index`` operation."""

    del root
    from .a_stock import _mootdx_call, _normalize_mootdx_bars_frame

    raw = _mootdx_call(
        "index",
        symbol=CALENDAR_INDEX_CODE,
        frequency=9,
        offset=_ONLINE_INDEX_BARS,
        _observe_capability_health=_observe_capability_health,
    )
    if raw is None:
        raise VendorNoDataError("mootdx calendar returned no rows")
    if not isinstance(raw, pd.DataFrame):
        raise ValueError(  # noqa: TRY004 - structure failures use ValueError taxonomy
            "mootdx calendar payload must be a pandas DataFrame"
        )
    frame = _normalize_mootdx_bars_frame(raw)
    if frame is None or frame.empty:
        raise VendorNoDataError("mootdx calendar returned no rows")
    if "Date" not in frame.columns:
        raise ValueError("mootdx calendar payload missing Date column")
    return frame["Date"].tolist()


def _fetch_sina_index_days(*, root: Any = None) -> Any:
    """Read Shanghai index daily bars through the audited Sina endpoint."""

    del root
    from .a_stock import _source_http_get

    response = _source_http_get(
        "sina",
        _SINA_KLINE_URL,
        params={
            "symbol": f"{CALENDAR_INDEX_MARKET}{CALENDAR_INDEX_CODE}",
            "scale": "240",
            "ma": "no",
            "datalen": _ONLINE_INDEX_BARS,
        },
        timeout=15,
        fallback_from="trading_calendar",
    )
    raise_for_status = getattr(response, "raise_for_status", None)
    if callable(raise_for_status):
        raise_for_status()
    try:
        payload = json.loads(response.text)
    except AttributeError as exc:
        raise ValueError("sina calendar response has no text payload") from exc
    if not isinstance(payload, list):
        raise ValueError(  # noqa: TRY004 - structure failures use ValueError taxonomy
            "sina calendar payload must be a list"
        )
    if not payload:
        raise VendorNoDataError("sina calendar returned no rows")
    return [
        item.get("day") if isinstance(item, Mapping) else None
        for item in payload
    ]


CALENDAR_ADAPTERS: dict[str, Callable[..., Any]] = {
    "tdx_vipdoc": _fetch_local_index_days,
    "mootdx": lambda *, root=None: _fetch_mootdx_index_days(
        root=root,
        _observe_capability_health=False,
    ),
    "sina": _fetch_sina_index_days,
}


# ── local (zero network) ─────────────────────────────────────────────────────


def _read_local_index_days(root: Any = None) -> tuple[str, ...] | None:
    """Read the local index daily file with an explicit sh market address."""

    try:
        return canonicalize_trading_days(
            _fetch_local_index_days(root=root),
            provider="tdx_vipdoc",
        )
    except Exception as exc:  # noqa: BLE001 - a local read failure must degrade
        logger.info(
            "trading calendar local read failed: %s", type(exc).__name__
        )
        return None


def local_is_trading_day(day: str, *, root: Any = None) -> bool | None:
    """Local-only verdict for ``day``; ``None`` outside coverage or on failure.

    Never touches the network (used by request-budget decisions where the
    network call itself must not be triggered).
    """

    normalized = _normalize_day(day)
    if normalized is None:
        return None
    days = _read_local_index_days(root)
    if not days:
        return None
    if normalized < days[0] or normalized > days[-1]:
        return None
    index = bisect.bisect_left(days, normalized)
    return index < len(days) and days[index] == normalized


def local_latest_index_bar(*, root: Any = None) -> str | None:
    """Latest local index bar date (``None`` when unavailable)."""

    days = _read_local_index_days(root)
    return days[-1] if days else None


# ── online fallback (mootdx -> sina) ─────────────────────────────────────────


def _read_mootdx_index_days() -> tuple[str, ...] | None:
    try:
        return canonicalize_trading_days(
            _fetch_mootdx_index_days(),
            provider="mootdx",
        )
    except Exception as exc:  # noqa: BLE001 - fallback chain handles failures
        logger.info(
            "trading calendar mootdx fallback failed: %s", type(exc).__name__
        )
        return None


def _read_sina_index_days() -> tuple[str, ...] | None:
    try:
        return canonicalize_trading_days(
            _fetch_sina_index_days(),
            provider="sina",
        )
    except Exception as exc:  # noqa: BLE001 - fallback chain handles failures
        logger.info(
            "trading calendar sina fallback failed: %s", type(exc).__name__
        )
        return None


def _read_online_index_days() -> tuple[str, tuple[str, ...]] | None:
    """Return ``(source, days)`` from the online chain, or ``None``."""

    days = _read_mootdx_index_days()
    if days:
        return SOURCE_MOOTDX, days
    days = _read_sina_index_days()
    if days:
        return SOURCE_SINA, days
    return None


# ── public derivation ────────────────────────────────────────────────────────


def _run_calendar_adapter(
    provider: str,
    capability_id: str,
    adapter: Callable[..., Any] | None,
    *,
    root: Any,
    attempts: list[FetchAttempt],
    clock: Callable[[], float],
) -> tuple[tuple[str, ...] | None, bool]:
    """Execute one truthful adapter and append its attempt/health observation."""

    started = clock()
    started_at = utc_now_iso()
    if adapter is None:
        record_fetch_observation(
            attempts,
            provider=provider,
            capability_id=capability_id,
            status=FETCH_NOT_CONFIGURED,
            started_at=started_at,
            elapsed_ms=0,
            message="provider not available in this chain",
        )
        return None, False

    try:
        raw = adapter(root=root)
    except Exception as exc:  # noqa: BLE001 - classification is the adapter contract
        elapsed = elapsed_ms(clock, started)
        status = exception_to_fetch_status(exc)
        record_fetch_observation(
            attempts,
            provider=provider,
            capability_id=capability_id,
            status=status,
            started_at=started_at,
            elapsed_ms=elapsed,
            error_type=type(exc).__name__,
            message=str(exc),
            error_summary=str(exc),
        )
        return None, False

    elapsed = elapsed_ms(clock, started)
    is_empty = raw is None
    if isinstance(raw, pd.DataFrame):
        # An empty frame with no Date field is malformed, not a valid empty
        # response.  Provider adapters that represent a genuine empty answer
        # raise VendorNoDataError before reaching this generic boundary.
        is_empty = raw.empty and "Date" in raw.columns
    elif not is_empty and not isinstance(raw, (str, bytes, Mapping)):
        try:
            is_empty = len(raw) == 0
        except TypeError:
            is_empty = False
    if is_empty:
        record_fetch_observation(
            attempts,
            provider=provider,
            capability_id=capability_id,
            status=FETCH_NORMAL_EMPTY,
            started_at=started_at,
            elapsed_ms=elapsed,
            record_count=0,
            message="provider returned no trading-day rows",
        )
        return None, False

    try:
        days, partial = _canonicalize_trading_days_with_quality(
            raw,
            provider=provider,
        )
    except Exception as exc:  # noqa: BLE001 - canonical boundary is structure
        status = exception_to_fetch_status(exc)
        record_fetch_observation(
            attempts,
            provider=provider,
            capability_id=capability_id,
            status=status,
            started_at=started_at,
            elapsed_ms=elapsed,
            error_type=type(exc).__name__,
            message=str(exc),
            error_summary=str(exc),
        )
        return None, False

    record_fetch_observation(
        attempts,
        provider=provider,
        capability_id=capability_id,
        status=FETCH_SUCCESS,
        started_at=started_at,
        elapsed_ms=elapsed,
        record_count=len(days),
    )
    return days, partial


def _calendar_result(
    calendar: TradingCalendar | None,
    attempts: list[FetchAttempt],
    *,
    providers_used: list[str] | None = None,
    limitations: list[str] | None = None,
    partial: bool = False,
) -> FetchResult[TradingCalendar | None]:
    final_limitations = list(limitations or ())
    if calendar is not None:
        final_limitations = list(calendar.limitations) + final_limitations
    if partial and "invalid_calendar_dates_dropped" not in final_limitations:
        final_limitations.append("invalid_calendar_dates_dropped")
    providers = list(providers_used or ())
    metadata = FetchMetadata(
        capability=TRADING_CALENDAR_CAPABILITY,
        final_provider=providers[0] if len(providers) == 1 else None,
        retrieved_at=utc_now_iso(),
        observed_at=None,
        data_as_of=calendar.last_bar_date if calendar is not None else None,
        stale=calendar.stale if calendar is not None else False,
        partial=partial,
        limitations=final_limitations,
        attempts=list(attempts),
        providers_used=providers,
    )
    return FetchResult(data=calendar, metadata=metadata)


def _calendar_from_days(
    days: tuple[str, ...],
    source: str,
    today: date,
    *,
    stale: bool,
    limitations: tuple[str, ...] = (),
) -> TradingCalendar:
    return TradingCalendar(
        trading_days=days,
        source=source,
        covered_range=(days[0], days[-1]),
        last_bar_date=days[-1],
        stale=stale,
        as_of=today.isoformat(),
        limitations=limitations,
    )


def _calendar_from_provider_days(
    provider: str,
    days: tuple[str, ...],
    today: date,
) -> TradingCalendar:
    """Build a provider payload using the route's freshness policy."""

    if provider == "tdx_vipdoc":
        age = (today - date.fromisoformat(days[-1])).days
        max_staleness = _max_staleness_days()
        stale = age > max_staleness
        limitations = (
            (
                (
                    f"本地 vipdoc 上证指数最新 bar 落后 {age} 天"
                    f"（阈值 {max_staleness:g} 天）"
                ),
            )
            if stale
            else ()
        )
    else:
        stale = False
        limitations = ()
    return _calendar_from_days(
        days,
        _SOURCE_BY_PROVIDER[provider],
        today,
        stale=stale,
        limitations=limitations,
    )


def fetch_trading_calendar(
    *,
    root: Any = None,
    today: Any = None,
    adapters: Mapping[str, Callable[..., Any]] | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> FetchResult[TradingCalendar | None]:
    """Fetch the trading calendar through the structured local-first route.

    This capability is supportive: no provider combination raises a routing
    exception.  ``data`` is ``None`` when no provider produced a usable
    calendar; the factual outcome remains visible in ``metadata.attempts``.
    ``adapters`` and ``clock`` are test seams and do not alter the default
    provider request semantics.
    """

    resolved_today = _coerce_day(today)
    chain = CALENDAR_ADAPTERS if adapters is None else adapters
    attempts: list[FetchAttempt] = []

    local_days, local_partial = _run_calendar_adapter(
        "tdx_vipdoc",
        "tdx_vipdoc:index_bars",
        chain.get("tdx_vipdoc"),
        root=root,
        attempts=attempts,
        clock=clock,
    )
    local_calendar: TradingCalendar | None = None
    if local_days:
        local_calendar = _calendar_from_provider_days(
            "tdx_vipdoc",
            local_days,
            resolved_today,
        )
        if not local_calendar.stale:
            return _calendar_result(
                local_calendar,
                attempts,
                providers_used=["tdx_vipdoc"],
                partial=local_partial,
            )

    for provider, capability_id in TRADING_CALENDAR_PROVIDERS[1:]:
        days, provider_partial = _run_calendar_adapter(
            provider,
            capability_id,
            chain.get(provider),
            root=root,
            attempts=attempts,
            clock=clock,
        )
        if not days:
            continue

        online_calendar = _calendar_from_provider_days(
            provider,
            days,
            resolved_today,
        )
        if local_calendar is None or online_calendar.last_bar_date >= local_calendar.last_bar_date:
            return _calendar_result(
                online_calendar,
                attempts,
                providers_used=[provider],
                partial=provider_partial,
            )

        preserved = TradingCalendar(
            trading_days=local_calendar.trading_days,
            source=local_calendar.source,
            covered_range=local_calendar.covered_range,
            last_bar_date=local_calendar.last_bar_date,
            stale=True,
            as_of=local_calendar.as_of,
            limitations=local_calendar.limitations
            + ("在线回落返回的日线不新于本地包，保留本地（陈旧）日历",),
        )
        return _calendar_result(
            preserved,
            attempts,
            providers_used=["tdx_vipdoc"],
            partial=local_partial,
        )

    if local_calendar is not None:
        preserved = TradingCalendar(
            trading_days=local_calendar.trading_days,
            source=local_calendar.source,
            covered_range=local_calendar.covered_range,
            last_bar_date=local_calendar.last_bar_date,
            stale=True,
            as_of=local_calendar.as_of,
            limitations=local_calendar.limitations
            + ("本地包超过陈旧度阈值，且在线回落失败；覆盖区间外日期不能判定",),
        )
        return _calendar_result(
            preserved,
            attempts,
            providers_used=["tdx_vipdoc"],
            partial=local_partial,
        )

    if any(attempt.is_failure() for attempt in attempts):
        limitations = ["all_sources_failed"]
    elif any(attempt.status == FETCH_NORMAL_EMPTY for attempt in attempts):
        limitations = ["all_sources_normal_empty"]
    elif any(attempt.status == FETCH_NOT_CONFIGURED for attempt in attempts):
        limitations = ["all_sources_not_configured"]
    else:
        limitations = ["all_sources_unavailable"]
    return _calendar_result(
        None,
        attempts,
        limitations=limitations,
        partial=False,
    )


def _build_calendar(root: Any, today: date) -> TradingCalendar | None:
    """Compatibility seam returning only the structured route payload."""

    return fetch_trading_calendar(root=root, today=today).data


def probe_trading_calendar_provider(
    provider: str,
    *,
    root: Any = None,
    today: Any = None,
    adapter: Callable[..., Any] | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> FetchResult[TradingCalendar | None]:
    """Observe exactly one provider's calendar capability."""

    provider_map = dict(TRADING_CALENDAR_PROVIDERS)
    if provider not in provider_map:
        raise ValueError(f"unknown trading calendar provider: {provider!r}")

    resolved_today = _coerce_day(today)
    capability_id = provider_map[provider]
    attempts: list[FetchAttempt] = []
    selected = adapter if adapter is not None else CALENDAR_ADAPTERS.get(provider)
    days, partial = _run_calendar_adapter(
        provider,
        capability_id,
        selected,
        root=root,
        attempts=attempts,
        clock=clock,
    )
    if days:
        calendar = _calendar_from_provider_days(
            provider,
            days,
            resolved_today,
        )
        return _calendar_result(
            calendar,
            attempts,
            providers_used=[provider],
            partial=partial,
        )
    return _calendar_result(
        None,
        attempts,
        limitations=[f"probe_unusable:{provider}"],
        partial=partial,
    )


def load_trading_calendar(
    *,
    root: Any = None,
    today: Any = None,
    use_cache: bool = True,
) -> TradingCalendar | None:
    """Derive the trading calendar (local-first, labelled online fallback).

    Returns ``None`` when no source is usable.  ``today`` (date or ISO string)
    only drives the staleness comparison; it never extends coverage.
    """

    resolved_today = _coerce_day(today)
    key = (str(root) if root is not None else "", resolved_today.isoformat())
    if use_cache and key in _CALENDAR_CACHE:
        return _CALENDAR_CACHE[key]
    calendar = fetch_trading_calendar(
        root=root,
        today=resolved_today,
    ).data
    if use_cache:
        _CALENDAR_CACHE[key] = calendar
    return calendar


def is_trading_day(
    calendar: TradingCalendar | None, day: Any
) -> bool | None:
    """Verdict for ``day``; ``None`` when outside coverage or unknown.

    A date after ``last_bar_date`` is unknown, not a holiday: the calendar
    must never turn "package not refreshed yet" into "no trading".
    """

    if calendar is None or not calendar.trading_days:
        return None
    normalized = _normalize_day(day)
    if normalized is None or calendar.last_bar_date is None:
        return None
    if calendar.covered_range and normalized < calendar.covered_range[0]:
        return None
    if normalized > calendar.last_bar_date:
        return None
    index = bisect.bisect_left(calendar.trading_days, normalized)
    return index < len(calendar.trading_days) and calendar.trading_days[index] == normalized


def latest_trading_day_on_or_before(
    calendar: TradingCalendar | None, day: Any
) -> str | None:
    """Latest known trading day ``<= day``; ``None`` when outside coverage."""

    if calendar is None or not calendar.trading_days:
        return None
    normalized = _normalize_day(day)
    if normalized is None or calendar.last_bar_date is None:
        return None
    if calendar.covered_range and normalized < calendar.covered_range[0]:
        return None
    if normalized > calendar.last_bar_date:
        return None
    index = bisect.bisect_right(calendar.trading_days, normalized) - 1
    if index < 0:
        return None
    return calendar.trading_days[index]


__all__ = [
    "CALENDAR_INDEX_CODE",
    "CALENDAR_INDEX_MARKET",
    "SOURCE_LOCAL",
    "SOURCE_MOOTDX",
    "SOURCE_SINA",
    "TRADING_CALENDAR_CAPABILITY",
    "TRADING_CALENDAR_PROVIDERS",
    "TradingCalendar",
    "canonicalize_trading_days",
    "fetch_trading_calendar",
    "is_trading_day",
    "latest_trading_day_on_or_before",
    "load_trading_calendar",
    "local_is_trading_day",
    "local_latest_index_bar",
    "probe_trading_calendar_provider",
]
