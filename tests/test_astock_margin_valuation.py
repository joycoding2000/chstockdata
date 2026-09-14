"""Contract tests for the DEC-P1-24/25 data functions.

Covers ``get_margin_trading`` (RPTA_WEB_RZRQ_GGMX) and
``get_valuation_history`` (RPT_VALUEANALYSIS_DET).  All provider access is
mocked at ``a_stock._em_get``; no network is touched.  The live-confirmed
field shapes and unit calibrations (600519 on 2026-09-11, 920066 for BSE,
8.7-year history depth) are pinned with synthetic rows.
"""

from __future__ import annotations

import json
from datetime import date, timedelta

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


# ---- get_margin_trading ----


def _margin_row(
    day: str,
    *,
    rzye: float = 17_186_171_706.0,
    rqye: float = 0.0,
    rzrqye: float | None = None,
    rzjme: float = -34_104_703.0,
    rqyl: float = 128_948.0,
    rqmcl: float = 6_400.0,
    market: str = "融资融券_沪证",
    secname: str = "贵州茅台",
) -> dict:
    return {
        "DATE": f"{day} 00:00:00",
        "SCODE": "600519",
        "SECNAME": secname,
        "MARKET": market,
        "RZYE": rzye,
        "RQYE": rqye,
        "RZRQYE": rzye + rqye if rzrqye is None else rzrqye,
        "RZMRE": 291_614_311.0,
        "RZCHE": 325_719_014.0,
        "RZJME": rzjme,
        "RQYL": rqyl,
        "RQMCL": rqmcl,
        "RZYEZB": 1.07814234,
        "RZMRE3D": 792_027_450.0,
        "RZMRE5D": 1_204_842_358.0,
        "RZMRE10D": 2_483_376_350.0,
        "RZJME3D": 94_959_065.0,
        "RZJME5D": 151_429_382.0,
        "RZJME10D": -164_874_616.0,
        "SPJ": 1275.16,
        "ZDF": -0.7758,
    }


def test_margin_trading_parses_latest_rows_and_provider_units(monkeypatch):
    calls = []

    def fake_em_get(url, params=None, **kwargs):
        calls.append((url, params))
        # Provider returns oldest-last on purpose: the function must sort by
        # the parsed DATE itself.
        return _Response(
            _envelope(
                [
                    _margin_row("2026-09-09", rzye=17_000_000_000.0),
                    _margin_row("2026-09-11"),
                ]
            )
        )

    monkeypatch.setattr(a_stock, "_em_get", fake_em_get)
    raw = a_stock.get_margin_trading("600519")
    payload = _result_payload(raw)

    url, params = calls[0]
    assert url == a_stock._DATACENTER_URL
    assert params["reportName"] == "RPTA_WEB_RZRQ_GGMX"
    assert params["filter"] == '(scode="600519")'
    assert params["sortColumns"] == "DATE"
    assert params["sortTypes"] == "-1"

    assert payload["status"] == "success"
    assert payload["latest_date"] == "2026-09-11"
    assert payload["market"] == "融资融券_沪证"
    assert payload["name"] == "贵州茅台"
    assert payload["source"] == "Eastmoney datacenter RPTA_WEB_RZRQ_GGMX"

    latest = payload["records"][0]
    assert latest["date"] == "2026-09-11"
    assert latest["financing_balance_yi"] == pytest.approx(171.8617)
    assert latest["securities_lending_balance_yi"] == 0.0
    assert latest["financing_net_buy_yi"] == pytest.approx(-0.341)
    assert latest["securities_lending_volume_wan_shares"] == pytest.approx(12.8948)
    assert latest["financing_buy_10d_yi"] == pytest.approx(24.8338)
    assert latest["financing_net_buy_10d_yi"] == pytest.approx(-1.6487)
    assert latest["financing_balance_pct_of_float"] == pytest.approx(1.07814234)
    assert latest["close"] == pytest.approx(1275.16)
    assert "T+1" in payload["boundary"]


def test_margin_trading_zero_lending_balance_is_kept_as_zero(monkeypatch):
    # The provider serializes a real zero lending balance; it must not be
    # normalized away as if the field were missing.
    monkeypatch.setattr(
        a_stock,
        "_em_get",
        lambda *a, **k: _Response(
            _envelope([_margin_row("2026-09-10", rqye=0.0, rqyl=0.0, rqmcl=0.0)])
        ),
    )
    payload = _result_payload(a_stock.get_margin_trading("920066"))
    assert payload["records"][0]["securities_lending_balance_yi"] == 0.0
    assert payload["records"][0]["securities_lending_volume_wan_shares"] == 0.0
    assert payload["records"][0]["securities_lending_sell_wan_shares"] == 0.0


