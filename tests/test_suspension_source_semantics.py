"""Regressions for latest-event data being mistaken for historical state."""
from datetime import date

import pytest
from test_suspension_structured import _Response, _row, _snapshot
from test_tradability import _calendar_result, _delisting_result

from chstockdata import (
    a_stock,
    fetch_suspension_info,
    get_suspension_info,
    suspension,
    tradability,
)
from chstockdata.fetch_result import (
    FETCH_FAILED_STRUCTURE,
    FETCH_NORMAL_EMPTY,
    FetchMetadata,
    FetchResult,
)


@pytest.fixture(autouse=True)
def isolated_current_day(monkeypatch):
    monkeypatch.setattr(a_stock, "_today", lambda: date(2026, 10, 9))
    suspension._suspension_snapshot_cache.clear()
    yield
    suspension._suspension_snapshot_cache.clear()


@pytest.mark.parametrize("rows", [[], [_row("000001")], [_row("600519", "2026-10-08")]])
def test_historical_latest_events_cannot_prove_suspension_or_absence(monkeypatch, rows):
    monkeypatch.setattr(a_stock, "_em_get", lambda *a, **k: _Response(_snapshot(rows, len(rows))))
    result = fetch_suspension_info("600519", "2026-09-11")
    assert result.data.get("suspended") is None
    assert result.metadata.request_status == FETCH_FAILED_STRUCTURE
    assert result.metadata.data_as_of is None
    assert "historical_suspension_unavailable" in result.metadata.limitations
    assert get_suspension_info("600519", "2026-09-11").startswith("[数据缺失]")


def test_current_cached_response_cannot_be_reused_as_historical_state(monkeypatch):
    calls = []
    def transport(*a, **k):
        calls.append(k["params"]["filter"])
        return _Response(_snapshot([_row("600519", "2026-10-08")], 1))
    monkeypatch.setattr(a_stock, "_em_get", transport)
    assert fetch_suspension_info("600519", "2026-10-09").data["suspended"] is True
    monkeypatch.setattr(a_stock, "_today", lambda: date(2026, 10, 10))
    result = fetch_suspension_info("600519", "2026-10-09")
    assert result.data.get("suspended") is None
    assert result.metadata.data_as_of is None
    assert len(calls) == 1


def test_future_event_does_not_block_current_trading(monkeypatch):
    monkeypatch.setattr(a_stock, "_em_get", lambda *a, **k: _Response(_snapshot([_row("600519", "2026-10-12")], 1)))
    result = fetch_suspension_info("600519", "2026-10-09")
    assert result.data.get("suspended") is None
    assert result.metadata.request_status == FETCH_FAILED_STRUCTURE


def test_current_resumed_record_is_not_suspended(monkeypatch):
    row = _row("603183", "2026-09-30")
    row["SUSPEND_END_TIME"] = "2026-10-08 15:00:00"
    row["PREDICT_RESUME_DATE"] = "2026-10-09 00:00:00"
    monkeypatch.setattr(a_stock, "_em_get", lambda *a, **k: _Response(_snapshot([row], 1)))
    result = fetch_suspension_info("603183", "2026-10-09")
    assert result.data["suspended"] is False


@pytest.mark.parametrize("suspended", [None, "false", 0])
def test_normal_empty_without_boolean_negative_is_unknown(monkeypatch, suspended):
    monkeypatch.setattr(tradability, "fetch_trading_calendar", lambda **k: _calendar_result(days=("2026-09-10",)))
    monkeypatch.setattr(tradability, "fetch_delisting_status", lambda *a: _delisting_result(status=FETCH_NORMAL_EMPTY))
    unknown = FetchResult(data={"suspended": suspended}, metadata=FetchMetadata(capability="suspension", final_provider=None, retrieved_at="2026-10-09T00:00:00+00:00", outcome_status=FETCH_NORMAL_EMPTY))
    monkeypatch.setattr(tradability, "fetch_suspension_info", lambda *a: unknown)
    result = tradability.fetch_tradability("600519", "2026-09-10")
    assert result.data["tradable"] is None
    assert result.data["reason"] == "suspension_unknown"
