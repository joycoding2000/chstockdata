"""Derived tradability verdict contracts."""

from __future__ import annotations

import pytest

import chstockdata.tradability as tradability
from chstockdata import (
    FETCH_FAILED_NETWORK,
    FETCH_NORMAL_EMPTY,
    FETCH_SUCCESS,
    fetch_tradability,
)
from chstockdata.capabilities import capability_health_snapshot, reset_capability_health
from chstockdata.fetch_result import FetchAttempt, FetchMetadata, FetchResult
from chstockdata.trading_calendar import TradingCalendar


_DATE = "2026-09-10"


@pytest.fixture(autouse=True)
def _reset_health():
    reset_capability_health()
    yield
    reset_capability_health()


def _attempt(provider: str, capability: str, status: str) -> FetchAttempt:
    return FetchAttempt(
        provider=provider,
        capability=capability,
        status=status,
        started_at="2026-09-10T00:00:00+00:00",
        elapsed_ms=1,
    )


def _calendar_result(
    *,
    days: tuple[str, ...],
    attempts: list[FetchAttempt] | None = None,
    providers_used: list[str] | None = None,
    limitations: list[str] | None = None,
    outcome_status: str | None = None,
) -> FetchResult[TradingCalendar | None]:
    calendar = TradingCalendar(
        trading_days=days,
        source="vipdoc_sh000001",
        covered_range=(days[0], days[-1]) if days else None,
        last_bar_date=days[-1] if days else None,
        stale=False,
        as_of=_DATE,
    ) if days else None
    attempts = attempts or [
        _attempt("tdx_vipdoc", "tdx_vipdoc:index_bars", FETCH_SUCCESS)
    ]
    providers_used = providers_used if providers_used is not None else ["tdx_vipdoc"]
    metadata = FetchMetadata(
        capability="trading_calendar",
        final_provider=None,
        retrieved_at="2026-09-10T00:00:01+00:00",
        data_as_of=days[-1] if days else None,
        limitations=limitations or [],
        attempts=attempts,
        providers_used=providers_used,
        outcome_status=outcome_status,
    )
    return FetchResult(data=calendar, metadata=metadata)


def _suspension_result(
    *,
    status: str,
    suspended: bool | None,
    limitations: list[str] | None = None,
) -> FetchResult[dict]:
    attempts = [
        _attempt("eastmoney", "eastmoney:suspension_snapshot", status)
    ]
    metadata = FetchMetadata(
        capability="suspension",
        final_provider=None if status == FETCH_FAILED_NETWORK else "eastmoney",
        retrieved_at="2026-09-10T00:00:02+00:00",
        data_as_of=_DATE if status != FETCH_FAILED_NETWORK else None,
        limitations=limitations or [],
        attempts=attempts,
        providers_used=[] if status == FETCH_FAILED_NETWORK else ["eastmoney"],
        outcome_status=status,
    )
    return FetchResult(
        data={} if suspended is None else {"suspended": suspended},
        metadata=metadata,
    )


def test_holiday_is_closed_without_requesting_suspension(monkeypatch):
    calendar = _calendar_result(days=("2026-09-09", "2026-09-11"))
    calendar_calls = []
    suspension_calls = []

    def _fetch_calendar(*, root=None, today=None):
        calendar_calls.append((root, today))
        return calendar

    monkeypatch.setattr(tradability, "fetch_trading_calendar", _fetch_calendar)
    monkeypatch.setattr(
        tradability,
        "fetch_suspension_info",
        lambda *args: suspension_calls.append(args),
    )

    result = fetch_tradability("600519", _DATE, root="fixture-root")

    assert result.data == {
        "ticker": "600519",
        "date": _DATE,
        "tradable": False,
        "market_open": False,
        "suspended": None,
        "reason": "market_closed",
    }
    assert calendar_calls == [("fixture-root", _DATE)]
    assert suspension_calls == []
    assert result.metadata.request_status == FETCH_SUCCESS
    assert result.metadata.data_as_of == _DATE


def test_trading_day_without_suspension_is_tradable(monkeypatch):
    monkeypatch.setattr(
        tradability,
        "fetch_trading_calendar",
        lambda **_kwargs: _calendar_result(
            days=("2026-09-09", _DATE, "2026-09-11")
        ),
    )
    calls = []
    monkeypatch.setattr(
        tradability,
        "fetch_suspension_info",
        lambda ticker, curr_date: (
            calls.append((ticker, curr_date))
            or _suspension_result(status=FETCH_NORMAL_EMPTY, suspended=False)
        ),
    )

    result = fetch_tradability("600519", _DATE)

    assert result.data == {
        "ticker": "600519",
        "date": _DATE,
        "tradable": True,
        "market_open": True,
        "suspended": False,
        "reason": "open_not_suspended",
    }
    assert calls == [("600519", _DATE)]
    assert result.metadata.request_status == FETCH_SUCCESS


def test_trading_day_with_suspension_is_not_tradable(monkeypatch):
    monkeypatch.setattr(
        tradability,
        "fetch_trading_calendar",
        lambda **_kwargs: _calendar_result(
            days=("2026-09-09", _DATE, "2026-09-11")
        ),
    )
    monkeypatch.setattr(
        tradability,
        "fetch_suspension_info",
        lambda *_args: _suspension_result(status=FETCH_SUCCESS, suspended=True),
    )

    result = fetch_tradability("600519", _DATE)

    assert result.data == {
        "ticker": "600519",
        "date": _DATE,
        "tradable": False,
        "market_open": True,
        "suspended": True,
        "reason": "suspended",
    }
    assert result.metadata.request_status == FETCH_SUCCESS