def test_margin_trading_bounds_records_to_max_rows(monkeypatch):
    rows = [
        _margin_row((date(2026, 9, 11) - timedelta(days=offset)).isoformat())
        for offset in range(15)
    ]
    monkeypatch.setattr(
        a_stock, "_em_get", lambda *a, **k: _Response(_envelope(rows))
    )
    payload = _result_payload(a_stock.get_margin_trading("600519"))
    assert len(payload["records"]) == a_stock._MARGIN_MAX_ROWS
    assert payload["records"][0]["date"] == "2026-09-11"
    assert payload["records"][-1]["date"] == "2026-09-02"


def test_margin_trading_null_result_is_normal_empty_not_failure(monkeypatch):
    monkeypatch.setattr(
        a_stock,
        "_em_get",
        lambda *a, **k: _Response(
            {"result": None, "code": 9201, "message": "返回数据为空"}
        ),
    )
    raw = a_stock.get_margin_trading("600001")
    assert raw.startswith("[正常空]")
    payload = _result_payload(raw)
    assert payload["status"] == "normal_empty"
    assert payload["records"] == []
    assert payload["latest_date"] is None
    assert "不是无杠杆风险的证据" in payload["boundary"]


def test_margin_trading_structure_error_fails_closed(monkeypatch):
    monkeypatch.setattr(
        a_stock,
        "_em_get",
        lambda *a, **k: _Response({"result": None, "code": 9501, "message": "gone"}),
    )
    raw = a_stock.get_margin_trading("600519")
    assert raw.startswith("[数据缺失]")
    assert _result_payload(raw)["status"] == "failed_structure"


def test_margin_trading_network_error_is_failed_network(monkeypatch):
    def boom(*a, **k):
        raise a_stock._requests.ConnectionError("connection reset")

    monkeypatch.setattr(a_stock, "_em_get", boom)
    payload = _result_payload(a_stock.get_margin_trading("600519"))
    assert payload["status"] == "failed_network"


def test_margin_trading_invalid_ticker_is_recoverable(monkeypatch):
    raw = a_stock.get_margin_trading("AAPL")
    assert raw.startswith("Invalid ticker")
    assert _result_payload(raw)["status"] == "invalid_input"


# ---- get_valuation_history ----


def _valuation_row(
    day: str,
    pe_ttm: float | None,
    *,
    pb_mrq: float | None = 6.0,
    close: float = 1275.16,
) -> dict:
    return {
        "SECURITY_CODE": "600519",
        "SECURITY_NAME_ABBR": "贵州茅台",
        "TRADE_DATE": f"{day} 00:00:00",
        "CLOSE_PRICE": close,
        "PE_TTM": pe_ttm,
        "PE_LAR": 19.36,
        "PB_MRQ": pb_mrq,
        "PS_TTM": 9.2,
        "PCF_OCF_TTM": 13.38,
        "PEG_CAR": -4.72,
        "TOTAL_MARKET_CAP": 1_594_054_054_331.16,
        "NOTLIMITED_MARKETCAP_A": 1_594_054_054_331.16,
        "TOTAL_SHARES": 1_250_081_601,
        "FREE_SHARES_A": 1_250_081_601,
        "BOARD_NAME": "白酒Ⅱ",
    }


def _monthly_valuation_rows(count: int = 200, latest: str = "2026-09-11"):
    """Newest-first rows with strictly increasing PE towards the latest date."""
    latest_day = date.fromisoformat(latest)
    rows = []
    for index in range(count):
        day = (latest_day - timedelta(days=30 * index)).isoformat()
        rows.append(_valuation_row(day, float(count - index)))
    return rows


def test_valuation_history_computes_window_percentiles_and_quantiles(monkeypatch):
    rows = _monthly_valuation_rows()
    calls = []

    def fake_em_get(url, params=None, **kwargs):
        calls.append(params["pageNumber"])
        return _Response(_envelope(rows, count=len(rows)))

    monkeypatch.setattr(a_stock, "_em_get", fake_em_get)
    payload = _result_payload(a_stock.get_valuation_history("600519"))

    assert calls == [1]  # count reached on page 1; no extra request
    assert payload["status"] == "success"
    assert payload["latest_date"] == "2026-09-11"
    assert payload["as_of_date"] == "2026-09-11"
    assert payload["board_name"] == "白酒Ⅱ"
    assert payload["market_cap_yi"] == pytest.approx(15940.5405)
    assert payload["metrics"]["pe_ttm"] == pytest.approx(200.0)
    assert "估值" in payload["boundary"]

    pe = payload["percentiles"]["pe_ttm"]
    assert pe["latest"] == pytest.approx(200.0)
    all_window = pe["windows"]["all"]
    assert all_window["sample_count"] == 200
    assert all_window["percentile"] == 100.0
    # 200 monthly samples is a valid but sub-250-seed window.
    assert all_window["reliability"] == "limited_samples"
    assert all_window["window_start"] == rows[-1]["TRADE_DATE"][:10]
    assert pe["all_quantiles"]["p50"] == pytest.approx(100.5)

    latest_day = date.fromisoformat("2026-09-11")
    expected_3y = sum(
        1
        for item in rows
        if date.fromisoformat(item["TRADE_DATE"][:10])
        >= latest_day - timedelta(days=365 * 3)
    )
    assert pe["windows"]["3y"]["sample_count"] == expected_3y
    assert payload["history"]["fetched_rows"] == 200
    assert payload["history"]["provider_count"] == 200
    assert payload["history"]["truncated"] is False


