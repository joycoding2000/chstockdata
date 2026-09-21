"""v0.4.0 Phase 1.1 — structured core semantics regression tests.

Acceptance criteria covered here:

2. single-provider probe updates only its own capability health (Task B)
3. FetchAttempt status and CapabilityHealth status stay consistent (Task C)
4. mixed-source quote result is represented correctly (Task D)
5. normal_empty does not encode a universal routing-stop policy (Task D)
6. partial quote routing remains success + partial (Task D)
7. health clock seam is deterministic (Task E)
"""

import time
from datetime import datetime, timezone

import pytest

from chstockdata.capabilities import (
    HEALTH_FAILED,
    HEALTH_NORMAL_EMPTY,
    HEALTH_NOT_CONFIGURED,
    HEALTH_SUCCESS,
    ProviderCapability,
    capability_health_snapshot,
    fetch_status_to_health_status,
    get_capability_health,
    record_capability_health,
    reset_capability_health,
    set_health_clock,
)
from chstockdata.fetch_result import (
    FETCH_FAILED_NETWORK,
    FETCH_FAILED_RATE_LIMIT,
    FETCH_FAILED_STRUCTURE,
    FETCH_NORMAL_EMPTY,
    FETCH_NOT_CONFIGURED,
    FETCH_SUCCESS,
    FetchAttempt,
    FetchMetadata,
)
from chstockdata.quote_chain import (
    RealtimeQuoteRoutingError,
    fetch_realtime_quotes,
    probe_quote_provider,
)
from chstockdata.vendor_errors import (
    VendorNetworkError,
    VendorNoDataError,
    VendorNotConfiguredError,
    VendorRateLimitError,
)


@pytest.fixture(autouse=True)
def _clean_health_store():
    reset_capability_health()
    yield
    reset_capability_health()


def _num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _quote(code="600519", *, price=1500.0, source="tencent", **overrides):
    value = {
        "name": "贵州茅台",
        "price": price,
        "last_close": 1490.0,
        "amount_wan": 12345.0,
        "is_stale": False,
        "source": source,
    }
    value.update(overrides)
    return {code: value}


# ── Task B: single-provider probe isolation ─────────────────────────────────

class TestSingleProviderProbeIsolation:
    def test_probe_updates_only_its_own_health(self):
        """probe Tencent → 只写 tencent:quote；probe mootdx → 只写 mootdx:quote。"""
        result = probe_quote_provider(
            "tencent", ["600519"], lambda codes, **_kw: _quote(),
            quote_number=_num,
        )
        assert result.metadata.final_status == FETCH_SUCCESS
        assert capability_ids() == ["tencent:quote"]

        probe_quote_provider(
            "mootdx", ["600519"],
            lambda codes, **_kw: _quote(source="mootdx"),
            quote_number=_num,
        )
        assert capability_ids() == ["mootdx:quote", "tencent:quote"]
        assert get_capability_health(ProviderCapability("mootdx", "quote")).status \
            == HEALTH_SUCCESS

    def test_probe_sina_failure_leaves_others_untouched(self):
        probe_quote_provider(
            "tencent", ["600519"], lambda codes, **_kw: _quote(),
            quote_number=_num,
        )
        probe_quote_provider(
            "mootdx", ["600519"],
            lambda codes, **_kw: _quote(source="mootdx"),
            quote_number=_num,
        )
        result = probe_quote_provider(
            "sina", ["600519"],
            lambda codes, **_kw: (_ for _ in ()).throw(ConnectionError("down")),
            quote_number=_num,
        )

        snapshot_map = {
            capability_id: health.status
            for capability_id, health in
            capability_health_snapshot().items()
        }
        # 接受标准：三个独立 probe 的真实结果，互不污染、无 not_configured。
        assert snapshot_map == {
            "tencent:quote": HEALTH_SUCCESS,
            "mootdx:quote": HEALTH_SUCCESS,
            "sina:quote": HEALTH_FAILED,
        }
        assert result.metadata.final_status == FETCH_FAILED_NETWORK
        assert result.metadata.attempts[0].status == FETCH_FAILED_NETWORK

    def test_probe_never_records_not_configured(self):
        """未参与 probe 的 provider 不得被写成 not_configured。"""
        probe_quote_provider(
            "sina", ["600519"], lambda codes, **_kw: {},
            quote_number=_num,
        )
        snapshot_map = {
            capability_id: health.status
            for capability_id, health in capability_health_snapshot().items()
        }
        assert snapshot_map == {"sina:quote": HEALTH_NORMAL_EMPTY}

    def test_probe_unknown_provider_rejected(self):
        with pytest.raises(ValueError, match="unknown quote provider"):
            probe_quote_provider(
                "eastmoney", ["600519"], lambda codes, **_kw: {},
                quote_number=_num,
            )

    def test_probe_stale_snapshot_is_success_with_limitation(self):
        result = probe_quote_provider(
            "tencent", ["600519"],
            lambda codes, **_kw: _quote(is_stale=True),
            quote_number=_num,
        )
        assert result.metadata.final_status == FETCH_SUCCESS
        assert result.metadata.stale is True
        assert "stale_snapshot" in result.metadata.limitations


