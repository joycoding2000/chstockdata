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
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any

import pandas as pd

from .vipdoc_history import load_vipdoc_daily

logger = logging.getLogger(__name__)

CALENDAR_INDEX_CODE = "000001"
CALENDAR_INDEX_MARKET = "sh"

SOURCE_LOCAL = "vipdoc_sh000001"
SOURCE_MOOTDX = "mootdx_sh000001"
SOURCE_SINA = "sina_sh000001"

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
_CALENDAR_CACHE: dict[tuple[str, str], "TradingCalendar | None"] = {}


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
    except Exception:  # pragma: no cover - config failure keeps the default
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


# ── local (zero network) ─────────────────────────────────────────────────────


def _read_local_index_days(root: Any = None) -> tuple[str, ...] | None:
    """Read the local index daily file with an explicit sh market address."""

    try:
        frame = load_vipdoc_daily(
            CALENDAR_INDEX_CODE,
            market=CALENDAR_INDEX_MARKET,
            root=root,
        )
    except Exception as exc:  # noqa: BLE001 - a local read failure must degrade
        logger.info(
            "trading calendar local read failed: %s", type(exc).__name__
        )
        return None
    return _frame_days(frame)


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
        from .a_stock import _mootdx_call, _normalize_mootdx_bars_frame

        frame = _normalize_mootdx_bars_frame(
            _mootdx_call(
                "index",
                symbol=CALENDAR_INDEX_CODE,
                frequency=9,
                offset=_ONLINE_INDEX_BARS,
            )
        )
    except Exception as exc:  # noqa: BLE001 - fallback chain handles failures
        logger.info(
            "trading calendar mootdx fallback failed: %s", type(exc).__name__
        )
        return None
    return _frame_days(frame)


def _read_sina_index_days() -> tuple[str, ...] | None:
    try:
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
        payload = json.loads(response.text)
    except Exception as exc:  # noqa: BLE001 - fallback chain handles failures
        logger.info(
            "trading calendar sina fallback failed: %s", type(exc).__name__
        )
        return None
    if not isinstance(payload, list):
        return None
    days: set[str] = set()
    for item in payload:
        if not isinstance(item, Mapping):
            continue
        normalized = _normalize_day(item.get("day"))
        if normalized is not None:
            days.add(normalized)
    return tuple(sorted(days)) if days else None


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


def _build_calendar(root: Any, today: date) -> TradingCalendar | None:
    max_staleness = _max_staleness_days()
    local_days = _read_local_index_days(root)
    local_calendar: TradingCalendar | None = None
    if local_days:
        age = (today - date.fromisoformat(local_days[-1])).days
        local_calendar = _calendar_from_days(
            local_days,
            SOURCE_LOCAL,
            today,
            stale=age > max_staleness,
            limitations=(
                (
                    f"本地 vipdoc 上证指数最新 bar 落后 {age} 天"
                    f"（阈值 {max_staleness:g} 天）",
                )
                if age > max_staleness
                else ()
            ),
        )
        if not local_calendar.stale:
            return local_calendar

    online = _read_online_index_days()
    if online is not None:
        source, days = online
        online_last = days[-1]
        if local_calendar is None or online_last >= local_calendar.last_bar_date:
            return _calendar_from_days(days, source, today, stale=False)
        return TradingCalendar(
            trading_days=local_calendar.trading_days,
            source=local_calendar.source,
            covered_range=local_calendar.covered_range,
            last_bar_date=local_calendar.last_bar_date,
            stale=True,
            as_of=local_calendar.as_of,
            limitations=local_calendar.limitations
            + ("在线回落返回的日线不新于本地包，保留本地（陈旧）日历",),
        )

    if local_calendar is not None:
        return TradingCalendar(
            trading_days=local_calendar.trading_days,
            source=local_calendar.source,
            covered_range=local_calendar.covered_range,
            last_bar_date=local_calendar.last_bar_date,
            stale=True,
            as_of=local_calendar.as_of,
            limitations=local_calendar.limitations
            + ("本地包超过陈旧度阈值，且在线回落失败；覆盖区间外日期不能判定",),
        )
    return None


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
    calendar = _build_calendar(root, resolved_today)
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
    "TradingCalendar",
    "is_trading_day",
    "latest_trading_day_on_or_before",
    "load_trading_calendar",
    "local_is_trading_day",
    "local_latest_index_bar",
]
