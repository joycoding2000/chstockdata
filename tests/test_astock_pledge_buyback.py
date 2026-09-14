"""Contract tests for the P1-EVENT-01 pledge/buyback data functions.

Covers the two Eastmoney datacenter endpoints added by DEC-P1-14A:
``get_shareholder_pledge`` (RPT_CSDC_LIST weekly stock-state series) and
``get_corporate_buyback`` (RPTA_WEB_GETHGLIST_NEW plan/progress records).
All provider access is mocked at ``a_stock._em_get``; no network is touched.
"""

from __future__ import annotations

import json

import pytest

import chstockdata.a_stock as a_stock


class _Response:
    def __init__(self, payload, *, json_error: bool = False):
        self._payload = payload
        self._json_error = json_error

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


# ---- get_shareholder_pledge ----


def _pledge_row(trade_date: str, ratio: str, deals: str = "29") -> dict:
    return {
        "SECUCODE": "600016.SH",
        "SECURITY_CODE": "600016",
        "TRADE_DATE": trade_date,
        "PLEDGE_RATIO": ratio,
        "PLEDGE_DEAL_NUM": deals,
        # Provider quirk under test: the pledged-share balance rides on a
        # buyback-looking column name.
        "REPURCHASE_BALANCE": "198715.17",
        "PLEDGE_MARKET_CAP": "717361.7637",
    }


def test_shareholder_pledge_parses_latest_weekly_row(monkeypatch):
    calls = []

    def fake_em_get(url, params=None, **kwargs):
        calls.append((url, params))
        # Provider returns newest-last on purpose: the function must pick the
        # newest parsable row itself instead of trusting provider order.
        return _Response(
            _envelope(
                [
                    _pledge_row("2026-08-28 00:00:00", "6.1"),
                    _pledge_row("2026-09-04 00:00:00", "5.6"),
                ]
            )
        )

    monkeypatch.setattr(a_stock, "_em_get", fake_em_get)
    raw = a_stock.get_shareholder_pledge("600016")
    payload = _result_payload(raw)

    url, params = calls[0]
    assert url == a_stock._DATACENTER_URL
    assert params["reportName"] == "RPT_CSDC_LIST"
    assert params["filter"] == '(SECURITY_CODE="600016")'
    assert params["sortColumns"] == "TRADE_DATE"
    assert params["sortTypes"] == "-1"

    assert payload["status"] == "success"
    assert payload["trade_date"] == "2026-09-04"
    assert payload["pledge_ratio_pct"] == 5.6
    assert payload["pledge_deal_num"] == 29
    assert payload["pledge_shares_wan"] == 198715.17
    assert payload["pledge_mcap_wan"] == 717361.7637
    assert payload["source"] == "Eastmoney datacenter RPT_CSDC_LIST"
    assert "observed_at" in payload and "as_of_date" in payload
    assert raw.startswith("{")


def test_shareholder_pledge_near_zero_ratio_is_data_not_empty(monkeypatch):
    monkeypatch.setattr(
        a_stock,
        "_em_get",
        lambda *a, **k: _Response(_envelope([_pledge_row("2026-09-04 00:00:00", "0.04")])),
    )
    payload = _result_payload(a_stock.get_shareholder_pledge("600519"))
    assert payload["status"] == "success"
    assert payload["pledge_ratio_pct"] == 0.04


def test_shareholder_pledge_datacenter_null_result_with_empty_code_is_normal_empty(monkeypatch):
    monkeypatch.setattr(
        a_stock,
        "_em_get",
        lambda *a, **k: _Response(
            {"result": None, "code": 9201, "message": "返回数据为空"}
        ),
    )
    raw = a_stock.get_shareholder_pledge("999999")
    assert raw.startswith("[正常空]")
    payload = _result_payload(raw)
    assert payload["status"] == "normal_empty"
    assert payload["trade_date"] is None


def test_shareholder_pledge_null_result_with_other_code_is_structure_failure(monkeypatch):
    monkeypatch.setattr(
        a_stock,
        "_em_get",
        lambda *a, **k: _Response(
            {"result": None, "code": 9501, "message": "报表配置不存在"}
        ),
    )
    raw = a_stock.get_shareholder_pledge("600016")
    assert raw.startswith("[数据缺失]")
    assert _result_payload(raw)["status"] == "failed_structure"


