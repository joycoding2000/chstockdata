"""mootdx 服务器选取（上游 #90）。

现实里存在大量"TCP 三次握手成功、通达信协议握手立刻被 RST"的服务器。旧实现
只做 TCP 探测就把 client 钉进单例，于是之后每一次取数都失败降级、且永远不会
重选服务器。这些用例锁死修复后的三条行为：

1. TCP 通但取不到数的服务器必须被跳过，继续试下一台；
2. 全部失败后要抛错，并在冷却期内快速失败（不再逐台重探）；
3. 选中的服务器之后挂掉时，要弃用它，下次换一台。
"""

import threading
import time
from contextlib import contextmanager

import pytest

from chstockdata import a_stock


class FakeQuotesClient:
    """假的 mootdx client：可配置成"协议层直接炸"或"正常返回"。"""

    def __init__(self, ip, works: bool):
        self.ip = ip
        self.works = works
        self.calls = 0

    def bars(self, **kwargs):
        self.calls += 1
        if not self.works:
            raise ConnectionResetError("[Errno 54] Connection reset by peer")
        import pandas as pd

        return pd.DataFrame({"close": [1700.0]})


@pytest.fixture
def fake_tdx(monkeypatch, tmp_path):
    """把服务器表、TCP 探测、Quotes.factory 全部换成可控假件。"""
    import mootdx.quotes

    # P0 可靠性：负缓存已磁盘持久化。隔离到 tmp_path，既不让本文件用例读到
    # 真实 ~/.chstockdata 缓存（conftest 预热线程在真网故障时会写它），
    # 也不让用例把假件失败写进真实缓存。
    monkeypatch.setattr(
        a_stock,
        "_mootdx_unavailable_cache_file",
        lambda: str(tmp_path / "mootdx-unavailable.json"),
    )

    servers = [("1.1.1.1", 7709), ("2.2.2.2", 7709), ("3.3.3.3", 7709)]
    state = {
        "tcp_open": {ip for ip, _ in servers},  # TCP 端口开着的
        "protocol_ok": set(),                   # 协议层真能取数的
        "probe_calls": [],
        "clients": {},
    }

    monkeypatch.setattr(a_stock, "_TDX_SERVERS", servers)
    # Pin the candidate source as a whole: `_candidate_tdx_servers` otherwise
    # appends mootdx's real HQ_HOSTS table, and in some full-suite orderings
    # that real table reaches the TCP pre-filter / bare-factory fallback and
    # creates a genuine StdQuotes client (real network in unit tests).
    monkeypatch.setattr(a_stock, "_candidate_tdx_servers", lambda: list(servers))
    monkeypatch.setattr(a_stock, "_mootdx_client", None)
    monkeypatch.setattr(a_stock, "_mootdx_unavailable_until", 0.0)
    # A pre-existing daemon may be blocked in the old production lock while
    # probing real hosts. Unit cases own no shared socket, so give their fake
    # dataflow state a fresh lock instead of inheriting that unrelated wait.
    monkeypatch.setattr(a_stock, "_mootdx_call_lock", threading.RLock())
    monkeypatch.setattr(a_stock, "_mootdx_last_call", 0.0)
    # issues/023 P0 止血新增的探针间隔/调用节流默认会真实 sleep，测试里关掉保速度
    monkeypatch.setattr(a_stock, "_TDX_PROBE_GAP_S", 0.0)
    monkeypatch.setattr(a_stock, "_mootdx_outage_rounds", 0)
    # 有界重选状态（candidates/index/pending）也是进程全局：前序测试留下的
    # pending 队列会让本文件的用例吃到别人的候选表，表现为顺序敏感偶发。
    monkeypatch.setattr(a_stock, "_mootdx_reselect_pending", False)
    monkeypatch.setattr(a_stock, "_mootdx_reselect_candidates", ())
    monkeypatch.setattr(a_stock, "_mootdx_reselect_index", None)
    monkeypatch.setenv("TDX_MIN_INTERVAL", "0")

    def fake_probe(ip, port, timeout=2.0):
        state["probe_calls"].append(ip)
        return ip in state["tcp_open"]

    monkeypatch.setattr(a_stock, "_probe_tdx", fake_probe)

    class FakeQuotes:
        @staticmethod
        def factory(market="std", server=None, **kwargs):
            ip = server[0] if server else "bestip"
            client = FakeQuotesClient(ip, works=ip in state["protocol_ok"])
            state["clients"][ip] = client
            return client

    monkeypatch.setattr(mootdx.quotes, "Quotes", FakeQuotes)
    return state


