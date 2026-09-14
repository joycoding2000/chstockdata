"""Contract tests for the DEC-P1-26 macro data function.

Covers ``get_macro_indicators`` (RPT_ECONOMY_PMI/CPI/PPI/GDP).  All provider
access is mocked at ``a_stock._em_get``; no network is touched.  The
live-confirmed field contracts (2026-09-13 production ``_em_get()``: only
REPORT_DATE + TIME as period metadata, no per-row publication date; GDP's
provider spelling ``DOMESTICL_PRODUCT_BASE``) are pinned with synthetic rows.
"""

from __future__ import annotations

import inspect
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


def _envelope(rows: list[dict], *, count: int | None = None) -> dict:
    return {
        "status": 0,
        "code": 0,
        "message": "ok",
        "result": {"data": rows, "count": len(rows) if count is None else count},
    }


def _result_payload(value: str) -> dict:
    return json.loads(value[value.find("{") :])


def _pmi_row(day: str, *, index: float = 49.8, label: str = "2026年8月份") -> dict:
    return {
        "REPORT_DATE": f"{day} 00:00:00",
        "TIME": label,
        "MAKE_INDEX": index,
        "MAKE_SAME": 0.8097166,
        "NMAKE_INDEX": 49,
        "NMAKE_SAME": -2.58449304,
    }


def _cpi_row(day: str, *, same: float = 0.8, label: str = "2026年8月份") -> dict:
    return {
        "REPORT_DATE": f"{day} 00:00:00",
        "TIME": label,
        "NATIONAL_SAME": same,
        "NATIONAL_BASE": 100.8,
        "NATIONAL_SEQUENTIAL": 0.4,
        "NATIONAL_ACCUMULATE": 100.9,
        "CITY_SAME": 0.8,
        "CITY_BASE": 100.8,
        "CITY_SEQUENTIAL": 0.4,
        "CITY_ACCUMULATE": 100.9,
        "RURAL_SAME": 0.7,
        "RURAL_BASE": 100.7,
        "RURAL_SEQUENTIAL": 0.4,
        "RURAL_ACCUMULATE": 100.7,
    }


def _ppi_row(day: str, *, same: float = 3.8, label: str = "2026年8月份") -> dict:
    return {
        "REPORT_DATE": f"{day} 00:00:00",
        "TIME": label,
        "BASE": 103.8,
        "BASE_SAME": same,
        "BASE_ACCUMULATE": 102,
    }


def _gdp_row(day: str, *, total: float = 695704.0, label: str = "2026年第1-2季度") -> dict:
    return {
        "REPORT_DATE": f"{day} 00:00:00",
        "TIME": label,
        "DOMESTICL_PRODUCT_BASE": total,
        "FIRST_PRODUCT_BASE": 31521.8,
        "FIRST_SAME": 3.7,
        "SECOND_PRODUCT_BASE": 250472.9,
        "SECOND_SAME": 3.9,
        "THIRD_PRODUCT_BASE": 413709.2,
        "THIRD_SAME": 5.2,
        "SUM_SAME": 4.7,
    }


def _dispatch(rows_by_report, *, count_by_report=None):
    calls = []

    def fake_em_get(url, params=None, **kwargs):
        report = params["reportName"]
        calls.append((report, params))
        if report not in rows_by_report:
            raise a_stock._requests.ConnectionError(f"no fixture for {report}")
        rows = rows_by_report[report]
        count = (count_by_report or {}).get(report)
        return _Response(_envelope(rows, count=count))

    return fake_em_get, calls


def test_macro_parses_four_indicators_periods_and_labels(monkeypatch):
    fake_em_get, calls = _dispatch(
        {
            "RPT_ECONOMY_PMI": [_pmi_row("2026-07-01"), _pmi_row("2026-08-01")],
            "RPT_ECONOMY_CPI": [_cpi_row("2026-08-01")],
            "RPT_ECONOMY_PPI": [_ppi_row("2026-08-01")],
            "RPT_ECONOMY_GDP": [_gdp_row("2026-06-01")],
        },
        count_by_report={"RPT_ECONOMY_PMI": 224, "RPT_ECONOMY_GDP": 82},
    )
    monkeypatch.setattr(a_stock, "_em_get", fake_em_get)
    payload = _result_payload(a_stock.get_macro_indicators())

    assert payload["status"] == "success"
    assert payload["source"] == "Eastmoney datacenter RPT_ECONOMY_PMI/CPI/PPI/GDP"
    assert payload["as_of_date"]
    assert "数据所属期" in payload["period_note"]
    assert "未采集" in payload["boundary"]
    assert payload["failed_indicators"] == {}
    assert payload["empty_indicators"] == []

    indicators = {item["indicator"]: item for item in payload["indicators"]}
    assert list(indicators) == ["pmi", "cpi", "ppi", "gdp"]
    assert indicators["pmi"]["latest_period"] == "2026-08-01"
    assert indicators["pmi"]["provider_count"] == 224
    assert indicators["pmi"]["periods"][0]["period_label"] == "2026年8月份"
    assert indicators["pmi"]["periods"][0]["values"]["make_index"] == 49.8
    assert indicators["pmi"]["field_labels"]["make_index"].startswith("制造业PMI")
    assert indicators["cpi"]["periods"][0]["values"]["national_same"] == 0.8
    assert indicators["ppi"]["periods"][0]["values"]["base_same"] == 3.8
    assert indicators["gdp"]["periods"][0]["values"]["domestic_product_base"] == 695704.0
    assert indicators["gdp"]["periods"][0]["values"]["sum_same"] == 4.7

    # Every request is one bounded, REPORT_DATE-descending, _em_get() call.
    assert {report for report, _params in calls} == {
        "RPT_ECONOMY_PMI",
        "RPT_ECONOMY_CPI",
        "RPT_ECONOMY_PPI",
        "RPT_ECONOMY_GDP",
    }
    for _report, params in calls:
        assert params["columns"] == "ALL"
        assert params["sortColumns"] == "REPORT_DATE"
        assert params["sortTypes"] == "-1"
        assert params["pageSize"] <= a_stock._MACRO_MAX_PERIODS


