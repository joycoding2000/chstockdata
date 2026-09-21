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
def _reset_mootdx_readiness_globals(monkeypatch):
    """Isolate the v0.4.0 Phase 1.1 transport-readiness globals per test.

    ``_mootdx_transport_ok`` / ``_mootdx_transport_candidates`` are process
    globals written by full-table scans; without a per-test reset a canary
    verdict from one file would leak into another file's selection paths.
    monkeypatch restores the prior value automatically.
    """
    try:
        from chstockdata import a_stock
    except Exception:  # pragma: no cover - heavy optional import unavailable
        return
    monkeypatch.setattr(a_stock, "_mootdx_transport_ok", True)
    monkeypatch.setattr(a_stock, "_mootdx_transport_candidates", ())


@pytest.fixture(autouse=True)
def _no_vipdoc_history(request, monkeypatch):
    """Keep the machine-local vipdoc layer out of the default test process.

    ``get_stock_data`` reads the official TDX daily package if the developer
    (or CI) has one under ``data_cache_dir``; without this guard, existing
    OHLCV tests would become environment-dependent. Tests that exercise the
    layer opt in via ``allow_vipdoc_history``.

    v0.4.0 Phase 2: the daily-bars structured engine owns the vipdoc adapter
    (``daily_bars.ADAPTERS``), so BOTH the legacy helper and the engine
    adapter are stubbed here (not-configured = absent local layer).
    """
    if request.node.get_closest_marker("allow_vipdoc_history"):
        return

    def _vipdoc_unavailable(*args, **kwargs):
        from chstockdata.vendor_errors import VendorNotConfiguredError

        raise VendorNotConfiguredError(
            "vipdoc history disabled for this test"
        )

    try:
        from chstockdata import a_stock
    except Exception:  # pragma: no cover - heavy optional import unavailable
        a_stock = None
    else:
        monkeypatch.setattr(a_stock, "_load_vipdoc_ohlcv_frame", lambda *args, **kwargs: None)
    try:
        from chstockdata import daily_bars
    except Exception:  # pragma: no cover - heavy optional import unavailable
        return
    monkeypatch.setitem(daily_bars.ADAPTERS, "tdx_vipdoc", _vipdoc_unavailable)


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
    # The structured calendar route has truthful provider adapters and no
    # longer consults the legacy fail-soft readers.  Keep the default suite
    # hermetic by making the legacy compatibility seam unavailable unless a
    # test opts into the real calendar or supplies its own route adapters.
    monkeypatch.setattr(
        trading_calendar, "load_trading_calendar", lambda *args, **kwargs: None
    )
