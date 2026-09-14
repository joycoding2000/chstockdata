"""issues/023 P0 止血：TDX 请求形态治理回归测试。

锁定六条止血行为（对应 issues/023「P0 止血实施稿」）：
1. 桥：缓存 best_host 优先（`cls()` 单台直连），不触发全池 ping；
2. 桥：全池选优（from_best_host）被 stamp 文件限频——选优窗口内第二次失败直接上抛；
3. 桥：行业排名 top/bottom 共用一个连接（原来各连一次）；
4. 主进程桥调用：相邻 launch 补足 TDX_BRIDGE_MIN_INTERVAL；并发调用被串行化；
5. mootdx：_mootdx_call 串行锁 + TDX_MIN_INTERVAL 节流；负缓存指数退避；
   非交易时段全表失败直接用最长档；候选逐台验证间有最小间隔；
6. 名称映射：当日磁盘缓存命中时不再走网络全市场拉取。
"""

from __future__ import annotations

import importlib.util
import threading
import time as _time
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from chstockdata import a_stock


import chstockdata.tdx_bridge as _tdx_bridge_mod
BRIDGE_PATH = Path(_tdx_bridge_mod.__file__).with_name("_easy_tdx_bridge.py")
_MARKET = SimpleNamespace(SH=1, SZ=0, BJ=2)


