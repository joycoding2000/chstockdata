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
def _reset_health(monkeypatch):
    monkeypatch.setattr(
        tradability,
        "fetch_delisting_status",
        lambda _ticker: _delisting_result(status=FETCH_NORMAL_EMPTY),
        raising=False,
    )
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
    partial: bool = False,
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
        partial=partial,
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


def _delisting_result(
    *,
    status: str,
    coverage: str = "covered",
    delisted: bool | None = False,
    eligible_by_delisting: bool | None = True,
    record: dict | None = None,
    limitations: list[str] | None = None,
) -> FetchResult[dict]:
    attempts = [
        _attempt(
            "sse",
            "sse:delisting",
            FETCH_SUCCESS if status == FETCH_NORMAL_EMPTY else status,
        )
    ] if coverage == "covered" else []
    metadata = FetchMetadata(
        capability="delisting",
        final_provider="sse" if status in {FETCH_SUCCESS, FETCH_NORMAL_EMPTY} else None,
        retrieved_at="2026-09-10T00:00:02+00:00",
        data_as_of=_DATE if status in {FETCH_SUCCESS, FETCH_NORMAL_EMPTY} else None,
        limitations=limitations or [],
        attempts=attempts,
        providers_used=["sse"] if status in {FETCH_SUCCESS, FETCH_NORMAL_EMPTY} else [],
        outcome_status=status,
    )
    return FetchResult(
        data={
            "ticker": "600519",
            "market": "sh" if coverage == "covered" else "bse",
            "coverage": coverage,
            "delisted": delisted,
            "eligible_by_delisting": eligible_by_delisting,
            "record": record,
            "reference_date": _DATE if coverage == "covered" else None,
        } if status in {FETCH_SUCCESS, FETCH_NORMAL_EMPTY} else {},
        metadata=metadata,
    )


def test_holiday_is_closed_without_requesting_suspension(monkeypatch):
    calendar = _calendar_result(days=("2026-09-09", "2026-09-11"))
    calendar_calls = []
    delisting_calls = []
    suspension_calls = []

    def _fetch_calendar(*, root=None, today=None):
        calendar_calls.append((root, today))
        return calendar

    monkeypatch.setattr(tradability, "fetch_trading_calendar", _fetch_calendar)
    monkeypatch.setattr(
        tradability,
        "fetch_delisting_status",
        lambda ticker: delisting_calls.append(ticker),
    )
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
    assert delisting_calls == []
    assert suspension_calls == []
    assert result.metadata.request_status == FETCH_SUCCESS
    assert result.metadata.data_as_of == _DATE