def test_shareholder_pledge_rows_without_parseable_ratio_fail_structure(monkeypatch):
    monkeypatch.setattr(
        a_stock,
        "_em_get",
        lambda *a, **k: _Response(
            _envelope([_pledge_row("2026-09-04 00:00:00", None)])
        ),
    )
    raw = a_stock.get_shareholder_pledge("600016")
    assert _result_payload(raw)["status"] == "failed_structure"


def test_shareholder_pledge_network_and_json_failures_are_explicit(monkeypatch):
    def _raise_connection(*args, **kwargs):
        raise ConnectionError("boom")

    monkeypatch.setattr(a_stock, "_em_get", _raise_connection)
    raw = a_stock.get_shareholder_pledge("600016")
    assert _result_payload(raw)["status"] == "failed_network"

    monkeypatch.setattr(
        a_stock, "_em_get", lambda *a, **k: _Response({}, json_error=True)
    )
    raw = a_stock.get_shareholder_pledge("600016")
    assert _result_payload(raw)["status"] == "failed_structure"


def test_shareholder_pledge_bse_code_passes_through(monkeypatch):
    calls = []

    def fake_em_get(url, params=None, **kwargs):
        calls.append(params)
        return _Response(
            {"result": None, "code": 9201, "message": "返回数据为空"}
        )

    monkeypatch.setattr(a_stock, "_em_get", fake_em_get)
    raw = a_stock.get_shareholder_pledge("920066")
    assert calls[0]["filter"] == '(SECURITY_CODE="920066")'
    assert _result_payload(raw)["status"] == "normal_empty"


@pytest.mark.parametrize("ticker", ["AAPL", "00700", "60051", ""])
def test_shareholder_pledge_rejects_non_a_share_input(ticker):
    raw = a_stock.get_shareholder_pledge(ticker)
    assert raw.startswith("Invalid ticker")
    assert _result_payload(raw)["status"] == "invalid_input"


# ---- get_corporate_buyback ----


def _buyback_row(announced: str, progress: str = "006", amount: str = "2999933749.57") -> dict:
    return {
        "DIM_SCODE": "600519",
        "DIM_DATE": announced,
        "REPURPROGRESS": progress,
        "REPURAMOUNTLOWER": "1500000000",
        "REPURAMOUNTLIMIT": "3000000000",
        "REPURAMOUNT": amount,
        "REPURNUM": "2188614",
        "FINISHDATE": "2026-05-27",
        "REPUROBJECTIVE": "为维护公司及广大投资者的利益，增强投资者信心。",
    }


def test_corporate_buyback_parses_sorts_and_dedupes(monkeypatch):
    calls = []

    def fake_em_get(url, params=None, **kwargs):
        calls.append((url, params))
        return _Response(
            _envelope(
                [
                    _buyback_row("2025-11-06"),
                    _buyback_row("2025-11-06"),
                    _buyback_row("2024-09-21", amount="5999993751.17"),
                ]
            )
        )

    monkeypatch.setattr(a_stock, "_em_get", fake_em_get)
    monkeypatch.setattr(a_stock, "_today", lambda: a_stock.date(2026, 9, 10))
    raw = a_stock.get_corporate_buyback("600519")
    payload = _result_payload(raw)

    url, params = calls[0]
    assert url == a_stock._DATACENTER_URL
    assert params["reportName"] == "RPTA_WEB_GETHGLIST_NEW"
    assert params["filter"] == '(DIM_SCODE="600519")'
    assert params["sortColumns"] == "UPD,DIM_DATE,DIM_SCODE"
    assert params["sortTypes"] == "-1,-1,-1"

    assert payload["status"] == "success"
    assert payload["buyback_count"] == 2
    assert payload["latest_announced_date"] == "2025-11-06"
    assert [row["announced_date"] for row in payload["buybacks"]] == [
        "2025-11-06",
        "2024-09-21",
    ]
    latest = payload["buybacks"][0]
    assert latest["progress_code"] == "006"
    assert latest["progress"] == "完成实施"
    assert latest["plan_amount_lower_yi"] == 15.0
    assert latest["plan_amount_upper_yi"] == 30.0
    assert latest["executed_amount_yi"] == 29.9993
    assert latest["executed_shares_wan"] == 218.86
    assert latest["finish_date"] == "2026-05-27"
    assert latest["objective"].startswith("为维护公司")
    older = payload["buybacks"][1]
    assert older["executed_amount_yi"] == 59.9999


