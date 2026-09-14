"""Contract tests for DEC-P1-10 Eastmoney earnings pre-announcements."""

from __future__ import annotations

import json

import pytest

from chstockdata import a_stock


class _Response:
    def __init__(self, payload, *, status_code: int = 200, json_error: Exception | None = None):
        self.payload = payload
        self.status_code = status_code
        self.json_error = json_error

    def raise_for_status(self):
        if self.status_code >= 400:
            raise a_stock._requests.exceptions.HTTPError(f"status={self.status_code}")

    def json(self):
        if self.json_error:
            raise self.json_error
        return self.payload


def _row(
    *,
    report_date: str = "2024-12-31",
    notice_date: str = "2025-01-03",
    forecast_type: str = "略增",
    lower: float | None = 85700000000,
    upper: float | None = 85700000000,
    content: str | None = "预计2024年1-12月归属于上市公司股东的净利润盈利约:8,570,000万元。",
):
    return {
        "SECURITY_CODE": "600519",
        "SECURITY_NAME_ABBR": "贵州茅台",
        "NOTICE_DATE": f"{notice_date} 00:00:00" if notice_date else notice_date,
        "REPORTDATE": f"{report_date} 00:00:00" if report_date else report_date,
        "FORECASTL": lower,
        "FORECASTT": upper,
        "INCREASEL": 14.67,
        "INCREASET": 14.67,
        "FORECASTCONTENT": content,
        "CHANGEREASONDSCRPT": None,
        "FORECASTTYPE": forecast_type,
        "YEAREARLIER": 74734071550.75,
        "ISLATEST": "T",
    }


def _result_payload(value: str):
    return json.loads(value[value.find("{") :])


def test_earnings_forecast_parses_sorts_and_dedupes(monkeypatch):
    calls = []
    payload = {
        "result": {
            "pages": 1,
            "count": 3,
            "data": [
                _row(),
                _row(content="duplicate row must not survive"),
                _row(report_date="2023-12-31", notice_date="2023-12-30"),
            ],
        },
        "success": True,
    }

    def fake_em_get(url, **kwargs):
        calls.append((url, kwargs))
        return _Response(payload)

    monkeypatch.setattr(a_stock, "_em_get", fake_em_get)
    monkeypatch.setattr(a_stock, "_today", lambda: a_stock.date(2026, 9, 10))

    result = _result_payload(a_stock.get_earnings_forecast("600519"))

    assert len(calls) == 1
    assert calls[0][0] == a_stock._DATACENTER_URL
    params = calls[0][1]["params"]
    assert params["reportName"] == "RPT_PUBLIC_OP_PREDICT"
    assert params["filter"] == '(SECURITY_CODE="600519")'
    assert params["sortColumns"] == "NOTICE_DATE"
    assert params["pageSize"] == a_stock._EARNINGS_FORECAST_PAGE_SIZE
    assert result["status"] == "success"
    assert result["source"] == "Eastmoney datacenter RPT_PUBLIC_OP_PREDICT"
    assert result["window_years"] == a_stock._EARNINGS_FORECAST_WINDOW_YEARS
    assert result["forecast_count"] == 2
    assert result["latest_report_date"] == "2024-12-31"
    # Sorted most recent report period first; amounts projected to 亿元.
    assert [item["report_date"] for item in result["forecasts"]] == ["2024-12-31", "2023-12-31"]
    latest = result["forecasts"][0]
    assert latest["notice_date"] == "2025-01-03"
    assert latest["forecast_type"] == "略增"
    assert latest["profit_lower_yi"] == 857.0
    assert latest["profit_upper_yi"] == 857.0
    assert latest["increase_lower_pct"] == 14.67
    assert latest["prior_year_profit_yi"] == round(74734071550.75 / 100_000_000, 4)
    assert latest["content"].startswith("预计2024年")


def test_earnings_forecast_window_filters_stale_rows(monkeypatch):
    """A decades-old forecast must not read as current guidance (window filter)."""
    payload = {
        "result": {
            "data": [
                _row(report_date="2024-12-31", notice_date="2025-01-03"),
                _row(report_date="2009-12-31", notice_date="2010-01-27"),
            ]
        },
        "success": True,
    }
    monkeypatch.setattr(a_stock, "_em_get", lambda url, **kwargs: _Response(payload))
    monkeypatch.setattr(a_stock, "_today", lambda: a_stock.date(2026, 9, 10))
    result = _result_payload(a_stock.get_earnings_forecast("601398"))
    assert result["forecast_count"] == 1
    assert result["forecasts"][0]["report_date"] == "2024-12-31"


