"""Structured delisting status vertical-slice contract tests."""

from __future__ import annotations

import json

import pytest

import chstockdata
from chstockdata import a_stock
from chstockdata.capabilities import capability_health_snapshot, reset_capability_health
from chstockdata.fetch_result import (
    FETCH_FAILED_NETWORK,
    FETCH_NORMAL_EMPTY,
    FETCH_SUCCESS,
)


class _Response:
    def __init__(self, payload):
        self._payload = payload
        self.text = json.dumps(payload, ensure_ascii=False)

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def _sse_row(code: str, name: str = "测试退", list_date: str = "19980122", delist_date: str = "20091229") -> dict:
    return {
        "COMPANY_CODE": code,
        "COMPANY_ABBR": name,
        "LIST_DATE": list_date,
        "DELIST_DATE": delist_date,
    }


def _szse_row(code: str, name: str = "测试退", list_date: str = "1992-11-23", delist_date: str = "2022-06-27") -> dict:
    return {"zqdm": code, "zqjc": name, "ssrq": list_date, "zzrq": delist_date}


def _szse_tab2(rows: list[dict]) -> list[dict]:
    return [{"metadata": {"catalogid": "1793_ssgs", "tabkey": "tab2"}, "data": rows, "error": None}]


def _patch_cache_path(monkeypatch, tmp_path):
    monkeypatch.setattr(a_stock, "_delist_cache_path", lambda: str(tmp_path / "delist-list.json"))


def _fake_get_factory(sse_rows, szse_pages, calls, *, failures=()):
    failures = set(failures)

    def fake_get(source_id, url, *, params=None, **kwargs):
        calls.append((source_id, params))
        if source_id in failures:
            raise ConnectionError(f"{source_id} offline")
        if source_id == "sse":
            return _Response({"pageHelp": {"data": sse_rows}})
        page = int(params["PAGENO"])
        return _Response(_szse_tab2(szse_pages.get(page, [])))

    return fake_get


def _fetch(ticker: str):
    fetcher = getattr(chstockdata, "fetch_delisting_status", None)
    assert fetcher is not None, "fetch_delisting_status must be publicly exported"
    return fetcher(ticker)


@pytest.fixture(autouse=True)
def _reset_health():
    reset_capability_health()
    yield
    reset_capability_health()


def test_sse_match_returns_structured_delisted_true(monkeypatch, tmp_path):
    _patch_cache_path(monkeypatch, tmp_path)
    calls = []
    monkeypatch.setattr(
        a_stock,
        "_source_http_get",
        _fake_get_factory([_sse_row("600001")], {1: [_szse_row("000502")]}, calls),
    )

    result = _fetch("600001")

    assert set(result.data) == {
        "ticker",
        "market",
        "coverage",
        "delisted",
        "eligible_by_delisting",
        "record",
        "reference_date",
    }
    assert result.data["ticker"] == "600001"
    assert result.data["market"] == "sh"
    assert result.data["coverage"] == "covered"
    assert result.data["delisted"] is True
    assert result.data["eligible_by_delisting"] is False
    assert result.data["record"]["market"] == "sh"
    assert result.metadata.request_status == FETCH_SUCCESS
    assert {attempt.capability for attempt in result.metadata.attempts} == {
        "sse:delisting",
        "szse:delisting",
    }


def test_szse_match_returns_structured_delisted_true(monkeypatch, tmp_path):
    _patch_cache_path(monkeypatch, tmp_path)
    calls = []
    monkeypatch.setattr(
        a_stock,
        "_source_http_get",
        _fake_get_factory([], {1: [_szse_row("000502")]}, calls),
    )

    result = _fetch("000502")

    assert result.data["ticker"] == "000502"
    assert result.data["market"] == "sz"
    assert result.data["delisted"] is True
    assert result.data["eligible_by_delisting"] is False
    assert result.data["record"]["source"] == "szse_terminated_listings"
    assert result.metadata.request_status == FETCH_SUCCESS


def test_covered_market_miss_is_provider_success_but_request_normal_empty(monkeypatch, tmp_path):
    _patch_cache_path(monkeypatch, tmp_path)
    calls = []
    monkeypatch.setattr(
        a_stock,
        "_source_http_get",
        _fake_get_factory([], {1: []}, calls),
    )

    result = _fetch("600519")

    assert result.data["coverage"] == "covered"
    assert result.data["delisted"] is False
    assert result.data["eligible_by_delisting"] is True
    assert result.data["record"] is None
    assert result.metadata.request_status == FETCH_NORMAL_EMPTY
    assert [attempt.status for attempt in result.metadata.attempts] == [
        FETCH_SUCCESS,
        FETCH_SUCCESS,
    ]
    health = capability_health_snapshot()
    assert health["sse:delisting"].status == FETCH_SUCCESS
    assert health["szse:delisting"].status == FETCH_SUCCESS