def test_skips_server_that_accepts_tcp_but_fails_protocol(fake_tdx):
    """1.1.1.1 端口开着却取不到数 → 必须跳过它，选到真正可用的 2.2.2.2。"""
    fake_tdx["protocol_ok"] = {"2.2.2.2"}

    client = a_stock._get_mootdx_client()

    assert client.ip == "2.2.2.2"
    # 坏服务器被真实取数验证挡下来了，而不是被采纳
    assert fake_tdx["clients"]["1.1.1.1"].works is False


def test_selected_client_is_cached(fake_tdx):
    """选中之后要复用，不能每次调用都重新逐台探测。"""
    fake_tdx["protocol_ok"] = {"1.1.1.1"}

    first = a_stock._get_mootdx_client()
    probes_after_first = len(fake_tdx["probe_calls"])
    second = a_stock._get_mootdx_client()

    assert first is second
    assert len(fake_tdx["probe_calls"]) == probes_after_first


def test_all_servers_dead_raises_then_fails_fast(fake_tdx):
    """全挂 → 抛错；冷却期内第二次调用直接失败，不再重探。"""
    fake_tdx["protocol_ok"] = set()

    with pytest.raises(RuntimeError, match="通达信"):
        a_stock._get_mootdx_client()
    probes_after_first = len(fake_tdx["probe_calls"])
    assert probes_after_first >= len(fake_tdx["tcp_open"])

    with pytest.raises(RuntimeError, match="不再重探|不再重试"):
        a_stock._get_mootdx_client()
    # 快速失败：没有再打一遍服务器表
    assert len(fake_tdx["probe_calls"]) == probes_after_first


def test_tcp_unreachable_servers_are_not_probed_for_data(fake_tdx):
    """TCP 不通的直接跳过，不去建 client。"""
    fake_tdx["tcp_open"] = {"3.3.3.3"}
    fake_tdx["protocol_ok"] = {"3.3.3.3"}

    client = a_stock._get_mootdx_client()

    assert client.ip == "3.3.3.3"
    assert "1.1.1.1" not in fake_tdx["clients"]
    assert "2.2.2.2" not in fake_tdx["clients"]


def test_mootdx_call_discards_client_after_failure(fake_tdx):
    """选中的服务器后来挂了 → 弃用它，下一次换一台，而不是一直降级。"""
    # A daemon warmup from another test can write this process-global cache at
    # any time. This case owns client reselection, not negative-cache policy
    # (which has dedicated tests below), so isolate every selection attempt.
    original_get_client = a_stock._get_mootdx_client

    def get_client_without_external_negative_cache(*args, **kwargs):
        a_stock._mootdx_unavailable_until = 0.0
        return original_get_client(*args, **kwargs)

    # Keep this patch local to the test so the dedicated cooldown tests still
    # exercise the real production negative-cache branch.
    from pytest import MonkeyPatch
    patch = MonkeyPatch()
    patch.setattr(a_stock, "_get_mootdx_client", get_client_without_external_negative_cache)
    try:
        _assert_mootdx_call_discards_client_after_failure(fake_tdx)
    finally:
        patch.undo()


