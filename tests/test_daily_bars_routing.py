"""v0.4.0 Phase 2 — daily-bars structured routing engine 回归测试。

覆盖（离线，全部用注入的 fake adapters，零网络）：
- 路由顺序与短路：vipdoc 命中不触 mootdx/sina；vipdoc 不可用走 mootdx；
  mootdx 硬失败继续新浪；
- normal_empty routing policy（bars engine 内）：全部空 → normal_empty；
  全部硬失败 → 结构化路由错误（脱敏）；
- legacy 尾部补齐 contract：supplement 成功推进末根 → 双贡献者；
  supplement 失败不推翻 base，但 degraded=True；
- capability health 一致性：attempt 经唯一映射写 health；mootdx:bars 失败
  不改写 mootdx:finance（Phase 1.1 capability isolation 不回退）；
- 单 provider 隔离 probe（live 探针同路径）。
"""

import pandas as pd
import pytest

from chstockdata.capabilities import (
    ProviderCapability,
    capability_health_snapshot,
    get_capability_health,
    reset_capability_health,
)
from chstockdata.daily_bars import (
    DAILY_BAR_PROVIDERS,
    DailyBarsRoutingError,
    fetch_daily_bars,
    probe_daily_bars_provider,
)
from chstockdata.fetch_result import (
    FETCH_NORMAL_EMPTY,
    FETCH_NOT_CONFIGURED,
    FETCH_FAILED_NETWORK,
    FETCH_SUCCESS,
)
from chstockdata.vendor_errors import (
    VendorNetworkError,
    VendorNoDataError,
    VendorNotConfiguredError,
)

CODE = "600519"
START = "2026-09-08"
END = "2026-09-09"


@pytest.fixture(autouse=True)
def _fresh_health():
    reset_capability_health()
    yield
    reset_capability_health()


def _frame(dates, *, close=10.0, volume=1000, pre_close=False):
    frame = pd.DataFrame(
        {
            "Date": pd.to_datetime(dates),
            "Open": [close - 0.5] * len(dates),
            "High": [close + 1.0] * len(dates),
            "Low": [close - 1.0] * len(dates),
            "Close": [close] * len(dates),
            "Volume": [volume] * len(dates),
        }
    )
    if pre_close:
        frame["pre_close"] = [None] + [close] * (len(dates) - 1)
    return frame


def _never(provider):
    def _adapter(*args, **kwargs):
        raise AssertionError(f"{provider} must not be called")

    return _adapter


def _ok(dates, **kwargs):
    def _adapter(code, start, end):
        return _frame(dates, **kwargs)

    return _adapter


def _unconfigured(code, start, end):
    raise VendorNotConfiguredError("vipdoc missing")


def _no_data(code, start, end):
    raise VendorNoDataError("empty")


def _network_down(code, start, end):
    raise VendorNetworkError("connection reset")


def _chain(**overrides):
    chain = {
        "tdx_vipdoc": _unconfigured,
        "mootdx": _no_data,
        "sina": _no_data,
    }
    chain.update(overrides)
    return chain


# ── 1. 路由顺序与短路 ────────────────────────────────────────────────────────


def test_vipdoc_success_short_circuits_chain():
    result = fetch_daily_bars(
        CODE,
        START,
        END,
        adapters=_chain(
            tdx_vipdoc=_ok([START, END], pre_close=True),
            mootdx=_never("mootdx"),
            sina=_never("sina"),
        ),
    )

    assert result.succeeded
    assert result.metadata.final_provider == "tdx_vipdoc"
    assert result.metadata.providers_used == ["tdx_vipdoc"]
    assert not result.metadata.degraded
    assert [a.status for a in result.metadata.attempts] == [FETCH_SUCCESS]
    assert len(result.data) == 2
    # 只有被尝试的 provider 有 health 观察
    snapshot = capability_health_snapshot()
    assert set(snapshot) == {"tdx_vipdoc:daily_bars"}
    assert snapshot["tdx_vipdoc:daily_bars"].status == FETCH_SUCCESS