def capability_ids():
    return sorted(capability_health_snapshot())


# ── Task C: FetchAttempt ↔ CapabilityHealth status consistency ──────────────

class TestStatusConsistency:
    @pytest.mark.parametrize(
        ("exc", "expected_attempt_status", "expected_health_status"),
        [
            (VendorNoDataError("no rows"), FETCH_NORMAL_EMPTY, HEALTH_NORMAL_EMPTY),
            (VendorNotConfiguredError("no key"), FETCH_NOT_CONFIGURED, HEALTH_NOT_CONFIGURED),
            (VendorRateLimitError("throttled"), FETCH_FAILED_RATE_LIMIT, HEALTH_FAILED),
            (VendorNetworkError("conn reset"), FETCH_FAILED_NETWORK, HEALTH_FAILED),
            (ValueError("bad shape"), FETCH_FAILED_STRUCTURE, HEALTH_FAILED),
        ],
    )
    def test_attempt_and_health_status_agree(
        self, exc, expected_attempt_status, expected_health_status
    ):
        """同一次 provider observation：attempt 状态与 health 状态不得冲突。"""
        provider = "sina"
        result = probe_quote_provider(
            provider, ["600519"],
            lambda codes, **_kw: (_ for _ in ()).throw(exc),
            quote_number=_num,
        )
        attempt = result.metadata.attempts[0]
        assert attempt.status == expected_attempt_status

        health = get_capability_health(ProviderCapability(provider, "quote"))
        assert health.status == expected_health_status
        # 唯一映射自洽：attempt status 经映射后必须等于 health status。
        assert fetch_status_to_health_status(attempt.status) == health.status

    def test_mapping_is_total_over_fetch_vocabulary(self):
        assert fetch_status_to_health_status(FETCH_SUCCESS) == HEALTH_SUCCESS
        assert fetch_status_to_health_status(FETCH_NORMAL_EMPTY) == HEALTH_NORMAL_EMPTY
        assert fetch_status_to_health_status(FETCH_NOT_CONFIGURED) == HEALTH_NOT_CONFIGURED
        assert fetch_status_to_health_status("skipped") == "skipped"
        assert fetch_status_to_health_status(FETCH_FAILED_NETWORK) == HEALTH_FAILED
        assert fetch_status_to_health_status(FETCH_FAILED_RATE_LIMIT) == HEALTH_FAILED
        assert fetch_status_to_health_status(FETCH_FAILED_STRUCTURE) == HEALTH_FAILED

    def test_mapping_is_idempotent_over_health_vocabulary(self):
        for status in (HEALTH_SUCCESS, HEALTH_NORMAL_EMPTY, HEALTH_FAILED,
                       HEALTH_NOT_CONFIGURED, "skipped"):
            assert fetch_status_to_health_status(status) == status

    def test_mapping_rejects_unknown_status(self):
        with pytest.raises(ValueError, match="unknown fetch/health status"):
            fetch_status_to_health_status("broken")


# ── Task D: multi-provider / mixed-source metadata semantics ────────────────

