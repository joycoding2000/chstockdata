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

import pytest

from chstockdata import a_stock
from chstockdata.capabilities import (
    capability_health_snapshot,
    reset_capability_health,
)
from chstockdata.fetch_result import FETCH_SUCCESS
from chstockdata.quote_chain import QUOTE_PROVIDERS, probe_quote_provider

pytestmark = pytest.mark.network

TICKER = "600519"

_QUOTE_FETCHERS = {
    "tencent": a_stock._tencent_quote,
    "mootdx": a_stock._mootdx_realtime_quote,
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
