"""板块资金流（bkzj 非 push2）离线回归。"""

from __future__ import annotations

import pytest

from chstockdata import board_flow
from chstockdata.vendor_errors import VendorNetworkError, VendorNoDataError


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload
        self.status_code = 200

    def json(self):
        return self._payload


def _payload():
    return {
        "data": {
            "total": 3,
            "diff": [
                {"f12": "BK1216", "f13": 90, "f14": "医药商业", "f62": 2_897_983_488},
                {"f12": "BK0459", "f13": 90, "f14": "元件", "f62": 13_346_588_928},
                {"f12": "BK0999", "f13": 90, "f14": "空值板块"},
                {"f14": "缺代码", "f62": 1},
            ],
        }
    }


def test_board_flow_sorts_by_main_net_and_skips_malformed(monkeypatch):
    captured: dict = {}

    def _fake(url, **kwargs):
        captured.update(kwargs)
        return _FakeResponse(_payload())

    monkeypatch.setattr(board_flow.a_stock, "_em_get", _fake)
    result = board_flow.get_board_fund_flow("industry", "today", top_n=10)
    assert captured["params"] == {"key": "f62", "code": "m:90+t:2"}
    assert result["board_type"] == "industry"
    assert result["period"] == "today"
    assert result["key"] == "f62"
    assert result["count"] == 2
    assert [row["name"] for row in result["rows"]] == ["元件", "医药商业"]
    assert result["rows"][0]["main_net_yuan"] == pytest.approx(13_346_588_928)
    assert result["rows"][0]["main_net_yi"] == pytest.approx(133.46588928)
    assert result["total_count"] == 3
    assert result["limitations"]


def test_board_flow_period_key_mapping_and_top_n(monkeypatch):
    captured: dict = {}

    def _fake(url, **kwargs):
        captured.update(kwargs)
        return _FakeResponse(_payload())

    monkeypatch.setattr(board_flow.a_stock, "_em_get", _fake)
    board_flow.get_board_fund_flow("concept", "10d", top_n=1)
    assert captured["params"]["key"] == "f174"
    result = board_flow.get_board_fund_flow("region", "5d")
    assert result["key"] == "f164"


def test_board_flow_rejects_bad_arguments():
    with pytest.raises(ValueError, match="未知板块类型"):
        board_flow.get_board_fund_flow("sector")
    with pytest.raises(ValueError, match="未知周期"):
        board_flow.get_board_fund_flow("industry", "30d")
    with pytest.raises(ValueError, match="top_n"):
        board_flow.get_board_fund_flow("industry", "today", top_n=0)


def test_board_flow_structure_and_network_failures(monkeypatch):
    monkeypatch.setattr(
        board_flow.a_stock, "_em_get", lambda *a, **kw: _FakeResponse({"data": {}})
    )
    with pytest.raises(VendorNoDataError, match="结构异常"):
        board_flow.get_board_fund_flow("industry")

    def _boom(*args, **kwargs):
        raise OSError("reset")

    monkeypatch.setattr(board_flow.a_stock, "_em_get", _boom)
    with pytest.raises(VendorNetworkError, match="请求失败"):
        board_flow.get_board_fund_flow("industry")
