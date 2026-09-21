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


def _business_frame(end_date, rows, *, reverse=False):
    days = pd.bdate_range(end=pd.Timestamp(end_date), periods=rows)
    frame = _frame(days.strftime("%Y-%m-%d"))
    if reverse:
        return frame.iloc[::-1].reset_index(drop=True)
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


def test_structured_refresh_preserves_legacy_800_row_depth_and_cache_size(
    tmp_path, monkeypatch
):
    _patch_config(monkeypatch, tmp_path)
    curr_date = "2026-09-21"
    source = _business_frame(curr_date, 1000, reverse=True)
    monkeypatch.setattr(
        daily_bars,
        "fetch_daily_bars",
        lambda *args, **kwargs: _result(source),
    )

    result = a_stock._load_ohlcv_astock(CODE, curr_date)
    expected = source.sort_values("Date", kind="mergesort").tail(800)
    cached = pd.read_csv(_cache_path(tmp_path), parse_dates=["Date"])

    assert len(result) == 800
    assert result["Date"].iloc[0] == expected["Date"].iloc[0]
    assert result["Date"].iloc[-1] == expected["Date"].iloc[-1]
    assert len(cached) == 800


def test_fresh_oversized_cache_is_normalized_to_recent_800_rows(
    tmp_path, monkeypatch
):
    _patch_config(monkeypatch, tmp_path)
    curr_date = "2026-09-21"
    source = _business_frame(curr_date, 1200, reverse=True)
    _fresh_cache(tmp_path, source)
    monkeypatch.setattr(
        a_stock,
        "_calendar_reference_last_bar",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        daily_bars,
        "fetch_daily_bars",
        lambda *args, **kwargs: pytest.fail(
            "oversized fresh cache must short-circuit fetch"
        ),
    )

    result = a_stock._load_ohlcv_astock(CODE, curr_date)
    cached = pd.read_csv(_cache_path(tmp_path), parse_dates=["Date"])
    expected = source.sort_values("Date", kind="mergesort").tail(800)

    assert len(result) == 800
    assert len(cached) == 800
    assert result["Date"].iloc[0] == expected["Date"].iloc[0]
    assert result["Date"].iloc[-1] == expected["Date"].iloc[-1]


def test_future_rows_are_removed_before_selecting_recent_800(
    tmp_path, monkeypatch
):
    _patch_config(monkeypatch, tmp_path)
    curr_date = "2026-09-20"
    history = _business_frame("2026-09-18", 1000, reverse=True)
    future = _frame(["2026-09-21", "2026-09-22"])
    _fresh_cache(tmp_path, pd.concat([history, future], ignore_index=True))
    monkeypatch.setattr(
        a_stock,
        "_calendar_reference_last_bar",
        lambda *_args, **_kwargs: "2026-09-18",
    )
    monkeypatch.setattr(
        daily_bars,
        "fetch_daily_bars",
        lambda *args, **kwargs: pytest.fail(
            "PIT-valid cache must short-circuit fetch"
        ),
    )

    result = a_stock._load_ohlcv_astock(CODE, curr_date)
    expected = history.sort_values("Date", kind="mergesort").tail(800)
    cached = pd.read_csv(_cache_path(tmp_path), parse_dates=["Date"])

    assert len(result) == 800
    assert result["Date"].iloc[0] == expected["Date"].iloc[0]
    assert result["Date"].iloc[-1] == pd.Timestamp("2026-09-18")
    assert (result["Date"] <= pd.Timestamp(curr_date)).all()
    assert (cached["Date"] <= pd.Timestamp(curr_date)).all()


@pytest.mark.parametrize(
    ("curr_date", "cached_last", "expected_last"),
    [
        ("2026-09-20", "2026-09-18", "2026-09-18"),
        ("2026-10-06", "2026-09-30", "2026-09-30"),
    ],
)
def test_fresh_cache_uses_expected_market_session_for_weekend_and_holiday(
    tmp_path, monkeypatch, curr_date, cached_last, expected_last
):
    _patch_config(monkeypatch, tmp_path)
    _fresh_cache(tmp_path, _frame(["2026-09-01", cached_last]))
    monkeypatch.setattr(
        a_stock,
        "_calendar_reference_last_bar",
        lambda *_args, **_kwargs: expected_last,
    )
    monkeypatch.setattr(
        daily_bars,
        "fetch_daily_bars",
        lambda *args, **kwargs: pytest.fail(
            "market-session-covered cache must be fresh"
        ),
    )

    result = a_stock._load_ohlcv_astock(CODE, curr_date)

    assert result["Date"].iloc[-1] == pd.Timestamp(cached_last)