def _assert_mootdx_call_discards_client_after_failure(fake_tdx):
    """Core re-selection assertions, isolated from process-global cooldown."""
    fake_tdx["protocol_ok"] = {"1.1.1.1", "2.2.2.2"}

    a_stock._mootdx_call("bars", symbol="600519")
    assert a_stock._mootdx_client is not None
    assert a_stock._mootdx_client.ip == "1.1.1.1"
    probes_after_initial = len(fake_tdx["probe_calls"])

    # 服务器挂掉：当前 client 被弃用，并且本次调用只重选一次后重试。
    a_stock._mootdx_client.works = False
    fake_tdx["protocol_ok"] = {"2.2.2.2"}
    replacement = a_stock._mootdx_call("bars", symbol="600519")

    # 关键断言：坏 client 已被丢弃，当前调用落到还活着的那台。
    assert replacement is not None
    assert len(fake_tdx["probe_calls"]) == probes_after_initial
    probes_after_reselect = len(fake_tdx["probe_calls"])
    a_stock._mootdx_call("bars", symbol="600519")
    assert a_stock._mootdx_client.ip == "2.2.2.2"
    assert len(fake_tdx["probe_calls"]) == probes_after_reselect


def test_get_client_failure_does_not_clear_negative_cache(fake_tdx):
    """取 client 失败不该清掉负缓存，否则快速失败就失效了。"""
    fake_tdx["protocol_ok"] = set()

    with pytest.raises(RuntimeError):
        a_stock._mootdx_call("bars", symbol="600519")
    probes = len(fake_tdx["probe_calls"])

    with pytest.raises(RuntimeError):
        a_stock._mootdx_call("bars", symbol="600519")
    assert len(fake_tdx["probe_calls"]) == probes


# ---------------------------------------------------------------------------
# 协议层失败的真实形态：握手在 Quotes.factory 内部就炸，根本走不到取数验证。
# 只统计"取数失败"会让计数恒为 0，快速失败判断随之失效（实测踩过）。
# ---------------------------------------------------------------------------


@pytest.fixture
def handshake_fails(monkeypatch, tmp_path):
    """服务器 TCP 通，但 Quotes.factory 建连时握手被 RST —— 线上就是这个形态。"""
    import mootdx.quotes

    monkeypatch.setattr(
        a_stock,
        "_mootdx_unavailable_cache_file",
        lambda: str(tmp_path / "mootdx-unavailable.json"),
    )

    servers = [(f"10.0.0.{i}", 7709) for i in range(1, 9)]
    state = {"factory_calls": [], "bestip_used": False}

    monkeypatch.setattr(a_stock, "_TDX_SERVERS", servers)
    # 候选表 = 精选表 + mootdx 自带主机表；测试里只保留精选表，断言才可控
    monkeypatch.setattr(a_stock, "_candidate_tdx_servers", lambda: list(servers))
    monkeypatch.setattr(a_stock, "_mootdx_client", None)
    monkeypatch.setattr(a_stock, "_mootdx_unavailable_until", 0.0)
    # issues/023 P0 止血新增的探针间隔/调用节流默认会真实 sleep，测试里关掉保速度
    monkeypatch.setattr(a_stock, "_TDX_PROBE_GAP_S", 0.0)
    monkeypatch.setattr(a_stock, "_mootdx_outage_rounds", 0)
    # 有界重选状态（candidates/index/pending）也是进程全局：前序测试留下的
    # pending 队列会让本文件的用例吃到别人的候选表，表现为顺序敏感偶发。
    monkeypatch.setattr(a_stock, "_mootdx_reselect_pending", False)
    monkeypatch.setattr(a_stock, "_mootdx_reselect_candidates", ())
    monkeypatch.setattr(a_stock, "_mootdx_reselect_index", None)
    monkeypatch.setenv("TDX_MIN_INTERVAL", "0")
    monkeypatch.setattr(a_stock, "_probe_tdx", lambda ip, port, timeout=2.0: True)

    class FakeQuotes:
        @staticmethod
        def factory(market="std", server=None, **kwargs):
            if kwargs.get("bestip"):
                state["bestip_used"] = True
                raise ConnectionResetError("bestip 也连不上")
            state["factory_calls"].append(server[0] if server else "bare")
            raise ConnectionResetError("[Errno 54] Connection reset by peer")

    monkeypatch.setattr(mootdx.quotes, "Quotes", FakeQuotes)
    return state


