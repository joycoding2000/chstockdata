"""Contract tests for DEC-P1-04 Eastmoney sell-side research summaries."""

from __future__ import annotations

import json

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


def _report(
    info_code: str | None,
    *,
    publish_date: str = "2026-09-01",
    institution: str = "示例证券",
    title: str = "盈利预测更新",
    rating: str = "买入",
    rating_change: str = "维持",
    eps_2026: float | None = 10.1,
    eps_2027: float | None = 11.2,
    eps_2028: float | None = 12.3,
):
    return {
        "infoCode": info_code,
        "publishDate": publish_date,
        "orgSName": institution,
        "title": title,
        "emRatingName": rating,
        "ratingChange": rating_change,
        "predictThisYearEps": eps_2026,
        "predictNextYearEps": eps_2027,
        "predictNextTwoYearEps": eps_2028,
        "industryName": "白酒",
        "pdfUrl": "https://example.invalid/report.pdf",
    }


def _result_payload(value: str):
    return json.loads(value[value.find("{") :])


def test_research_reports_filter_dedupe_and_aggregate_without_pdf(monkeypatch):
    calls = []
    payload = {
        "data": [
            _report("A"),
            _report("A", title="duplicate should not survive"),
            _report(None, publish_date="2026-08-20", institution="乙证券", title="fallback key"),
            _report("OLD", publish_date="2026-06-11", title="outside 90 days"),
            _report("FUTURE", publish_date="2026-09-11", title="future report"),
        ]
    }

    def fake_em_get(url, **kwargs):
        calls.append((url, kwargs))
        return _Response(payload)

    monkeypatch.setattr(a_stock, "_em_get", fake_em_get)
    monkeypatch.setattr(a_stock, "_today", lambda: a_stock.date(2026, 9, 10))

    result = _result_payload(a_stock.get_research_reports("920001"))

    assert len(calls) == 1
    assert calls[0][0] == a_stock._EASTMONEY_RESEARCH_REPORT_URL
    assert calls[0][1]["params"]["code"] == "920001"
    assert calls[0][1]["params"]["pageNo"] == 1
    assert calls[0][1]["params"]["pageSize"] == 10
    assert calls[0][1]["params"] == {
        "code": "920001",
        "beginTime": "2026-06-13",
        "endTime": "2026-09-10",
        "pageNo": 1,
        "pageSize": 10,
        "qType": "0",
        "industryCode": "*",
        "industry": "*",
        "rating": "*",
        "ratingChange": "*",
        "fields": "",
        "orgCode": "",
        "rcode": "",
        "p": 1,
        "pageNum": 1,
        "pageNumber": 1,
    }
    assert result["status"] == "success"
    assert result["as_of_date"] == "2026-09-10"
    assert result["window_days"] == 90
    assert result["report_count"] == 2
    assert result["institution_count"] == 2
    assert result["rating_distribution"] == {"买入": 2}
    assert result["rating_change_distribution"] == {"维持": 2}
    assert result["eps_forecasts"]["2026"] == {
        "sample_count": 2,
        "median": 10.1,
        "min": 10.1,
        "max": 10.1,
    }
    assert [item["info_code"] for item in result["recent_reports"]] == ["A", None]
    assert "pdf" not in json.dumps(result, ensure_ascii=False).lower()


def test_research_reports_preserve_missing_values_and_normal_empty(monkeypatch):
    monkeypatch.setattr(
        a_stock,
        "_em_get",
        lambda *args, **kwargs: _Response({"data": []}),
    )
    empty = _result_payload(a_stock.get_research_reports("600519"))
    assert empty["status"] == "normal_empty"
    assert empty["report_count"] == 0
    assert empty["recent_reports"] == []

    monkeypatch.setattr(
        a_stock,
        "_em_get",
        lambda *args, **kwargs: _Response(
            {"data": [_report("MISSING", rating="", rating_change="", eps_2026=None, eps_2027=None, eps_2028=None)]}
        ),
    )
    partial = _result_payload(a_stock.get_research_reports("600519"))
    report = partial["recent_reports"][0]
    assert report["rating"] is None
    assert report["rating_change"] is None
    assert report["eps"] == {"2026": None, "2027": None, "2028": None}
    assert partial["eps_forecasts"] == {}


def test_research_reports_fail_closed_for_request_json_and_structure_errors(monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError("network unavailable")

    monkeypatch.setattr(a_stock, "_em_get", broken)
    assert "failed_network" in a_stock.get_research_reports("600519")

    monkeypatch.setattr(
        a_stock,
        "_em_get",
        lambda *args, **kwargs: _Response({}, status_code=500),
    )
    assert "failed_network" in a_stock.get_research_reports("600519")

    monkeypatch.setattr(
        a_stock,
        "_em_get",
        lambda *args, **kwargs: _Response({}, json_error=ValueError("bad json")),
    )
    assert "failed_structure" in a_stock.get_research_reports("600519")

    monkeypatch.setattr(a_stock, "_em_get", lambda *args, **kwargs: _Response({"data": {}}))
    assert "failed_structure" in a_stock.get_research_reports("600519")


def test_research_reports_reject_invalid_ticker_before_request(monkeypatch):
    monkeypatch.setattr(
        a_stock,
        "_em_get",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not request")),
    )
    assert "invalid_input" in a_stock.get_research_reports("12345")


def test_eps_forecasts_use_each_report_publication_year(monkeypatch):
    """predictThisYearEps is relative to the report, not to the query date.

    A 90-day window spans a year boundary every Jan-Mar.  Labelling every
    report's "this year" with as_of.year both misattributed the previous year's
    forecast and mixed two fiscal years into one aggregate key.
    """
    payload = {
        "data": [
            _report("DEC", publish_date="2025-12-20", eps_2026=10.0, eps_2027=11.0, eps_2028=12.0),
            _report("JAN", publish_date="2026-01-10", eps_2026=20.0, eps_2027=21.0, eps_2028=22.0),
        ]
    }

    monkeypatch.setattr(a_stock, "_em_get", lambda url, **kwargs: _Response(payload))
    monkeypatch.setattr(a_stock, "_today", lambda: a_stock.date(2026, 1, 15))

    result = _result_payload(a_stock.get_research_reports("600519"))

    assert result["report_count"] == 2
    # The December report's "this year" is 2025; the January report's is 2026.
    assert set(result["eps_forecasts"]) == {"2025", "2026", "2027", "2028"}
    assert result["eps_forecasts"]["2025"]["median"] == 10.0
    assert result["eps_forecasts"]["2025"]["sample_count"] == 1
    assert result["eps_forecasts"]["2026"] == {
        "sample_count": 2,
        "median": 15.5,
        "min": 11.0,
        "max": 20.0,
    }
    assert result["eps_forecasts"]["2028"]["median"] == 22.0
    published = {item["info_code"]: item for item in result["recent_reports"]}
    assert published["DEC"]["eps"]["2025"] == 10.0
    assert published["JAN"]["eps"]["2026"] == 20.0