class TestMultiProviderMetadata:
    def test_mixed_source_result_reflects_both_providers(self):
        """600519←腾讯、000001←新浪：providers_used 记录两源，final_provider=None。"""
        fetchers = {
            "tencent": lambda codes, **_kw: _quote("600519"),
            "mootdx": lambda codes, **_kw: {},
            "sina": lambda codes, **_kw: _quote("000001", source="sina"),
        }
        result = fetch_realtime_quotes(["600519", "000001"], fetchers,
                                       quote_number=_num)

        assert set(result.data) == {"600519", "000001"}
        assert result.data["600519"]["source"] == "tencent"
        assert result.data["000001"]["source"] == "sina"
        assert result.metadata.providers_used == ["tencent", "sina"]
        assert result.metadata.final_provider is None  # 不谎称单源
        assert result.metadata.partial is False
        assert result.metadata.final_status == FETCH_SUCCESS

    def test_single_source_result_keeps_final_provider(self):
        fetchers = {
            "tencent": lambda codes, **_kw: {
                "600519": _quote("600519")["600519"],
                "000001": _quote("000001")["000001"],
            },
            "mootdx": lambda codes, **_kw: {},
            "sina": lambda codes, **_kw: {},
        }
        result = fetch_realtime_quotes(["600519", "000001"], fetchers,
                                       quote_number=_num)
        assert result.metadata.providers_used == ["tencent"]
        assert result.metadata.final_provider == "tencent"

    def test_final_provider_invariant_enforced(self):
        """混源结果手工指定 final_provider 必须被拒绝（契约防护）。"""
        with pytest.raises(ValueError, match="providers_used"):
            FetchMetadata(
                capability="quote", final_provider="tencent",
                retrieved_at="2026-01-01T00:00:00+00:00",
                providers_used=["tencent", "sina"],
            )

    def test_mixed_result_serialization_roundtrip(self):
        fetchers = {
            "tencent": lambda codes, **_kw: _quote("600519"),
            "mootdx": lambda codes, **_kw: {},
            "sina": lambda codes, **_kw: _quote("000001", source="sina"),
        }
        result = fetch_realtime_quotes(["600519", "000001"], fetchers,
                                       quote_number=_num)
        payload = result.metadata.to_dict()
        assert payload["providers_used"] == ["tencent", "sina"]
        assert payload["final_provider"] is None
        assert payload["final_status"] == FETCH_SUCCESS

    def test_partial_response_is_success_with_partial_flag(self):
        """600519 成功、000001 三源全空 → routing success + partial=True。"""
        fetchers = {
            "tencent": lambda codes, **_kw: _quote("600519"),
            "mootdx": lambda codes, **_kw: {},
            "sina": lambda codes, **_kw: {},
        }
        result = fetch_realtime_quotes(["600519", "000001"], fetchers,
                                       quote_number=_num)
        assert result.succeeded
        assert result.metadata.partial is True
        assert "missing_quotes:000001" in result.metadata.limitations

    def test_all_normal_empty_routing_stays_normal_empty(self):
        fetchers = {p: (lambda codes, **_kw: {}) for p in ("tencent", "mootdx", "sina")}
        result = fetch_realtime_quotes(["600519"], fetchers, quote_number=_num)
        assert result.metadata.final_status == FETCH_NORMAL_EMPTY
        assert result.data == {}
        assert result.metadata.providers_used == []
        assert result.metadata.final_provider is None

    def test_failure_then_success_is_degraded_but_visible(self):
        fetchers = {
            "tencent": lambda codes, **_kw: (
                (_ for _ in ()).throw(ConnectionError("tencent down"))
            ),
            "mootdx": lambda codes, **_kw: {},
            "sina": lambda codes, **_kw: _quote(source="sina"),
        }
        result = fetch_realtime_quotes(["600519"], fetchers, quote_number=_num)
        assert result.succeeded
        assert result.metadata.final_status == FETCH_SUCCESS
        assert result.metadata.degraded is True
        assert result.metadata.failed_providers == ["tencent"]
        assert result.metadata.final_provider == "sina"

    def test_all_hard_failures_raise(self):
        def _fail(codes, **_kw):
            raise ConnectionError("down")

        fetchers = {p: _fail for p in ("tencent", "mootdx", "sina")}
        with pytest.raises(RealtimeQuoteRoutingError):
            fetch_realtime_quotes(["600519"], fetchers, quote_number=_num)