def test_valuation_history_paginates_until_provider_count(monkeypatch):
    monkeypatch.setattr(a_stock, "_VALUATION_PAGE_SIZE", 2)
    monkeypatch.setattr(a_stock, "_VALUATION_MAX_PAGES", 3)
    monkeypatch.setattr(a_stock, "_VALUATION_MAX_ROWS", 100)
    pages = {
        1: [_valuation_row("2026-09-11", 30.0), _valuation_row("2026-09-10", 29.0)],
        2: [_valuation_row("2026-09-09", 28.0)],
    }
    calls = []

    def fake_em_get(url, params=None, **kwargs):
        page = params["pageNumber"]
        calls.append(page)
        return _Response(_envelope(pages.get(page, []), count=3))

    monkeypatch.setattr(a_stock, "_em_get", fake_em_get)
    payload = _result_payload(a_stock.get_valuation_history("600519"))

    assert calls == [1, 2]
    assert payload["history"]["fetched_rows"] == 3
    assert payload["history"]["sample_count"] == 3
    assert payload["history"]["truncated"] is False


def test_valuation_history_truncation_is_disclosed(monkeypatch):
    monkeypatch.setattr(a_stock, "_VALUATION_PAGE_SIZE", 2)
    monkeypatch.setattr(a_stock, "_VALUATION_MAX_ROWS", 2)
    rows = [_valuation_row("2026-09-11", 30.0), _valuation_row("2026-09-10", 29.0)]

    def fake_em_get(url, params=None, **kwargs):
        return _Response(_envelope(rows, count=5))

    monkeypatch.setattr(a_stock, "_em_get", fake_em_get)
    payload = _result_payload(a_stock.get_valuation_history("600519"))
    assert payload["history"]["provider_count"] == 5
    assert payload["history"]["fetched_rows"] == 2
    assert payload["history"]["truncated"] is True


def test_valuation_history_new_listing_discloses_insufficient_samples(monkeypatch):
    rows = [
        _valuation_row((date(2026, 9, 11) - timedelta(days=index)).isoformat(), 30.0)
        for index in range(10)
    ]
    monkeypatch.setattr(
        a_stock, "_em_get", lambda *a, **k: _Response(_envelope(rows, count=10))
    )
    payload = _result_payload(a_stock.get_valuation_history("920066"))

    window = payload["percentiles"]["pe_ttm"]["windows"]["all"]
    assert window["sample_count"] == 10
    assert window["percentile"] is None
    assert window["reliability"] == "insufficient_samples"
    assert "样本不足" in window["note"]


def test_valuation_history_non_positive_latest_value_makes_percentile_unavailable(
    monkeypatch,
):
    rows = _monthly_valuation_rows(count=120)
    rows[0] = _valuation_row("2026-09-11", -3.5)
    monkeypatch.setattr(
        a_stock, "_em_get", lambda *a, **k: _Response(_envelope(rows, count=120))
    )
    payload = _result_payload(a_stock.get_valuation_history("600519"))

    window = payload["percentiles"]["pe_ttm"]["windows"]["all"]
    assert window["percentile"] is None
    assert window["reliability"] == "unavailable"
    assert "非正" in window["note"]
    # PB stays computable from its own series.
    assert payload["percentiles"]["pb_mrq"]["windows"]["all"]["percentile"] == 100.0


def test_valuation_history_null_result_is_normal_empty(monkeypatch):
    monkeypatch.setattr(
        a_stock,
        "_em_get",
        lambda *a, **k: _Response({"result": None, "code": 9201, "message": "空"}),
    )
    raw = a_stock.get_valuation_history("600001")
    assert raw.startswith("[正常空]")
    payload = _result_payload(raw)
    assert payload["status"] == "normal_empty"
    assert payload["percentiles"] is None
    assert payload["history"]["fetched_rows"] == 0


def test_valuation_history_structure_error_fails_closed(monkeypatch):
    monkeypatch.setattr(
        a_stock,
        "_em_get",
        lambda *a, **k: _Response({"result": {"data": "not-a-list"}, "code": 0}),
    )
    raw = a_stock.get_valuation_history("600519")
    assert raw.startswith("[数据缺失]")
    assert _result_payload(raw)["status"] == "failed_structure"


def test_valuation_history_network_error_is_failed_network(monkeypatch):
    def boom(*a, **k):
        raise a_stock._requests.ConnectionError("connection reset")

    monkeypatch.setattr(a_stock, "_em_get", boom)
    payload = _result_payload(a_stock.get_valuation_history("600519"))
    assert payload["status"] == "failed_network"
