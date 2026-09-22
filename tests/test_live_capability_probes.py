"""活体能力探针（``network`` 标记）：逐 capability 报告 provider 健康现状。

与 ``test_data_layer_live_smoke.py``（routing-chain smoke）的分工：

- routing smoke 回答「用户请求经 fallback 链是否最终成功」——链上有任何一源
  活着就 green；
- 本文件回答「**每个 provider capability** 现在是否正常」——mootdx:quote 挂了
  但新浪兜底成功时，routing green 而 ``mootdx:quote`` probe 必须单独红，
  问题不会被 fallback 成功掩盖。

Phase 1.1：probe 走 ``probe_quote_provider`` 单 provider 执行路径——
probe Tencent 只更新 ``tencent:quote``，probe mootdx 只更新 ``mootdx:quote``，
未参与 probe 的 provider 不会被写成 ``not_configured``、不会覆盖已有 health。
summary 打印的是真实最后观察。

只覆盖零鉴权免费主力源；东财端点刻意排除（CI runner 是数据中心 IP）。
"""

import datetime as dt

import pytest

from chstockdata import a_stock
from chstockdata.capabilities import (
    ProviderCapability,
    capability_health_snapshot,
    get_capability_health,
    reset_capability_health,
)
from chstockdata.fetch_result import FETCH_SUCCESS
from chstockdata.quote_chain import QUOTE_PROVIDERS, probe_quote_provider

pytestmark = pytest.mark.network

TICKER = "600519"

_QUOTE_FETCHERS = {
    "tencent": a_stock._tencent_quote,
    "mootdx": lambda codes: a_stock._mootdx_realtime_quote(
        codes,
        _observe_capability_health=False,
    ),
    "sina": a_stock._sina_realtime_quote,
}


def _probe(provider: str) -> bool:
    """对单个 provider capability 做隔离探测（只更新它自己的 health）。"""
    result = probe_quote_provider(
        provider,
        [TICKER],
        _QUOTE_FETCHERS[provider],
        quote_number=a_stock._quote_number,
    )
    return result.metadata.final_status == FETCH_SUCCESS


def test_tencent_quote_capability_probe():
    assert _probe("tencent"), "tencent:quote capability probe failed"


def test_mootdx_quote_capability_probe():
    assert _probe("mootdx"), "mootdx:quote capability probe failed"


def test_sina_quote_capability_probe():
    assert _probe("sina"), "sina:quote capability probe failed"


def test_capability_health_report_is_emitted():
    """探测结束后输出逐能力健康报告（live gate 的分项可见性）。

    每个 probe 只写自己的 capability；summary 与测试结论一一对应——
    某个 provider 的 probe 失败时，snapshot 里它的状态必然是 failed。
    """
    reset_capability_health()
    outcomes = {}
    for provider, _cap in QUOTE_PROVIDERS:
        ok = _probe(provider)
        outcomes[provider] = ok
        snapshot = capability_health_snapshot()
        health = snapshot[f"{provider}:quote"]
        # probe 结论与 health 记录一致（单 provider 探测不污染他人）。
        if ok:
            assert health.status == FETCH_SUCCESS, (provider, health)
        else:
            assert health.status != FETCH_SUCCESS, (provider, health)

    report = {
        capability_id: health.status
        for capability_id, health in sorted(capability_health_snapshot().items())
    }
    print("\nprovider capability health:", report)
    # 只有真正被 probe 过的三个 capability 有观察记录——没有 not_configured 污染。
    assert set(report) == {"tencent:quote", "mootdx:quote", "sina:quote"}, report
    assert all(status != "not_configured" for status in report.values()), report


# ── daily bars capability probes（v0.4.0 Phase 2，观测性 / 非阻塞）───────────
#
# 与 quote 探针同一分工：routing smoke（test_data_layer_live_smoke）回答
# 「daily-bars 用户路由是否最终拿到数据」；这里回答「哪个 individual provider
# capability 当前坏了」。单个 probe 只更新自己的 capability health。
# tdx_vipdoc 是本地数据路径，GitHub-hosted runner 无本地包，不进 live probe。
# mootdx:bars 在 CI 网络中失败必须真实显示——不允许 fallback 成绿掩盖。