def test_macro_sorts_and_bounds_periods(monkeypatch):
    rows = [
        _pmi_row(f"2026-{month:02d}-01", index=40.0 + month, label=f"2026年{month}月份")
        for month in range(1, 13)
    ]
    fake_em_get, _calls = _dispatch(
        {
            "RPT_ECONOMY_PMI": list(reversed(rows)),
            "RPT_ECONOMY_CPI": [_cpi_row("2026-08-01")],
            "RPT_ECONOMY_PPI": [_ppi_row("2026-08-01")],
            "RPT_ECONOMY_GDP": [_gdp_row("2026-06-01")],
        }
    )
    monkeypatch.setattr(a_stock, "_em_get", fake_em_get)
    payload = _result_payload(a_stock.get_macro_indicators())

    pmi = next(item for item in payload["indicators"] if item["indicator"] == "pmi")
    assert len(pmi["periods"]) == a_stock._MACRO_MAX_PERIODS
    assert pmi["periods"][0]["report_date"] == "2026-12-01"
    dates = [item["report_date"] for item in pmi["periods"]]
    assert dates == sorted(dates, reverse=True)


def test_macro_partial_network_failure_is_disclosed_not_masked(monkeypatch):
    def fake_em_get(url, params=None, **kwargs):
        if params["reportName"] == "RPT_ECONOMY_GDP":
            raise a_stock._requests.ConnectionError("connection reset")
        return _Response(_envelope([_pmi_row("2026-08-01")]))

    monkeypatch.setattr(a_stock, "_em_get", fake_em_get)
    payload = _result_payload(a_stock.get_macro_indicators())

    assert payload["status"] == "success"
    assert payload["failed_indicators"] == {"gdp": "failed_network"}
    gdp = next(item for item in payload["indicators"] if item["indicator"] == "gdp")
    assert gdp["status"] == "failed_network"
    assert gdp["periods"] == []
    assert gdp["latest_period"] is None


def test_macro_all_network_failures_are_failed_network(monkeypatch):
    def boom(*args, **kwargs):
        raise a_stock._requests.ConnectionError("connection reset")

    monkeypatch.setattr(a_stock, "_em_get", boom)
    raw = a_stock.get_macro_indicators()
    assert raw.startswith("[数据缺失]")
    payload = _result_payload(raw)
    assert payload["status"] == "failed_network"
    assert set(payload["failed_indicators"]) == {"pmi", "cpi", "ppi", "gdp"}


def test_macro_structure_failure_takes_precedence_over_network(monkeypatch):
    def fake_em_get(url, params=None, **kwargs):
        if params["reportName"] == "RPT_ECONOMY_GDP":
            return _Response({"result": None, "code": 9501, "message": "gone"})
        raise a_stock._requests.ConnectionError("connection reset")

    monkeypatch.setattr(a_stock, "_em_get", fake_em_get)
    raw = a_stock.get_macro_indicators()
    assert raw.startswith("[数据缺失]")
    payload = _result_payload(raw)
    assert payload["status"] == "failed_structure"
    assert payload["failed_indicators"]["gdp"] == "failed_structure"


def test_macro_null_result_is_normal_empty_not_failure(monkeypatch):
    monkeypatch.setattr(
        a_stock,
        "_em_get",
        lambda *a, **k: _Response({"result": None, "code": 9201, "message": "空"}),
    )
    raw = a_stock.get_macro_indicators()
    assert raw.startswith("[正常空]")
    payload = _result_payload(raw)
    assert payload["status"] == "normal_empty"
    assert set(payload["empty_indicators"]) == {"pmi", "cpi", "ppi", "gdp"}
    assert all(item["periods"] == [] for item in payload["indicators"])


def test_macro_rows_without_report_date_fail_closed(monkeypatch):
    def fake_em_get(url, params=None, **kwargs):
        if params["reportName"] == "RPT_ECONOMY_PMI":
            return _Response(_envelope([{"TIME": "2026年8月份", "MAKE_INDEX": 49.8}]))
        raise a_stock._requests.ConnectionError("connection reset")

    monkeypatch.setattr(a_stock, "_em_get", fake_em_get)
    payload = _result_payload(a_stock.get_macro_indicators())
    assert payload["status"] == "failed_structure"
    assert payload["failed_indicators"]["pmi"] == "failed_structure"
    assert "REPORT_DATE" in payload["indicators"][0]["error"]


def test_macro_takes_no_market_arguments():
    params = inspect.signature(a_stock.get_macro_indicators).parameters
    assert params == {}
