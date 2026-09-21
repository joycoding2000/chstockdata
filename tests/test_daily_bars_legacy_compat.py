"""v0.4.0 Phase 2 — get_stock_data 公共契约冻结测试（structured path 承载后）。

目标是证明：raw/D 主路径改由 ``daily_bars.fetch_daily_bars`` 承载后，
``get_stock_data`` 的用户可见输出逐字不变：

- signature / 列顺序 / 日期顺序不变；
- ``# Data source`` 标注逐字不变（含 supplement 后缀规则）；
- 空结果、双源失败、stale coverage 的错误 envelope 逐字不变；
- vipdoc 文件的 pre_close/Amount 不泄漏进 CSV；
- 非 raw / 非 D 路径仍走既有 mootdx 链、不触 vipdoc。
"""

import struct
from types import SimpleNamespace

import pandas as pd
import pytest

from chstockdata import a_stock
from chstockdata import vipdoc_history as vh

pytestmark = pytest.mark.allow_vipdoc_history

CODE = "600519"


@pytest.fixture(autouse=True)
def _fresh_health():
    from chstockdata.capabilities import reset_capability_health

    reset_capability_health()
    yield
    reset_capability_health()


# ── helpers ─────────────────────────────────────────────────────────────────


def _record(date_raw, o, h, low, c, amount, volume):
    return struct.pack("<IIIIIfII", date_raw, o, h, low, c, amount, volume, 0)


def _write_vipdoc(root: object, code=CODE, days=("20260908", "20260909")) -> None:
    market = vh.market_for_code(code).lower()
    path = root / market / "lday" / f"{market}{code}.day"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = b"".join(
        _record(int(day), 10000 + i, 10100 + i, 9900 + i, 10050 + i, 1.0e9, 1000 + i)
        for i, day in enumerate(days)
    )
    path.write_bytes(payload)


def _vipdoc_config(cache_root, **overrides):
    cfg = {
        "data_cache_dir": str(cache_root),
        "vipdoc_history_dir": None,
        "vipdoc_history_enabled": True,
        "vipdoc_history_max_staleness_days": 5,
    }
    cfg.update(overrides)
    return cfg


def _patch_config(monkeypatch, cfg):
    from chstockdata import config as dataflow_config

    monkeypatch.setattr(dataflow_config, "get_config", lambda: dict(cfg))


def _mootdx_frame(days=("2026-09-08", "2026-09-09")):
    """归一化后的 mootdx 帧（``_fetch_mootdx_bars`` 真实返回形状：Date 列）。"""
    return pd.DataFrame(
        {
            "Date": pd.to_datetime(list(days)),
            "Open": [1.0] * len(days),
            "High": [1.1] * len(days),
            "Low": [0.9] * len(days),
            "Close": [1.05] * len(days),
            "Volume": [100.0] * len(days),
        }
    )


def _payload_lines(result: str) -> list[str]:
    """去掉时间敏感的 retrieved-on 行，其余逐字比对。"""
    return [
        line
        for line in result.splitlines()
        if not line.startswith("# Data retrieved on:")
    ]


# ── 1. vipdoc 命中：完整输出契约 ─────────────────────────────────────────────


def test_vipdoc_hit_output_contract_frozen(tmp_path, monkeypatch):
    _write_vipdoc(tmp_path / "vipdoc")
    _patch_config(monkeypatch, _vipdoc_config(tmp_path))

    def _no_mootdx(*args, **kwargs):
        pytest.fail("本地命中时不得触发 mootdx")

    def _no_sina(*args, **kwargs):
        pytest.fail("本地已覆盖区间，不得触新浪")

    monkeypatch.setattr(a_stock, "_fetch_mootdx_bars", _no_mootdx)
    monkeypatch.setattr(a_stock, "_sina_kline_fallback", _no_sina)

    result = a_stock.get_stock_data(CODE, "2026-09-08", "2026-09-09")

    assert _payload_lines(result) == [
        "# Stock data for 600519 (A-stock) from 2026-09-08 to 2026-09-09",
        "# Total records: 2",
        "# Data source: vipdoc local (TDX official hsjday package)",
        "# Price basis: RAW（对应日期实际历史价格；除权跳变未消除）",
        "# Period: D",
        "# Observed date range: 2026-09-08 to 2026-09-09",
        "",
        "Date,Open,High,Low,Close,Volume",
        "2026-09-08,100.0,101.0,99.0,100.5,1000",
        "2026-09-09,100.01,101.01,99.01,100.51,1001",
    ]