def _load_bridge():
    spec = importlib.util.spec_from_file_location("easy_tdx_bridge_hygiene", BRIDGE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# 桥（scripts/easy_tdx_bridge.py）：缓存优先 / 选优限频 / 单连接复用
# ---------------------------------------------------------------------------


class _CountingClient:
    def __init__(self, cached_ok: bool = True):
        self.cached_ok = cached_ok
        self.refresh_mode = False
        self.connected = 0
        self.closed = 0

    def connect(self):
        self.connected += 1
        if not self.cached_ok and not self.refresh_mode:
            raise ConnectionError("cached best_host down")

    def close(self):
        self.closed += 1

    def get_capital_flow(self, market, code):
        return pd.DataFrame([{"main_net": 1.0}])

    def get_board_ranking(self, **kwargs):
        return pd.DataFrame([{"name": "农业", "change_pct": 1.0}])

    def get_history_fund_flow(self, market, code, start, count):
        return pd.DataFrame([{"day": 1}])


def test_bridge_prefers_cached_best_host(monkeypatch):
    """正常路径只连缓存 best_host 一台，绝不触发全池 ping（issues/023 R1）。"""
    bridge = _load_bridge()
    flags: list[bool] = []

    def factory(refresh: bool = False):
        flags.append(refresh)
        return _CountingClient()

    monkeypatch.setattr(
        bridge, "_load_clients", lambda: (factory, factory, _MARKET)
    )

    payload = bridge.execute(["fund-flow", "SH", "600519", "0"])

    assert payload["source"] == "tdx"
    assert flags == [False], "正常路径不得触发 from_best_host 全池扫描"


def test_bridge_full_pool_refresh_is_rate_limited(monkeypatch, tmp_path):
    """缓存 host 连不上时允许一次全池选优并落 stamp；窗口内再次失败直接上抛。"""
    monkeypatch.setenv("EASY_TDX_CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("TDX_BEST_HOST_REFRESH_INTERVAL_S", "3600")
    bridge = _load_bridge()
    flags: list[bool] = []

    def factory(refresh: bool = False):
        client = _CountingClient(cached_ok=False)
        client.refresh_mode = refresh
        flags.append(refresh)
        return client

    monkeypatch.setattr(
        bridge, "_load_clients", lambda: (factory, factory, _MARKET)
    )

    # 第一次：缓存失败 → 允许一次选优（refresh=True）→ 成功
    payload = bridge.execute(["fund-flow", "SH", "600519", "0"])
    assert payload["source"] == "tdx"
    assert flags == [False, True]
    assert (tmp_path / "besthost-refresh.stamp").exists()

    # 第二次：仍在选优窗口内 → 不再扫描，缓存失败直接上抛
    with pytest.raises(ConnectionError):
        bridge.execute(["fund-flow", "SH", "600519", "0"])
    assert flags == [False, True, False]


def test_bridge_industry_reuses_single_connection(monkeypatch):
    """行业排名 top+bottom 共用一个 mac 连接（issues/023 P0-2）。"""
    bridge = _load_bridge()
    client = _CountingClient()
    ranking_calls: list[dict] = []

    def factory(refresh: bool = False):
        assert refresh is False
        return client

    real_ranking = client.get_board_ranking

    def spy_ranking(**kwargs):
        ranking_calls.append(kwargs)
        return real_ranking(**kwargs)

    client.get_board_ranking = spy_ranking
    monkeypatch.setattr(
        bridge, "_load_clients", lambda: (factory, factory, _MARKET)
    )

    payload = bridge.execute(["industry-ranking", "3", "2"])

    assert payload["source"] == "tdx"
    assert client.connected == 1, "top/bottom 应共用一个连接"
    assert client.closed == 1
    assert len(ranking_calls) == 2, "top 与 bottom 各查一次排行"
    assert len(payload["top"]) == 1 and len(payload["bottom"]) == 1


# ---------------------------------------------------------------------------
# 主进程桥调用（tdx_bridge.py）：间隔补足 + 串行化
# ---------------------------------------------------------------------------


def _ok_process():
    from subprocess import CompletedProcess

    import json

    return CompletedProcess(
        [],
        0,
        stdout=json.dumps({"source": "tdx", "current": [{"main_net": 1.0}]}),
        stderr="",
    )


@pytest.fixture(autouse=True)
def _clean_bridge_state(monkeypatch):
    from chstockdata import tdx_bridge

    monkeypatch.setenv("TDX_BRIDGE_MIN_INTERVAL", "0")
    tdx_bridge._reset_health()
    tdx_bridge._last_bridge_launch = float("-inf")
    yield
    tdx_bridge._reset_health()
    tdx_bridge._last_bridge_launch = float("-inf")


def test_bridge_launch_interval_enforced(monkeypatch):
    """相邻桥子进程 launch 之间补足 TDX_BRIDGE_MIN_INTERVAL（默认 1s）。"""
    from chstockdata import tdx_bridge

    monkeypatch.setenv("TDX_BRIDGE_MIN_INTERVAL", "5")
    # 常数时钟：elapsed 恒为 0 → 第二次调用必须补足完整间隔
    monkeypatch.setattr(tdx_bridge.time, "monotonic", lambda: 100.0)
    sleeps: list[float] = []
    monkeypatch.setattr(tdx_bridge.time, "sleep", lambda s: sleeps.append(s))
    monkeypatch.setattr(
        tdx_bridge.subprocess, "run", lambda command, **kw: _ok_process()
    )

    tdx_bridge.run_tdx_bridge("fund-flow", "SH", "600519", "0")
    assert sleeps == [], "首次 launch（-inf 基线）不应等待"

    tdx_bridge.run_tdx_bridge("fund-flow", "SH", "600519", "0")
    assert sleeps == [5.0], "相邻 launch 应补足最小间隔"


def test_bridge_calls_are_serialized(monkeypatch):
    """并发桥调用排队执行：任何时刻至多一个子进程在跑（不再叠加扫描突发）。"""
    from chstockdata import tdx_bridge

    active = {"n": 0}
    max_active = {"n": 0}

    def fake_run(command, **kwargs):
        active["n"] += 1
        max_active["n"] = max(max_active["n"], active["n"])
        _time.sleep(0.05)
        active["n"] -= 1
        return _ok_process()

    monkeypatch.setattr(tdx_bridge.subprocess, "run", fake_run)

    threads = [
        threading.Thread(
            target=tdx_bridge.run_tdx_bridge,
            args=("fund-flow", "SH", "600519", "0"),
        )
        for _ in range(3)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
        assert not t.is_alive(), "桥调用线程应在超时前完成"

    assert max_active["n"] == 1, "桥子进程调用必须串行"


# ---------------------------------------------------------------------------
# mootdx（a_stock.py）：节流 / 串行锁 / 指数退避 / 交易时段 / 探测间隔
# ---------------------------------------------------------------------------


class _FakeMootdxClient:
    def bars(self, **kwargs):
        return pd.DataFrame({"close": [1700.0]})


@pytest.fixture
def clean_mootdx_state(monkeypatch, tmp_path):
    monkeypatch.setenv("TDX_MIN_INTERVAL", "0")
    # P0 可靠性：负缓存已磁盘持久化，隔离到 tmp_path（理由同 fake_tdx）。
    monkeypatch.setattr(
        a_stock,
        "_mootdx_unavailable_cache_file",
        lambda: str(tmp_path / "mootdx-unavailable.json"),
    )
    saved = (
        a_stock._mootdx_client,
        a_stock._mootdx_unavailable_until,
        a_stock._mootdx_outage_rounds,
        a_stock._mootdx_last_call,
        a_stock._mootdx_reselect_pending,
        a_stock._mootdx_reselect_candidates,
        a_stock._mootdx_reselect_index,
    )
    a_stock._mootdx_client = None
    a_stock._mootdx_unavailable_until = 0.0
    a_stock._mootdx_outage_rounds = 0
    a_stock._mootdx_last_call = float("-inf")
    # 防御性重置 reselect 三件套：上游测试若有 pending/候选残留，全表失败用例
    # 会误入 bounded-reselect 分支而非全表扫描路径（实测踩过）。
    a_stock._mootdx_reselect_pending = False
    a_stock._mootdx_reselect_candidates = ()
    a_stock._mootdx_reselect_index = None
    yield
    (
        a_stock._mootdx_client,
        a_stock._mootdx_unavailable_until,
        a_stock._mootdx_outage_rounds,
        a_stock._mootdx_last_call,
        a_stock._mootdx_reselect_pending,
        a_stock._mootdx_reselect_candidates,
        a_stock._mootdx_reselect_index,
    ) = saved


def test_mootdx_call_throttled_by_min_interval(monkeypatch, clean_mootdx_state):
    """相邻 mootdx 调用补足 TDX_MIN_INTERVAL；首次（-inf 基线）不等。"""
    monkeypatch.setenv("TDX_MIN_INTERVAL", "5")
    a_stock._mootdx_client = _FakeMootdxClient()
    sleeps: list[float] = []
    monkeypatch.setattr(a_stock.time, "sleep", lambda s: sleeps.append(s))

    a_stock._mootdx_call("bars", symbol="600519")
    assert sleeps == []

    a_stock._mootdx_call("bars", symbol="600519")
    assert len(sleeps) == 1 and 0 < sleeps[0] <= 5.0


def test_mootdx_call_is_serialized(clean_mootdx_state):
    """持锁期间其他线程的 mootdx 调用必须阻塞等待。"""
    a_stock._mootdx_client = _FakeMootdxClient()
    done = {"ok": False}

    a_stock._mootdx_call_lock.acquire()
    try:
        worker = threading.Thread(
            target=lambda: (
                a_stock._mootdx_call("bars", symbol="600519"),
                done.__setitem__("ok", True),
            )
        )
        worker.start()
        worker.join(timeout=0.3)
        assert not done["ok"], "锁被占用时 mootdx 调用应阻塞"
    finally:
        a_stock._mootdx_call_lock.release()
    worker.join(timeout=5)
    assert done["ok"], "释放锁后调用应完成"


def _make_all_servers_dead(monkeypatch, servers):
    """全表协议失败的最小假件（TCP 全通、协议全拒）。"""
    import mootdx.quotes as mq

    monkeypatch.setattr(a_stock, "_TDX_SERVERS", servers)
    monkeypatch.setattr(a_stock, "_candidate_tdx_servers", lambda: list(servers))
    monkeypatch.setattr(a_stock, "_probe_tdx", lambda ip, port, timeout=2.0: True)
    monkeypatch.setattr(a_stock, "_TDX_PROBE_GAP_S", 0.0)

    class DeadQuotes:
        @staticmethod
        def factory(market="std", server=None, **kwargs):
            raise ConnectionResetError("[Errno 54] Connection reset by peer")

    monkeypatch.setattr(mq, "Quotes", DeadQuotes)


def test_negative_cache_backoff_escalates(monkeypatch, clean_mootdx_state):
    """连续全表失败：负缓存窗口按 300→1800→…逐级拉长。"""
    _make_all_servers_dead(
        monkeypatch, [("1.1.1.1", 7709), ("2.2.2.2", 7709), ("3.3.3.3", 7709)]
    )
    monkeypatch.setattr(a_stock, "_tdx_probe_window_open", lambda: True)

    with pytest.raises(RuntimeError):
        a_stock._get_mootdx_client()
    assert a_stock._mootdx_outage_rounds == 1
    window_1 = a_stock._mootdx_unavailable_until - _time.time()
    assert abs(window_1 - 300.0) < 60.0

    # 模拟负缓存过期后再探一轮：内存窗口与磁盘持久化窗口都要过期
    # （P0 可靠性：新进程必须等磁盘窗口过期才会重新探测，这正是设计意图）
    a_stock._mootdx_unavailable_until = 0.0
    import os as _os

    _os.remove(a_stock._mootdx_unavailable_cache_file())
    with pytest.raises(RuntimeError):
        a_stock._get_mootdx_client()
    assert a_stock._mootdx_outage_rounds == 2
    window_2 = a_stock._mootdx_unavailable_until - _time.time()
    assert abs(window_2 - 1800.0) < 60.0, "第二轮失败应升级到 30 分钟档"


def test_offhours_failure_uses_longest_backoff(monkeypatch, clean_mootdx_state):
    """非交易时段（周一至五 09:00–15:30 之外）全表失败直接用最长档。"""
    _make_all_servers_dead(
        monkeypatch, [("1.1.1.1", 7709), ("2.2.2.2", 7709)]
    )
    monkeypatch.setattr(a_stock, "_tdx_probe_window_open", lambda: False)

    with pytest.raises(RuntimeError):
        a_stock._get_mootdx_client()
    window = a_stock._mootdx_unavailable_until - _time.time()
    assert abs(window - 21600.0) < 60.0, "休市时段应直接用 6 小时档"


def test_probe_gap_between_candidates(monkeypatch, clean_mootdx_state):
    """候选逐台验证之间留最小间隔（把连发扫描摊成慢速敲门）。"""
    _make_all_servers_dead(
        monkeypatch, [("1.1.1.1", 7709), ("2.2.2.2", 7709), ("3.3.3.3", 7709)]
    )
    monkeypatch.setattr(a_stock, "_TDX_PROBE_GAP_S", 0.25)
    monkeypatch.setattr(a_stock, "_tdx_probe_window_open", lambda: True)
    sleeps: list[float] = []
    monkeypatch.setattr(a_stock.time, "sleep", lambda s: sleeps.append(s))

    with pytest.raises(RuntimeError):
        a_stock._get_mootdx_client()

    assert sleeps.count(0.25) == 2, "3 台候选之间应有 2 次间隔（首台前不等待）"


# ---------------------------------------------------------------------------
# 名称映射磁盘日缓存（a_stock.py）
# ---------------------------------------------------------------------------


def test_name_code_map_disk_cache_roundtrip(monkeypatch, tmp_path):
    """当日磁盘缓存命中时不再走 mootdx 全市场拉取。"""
    from chstockdata import config as dataflow_config

    monkeypatch.setattr(
        dataflow_config, "get_config", lambda: {"data_cache_dir": str(tmp_path)}
    )
    saved = (a_stock._name_to_code, a_stock._code_to_name)
    try:
        a_stock._name_to_code = None
        a_stock._code_to_name = None

        frames = {
            0: pd.DataFrame([{"code": "000001", "name": "平安银行"}]),
            1: pd.DataFrame([{"code": "600519", "name": "贵州茅台"}]),
        }
        calls = {"n": 0}

        def fake_mootdx_call(method, **kwargs):
            calls["n"] += 1
            return frames[kwargs["market"]]

        monkeypatch.setattr(a_stock, "_mootdx_call", fake_mootdx_call)

        n2c, _ = a_stock._build_name_code_map()
        assert calls["n"] == 2
        assert n2c["贵州茅台"] == "600519"
        assert (tmp_path / "name-code-map.json").exists()

        # 模拟新进程：清空内存缓存 → 磁盘当日命中，不再发起网络请求
        a_stock._name_to_code = None
        a_stock._code_to_name = None
        n2c2, _ = a_stock._build_name_code_map()
        assert calls["n"] == 2, "磁盘缓存命中后不得再走网络"
        assert n2c2["平安银行"] == "000001"

        # 隔日缓存失效：回网络重建
        import json as _json

        stale = {"date": "2000-01-01", "pairs": [["旧名称", "000000"]]}
        with open(tmp_path / "name-code-map.json", "w", encoding="utf-8") as fh:
            _json.dump(stale, fh, ensure_ascii=False)
        a_stock._name_to_code = None
        a_stock._code_to_name = None
        n2c3, _ = a_stock._build_name_code_map()
        assert calls["n"] == 4, "隔日缓存应失效并回网络"
        assert n2c3["贵州茅台"] == "600519"
    finally:
        a_stock._name_to_code, a_stock._code_to_name = saved
