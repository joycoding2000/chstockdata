"""Shared pytest fixtures: keep the default suite hermetic and offline.

Carried over from TradingAgents-astock's tests/conftest.py (data-layer
fixtures only), retargeted at chstockdata module paths.
"""

import pytest


def pytest_configure(config):
    for marker in ("unit", "integration", "smoke", "network"):
        config.addinivalue_line("markers", f"{marker}: {marker}-level tests")
    config.addinivalue_line(
        "markers",
        "allow_name_map_warmup: opt-in for tests exercising the real warmup starter",
    )
    config.addinivalue_line(
        "markers",
        "allow_vipdoc_history: opt-in for tests exercising the real local vipdoc reader",
    )
    config.addinivalue_line(
        "markers",
        "allow_trading_calendar: opt-in for tests exercising the real trading calendar",
    )


@pytest.fixture(autouse=True)
def _no_background_name_map_warmup(request, monkeypatch):
    """Keep the UI name-map warmup daemon out of the test process.

    The warmup thread probes real TDX servers in the background (worst case
    ~70s) and writes a_stock's process-global negative-cache/client state
    while later tests run. Tests that exercise the warmup itself opt in via
    ``allow_name_map_warmup``.
    """
    if request.node.get_closest_marker("allow_name_map_warmup"):
        return
    try:
        from chstockdata import a_stock
    except Exception:  # pragma: no cover - heavy optional import unavailable
        return
    monkeypatch.setattr(a_stock, "ensure_name_code_map_warmup", lambda: None)


@pytest.fixture(autouse=True)
def _no_vipdoc_history(request, monkeypatch):
    """Keep the machine-local vipdoc layer out of the default test process.

    ``get_stock_data`` reads the official TDX daily package if the developer
    (or CI) has one under ``data_cache_dir``; without this guard, existing
    OHLCV tests would become environment-dependent. Tests that exercise the
    layer opt in via ``allow_vipdoc_history``.
    """
    if request.node.get_closest_marker("allow_vipdoc_history"):
        return
    try:
        from chstockdata import a_stock
    except Exception:  # pragma: no cover - heavy optional import unavailable
        return
    monkeypatch.setattr(a_stock, "_load_vipdoc_ohlcv_frame", lambda *args, **kwargs: None)


@pytest.fixture(autouse=True)
def _no_trading_calendar(request, monkeypatch):
    """Keep the machine-local trading calendar (and its online fallback) out.

    The calendar reads the local vipdoc index file and, when that is missing
    or stale, falls back to the online mootdx/Sina chain. Tests that exercise
    the calendar opt in via ``allow_trading_calendar``.
    """
    if request.node.get_closest_marker("allow_trading_calendar"):
        return
    try:
        from chstockdata import trading_calendar
    except Exception:  # pragma: no cover - heavy optional import unavailable
        return
    trading_calendar._clear_calendar_cache()
    monkeypatch.setattr(
        trading_calendar, "_read_local_index_days", lambda *args, **kwargs: None
    )
    monkeypatch.setattr(
        trading_calendar, "_read_online_index_days", lambda *args, **kwargs: None
    )
