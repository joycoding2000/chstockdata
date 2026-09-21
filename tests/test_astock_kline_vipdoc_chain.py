"""raw/D 日线本地 vipdoc 优先链接入回归测试（计划 Task 3）。

链接入语义：``adjust="raw"`` 且 ``period="D"`` 时优先本地官方 vipdoc 包；
本地不可用/过期/区间无数据 → 回落既有 mootdx→新浪链；flag off / 非 raw /
非 D 行为与现状一致。默认套件由 conftest 把本地层剥离；本文件用
``allow_vipdoc_history`` 标记走真实读取器（指向 ``tmp_path``，不触碰机器缓存）。
"""

import struct
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from chstockdata import a_stock
from chstockdata import vipdoc_history as vh

pytestmark = pytest.mark.allow_vipdoc_history


# ── helpers ─────────────────────────────────────────────────────────────────


def _record(date_raw, o, h, low, c, amount, volume):
    return struct.pack("<IIIIIfII", date_raw, o, h, low, c, amount, volume, 0)


def _write_vipdoc(root: Path, code="600519", days=("20260908", "20260909")) -> None:
    market = vh.market_for_code(code).lower()
    path = root / market / "lday" / f"{market}{code}.day"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = b"".join(
        _record(int(day), 10000 + i, 10100 + i, 9900 + i, 10050 + i, 1.0e9, 1000 + i)
        for i, day in enumerate(days)
    )
    path.write_bytes(payload)


def _vipdoc_config(cache_root: Path, **overrides):
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
    """``_fetch_mootdx_bars`` 的真实返回形状：归一化后的 Date 列帧。

    Phase 2.1 canonical validation 起引擎会拒绝缺 Date 列的非空帧
    （failed_structure）——旧版这里的 datetime-index 形状曾被"真实新浪
    兜底"意外掩盖，属于测试对网络的隐式依赖，必须用真实契约形状。
    """
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


def _fake_adjusted_result(days=("2026-09-08", "2026-09-09")):
    return SimpleNamespace(
        frame=_mootdx_frame(days),
        factor_source="fake",
        anchor_date=None,
        limitations=[],
    )


# ── 1. 本地优先 ─────────────────────────────────────────────────────────────


def test_raw_daily_uses_local_vipdoc_as_base(tmp_path, monkeypatch):
    cache_root = tmp_path / "cache"
    _write_vipdoc(cache_root / "vipdoc")
    _patch_config(monkeypatch, _vipdoc_config(cache_root))
    monkeypatch.setattr(
        a_stock,
        "_fetch_mootdx_bars",
        lambda *args, **kwargs: pytest.fail("本地命中时不得触发 mootdx 探测"),
    )
    monkeypatch.setattr(
        a_stock,
        "_sina_kline_fallback",
        lambda *args, **kwargs: pytest.fail("本地已覆盖区间，不得补新浪"),
    )

    result = a_stock.get_stock_data("600519", "2026-09-08", "2026-09-09")

    assert "# Data source: vipdoc local (TDX official hsjday package)" in result
    assert "# Total records: 2" in result
    assert "2026-09-08,100.0,101.0,99.0,100.5,1000" in result
    assert "2026-09-09,100.01,101.01,99.01,100.51,1001" in result
    header = next(line for line in result.splitlines() if line.startswith("Date,"))
    assert header == "Date,Open,High,Low,Close,Volume"


def test_raw_daily_local_base_reaches_back_beyond_800_bars(tmp_path, monkeypatch):
    """本地包不受在线 800 根窗口限制（同一路径的旧区间请求可直接命中）。"""
    cache_root = tmp_path / "cache"
    _write_vipdoc(cache_root / "vipdoc", days=("20200102", "20200103"))
    _patch_config(monkeypatch, _vipdoc_config(cache_root))
    monkeypatch.setattr(
        a_stock, "_fetch_mootdx_bars", lambda *args, **kwargs: pytest.fail("不得探测")
    )

    result = a_stock.get_stock_data("600519", "2020-01-02", "2020-01-03")

    assert "# Data source: vipdoc local (TDX official hsjday package)" in result
    assert "# Total records: 2" in result


# ── 2. flag off / 非 raw / 非 D 与现状一致 ─────────────────────────────────


def test_flag_off_keeps_existing_mootdx_chain(tmp_path, monkeypatch):
    cache_root = tmp_path / "cache"
    _write_vipdoc(cache_root / "vipdoc")
    _patch_config(
        monkeypatch, _vipdoc_config(cache_root, vipdoc_history_enabled=False)
    )
    calls = []

    def _mootdx(*args, **kwargs):
        calls.append(True)
        return _mootdx_frame()

    monkeypatch.setattr(a_stock, "_fetch_mootdx_bars", _mootdx)

    result = a_stock.get_stock_data("600519", "2026-09-08", "2026-09-09")

    assert calls, "flag off 时必须走既有 mootdx 链"
    assert "# Data source: mootdx (TCP)" in result