def test_corporate_buyback_window_filters_stale_plans(monkeypatch):
    monkeypatch.setattr(
        a_stock,
        "_em_get",
        lambda *a, **k: _Response(
            _envelope(
                [
                    _buyback_row("2019-04-03", progress="005"),
                    _buyback_row("2025-11-06"),
                ]
            )
        ),
    )
    monkeypatch.setattr(a_stock, "_today", lambda: a_stock.date(2026, 9, 10))
    payload = _result_payload(a_stock.get_corporate_buyback("600519"))
    assert payload["buyback_count"] == 1
    assert payload["buybacks"][0]["announced_date"] == "2025-11-06"


def test_corporate_buyback_caps_rows_at_the_bounded_limit(monkeypatch):
    rows = [
        _buyback_row(f"2026-0{index}-1{index}", progress="004") for index in range(1, 8)
    ]
    monkeypatch.setattr(a_stock, "_em_get", lambda *a, **k: _Response(_envelope(rows)))
    monkeypatch.setattr(a_stock, "_today", lambda: a_stock.date(2026, 9, 10))
    payload = _result_payload(a_stock.get_corporate_buyback("600519"))
    assert payload["buyback_count"] == a_stock._BUYBACK_MAX_ROWS == 5


def test_corporate_buyback_unknown_progress_code_falls_back_to_raw(monkeypatch):
    monkeypatch.setattr(
        a_stock,
        "_em_get",
        lambda *a, **k: _Response(_envelope([_buyback_row("2025-11-06", progress="099")])),
    )
    monkeypatch.setattr(a_stock, "_today", lambda: a_stock.date(2026, 9, 10))
    payload = _result_payload(a_stock.get_corporate_buyback("600519"))
    assert payload["buybacks"][0]["progress"] == "099"


def test_corporate_buyback_normal_empty_and_structure_failures_are_explicit(monkeypatch):
    monkeypatch.setattr(
        a_stock,
        "_em_get",
        lambda *a, **k: _Response(
            {"result": None, "code": 9201, "message": "返回数据为空"}
        ),
    )
    raw = a_stock.get_corporate_buyback("601398")
    assert raw.startswith("[正常空]")
    assert _result_payload(raw)["status"] == "normal_empty"

    monkeypatch.setattr(
        a_stock,
        "_em_get",
        lambda *a, **k: _Response(
            {"result": None, "code": 9501, "message": "报表配置不存在"}
        ),
    )
    raw = a_stock.get_corporate_buyback("601398")
    assert raw.startswith("[数据缺失]")
    assert _result_payload(raw)["status"] == "failed_structure"

    monkeypatch.setattr(
        a_stock,
        "_em_get",
        lambda *a, **k: _Response(_envelope([{"DIM_SCODE": "600519"}])),
    )
    raw = a_stock.get_corporate_buyback("600519")
    assert _result_payload(raw)["status"] == "failed_structure"


def test_corporate_buyback_network_failure_is_explicit(monkeypatch):
    def _raise_timeout(*args, **kwargs):
        raise TimeoutError("boom")

    monkeypatch.setattr(a_stock, "_em_get", _raise_timeout)
    raw = a_stock.get_corporate_buyback("600519")
    assert _result_payload(raw)["status"] == "failed_network"


def test_corporate_buyback_bse_code_passes_through(monkeypatch):
    calls = []

    def fake_em_get(url, params=None, **kwargs):
        calls.append(params)
        return _Response({"result": None, "code": 9201, "message": "返回数据为空"})

    monkeypatch.setattr(a_stock, "_em_get", fake_em_get)
    a_stock.get_corporate_buyback("920066")
    assert calls[0]["filter"] == '(DIM_SCODE="920066")'


@pytest.mark.parametrize("ticker", ["AAPL", "00700", "60051", ""])
def test_corporate_buyback_rejects_non_a_share_input(ticker):
    raw = a_stock.get_corporate_buyback(ticker)
    assert raw.startswith("Invalid ticker")
    assert _result_payload(raw)["status"] == "invalid_input"
