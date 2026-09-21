"""FetchResult structured core tests — provider vs routing health, statuses,
timing separation, and legacy compatibility of the migrated quote slice."""

import pytest

from chstockdata import a_stock
from chstockdata.capabilities import (
    capability_health_snapshot,
    reset_capability_health,
)
from chstockdata.fetch_result import (
    FETCH_FAILED_NETWORK,
    FETCH_NORMAL_EMPTY,
    FETCH_SUCCESS,
    FetchAttempt,
    FetchMetadata,
    FetchResult,
)
from chstockdata.quote_chain import (
    QUOTE_PROVIDERS,
    RealtimeQuoteRoutingError,
    fetch_realtime_quotes,
)


@pytest.fixture(autouse=True)
def _clean_health_store():
    reset_capability_health()
    yield
    reset_capability_health()


def _quote(code="600519", *, price=1500.0, source="mootdx", **overrides):
    value = {
        "name": "贵州茅台",
        "price": price,
        "last_close": 1490.0,
        "open": 1495.0,
        "high": 1510.0,
        "low": 1488.0,
        "amount_wan": 12345.0,
        "change_pct": 0.67,
        "pe_ttm": None,
        "pe_static": None,
        "pb": None,
        "mcap_yi": None,
        "float_mcap_yi": None,
        "turnover_pct": None,
        "limit_up": None,
        "limit_down": None,
        "is_stale": False,
        "source": source,
    }
    value.update(overrides)
    return {code: value}


