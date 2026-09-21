"""v0.4.0 Phase 1.1 Task A — mootdx 运行级 capability 隔离。

Phase 1 的 health store 是 capability-specific 的，但 runtime gating 不是：
bars readiness canary 全失败 → 全局负缓存 → finance/xdxr/quote 的
`_get_mootdx_call` 在 `_get_mootdx_client()` 就被快速失败，从未尝试。

本文件锁死修复后的行为分层（全部走真实 `_get_mootdx_client()` 路径，
只 patch 基础设施：服务器表 / TCP 预筛 / Quotes.factory / 负缓存文件）：

- transport 层结论（无一台能建 client）→ 所有 capability 快速失败（保留）；
- bars readiness 层结论（client 都建得起来，仅 bars canary 全失败）→
  只约束 bars；finance 等 capability 走 bounded bypass 并能成功；
- bypass 有界：不重新 TCP 全表预筛，不做 canary，单次调用内重试有界。
"""

import json
import threading

import pandas as pd
import pytest

from chstockdata import a_stock
from chstockdata.capabilities import (
    capability_health_snapshot,
    reset_capability_health,
)


class FakeMootdxClient:
    """bars 与 finance 行为可独立配置的假 client。"""

    def __init__(self, ip, *, bars_ok, finance_ok):
        self.ip = ip
        self.bars_ok = bars_ok
        self.finance_ok = finance_ok
        self.bars_calls = 0
        self.finance_calls = 0

    def bars(self, **kwargs):
        self.bars_calls += 1
        if not self.bars_ok:
            raise ConnectionResetError("[Errno 54] Connection reset by peer")
        return pd.DataFrame({"close": [1700.0]})

    def finance(self, **kwargs):
        self.finance_calls += 1
        if not self.finance_ok:
            raise ConnectionResetError("finance endpoint down")
        return pd.DataFrame([{"zongguben": 1_000_000_000}])


@pytest.fixture
def mootdx_env(monkeypatch, tmp_path):
    """隔离全部基础设施；client 行为由 state 控制。"""
    import mootdx.quotes

    cache_file = tmp_path / "mootdx-unavailable.json"
    monkeypatch.setattr(
        a_stock, "_mootdx_unavailable_cache_file", lambda: str(cache_file)
    )

    servers = [("1.1.1.1", 7709), ("2.2.2.2", 7709)]
    state = {
        "tcp_open": {ip for ip, _ in servers},
        "factory_ok": {ip for ip, _ in servers},  # 能建 client 的（transport 层）
        "bars_ok": set(),                          # bars canary 能过的
        "finance_ok": set(),                       # finance 端点能用的
        "probe_calls": [],
        "factory_calls": [],
        "clients": {},
        "cache_file": cache_file,
    }

    monkeypatch.setattr(a_stock, "_TDX_SERVERS", servers)
    monkeypatch.setattr(a_stock, "_candidate_tdx_servers", lambda: list(servers))
    monkeypatch.setattr(a_stock, "_mootdx_client", None)
    monkeypatch.setattr(a_stock, "_mootdx_unavailable_until", 0.0)
    monkeypatch.setattr(a_stock, "_mootdx_outage_rounds", 0)
    monkeypatch.setattr(a_stock, "_mootdx_reselect_pending", False)
    monkeypatch.setattr(a_stock, "_mootdx_reselect_candidates", ())
    monkeypatch.setattr(a_stock, "_mootdx_reselect_index", None)
    monkeypatch.setattr(a_stock, "_TDX_PROBE_GAP_S", 0.0)
    monkeypatch.setattr(a_stock, "_mootdx_last_call", 0.0)
    monkeypatch.setattr(a_stock, "_mootdx_call_lock", threading.RLock())
    monkeypatch.setenv("TDX_MIN_INTERVAL", "0")

    monkeypatch.setattr(
        a_stock,
        "_probe_tdx",
        lambda ip, port, timeout=2.0: (
            state["probe_calls"].append(ip) or ip in state["tcp_open"]
        ),
    )

    class FakeQuotes:
        @staticmethod
        def factory(market="std", server=None, **kwargs):
            ip = server[0] if server else "bestip"
            state["factory_calls"].append(ip)
            if ip not in state["factory_ok"]:
                raise ConnectionResetError("[Errno 54] Connection reset by peer")
            client = FakeMootdxClient(
                ip,
                bars_ok=ip in state["bars_ok"],
                finance_ok=ip in state["finance_ok"],
            )
            state["clients"][ip] = client
            return client

    monkeypatch.setattr(mootdx.quotes, "Quotes", FakeQuotes)
    reset_capability_health()
    yield state
    reset_capability_health()