def test_handshake_failure_counts_as_protocol_failure(handshake_fails):
    """握手期就炸的服务器要被算进协议失败（决定报错文案与是否跑 bestip）。

    ⚠️ 这里**必须把整张表试完**。曾经加过「连续 3 台失败就停手」，被 codex 指出：
    三台远端拒绝证明不了本地封了协议，列表靠后的服务器完全可能是好的，提前收手
    会让那台永远试不到、还顺手记 5 分钟负缓存。
    """
    with pytest.raises(RuntimeError, match="协议握手/取数被拒"):
        a_stock._get_mootdx_client()

    tried = [c for c in handshake_fails["factory_calls"] if c != "bare"]
    assert len(tried) == len(a_stock._TDX_SERVERS), (
        f"应当把整张服务器表试完，实际只试了 {len(tried)} 台"
    )


def test_later_working_server_is_still_found(handshake_fails, monkeypatch):
    """前几台协议失败不能妨碍后面那台可用服务器被选中（codex P2）。"""
    import mootdx.quotes
    import pandas as pd

    good_ip = a_stock._TDX_SERVERS[-1][0]

    class GoodClient:
        ip = good_ip

        def bars(self, **kwargs):
            return pd.DataFrame({"close": [1700.0]})

    class FakeQuotes:
        @staticmethod
        def factory(market="std", server=None, **kwargs):
            if server and server[0] == good_ip:
                return GoodClient()
            raise ConnectionResetError("[Errno 54] Connection reset by peer")

    monkeypatch.setattr(mootdx.quotes, "Quotes", FakeQuotes)

    assert a_stock._get_mootdx_client().ip == good_ip


def test_bestip_skipped_when_protocol_is_the_problem(handshake_fails):
    """bestip 会把内置主机表整个测速一遍（实测几分钟）。协议层被拦时它用的是
    同一套协议、同一批主机，不可能有别的结果，跑它只是让用户干等。"""
    with pytest.raises(RuntimeError):
        a_stock._get_mootdx_client()

    assert handshake_fails["bestip_used"] is False


def test_candidate_list_includes_mootdx_own_hosts():
    """候选表必须覆盖 mootdx 自带主机表，而不只是精选的那 10 台。

    只试精选表的话，它们恰好都不可用时会被判成"全网不可达"并记 5 分钟负缓存，
    而 mootdx 自带表里可能还有活着的主机（codex 复审指出）。
    """
    candidates = a_stock._candidate_tdx_servers()

    assert len(candidates) > len(a_stock._TDX_SERVERS)
    assert candidates[:len(a_stock._TDX_SERVERS)] == list(a_stock._TDX_SERVERS), (
        "实测精选的服务器应排在前面，让常见情况第一台就命中"
    )
    assert len(candidates) == len(set(candidates)), "候选表不该有重复"


def test_bestip_is_never_used(handshake_fails):
    """不再用 bestip：它要把整张表测速一遍（实测几分钟），而候选表已逐台验证过，
    覆盖面相当且每台都是"真取到数才算通过"。"""
    with pytest.raises(RuntimeError):
        a_stock._get_mootdx_client()

    assert handshake_fails["bestip_used"] is False


def test_probing_restores_mootdx_bestip_when_nothing_works(handshake_fails, monkeypatch):
    """探测不能把用户配好的服务器覆写掉（codex 第五轮）。

    mootdx 的 StdQuotes.__init__ 里有 `config.set('BESTIP', {'HQ': self.server})`
    ——每建一次带 server 的 client 都会持久化写入配置文件。逐台探测几十个候选等于
    一路覆写，最后留下的是最后一台**失败的**服务器，裸 factory 兜底（读 BESTIP）
    再也救不回来，还会连累同机上其它用 mootdx 的程序。
    """
    from mootdx import config as mootdx_config

    original = {"HQ": ["1.2.3.4", 7709], "EX": "", "GP": ""}
    store = {"BESTIP": {"HQ": "", "EX": "", "GP": ""}}   # 未 setup 时的模块默认空值
    setup_called = {"n": 0}

    def fake_setup():
        # 复刻真实语义：setup() 之后才把持久化的值读进来
        setup_called["n"] += 1
        store["BESTIP"] = dict(original)

    monkeypatch.setattr(mootdx_config, "setup", fake_setup)
    monkeypatch.setattr(mootdx_config, "get", lambda k: store.get(k))
    monkeypatch.setattr(mootdx_config, "set", lambda k, v: store.__setitem__(k, v))

    with pytest.raises(RuntimeError):
        a_stock._get_mootdx_client()

    assert setup_called["n"] >= 1, (
        "必须先 setup() 再快照——新进程里 config.get('BESTIP') 是模块默认空值，"
        "快照到空值的话'还原'反而会把用户真实配置抹掉"
    )
    assert store["BESTIP"] == original, "全部探测失败后应把 BESTIP 还原成原样"


