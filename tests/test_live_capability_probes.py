"""活体能力探针（``network`` 标记）：逐 capability 报告 provider 健康现状。

与 ``test_data_layer_live_smoke.py``（routing-chain smoke）的分工：

- routing smoke 回答「用户请求经 fallback 链是否最终成功」——链上有任何一源
  活着就 green；
- 本文件回答「**每个 provider capability** 现在是否正常」——mootdx:quote 挂了
  但新浪兜底成功时，routing green 而 ``mootdx:quote`` probe 必须单独红，
  问题不会被 fallback 成功掩盖。

只覆盖零鉴权免费主力源；东财端点刻意排除（CI runner 是数据中心 IP）。
"""

import pytest

from chstockdata import a_stock
from chstockdata.capabilities import (
    capability_health_snapshot,
    reset_capability_health,
)
from chstockdata.quote_chain import fetch_realtime_quotes

pytestmark = pytest.mark.network

TICKER = "600519"


def _provider_probe(provider: str) -> bool:
    """对单个 provider capability 做独立探测（不经过 fallback 链）。"""
    fetchers = {
        "tencent": a_stock._tencent_quote,
        "mootdx": a_stock._mootdx_realtime_quote,
        "sina": a_stock._sina_realtime_quote,
    }
    try:
        result = fetch_realtime_quotes(
            [TICKER],
            {provider: fetchers[provider]},
            quote_number=a_stock._quote_number,
        )
    except Exception:
        return False
    return bool(result.data.get(TICKER))


def test_tencent_quote_capability_probe():
    assert _provider_probe("tencent"), "tencent:quote capability probe failed"


def test_mootdx_quote_capability_probe():
    assert _provider_probe("mootdx"), "mootdx:quote capability probe failed"


def test_sina_quote_capability_probe():
    assert _provider_probe("sina"), "sina:quote capability probe failed"


def test_capability_health_report_is_emitted():
    """探测结束后输出逐能力健康报告（live gate 的分项可见性）。"""
    reset_capability_health()
    for provider in ("tencent", "mootdx", "sina"):
        _provider_probe(provider)
    snapshot = capability_health_snapshot()
    report = {
        capability_id: health.status
        for capability_id, health in sorted(snapshot.items())
    }
    print("\nprovider capability health:", report)
    # 至少探测到 quote 能力的观察记录。
    assert any(cap_id.endswith(":quote") for cap_id in report), report