def test_partial_calendar_positive_membership_still_queries_suspension(monkeypatch):
    monkeypatch.setattr(
        tradability,
        "fetch_trading_calendar",
        lambda **_kwargs: _calendar_result(
            days=("2026-09-09", _DATE, "2026-09-11"),
            partial=True,
            limitations=["invalid_calendar_dates_dropped"],
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

    assert result.data["tradable"] is True
    assert result.data["reason"] == "open_not_suspended"
    assert calls == [("600519", _DATE)]
    assert result.metadata.request_status == FETCH_SUCCESS


def test_partial_calendar_negative_membership_is_unknown_without_suspension(
    monkeypatch,
):
    monkeypatch.setattr(
        tradability,
        "fetch_trading_calendar",
        lambda **_kwargs: _calendar_result(
            days=("2026-09-09", "2026-09-11"),
            partial=True,
            limitations=["invalid_calendar_dates_dropped"],
        ),
    )
    delisting_calls = []
    monkeypatch.setattr(
        tradability,
        "fetch_delisting_status",
        lambda ticker: delisting_calls.append(ticker),
    )
    monkeypatch.setattr(
        tradability,
        "fetch_suspension_info",
        lambda *_args: pytest.fail(
            "partial calendar absence must not query suspension"
        ),
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
    assert [
        (attempt.provider, attempt.status)
        for attempt in result.metadata.attempts
    ] == [("tdx_vipdoc", FETCH_SUCCESS)]
    assert result.metadata.providers_used == ["tdx_vipdoc"]
    assert result.metadata.limitations == ["invalid_calendar_dates_dropped"]
    assert delisting_calls == []


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
    delisting_calls = []
    monkeypatch.setattr(
        tradability,
        "fetch_delisting_status",
        lambda ticker: delisting_calls.append(ticker),
    )
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
    assert delisting_calls == []


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
    monkeypatch.setattr(
        tradability,
        "fetch_delisting_status",
        lambda *_args: _delisting_result(
            status=FETCH_NORMAL_EMPTY,
            limitations=["delisting limitation"],
        ),
    )
    monkeypatch.setattr(tradability, "fetch_suspension_info", lambda *_args: suspension)

    result = fetch_tradability("600519", _DATE)

    assert result.metadata.capability == "tradability"
    assert [attempt.provider for attempt in result.metadata.attempts] == [
        "tdx_vipdoc",
        "mootdx",
        "sse",
        "eastmoney",
    ]
    assert result.metadata.providers_used == ["mootdx", "sse", "eastmoney"]
    assert result.metadata.limitations == [
        "calendar limitation",
        "delisting limitation",
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


@pytest.mark.parametrize(
    ("requested_date", "delist_date"),
    [
        ("2026-09-10", "2025-06-01"),
        ("2025-06-01", "2025-06-01"),
    ],
)
def test_effective_delisting_blocks_tradability_without_suspension(
    monkeypatch, requested_date, delist_date,
):
    monkeypatch.setattr(
        tradability,
        "fetch_trading_calendar",
        lambda **_kwargs: _calendar_result(
            days=("2025-05-30", requested_date, "2026-09-11")
        ),
    )
    monkeypatch.setattr(
        tradability,
        "fetch_delisting_status",
        lambda _ticker: _delisting_result(
            status=FETCH_SUCCESS,
            delisted=True,
            eligible_by_delisting=False,
            record={"delist_date": delist_date},
        ),
    )
    monkeypatch.setattr(
        tradability,
        "fetch_suspension_info",
        lambda *_args: pytest.fail("effective delisting must not query suspension"),
    )

    result = fetch_tradability("600519", requested_date)

    assert result.data["tradable"] is False
    assert result.data["market_open"] is True
    assert result.data["suspended"] is None
    assert result.data["reason"] == "delisted"
    assert result.metadata.request_status == FETCH_SUCCESS
    assert result.metadata.data_as_of == requested_date


def test_future_delisting_does_not_leak_backward(monkeypatch):
    requested_date = "2023-01-01"
    delisting_calls = []
    suspension_calls = []
    monkeypatch.setattr(
        tradability,
        "fetch_trading_calendar",
        lambda **_kwargs: _calendar_result(
            days=("2022-12-30", requested_date, "2023-01-03")
        ),
    )
    monkeypatch.setattr(
        tradability,
        "fetch_delisting_status",
        lambda ticker: delisting_calls.append(ticker) or _delisting_result(
            status=FETCH_SUCCESS,
            delisted=True,
            eligible_by_delisting=False,
            record={"delist_date": "2025-06-01"},
        ),
    )
    monkeypatch.setattr(
        tradability,
        "fetch_suspension_info",
        lambda ticker, curr_date: suspension_calls.append((ticker, curr_date))
        or _suspension_result(status=FETCH_NORMAL_EMPTY, suspended=False),
    )

    result = fetch_tradability("600519", requested_date)

    assert result.data["tradable"] is True
    assert result.data["reason"] == "open_not_suspended"
    assert delisting_calls == ["600519"]
    assert suspension_calls == [("600519", requested_date)]


def test_covered_delisting_miss_continues_to_suspension(monkeypatch):
    calls = []
    monkeypatch.setattr(
        tradability,
        "fetch_trading_calendar",
        lambda **_kwargs: _calendar_result(
            days=("2026-09-09", _DATE, "2026-09-11")
        ),
    )
    monkeypatch.setattr(
        tradability,
        "fetch_delisting_status",
        lambda _ticker: _delisting_result(status=FETCH_NORMAL_EMPTY),
    )
    monkeypatch.setattr(
        tradability,
        "fetch_suspension_info",
        lambda ticker, curr_date: calls.append((ticker, curr_date))
        or _suspension_result(status=FETCH_NORMAL_EMPTY, suspended=False),
    )

    result = fetch_tradability("600519", _DATE)

    assert result.data["tradable"] is True
    assert result.data["reason"] == "open_not_suspended"
    assert calls == [("600519", _DATE)]


def test_uncovered_delisting_stays_unknown_without_suspension(monkeypatch):
    monkeypatch.setattr(
        tradability,
        "fetch_trading_calendar",
        lambda **_kwargs: _calendar_result(
            days=("2026-09-09", _DATE, "2026-09-11")
        ),
    )
    monkeypatch.setattr(
        tradability,
        "fetch_delisting_status",
        lambda _ticker: _delisting_result(
            status=FETCH_NORMAL_EMPTY,
            coverage="uncovered",
            delisted=None,
            eligible_by_delisting=None,
            limitations=["market_uncovered"],
        ),
    )
    monkeypatch.setattr(
        tradability,
        "fetch_suspension_info",
        lambda *_args: pytest.fail("uncovered delisting must not query suspension"),
    )

    result = fetch_tradability("920066", _DATE)

    assert result.data == {
        "ticker": "920066",
        "date": _DATE,
        "tradable": None,
        "market_open": True,
        "suspended": None,
        "reason": "delisting_unknown",
    }
    assert result.metadata.request_status == FETCH_NORMAL_EMPTY
    assert [attempt.provider for attempt in result.metadata.attempts] == [
        "tdx_vipdoc"
    ]


def test_delisting_failure_stays_unknown_without_suspension(monkeypatch):
    monkeypatch.setattr(
        tradability,
        "fetch_trading_calendar",
        lambda **_kwargs: _calendar_result(
            days=("2026-09-09", _DATE, "2026-09-11")
        ),
    )
    monkeypatch.setattr(
        tradability,
        "fetch_delisting_status",
        lambda _ticker: _delisting_result(status=FETCH_FAILED_NETWORK),
    )
    monkeypatch.setattr(
        tradability,
        "fetch_suspension_info",
        lambda *_args: pytest.fail("delisting failure must not query suspension"),
    )

    result = fetch_tradability("600519", _DATE)

    assert result.data["tradable"] is None
    assert result.data["market_open"] is True
    assert result.data["reason"] == "delisting_unknown"
    assert result.metadata.request_status == FETCH_FAILED_NETWORK


@pytest.mark.parametrize("record", [None, {}, {"delist_date": "not-a-date"}])
def test_unusable_delist_date_stays_unknown_without_suspension(monkeypatch, record):
    monkeypatch.setattr(
        tradability,
        "fetch_trading_calendar",
        lambda **_kwargs: _calendar_result(
            days=("2026-09-09", _DATE, "2026-09-11")
        ),
    )
    monkeypatch.setattr(
        tradability,
        "fetch_delisting_status",
        lambda _ticker: _delisting_result(
            status=FETCH_SUCCESS,
            delisted=True,
            eligible_by_delisting=False,
            record=record,
        ),
    )
    monkeypatch.setattr(
        tradability,
        "fetch_suspension_info",
        lambda *_args: pytest.fail("unusable delist date must not query suspension"),
    )

    result = fetch_tradability("600519", _DATE)

    assert result.data["tradable"] is None
    assert result.data["market_open"] is True
    assert result.data["reason"] == "delisting_unknown"
    assert result.metadata.request_status == FETCH_NORMAL_EMPTY


@pytest.mark.parametrize(
    ("status", "coverage"),
    [
        (FETCH_SUCCESS, "uncovered"),
        (FETCH_NORMAL_EMPTY, "covered"),
    ],
)
def test_inconsistent_delisting_payload_stays_unknown_without_suspension(
    monkeypatch, status, coverage,
):
    monkeypatch.setattr(
        tradability,
        "fetch_trading_calendar",
        lambda **_kwargs: _calendar_result(
            days=("2026-09-09", _DATE, "2026-09-11")
        ),
    )
    monkeypatch.setattr(
        tradability,
        "fetch_delisting_status",
        lambda _ticker: _delisting_result(
            status=status,
            coverage=coverage,
            delisted=True,
            eligible_by_delisting=False,
            record={"delist_date": "2025-06-01"},
        ),
    )
    monkeypatch.setattr(
        tradability,
        "fetch_suspension_info",
        lambda *_args: pytest.fail("inconsistent delisting payload must not query suspension"),
    )

    result = fetch_tradability("600519", _DATE)

    assert result.data["tradable"] is None
    assert result.data["reason"] == "delisting_unknown"
    assert result.metadata.request_status == FETCH_NORMAL_EMPTY