def test_bestip_kept_when_a_server_works(fake_tdx, monkeypatch):
    """选出可用服务器时**不能**还原——那次覆写正是我们想要的结果。"""
    from mootdx import config as mootdx_config

    store = {"BESTIP": {"HQ": "", "EX": "", "GP": ""}}
    persisted = {"HQ": ["1.2.3.4", 7709], "EX": "", "GP": ""}
    monkeypatch.setattr(mootdx_config, "setup", lambda: store.__setitem__("BESTIP", dict(persisted)))
    monkeypatch.setattr(mootdx_config, "get", lambda k: store.get(k))
    monkeypatch.setattr(mootdx_config, "set", lambda k, v: store.__setitem__(k, v))

    fake_tdx["protocol_ok"] = {"2.2.2.2"}
    # 模拟 mootdx：建 client 时写 BESTIP
    import mootdx.quotes as mq
    real = mq.Quotes.factory

    class Wrapped:
        @staticmethod
        def factory(market="std", server=None, **kw):
            if server:
                store["BESTIP"] = {"HQ": list(server), "EX": "", "GP": ""}
            return real(market=market, server=server, **kw)

    monkeypatch.setattr(mq, "Quotes", Wrapped)

    client = a_stock._get_mootdx_client()

    assert client.ip == "2.2.2.2"
    assert store["BESTIP"]["HQ"] == ["2.2.2.2", 7709], (
        "选中的服务器应当留在配置里，而不是被还原掉"
    )


def test_bestip_restored_even_if_probing_raises(handshake_fails, monkeypatch):
    """探测中途抛异常也要还原——手动调还原函数时这条路径最容易漏。"""
    from mootdx import config as mootdx_config

    persisted = {"HQ": ["1.2.3.4", 7709], "EX": "", "GP": ""}
    store = {"BESTIP": {"HQ": "", "EX": "", "GP": ""}}
    monkeypatch.setattr(mootdx_config, "setup", lambda: store.__setitem__("BESTIP", dict(persisted)))
    monkeypatch.setattr(mootdx_config, "get", lambda k: store.get(k))
    monkeypatch.setattr(mootdx_config, "set", lambda k, v: store.__setitem__(k, v))
    monkeypatch.setattr(a_stock, "_reachable_tdx_servers",
                        lambda servers, timeout=2.0: (_ for _ in ()).throw(RuntimeError("boom")))

    with pytest.raises(RuntimeError, match="boom"):
        a_stock._get_mootdx_client()

    assert store["BESTIP"] == persisted, "异常路径也必须还原"


def test_reset_without_candidates_preserves_negative_cache(fake_tdx):
    """全表不可用后 reset 不能清掉负缓存，否则核心工具会重复全表扫描
    （服务器实测：get_stock_data 预算被重复选服耗尽）。"""
    fake_tdx["protocol_ok"] = set()

    with pytest.raises(RuntimeError):
        a_stock._get_mootdx_client()  # 全表失败 -> 负缓存生效
    assert a_stock._mootdx_unavailable_until > 0

    # 客户端调用失败路径会调 reset_mootdx_client()；无候选可重选时必须保留负缓存。
    a_stock.reset_mootdx_client()
    assert a_stock._mootdx_unavailable_until > 0

    probes = len(fake_tdx["probe_calls"])
    with pytest.raises(RuntimeError, match="不再重探|不再重试"):
        a_stock._get_mootdx_client()  # 仍走快速失败，不重新扫表
    assert len(fake_tdx["probe_calls"]) == probes


