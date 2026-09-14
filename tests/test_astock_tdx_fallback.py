"""Push2-independent fund-flow and industry source-chain regression tests."""

from __future__ import annotations

import json
from subprocess import CompletedProcess

import pytest


def test_bridge_runner_uses_configured_isolated_python_without_shell(monkeypatch):
    from chstockdata import tdx_bridge

    seen = {}

    def fake_run(command, **kwargs):
        seen["command"] = command
        seen["kwargs"] = kwargs
        return CompletedProcess(
            command,
            0,
            stdout=json.dumps(
                {
                    "source": "tdx",
                    "methodology": "tdx_l1_reconstructed",
                    "current": [{"main_net": 1.0}],
                    "history": [],
                }
            ),
            stderr="",
        )

    monkeypatch.setenv("EASY_TDX_PYTHON", "/opt/easy-tdx/bin/python")
    monkeypatch.setattr(tdx_bridge.subprocess, "run", fake_run)

    result = tdx_bridge.run_tdx_bridge("fund-flow", "SH", "600519", "0")

    assert result["source"] == "tdx"
    assert seen["command"][-4:] == ["fund-flow", "SH", "600519", "0"]
    assert seen["kwargs"]["shell"] is False
    assert seen["kwargs"]["timeout"] == tdx_bridge.TDX_BRIDGE_TIMEOUT_SECONDS


def test_tdx_bridge_routes_920_codes_to_beijing_market():
    """北交所 920 号段不能被通用的 9 开头沪市规则吞掉。"""
    from chstockdata.tdx_bridge import market_for_code

    assert market_for_code("920001") == "BJ"


def test_fund_flow_prefers_tdx_without_calling_eastmoney(monkeypatch):
    from chstockdata import a_stock

    monkeypatch.setattr(
        a_stock,
        "_get_tdx_fund_flow",
        lambda code, include_history: {
            "source": "tdx",
            "methodology": "tdx_l1_reconstructed",
            "current": [{"main_net": 120000.0, "small_net": -120000.0}],
            "history": [],
        },
        raising=False,
    )
    monkeypatch.setattr(
        a_stock,
        "_em_get",
        lambda *args, **kwargs: pytest.fail("fund flow must not call push2"),
    )

    result = a_stock.get_fund_flow("600519", "2026-08-17", include_history=False)

    assert "Source: TDX" in result
    assert "Methodology: tdx_l1_reconstructed" in result
    assert "主力净流入=12万" in result
    assert "Realtime Minute Flow" not in result


def test_fund_flow_uses_sina_daily_fallback_after_tdx_failure(monkeypatch):
    from chstockdata import a_stock

    monkeypatch.setattr(
        a_stock,
        "_get_tdx_fund_flow",
        lambda code, include_history: (_ for _ in ()).throw(RuntimeError("tdx down")),
        raising=False,
    )
    monkeypatch.setattr(
        a_stock,
        "_sina_daily_fund_flow",
        lambda code, history_count, cutoff_date=None: [
            {"date": "2026-08-17", "net_amount": 50000.0, "main_net": 30000.0}
        ],
        raising=False,
    )
    monkeypatch.setattr(
        a_stock,
        "_em_get",
        lambda *args, **kwargs: pytest.fail("fund flow must not call push2"),
    )

    result = a_stock.get_fund_flow("600519", "2026-08-17")

    assert "Source: 新浪财经" in result
    assert "日频资金流降级" in result
    assert "2026-08-17" in result


def test_fund_flow_sina_fallback_truncates_future_dates(monkeypatch):
    """历史复盘时新浪降级不能把分析日之后的资金流当当日数据喂给模型（P4）。"""
    from chstockdata import a_stock

    future_and_past = [
        {"date": "2026-08-18", "net_amount": 90000.0, "main_net": 90000.0},
        {"date": "2026-08-17", "net_amount": 50000.0, "main_net": 30000.0},
        {"date": "2026-08-14", "net_amount": 20000.0, "main_net": 10000.0},
    ]

    monkeypatch.setattr(
        a_stock,
        "_get_tdx_fund_flow",
        lambda code, include_history: (_ for _ in ()).throw(RuntimeError("tdx down")),
        raising=False,
    )
    monkeypatch.setattr(
        a_stock,
        "_sina_daily_fund_flow",
        lambda code, history_count, cutoff_date=None: [
            r for r in future_and_past if str(r["date"])[:10] <= cutoff_date
        ],
        raising=False,
    )

    result = a_stock.get_fund_flow("600519", "2026-08-17")

    assert "2026-08-17" in result
    assert "2026-08-14" in result
    assert "2026-08-18" not in result