def test_adjusted_and_non_daily_paths_skip_vipdoc(tmp_path, monkeypatch):
    cache_root = tmp_path / "cache"
    _write_vipdoc(cache_root / "vipdoc")
    _patch_config(monkeypatch, _vipdoc_config(cache_root))
    monkeypatch.setattr(
        a_stock,
        "_load_vipdoc_ohlcv_frame",
        lambda *args, **kwargs: pytest.fail("非 raw/D 不得读取 vipdoc"),
    )
    monkeypatch.setattr(a_stock, "_fetch_mootdx_bars", lambda *args, **kwargs: _mootdx_frame())
    monkeypatch.setattr(
        "chstockdata.adjusted_bars.get_adjusted_bars",
        lambda *args, **kwargs: _fake_adjusted_result(),
    )

    qfq = a_stock.get_stock_data("600519", "2026-09-08", "2026-09-09", adjust="qfq")
    weekly = a_stock.get_stock_data("600519", "2026-09-08", "2026-09-09", period="W")

    assert "# Data source: mootdx (TCP)" in qfq
    assert "# Data source: mootdx (TCP)" in weekly


# ── 3. 本地不可用 / 过期 / 缺失 → 回落现有链 ──────────────────────────────


def test_missing_local_tree_falls_back_to_mootdx(tmp_path, monkeypatch):
    cache_root = tmp_path / "cache"  # 无 vipdoc 树
    _patch_config(monkeypatch, _vipdoc_config(cache_root))
    monkeypatch.setattr(a_stock, "_fetch_mootdx_bars", lambda *args, **kwargs: _mootdx_frame())

    result = a_stock.get_stock_data("600519", "2026-09-08", "2026-09-09")

    assert "# Data source: mootdx (TCP)" in result


def test_stale_local_package_falls_back_to_mootdx(tmp_path, monkeypatch):
    cache_root = tmp_path / "cache"
    _write_vipdoc(cache_root / "vipdoc", days=("20260801",))
    _patch_config(
        monkeypatch,
        _vipdoc_config(cache_root, vipdoc_history_max_staleness_days=5),
    )
    monkeypatch.setattr(a_stock, "_fetch_mootdx_bars", lambda *args, **kwargs: _mootdx_frame())

    result = a_stock.get_stock_data("600519", "2026-09-08", "2026-09-09")

    assert "# Data source: mootdx (TCP)" in result


def test_local_window_with_no_rows_falls_back_to_mootdx(tmp_path, monkeypatch):
    cache_root = tmp_path / "cache"
    _write_vipdoc(cache_root / "vipdoc", days=("20260908",))
    _patch_config(monkeypatch, _vipdoc_config(cache_root))
    monkeypatch.setattr(a_stock, "_fetch_mootdx_bars", lambda *args, **kwargs: _mootdx_frame())

    result = a_stock.get_stock_data("600519", "2026-09-09", "2026-09-09")

    assert "# Data source: mootdx (TCP)" in result


# ── 4. 本地缺最新交易日 → 有界新浪补齐 ─────────────────────────────────────


def test_partial_local_window_is_supplemented_by_sina(tmp_path, monkeypatch):
    cache_root = tmp_path / "cache"
    _write_vipdoc(cache_root / "vipdoc", days=("20260908", "20260909"))
    _patch_config(monkeypatch, _vipdoc_config(cache_root))
    monkeypatch.setattr(
        a_stock, "_fetch_mootdx_bars", lambda *args, **kwargs: pytest.fail("不得探测")
    )

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

    monkeypatch.setattr(a_stock, "_sina_kline_fallback", _sina)

    result = a_stock.get_stock_data("600519", "2026-09-08", "2026-09-10")

    assert (
        "# Data source: vipdoc local (TDX official hsjday package) + sina HTTP supplement"
        in result
    )
    assert "2026-09-10,101.0,102.0,100.0,101.5,1234" in result


# ── 5. 配置键：默认值 / env 覆盖 / 校验 ─────────────────────────────────────


@pytest.fixture()
def fresh_config():
    from chstockdata.config import reset_config

    reset_config()
    yield
    reset_config()


def test_vipdoc_defaults(fresh_config):
    from chstockdata.config import get_config

    cfg = get_config()
    assert cfg["vipdoc_history_enabled"] is True
    assert cfg["vipdoc_history_dir"] is None
    assert cfg["vipdoc_history_max_staleness_days"] == 5
    assert cfg["vipdoc_history_url"].startswith("https://data.tdx.com.cn/")


def test_vipdoc_env_overrides_are_typed(fresh_config, monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_VIPDOC_HISTORY_ENABLED", "false")
    monkeypatch.setenv("TRADINGAGENTS_VIPDOC_HISTORY_DIR", "D:/vipdoc-test")
    monkeypatch.setenv("TRADINGAGENTS_VIPDOC_HISTORY_MAX_STALENESS_DAYS", "7.5")

    from chstockdata.config import get_config

    cfg = get_config()
    assert cfg["vipdoc_history_enabled"] is False
    assert cfg["vipdoc_history_dir"] == "D:/vipdoc-test"
    assert cfg["vipdoc_history_max_staleness_days"] == 7.5
    assert isinstance(cfg["vipdoc_history_max_staleness_days"], float)


def test_validate_vipdoc_history_config_rejects_bad_values():
    from chstockdata.config import validate_vipdoc_history_config

    validate_vipdoc_history_config({})  # defaults are valid
    with pytest.raises(ValueError):
        validate_vipdoc_history_config({"vipdoc_history_enabled": "yes"})
    with pytest.raises(ValueError):
        validate_vipdoc_history_config({"vipdoc_history_max_staleness_days": -1})
    with pytest.raises(ValueError):
        validate_vipdoc_history_config(
            {"vipdoc_history_max_staleness_days": float("nan")}
        )
    with pytest.raises(ValueError):
        validate_vipdoc_history_config({"vipdoc_history_dir": 123})
    with pytest.raises(ValueError):
        validate_vipdoc_history_config({"vipdoc_history_url": ["x"]})