def test_vipdoc_unavailable_mootdx_success_sina_untouched():
    result = fetch_daily_bars(
        CODE,
        START,
        END,
        adapters=_chain(
            tdx_vipdoc=_unconfigured,
            mootdx=_ok([START, END]),
            sina=_never("sina"),
        ),
    )

    assert result.succeeded
    assert result.metadata.final_provider == "mootdx"
    assert result.metadata.providers_used == ["mootdx"]
    # not_configured 是事实不是硬失败：不构成 degraded
    assert not result.metadata.degraded
    statuses = [a.status for a in result.metadata.attempts]
    assert statuses == [FETCH_NOT_CONFIGURED, FETCH_SUCCESS]
    snapshot = capability_health_snapshot()
    assert snapshot["tdx_vipdoc:daily_bars"].status == "not_configured"
    assert snapshot["mootdx:bars"].status == FETCH_SUCCESS
    assert "sina:bars" not in snapshot


def test_structured_mootdx_adapter_suppresses_primitive_health(monkeypatch):
    """The structured canonical boundary is the only mootdx:bars owner."""
    from chstockdata import a_stock
    from chstockdata import daily_bars as bars

    calls = []

    def _mootdx_bars(*args, **kwargs):
        calls.append(kwargs)
        return _frame([START, END])

    monkeypatch.setattr(a_stock, "_fetch_mootdx_bars", _mootdx_bars)
    result = fetch_daily_bars(
        CODE,
        START,
        END,
        adapters=_chain(
            tdx_vipdoc=_unconfigured,
            mootdx=bars._fetch_structured_mootdx_daily_bars,
            sina=_never("sina"),
        ),
    )

    assert result.metadata.attempts[-1].status == FETCH_SUCCESS
    assert calls == [{"offset": 800, "_observe_capability_health": False}]


def test_malformed_structured_mootdx_payload_has_one_failed_health_owner(monkeypatch):
    """Primitive success telemetry must not precede structured rejection."""
    from chstockdata import a_stock
    from chstockdata import daily_bars as bars

    primitive_observations = []

    class _Client:
        def bars(self, **_kwargs):
            return pd.DataFrame(
                {
                    "Date": [START],
                    "Open": [10.0],
                    "High": [11.0],
                    "Low": [9.0],
                    "Volume": [1000],
                }
            )

    client = _Client()
    monkeypatch.setattr(a_stock, "_mootdx_client", client)
    monkeypatch.setattr(a_stock, "_get_mootdx_client", lambda **_kwargs: client)
    monkeypatch.setattr(a_stock, "_tdx_min_interval", lambda: 0.0)
    monkeypatch.setattr(
        a_stock,
        "_record_mootdx_capability",
        lambda *args, **kwargs: primitive_observations.append((args, kwargs)),
    )

    with pytest.raises(DailyBarsRoutingError) as exc_info:
        fetch_daily_bars(
            CODE,
            START,
            END,
            adapters=_chain(
                tdx_vipdoc=_unconfigured,
                mootdx=bars._fetch_structured_mootdx_daily_bars,
                sina=_no_data,
            ),
        )

    mootdx_attempt = next(
        attempt for attempt in exc_info.value.attempts if attempt.provider == "mootdx"
    )
    assert mootdx_attempt.status == "failed_structure"
    assert primitive_observations == []
    assert capability_health_snapshot()["mootdx:bars"].status == "failed"


def test_vipdoc_unavailable_mootdx_failure_sina_success():
    result = fetch_daily_bars(
        CODE,
        START,
        END,
        adapters=_chain(
            tdx_vipdoc=_unconfigured,
            mootdx=_network_down,
            sina=_ok([START, END]),
        ),
    )

    assert result.succeeded
    assert result.metadata.final_provider == "sina"
    assert result.metadata.providers_used == ["sina"]
    assert result.metadata.degraded, "硬失败的 provider 必须让结果标记 degraded"
    assert result.metadata.failed_providers == ["mootdx"]
    # attempts 保留全部观察
    statuses = [a.status for a in result.metadata.attempts]
    assert statuses == [FETCH_NOT_CONFIGURED, FETCH_FAILED_NETWORK, FETCH_SUCCESS]
    snapshot = capability_health_snapshot()
    assert snapshot["tdx_vipdoc:daily_bars"].status == "not_configured"
    assert snapshot["mootdx:bars"].status == "failed"
    assert snapshot["sina:bars"].status == FETCH_SUCCESS