def _noop_quote_number(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number


class TestProviderVsRoutingHealth:
    def test_provider_a_failed_provider_b_success_routing_success(self):
        """核心场景：腾讯挂了、新浪救回 → 腾讯 attempt=failed、
        路由=success、final_provider=sina，且腾讯失败不被隐藏。"""
        def _tencent_fail(codes, **_kwargs):
            raise ConnectionError("tencent down")

        fetchers = {
            "tencent": _tencent_fail,
            "mootdx": lambda codes, **_kw: {},
            "sina": lambda codes, **_kw: _quote(source="sina"),
        }

        result = fetch_realtime_quotes(
            ["600519"], fetchers, quote_number=_noop_quote_number
        )

        assert result.succeeded
        assert result.metadata.final_provider == "sina"
        assert result.metadata.final_status == FETCH_SUCCESS
        # Provider health: 失败可见，不被路由成功掩盖。
        assert result.metadata.degraded
        assert "tencent" in result.metadata.failed_providers
        statuses = {a.provider: a.status for a in result.metadata.attempts}
        assert statuses["tencent"] == FETCH_FAILED_NETWORK
        assert statuses["sina"] == FETCH_SUCCESS
        # Capability health store 同步记录了逐能力结论。
        snapshot = capability_health_snapshot()
        assert snapshot["tencent:quote"].status == "failed"
        assert snapshot["sina:quote"].status == FETCH_SUCCESS

    def test_exception_classification_uses_vendor_taxonomy(self):
        """vendor_errors 行为分类：限流/无数据/未配置/网络/结构 各归其位。"""
        from chstockdata.vendor_errors import (
            VendorNetworkError,
            VendorNoDataError,
            VendorNotConfiguredError,
            VendorRateLimitError,
        )
        from chstockdata.quote_chain import _classify_status

        assert _classify_status(VendorRateLimitError("slow down")) == "failed_rate_limit"
        assert _classify_status(VendorNoDataError("no rows")) == "normal_empty"
        assert _classify_status(VendorNotConfiguredError("no key")) == "not_configured"
        assert _classify_status(VendorNetworkError("conn reset")) == "failed_network"
        assert _classify_status(KeyError("field")) == "failed_structure"
        assert _classify_status(ValueError("bad shape")) == "failed_structure"
        assert _classify_status(ConnectionError("down")) == "failed_network"

    def test_rate_limit_failure_does_not_block_next_provider(self):
        from chstockdata.vendor_errors import VendorRateLimitError

        fetchers = {
            "tencent": lambda codes, **_kw: (
                (_ for _ in ()).throw(VendorRateLimitError("throttled"))
            ),
            "mootdx": lambda codes, **_kw: _quote(source="mootdx"),
        }
        result = fetch_realtime_quotes(
            ["600519"], fetchers, quote_number=_noop_quote_number
        )
        assert result.succeeded
        assert result.metadata.final_provider == "mootdx"
        statuses = {a.provider: a.status for a in result.metadata.attempts}
        assert statuses["tencent"] == "failed_rate_limit"

    def test_all_providers_fail_raises_routing_error_with_attempts(self):
        def _fail(codes, **_kwargs):
            raise ConnectionError("down")

        fetchers = {p: _fail for p, _cap in QUOTE_PROVIDERS}

        with pytest.raises(RealtimeQuoteRoutingError) as exc_info:
            fetch_realtime_quotes(
                ["600519"], fetchers, quote_number=_noop_quote_number
            )
        assert len(exc_info.value.attempts) == 3
        assert all(a.status == FETCH_FAILED_NETWORK for a in exc_info.value.attempts)

    def test_mootdx_not_configured_is_recorded_and_chain_continues(self):
        """缺 mootdx（未装 extra）不阻断链路，capability 记 not_configured。"""
        fetchers = {
            "tencent": lambda codes, **_kw: {},
            "sina": lambda codes, **_kw: _quote(source="sina"),
        }
        result = fetch_realtime_quotes(
            ["600519"], fetchers, quote_number=_noop_quote_number
        )
        assert result.succeeded
        mootdx_attempt = next(
            a for a in result.metadata.attempts if a.provider == "mootdx"
        )
        assert mootdx_attempt.status == "not_configured"
        assert capability_health_snapshot()["mootdx:quote"].status == "not_configured"


class TestNormalEmptyVsFailure:
    def test_normal_empty_is_distinct_from_network_failure(self):
        """空响应 = normal_empty（健康观察）；连接失败 = failed（降级）。
        normal_empty 不编码"路由停止"策略——那由各 routing engine 决定。"""
        empty_attempt = FetchAttempt(
            provider="tencent", capability="tencent:quote",
            status=FETCH_NORMAL_EMPTY, started_at="2026-01-01T00:00:00+00:00",
            elapsed_ms=10, record_count=0,
        )
        failed_attempt = FetchAttempt(
            provider="mootdx", capability="mootdx:quote",
            status=FETCH_FAILED_NETWORK, started_at="2026-01-01T00:00:01+00:00",
            elapsed_ms=10, error_type="ConnectionError",
        )
        assert not empty_attempt.is_failure()
        assert not empty_attempt.is_success()  # 没有 data，只是正常空
        assert failed_attempt.is_failure() and not failed_attempt.is_success()

    def test_chain_with_only_empty_results_is_normal_empty_routing(self):
        """三源都正常返回空 → 路由结论 normal_empty，不是 failed_network。"""
        fetchers = {p: (lambda codes, **_kw: {}) for p, _ in QUOTE_PROVIDERS}
        result = fetch_realtime_quotes(
            ["600519"], fetchers, quote_number=_noop_quote_number
        )
        assert result.metadata.final_status == FETCH_NORMAL_EMPTY
        assert result.is_normal_empty
        assert result.data == {}
        # normal_empty 是健康观察，不是能力故障。
        snapshot = capability_health_snapshot()
        assert snapshot["tencent:quote"].status == FETCH_NORMAL_EMPTY
        assert snapshot["tencent:quote"].is_healthy

    def test_invalid_price_is_not_success(self):
        """价格非法（<=0）不计为成功；响应正常但数据不可用 = normal_empty
        路由，且与网络失败严格区分。"""
        fetchers = {
            "tencent": lambda codes, **_kw: _quote(price=0.0),
            "mootdx": lambda codes, **_kw: _quote(price=-1.0),
            "sina": lambda codes, **_kw: _quote(price=None),
        }
        result = fetch_realtime_quotes(
            ["600519"], fetchers, quote_number=_noop_quote_number
        )
        assert result.is_normal_empty
        assert result.data == {}
        assert not result.metadata.degraded  # 无 hard failure
        # 每个 attempt 都不是 success。
        assert all(a.status != FETCH_SUCCESS for a in result.metadata.attempts)


class TestMetadataTiming:
    def test_retrieved_at_and_observed_at_are_separate_fields(self):
        metadata = FetchMetadata(
            capability="quote",
            final_provider="sina",
            retrieved_at="2026-09-21T01:30:00+00:00",
            observed_at="2026-09-21T01:29:58+00:00",
            data_as_of="2026-09-21",
            attempts=[FetchAttempt(
                provider="sina", capability="sina:quote",
                status=FETCH_SUCCESS, started_at="2026-09-21T01:29:58+00:00",
                elapsed_ms=120,
            )],
            providers_used=["sina"],
        )
        # 抓取时间 ≠ 数据自身时间：两个字段独立存在且可不同。
        assert metadata.retrieved_at != metadata.observed_at
        assert metadata.data_as_of == "2026-09-21"
        serialized = metadata.to_dict()
        assert serialized["retrieved_at"] == "2026-09-21T01:30:00+00:00"
        assert serialized["observed_at"] == "2026-09-21T01:29:58+00:00"
        assert serialized["data_as_of"] == "2026-09-21"

    def test_fetch_result_is_generic_and_typed_container(self):
        metadata = FetchMetadata(
            capability="quote", final_provider=None,
            retrieved_at="2026-01-01T00:00:00+00:00",
            attempts=[FetchAttempt(
                provider="tencent", capability="tencent:quote",
                status=FETCH_SUCCESS, started_at="2026-01-01T00:00:00+00:00",
                elapsed_ms=80, record_count=1,
            )],
            providers_used=["tencent"],
        )
        result = FetchResult[dict](data={"600519": {"price": 1500.0}},
                                   metadata=metadata)
        assert result.succeeded
        assert not result.is_normal_empty
        assert result.data["600519"]["price"] == 1500.0
        assert result.metadata.capability == "quote"
        # 单 provider：final_provider 由不变量自动补全。
        assert metadata.final_provider == "tencent"

    def test_serialization_roundtrip_keeps_attempts_as_truth(self):
        metadata = FetchMetadata(
            capability="quote", final_provider=None,
            retrieved_at="2026-01-01T00:00:00+00:00",
            attempts=[
                FetchAttempt(
                    provider="tencent", capability="tencent:quote",
                    status=FETCH_FAILED_NETWORK,
                    started_at="2026-01-01T00:00:00+00:00",
                    elapsed_ms=5, error_type="ConnectionError",
                ),
                FetchAttempt(
                    provider="sina", capability="sina:quote",
                    status=FETCH_SUCCESS, started_at="2026-01-01T00:00:05+00:00",
                    elapsed_ms=120, record_count=1,
                ),
            ],
            providers_used=["sina"],
        )
        payload = metadata.to_dict()
        # 派生路由结论 = success（最后 terminal attempt），但早期失败保留在
        # attempts 里作为唯一事实来源——降级可见，不被成功掩盖。
        assert payload["final_status"] == FETCH_SUCCESS
        assert payload["attempts"][0]["status"] == FETCH_FAILED_NETWORK
        assert payload["degraded"] is True
        assert payload["failed_providers"] == ["tencent"]


class TestLegacyQuoteCompatibility:
    """Vertical-slice legacy contract：structured core 之上的 wrapper 行为不变。"""

    def test_wrapper_stops_at_tencent(self, monkeypatch):
        monkeypatch.setattr(
            a_stock, "_tencent_quote",
            lambda codes, **_kw: _quote(source="tencent"),
        )
        monkeypatch.setattr(
            a_stock, "_mootdx_realtime_quote",
            lambda codes, **_kw: pytest.fail("腾讯成功时不应调用 mootdx"),
        )
        result = a_stock._get_realtime_quotes(["600519"])
        assert result["600519"]["source"] == "tencent"

    def test_wrapper_falls_back_and_preserves_fallback_attempts(self, monkeypatch):
        def _fail(_codes, **_kwargs):
            raise ConnectionError("tencent down")

        monkeypatch.setattr(a_stock, "_tencent_quote", _fail)
        monkeypatch.setattr(
            a_stock, "_mootdx_realtime_quote",
            lambda codes, **_kw: _quote(source="mootdx"),
        )
        result = a_stock._get_realtime_quotes(["600519"])
        assert result["600519"]["source"] == "mootdx"
        # 每条 quote 保留 fallback_attempts（per-code 降级轨迹）。
        assert "ConnectionError" in result["600519"]["fallback_attempts"]

    def test_wrapper_stale_last_resort_unchanged(self, monkeypatch):
        stale = _quote(source="tencent", is_stale=True)
        monkeypatch.setattr(
            a_stock, "_tencent_quote", lambda codes, **_kw: stale
        )
        monkeypatch.setattr(
            a_stock, "_mootdx_realtime_quote",
            lambda codes, **_kw: _quote(source="mootdx", is_stale=True),
        )
        monkeypatch.setattr(
            a_stock, "_sina_realtime_quote",
            lambda codes, **_kw: _quote(source="sina", is_stale=True),
        )
        result = a_stock._get_realtime_quotes(["600519"])
        assert result["600519"]["quote_status"] == "stale_last_resort"
        assert result["600519"]["source"] == "tencent"

    def test_wrapper_sanitized_error_unchanged(self, monkeypatch):
        def _fail(_codes, **_kwargs):
            raise RuntimeError("https://private.example/token=secret")

        monkeypatch.setattr(a_stock, "_tencent_quote", _fail)
        monkeypatch.setattr(a_stock, "_mootdx_realtime_quote", _fail)
        monkeypatch.setattr(a_stock, "_sina_realtime_quote", _fail)

        with pytest.raises(a_stock._RealtimeQuoteUnavailable) as exc_info:
            a_stock._get_realtime_quotes(["600519"])
        message = str(exc_info.value)
        assert "实时行情不可用" in message
        assert "secret" not in message
        assert "private.example" not in message

    def test_snapshot_facade_output_unchanged(self, monkeypatch):
        monkeypatch.setattr(
            a_stock, "_get_realtime_quotes",
            lambda codes: {
                "002594": {
                    "name": "比亚迪", "price": 300.0, "change_pct": 1.25,
                    "source": "tencent", "is_stale": False,
                }
            },
        )
        snap = a_stock.get_realtime_snapshot("002594")
        assert snap["status"] == "ready"
        assert snap["price"] == 300.0
        assert snap["source"] == "tencent"
        assert snap["data_group"] == "实时行情"
        assert snap["observed_at"]