def test_bars_readiness_failure_does_not_block_finance(mootdx_env):
    """核心验收：bars canary 全失败 → bars 不可用，但 finance 仍能成功。

    全程真实 `_get_mootdx_client()` 路径（只 patch 基础设施）。
    """
    mootdx_env["finance_ok"] = {"1.1.1.1", "2.2.2.2"}
    # bars_ok 保持空集：所有服务器 bars canary 全失败。

    with pytest.raises(RuntimeError):
        a_stock._mootdx_call("bars", symbol="600519")

    # bars 结论落盘，且结论层级标注为"transport 实际可用"（canary 推导）。
    assert mootdx_env["cache_file"].exists()
    payload = json.loads(mootdx_env["cache_file"].read_text(encoding="utf-8"))
    assert payload["transport_ok"] is True
    assert a_stock._mootdx_unavailable_until > 0
    assert capability_health_snapshot()["mootdx:bars"].status == "failed"

    # finance 走 bounded bypass（真实 client 选择路径），成功返回。
    probes_before = len(mootdx_env["probe_calls"])
    result = a_stock._mootdx_call("finance", symbol="600519")
    assert not result.empty
    assert a_stock._mootdx_client is not None
    # bypass 复用已缓存候选表：没有重新 TCP 全表预筛。
    assert len(mootdx_env["probe_calls"]) == probes_before
    # 健康观察互相独立。
    snapshot = capability_health_snapshot()
    assert snapshot["mootdx:bars"].status == "failed"
    assert snapshot["mootdx:finance"].status == "success"


def test_bars_and_finance_both_fail_degrades_bounded(mootdx_env):
    """bars fails + finance fails：正确降级，不产生无限扫描/重试。"""
    # finance_ok / bars_ok 都为空集。

    with pytest.raises(RuntimeError):
        a_stock._mootdx_call("bars", symbol="600519")
    probes_after_bars = len(mootdx_env["probe_calls"])

    # finance：bypass 建起 client → 真实 finance 调用失败 → 有界重试后抛错。
    with pytest.raises(ConnectionResetError, match="finance endpoint down"):
        a_stock._mootdx_call("finance", symbol="600519")
    # 单次 finance 调用 = 两次 bypass 遍历（初次 + 有界重试一次），全部复用
    # 已缓存候选表，无任何新增 TCP 预筛。
    assert len(mootdx_env["probe_calls"]) == probes_after_bars
    finance_factory_calls = mootdx_env["factory_calls"].count("1.1.1.1")
    assert 0 < finance_factory_calls <= 4, (
        "单次调用的 factory 尝试应有界"
    )

    # 再次 finance：仍走有界 bypass（候选表缓存），不重新扫表。
    with pytest.raises(ConnectionResetError):
        a_stock._mootdx_call("finance", symbol="600519")
    assert len(mootdx_env["probe_calls"]) == probes_after_bars

    # capability 健康彼此独立：bars 的失败结论不被 finance 的失败覆盖。
    snapshot = capability_health_snapshot()
    assert snapshot["mootdx:bars"].status == "failed"
    assert snapshot["mootdx:finance"].status == "failed"


def test_transport_level_failure_still_gates_all_capabilities(mootdx_env):
    """transport 级失败（无一台能建 client）→ 所有 capability 快速失败（保留）。"""
    mootdx_env["factory_ok"] = set()  # 握手都建不起来

    with pytest.raises(RuntimeError, match="协议握手/取数被拒"):
        a_stock._mootdx_call("bars", symbol="600519")
    probes_after_bars = len(mootdx_env["probe_calls"])

    with pytest.raises(RuntimeError, match="不再重试"):
        a_stock._mootdx_call("finance", symbol="600519")
    # transport 负缓存对非 bars capability 同样快速失败，无新探测。
    assert len(mootdx_env["probe_calls"]) == probes_after_bars
    payload = json.loads(mootdx_env["cache_file"].read_text(encoding="utf-8"))
    assert payload["transport_ok"] is False


def test_cold_start_with_canary_derived_disk_cache_allows_finance(
    mootdx_env, tmp_path
):
    """冷启动 + 磁盘 canary 推导负缓存（transport_ok=True）→ finance 可 bypass。"""
    import time

    mootdx_env["cache_file"].write_text(
        json.dumps({
            "until": time.time() + 3600,
            "rounds": 2,
            "reason": "bars readiness canary 全失败",
            "transport_ok": True,
        }),
        encoding="utf-8",
    )
    mootdx_env["finance_ok"] = {"1.1.1.1"}

    result = a_stock._mootdx_call("finance", symbol="600519")
    assert not result.empty
    assert a_stock._mootdx_client.ip == "1.1.1.1"


def test_cold_start_with_legacy_disk_cache_still_fast_fails(
    mootdx_env, monkeypatch
):
    """旧格式磁盘负缓存（无 transport_ok 字段）→ 保守按 transport 级处理。

    与 Phase 1.1 之前行为一致：所有 capability 快速失败、不探测。
    """
    import time

    mootdx_env["cache_file"].write_text(
        json.dumps({
            "until": time.time() + 3600,
            "rounds": 3,
            "reason": "legacy format",
        }),
        encoding="utf-8",
    )

    def _forbidden(*args, **kwargs):
        raise AssertionError("legacy cache hit must not probe servers")

    monkeypatch.setattr(a_stock, "_probe_tdx", _forbidden)
    monkeypatch.setattr(a_stock, "_candidate_tdx_servers", _forbidden)

    with pytest.raises(RuntimeError, match="不再重试"):
        a_stock._mootdx_call("finance", symbol="600519")