def test_reset_with_candidates_clears_negative_cache_for_bounded_reselect(fake_tdx, monkeypatch):
    """有 readiness 候选时 reset 才清负缓存，允许有界重选（spec §7）。"""
    fake_tdx["protocol_ok"] = set()
    with pytest.raises(RuntimeError):
        a_stock._get_mootdx_client()
    assert a_stock._mootdx_unavailable_until > 0

    # 模拟 readiness 阶段捕获过候选。⚠️ 必须经 monkeypatch：直接赋值会把
    # pending=True/候选表泄漏到后续测试（实测让 test_tdx_request_hygiene 的
    # 全表失败用例误入 bounded-reselect 路径并对字符串解包炸掉）。
    monkeypatch.setattr(
        a_stock, "_mootdx_reselect_candidates", list(fake_tdx["tcp_open"])
    )
    monkeypatch.setattr(a_stock, "_mootdx_reselect_index", 0)
    # reset(preserve=True) 会把 pending 置 True——先经 monkeypatch 声明前置值，
    # 测试结束自动还原，避免 True 泄漏给后续测试。
    monkeypatch.setattr(a_stock, "_mootdx_reselect_pending", False)
    a_stock.reset_mootdx_client(preserve_candidates=True)
    assert a_stock._mootdx_unavailable_until == 0.0
    assert a_stock._mootdx_reselect_pending is True


# ── 负缓存磁盘持久化（2026-09-11 数据层可靠性 P0）─────────────────────────────
# 冷启动进程（审计/CLI/重启后的 worker）不再在工具预算内重付 ~100s 全表探测：
# 全表失败落盘，新进程入口命中即快速失败让新浪兜底接管；成功选中清盘。


def test_full_table_failure_persists_negative_cache(fake_tdx, tmp_path, monkeypatch):
    import json
    import time

    cache_file = tmp_path / "mootdx-unavailable.json"
    monkeypatch.setattr(
        a_stock, "_mootdx_unavailable_cache_file", lambda: str(cache_file)
    )
    fake_tdx["protocol_ok"] = set()

    with pytest.raises(RuntimeError, match="通达信"):
        a_stock._get_mootdx_client()

    assert cache_file.exists()
    payload = json.loads(cache_file.read_text(encoding="utf-8"))
    assert payload["until"] > time.time()
    assert payload["rounds"] >= 1
    assert payload["reason"]


def test_disk_negative_cache_fast_fails_without_probing(
    fake_tdx, tmp_path, monkeypatch
):
    import json
    import time

    cache_file = tmp_path / "mootdx-unavailable.json"
    monkeypatch.setattr(
        a_stock, "_mootdx_unavailable_cache_file", lambda: str(cache_file)
    )
    cache_file.write_text(
        json.dumps({"until": time.time() + 3600, "rounds": 3, "reason": "test"}),
        encoding="utf-8",
    )

    def _forbidden(*args, **kwargs):
        raise AssertionError("disk negative-cache hit must not probe servers")

    monkeypatch.setattr(a_stock, "_probe_tdx", _forbidden)
    monkeypatch.setattr(a_stock, "_candidate_tdx_servers", _forbidden)
    monkeypatch.setattr(a_stock, "_mootdx_client", None)
    monkeypatch.setattr(a_stock, "_mootdx_unavailable_until", 0.0)
    monkeypatch.setattr(a_stock, "_mootdx_outage_rounds", 0)

    with pytest.raises(RuntimeError, match="不再重试"):
        a_stock._get_mootdx_client()
    # 退避档位从磁盘延续，跨进程不降级
    assert a_stock._mootdx_outage_rounds == 3


