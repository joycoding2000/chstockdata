"""DEC-P1-27 consumer-convergence contracts.

The trading calendar is a supportive capability: these tests pin that the
three converged consumers use it when it is available and fall back to the
pre-existing heuristics (weekend rule, all-pools-empty rule, calendar-day
staleness, probe window) when it is not.
"""

from __future__ import annotations

import struct
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from chstockdata import a_stock, market_breadth as mb

from test_free_market_breadth import (  # noqa: E402 - sibling test helpers
    _adv_ok,
    _fix_clock,
    _patch_adv,
    _patch_pools,
)

_CST = timezone(timedelta(hours=8))


def _write_day_file(path: Path, dates: list[str], *, base: float = 3000.0) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    records = bytearray()
    for index, day in enumerate(dates):
        compact = int(day.replace("-", ""))
        price = int((base + index) * 100)
        records += struct.pack(
            "<IIIIIfII",
            compact,
            price,
            price + 10,
            price - 10,
            price,
            1_000_000.0,
            12_345,
            0,
        )
    path.write_bytes(bytes(records))


# ── market_breadth ───────────────────────────────────────────────────────────


def test_market_breadth_calendar_confirmed_holiday_skips_pool_requests(monkeypatch):
    _fix_clock(monkeypatch, datetime(2026, 10, 9, 12, 30, tzinfo=_CST))
    monkeypatch.setattr(mb, "_sina_index_anchor", lambda: ("2026-10-09", "11:30:00"))
    requested = _patch_pools(monkeypatch)
    _patch_adv(monkeypatch)
    monkeypatch.setattr(mb, "_calendar_is_trading_day", lambda day: False)

    result = mb.get_market_breadth("2026-10-02")  # weekday holiday request

    assert requested["dates"] == []  # no Eastmoney pool request
    for key in ("limit_up", "failed_board", "limit_down"):
        assert result[key]["status"] == "unavailable"
        assert "交易日历" in result[key]["reason"] and "不是 0 家" in result[key]["reason"]
    assert result["status"] == "unavailable"


def test_market_breadth_calendar_confirmed_trading_day_refines_all_empty_note(monkeypatch):
    _fix_clock(monkeypatch, datetime(2026, 10, 9, 12, 30, tzinfo=_CST))
    monkeypatch.setattr(mb, "_sina_index_anchor", lambda: ("2026-10-09", "11:30:00"))
    _patch_pools(
        monkeypatch,
        zt={"tc": 0, "pool": []},
        zb={"tc": 0, "pool": []},
        dt={"tc": 0, "pool": []},
    )
    _patch_adv(monkeypatch, result=_adv_ok(trade_date="2026-10-09"))
    monkeypatch.setattr(mb, "_calendar_is_trading_day", lambda day: True)

    result = mb.get_market_breadth("2026-10-09")

    assert any(
        "交易日历确认该日为交易日" in line for line in result["limitations"]
    )
    for key in ("limit_up", "failed_board", "limit_down"):
        assert result[key]["status"] == "unavailable"
        assert "交易日历确认是交易日" in result[key]["reason"]


def test_market_breadth_calendar_unavailable_keeps_weekend_rule(monkeypatch):
    _fix_clock(monkeypatch, datetime(2026, 9, 7, 12, 30, tzinfo=_CST))
    monkeypatch.setattr(mb, "_sina_index_anchor", lambda: ("2026-09-07", "11:35:57"))
    requested = _patch_pools(monkeypatch)
    _patch_adv(monkeypatch)
    monkeypatch.setattr(mb, "_calendar_is_trading_day", lambda day: None)

    result = mb.get_market_breadth("2026-09-06")  # Sunday

    assert requested["dates"] == []
    assert "周末" in result["limit_up"]["reason"]


def test_market_breadth_calendar_error_falls_back_without_failing(monkeypatch):
    _fix_clock(monkeypatch, datetime(2026, 9, 7, 12, 30, tzinfo=_CST))
    monkeypatch.setattr(mb, "_sina_index_anchor", lambda: ("2026-09-07", "11:35:57"))
    _patch_pools(monkeypatch)
    _patch_adv(monkeypatch, result=_adv_ok())

    from chstockdata import trading_calendar

    def broken(*args, **kwargs):
        raise RuntimeError("calendar exploded")

    monkeypatch.setattr(trading_calendar, "load_trading_calendar", broken)

    # The seam (not the caller) owns the fail-soft contract: a calendar
    # failure must not fail the breadth tool.
    result = mb.get_market_breadth("2026-09-07")
    assert result["status"] == "success"
    assert result["limit_up"]["status"] == "success"


