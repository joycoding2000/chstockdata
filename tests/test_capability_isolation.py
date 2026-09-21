"""Capability isolation tests — one capability failing ≠ provider dead.

v0.4.0 regression guard: ``mootdx.bars`` unhealthy must never imply
``mootdx.finance`` / ``mootdx.xdxr`` unhealthy.
"""

import pytest

from chstockdata.capabilities import (
    HEALTH_FAILED,
    HEALTH_NORMAL_EMPTY,
    HEALTH_SUCCESS,
    ProviderCapability,
    capability_health_snapshot,
    get_capability_health,
    known_capabilities,
    record_capability_health,
    reset_capability_health,
)


@pytest.fixture(autouse=True)
def _clean_store():
    reset_capability_health()
    yield
    reset_capability_health()


class TestProviderCapabilityIdentity:
    def test_id_composition_is_stable(self):
        cap = ProviderCapability("mootdx", "bars")
        assert cap.id() == "mootdx:bars"
        assert ProviderCapability("mootdx", "quote").id() == "mootdx:quote"
        assert ProviderCapability("mootdx", "finance").id() == "mootdx:finance"
        assert ProviderCapability("mootdx", "xdxr").id() == "mootdx:xdxr"

    def test_identity_is_consumer_neutral(self):
        """Capability id 描述数据操作，不是下游 tool name。"""
        cap = ProviderCapability("tencent", "quote")
        assert cap.provider == "tencent"
        assert cap.capability == "quote"
        # 不含任何 TradingAgents-specific 语义。
        assert "tool" not in cap.capability

    def test_empty_components_rejected(self):
        with pytest.raises(ValueError):
            ProviderCapability("", "bars")
        with pytest.raises(ValueError):
            ProviderCapability("mootdx", "")

    def test_separator_characters_rejected(self):
        with pytest.raises(ValueError):
            ProviderCapability("moot:dx", "bars")
        with pytest.raises(ValueError):
            ProviderCapability("mootdx", "b ars")


class TestCapabilityIsolation:
    def test_bars_failure_does_not_mark_finance_failed(self):
        """核心隔离保证：bars 失败，finance/xdxr 不受牵连。"""
        bars = ProviderCapability("mootdx", "bars")
        finance = ProviderCapability("mootdx", "finance")
        xdxr = ProviderCapability("mootdx", "xdxr")

        record_capability_health(bars, HEALTH_FAILED, error_summary="timeout")

        assert get_capability_health(bars).status == HEALTH_FAILED
        assert get_capability_health(finance) is None
        assert get_capability_health(xdxr) is None

    def test_finance_succeeds_after_bars_failed(self):
        bars = ProviderCapability("mootdx", "bars")
        finance = ProviderCapability("mootdx", "finance")
        record_capability_health(bars, HEALTH_FAILED)
        record_capability_health(finance, HEALTH_SUCCESS)

        snapshot = capability_health_snapshot()
        assert snapshot["mootdx:bars"].status == HEALTH_FAILED
        assert snapshot["mootdx:finance"].status == HEALTH_SUCCESS
        assert snapshot["mootdx:finance"].is_healthy
        assert not snapshot["mootdx:bars"].is_healthy

    def test_isolation_across_providers(self):
        tencent_quote = ProviderCapability("tencent", "quote")
        sina_quote = ProviderCapability("sina", "quote")
        record_capability_health(tencent_quote, HEALTH_FAILED)
        record_capability_health(sina_quote, HEALTH_SUCCESS)

        snapshot = capability_health_snapshot()
        assert snapshot["tencent:quote"].status == HEALTH_FAILED
        assert snapshot["sina:quote"].status == HEALTH_SUCCESS

    def test_normal_empty_is_healthy(self):
        cap = ProviderCapability("mootdx", "xdxr")
        health = record_capability_health(cap, HEALTH_NORMAL_EMPTY)
        assert health.is_healthy

    def test_known_capabilities_lists_all_recorded(self):
        record_capability_health(ProviderCapability("mootdx", "bars"), HEALTH_FAILED)
        record_capability_health(ProviderCapability("mootdx", "finance"), HEALTH_SUCCESS)
        assert known_capabilities() == ["mootdx:bars", "mootdx:finance"]

    def test_invalid_status_rejected(self):
        with pytest.raises(ValueError):
            record_capability_health(ProviderCapability("mootdx", "bars"), "broken")
