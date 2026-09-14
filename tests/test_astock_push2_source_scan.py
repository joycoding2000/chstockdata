"""Source-scan guard: Eastmoney push2 URLs must not re-enter the A-share vendor.

运行时行为由 test_astock_tdx_fallback.py 以 monkeypatch 锁死；本文件是结构性
守护--直接扫描源码文本，防止 push2 URL 字面量随未来改动回归（注释/文案中的
历史性提及不受限，仅禁 URL 字面量）。

范围在反向移植轮（v0.2.0）扩展至全部新增模块：期权（新浪）、打板层
（push2ex 专题池，允许）、筹码（本地+baostock）、板块资金流（bkzj 非 push2）、
互动易（巨潮）、热榜（同花顺 + emappdata）。
"""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).parents[1]
_SCANNED = (
    ROOT / "src" / "chstockdata" / "a_stock.py",
    ROOT / "src" / "chstockdata" / "tdx_bridge.py",
    ROOT / "src" / "chstockdata" / "refresh_vipdoc.py",
    ROOT / "src" / "chstockdata" / "etf_options.py",
    ROOT / "src" / "chstockdata" / "limit_up.py",
    ROOT / "src" / "chstockdata" / "chips.py",
    ROOT / "src" / "chstockdata" / "board_flow.py",
    ROOT / "src" / "chstockdata" / "investor_qa.py",
    ROOT / "src" / "chstockdata" / "hot_rank.py",
)


def test_no_push2_url_literals_in_data_plane_sources():
    for path in _SCANNED:
        source = path.read_text(encoding="utf-8")
        assert "push2.eastmoney.com" not in source, f"{path.name} 含 push2 URL 字面量"
        assert "push2his.eastmoney.com" not in source, f"{path.name} 含 push2his URL 字面量"


def test_limit_up_uses_the_push2ex_topic_pool_domain_only():
    """打板层允许 push2ex（专题池，与 push2 是不同端点），但不得含 push2。"""
    source = (ROOT / "src" / "chstockdata" / "limit_up.py").read_text(encoding="utf-8")
    assert "push2ex.eastmoney.com" in source