# ── vipdoc staleness (a_stock._load_vipdoc_ohlcv_frame) ─────────────────────


@pytest.mark.allow_vipdoc_history
def test_vipdoc_staleness_keeps_local_when_calendar_confirms_latest_session(
    tmp_path, monkeypatch
):
    from chstockdata import vipdoc_history

    monkeypatch.setattr(vipdoc_history, "vipdoc_history_dir", lambda: str(tmp_path))
    _write_day_file(
        tmp_path / "sh" / "lday" / "sh600519.day",
        ["2026-09-28", "2026-09-29", "2026-09-30"],
    )

    # Calendar-day gap > 5 (golden week), but the calendar confirms the local
    # package already reaches the market's latest session.
    monkeypatch.setattr(
        a_stock, "_calendar_reference_last_bar", lambda *_a, **_k: "2026-09-30"
    )
    frame = a_stock._load_vipdoc_ohlcv_frame("600519", "2026-09-01", "2026-10-08")
    assert frame is not None
    assert frame["Date"].max().strftime("%Y-%m-%d") == "2026-09-30"

    # Without the calendar the pre-existing calendar-day rule still falls back.
    monkeypatch.setattr(a_stock, "_calendar_reference_last_bar", lambda *_a, **_k: None)
    assert a_stock._load_vipdoc_ohlcv_frame("600519", "2026-09-01", "2026-10-08") is None


@pytest.mark.allow_vipdoc_history
def test_vipdoc_staleness_calendar_never_masks_a_stale_package(tmp_path, monkeypatch):
    from chstockdata import vipdoc_history

    monkeypatch.setattr(vipdoc_history, "vipdoc_history_dir", lambda: str(tmp_path))
    _write_day_file(
        tmp_path / "sh" / "lday" / "sh600519.day",
        ["2026-09-28", "2026-09-29", "2026-09-30"],
    )
    # The calendar's latest session (2026-10-09) is newer than the stock's
    # last bar, so the online chain must still be preferred.
    monkeypatch.setattr(
        a_stock, "_calendar_reference_last_bar", lambda *_a, **_k: "2026-10-09"
    )
    assert a_stock._load_vipdoc_ohlcv_frame("600519", "2026-09-01", "2026-10-09") is None


# ── mootdx negative-cache tiering (_tdx_probe_window_open) ──────────────────


def test_tdx_probe_window_closes_on_calendar_holiday(monkeypatch):
    class _FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 10, 2, 12, 0)  # weekday holiday inside the window

    monkeypatch.setattr(a_stock, "datetime", _FrozenDatetime)
    monkeypatch.setattr(a_stock, "_calendar_local_is_trading_day", lambda day: False)
    assert a_stock._tdx_probe_window_open() is False


def test_tdx_probe_window_keeps_time_heuristic_when_calendar_unknown(monkeypatch):
    class _FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 10, 2, 12, 0)

    monkeypatch.setattr(a_stock, "datetime", _FrozenDatetime)
    monkeypatch.setattr(a_stock, "_calendar_local_is_trading_day", lambda day: None)
    assert a_stock._tdx_probe_window_open() is True


# ── calendar reference semantics for the vipdoc staleness seam ──────────────


def test_calendar_reference_prefers_request_cutoff_within_coverage(monkeypatch):
    from chstockdata import trading_calendar as tc

    calendar = tc.TradingCalendar(
        trading_days=("2026-09-28", "2026-09-29", "2026-09-30", "2026-10-09"),
        source=tc.SOURCE_LOCAL,
        covered_range=("2026-09-28", "2026-10-09"),
        last_bar_date="2026-10-09",
        stale=False,
        as_of="2026-10-09",
    )
    monkeypatch.setattr(tc, "load_trading_calendar", lambda *a, **k: calendar)

    # Historical window ending mid-holiday: the expected last session is the
    # latest trading day at or before the requested cutoff.
    assert a_stock._calendar_reference_last_bar("2026-10-06") == "2026-09-30"
    assert a_stock._calendar_reference_last_bar("2026-10-09") == "2026-10-09"
    # Beyond coverage: the market's latest known session is the reference.
    assert a_stock._calendar_reference_last_bar("2026-10-10") == "2026-10-09"
    assert a_stock._calendar_reference_last_bar(None) == "2026-10-09"

    def broken(*args, **kwargs):
        raise RuntimeError("calendar exploded")

    monkeypatch.setattr(tc, "load_trading_calendar", broken)
    assert a_stock._calendar_reference_last_bar("2026-10-06") is None
