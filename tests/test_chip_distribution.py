"""CYQ 筹码分布：纯算法不变量 + baostock 装配隔离（离线回归）。"""

from __future__ import annotations

import sys

import pandas as pd
import pytest

from chstockdata import chips as cyq
from chstockdata.vendor_errors import VendorNotConfiguredError


def _rows(closes, turn=2.5):
    return [
        {
            "date": f"2026-08-{index + 1:02d}",
            "high": close + 0.2,
            "low": close - 0.2,
            "close": close,
            "turn": turn,
        }
        for index, close in enumerate(closes)
    ]


def test_chip_distribution_requires_date_and_turn_columns():
    frame = pd.DataFrame(_rows([10.0, 10.5])).drop(columns=["date", "turn"])
    with pytest.raises(ValueError, match="缺少列"):
        cyq.chip_distribution(frame)


def test_chip_distribution_empty_frame_fails_loud():
    frame = pd.DataFrame(
        [{"date": "2026-08-01", "high": 0, "low": 0, "close": 0, "turn": 1.0}]
    )
    with pytest.raises(ValueError, match="有效行数为 0"):
        cyq.chip_distribution(frame)


def test_chip_distribution_is_time_direction_independent():
    frame = pd.DataFrame(_rows([10.0, 10.4, 10.9, 11.2, 11.0, 11.6]))
    forward = cyq.chip_distribution(frame)
    backward = cyq.chip_distribution(frame.iloc[::-1].reset_index(drop=True))
    assert forward["avg_cost"] == pytest.approx(backward["avg_cost"], rel=1e-12)
    assert forward["profit_ratio"] == pytest.approx(
        backward["profit_ratio"], rel=1e-12
    )
    assert forward["peak_price"] == pytest.approx(backward["peak_price"], rel=1e-12)


def test_chip_distribution_seeds_first_day_with_full_float():
    """上游 CHANGELOG 反例：1% 换手 @10 + 1% 换手 @100 应约 99%/1%，
    而不是从零播种得到的 50/50。"""
    frame = pd.DataFrame(
        [
            {"date": "2026-08-01", "high": 10.0, "low": 10.0, "close": 10.0, "turn": 1.0},
            {"date": "2026-08-04", "high": 100.0, "low": 100.0, "close": 100.0, "turn": 1.0},
        ]
    )
    result = cyq.chip_distribution(frame)
    high_side = sum(weight for price, weight in result["histogram"] if price > 50)
    low_side = sum(weight for price, weight in result["histogram"] if price < 50)
    assert high_side == pytest.approx(0.01, abs=1e-6)
    assert low_side == pytest.approx(0.99, abs=1e-6)
    assert result["avg_cost"] < 11.0
    assert result["peak_price"] < 11.0  # 峰值落在低价侧网格点（步长约 0.3）


def test_chip_distribution_hard_invariants():
    closes = [10 + (index % 7) * 0.3 for index in range(30)]
    result = cyq.chip_distribution(pd.DataFrame(_rows(closes)))
    assert 0.0 <= result["profit_ratio"] <= 1.0
    assert result["cost_90"][0] <= result["cost_90"][1]
    assert result["cost_70"][0] <= result["cost_70"][1]
    assert result["cost_90"][0] <= result["cost_70"][0]
    assert result["cost_90"][1] >= result["cost_70"][1]
    assert result["concentration_90"] > result["concentration_70"]
    assert result["histogram"]
    assert result["peak_price"] >= min(price for price, _ in result["histogram"])
    assert result["peak_price"] <= max(price for price, _ in result["histogram"])


def test_chip_distribution_rejects_bad_grid_and_decay():
    frame = pd.DataFrame(_rows([10.0, 10.5]))
    with pytest.raises(ValueError, match="grid_size"):
        cyq.chip_distribution(frame, grid_size=3)
    with pytest.raises(ValueError, match="decay"):
        cyq.chip_distribution(frame, decay=-1)


def test_bs_code_maps_markets_and_rejects_bse():
    assert cyq._bs_code("600519") == "sh.600519"
    assert cyq._bs_code("688017") == "sh.688017"
    assert cyq._bs_code("000001") == "sz.000001"
    assert cyq._bs_code("300750") == "sz.300750"
    with pytest.raises(ValueError, match="不支持该代码"):
        cyq._bs_code("920982")
    with pytest.raises(ValueError, match="不支持该代码"):
        cyq._bs_code("830799")


def test_load_baostock_missing_dependency_is_configured_error(monkeypatch):
    monkeypatch.setitem(sys.modules, "baostock", None)
    with pytest.raises(VendorNotConfiguredError, match="baostock"):
        cyq._load_baostock()


def test_get_chip_distribution_assembles_metadata(monkeypatch):
    frame = pd.DataFrame(_rows([10.0, 10.4, 10.9, 10.6, 11.1]))
    monkeypatch.setattr(
        cyq,
        "_fetch_turnover_frame",
        lambda code, start, end: (frame, 2),
    )
    result = cyq.get_chip_distribution("600519", "2026-08-01", "2026-08-31")
    assert result["ticker"] == "600519"
    assert result["trading_days"] == 5
    assert result["input_quality"]["suspended_days_excluded"] == 2
    assert result["input_quality"]["cumulative_turnover_pct"] == pytest.approx(12.5)
    assert "推演" in result["disclaimer"]
    assert result["metrics"]["cost_90"][0] <= result["metrics"]["avg_cost"]


def test_get_chip_distribution_rejects_invalid_ticker_and_dates(monkeypatch):
    monkeypatch.setattr(
        cyq, "_fetch_turnover_frame", lambda code, start, end: (pd.DataFrame(), 0)
    )
    with pytest.raises(ValueError, match="非法 ticker"):
        cyq.get_chip_distribution("AAPL", "2026-08-01", "2026-08-31")
    with pytest.raises(ValueError, match="920982"):
        cyq.get_chip_distribution("920982", "2026-08-01", "2026-08-31")
    with pytest.raises(ValueError):
        cyq.get_chip_distribution("600519", "2026/08/01", "2026-08-31")
