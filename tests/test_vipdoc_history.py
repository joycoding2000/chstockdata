"""vipdoc 本地日线读取器契约测试（计划 Task 1）。

官方盘后数据包（hsjday.zip）内的 ``.day`` 记录为 32B 小端定长：
``date``(uint32 YYYYMMDD) + OHLC(uint32 ×100) + ``amount``(float32) +
``volume``(uint32) + ``reserved``(uint32)。这些用例用离线 golden buffer
固定记录布局、价格/量/额缩放与 sh/sz/bj（含 920 号段）路由，不发任何网络请求。
"""

import json
import struct
from pathlib import Path

import pandas as pd
import pytest

from chstockdata import vipdoc_history as vh

_COLUMNS = ["Date", "Open", "High", "Low", "Close", "pre_close", "Volume", "Amount"]


def _record(date_raw, o, h, low, c, amount, volume):
    return struct.pack("<IIIIIfII", date_raw, o, h, low, c, amount, volume, 0)


def _golden_bytes():
    return (
        _record(20260908, 131800, 132300, 130905, 130930, 4.2e9, 1753404)
        + _record(20260909, 130501, 130930, 128668, 129088, 3.1e9, 3222611)
        # 不完整尾记录（模拟坏文件截断）：必须跳过并计数，不能抛错。
        + b"\x00" * 8
    )


