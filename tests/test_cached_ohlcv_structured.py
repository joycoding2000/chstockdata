"""Regression tests for the cached legacy OHLCV consumer.

The CSV cache remains a storage/PIT compatibility layer.  Provider routing is
owned by ``daily_bars.fetch_daily_bars`` and must not be reimplemented here.
"""

import os
from datetime import datetime
from types import SimpleNamespace

import pandas as pd
import pytest

from chstockdata import a_stock, daily_bars
from chstockdata.capabilities import (
    capability_health_snapshot,
    reset_capability_health,
)

CODE = "600519"
REQUIRED_COLUMNS = ["Date", "Open", "High", "Low", "Close", "Volume"]


@pytest.fixture(autouse=True)
def _fresh_capability_health():
    reset_capability_health()
    yield
    reset_capability_health()


def _frame(days, *, extra_columns=False):
    frame = pd.DataFrame(
        {
            "Date": pd.to_datetime(list(days)),
            "Open": [10.0 + i for i, _ in enumerate(days)],
            "High": [11.0 + i for i, _ in enumerate(days)],
            "Low": [9.0 + i for i, _ in enumerate(days)],
            "Close": [10.5 + i for i, _ in enumerate(days)],
            "Volume": [1000 + i for i, _ in enumerate(days)],
        }
    )
    if extra_columns:
        frame["pre_close"] = [10.0 + i for i, _ in enumerate(days)]
        frame["Amount"] = [100000.0 + i for i, _ in enumerate(days)]
    return frame


def _result(frame, *, normal_empty=False):
    return SimpleNamespace(
        data=frame,
        is_normal_empty=normal_empty,
        metadata=SimpleNamespace(stale=False),
    )


def _cache_path(tmp_path):
    return tmp_path / f"{CODE}-astock-daily.csv"


def _fresh_cache(tmp_path, frame):
    path = _cache_path(tmp_path)
    frame.to_csv(path, index=False, encoding="utf-8")
    now = datetime.now().timestamp()
    os.utime(path, (now, now))
    return path


def _patch_config(monkeypatch, tmp_path):
    from chstockdata import config as dataflow_config

    monkeypatch.setattr(
        dataflow_config,
        "get_config",
        lambda: {"data_cache_dir": str(tmp_path)},
    )


def test_fresh_valid_cache_short_circuits_structured_fetch(tmp_path, monkeypatch):
    _patch_config(monkeypatch, tmp_path)
    _fresh_cache(tmp_path, _frame(["2026-09-01", "2026-09-02"]))

    monkeypatch.setattr(
        daily_bars,
        "fetch_daily_bars",
        lambda *args, **kwargs: pytest.fail("fresh cache must short-circuit fetch"),
    )

    result = a_stock._load_ohlcv_astock(CODE, "2026-09-02")

    assert list(result.columns) == REQUIRED_COLUMNS
    assert result["Date"].dt.strftime("%Y-%m-%d").tolist() == [
        "2026-09-01",
        "2026-09-02",
    ]
    assert "cache:daily_bars" not in capability_health_snapshot()


def test_pit_filter_excludes_future_rows_from_fresh_cache(tmp_path, monkeypatch):
    _patch_config(monkeypatch, tmp_path)
    _fresh_cache(
        tmp_path,
        _frame(["2026-09-01", "2026-09-02", "2026-09-10"]),
    )
    monkeypatch.setattr(
        daily_bars,
        "fetch_daily_bars",
        lambda *args, **kwargs: pytest.fail("future cache rows must not trigger fetch"),
    )

    result = a_stock._load_ohlcv_astock(CODE, "2026-09-02")

    assert result["Date"].dt.strftime("%Y-%m-%d").tolist() == [
        "2026-09-01",
        "2026-09-02",
    ]
    assert (result["Date"] <= pd.Timestamp("2026-09-02")).all()


def test_malformed_fresh_cache_is_bypassed_and_rewritten(tmp_path, monkeypatch):
    _patch_config(monkeypatch, tmp_path)
    path = _cache_path(tmp_path)
    pd.DataFrame(
        {
            "Date": ["not-a-date"],
            "Open": [10.0],
            "High": [11.0],
            "Low": [9.0],
            "Volume": [1000],
        }
    ).to_csv(path, index=False, encoding="utf-8")
    now = datetime.now().timestamp()
    os.utime(path, (now, now))
    calls = []

    def _fetch(code, start_date, end_date):
        calls.append((code, start_date, end_date))
        return _result(_frame(["2026-09-01", "2026-09-02"], extra_columns=True))

    monkeypatch.setattr(daily_bars, "fetch_daily_bars", _fetch)
    monkeypatch.setattr(
        a_stock,
        "_fetch_mootdx_bars",
        lambda *args, **kwargs: pytest.fail("cache corruption must not call mootdx"),
    )
    monkeypatch.setattr(
        a_stock,
        "_sina_kline_fallback",
        lambda *args, **kwargs: pytest.fail("cache corruption must not call Sina directly"),
    )

    result = a_stock._load_ohlcv_astock(CODE, "2026-09-02")
    rewritten = pd.read_csv(path)

    assert calls == [(CODE, "2022-09-02", "2026-09-02")]
    assert list(result.columns) == REQUIRED_COLUMNS
    assert list(rewritten.columns) == REQUIRED_COLUMNS
    assert "pre_close" not in rewritten.columns
    assert "Amount" not in rewritten.columns
    assert "cache:daily_bars" not in capability_health_snapshot()


