"""v0.4.0 Phase 2 — canonical daily-bars schema 锁定测试。

锁死（离线 fixture，零网络；adapters 显式注入，任何未授权 provider 触达
都会以 pytest.fail 炸掉测试）：
- 必需列 / 数值类型 / Date 归一化到日粒度；
- pre_close 只在 provider 真实提供时出现（vipdoc 文件语义），绝不派生；
- units：provider-native passthrough —— 值不做任何 ×100/÷100 换算
  （unit regression，锁死 adjusted_bars 口径红线的"不缩放"约定）；
- merge 语义：supplement 行在重叠日期胜出、按日期升序、无重复日期。
"""

import struct

import pandas as pd
import pytest

from chstockdata.daily_bars import (
    CANONICAL_OPTIONAL_COLUMNS,
    CANONICAL_REQUIRED_COLUMNS,
    fetch_daily_bars,
    fetch_vipdoc_daily_bars,
)
from chstockdata.vendor_errors import VendorNoDataError, VendorNotConfiguredError

CODE = "600519"


@pytest.fixture(autouse=True)
def _fresh_health():
    from chstockdata.capabilities import reset_capability_health

    reset_capability_health()
    yield
    reset_capability_health()


def _write_vipdoc(root, code=CODE, rows=()):
    """rows: (date_int, open_raw, high_raw, low_raw, close_raw, amount, volume)"""
    from chstockdata import vipdoc_history as vh

    market = vh.market_for_code(str(code)).lower()
    path = root / market / "lday" / f"{market}{code}.day"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        b"".join(struct.pack("<IIIIIfII", *row, 0) for row in rows)
    )


def _vipdoc_config(root):
    return {
        "data_cache_dir": str(root),
        "vipdoc_history_dir": None,
        "vipdoc_history_enabled": True,
        "vipdoc_history_max_staleness_days": 5,
    }


def _patch_config(monkeypatch, cfg):
    from chstockdata import config as dataflow_config

    monkeypatch.setattr(dataflow_config, "get_config", lambda: dict(cfg))


def _must_not_run(provider):
    def _adapter(*args, **kwargs):
        pytest.fail(f"{provider} must not be called")

    return _adapter


def _unavailable(provider):
    def _adapter(*args, **kwargs):
        raise VendorNotConfiguredError(f"{provider} unavailable in this test")

    return _adapter


def _vipdoc_chain():
    """真实 vipdoc adapter（config/tmp 包由测试控制）+ fail-fast 其余源。"""
    return {
        "tdx_vipdoc": fetch_vipdoc_daily_bars,
        "mootdx": _must_not_run("mootdx"),
        "sina": _must_not_run("sina"),
    }


# ── 1. 必需列 / 类型 / 日期归一化 ───────────────────────────────────────────


def test_canonical_column_contract(tmp_path, monkeypatch):
    _write_vipdoc(
        tmp_path / "vipdoc",
        rows=[
            (20260908, 10000, 10100, 9900, 10050, 1.0e9, 1000),
            (20260909, 10050, 10200, 9950, 10100, 1.1e9, 1200),
        ],
    )
    _patch_config(monkeypatch, _vipdoc_config(tmp_path))

    result = fetch_daily_bars(
        CODE, "2026-09-08", "2026-09-09", adapters=_vipdoc_chain()
    )

    frame = result.data
    for column in CANONICAL_REQUIRED_COLUMNS:
        assert column in frame.columns
    for column in frame.columns:
        assert column in (*CANONICAL_REQUIRED_COLUMNS, *CANONICAL_OPTIONAL_COLUMNS)
    assert pd.api.types.is_datetime64_any_dtype(frame["Date"])
    assert pd.api.types.is_numeric_dtype(frame["Open"])
    assert pd.api.types.is_numeric_dtype(frame["High"])
    assert pd.api.types.is_numeric_dtype(frame["Low"])
    assert pd.api.types.is_numeric_dtype(frame["Close"])
    assert pd.api.types.is_numeric_dtype(frame["Volume"])
    # Date 归一化到日粒度（午夜，无时间分量）
    assert (frame["Date"] == frame["Date"].dt.normalize()).all()


def test_data_as_of_is_last_business_date_of_bars(tmp_path, monkeypatch):
    _write_vipdoc(
        tmp_path / "vipdoc",
        rows=[
            (20260908, 10000, 10100, 9900, 10050, 1.0e9, 1000),
            (20260909, 10050, 10200, 9950, 10100, 1.1e9, 1200),
        ],
    )
    _patch_config(monkeypatch, _vipdoc_config(tmp_path))

    result = fetch_daily_bars(
        CODE, "2026-09-01", "2026-09-09", adapters=_vipdoc_chain()
    )

    assert result.metadata.data_as_of == "2026-09-09"
    assert result.metadata.observed_at is None, "bars 链无 observation timestamp，不得伪造"


# ── 2. units：provider-native passthrough（unit regression）─────────────────


def test_vipdoc_volume_and_price_pass_through_unscaled(tmp_path, monkeypatch):
    """vipdoc .day 原始记录：价格 uint32 ×100、volume uint32 股、amount 元。

    canonical path 必须原样透传（不引入任何 ×100/÷100 单位换算）。
    """
    _write_vipdoc(
        tmp_path / "vipdoc",
        rows=[
            (20260908, 10000, 10100, 9900, 10050, 1.5e9, 1000),
            (20260909, 10050, 10200, 9950, 10100, 2.5e9, 12345),
        ],
    )
    _patch_config(monkeypatch, _vipdoc_config(tmp_path))

    result = fetch_daily_bars(
        CODE, "2026-09-08", "2026-09-09", adapters=_vipdoc_chain()
    )

    frame = result.data
    assert frame["Close"].tolist() == [100.50, 101.00]
    assert frame["Open"].tolist() == [100.00, 100.50]
    # volume 股数原样：1000 / 12345 —— 不被 ×100 或 ÷100
    assert frame["Volume"].tolist() == [1000, 12345]