# ── Task D: normal_empty is policy-neutral in the generic model ─────────────

class TestNormalEmptyPolicyNeutrality:
    def test_attempt_model_has_no_routing_stop_api(self):
        """generic attempt 不携带"是否应停止路由"的判断。"""
        attempt = FetchAttempt(
            provider="tencent", capability="tencent:quote",
            status=FETCH_NORMAL_EMPTY, started_at="2026-01-01T00:00:00+00:00",
            elapsed_ms=5,
        )
        assert not hasattr(attempt, "is_terminal")
        assert not hasattr(attempt, "should_fallback")

    def test_quote_chain_policy_falls_through_on_normal_empty(self):
        """quote 路由策略：normal_empty → 继续下一源（策略在 engine，不在模型）。"""
        calls = []

        def _tencent(codes, **_kw):
            calls.append("tencent")
            return {}

        def _mootdx(codes, **_kw):
            calls.append("mootdx")
            return _quote(source="mootdx")

        result = fetch_realtime_quotes(
            ["600519"],
            {"tencent": _tencent, "mootdx": _mootdx},
            quote_number=_num,
        )
        assert calls == ["tencent", "mootdx"]
        assert result.metadata.final_provider == "mootdx"

    def test_final_status_reflects_whole_request_not_last_attempt(self):
        """final_status = 整个路由请求的结论：先空后成功 → success（而非
        机械取"最后一条 attempt"）。"""
        metadata = FetchMetadata(
            capability="quote", final_provider=None,
            retrieved_at="2026-01-01T00:00:00+00:00",
            attempts=[
                FetchAttempt(
                    provider="tencent", capability="tencent:quote",
                    status=FETCH_NORMAL_EMPTY,
                    started_at="2026-01-01T00:00:00+00:00", elapsed_ms=5,
                ),
                FetchAttempt(
                    provider="sina", capability="sina:quote",
                    status=FETCH_SUCCESS,
                    started_at="2026-01-01T00:00:05+00:00", elapsed_ms=50,
                    record_count=1,
                ),
            ],
            providers_used=["sina"],
        )
        assert metadata.final_status == FETCH_SUCCESS
        assert metadata.final_provider == "sina"


# ── Task E: health clock seam ────────────────────────────────────────────────

class TestHealthClockSeam:
    def setup_method(self):
        reset_capability_health()

    def teardown_method(self):
        set_health_clock(time.time)
        reset_capability_health()

    def test_fake_clock_makes_observed_at_deterministic(self):
        fixed_epoch = 1_700_000_000.0
        set_health_clock(lambda: fixed_epoch)

        health = record_capability_health(
            ProviderCapability("mootdx", "bars"), HEALTH_SUCCESS
        )
        expected = datetime.fromtimestamp(
            fixed_epoch, timezone.utc
        ).isoformat()
        assert health.observed_at == expected

    def test_two_observations_with_stopped_clock_share_timestamp(self):
        set_health_clock(lambda: 1_700_000_000.0)
        first = record_capability_health(
            ProviderCapability("mootdx", "bars"), HEALTH_FAILED
        )
        second = record_capability_health(
            ProviderCapability("mootdx", "finance"), HEALTH_SUCCESS
        )
        assert first.observed_at == second.observed_at

    def test_default_clock_restored(self):
        set_health_clock(lambda: 1_700_000_000.0)
        record_capability_health(ProviderCapability("mootdx", "bars"), HEALTH_SUCCESS)
        set_health_clock(time.time)
        health = record_capability_health(
            ProviderCapability("mootdx", "bars"), HEALTH_SUCCESS
        )
        # 恢复真实时钟后，observed_at 接近当前时间（±1 分钟）。
        now_iso = datetime.now(timezone.utc).isoformat()
        assert health.observed_at[:16] == now_iso[:16]
