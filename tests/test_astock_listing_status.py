"""Contract tests for the DEC-P1-15A/15B listing-status data functions.

Covers ``get_disclosure_schedule`` (RPT_PUBLIC_BS_APPOIN), the per-date
suspend snapshot (RPT_CUSTOM_SUSPEND_DATA_INTERFACE), and the
exchange-official delisting reference (SSE common query + SZSE terminated
tab with a same-day disk cache).  Provider access is mocked; no network.
"""

from __future__ import annotations

import json

import pytest

import chstockdata.a_stock as a_stock


class _Response:
    def __init__(self, payload, *, json_error: bool = False):
        self._payload = payload
        self._json_error = json_error
        self.text = json.dumps(payload, ensure_ascii=False) if payload is not None else "{"

    def raise_for_status(self):
        return None

    def json(self):
        if self._json_error:
            raise a_stock._json.JSONDecodeError("bad json", "{", 0)
        return self._payload


def _envelope(rows: list[dict]) -> dict:
    return {
        "status": 0,
        "code": 0,
        "message": "ok",
        "result": {"data": rows, "count": len(rows)},
    }


def _result_payload(value: str) -> dict:
    return json.loads(value[value.find("{") :])


def _patch_cache_path(monkeypatch, tmp_path):
    monkeypatch.setattr(a_stock, "_delist_cache_path", lambda: str(tmp_path / "delist-list.json"))


# ---- get_disclosure_schedule ----


def _schedule_row(report_date: str, appointed: str, actual: str | None, modify: str | None) -> dict:
    return {
        "SECURITY_CODE": "600519",
        "REPORT_DATE": f"{report_date} 00:00:00",
        "FIRST_APPOINT_DATE": f"{appointed} 00:00:00",
        "APPOINT_PUBLISH_DATE": f"{appointed} 00:00:00",
        "ACTUAL_PUBLISH_DATE": f"{actual} 00:00:00" if actual else None,
        "MODIFY_TIMES": modify,
    }


def test_disclosure_schedule_parses_newest_rows_client_side(monkeypatch):
    calls = []

    def fake_em_get(url, params=None, **kwargs):
        calls.append(params)
        # Provider returns oldest-first on purpose: newest row must be picked
        # client-side, never trusting provider order.
        return _Response(
            _envelope(
                [
                    _schedule_row("2025-12-31", "2026-04-17", "2026-04-17", None),
                    _schedule_row("2026-06-30", "2026-08-15", None, "1"),
                ]
            )
        )

    monkeypatch.setattr(a_stock, "_em_get", fake_em_get)
    raw = a_stock.get_disclosure_schedule("600519")
    payload = _result_payload(raw)
    assert payload["status"] == "success"
    assert payload["latest_report_date"] == "2026-06-30"
    assert payload["schedule"][0]["report_date"] == "2026-06-30"
    assert payload["schedule"][0]["actual_publish_date"] is None
    assert payload["schedule"][0]["modify_times"] == 1.0
    assert payload["schedule"][1]["report_date"] == "2025-12-31"
    assert calls[0]["filter"] == '(SECURITY_CODE="600519")'
    assert "[数据缺失]" not in raw and "[正常空]" not in raw


def test_disclosure_schedule_caps_recent_periods(monkeypatch):
    rows = [
        _schedule_row(f"2025-0{index}-30", f"2025-0{index}-28", f"2025-0{index}-29", None)
        for index in range(1, 7)
    ]
    monkeypatch.setattr(a_stock, "_em_get", lambda *a, **k: _Response(_envelope(rows)))
    payload = _result_payload(a_stock.get_disclosure_schedule("600519"))
    assert payload["schedule_count"] == 4
    assert len(payload["schedule"]) == 4


def test_disclosure_schedule_datacenter_null_result_with_empty_code_is_normal_empty(monkeypatch):
    monkeypatch.setattr(
        a_stock,
        "_em_get",
        lambda *a, **k: _Response({"status": 0, "code": 9201, "message": "返回数据为空", "result": None}),
    )
    raw = a_stock.get_disclosure_schedule("600519")
    assert raw.startswith("[正常空]")
    assert _result_payload(raw)["status"] == "normal_empty"