def _write_day(path: Path, records: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(records)


# ── 1. 解析器：golden 布局 / 缩放 / 无效记录 ────────────────────────────────


def test_parse_day_file_golden_layout_scales_and_skips_invalid(tmp_path):
    path = tmp_path / "sh600519.day"
    # 一条 date=0 的坏记录 + 两条有效记录 + 截断尾记录。
    payload = b"\x00" * 32 + _golden_bytes()
    path.write_bytes(payload)

    frame = vh.parse_day_file(path)

    assert list(frame.columns) == _COLUMNS
    assert len(frame) == 2

    first = frame.iloc[0]
    assert first["Date"] == pd.Timestamp("2026-09-08")
    assert first["Open"] == pytest.approx(1318.0)
    assert first["High"] == pytest.approx(1323.0)
    assert first["Low"] == pytest.approx(1309.05)
    assert first["Close"] == pytest.approx(1309.30)
    assert pd.isna(first["pre_close"])
    assert first["Volume"] == 1753404
    assert first["Amount"] == pytest.approx(4.2e9, rel=1e-6)

    second = frame.iloc[1]
    assert second["Date"] == pd.Timestamp("2026-09-09")
    assert second["Close"] == pytest.approx(1290.88)
    assert second["pre_close"] == pytest.approx(1309.30)
    assert second["Amount"] == pytest.approx(3.1e9, rel=1e-6)


def test_parse_day_file_empty_file_returns_contract_frame(tmp_path):
    path = tmp_path / "sh600519.day"
    path.write_bytes(b"")

    frame = vh.parse_day_file(path)

    assert list(frame.columns) == _COLUMNS
    assert frame.empty


def test_parse_day_file_sorts_and_deduplicates_by_date(tmp_path):
    path = tmp_path / "sh600519.day"
    path.write_bytes(
        _record(20260909, 1, 1, 1, 1, 1.0, 1)
        + _record(20260908, 2, 2, 2, 2, 2.0, 2)
        + _record(20260909, 3, 3, 3, 3, 3.0, 3)
    )

    frame = vh.parse_day_file(path)

    assert frame["Date"].tolist() == [pd.Timestamp("2026-09-08"), pd.Timestamp("2026-09-09")]
    assert frame.iloc[-1]["Close"] == pytest.approx(0.03)


# ── 2. 读取器：路由 / 日期过滤 / 缺失语义 ──────────────────────────────────


def test_load_vipdoc_daily_routes_sh_sz_bj_and_filters_dates(tmp_path):
    _write_day(tmp_path / "sh" / "lday" / "sh600519.day", _golden_bytes())
    _write_day(tmp_path / "sz" / "lday" / "sz000001.day", _golden_bytes())
    _write_day(tmp_path / "bj" / "lday" / "bj920185.day", _golden_bytes())

    sh = vh.load_vipdoc_daily("600519", "2026-09-08", "2026-09-08", root=tmp_path)
    sz = vh.load_vipdoc_daily("000001", None, None, root=tmp_path)
    bj = vh.load_vipdoc_daily("920185", None, None, root=tmp_path)

    assert sh is not None and len(sh) == 1
    assert sh.iloc[0]["Date"] == pd.Timestamp("2026-09-08")
    assert sz is not None and len(sz) == 2
    assert bj is not None and len(bj) == 2
    assert list(bj.columns) == _COLUMNS


def test_load_vipdoc_daily_derives_pre_close_before_window_filter(tmp_path):
    path = tmp_path / "sh" / "lday" / "sh600519.day"
    _write_day(
        path,
        _record(20260907, 100, 110, 90, 100, 1.0, 10)
        + _record(20260908, 101, 111, 91, 105, 2.0, 20),
    )

    frame = vh.load_vipdoc_daily("600519", "2026-09-08", "2026-09-08", root=tmp_path)

    assert "pre_close" in frame.columns
    assert frame.iloc[0]["pre_close"] == 1.0


def test_load_vipdoc_daily_missing_file_returns_none(tmp_path):
    assert vh.load_vipdoc_daily("600519", None, None, root=tmp_path) is None


def test_load_vipdoc_daily_rejects_path_traversal_code(tmp_path):
    assert vh.load_vipdoc_daily("../sh600519", None, None, root=tmp_path) is None
    assert vh.load_vipdoc_daily("600519.day", None, None, root=tmp_path) is None


# ── 3. manifest / 状态 / 目录派生 ──────────────────────────────────────────


def test_scan_lday_tree_counts_records_and_latest_dates(tmp_path):
    _write_day(tmp_path / "sh" / "lday" / "sh600519.day", _golden_bytes())
    _write_day(tmp_path / "sz" / "lday" / "sz000001.day", _golden_bytes())

    scan = vh.scan_lday_tree(tmp_path)

    assert scan["record_counts"] == {"sh": 2, "sz": 2, "bj": 0}
    assert scan["max_bar_date"]["600519"] == "2026-09-09"
    assert scan["max_bar_date"]["000001"] == "2026-09-09"


def test_write_and_read_manifest_roundtrip(tmp_path):
    manifest = {
        "schema_version": vh.MANIFEST_SCHEMA_VERSION,
        "source_url": vh.VIPDOC_SOURCE_URL,
        "source_last_modified": "2026-09-10T07:58:52Z",
        "downloaded_at": "2026-09-11T00:00:00Z",
        "record_counts": {"sh": 1, "sz": 0, "bj": 0},
        "max_bar_date": {"600519": "2026-09-09"},
        "zip_sha256": "0" * 64,
    }
    vh.write_manifest(tmp_path, manifest)

    assert vh._read_manifest(tmp_path / "manifest.json") == manifest


def test_vipdoc_history_status_manifest_freshness(tmp_path, monkeypatch):
    today = pd.Timestamp.now(tz="Asia/Shanghai").normalize()
    latest = (today - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    vh.write_manifest(
        tmp_path,
        {
            "schema_version": 1,
            "source_url": vh.VIPDOC_SOURCE_URL,
            "source_last_modified": "2026-09-10T07:58:52Z",
            "downloaded_at": "2026-09-11T00:00:00Z",
            "record_counts": {"sh": 3, "sz": 2, "bj": 1},
            "max_bar_date": {"600519": latest, "000001": latest},
            "zip_sha256": "0" * 64,
        },
    )

    status = vh.vipdoc_history_status(root=tmp_path)

    assert status["available"] is True
    assert status["latest_bar_date"] == latest
    assert status["age_days"] == 1
    assert status["stale"] is False
    assert status["record_counts"] == {"sh": 3, "sz": 2, "bj": 1}


def test_vipdoc_history_status_without_manifest_is_unavailable(tmp_path):
    status = vh.vipdoc_history_status(root=tmp_path)

    assert status["available"] is True
    assert status["manifest"] is None
    assert status["latest_bar_date"] is None
    assert status["stale"] is True


def test_vipdoc_history_dir_derives_from_data_cache_dir(monkeypatch, tmp_path):
    from chstockdata import config as dataflow_config

    cache_root = tmp_path / "cache-root"
    monkeypatch.setattr(
        dataflow_config,
        "get_config",
        lambda: {"data_cache_dir": str(cache_root), "vipdoc_history_dir": None},
    )
    assert vh.vipdoc_history_dir() == str(cache_root / "vipdoc")

    explicit = tmp_path / "explicit"
    monkeypatch.setattr(
        dataflow_config,
        "get_config",
        lambda: {"vipdoc_history_dir": str(explicit)},
    )
    assert vh.vipdoc_history_dir() == str(explicit)