def test_all_providers_normal_empty():
    result = fetch_daily_bars(
        CODE, START, END, adapters=_chain(tdx_vipdoc=_no_data)
    )

    assert result.is_normal_empty
    assert result.metadata.final_status == FETCH_NORMAL_EMPTY
    assert result.data.empty
    assert list(result.data.columns) == [
        "Date", "Open", "High", "Low", "Close", "Volume",
    ]
    assert result.metadata.limitations == ["all_sources_normal_empty"]
    snapshot = capability_health_snapshot()
    assert all(
        health.status == FETCH_NORMAL_EMPTY for health in snapshot.values()
    )


def test_all_providers_hard_failure_raises_sanitized_error():
    with pytest.raises(DailyBarsRoutingError) as excinfo:
        fetch_daily_bars(
            CODE,
            START,
            END,
            adapters=_chain(mootdx=_network_down, sina=_network_down),
        )

    assert len(excinfo.value.attempts) == 3
    # 脱敏：异常文案不带 vendor 细节
    assert "http" not in str(excinfo.value).lower()
    assert "reset" not in str(excinfo.value).lower()


def test_missing_provider_in_chain_is_not_configured():
    result = fetch_daily_bars(
        CODE,
        START,
        END,
        adapters={"mootdx": _ok([START, END])},
    )

    assert result.succeeded
    assert result.metadata.final_provider == "mootdx"
    statuses = [a.status for a in result.metadata.attempts]
    # 链首 vipdoc 缺席记 not_configured；mootdx 成功后短路，sina 不再尝试
    assert statuses == [FETCH_NOT_CONFIGURED, FETCH_SUCCESS]


# ── 2. legacy 尾部补齐（supplement）contract ────────────────────────────────


def test_supplement_advancing_last_bar_lists_both_providers():
    def _sina_supplement(code, start, end):
        assert start == START and end == "2026-09-10"
        return _frame(["2026-09-10"], close=11.0)

    result = fetch_daily_bars(
        CODE,
        START,
        "2026-09-10",
        adapters=_chain(
            tdx_vipdoc=_ok([START, END], pre_close=True),
            mootdx=_never("mootdx"),
            sina=_sina_supplement,
        ),
    )

    assert result.succeeded
    assert result.metadata.providers_used == ["tdx_vipdoc", "sina"]
    # 双贡献者：final_provider 不得谎称单源（FetchMetadata 不变量）
    assert result.metadata.final_provider is None
    assert result.data["Date"].max().strftime("%Y-%m-%d") == "2026-09-10"
    assert result.metadata.data_as_of == "2026-09-10"


def test_supplement_hard_failure_keeps_base_and_marks_degraded():
    result = fetch_daily_bars(
        CODE,
        START,
        "2026-09-10",
        adapters=_chain(
            tdx_vipdoc=_ok([START, END]),
            mootdx=_never("mootdx"),
            sina=_network_down,
        ),
    )

    assert result.succeeded, "supplement 失败不推翻 base（legacy 语义）"
    assert result.metadata.degraded
    assert result.metadata.providers_used == ["tdx_vipdoc"]
    assert "sina_supplement_failed" in result.metadata.limitations
    assert len(result.data) == 2


def test_supplement_empty_keeps_base_without_degradation():
    result = fetch_daily_bars(
        CODE,
        START,
        "2026-09-10",
        adapters=_chain(
            tdx_vipdoc=_ok([START, END]),
            mootdx=_never("mootdx"),
            sina=_no_data,
        ),
    )

    assert result.succeeded
    assert not result.metadata.degraded
    assert result.metadata.providers_used == ["tdx_vipdoc"]
    assert len(result.data) == 2


def test_base_reaching_end_skips_supplement():
    result = fetch_daily_bars(
        CODE,
        START,
        END,
        adapters=_chain(
            tdx_vipdoc=_unconfigured,
            mootdx=_ok([START, END]),
            sina=_never("sina"),
        ),
    )

    assert result.succeeded
    statuses = [a.status for a in result.metadata.attempts]
    assert statuses == [FETCH_NOT_CONFIGURED, FETCH_SUCCESS]