def test_vipdoc_pre_close_and_amount_do_not_leak_into_csv(tmp_path, monkeypatch):
    """canonical 帧携带 pre_close，但 legacy CSV 列契约必须不变。"""
    _write_vipdoc(
        tmp_path / "vipdoc",
        days=("20260907", "20260908", "20260909"),
    )
    _patch_config(monkeypatch, _vipdoc_config(tmp_path))

    result = a_stock.get_stock_data(CODE, "2026-09-08", "2026-09-09")

    header = next(line for line in result.splitlines() if line.startswith("Date,"))
    assert header == "Date,Open,High,Low,Close,Volume"
    assert "pre_close" not in result
    assert "Amount" not in result


# ── 2. 在线链路标注 ─────────────────────────────────────────────────────────


def test_mootdx_chain_label_frozen(tmp_path, monkeypatch):
    cache_root = tmp_path  # 无 vipdoc 树
    _patch_config(monkeypatch, _vipdoc_config(cache_root))
    monkeypatch.setattr(a_stock, "_fetch_mootdx_bars", lambda *a, **k: _mootdx_frame())
    monkeypatch.setattr(
        a_stock, "_sina_kline_fallback",
        lambda *a, **k: pytest.fail("mootdx 成功时不得触新浪"),
    )

    result = a_stock.get_stock_data(CODE, "2026-09-08", "2026-09-09")

    assert "# Data source: mootdx (TCP)" in result


def test_sina_fallback_label_frozen(tmp_path, monkeypatch):
    _patch_config(monkeypatch, _vipdoc_config(tmp_path))
    monkeypatch.setattr(
        a_stock, "_fetch_mootdx_bars", lambda *a, **k: (_ for _ in ()).throw(Exception("down"))
    )
    monkeypatch.setattr(
        a_stock,
        "_sina_kline_fallback",
        lambda *a, **k: _mootdx_frame(),
    )

    result = a_stock.get_stock_data(CODE, "2026-09-08", "2026-09-09")

    assert "# Data source: sina HTTP (fallback)" in result


def test_supplement_suffix_rule_frozen(tmp_path, monkeypatch):
    """base 未到 end 且新浪实际推进末根 → 保留 legacy 双段标注。"""
    _write_vipdoc(tmp_path / "vipdoc")  # ends 2026-09-09
    _patch_config(monkeypatch, _vipdoc_config(tmp_path))

    def _sina(code, start_date=None, end_date=None, **kwargs):
        return pd.DataFrame(
            {
                "Date": pd.to_datetime(["2026-09-10"]),
                "Open": [101.0],
                "High": [102.0],
                "Low": [100.0],
                "Close": [101.5],
                "Volume": [1234],
            }
        )

    monkeypatch.setattr(a_stock, "_fetch_mootdx_bars", lambda *a, **k: pytest.fail("不得探测"))
    monkeypatch.setattr(a_stock, "_sina_kline_fallback", _sina)

    result = a_stock.get_stock_data(CODE, "2026-09-08", "2026-09-10")

    assert (
        "# Data source: vipdoc local (TDX official hsjday package) + sina HTTP supplement"
        in result
    )
    assert "2026-09-10,101.0,102.0,100.0,101.5,1234" in result


# ── 3. 空/失败 envelope ─────────────────────────────────────────────────────


def test_both_sources_down_legacy_error_envelope(tmp_path, monkeypatch):
    _patch_config(monkeypatch, _vipdoc_config(tmp_path))
    monkeypatch.setattr(
        a_stock, "_fetch_mootdx_bars", lambda *a, **k: (_ for _ in ()).throw(Exception("down"))
    )
    monkeypatch.setattr(
        a_stock, "_sina_kline_fallback", lambda *a, **k: (_ for _ in ()).throw(Exception("down"))
    )

    result = a_stock.get_stock_data(CODE, "2026-09-08", "2026-09-09")

    assert result == "K线数据获取失败：mootdx和新浪备用源均不可用，请检查网络连接"


def test_window_empty_legacy_message(tmp_path, monkeypatch):
    """mootdx 成功但 800 根窗口与请求窗口无交集。"""
    _patch_config(monkeypatch, _vipdoc_config(tmp_path))
    monkeypatch.setattr(
        a_stock, "_fetch_mootdx_bars", lambda *a, **k: _mootdx_frame(days=("2020-01-02",))
    )
    monkeypatch.setattr(a_stock, "_sina_kline_fallback", lambda *a, **k: pd.DataFrame())

    result = a_stock.get_stock_data(CODE, "2026-09-08", "2026-09-09")

    assert result == "No data found for A-stock '600519' between 2026-09-08 and 2026-09-09"


