"""TDX bridge in-process health circuit regression tests."""

from __future__ import annotations

import json
from subprocess import CompletedProcess

import pytest


def _ok_process() -> CompletedProcess:
    return CompletedProcess(
        [],
        0,
        stdout=json.dumps({"source": "tdx", "current": [{"main_net": 1.0}]}),
        stderr="",
    )


def _failed_process() -> CompletedProcess:
    return CompletedProcess([], 2, stdout="", stderr='{"error_type": "ImportError"}')


@pytest.fixture(autouse=True)
def _clean_health(monkeypatch):
    from chstockdata import tdx_bridge

    # issues/023 P0 止血：桥调用串行化后相邻 launch 会补足 TDX_BRIDGE_MIN_INTERVAL，
    # 测试里关掉间隔，避免真实 sleep 拖慢套件。
    monkeypatch.setenv("TDX_BRIDGE_MIN_INTERVAL", "0")
    tdx_bridge._reset_health()
    tdx_bridge._last_bridge_launch = float("-inf")
    yield
    tdx_bridge._reset_health()
    tdx_bridge._last_bridge_launch = float("-inf")


def test_circuit_opens_after_consecutive_failures(monkeypatch):
    """连续失败达到阈值后，后续调用直接短路，不再起子进程。"""
    from chstockdata import tdx_bridge

    calls = {"n": 0}

    def fake_run(command, **kwargs):
        calls["n"] += 1
        return _failed_process()

    monkeypatch.setattr(tdx_bridge.subprocess, "run", fake_run)

    for _ in range(tdx_bridge._FAILURE_THRESHOLD):
        with pytest.raises(tdx_bridge.TdxBridgeUnavailable):
            tdx_bridge.run_tdx_bridge("fund-flow", "SH", "600519", "0")

    # Each logical bridge call has one bounded restart/retry; health counts
    # the exhausted call once, rather than counting both subprocess attempts.
    assert calls["n"] == tdx_bridge._FAILURE_THRESHOLD * 2

    def must_not_run(command, **kwargs):
        raise AssertionError("circuit open must not spawn a bridge subprocess")

    monkeypatch.setattr(tdx_bridge.subprocess, "run", must_not_run)
    with pytest.raises(tdx_bridge.TdxBridgeUnavailable) as exc_info:
        tdx_bridge.run_tdx_bridge("fund-flow", "SH", "600519", "0")
    assert exc_info.value.category == "CircuitOpen"


def test_single_failure_does_not_open_circuit(monkeypatch):
    """单次失败不熔断：下一次调用仍真实探测。"""
    from chstockdata import tdx_bridge

    state = {"next_ok": False}

    def fake_run(command, **kwargs):
        return _ok_process() if state["next_ok"] else _failed_process()

    monkeypatch.setattr(tdx_bridge.subprocess, "run", fake_run)

    with pytest.raises(tdx_bridge.TdxBridgeUnavailable):
        tdx_bridge.run_tdx_bridge("fund-flow", "SH", "600519", "0")

    state["next_ok"] = True
    result = tdx_bridge.run_tdx_bridge("fund-flow", "SH", "600519", "0")
    assert result["source"] == "tdx"


def test_success_resets_failure_counter(monkeypatch):
    """成功重置计数：失败-成功-失败后仍未熔断。"""
    from chstockdata import tdx_bridge

    state = {"next_ok": False}

    def fake_run(command, **kwargs):
        return _ok_process() if state["next_ok"] else _failed_process()

    monkeypatch.setattr(tdx_bridge.subprocess, "run", fake_run)

    with pytest.raises(tdx_bridge.TdxBridgeUnavailable):
        tdx_bridge.run_tdx_bridge("fund-flow", "SH", "600519", "0")
    state["next_ok"] = True
    assert tdx_bridge.run_tdx_bridge("fund-flow", "SH", "600519", "0")["source"] == "tdx"

    state["next_ok"] = False
    with pytest.raises(tdx_bridge.TdxBridgeUnavailable) as first:
        tdx_bridge.run_tdx_bridge("fund-flow", "SH", "600519", "0")
    # 阈值默认为 2；失败-成功-失败只累计 1 次连续失败，仍是真实探测而非短路。
    assert first.value.category == "RuntimeError"


def test_cooldown_expiry_allows_probe_again(monkeypatch):
    """冷却期满后放行一次真实探测，成功即恢复。"""
    from chstockdata import tdx_bridge

    now = {"t": 0.0}

    def fake_monotonic():
        return now["t"]

    state = {"next_ok": False}

    def fake_run(command, **kwargs):
        return _ok_process() if state["next_ok"] else _failed_process()

    monkeypatch.setattr(tdx_bridge.time, "monotonic", fake_monotonic)
    monkeypatch.setattr(tdx_bridge.subprocess, "run", fake_run)

    for _ in range(tdx_bridge._FAILURE_THRESHOLD):
        with pytest.raises(tdx_bridge.TdxBridgeUnavailable):
            tdx_bridge.run_tdx_bridge("fund-flow", "SH", "600519", "0")

    now["t"] += tdx_bridge._COOLDOWN_SECONDS + 1
    state["next_ok"] = True
    assert tdx_bridge.run_tdx_bridge("fund-flow", "SH", "600519", "0")["source"] == "tdx"