def test_disclosure_schedule_null_result_with_other_code_is_structure_failure(monkeypatch):
    monkeypatch.setattr(
        a_stock,
        "_em_get",
        lambda *a, **k: _Response({"status": 0, "code": 9501, "message": "unknown", "result": None}),
    )
    raw = a_stock.get_disclosure_schedule("600519")
    assert raw.startswith("[数据缺失]")
    assert _result_payload(raw)["status"] == "failed_structure"


def test_disclosure_schedule_rows_without_parseable_report_date_fail_structure(monkeypatch):
    monkeypatch.setattr(
        a_stock,
        "_em_get",
        lambda *a, **k: _Response(_envelope([{"SECURITY_CODE": "600519", "REPORT_DATE": None}])),
    )
    raw = a_stock.get_disclosure_schedule("600519")
    assert raw.startswith("[正常空]")


@pytest.mark.parametrize("exc", [ConnectionError("boom"), TimeoutError("slow")])
def test_disclosure_schedule_network_failures_are_explicit(monkeypatch, exc):
    def _raise(*args, **kwargs):
        raise exc

    monkeypatch.setattr(a_stock, "_em_get", _raise)
    raw = a_stock.get_disclosure_schedule("600519")
    assert raw.startswith("[数据缺失]")
    assert _result_payload(raw)["status"] == "failed_network"


def test_disclosure_schedule_rejects_non_a_share_input():
    # Keep the rejected input non-Chinese: Chinese names would fall through to
    # resolve_ticker and probe the mootdx full-market name map (network).
    raw = a_stock.get_disclosure_schedule("AAPL")
    assert "Invalid ticker" in raw
    assert _result_payload(raw)["status"] == "invalid_input"


# ---- get_suspension_info ----


def _suspend_row(code: str, start: str, reason: str = "刊登重要公告") -> dict:
    return {
        "SECURITY_CODE": code,
        "SECURITY_NAME_ABBR": "测试股",
        "SUSPEND_START_TIME": f"{start} 09:30:00",
        "SUSPEND_END_TIME": None,
        "SUSPEND_EXPIRE": "连续停牌",
        "SUSPEND_REASON": reason,
        "TRADE_MARKET": "上交所主板",
        "SUSPEND_START_DATE": f"{start} 00:00:00",
        "PREDICT_RESUME_DATE": None,
        "SECUCODE": f"{code}.SH",
    }


def test_suspension_parses_matching_snapshot_row(monkeypatch):
    calls = []
    rows = [_suspend_row("688432", "2026-08-31", "拟筹划重大资产重组"), _suspend_row("600519", "2026-09-11")]

    def fake_em_get(url, params=None, **kwargs):
        calls.append(params)
        return _Response(_envelope(rows))

    monkeypatch.setattr(a_stock, "_em_get", fake_em_get)
    payload = _result_payload(a_stock.get_suspension_info("688432", "2026-09-10"))
    assert payload["status"] == "success"
    assert payload["suspended"] is True
    assert payload["suspend_start_date"] == "2026-08-31"
    assert payload["suspend_reason"] == "拟筹划重大资产重组"
    assert payload["snapshot_rows"] == 2
    # Provider rejects filters without MARKET (code 9501); per-stock filter
    # stays client-side.
    assert '(MARKET="全部")' in calls[0]["filter"]
    assert "(DATETIME='2026-09-10')" in calls[0]["filter"]
    assert "688432" not in calls[0]["filter"]


def test_suspension_absence_is_normal_empty_not_failure(monkeypatch):
    monkeypatch.setattr(
        a_stock, "_em_get", lambda *a, **k: _Response(_envelope([_suspend_row("688432", "2026-08-31")]))
    )
    raw = a_stock.get_suspension_info("600519", "2026-09-10")
    assert raw.startswith("[正常空]")
    payload = _result_payload(raw)
    assert payload["status"] == "normal_empty"
    assert payload["suspended"] is False
    assert payload["snapshot_rows"] == 1


