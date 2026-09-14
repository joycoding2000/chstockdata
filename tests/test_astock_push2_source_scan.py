"""Source-scan guard: Eastmoney push2 URLs must not re-enter the A-share vendor.

运行时行为由 test_astock_tdx_fallback.py 以 monkeypatch 锁死；本文件是结构性
守护--直接扫描源码文本，防止 push2 URL 字面量随未来改动回归（注释/文案中的
历史性提及不受限，仅禁 URL 字面量）。
"""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).parents[1]
_SCANNED = (
    ROOT / "src" / "chstockdata" / "a_stock.py",
    ROOT / "src" / "chstockdata" / "tdx_bridge.py",
    ROOT / "src" / "chstockdata" / "refresh_vipdoc.py",
)


def test_no_push2_url_literals_in_data_plane_sources():
    for path in _SCANNED:
        source = path.read_text(encoding="utf-8")
        assert "push2.eastmoney.com" not in source, f"{path.name} 含 push2 URL 字面量"
        assert "push2his.eastmoney.com" not in source, f"{path.name} 含 push2his URL 字面量"
