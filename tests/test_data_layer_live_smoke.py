"""活体数据门：真实网络数据层冒烟（``network`` 标记，默认套件排除）。

设计约束（与源仓库 DEC-P4-01/06 一致）：

- 仅覆盖零鉴权免费主力源：腾讯 → mootdx(TCP) → 新浪。**东财端点刻意排除**——
  CI runner 是数据中心 IP，东财有封禁 IDC 的在案历史，活体门不得把 runner IP
  暴露给东财限流；东财端点的手动验收另行执行。
- 断言看字段不看长度：关键字段存在 + 数值合法，不复制 ``length > 50`` 弱判定。
- 触发：``live-data-gate`` workflow 的 scheduled（A 股交易日早晨）+
  ``workflow_dispatch`` 手动；本地单独运行用 ``pytest -m network``。
- 这是观察性哨兵而非合并门：失败反映"外部端点死亡/改版"，与代码变更无关。
"""

import datetime as dt

import pytest

from chstockdata import (
    get_free_financial_indicators,
    get_realtime_snapshot,
    get_stock_data,
)
from chstockdata.etf_options import get_etf_option_chain

pytestmark = pytest.mark.network

# 常年成交、三表数据完整的基准样本；不要换成小盘股（停牌/缺数据会造成假阴性）。
TICKER = "600519"


def test_realtime_snapshot_returns_price_name_and_source():
    """腾讯→mootdx→新浪 实时链至少一源存活，且快照字段级完整。"""
    snap = get_realtime_snapshot(TICKER)
    assert snap.get("status") == "ready", snap
    assert snap.get("ticker") == TICKER
    assert snap.get("name"), f"quote name must be non-empty: {snap}"
    price = snap.get("price")
    assert price is not None and price > 0, f"price must be positive: {snap}"
    source = str(snap.get("source") or "")
    assert source and source != "unknown", f"quote source missing: {snap}"


def test_stock_data_returns_recent_daily_bars():
    """mootdx→新浪 K 线链在近 45 天窗口内给出字段级合法的日线。"""
    end = dt.date.today()
    start = end - dt.timedelta(days=45)
    payload = get_stock_data(TICKER, start.isoformat(), end.isoformat())
    lines = [ln for ln in payload.splitlines() if ln.strip()]
    header_idx = next(
        (i for i, ln in enumerate(lines) if ln.lower().startswith("date,")),
        None,
    )
    assert header_idx is not None, f"no CSV header in payload:\n{payload[:400]}"
    columns = [c.strip().lower() for c in lines[header_idx].split(",")]
    close_idx = columns.index("close")
    rows = lines[header_idx + 1 :]
    assert len(rows) >= 10, (
        f"expected >=10 trading bars in a 45d window, got {len(rows)}:\n{payload[:400]}"
    )
    last_close = float(rows[-1].split(",")[close_idx])
    assert last_close > 0, f"last close must be positive, got {last_close}"


def test_free_financial_indicators_derive_from_sina():
    """新浪三表链路存活且派生指标给出真实数值（issues/006 回归哨兵）。"""
    today = dt.date.today().isoformat()
    text = get_free_financial_indicators(TICKER, today)
    assert "sina_derived" in text, f"source marker missing:\n{text[:400]}"
    assert "report_period_end:" in text, f"report period missing:\n{text[:400]}"
    # 字段级：核心值行必须带数值而不是"不可用"占位（600519 常年有完整季报）。
    for label in ("营业收入", "净利润"):
        line = next(
            (ln for ln in text.splitlines() if ln.startswith(f"- {label}:")), None
        )
        assert line is not None, f"'{label}' line missing:\n{text[:400]}"
        assert "不可用" not in line, f"'{label}' has no value: {line}"
        value = float(line.rsplit(":", 1)[1])
        assert value != 0, f"'{label}' unexpectedly zero: {line}"


def test_sh_etf_realtime_quote_routes_to_shanghai():
    """5x 沪市 ETF 路由哨兵：腾讯/新浪链路必须能取到 510050 实时快照。"""
    snap = get_realtime_snapshot("510050")
    assert snap.get("status") == "ready", snap
    assert snap.get("price") is not None and snap["price"] > 0, snap


def test_etf_option_chain_returns_field_level_payload():
    """新浪期权链存活：合约清单 + T 型报价 + 希腊字母字段级完整。"""
    chain = get_etf_option_chain("510050")
    assert chain["underlying"] == "510050"
    month = str(chain["month"])
    assert month.isdigit() and len(month) == 4, chain["month"]
    assert chain["rows"], f"no quoted contracts: {chain}"
    row = next(
        (item for item in chain["rows"] if item.get("strike") and item.get("last")),
        None,
    )
    assert row is not None, f"no readable contract in chain: {chain['rows'][:3]}"
    assert row["name"], row
    greeks = row.get("greeks") or {}
    assert greeks.get("iv") is not None and greeks["iv"] > 0, greeks
    assert greeks.get("delta") is not None, greeks
