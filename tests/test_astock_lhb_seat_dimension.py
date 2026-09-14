"""Regression tests for DEC-P1-02龙虎榜营业部画像。"""

import pytest


def test_dragon_tiger_board_adds_current_seat_activity_and_return_profile(
    monkeypatch,
):
    from chstockdata import a_stock

    calls = []

    payloads = {
        "RPT_DAILYBILLBOARD_DETAILSNEW": [
            {
                "TRADE_DATE": "2026-09-09",
                "BILLBOARD_NET_AMT": 20_000_000,
                "TURNOVERRATE": 8.2,
                "EXPLANATION": "日涨幅偏离值",
            }
        ],
        "RPT_BILLBOARD_DAILYDETAILSBUY": [
            {
                "OPERATEDEPT_CODE": "1001",
                "OPERATEDEPT_NAME": "测试营业部A",
                "BUY": 30_000_000,
                "SELL": 5_000_000,
                "NET": 25_000_000,
            }
        ],
        "RPT_BILLBOARD_DAILYDETAILSSELL": [
            {
                "OPERATEDEPT_CODE": "1002",
                "OPERATEDEPT_NAME": "测试营业部B",
                "BUY": 4_000_000,
                "SELL": 16_000_000,
                "NET": -12_000_000,
            }
        ],
        "RPT_OPERATEDEPT_ACTIVE": [
            {
                "OPERATEDEPT_CODE": "1001",
                "OPERATEDEPT_NAME": "测试营业部A",
                "ONLIST_DATE": "2026-09-01",
                "BUYER_APPEAR_NUM": 3,
                "SELLER_APPEAR_NUM": 1,
                "TOTAL_BUYAMT": 120_000_000,
                "TOTAL_SELLAMT": 20_000_000,
                "TOTAL_NETAMT": 100_000_000,
            }
        ],
        "RPT_RATEDEPT_RETURNT_RANKING": [
            {
                "OPERATEDEPT_CODE": "1001",
                "OPERATEDEPT_NAME": "测试营业部A",
                "AVERAGE_INCREASE_1DAY": 1.25,
                "RISE_PROBABILITY_1DAY": 60.0,
                "AVERAGE_INCREASE_3DAY": 2.5,
                "RISE_PROBABILITY_3DAY": 70.0,
            }
        ],
    }

    def fake_datacenter(report_name, **kwargs):
        calls.append((report_name, kwargs))
        return payloads[report_name]

    monkeypatch.setattr(a_stock, "_eastmoney_datacenter", fake_datacenter)

    result = a_stock.get_dragon_tiger_board("600519", "2026-09-10")

    assert "## 当前龙虎榜营业部画像" in result
    assert "测试营业部A | 买" in result
    assert "活跃交易日=1" in result
    assert "买入个股数=3" in result
    assert "卖出个股数=1" in result
    assert "1日平均涨幅=1.25%" in result
    assert "3日上涨概率=70.00%" in result
    assert [report_name for report_name, _ in calls] == [
        "RPT_DAILYBILLBOARD_DETAILSNEW",
        "RPT_BILLBOARD_DAILYDETAILSBUY",
        "RPT_BILLBOARD_DAILYDETAILSSELL",
        "RPT_OPERATEDEPT_ACTIVE",
        "RPT_RATEDEPT_RETURNT_RANKING",
    ]

    active_params = calls[3][1]
    assert "ONLIST_DATE>=" in active_params["filter_str"]
    assert 'OPERATEDEPT_CODE in ("1001","1002")' in active_params["filter_str"]
    assert active_params["sort_columns"] == (
        "TOTAL_NETAMT,ONLIST_DATE,OPERATEDEPT_CODE"
    )

    ranking_params = calls[4][1]
    assert '(STATISTICSCYCLE="01")' in ranking_params["filter_str"]
    assert 'OPERATEDEPT_CODE in ("1001","1002")' in ranking_params["filter_str"]


def test_strict_eastmoney_datacenter_rejects_malformed_rows(monkeypatch):
    from chstockdata import a_stock

    class Response:
        def json(self):
            return {"result": {"data": {"unexpected": "object"}}}

    monkeypatch.setattr(a_stock, "_em_get", lambda *args, **kwargs: Response())

    with pytest.raises(ValueError, match="data must be a list"):
        a_stock._eastmoney_datacenter(
            "RPT_OPERATEDEPT_ACTIVE",
            strict=True,
        )


def test_seat_profile_keeps_active_failure_separate_from_return_statistics(
    monkeypatch,
):
    from chstockdata import a_stock

    def fake_datacenter(report_name, **kwargs):
        if report_name == "RPT_DAILYBILLBOARD_DETAILSNEW":
            return [{"TRADE_DATE": "2026-09-09"}]
        if report_name == "RPT_BILLBOARD_DAILYDETAILSBUY":
            return [
                {
                    "OPERATEDEPT_CODE": "1001",
                    "OPERATEDEPT_NAME": "测试营业部A",
                }
            ]
        if report_name == "RPT_BILLBOARD_DAILYDETAILSSELL":
            return []
        if report_name == "RPT_OPERATEDEPT_ACTIVE":
            raise RuntimeError("provider detail must not leak")
        return [
            {
                "OPERATEDEPT_CODE": "1001",
                "AVERAGE_INCREASE_1DAY": 1.5,
                "RISE_PROBABILITY_1DAY": 55,
            }
        ]

    monkeypatch.setattr(a_stock, "_eastmoney_datacenter", fake_datacenter)

    result = a_stock.get_dragon_tiger_board("600519", "2026-09-10")

    assert "[数据缺失: 龙虎榜营业部活跃画像暂不可用]" in result
    assert "1日平均涨幅=1.50%" in result
    assert "provider detail must not leak" not in result


def test_empty_seat_profiles_are_normal_empty_not_provider_failure(monkeypatch):
    from chstockdata import a_stock

    def fake_datacenter(report_name, **kwargs):
        if report_name == "RPT_DAILYBILLBOARD_DETAILSNEW":
            return [{"TRADE_DATE": "2026-09-09"}]
        if report_name == "RPT_BILLBOARD_DAILYDETAILSBUY":
            return [
                {
                    "OPERATEDEPT_CODE": "1001",
                    "OPERATEDEPT_NAME": "测试营业部A",
                }
            ]
        return []

    monkeypatch.setattr(a_stock, "_eastmoney_datacenter", fake_datacenter)

    result = a_stock.get_dragon_tiger_board("600519", "2026-09-10")

    assert "活跃画像=无匹配记录" in result
    assert "收益统计=无匹配记录" in result
    assert "龙虎榜营业部活跃画像暂不可用" not in result
    assert "龙虎榜营业部收益统计暂不可用" not in result