def test_mixed_factory_failure_and_canary_failure_keeps_transport_available(
    mootdx_env,
):
    """Phase 1.1.1 核心验收（mixed 边界）：

    A: factory fail；B: factory success + bars canary fail + finance success。
    存在性结论：至少一台 factory 成功 → transport_ok=True；
    bars 结论只约束 bars；finance 必须仍可尝试并成功。
    """
    mootdx_env["factory_ok"] = {"2.2.2.2"}   # A(1.1.1.1) 握手失败，B 可建 client
    mootdx_env["finance_ok"] = {"2.2.2.2"}
    # bars_ok 保持空集：B 的 bars canary 失败。

    with pytest.raises(RuntimeError):
        a_stock._mootdx_call("bars", symbol="600519")

    # 落盘结论必须是"transport 可用、bars readiness 失败"，而不是 transport 级。
    assert mootdx_env["cache_file"].exists()
    payload = json.loads(mootdx_env["cache_file"].read_text(encoding="utf-8"))
    assert payload["transport_ok"] is True
    assert "bars readiness canary" in payload["reason"]
    assert capability_health_snapshot()["mootdx:bars"].status == "failed"
    assert a_stock._mootdx_transport_ok is True

    # finance 走 bounded bypass 成功；复用已缓存候选表，不重新 TCP 全表扫描。
    probes_before = len(mootdx_env["probe_calls"])
    result = a_stock._mootdx_call("finance", symbol="600519")
    assert not result.empty
    assert a_stock._mootdx_client is not None
    assert capability_health_snapshot()["mootdx:finance"].status == "success"
    assert len(mootdx_env["probe_calls"]) == probes_before


def test_all_factory_failures_still_yield_transport_unavailable(mootdx_env):
    """反向回归：所有 factory 都失败（无任何成功证据）→ transport_ok=False。"""
    mootdx_env["factory_ok"] = set()

    with pytest.raises(RuntimeError, match="协议握手/取数被拒"):
        a_stock._mootdx_call("bars", symbol="600519")

    payload = json.loads(mootdx_env["cache_file"].read_text(encoding="utf-8"))
    assert payload["transport_ok"] is False
    assert "协议握手/取数被拒" in payload["reason"]

    with pytest.raises(RuntimeError, match="不再重试"):
        a_stock._mootdx_call("finance", symbol="600519")


def test_bare_factory_success_counts_as_transport_evidence(mootdx_env):
    """裸 factory 成功（+ bars canary 失败）也必须纳入 transport evidence。

    候选表全部 factory 失败时，裸 factory 兜底若能建 client，transport 层
    同样被证明可用——不能因为候选表曾有 factory 失败就写 transport_ok=False。
    """
    mootdx_env["factory_ok"] = set()  # 候选表全部 factory 失败
    # 裸 factory 走 user-config 分支：fixture 的 FakeQuotes 对 server=None 用
    # "bestip" 键 —— 这里直接让它成功（factory_ok 加 "bestip"）。
    mootdx_env["factory_ok"].add("bestip")
    mootdx_env["finance_ok"].add("bestip")

    with pytest.raises(RuntimeError):
        a_stock._mootdx_call("bars", symbol="600519")

    payload = json.loads(mootdx_env["cache_file"].read_text(encoding="utf-8"))
    assert payload["transport_ok"] is True

    # finance 走 bypass：候选表为空（全部 factory 失败未缓存）时做一次有界
    # TCP 预筛，随后复用；不陷入重复全表扫描。
    probes_before = len(mootdx_env["probe_calls"])
    result = a_stock._mootdx_call("finance", symbol="600519")
    assert not result.empty
    probes_after = len(mootdx_env["probe_calls"])
    probes_before2 = probes_after
    a_stock._mootdx_call("finance", symbol="600519")
    assert len(mootdx_env["probe_calls"]) == probes_before2
    # 有界：bypass 只补一轮预筛（2 台），不是每次调用都扫全表。
    assert probes_after - probes_before <= len(mootdx_env["tcp_open"])


def test_unknown_capability_stays_conservative(mootdx_env):
    """未知 capability 名保守要求 canary（与 Phase 1 之前一致）。"""
    with pytest.raises(RuntimeError):
        a_stock._mootdx_call("brand_new_method", symbol="600519")
    # canary 全失败 → 负缓存写盘；之后同样保守快速失败。
    with pytest.raises(RuntimeError, match="不再重试"):
        a_stock._mootdx_call("brand_new_method", symbol="600519")
