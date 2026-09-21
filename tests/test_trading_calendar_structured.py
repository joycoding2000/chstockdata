"""Structured trading-calendar vertical slice contracts."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from chstockdata import (
    TRADING_CALENDAR_PROVIDERS,
    fetch_trading_calendar,
    load_trading_calendar,
    probe_trading_calendar_provider,
)
from chstockdata import trading_calendar as tc
from chstockdata.capabilities import (
    ProviderCapability,
    capability_health_snapshot,
    record_capability_health,
    reset_capability_health,
)
from chstockdata.fetch_result import (
    FETCH_FAILED_NETWORK,
    FETCH_FAILED_STRUCTURE,
    FETCH_NORMAL_EMPTY,
    FETCH_NOT_CONFIGURED,
    FETCH_SUCCESS,
    FetchMetadata,
    FetchResult,
)
from chstockdata.vendor_errors import (
    VendorNetworkError,
    VendorNotConfiguredError,
    VendorNoDataError,
)

pytestmark = pytest.mark.allow_trading_calendar


@pytest.fixture(autouse=True)
def _reset_calendar_state():
    tc._clear_calendar_cache()
    reset_capability_health()
    yield
    tc._clear_calendar_cache()
    reset_capability_health()


def _adapter(value):
    def _run(*, root=None):
        if isinstance(value, BaseException):
            raise value
        return value

    return _run


def _calendar_adapters(local, mootdx, sina):
    return {
        "tdx_vipdoc": _adapter(local),
        "mootdx": _adapter(mootdx),
        "sina": _adapter(sina),
    }


def _days(*values: str) -> tuple[str, ...]:
    return tuple(values)


def test_provider_identities_are_operation_level():
    assert TRADING_CALENDAR_PROVIDERS == (
        ("tdx_vipdoc", "tdx_vipdoc:index_bars"),
        ("mootdx", "mootdx:index"),
        ("sina", "sina:index_bars"),
    )


def test_canonicalize_trading_days_is_sorted_unique_iso():
    assert tc.canonicalize_trading_days(
        ["2026/09/21", "2026-09-19", "2026-09-21", "2026-09-20"],
        provider="mootdx",
    ) == ("2026-09-19", "2026-09-20", "2026-09-21")


def test_canonicalize_trading_days_keeps_valid_rows_when_some_dates_are_bad():
    assert tc.canonicalize_trading_days(
        ["2026-09-21", "not-a-date", "2026-09-20"],
        provider="sina",
    ) == ("2026-09-20", "2026-09-21")


@pytest.mark.parametrize(
    "payload",
    [[], ["not-a-date"], {"Date": ["2026-09-21"]}],
)
def test_canonicalize_trading_days_rejects_empty_invalid_or_wrong_shape(payload):
    with pytest.raises(ValueError):
        tc.canonicalize_trading_days(payload, provider="sina")


def test_local_adapter_uses_explicit_shanghai_market(monkeypatch, tmp_path):
    calls = {}

    def _load(code, *, market=None, root=None):
        calls.update(code=code, market=market, root=root)
        return pd.DataFrame({"Date": ["2026-09-21"]})

    monkeypatch.setattr(tc, "load_vipdoc_daily", _load)

    assert tc._fetch_local_index_days(root=tmp_path) == ["2026-09-21"]
    assert calls == {"code": "000001", "market": "sh", "root": tmp_path}


def test_mootdx_adapter_preserves_index_request_shape(monkeypatch):
    from chstockdata import a_stock

    calls = {}

    def _mootdx(method, **kwargs):
        calls.update(method=method, kwargs=kwargs)
        return pd.DataFrame(
            {
                "open": [1, 1],
                "high": [1, 1],
                "low": [1, 1],
                "close": [1, 1],
                "vol": [1, 1],
            },
            index=pd.to_datetime(["2026-09-20", "2026-09-21"]),
        )

    monkeypatch.setattr(a_stock, "_mootdx_call", _mootdx)
    assert tc.canonicalize_trading_days(
        tc._fetch_mootdx_index_days(), provider="mootdx"
    ) == ("2026-09-20", "2026-09-21")
    assert calls == {
        "method": "index",
        "kwargs": {
            "symbol": "000001",
            "frequency": 9,
            "offset": 2000,
            "_observe_capability_health": True,
        },
    }


def test_structured_mootdx_calendar_adapter_suppresses_primitive_health(monkeypatch):
    from chstockdata import a_stock

    calls = {}

    def _mootdx(method, **kwargs):
        calls.update(method=method, kwargs=kwargs)
        return pd.DataFrame(
            {
                "open": [1],
                "high": [1],
                "low": [1],
                "close": [1],
                "vol": [1],
            },
            index=pd.to_datetime(["2026-09-21"]),
        )

    monkeypatch.setattr(a_stock, "_mootdx_call", _mootdx)
    assert tc.canonicalize_trading_days(
        tc.CALENDAR_ADAPTERS["mootdx"](),
        provider="mootdx",
    ) == ("2026-09-21",)
    assert calls["kwargs"]["_observe_capability_health"] is False


def test_sina_adapter_preserves_endpoint_and_parameters(monkeypatch):
    from chstockdata import a_stock

    calls = {}

    class _Response:
        text = '[{"day": "2026-09-21"}]'

        def raise_for_status(self):
            calls["raise_for_status"] = True

    def _http(source, url, **kwargs):
        calls.update(source=source, url=url, kwargs=kwargs)
        return _Response()

    monkeypatch.setattr(a_stock, "_source_http_get", _http)

    assert tc.canonicalize_trading_days(
        tc._fetch_sina_index_days(), provider="sina"
    ) == ("2026-09-21",)
    assert calls["source"] == "sina"
    assert calls["kwargs"]["params"] == {
        "symbol": "sh000001",
        "scale": "240",
        "ma": "no",
        "datalen": 2000,
    }
    assert calls["kwargs"]["timeout"] == 15
    assert calls["kwargs"]["fallback_from"] == "trading_calendar"
    assert calls["raise_for_status"] is True


def test_fresh_local_success_stops_before_online(monkeypatch):
    calls = []

    def _local(*, root=None):
        calls.append("local")
        return _days("2026-09-19", "2026-09-21")

    def _must_not_run(*, root=None):
        calls.append("online")
        raise AssertionError("fresh local must stop the route")

    result = fetch_trading_calendar(
        today="2026-09-21",
        adapters={
            "tdx_vipdoc": _local,
            "mootdx": _must_not_run,
            "sina": _must_not_run,
        },
    )

    assert calls == ["local"]
    assert result.data is not None
    assert result.data.source == "vipdoc_sh000001"
    assert result.data.stale is False
    assert result.metadata.providers_used == ["tdx_vipdoc"]
    assert result.metadata.final_provider == "tdx_vipdoc"
    assert result.metadata.data_as_of == "2026-09-21"
    assert result.metadata.observed_at is None
    assert [(a.capability, a.status) for a in result.metadata.attempts] == [
        ("tdx_vipdoc:index_bars", FETCH_SUCCESS),
    ]
    assert set(capability_health_snapshot()) == {"tdx_vipdoc:index_bars"}


def test_mixed_invalid_dates_keep_data_and_expose_partial_metadata():
    result = fetch_trading_calendar(
        today="2026-09-21",
        adapters=_calendar_adapters(
            ["2026-09-20", "bad-date", "2026-09-21"],
            AssertionError("fresh local must stop the route"),
            AssertionError("fresh local must stop the route"),
        ),
    )

    assert result.data is not None
    assert result.data.trading_days == ("2026-09-20", "2026-09-21")
    assert result.metadata.partial is True
    assert "invalid_calendar_dates_dropped" in result.metadata.limitations


def test_partial_stale_local_does_not_pollute_clean_newer_online_payload():
    result = fetch_trading_calendar(
        today="2026-09-21",
        adapters=_calendar_adapters(
            ["2026-09-09", "bad-date", "2026-09-10"],
            _days("2026-09-20"),
            AssertionError("Sina must not run after mootdx success"),
        ),
    )

    assert result.data is not None
    assert result.data.source == "mootdx_sh000001"
    assert result.metadata.providers_used == ["mootdx"]
    assert result.metadata.final_provider == "mootdx"
    assert result.metadata.partial is False
    assert "invalid_calendar_dates_dropped" not in result.metadata.limitations
    assert result.metadata.attempts[0].status == FETCH_SUCCESS


def test_partial_older_online_does_not_pollute_retained_clean_local_payload():
    result = fetch_trading_calendar(
        today="2026-09-21",
        adapters=_calendar_adapters(
            _days("2026-09-10"),
            ["2026-09-08", "bad-date", "2026-09-09"],
            AssertionError("Sina is not reached after a usable mootdx response"),
        ),
    )

    assert result.data is not None
    assert result.data.source == "vipdoc_sh000001"
    assert result.metadata.providers_used == ["tdx_vipdoc"]
    assert result.metadata.partial is False
    assert "invalid_calendar_dates_dropped" not in result.metadata.limitations
    assert "在线回落返回的日线不新于本地包，保留本地（陈旧）日历" in result.data.limitations


def test_partial_newer_online_owns_final_payload_quality():
    result = fetch_trading_calendar(
        today="2026-09-21",
        adapters=_calendar_adapters(
            _days("2026-09-10"),
            ["2026-09-20", "bad-date", "2026-09-21"],
            AssertionError("Sina must not run after mootdx success"),
        ),
    )

    assert result.data is not None
    assert result.data.source == "mootdx_sh000001"
    assert result.metadata.providers_used == ["mootdx"]
    assert result.metadata.partial is True
    assert "invalid_calendar_dates_dropped" in result.metadata.limitations


def test_partial_stale_local_remains_partial_when_online_fails():
    result = fetch_trading_calendar(
        today="2026-09-21",
        adapters=_calendar_adapters(
            ["2026-09-09", "bad-date", "2026-09-10"],
            VendorNetworkError("mootdx down"),
            VendorNetworkError("sina down"),
        ),
    )

    assert result.data is not None
    assert result.data.source == "vipdoc_sh000001"
    assert result.metadata.providers_used == ["tdx_vipdoc"]
    assert result.metadata.partial is True
    assert result.metadata.degraded is True
    assert "invalid_calendar_dates_dropped" in result.metadata.limitations


def test_stale_local_and_newer_mootdx_uses_online_payload():
    result = fetch_trading_calendar(
        today="2026-09-21",
        adapters=_calendar_adapters(
            _days("2026-09-10"),
            _days("2026-09-20"),
            AssertionError("Sina must not run after mootdx success"),
        ),
    )

    assert result.data is not None
    assert result.data.source == "mootdx_sh000001"
    assert result.data.last_bar_date == "2026-09-20"
    assert result.data.stale is False
    assert result.metadata.providers_used == ["mootdx"]
    assert result.metadata.final_provider == "mootdx"
    assert result.metadata.data_as_of == "2026-09-20"
    assert [a.provider for a in result.metadata.attempts] == [
        "tdx_vipdoc",
        "mootdx",
    ]
    assert result.metadata.attempts[0].status == FETCH_SUCCESS
    assert capability_health_snapshot()["tdx_vipdoc:index_bars"].status == FETCH_SUCCESS
    assert capability_health_snapshot()["mootdx:index"].status == FETCH_SUCCESS


def test_stale_local_and_older_online_preserves_local_stale_payload():
    result = fetch_trading_calendar(
        today="2026-09-21",
        adapters=_calendar_adapters(
            _days("2026-09-10"),
            _days("2026-09-09"),
            AssertionError("Sina is not reached after a usable mootdx response"),
        ),
    )

    assert result.data is not None
    assert result.data.source == "vipdoc_sh000001"
    assert result.data.last_bar_date == "2026-09-10"
    assert result.data.stale is True
    assert result.metadata.providers_used == ["tdx_vipdoc"]
    assert result.metadata.final_provider == "tdx_vipdoc"
    assert "在线回落返回的日线不新于本地包，保留本地（陈旧）日历" in result.data.limitations
    assert result.metadata.degraded is False


def test_stale_local_mootdx_failure_sina_newer_wins_and_is_degraded():
    result = fetch_trading_calendar(
        today="2026-09-21",
        adapters=_calendar_adapters(
            _days("2026-09-10"),
            VendorNetworkError("mootdx down"),
            _days("2026-09-20"),
        ),
    )

    assert result.data is not None
    assert result.data.source == "sina_sh000001"
    assert result.data.stale is False
    assert result.metadata.providers_used == ["sina"]
    assert result.metadata.final_provider == "sina"
    assert result.metadata.degraded is True
    assert [
        (a.capability, a.status)
        for a in result.metadata.attempts
    ] == [
        ("tdx_vipdoc:index_bars", FETCH_SUCCESS),
        ("mootdx:index", FETCH_FAILED_NETWORK),
        ("sina:index_bars", FETCH_SUCCESS),
    ]


def test_stale_local_and_all_online_fail_returns_stale_local_degraded():
    result = fetch_trading_calendar(
        today="2026-09-21",
        adapters=_calendar_adapters(
            _days("2026-09-10"),
            VendorNetworkError("mootdx down"),
            VendorNetworkError("sina down"),
        ),
    )

    assert result.data is not None
    assert result.data.source == "vipdoc_sh000001"
    assert result.data.stale is True
    assert result.metadata.providers_used == ["tdx_vipdoc"]
    assert result.metadata.final_provider == "tdx_vipdoc"
    assert result.metadata.degraded is True
    assert "本地包超过陈旧度阈值，且在线回落失败；覆盖区间外日期不能判定" in result.data.limitations
    assert [a.status for a in result.metadata.attempts] == [
        FETCH_SUCCESS,
        FETCH_FAILED_NETWORK,
        FETCH_FAILED_NETWORK,
    ]


def test_unavailable_local_and_mootdx_success_does_not_degrade():
    result = fetch_trading_calendar(
        today="2026-09-21",
        adapters=_calendar_adapters(
            VendorNotConfiguredError("missing vipdoc"),
            _days("2026-09-20"),
            AssertionError("Sina must not run after mootdx success"),
        ),
    )

    assert result.data is not None
    assert result.data.source == "mootdx_sh000001"
    assert result.metadata.providers_used == ["mootdx"]
    assert result.metadata.final_provider == "mootdx"
    assert result.metadata.degraded is False
    assert [a.status for a in result.metadata.attempts] == [
        FETCH_NOT_CONFIGURED,
        FETCH_SUCCESS,
    ]


def test_unavailable_local_mootdx_failure_sina_success_is_degraded():
    result = fetch_trading_calendar(
        today="2026-09-21",
        adapters=_calendar_adapters(
            VendorNotConfiguredError("missing vipdoc"),
            VendorNetworkError("mootdx down"),
            _days("2026-09-20"),
        ),
    )

    assert result.data is not None
    assert result.data.source == "sina_sh000001"
    assert result.metadata.providers_used == ["sina"]
    assert result.metadata.final_provider == "sina"
    assert result.metadata.degraded is True


def test_all_providers_unusable_returns_none_and_legacy_none():
    adapters = _calendar_adapters(
        VendorNotConfiguredError("missing vipdoc"),
        VendorNetworkError("mootdx down"),
        VendorNetworkError("sina down"),
    )
    result = fetch_trading_calendar(today="2026-09-21", adapters=adapters)

    assert result.data is None
    assert result.metadata.providers_used == []
    assert result.metadata.final_provider is None
    assert result.metadata.succeeded is False
    assert [a.status for a in result.metadata.attempts] == [
        FETCH_NOT_CONFIGURED,
        FETCH_FAILED_NETWORK,
        FETCH_FAILED_NETWORK,
    ]

    monkeypatch = pytest.MonkeyPatch()
    try:
        monkeypatch.setattr(tc, "fetch_trading_calendar", lambda **kwargs: result)
        assert load_trading_calendar(today="2026-09-21", use_cache=False) is None
    finally:
        monkeypatch.undo()


def test_all_normal_empty_returns_structured_normal_empty():
    result = fetch_trading_calendar(
        today="2026-09-21",
        adapters=_calendar_adapters(
            VendorNoDataError("local empty"),
            VendorNoDataError("mootdx empty"),
            VendorNoDataError("sina empty"),
        ),
    )

    assert result.data is None
    assert result.metadata.final_status == FETCH_NORMAL_EMPTY
    assert result.metadata.succeeded is True
    assert result.metadata.degraded is False


def test_invalid_provider_payload_is_failed_structure_not_empty():
    result = fetch_trading_calendar(
        today="2026-09-21",
        adapters=_calendar_adapters(
            {"wrong_field": ["2026-09-21"]},
            {"wrong_field": ["2026-09-21"]},
            {"wrong_field": ["2026-09-21"]},
        ),
    )

    assert result.data is None
    assert result.metadata.final_status == FETCH_FAILED_STRUCTURE
    assert [a.status for a in result.metadata.attempts] == [
        FETCH_FAILED_STRUCTURE,
        FETCH_FAILED_STRUCTURE,
        FETCH_FAILED_STRUCTURE,
    ]


def test_empty_frame_without_date_field_is_failed_structure():
    malformed_empty = pd.DataFrame({"wrong_field": pd.Series(dtype=str)})
    result = fetch_trading_calendar(
        today="2026-09-21",
        adapters=_calendar_adapters(
            malformed_empty,
            malformed_empty,
            malformed_empty,
        ),
    )

    assert result.data is None
    assert result.metadata.final_status == FETCH_FAILED_STRUCTURE
    assert [a.status for a in result.metadata.attempts] == [
        FETCH_FAILED_STRUCTURE,
        FETCH_FAILED_STRUCTURE,
        FETCH_FAILED_STRUCTURE,
    ]


def test_today_only_controls_staleness_not_coverage():
    result = fetch_trading_calendar(
        today="2026-09-21",
        adapters=_calendar_adapters(
            _days("2026-09-10"),
            VendorNetworkError("mootdx down"),
            VendorNetworkError("sina down"),
        ),
    )

    assert result.data is not None
    assert result.data.covered_range == ("2026-09-10", "2026-09-10")
    assert result.data.trading_days == ("2026-09-10",)
    assert result.data.as_of == "2026-09-21"


def test_load_cache_remains_legacy_payload_memo_and_structured_fetch_is_fresh(
    monkeypatch,
):
    calls = []

    calendar = tc.TradingCalendar(
        trading_days=("2026-09-21",),
        source="vipdoc_sh000001",
        covered_range=("2026-09-21", "2026-09-21"),
        last_bar_date="2026-09-21",
        stale=False,
        as_of="2026-09-21",
    )
    metadata = FetchMetadata(
        capability="trading_calendar",
        final_provider="tdx_vipdoc",
        retrieved_at="2026-09-21T00:00:00+00:00",
        providers_used=["tdx_vipdoc"],
        data_as_of="2026-09-21",
    )
    result = FetchResult(data=calendar, metadata=metadata)

    def _fetch(**kwargs):
        calls.append(kwargs)
        return result

    monkeypatch.setattr(tc, "fetch_trading_calendar", _fetch)

    first = load_trading_calendar(today="2026-09-21", use_cache=True)
    second = load_trading_calendar(today="2026-09-21", use_cache=True)
    uncached = load_trading_calendar(today="2026-09-21", use_cache=False)

    assert first is calendar
    assert second is calendar
    assert uncached is calendar
    assert len(calls) == 2
    assert calls[0] == {"root": None, "today": date(2026, 9, 21)}


def test_local_helpers_do_not_touch_online_sources(monkeypatch):
    monkeypatch.setattr(
        tc,
        "_read_local_index_days",
        lambda root=None: ("2026-09-20", "2026-09-21"),
    )
    monkeypatch.setattr(
        tc,
        "_mootdx_call",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("local helper touched mootdx")
        ),
        raising=False,
    )
    monkeypatch.setattr(
        tc,
        "_source_http_get",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("local helper touched Sina")
        ),
        raising=False,
    )

    assert tc.local_is_trading_day("2026-09-20") is True
    assert tc.local_latest_index_bar() == "2026-09-21"


def test_probe_runs_one_provider_and_only_records_its_capability():
    result = probe_trading_calendar_provider(
        "mootdx",
        today="2026-09-21",
        adapter=_adapter(_days("2026-09-20", "2026-09-21")),
    )

    assert result.data is not None
    assert result.data.source == "mootdx_sh000001"
    assert [(a.provider, a.capability, a.status) for a in result.metadata.attempts] == [
        ("mootdx", "mootdx:index", FETCH_SUCCESS),
    ]
    assert set(capability_health_snapshot()) == {"mootdx:index"}
    assert capability_health_snapshot()["mootdx:index"].status == "success"


def test_local_probe_applies_stale_policy_while_remaining_successful(monkeypatch):
    monkeypatch.setattr(tc, "_max_staleness_days", lambda: 5.0)

    result = probe_trading_calendar_provider(
        "tdx_vipdoc",
        today="2026-09-21",
        adapter=_adapter(_days("2026-09-10")),
    )

    assert result.data is not None
    assert result.data.source == "vipdoc_sh000001"
    assert result.data.stale is True
    assert result.metadata.stale is True
    assert result.metadata.providers_used == ["tdx_vipdoc"]
    assert result.metadata.final_provider == "tdx_vipdoc"
    assert result.metadata.attempts[0].status == FETCH_SUCCESS
    assert capability_health_snapshot()["tdx_vipdoc:index_bars"].status == "success"
    assert "本地 vipdoc 上证指数最新 bar 落后 11 天（阈值 5 天）" in result.data.limitations


def test_fresh_local_probe_remains_fresh_and_successful(monkeypatch):
    monkeypatch.setattr(tc, "_max_staleness_days", lambda: 5.0)

    result = probe_trading_calendar_provider(
        "tdx_vipdoc",
        today="2026-09-21",
        adapter=_adapter(_days("2026-09-20")),
    )

    assert result.data is not None
    assert result.data.stale is False
    assert result.metadata.stale is False
    assert result.metadata.attempts[0].status == FETCH_SUCCESS
    assert capability_health_snapshot()["tdx_vipdoc:index_bars"].status == "success"


def test_mootdx_index_failure_does_not_touch_other_mootdx_capabilities():
    for capability in ("bars", "quote", "finance", "xdxr"):
        record_capability_health(
            ProviderCapability("mootdx", capability),
            FETCH_SUCCESS,
        )

    result = probe_trading_calendar_provider(
        "mootdx",
        today="2026-09-21",
        adapter=_adapter(VendorNetworkError("index down")),
    )

    assert result.data is None
    snapshot = capability_health_snapshot()
    assert snapshot["mootdx:index"].status == "failed"
    for capability in ("bars", "quote", "finance", "xdxr"):
        assert snapshot[f"mootdx:{capability}"].status == FETCH_SUCCESS


def test_sina_index_failure_does_not_touch_bars_or_quote():
    record_capability_health(ProviderCapability("sina", "bars"), FETCH_SUCCESS)
    record_capability_health(ProviderCapability("sina", "quote"), FETCH_SUCCESS)

    result = probe_trading_calendar_provider(
        "sina",
        today="2026-09-21",
        adapter=_adapter(VendorNetworkError("index down")),
    )

    assert result.data is None
    snapshot = capability_health_snapshot()
    assert snapshot["sina:index_bars"].status == "failed"
    assert snapshot["sina:bars"].status == FETCH_SUCCESS
    assert snapshot["sina:quote"].status == FETCH_SUCCESS