def _bars_probe(provider: str) -> bool:
    """对单个 provider 的 bars capability 做隔离探测（真实适配器路径）。"""
    from chstockdata.daily_bars import ADAPTERS, probe_daily_bars_provider

    end = a_stock._today()
    start = end - dt.timedelta(days=30)
    result = probe_daily_bars_provider(
        provider,
        TICKER,
        start.isoformat(),
        end.isoformat(),
        ADAPTERS[provider],
    )
    return result.metadata.final_status == FETCH_SUCCESS


def test_sina_bars_capability_probe():
    ok = _bars_probe("sina")
    health = get_capability_health(ProviderCapability("sina", "bars"))
    assert health is not None and health.status != "not_configured", health
    assert ok, f"sina:bars capability probe failed (health={health})"


def test_mootdx_bars_capability_probe():
    ok = _bars_probe("mootdx")
    health = get_capability_health(ProviderCapability("mootdx", "bars"))
    assert health is not None and health.status != "not_configured", health
    assert ok, f"mootdx:bars capability probe failed (health={health})"


def test_bars_capability_health_report_is_emitted():
    """bars 探针结束后输出逐能力健康报告（与 quote 探针同款可见性）。"""
    from chstockdata.daily_bars import DAILY_BAR_PROVIDERS

    outcomes = {}
    for provider, capability_id in DAILY_BAR_PROVIDERS:
        if provider == "tdx_vipdoc":
            continue  # 本地包路径，CI 无 fixture 包，不进 live probe
        ok = _bars_probe(provider)
        outcomes[provider] = ok
        health = get_capability_health(ProviderCapability(*capability_id.split(":")))
        if ok:
            assert health.status == FETCH_SUCCESS, (provider, health)
        else:
            assert health.status != FETCH_SUCCESS, (provider, health)

    report = {
        capability_id: health.status
        for capability_id, health in sorted(capability_health_snapshot().items())
    }
    print("\ndaily-bars capability health:", report)


# ── trading-calendar capability probes (v0.4.0 Phase 3) ─────────────────────
# The local vipdoc adapter is intentionally excluded from hosted probes.  The
# two online probes are observability-only and remain under the workflow's
# continue-on-error probe step.


def _calendar_probe(provider: str) -> bool:
    from chstockdata.trading_calendar import (
        CALENDAR_ADAPTERS,
        probe_trading_calendar_provider,
    )

    result = probe_trading_calendar_provider(
        provider,
        today=a_stock._today(),
        adapter=CALENDAR_ADAPTERS[provider],
    )
    return result.metadata.final_status == FETCH_SUCCESS


def test_sina_trading_calendar_capability_probe():
    ok = _calendar_probe("sina")
    health = get_capability_health(ProviderCapability("sina", "index_bars"))
    assert health is not None and health.status != "not_configured", health
    assert ok, f"sina:index_bars capability probe failed (health={health})"


def test_mootdx_trading_calendar_capability_probe():
    ok = _calendar_probe("mootdx")
    health = get_capability_health(ProviderCapability("mootdx", "index"))
    assert health is not None and health.status != "not_configured", health
    assert ok, f"mootdx:index capability probe failed (health={health})"


def test_trading_calendar_capability_health_report_is_emitted():
    from chstockdata.trading_calendar import TRADING_CALENDAR_PROVIDERS

    reset_capability_health()
    outcomes = {}
    for provider, capability_id in TRADING_CALENDAR_PROVIDERS:
        if provider == "tdx_vipdoc":
            continue
        ok = _calendar_probe(provider)
        outcomes[provider] = ok
        health = get_capability_health(
            ProviderCapability(*capability_id.split(":", 1))
        )
        if ok:
            assert health.status == FETCH_SUCCESS, (provider, health)
        else:
            assert health.status != FETCH_SUCCESS, (provider, health)

    report = {
        capability_id: health.status
        for capability_id, health in sorted(capability_health_snapshot().items())
    }
    print("\ntrading-calendar capability health:", report)
    assert set(report) == {"mootdx:index", "sina:index_bars"}, report
