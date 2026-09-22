"""Structured suspension snapshot contract (Phase 5)."""

from __future__ import annotations

import pytest

import chstockdata.a_stock as a_stock
from chstockdata import (
    FETCH_FAILED_NETWORK,
    FETCH_FAILED_STRUCTURE,
    FETCH_NORMAL_EMPTY,
    FETCH_SUCCESS,
    fetch_suspension_info,
    get_suspension_info,
    get_capability_health,
    reset_capability_health,
)
from chstockdata.capabilities import ProviderCapability


class _Response:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def _row(code: str, start: str = "2026-09-10") -> dict:
    return {
        "SECURITY_CODE": code,
        "SECURITY_NAME_ABBR": "测试股",
        "SUSPEND_START_TIME": f"{start} 09:30:00",
        "SUSPEND_EXPIRE": "连续停牌",
        "SUSPEND_REASON": "刊登重要公告",
        "TRADE_MARKET": "上交所主板",
        "SUSPEND_START_DATE": f"{start} 00:00:00",
        "PREDICT_RESUME_DATE": None,
    }


def _snapshot(rows: list[dict], count: int | None = None) -> dict:
    result = {"data": rows}
    if count is not None:
        result["count"] = count
    return {"status": 0, "code": 0, "result": result}


@pytest.fixture(autouse=True)
def _clean_health_and_snapshot_cache():
    import chstockdata.suspension as suspension

    reset_capability_health()
    suspension._suspension_snapshot_cache.clear()
    yield
    reset_capability_health()
    suspension._suspension_snapshot_cache.clear()


def test_matched_ticker_returns_successful_structured_snapshot(monkeypatch):
    monkeypatch.setattr(a_stock, "_em_get", lambda *_args, **_kwargs: _Response(_snapshot([_row("600519")], 1)))

    result = fetch_suspension_info("600519", "2026-09-10")

    assert result.metadata.final_status == FETCH_SUCCESS
    assert result.metadata.request_status == FETCH_SUCCESS
    assert result.metadata.capability == "suspension"
    assert result.metadata.providers_used == ["eastmoney"]
    assert result.metadata.data_as_of == "2026-09-10"
    assert result.metadata.observed_at is None
    assert result.data["suspended"] is True
    assert result.data["suspend_start_date"] == "2026-09-10"
    assert result.metadata.attempts[0].capability == "eastmoney:suspension_snapshot"


def test_absent_ticker_is_request_normal_empty_after_successful_provider(monkeypatch):
    monkeypatch.setattr(a_stock, "_em_get", lambda *_args, **_kwargs: _Response(_snapshot([_row("688432")], 1)))

    result = fetch_suspension_info("600519", "2026-09-10")

    assert result.metadata.final_status == FETCH_SUCCESS
    assert result.metadata.request_status == FETCH_NORMAL_EMPTY
    assert result.is_normal_empty is True
    assert result.metadata.providers_used == ["eastmoney"]
    assert result.data["suspended"] is False


@pytest.mark.parametrize(
    ("transport", "expected"),
    [
        (lambda *_args, **_kwargs: (_ for _ in ()).throw(ConnectionError("offline")), FETCH_FAILED_NETWORK),
        (lambda *_args, **_kwargs: _Response(_snapshot([{"SECURITY_CODE": "600519", "SUSPEND_START_DATE": None}], 1)), FETCH_FAILED_STRUCTURE),
        (lambda *_args, **_kwargs: _Response(_snapshot([_row("688432")], 501)), FETCH_FAILED_STRUCTURE),
    ],
)
def test_snapshot_failures_are_provider_attempt_failures(monkeypatch, transport, expected):
    monkeypatch.setattr(a_stock, "_em_get", transport)

    result = fetch_suspension_info("600519", "2026-09-10")

    assert result.data == {}
    assert result.metadata.final_status == expected
    assert result.metadata.request_status == expected
    assert result.metadata.attempts[0].status == expected


def test_full_page_without_snapshot_count_is_failed_structure(monkeypatch):
    monkeypatch.setattr(
        a_stock,
        "_em_get",
        lambda *_args, **_kwargs: _Response(_snapshot([_row(f"{600000 + index:06d}") for index in range(500)])),
    )

    result = fetch_suspension_info("600519", "2026-09-10")

    assert result.data == {}
    assert result.metadata.attempts[0].status == FETCH_FAILED_STRUCTURE
    assert result.metadata.limitations == ["snapshot_count_missing"]


def test_same_date_cache_reuses_original_attempt_without_new_health(monkeypatch):
    calls = []

    def transport(*_args, **_kwargs):
        calls.append(1)
        return _Response(_snapshot([_row("600519")], 1))

    monkeypatch.setattr(a_stock, "_em_get", transport)
    first = fetch_suspension_info("600519", "2026-09-10")
    health = get_capability_health(ProviderCapability("eastmoney", "suspension_snapshot"))
    second = fetch_suspension_info("688432", "2026-09-10")

    assert len(calls) == 1
    assert second.metadata.attempts[0] is first.metadata.attempts[0]
    assert get_capability_health(ProviderCapability("eastmoney", "suspension_snapshot")) is health
    assert second.metadata.request_status == FETCH_NORMAL_EMPTY


def test_health_identity_isolated_and_legacy_renderer_remains_compatible(monkeypatch):
    monkeypatch.setattr(a_stock, "_em_get", lambda *_args, **_kwargs: _Response(_snapshot([_row("600519")], 1)))

    structured = fetch_suspension_info("600519", "2026-09-10")
    legacy = get_suspension_info("600519", "2026-09-10")

    assert get_capability_health(ProviderCapability("eastmoney", "suspension_snapshot")) is not None
    assert get_capability_health(ProviderCapability("eastmoney", "datacenter")) is None
    assert '"status":"success"' in legacy
    assert structured.data["suspended"] is True