def test_fund_flow_tdx_history_truncates_future_dates(monkeypatch):
    """TDX 主路径的历史资金流也按分析日截断，复盘历史时不泄露未来序列（P4）。"""
    from chstockdata import a_stock

    monkeypatch.setattr(
        a_stock,
        "_get_tdx_fund_flow",
        lambda code, include_history: {
            "source": "tdx",
            "methodology": "tdx_l1_reconstructed",
            "current": [{"main_net": 120000.0, "small_net": -120000.0}],
            "history": [
                {"date": "2026-08-18", "main_net": 90000.0},
                {"date": "2026-07-31", "main_net": 60000.0},
                {"date": "2026-07-30", "main_net": 50000.0},
            ],
        },
        raising=False,
    )
    monkeypatch.setattr(
        a_stock,
        "_sina_daily_fund_flow",
        lambda code, history_count, cutoff_date=None: pytest.fail("TDX 历史不应触发新浪"),
    )

    result = a_stock.get_fund_flow("600519", "2026-07-31")

    assert "2026-07-31" in result
    assert "2026-07-30" in result
    assert "2026-08-18" not in result
    assert "Source: TDX" in result


def test_fund_flow_tdx_history_synthesizes_main_net_from_four_tiers(monkeypatch):
    """Category 22 历史行只有四档 in/out、无 main_net 键。

    easy-tdx 的 ``main_net_inflow`` 是 @property 不进桥载荷（2026-09-12 侧查），
    修复前历史段会逐行打印"主力净额=0万"；现在按 主力=超大+大 合成，
    并透传四档净额（TDX 口径）。
    """
    from chstockdata import a_stock

    monkeypatch.setattr(
        a_stock,
        "_get_tdx_fund_flow",
        lambda code, include_history: {
            "source": "tdx",
            "methodology": "tdx_l1_reconstructed",
            "current": [{"main_net": 120000.0, "small_net": -120000.0}],
            "history": [
                {
                    "date": "2026-09-10",
                    "super_in": 3.0e8,
                    "super_out": 2.0e8,
                    "large_in": 1.0e8,
                    "large_out": 1.5e8,
                    "medium_in": 0.5e8,
                    "medium_out": 0.4e8,
                    "small_in": 0.2e8,
                    "small_out": 0.15e8,
                }
            ],
        },
        raising=False,
    )
    monkeypatch.setattr(
        a_stock,
        "_sina_daily_fund_flow",
        lambda code, history_count, cutoff_date=None: pytest.fail("TDX 历史不应触发新浪"),
    )

    result = a_stock.get_fund_flow("600519", "2026-09-11")

    # 主力 = (3e8 + 1e8) - (2e8 + 1.5e8) = 0.5e8 = 5000 万
    assert "主力净额=5000万" in result
    assert "主力净额=0万" not in result
    # 四档净额透传：超大 +1e8、大 -0.5e8、中 +0.1e8、小 +0.05e8
    assert "超大=10000万" in result
    assert "大=-5000万" in result
    assert "中=1000万" in result
    assert "小=500万" in result


def test_fund_flow_current_displays_five_day_tier_nets(monkeypatch):
    """当日段透传近5日档位净额：legacy large_net/mid_net 列为 5 日聚合值。"""
    from chstockdata import a_stock

    monkeypatch.setattr(
        a_stock,
        "_get_tdx_fund_flow",
        lambda code, include_history: {
            "source": "tdx",
            "methodology": "tdx_l1_reconstructed",
            "current": [
                {
                    "main_net": -332490496.0,
                    "small_net": 332490496.0,
                    "large_net": -404627328.0,
                    "mid_net": 1193373184.0,
                }
            ],
            "history": [],
        },
        raising=False,
    )

    result = a_stock.get_fund_flow("600519", "2026-09-12", include_history=False)

    assert "近5日档位净额" in result
    assert "非东财四档" in result
    assert "大单5日净额=-40463万" in result
    assert "中单5日净额=119337万" in result
    # 未映射字段不得显示，且当日行保持原语义
    assert "超大单5日净额" not in result
    assert "小单5日净额" not in result
    assert "主力净流入=-33249万" in result