def test_earnings_forecast_zero_amount_placeholder_is_not_a_fake_disclosure(monkeypatch):
    """Provider fills 0 where no absolute amount was disclosed; keep it None."""
    payload = {
        "result": {
            "data": [
                _row(lower=0, upper=0, content="预计净利润同比增长50%以上。"),
            ]
        },
        "success": True,
    }
    monkeypatch.setattr(a_stock, "_em_get", lambda url, **kwargs: _Response(payload))
    monkeypatch.setattr(a_stock, "_today", lambda: a_stock.date(2026, 9, 10))
    result = _result_payload(a_stock.get_earnings_forecast("600519"))
    row = result["forecasts"][0]
    assert row["profit_lower_yi"] is None
    assert row["profit_upper_yi"] is None
    assert row["increase_upper_pct"] == 14.67


def test_earnings_forecast_normal_empty_is_not_a_failure(monkeypatch):
    monkeypatch.setattr(
        a_stock, "_em_get", lambda url, **kwargs: _Response({"result": {"data": []}, "success": True})
    )
    raw = a_stock.get_earnings_forecast("600519")
    assert raw.startswith("[正常空]")
    result = _result_payload(raw)
    assert result["status"] == "normal_empty"
    assert result["forecast_count"] == 0
    assert result["forecasts"] == []
    assert result["latest_report_date"] is None


def test_earnings_forecast_datacenter_null_result_with_empty_code_is_normal_empty(monkeypatch):
    """No pre-announcement is the common case: datacenter returns result=null +
    code=9201 (返回数据为空); it must stay normal_empty, never 数据缺失."""
    monkeypatch.setattr(
        a_stock,
        "_em_get",
        lambda url, **kwargs: _Response(
            {"version": None, "result": None, "success": False, "message": "返回数据为空", "code": 9201}
        ),
    )
    raw = a_stock.get_earnings_forecast("600519")
    assert raw.startswith("[正常空]")
    assert _result_payload(raw)["status"] == "normal_empty"


def test_earnings_forecast_null_result_with_other_code_is_structure_failure(monkeypatch):
    monkeypatch.setattr(
        a_stock,
        "_em_get",
        lambda url, **kwargs: _Response(
            {"version": None, "result": None, "success": False,
             "message": "报表配置不存在,RPT_WRONG", "code": 9501}
        ),
    )
    assert _result_payload(a_stock.get_earnings_forecast("600519"))["status"] == "failed_structure"


def test_earnings_forecast_bse_code_passes_through(monkeypatch):
    calls = []

    def fake_em_get(url, **kwargs):
        calls.append(kwargs)
        return _Response({"result": {"data": []}, "success": True})

    monkeypatch.setattr(a_stock, "_em_get", fake_em_get)
    a_stock.get_earnings_forecast("920066")
    assert calls[0]["params"]["filter"] == '(SECURITY_CODE="920066")'


def test_earnings_forecast_caps_rows_at_the_bounded_limit(monkeypatch):
    rows = [
        _row(
            report_date=f"2026-06-{day:02d}",
            notice_date=f"2026-08-{day:02d}",
        )
        for day in range(1, 11)
    ]
    monkeypatch.setattr(
        a_stock, "_em_get", lambda url, **kwargs: _Response({"result": {"data": rows}, "success": True})
    )
    monkeypatch.setattr(a_stock, "_today", lambda: a_stock.date(2026, 9, 10))
    result = _result_payload(a_stock.get_earnings_forecast("600519"))
    assert result["forecast_count"] == a_stock._EARNINGS_FORECAST_MAX_ROWS


@pytest.mark.parametrize(
    "payload,expected",
    [
        ({"success": False, "result": None}, "failed_structure"),
        ({"result": {"data": "not-a-list"}}, "failed_structure"),
        ({"result": {"data": [_row(report_date="")]}}, "failed_structure"),
        ({"result": {"data": [_row(forecast_type="")]}}, "failed_structure"),
    ],
)
def test_earnings_forecast_structure_failures_are_explicit(monkeypatch, payload, expected):
    monkeypatch.setattr(a_stock, "_em_get", lambda url, **kwargs: _Response(payload))
    assert _result_payload(a_stock.get_earnings_forecast("600519"))["status"] == expected


def test_earnings_forecast_network_and_json_failures_are_explicit(monkeypatch):
    def raise_connection(url, **kwargs):
        raise a_stock._requests.exceptions.ConnectionError("boom")

    monkeypatch.setattr(a_stock, "_em_get", raise_connection)
    assert _result_payload(a_stock.get_earnings_forecast("600519"))["status"] == "failed_network"

    monkeypatch.setattr(
        a_stock,
        "_em_get",
        lambda url, **kwargs: _Response({}, json_error=json.JSONDecodeError("bad", "<", 0)),
    )
    assert _result_payload(a_stock.get_earnings_forecast("600519"))["status"] == "failed_structure"


@pytest.mark.parametrize("ticker", ["AAPL", "00700", "60051", ""])
def test_earnings_forecast_rejects_non_a_share_input(ticker):
    assert _result_payload(a_stock.get_earnings_forecast(ticker))["status"] == "invalid_input"