def test_successful_selection_clears_disk_negative_cache(
    fake_tdx, tmp_path, monkeypatch
):
    import json
    import time

    cache_file = tmp_path / "mootdx-unavailable.json"
    monkeypatch.setattr(
        a_stock, "_mootdx_unavailable_cache_file", lambda: str(cache_file)
    )
    cache_file.write_text(
        json.dumps({"until": time.time() - 1, "rounds": 2, "reason": "expired"}),
        encoding="utf-8",
    )
    fake_tdx["protocol_ok"] = {"1.1.1.1"}

    client = a_stock._get_mootdx_client()

    assert client.ip == "1.1.1.1"
    assert not cache_file.exists()


def test_corrupt_disk_cache_is_ignored(fake_tdx, tmp_path, monkeypatch):
    import json
    import time

    cache_file = tmp_path / "mootdx-unavailable.json"
    monkeypatch.setattr(
        a_stock, "_mootdx_unavailable_cache_file", lambda: str(cache_file)
    )
    cache_file.write_text("{not json", encoding="utf-8")
    fake_tdx["protocol_ok"] = set()

    # 损坏文件不得崩溃，也不得误判为"缓存命中"：走正常全表探测并失败
    with pytest.raises(RuntimeError, match="通达信"):
        a_stock._get_mootdx_client()

    payload = json.loads(cache_file.read_text(encoding="utf-8"))
    assert payload["until"] > time.time()


# ── DEC-P3-19 P1：工具调用上下文内的探测短预算（2026-09-12）─────────────────
# 服务器实测：全表选服 ~100s，会在 get_stock_data 的 105s 工具预算内被重付，
# 饿死新浪兜底。工具上下文内改为短预算（默认 6s）：超预算即抛、备用源接管；
# worker warmup / 库调用没有该上下文，保持全表选优语义。


@contextmanager
def _tool_context():
    # Host-simulation: install a source-execution context via the package
    # hook, mirroring what a host (TradingAgents) does inside one tool call.
    import chstockdata.source_context as _sc

    _sc.install(get_source_execution_context=lambda: object())
    try:
        yield
    finally:
        _sc.reset()


def test_tool_context_probe_budget_aborts_before_server_verification(
    fake_tdx, tmp_path, monkeypatch
):
    """工具上下文里探测超预算 → 抛错、不建 client、不写全表负缓存。"""
    monkeypatch.setattr(a_stock, "_TOOL_CONTEXT_PROBE_BUDGET_S", 0.01)

    def slow_probe(ip, port, timeout=2.0):
        fake_tdx["probe_calls"].append(ip)
        time.sleep(0.05)
        return True

    monkeypatch.setattr(a_stock, "_probe_tdx", slow_probe)
    fake_tdx["protocol_ok"] = {"1.1.1.1"}  # 健康服务器存在，但预算先烧尽

    with _tool_context():
        with pytest.raises(RuntimeError, match="工具调用预算"):
            a_stock._get_mootdx_client()

    # 预算烧尽后不得再 factory / 取数验证
    assert fake_tdx["clients"] == {}
    # 被截断的探测不得记成"全表不可用"（内存与磁盘都不写）
    assert a_stock._mootdx_unavailable_until == 0.0
    assert not (tmp_path / "mootdx-unavailable.json").exists()


def test_tool_context_probe_selects_healthy_server_within_budget(fake_tdx):
    """预算内的正常选服（含回退到第二台）不受影响。"""
    fake_tdx["protocol_ok"] = {"2.2.2.2"}

    with _tool_context():
        client = a_stock._get_mootdx_client()

    assert client.ip == "2.2.2.2"


def test_tool_context_fast_full_failure_still_persists_negative_cache(
    fake_tdx, tmp_path, monkeypatch
):
    """快速试完全表仍属"完成态"失败：负缓存照常写入，预算只截断慢探测。"""
    cache_file = tmp_path / "mootdx-unavailable.json"
    monkeypatch.setattr(
        a_stock, "_mootdx_unavailable_cache_file", lambda: str(cache_file)
    )
    fake_tdx["protocol_ok"] = set()

    with _tool_context():
        with pytest.raises(RuntimeError, match="通达信"):
            a_stock._get_mootdx_client()

    assert cache_file.exists()