def test_stale_coverage_legacy_message(tmp_path, monkeypatch):
    _patch_config(monkeypatch, _vipdoc_config(tmp_path))
    monkeypatch.setattr(
        a_stock, "_fetch_mootdx_bars", lambda *a, **k: _mootdx_frame(days=("2026-08-20",))
    )
    monkeypatch.setattr(a_stock, "_sina_kline_fallback", lambda *a, **k: pd.DataFrame())

    result = a_stock.get_stock_data(CODE, "2026-08-20", "2026-09-09")

    assert result == (
        "[数据缺失] historical_ohlcv_stale: 600519 requested_end=2026-09-09 "
        "observed_max=2026-08-20 gap_days=20"
    )


# ── 4. 非 structured 路径行为保持 ────────────────────────────────────────────


def test_flag_off_keeps_existing_mootdx_chain(tmp_path, monkeypatch):
    _write_vipdoc(tmp_path / "vipdoc")
    _patch_config(
        monkeypatch, _vipdoc_config(tmp_path, vipdoc_history_enabled=False)
    )
    calls = []

    def _mootdx(*args, **kwargs):
        calls.append(True)
        return _mootdx_frame()

    monkeypatch.setattr(a_stock, "_fetch_mootdx_bars", _mootdx)

    result = a_stock.get_stock_data(CODE, "2026-09-08", "2026-09-09")

    assert calls, "flag off 时必须走既有 mootdx 链"
    assert "# Data source: mootdx (TCP)" in result


def test_adjusted_and_non_daily_paths_skip_vipdoc(tmp_path, monkeypatch):
    _write_vipdoc(tmp_path / "vipdoc")
    _patch_config(monkeypatch, _vipdoc_config(tmp_path))
    monkeypatch.setattr(
        a_stock,
        "_load_vipdoc_ohlcv_frame",
        lambda *args, **kwargs: pytest.fail("非 raw/D 不得读取 vipdoc"),
    )
    monkeypatch.setattr(a_stock, "_fetch_mootdx_bars", lambda *a, **k: _mootdx_frame())

    def _fake_adjusted(*args, **kwargs):
        return SimpleNamespace(
            frame=_mootdx_frame(), factor_source="fake", anchor_date=None, limitations=[]
        )

    monkeypatch.setattr(
        "chstockdata.adjusted_bars.get_adjusted_bars", _fake_adjusted
    )

    qfq = a_stock.get_stock_data(CODE, "2026-09-08", "2026-09-09", adjust="qfq")
    weekly = a_stock.get_stock_data(CODE, "2026-09-08", "2026-09-09", period="W")

    assert "# Data source: mootdx (TCP)" in qfq
    assert "# Data source: mootdx (TCP)" in weekly


# ── 5. _get_close_on_date：structured bars 直读（不再解析文本）───────────────


def test_get_close_on_date_matches_get_stock_data_rendered_value(
    tmp_path, monkeypatch
):
    """同一 fixture：structured 直读值 == 渲染文本解析值（round(2) 对齐）。"""
    _write_vipdoc(tmp_path / "vipdoc")
    _patch_config(monkeypatch, _vipdoc_config(tmp_path))
    monkeypatch.setattr(
        a_stock, "_fetch_mootdx_bars", lambda *a, **k: pytest.fail("不得探测")
    )

    rendered = a_stock.get_stock_data(CODE, "2026-09-09", "2026-09-09")
    csv_line = next(
        line for line in rendered.splitlines() if line.startswith("2026-09-09,")
    )
    parsed_close = float(csv_line.split(",")[4])

    assert a_stock._get_close_on_date(CODE, "2026-09-09") == parsed_close == 100.51


def test_get_close_on_date_via_mootdx_path(tmp_path, monkeypatch):
    _patch_config(monkeypatch, _vipdoc_config(tmp_path))  # 无 vipdoc 树
    monkeypatch.setattr(a_stock, "_fetch_mootdx_bars", lambda *a, **k: _mootdx_frame())
    monkeypatch.setattr(
        a_stock, "_sina_kline_fallback",
        lambda *a, **k: pytest.fail("mootdx 成功时不得触新浪"),
    )

    assert a_stock._get_close_on_date(CODE, "2026-09-08") == 1.05


def test_get_close_on_date_none_on_unavailable(tmp_path, monkeypatch):
    _patch_config(monkeypatch, _vipdoc_config(tmp_path))  # 无 vipdoc 树
    monkeypatch.setattr(
        a_stock, "_fetch_mootdx_bars", lambda *a, **k: (_ for _ in ()).throw(Exception("down"))
    )
    monkeypatch.setattr(
        a_stock, "_sina_kline_fallback", lambda *a, **k: pd.DataFrame()
    )

    assert a_stock._get_close_on_date(CODE, "2026-09-08") is None