# ── 3. 窗口语义 ─────────────────────────────────────────────────────────────


def test_success_with_no_rows_in_window_is_success_with_limitation():
    # mootdx 契约是"最近 800 根"，可能完全落在请求窗口之外
    result = fetch_daily_bars(
        CODE,
        START,
        END,
        adapters=_chain(
            tdx_vipdoc=_unconfigured,
            mootdx=_ok(["2020-01-02", "2020-01-03"]),
            sina=_no_data,
        ),
    )

    assert result.succeeded
    assert result.data.empty
    assert result.metadata.data_as_of is None
    assert "no_bars_in_requested_window" in result.metadata.limitations


def test_window_filter_is_inclusive_on_both_ends():
    dates = ["2026-09-01", "2026-09-08", "2026-09-09", "2026-09-15"]
    result = fetch_daily_bars(
        CODE,
        START,
        END,
        adapters=_chain(tdx_vipdoc=_ok(dates), mootdx=_never("mootdx"), sina=_never("sina")),
    )

    assert list(result.data["Date"].dt.strftime("%Y-%m-%d")) == [START, END]


# ── 4. stale coverage policy ────────────────────────────────────────────────


def test_stale_coverage_is_success_with_stale_metadata():
    result = fetch_daily_bars(
        CODE,
        "2026-08-01",
        "2026-09-09",
        adapters=_chain(
            tdx_vipdoc=_unconfigured,
            mootdx=_ok(["2026-08-03", "2026-08-04"]),
            sina=_no_data,
        ),
    )

    assert result.succeeded
    assert result.metadata.stale
    assert any(
        item.startswith("stale_coverage:") for item in result.metadata.limitations
    )


# ── 5. capability health 隔离（Phase 1.1 语义不回退）────────────────────────


def test_mootdx_bars_failure_never_touches_other_mootdx_capabilities():
    from chstockdata.capabilities import record_capability_health

    record_capability_health(
        ProviderCapability("mootdx", "finance"), FETCH_SUCCESS
    )
    with pytest.raises(DailyBarsRoutingError):
        fetch_daily_bars(
            CODE,
            START,
            END,
            adapters=_chain(mootdx=_network_down, sina=_network_down),
        )

    snapshot = capability_health_snapshot()
    assert snapshot["mootdx:bars"].status == "failed"
    assert snapshot["mootdx:finance"].status == FETCH_SUCCESS, (
        "bars 失败不得改写 finance 的健康观察"
    )


# ── 6. vipdoc adapter 的 local 源状态分类（真实读取器 + tmp 包）──────────────


@pytest.mark.allow_vipdoc_history
def test_vipdoc_adapter_classifies_disabled_and_missing(tmp_path, monkeypatch):
    from chstockdata import vipdoc_history as vh
    from chstockdata.daily_bars import fetch_vipdoc_daily_bars

    monkeypatch.setattr(vh, "vipdoc_history_dir", lambda: str(tmp_path))
    monkeypatch.setattr("chstockdata.config.get_config", lambda: {
        "vipdoc_history_enabled": False,
        "vipdoc_history_max_staleness_days": 5,
    })
    with pytest.raises(VendorNotConfiguredError):
        fetch_vipdoc_daily_bars(CODE, START, END)

    monkeypatch.setattr("chstockdata.config.get_config", lambda: {
        "vipdoc_history_enabled": True,
        "vipdoc_history_max_staleness_days": 5,
    })
    with pytest.raises(VendorNotConfiguredError):
        fetch_vipdoc_daily_bars(CODE, START, END)  # 无本地文件