def test_calendar_session_reference_does_not_mask_a_lagging_cache(
    tmp_path, monkeypatch
):
    _patch_config(monkeypatch, tmp_path)
    _fresh_cache(tmp_path, _frame(["2026-09-01", "2026-09-16"]))
    monkeypatch.setattr(
        a_stock,
        "_calendar_reference_last_bar",
        lambda *_args, **_kwargs: "2026-09-18",
    )
    calls = []

    def _fetch(code, start_date, end_date):
        calls.append((code, start_date, end_date))
        return _result(_frame(["2026-09-18", "2026-09-20"]))

    monkeypatch.setattr(daily_bars, "fetch_daily_bars", _fetch)
    result = a_stock._load_ohlcv_astock(CODE, "2026-09-20")

    assert calls == [(CODE, "2022-09-20", "2026-09-20")]
    assert result["Date"].iloc[-1] == pd.Timestamp("2026-09-20")


def test_calendar_unavailable_keeps_legacy_tolerance_for_recent_cache(
    tmp_path, monkeypatch
):
    _patch_config(monkeypatch, tmp_path)
    _fresh_cache(tmp_path, _frame(["2026-09-01", "2026-09-18"]))
    monkeypatch.setattr(
        a_stock,
        "_calendar_reference_last_bar",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        daily_bars,
        "fetch_daily_bars",
        lambda *args, **kwargs: pytest.fail(
            "recent cache is valid under fallback tolerance"
        ),
    )

    result = a_stock._load_ohlcv_astock(CODE, "2026-09-20")

    assert result["Date"].iloc[-1] == pd.Timestamp("2026-09-18")


def test_calendar_unavailable_refreshes_cache_beyond_legacy_tolerance(
    tmp_path, monkeypatch
):
    _patch_config(monkeypatch, tmp_path)
    _fresh_cache(tmp_path, _frame(["2026-09-01", "2026-09-01"]))
    monkeypatch.setattr(
        a_stock,
        "_calendar_reference_last_bar",
        lambda *_args, **_kwargs: None,
    )
    calls = []

    def _fetch(code, start_date, end_date):
        calls.append((code, start_date, end_date))
        return _result(_frame(["2026-09-19", "2026-09-20"]))

    monkeypatch.setattr(daily_bars, "fetch_daily_bars", _fetch)
    result = a_stock._load_ohlcv_astock(CODE, "2026-09-20")

    assert calls == [(CODE, "2022-09-20", "2026-09-20")]
    assert result["Date"].iloc[-1] == pd.Timestamp("2026-09-20")


def test_stale_structured_refresh_is_not_written_as_fresh_cache(tmp_path, monkeypatch):
    _patch_config(monkeypatch, tmp_path)
    monkeypatch.setattr(
        daily_bars,
        "fetch_daily_bars",
        lambda *args, **kwargs: _result(_frame(["2026-08-01"])),
    )

    with pytest.raises(ValueError, match="historical_ohlcv_stale"):
        a_stock._load_ohlcv_astock(CODE, "2026-09-21")

    assert not _cache_path(tmp_path).exists()


def test_indicator_path_receives_at_most_800_cached_rows(tmp_path, monkeypatch):
    _patch_config(monkeypatch, tmp_path)
    curr_date = "2026-09-21"
    source = _business_frame(curr_date, 1000)
    monkeypatch.setattr(
        daily_bars,
        "fetch_daily_bars",
        lambda *args, **kwargs: _result(source),
    )
    observed = {}

    def _adjusted(*args, **kwargs):
        observed["rows"] = len(kwargs["daily_bars"])
        return SimpleNamespace(
            frame=kwargs["daily_bars"],
            factor_source=None,
            anchor_date=None,
            limitations=[],
        )

    monkeypatch.setattr("chstockdata.adjusted_bars.get_adjusted_bars", _adjusted)

    rendered = a_stock._compute_and_format_indicators(CODE, curr_date, [])

    assert observed["rows"] == 800
    assert "## Technical Indicators" in rendered
