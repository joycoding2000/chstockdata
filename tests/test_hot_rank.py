"""市场热度（同花顺热榜 / 东财人气榜 / 概念命中）离线回归。"""

from __future__ import annotations

import pytest

from chstockdata import hot_rank
from chstockdata.vendor_errors import VendorNetworkError, VendorNoDataError


class _FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


_THS_PAYLOAD = {
    "data": {
        "stock_list": [
            {
                "order": 1,
                "code": "000636",
                "name": "风华高科",
                "rate": "1059860.0",
                "rise_and_fall": 3.21,
                "hot_rank_chg": 0,
                "tag": {"concept_tag": ["MLCC概念", "被动元件"], "popularity_tag": "2天1板"},
            },
            {
                "order": 2,
                "code": "600519",
                "name": "贵州茅台",
                "rate": "998000.0",
                "rise_and_fall": -0.5,
                "hot_rank_chg": -1,
                "tag": {},
            },
        ]
    }
}

_EM_RANK_PAYLOAD = {
    "data": [
        {"sc": "SZ000636", "rk": 1, "hisRc": 0},
        {"sc": "SH600519", "rk": 2, "hisRc": -1},
    ]
}

_EM_CONCEPT_PAYLOAD = {
    "data": [
        {"conceptName": "MLCC概念", "conceptId": "BK1234", "hitCount": 320},
        {"conceptName": "被动元件", "conceptId": "BK5678", "hitCount": 180},
        {"conceptName": "", "conceptId": "BK0000", "hitCount": 1},
    ]
}


def test_get_hot_rank_parses_rows_and_period(monkeypatch):
    captured: dict = {}

    def _fake(source_id, url, **kwargs):
        captured.update(kwargs)
        return _FakeResponse(_THS_PAYLOAD)

    monkeypatch.setattr(hot_rank.a_stock, "_source_http_get", _fake)
    result = hot_rank.get_hot_rank("day")
    assert captured["params"] == {"stock_type": "a", "type": "day", "list_type": "normal"}
    assert result["period"] == "day"
    assert result["count"] == 2
    first = result["rows"][0]
    assert first["rank"] == 1.0
    assert first["code"] == "000636"
    assert first["heat"] == pytest.approx(1059860.0)
    assert first["concepts"] == ["MLCC概念", "被动元件"]
    assert first["tag"] == "2天1板"
    assert result["rows"][1]["concepts"] == []
    with pytest.raises(ValueError, match="未知周期"):
        hot_rank.get_hot_rank("week")


def test_get_em_hot_rank_hydrates_via_tencent_and_discloses_failure(monkeypatch):
    posts: list[dict] = []

    def _fake_post(url, **kwargs):
        posts.append({"url": url, **kwargs})
        return _FakeResponse(_EM_RANK_PAYLOAD)

    monkeypatch.setattr(hot_rank.a_stock, "_em_post", _fake_post)
    monkeypatch.setattr(
        hot_rank.a_stock,
        "_get_realtime_quotes",
        lambda codes: {
            "000636": {"name": "风华高科", "price": 15.5, "change_pct": 3.21},
            "600519": {"name": "贵州茅台", "price": 1277.96, "change_pct": -0.5},
        },
    )
    result = hot_rank.get_em_hot_rank(10)
    assert posts[0]["json"]["pageSize"] == 10
    assert result["hydration_error"] is None
    assert result["rows"][0]["code"] == "000636"
    assert result["rows"][0]["market"] == "SZ"
    assert result["rows"][0]["name"] == "风华高科"
    assert result["rows"][0]["price"] == pytest.approx(15.5)
    assert result["rows"][1]["pct"] == pytest.approx(-0.5)

    def _boom(codes):
        raise RuntimeError("quote chain down")

    monkeypatch.setattr(hot_rank.a_stock, "_get_realtime_quotes", _boom)
    degraded = hot_rank.get_em_hot_rank(10)
    assert degraded["hydration_error"] == "RuntimeError"
    assert degraded["rows"][0]["name"] is None
    assert degraded["rows"][0]["hydration_failed"] is True
    with pytest.raises(ValueError, match="top"):
        hot_rank.get_em_hot_rank(0)


def test_get_hot_concepts_sorts_and_uses_market_prefix(monkeypatch):
    captured: dict = {}

    def _fake_post(url, **kwargs):
        captured.update(kwargs)
        return _FakeResponse(_EM_CONCEPT_PAYLOAD)

    monkeypatch.setattr(hot_rank.a_stock, "_em_post", _fake_post)
    result = hot_rank.get_hot_concepts("600519")
    assert captured["json"]["srcSecurityCode"] == "SH600519"
    assert result["count"] == 2
    assert [row["concept"] for row in result["rows"]] == ["MLCC概念", "被动元件"]
    assert result["rows"][0]["hit"] == pytest.approx(320)
    with pytest.raises(ValueError, match="非法 ticker"):
        hot_rank.get_hot_concepts("AAPL")


def test_hot_rank_structure_and_network_failures(monkeypatch):
    monkeypatch.setattr(
        hot_rank.a_stock,
        "_source_http_get",
        lambda *a, **kw: _FakeResponse({"data": {}}),
    )
    with pytest.raises(VendorNoDataError, match="结构异常"):
        hot_rank.get_hot_rank()

    monkeypatch.setattr(
        hot_rank.a_stock,
        "_em_post",
        lambda *a, **kw: _FakeResponse({"data": None}),
    )
    with pytest.raises(VendorNoDataError, match="结构异常"):
        hot_rank.get_em_hot_rank()
    with pytest.raises(VendorNoDataError, match="结构异常"):
        hot_rank.get_hot_concepts("600519")

    def _boom(*args, **kwargs):
        raise OSError("reset")

    monkeypatch.setattr(hot_rank.a_stock, "_source_http_get", _boom)
    with pytest.raises(VendorNetworkError, match="请求失败"):
        hot_rank.get_hot_rank()
    monkeypatch.setattr(hot_rank.a_stock, "_em_post", _boom)
    with pytest.raises(VendorNetworkError, match="请求失败"):
        hot_rank.get_em_hot_rank()