def test_unknown_calendar_does_not_request_suspension(monkeypatch):
    monkeypatch.setattr(
        tradability,
        "fetch_trading_calendar",
        lambda **_kwargs: _calendar_result(days=("2026-09-09",)),
    )
    monkeypatch.setattr(
        tradability,
        "fetch_suspension_info",
        lambda *_args: pytest.fail("unknown calendar must not query suspension"),
    )

    result = fetch_tradability("600519", _DATE)

    assert result.data == {
        "ticker": "600519",
        "date": _DATE,
        "tradable": None,
        "market_open": None,
        "suspended": None,
        "reason": "calendar_unknown",
    }
    assert result.metadata.request_status == FETCH_NORMAL_EMPTY
    assert result.metadata.data_as_of is None


def test_calendar_failure_status_wins_over_payload_and_short_circuits(monkeypatch):
    monkeypatch.setattr(
        tradability,
        "fetch_trading_calendar",
        lambda **_kwargs: _calendar_result(
            days=("2026-09-09", _DATE, "2026-09-11"),
            outcome_status=FETCH_FAILED_NETWORK,
        ),
    )
    monkeypatch.setattr(
        tradability,
        "fetch_suspension_info",
        lambda *_args: pytest.fail("calendar failure must not query suspension"),
    )

    result = fetch_tradability("600519", _DATE)

    assert result.data == {
        "ticker": "600519",
        "date": _DATE,
        "tradable": None,
        "market_open": None,
        "suspended": None,
        "reason": "calendar_unknown",
    }
    assert result.metadata.request_status == FETCH_FAILED_NETWORK
    assert result.metadata.data_as_of is None


def test_trading_day_with_suspension_failure_stays_unknown(monkeypatch):
    monkeypatch.setattr(
        tradability,
        "fetch_trading_calendar",
        lambda **_kwargs: _calendar_result(
            days=("2026-09-09", _DATE, "2026-09-11")
        ),
    )
    monkeypatch.setattr(
        tradability,
        "fetch_suspension_info",
        lambda *_args: _suspension_result(
            status=FETCH_FAILED_NETWORK,
            suspended=None,
            limitations=["eastmoney unavailable"],
        ),
    )

    result = fetch_tradability("600519", _DATE)

    assert result.data == {
        "ticker": "600519",
        "date": _DATE,
        "tradable": None,
        "market_open": True,
        "suspended": None,
        "reason": "suspension_unknown",
    }
    assert result.metadata.request_status == FETCH_FAILED_NETWORK
    assert result.metadata.data_as_of is None


def test_failed_suspension_cannot_be_overridden_by_false_payload(monkeypatch):
    monkeypatch.setattr(
        tradability,
        "fetch_trading_calendar",
        lambda **_kwargs: _calendar_result(
            days=("2026-09-09", _DATE, "2026-09-11")
        ),
    )
    monkeypatch.setattr(
        tradability,
        "fetch_suspension_info",
        lambda *_args: _suspension_result(
            status=FETCH_FAILED_NETWORK,
            suspended=False,
        ),
    )

    result = fetch_tradability("600519", _DATE)

    assert result.data["tradable"] is None
    assert result.data["reason"] == "suspension_unknown"
    assert result.metadata.request_status == FETCH_FAILED_NETWORK


def test_child_provenance_is_combined_in_execution_order(monkeypatch):
    calendar = _calendar_result(
        days=("2026-09-09", _DATE, "2026-09-11"),
        attempts=[
            _attempt("tdx_vipdoc", "tdx_vipdoc:index_bars", "failed_network"),
            _attempt("mootdx", "mootdx:index", FETCH_SUCCESS),
        ],
        providers_used=["mootdx"],
        limitations=["calendar limitation"],
    )
    suspension = _suspension_result(
        status=FETCH_SUCCESS,
        suspended=False,
        limitations=["suspension limitation"],
    )
    monkeypatch.setattr(tradability, "fetch_trading_calendar", lambda **_kwargs: calendar)
    monkeypatch.setattr(tradability, "fetch_suspension_info", lambda *_args: suspension)

    result = fetch_tradability("600519", _DATE)

    assert result.metadata.capability == "tradability"
    assert [attempt.provider for attempt in result.metadata.attempts] == [
        "tdx_vipdoc",
        "mootdx",
        "eastmoney",
    ]
    assert result.metadata.providers_used == ["mootdx", "eastmoney"]
    assert result.metadata.limitations == [
        "calendar limitation",
        "suspension limitation",
    ]


def test_derived_capability_does_not_record_its_own_health(monkeypatch):
    monkeypatch.setattr(
        tradability,
        "fetch_trading_calendar",
        lambda **_kwargs: _calendar_result(
            days=("2026-09-09", _DATE, "2026-09-11")
        ),
    )
    monkeypatch.setattr(
        tradability,
        "fetch_suspension_info",
        lambda *_args: _suspension_result(status=FETCH_NORMAL_EMPTY, suspended=False),
    )

    fetch_tradability("600519", _DATE)

    assert not any(
        key.startswith("tradability:") for key in capability_health_snapshot()
    )