def test_fund_flow_current_includes_fork_mapped_super_and_small_5d(monkeypatch):
    """fork 补充映射的 super_net_5d/small_net_5d 存在时一并透传。"""
    from chstockdata import a_stock

    monkeypatch.setattr(
        a_stock,
        "_get_tdx_fund_flow",
        lambda code, include_history: {
            "source": "tdx",
            "methodology": "tdx_l1_reconstructed",
            "current": [
                {
                    "main_net": -58348672.0,
                    "small_net": 58368256.0,
                    "super_net_5d": -786833600.0,
                    "large_net": 128130928.0,
                    "mid_net": 186502480.0,
                    "small_net_5d": -1421968.25,
                }
            ],
            "history": [],
        },
        raising=False,
    )

    result = a_stock.get_fund_flow("000001", "2026-09-12", include_history=False)

    assert "超大单5日净额=-78683万" in result
    assert "大单5日净额=12813万" in result
    assert "中单5日净额=18650万" in result
    assert "小单5日净额=-142万" in result


def test_fund_flow_current_omits_five_day_section_when_absent(monkeypatch):
    """载荷不含任何 5 日档位键时整段省略，不留空标题。"""
    from chstockdata import a_stock

    monkeypatch.setattr(
        a_stock,
        "_get_tdx_fund_flow",
        lambda code, include_history: {
            "source": "tdx",
            "methodology": "tdx_l1_reconstructed",
            "current": [{"main_net": 120000.0, "small_net": -120000.0}],
            "history": [],
        },
        raising=False,
    )

    result = a_stock.get_fund_flow("600519", "2026-09-12", include_history=False)

    assert "近5日档位净额" not in result


def test_industry_prefers_tdx_taxonomy_without_calling_eastmoney(monkeypatch):
    from chstockdata import a_stock

    monkeypatch.setattr(
        a_stock,
        "_get_tdx_industry_ranking",
        lambda top_n: {
            "source": "tdx",
            "taxonomy": "tdx_industry",
            "top": [{"name": "半导体", "change_pct": 3.0, "up_count": 10, "down_count": 2}],
            "bottom": [{"name": "银行", "change_pct": -1.0, "up_count": 2, "down_count": 8}],
        },
        raising=False,
    )
    monkeypatch.setattr(
        a_stock,
        "_get_tdx_concept_ranking",
        lambda top_n: {
            "source": "tdx",
            "taxonomy": "tdx_concept",
            "top": [{"name": "概念甲", "change_pct": 1.5}],
            "bottom": [],
        },
        raising=False,
    )
    monkeypatch.setattr(
        a_stock,
        "_em_get",
        lambda *args, **kwargs: pytest.fail("industry must not call push2"),
    )

    result = a_stock.get_industry_comparison("600519", "2026-08-17", top_n=1)

    assert "Source: TDX" in result
    assert "行业分类: 通达信" in result
    assert "半导体" in result
    assert "银行" in result
    assert "概念甲" in result


def test_industry_uses_sina_after_tdx_failure(monkeypatch):
    from chstockdata import a_stock

    monkeypatch.setattr(
        a_stock,
        "_get_tdx_industry_ranking",
        lambda top_n: (_ for _ in ()).throw(RuntimeError("tdx down")),
        raising=False,
    )
    monkeypatch.setattr(
        a_stock,
        "_get_tdx_concept_ranking",
        lambda top_n: (_ for _ in ()).throw(RuntimeError("tdx down")),
        raising=False,
    )
    monkeypatch.setattr(
        a_stock,
        "_sina_industry_ranking",
        lambda: [
            {"name": "电子", "change_pct": 2.1, "amount": 100.0, "leader": "测试股"}
        ],
        raising=False,
    )
    monkeypatch.setattr(
        a_stock,
        "_em_get",
        lambda *args, **kwargs: pytest.fail("industry must not call push2"),
    )

    result = a_stock.get_industry_comparison("600519", "2026-08-17", top_n=1)

    assert "Source: 新浪财经" in result
    assert "电子" in result
    assert "测试股" in result
    assert "（TDX 概念板块行情暂不可用）" in result