def test_suspension_truncated_snapshot_cannot_be_reported_as_normal_empty(monkeypatch):
    # Page holds one row but the provider reports 501 existing rows; the
    # requested stock may sit beyond the fetched page — fail closed instead
    # of asserting "no suspension record" (v0.5.0 coverage fix).
    envelope = _envelope([_suspend_row("688432", "2026-08-31")])
    envelope["result"]["count"] = 501
    monkeypatch.setattr(a_stock, "_em_get", lambda *a, **k: _Response(envelope))

    raw = a_stock.get_suspension_info("600519", "2026-09-10")

    assert raw.startswith("[数据缺失]")
    payload = _result_payload(raw)
    assert payload["status"] == "failed_structure"
    assert payload["reason"] == "snapshot_truncated"
    assert payload["reported_count"] == 501


def test_suspension_datacenter_null_result_is_normal_empty(monkeypatch):
    monkeypatch.setattr(
        a_stock,
        "_em_get",
        lambda *a, **k: _Response({"status": 0, "code": 9201, "message": "返回数据为空", "result": None}),
    )
    raw = a_stock.get_suspension_info("600519", "2026-09-10")
    assert raw.startswith("[正常空]")
    assert _result_payload(raw)["suspended"] is False


def test_suspension_row_missing_required_start_date_fails_structure(monkeypatch):
    monkeypatch.setattr(
        a_stock,
        "_em_get",
        lambda *a, **k: _Response(_envelope([{"SECURITY_CODE": "600519", "SUSPEND_START_DATE": None}])),
    )
    raw = a_stock.get_suspension_info("600519", "2026-09-10")
    assert raw.startswith("[数据缺失]")
    assert _result_payload(raw)["status"] == "failed_structure"


def test_suspension_rejects_invalid_date_input():
    raw = a_stock.get_suspension_info("600519", "not-a-date")
    assert "Invalid ticker" in raw
    assert _result_payload(raw)["status"] == "invalid_input"


# ---- get_delisting_info ----


def _sse_delist_row(code: str, name: str, list_date: str, delist_date: str) -> dict:
    return {
        "COMPANY_CODE": code,
        "COMPANY_ABBR": name,
        "LIST_DATE": list_date,
        "DELIST_DATE": delist_date,
    }


def _szse_tab2(rows: list[dict]) -> list[dict]:
    return [{"metadata": {"catalogid": "1793_ssgs", "tabkey": "tab2"}, "data": rows, "error": None}]


def _szse_row(code: str, name: str, ssrq: str, zzrq: str) -> dict:
    return {"zqdm": code, "zqjc": name, "ssrq": ssrq, "zzrq": zzrq}


class _HttpResp:
    def __init__(self, payload):
        self._payload = payload
        self.text = json.dumps(payload, ensure_ascii=False)

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def _fake_get_factory(sse_rows, szse_pages, calls):
    def fake_get(source_id, url, *, params=None, headers=None, timeout=0, **kwargs):
        calls.append((source_id, params))
        if source_id == "sse":
            return _HttpResp({"pageHelp": {"data": sse_rows}})
        rows = szse_pages.get(int(params["PAGENO"]), [])
        return _HttpResp(_szse_tab2(rows))

    return fake_get


@pytest.fixture()
def _no_sleep(monkeypatch):
    monkeypatch.setattr(a_stock.time, "sleep", lambda _seconds: None)