def test_mootdx_frame_passes_through_unscaled():
    def _mootdx(code, start, end):
        # TDX wire vol（get_volume 浮点解码），引擎不得改值
        return pd.DataFrame(
            {
                "Date": pd.to_datetime(["2026-09-08", "2026-09-09"]),
                "Open": [10.01, 10.02],
                "High": [10.51, 10.52],
                "Low": [9.81, 9.82],
                "Close": [10.25, 10.26],
                "Volume": [123456.0, 234567.0],
            }
        )

    result = fetch_daily_bars(
        CODE, "2026-09-08", "2026-09-09",
        adapters={
            "tdx_vipdoc": _unavailable("tdx_vipdoc"),
            "mootdx": _mootdx,
            "sina": _must_not_run("sina"),
        },
    )

    assert result.data["Volume"].tolist() == [123456.0, 234567.0]
    assert result.data["Close"].tolist() == [10.25, 10.26]


# ── 3. pre_close 语义 ───────────────────────────────────────────────────────


def test_pre_close_carried_from_vipdoc_file_semantics(tmp_path, monkeypatch):
    """vipdoc pre_close = 完整 .day 文件内前一交易日原始 Close（文件语义）。

    请求窗口裁剪不得用窗口内前一行重新派生（2026-09-08 的 pre_close 必须是
    文件里更早交易日的 close，而不是 NaN/窗口内重算）。
    """
    _write_vipdoc(
        tmp_path / "vipdoc",
        rows=[
            (20260907, 9900, 10000, 9800, 9950, 1.0e9, 900),   # 窗口外
            (20260908, 10000, 10100, 9900, 10050, 1.1e9, 1000),
            (20260909, 10050, 10200, 9950, 10100, 1.2e9, 1100),
        ],
    )
    _patch_config(monkeypatch, _vipdoc_config(tmp_path))

    result = fetch_daily_bars(
        CODE, "2026-09-08", "2026-09-09", adapters=_vipdoc_chain()
    )

    frame = result.data
    assert frame["pre_close"].tolist() == [99.50, 100.50]


def test_pre_close_absent_for_providers_without_it():
    def _mootdx(code, start, end):
        return pd.DataFrame(
            {
                "Date": pd.to_datetime(["2026-09-08"]),
                "Open": [10.0], "High": [10.5], "Low": [9.8],
                "Close": [10.25], "Volume": [123456.0],
            }
        )

    result = fetch_daily_bars(
        CODE, "2026-09-08", "2026-09-08",
        adapters={
            "tdx_vipdoc": _unavailable("tdx_vipdoc"),
            "mootdx": _mootdx,
            "sina": _must_not_run("sina"),
        },
    )

    assert "pre_close" not in result.data.columns, (
        "provider 未提供的字段不得伪造（尤其不得用前一行 close 派生）"
    )


# ── 4. merge 语义（supplement 行胜出 / 升序 / 无重复）────────────────────────


def test_merge_dedupes_ascending_with_supplement_winning():
    def _vipdoc(code, start, end):
        return pd.DataFrame(
            {
                "Date": pd.to_datetime(["2026-09-08", "2026-09-09"]),
                "Open": [100.0, 101.0], "High": [101.0, 102.0],
                "Low": [99.0, 100.0], "Close": [100.5, 101.5],
                "Volume": [1000, 1100],
            }
        )

    def _sina(code, start, end):
        # 整窗返回：重叠日期的新浪行必须胜出（legacy _merge_ohlcv keep-last）
        return pd.DataFrame(
            {
                "Date": pd.to_datetime(
                    ["2026-09-08", "2026-09-09", "2026-09-10"]
                ),
                "Open": [200.0, 201.0, 202.0], "High": [201.0, 202.0, 203.0],
                "Low": [199.0, 200.0, 201.0], "Close": [200.5, 201.5, 202.5],
                "Volume": [9000, 9100, 9200],
            }
        )

    result = fetch_daily_bars(
        CODE, "2026-09-08", "2026-09-10",
        adapters={"tdx_vipdoc": _vipdoc, "mootdx": _vipdoc, "sina": _sina},
    )

    frame = result.data
    assert frame["Date"].is_monotonic_increasing
    assert not frame["Date"].duplicated().any()
    assert frame["Close"].tolist() == [200.5, 201.5, 202.5]
    assert result.metadata.providers_used == ["tdx_vipdoc", "sina"]


def test_empty_result_carries_canonical_columns():
    def _empty(code, start, end):
        raise VendorNoDataError("nothing")

    result = fetch_daily_bars(
        CODE, "2026-09-08", "2026-09-09",
        adapters={"tdx_vipdoc": _empty, "mootdx": _empty, "sina": _empty},
    )

    assert list(result.data.columns) == list(CANONICAL_REQUIRED_COLUMNS)


# ── 5. 缺失 vipdoc 包时的 not_configured 路由（默认 conftest stub 语义）──────


def test_missing_vipdoc_file_is_not_configured_not_network(tmp_path, monkeypatch):
    _patch_config(monkeypatch, _vipdoc_config(tmp_path))  # 无 vipdoc 树

    with pytest.raises(VendorNotConfiguredError):
        fetch_vipdoc_daily_bars(CODE, "2026-09-08", "2026-09-09")
