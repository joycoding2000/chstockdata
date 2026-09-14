"""打板层（东财四池 + 同花顺涨停揭秘）离线解析与失败闭合回归。

样本字段名与实测值引自 2026-09-14 探测（getYesterdayZTPool 35 行）与上游
SKILL v3.7.1 实测记录；断言只看字段映射与语义，不复制源端行数。
"""

from __future__ import annotations

import pytest

from chstockdata import limit_up
from chstockdata.vendor_errors import VendorNetworkError, VendorNoDataError


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload
        self.status_code = 200

    def json(self):
        return self._payload


# 20260911 getYesterdayZTPool 实测首行（920268 中航泰达，字段名逐字复制）
_YZT_ROW = {
    "c": "920268",
    "m": 0,
    "n": "中航泰达",
    "p": 41500,
    "ztp": 45420,
    "zdp": 18.775043487548828,
    "amount": 392724480,
    "ltsz": 599597644.0,
    "tshare": 2249300000.0,
    "hs": 70.58277893066406,
    "zf": 33.342872619628906,
    "zs": 0.7281553745269775,
    "yfbt": 100727,
    "ylbc": 1,
    "hybk": "环保设备",
    "zttj": {"days": 2, "ct": 1},
}


def test_fmt_pool_time():
    assert limit_up._fmt_pool_time(92500) == "09:25:00"
    assert limit_up._fmt_pool_time(100727) == "10:07:27"
    assert limit_up._fmt_pool_time("93000") == "09:30:00"
    assert limit_up._fmt_pool_time(0) is None
    assert limit_up._fmt_pool_time(None) is None
    assert limit_up._fmt_pool_time("") is None
    assert limit_up._fmt_pool_time(240000) is None


def test_normalize_pool_date_supports_both_formats_and_rejects_garbage():
    assert limit_up._normalize_pool_date("2026-09-11") == ("2026-09-11", "20260911")
    assert limit_up._normalize_pool_date("20260911") == ("2026-09-11", "20260911")
    with pytest.raises(ValueError, match="非法日期"):
        limit_up._normalize_pool_date("2026/09/11")


def test_get_limit_up_pool_normalizes_yzt_row(monkeypatch):
    payload = {"data": {"tc": 35, "qdate": 20260914, "pool": [_YZT_ROW]}}
    monkeypatch.setattr(
        limit_up.a_stock, "_em_get", lambda *a, **kw: _FakeResponse(payload)
    )
    result = limit_up.get_limit_up_pool("20260911", kind="yzt")
    assert result["date"] == "2026-09-11"
    assert result["query_date"] == "20260911"
    assert result["kind"] == "yzt"
    assert result["count"] == 1
    assert result["source_total_count"] == 35
    assert result["source_query_stamp"] == "20260914"
    assert result["empty_reason"] is None
    row = result["rows"][0]
    assert row["code"] == "920268"
    assert row["name"] == "中航泰达"
    assert row["price"] == pytest.approx(41.5)
    assert row["pct"] == pytest.approx(18.775043)
    assert row["turnover_pct"] == pytest.approx(70.582779)
    assert row["amplitude_pct"] == pytest.approx(33.342873)
    assert row["speed_pct"] == pytest.approx(0.728155)
    assert row["y_first_seal"] == "10:07:27"
    assert row["y_limit_days"] == 1
    assert row["industry"] == "环保设备"
    assert row["zt_stat"] == "2天1板"
    assert row["amount_yuan"] == pytest.approx(392724480)
    assert row["float_cap_yuan"] == pytest.approx(599597644.0)


def test_get_limit_up_pool_normalizes_zt_row(monkeypatch):
    payload = {
        "data": {
            "tc": 1,
            "pool": [
                {
                    "c": "000001", "n": "平安银行", "p": 12340, "zdp": 10.01,
                    "amount": 1_000_000_000, "ltsz": 5_000_000_000, "hs": 3.5,
                    "lbc": 2, "fbt": 93500, "lbt": 145959, "fund": 88_000_000,
                    "zbc": 1, "hybk": "银行", "zttj": {"days": 3, "ct": 2},
                }
            ],
        }
    }
    monkeypatch.setattr(
        limit_up.a_stock, "_em_get", lambda *a, **kw: _FakeResponse(payload)
    )
    row = limit_up.get_limit_up_pool("2026-09-11", kind="zt")["rows"][0]
    assert row["price"] == pytest.approx(12.34)
    assert row["limit_days"] == 2
    assert row["first_seal"] == "09:35:00"
    assert row["last_seal"] == "14:59:59"
    assert row["seal_fund_yuan"] == pytest.approx(88_000_000)
    assert row["break_times"] == 1
    assert row["zt_stat"] == "3天2板"


