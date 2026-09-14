"""ETF 期权模块（新浪源）离线解析与失败闭合回归。

载荷样本为 2026-09-14 实测记录（50ETF 认购 2609 合约，CON_OP/CON_SO 全字段），
数值型断言直接引自实测值。
"""

from __future__ import annotations

import pytest

from chstockdata import etf_options
from chstockdata.vendor_errors import (
    VendorNetworkError,
    VendorNoDataError,
)

# 2026-09-14 实测 CON_OP_10010974（51 字段，前 46 位为真实载荷，尾部补足长度）
_TQUOTE_FIELDS = [
    "1", "0.0184", "0.0185", "0.0185", "448", "105232", "-21.61", "3.0000",
    "0.0236", "0.0190", "0.3198", "0.0001", "0.0189", "3", "0.0188", "111",
    "0.0187", "31", "0.0186", "7", "0.0185", "448", "0.0184", "1", "0.0182",
    "4", "0.0181", "15", "0.0180", "1", "0.0179", "2",
    "2026-09-14 15:00:00", "0", "E 00", "EBS", "510050", "50ETF购9月3000",
    "20.34", "0.0204", "0.0156", "67997", "12038859.00", "M", "0.0236", "C",
    "", "", "", "", "",
]
# 2026-09-14 实测 CON_SO_10010974（17 字段）
_GREEKS_FIELDS = [
    "50ETF购9月3000", "", "", "", "67997", "0.4155", "4.2572", "-0.7727",
    "0.1822", "0.1484", "0.0204", "0.0156", "510050C2609M03000", "3.0000",
    "0.0185", "0.0271", "M",
]


class _FakeResponse:
    def __init__(self, *, text="", content=None, status_code=200, json_payload=None):
        self.text = text
        self.content = content if content is not None else text.encode("utf-8")
        self.status_code = status_code
        self._json = json_payload

    def json(self):
        return self._json


def _sina_hq_shell(fields: list[str]) -> str:
    return 'var hq_str_CON_OP_10010974="' + ",".join(fields) + '";'


def test_parse_months_dedupes_and_converts_to_yymm():
    payload = {
        "result": {
            "data": {
                "contractMonth": ["2026-09", "2026-09", "2026-10", "2026-12", "2027-03"]
            }
        }
    }
    assert etf_options._parse_months(payload) == ["2609", "2610", "2612", "2703"]
    assert etf_options._parse_months({}) == []
    assert etf_options._parse_months({"result": {"data": {"contractMonth": ["bad"]}}}) == []


def test_parse_tquote_maps_live_payload():
    parsed = etf_options._parse_tquote_fields(list(_TQUOTE_FIELDS))
    assert parsed["bid_vol"] == 1.0
    assert parsed["bid"] == pytest.approx(0.0184)
    assert parsed["last"] == pytest.approx(0.0185)
    assert parsed["ask"] == pytest.approx(0.0185)
    assert parsed["ask_vol"] == 448.0
    assert parsed["open_interest"] == pytest.approx(105232)
    assert parsed["pct"] == pytest.approx(-21.61)
    assert parsed["strike"] == pytest.approx(3.0)
    assert parsed["prev_close"] == pytest.approx(0.0236)
    assert parsed["open"] == pytest.approx(0.0190)
    assert parsed["limit_up"] == pytest.approx(0.3198)
    assert parsed["limit_down"] == pytest.approx(0.0001)
    assert parsed["name"] == "50ETF购9月3000"
    assert parsed["amplitude"] == pytest.approx(20.34)
    assert parsed["high"] == pytest.approx(0.0204)
    assert parsed["low"] == pytest.approx(0.0156)
    assert parsed["volume"] == pytest.approx(67997)
    assert parsed["amount"] == pytest.approx(12038859.0)


def test_parse_tquote_rejects_short_payload():
    with pytest.raises(VendorNoDataError, match="字段数不足"):
        etf_options._parse_tquote_fields(["1", "2"])


def test_parse_greeks_skips_three_empty_fields():
    parsed = etf_options._parse_greeks_fields(list(_GREEKS_FIELDS))
    assert parsed["name"] == "50ETF购9月3000"
    assert parsed["volume"] == pytest.approx(67997)
    assert parsed["delta"] == pytest.approx(0.4155)
    assert parsed["gamma"] == pytest.approx(4.2572)
    assert parsed["theta"] == pytest.approx(-0.7727)
    assert parsed["vega"] == pytest.approx(0.1822)
    assert parsed["iv"] == pytest.approx(0.1484)
    assert parsed["trade_code"] == "510050C2609M03000"
    assert parsed["strike"] == pytest.approx(3.0)
    assert parsed["last"] == pytest.approx(0.0185)
    assert parsed["theory"] == pytest.approx(0.0271)


