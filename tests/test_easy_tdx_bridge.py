"""Contract tests for the isolated easy-tdx bridge.

The project runtime deliberately does not import easy-tdx.  These tests inject
small fake client factories so the bridge protocol remains deterministic.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pandas as pd


import chstockdata.tdx_bridge as _tdx_bridge_mod
BRIDGE_PATH = Path(_tdx_bridge_mod.__file__).with_name("_easy_tdx_bridge.py")
_MARKET = SimpleNamespace(SH=1, SZ=0, BJ=2)


def _load_bridge():
    spec = importlib.util.spec_from_file_location("easy_tdx_bridge", BRIDGE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Client:
    def __init__(self, frame):
        self.frame = frame

    def connect(self):
        return None

    def close(self):
        return None

    def get_capital_flow(self, market, code):
        return self.frame

    def get_board_ranking(self, **kwargs):
        return self.frame

    def get_board_list(self, board_type):
        return self.frame

    def get_belong_board(self, market, code):
        return self.frame

    def get_history_fund_flow(self, market, code, start, count):
        return self.frame


def test_fund_flow_payload_is_source_labeled_and_json_safe(monkeypatch):
    bridge = _load_bridge()
    current = pd.DataFrame(
        [{"main_net": 123456.0, "small_net": -123456.0, "date": ""}]
    )
    history = pd.DataFrame(
        [{"year": 2026, "month": 8, "day": 17, "main_net_inflow": 100.0}]
    )
    monkeypatch.setattr(
        bridge,
        "_load_clients",
        lambda: (
            lambda refresh=False: _Client(current),
            lambda refresh=False: _Client(history),
            _MARKET,
        ),
    )

    payload = bridge.execute(["fund-flow", "SH", "600519", "1"])

    assert payload["source"] == "tdx"
    assert payload["methodology"] == "tdx_l1_reconstructed"
    assert payload["current"][0]["main_net"] == 123456.0
    assert payload["history"][0]["day"] == 17


def test_industry_payload_has_tdx_taxonomy(monkeypatch):
    bridge = _load_bridge()
    ranking = pd.DataFrame(
        [{"code": "881001", "name": "农业", "change_pct": 2.3, "up_count": 8}]
    )
    monkeypatch.setattr(
        bridge,
        "_load_clients",
        lambda: (
            lambda refresh=False: _Client(ranking),
            lambda refresh=False: _Client(ranking),
            _MARKET,
        ),
    )

    payload = bridge.execute(["industry-ranking", "1", "0"])

    assert payload["source"] == "tdx"
    assert payload["taxonomy"] == "tdx_industry"
    assert payload["top"][0]["name"] == "农业"


def test_execute_rejects_unknown_command():
    bridge = _load_bridge()

    try:
        bridge.execute(["unknown"])
    except ValueError as exc:
        assert "unsupported command" in str(exc)
    else:
        raise AssertionError("unknown bridge command must fail explicitly")


def _one_factory(frame):
    return (
        lambda refresh=False: _Client(frame),
        lambda refresh=False: _Client(frame),
        _MARKET,
    )


def test_belong_board_payload_computes_change_pct(monkeypatch):
    """belong-board：个股全部板块 + close/pre_close 本地算涨跌幅，零基准为 None。"""
    bridge = _load_bridge()
    boards = pd.DataFrame(
        [
            {
                "board_type": 12,
                "market": 1,
                "board_code": "881130",
                "board_name": "酿酒",
                "close": 566.65,
                "pre_close": 572.86,
            },
            {
                "board_type": 5,
                "market": 1,
                "board_code": "880821",
                "board_name": "大盘股",
                "close": 2139.88,
                "pre_close": 0.0,
            },
        ]
    )
    monkeypatch.setattr(bridge, "_load_clients", lambda: _one_factory(boards))

    payload = bridge.execute(["belong-board", "SH", "600519"])

    assert payload["source"] == "tdx"
    assert payload["methodology"] == "tdx_board_snapshot"
    assert payload["taxonomy"] == "tdx_board"
    assert payload["boards"][0]["board_name"] == "酿酒"
    assert payload["boards"][0]["change_pct"] == -1.08
    assert payload["boards"][1]["change_pct"] is None


def test_belong_board_rejects_non_code_ticker(monkeypatch):
    bridge = _load_bridge()
    monkeypatch.setattr(
        bridge, "_load_clients", lambda: _one_factory(pd.DataFrame())
    )

    try:
        bridge.execute(["belong-board", "SH", "茅台"])
    except ValueError as exc:
        assert "6-digit" in str(exc)
    else:
        raise AssertionError("non-numeric ticker must fail explicitly")


def test_concept_ranking_sorts_full_board_list(monkeypatch):
    """concept-ranking：全量 board_list 本地计算，top/bottom 按涨跌幅取极值。"""
    bridge = _load_bridge()
    boards = pd.DataFrame(
        [
            {"code": "880001", "name": "概念甲", "price": 110.0, "pre_close": 100.0},
            {"code": "880002", "name": "概念乙", "price": 90.0, "pre_close": 100.0},
            {"code": "880003", "name": "概念丙", "price": 100.0, "pre_close": 0.0},
        ]
    )
    monkeypatch.setattr(bridge, "_load_clients", lambda: _one_factory(boards))
    monkeypatch.setattr(bridge, "_board_type_enum", lambda: SimpleNamespace(GN=3))

    payload = bridge.execute(["concept-ranking", "1", "1"])

    assert payload["source"] == "tdx"
    assert payload["methodology"] == "tdx_board_snapshot"
    assert payload["taxonomy"] == "tdx_concept"
    assert [item["name"] for item in payload["top"]] == ["概念甲"]
    assert payload["top"][0]["change_pct"] == 10.0
    assert [item["name"] for item in payload["bottom"]] == ["概念乙"]
    assert payload["bottom"][0]["change_pct"] == -10.0
    assert "概念丙" not in {item["name"] for item in payload["top"] + payload["bottom"]}