def test_get_limit_up_pool_dt_and_zb_fields(monkeypatch):
    payload = {
        "data": {
            "pool": [
                {
                    "c": "600519", "n": "贵州茅台", "p": 120000, "zdp": -10.0,
                    "hs": 0.5, "pe": 19.6, "fund": 55_000_000, "lbt": 92600,
                    "fba": 12_000_000, "days": 3, "oc": 2, "hybk": "白酒",
                },
                {
                    "c": "300750", "n": "宁德时代", "p": 200100, "ztp": 222200,
                    "zdp": 3.2, "hs": 8.8, "fbt": 101500, "zbc": 4,
                    "zf": 9.75, "zs": -0.31, "hybk": "电池", "zttj": {"days": 2, "ct": 1},
                },
            ]
        }
    }
    monkeypatch.setattr(
        limit_up.a_stock, "_em_get", lambda *a, **kw: _FakeResponse(payload)
    )
    dt = limit_up.get_limit_up_pool("2026-09-11", kind="dt")["rows"][0]
    assert dt["seal_fund_yuan"] == pytest.approx(55_000_000)
    assert dt["last_seal"] == "09:26:00"
    assert dt["board_amount_yuan"] == pytest.approx(12_000_000)
    assert dt["dt_days"] == 3
    assert dt["open_times"] == 2
    assert dt["pe"] == pytest.approx(19.6)

    zb = limit_up.get_limit_up_pool("2026-09-11", kind="zb")["rows"][1]
    assert zb["limit_price"] == pytest.approx(222.2)
    assert zb["break_times"] == 4
    assert zb["amplitude_pct"] == pytest.approx(9.75)
    assert zb["speed_pct"] == pytest.approx(-0.31)
    assert zb["zt_stat"] == "2天1板"


def test_get_limit_up_pool_null_data_is_explicit_empty(monkeypatch):
    monkeypatch.setattr(
        limit_up.a_stock, "_em_get", lambda *a, **kw: _FakeResponse({"data": None})
    )
    result = limit_up.get_limit_up_pool("2026-09-13", kind="zt")
    assert result["rows"] == []
    assert result["count"] == 0
    assert "非交易日" in result["empty_reason"]


def test_get_limit_up_pool_malformed_pool_fails_loud(monkeypatch):
    monkeypatch.setattr(
        limit_up.a_stock,
        "_em_get",
        lambda *a, **kw: _FakeResponse({"data": {"pool": "oops"}}),
    )
    with pytest.raises(VendorNoDataError, match="结构异常"):
        limit_up.get_limit_up_pool("2026-09-11", kind="zt")


def test_get_limit_up_pool_rejects_unknown_kind_and_wraps_network(monkeypatch):
    with pytest.raises(ValueError, match="未知的池类型"):
        limit_up.get_limit_up_pool("2026-09-11", kind="xx")

    def _boom(*args, **kwargs):
        raise OSError("reset")

    monkeypatch.setattr(limit_up.a_stock, "_em_get", _boom)
    with pytest.raises(VendorNetworkError, match="请求失败"):
        limit_up.get_limit_up_pool("2026-09-11", kind="zt")


# 同花顺涨停揭秘实测字段（2026-09-14 探测 keys + 上游映射）
_THS_INFO = [
    {
        "code": "002031", "name": "巨轮智能", "latest": 5.12, "change_rate": 10.11,
        "reason_type": "机器人+减速器", "limit_up_type": "换手板",
        "limit_up_suc_rate": 0.86, "open_num": 1, "order_amount": 320000000,
        "high_days": "3天3板", "first_limit_up_time": 1757826000,
        "is_again_limit": 0,
    }
]


def test_get_limit_up_reasons_parses_unix_time_and_quality_fields(monkeypatch):
    monkeypatch.setattr(
        limit_up.a_stock,
        "_source_http_get",
        lambda *a, **kw: _FakeResponse({"data": {"info": _THS_INFO}}),
    )
    result = limit_up.get_limit_up_reasons("2026-09-11")
    assert result["count"] == 1
    row = result["rows"][0]
    assert row["code"] == "002031"
    assert row["reason"] == "机器人+减速器"
    assert row["board_type"] == "换手板"
    assert row["seal_rate"] == pytest.approx(0.86)
    assert row["seal_amount_yuan"] == pytest.approx(320000000)
    assert row["high_days"] == "3天3板"
    # Unix 秒 → 北京时间 HH:MM:SS（1757826000 = 2025-09-14 13:00:00 +08）
    assert row["first_time"] == "13:00:00"
    assert row["is_again_limit"] == 0


def test_get_limit_up_reasons_empty_and_malformed(monkeypatch):
    monkeypatch.setattr(
        limit_up.a_stock,
        "_source_http_get",
        lambda *a, **kw: _FakeResponse({"data": {"info": []}}),
    )
    result = limit_up.get_limit_up_reasons("2026-09-13")
    assert result["rows"] == []
    assert "非交易日" in result["empty_reason"]

    monkeypatch.setattr(
        limit_up.a_stock,
        "_source_http_get",
        lambda *a, **kw: _FakeResponse({"data": {"info": None}}),
    )
    with pytest.raises(VendorNoDataError, match="结构异常"):
        limit_up.get_limit_up_reasons("2026-09-13")
