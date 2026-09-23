"""Offline contract tests for ETF/fund distribution actions."""

from __future__ import annotations

import json

import chstockdata
import chstockdata.a_stock as a_stock
from chstockdata import corporate_actions as ca


class _Response:
    def __init__(self, *, payload=None, text=""):
        self._payload = payload
        self.text = text

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def _distribution_html() -> str:
    return """
    <table class="w782 comm cfxq">
      <thead><tr><th>年份</th><th>权益登记日</th><th>除息日</th>
        <th>每10份分红</th><th>分红发放日</th></tr></thead>
      <tbody>
        <tr><td>2022年</td><td>2022-01-18</td><td>2022-01-19</td>
          <td>每10份派现金0.7500元</td><td>2022-01-24</td></tr>
        <tr><td>2019年</td><td>2019-12-10</td><td>2019-12-11</td>
          <td>每10份派现金0.6200元</td><td>2019-12-16</td></tr>
      </tbody>
    </table>
    """


def _announcement_payload() -> dict:
    return {
        "Data": [
            {
                "FUNDCODE": "510300",
                "ID": "AN202201121539913641",
                "TITLE": "华泰柏瑞沪深300交易型开放式指数证券投资基金分红公告",
                "PUBLISHDATE": "2022-01-12T00:00:00",
                "PUBLISHDATEDesc": "2022-01-12",
            },
            {
                "FUNDCODE": "510300",
                "ID": "AN201912051371585727",
                "TITLE": "华泰柏瑞沪深300交易型开放式指数证券投资基金收益分配公告",
                "PUBLISHDATE": "2019-12-05T00:00:00",
                "PUBLISHDATEDesc": "2019-12-05",
            },
        ],
        "ErrCode": 0,
        "TotalCount": 2,
        "PageSize": 100,
        "PageIndex": 1,
    }


def test_fund_distribution_normalizes_records_and_keeps_announcement_dates():
    calls = []

    def fake_request(url, params=None, **kwargs):
        calls.append((url, params, kwargs))
        if url.endswith("/FHGG"):
            return _Response(payload=_announcement_payload())
        return _Response(text=_distribution_html())

    result = ca.get_fund_corporate_actions(
        "510300",
        "2015-01-01",
        "2022-12-31",
        as_of_date="2022-12-31",
        page=1,
        page_size=50,
        request_get=fake_request,
    )

    assert result["status"] == "success"
    assert result["coverage"] == "complete"
    assert len(result["items"]) == 2
    item = result["items"][0]
    assert item["source_identifier"] == "AN202201121539913641"
    assert item["source_identifier_kind"] == "provider_identifier"
    assert item["announcement_date"] == "2022-01-12"
    assert item["equity_record_date"] == "2022-01-18"
    assert item["ex_dividend_date"] == "2022-01-19"
    assert item["payment_date"] == "2022-01-24"
    assert item["cash_dividend"] == {
        "value": 0.75,
        "unit": "per_10_shares",
        "source_field": "每10份分红",
        "tax_basis": "unknown",
    }
    assert item["stock_dividend"] is None
    assert item["capital_reserve_transfer"] is None
    assert item["rights_issue"] is None
    assert calls[0][0].endswith("fhsp_510300.html")
    assert calls[1][0].endswith("/FHGG")


def test_fund_distribution_empty_table_is_normal_empty_without_announcement_request():
    calls = []

    def fake_request(url, params=None, **kwargs):
        calls.append(url)
        return _Response(
            text=(
                '<table class="w782 comm cfxq"><tbody>'
                '<tr><td colspan="5">暂无分红信息!</td></tr>'
                "</tbody></table>"
            )
        )

    result = ca.get_fund_corporate_actions(
        "159915",
        "2015-01-01",
        "2022-12-31",
        request_get=fake_request,
    )

    assert result["status"] == "normal_empty"
    assert result["coverage"] == "complete"
    assert result["items"] == []
    assert len(calls) == 1


def test_public_fund_distribution_adapter_preserves_empty_envelope(monkeypatch):
    monkeypatch.setattr(
        ca,
        "get_fund_corporate_actions",
        lambda code, start, end, **kwargs: {
            "status": "normal_empty",
            "coverage": "complete",
            "items": [],
            "source": "eastmoney_fund_f10",
            "fetched_at": "2026-09-17T00:00:00+00:00",
            "failure_kind": None,
            "error_summary": None,
        },
    )

    raw = a_stock.get_fund_corporate_actions(
        "159915", "2015-01-01", "2022-12-31", "2022-12-31"
    )

    assert raw.startswith("[正常空]")
    assert json.loads(raw[raw.find("{") :])["status"] == "normal_empty"


def test_release_version_is_040():
    assert chstockdata.__version__ == "0.4.0"