def test_parse_greeks_rejects_short_payload():
    with pytest.raises(VendorNoDataError, match="字段数不足"):
        etf_options._parse_greeks_fields(["name", "", "", ""])


def test_fetch_option_text_wraps_network_error(monkeypatch):
    def _boom(*args, **kwargs):
        raise OSError("connection reset")

    monkeypatch.setattr(etf_options.a_stock, "_source_http_get", _boom)
    with pytest.raises(VendorNetworkError, match="请求失败"):
        etf_options._fetch_option_text("https://hq.sinajs.cn/list=CON_OP_1")


def test_fetch_option_text_rejects_http_error_status(monkeypatch):
    monkeypatch.setattr(
        etf_options.a_stock,
        "_source_http_get",
        lambda *args, **kwargs: _FakeResponse(status_code=403, text=""),
    )
    with pytest.raises(VendorNoDataError, match="HTTP 403"):
        etf_options._fetch_option_text("https://hq.sinajs.cn/list=CON_OP_1")


def test_list_contracts_groups_months_and_ignores_foreign_items(monkeypatch):
    monkeypatch.setattr(etf_options, "_fetch_option_months", lambda code: ["2609"])
    payloads = {
        "OP_UP_5100502609": 'var hq_str_x="CON_OP_10010974,foo,CON_OP_10010975";',
        "OP_DOWN_5100502609": 'var hq_str_x="CON_OP_10010976";',
    }
    monkeypatch.setattr(
        etf_options, "_fetch_option_text", lambda url, **kw: payloads[url.rsplit("=", 1)[1]]
    )
    assert etf_options.list_etf_option_contracts("510050", call=True) == {
        "2609": ["10010974", "10010975"]
    }
    assert etf_options.list_etf_option_contracts("510050", call=False) == {
        "2609": ["10010976"]
    }


def test_list_contracts_rejects_unknown_underlying():
    with pytest.raises(ValueError, match="不支持的期权标的"):
        etf_options.list_etf_option_contracts("159915")


def test_get_tquote_and_greeks_with_patched_transport(monkeypatch):
    payloads = {
        "CON_OP_10010974": _sina_hq_shell(list(_TQUOTE_FIELDS)),
        "CON_SO_10010974": _sina_hq_shell(list(_GREEKS_FIELDS)),
    }
    monkeypatch.setattr(
        etf_options, "_fetch_option_text", lambda url, **kw: payloads[url.rsplit("=", 1)[1]]
    )
    tquote = etf_options.get_etf_option_tquote("10010974")
    assert tquote["code"] == "10010974"
    assert tquote["strike"] == pytest.approx(3.0)
    assert tquote["source"] == "sina CON_OP"
    greeks = etf_options.get_etf_option_greeks("10010974")
    assert greeks["code"] == "10010974"
    assert greeks["iv"] == pytest.approx(0.1484)
    with pytest.raises(ValueError, match="无效的期权合约代码"):
        etf_options.get_etf_option_tquote("CON_OP_10010974")


def test_chain_merges_rows_and_discloses_failed_contracts(monkeypatch):
    monkeypatch.setattr(etf_options, "_fetch_option_months", lambda code: ["2609"])
    good_tquote = _sina_hq_shell(list(_TQUOTE_FIELDS))
    good_greeks = _sina_hq_shell(list(_GREEKS_FIELDS))
    payloads = {
        "OP_UP_5100502609": 'var x="CON_OP_10000001,CON_OP_10000002";',
        "OP_DOWN_5100502609": 'var x="CON_OP_10000003";',
        "CON_OP_10000001": good_tquote,
        "CON_OP_10000002": 'var x="";',
        "CON_OP_10000003": good_tquote,
        "CON_SO_10000001": good_greeks,
        "CON_SO_10000003": good_greeks,
    }
    monkeypatch.setattr(
        etf_options, "_fetch_option_text", lambda url, **kw: payloads[url.rsplit("=", 1)[1]]
    )
    chain = etf_options.get_etf_option_chain("510050")
    assert chain["month"] == "2609"
    assert [row["code"] for row in chain["rows"]] == ["10000001", "10000003"]
    assert chain["rows"][0]["greeks"]["delta"] == pytest.approx(0.4155)
    assert chain["failed_contracts"] == [
        {"direction": "call", "code": "10000002", "error": "VendorNoDataError: 新浪 T 型报价字段数不足：期望 >= 43，实得 1（名称部分可能已下线或结构变更）"}
    ]
    with pytest.raises(ValueError, match="无 2612 月合约"):
        etf_options.get_etf_option_chain("510050", month="2612")