def test_delisting_matches_official_records_and_caches_same_day(monkeypatch, tmp_path, _no_sleep):
    _patch_cache_path(monkeypatch, tmp_path)
    calls: list = []
    fake_get = _fake_get_factory(
        [_sse_delist_row("600001", "邯郸钢铁", "19980122", "20091229")],
        {1: [_szse_row("000502", "绿景退", "1992-11-23", "2022-06-27")]},
        calls,
    )
    monkeypatch.setattr(a_stock, "_source_http_get", fake_get)

    sh_payload = _result_payload(a_stock.get_delisting_info("600001"))
    assert sh_payload["status"] == "success"
    assert sh_payload["delisted"] is True
    assert sh_payload["record"]["delist_date"] == "2009-12-29"
    assert sh_payload["record"]["market"] == "sh"
    assert sh_payload["searched_market"] == "sh"

    sz_payload = _result_payload(a_stock.get_delisting_info("000502"))
    assert sz_payload["status"] == "success"
    assert sz_payload["delisted"] is True
    assert sz_payload["record"]["source"] == "szse_terminated_listings"

    miss_payload = _result_payload(a_stock.get_delisting_info("600519"))
    assert miss_payload["status"] == "normal_empty"
    assert miss_payload["delisted"] is False

    # Same-day cache: no further provider calls after the first run.
    calls_after_first_run = len(calls)
    a_stock.get_delisting_info("600001")
    assert len(calls) == calls_after_first_run


def test_delisting_bse_is_explicitly_uncovered_never_not_delisted(monkeypatch, tmp_path):
    _patch_cache_path(monkeypatch, tmp_path)
    raw = a_stock.get_delisting_info("920066")
    assert raw.startswith("[正常空]")
    payload = _result_payload(raw)
    assert payload["delisted"] is None
    assert payload["searched_market"] == "bse"
    assert "未覆盖" in payload["coverage_note"]


def test_delisting_own_market_failure_is_failed_and_never_cached(monkeypatch, tmp_path, _no_sleep):
    _patch_cache_path(monkeypatch, tmp_path)
    cache_file = tmp_path / "delist-list.json"

    def failing_sse(source_id, url, **kwargs):
        if source_id == "sse":
            raise ConnectionError("offline")
        return _HttpResp(_szse_tab2([_szse_row("000502", "绿景退", "1992-11-23", "2022-06-27")]))

    monkeypatch.setattr(a_stock, "_source_http_get", failing_sse)
    raw = a_stock.get_delisting_info("600519")
    assert raw.startswith("[数据缺失]")
    assert _result_payload(raw)["status"] == "failed_network"
    assert not cache_file.exists()

    # The other market still answers, with the partial-source limitation.
    sz_payload = _result_payload(a_stock.get_delisting_info("000502"))
    assert sz_payload["status"] == "success"
    assert sz_payload["cross_market_source_failed"] is True


def test_delisting_ignores_stale_or_corrupt_cache(monkeypatch, tmp_path, _no_sleep):
    cache_file = tmp_path / "delist-list.json"
    _patch_cache_path(monkeypatch, tmp_path)

    # Corrupt cache is ignored and refetched.
    cache_file.write_text("{not-json", encoding="utf-8")
    calls: list = []
    monkeypatch.setattr(
        a_stock,
        "_source_http_get",
        _fake_get_factory([], {1: []}, calls),
    )
    a_stock.get_delisting_info("600519")
    assert calls

    # Stale (previous-day) cache is ignored: cache_date is rewritten.
    cache_file.write_text(
        json.dumps(
            {
                "cache_date": "2020-01-01",
                "observed_at": "2020-01-01T00:00:00+08:00",
                "rows": [_sse_delist_row("600001", "邯郸钢铁", "19980122", "20091229")],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    calls.clear()
    monkeypatch.setattr(
        a_stock,
        "_source_http_get",
        _fake_get_factory([], {1: []}, calls),
    )
    payload = _result_payload(a_stock.get_delisting_info("600001"))
    assert payload["delisted"] is False
    assert payload["reference_date"] != "2020-01-01"
    assert calls


def test_delisting_rejects_non_a_share_input():
    raw = a_stock.get_delisting_info("AAPL")
    assert "Invalid ticker" in raw
    assert _result_payload(raw)["status"] == "invalid_input"
