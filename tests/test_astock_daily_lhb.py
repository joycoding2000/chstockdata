"""全市场龙虎榜（get_daily_dragon_tiger）离线回归。"""

from __future__ import annotations

import pytest

from chstockdata import a_stock
from chstockdata.vendor_errors import VendorNetworkError, VendorNoDataError

_ROWS = [
    {
        "TRADE_DATE": "2026-09-11 00:00:00",
        "SECURITY_CODE": "002475",
        "SECURITY_NAME_ABBR": "立讯精密",
        "EXPLANATION": "日涨幅偏离值达7%的证券",
        "CLOSE_PRICE": 45.67,
        "CHANGE_RATE": 9.987,
        "BILLBOARD_NET_AMT": 120_000_000,
        "BILLBOARD_BUY_AMT": 300_000_000,
        "BILLBOARD_SELL_AMT": 180_000_000,
        "TURNOVERRATE": 3.456,
    },
    {
        "TRADE_DATE": "2026-09-11 00:00:00",
        "SECURITY_CODE": "600519",
        "SECURITY_NAME_ABBR": "贵州茅台",
        "EXPLANATION": "连续三个交易日内涨幅偏离值累计20%",
        "CLOSE_PRICE": 1277.96,
        "CHANGE_RATE": 0.22,
        "BILLBOARD_NET_AMT": -50_000_000,
        "BILLBOARD_BUY_AMT": 10_000_000,
        "BILLBOARD_SELL_AMT": 60_000_000,
        "TURNOVERRATE": 0.31,
    },
]


def test_daily_lhb_maps_rows_and_uses_source_trade_date(monkeypatch):
    captured: dict = {}

    def _fake(report_name, **kwargs):
        captured["report_name"] = report_name
        captured.update(kwargs)
        return list(_ROWS)

    monkeypatch.setattr(a_stock, "_eastmoney_datacenter", _fake)
    result = a_stock.get_daily_dragon_tiger("2026-09-11")
    assert captured["report_name"] == "RPT_DAILYBILLBOARD_DETAILSNEW"
    assert "TRADE_DATE>='2026-09-11'" in captured["filter_str"]
    assert result["status"] == "success"
    assert result["date"] == "2026-09-11"
    assert result["count"] == 2
    first = result["stocks"][0]
    assert first["code"] == "002475"
    assert first["name"] == "立讯精密"
    assert first["net_buy_wan"] == pytest.approx(12000.0)
    assert first["buy_wan"] == pytest.approx(30000.0)
    assert first["sell_wan"] == pytest.approx(18000.0)
    assert first["pct"] == pytest.approx(9.99)
    assert first["turnover_pct"] == pytest.approx(3.46)
    assert result["stocks"][1]["net_buy_wan"] == pytest.approx(-5000.0)
    assert result["empty_reason"] is None


def test_daily_lhb_min_net_buy_filter(monkeypatch):
    monkeypatch.setattr(
        a_stock, "_eastmoney_datacenter", lambda *a, **kw: list(_ROWS)
    )
    result = a_stock.get_daily_dragon_tiger("2026-09-11", min_net_buy_wan=5000)
    assert [row["code"] for row in result["stocks"]] == ["002475"]


def test_daily_lhb_empty_is_explicit(monkeypatch):
    monkeypatch.setattr(a_stock, "_eastmoney_datacenter", lambda *a, **kw: [])
    result = a_stock.get_daily_dragon_tiger("2026-09-13")
    assert result["status"] == "normal_empty"
    assert result["stocks"] == []
    assert "2026-09-13" in result["empty_reason"]


def test_daily_lhb_rejects_bad_date():
    with pytest.raises(ValueError, match="非法日期"):
        a_stock.get_daily_dragon_tiger("2026/09/11")


def test_daily_lhb_classifies_structure_and_network_failures(monkeypatch):
    def _structure(*args, **kwargs):
        raise ValueError("payload missing result.data list")

    monkeypatch.setattr(a_stock, "_eastmoney_datacenter", _structure)
    with pytest.raises(VendorNoDataError, match="结构异常"):
        a_stock.get_daily_dragon_tiger("2026-09-11")

    def _network(*args, **kwargs):
        raise OSError("connection reset")

    monkeypatch.setattr(a_stock, "_eastmoney_datacenter", _network)
    with pytest.raises(VendorNetworkError, match="请求失败"):
        a_stock.get_daily_dragon_tiger("2026-09-11")