@pytest.mark.allow_vipdoc_history
def test_vipdoc_adapter_classifies_empty_window_and_staleness(tmp_path, monkeypatch):
    import struct
    from datetime import datetime, timezone, timedelta

    from chstockdata import vipdoc_history as vh
    from chstockdata.daily_bars import fetch_vipdoc_daily_bars

    market = vh.market_for_code(CODE).lower()
    path = tmp_path / market / "lday" / f"{market}{CODE}.day"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        b"".join(
            struct.pack("<IIIIIfII", int(day), 10000, 10100, 9900, 10050, 1.0e9, 1000, 0)
            for day in ("20260908", "20260909")
        )
    )
    monkeypatch.setattr(vh, "vipdoc_history_dir", lambda: str(tmp_path))
    monkeypatch.setattr("chstockdata.config.get_config", lambda: {
        "vipdoc_history_enabled": True,
        "vipdoc_history_max_staleness_days": 5,
    })

    # 文件存在、合法，但请求区间无记录 → normal_empty
    with pytest.raises(VendorNoDataError):
        fetch_vipdoc_daily_bars(CODE, "2026-09-15", "2026-09-16")

    # 超过 staleness policy（本地包落后请求截止 > 5 天）→ normal_empty，理由可读
    monkeypatch.setattr(
        "chstockdata.a_stock._calendar_reference_last_bar", lambda *_a, **_k: None
    )
    with pytest.raises(VendorNoDataError) as excinfo:
        fetch_vipdoc_daily_bars(CODE, "2026-09-01", "2026-09-30")
    assert "vipdoc package ends 2026-09-09" in str(excinfo.value)

    # 交易日历确认市场无更新 session（DEC-P1-27）→ 保留本地帧
    monkeypatch.setattr(
        "chstockdata.a_stock._calendar_reference_last_bar",
        lambda *_a, **_k: "2026-09-09",
    )
    frame = fetch_vipdoc_daily_bars(CODE, START, "2026-09-30")
    assert list(frame["Date"].dt.strftime("%Y-%m-%d")) == [START, END]
    # .day 文件语义的 pre_close 随帧携带；Amount 不进入 canonical bars
    assert "pre_close" in frame.columns
    assert "Amount" not in frame.columns


@pytest.mark.allow_vipdoc_history
def test_vipdoc_adapter_wraps_read_failure_as_structure_error(tmp_path, monkeypatch):
    from chstockdata import vipdoc_history as vh
    from chstockdata.daily_bars import fetch_vipdoc_daily_bars

    monkeypatch.setattr(vh, "vipdoc_history_dir", lambda: str(tmp_path))
    monkeypatch.setattr("chstockdata.config.get_config", lambda: {
        "vipdoc_history_enabled": True,
        "vipdoc_history_max_staleness_days": 5,
    })

    def _boom(*args, **kwargs):
        raise OSError("permission denied")

    monkeypatch.setattr(vh, "load_vipdoc_daily", _boom)
    with pytest.raises(ValueError, match="unreadable"):
        fetch_vipdoc_daily_bars(CODE, START, END)


# ── 7. 单 provider 隔离 probe（live 探针执行路径）───────────────────────────


def test_probe_records_only_the_probed_capability():
    result = probe_daily_bars_provider(
        "sina", CODE, START, END, _ok([START, END])
    )

    assert result.succeeded
    assert result.metadata.final_provider is None or result.metadata.providers_used == ["sina"]
    snapshot = capability_health_snapshot()
    assert set(snapshot) == {"sina:bars"}
    assert snapshot["sina:bars"].status == FETCH_SUCCESS


def test_probe_failure_and_empty_are_visible():
    failed = probe_daily_bars_provider("mootdx", CODE, START, END, _network_down)
    assert not failed.succeeded
    snapshot = capability_health_snapshot()
    assert snapshot["mootdx:bars"].status == "failed"
    assert set(snapshot) == {"mootdx:bars"}

    reset_capability_health()
    empty = probe_daily_bars_provider("mootdx", CODE, START, END, _no_data)
    assert empty.metadata.final_status == FETCH_NORMAL_EMPTY
    snapshot = capability_health_snapshot()
    assert snapshot["mootdx:bars"].status == FETCH_NORMAL_EMPTY


def test_provider_registry_matches_capability_ids():
    assert dict(DAILY_BAR_PROVIDERS) == {
        "tdx_vipdoc": "tdx_vipdoc:daily_bars",
        "mootdx": "mootdx:bars",
        "sina": "sina:bars",
    }