def test_bse_is_uncovered_without_sse_or_szse_calls(monkeypatch, tmp_path):
    _patch_cache_path(monkeypatch, tmp_path)
    calls = []
    monkeypatch.setattr(
        a_stock,
        "_source_http_get",
        lambda *args, **kwargs: calls.append((args, kwargs)) or pytest.fail("BSE must not call SSE/SZSE"),
    )

    result = _fetch("920066")

    assert result.data == {
        "ticker": "920066",
        "market": "bse",
        "coverage": "uncovered",
        "delisted": None,
        "eligible_by_delisting": None,
        "record": None,
        "reference_date": None,
    }
    assert result.metadata.request_status == FETCH_NORMAL_EMPTY
    assert result.metadata.attempts == []
    assert calls == []
    assert capability_health_snapshot() == {}


def test_own_market_failure_is_unknown_and_not_masked_by_other_market_success(monkeypatch, tmp_path):
    _patch_cache_path(monkeypatch, tmp_path)
    calls = []
    monkeypatch.setattr(
        a_stock,
        "_source_http_get",
        _fake_get_factory([], {1: [_szse_row("000502")]}, calls, failures={"sse"}),
    )

    result = _fetch("600519")

    assert result.data == {}
    assert result.metadata.request_status == FETCH_FAILED_NETWORK
    assert {attempt.provider: attempt.status for attempt in result.metadata.attempts} == {
        "sse": FETCH_FAILED_NETWORK,
        "szse": FETCH_SUCCESS,
    }
    assert not (tmp_path / "delist-list.json").exists()


def test_cross_market_failure_preserves_own_market_answer_and_limitation(monkeypatch, tmp_path):
    _patch_cache_path(monkeypatch, tmp_path)
    calls = []
    monkeypatch.setattr(
        a_stock,
        "_source_http_get",
        _fake_get_factory([_sse_row("600001")], {}, calls, failures={"szse"}),
    )

    result = _fetch("600001")

    assert result.data["delisted"] is True
    assert result.metadata.request_status == FETCH_SUCCESS
    assert "cross_market_source_failed:szse" in result.metadata.limitations
    assert {attempt.provider: attempt.status for attempt in result.metadata.attempts} == {
        "sse": FETCH_SUCCESS,
        "szse": FETCH_FAILED_NETWORK,
    }


def test_cache_hit_has_no_new_attempt_or_health_observation(monkeypatch, tmp_path):
    _patch_cache_path(monkeypatch, tmp_path)
    calls = []
    monkeypatch.setattr(
        a_stock,
        "_source_http_get",
        _fake_get_factory([_sse_row("600001")], {1: [_szse_row("000502")]}, calls),
    )

    first = _fetch("600001")
    calls_after_first = len(calls)
    health_after_first = capability_health_snapshot()

    second = _fetch("600001")

    assert first.metadata.request_status == FETCH_SUCCESS
    assert second.metadata.request_status == FETCH_SUCCESS
    assert second.data == first.data
    assert second.metadata.attempts == []
    assert "reference_cache_hit" in second.metadata.limitations
    assert len(calls) == calls_after_first
    assert capability_health_snapshot() == health_after_first


def test_sse_and_szse_delisting_health_are_independent(monkeypatch, tmp_path):
    _patch_cache_path(monkeypatch, tmp_path)
    calls = []
    monkeypatch.setattr(
        a_stock,
        "_source_http_get",
        _fake_get_factory([], {1: []}, calls, failures={"sse"}),
    )

    _fetch("000519")

    health = capability_health_snapshot()
    assert health["sse:delisting"].status == "failed"
    assert health["szse:delisting"].status == FETCH_SUCCESS
    assert not any(
        capability_id.startswith(("listing:", "delisting:"))
        for capability_id in health
    )


def test_legacy_renderer_keeps_existing_envelope_fields(monkeypatch, tmp_path):
    _patch_cache_path(monkeypatch, tmp_path)
    calls = []
    monkeypatch.setattr(
        a_stock,
        "_source_http_get",
        _fake_get_factory([_sse_row("600001")], {1: [_szse_row("000502")]}, calls),
    )

    matched_raw = chstockdata.get_delisting_info("600001")
    matched = json.loads(matched_raw[matched_raw.find("{") :])
    assert matched["status"] == "success"
    assert matched["searched_market"] == "sh"
    assert matched["delisted"] is True
    assert matched["record"]["market"] == "sh"
    assert "ticker" not in matched

    miss_raw = chstockdata.get_delisting_info("600519")
    miss = json.loads(miss_raw[miss_raw.find("{") :])
    assert miss_raw.startswith("[正常空]")
    assert miss["status"] == "normal_empty"
    assert miss["delisted"] is False
    assert "在覆盖市场内未命中" in miss["coverage_note"]

    bse_raw = chstockdata.get_delisting_info("920066")
    bse = json.loads(bse_raw[bse_raw.find("{") :])
    assert bse_raw.startswith("[正常空]")
    assert bse["delisted"] is None
    assert "未覆盖" in bse["coverage_note"]


def test_structured_payload_is_minimal_and_version_stays_041():
    assert chstockdata.__version__ == "0.4.1"
    assert set(
        {
            "ticker",
            "market",
            "coverage",
            "delisted",
            "eligible_by_delisting",
            "record",
            "reference_date",
        }
    ) == {
        "ticker",
        "market",
        "coverage",
        "delisted",
        "eligible_by_delisting",
        "record",
        "reference_date",
    }