def test_valid_but_lagging_cache_refreshes_through_structured_engine(
    tmp_path, monkeypatch
):
    _patch_config(monkeypatch, tmp_path)
    _fresh_cache(tmp_path, _frame(["2026-08-01"]))
    calls = []

    def _fetch(code, start_date, end_date):
        calls.append((code, start_date, end_date))
        return _result(_frame(["2026-09-20", "2026-09-21"]))

    monkeypatch.setattr(daily_bars, "fetch_daily_bars", _fetch)
    monkeypatch.setattr(
        a_stock,
        "_fetch_mootdx_bars",
        lambda *args, **kwargs: pytest.fail("refresh must use structured engine"),
    )
    monkeypatch.setattr(
        a_stock,
        "_sina_kline_fallback",
        lambda *args, **kwargs: pytest.fail("refresh must use structured engine"),
    )
    monkeypatch.setattr(
        a_stock,
        "_supplement_stale_ohlcv_with_sina",
        lambda *args, **kwargs: pytest.fail("refresh must use structured engine"),
    )

    result = a_stock._load_ohlcv_astock(CODE, "2026-09-21")

    assert calls == [(CODE, "2022-09-21", "2026-09-21")]
    assert result["Date"].dt.strftime("%Y-%m-%d").tolist() == [
        "2026-09-20",
        "2026-09-21",
    ]


def test_structured_routing_failure_maps_to_legacy_value_error(tmp_path, monkeypatch):
    _patch_config(monkeypatch, tmp_path)
    from chstockdata.daily_bars import DailyBarsRoutingError

    monkeypatch.setattr(
        daily_bars,
        "fetch_daily_bars",
        lambda *args, **kwargs: (_ for _ in ()).throw(DailyBarsRoutingError([])),
    )

    with pytest.raises(ValueError, match=r"^No OHLCV data from mootdx/sina for 600519$"):
        a_stock._load_ohlcv_astock(CODE, "2026-09-21")


def test_structured_normal_empty_keeps_legacy_no_data_contract(tmp_path, monkeypatch):
    _patch_config(monkeypatch, tmp_path)
    empty = pd.DataFrame(columns=REQUIRED_COLUMNS)
    monkeypatch.setattr(
        daily_bars,
        "fetch_daily_bars",
        lambda *args, **kwargs: _result(empty, normal_empty=True),
    )

    with pytest.raises(ValueError, match=r"^No OHLCV data from mootdx/sina for 600519$"):
        a_stock._load_ohlcv_astock(CODE, "2026-09-21")


def test_vipdoc_backed_structured_frame_returns_legacy_six_columns(
    tmp_path, monkeypatch
):
    _patch_config(monkeypatch, tmp_path)
    calls = []

    def _vipdoc(code, start_date, end_date):
        calls.append((code, start_date, end_date))
        return _frame(["2026-09-20", "2026-09-21"], extra_columns=True)

    monkeypatch.setitem(daily_bars.ADAPTERS, "tdx_vipdoc", _vipdoc)
    monkeypatch.setitem(
        daily_bars.ADAPTERS,
        "mootdx",
        lambda *args, **kwargs: pytest.fail("vipdoc base should stop the route"),
    )

    result = a_stock._load_ohlcv_astock(CODE, "2026-09-21")
    cached = pd.read_csv(_cache_path(tmp_path))

    assert calls == [(CODE, "2022-09-21", "2026-09-21")]
    assert list(result.columns) == REQUIRED_COLUMNS
    assert list(cached.columns) == REQUIRED_COLUMNS
    assert "pre_close" not in result.columns
    assert "Amount" not in result.columns
    assert result.attrs == {}


def test_indicator_fallback_uses_structured_cached_history(tmp_path, monkeypatch):
    _patch_config(monkeypatch, tmp_path)
    calls = []
    history = _frame(
        pd.date_range("2026-07-04", "2026-09-21", freq="D").strftime("%Y-%m-%d")
    )

    def _fetch(code, start_date, end_date):
        calls.append((code, start_date, end_date))
        return _result(history)

    monkeypatch.setattr(daily_bars, "fetch_daily_bars", _fetch)
    monkeypatch.setattr(
        "chstockdata.adjusted_bars.get_adjusted_bars",
        lambda *args, **kwargs: SimpleNamespace(
            frame=history,
            factor_source=None,
            anchor_date=None,
            limitations=[],
        ),
    )

    rendered = a_stock._compute_and_format_indicators(
        CODE,
        "2026-09-21",
        [],
    )

    assert calls == [(CODE, "2022-09-21", "2026-09-21")]
    assert "## Technical Indicators" in rendered
