"""A-stock (China mainland) data vendor for TradingAgents.

Zero third-party data dependency (no akshare). All sources are direct HTTP APIs
or mootdx TCP.

Data sources:
- mootdx (TCP 7709): OHLCV K-lines, financial snapshots, F10 text
- Tencent Finance (HTTP GBK): realtime quotes (primary), PE/PB/market cap/turnover
- 通达信 easy-tdx (isolated TCP bridge): L1 fund-flow reconstruction, industry ranking
- 东方财富 datacenter/F10/search (direct HTTP): dragon-tiger, lockup, holders, concept blocks, news
- 新浪财经 (direct HTTP): realtime quote fallback, K-line fallback, daily fund flow, financial statements
- 同花顺 (direct HTTP): consensus EPS, hot stocks, northbound capital flow
- 财联社 (direct HTTP): global news wire
"""

from __future__ import annotations

from typing import Annotated, Any, Mapping
from datetime import date, datetime, timezone, timedelta
from dateutil.relativedelta import relativedelta
import contextlib
import hashlib
import json as _json
import os
import logging
import io
import math
import random
import re as _re
import socket
import sqlite3 as _sqlite3
import time
import threading
import uuid
from urllib.parse import urlsplit

import pandas as pd
import requests as _requests

from .utils import safe_ticker_component
from .vendor_errors import VendorNetworkError
from .point_in_time import (
    POINT_IN_TIME_LIMITED_MARKER,
    filter_financial_records,
    is_historical_analysis,
    point_in_time_unavailable_message,
)
from .tdx_bridge import (
    TdxBridgeUnavailable,
    get_tdx_belong_board as _get_tdx_belong_board,
    get_tdx_concept_ranking as _get_tdx_concept_ranking,
    get_tdx_fund_flow as _get_tdx_fund_flow,
    get_tdx_industry_ranking as _get_tdx_industry_ranking,
    market_for_code as _tdx_market_for_code,
)
from .policy_news_models import PolicyTargetContext
from .policy_news_registry import (
    exchange_for_ticker,
    normalize_province,
    route_industry_authorities,
)

logger = logging.getLogger(__name__)


# A 股市场时区。判"今天"必须按市场所在地算，不能用主机本地时区——
# 主机在 UTC+9 以东（如新西兰 UTC+13）时，当地已过零点而上海还在前一天，
# 当天的分析会被判成"复盘历史"；反过来西半球也会把已过去的交易日当成"今天"。
_MARKET_TZ = timezone(timedelta(hours=8))


def _today() -> date:
    """A 股市场当前日期（Asia/Shanghai），与主机时区无关。

    Indirection keeps current-date point-in-time behavior testable.
    """
    return datetime.now(_MARKET_TZ).date()


# ---------------------------------------------------------------------------
# Helpers: ticker format & market detection
# ---------------------------------------------------------------------------

def _get_prefix(code: str) -> str:
    """6-digit A-stock code -> market prefix for Tencent/Sina/Eastmoney APIs.

    市场判定统一委托 tdx_bridge.market_for_code（北交所 920 号段先于 9 判断；
    4x/8x 为北交所老号段），避免两份路由规则漂移。
    移植自上游 a-stock-data v3.5.1（920 号段误判为沪市的修复）。
    """
    return _tdx_market_for_code(code).lower()


def _reject_non_a_share(original: str, code: str) -> None:
    """港股/美股代码走到 A 股数据层时当场报错，而不是拿去查 A 股（#43）。

    A 股代码恒为 6 位数字。港股是 4~5 位（`00700`）或带 `.HK` 后缀，美股是字母。
    这些代码此前会被**原样放行**，然后拿去问 mootdx / 腾讯 / 东财——而这些源对
    不存在的代码往往不报错，只返回空值或僵尸报价。于是模型会拿着一份看起来正常、
    实际属于别的市场或根本不存在的数据写完整篇报告，报告里完全看不出来。
    """
    if code.isdigit() and len(code) == 6:
        return
    upper = original.strip().upper()
    if upper.endswith(".HK") or (code.isdigit() and len(code) in (4, 5)):
        raise ValueError(
            f"'{original}' 是港股代码。本数据层只支持 A 股（6 位数字代码，"
            f"如 600519 / 000001）。"
        )
    if code and not code.isdigit():
        raise ValueError(
            f"'{original}' 不是 A 股代码。本数据层只支持 A 股 6 位数字代码"
            f"（如 600519）；美股/港股请走其它数据层。"
        )
    raise ValueError(
        f"'{original}' 不是有效的 A 股代码：A 股代码恒为 6 位数字（如 600519），"
        f"这里解析出的是 '{code}'。"
    )


def _normalize_ticker(symbol: str) -> str:
    """Strip exchange prefix/suffix, return pure 6-digit code.

    Handles: '688017', 'SH688017', '688017.SH', 'sh688017'

    非 A 股代码（港股 `00700` / `0700.HK`、美股 `AAPL`）会直接报错，不再原样
    放行去查 A 股数据源（#43）。
    """
    s = symbol.strip().upper()
    # Remove .SH / .SZ / .BJ suffix
    for suffix in (".SH", ".SZ", ".BJ"):
        if s.endswith(suffix):
            s = s[: -len(suffix)]
            break
    # Remove SH / SZ / BJ prefix
    for prefix in ("SH", "SZ", "BJ"):
        if s.startswith(prefix):
            s = s[len(prefix) :]
            break
    code = safe_ticker_component(s)
    _reject_non_a_share(symbol, code)
    return code


# ---------------------------------------------------------------------------
# Stock name <-> code mapping (cached)
# ---------------------------------------------------------------------------

_name_to_code: dict[str, str] | None = None
_code_to_name: dict[str, str] | None = None
_name_code_map_lock = threading.Lock()
_name_map_warmup_started = False


def name_code_map_ready() -> bool:
    """映射是否已构建完成（纯内存检查，绝不触发网络）。"""
    return _name_to_code is not None


def ensure_name_code_map_warmup() -> None:
    """在后台线程预热名称映射（幂等，失败无害）。

    首次构建要下载 mootdx 两张全市场表；mootdx 全挂时还得先走完整服务器探测
    （实测最坏 ~70s）。UI 渲染线程绝不能同步等它——渲染被阻塞时 Streamlit
    本次运行无法正常收尾，旧界面元素会以孤儿形式残留（2026-08-30 首页残留
    问题的根因）。渲染路径用 ``name_code_map_ready()`` 判断，未就绪就跳过。
    """
    global _name_map_warmup_started
    if _name_map_warmup_started or _name_to_code is not None:
        return
    _name_map_warmup_started = True

    def _warm() -> None:
        try:
            _build_name_code_map()
        except Exception as exc:
            logger.info("name-code map warmup skipped (%s)", type(exc).__name__)

    threading.Thread(target=_warm, name="ta-name-map-warmup", daemon=True).start()


def _name_map_cache_file() -> str:
    """名称映射磁盘日缓存路径（与 OHLCV/北向缓存同目录）。"""
    try:
        from .config import get_config

        cache_dir = get_config().get(
            "data_cache_dir", os.path.expanduser("~/.chstockdata/cache")
        )
    except Exception:  # pragma: no cover - 配置不可用时退回默认目录
        cache_dir = os.path.expanduser("~/.chstockdata/cache")
    return os.path.join(cache_dir, "name-code-map.json")


def _mootdx_unavailable_cache_file() -> str:
    """mootdx 全表不可用负缓存的磁盘路径（与 name-code-map.json 同目录）。"""
    try:
        from .config import get_config

        cache_dir = get_config().get(
            "data_cache_dir", os.path.expanduser("~/.chstockdata/cache")
        )
    except Exception:  # pragma: no cover - 配置不可用时退回默认目录
        cache_dir = os.path.expanduser("~/.chstockdata/cache")
    return os.path.join(cache_dir, "mootdx-unavailable.json")


def _load_mootdx_unavailable_from_disk() -> tuple[float, int] | None:
    """读持久化负缓存；仍在生效期内返回 ``(until, rounds)``，否则 None。

    损坏/过期/读失败一律返回 None（静默回退正常探测路径）。until 自过期，
    因此持久化不会掩盖真实恢复——退避最长 6 小时后自然会重新探测。
    """
    path = _mootdx_unavailable_cache_file()
    try:
        with open(path, encoding="utf-8") as fh:
            payload = _json.load(fh)
        until = float(payload.get("until") or 0.0)
        rounds = int(payload.get("rounds") or 0)
    except Exception:
        return None
    if until <= time.time():
        return None
    return until, max(1, rounds)


def _persist_mootdx_unavailable(until: float, rounds: int, reason: str) -> None:
    """全表探测失败后原子写入持久化负缓存；写失败静默（诊断元数据）。"""
    path = _mootdx_unavailable_cache_file()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        payload = {
            "until": until,
            "rounds": max(1, rounds),
            "reason": str(reason)[:300],
            "persisted_at": time.time(),
        }
        tmp = f"{path}.{os.getpid()}.tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            _json.dump(payload, fh, ensure_ascii=False)
        os.replace(tmp, path)
    except Exception:
        return


def _clear_mootdx_unavailable_disk() -> None:
    """成功选中服务器后删除持久化负缓存；文件不存在/删除失败静默。"""
    try:
        os.remove(_mootdx_unavailable_cache_file())
    except OSError:
        return


def _load_name_code_map_from_disk() -> tuple[dict[str, str], dict[str, str]] | None:
    """读当日磁盘缓存；非当日/损坏/读失败一律返回 None（静默回退网络路径）。"""
    path = _name_map_cache_file()
    try:
        with open(path, encoding="utf-8") as fh:
            payload = _json.load(fh)
        if not isinstance(payload, dict) or payload.get("date") != date.today().isoformat():
            return None
        pairs = payload.get("pairs")
        if not isinstance(pairs, list) or not pairs:
            return None
        n2c = {str(name): str(code) for name, code in pairs}
        c2n = {code: name for name, code in n2c.items()}
        return n2c, c2n
    except Exception:
        return None


def _save_name_code_map_to_disk(n2c: dict[str, str]) -> None:
    """写当日磁盘缓存；失败仅记日志，绝不影响主流程。"""
    path = _name_map_cache_file()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        payload = {
            "date": date.today().isoformat(),
            "pairs": list(n2c.items()),
        }
        with open(path, "w", encoding="utf-8") as fh:
            _json.dump(payload, fh, ensure_ascii=False)
    except Exception as e:
        logger.debug("写名称映射磁盘缓存失败（不影响主流程）：%s", e)


def _build_name_code_map() -> tuple[dict[str, str], dict[str, str]]:
    """Build name→code and code→name maps via mootdx (both SH & SZ markets)."""
    global _name_to_code, _code_to_name
    if _name_to_code is not None:
        return _name_to_code, _code_to_name

    # 后台预热线程与图内 resolve_ticker 可能并发首建；锁内二次检查避免重复
    # 下载两张全市场表。
    with _name_code_map_lock:
        if _name_to_code is not None:
            return _name_to_code, _code_to_name

        # issues/023 止血：当日磁盘缓存优先——此前每个新进程（web 重启/prefetch
        # worker/E2E 子进程）都要经 mootdx 重拉两张全市场表。
        cached = _load_name_code_map_from_disk()
        if cached is not None:
            _name_to_code, _code_to_name = cached
            logger.info("Loaded stock name-code map from disk cache: %d entries", len(cached[0]))
            return _name_to_code, _code_to_name

        n2c: dict[str, str] = {}
        c2n: dict[str, str] = {}

        try:
            for market in (0, 1):  # 0=SZ, 1=SH
                stocks = _mootdx_call("stocks", market=market)
                if stocks is None or stocks.empty:
                    continue
                for _, row in stocks.iterrows():
                    code = str(row["code"]).strip()
                    name = str(row["name"]).strip()
                    if not _re.match(r"^[036]\d{5}$", code):
                        continue
                    clean_name = name.replace(" ", "").replace("　", "")
                    n2c[clean_name] = code
                    c2n[code] = clean_name
        except Exception as e:
            # 网络抖动/通达信不可达时给出明确提示，而非冒泡成风马牛不相及的报错（#46/#66）
            raise ValueError(
                "无法通过 mootdx 解析股票名称（通达信服务暂时不可达）：%s。"
                "请稍后重试，或直接输入 6 位股票代码。" % e
            ) from e

        _name_to_code = n2c
        _code_to_name = c2n
        _save_name_code_map_to_disk(n2c)

    logger.info("Built stock name-code map: %d entries", len(n2c))
    return _name_to_code, _code_to_name


def resolve_ticker(user_input: str) -> str:
    """Resolve user input (code or Chinese name) to a 6-digit A-stock code.

    Accepts: '600379', 'SH600379', '600379.SH', '宝光股份'.
    Alphabetic pinyin initials are intentionally rejected before any full-market
    lookup so invalid input cannot block the Web UI on the mootdx connection.
    Returns: '600379'
    Raises: ValueError if not resolvable.
    """
    s = user_input.strip()
    if not s:
        raise ValueError("输入不能为空")

    has_chinese = any("一" <= ch <= "鿿" for ch in s)

    if not has_chinese:
        # 快速路径：纯 6 位代码（含交易所前缀/后缀形式）不进名称映射，直接归一化。
        # 先做一次轻量剥离判断，避免为每个 ticker 触发昂贵的全市场名称表构建。
        stripped = s.upper()
        for suffix in (".SH", ".SZ", ".BJ"):
            if stripped.endswith(suffix):
                stripped = stripped[: -len(suffix)]
                break
        for prefix in ("SH", "SZ", "BJ"):
            if stripped.startswith(prefix):
                stripped = stripped[len(prefix) :]
                break
        if _re.fullmatch(r"\d{6}", stripped):
            return _normalize_ticker(s)

        # Alphabetic shorthand is intentionally unsupported.  Reject it before
        # `_build_name_code_map`, whose mootdx full-market request can block the
        # Web UI for tens of seconds when TCP 7709 is unavailable.
        if _re.fullmatch(r"[A-Za-z]+", s):
            raise ValueError(
                "暂不支持拼音首字母或其他字母缩写，请输入完整中文股票名称或 "
                "6 位 A 股代码（如 002594）。"
            )
        # 不是代码：交给 _normalize_ticker 报"非 A 股/无效"错误。
        return _normalize_ticker(s)

    clean = s.replace(" ", "").replace("　", "")
    n2c, _ = _build_name_code_map()

    if clean in n2c:
        return n2c[clean]

    matches = {name: code for name, code in n2c.items() if clean in name}
    if len(matches) == 1:
        return next(iter(matches.values()))
    if len(matches) > 1:
        examples = ", ".join(f"{n}({c})" for n, c in list(matches.items())[:5])
        raise ValueError(f"'{s}' 匹配到多只股票: {examples}，请输入完整名称或代码")

    # LLM 有时会把行业/概念名（如 '游戏'、'白酒'）当 ticker 传进来（#76）。
    # 报错必须写明原因和正确用法，让模型能在下一次工具调用中自我纠正。
    raise ValueError(
        f"找不到股票 '{s}'。ticker 参数只接受 6 位股票代码（如 '600519'）"
        f"或完整股票名称（如 '贵州茅台'）；行业/概念/板块名（如 '游戏'）不是"
        f"有效的股票标识。请改用目标个股的 6 位股票代码重试。"
    )


# ---------------------------------------------------------------------------
# mootdx client (singleton)
# ---------------------------------------------------------------------------

_mootdx_client = None

# The readiness selection records the ordered TCP-reachable candidates for the
# worker.  A later selected-server failure may consume the next candidate once
# without starting another full discovery scan.  The list is deliberately
# worker-local: every Prefetch worker imports this module in its own process.
_mootdx_reselect_candidates: tuple[tuple[str, int], ...] = ()
_mootdx_reselect_index: int | None = None
_mootdx_reselect_pending = False

# 实测可用的通达信备选服务器。用于规避 mootdx 0.11.x 全新安装时 BESTIP.HQ 为空串
# 导致的 `ValueError: not enough values to unpack`。
# ⚠️ 2026-09-03 issues/023 金丝雀探测（阿里云 ECS 容器内 + 本机家宽双视角）：
# 云段节点（华为/腾讯/阿里云段）协议层对**所有人**失效/拒绝，仅经典电信主站存活——
# 前三台（上海电信Z1/杭州电信J2/杭州电信J3）在服务器容器内 canary 真实取数通过，
# 置于表首优先命中。mootdx 自带 HQ_HOSTS 38 台全为云段，不含任何一台经典电信主站，
# 这正是服务器"全量协议被拒"而探测永远找不到活主机的原因。原华为云 9 台 +
# 119.97.185.59 保留表尾兜底（协议已死，canary 会自动跳过；若复活自动可用）。
_TDX_SERVERS = [
    ("180.153.18.170", 7709), ("115.238.56.198", 7709), ("218.75.126.9", 7709),
    ("119.97.185.59", 7709), ("124.70.133.119", 7709), ("116.205.183.150", 7709),
    ("123.60.73.44", 7709), ("116.205.163.254", 7709), ("121.36.225.169", 7709),
    ("123.60.70.228", 7709), ("124.71.9.153", 7709), ("110.41.147.114", 7709),
    ("124.71.187.122", 7709),
]


# 探测用的探针股票：主板老票，任何通达信服务器都应能返回它的日线。
_TDX_CANARY_SYMBOL = "600519"

# 全部服务器都验不过之后，隔多久才允许再探一轮（秒）。没有这个负缓存，
# 每一次取数都会把整张服务器表重探一遍（几十台 × TCP 超时），把"取不到数"
# 放大成"每个请求卡几十秒"。
# issues/023 止血（2026-09-02）：固定 300s 改为指数退避（5min→30min→2h→6h），
# 连续全表失败逐级拉长、成功选中即归零；非交易时段（周一至五 09:00–15:30 之外）
# 全表失败直接用最长档——夜间/休市不再反复敲门（新浪兜底是设计内运行态）。
_MOOTDX_RETRY_AFTER_S = 300.0  # 退避序列首档（保留常量名兼容既有引用）
_MOOTDX_RETRY_BACKOFF_S = (300.0, 1800.0, 7200.0, 21600.0)
_mootdx_outage_rounds = 0
_mootdx_unavailable_until = 0.0

# issues/023 止血：mootdx 调用串行锁 + 轻节流。七分析师并行分支 + prefetch
# worker 可能并发打同一个 TCP socket（二进制帧交错→报错→重连抖动），且 TDX
# 请求此前完全无节制（与东财的 _em_get 不同）。锁序约定：_name_code_map_lock
# → _mootdx_call_lock 单向（mootdx 调用路径不会反向拿名称映射锁，无死锁）。
_mootdx_call_lock = threading.Lock()
_mootdx_last_call = float("-inf")

# 候选逐台验证之间的最小间隔（秒）：把"几十台连发"变成慢速敲门。
# 测试可用 TDX_PROBE_GAP_SECONDS=0 关闭。
_TDX_PROBE_GAP_S = float(os.environ.get("TDX_PROBE_GAP_SECONDS", "0.3"))

# DEC-P3-19 P1（2026-09-12）：工具调用上下文内的选服探测预算（秒，5–8s 窗口）。
# 工具上下文里没有任何一次 warmup 来摊销全表探测（服务器实测 ~100s，会在
# get_stock_data 的 105s 预算内被重付并饿死新浪兜底）；超预算即抛错、备用源
# 接管。worker warmup / 库调用没有该上下文，保持全表选优语义不变。
_TOOL_CONTEXT_PROBE_BUDGET_S = float(
    os.environ.get("TDX_TOOL_PROBE_BUDGET_SECONDS", "6.0")
)


def _tdx_min_interval() -> float:
    """两次 mootdx 调用的最小间隔（env TDX_MIN_INTERVAL，默认 0.3s，调用时读取）。"""
    try:
        return float(os.environ.get("TDX_MIN_INTERVAL", "0.3"))
    except ValueError:
        return 0.3


def _calendar_local_is_trading_day(day: str) -> bool | None:
    """本地交易日历判定（零网络）；不可用/区间外返回 None（DEC-P1-27）。

    这里不能触发在线回落：该判定本身用于决定是否探测 TDX，走网络会形成
    自指并拖慢退避路径。日历是支持性能力，任何失败都回落原启发式。
    """
    try:
        from .trading_calendar import local_is_trading_day

        return local_is_trading_day(day)
    except Exception:  # noqa: BLE001 - supportive capability must not break calls
        return None


def _tdx_probe_window_open() -> bool:
    """周一至周五 09:00–15:30（服务器本地时区）才做全表重探。

    DEC-P1-27：本地交易日本地日历确认当天非交易日时直接关闭全表重探
    （覆盖区间内的节假日）；日历不可用或区间外维持原有日期/时段启发式。
    """
    now = datetime.now()
    if _calendar_local_is_trading_day(now.date().isoformat()) is False:
        return False
    if now.weekday() >= 5:
        return False
    if now.hour < 9 or now.hour > 15:
        return False
    return not (now.hour == 15 and now.minute > 30)


def _tool_context_probe_deadline_at() -> float | None:
    """工具调用上下文内的探测 deadline；上下文外返回 None（保持全表选优）。

    DEC-P3-19 P1：只在一次 prefetch 工具调用（``source_execution_context``）
    内部启用短预算。worker warmup 与库调用没有该上下文，探测行为不变。
    """
    try:
        from .source_context import get_source_execution_context
    except ImportError:  # pragma: no cover - partial installs
        return None
    try:
        state = get_source_execution_context()
    except Exception:  # pragma: no cover - context is diagnostic only
        return None
    if state is None:
        return None
    budget = _TOOL_CONTEXT_PROBE_BUDGET_S
    if budget <= 0:
        return None
    return time.monotonic() + budget


def _mootdx_probe_budget_exceeded() -> RuntimeError:
    return RuntimeError(
        "mootdx 服务器探测超出工具调用预算（%.0fs）：单次工具调用内不做全表"
        "选优，改用备用数据源；后台 warmup 会继续完成选服。"
        % _TOOL_CONTEXT_PROBE_BUDGET_S
    )


def _next_mootdx_backoff_seconds() -> float:
    """全表失败后的负缓存时长：交易时段按指数退避；非交易时段直接取最长档。"""
    global _mootdx_outage_rounds
    _mootdx_outage_rounds += 1
    if not _tdx_probe_window_open():
        return _MOOTDX_RETRY_BACKOFF_S[-1]
    return _MOOTDX_RETRY_BACKOFF_S[
        min(_mootdx_outage_rounds - 1, len(_MOOTDX_RETRY_BACKOFF_S) - 1)
    ]

# ⚠️ 曾经加过「连续 N 台协议失败就停手」的提前退出，已移除：三台远端拒绝**证明不了**
# 本地网络封了协议，而列表里靠后的服务器完全可能是好的。提前收手会让那台可用服务器
# 永远试不到，还顺手记下 5 分钟负缓存。省下的十几秒不值得换这个风险——真正的耗时
# 大头是 bestip 全表测速，那个已经单独规避了。


def _candidate_tdx_servers() -> list[tuple[str, int]]:
    """待试的通达信服务器：先用实测精选的 `_TDX_SERVERS`，再补 mootdx 自带的完整主机表。

    只试精选的那 10 台是不够的——它们要是恰好都不可用，而 mootdx 自带表里还有活着的
    主机，就会被判成"全网不可达"并记 5 分钟负缓存。这里把两张表合起来去重后逐台验证，
    覆盖面等同 `bestip`，但不做它那套要跑几分钟的全表测速。
    """
    servers = list(_TDX_SERVERS)
    seen = set(servers)
    try:
        from mootdx.consts import HQ_HOSTS
        for entry in HQ_HOSTS:
            # 形如 ("深圳双线主站1", "110.41.147.114", 7709)
            host = (entry[1], entry[2]) if len(entry) >= 3 else None
            if host and host not in seen:
                seen.add(host)
                servers.append(host)
    except Exception as e:  # mootdx 版本变动导致取不到就只用精选表，不影响主流程
        logger.debug("读取 mootdx HQ_HOSTS 失败，仅使用内置精选表：%s", e)
    return servers


def _reachable_tdx_servers(
    servers, timeout: float = 2.0, *, deadline_at: float | None = None
):
    """并发做 TCP 预筛，返回可连的那些（保持原顺序）。

    只是把"等超时"这件事并行化，不改变优先级：返回顺序仍是候选表顺序，所以实测
    精选的服务器依旧排在前面、依旧第一个被真实验证。

    ``deadline_at``（仅工具上下文内提供，DEC-P3-19 P1）：到达即停止剩余批次、
    返回已收集结果；其后的候选循环按同一 deadline 中止，因此被截断的探测不会
    被当成"全表试完"而写入全表不可用负缓存。
    """
    if not servers:
        return []
    from concurrent.futures import ThreadPoolExecutor

    # issues/023 止血：预筛并发从 16 收到 6——几十台端口的并发握手突发本身
    # 就是扫描样行为；等 IO 的代价由候选间隔共同摊慢，不改变选取语义。
    workers = min(6, len(servers))
    reachable: list[tuple[str, int]] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for start in range(0, len(servers), workers):
            if deadline_at is not None:
                remaining = deadline_at - time.monotonic()
                if remaining <= 0:
                    break
                probe_timeout = min(timeout, max(0.05, remaining))
            else:
                probe_timeout = timeout
            batch = servers[start:start + workers]
            flags = list(
                pool.map(lambda s: _probe_tdx(s[0], s[1], probe_timeout), batch)
            )
            reachable.extend(srv for srv, ok in zip(batch, flags) if ok)
    return reachable


def _probe_tdx(ip: str, port: int, timeout: float = 2.0) -> bool:
    """TCP 握手探测通达信服务器端口是否开着。

    ⚠️ 只是**廉价预筛**，通过不代表能取到数：实测存在大量"TCP 三次握手成功、
    通达信协议握手立刻被 RST"的服务器。选服务器必须再走 `_tdx_client_works()`
    做一次真实取数验证（#90）。
    """
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except OSError:
        return False


def _tdx_client_works(client) -> bool:
    """真实拉一根 K 线来验证这个 client 确实能取数。"""
    try:
        df = _source_call(
            "mootdx",
            "canary",
            lambda: client.bars(
                symbol=_TDX_CANARY_SYMBOL, category=4, offset=1
            ),
        )
        return df is not None and not df.empty
    except Exception as exc:
        if _source_deadline_error(exc):
            raise
        return False


def reset_mootdx_client(*, preserve_candidates: bool = False) -> None:
    """丢弃缓存的 client，让下一次调用重新选服务器。

    单例一旦钉在一台"当时能用、后来挂了"的服务器上，之后每次取数都失败降级且
    永远不会重选。数据调用发现 mootdx 出错时调它，下一次就能换一台（#90）。

    ``preserve_candidates=True`` 仅用于一次选中服务器失败后的有界重选：保留
    readiness 阶段记录的候选队列，避免在健康调用之间重新扫描整张服务器表。

    负缓存（``_mootdx_unavailable_until``）代表"整张服务器表都不可用"。只有确实
    存在可重选的候选队列时才会清除它；否则保留，让下一次调用走快速失败而不是
    重新扫描整张表（spec §7：不得每次重新扫描全部服务器——服务器上 mootdx 不可用
    时，重复全表探测会把核心工具预算耗尽）。
    """
    global _mootdx_client, _mootdx_unavailable_until, _mootdx_reselect_pending
    _mootdx_client = None
    _mootdx_reselect_pending = bool(
        preserve_candidates
        and _mootdx_reselect_candidates
        and _mootdx_reselect_index is not None
    )
    if not preserve_candidates:
        _clear_mootdx_reselect_candidates()
    if _mootdx_reselect_pending:
        # 有 readiness 候选可重选：清负缓存，允许走有界重选。
        _mootdx_unavailable_until = 0.0
    # 否则保留负缓存（若已设置）：全表不可用时不重复扫描，工具应降级到备用源。


def _clear_mootdx_reselect_candidates() -> None:
    global _mootdx_reselect_candidates, _mootdx_reselect_index
    _mootdx_reselect_candidates = ()
    _mootdx_reselect_index = None


@contextlib.contextmanager
def _preserve_mootdx_bestip():
    """探测期间保护 mootdx 的持久化服务器配置，退出时按需还原。

    `StdQuotes.__init__` 里有 `config.set('BESTIP', {'HQ': self.server})`——**每建一次
    带 server 的 client 都会写进 mootdx 的配置文件**。逐台探测几十个候选就等于把用户
    原本配好的服务器一路覆写，最后留下的是最后一台**失败的**服务器，还会连累同一台
    机器上其它用 mootdx 的程序。

    🔴 必须先 `setup()` 再快照：新进程里 `config.get("BESTIP")` 返回的是模块默认空值，
    用户持久化的值要等 `BaseQuotes.__init__` 调 `setup()` 才读进来。快照到空值的话，
    "还原"反而会把真实配置抹成空——比不还原更糟。

    用法：`with _preserve_mootdx_bestip() as keep:` —— 选出可用服务器时调 `keep()`
    表示"这次的覆写是我们想要的，别还原"；不调就在退出时还原。

    ⚠️ **做成上下文管理器而不是手动调还原函数**：此前是在多处分别调还原，再加一条
    提前返回就会漏掉一处，而漏掉的后果是静默留下一台死服务器。
    """
    saved = None
    try:
        from mootdx import config as _cfg
        _cfg.setup()
        saved = _cfg.get("BESTIP")
        if isinstance(saved, dict):
            saved = dict(saved)
    except Exception as e:  # 版本差异导致取不到就跳过保护，别影响主流程
        logger.debug("读取 mootdx BESTIP 失败，本次探测不做保护：%s", e)

    keep = {"flag": False}
    try:
        yield lambda: keep.__setitem__("flag", True)
    finally:
        if saved is not None and not keep["flag"]:
            try:
                from mootdx import config as _cfg2
                _cfg2.set("BESTIP", saved)
            except Exception as e:
                logger.debug("恢复 mootdx BESTIP 失败：%s", e)


def _get_mootdx_client():
    """Lazy-init 健壮版 mootdx Quotes client（TCP 连接，可复用）。

    选服务器的顺序：内置服务器表（TCP 预筛 + 真实取数验证）→ 裸 factory（老用户
    config 里已有 IP）。每一级都必须真正取到数据才会被采用，避免把 client 钉死在
    一台"端口开着但协议不通"的服务器上（#90）。全部失败时抛 RuntimeError，并在
    `_MOOTDX_RETRY_AFTER_S` 内直接快速失败，不再逐台重探。
    """
    global _mootdx_client, _mootdx_unavailable_until
    global _mootdx_reselect_candidates, _mootdx_reselect_index
    global _mootdx_reselect_pending, _mootdx_outage_rounds
    if _mootdx_client is not None:
        return _mootdx_client

    now = time.time()
    # 可靠性（2026-09-11，数据层 DEC）：进程内存负缓存之外再查磁盘持久化负缓存。
    # 冷启动进程（审计/CLI/重启后的 worker）不再在工具预算内重付 ~100s 全表
    # 探测，而是立即快速失败、让新浪兜底接管；退避档位跨进程延续。
    disk_unavailable = _load_mootdx_unavailable_from_disk()
    if disk_unavailable is not None:
        disk_until, disk_rounds = disk_unavailable
        if disk_rounds > _mootdx_outage_rounds:
            _mootdx_outage_rounds = disk_rounds
        if disk_until > _mootdx_unavailable_until:
            _mootdx_unavailable_until = disk_until
    if now < _mootdx_unavailable_until:
        raise RuntimeError(
            "mootdx 通达信服务器暂不可用（%.0f 秒内不再重试）。"
            "已尝试全部内置服务器：端口能连上的也没能完成通达信协议取数。"
            "请检查网络环境（代理/防火墙/公司网络常拦 TCP 7709），"
            "或改用 6 位股票代码直接查询。" % (_mootdx_unavailable_until - now)
        )

    # DEC-P3-19 P1：工具调用上下文内给选服探测一个短 deadline；上下文外为 None。
    probe_deadline_at = _tool_context_probe_deadline_at()

    from mootdx.quotes import Quotes

    # A selected client can fail after readiness.  Use the next candidate
    # captured during that readiness selection exactly once.  In particular,
    # do not call `_candidate_tdx_servers()` or `_reachable_tdx_servers()` on
    # this recovery path: a new full scan would turn a single source failure
    # into a long blocking retry and defeat warm-worker reuse.
    if _mootdx_reselect_pending:
        _mootdx_reselect_pending = False
        current_index = _mootdx_reselect_index
        next_index = (
            None
            if current_index is None
            else current_index + 1
        )
        if next_index is not None and next_index < len(_mootdx_reselect_candidates):
            if probe_deadline_at is not None and time.monotonic() >= probe_deadline_at:
                raise _mootdx_probe_budget_exceeded()
            ip, port = _mootdx_reselect_candidates[next_index]
            try:
                candidate = Quotes.factory(market="std", server=(ip, port))
            except Exception as exc:
                _clear_mootdx_reselect_candidates()
                raise RuntimeError(
                    "mootdx readiness candidate replacement failed"
                ) from exc
            if _tdx_client_works(candidate):
                _mootdx_client = candidate
                _mootdx_reselect_index = next_index
                _mootdx_outage_rounds = 0
                _clear_mootdx_unavailable_disk()
                return _mootdx_client
        _clear_mootdx_reselect_candidates()
        raise RuntimeError("mootdx readiness candidates exhausted")

    # `_mootdx_client` may have been cleared by a caller starting a fresh
    # readiness cycle.  Discard any stale candidate metadata before the full
    # initial selection below.
    _clear_mootdx_reselect_candidates()

    tcp_ok_but_dead = 0
    # 探测会覆写 mootdx 的持久化配置——包在这里，只有真选出可用服务器时才 keep()，
    # 其余每条退出路径（含异常）都自动还原。
    with _preserve_mootdx_bestip() as keep_bestip:
        # TCP 预筛并发跑：几十台里多数是"连都连不上"，串行每台要等满超时（实测整轮
        # 几十秒，首次调用像卡死）。预筛纯粹是等 IO，并发不改变选取语义——下面仍按
        # 原顺序、逐台做真实取数验证，精选表依旧优先。
        candidates = _candidate_tdx_servers()
        if probe_deadline_at is not None:
            reachable = _reachable_tdx_servers(
                candidates, deadline_at=probe_deadline_at
            )
        else:
            reachable = _reachable_tdx_servers(candidates)
        _mootdx_reselect_candidates = tuple(reachable)

        for candidate_index, (ip, port) in enumerate(reachable):
            # DEC-P3-19 P1：预算烧尽即抛——截断的探测不得走到"全表失败"的
            # 负缓存写入路径，由调用方降级到备用源。
            if probe_deadline_at is not None and time.monotonic() >= probe_deadline_at:
                raise _mootdx_probe_budget_exceeded()
            # issues/023 止血：候选逐台验证之间留最小间隔，把整轮探测从
            # "连发扫描"摊成慢速敲门（首台前的等待没有意义，跳过）。
            if candidate_index and _TDX_PROBE_GAP_S > 0:
                time.sleep(_TDX_PROBE_GAP_S)
            # 「TCP 通但通达信协议不通」有两种表现：factory 建连时握手就被拒，
            # 或者建出来了但取不到数。**两种都要算**——只统计后者的话，计数永远是 0，
            # 下面的快速失败判断就失效了。
            try:
                candidate = Quotes.factory(market="std", server=(ip, port))
            except Exception as e:
                tcp_ok_but_dead += 1
                logger.debug("mootdx %s:%s 握手失败（%s），换下一台", ip, port, type(e).__name__)
            else:
                if _tdx_client_works(candidate):
                    logger.info("mootdx server selected: %s:%s", ip, port)
                    keep_bestip()   # 这次的覆写正是我们想要的，别还原
                    _mootdx_client = candidate
                    _mootdx_reselect_index = candidate_index
                    _mootdx_outage_rounds = 0
                    _clear_mootdx_unavailable_disk()
                    return _mootdx_client
                tcp_ok_but_dead += 1
                logger.debug("mootdx %s:%s 建连成功但取不到数，换下一台", ip, port)

    # 走到这里说明逐台探测都没成——上面的 with 已经把 BESTIP 还原成用户原本的配置，
    # 下面的裸 factory 读的正是它，这个兜底才有意义。
    # ⚠️ 刻意**不用** `bestip=True`：它会把整张主机表做一遍测速，实测要几分钟。
    # `_candidate_tdx_servers()` 已经把 mootdx 自带的完整主机表逐台验证过了，
    # 覆盖面不比 bestip 差，而且每台都是"真取到数才算通过"。
    if probe_deadline_at is not None and time.monotonic() >= probe_deadline_at:
        raise _mootdx_probe_budget_exceeded()
    try:
        candidate = Quotes.factory(market="std")
    except Exception as e:
        logger.debug("mootdx 裸 factory 失败 — %s", e)
    else:
        if _tdx_client_works(candidate):
            logger.info("mootdx client from 裸 factory（用户已有配置）")
            _mootdx_client = candidate
            _clear_mootdx_reselect_candidates()
            _mootdx_outage_rounds = 0
            _clear_mootdx_unavailable_disk()
            return _mootdx_client

    _clear_mootdx_reselect_candidates()
    backoff = _next_mootdx_backoff_seconds()
    _mootdx_unavailable_until = time.time() + backoff
    if tcp_ok_but_dead:
        # 说清楚是"协议被拒"而不是"连不上"——这两者的排查方向完全不同。
        cause = (
            "%d 台服务器端口能连上，但通达信协议握手/取数被拒。"
            "这通常是协议层被拦（代理、防火墙、公司网络对 TCP 7709 的策略），"
            "换服务器解决不了。" % tcp_ok_but_dead
        )
    else:
        cause = "内置服务器表里没有一台的 TCP 7709 能连上，请检查网络连通性。"
    _persist_mootdx_unavailable(_mootdx_unavailable_until, _mootdx_outage_rounds, cause)
    raise RuntimeError(
        "mootdx 通达信服务器不可用：%s"
        "可改用 6 位股票代码直接查询。%.0f 秒内将直接快速失败、不再逐台重探。"
        % (cause, backoff)
    )


def _mootdx_call(method: str, *, _fallback_from: str | None = None, **kwargs):
    """调用 mootdx 的某个方法，失败就弃用当前服务器。

    选中的服务器随时可能挂掉；不弃用的话单例会一直指着它，之后每次取数都失败降级
    且永不重选（#90 的「反复降级」）。取 client 本身失败时不清缓存——那条路径已经
    在 `_get_mootdx_client` 里做了负缓存，清掉等于取消快速失败。

    issues/023 止血：全程持 `_mootdx_call_lock`——七分析师并行分支与 prefetch
    worker 共享同一个 TCP socket，串行化既避免二进制帧交错（正确性），也保证
    服务器重选不会并发发生；相邻调用间补足 `_tdx_min_interval()` 最小间隔。
    """
    global _mootdx_last_call
    with _mootdx_call_lock:
        wait = _tdx_min_interval() - (time.monotonic() - _mootdx_last_call)
        if wait > 0:
            time.sleep(wait)
        _mootdx_last_call = time.monotonic()
        client = _get_mootdx_client()
        for attempt in range(1, 3):
            try:
                return _source_call(
                    "mootdx",
                    method,
                    lambda: getattr(client, method)(**kwargs),
                    attempt_no=attempt,
                    fallback_from=_fallback_from,
                )
            except Exception as exc:
                # A malformed wire timestamp is a response-structure issue; keep
                # the selected client available for the raw-date recovery path
                # instead of needlessly selecting another server.
                if "year must be in 1..9999" in str(exc).lower():
                    raise
                if _source_deadline_error(exc):
                    raise
                reset_mootdx_client(preserve_candidates=attempt < 2)
                if attempt >= 2:
                    raise
                client = _get_mootdx_client()
        raise RuntimeError("mootdx call did not return")  # pragma: no cover


# ---------------------------------------------------------------------------
# Tencent Finance API
# ---------------------------------------------------------------------------

def _tencent_quote(
    codes: list[str], *, fallback_from: str | None = None
) -> dict[str, dict]:
    """Batch real-time quotes from Tencent Finance (qt.gtimg.cn).

    Returns dict[code] -> {name, price, pe_ttm, pb, mcap_yi, ...}
    """
    prefixed = [f"{_get_prefix(c)}{c}" for c in codes]
    url = "https://qt.gtimg.cn/q=" + ",".join(prefixed)
    # 用项目统一的 requests 会话而非 urllib：macOS 系统 Python 的 urllib
    # 常因证书链（CERTIFICATE_VERIFY_FAILED）连腾讯失败，导致这个最优先的
    # 实时源在本地/部分部署上恒降级到新浪。requests 会走系统/打包证书。
    resp = _source_http_get(
        "tencent",
        url,
        timeout=10,
        headers={"User-Agent": _UA},
        fallback_from=fallback_from,
    )
    resp.raise_for_status()
    raw = resp.content.decode("gbk", errors="replace")

    result = {}
    for line in raw.strip().split(";"):
        if not line.strip() or "=" not in line or '"' not in line:
            continue
        key = line.split("=")[0].split("_")[-1]
        vals = line.split('"')[1].split("~")
        if len(vals) < 54:  # needs index 53 (市盈率(静)) to expose a full quote
            continue
        code = key[2:]  # strip sh/sz/bj prefix
        result[code] = {
            "name": vals[1],
            "price": float(vals[3]) if vals[3] else 0,
            "last_close": float(vals[4]) if vals[4] else 0,
            "open": float(vals[5]) if vals[5] else 0,
            "change_pct": float(vals[32]) if vals[32] else 0,
            "high": float(vals[33]) if vals[33] else 0,
            "low": float(vals[34]) if vals[34] else 0,
            "amount_wan": float(vals[37]) if vals[37] else 0,
            "turnover_pct": float(vals[38]) if vals[38] else 0,
            "pe_ttm": float(vals[39]) if vals[39] else 0,
            # ⚠️ 44=流通市值、45=总市值（曾标反）。总股本≠流通股本时差数倍。
            # 上游 a-stock-data v3.5.1 实测校准：中船特气 688146 流通 356 亿 vs 总市值 1300 亿（3.65×）。
            "float_mcap_yi": float(vals[44]) if vals[44] else 0,
            "mcap_yi": float(vals[45]) if vals[45] else 0,
            "pb": float(vals[46]) if vals[46] else 0,
            "limit_up": float(vals[47]) if vals[47] else 0,
            "limit_down": float(vals[48]) if vals[48] else 0,
            # ⚠️ 52=市盈率(动)、53=市盈率(静)（曾取 52 当静态 PE）。成长股两档
            # 可差约 2×：实测 300308 pos52=39.95 vs pos53=101.02（TTM=53.33）。
            "pe_static": float(vals[53]) if vals[53] else 0,
        }
        # 僵尸报价检测：成交额为 0 且最新价==昨收，极可能是已迁移的北交所老码 /
        # 停牌股的定格报价（腾讯对这类标的照样返回 HTTP 200，不报错）。
        # 上游 a-stock-data v3.6.0 实测 bj832982 报 112.60（老码），真实新码 920982 为 131.74。
        q = result[code]
        q["is_stale"] = (
            q["amount_wan"] == 0
            and q["price"] == q["last_close"]
            and q["price"] > 0
        )
    return result


class _RealtimeQuoteUnavailable(VendorNetworkError):
    """All free real-time quote providers failed or returned invalid prices."""

    def __init__(self, attempts: dict[str, list[str]]):
        self.attempts = attempts
        # Keep the public error deliberately provider- and credential-safe.  The
        # detailed exception type is retained in ``attempts`` for diagnostics,
        # while proxy URLs/tokens never enter tool output.
        super().__init__("实时行情不可用：腾讯、mootdx、新浪均未返回有效价格")


def _quote_number(value):
    """Convert a provider field to a finite float, preserving missing values."""
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _quote_row_value(row, *keys):
    """Read the first non-missing value from a dict/Series-like quote row."""
    for key in keys:
        try:
            value = row.get(key)
        except AttributeError:
            value = None
        if value is not None and value != "":
            return value
    return None


def _normalize_realtime_quote(
    code: str,
    row,
    source: str,
    *,
    amount_is_yuan: bool = False,
) -> dict | None:
    """Normalize one free-source quote to the Tencent-compatible shape.

    Tencent supplies valuation fields, whereas mootdx/Sina only supply market
    snapshot fields.  Missing valuation fields remain ``None`` instead of
    being fabricated from a different semantic measure.
    """
    price = _quote_number(_quote_row_value(row, "price", "last", "current"))
    if price is None or price <= 0:
        return None

    last_close = _quote_number(
        _quote_row_value(row, "last_close", "pre_close", "previous_close")
    )
    open_price = _quote_number(_quote_row_value(row, "open", "open_price"))
    high = _quote_number(_quote_row_value(row, "high", "high_price"))
    low = _quote_number(_quote_row_value(row, "low", "low_price"))
    amount = _quote_number(_quote_row_value(row, "amount_wan", "amount"))
    if amount is not None and amount_is_yuan:
        amount /= 10000.0
    change_pct = _quote_number(_quote_row_value(row, "change_pct"))
    if change_pct is None and last_close:
        change_pct = (price / last_close - 1) * 100

    return {
        "name": _quote_row_value(row, "name", "stock_name") or "",
        "price": price,
        "last_close": last_close,
        "open": open_price,
        "change_pct": change_pct,
        "high": high,
        "low": low,
        "amount_wan": amount,
        "turnover_pct": _quote_number(_quote_row_value(row, "turnover_pct")),
        "pe_ttm": _quote_number(_quote_row_value(row, "pe_ttm")),
        "pe_static": _quote_number(_quote_row_value(row, "pe_static")),
        "mcap_yi": _quote_number(_quote_row_value(row, "mcap_yi")),
        "float_mcap_yi": _quote_number(_quote_row_value(row, "float_mcap_yi")),
        "pb": _quote_number(_quote_row_value(row, "pb")),
        "limit_up": _quote_number(_quote_row_value(row, "limit_up")),
        "limit_down": _quote_number(_quote_row_value(row, "limit_down")),
        "is_stale": bool(_quote_row_value(row, "is_stale")),
        "source": source,
    }


def _mootdx_realtime_quote(
    codes: list[str], *, fallback_from: str | None = None
) -> dict[str, dict]:
    """Fetch real-time snapshots from the TDX TCP service via mootdx."""
    frame = _mootdx_call("quotes", symbol=codes, _fallback_from=fallback_from)
    if frame is None:
        return {}
    if not isinstance(frame, pd.DataFrame):
        frame = pd.DataFrame(frame)
    if frame.empty:
        return {}

    requested = [str(code).strip().lower() for code in codes]
    result = {}
    records = frame.to_dict("records")
    for index, row in enumerate(records):
        raw_code = _quote_row_value(row, "code", "symbol", "ticker")
        normalized_code = str(raw_code).strip().lower() if raw_code else ""
        for prefix in ("sh", "sz", "bj"):
            if normalized_code.startswith(prefix):
                normalized_code = normalized_code[len(prefix) :]
                break
        if normalized_code not in requested and len(records) == len(requested):
            normalized_code = requested[index]
        if normalized_code not in requested:
            continue
        normalized = _normalize_realtime_quote(
            normalized_code,
            row,
            "mootdx",
            amount_is_yuan=True,
        )
        if normalized is not None:
            result[normalized_code] = normalized
    return result


def _sina_realtime_quote(
    codes: list[str], *, fallback_from: str | None = None
) -> dict[str, dict]:
    """Fetch real-time snapshots from Sina ``hq.sinajs.cn``."""
    symbols = ",".join(_sina_stock_code(str(code).strip()) for code in codes)
    response = _source_http_get(
        "sina",
        "https://hq.sinajs.cn/list=" + symbols,
        headers={
            "User-Agent": _UA,
            "Referer": "https://finance.sina.com.cn/",
        },
        timeout=10,
        fallback_from=fallback_from,
    )
    response.raise_for_status()
    raw_content = getattr(response, "content", None)
    if isinstance(raw_content, bytes):
        raw = raw_content.decode("gbk", errors="replace")
    else:
        raw = str(getattr(response, "text", ""))

    requested = {str(code).strip().lower() for code in codes}
    result = {}
    for match in _re.finditer(r'hq_str_([a-z0-9]+)\s*=\s*"([^"]*)"', raw):
        symbol, payload = match.groups()
        code = symbol[2:] if symbol[:2] in {"sh", "sz", "bj"} else symbol
        if code not in requested:
            continue
        fields = payload.split(",")
        if len(fields) < 10:
            continue
        row = {
            "name": fields[0],
            "open": fields[1],
            "last_close": fields[2],
            "price": fields[3],
            "high": fields[4],
            "low": fields[5],
            # Sina's field 9 is yuan; normalize to 万元.
            "amount": fields[9],
        }
        normalized = _normalize_realtime_quote(
            code,
            row,
            "sina",
            amount_is_yuan=True,
        )
        if normalized is None:
            continue
        normalized["is_stale"] = bool(
            normalized["amount_wan"] == 0
            and normalized["last_close"] == normalized["price"]
        )
        result[code] = normalized
    return result


def _get_realtime_quotes(codes: list[str]) -> dict[str, dict]:
    """Get snapshots in the explicit free-source order Tencent → TDX → Sina.

    Fallback is per code, so a partial Tencent response does not discard valid
    data for other symbols.  ``_RealtimeQuoteUnavailable`` is raised only when
    no requested code has a usable positive-price snapshot.
    """
    requested = list(
        dict.fromkeys(str(code).strip() for code in codes if str(code).strip())
    )
    if not requested:
        raise _RealtimeQuoteUnavailable({})

    remaining = set(requested)
    result: dict[str, dict] = {}
    stale_candidates: dict[str, dict] = {}
    attempts = {code: [] for code in requested}
    providers = (
        ("tencent", _tencent_quote),
        ("mootdx", _mootdx_realtime_quote),
        ("sina", _sina_realtime_quote),
    )

    fallback_from: str | None = None
    for provider, fetcher in providers:
        if not remaining:
            break
        current = sorted(remaining)
        try:
            payload = fetcher(current, fallback_from=fallback_from) or {}
        except Exception as exc:
            error_type = type(exc).__name__
            for code in current:
                attempts[code].append(error_type)
            fallback_from = provider
            continue
        if not isinstance(payload, dict):
            payload = {}
        for code in current:
            quote = payload.get(code)
            if not isinstance(quote, dict):
                attempts[code].append("empty")
                continue
            price = _quote_number(quote.get("price"))
            if price is None or price <= 0:
                attempts[code].append("invalid_price")
                continue
            if quote.get("is_stale"):
                # A stale snapshot may be a suspended/legacy-code zombie, but
                # it is also the legitimate last-close response outside market
                # hours. Prefer a fresh next source; retain the first stale
                # candidate only as a last resort rather than reporting a
                # false network failure.
                stale_candidates.setdefault(code, dict(quote))
                attempts[code].append("stale")
                continue
            normalized = dict(quote)
            normalized.setdefault("source", provider)
            normalized["fallback_attempts"] = list(attempts[code])
            result[code] = normalized
            remaining.remove(code)
        fallback_from = provider

    for code, quote in stale_candidates.items():
        if code in result:
            continue
        quote["fallback_attempts"] = list(attempts[code])
        quote["quote_status"] = "stale_last_resort"
        result[code] = quote

    if not result:
        raise _RealtimeQuoteUnavailable(attempts)
    return result


def get_realtime_snapshot(ticker: str) -> dict[str, Any]:
    """Return one display-safe, current-only quote snapshot for the Web UI.

    This is a presentation facade over the existing Tencent → mootdx → Sina
    fallback chain.  It deliberately stays outside the LLM tool registry and
    does not mix historical prices or prefetched research data into the
    current quote.
    """
    code = _normalize_ticker(ticker)
    quotes = _get_realtime_quotes([code])
    quote = quotes.get(code)
    if not isinstance(quote, dict):
        raise _RealtimeQuoteUnavailable({code: ["missing_quote"]})

    price = _quote_number(quote.get("price"))
    if price is None or price <= 0:
        raise _RealtimeQuoteUnavailable({code: ["invalid_price"]})

    numeric_fields = (
        "last_close",
        "open",
        "change_pct",
        "high",
        "low",
        "amount_wan",
        "turnover_pct",
        "pe_ttm",
        "pe_static",
        "pb",
        "mcap_yi",
        "float_mcap_yi",
        "limit_up",
        "limit_down",
    )
    snapshot: dict[str, Any] = {
        "status": "ready",
        "ticker": code,
        "name": str(quote.get("name") or code)[:80],
        "price": price,
        "source": str(quote.get("source") or "unknown")[:80],
        "quote_status": str(quote.get("quote_status") or "")[:80] or None,
        "data_group": "实时行情",
        "observed_at": datetime.now(_MARKET_TZ).isoformat(),
    }
    for field in numeric_fields:
        snapshot[field] = _quote_number(quote.get(field))
    return snapshot


# ---------------------------------------------------------------------------
# Eastmoney Datacenter unified helper (龙虎榜/解禁 etc.)
# ---------------------------------------------------------------------------

_DATACENTER_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"
_EASTMONEY_BOARD_FLOW_URL = "https://data.eastmoney.com/dataapi/bkzj/getbkzj"
_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
_CLS_V1_ROLL_URL = "https://www.cls.cn/v1/roll/get_roll_list"
_CLS_CACHE_URL = "https://www.cls.cn/api/cache"
_CLS_V1_VERSION = "7.7.5"


# ---------------------------------------------------------------------------
# 东财防封：全局节流 + 会话复用 (Eastmoney anti-ban: throttle + Keep-Alive)
# ---------------------------------------------------------------------------
# 东财系 HTTP 接口（datacenter-web / search-api / np-weblist / emweb F10；
# push2/push2his 已于 2026-08-17 随核心路径解耦全部移除）
# 有风控：每秒 >5 次 / 单 IP 并发 ≥10 / 1 分钟 ≥200 次 / 5 分钟 ≥300 次 → 临时封 IP。
# 多 Agent 投研跑批量分析时会高频请求东财，是被封的头号元凶。所有 eastmoney.com
# 请求一律走 _em_get()：串行限流（最小间隔 + 随机抖动）+ 复用 Keep-Alive 会话 + 默认 UA。
# 注意：仅东财接口走此入口；mootdx(TCP) / 腾讯 / 新浪 / 同花顺 / 财联社 / 百度 等
# 不限流（实测不封 IP 或风控极弱）。批量任务可调大 EM_MIN_INTERVAL 进一步降速。
_EM_SESSION = _requests.Session()
# 东财仅直连，不能经过任何代理（含进程级代理、动态代理池与固定隧道）。历史上的
# JULIANGIP_API_URL 动态代理池（v0.2.22）与 QINGGUO_HTTP_PROXY 固定隧道均已移除：
# Free 核心链路不依赖 push2，剩余东财端点（龙虎榜/解禁/F10/新闻）尽力获取、失败按
# [数据缺失] 闭合，不再为东财购买或配置任何代理。
_EM_SESSION.trust_env = False
_EM_SESSION.headers.update({"User-Agent": _UA})
_em_request_lock = threading.Lock()

# 两次东财请求最小间隔(秒)；批量多 Agent 场景可设环境变量 EM_MIN_INTERVAL=1.5~2 降速。
_EM_MIN_INTERVAL = float(os.environ.get("EM_MIN_INTERVAL", "1.0"))
_em_last_call = [0.0]  # 模块级上次东财请求时间戳


class _EastmoneyDataUnavailable(VendorNetworkError, _requests.exceptions.RequestException):
    """东财数据不可用的脱敏异常，不向分析报告泄露代理或网络实现细节。

    Keeps the legacy ``RequestException`` base (callers catch the requests
    exception tuple) while joining the typed vendor error hierarchy.
    """


def _eastmoney_data_missing(label: str, exc: Exception) -> str:
    """记录内部失败原因，并返回供分析师识别的统一数据缺失标记。"""
    logger.warning("东财%s未获取（%s）", label, type(exc).__name__)
    return f"[数据缺失: {label}暂不可用]"


def _eastmoney_source_id(url: str) -> str:
    """Map one Eastmoney URL family to the governed source identifier."""

    host = (urlsplit(str(url)).hostname or "").lower()
    if host.startswith("emweb."):
        return "eastmoney_f10"
    if host.startswith("mobappconfig."):
        return "eastmoney_datacenter"
    if host.startswith("datacenter-web.") or host.startswith("data."):
        return "eastmoney_datacenter"
    return "eastmoney_news"


def _source_call(
    source_id: str,
    operation: str,
    function,
    *,
    attempt_no: int = 1,
    fallback_from: str | None = None,
):
    """Call through the optional Prefetch source context at the I/O boundary."""

    try:
        from .source_context import call_source
    except ImportError:  # pragma: no cover - compatibility with partial installs
        return function()
    return call_source(
        source_id,
        operation,
        function,
        attempt_no=attempt_no,
        fallback_from=fallback_from,
    )


def _source_deadline_error(exc: BaseException) -> bool:
    return exc.__class__.__name__ == "SourceContextDeadlineExceeded"


def _source_retryable_exception(exc: BaseException) -> bool:
    """Return whether one external HTTP attempt may be retried.

    The adapter boundary must not turn parse/programming errors into repeated
    network calls.  A response-status-bearing HTTP error is retryable only for
    5xx; 4xx and structure errors remain single-attempt failures.
    """

    if _source_deadline_error(exc):
        return False
    response = getattr(exc, "response", None)
    status_code = getattr(response, "status_code", None)
    try:
        if status_code is not None:
            status = int(status_code)
            return 500 <= status <= 599
    except (TypeError, ValueError):
        return False
    if isinstance(exc, (TimeoutError, ConnectionError, OSError)):
        return True
    request_exception = getattr(
        getattr(_requests, "exceptions", None), "RequestException", ()
    )
    return bool(request_exception and isinstance(exc, request_exception))


def _source_http_get(
    source_id: str,
    url: str,
    *,
    params=None,
    headers=None,
    timeout=15,
    fallback_from: str | None = None,
    session=None,
    **kwargs,
):
    """Perform one source HTTP request with one bounded network/5xx retry."""

    last_error: Exception | None = None
    for attempt in range(1, 3):
        try:
            request_kwargs = dict(kwargs)
            if params is not None:
                request_kwargs["params"] = params
            if headers is not None:
                request_kwargs["headers"] = headers
            request_kwargs["timeout"] = timeout
            client = session or _requests
            response = _source_call(
                source_id,
                "http_get",
                lambda: client.get(
                    url,
                    **request_kwargs,
                ),
                attempt_no=attempt,
                fallback_from=fallback_from,
            )
        except Exception as exc:
            if _source_deadline_error(exc):
                raise
            last_error = exc
            if attempt < 2 and _source_retryable_exception(exc):
                time.sleep(0.5)
                continue
            raise

        status_code = int(getattr(response, "status_code", 200))
        if status_code >= 500 and attempt < 2:
            time.sleep(0.5)
            continue
        return response

    if last_error is not None:  # pragma: no cover - loop always returns/raises
        raise last_error
    raise RuntimeError("source request did not return")


def _source_http_post(
    source_id: str,
    url: str,
    *,
    data=None,
    headers=None,
    timeout=15,
    fallback_from: str | None = None,
    session=None,
    **kwargs,
):
    """Perform one governed source POST with the same bounded retry rules as GET."""

    last_error: Exception | None = None
    for attempt in range(1, 3):
        try:
            request_kwargs = dict(kwargs)
            if data is not None:
                request_kwargs["data"] = data
            if headers is not None:
                request_kwargs["headers"] = headers
            request_kwargs["timeout"] = timeout
            client = session or _requests
            response = _source_call(
                source_id,
                "http_post",
                lambda: client.post(url, **request_kwargs),
                attempt_no=attempt,
                fallback_from=fallback_from,
            )
        except Exception as exc:
            if _source_deadline_error(exc):
                raise
            last_error = exc
            if attempt < 2 and _source_retryable_exception(exc):
                time.sleep(0.5)
                continue
            raise
        status_code = int(getattr(response, "status_code", 200))
        if status_code >= 500 and attempt < 2:
            time.sleep(0.5)
            continue
        return response
    if last_error is not None:  # pragma: no cover
        raise last_error
    raise RuntimeError("source request did not return")


def _em_get(url, params=None, headers=None, timeout=15, retries=2, **kwargs):
    """东财统一请求入口：自动节流 + 复用 session + 默认 UA + 偶发重试。

    所有 eastmoney.com 接口都应通过它请求，避免多 Agent 高频拉数据被封 IP。
    串行限流：与上次东财请求间隔 < EM_MIN_INTERVAL 时 sleep 补足 + 0.1~0.5s 随机抖动。
    传入的 headers 会覆盖 session 默认 UA（用于保留各端点自己的 Referer/Origin）。
    偶发重试：连接异常（RemoteDisconnected/Timeout/ConnectionError）或 5xx 响应
    最多两次总尝试；429/403 立即失败并交给 SourceGovernor 触发冷却；其他 4xx
    直接返回（接口本身问题不重试，交给调用方处理）。``retries`` 仅保留为
    兼容参数，任何值都不会把总尝试数放宽到两次以上。

    东财仅直连：session 已设 ``trust_env=False``，不继承进程级代理，也不走任何
    动态/固定代理；失败按普通请求失败重试并如实进入数据缺失语义。
    """
    # The graph can execute multiple tool nodes concurrently. Serialise the
    # entire request/retry cycle so the interval really applies to every
    # Eastmoney endpoint.
    total_attempts = min(2, max(1, int(retries)))
    source_id = _eastmoney_source_id(url)
    with _em_request_lock:
        for attempt in range(1, total_attempts + 1):
            wait = _EM_MIN_INTERVAL - (time.time() - _em_last_call[0])
            if wait > 0:
                time.sleep(wait + random.uniform(0.1, 0.5))
            try:
                resp = _source_call(
                    source_id,
                    "http_get",
                    lambda: _EM_SESSION.get(
                        url, params=params, headers=headers, timeout=timeout, **kwargs
                    ),
                    attempt_no=attempt,
                )
                _em_last_call[0] = time.time()
                status_code = int(getattr(resp, "status_code", 200))
                if status_code in {403, 429}:
                    logger.warning("东财请求失败（HTTP %s）", status_code)
                    raise _EastmoneyDataUnavailable("东财数据暂不可用")
                if status_code >= 500 and attempt < total_attempts:
                    time.sleep(0.5 * (2 ** (attempt - 1)))
                    continue
                if status_code >= 500:
                    logger.warning("东财请求失败（HTTP %s）", status_code)
                    raise _EastmoneyDataUnavailable("东财数据暂不可用")
                return resp
            except _EastmoneyDataUnavailable:
                raise
            except Exception as e:
                if _source_deadline_error(e):
                    raise
                _em_last_call[0] = time.time()
                if attempt < total_attempts and _source_retryable_exception(e):
                    time.sleep(0.5 * (2 ** (attempt - 1)))
                    continue
                logger.warning("东财请求失败（%s）", type(e).__name__)
                raise _EastmoneyDataUnavailable("东财数据暂不可用") from None
        raise _EastmoneyDataUnavailable("东财数据暂不可用")


def _eastmoney_datacenter(
    report_name: str,
    columns: str = "ALL",
    filter_str: str = "",
    page_size: int = 50,
    sort_columns: str = "",
    sort_types: str = "-1",
    *,
    strict: bool = False,
) -> list[dict]:
    """东财数据中心统一查询 — 龙虎榜/解禁 共用."""
    params = {
        "reportName": report_name,
        "columns": columns,
        "filter": filter_str,
        "pageNumber": "1",
        "pageSize": str(page_size),
        "sortColumns": sort_columns,
        "sortTypes": sort_types,
        "source": "WEB",
        "client": "WEB",
    }
    r = _em_get(_DATACENTER_URL, params=params, timeout=15)
    d = r.json()
    if strict:
        if not isinstance(d, Mapping):
            raise ValueError("Eastmoney datacenter payload must be an object")
        result = d.get("result")
        if not isinstance(result, Mapping):
            raise ValueError("Eastmoney datacenter result must be an object")
        rows = result.get("data")
        if rows is None:
            return []
        if not isinstance(rows, list):
            raise ValueError("Eastmoney datacenter data must be a list")
        return rows
    if d.get("result") and d["result"].get("data"):
        return d["result"]["data"]
    return []


# ---------------------------------------------------------------------------
# Homepage research examples (Eastmoney concept-board capital flow)
# ---------------------------------------------------------------------------

def _eastmoney_board_flow_rows(scope: str) -> list[dict[str, Any]]:
    """Return board/member rows sorted by today's main net inflow.

    ``m:90+t:3`` is Eastmoney's concept-board universe.  Passing ``b:BKxxxx``
    switches the same endpoint to that board's constituent stocks.  This is
    intentionally kept separate from the analysis fund-flow tool: homepage
    examples are current-only discovery data, not report evidence.
    """
    response = _em_get(
        _EASTMONEY_BOARD_FLOW_URL,
        params={"key": "f62", "code": scope},
        headers={"Referer": "https://data.eastmoney.com/bkzj/gn.html"},
        timeout=10,
        retries=3,
    )
    response.raise_for_status()
    payload = response.json()
    data = payload.get("data") if isinstance(payload, dict) else None
    raw_rows = data.get("diff") if isinstance(data, dict) else None
    if not isinstance(raw_rows, list):
        raise ValueError("Eastmoney board-flow payload is empty")

    rows: list[dict[str, Any]] = []
    for raw in raw_rows:
        if not isinstance(raw, dict):
            continue
        code = str(raw.get("f12") or "").strip()
        name = str(raw.get("f14") or "").strip()
        net_inflow = _quote_number(raw.get("f62"))
        if not code or not name or net_inflow is None:
            continue
        rows.append(
            {
                "code": code,
                "name": name,
                "net_inflow": net_inflow,
            }
        )
    if not rows:
        raise ValueError("Eastmoney board-flow rows are empty")
    return sorted(rows, key=lambda item: item["net_inflow"], reverse=True)


def get_hot_concept_examples(top_n: int = 3) -> list[dict[str, Any]]:
    """Pick current homepage examples from concept-board fund inflows.

    Boards are ranked by today's main net inflow.  For each selected board,
    the constituent with the highest same-day main net inflow is used as the
    representative stock.  The function raises when Eastmoney data is not
    usable so the Web layer can make the failure explicit and use its static
    fallback without confusing it with an empty market result.
    """
    if top_n < 1:
        return []

    boards = _eastmoney_board_flow_rows("m:90+t:3")
    examples: list[dict[str, Any]] = []
    used_stock_codes: set[str] = set()
    retrieved_at = datetime.now(_MARKET_TZ).isoformat(timespec="minutes")

    # A malformed/empty board member response should not prevent the next
    # ranked board from supplying an example.  Limit the probe window so a
    # transient provider problem cannot make the homepage wait indefinitely.
    for board in boards[: max(top_n + 3, top_n)]:
        board_code = board["code"]
        if not _re.fullmatch(r"BK\d{4}", board_code):
            continue
        try:
            members = _eastmoney_board_flow_rows(f"b:{board_code}")
        except Exception as exc:  # optional homepage enrichment
            logger.warning(
                "东财概念板块成分股未获取（%s）：%s",
                board_code,
                type(exc).__name__,
            )
            continue
        member = next(
            (
                item
                for item in members
                if _re.fullmatch(r"\d{6}", str(item.get("code") or ""))
                and str(item.get("code")) not in used_stock_codes
            ),
            None,
        )
        if member is None:
            continue
        examples.append(
            {
                "board_code": board_code,
                "board_name": board["name"],
                "board_net_inflow": board["net_inflow"],
                "stock_code": member["code"],
                "stock_name": member["name"],
                "stock_net_inflow": member["net_inflow"],
                "retrieved_at": retrieved_at,
                "source": "eastmoney_concept_fund_flow",
            }
        )
        used_stock_codes.add(member["code"])
        if len(examples) >= top_n:
            break

    if len(examples) < top_n:
        raise ValueError(
            "Eastmoney returned fewer usable concept-board examples than requested"
        )
    return examples


# ---------------------------------------------------------------------------
# 同花顺 EPS forecast helper (direct HTTP, no akshare)
# ---------------------------------------------------------------------------


def _ths_eps_forecast(code: str) -> pd.DataFrame:
    """Fetch consensus EPS forecast from 同花顺 (direct HTTP).

    Returns DataFrame with columns roughly: 年度, 预测机构数, 最小值, 均值, 最大值.
    """
    url = f"https://basic.10jqka.com.cn/new/{code}/worth.html"
    headers = {
        "User-Agent": _UA,
        "Referer": "https://basic.10jqka.com.cn/",
    }
    r = _source_http_get("ths", url, headers=headers, timeout=15)
    if hasattr(r, "raise_for_status"):
        r.raise_for_status()
    r.encoding = "gbk"
    dfs = pd.read_html(io.StringIO(r.text))
    # Find the table containing EPS data
    for df in dfs:
        cols = [str(c) for c in df.columns]
        if any("每股收益" in c or "均值" in c for c in cols):
            return df
    # Fallback: return first table if exists
    return dfs[0] if dfs else pd.DataFrame()


# ---------------------------------------------------------------------------
# Sina K-line fallback helper (direct HTTP, no akshare)
# ---------------------------------------------------------------------------


def _sina_kline_fallback(
    code: str,
    start_date: str = None,
    end_date: str = None,
    *,
    fallback_from: str | None = None,
) -> pd.DataFrame:
    """Fetch daily K-line from Sina HTTP API as mootdx fallback.

    Returns DataFrame with columns: Date, Open, High, Low, Close, Volume.
    """
    prefix = _get_prefix(code)
    url = (
        "http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/"
        "CN_MarketData.getKLineData"
    )
    params = {
        "symbol": f"{prefix}{code}",
        "scale": "240",  # daily
        "ma": "no",
        "datalen": "800",
    }
    r = _source_http_get(
        "sina", url, params=params, timeout=15, fallback_from=fallback_from
    )
    if hasattr(r, "raise_for_status"):
        r.raise_for_status()
    data = _json.loads(r.text)

    if not data:
        return pd.DataFrame()

    rows = []
    for item in data:
        rows.append({
            "Date": item["day"],
            "Open": float(item["open"]),
            "High": float(item["high"]),
            "Low": float(item["low"]),
            "Close": float(item["close"]),
            "Volume": int(item["volume"]),
        })

    df = pd.DataFrame(rows)
    df["Date"] = pd.to_datetime(df["Date"])

    if start_date:
        df = df[df["Date"] >= pd.to_datetime(start_date)]
    if end_date:
        df = df[df["Date"] <= pd.to_datetime(end_date)]

    return df


def _last_ohlcv_date(df: pd.DataFrame) -> pd.Timestamp | None:
    """Return the latest OHLCV Date in a normalized dataframe."""
    if df is None or df.empty or "Date" not in df.columns:
        return None
    dates = pd.to_datetime(df["Date"], errors="coerce")
    if dates.dropna().empty:
        return None
    return dates.max().normalize()


_OHLCV_MAX_STALENESS_DAYS = 14


def _ohlcv_coverage(df: pd.DataFrame, target_date: str) -> dict[str, Any]:
    """Describe whether an OHLCV frame reaches the requested cutoff date.

    A provider can return a non-empty but stale frame. Treating that frame as
    success is worse than returning no data because downstream indicators then
    describe the wrong historical window. The tolerance is calendar-based to
    cover weekends and ordinary exchange holidays without adding a calendar
    dependency to the vendor boundary.
    """
    target = pd.to_datetime(target_date).normalize()
    observed = _last_ohlcv_date(df)
    if observed is None:
        return {
            "requested_end": target.strftime("%Y-%m-%d"),
            "observed_max": None,
            "gap_days": None,
            "stale": True,
        }
    gap_days = max((target - observed).days, 0)
    return {
        "requested_end": target.strftime("%Y-%m-%d"),
        "observed_max": observed.strftime("%Y-%m-%d"),
        "gap_days": gap_days,
        "stale": gap_days > _OHLCV_MAX_STALENESS_DAYS,
    }


def _stale_ohlcv_message(code: str, coverage: Mapping[str, Any]) -> str:
    """Return a stable, response-safe failure marker for stale OHLCV data."""
    logger.warning(
        "OHLCV coverage stale for %s: requested_end=%s observed_max=%s gap_days=%s",
        code,
        coverage.get("requested_end"),
        coverage.get("observed_max"),
        coverage.get("gap_days"),
    )
    return (
        "[数据缺失] historical_ohlcv_stale: "
        f"{code} requested_end={coverage.get('requested_end')} "
        f"observed_max={coverage.get('observed_max')} "
        f"gap_days={coverage.get('gap_days')}"
    )


def _normalize_ohlcv_dates(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize OHLCV Date values to daily granularity."""
    if df is None or df.empty or "Date" not in df.columns:
        return df
    df = df.copy()
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce").dt.normalize()
    return df.dropna(subset=["Date"])


def _normalize_mootdx_bars_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize a mootdx bars frame without trusting its datetime column.

    ``mootdx.utils.to_data`` eagerly parses the wire ``datetime`` string.  A
    corrupted TDX response can therefore raise before this module gets a
    chance to apply ``errors='coerce'``.  This helper is used for the normal
    DataFrame path and for the raw-response recovery path below.
    """
    if df is None or df.empty:
        raise ValueError("No OHLCV data from mootdx")

    frame = df.copy()
    if "Date" not in frame.columns:
        frame = frame.drop(
            columns=["datetime", "year", "month", "day", "hour", "minute"],
            errors="ignore",
        ).reset_index()
        frame = frame.rename(
            columns={
                "index": "Date",
                "datetime": "Date",
                "open": "Open",
                "close": "Close",
                "high": "High",
                "low": "Low",
                "volume": "Volume",
                "vol": "Volume",
                "amount": "Amount",
            }
        )
    else:
        frame = frame.rename(
            columns={
                "open": "Open",
                "close": "Close",
                "high": "High",
                "low": "Low",
                "volume": "Volume",
                "vol": "Volume",
                "amount": "Amount",
            }
        )

    required = ["Date", "Open", "High", "Low", "Close", "Volume"]
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise ValueError(
            "mootdx OHLCV response missing columns: " + ", ".join(missing)
        )
    # TDX responses can carry both ``vol`` and ``volume`` (identical values);
    # renaming both to ``Volume`` yields duplicate labels that pandas 3.x
    # refuses to concat/reindex downstream (cache-miss path regression).
    frame = frame.loc[:, ~frame.columns.duplicated(keep="first")]
    frame = _normalize_ohlcv_dates(frame[required])
    if frame.empty:
        raise ValueError("mootdx OHLCV response contained no valid dates")
    return frame


def _normalize_mootdx_raw_bars(rows: object) -> pd.DataFrame:
    """Build OHLCV rows from raw TDX fields, dropping malformed timestamps."""
    frame = pd.DataFrame(rows)
    if frame.empty:
        raise ValueError("No raw OHLCV data from mootdx")

    date_fields = ("year", "month", "day", "hour", "minute")
    if not all(field in frame.columns for field in date_fields):
        raise ValueError("mootdx raw OHLCV response missing date fields")

    parts = {
        field: pd.to_numeric(frame[field], errors="coerce")
        .astype("Int64")
        .astype("string")
        for field in date_fields
    }
    date_text = (
        parts["year"]
        + "-"
        + parts["month"].str.zfill(2)
        + "-"
        + parts["day"].str.zfill(2)
        + " "
        + parts["hour"].str.zfill(2)
        + ":"
        + parts["minute"].str.zfill(2)
    )
    frame["Date"] = pd.to_datetime(
        date_text,
        format="%Y-%m-%d %H:%M",
        errors="coerce",
    )
    return _normalize_mootdx_bars_frame(frame)


def _fetch_mootdx_bars(code: str, offset: int = 800) -> pd.DataFrame:
    """Fetch and normalize mootdx bars, recovering malformed wire dates."""
    client = _get_mootdx_client()
    try:
        return _normalize_mootdx_bars_frame(
            _mootdx_call("bars", symbol=code, category=4, offset=offset)
        )
    except Exception as exc:
        message = str(exc).lower()
        if "year must be in 1..9999" not in message:
            # 服务器挂了/取数失败：弃用当前 client，让下一次调用重选（#90）。
            reset_mootdx_client()
            raise

        raw_client = getattr(client, "client", None)
        if raw_client is None:
            raise
        try:
            from mootdx.utils import get_stock_market

            rows = _source_call(
                "mootdx",
                "get_security_bars",
                lambda: raw_client.get_security_bars(
                    9,
                    get_stock_market(code),
                    code,
                    0,
                    min(int(offset), 800),
                ),
            )
            recovered = _normalize_mootdx_raw_bars(rows)
        except Exception as raw_exc:
            reset_mootdx_client()
            raise ValueError(
                "mootdx returned malformed timestamps and raw recovery failed"
            ) from raw_exc
        logger.warning(
            "mootdx returned malformed timestamps for %s; dropped invalid rows "
            "and recovered %d valid rows",
            code,
            len(recovered),
        )
        return recovered


def _needs_sina_supplement(df: pd.DataFrame, target_date: str | None) -> bool:
    """True when mootdx/cache data is older than the requested cutoff date."""
    if not target_date:
        return False
    last_date = _last_ohlcv_date(df)
    if last_date is None:
        return True
    target = pd.to_datetime(target_date).normalize()
    return last_date < target


def _merge_ohlcv(primary: pd.DataFrame, supplement: pd.DataFrame) -> pd.DataFrame:
    """Merge OHLCV frames, preferring supplement rows on duplicate dates."""
    frames = [frame for frame in (primary, supplement) if frame is not None and not frame.empty]
    if not frames:
        return pd.DataFrame(columns=["Date", "Open", "High", "Low", "Close", "Volume"])
    combined = pd.concat(frames, ignore_index=True)
    combined = _normalize_ohlcv_dates(combined)
    combined = combined.drop_duplicates(subset=["Date"], keep="last")
    combined = combined.sort_values("Date").reset_index(drop=True)
    return combined


def _supplement_stale_ohlcv_with_sina(
    code: str,
    df: pd.DataFrame,
    target_date: str | None,
    start_date: str | None = None,
) -> tuple[pd.DataFrame, bool]:
    """Use Sina daily K-line to fill dates missing from mootdx/cache data."""
    if not _needs_sina_supplement(df, target_date):
        return df, False
    try:
        sina_df = _sina_kline_fallback(code, start_date, target_date)
    except Exception as e:
        logger.warning("sina K-line supplement failed for %s: %s", code, e)
        return df, False
    if sina_df.empty:
        return df, False
    merged = _merge_ohlcv(df, sina_df)
    return merged, _last_ohlcv_date(merged) != _last_ohlcv_date(df)


def _calendar_reference_last_bar(end_date: str | None = None) -> str | None:
    """请求窗口内"市场最新交易日"参考；不可用返回 None（DEC-P1-27）。

    只用于把"包未刷新"与"市场确实没有更新交易日"区分开——例如黄金周期间
    本地最后一根 bar 就是市场最新 session，日历日差值不应触发 mootdx→新浪
    回落。请求截止日在日历覆盖内时取该日之前最近的交易日（历史窗口的假期
    中段），否则取市场已确认的最新 bar。日历是支持性能力，任何失败返回
    None，调用方保持既有日历日阈值规则；结果在进程内按日缓存。
    """
    try:
        from .trading_calendar import (
            latest_trading_day_on_or_before,
            load_trading_calendar,
        )

        calendar = load_trading_calendar()
        if calendar is None:
            return None
        if end_date:
            cutoff = str(end_date)[:10]
            if (
                calendar.last_bar_date is not None
                and cutoff <= calendar.last_bar_date
            ):
                return latest_trading_day_on_or_before(calendar, cutoff)
        return calendar.last_bar_date
    except Exception:  # noqa: BLE001 - supportive capability must not break reads
        return None


def _load_vipdoc_ohlcv_frame(
    code: str, start_date: str, end_date: str
) -> pd.DataFrame | None:
    """Load raw daily bars from the local official TDX vipdoc package.

    Local-first base for the ``adjust="raw"`` / ``period="D"`` path so history
    no longer depends on the public HQ 7709 pool (issues/023).  Returns
    ``None`` — falling back to the existing mootdx → Sina chain — when the
    layer is disabled, the tree/file is missing, the requested window has no
    local rows, or the local last bar lags the requested end by more than
    ``vipdoc_history_max_staleness_days``.  Read-only, zero network (the
    trading calendar's own cached fallback may consult the online chain; it
    never triggers a per-stock online fetch).

    DEC-P1-27: when the calendar-day gap trips the threshold but the trading
    calendar confirms the local package already reaches the market's latest
    session (e.g. a long holiday), the local frame is kept instead of falling
    back to the online chain.

    The ``Amount`` column the reader parses is intentionally dropped here:
    the public ``get_stock_data`` column contract is
    Date/Open/High/Low/Close/Volume.
    """
    try:
        from .config import get_config

        cfg = get_config()
    except Exception:  # pragma: no cover - config failure must not kill the chain
        return None
    if not cfg.get("vipdoc_history_enabled", True):
        return None
    try:
        max_staleness = float(cfg.get("vipdoc_history_max_staleness_days", 5))
    except (TypeError, ValueError):
        max_staleness = 5.0
    try:
        from .vipdoc_history import load_vipdoc_daily

        frame = load_vipdoc_daily(code, start_date, end_date)
    except Exception as exc:  # noqa: BLE001 - a local read failure must degrade
        logger.warning("vipdoc history read failed for %s: %s", code, exc)
        return None
    if frame is None or frame.empty:
        return None
    last = _last_ohlcv_date(frame)
    if last is None:
        return None
    target = pd.to_datetime(end_date).normalize()
    if (target - last).days > max_staleness:
        reference = _calendar_reference_last_bar(end_date)
        if reference is not None:
            try:
                reference_stamp = pd.to_datetime(reference).normalize()
            except (TypeError, ValueError):
                reference_stamp = None
            if reference_stamp is not None and last >= reference_stamp:
                logger.info(
                    "vipdoc history for %s ends %s; the trading calendar "
                    "confirms no newer session than the requested %s, keeping "
                    "the local frame",
                    code,
                    last.date(),
                    end_date,
                )
                columns = ["Date", "Open", "High", "Low", "Close", "Volume"]
                return frame[columns].reset_index(drop=True)
        logger.info(
            "vipdoc history for %s ends %s, more than %s days behind requested %s; "
            "using the online mootdx -> sina chain",
            code,
            last.date(),
            max_staleness,
            end_date,
        )
        return None
    columns = ["Date", "Open", "High", "Low", "Close", "Volume"]
    return frame[columns].reset_index(drop=True)


# ---------------------------------------------------------------------------
# OHLCV loading with cache (mootdx -> CSV)
# ---------------------------------------------------------------------------

def _load_ohlcv_astock(symbol: str, curr_date: str) -> pd.DataFrame:
    """Fetch OHLCV via mootdx, cache to CSV, filter by curr_date.

    Mirrors stockstats_utils.load_ohlcv but uses mootdx instead of yfinance.
    Returns DataFrame with columns: Date, Open, High, Low, Close, Volume
    """
    from .config import get_config

    code = _normalize_ticker(symbol)
    config = get_config()
    cache_dir = config.get(
        "data_cache_dir", os.path.expanduser("~/.chstockdata/cache")
    )
    os.makedirs(cache_dir, exist_ok=True)

    cache_file = os.path.join(cache_dir, f"{code}-astock-daily.csv")

    if os.path.exists(cache_file):
        mtime = datetime.fromtimestamp(os.path.getmtime(cache_file))
        if mtime.date() == datetime.now().date():
            data = pd.read_csv(cache_file, on_bad_lines="skip", encoding="utf-8")
            data = _normalize_ohlcv_dates(data)
            data, supplemented = _supplement_stale_ohlcv_with_sina(
                code, data, curr_date, start_date=None
            )
            if supplemented:
                data.to_csv(cache_file, index=False, encoding="utf-8")
            cutoff = pd.to_datetime(curr_date)
            data = data[data["Date"] <= cutoff]
            coverage = _ohlcv_coverage(data, curr_date)
            if coverage["stale"]:
                raise ValueError(_stale_ohlcv_message(code, coverage))
            return data

    # Fetch from mootdx — 800 daily bars (~3 years of trading days)
    try:
        df = _fetch_mootdx_bars(code, offset=800)
    except Exception as e:
        logger.warning("mootdx OHLCV failed for %s: %s, trying sina HTTP fallback", code, e)
        # Fallback: Sina direct HTTP API
        try:
            df = _sina_kline_fallback(code, fallback_from="mootdx")
            if df.empty:
                raise ValueError(f"No OHLCV data from sina for {code}")
        except Exception:
            raise ValueError(f"No OHLCV data from mootdx/sina for {code}")

    df, _ = _supplement_stale_ohlcv_with_sina(code, df, curr_date, start_date=None)

    # Cache to disk
    df.to_csv(cache_file, index=False, encoding="utf-8")

    # Filter by curr_date to prevent look-ahead bias
    cutoff = pd.to_datetime(curr_date)
    df = df[df["Date"] <= cutoff]
    coverage = _ohlcv_coverage(df, curr_date)
    if coverage["stale"]:
        raise ValueError(_stale_ohlcv_message(code, coverage))
    return df


def get_ohlcv_frame_cached(symbol: str, curr_date: str) -> pd.DataFrame:
    """Public OHLCV DataFrame accessor for internal consumers.

    Delegates to the cached mootdx→Sina path (``_load_ohlcv_astock``): the
    returned frame carries Date/Open/High/Low/Close/Volume rows filtered to
    ``<= curr_date``, and the daily CSV cache is written/refreshed as a side
    effect.  Raises ``ValueError`` on stale coverage (tolerance is calendar
    based — weekends and ordinary holidays are covered, see
    ``_OHLCV_MAX_STALENESS_DAYS``).  Tool-facing callers should keep using
    ``get_stock_data`` (formatted text); this wrapper exists for code that
    needs the raw frame, e.g. the background memory settlement task.
    """
    return _load_ohlcv_astock(symbol, curr_date)


# ===========================================================================
# 9 Vendor Methods (matching interface.py VENDOR_METHODS signatures)
# ===========================================================================


# ---- 1. get_stock_data ----

# Default set of common indicators for merged data+indicators output
_COMMON_INDICATORS = [
    "close_10_ema", "close_50_sma", "macd", "macds", "macdh",
    "rsi", "boll", "boll_ub", "boll_lb", "vwma",
]


def _compute_and_format_indicators(
    code: str,
    end_date: str,
    ind_names: list[str],
    look_back: int = 60,
    *,
    daily_bars: pd.DataFrame | None = None,
    daily_source: str | None = None,
    qfq_bars=None,
) -> str:
    """Compute trend indicators from one explicit QFQ daily price series.

    The enclosing tool keeps raw OHLCV separate for actual-price use.  Passing
    its already-fetched raw frame avoids a second provider read; any QFQ
    failure is rendered as a limitation instead of silently falling back to
    unadjusted trend indicators.
    """
    try:
        from stockstats import wrap

        from .adjusted_bars import ADJUST_QFQ, PERIOD_DAILY, get_adjusted_bars

        raw = daily_bars if daily_bars is not None else _load_ohlcv_astock(code, end_date)
        if raw is None or raw.empty:
            raise ValueError("原始日线为空")
        adjusted = qfq_bars or get_adjusted_bars(
            code,
            str(pd.to_datetime(raw["Date"]).min())[:10],
            end_date,
            adjust=ADJUST_QFQ,
            period=PERIOD_DAILY,
            daily_bars=raw,
            daily_source=daily_source,
        )
        df = adjusted.frame
        ind_data = wrap(df)
        ind_data["Date"] = ind_data["Date"].apply(
            lambda x: x.strftime("%Y-%m-%d") if hasattr(x, "strftime") else str(x)
        )

        anchor = adjusted.anchor_date or "无除权事件（QFQ 退化为原始序列）"
        lines = [
            "\n\n## Technical Indicators",
            "",
            "# Technical price basis: QFQ（前复权，仅趋势/指标；非可成交价格）",
            f"# QFQ anchor: {anchor}",
            f"# Factor source: {adjusted.factor_source or '无除权事件'}",
        ]
        if adjusted.limitations:
            lines.append("# QFQ limitations: " + "; ".join(adjusted.limitations))

        # --- latest-value summary table ---
        lines.append("| Indicator | Latest | Description |")
        lines.append("|-----------|--------|-------------|")
        for name in ind_names:
            try:
                latest = ind_data[name].iloc[-1]
                val = "N/A" if pd.isna(latest) else f"{float(latest):.4f}"
                desc = _INDICATOR_DESCRIPTIONS.get(name, "")
                lines.append(f"| {name} | {val} | {desc} |")
            except Exception:
                pass

        # --- recent trend (last N rows) ---
        recent = ind_data.tail(look_back)
        trend_cols = [c for c in ind_names if c in recent.columns]
        if trend_cols:
            lines.append(f"\n### Recent {look_back}-Day Trend")
            lines.append(
                recent[["Date"] + trend_cols]
                .round(4)
                .to_csv(index=False)
                .strip()
            )
        return "\n".join(lines)
    except Exception as exc:
        logger.warning("QFQ indicator computation failed for %s: %s", code, exc)
        return (
            "\n\n## Technical Indicators\n\n"
            "# [数据缺失] qfq_adjustment_unavailable: "
            f"{type(exc).__name__}；未使用原始价格替代趋势指标\n"
        )


def get_stock_data(
    symbol: Annotated[str, "A-stock code (e.g. 688017, SH688017)"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
    indicators: Annotated[
        str,
        "Optional: compute technical indicators together with price data. "
        "Use 'all' for common indicators (close_10_ema, close_50_sma, macd, "
        "macds, macdh, rsi, boll, boll_ub, boll_lb, vwma), or a comma-separated "
        "list: close_50_sma, close_200_sma, close_10_ema, macd, macds, macdh, "
        "rsi, boll, boll_ub, boll_lb, atr, vwma, mfi",
    ] = "",
    adjust: Annotated[
        str,
        "Price basis: raw for actual historical prices, qfq for trend analysis, or hfq for historical adjusted analysis",
    ] = "raw",
    period: Annotated[str, "Bar period: D (daily), W (weekly), or M (monthly)"] = "D",
) -> str:
    """Get raw/QFQ/HFQ OHLCV and optional QFQ trend indicators.

    ``raw`` is the only basis suitable for actual historical trading prices.
    ``qfq``/``hfq`` transform only OHLC; volume and amount retain their source
    units.  Weekly/monthly bars are aggregated from the same requested daily
    basis and carry completeness metadata.
    """
    code = _normalize_ticker(symbol)
    adjust = str(adjust or "raw").strip().lower()
    period = str(period or "D").strip().upper()

    data_source = "mootdx (TCP)"
    df: pd.DataFrame | None = None
    if adjust == "raw" and period == "D":
        # issues/023 方案 A：raw/D 主路径优先本地官方 vipdoc 包，不触发 mootdx
        # 全表探测（公共 HQ 池会周期性整体失效）。
        df = _load_vipdoc_ohlcv_frame(code, start_date, end_date)
        if df is not None:
            data_source = "vipdoc local (TDX official hsjday package)"
    if df is None:
        try:
            df = _fetch_mootdx_bars(code, offset=800)

        except Exception as e:
            logger.warning("mootdx K-line failed for %s: %s, trying sina HTTP fallback", code, e)
            # Fallback: Sina direct HTTP API
            try:
                df = _sina_kline_fallback(
                    code, start_date, end_date, fallback_from="mootdx"
                )
                if df.empty:
                    return "K线数据获取失败：mootdx和新浪备用源均不可用，请检查网络连接"
                data_source = "sina HTTP (fallback)"
            except Exception:
                return "K线数据获取失败：mootdx和新浪备用源均不可用，请检查网络连接"

    df, supplemented = _supplement_stale_ohlcv_with_sina(code, df, end_date, start_date)
    if supplemented:
        data_source = f"{data_source} + sina HTTP supplement"

    # Filter raw provider data once.  Both the public bar output and QFQ
    # indicators below derive from this exact raw frame, never a second fetch.
    start_dt = pd.to_datetime(start_date)
    end_dt = pd.to_datetime(end_date)
    df = df[(df["Date"] >= start_dt) & (df["Date"] <= end_dt)]

    if df.empty:
        return (
            f"No data found for A-stock '{code}' "
            f"between {start_date} and {end_date}"
        )

    coverage = _ohlcv_coverage(df, end_date)
    if coverage["stale"]:
        return _stale_ohlcv_message(code, coverage)

    raw_df = df.copy()
    adjusted_result = None
    if adjust != "raw" or period != "D":
        try:
            from .adjusted_bars import get_adjusted_bars

            adjusted_result = get_adjusted_bars(
                code,
                start_date,
                end_date,
                adjust=adjust,
                period=period,
                daily_bars=raw_df,
                daily_source=data_source,
            )
            df = adjusted_result.frame.copy()
        except Exception as exc:
            return (
                "[数据缺失] adjusted_ohlcv_unavailable: "
                f"{adjust.upper()}/{period} 未生成（{type(exc).__name__}）；"
                "原始行情未被标记为已复权"
            )

    for col in ["Open", "High", "Low", "Close"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").round(2)

    observed_min = pd.to_datetime(df["Date"], errors="coerce").min()
    display_df = df.copy()
    for col in ("Date", "period_start"):
        if col in display_df.columns:
            display_df[col] = pd.to_datetime(display_df[col], errors="coerce").dt.strftime("%Y-%m-%d")
    csv_columns = [
        column for column in (
            "Date", "period_start", "Open", "High", "Low", "Close", "Volume",
            "Amount", "trade_days", "complete",
        ) if column in display_df.columns
    ]
    csv_out = display_df[csv_columns].to_csv(index=False)

    header = f"# Stock data for {code} (A-stock) from {start_date} to {end_date}\n"
    header += f"# Total records: {len(df)}\n"
    header += f"# Data source: {data_source}\n"
    if adjusted_result is None:
        header += "# Price basis: RAW（对应日期实际历史价格；除权跳变未消除）\n"
        header += "# Period: D\n"
    else:
        header += f"# Price basis: {adjust.upper()}（仅趋势/指标，非可成交真实价格）\n"
        header += f"# Period: {period}\n"
        header += f"# Factor source: {adjusted_result.factor_source or 'raw'}\n"
        if adjusted_result.anchor_date:
            header += f"# QFQ anchor: {adjusted_result.anchor_date}\n"
        if adjusted_result.limitations:
            header += "# Limitations: " + "; ".join(adjusted_result.limitations) + "\n"
    header += (
        f"# Observed date range: {observed_min.strftime('%Y-%m-%d')} "
        f"to {coverage['observed_max']}\n"
    )
    header += (
        f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    )

    result = header + csv_out

    # Append technical indicators when requested
    if indicators and indicators.strip():
        ind_str = indicators.strip().lower()
        if ind_str == "all":
            ind_names = _COMMON_INDICATORS
        else:
            ind_names = [n.strip() for n in ind_str.split(",")]

        qfq_daily = adjusted_result if adjust == "qfq" and period == "D" else None
        ind_block = _compute_and_format_indicators(
            code,
            end_date,
            ind_names,
            daily_bars=raw_df,
            daily_source=data_source,
            qfq_bars=qfq_daily,
        )
        if ind_block:
            result += ind_block

    return result


# Supported technical indicators with descriptions (shared by get_stock_data)
_INDICATOR_DESCRIPTIONS = {
    "close_50_sma": "50 SMA: Medium-term trend indicator.",
    "close_200_sma": "200 SMA: Long-term trend benchmark.",
    "close_10_ema": "10 EMA: Responsive short-term average.",
    "macd": "MACD: Momentum via EMA differences.",
    "macds": "MACD Signal: EMA smoothing of MACD line.",
    "macdh": "MACD Histogram: Gap between MACD and signal.",
    "rsi": "RSI: Momentum overbought/oversold indicator (70/30 thresholds).",
    "boll": "Bollinger Middle: 20 SMA basis for Bollinger Bands.",
    "boll_ub": "Bollinger Upper Band: 2 std devs above middle.",
    "boll_lb": "Bollinger Lower Band: 2 std devs below middle.",
    "atr": "ATR: Average True Range volatility measure.",
    "vwma": "VWMA: Volume-weighted moving average.",
    "mfi": "MFI: Money Flow Index (volume + price momentum).",
}


# ---- 3. get_fundamentals ----


def _get_close_on_date(code, date_str):
    """取指定日期收盘价。复用 get_stock_data（mootdx + 新浪 fallback），与技术分析同源。
    找不到返回 None。"""
    try:
        out = get_stock_data(code, date_str, date_str)
        if not out or "Close" not in out:
            return None
        for line in reversed(out.splitlines()):
            line = line.strip()
            if not line or line.startswith("#") or "," not in line:
                continue
            parts = line.split(",")
            if len(parts) >= 5 and parts[4] not in ("Close", ""):
                try:
                    return float(parts[4])
                except ValueError:
                    continue
        return None
    except Exception:
        return None


def _resolve_price(code, curr_date, realtime_price, historical_review=None):
    """股价对齐：curr_date 早于今日时返回该日收盘价（与技术分析基准日一致），
    否则返回实时价。历史收盘缺失时绝不回退到今天的实时价。"""
    if historical_review is None:
        historical_review = is_historical_analysis(curr_date, as_of_date=_today())
    if historical_review:
        d = str(curr_date)[:10]
        close = _get_close_on_date(code, d)
        if close is not None:
            return close, f"close on {d}"
        return None, f"historical close unavailable on {d}"
    # 实时价守卫：过滤掉 0 / None（停牌、僵尸报价、腾讯返回空载荷时常见），
    # 避免把无效价当真实价喂给估值计算。僵尸报价本身由 _tencent_quote 的 is_stale 标记，
    # 这里只做通用的数值有效性兜底。
    if realtime_price is not None and realtime_price > 0:
        return realtime_price, "realtime"
    return None, "realtime unavailable"


def get_fundamentals(
    ticker: Annotated[str, "A-stock code"],
    curr_date: Annotated[str, "current date"] = None,
    historical_review: bool | None = None,
) -> str:
    """Get fundamentals without presenting current snapshots as historical facts."""
    code = _normalize_ticker(ticker)
    historical = (
        is_historical_analysis(curr_date, as_of_date=_today())
        if historical_review is None
        else historical_review
    )

    try:
        lines = []

        def _record_provider_failure(provider: str, exc: Exception) -> None:
            """Expose a recoverable provider failure without logging request details."""
            error_type = type(exc).__name__
            logger.warning("%s failed for %s: %s", provider, code, error_type)
            lines.append(f"{provider}源失败：{error_type}（详情已隐藏）")

        # --- Free real-time quote chain: Tencent → mootdx → Sina ---
        # 腾讯不提供历史估值快照的公告/观测时间；历史分析仅使用独立日线得到的收盘价。
        try:
            tq = _get_realtime_quotes([code])
            if code in tq:
                q = tq[code]
                price_val, price_src = _resolve_price(
                    code, curr_date, q.get("price"), historical
                )
                lines.append(f"Name: {q.get('name') or code}")
                lines.append(f"Quote source: {q.get('source', 'unknown')}")
                if price_val is not None:
                    lines.append(f"Price: {price_val} ({price_src})")
                if not historical:
                    optional_fields = (
                        ("pe_ttm", "PE (TTM)", ""),
                        ("pe_static", "PE (Static)", ""),
                        ("pb", "PB", ""),
                        ("mcap_yi", "Market Cap (100M CNY)", ""),
                        ("float_mcap_yi", "Float Market Cap (100M CNY)", ""),
                        ("turnover_pct", "Turnover Rate", "%"),
                        ("change_pct", "Change", "%"),
                        ("limit_up", "Limit Up", ""),
                        ("limit_down", "Limit Down", ""),
                    )
                    for field, label, suffix in optional_fields:
                        value = q.get(field)
                        if value is not None:
                            lines.append(f"{label}: {value}{suffix}")
        except Exception as e:
            _record_provider_failure("实时行情降级链", e)

        if historical:
            lines.append(point_in_time_unavailable_message(
                "腾讯实时估值、mootdx 财务快照、东方财富 F10 股本市值和同花顺一致预期"
            ))
            header = f"# Company Fundamentals for {code} (A-stock)\n"
            header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            return header + "\n".join(lines)

        # --- mootdx: financial snapshot (F10 概况，字段为拼音缩写) ---
        # 注意：mootdx client.finance() 返回的是 F10 公司概况，列名为拼音缩写
        # (jinglirun=净利润 / zhuyingshouru=主营收入 / meigujingzichan=每股净资产 ...)，
        # 并无 eps/roe 英文字段；EPS/ROE 需由净利润÷股本、净利润÷净资产 推算。
        # 金额字段在 TDX 7709 协议里以 0.1 元（角）计，mootdx 原样透传：直接按元渲染
        # 会放大 10 倍（600519 实测：raw 907032640000 → /10 = 907.03 亿，与新浪
        # 2026-06-30 期营收一致；000858 同样核对通过）。股本/每股字段单位正确，不缩放。
        try:
            fin = _mootdx_call("finance", symbol=code)
            if fin is not None and not (
                isinstance(fin, pd.DataFrame) and fin.empty
            ):
                row = fin.iloc[0] if isinstance(fin, pd.DataFrame) else fin
                _AMOUNT_FIELDS_0_1_YUAN = frozenset({
                    "zhuyingshouru", "jinglirun", "yingyelirun", "lirunzonghe",
                    "shuihoulirun", "jingyingxianjinliu", "zongxianjinliu",
                    "zongzichan", "jingzichan", "cunhuo",
                })
                field_map = {
                    "zongguben": "Total Shares (总股本)",
                    "liutongguben": "Float Shares (流通股本)",
                    "zhuyingshouru": "Revenue (主营收入)",
                    "jinglirun": "Net Profit (净利润)",
                    "yingyelirun": "Operating Profit (营业利润)",
                    "lirunzonghe": "Total Profit (利润总额)",
                    "shuihoulirun": "After-tax Profit (税后利润)",
                    "meigujingzichan": "Book Value Per Share (每股净资产)",
                    "jingyingxianjinliu": "Operating Cash Flow (经营现金流)",
                    "zongxianjinliu": "Total Cash Flow (总现金流)",
                    "zongzichan": "Total Assets (总资产)",
                    "jingzichan": "Net Assets (净资产)",
                    "cunhuo": "Inventory (存货)",
                }
                idx = row.index if hasattr(row, "index") else []

                def _raw(key):
                    if key not in idx:
                        return None
                    try:
                        f = float(row[key])
                    except (TypeError, ValueError):
                        return None
                    return f if f == f else None  # 过滤 nan

                for field, label in field_map.items():
                    if field in idx:
                        raw = _raw(field)
                        if raw is not None:
                            shown = raw / 10 if field in _AMOUNT_FIELDS_0_1_YUAN else raw
                            lines.append(f"{label}: {shown}")
                # 推算 EPS / ROE（mootdx 无直字段）
                jinglirun = _raw("jinglirun")
                zongguben = _raw("zongguben")
                jingzichan = _raw("jingzichan")
                if jinglirun is not None and zongguben:
                    lines.append(
                        f"EPS (derived): {jinglirun / 10 / zongguben:.4f}"
                    )
                if jinglirun is not None and jingzichan:
                    lines.append(
                        f"ROE (%) (derived): {jinglirun / jingzichan * 100:.2f}"
                    )
        except Exception as e:
            _record_provider_failure("mootdx 财务快照", e)

        # --- 同花顺 direct HTTP: consensus EPS forecast ---
        # 页面不提供历史观测版本，历史分析必须排除预测和衍生的前瞻估值。
        try:
            forecast_df = _ths_eps_forecast(code)
            if forecast_df is not None and not forecast_df.empty:
                lines.append("\n--- Consensus EPS Forecast (同花顺) ---")
                eps_by_year = {}
                for _, row in forecast_df.iterrows():
                    year = str(row.iloc[0]) if len(row) > 0 else ""
                    mean_eps_val = row.iloc[3] if len(row) > 3 else 0
                    count_val = row.iloc[1] if len(row) > 1 else 0
                    min_eps_val = row.iloc[2] if len(row) > 2 else "N/A"
                    max_eps_val = row.iloc[4] if len(row) > 4 else "N/A"
                    try:
                        mean_eps = float(mean_eps_val)
                    except (ValueError, TypeError):
                        mean_eps = 0
                    try:
                        count = int(count_val)
                    except (ValueError, TypeError):
                        count = 0
                    lines.append(
                        f"FY{year}: EPS={mean_eps} "
                        f"(range {min_eps_val}~{max_eps_val}, {count} analysts)"
                    )
                    if count < 3:
                        lines.append("  Warning: low coverage (<3 analysts)")
                    eps_by_year[year] = mean_eps

                # Forward PE / PEG / PE digestion
                try:
                    tq = _get_realtime_quotes([code])
                except Exception as e:
                    _record_provider_failure("实时行情（前瞻估值降级链）", e)
                else:
                    try:
                        if code in tq:
                            price, _price_src = _resolve_price(
                                code, curr_date, tq[code].get("price")
                            )
                            years_sorted = sorted(eps_by_year.keys())
                            if (
                                price is not None
                                and years_sorted
                                and eps_by_year.get(years_sorted[0], 0) > 0
                            ):
                                eps_cur = eps_by_year[years_sorted[0]]
                                fwd_pe = price / eps_cur
                                lines.append(
                                    f"\nForward PE (FY{years_sorted[0]}): "
                                    f"{fwd_pe:.1f}x (price={price}, EPS={eps_cur})"
                                )
                                if (
                                    len(years_sorted) >= 2
                                    and eps_by_year.get(years_sorted[1], 0) > 0
                                ):
                                    eps_next = eps_by_year[years_sorted[1]]
                                    cagr = eps_next / eps_cur - 1
                                    if cagr > 0:
                                        peg = fwd_pe / (cagr * 100)
                                        lines.append(
                                            f"PEG: {peg:.2f} "
                                            f"(EPS CAGR={cagr * 100:.0f}%)"
                                        )
                                        if fwd_pe > 30:
                                            digest = math.log(fwd_pe / 30) / math.log(
                                                1 + cagr
                                            )
                                            lines.append(
                                                f"PE Digestion to 30x: {digest:.1f} years"
                                            )
                                        else:
                                            lines.append("PE already below 30x target")
                                    else:
                                        lines.append(
                                            f"EPS declining ({cagr * 100:.0f}%), "
                                            f"PEG not applicable"
                                        )
                    except Exception as e:
                        _record_provider_failure("前瞻估值计算", e)
        except Exception as e:
            _record_provider_failure("同花顺 EPS 一致预期", e)

        if not lines:
            return f"No fundamentals data found for A-stock '{code}'"

        header = f"# Company Fundamentals for {code} (A-stock)\n"
        header += (
            f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        )

        return header + "\n".join(lines)

    except Exception as e:
        return f"Error retrieving fundamentals for {code}: {type(e).__name__}（详情已隐藏）"


# ---- 4. get_balance_sheet ----


def _sina_stock_code(code: str) -> str:
    """Pure 6-digit code → sina format (sh688017 / sz000001 / bj832000)."""
    return f"{_get_prefix(code)}{code}"


def _get_financial_report_sina(
    code: str,
    report_type: str,
    freq: str,
    curr_date: str = None,
    historical_review: bool | None = None,
) -> pd.DataFrame:
    """Shared helper: fetch financial report via Sina direct HTTP API.

    report_type: '资产负债表' | '利润表' | '现金流量表'
    返回 DataFrame：每行一个报告期，列为报表项目名(item_title)，值为 item_value。
    """
    _report_type_map = {
        "资产负债表": "fzb",
        "利润表": "lrb",
        "现金流量表": "llb",
    }
    source_type = _report_type_map.get(report_type, "lrb")

    # paperCode 必须经 _sina_stock_code 统一市场路由（北交所 920/8x/4x 号段为 bj 前缀），
    # 手拼 sh/sz 会让新浪对北交所代码恒返回空三表。
    paper_code = _sina_stock_code(code)
    url = "https://quotes.sina.cn/cn/api/openapi.php/CompanyFinanceService.getFinanceReport2022"
    params = {
        "paperCode": paper_code,
        "source": source_type,
        "type": "0",
        "page": "1",
        "num": "20",
    }
    r = _source_http_get(
        "sina",
        url,
        params=params,
        headers={"User-Agent": _UA},
        timeout=15,
    )
    if hasattr(r, "raise_for_status"):
        r.raise_for_status()
    d = r.json()

    # 新浪 API 结构：result.data.report_list = {日期YYYYMMDD: {data: [{item_title, item_value, ...}]}}
    # 旧代码误用 result.data.<source_type> 取数（key 不存在），导致三表恒空。
    report_list = d.get("result", {}).get("data", {}).get("report_list", {})
    if not isinstance(report_list, dict) or not report_list:
        return pd.DataFrame()

    rows = []
    for date_key, report in report_list.items():
        items = report.get("data", []) if isinstance(report, dict) else []
        match = _re.search(r"\d{8}", str(date_key))
        if not match:
            continue
        report_date = match.group(0)
        row = {"报告日": report_date, "end_date": report_date}
        if isinstance(report, dict):
            for key in ("ann_date", "announcement_date", "publish_date", "notice_date"):
                if report.get(key):
                    row["ann_date"] = report[key]
                    break
        for item in items:
            if isinstance(item, dict):
                if "ann_date" not in row:
                    for key in ("ann_date", "announcement_date", "publish_date", "notice_date"):
                        if item.get(key):
                            row["ann_date"] = item[key]
                            break
                title = item.get("item_title")
                if title and title not in row:
                    row[title] = item.get("item_value")
                    if item.get("item_tongbi") is not None:
                        row[f"{title}同比"] = item.get("item_tongbi")
        rows.append(row)

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    if historical_review is None:
        historical_review = bool(curr_date) and is_historical_analysis(
            curr_date, as_of_date=_today()
        )
    if curr_date and historical_review:
        visible, excluded = filter_financial_records(
            rows,
            curr_date,
            source="sina",
            as_of_date=_today(),
            historical_review=True,
        )
        if not visible:
            empty = pd.DataFrame()
            empty.attrs["point_in_time_unavailable"] = bool(excluded)
            return empty
        df = pd.DataFrame(visible)
        if excluded:
            df.attrs["point_in_time_limited"] = True

    # 日期解析 + 按报告期降序（最新在前）
    df["报告日"] = pd.to_datetime(df["报告日"], format="%Y%m%d", errors="coerce")
    df = df.sort_values("报告日", ascending=False).reset_index(drop=True)

    if "ann_date" in df.columns:
        df["公告日"] = pd.to_datetime(df["ann_date"], errors="coerce")
        df = df.drop(columns=["ann_date"])
    df = df.drop(columns=["end_date"], errors="ignore")

    # Filter by frequency (annual = 年报，12 月末报告)
    if freq.lower() == "annual":
        df = df[df["报告日"].dt.month == 12]

    return df.head(8)


def get_balance_sheet(
    ticker: Annotated[str, "A-stock code"],
    freq: Annotated[str, "frequency: 'annual' or 'quarterly'"] = "quarterly",
    curr_date: Annotated[str, "current date in YYYY-MM-DD format"] = None,
    historical_review: bool | None = None,
) -> str:
    """Get balance sheet via Sina direct HTTP API."""
    code = _normalize_ticker(ticker)

    try:
        df = _get_financial_report_sina(
            code, "资产负债表", freq, curr_date, historical_review
        )

        if df.empty:
            if df.attrs.get("point_in_time_unavailable"):
                return point_in_time_unavailable_message("新浪资产负债表")
            return f"No balance sheet data found for A-stock '{code}'"

        csv_string = df.to_csv(index=False)

        header = f"# Balance Sheet for {code} (A-stock, {freq})\n"
        header += "# Data source: sina direct HTTP\n"
        header += (
            f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        )

        return header + csv_string

    except Exception as e:
        return f"Error retrieving balance sheet for {code}: {str(e)}"


# ---- 5. get_cashflow ----


def get_cashflow(
    ticker: Annotated[str, "A-stock code"],
    freq: Annotated[str, "frequency: 'annual' or 'quarterly'"] = "quarterly",
    curr_date: Annotated[str, "current date in YYYY-MM-DD format"] = None,
    historical_review: bool | None = None,
) -> str:
    """Get cash flow statement via Sina direct HTTP API."""
    code = _normalize_ticker(ticker)

    try:
        df = _get_financial_report_sina(
            code, "现金流量表", freq, curr_date, historical_review
        )

        if df.empty:
            if df.attrs.get("point_in_time_unavailable"):
                return point_in_time_unavailable_message("新浪现金流量表")
            return f"No cash flow data found for A-stock '{code}'"

        csv_string = df.to_csv(index=False)

        header = f"# Cash Flow for {code} (A-stock, {freq})\n"
        header += "# Data source: sina direct HTTP\n"
        header += (
            f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        )

        return header + csv_string

    except Exception as e:
        return f"Error retrieving cash flow for {code}: {str(e)}"


# ---- 6. get_income_statement ----


def get_income_statement(
    ticker: Annotated[str, "A-stock code"],
    freq: Annotated[str, "frequency: 'annual' or 'quarterly'"] = "quarterly",
    curr_date: Annotated[str, "current date in YYYY-MM-DD format"] = None,
    historical_review: bool | None = None,
) -> str:
    """Get income statement via Sina direct HTTP API."""
    code = _normalize_ticker(ticker)

    try:
        df = _get_financial_report_sina(
            code, "利润表", freq, curr_date, historical_review
        )

        if df.empty:
            if df.attrs.get("point_in_time_unavailable"):
                return point_in_time_unavailable_message("新浪利润表")
            return f"No income statement data found for A-stock '{code}'"

        csv_string = df.to_csv(index=False)

        header = f"# Income Statement for {code} (A-stock, {freq})\n"
        header += "# Data source: sina direct HTTP\n"
        header += (
            f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        )

        if df.attrs.get("point_in_time_limited"):
            header += f"# {POINT_IN_TIME_LIMITED_MARKER} 已排除 analysis_date 后公告的报告版本\n"
        return header + csv_string

    except Exception as e:
        return f"Error retrieving income statement for {code}: {str(e)}"


def get_free_financial_indicators(
    ticker: Annotated[str, "A-stock code"],
    curr_date: Annotated[str, "current date in YYYY-MM-DD format"] = None,
    historical_review: bool | None = None,
) -> str:
    """Derive Free core financial indicators from Sina's three statements."""
    code = _normalize_ticker(ticker)
    reports = {
        "利润表": _get_financial_report_sina(
            code, "利润表", "quarterly", curr_date, historical_review
        ),
        "资产负债表": _get_financial_report_sina(
            code, "资产负债表", "quarterly", curr_date, historical_review
        ),
        "现金流量表": _get_financial_report_sina(
            code, "现金流量表", "quarterly", curr_date, historical_review
        ),
    }
    if any(frame.empty for frame in reports.values()):
        return f"No complete Sina three-statement data found for A-stock '{code}'"

    def date_text(value: Any) -> str | None:
        parsed = pd.to_datetime(value, errors="coerce")
        return None if pd.isna(parsed) else parsed.strftime("%Y-%m-%d")

    periods_by_report = {
        name: {
            date_text(value)
            for value in frame.get("报告日", pd.Series(dtype=object))
            if date_text(value)
        }
        for name, frame in reports.items()
    }
    common_periods = set.intersection(*periods_by_report.values())
    if not common_periods:
        return f"No common Sina report period found for A-stock '{code}'"
    report_period = max(common_periods)

    def row_for(frame: pd.DataFrame, period: str) -> Mapping[str, Any]:
        matching = frame.loc[
            frame["报告日"].map(date_text) == period
        ]
        return matching.iloc[0].to_dict()

    income_row = row_for(reports["利润表"], report_period)
    balance_row = row_for(reports["资产负债表"], report_period)
    cashflow_row = row_for(reports["现金流量表"], report_period)
    statement_rows = {
        "利润表": income_row,
        "资产负债表": balance_row,
        "现金流量表": cashflow_row,
    }
    announcement_dates = {
        name: date_text(row.get("公告日"))
        for name, row in statement_rows.items()
    }
    if not all(announcement_dates.values()):
        return (
            f"Error deriving Free financial indicators for {code}: "
            "Sina report announcement date is unavailable"
        )
    announcement_date = max(announcement_dates.values())

    def number(value: Any) -> float | None:
        if value is None or pd.isna(value):
            return None
        try:
            parsed = float(str(value).replace(",", "").replace("%", "").strip())
        except (TypeError, ValueError):
            return None
        return parsed if math.isfinite(parsed) else None

    def field(row: Mapping[str, Any], *names: str) -> float | None:
        for name in names:
            if name in row:
                value = number(row[name])
                if value is not None:
                    return value
        return None

    revenue = field(income_row, "营业收入", "主营业务收入")
    operating_cost = field(income_row, "营业成本", "主营业务成本")
    net_profit = field(income_row, "净利润", "归属于母公司股东的净利润")
    total_assets = field(balance_row, "资产总计", "总资产")
    total_liabilities = field(balance_row, "负债合计", "总负债")
    parent_equity = field(
        balance_row,
        "归属于母公司股东权益合计",
        "归属于母公司所有者权益合计",
        "归属于母公司股东的所有者权益",
    )
    operating_cashflow = field(cashflow_row, "经营活动产生的现金流量净额")

    def percent_ratio(numerator: float | None, denominator: float | None) -> float | None:
        if numerator is None or denominator in (None, 0):
            return None
        return numerator / denominator * 100

    def raw_yoy(row: Mapping[str, Any], *names: str) -> float | None:
        for name in names:
            if name in row:
                parsed = number(row[name])
                if parsed is not None:
                    return parsed
        return None

    has_insurance_or_net_interest = any(
        field(income_row, marker) is not None
        for marker in ("利息净收入", "已赚保费", "保费收入")
    )
    has_bank_interest_structure = (
        revenue is None
        and operating_cost is None
        and field(income_row, "利息收入") is not None
        and field(income_row, "利息支出") is not None
    )
    is_financial = has_insurance_or_net_interest or has_bank_interest_structure
    previous_equity = None
    prior_period = (pd.Timestamp(report_period) - pd.DateOffset(years=1)).strftime("%Y-%m-%d")
    prior_rows = reports["资产负债表"].loc[
        reports["资产负债表"]["报告日"].map(date_text) == prior_period
    ]
    if not prior_rows.empty:
        previous_equity = field(
            prior_rows.iloc[0].to_dict(),
            "归属于母公司股东权益合计",
            "归属于母公司所有者权益合计",
            "归属于母公司股东的所有者权益",
        )
    roe = None
    roe_basis = "不可用"
    if report_period.endswith("12-31") and net_profit is not None and parent_equity is not None and previous_equity is not None:
        roe = percent_ratio(net_profit, (parent_equity + previous_equity) / 2)
        roe_basis = "年报净利润/平均归母权益"
    elif net_profit is not None and parent_equity is not None and previous_equity is not None:
        prior_year_end = f"{pd.Timestamp(report_period).year - 1}-12-31"
        prior_income_rows = reports["利润表"].loc[
            reports["利润表"]["报告日"].map(date_text) == prior_period
        ]
        prior_annual_rows = reports["利润表"].loc[
            reports["利润表"]["报告日"].map(date_text) == prior_year_end
        ]
        if not prior_income_rows.empty and not prior_annual_rows.empty:
            prior_same_profit = field(
                prior_income_rows.iloc[0].to_dict(), "净利润", "归属于母公司股东的净利润"
            )
            prior_annual_profit = field(
                prior_annual_rows.iloc[0].to_dict(), "净利润", "归属于母公司股东的净利润"
            )
            if prior_same_profit is not None and prior_annual_profit is not None:
                roe = percent_ratio(
                    net_profit + prior_annual_profit - prior_same_profit,
                    (parent_equity + previous_equity) / 2,
                )
                roe_basis = "TTM净利润/平均归母权益"

    def rendered_amount(label: str, value: float | None) -> str:
        return f"- {label}: {value:.2f}" if value is not None else f"- {label}: 不可用"

    def rendered_percent(label: str, value: float | None, suffix: str = "%") -> str:
        return f"- {label}: {value:.2f}{suffix}" if value is not None else f"- {label}: 不可用"

    cash_profit = (
        None if operating_cashflow is None or net_profit in (None, 0)
        else operating_cashflow / net_profit
    )
    gross_margin = None if is_financial else percent_ratio(
        None if revenue is None or operating_cost is None else revenue - operating_cost,
        revenue,
    )
    lines = [
        f"# Free Core Financial Indicators for {code}",
        "# Data source: sina_derived",
        "source=sina_derived",
        f"report_period_end: {report_period}",
        f"announcement_date: {announcement_date}",
        "statement_announcement_dates: " + "; ".join(
            f"{name}={value}" for name, value in announcement_dates.items()
        ),
        "## 七项核心值（同一报告期）",
        rendered_amount("营业收入", revenue),
        rendered_amount("营业成本", operating_cost),
        rendered_amount("净利润", net_profit),
        rendered_amount("总资产", total_assets),
        rendered_amount("总负债", total_liabilities),
        rendered_amount("归母权益", parent_equity),
        rendered_amount("经营现金流", operating_cashflow),
        "## 派生指标",
        (
            f"- ROE: {roe:.2f}%（{roe_basis}）"
            if roe is not None else f"- ROE: 不可用（{roe_basis}）"
        ),
        (
            "- 毛利率: 不适用（银行/保险）"
            if is_financial else rendered_percent("毛利率", gross_margin)
        ),
        rendered_percent("净利率", percent_ratio(net_profit, revenue)),
        rendered_percent("营收同比增长率", raw_yoy(income_row, "营业收入同比", "主营业务收入同比")),
        rendered_percent("净利润同比增长率", raw_yoy(income_row, "净利润同比", "归属于母公司股东的净利润同比")),
        rendered_percent("资产负债率", percent_ratio(total_liabilities, total_assets)),
        rendered_percent("经营性现金流/净利润匹配度", cash_profit, "x"),
    ]
    return "\n".join(lines)


# ---- 7. get_news ----


def _fetch_news_eastmoney(code: str, page_size: int = 20) -> list[dict]:
    """Direct East Money search API for individual stock news."""
    url = "https://search-api-web.eastmoney.com/search/jsonp"
    inner_param = {
        "uid": "",
        "keyword": code,
        "type": ["cmsArticleWebOld"],
        "client": "web",
        "clientType": "web",
        "clientVersion": "curr",
        "param": {
            "cmsArticleWebOld": {
                "searchScope": "default",
                "sort": "default",
                "pageIndex": 1,
                "pageSize": page_size,
                "preTag": "",
                "postTag": "",
            }
        },
    }
    params = {
        "cb": "callback",
        "param": _json.dumps(inner_param, ensure_ascii=False),
        "_": "1",
    }
    headers = {
        "Referer": "https://so.eastmoney.com/",
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"
        ),
    }

    resp = _em_get(url, params=params, headers=headers, timeout=15)
    resp.raise_for_status()
    text = resp.text
    text = text[text.index("(") + 1 : text.rindex(")")]
    data = _json.loads(text)

    articles: list[dict] = []
    for item in data.get("result", {}).get("cmsArticleWebOld", []):
        articles.append({
            "title": item.get("title", ""),
            "content": item.get("content", ""),
            "time": item.get("date", ""),
            "source": item.get("mediaName", "东方财富"),
            "url": item.get("url", ""),
        })
    return articles


def _fetch_news_sina(code: str, page_size: int = 20) -> list[dict]:
    """Sina Finance stock news API (backup source)."""
    prefix = _get_prefix(code)
    url = (
        f"https://vip.stock.finance.sina.com.cn/corp/view/"
        f"vCB_AllNewsStock.php?symbol={prefix}{code}&Page=1"
    )
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"
        ),
        "Referer": "https://finance.sina.com.cn/",
    }

    resp = _source_http_get("sina", url, headers=headers, timeout=15)
    if hasattr(resp, "raise_for_status"):
        resp.raise_for_status()
    resp.encoding = "gb2312"
    html = resp.text

    articles: list[dict] = []
    rows = _re.findall(
        r"(\d{4}-\d{2}-\d{2})\s*(?:&nbsp;)*(\d{2}:\d{2})\s*(?:&nbsp;)*"
        r"<a[^>]+href='([^']+)'[^>]*>([^<]+)</a>",
        html,
    )
    for date_str, time_str, link, title in rows[:page_size]:
        articles.append({
            "title": title.strip(),
            "content": "",
            "time": f"{date_str} {time_str}",
            "source": "新浪财经",
            "url": link,
        })
    return articles


def get_news(
    ticker: Annotated[str, "A-stock code"],
    start_date: Annotated[str, "Start date yyyy-mm-dd"],
    end_date: Annotated[str, "End date yyyy-mm-dd"],
) -> str:
    """Get stock-specific news via East Money direct API (Sina as fallback)."""
    code = _normalize_ticker(ticker)

    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")

    articles: list[dict] = []
    source_label = ""
    provider_failures: list[str] = []

    def _record_news_failure(provider: str, exc: Exception) -> None:
        error_type = type(exc).__name__
        logger.warning("%s news fetch failed for %s: %s", provider, code, error_type)
        provider_failures.append(
            f"{provider}新闻源失败：{error_type}（详情已隐藏）"
        )

    try:
        articles = _fetch_news_eastmoney(code)
        source_label = "东方财富"
    except Exception as e:
        _record_news_failure("东方财富", e)

    if not articles:
        try:
            articles = _fetch_news_sina(code)
            source_label = "新浪财经"
        except Exception as e:
            _record_news_failure("新浪财经", e)

    if not articles:
        if provider_failures:
            return "\n".join([
                f"No news found for A-stock '{code}'",
                *provider_failures,
            ])
        return f"No news found for A-stock '{code}'"

    news_str = ""
    count = 0
    for art in articles:
        pub_time = art.get("time", "")
        try:
            pub_dt = datetime.strptime(pub_time[:10], "%Y-%m-%d")
            if pub_dt < start_dt or pub_dt > end_dt:
                continue
        except (ValueError, IndexError):
            pass

        title = art["title"]
        content = art.get("content", "")
        source = art.get("source", source_label)
        link = art.get("url", "")

        news_str += f"### {title} (source: {source})\n"
        if content:
            snippet = content[:300] + "..." if len(content) > 300 else content
            news_str += f"{snippet}\n"
        if link and link != "nan":
            news_str += f"Link: {link}\n"
        news_str += "\n"
        count += 1

    if count == 0:
        return (
            f"No news found for A-stock '{code}' "
            f"between {start_date} and {end_date}"
        )

    return (
        f"## {code} (A-stock) News, from {start_date} to {end_date}:\n\n"
        + news_str
    )


# ---- 8. get_global_news ----


def _cls_v1_url(limit: int, last_time: str = "") -> str:
    """Build the CLS frontend v1 roll-list URL and its deterministic sign."""
    params = {
        "appName": "CailianpressWeb",
        "last_time": last_time,
        "os": "web",
        "refresh_type": "1",
        "rn": str(limit),
        "sv": _CLS_V1_VERSION,
    }
    query = "&".join(f"{key}={params[key]}" for key in sorted(params))
    sign = hashlib.md5(
        hashlib.sha1(query.encode("utf-8")).hexdigest().encode("utf-8")
    ).hexdigest()
    return f"{_CLS_V1_ROLL_URL}?{query}&sign={sign}"


def get_global_news(
    curr_date: Annotated[str, "Current date yyyy-mm-dd"],
    look_back_days: Annotated[int, "Days to look back"] = 7,
    limit: Annotated[int, "Max articles"] = 10,
) -> str:
    """Get China/global financial news via direct HTTP (CLS + Eastmoney)."""
    start_dt = datetime.strptime(curr_date, "%Y-%m-%d") - relativedelta(
        days=look_back_days
    )
    start_date = start_dt.strftime("%Y-%m-%d")

    all_news: list[dict] = []

    # Source 1: CLS wire (财联社快讯) — signed v1 first, legacy cache fallback.
    cls_headers = {"User-Agent": _UA, "Referer": "https://www.cls.cn/telegraph"}
    cls_attempts = (
        (_cls_v1_url(limit), None, "v1"),
        (_CLS_CACHE_URL, {"name": "telegraph", "rn": str(limit)}, "cache"),
    )
    for cls_url, cls_params, cls_variant in cls_attempts:
        try:
            request_kwargs = {"headers": cls_headers, "timeout": 10}
            if cls_params is not None:
                request_kwargs["params"] = cls_params
            r_cls = _source_http_get("cls", cls_url, **request_kwargs)
            if hasattr(r_cls, "raise_for_status"):
                r_cls.raise_for_status()
            d_cls = r_cls.json()
            if cls_variant == "v1" and str(d_cls.get("errno")) != "0":
                raise ValueError(f"CLS v1 returned errno={d_cls.get('errno')}")
            for item in d_cls.get("data", {}).get("roll_data", []):
                title = item.get("title", "") or item.get("brief", "")
                content = item.get("content", "") or item.get("brief", "")
                ctime = item.get("ctime", "")
                # ctime is unix timestamp
                pub_time = ""
                if ctime:
                    try:
                        pub_time = datetime.fromtimestamp(int(ctime)).strftime(
                            "%Y-%m-%d %H:%M"
                        )
                    except (ValueError, TypeError, OSError):
                        pub_time = str(ctime)
                all_news.append({
                    "title": title,
                    "content": content,
                    "time": pub_time,
                    "source": "CLS Wire",
                })
            break
        except Exception as e:
            logger.warning("CLS %s news fetch failed: %s", cls_variant, e)

    # Source 2: Eastmoney global (东财7x24资讯) — direct HTTP
    try:
        em_url = "https://np-weblist.eastmoney.com/comm/web/getFastNewsList"
        em_params = {
            "client": "web",
            "biz": "web_724",
            "fastColumn": "102",
            "sortEnd": "",
            "pageSize": str(limit),
            "req_trace": str(uuid.uuid4()),
        }
        em_headers = {"User-Agent": _UA, "Referer": "https://kuaixun.eastmoney.com/"}
        r_em = _em_get(em_url, params=em_params, headers=em_headers, timeout=10)
        d_em = r_em.json()
        for item in d_em.get("data", {}).get("fastNewsList", []):
            title = item.get("title", "")
            summary = item.get("summary", "")[:200]
            pub_time = item.get("showTime", "")
            all_news.append({
                "title": title,
                "content": summary,
                "time": pub_time,
                "source": "Eastmoney Global",
            })
    except Exception as e:
        logger.warning("Eastmoney global news fetch failed: %s", e)

    if not all_news:
        return f"No global news found for {curr_date}"

    # Deduplicate by title
    seen: set[str] = set()
    unique: list[dict] = []
    for n in all_news:
        if n["title"] not in seen:
            seen.add(n["title"])
            unique.append(n)

    news_str = ""
    for n in unique[:limit]:
        news_str += f"### {n['title']} (source: {n['source']})\n"
        if n.get("content"):
            snippet = (
                n["content"][:300] + "..."
                if len(n["content"]) > 300
                else n["content"]
            )
            news_str += f"{snippet}\n"
        news_str += "\n"

    return (
        f"## China & Global Market News, from {start_date} to {curr_date}:\n\n"
        + news_str
    )


# ---- 9. get_insider_transactions ----


def get_insider_transactions(
    ticker: Annotated[str, "A-stock code"],
) -> str:
    """Get top-10 shareholders + 股东户数变化 + 董监高持股变动 via 东财.

    A 股无美股式 insider transactions 概念，整合三段最接近等价数据：
    1. 十大股东（datacenter RPT_F10_EH_HOLDERS，最新一期持股变化）
    2. 股东户数变化（F10 ShareholderResearch/PageAjax gdrs，近 4 期）
    3. 董监高持股变动（F10 CompanyManagement/PageAjax cgbd，近 10 条）
    """
    code = _normalize_ticker(ticker)
    prefix = _get_prefix(code).upper()

    sections = []

    # --- 1. 十大股东（datacenter RPT_F10_EH_HOLDERS） ---
    try:
        data = _eastmoney_datacenter(
            "RPT_F10_EH_HOLDERS",
            filter_str=f'(SECURITY_CODE="{code}")',
            page_size=50,
            sort_columns="END_DATE",
            sort_types="-1",
        )
        if data:
            latest_date = str(data[0].get("END_DATE", ""))[:10]
            latest_holders = [
                x for x in data if str(x.get("END_DATE", ""))[:10] == latest_date
            ][:10]
            lines = [
                f"## 十大股东（最新一期 {latest_date}）",
                "股东名称 | 持股数 | 持股比例(%) | 持股变化 | 是否机构",
            ]
            for x in latest_holders:
                name = x.get("HOLDER_NAME", "")
                hold = x.get("HOLD_NUM", 0)
                ratio = x.get("HOLD_NUM_RATIO", 0)
                change = x.get("HOLD_NUM_CHANGE", "不变")
                is_org = "机构" if str(x.get("IS_HOLDORG")) == "1" else "个人"
                lines.append(f"  {name} | {hold} | {ratio} | {change} | {is_org}")
            sections.append("\n".join(lines))
    except Exception as e:
        sections.append(_eastmoney_data_missing("十大股东数据", e))

    # --- 2. 股东户数变化（F10 ShareholderResearch gdrs） ---
    try:
        url = f"https://emweb.securities.eastmoney.com/PC_HSF10/ShareholderResearch/PageAjax?code={prefix}{code}"
        r = _em_get(
            url,
            headers={"Referer": "https://emweb.eastmoney.com/"},
            timeout=10,
        )
        gdrs = (r.json() or {}).get("gdrs", []) or []
        if gdrs:
            lines = [
                "## 股东户数变化",
                "报告期 | 股东户数 | 户数变化(%) | 户均流通股 | 筹码集中度",
            ]
            for x in gdrs[:4]:
                d = str(x.get("END_DATE", ""))[:10]
                num = x.get("HOLDER_TOTAL_NUM", "-")
                ratio = x.get("TOTAL_NUM_RATIO", "-")
                avg = x.get("AVG_FREE_SHARES", "-")
                focus = x.get("HOLD_FOCUS", "-")
                lines.append(f"  {d} | {num} | {ratio} | {avg} | {focus}")
            sections.append("\n".join(lines))
    except Exception as e:
        sections.append(_eastmoney_data_missing("股东户数数据", e))

    # --- 3. 董监高持股变动（F10 CompanyManagement cgbd） ---
    try:
        url = f"https://emweb.securities.eastmoney.com/PC_HSF10/CompanyManagement/PageAjax?code={prefix}{code}"
        r = _em_get(
            url,
            headers={"Referer": "https://emweb.eastmoney.com/"},
            timeout=10,
        )
        cgbd = (r.json() or {}).get("cgbd", []) or []
        if cgbd:
            lines = [
                "## 董监高持股变动（近 10 条）",
                "变动日期 | 高管/变动人 | 职务 | 变动股数 | 均价 | 变动后持股 | 变动方式",
            ]
            for x in cgbd[:10]:
                d = str(x.get("END_DATE", ""))[:10]
                name = x.get("EXECUTIVE_NAME") or x.get("HOLDER_NAME", "-")
                pos = x.get("POSITION", "-")
                chg = x.get("CHANGE_NUM", "-")
                price = x.get("AVERAGE_PRICE", "-")
                after = x.get("CHANGE_AFTER_HOLDNUM", "-")
                way = x.get("TRADE_WAY", "-")
                lines.append(f"  {d} | {name} | {pos} | {chg} | {price} | {after} | {way}")
            sections.append("\n".join(lines))
    except Exception as e:
        sections.append(_eastmoney_data_missing("董监高持股变动数据", e))

    if not sections:
        return f"No shareholder data found for A-stock '{code}'"

    header = f"# Shareholder & Insider Data for {code} (A-stock)\n"
    header += "# Data source: 东财 datacenter + F10 PageAjax\n"
    header += f"# Retrieved: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
    return header + "\n" + "\n\n".join(sections)



# ---- 11. get_research_reports ----


_EASTMONEY_RESEARCH_REPORT_URL = "https://reportapi.eastmoney.com/report/list"
_EASTMONEY_RESEARCH_REPORT_REFERER = "https://data.eastmoney.com/report/"
_RESEARCH_REPORT_WINDOW_DAYS = 90
_RESEARCH_REPORT_PAGE_SIZE = 10


def _research_report_field(row: Mapping[str, Any], *names: str) -> Any:
    """Read one provider field without conflating absent values with zero."""
    normalized = {str(key).lower(): value for key, value in row.items()}
    for name in names:
        value = normalized.get(name.lower())
        if value is not None:
            return value
    return None


def _research_report_text(row: Mapping[str, Any], *names: str) -> str | None:
    value = _research_report_field(row, *names)
    text = str(value or "").strip()
    return text or None


def _research_report_number(row: Mapping[str, Any], *names: str) -> float | None:
    value = _research_report_field(row, *names)
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(str(value).strip().replace(",", ""))
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _research_report_date(value: Any) -> str | None:
    text = str(value or "").strip()[:10].replace("/", "-")
    if len(text) == 8 and text.isdigit():
        text = f"{text[:4]}-{text[4:6]}-{text[6:]}"
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError:
        return None


def _research_report_rows(payload: object) -> list[Mapping[str, Any]]:
    """Accept only the documented list envelopes, never a guessed fallback."""
    if not isinstance(payload, Mapping):
        raise ValueError("research report payload must be an object")
    data = payload.get("data")
    if isinstance(data, list):
        rows = data
    elif isinstance(data, Mapping) and isinstance(data.get("data"), list):
        rows = data["data"]
    elif isinstance(data, Mapping) and isinstance(data.get("list"), list):
        rows = data["list"]
    else:
        raise ValueError("research report payload missing expected data list")
    if not all(isinstance(item, Mapping) for item in rows):
        raise ValueError("research report data list contains a non-object row")
    return list(rows)


def _research_report_result(status: str, **fields: Any) -> str:
    """Return a parsable bounded payload while retaining ResultStore status markers."""
    payload = {"status": status, **fields}
    encoded = _json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if status == "normal_empty":
        return f"[正常空] Eastmoney research reports\n{encoded}"
    if status.startswith("failed"):
        return f"[数据缺失] Eastmoney research reports\n{encoded}"
    if status == "invalid_input":
        return f"Invalid ticker for Eastmoney research reports\n{encoded}"
    return encoded


def get_research_reports(
    ticker: Annotated[str, "6-digit A-share code (e.g. 600519)"],
) -> str:
    """Return a bounded Eastmoney sell-side research *metadata* summary.

    The adapter intentionally requests only one listing page and never follows
    report/PDF links. Ratings and EPS are attributed as sell-side expectations,
    not company facts or investment conclusions.
    """
    try:
        code = _normalize_ticker(ticker)
    except (TypeError, ValueError) as exc:
        return _research_report_result("invalid_input", reason=type(exc).__name__)

    as_of = _today()
    window_start = as_of - timedelta(days=_RESEARCH_REPORT_WINDOW_DAYS - 1)
    try:
        response = _em_get(
            _EASTMONEY_RESEARCH_REPORT_URL,
            params={
                "code": code,
                "beginTime": window_start.isoformat(),
                "endTime": as_of.isoformat(),
                "pageNo": 1,
                "pageSize": _RESEARCH_REPORT_PAGE_SIZE,
                # The listing endpoint expects the stock-report query shape;
                # omitting these wildcard/pagination fields currently yields
                # an HTTP 500 instead of a validation response.
                "qType": "0",
                "industryCode": "*",
                "industry": "*",
                "rating": "*",
                "ratingChange": "*",
                "fields": "",
                "orgCode": "",
                "rcode": "",
                "p": 1,
                "pageNum": 1,
                "pageNumber": 1,
            },
            headers={"Referer": _EASTMONEY_RESEARCH_REPORT_REFERER},
            timeout=15,
        )
        raise_for_status = getattr(response, "raise_for_status", None)
        if callable(raise_for_status):
            raise_for_status()
        raw_rows = _research_report_rows(response.json())
    except (_requests.RequestException, TimeoutError, ConnectionError) as exc:
        return _research_report_result("failed_network", reason=type(exc).__name__)
    except (ValueError, TypeError, _json.JSONDecodeError) as exc:
        return _research_report_result("failed_structure", reason=type(exc).__name__)
    except Exception as exc:
        logger.warning("Eastmoney research report request failed for %s: %s", code, type(exc).__name__)
        return _research_report_result("failed_network", reason=type(exc).__name__)

    reports: list[dict[str, Any]] = []
    seen: set[tuple[str, ...]] = set()
    try:
        for row in raw_rows:
            publish_date = _research_report_date(
                _research_report_field(row, "publishDate", "publish_date", "date")
            )
            if publish_date is None:
                raise ValueError("research report row missing valid publish date")
            published = date.fromisoformat(publish_date)
            if not window_start <= published <= as_of:
                continue
            # predictThisYearEps is relative to the report's own publication year,
            # not to the query date.  Labelling it with as_of.year misattributes
            # the forecast for any report published in a different year (the
            # 90-day window spans a year boundary every Jan-Mar), which then
            # mixed fiscal years inside one year key's min/median/max.
            forecast_year = published.year
            institution = _research_report_text(row, "orgSName", "orgName", "institution")
            title = _research_report_text(row, "title", "reportTitle")
            info_code = _research_report_text(row, "infoCode", "info_code")
            dedupe_key = (
                ("info", info_code)
                if info_code
                else ("fallback", publish_date, institution or "", title or "")
            )
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            reports.append(
                {
                    "publish_date": publish_date,
                    "institution": institution,
                    "title": title,
                    "rating": _research_report_text(
                        row, "emRatingName", "ratingName", "rating", "rating_name"
                    ),
                    "rating_change": _research_report_text(row, "ratingChange", "rating_change"),
                    "eps": {
                        str(forecast_year): _research_report_number(row, "predictThisYearEps", "thisYearEps"),
                        str(forecast_year + 1): _research_report_number(row, "predictNextYearEps", "nextYearEps"),
                        str(forecast_year + 2): _research_report_number(row, "predictNextTwoYearEps", "nextTwoYearEps"),
                    },
                    "industry": _research_report_text(row, "industryName", "industry"),
                    "info_code": info_code,
                }
            )
            if len(reports) >= _RESEARCH_REPORT_PAGE_SIZE:
                break
    except (TypeError, ValueError) as exc:
        return _research_report_result("failed_structure", reason=type(exc).__name__)

    reports.sort(key=lambda item: item["publish_date"], reverse=True)
    observed_at = datetime.now(_MARKET_TZ).isoformat(timespec="seconds")
    base = {
        "source": "Eastmoney reportapi aggregation",
        "observed_at": observed_at,
        "as_of_date": as_of.isoformat(),
        "window_days": _RESEARCH_REPORT_WINDOW_DAYS,
        "report_count": len(reports),
        "institution_count": len({item["institution"] for item in reports if item["institution"]}),
        "rating_distribution": {},
        "rating_change_distribution": {},
        "eps_forecasts": {},
        "recent_reports": reports[:5],
    }
    if not reports:
        return _research_report_result("normal_empty", **base)

    for key, output in (("rating", "rating_distribution"), ("rating_change", "rating_change_distribution")):
        distribution: dict[str, int] = {}
        for item in reports:
            value = item[key]
            if value:
                distribution[value] = distribution.get(value, 0) + 1
        base[output] = distribution
    # Aggregate every fiscal year actually forecast across the window.  Deriving
    # the three keys from one report's year would drop the other reports' years
    # and raised NameError when the window filtered every row out.
    for year in sorted({year for item in reports for year in item["eps"]}):
        values = sorted(
            item["eps"][year] for item in reports if item["eps"].get(year) is not None
        )
        if values:
            midpoint = len(values) // 2
            median = values[midpoint] if len(values) % 2 else (values[midpoint - 1] + values[midpoint]) / 2
            base["eps_forecasts"][year] = {
                "sample_count": len(values), "median": median, "min": values[0], "max": values[-1],
            }
    return _research_report_result("success", **base)


# ---- 15. get_earnings_forecast ----


_EARNINGS_FORECAST_REPORT_NAME = "RPT_PUBLIC_OP_PREDICT"
_EARNINGS_FORECAST_PAGE_SIZE = 10
_EARNINGS_FORECAST_MAX_ROWS = 8
_EARNINGS_FORECAST_WINDOW_YEARS = 3
_EARNINGS_FORECAST_CONTENT_MAX_CHARS = 240
_EARNINGS_FORECAST_REASON_MAX_CHARS = 160


def _earnings_forecast_field(row: Mapping[str, Any], *names: str) -> Any:
    normalized = {str(key).lower(): value for key, value in row.items()}
    for name in names:
        value = normalized.get(name.lower())
        if value is not None:
            return value
    return None


def _earnings_forecast_text(row: Mapping[str, Any], *names: str, limit: int = 0) -> str | None:
    value = _earnings_forecast_field(row, *names)
    text = str(value or "").strip()
    if not text:
        return None
    return text[:limit] if limit else text


def _earnings_forecast_number(row: Mapping[str, Any], *names: str) -> float | None:
    value = _earnings_forecast_field(row, *names)
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(str(value).strip().replace(",", ""))
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _earnings_forecast_date(value: Any) -> str | None:
    text = str(value or "").strip()[:10].replace("/", "-")
    if len(text) == 8 and text.isdigit():
        text = f"{text[:4]}-{text[4:6]}-{text[6:]}"
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError:
        return None


def _earnings_forecast_yi(row: Mapping[str, Any], *names: str) -> float | None:
    """Provider amounts are yuan; project to 亿元 for bounded readability.

    The provider fills ``0`` where no absolute amount was disclosed (增幅-only
    forecasts); an exactly-zero pre-announced profit is not a real disclosure,
    so it is normalized to None instead of a fake "0.00 亿元".
    """
    value = _earnings_forecast_number(row, *names)
    if value is None or value == 0:
        return None
    return round(value / 100_000_000, 4)


def _earnings_forecast_rows(payload: object) -> list[Mapping[str, Any]]:
    """Accept only the datacenter report envelope, never a guessed fallback.

    The datacenter signals "no rows" with ``result: null`` + ``code: 9201``
    (返回数据为空) — that is a normal empty, never a failure.  Any other null
    result (e.g. 9501 parameter/report errors) stays a structure failure.
    """
    if not isinstance(payload, Mapping):
        raise ValueError("earnings forecast payload must be an object")
    result = payload.get("result")
    if result is None:
        if str(payload.get("code")) == "9201":
            return []
        raise ValueError(
            f"earnings forecast payload has null result (code={payload.get('code')})"
        )
    data = result.get("data") if isinstance(result, Mapping) else None
    if not isinstance(data, list):
        raise ValueError("earnings forecast payload missing result.data list")
    if not all(isinstance(item, Mapping) for item in data):
        raise ValueError("earnings forecast data list contains a non-object row")
    return list(data)


def _earnings_forecast_result(status: str, **fields: Any) -> str:
    """Return a parsable bounded payload while retaining ResultStore status markers."""
    payload = {"status": status, **fields}
    encoded = _json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if status == "normal_empty":
        return f"[正常空] Eastmoney earnings pre-announcement\n{encoded}"
    if status.startswith("failed"):
        return f"[数据缺失] Eastmoney earnings pre-announcement\n{encoded}"
    if status == "invalid_input":
        return f"Invalid ticker for Eastmoney earnings pre-announcement\n{encoded}"
    return encoded


def get_earnings_forecast(
    ticker: Annotated[str, "6-digit A-share code (e.g. 600519)"],
) -> str:
    """Return the company's official earnings pre-announcements (业绩预告).

    Every row is company preliminary disclosure carrying its announcement date
    (NOTICE_DATE).  Rows outside the recent 3-year announcement window are
    relevance-filtered: a decades-old forecast must not read as current
    guidance.  This is neither analyst consensus nor an audited result, may
    differ from the final financial report, and is never a buy/sell signal.
    业绩快报 (express, unaudited actuals) is deliberately out of scope.
    """
    try:
        code = _normalize_ticker(ticker)
    except (TypeError, ValueError) as exc:
        return _earnings_forecast_result("invalid_input", reason=type(exc).__name__)

    try:
        response = _em_get(
            _DATACENTER_URL,
            params={
                "reportName": _EARNINGS_FORECAST_REPORT_NAME,
                "columns": "ALL",
                "filter": f'(SECURITY_CODE="{code}")',
                "pageSize": _EARNINGS_FORECAST_PAGE_SIZE,
                "pageNumber": 1,
                "sortColumns": "NOTICE_DATE",
                "sortTypes": "-1",
                "source": "WEB",
                "client": "WEB",
            },
            timeout=15,
        )
        raise_for_status = getattr(response, "raise_for_status", None)
        if callable(raise_for_status):
            raise_for_status()
        raw_rows = _earnings_forecast_rows(response.json())
    except (_requests.RequestException, TimeoutError, ConnectionError) as exc:
        return _earnings_forecast_result("failed_network", reason=type(exc).__name__)
    except (ValueError, TypeError, _json.JSONDecodeError) as exc:
        return _earnings_forecast_result("failed_structure", reason=type(exc).__name__)
    except Exception as exc:
        logger.warning(
            "Eastmoney earnings forecast request failed for %s: %s", code, type(exc).__name__
        )
        return _earnings_forecast_result("failed_network", reason=type(exc).__name__)

    forecasts: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    window_start_year = _today().year - _EARNINGS_FORECAST_WINDOW_YEARS
    try:
        for row in raw_rows:
            notice_date = _earnings_forecast_date(
                _earnings_forecast_field(row, "NOTICE_DATE", "notice_date")
            )
            report_date = _earnings_forecast_date(
                _earnings_forecast_field(row, "REPORTDATE", "report_date")
            )
            forecast_type = _earnings_forecast_text(row, "FORECASTTYPE", "forecast_type")
            if notice_date is None or report_date is None or not forecast_type:
                raise ValueError("earnings forecast row missing required disclosure fields")
            # 业绩预告的价值在"最新"；超出窗口的陈年预告不进入载荷，
            # 以免陈旧区间被当作当前指引（公告日语义，§13.4 准入(3)）。
            if date.fromisoformat(notice_date).year < window_start_year:
                continue
            dedupe_key = (report_date, notice_date)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            forecasts.append(
                {
                    "report_date": report_date,
                    "notice_date": notice_date,
                    "forecast_type": forecast_type,
                    "profit_lower_yi": _earnings_forecast_yi(row, "FORECASTL", "forecastl"),
                    "profit_upper_yi": _earnings_forecast_yi(row, "FORECASTT", "forecastt"),
                    "increase_lower_pct": _earnings_forecast_number(row, "INCREASEL", "increasel"),
                    "increase_upper_pct": _earnings_forecast_number(row, "INCREASET", "increaset"),
                    "prior_year_profit_yi": _earnings_forecast_yi(row, "YEAREARLIER", "yearearlier"),
                    "content": _earnings_forecast_text(
                        row, "FORECASTCONTENT", "forecastcontent",
                        limit=_EARNINGS_FORECAST_CONTENT_MAX_CHARS,
                    ),
                    "change_reason": _earnings_forecast_text(
                        row, "CHANGEREASONDSCRPT", "changereasondscrpt",
                        limit=_EARNINGS_FORECAST_REASON_MAX_CHARS,
                    ),
                }
            )
            if len(forecasts) >= _EARNINGS_FORECAST_MAX_ROWS:
                break
    except (TypeError, ValueError) as exc:
        return _earnings_forecast_result("failed_structure", reason=type(exc).__name__)

    forecasts.sort(key=lambda item: (item["report_date"], item["notice_date"]), reverse=True)
    observed_at = datetime.now(_MARKET_TZ).isoformat(timespec="seconds")
    base = {
        "source": f"Eastmoney datacenter {_EARNINGS_FORECAST_REPORT_NAME}",
        "observed_at": observed_at,
        "as_of_date": _today().isoformat(),
        "window_years": _EARNINGS_FORECAST_WINDOW_YEARS,
        "forecast_count": len(forecasts),
        "latest_report_date": forecasts[0]["report_date"] if forecasts else None,
        "forecasts": forecasts,
    }
    if not forecasts:
        return _earnings_forecast_result("normal_empty", **base)
    return _earnings_forecast_result("success", **base)


# ---- get_shareholder_pledge / get_corporate_buyback (P1-EVENT-01) ----

_PLEDGE_REPORT_NAME = "RPT_CSDC_LIST"
_PLEDGE_PAGE_SIZE = 5
_PLEDGE_LABEL = "Eastmoney share pledge status"

_BUYBACK_REPORT_NAME = "RPTA_WEB_GETHGLIST_NEW"
_BUYBACK_PAGE_SIZE = 20
_BUYBACK_MAX_ROWS = 5
_BUYBACK_WINDOW_YEARS = 3
_BUYBACK_OBJECTIVE_MAX_CHARS = 120
_BUYBACK_LABEL = "Eastmoney share buyback plans"

# Progress codes as exposed by the Eastmoney buyback list (verified 2026-09-10
# against RPTA_WEB_GETHGLIST_NEW). Unknown codes fall back to the raw value.
_BUYBACK_PROGRESS_LABELS = {
    "001": "董事会预案",
    "002": "股东大会通过",
    "003": "股东大会否决",
    "004": "实施中",
    "005": "停止实施",
    "006": "完成实施",
}


def _dc_row_field(row: Mapping[str, Any], *names: str) -> Any:
    normalized = {str(key).lower(): value for key, value in row.items()}
    for name in names:
        value = normalized.get(name.lower())
        if value is not None:
            return value
    return None


def _dc_row_text(row: Mapping[str, Any], *names: str, limit: int = 0) -> str | None:
    value = _dc_row_field(row, *names)
    text = str(value or "").strip()
    if not text:
        return None
    return text[:limit] if limit else text


def _dc_row_number(row: Mapping[str, Any], *names: str) -> float | None:
    value = _dc_row_field(row, *names)
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(str(value).strip().replace(",", ""))
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _dc_row_date(value: Any) -> str | None:
    text = str(value or "").strip()[:10].replace("/", "-")
    if len(text) == 8 and text.isdigit():
        text = f"{text[:4]}-{text[4:6]}-{text[6:]}"
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError:
        return None


def _dc_amount_yi(row: Mapping[str, Any], *names: str) -> float | None:
    """Provider amounts are yuan; project to 亿元 for bounded readability.

    The provider fills ``0`` where no amount applies; an exactly-zero amount
    is not a real disclosure, so it is normalized to None instead of a fake
    "0.00 亿元".
    """
    value = _dc_row_number(row, *names)
    if value is None or value == 0:
        return None
    return round(value / 100_000_000, 4)


def _dc_report_rows(payload: object, label: str) -> list[Mapping[str, Any]]:
    """Accept only the datacenter report envelope, never a guessed fallback.

    The datacenter signals "no rows" with ``result: null`` + ``code: 9201``
    (返回数据为空) — that is a normal empty, never a failure.  Any other null
    result (e.g. 9501 unknown report) stays a structure failure.
    """
    if not isinstance(payload, Mapping):
        raise ValueError(f"{label} payload must be an object")
    result = payload.get("result")
    if result is None:
        if str(payload.get("code")) == "9201":
            return []
        raise ValueError(f"{label} payload has null result (code={payload.get('code')})")
    data = result.get("data") if isinstance(result, Mapping) else None
    if not isinstance(data, list):
        raise ValueError(f"{label} payload missing result.data list")
    if not all(isinstance(item, Mapping) for item in data):
        raise ValueError(f"{label} data list contains a non-object row")
    return list(data)


def _dc_result_count(payload: object) -> int | None:
    """Return ``result.count`` when the datacenter envelope reports one."""
    if not isinstance(payload, Mapping):
        return None
    result = payload.get("result")
    if not isinstance(result, Mapping):
        return None
    try:
        count = int(result.get("count"))
    except (TypeError, ValueError):
        return None
    return count if count >= 0 else None


def _dc_result(status: str, label: str, **fields: Any) -> str:
    """Return a parsable bounded payload while retaining ResultStore status markers."""
    payload = {"status": status, **fields}
    encoded = _json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if status == "normal_empty":
        return f"[正常空] {label}\n{encoded}"
    if status.startswith("failed"):
        return f"[数据缺失] {label}\n{encoded}"
    if status == "invalid_input":
        return f"Invalid ticker for {label}\n{encoded}"
    return encoded


def get_shareholder_pledge(
    ticker: Annotated[str, "6-digit A-share code (e.g. 600519)"],
) -> str:
    """Return the company's latest share pledge status (股权质押).

    The CSDC pledge series is a weekly outstanding stock-state snapshot
    covering listed shares: the latest row is the current pledge ratio, not
    an event announcement.  A near-zero ratio, or even an absent record,
    must never be stated as pledge safety or as the absence of shareholder
    risk.  Pledge shares/market-cap units are 万股/万元 (provider units).
    """
    try:
        code = _normalize_ticker(ticker)
    except (TypeError, ValueError) as exc:
        return _dc_result("invalid_input", _PLEDGE_LABEL, reason=type(exc).__name__)

    try:
        response = _em_get(
            _DATACENTER_URL,
            params={
                "reportName": _PLEDGE_REPORT_NAME,
                "columns": "ALL",
                "filter": f'(SECURITY_CODE="{code}")',
                "pageSize": _PLEDGE_PAGE_SIZE,
                "pageNumber": 1,
                "sortColumns": "TRADE_DATE",
                "sortTypes": "-1",
                "source": "WEB",
                "client": "WEB",
            },
            timeout=15,
        )
        raise_for_status = getattr(response, "raise_for_status", None)
        if callable(raise_for_status):
            raise_for_status()
        raw_rows = _dc_report_rows(response.json(), label=_PLEDGE_LABEL)
    except (_requests.RequestException, TimeoutError, ConnectionError) as exc:
        return _dc_result("failed_network", _PLEDGE_LABEL, reason=type(exc).__name__)
    except (ValueError, TypeError, _json.JSONDecodeError) as exc:
        return _dc_result("failed_structure", _PLEDGE_LABEL, reason=type(exc).__name__)
    except Exception as exc:
        logger.warning(
            "Eastmoney share pledge request failed for %s: %s", code, type(exc).__name__
        )
        return _dc_result("failed_network", _PLEDGE_LABEL, reason=type(exc).__name__)

    observed_at = datetime.now(_MARKET_TZ).isoformat(timespec="seconds")
    if not raw_rows:
        # code 9201 (no rows for this security) is a normal empty, never a
        # failure; it must stay distinguishable from a malformed payload.
        return _dc_result(
            "normal_empty",
            _PLEDGE_LABEL,
            source=f"Eastmoney datacenter {_PLEDGE_REPORT_NAME}",
            observed_at=observed_at,
            as_of_date=_today().isoformat(),
            trade_date=None,
            pledge_ratio_pct=None,
            pledge_deal_num=None,
            pledge_shares_wan=None,
            pledge_mcap_wan=None,
        )

    latest_trade_date: str | None = None
    latest_row: Mapping[str, Any] | None = None
    try:
        # Server-side sort is not trusted: pick the newest row that carries a
        # parsable date AND ratio, so a provider ordering change can never
        # feed a stale snapshot as "current".
        for row in raw_rows:
            trade_date = _dc_row_date(_dc_row_field(row, "TRADE_DATE", "trade_date"))
            ratio = _dc_row_number(row, "PLEDGE_RATIO", "pledge_ratio")
            if trade_date is None or ratio is None:
                continue
            if latest_trade_date is None or trade_date > latest_trade_date:
                latest_trade_date, latest_row = trade_date, row
        if latest_row is None:
            raise ValueError("pledge rows missing required TRADE_DATE/PLEDGE_RATIO")
        deal_num = _dc_row_number(latest_row, "PLEDGE_DEAL_NUM", "pledge_deal_num")
        # Provider quirk: REPURCHASE_BALANCE in this CSDC series is the
        # pledged-share balance in 万股; it is unrelated to corporate buybacks.
        shares_wan = _dc_row_number(latest_row, "REPURCHASE_BALANCE", "repurchase_balance")
        mcap_wan = _dc_row_number(latest_row, "PLEDGE_MARKET_CAP", "pledge_market_cap")
    except (TypeError, ValueError) as exc:
        return _dc_result("failed_structure", _PLEDGE_LABEL, reason=type(exc).__name__)

    base = {
        "source": f"Eastmoney datacenter {_PLEDGE_REPORT_NAME}",
        "observed_at": observed_at,
        "as_of_date": _today().isoformat(),
        "trade_date": latest_trade_date,
        "pledge_ratio_pct": _dc_row_number(latest_row, "PLEDGE_RATIO", "pledge_ratio"),
        "pledge_deal_num": int(deal_num) if deal_num is not None else None,
        "pledge_shares_wan": shares_wan,
        "pledge_mcap_wan": mcap_wan,
    }
    return _dc_result("success", _PLEDGE_LABEL, **base)


def get_corporate_buyback(
    ticker: Annotated[str, "6-digit A-share code (e.g. 600519)"],
) -> str:
    """Return the company's share buyback plans and progress (公司回购).

    Every record is a company buyback disclosure: announcement date
    (DIM_DATE), progress code, planned/executed amount range.  A buyback plan
    is company disclosure — never a buy signal and never a price-support
    guarantee; stopped or rejected plans are disclosed as-is.  Rows outside
    the recent 3-year announcement window are relevance-filtered.
    """
    try:
        code = _normalize_ticker(ticker)
    except (TypeError, ValueError) as exc:
        return _dc_result("invalid_input", _BUYBACK_LABEL, reason=type(exc).__name__)

    try:
        response = _em_get(
            _DATACENTER_URL,
            params={
                "reportName": _BUYBACK_REPORT_NAME,
                "columns": "ALL",
                "filter": f'(DIM_SCODE="{code}")',
                "pageSize": _BUYBACK_PAGE_SIZE,
                "pageNumber": 1,
                "sortColumns": "UPD,DIM_DATE,DIM_SCODE",
                "sortTypes": "-1,-1,-1",
                "source": "WEB",
                "client": "WEB",
            },
            timeout=15,
        )
        raise_for_status = getattr(response, "raise_for_status", None)
        if callable(raise_for_status):
            raise_for_status()
        raw_rows = _dc_report_rows(response.json(), label=_BUYBACK_LABEL)
    except (_requests.RequestException, TimeoutError, ConnectionError) as exc:
        return _dc_result("failed_network", _BUYBACK_LABEL, reason=type(exc).__name__)
    except (ValueError, TypeError, _json.JSONDecodeError) as exc:
        return _dc_result("failed_structure", _BUYBACK_LABEL, reason=type(exc).__name__)
    except Exception as exc:
        logger.warning(
            "Eastmoney share buyback request failed for %s: %s", code, type(exc).__name__
        )
        return _dc_result("failed_network", _BUYBACK_LABEL, reason=type(exc).__name__)

    buybacks: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    window_start_year = _today().year - _BUYBACK_WINDOW_YEARS
    try:
        for row in raw_rows:
            announced_date = _dc_row_date(_dc_row_field(row, "DIM_DATE", "dim_date"))
            progress_code = _dc_row_text(row, "REPURPROGRESS", "repurprogress")
            if announced_date is None or not progress_code:
                raise ValueError("buyback row missing required disclosure fields")
            if date.fromisoformat(announced_date).year < window_start_year:
                continue
            dedupe_key = (announced_date, progress_code)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            executed_shares = _dc_row_number(row, "REPURNUM", "repurnum")
            buybacks.append(
                {
                    "announced_date": announced_date,
                    "progress_code": progress_code,
                    "progress": _BUYBACK_PROGRESS_LABELS.get(progress_code, progress_code),
                    "plan_amount_lower_yi": _dc_amount_yi(row, "REPURAMOUNTLOWER", "repuramountlower"),
                    "plan_amount_upper_yi": _dc_amount_yi(row, "REPURAMOUNTLIMIT", "repuramountlimit"),
                    "executed_amount_yi": _dc_amount_yi(row, "REPURAMOUNT", "repuramount"),
                    "executed_shares_wan": (
                        round(executed_shares / 10_000, 2) if executed_shares else None
                    ),
                    "finish_date": _dc_row_date(_dc_row_field(row, "FINISHDATE", "finishdate")),
                    "objective": _dc_row_text(
                        row, "REPUROBJECTIVE", "repurobjective",
                        limit=_BUYBACK_OBJECTIVE_MAX_CHARS,
                    ),
                }
            )
            if len(buybacks) >= _BUYBACK_MAX_ROWS:
                break
    except (TypeError, ValueError) as exc:
        return _dc_result("failed_structure", _BUYBACK_LABEL, reason=type(exc).__name__)

    buybacks.sort(key=lambda item: item["announced_date"], reverse=True)
    observed_at = datetime.now(_MARKET_TZ).isoformat(timespec="seconds")
    base = {
        "source": f"Eastmoney datacenter {_BUYBACK_REPORT_NAME}",
        "observed_at": observed_at,
        "as_of_date": _today().isoformat(),
        "window_years": _BUYBACK_WINDOW_YEARS,
        "buyback_count": len(buybacks),
        "latest_announced_date": buybacks[0]["announced_date"] if buybacks else None,
        "buybacks": buybacks,
    }
    if not buybacks:
        return _dc_result("normal_empty", _BUYBACK_LABEL, **base)
    return _dc_result("success", _BUYBACK_LABEL, **base)


# ---- get_margin_trading / get_valuation_history (DEC-P1-24/25) ----

_MARGIN_REPORT_NAME = "RPTA_WEB_RZRQ_GGMX"
_MARGIN_MAX_ROWS = 10
_MARGIN_LABEL = "Eastmoney margin trading detail"

_VALUATION_REPORT_NAME = "RPT_VALUEANALYSIS_DET"
_VALUATION_PAGE_SIZE = 1000
_VALUATION_MAX_PAGES = 4
_VALUATION_MAX_ROWS = 3000
_VALUATION_MIN_SAMPLES = 60
_VALUATION_RELIABLE_SAMPLES = 250
_VALUATION_WINDOWS: tuple[tuple[str, int | None], ...] = (
    ("3y", 3),
    ("5y", 5),
    ("all", None),
)
_VALUATION_METRICS = ("pe_ttm", "pb_mrq")
_VALUATION_LABEL = "Eastmoney valuation history"

_MARGIN_BOUNDARY = (
    "东财数据中心两融明细为 T+1 披露，以返回的最新 DATE 为准（沪深披露不同步）；"
    "余额或净买入变化不是买卖信号或主力意图；无记录仅表示源端无该证券两融明细，"
    "不是无杠杆风险的证据。"
)
_VALUATION_BOUNDARY = (
    "估值为东财数据中心日线序列（老股自 2018 年起），分位为最新值在窗口样本中的"
    "历史相对位置；不构成买卖信号、目标价或收益预测；样本不足或最新值非正的窗口"
    "必须在报告中如实披露。"
)


def _dc_amount_plain_yi(row: Mapping[str, Any], *names: str) -> float | None:
    """Project provider yuan amounts to 亿元, keeping a real zero as zero."""
    value = _dc_row_number(row, *names)
    if value is None:
        return None
    return round(value / 100_000_000, 4)


def _dc_shares_wan(row: Mapping[str, Any], *names: str) -> float | None:
    """Project provider share quantities to 万股, keeping a real zero as zero."""
    value = _dc_row_number(row, *names)
    if value is None:
        return None
    return round(value / 10_000, 4)


def _valuation_percentile(values: list[float], current: float) -> float | None:
    usable = [value for value in values if math.isfinite(value)]
    if not usable:
        return None
    below = sum(1 for value in usable if value <= current)
    return round(below / len(usable) * 100, 2)


def _valuation_quantile(values: list[float], quantile: float) -> float | None:
    ordered = sorted(value for value in values if math.isfinite(value))
    if not ordered:
        return None
    position = (len(ordered) - 1) * quantile
    lower, upper = math.floor(position), math.ceil(position)
    if lower == upper:
        return round(ordered[lower], 4)
    fraction = position - lower
    blended = ordered[lower] * (1 - fraction) + ordered[upper] * fraction
    return round(blended, 4)


def get_margin_trading(
    ticker: Annotated[str, "6-digit A-share code (e.g. 600519)"],
) -> str:
    """Return the latest margin-trading (融资融券) records for one A-share.

    Each row is one disclosure date from the Eastmoney datacenter series
    (T+1).  The Shanghai and Shenzhen exchanges publish on different
    schedules, so every reference must cite the row's actual DATE instead of
    "today".  Financing/securities-lending amounts are 亿元, securities-lending
    quantities are 万股, and the balance ratio is percent of float market cap.
    A security outside the margin-trading list simply has no rows (normal
    empty, not a failure); an absent row is never evidence of low leverage
    risk, and balance changes are not a directional or "main force" signal.
    """
    try:
        code = _normalize_ticker(ticker)
    except (TypeError, ValueError) as exc:
        return _dc_result("invalid_input", _MARGIN_LABEL, reason=type(exc).__name__)

    try:
        response = _em_get(
            _DATACENTER_URL,
            params={
                "reportName": _MARGIN_REPORT_NAME,
                "columns": "ALL",
                "filter": f'(scode="{code}")',
                "pageSize": _MARGIN_MAX_ROWS,
                "pageNumber": 1,
                "sortColumns": "DATE",
                "sortTypes": "-1",
                "source": "WEB",
                "client": "WEB",
            },
            timeout=15,
        )
        raise_for_status = getattr(response, "raise_for_status", None)
        if callable(raise_for_status):
            raise_for_status()
        raw_rows = _dc_report_rows(response.json(), label=_MARGIN_LABEL)
    except (_requests.RequestException, TimeoutError, ConnectionError) as exc:
        return _dc_result("failed_network", _MARGIN_LABEL, reason=type(exc).__name__)
    except (ValueError, TypeError, _json.JSONDecodeError) as exc:
        return _dc_result("failed_structure", _MARGIN_LABEL, reason=type(exc).__name__)
    except Exception as exc:
        logger.warning(
            "Eastmoney margin trading request failed for %s: %s", code, type(exc).__name__
        )
        return _dc_result("failed_network", _MARGIN_LABEL, reason=type(exc).__name__)

    observed_at = datetime.now(_MARKET_TZ).isoformat(timespec="seconds")
    if not raw_rows:
        # code 9201 (no rows for this security) is a normal empty: the stock
        # is not on the margin-trading list or the source has no row for it.
        return _dc_result(
            "normal_empty",
            _MARGIN_LABEL,
            source=f"Eastmoney datacenter {_MARGIN_REPORT_NAME}",
            observed_at=observed_at,
            latest_date=None,
            market=None,
            name=None,
            records=[],
            boundary=_MARGIN_BOUNDARY,
        )

    parsed: dict[str, dict[str, Any]] = {}
    meta_by_date: dict[str, tuple[str | None, str | None]] = {}
    try:
        for row in raw_rows:
            row_date = _dc_row_date(_dc_row_field(row, "DATE", "date"))
            if row_date is None:
                continue
            parsed.setdefault(
                row_date,
                {
                    "date": row_date,
                    "financing_balance_yi": _dc_amount_plain_yi(row, "RZYE", "rzye"),
                    "securities_lending_balance_yi": _dc_amount_plain_yi(row, "RQYE", "rqye"),
                    "margin_balance_yi": _dc_amount_plain_yi(row, "RZRQYE", "rzrqye"),
                    "financing_buy_yi": _dc_amount_plain_yi(row, "RZMRE", "rzmre"),
                    "financing_repay_yi": _dc_amount_plain_yi(row, "RZCHE", "rzche"),
                    "financing_net_buy_yi": _dc_amount_plain_yi(row, "RZJME", "rzjme"),
                    "securities_lending_volume_wan_shares": _dc_shares_wan(row, "RQYL", "rqyl"),
                    "securities_lending_sell_wan_shares": _dc_shares_wan(row, "RQMCL", "rqmcl"),
                    "financing_balance_pct_of_float": _dc_row_number(row, "RZYEZB", "rzyezb"),
                    "financing_buy_3d_yi": _dc_amount_plain_yi(row, "RZMRE3D", "rzmre3d"),
                    "financing_buy_5d_yi": _dc_amount_plain_yi(row, "RZMRE5D", "rzmre5d"),
                    "financing_buy_10d_yi": _dc_amount_plain_yi(row, "RZMRE10D", "rzmre10d"),
                    "financing_net_buy_3d_yi": _dc_amount_plain_yi(row, "RZJME3D", "rzjme3d"),
                    "financing_net_buy_5d_yi": _dc_amount_plain_yi(row, "RZJME5D", "rzjme5d"),
                    "financing_net_buy_10d_yi": _dc_amount_plain_yi(row, "RZJME10D", "rzjme10d"),
                    "close": _dc_row_number(row, "SPJ", "spj"),
                    "change_pct": _dc_row_number(row, "ZDF", "zdf"),
                },
            )
            meta_by_date.setdefault(
                row_date,
                (
                    _dc_row_text(row, "MARKET", "market"),
                    _dc_row_text(row, "SECNAME", "secname"),
                ),
            )
    except (TypeError, ValueError) as exc:
        return _dc_result("failed_structure", _MARGIN_LABEL, reason=type(exc).__name__)
    if not parsed:
        return _dc_result(
            "failed_structure", _MARGIN_LABEL, reason="rows missing required DATE"
        )

    records = sorted(parsed.values(), key=lambda item: item["date"], reverse=True)
    records = records[:_MARGIN_MAX_ROWS]
    latest_date = records[0]["date"]
    market, name = meta_by_date.get(latest_date, (None, None))
    return _dc_result(
        "success",
        _MARGIN_LABEL,
        source=f"Eastmoney datacenter {_MARGIN_REPORT_NAME}",
        observed_at=observed_at,
        latest_date=latest_date,
        market=market,
        name=name,
        records=records,
        boundary=_MARGIN_BOUNDARY,
    )


def get_valuation_history(
    ticker: Annotated[str, "6-digit A-share code (e.g. 600519)"],
) -> str:
    """Return the Eastmoney daily valuation series and its percentile snapshot.

    The series carries PE_TTM/PE_LAR/PB_MRQ/PS_TTM/PCF/PEG and market cap per
    trading day (provider history begins 2018 for older listings; newer
    listings start at their listing date).  Each window percentile is the
    latest value's rank inside the samples actually fetched, so a window with
    too few samples (recent listings) is disclosed as insufficient rather than
    extrapolated.  Percentiles are historical relative positions, never
    buy/sell signals, price targets, or return forecasts; a non-positive
    latest PE/PB makes the percentile inapplicable and must be stated as such.
    """
    try:
        code = _normalize_ticker(ticker)
    except (TypeError, ValueError) as exc:
        return _dc_result("invalid_input", _VALUATION_LABEL, reason=type(exc).__name__)

    rows: list[Mapping[str, Any]] = []
    provider_count: int | None = None
    try:
        for page_number in range(1, _VALUATION_MAX_PAGES + 1):
            response = _em_get(
                _DATACENTER_URL,
                params={
                    "reportName": _VALUATION_REPORT_NAME,
                    "columns": "ALL",
                    "filter": f'(SECURITY_CODE="{code}")',
                    "pageSize": _VALUATION_PAGE_SIZE,
                    "pageNumber": page_number,
                    "sortColumns": "TRADE_DATE",
                    "sortTypes": "-1",
                    "source": "WEB",
                    "client": "WEB",
                },
                timeout=20,
            )
            raise_for_status = getattr(response, "raise_for_status", None)
            if callable(raise_for_status):
                raise_for_status()
            payload = response.json()
            if provider_count is None:
                provider_count = _dc_result_count(payload)
            page_rows = _dc_report_rows(payload, label=_VALUATION_LABEL)
            if not page_rows:
                break
            rows.extend(page_rows)
            if len(rows) >= _VALUATION_MAX_ROWS:
                break
            if len(page_rows) < _VALUATION_PAGE_SIZE:
                break
            if provider_count is not None and len(rows) >= provider_count:
                break
    except (_requests.RequestException, TimeoutError, ConnectionError) as exc:
        return _dc_result("failed_network", _VALUATION_LABEL, reason=type(exc).__name__)
    except (ValueError, TypeError, _json.JSONDecodeError) as exc:
        return _dc_result("failed_structure", _VALUATION_LABEL, reason=type(exc).__name__)
    except Exception as exc:
        logger.warning(
            "Eastmoney valuation history request failed for %s: %s",
            code,
            type(exc).__name__,
        )
        return _dc_result("failed_network", _VALUATION_LABEL, reason=type(exc).__name__)

    observed_at = datetime.now(_MARKET_TZ).isoformat(timespec="seconds")
    truncated = len(rows) >= _VALUATION_MAX_ROWS or (
        provider_count is not None and provider_count > len(rows)
    )
    if not rows:
        return _dc_result(
            "normal_empty",
            _VALUATION_LABEL,
            source=f"Eastmoney datacenter {_VALUATION_REPORT_NAME}",
            observed_at=observed_at,
            as_of_date=_today().isoformat(),
            latest_date=None,
            metrics=None,
            percentiles=None,
            history={
                "fetched_rows": 0,
                "sample_count": 0,
                "provider_count": provider_count,
                "truncated": False,
            },
        )

    samples: dict[str, dict[str, Any]] = {}
    for row in rows:
        row_date = _dc_row_date(_dc_row_field(row, "TRADE_DATE", "trade_date"))
        if row_date is None:
            continue
        samples.setdefault(
            row_date,
            {
                "close_price": _dc_row_number(row, "CLOSE_PRICE", "close_price"),
                "pe_ttm": _dc_row_number(row, "PE_TTM", "pe_ttm"),
                "pe_static": _dc_row_number(row, "PE_LAR", "pe_lar"),
                "pb_mrq": _dc_row_number(row, "PB_MRQ", "pb_mrq"),
                "ps_ttm": _dc_row_number(row, "PS_TTM", "ps_ttm"),
                "pcf_ocf_ttm": _dc_row_number(row, "PCF_OCF_TTM", "pcf_ocf_ttm"),
                "peg_car": _dc_row_number(row, "PEG_CAR", "peg_car"),
                "market_cap_yuan": _dc_row_number(
                    row, "TOTAL_MARKET_CAP", "total_market_cap"
                ),
                "float_market_cap_yuan": _dc_row_number(
                    row, "NOTLIMITED_MARKETCAP_A", "notlimited_marketcap_a"
                ),
                "board_name": _dc_row_text(row, "BOARD_NAME", "board_name"),
            },
        )

    ordered = sorted(samples.items(), key=lambda item: item[0], reverse=True)
    if not ordered:
        return _dc_result(
            "failed_structure", _VALUATION_LABEL, reason="rows missing required TRADE_DATE"
        )
    latest_date, latest = ordered[0]

    window_samples: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    for window_name, years in _VALUATION_WINDOWS:
        if years is None:
            window_samples[window_name] = ordered
        else:
            earliest = date.fromisoformat(latest_date) - timedelta(days=365 * years)
            window_samples[window_name] = [
                item for item in ordered if date.fromisoformat(item[0]) >= earliest
            ]

    percentiles: dict[str, dict[str, Any]] = {}
    for metric in _VALUATION_METRICS:
        latest_value = latest.get(metric)
        latest_number = (
            float(latest_value)
            if isinstance(latest_value, (int, float)) and not isinstance(latest_value, bool)
            else None
        )
        metric_windows: dict[str, dict[str, Any]] = {}
        for window_name, _years in _VALUATION_WINDOWS:
            selected = window_samples[window_name]
            values = [
                float(item.get(metric))
                for _sample_date, item in selected
                if isinstance(item.get(metric), (int, float))
                and not isinstance(item.get(metric), bool)
                and math.isfinite(float(item.get(metric)))
            ]
            non_positive = sum(1 for value in values if value <= 0)
            entry: dict[str, Any] = {
                "window_start": selected[-1][0] if selected else None,
                "window_end": latest_date,
                "sample_count": len(values),
                "non_positive_samples": non_positive,
            }
            if latest_number is None:
                entry["percentile"] = None
                entry["reliability"] = "unavailable"
                entry["note"] = "最新值缺失"
            elif latest_number <= 0:
                entry["percentile"] = None
                entry["reliability"] = "unavailable"
                entry["note"] = "最新值为非正（亏损），历史分位不适用"
            elif len(values) < _VALUATION_MIN_SAMPLES:
                entry["percentile"] = None
                entry["reliability"] = "insufficient_samples"
                entry["note"] = f"样本不足（{len(values)} 个交易日）"
            else:
                entry["percentile"] = _valuation_percentile(values, latest_number)
                entry["reliability"] = (
                    "ok"
                    if len(values) >= _VALUATION_RELIABLE_SAMPLES
                    else "limited_samples"
                )
                if non_positive:
                    entry["note"] = (
                        f"窗口含 {non_positive} 个非正值（亏损期）样本，"
                        "分位以全部有效样本计算"
                    )
            metric_windows[window_name] = entry
        all_values = [
            float(item.get(metric))
            for _sample_date, item in window_samples["all"]
            if isinstance(item.get(metric), (int, float))
            and not isinstance(item.get(metric), bool)
            and math.isfinite(float(item.get(metric)))
        ]
        percentiles[metric] = {
            "latest": latest_number,
            "windows": metric_windows,
            "all_quantiles": {
                "p10": _valuation_quantile(all_values, 0.10),
                "p25": _valuation_quantile(all_values, 0.25),
                "p50": _valuation_quantile(all_values, 0.50),
                "p75": _valuation_quantile(all_values, 0.75),
                "p90": _valuation_quantile(all_values, 0.90),
            },
        }

    market_cap_yuan = latest.get("market_cap_yuan")
    float_market_cap_yuan = latest.get("float_market_cap_yuan")
    return _dc_result(
        "success",
        _VALUATION_LABEL,
        source=f"Eastmoney datacenter {_VALUATION_REPORT_NAME}",
        observed_at=observed_at,
        as_of_date=latest_date,
        latest_date=latest_date,
        close_price=latest.get("close_price"),
        metrics={
            "pe_ttm": latest.get("pe_ttm"),
            "pe_static": latest.get("pe_static"),
            "pb_mrq": latest.get("pb_mrq"),
            "ps_ttm": latest.get("ps_ttm"),
            "pcf_ocf_ttm": latest.get("pcf_ocf_ttm"),
            "peg_car": latest.get("peg_car"),
        },
        market_cap_yi=(
            round(float(market_cap_yuan) / 100_000_000, 4)
            if isinstance(market_cap_yuan, (int, float))
            else None
        ),
        float_market_cap_yi=(
            round(float(float_market_cap_yuan) / 100_000_000, 4)
            if isinstance(float_market_cap_yuan, (int, float))
            else None
        ),
        board_name=latest.get("board_name"),
        percentiles=percentiles,
        history={
            "fetched_rows": len(rows),
            "sample_count": len(ordered),
            "first_date": ordered[-1][0],
            "last_date": latest_date,
            "provider_count": provider_count,
            "truncated": truncated,
            "min_samples": _VALUATION_MIN_SAMPLES,
        },
        boundary=_VALUATION_BOUNDARY,
    )


# ---- get_macro_indicators (DEC-P1-26 / P1-MACRO-01) ----

_MACRO_LABEL = "Eastmoney macro economy"
_MACRO_MAX_PERIODS = 6
_MACRO_BOUNDARY = (
    "宏观指标为东财数据中心对国家统计局/央行等官方发布的聚合转述，不是官方原始口径；"
    "月度/季度发布存在滞后，源端只提供数据所属期（REPORT_DATE/TIME），不提供逐行发布日期，"
    "发布时点只能以采集时点（observed_at）与发布节奏共同披露；引用必须标注数据所属期，"
    "禁止用采集日/查询日冒充数据期；未采集或源端无记录不代表该期无数据；同期数值可能被后续"
    "修正，源端不区分初值与修正值时按不确定性披露；本数据不构成预测、景气打分或交易信号。"
)

# 第一梯队四端点（DEC-P1-26 实测范围）。字段名以 2026-09-13 生产 `_em_get()` 实测契约为准；
# 未知结构按 failed_structure 闭合（禁止静默补零）。社融端点未定位（权威源为人民银行），
# 不在本工具范围。
_MACRO_INDICATORS: tuple[dict[str, Any], ...] = (
    {
        "indicator": "pmi",
        "label": "采购经理指数（PMI，月度）",
        "report_name": "RPT_ECONOMY_PMI",
        "value_fields": (
            ("make_index", ("MAKE_INDEX",), "制造业PMI（指数，50为荣枯线）"),
            ("make_same", ("MAKE_SAME",), "制造业PMI较上期变化（百分点）"),
            ("nmake_index", ("NMAKE_INDEX",), "非制造业商务活动指数"),
            ("nmake_same", ("NMAKE_SAME",), "非制造业商务活动指数较上期变化（百分点）"),
        ),
    },
    {
        "indicator": "cpi",
        "label": "居民消费价格指数（CPI，月度）",
        "report_name": "RPT_ECONOMY_CPI",
        "value_fields": (
            ("national_same", ("NATIONAL_SAME",), "全国同比（%）"),
            ("national_sequential", ("NATIONAL_SEQUENTIAL",), "全国环比（%）"),
            ("national_accumulate", ("NATIONAL_ACCUMULATE",), "全国累计（%）"),
            ("national_base", ("NATIONAL_BASE",), "全国定基指数（上年同月=100）"),
            ("city_same", ("CITY_SAME",), "城市同比（%）"),
            ("rural_same", ("RURAL_SAME",), "农村同比（%）"),
        ),
    },
    {
        "indicator": "ppi",
        "label": "工业生产者出厂价格指数（PPI，月度）",
        "report_name": "RPT_ECONOMY_PPI",
        "value_fields": (
            ("base_same", ("BASE_SAME",), "同比（%）"),
            ("base_accumulate", ("BASE_ACCUMULATE",), "累计同比（%）"),
            ("base", ("BASE",), "定基指数"),
        ),
    },
    {
        "indicator": "gdp",
        "label": "国内生产总值（GDP，季度）",
        "report_name": "RPT_ECONOMY_GDP",
        "value_fields": (
            ("sum_same", ("SUM_SAME",), "国内生产总值同比（%）"),
            (
                "domestic_product_base",
                ("DOMESTICL_PRODUCT_BASE", "DOMESTIC_PRODUCT_BASE"),
                "国内生产总值（亿元；源端字段拼写为 DOMESTICL_PRODUCT_BASE）",
            ),
            ("first_same", ("FIRST_SAME",), "第一产业同比（%）"),
            ("second_same", ("SECOND_SAME",), "第二产业同比（%）"),
            ("third_same", ("THIRD_SAME",), "第三产业同比（%）"),
        ),
    },
)


def _macro_indicator_request(definition: Mapping[str, Any]) -> dict[str, Any]:
    """Fetch one macro endpoint and return its bounded parsed payload."""
    report_name = str(definition["report_name"])
    try:
        response = _em_get(
            _DATACENTER_URL,
            params={
                "reportName": report_name,
                "columns": "ALL",
                "pageSize": _MACRO_MAX_PERIODS,
                "pageNumber": 1,
                "sortColumns": "REPORT_DATE",
                "sortTypes": "-1",
                "source": "WEB",
                "client": "WEB",
            },
            timeout=20,
        )
        raise_for_status = getattr(response, "raise_for_status", None)
        if callable(raise_for_status):
            raise_for_status()
        payload = response.json()
        provider_count = _dc_result_count(payload)
        raw_rows = _dc_report_rows(payload, label=report_name)
    except (_requests.RequestException, TimeoutError, ConnectionError) as exc:
        return {
            "status": "failed_network",
            "error": type(exc).__name__,
            "periods": [],
            "provider_count": None,
        }
    except (ValueError, TypeError, _json.JSONDecodeError) as exc:
        return {
            "status": "failed_structure",
            "error": type(exc).__name__,
            "periods": [],
            "provider_count": None,
        }
    except Exception as exc:
        logger.warning(
            "Eastmoney macro indicator request failed for %s: %s",
            report_name,
            type(exc).__name__,
        )
        return {
            "status": "failed_network",
            "error": type(exc).__name__,
            "periods": [],
            "provider_count": None,
        }

    periods: dict[str, dict[str, Any]] = {}
    for row in raw_rows:
        report_date = _dc_row_date(_dc_row_field(row, "REPORT_DATE", "report_date"))
        if report_date is None:
            continue
        values: dict[str, float] = {}
        for key, names, _label in definition["value_fields"]:
            number = _dc_row_number(row, *names)
            if number is not None:
                values[key] = number
        periods.setdefault(
            report_date,
            {
                "report_date": report_date,
                "period_label": _dc_row_text(row, "TIME", "time"),
                "values": values,
            },
        )
    ordered = sorted(
        periods.values(), key=lambda item: item["report_date"], reverse=True
    )
    if not ordered:
        if not raw_rows:
            return {
                "status": "normal_empty",
                "error": None,
                "periods": [],
                "provider_count": provider_count,
            }
        return {
            "status": "failed_structure",
            "error": "rows missing required REPORT_DATE",
            "periods": [],
            "provider_count": provider_count,
        }
    return {
        "status": "success",
        "error": None,
        "periods": ordered[:_MACRO_MAX_PERIODS],
        "provider_count": provider_count,
    }


def get_macro_indicators() -> str:
    """Return a bounded first-tier macro snapshot from the Eastmoney datacenter.

    Covers PMI, CPI, PPI and quarterly GDP (the minimal macro set for the
    policy/regime context).  Each reading carries its data period
    (``report_date`` plus the provider's ``period_label``).  The source does
    not provide a per-row publication date, so the collection time
    (``observed_at``) and the known monthly/quarterly release cadence must be
    disclosed instead: never cite the query/collection date as the data
    period, and never read an uncollected indicator as "the period had no
    data".  Values may be revised by later releases; the source does not
    distinguish preliminary from revised values, so treat them with the
    documented uncertainty.  This is contextual fact from Eastmoney's
    aggregation of official statistics (not the official original release),
    never a forecast, sentiment score, or trading signal.  Social financing
    (社融) is intentionally out of scope: its authoritative publisher is the
    PBoC and no working free endpoint has been located.
    """
    observed_at = datetime.now(_MARKET_TZ).isoformat(timespec="seconds")
    indicators: list[dict[str, Any]] = []
    failed: dict[str, str] = {}
    empty: list[str] = []
    any_data = False
    has_structure_failure = False
    for definition in _MACRO_INDICATORS:
        result = _macro_indicator_request(definition)
        status = str(result["status"])
        periods = result["periods"]
        indicators.append(
            {
                "indicator": definition["indicator"],
                "label": definition["label"],
                "source_report": definition["report_name"],
                "status": status,
                "latest_period": periods[0]["report_date"] if periods else None,
                "periods": periods,
                "provider_count": result["provider_count"],
                "error": result["error"],
                "field_labels": {
                    key: label for key, _names, label in definition["value_fields"]
                },
            }
        )
        if status == "success":
            any_data = True
        elif status == "normal_empty":
            empty.append(str(definition["indicator"]))
        else:
            failed[str(definition["indicator"])] = status
            has_structure_failure = (
                has_structure_failure or status == "failed_structure"
            )

    base: dict[str, Any] = {
        "source": "Eastmoney datacenter RPT_ECONOMY_PMI/CPI/PPI/GDP",
        "observed_at": observed_at,
        "as_of_date": _today().isoformat(),
        "period_note": "数据所属期见各期 report_date/period_label；源端不提供逐行发布日期。",
        "indicators": indicators,
        "failed_indicators": failed,
        "empty_indicators": empty,
        "boundary": _MACRO_BOUNDARY,
    }
    if any_data:
        return _dc_result("success", _MACRO_LABEL, **base)
    if failed:
        overall = "failed_structure" if has_structure_failure else "failed_network"
        return _dc_result(overall, _MACRO_LABEL, **base)
    return _dc_result("normal_empty", _MACRO_LABEL, **base)


# ---- get_disclosure_schedule / get_suspension_info / get_delisting_info (DEC-P1-15A/15B) ----

_SCHEDULE_REPORT_NAME = "RPT_PUBLIC_BS_APPOIN"
_SCHEDULE_MAX_ROWS = 4
_SCHEDULE_LABEL = "Eastmoney disclosure schedule"

_SUSPEND_REPORT_NAME = "RPT_CUSTOM_SUSPEND_DATA_INTERFACE"
_SUSPEND_PAGE_SIZE = 500
_SUSPEND_LABEL = "Eastmoney suspend/resume snapshot"

_DELIST_LABEL = "Exchange official delisting records"
_DELIST_CACHE_FILE = "delist-list.json"
_DELIST_SZSE_MAX_PAGES = 11
_DELIST_SZSE_PAGE_GAP_S = 0.25
_SSE_DELIST_URL = "https://query.sse.com.cn/commonQuery.do"
_SZSE_DELIST_URL = "https://www.szse.cn/api/report/ShowReport/data"


def get_disclosure_schedule(
    ticker: Annotated[str, "6-digit A-share code (e.g. 600519)"],
) -> str:
    """Return the company's periodic-report disclosure schedule (财报日历).

    Each row is one report period: the first appointed disclosure date, the
    current appointed date (may have been rescheduled), and the actual
    publish date once disclosed.  An appointed date is a company plan, not a
    guarantee; only ``actual_publish_date`` means the report exists.  An
    upcoming appointed date near the analysis date is a disclosure-window
    risk flag, not a trading signal.
    """
    try:
        code = _normalize_ticker(ticker)
    except (TypeError, ValueError) as exc:
        return _dc_result("invalid_input", _SCHEDULE_LABEL, reason=type(exc).__name__)

    try:
        response = _em_get(
            _DATACENTER_URL,
            params={
                "reportName": _SCHEDULE_REPORT_NAME,
                "columns": "ALL",
                "filter": f'(SECURITY_CODE="{code}")',
                "pageSize": _SCHEDULE_MAX_ROWS * 2,
                "pageNumber": 1,
                "sortColumns": "REPORT_DATE",
                "sortTypes": "-1",
                "source": "WEB",
                "client": "WEB",
            },
            timeout=15,
        )
        raise_for_status = getattr(response, "raise_for_status", None)
        if callable(raise_for_status):
            raise_for_status()
        raw_rows = _dc_report_rows(response.json(), label=_SCHEDULE_LABEL)
    except (_requests.RequestException, TimeoutError, ConnectionError) as exc:
        return _dc_result("failed_network", _SCHEDULE_LABEL, reason=type(exc).__name__)
    except (ValueError, TypeError, _json.JSONDecodeError) as exc:
        return _dc_result("failed_structure", _SCHEDULE_LABEL, reason=type(exc).__name__)
    except Exception as exc:
        logger.warning(
            "Eastmoney disclosure schedule request failed for %s: %s",
            code,
            type(exc).__name__,
        )
        return _dc_result("failed_network", _SCHEDULE_LABEL, reason=type(exc).__name__)

    try:
        # Server-side sort is not trusted: keep the newest rows that carry a
        # parsable report date, so a provider ordering change can never feed
        # a stale period as "latest".
        parsed_rows: list[dict[str, Any]] = []
        for row in raw_rows:
            report_date = _dc_row_date(_dc_row_field(row, "REPORT_DATE", "report_date"))
            if report_date is None:
                continue
            parsed_rows.append(
                {
                    "report_date": report_date,
                    "first_appointed_date": _dc_row_date(
                        _dc_row_field(row, "FIRST_APPOINT_DATE", "first_appoint_date")
                    ),
                    "appointed_date": _dc_row_date(
                        _dc_row_field(row, "APPOINT_PUBLISH_DATE", "appoint_publish_date")
                    ),
                    "actual_publish_date": _dc_row_date(
                        _dc_row_field(row, "ACTUAL_PUBLISH_DATE", "actual_publish_date")
                    ),
                    "modify_times": _dc_row_number(
                        row, "MODIFY_TIMES", "modify_times"
                    ),
                }
            )
        parsed_rows.sort(key=lambda item: item["report_date"], reverse=True)
        parsed_rows = parsed_rows[:_SCHEDULE_MAX_ROWS]
    except (TypeError, ValueError) as exc:
        return _dc_result("failed_structure", _SCHEDULE_LABEL, reason=type(exc).__name__)

    observed_at = datetime.now(_MARKET_TZ).isoformat(timespec="seconds")
    base = {
        "source": f"Eastmoney datacenter {_SCHEDULE_REPORT_NAME}",
        "observed_at": observed_at,
        "as_of_date": _today().isoformat(),
        "schedule_count": len(parsed_rows),
        "latest_report_date": parsed_rows[0]["report_date"] if parsed_rows else None,
        "latest_appointed_date": parsed_rows[0]["appointed_date"] if parsed_rows else None,
        "schedule": parsed_rows,
    }
    if not parsed_rows:
        return _dc_result("normal_empty", _SCHEDULE_LABEL, **base)
    return _dc_result("success", _SCHEDULE_LABEL, **base)


def get_suspension_info(
    ticker: Annotated[str, "6-digit A-share code (e.g. 600519)"],
    curr_date: Annotated[str, "Snapshot date YYYY-MM-DD"],
) -> str:
    """Return the stock's suspension record in that day's suspend/resume snapshot (停牌).

    The source is a per-date market-wide snapshot: a matching row means the
    stock was suspended (or had an announced suspension whose start time may
    still be in the future, e.g. 刊登重要公告/重大资产重组).  Absence from the
    snapshot is a normal empty — it means no suspension record on that date,
    never "never suspended" and never a statement about liquidity quality.
    """
    try:
        code = _normalize_ticker(ticker)
        snapshot_date = date.fromisoformat(str(curr_date)[:10]).isoformat()
    except (TypeError, ValueError) as exc:
        return _dc_result("invalid_input", _SUSPEND_LABEL, reason=type(exc).__name__)

    try:
        response = _em_get(
            _DATACENTER_URL,
            params={
                "reportName": _SUSPEND_REPORT_NAME,
                "columns": "ALL",
                # The provider rejects filters without MARKET (verified
                # 2026-09-10, code 9501); per-stock filtering is client-side.
                "filter": f'(MARKET="全部")(DATETIME=\'{snapshot_date}\')',
                "pageSize": _SUSPEND_PAGE_SIZE,
                "pageNumber": 1,
                "sortColumns": "SUSPEND_START_DATE",
                "sortTypes": "-1",
                "source": "WEB",
                "client": "WEB",
            },
            timeout=15,
        )
        raise_for_status = getattr(response, "raise_for_status", None)
        if callable(raise_for_status):
            raise_for_status()
        response_payload = response.json()
        raw_rows = _dc_report_rows(response_payload, label=_SUSPEND_LABEL)
        reported_count = _dc_result_count(response_payload)
    except (_requests.RequestException, TimeoutError, ConnectionError) as exc:
        return _dc_result("failed_network", _SUSPEND_LABEL, reason=type(exc).__name__)
    except (ValueError, TypeError, _json.JSONDecodeError) as exc:
        return _dc_result("failed_structure", _SUSPEND_LABEL, reason=type(exc).__name__)
    except Exception as exc:
        logger.warning(
            "Eastmoney suspend snapshot request failed for %s: %s",
            code,
            type(exc).__name__,
        )
        return _dc_result("failed_network", _SUSPEND_LABEL, reason=type(exc).__name__)

    try:
        matched: Mapping[str, Any] | None = None
        for row in raw_rows:
            row_code = _dc_row_text(row, "SECURITY_CODE", "security_code")
            if row_code == code:
                matched = row
                break
        if matched is None:
            if reported_count is not None and reported_count > len(raw_rows):
                # The market-wide snapshot was paginated below its reported
                # size; absence from the fetched page is NOT a no-suspension
                # answer (v0.5.0 CR-UNIFIED-CAPABILITY-OWNERSHIP hygiene fix).
                return _dc_result(
                    "failed_structure",
                    _SUSPEND_LABEL,
                    reason="snapshot_truncated",
                    snapshot_date=snapshot_date,
                    snapshot_rows=len(raw_rows),
                    reported_count=reported_count,
                )
            observed_at = datetime.now(_MARKET_TZ).isoformat(timespec="seconds")
            return _dc_result(
                "normal_empty",
                _SUSPEND_LABEL,
                source=f"Eastmoney datacenter {_SUSPEND_REPORT_NAME}",
                observed_at=observed_at,
                as_of_date=_today().isoformat(),
                snapshot_date=snapshot_date,
                snapshot_rows=len(raw_rows),
                suspended=False,
                suspend_start_time=None,
                suspend_expire=None,
                suspend_reason=None,
                trade_market=None,
                predict_resume_date=None,
            )
        start_time = _dc_row_text(matched, "SUSPEND_START_TIME", "suspend_start_time")
        start_date = _dc_row_date(_dc_row_field(matched, "SUSPEND_START_DATE", "suspend_start_date"))
        if start_date is None:
            raise ValueError("suspend row missing required SUSPEND_START_DATE")
        payload = {
            "source": f"Eastmoney datacenter {_SUSPEND_REPORT_NAME}",
            "observed_at": datetime.now(_MARKET_TZ).isoformat(timespec="seconds"),
            "as_of_date": _today().isoformat(),
            "snapshot_date": snapshot_date,
            "snapshot_rows": len(raw_rows),
            "suspended": True,
            "security_name": _dc_row_text(matched, "SECURITY_NAME_ABBR", "security_name_abbr", limit=20),
            "suspend_start_date": start_date,
            "suspend_start_time": start_time,
            "suspend_expire": _dc_row_text(matched, "SUSPEND_EXPIRE", "suspend_expire", limit=30),
            "suspend_reason": _dc_row_text(matched, "SUSPEND_REASON", "suspend_reason", limit=80),
            "trade_market": _dc_row_text(matched, "TRADE_MARKET", "trade_market", limit=20),
            "predict_resume_date": _dc_row_date(
                _dc_row_field(matched, "PREDICT_RESUME_DATE", "predict_resume_date")
            ),
        }
    except (TypeError, ValueError) as exc:
        return _dc_result("failed_structure", _SUSPEND_LABEL, reason=type(exc).__name__)
    return _dc_result("success", _SUSPEND_LABEL, **payload)


def _delist_cache_path() -> str:
    """退市名单磁盘日缓存路径（与名称映射/北向缓存同目录）。"""
    try:
        from .config import get_config

        cache_dir = get_config().get(
            "data_cache_dir", os.path.expanduser("~/.chstockdata/cache")
        )
    except Exception:  # pragma: no cover - 配置不可用时退回默认目录
        cache_dir = os.path.expanduser("~/.chstockdata/cache")
    return os.path.join(cache_dir, _DELIST_CACHE_FILE)


def _normalize_delist_date(value: Any) -> str | None:
    return _dc_row_date(value)


def _sse_delist_rows(http_get) -> list[dict[str, Any]]:
    """Fetch the SSE terminated-listing board (one bounded page covers it)."""
    response = http_get(
        "sse",
        _SSE_DELIST_URL,
        params={
            "sqlId": "COMMON_SSE_CP_GPJCTPZ_GPLB_GP_L",
            "isPagination": "true",
            "STOCK_CODE": "",
            "CSRC_CODE": "",
            "REG_PROVINCE": "",
            "STOCK_TYPE": "1,2,8",
            "COMPANY_STATUS": "3",
            "type": "inParams",
            "pageHelp.cacheSize": "1",
            "pageHelp.beginPage": "1",
            "pageHelp.pageSize": "500",
            "pageHelp.pageNo": "1",
            "pageHelp.endPage": "1",
        },
        headers={"Referer": "https://www.sse.com.cn/"},
        timeout=20,
    )
    raise_for_status = getattr(response, "raise_for_status", None)
    if callable(raise_for_status):
        raise_for_status()
    payload = response.json()
    page_help = payload.get("pageHelp") if isinstance(payload, Mapping) else None
    data = page_help.get("data") if isinstance(page_help, Mapping) else None
    if not isinstance(data, list):
        raise ValueError("sse delist payload missing pageHelp.data list")
    rows: list[dict[str, Any]] = []
    for item in data:
        if not isinstance(item, Mapping):
            raise ValueError("sse delist rows must be objects")
        code = _dc_row_text(item, "COMPANY_CODE", "company_code")
        delist_date = _normalize_delist_date(
            _dc_row_field(item, "DELIST_DATE", "delist_date")
        )
        if not code or delist_date is None:
            raise ValueError("sse delist row missing code/DELIST_DATE")
        rows.append(
            {
                "code": code,
                "name": _dc_row_text(item, "COMPANY_ABBR", "company_abbr", limit=20),
                "market": "sh",
                "list_date": _normalize_delist_date(
                    _dc_row_field(item, "LIST_DATE", "list_date")
                ),
                "delist_date": delist_date,
                "source": "sse_terminated_listings",
            }
        )
    return rows


def _szse_delist_rows(http_get) -> list[dict[str, Any]]:
    """Fetch the SZSE terminated-listing tab (bounded 20-row pages, throttled)."""
    rows: list[dict[str, Any]] = []
    for page_no in range(1, _DELIST_SZSE_MAX_PAGES + 1):
        if page_no > 1:
            time.sleep(_DELIST_SZSE_PAGE_GAP_S)
        response = http_get(
            "szse",
            _SZSE_DELIST_URL,
            params={
                "SHOWTYPE": "JSON",
                "CATALOGID": "1793_ssgs",
                "TABKEY": "tab2",
                "PAGENO": page_no,
                "random": "0.42",
            },
            headers={
                "User-Agent": "Mozilla/5.0",
                "Referer": "https://www.szse.cn/market/stock/suspend/index.html",
            },
            timeout=20,
        )
        raise_for_status = getattr(response, "raise_for_status", None)
        if callable(raise_for_status):
            raise_for_status()
        payload = _json.loads(str(response.text))
        if not isinstance(payload, list):
            raise ValueError("szse delist payload must be an array")
        tab = next(
            (item for item in payload if isinstance(item, Mapping) and item.get("metadata", {}).get("tabkey") == "tab2"),
            None,
        )
        if tab is None:
            raise ValueError("szse delist payload missing tab2")
        data = tab.get("data")
        if not isinstance(data, list):
            raise ValueError("szse delist tab2 data must be a list")
        for item in data:
            if not isinstance(item, Mapping):
                raise ValueError("szse delist rows must be objects")
            code = _dc_row_text(item, "zqdm")
            delist_date = _normalize_delist_date(_dc_row_field(item, "zzrq", "ztrq"))
            if not code or delist_date is None:
                raise ValueError("szse delist row missing zqdm/zzrq")
            rows.append(
                {
                    "code": code,
                    "name": _dc_row_text(item, "zqjc", limit=20),
                    "market": "sz",
                    "list_date": _normalize_delist_date(_dc_row_field(item, "ssrq")),
                    "delist_date": delist_date,
                    "source": "szse_terminated_listings",
                }
            )
        if len(data) < 20:
            break
    return rows


def _delist_market_for(code: str) -> str:
    if code.startswith("6"):
        return "sh"
    if code.startswith(("0", "3")):
        return "sz"
    return "bse"


def _delist_reference(http_get=None) -> dict[str, Any]:
    """Same-day cached merged delist reference; refetch only when absent.

    The delist list is slow-changing reference data (not quotes/flow/news),
    so a same-calendar-day disk cache follows the name-code-map precedent.
    Only complete two-market snapshots are cached; partial failures return
    explicit failure semantics and are never persisted.
    """
    observed_at = datetime.now(_MARKET_TZ).isoformat(timespec="seconds")
    cache_path = _delist_cache_path()
    try:
        with open(cache_path, encoding="utf-8") as fh:
            cached = _json.load(fh)
        if (
            isinstance(cached, dict)
            and cached.get("cache_date") == _today().isoformat()
            and isinstance(cached.get("rows"), list)
            and cached.get("rows")
        ):
            return {
                "rows": cached["rows"],
                "observed_at": cached.get("observed_at", observed_at),
                "cache_date": cached.get("cache_date"),
                "failed_sources": [],
            }
    except (OSError, ValueError):
        pass

    get = http_get or _source_http_get
    rows: list[dict[str, Any]] = []
    failed_sources: list[str] = []
    for source_name, fetcher in (
        ("sse", _sse_delist_rows),
        ("szse", _szse_delist_rows),
    ):
        try:
            rows.extend(fetcher(get))
        except (_requests.RequestException, TimeoutError, ConnectionError, OSError) as exc:
            failed_sources.append(source_name)
            logger.warning(
                "Delist reference fetch failed for %s: %s", source_name, type(exc).__name__
            )
        except Exception as exc:
            failed_sources.append(source_name)
            logger.warning(
                "Delist reference parse failed for %s: %s", source_name, type(exc).__name__
            )
    result = {
        "rows": rows,
        "observed_at": observed_at,
        "cache_date": _today().isoformat(),
        "failed_sources": failed_sources,
    }
    if not failed_sources and rows:
        try:
            payload = _json.dumps(
                {"cache_date": result["cache_date"], "observed_at": observed_at, "rows": rows},
                ensure_ascii=False,
            )
            with open(cache_path, "w", encoding="utf-8") as fh:
                fh.write(payload)
        except OSError:
            pass
    return result


def get_delisting_info(
    ticker: Annotated[str, "6-digit A-share code (e.g. 600519)"],
) -> str:
    """Return the stock's official delisting record, if any (退市名单).

    Sources are the exchange-official terminated-listing boards (SSE common
    query + SZSE terminated tab), merged with a same-day reference cache.
    "Not in the list" is a normal empty for the covered markets only: BSE
    delisting has no free official source here and is reported as uncovered,
    never as "not delisted".
    """
    try:
        code = _normalize_ticker(ticker)
    except (TypeError, ValueError) as exc:
        return _dc_result("invalid_input", _DELIST_LABEL, reason=type(exc).__name__)

    market = _delist_market_for(code)
    observed_at = datetime.now(_MARKET_TZ).isoformat(timespec="seconds")
    if market == "bse":
        return _dc_result(
            "normal_empty",
            _DELIST_LABEL,
            source="SSE/SZSE exchange official terminated listings",
            observed_at=observed_at,
            as_of_date=_today().isoformat(),
            searched_market=market,
            coverage_note="北交所退市名单无沪深交易所官方零鉴权来源，本工具未覆盖；未覆盖不是未退市。",
            delisted=None,
            record=None,
        )

    reference = _delist_reference()
    rows = reference["rows"]
    failed = reference["failed_sources"]
    market_by_source = {"sse": "sh", "szse": "sz"}
    failed_market = {
        market_by_source[name] for name in failed if name in market_by_source
    }
    if market in failed_market:
        return _dc_result(
            "failed_network",
            _DELIST_LABEL,
            reason="reference_source_unavailable",
            failed_sources=failed,
        )

    matched = next((row for row in rows if row.get("code") == code), None)
    payload = {
        "source": "SSE/SZSE exchange official terminated listings",
        "observed_at": reference["observed_at"],
        "as_of_date": _today().isoformat(),
        "reference_date": reference["cache_date"],
        "searched_market": market,
        "reference_rows": len(rows),
        "cross_market_source_failed": bool(failed),
        "delisted": matched is not None,
        "record": matched,
    }
    if matched is None:
        payload["coverage_note"] = "在覆盖市场内未命中退市名单；名单为交易所官方已终止上市板，不含在市股票。"
        return _dc_result("normal_empty", _DELIST_LABEL, **payload)
    return _dc_result("success", _DELIST_LABEL, **payload)


# ---- 12. get_hot_stocks ----

_THS_REASON_DETAIL_URL = (
    "http://zx.10jqka.com.cn/event/harden/stockreason/id/{record_id}"
)
_THS_REASON_DETAIL_ENTITIES = (
    ("&lt;spanclass=&quot;hl&quot;&gt;", ""),
    ("&lt;/span&gt;", ""),
    ("&amp;quot;", '"'),
)


def _fetch_hot_stock_reason_detail(record_id: str) -> str:
    """Fetch the THS per-stock limit-up reason detail page.

    Returns the cleaned deep-reason text, or "" when the page is unreachable
    or its payload shape changed. The detail body is THS AI-generated
    attribution content; callers must keep the source label attached.
    """
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "Chrome/117.0.0.0 Safari/537.36"
            )
        }
        r = _source_http_get(
            "ths",
            _THS_REASON_DETAIL_URL.format(record_id=record_id),
            headers=headers,
            timeout=10,
        )
        if hasattr(r, "raise_for_status"):
            r.raise_for_status()
        match = _re.search(r"var data = '(.*?)';", r.text)
        if not match:
            return ""
        cleaned = match.group(1)
        for entity, replacement in _THS_REASON_DETAIL_ENTITIES:
            cleaned = cleaned.replace(entity, replacement)
        return cleaned.strip()
    except Exception:
        return ""


def _render_hot_stock_reason_detail(row: dict) -> str:
    """Render the reason-detail section for one matched hot-stock row."""
    code = str(row.get("code", "")).strip()
    name = str(row.get("name", "")).strip()
    record_id = str(row.get("id", "")).strip()
    lines = [
        "",
        f"## Limit-up Reason Detail ({code} {name})",
        "# Source: 同花顺涨停详因（AI 归因摘要，非公司公告；引用以上市公司公告为准）",
    ]
    if not record_id.isdigit():
        lines.append("Detail record unavailable (missing record id).")
        return "\n".join(lines)
    detail = _fetch_hot_stock_reason_detail(record_id)
    if not detail:
        lines.append("Detail content unavailable (fetch or parse failed).")
        return "\n".join(lines)
    lines.append(detail)
    return "\n".join(lines)


def get_hot_stocks(
    curr_date: Annotated[str, "Date YYYY-MM-DD, empty string for today"] = "",
    ticker: Annotated[
        str,
        "Optional 6-digit A-share code; when given and on that day's list, "
        "expands the curated limit-up reason detail for this stock",
    ] = "",
) -> str:
    """Get strong stocks with topic attribution from 同花顺 editorial team.

    Returns stocks that hit limit-up with reason tags explaining WHY they
    surged (e.g. '算力租赁+AI政务'). When ``ticker`` is supplied and the
    stock is on that day's list, appends the per-stock deep reason detail
    from the THS second-level page (AI-generated attribution summary, not
    company filings).
    """
    if not curr_date or curr_date.strip() == "":
        curr_date = datetime.now().strftime("%Y-%m-%d")

    code_match = _re.search(r"\d{6}", str(ticker or ""))
    detail_code = code_match.group(0) if code_match else ""

    try:
        url = (
            f"http://zx.10jqka.com.cn/event/api/getharden/"
            f"date/{curr_date}/orderby/date/orderway/desc/charset/GBK/"
        )
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "Chrome/117.0.0.0 Safari/537.36"
            )
        }
        r = _source_http_get("ths", url, headers=headers, timeout=10)
        if hasattr(r, "raise_for_status"):
            r.raise_for_status()
        data = r.json()

        if data.get("errocode", 0) != 0:
            return f"同花顺 API error: {data.get('errormsg', 'unknown')}"

        rows = data.get("data") or []
        if not rows:
            return (
                f"No hot stocks data for {curr_date} "
                f"(may be non-trading day or data not yet available)"
            )

        lines = [
            f"# Hot Stocks with Topic Attribution ({curr_date})",
            f"# Source: 同花顺 editorial (human-curated reason tags)",
            f"# Total: {len(rows)} stocks",
            "",
        ]

        from collections import Counter

        all_tags: list[str] = []

        for row in rows:
            code = row.get("code", "")
            name = row.get("name", "")
            reason = row.get("reason", "")
            zhangfu = row.get("zhangfu", "")
            huanshou = row.get("huanshou", "")
            chengjiaoe = row.get("chengjiaoe", "")
            dde = row.get("ddejingliang", "")

            # Intraday payloads omit the quote fields entirely; render the
            # metrics segment only from values actually present.
            metrics = []
            if str(zhangfu).strip():
                metrics.append(f"+{zhangfu}%")
            if str(huanshou).strip():
                metrics.append(f"换手{huanshou}%")
            if str(chengjiaoe).strip():
                metrics.append(f"成交额{chengjiaoe}")
            if str(dde).strip():
                metrics.append(f"大单净量{dde}")
            metrics_text = f" {' '.join(metrics)} |" if metrics else ""
            lines.append(f"{code} {name}:{metrics_text} {reason}")

            if reason:
                tags = [t.strip() for t in str(reason).split("+") if t.strip()]
                all_tags.extend(tags)

        if all_tags:
            cnt = Counter(all_tags)
            lines.append(f"\n## Theme Frequency (top 15)")
            for tag, n in cnt.most_common(15):
                lines.append(f"  {tag}: {n} stocks")

        if detail_code:
            try:
                matched_row = next(
                    (
                        row
                        for row in rows
                        if str(row.get("code", "")).strip() == detail_code
                    ),
                    None,
                )
                if matched_row is None:
                    lines.append(
                        f"\n## Limit-up Reason Detail ({detail_code})\n"
                        f"Not on the {curr_date} hot-stock list; no reason detail record."
                    )
                else:
                    lines.append(_render_hot_stock_reason_detail(matched_row))
            except Exception:
                lines.append(
                    "\n## Limit-up Reason Detail\n"
                    "Detail expansion failed unexpectedly."
                )

        return "\n".join(lines)

    except Exception as e:
        return f"Error fetching hot stocks for {curr_date}: {str(e)}"


# ---- 12. get_stock_monitor ----


_STOCK_MONITOR_URL = (
    "https://mobappconfig.securities.eastmoney.com/emcfg/stock_monitor.json"
)
_STOCK_MONITOR_MARKETS = {"1": "SH", "0": "SZ", "B": "BJ"}
_STOCK_MONITOR_REFERER = "https://vipmoney.eastmoney.com/"


def _normalize_stock_monitor_date(value: object, *, field_name: str) -> str:
    text = str(value or "").strip()
    if len(text) == 8 and text.isdigit():
        text = f"{text[:4]}-{text[4:6]}-{text[6:]}"
    else:
        text = text[:10].replace("/", "-")
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a valid date") from exc


def _normalize_stock_monitor_code(value: object, *, field_name: str) -> str:
    code = str(value or "").strip().upper()
    for prefix in ("SH", "SZ", "BJ"):
        if code.startswith(prefix):
            code = code[len(prefix):]
            break
    if not _re.fullmatch(r"\d{6}", code):
        raise ValueError(f"{field_name} must be a 6-digit A-share code")
    return code


def _parse_stock_monitor_rows(payload: object) -> list[dict[str, str]]:
    if not isinstance(payload, list):
        raise ValueError("stock monitor payload must be a list")

    rows: list[dict[str, str]] = []
    required = (
        "STKCODE",
        "STKNAME",
        "MARKET",
        "VALIDATESTARTDATE",
        "VALIDATEENDDATE",
    )
    for index, item in enumerate(payload):
        if not isinstance(item, Mapping):
            raise ValueError(f"stock monitor row {index} must be an object")
        missing = [key for key in required if not str(item.get(key) or "").strip()]
        if missing:
            raise ValueError(
                f"stock monitor row {index} missing {', '.join(missing)}"
            )
        code = _normalize_stock_monitor_code(
            item.get("STKCODE"), field_name=f"row {index} STKCODE"
        )
        start = _normalize_stock_monitor_date(
            item.get("VALIDATESTARTDATE"),
            field_name=f"row {index} VALIDATESTARTDATE",
        )
        end = _normalize_stock_monitor_date(
            item.get("VALIDATEENDDATE"),
            field_name=f"row {index} VALIDATEENDDATE",
        )
        if start > end:
            raise ValueError(f"stock monitor row {index} has an inverted date window")
        raw_market = str(item.get("MARKET") or "").strip().upper()
        rows.append(
            {
                "code": code,
                "name": str(item.get("STKNAME") or "").strip(),
                "market": _STOCK_MONITOR_MARKETS.get(raw_market, f"?{raw_market}"),
                "start": start,
                "end": end,
                "link": str(item.get("LINK_URL") or "").strip(),
            }
        )
    return rows


def get_stock_monitor(
    ticker: Annotated[str, "6-digit A-share code (e.g. 600519)"],
    curr_date: Annotated[str, "Observation date in YYYY-MM-DD format"],
) -> str:
    """Read the Eastmoney stock-monitor pool for one target and one date.

    The upstream feed is a current, non-paginated snapshot.  This adapter
    keeps only rows whose code matches ``ticker`` and whose inclusive validity
    window contains ``curr_date``.  An absent matching row is a normal empty
    result, not evidence that the stock has no risk.
    """
    try:
        code = safe_ticker_component(ticker)
        if not _re.fullmatch(r"\d{6}", code):
            return "Invalid ticker: stock monitor requires a 6-digit A-share code"
        observation_date = _normalize_stock_monitor_date(
            curr_date or _today().isoformat(), field_name="curr_date"
        )
        response = _em_get(
            _STOCK_MONITOR_URL,
            headers={
                "User-Agent": _UA,
                "Referer": _STOCK_MONITOR_REFERER,
            },
            timeout=10,
        )
        raise_for_status = getattr(response, "raise_for_status", None)
        if callable(raise_for_status):
            raise_for_status()
        rows = _parse_stock_monitor_rows(response.json())
        active = [
            row
            for row in rows
            if row["code"] == code
            and row["start"] <= observation_date <= row["end"]
        ]
        header = [
            "# Eastmoney Stock Monitor (重点监控池)",
            "# Data source: Eastmoney stock_monitor.json",
            f"# Observation date: {observation_date}",
        ]
        if not active:
            return "\n".join(
                [
                    *header,
                    "status: normal_empty",
                    "[正常空] No active Eastmoney stock-monitor record "
                    f"for {code} on {observation_date}.",
                ]
            )

        lines = [
            *header,
            "status: success",
            f"# Active records: {len(active)}",
            "",
            "code | name | market | start | end | link",
        ]
        lines.extend(
            " | ".join(
                [
                    row["code"],
                    row["name"],
                    row["market"],
                    row["start"],
                    row["end"],
                    row["link"] or "-",
                ]
            )
            for row in active
        )
        return "\n".join(lines)
    except Exception as exc:
        return f"Error fetching stock monitor for {ticker}: {exc}"


# ---- 13. get_northbound_flow ----


def _northbound_cache_path() -> str:
    """Path to local CSV cache for northbound daily close snapshots."""
    from .config import get_config

    config = get_config()
    cache_dir = config.get(
        "data_cache_dir", os.path.expanduser("~/.chstockdata/cache")
    )
    os.makedirs(cache_dir, exist_ok=True)
    return os.path.join(cache_dir, "northbound_daily.csv")


def _save_northbound_snapshot(date_str: str, hgt: float, sgt: float) -> None:
    """Append today's northbound close to local CSV cache (dedup by date)."""
    import csv

    path = _northbound_cache_path()
    existing: dict[str, tuple[str, str]] = {}
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            next(reader, None)
            for row in reader:
                if len(row) >= 3:
                    existing[row[0]] = (row[1], row[2])
    existing[date_str] = (f"{hgt:.2f}", f"{sgt:.2f}")
    sorted_dates = sorted(existing.keys())
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["date", "hgt", "sgt"])
        for d in sorted_dates:
            writer.writerow([d, existing[d][0], existing[d][1]])


def _load_northbound_history(n: int = 20) -> list[tuple[str, float, float]]:
    """Load last N days of northbound close data from local cache."""
    import csv

    path = _northbound_cache_path()
    if not os.path.exists(path):
        return []
    rows: list[tuple[str, float, float]] = []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader, None)
        for row in reader:
            if len(row) >= 3:
                try:
                    rows.append((row[0], float(row[1]), float(row[2])))
                except ValueError:
                    continue
    return rows[-n:]


def _legacy_get_northbound_flow(
    curr_date: Annotated[str, "Date YYYY-MM-DD"],
    include_history: Annotated[
        bool, "Include historical daily data (last 20 trading days)"
    ] = False,
) -> str:
    """Get northbound capital flow (沪深股通) from 同花顺 hsgtApi.

    Realtime: minute-level cumulative net buying for HGT(沪股通) + SGT(深股通).
    History: self-cached daily close snapshots (upstream APIs stopped updating
    northbound history since 2024-08).
    """
    hsgt_headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "Chrome/117.0.0.0 Safari/537.36"
        ),
        "Host": "data.hexin.cn",
        "Referer": "https://data.hexin.cn/",
    }

    lines = [
        f"# Northbound Capital Flow ({curr_date})",
        "# Source: 同花顺 hsgtApi (沪深股通) + local cache",
        "",
    ]

    hgt_close = 0.0
    sgt_close = 0.0
    got_realtime = False

    try:
        url_rt = "https://data.hexin.cn/market/hsgtApi/method/dayChart/"
        r = _source_http_get(
            "ths", url_rt, headers=hsgt_headers, timeout=10
        )
        if hasattr(r, "raise_for_status"):
            r.raise_for_status()
        d = r.json()

        times = d.get("time", [])
        hgt = d.get("hgt", [])
        sgt = d.get("sgt", [])

        if times:
            lines.append("## Realtime (cumulative net buying, 亿元)")
            n = len(times)
            start_idx = max(0, n - 10)
            for i in range(start_idx, n):
                t = times[i]
                h = hgt[i] if i < len(hgt) else "N/A"
                s = sgt[i] if i < len(sgt) else "N/A"
                lines.append(f"  {t}: HGT={h} SGT={s}")

            hgt_close = float(hgt[-1]) if hgt else 0
            sgt_close = float(sgt[-1]) if sgt else 0
            total = hgt_close + sgt_close
            lines.append(
                f"\nClose: HGT(沪股通)={hgt_close:.2f}亿 "
                f"SGT(深股通)={sgt_close:.2f}亿 "
                f"Total={total:.2f}亿"
            )
            if total > 0:
                lines.append("Signal: Net northbound INFLOW (bullish)")
            elif total < 0:
                lines.append("Signal: Net northbound OUTFLOW (bearish)")
            got_realtime = True
        else:
            lines.append("No realtime data (non-trading hours or holiday)")

        if got_realtime:
            today_str = datetime.now().strftime("%Y-%m-%d")
            _save_northbound_snapshot(today_str, hgt_close, sgt_close)

        if include_history:
            history = _load_northbound_history(20)
            if history:
                lines.append("\n## Historical Daily Close (local cache, 亿元)")
                lines.append("Date       | HGT(沪股通) | SGT(深股通) | Total")
                for date, h, s in history:
                    lines.append(f"  {date}: HGT={h:.2f} SGT={s:.2f} Total={h + s:.2f}")
                avg_total = sum(h + s for _, h, s in history) / len(history)
                lines.append(
                    f"\n{len(history)}-day avg net flow: {avg_total:.2f}亿"
                )
                if got_realtime:
                    today_total = hgt_close + sgt_close
                    diff = today_total - avg_total
                    lines.append(
                        f"Today vs avg: {'+' if diff >= 0 else ''}{diff:.2f}亿 "
                        f"({'above' if diff >= 0 else 'below'} average)"
                    )
            else:
                lines.append(
                    "\n## Historical Daily: No cached data yet. "
                    "History accumulates automatically with each call."
                )

        return "\n".join(lines)

    except Exception as e:
        return f"Error fetching northbound flow: {str(e)}"


def _public_adapter_payload(
    payload: Mapping[str, Any],
    *,
    label: str,
    envelope: Mapping[str, Any] | None = None,
) -> str:
    """Render adapter results without losing their source/date/coverage fields.

    The public tools remain text-returning for LangChain compatibility, while
    the JSON body is retained verbatim in ResultStore/Evidence.  Prefixes are
    the existing ledger's terminal-status markers, not a parallel state model.
    ``envelope`` appends the system-generated structured-evidence block that
    ExecutionLedger captures; it never enters the JSON body.
    """

    status = str(payload.get("status", "failed"))
    body = _json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    if envelope is not None:
        encoded = _json.dumps(envelope, ensure_ascii=False, sort_keys=True, default=str)
        body = f"{body}\n<!-- EVIDENCE: {encoded} -->"
    if status == "normal_empty":
        return f"[正常空] {label}\n{body}"
    if status in {"failed", "unavailable"}:
        return f"[数据缺失] {label}\n{body}"
    return f"# {label}\n{body}"


def get_market_breadth(curr_date: Annotated[str, "Date YYYY-MM-DD"] = "") -> str:
    """Return one governed, market-wide breadth snapshot for the requested date."""

    from .market_breadth import (
        build_market_breadth_evidence,
        get_market_breadth as _get_market_breadth,
    )

    result = _get_market_breadth(curr_date)
    return _public_adapter_payload(
        result,
        label="Market breadth",
        envelope=build_market_breadth_evidence(result),
    )


def get_corporate_actions(
    ticker: Annotated[str, "6-digit A-share ticker"],
    announcement_start: Annotated[str, "Announcement window start YYYY-MM-DD"],
    announcement_end: Annotated[str, "Announcement window end YYYY-MM-DD"],
    as_of_date: Annotated[str, "Known-information cutoff YYYY-MM-DD"] = "",
    page: Annotated[int, "Bounded page number"] = 1,
    page_size: Annotated[int, "Page size, at most 100"] = 50,
) -> str:
    """Return one bounded page of dividend/distribution action records."""

    from .corporate_actions import get_corporate_actions as _get_actions

    code = safe_ticker_component(str(ticker).strip())
    result = _get_actions(
        code,
        announcement_start=announcement_start or None,
        announcement_end=announcement_end or None,
        as_of_date=as_of_date or None,
        page=page,
        page_size=page_size,
    )
    return _public_adapter_payload(result, label="Corporate actions")


def get_announcement_index(
    ticker: Annotated[str, "6-digit A-share ticker"],
    start_date: Annotated[str, "Announcement window start YYYY-MM-DD"],
    end_date: Annotated[str, "Announcement window end YYYY-MM-DD"],
    as_of_date: Annotated[str, "Known-information cutoff YYYY-MM-DD"] = "",
    page: Annotated[int, "Bounded page number"] = 1,
    page_size: Annotated[int, "Page size, at most 100"] = 50,
) -> str:
    """Return a bounded title/link index; announcement files are never fetched."""

    from .corporate_actions import get_announcement_index as _get_index

    code = safe_ticker_component(str(ticker).strip())
    result = _get_index(
        code,
        start_date=start_date or None,
        end_date=end_date or None,
        as_of_date=as_of_date or None,
        page=page,
        page_size=page_size,
    )
    return _public_adapter_payload(result, label="Announcement index")


def get_block_trades(
    ticker: Annotated[str, "6-digit A-share ticker"],
    start_date: Annotated[str, "Inclusive start date YYYY-MM-DD"],
    end_date: Annotated[str, "Inclusive end date YYYY-MM-DD"],
    max_pages: Annotated[int, "Bounded maximum pages"] = 10,
) -> str:
    """Return normalized block trades without inferring beneficiary or intent."""

    from .block_trades import fetch_free_block_trades

    code = safe_ticker_component(str(ticker).strip())

    def same_day_unadjusted_reference(symbol: str, trade_date: str):
        # get_stock_data defaults to raw bars.  Do not substitute a realtime or
        # adjusted value when the historical close is absent.
        close = _get_close_on_date(symbol, trade_date)
        return (close, trade_date) if close is not None else None

    result = fetch_free_block_trades(
        code,
        start_date,
        end_date,
        max_pages=max_pages,
        reference_price_lookup=same_day_unadjusted_reference,
    )
    payload = {
        "status": result.evidence.final_status,
        "coverage": result.evidence.completeness,
        "records": list(result.records),
        "evidence": result.evidence.to_dict(),
    }
    return _public_adapter_payload(
        payload, label="Block trades", envelope=result.evidence.to_dict()
    )


def _northbound_store_path():
    """Return F5's separately configurable, durable trusted-record store path."""

    from pathlib import Path
    from .config import get_config

    config = get_config()
    configured = config.get("northbound_store_path")
    if configured:
        return Path(str(configured))
    return Path(str(config.get("data_cache_dir"))) / "northbound" / "northbound.sqlite3"


_NORTHBOUND_TURNOVER_STALE_DAYS = 5


def _northbound_unavailable_payload(
    cutoff: str,
    *,
    reason_code: str,
    limitation: str,
) -> dict[str, object]:
    """Build a fail-closed offline-read result with explicit coverage state."""

    return {
        "status": "failed",
        "reason_code": reason_code,
        "coverage_status": "unknown",
        "source_query_status": "not_run",
        "records": [],
        "as_of_date": cutoff,
        "requested_as_of_date": cutoff,
        "scope": "northbound_sh/northbound_sz day-end turnover plus disclosed holdings",
        "coverage": {
            "northbound_sh": "沪股通日终成交总额/成交笔数/ETF成交额；可含季度持股快照",
            "northbound_sz": "深股通日终成交总额/成交笔数/ETF成交额（以可信库实际采集为准）；可含季度持股快照",
        },
        "limitations": [
            limitation,
            "离线读取不会联网、补采或把旧 CSV 自动升级为可信 SQLite 记录。",
            "成交总额/持股快照不等于净买入、净流入或实时持仓。",
        ],
    }


def get_northbound_flow(
    curr_date: Annotated[str, "As-of date YYYY-MM-DD"],
    include_history: Annotated[bool, "Include bounded trusted historical records"] = True,
    ticker: Annotated[str, "Optional current-report 6-digit ticker"] = "",
) -> str:
    """Read F5's trusted local store only; this tool never initiates a fetch."""

    from .northbound_store import NorthboundStore

    try:
        cutoff = date.fromisoformat(str(curr_date)[:10]).isoformat()
        code = safe_ticker_component(ticker) if ticker else None
        store_path = _northbound_store_path()
        if not store_path.exists():
            return _public_adapter_payload(
                _northbound_unavailable_payload(
                    cutoff,
                    reason_code="trusted_store_not_initialized",
                    limitation="可信北向 SQLite 尚未初始化；没有完成来源查询，不能解释为正常空或零持仓。",
                ),
                label="Northbound trusted history (not net inflow)",
            )
        store = NorthboundStore(store_path)
        all_records = store.query()
        if not all_records:
            return _public_adapter_payload(
                _northbound_unavailable_payload(
                    cutoff,
                    reason_code="trusted_store_empty",
                    limitation="可信北向 SQLite 已存在但没有任何有效记录；来源覆盖未知，不能解释为正常空或零持仓。",
                ),
                label="Northbound trusted history (not net inflow)",
            )
        turnover: list[dict[str, object]] = []
        for metric in (
            "turnover_total",
            "turnover_trade_count",
            "turnover_etf",
        ):
            for market_scope in ("northbound_sh", "northbound_sz"):
                metric_records = store.query(
                    metric=metric,
                    market_scope=market_scope,
                    as_of_before=cutoff,
                )
                turnover.extend(
                    metric_records[-4:] if include_history else metric_records[-1:]
                )
        holdings: list[dict[str, object]] = []
        if code:
            for market_scope in ("northbound_sh", "northbound_sz"):
                scope_records = store.query(
                    market_scope=market_scope, security_id=code, as_of_before=cutoff
                )
                # Slice per market, as the turnover loop above does: slicing the
                # concatenation of two scopes would let a longer scope push the
                # other scope's newest records out of the window entirely.
                holdings.extend(
                    scope_records[-12:] if include_history else scope_records[-1:]
                )
        records = turnover + holdings
        if not records:
            return _public_adapter_payload(
                _northbound_unavailable_payload(
                    cutoff,
                    reason_code="trusted_store_no_matching_record",
                    limitation="可信库存在记录，但当前日期/证券/范围没有匹配项；不能证明来源窗口完整，不能解释为正常空。",
                ),
                label="Northbound trusted history (not net inflow)",
            )

        record_dates = sorted({str(record.get("as_of_date")) for record in records if record.get("as_of_date")})
        observed_dates = sorted({str(record.get("observed_at")) for record in records if record.get("observed_at")})
        turnover_dates = sorted({
            str(record.get("as_of_date"))
            for record in records
            if str(record.get("metric", "")).startswith("turnover_") and record.get("as_of_date")
        })
        freshness_status = "snapshot_only"
        reason_code = "trusted_store_ready"
        freshness_age_days: int | None = None
        freshness_limitations: list[str] = []
        if turnover_dates:
            latest_turnover = max(date.fromisoformat(value) for value in turnover_dates)
            freshness_age_days = max(0, (date.fromisoformat(cutoff) - latest_turnover).days)
            if freshness_age_days > _NORTHBOUND_TURNOVER_STALE_DAYS:
                freshness_status = "stale"
                reason_code = "trusted_store_stale"
                freshness_limitations.append(
                    f"沪深股通成交记录最新基准日 {latest_turnover.isoformat()}，距请求日 {cutoff} 已 {freshness_age_days} 个日历日，数据陈旧且不是当日实时流量。"
                )
            else:
                freshness_status = "within_daily_window"
        payload = {
            "status": "success" if records else "normal_empty",
            "reason_code": reason_code,
            "coverage_status": "known",
            "source_query_status": "not_run",
            "records": records,
            "as_of_date": cutoff,
            "requested_as_of_date": cutoff,
            "record_as_of_dates": record_dates,
            "latest_record_as_of_date": (max(record_dates) if record_dates else None),
            "latest_observed_at": (max(observed_dates) if observed_dates else None),
            "freshness_status": freshness_status,
            "freshness_age_days": freshness_age_days,
            "scope": "northbound_sh/northbound_sz day-end turnover plus disclosed holdings",
            "coverage": {
                "northbound_sh": "沪股通日终成交总额/成交笔数/ETF成交额；可含季度持股快照",
                "northbound_sz": "深股通日终成交总额/成交笔数/ETF成交额（以可信库实际采集为准）；可含季度持股快照",
            },
            "limitations": [
                "Records are disclosed turnover or quarterly holdings, not net inflow.",
                "The read path is offline and does not refresh or infer missing data.",
            ] + freshness_limitations,
        }
        return _public_adapter_payload(
            payload, label="Northbound trusted history (not net inflow)"
        )
    except (TypeError, ValueError) as exc:
        # A malformed stored record raises ValueError from NorthboundStore;
        # keep that distinct from caller input validation.
        if "store_path" in locals() and store_path.exists():
            return _public_adapter_payload(
                _northbound_unavailable_payload(
                    str(curr_date)[:10],
                    reason_code="trusted_store_corrupt",
                    limitation=f"可信北向 SQLite 中的记录无法解析（{type(exc).__name__}），未使用其中内容，来源覆盖未知。",
                ),
                label="Northbound trusted history (not net inflow)",
            )
        return f"[数据缺失] Northbound trusted history invalid input: {type(exc).__name__}"
    except PermissionError:
        return _public_adapter_payload(
            _northbound_unavailable_payload(
                str(curr_date)[:10],
                reason_code="trusted_store_permission_denied",
                limitation="可信北向 SQLite 或其目录无运行用户读取权限，来源覆盖未知。",
            ),
            label="Northbound trusted history (not net inflow)",
        )
    except _sqlite3.DatabaseError:
        return _public_adapter_payload(
            _northbound_unavailable_payload(
                str(curr_date)[:10],
                reason_code="trusted_store_corrupt",
                limitation="可信北向 SQLite 无法通过数据库完整性读取，未使用其中内容，来源覆盖未知。",
            ),
            label="Northbound trusted history (not net inflow)",
        )
    except OSError:
        return _public_adapter_payload(
            _northbound_unavailable_payload(
                str(curr_date)[:10],
                reason_code="trusted_store_io_error",
                limitation="可信北向 SQLite 发生文件读取错误，来源覆盖未知。",
            ),
            label="Northbound trusted history (not net inflow)",
        )
    except Exception as exc:
        return _public_adapter_payload(
            _northbound_unavailable_payload(
                str(curr_date)[:10],
                reason_code="trusted_store_unavailable",
                limitation=f"可信北向 SQLite 读取失败（{type(exc).__name__}），来源覆盖未知。",
            ),
            label="Northbound trusted history (not net inflow)",
        )


# ---------------------------------------------------------------------------
# Concept block helpers (东财 F10 CoreConception；v0.2.20 自百度 PAE 迁移)
# ---------------------------------------------------------------------------

# ---- 13. get_concept_blocks ----


def _fetch_core_conception(code: str) -> dict[str, tuple[dict[str, Any], ...]]:
    """Fetch the structured EastMoney F10 concept payload once.

    Both the user-facing concept renderer and policy routing consume this
    structured response.  Keeping the validation here makes endpoint shape
    drift visible to the policy route instead of turning it into a guessed
    empty context.
    """

    prefix = _get_prefix(code).upper()
    url = (
        "https://emweb.securities.eastmoney.com/PC_HSF10/"
        f"CoreConception/PageAjax?code={prefix}{code}"
    )
    response = _em_get(
        url,
        headers={"Referer": "https://emweb.eastmoney.com/"},
        timeout=10,
    )
    payload = response.json()
    if not isinstance(payload, Mapping):
        raise ValueError("CoreConception payload is not an object")

    normalized: dict[str, tuple[dict[str, Any], ...]] = {}
    for key in ("ssbk", "hxtc"):
        records = payload.get(key, ()) or ()
        if not isinstance(records, (list, tuple)):
            raise ValueError(f"CoreConception {key} is not a record list")
        if any(not isinstance(record, Mapping) for record in records):
            raise ValueError(f"CoreConception {key} contains malformed records")
        normalized[key] = tuple(dict(record) for record in records)
    return normalized


def _build_policy_target_context(ticker: str) -> PolicyTargetContext:
    """Build deterministic policy routing context from CoreConception fields."""

    code = _normalize_ticker(ticker)
    exchange = exchange_for_ticker(code)
    try:
        payload = _fetch_core_conception(code)
    except Exception as exc:
        logger.warning("政策路由上下文获取失败（%s）", type(exc).__name__)
        return PolicyTargetContext(
            ticker=code,
            exchange=exchange,
            province=None,
            industry=None,
            concepts=(),
            selected_industry_authorities=(),
            routing_source="eastmoney_core_conception",
            limitations=(
                "routing_context_unavailable",
                "province_context_unavailable",
                "industry_context_unavailable",
            ),
        )

    records = sorted(
        payload["ssbk"],
        key=lambda record: (
            int(record.get("BOARD_RANK") or 10**9)
            if str(record.get("BOARD_RANK") or "").isdigit()
            else 10**9
        ),
    )
    board_names = tuple(
        str(record.get("BOARD_NAME", "")).strip()
        for record in records
        if str(record.get("BOARD_NAME", "")).strip()
    )
    province = normalize_province(board_names)
    province_names = {
        board_name
        for board_name in board_names
        if normalize_province((board_name,)) is not None
    }
    concepts = tuple(
        board_name
        for board_name in board_names
        if ("概念" in board_name or "题材" in board_name)
        and board_name not in province_names
    )
    company_attributes = tuple(
        board_name
        for board_name in board_names
        if any(marker in board_name for marker in ("国企", "央企", "民营"))
    )
    industry = next(
        (
            board_name
            for board_name in board_names
            if board_name not in province_names
            and board_name not in concepts
            and board_name not in company_attributes
        ),
        None,
    )
    selected, omitted = route_industry_authorities(
        industry=industry,
        company_attributes=company_attributes,
        concepts=concepts,
    )
    limitations: list[str] = []
    if province is None:
        limitations.append("province_context_unavailable")
    if industry is None and not selected:
        limitations.append("industry_context_unavailable")
    if omitted:
        limitations.append(
            "industry_authorities_truncated:" + ",".join(omitted)
        )
    return PolicyTargetContext(
        ticker=code,
        exchange=exchange,
        province=province,
        industry=industry,
        concepts=concepts,
        selected_industry_authorities=selected,
        routing_source="eastmoney_core_conception",
        limitations=tuple(limitations),
    )


def get_policy_news(
    ticker: str,
    start_date: str,
    end_date: str,
) -> str:
    """Return policy evidence from routed official authorities for one A-share."""

    code = _normalize_ticker(ticker)
    context = _build_policy_target_context(code)
    from .policy_news import get_policy_news_for_context

    return get_policy_news_for_context(context, start_date, end_date)


def get_concept_blocks(
    ticker: Annotated[str, "A-stock code (e.g. 688017)"],
) -> str:
    """Get concept/sector/region blocks that a stock belongs to (东财 F10).

    百度 PAE getrelatedblock 接口已下线（返回 403），v0.2.20 迁移至东财 F10
    CoreConception/PageAjax。返回所属板块（行业/地域/风格/概念）+ 核心题材要点。
    注：东财 ssbk 本身不含板块当日涨幅（百度 PAE 原有）；板块涨跌幅由 DEC-P1-19
    的 TDX 个股所属板块行情段另行提供（通达信分类，与东财 BK 不逐项等价）。
    """
    code = _normalize_ticker(ticker)

    try:
        d = _fetch_core_conception(code)
        ssbk = d["ssbk"]
        hxtc = d["hxtc"]

        if not ssbk and not hxtc:
            return f"No concept/block data for {code}"

        lines = [
            f"# Concept & Sector Blocks for {code} (A-stock)",
            f"# Source: 东财 F10 CoreConception",
            f"# Retrieved: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
        ]

        # 所属板块（行业/地域/风格/概念，按 BOARD_RANK 排序）
        if ssbk:
            lines.append("## 所属板块 (行业/地域/风格/概念)")
            for item in ssbk:
                name = item.get("BOARD_NAME", "")
                if name:
                    lines.append(f"  {name}")
            concept_names = [
                str(item.get("BOARD_NAME", ""))
                for item in ssbk
                if "概念" in str(item.get("BOARD_NAME", ""))
            ]
            if concept_names:
                lines.append(f"\nConcept tags: {' / '.join(concept_names)}")

        # 核心题材要点
        if hxtc:
            points = [x for x in hxtc if str(x.get("IS_POINT")) == "1"]
            if points:
                lines.append("\n## 核心题材")
                for item in points:
                    klass = item.get("KEY_CLASSIF", "")
                    content = str(item.get("MAINPOINT_CONTENT", "")).strip()
                    if content:
                        lines.append(f"  [{klass}] {content[:200]}")

        # 板块维度增强（DEC-P1-19）：TDX 个股所属板块当日涨跌幅。百度 PAE 下线后
        # F10 ssbk 仅归属无涨幅；TDX 不可用时按非 [数据缺失] 措辞降级披露，避免
        # classify_tool_result 把 F10 已成功的结果整体判 failed。
        try:
            tdx_payload = _get_tdx_belong_board(code)
            tdx_boards = tdx_payload.get("boards") or []
        except Exception as exc:
            logger.warning("TDX 板块行情未获取（%s）", type(exc).__name__)
            tdx_boards = []
        if tdx_boards:
            ordered = sorted(
                tdx_boards,
                key=lambda item: (
                    item.get("change_pct") is None,
                    -(float(item.get("change_pct") or 0.0)),
                ),
            )
            lines.extend(
                [
                    "",
                    "## TDX 板块行情（通达信分类，最新交易日快照）",
                    "# Source: TDX（通达信板块分类与东财不逐项等价）",
                ]
            )
            for item in ordered:
                board_name = str(item.get("board_name") or "").strip()
                if not board_name:
                    continue
                change = item.get("change_pct")
                change_text = f"{float(change):+.2f}%" if change is not None else "—"
                lines.append(f"  {board_name} | {change_text}")
        else:
            lines.extend(
                ["", "（TDX 板块当日行情暂不可用，以上板块归属不含涨跌幅）"]
            )

        return "\n".join(lines)

    except Exception as e:
        return _eastmoney_data_missing("所属概念板块数据", e)


# ---- 14. get_fund_flow ----


def _sina_daily_fund_flow(
    code: str, history_count: int, cutoff_date: str | None = None
) -> list[dict]:
    """Fetch Sina's daily flow series as the non-push2 fallback.

    Sina exposes total net flow and ``r0`` net flow; it does not provide an
    Eastmoney-compatible four-order-size series, so callers must preserve the
    source label and daily-only semantics.

    ``cutoff_date`` (YYYY-MM-DD) drops rows dated **after** the analysis date so
    a historical review cannot leak "today" data into the series.  Rows are
    returned newest-first; when the cutoff is in the past and sina's newest
    window contains no row on/before it, a ValueError is raised so the caller
    keeps data-missing semantics instead of presenting future data.
    """
    response = _source_http_get(
        "sina",
        "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/"
        "MoneyFlow.ssl_qsfx_zjlrqs",
        params={
            "page": 1,
            "num": min(max(history_count, 1), 20),
            "sort": "opendate",
            "asc": 0,
            "daima": _sina_stock_code(code),
        },
        headers={"User-Agent": _UA, "Referer": "https://vip.stock.finance.sina.com.cn/moneyflow/"},
        timeout=10,
    )
    response.raise_for_status()
    payload = _json.loads(response.text)
    if not isinstance(payload, list) or not payload:
        raise ValueError("Sina daily fund flow is unavailable")

    def number(value):
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return None
        return parsed if math.isfinite(parsed) else None

    records = []
    for row in payload:
        if not isinstance(row, dict) or not row.get("opendate"):
            continue
        records.append(
            {
                "date": str(row["opendate"]),
                "net_amount": number(row.get("netamount")),
                "main_net": number(row.get("r0_net")),
                "close": number(row.get("trade")),
                "change_pct": number(row.get("changeratio")),
            }
        )
    if cutoff_date:
        records = [r for r in records if str(r["date"])[:10] <= cutoff_date]
    if not records:
        raise ValueError("Sina daily fund flow is malformed")
    return records


def _sina_industry_ranking() -> list[dict]:
    """Parse Sina's public industry aggregate snapshot and sort locally."""
    response = _source_http_get(
        "sina",
        "https://vip.stock.finance.sina.com.cn/q/view/newFLJK.php",
        params={"param": "industry"},
        headers={"User-Agent": _UA, "Referer": "https://vip.stock.finance.sina.com.cn/mkt/"},
        timeout=10,
    )
    response.raise_for_status()
    match = _re.search(r"=\s*(\{.*\})\s*;?\s*$", response.text, _re.S)
    if match is None:
        raise ValueError("Sina industry payload is malformed")
    payload = _json.loads(match.group(1))
    if not isinstance(payload, dict):
        raise ValueError("Sina industry payload is malformed")

    def number(value):
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return None
        return parsed if math.isfinite(parsed) else None

    records = []
    for raw in payload.values():
        fields = str(raw).split(",")
        if len(fields) < 13:
            continue
        change_pct = number(fields[5])
        if change_pct is None:
            continue
        records.append(
            {
                "name": fields[1],
                "member_count": number(fields[2]),
                "change_pct": change_pct,
                "amount": number(fields[7]),
                "leader": fields[12],
            }
        )
    if not records:
        raise ValueError("Sina industry payload is empty")
    return sorted(records, key=lambda item: item["change_pct"], reverse=True)


def _tdx_history_main_net(row) -> float | None:
    """TDX 历史资金流行的主力净额：优先现成键，否则按四档 in/out 合成。

    easy-tdx 历史行（Category 22 / 逐笔回退）只有 super/large/medium/small
    四档 in/out；库模型的 ``main_net_inflow`` 是 @property，不进桥载荷。
    主力口径与库一致：超大 + 大。任一所需键缺失时返回 None（调用方按 0 展示）。
    """
    flow = row.get("main_net")
    if flow is None:
        flow = row.get("main_net_inflow")
    if flow is not None:
        return float(flow)
    try:
        return float(
            (row["super_in"] + row["large_in"])
            - (row["super_out"] + row["large_out"])
        )
    except (KeyError, TypeError, ValueError):
        return None


def get_fund_flow(
    ticker: Annotated[str, "A-stock code"],
    curr_date: Annotated[str, "Date YYYY-MM-DD"],
    include_history: Annotated[
        bool, "Include historical daily fund flow (last 20 days)"
    ] = True,
) -> str:
    """Get source-labelled current/daily A-share fund flow without push2."""
    code = _normalize_ticker(ticker)
    try:
        tdx = _get_tdx_fund_flow(code, include_history)
        current = tdx.get("current", [])
        if not isinstance(current, list) or not current:
            raise TdxBridgeUnavailable("TDX current fund flow is unavailable")
        lines = [
            f"# Fund Flow for {code} (A-stock)",
            "# Source: TDX",
            f"# Methodology: {tdx.get('methodology', 'tdx_l1_reconstructed')}",
            "# 注意：按通达信 L1 订单金额分层重算，非东财口径；不提供分钟级结论。",
            f"# Retrieved: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
        ]
        latest = current[0]
        main_net = float(latest.get("main_net") or latest.get("main_net_inflow") or 0)
        small_net = float(latest.get("small_net") or 0)
        lines.extend(
            [
                "## 当前交易日 L1 重算资金流",
                "# 该值对应该工具抓取时点（见上方 Retrieved），不是可回溯的历史日期值。",
                f"主力净流入={main_net / 1e4:.0f}万 | 小单净流入={small_net / 1e4:.0f}万",
            ]
        )
        # 近5日档位净额透传：legacy 的 large_net/mid_net 列实为 5 日聚合值
        # （easy_tdx SymbolCapitalFlowCmd 从 5 日行映射），super_net_5d/
        # small_net_5d 为 fork 补充映射。均为 5 日口径，绝不能标为当日数据。
        five_day_parts = []
        for label, keys in (
            ("超大单5日净额", ("super_net_5d",)),
            ("大单5日净额", ("large_net", "large_net_5d")),
            ("中单5日净额", ("mid_net", "mid_net_5d")),
            ("小单5日净额", ("small_net_5d",)),
        ):
            for key in keys:
                value = latest.get(key)
                if value is not None:
                    five_day_parts.append(f"{label}={float(value) / 1e4:.0f}万")
                    break
        if five_day_parts:
            lines.extend(
                [
                    "",
                    "## 近5日档位净额（TDX 口径 5 日聚合，非东财四档口径，非当日数据）",
                    " | ".join(five_day_parts),
                ]
            )
        history = tdx.get("history", []) if include_history else []
        # 历史复盘时剔除分析日之后的记录（未来函数防护）：TDX 返回的是"最近 N 天"，
        # 不带任何日期过滤。
        if history and curr_date:
            history = [
                r for r in history
                if str(r.get("date") or "")[:10] <= curr_date
            ]
        if include_history and not history:
            try:
                history = _sina_daily_fund_flow(code, 20, cutoff_date=curr_date)
            except Exception:
                history = []  # 新浪历史窗口没有分析日及之前的数据：保留 TDX 当日结果
            if history:
                lines.extend(["", "## 日频资金流降级（新浪财经）"])
        elif history:
            lines.extend(["", "## 历史日频资金流（TDX）"])
        for row in history:
            date_value = row.get("date") or "-".join(
                str(row.get(part, "")) for part in ("year", "month", "day")
            )
            flow = _tdx_history_main_net(row) or 0
            line = f"  {date_value} | 主力净额={float(flow) / 1e4:.0f}万"
            # 四档 in/out 全 present 时透传档位净额（TDX 口径，非东财四档）。
            tier_nets = []
            for label, in_key, out_key in (
                ("超大", "super_in", "super_out"),
                ("大", "large_in", "large_out"),
                ("中", "medium_in", "medium_out"),
                ("小", "small_in", "small_out"),
            ):
                in_value, out_value = row.get(in_key), row.get(out_key)
                if in_value is None or out_value is None:
                    tier_nets = []
                    break
                tier_nets.append((label, float(in_value) - float(out_value)))
            if tier_nets:
                line += " | " + " ".join(
                    f"{label}={net / 1e4:.0f}万" for label, net in tier_nets
                )
            lines.append(line)
        return "\n".join(lines)
    except Exception as tdx_exc:
        try:
            records = _sina_daily_fund_flow(
                code, 20 if include_history else 1, cutoff_date=curr_date
            )
            if not records:
                raise ValueError("Sina daily fund flow payload is empty")
            lines = [
                f"# Fund Flow for {code} (A-stock)",
                "# Source: 新浪财经",
                "# 日频资金流降级：仅含总净流与新浪 r0 主力口径，不提供分钟或四档订单流。",
                "",
            ]
            for row in records:
                lines.append(
                    f"  {row['date']} | 总净额={float(row.get('net_amount') or 0) / 1e4:.0f}万 "
                    f"| 主力净额={float(row.get('main_net') or 0) / 1e4:.0f}万"
                )
            return "\n".join(lines)
        except Exception:
            logger.warning("TDX/Sina fund flow unavailable for %s: %s", code, type(tdx_exc).__name__)
            return "\n".join([
                f"# 个股资金流 | {code}",
                "[数据缺失: 个股日频资金数据暂不可用]",
            ])


# ---------------------------------------------------------------------------
# 15. Dragon Tiger Board (龙虎榜)
# ---------------------------------------------------------------------------

_LHB_SEAT_PERIODS = (
    (30, "01"),
    (90, "02"),
    (180, "03"),
    (365, "04"),
)


def _lhb_seat_period(look_back_days: int) -> tuple[int, str]:
    """Map an arbitrary look-back window to Eastmoney's seat-cycle codes."""
    requested_days = max(1, int(look_back_days))
    for period_days, cycle_code in _LHB_SEAT_PERIODS:
        if requested_days <= period_days:
            return period_days, cycle_code
    return _LHB_SEAT_PERIODS[-1]


def _lhb_seat_codes(rows: list[dict]) -> list[str]:
    """Return safe, de-duplicated seat codes in their first-seen order."""
    codes: list[str] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        code = str(row.get("OPERATEDEPT_CODE") or "").strip()
        if not code or not _re.fullmatch(r"[A-Za-z0-9_-]+", code) or code in seen:
            continue
        seen.add(code)
        codes.append(code)
    return codes


def _lhb_seat_code_filter(codes: list[str]) -> str:
    """Build the Eastmoney ``in`` filter from provider-returned identifiers."""
    return f"(OPERATEDEPT_CODE in ({','.join(_json.dumps(code) for code in codes)}))"


def _lhb_number(value: Any) -> float:
    return _quote_number(value) or 0.0


def _lhb_format_count(value: Any) -> str:
    number = _quote_number(value)
    return "-" if number is None else str(int(number))


def _lhb_format_wan(value: Any) -> str:
    number = _quote_number(value)
    return "-" if number is None else f"{number / 10000:.0f}"


def _lhb_format_pct(value: Any) -> str:
    number = _quote_number(value)
    return "-" if number is None else f"{number:.2f}%"


def _lhb_activity_by_code(rows: list[dict]) -> dict[str, dict[str, Any]]:
    """Aggregate active-seat rows by seat code and unique listing date."""
    if not isinstance(rows, list):
        raise ValueError("active seat payload must be a list")

    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("active seat row must be an object")
        code = str(row.get("OPERATEDEPT_CODE") or "").strip()
        if not code:
            continue
        item = result.setdefault(
            code,
            {
                "name": str(row.get("OPERATEDEPT_NAME") or "").strip(),
                "dates": set(),
                "buyer_num": 0.0,
                "seller_num": 0.0,
                "net_amt": 0.0,
            },
        )
        onlist_date = str(row.get("ONLIST_DATE") or "").strip()[:10]
        if onlist_date:
            item["dates"].add(onlist_date)
        # Eastmoney's current payload uses *_APPEAR_NUM.  Keep the older
        # aliases as a compatibility fallback for historical snapshots.
        item["buyer_num"] += _lhb_number(
            _quote_row_value(row, "BUYER_APPEAR_NUM", "BUYER_NUM")
        )
        item["seller_num"] += _lhb_number(
            _quote_row_value(row, "SELLER_APPEAR_NUM", "SELLER_NUM")
        )
        item["net_amt"] += _lhb_number(row.get("TOTAL_NETAMT"))
    return result


def _lhb_return_by_code(rows: list[dict]) -> dict[str, dict[str, Any]]:
    """Index seat return-ranking rows by the stable provider seat code."""
    if not isinstance(rows, list):
        raise ValueError("seat return-ranking payload must be a list")

    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("seat return-ranking row must be an object")
        code = str(row.get("OPERATEDEPT_CODE") or "").strip()
        if code and code not in result:
            result[code] = dict(row)
    return result


def _append_lhb_seat_dimension(
    lines: list[str],
    *,
    buy_data: list[dict],
    sell_data: list[dict],
    start_date: str,
    trade_date: str,
    look_back_days: int,
) -> None:
    """Append current-seat activity and return context to a board report."""
    seat_rows: list[tuple[str, str, str]] = []
    seen_seats: set[tuple[str, str]] = set()
    for direction, rows in (("买", buy_data), ("卖", sell_data)):
        for row in rows:
            if not isinstance(row, Mapping):
                continue
            code = str(row.get("OPERATEDEPT_CODE") or "").strip()
            name = str(row.get("OPERATEDEPT_NAME") or "").strip()
            if not code or not name:
                continue
            key = (direction, code)
            if key not in seen_seats:
                seen_seats.add(key)
                seat_rows.append((code, name, direction))

    if not seat_rows:
        return

    codes = _lhb_seat_codes(
        [
            {"OPERATEDEPT_CODE": code}
            for code, _name, _direction in seat_rows
        ]
    )
    if not codes:
        lines.append(_eastmoney_data_missing("龙虎榜营业部代码", ValueError("invalid seat code")))
        return

    period_days, cycle_code = _lhb_seat_period(look_back_days)
    code_filter = _lhb_seat_code_filter(codes)
    active_rows: list[dict] = []
    ranking_rows: list[dict] = []
    active_error: Exception | None = None
    ranking_error: Exception | None = None

    try:
        active_rows = _eastmoney_datacenter(
            "RPT_OPERATEDEPT_ACTIVE",
            filter_str=(
                f"(ONLIST_DATE>='{start_date}')"
                f"(ONLIST_DATE<='{trade_date}')"
                f"{code_filter}"
            ),
            page_size=5000,
            sort_columns="TOTAL_NETAMT,ONLIST_DATE,OPERATEDEPT_CODE",
            sort_types="-1,-1,1",
            strict=True,
        )
    except Exception as exc:
        active_error = exc

    try:
        ranking_rows = _eastmoney_datacenter(
            "RPT_RATEDEPT_RETURNT_RANKING",
            filter_str=f'(STATISTICSCYCLE="{cycle_code}"){code_filter}',
            page_size=5000,
            sort_columns="TOTAL_BUYER_SALESTIMES_1DAY,OPERATEDEPT_CODE",
            sort_types="-1,1",
            strict=True,
        )
    except Exception as exc:
        ranking_error = exc

    activity_by_code: dict[str, dict[str, Any]] = {}
    ranking_by_code: dict[str, dict[str, Any]] = {}
    if active_error is None:
        try:
            activity_by_code = _lhb_activity_by_code(active_rows)
        except Exception as exc:
            active_error = exc
    if ranking_error is None:
        try:
            ranking_by_code = _lhb_return_by_code(ranking_rows)
        except Exception as exc:
            ranking_error = exc

    lines.append(
        f"\n## 当前龙虎榜营业部画像（活跃统计近{look_back_days}日；收益统计近{period_days}日）"
    )
    if active_error is not None:
        lines.append(_eastmoney_data_missing("龙虎榜营业部活跃画像", active_error))
    if ranking_error is not None:
        lines.append(_eastmoney_data_missing("龙虎榜营业部收益统计", ranking_error))
    lines.append(
        "营业部 | 本次方向 | 活跃交易日 | 买入个股数 | 卖出个股数 | "
        "净买入(万) | 1日平均涨幅 | 1日上涨概率 | 3日平均涨幅 | 3日上涨概率"
    )

    for code, name, direction in seat_rows:
        activity = activity_by_code.get(code)
        ranking = ranking_by_code.get(code)
        if activity is None and active_error is None:
            active_text = "活跃画像=无匹配记录"
        elif activity is None:
            active_text = "活跃画像=-"
        else:
            active_text = (
                f"活跃交易日={len(activity['dates'])}"
                f" | 买入个股数={_lhb_format_count(activity['buyer_num'])}"
                f" | 卖出个股数={_lhb_format_count(activity['seller_num'])}"
                f" | 净买入(万)={_lhb_format_wan(activity['net_amt'])}"
            )
        if ranking is None and ranking_error is None:
            return_text = "收益统计=无匹配记录"
        elif ranking is None:
            return_text = "收益统计=-"
        else:
            return_text = (
                f"1日平均涨幅={_lhb_format_pct(ranking.get('AVERAGE_INCREASE_1DAY'))}"
                f" | 1日上涨概率={_lhb_format_pct(ranking.get('RISE_PROBABILITY_1DAY'))}"
                f" | 3日平均涨幅={_lhb_format_pct(ranking.get('AVERAGE_INCREASE_3DAY'))}"
                f" | 3日上涨概率={_lhb_format_pct(ranking.get('RISE_PROBABILITY_3DAY'))}"
            )
        lines.append(f"  {name} | {direction} | {active_text} | {return_text}")


def get_dragon_tiger_board(
    ticker: str,
    trade_date: str,
    look_back_days: int = 30,
) -> str:
    """Get dragon-tiger board (龙虎榜) appearances and seat details.

    Args:
        ticker: 6-digit A-share code, e.g. '000858'
        trade_date: YYYY-MM-DD
        look_back_days: how many days back to search (default 30)

    Returns:
        Formatted text with LHB appearances, top buyer/seller seats,
        and institutional activity.
    """
    code = safe_ticker_component(ticker)
    end_dt = datetime.strptime(trade_date, "%Y-%m-%d")
    start_dt = end_dt - pd.Timedelta(days=look_back_days)
    start_date_str = start_dt.strftime("%Y-%m-%d")
    lines = [f"# 龙虎榜数据 | {code} | {trade_date} (近{look_back_days}日)"]
    data: list[dict] = []
    buy_data: list[dict] = []
    sell_data: list[dict] = []

    # 1. 上榜记录 — eastmoney datacenter direct HTTP
    try:
        data = _eastmoney_datacenter(
            "RPT_DAILYBILLBOARD_DETAILSNEW",
            filter_str=(
                f"(TRADE_DATE>='{start_date_str}')"
                f"(TRADE_DATE<='{trade_date}')"
                f"(SECURITY_CODE=\"{code}\")"
            ),
            page_size=50,
            sort_columns="TRADE_DATE",
            sort_types="-1",
        )
        if not data:
            lines.append(f"\n近{look_back_days}日未上龙虎榜。")
        else:
            lines.append(f"\n## 上榜记录 ({len(data)} 次)")
            lines.append("日期 | 原因 | 净买入(万) | 换手率")
            for row in data:
                net_buy = round((row.get("BILLBOARD_NET_AMT") or 0) / 10000, 1)
                turnover = round(float(row.get("TURNOVERRATE") or 0), 2)
                lines.append(
                    f"  {str(row.get('TRADE_DATE', ''))[:10]} "
                    f"| {row.get('EXPLANATION', '')} "
                    f"| {net_buy:.0f} "
                    f"| {turnover:.2f}%"
                )
    except Exception as e:
        lines.append(_eastmoney_data_missing("龙虎榜数据", e))

    # 2. 最近上榜的买卖席位 — eastmoney datacenter direct HTTP
    try:
        if data:
            latest_date = str(data[0].get("TRADE_DATE", ""))[:10]
            lines.append(f"\n## 最近上榜席位明细 ({latest_date})")

            # 买入席位
            buy_data = _eastmoney_datacenter(
                "RPT_BILLBOARD_DAILYDETAILSBUY",
                filter_str=f"(TRADE_DATE='{latest_date}')(SECURITY_CODE=\"{code}\")",
                page_size=10,
                sort_columns="BUY",
                sort_types="-1",
            )
            if buy_data:
                lines.append("\n### 买入席位 TOP5")
                lines.append("营业部 | 买入(万) | 卖出(万) | 净额(万)")
                for row in buy_data[:5]:
                    buy_amt = round((row.get("BUY") or 0) / 10000, 1)
                    sell_amt = round((row.get("SELL") or 0) / 10000, 1)
                    net = round((row.get("NET") or 0) / 10000, 1)
                    lines.append(
                        f"  {row.get('OPERATEDEPT_NAME', '')} "
                        f"| {buy_amt:.0f} | {sell_amt:.0f} | {net:.0f}"
                    )

            # 卖出席位
            sell_data = _eastmoney_datacenter(
                "RPT_BILLBOARD_DAILYDETAILSSELL",
                filter_str=f"(TRADE_DATE='{latest_date}')(SECURITY_CODE=\"{code}\")",
                page_size=10,
                sort_columns="SELL",
                sort_types="-1",
            )
            if sell_data:
                lines.append("\n### 卖出席位 TOP5")
                lines.append("营业部 | 买入(万) | 卖出(万) | 净额(万)")
                for row in sell_data[:5]:
                    buy_amt = round((row.get("BUY") or 0) / 10000, 1)
                    sell_amt = round((row.get("SELL") or 0) / 10000, 1)
                    net = round((row.get("NET") or 0) / 10000, 1)
                    lines.append(
                        f"  {row.get('OPERATEDEPT_NAME', '')} "
                        f"| {buy_amt:.0f} | {sell_amt:.0f} | {net:.0f}"
                    )
    except Exception as e:
        lines.append(_eastmoney_data_missing("龙虎榜买卖席位数据", e))

    # 3. 机构动向 — 从买卖席位明细筛选机构专用席位 (OPERATEDEPT_CODE="0")
    try:
        inst_buy = 0.0
        inst_sell = 0.0
        for detail, side in [(buy_data, "buy"), (sell_data, "sell")]:
            for row in (detail or []):
                if str(row.get("OPERATEDEPT_CODE", "")) == "0":
                    if side == "buy":
                        inst_buy += (row.get("BUY") or 0)
                    else:
                        inst_sell += (row.get("SELL") or 0)
        if inst_buy > 0 or inst_sell > 0:
            lines.append("\n## 机构动向")
            lines.append(
                f"  机构买入 {inst_buy/1e4:.0f} 万 "
                f"| 卖出 {inst_sell/1e4:.0f} 万 "
                f"| 净额 {(inst_buy - inst_sell)/1e4:.0f} 万"
            )
    except Exception as e:
        lines.append(_eastmoney_data_missing("龙虎榜机构动向数据", e))

    # 4. 当前买卖席位的跨日活跃度与历史收益统计
    _append_lhb_seat_dimension(
        lines,
        buy_data=buy_data,
        sell_data=sell_data,
        start_date=start_date_str,
        trade_date=trade_date,
        look_back_days=look_back_days,
    )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 16. Lockup Expiry Calendar (限售解禁日历)
# ---------------------------------------------------------------------------

def get_lockup_expiry(
    ticker: str,
    trade_date: str,
    forward_days: int = 90,
) -> str:
    """Get lockup expiry schedule for a stock.

    Args:
        ticker: 6-digit A-share code
        trade_date: YYYY-MM-DD
        forward_days: how many days forward to check (default 90)

    Returns:
        Formatted text with historical unlock records and upcoming
        expiry calendar with impact metrics.
    """
    code = safe_ticker_component(ticker)
    lines = [f"# 限售解禁日历 | {code} | {trade_date}"]

    # 1. 历史解禁记录 — eastmoney datacenter direct HTTP
    try:
        history_data = _eastmoney_datacenter(
            "RPT_LIFT_STAGE",
            filter_str=f"(SECURITY_CODE=\"{code}\")",
            page_size=15,
            sort_columns="FREE_DATE",
            sort_types="-1",
        )
        if history_data:
            lines.append(f"\n## 个股解禁记录 (共 {len(history_data)} 批)")
            lines.append("解禁时间 | 类型 | 解禁数量 | 实际可流通 | 占比")
            for row in history_data:
                # 东财 2026 改列名：LIMITED_STOCK_TYPE→FREE_SHARES_TYPE，
                # FREE_SHARES_NUM→FREE_SHARES（旧名已废，取不到值致字段恒空）。
                # ABLE_FREE_SHARES 是实际可流通股数（更贴近真实抛压）。
                lines.append(
                    f"  {str(row.get('FREE_DATE', ''))[:10]} "
                    f"| {row.get('FREE_SHARES_TYPE', '')} "
                    f"| {row.get('FREE_SHARES', '')} "
                    f"| {row.get('ABLE_FREE_SHARES', '')} "
                    f"| {row.get('FREE_RATIO', '')}"
                )
        else:
            lines.append("\n无历史解禁记录。")
    except Exception as e:
        lines.append(_eastmoney_data_missing("历史解禁数据", e))

    # 2. 未来待解禁 — eastmoney datacenter direct HTTP
    try:
        end_dt = datetime.strptime(trade_date, "%Y-%m-%d") + pd.Timedelta(
            days=forward_days
        )
        end_str = end_dt.strftime("%Y-%m-%d")
        upcoming_data = _eastmoney_datacenter(
            "RPT_LIFT_STAGE",
            filter_str=(
                f"(SECURITY_CODE=\"{code}\")"
                f"(FREE_DATE>='{trade_date}')"
                f"(FREE_DATE<='{end_str}')"
            ),
            page_size=20,
            sort_columns="FREE_DATE",
            sort_types="1",
        )
        if upcoming_data:
            lines.append(f"\n## 未来 {forward_days} 天待解禁")
            for row in upcoming_data:
                # 同上：FREE_SHARES_TYPE/FREE_SHARES 为东财现行列名，ABLE_FREE_SHARES 更贴近真实抛压
                lines.append(
                    f"  {str(row.get('FREE_DATE', ''))[:10]} "
                    f"| {row.get('FREE_SHARES_TYPE', '')} "
                    f"| 数量 {row.get('FREE_SHARES', '')} "
                    f"| 可流通 {row.get('ABLE_FREE_SHARES', '')} "
                    f"| 占比 {row.get('FREE_RATIO', '')}"
                )
        else:
            lines.append(f"\n未来 {forward_days} 天无待解禁。")
    except Exception as e:
        lines.append(_eastmoney_data_missing("未来解禁数据", e))

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 17. Industry Comparison (行业横向对比)
# ---------------------------------------------------------------------------

def get_industry_comparison(
    ticker: str,
    trade_date: str,
    top_n: int = 20,
) -> str:
    """Get industry sector performance comparison.

    Args:
        ticker: 6-digit A-share code (used to identify relevant sector)
        trade_date: YYYY-MM-DD
        top_n: number of top/bottom industries to show (default 20)

    Returns:
        Formatted text with sector performance ranking, highlighting
        the sector the target stock belongs to.
    """
    code = safe_ticker_component(ticker)
    lines = [
        f"# 行业横向对比 | {code} | 请求日 {trade_date}",
        "# 说明：行业排名与该股所属行业均为源端**最新交易日快照**，非请求日历史排名；"
        "请求日仅用于报告归档，不能据此断言该日行业强弱。",
    ]

    try:
        payload = _get_tdx_industry_ranking(top_n)
        top = payload.get("top", [])
        bottom = payload.get("bottom", [])
        if not isinstance(top, list) or not top:
            raise TdxBridgeUnavailable("TDX industry ranking is unavailable")
        lines.extend(
            [
                "# Source: TDX",
                "# 行业分类: 通达信（与东财行业分类不逐项等价）",
                "排名 | 行业 | 涨跌幅 | 上涨 | 下跌 | 主力净额(万)",
            ]
        )
        for index, item in enumerate(top, start=1):
            lines.append(
                f"  {index}. {item.get('name', '')} | {item.get('change_pct', 0)}% "
                f"| {item.get('up_count', '-')} | {item.get('down_count', '-')} "
                f"| {float(item.get('main_net_amount') or 0) / 1e4:.0f}"
            )
        if bottom:
            lines.append("\n## 跌幅靠前行业")
            for index, item in enumerate(bottom, start=1):
                lines.append(
                    f"  {index}. {item.get('name', '')} | {item.get('change_pct', 0)}% "
                    f"| {item.get('up_count', '-')} | {item.get('down_count', '-')} "
                    f"| {float(item.get('main_net_amount') or 0) / 1e4:.0f}"
                )
    except Exception as tdx_exc:
        try:
            items = _sina_industry_ranking()
            if not items:
                raise ValueError("Sina industry ranking payload is empty")
            lines.extend(
                [
                    "# Source: 新浪财经",
                    "# 行业分类: 新浪行业；仅提供板块涨跌幅、成交额和领涨股。",
                    "排名 | 行业 | 涨跌幅 | 成交额(万) | 领涨股",
                ]
            )
            for index, item in enumerate(items[:top_n], start=1):
                lines.append(
                    f"  {index}. {item['name']} | {item['change_pct']}% "
                    f"| {float(item.get('amount') or 0) / 1e4:.0f} | {item.get('leader', '')}"
                )
            lines.append("\n## 跌幅靠前行业")
            for index, item in enumerate(items[-top_n:][::-1], start=1):
                lines.append(
                    f"  {index}. {item['name']} | {item['change_pct']}% "
                    f"| {float(item.get('amount') or 0) / 1e4:.0f} | {item.get('leader', '')}"
                )
        except Exception:
            logger.warning("TDX/Sina industry ranking unavailable for %s: %s", code, type(tdx_exc).__name__)
            lines.append("[数据缺失: 行业横向对比数据暂不可用]")

    # 概念板块涨跌幅排行（DEC-P1-19 扩大项）：TDX 全量 board_list 本地计算；
    # 与行业段独立降级——不可用时按非 [数据缺失] 措辞披露，不改变行业段结论。
    try:
        concept = _get_tdx_concept_ranking(top_n)
        concept_top = concept.get("top") or []
        concept_bottom = concept.get("bottom") or []
    except Exception as exc:
        logger.warning("TDX 概念板块行情未获取（%s）", type(exc).__name__)
        concept_top, concept_bottom = [], []
    if concept_top:
        lines.extend(
            [
                "",
                "## 概念板块涨跌幅排行（通达信分类）",
                "# Source: TDX（通达信概念分类与东财概念板块不逐项等价）",
                f"涨幅前 {len(concept_top)}",
            ]
        )
        for index, item in enumerate(concept_top, start=1):
            lines.append(
                f"  {index}. {item.get('name', '')} | {item.get('change_pct', 0)}%"
            )
        if concept_bottom:
            lines.append("")
            lines.append("跌幅靠前概念")
            for index, item in enumerate(concept_bottom, start=1):
                lines.append(
                    f"  {index}. {item.get('name', '')} | {item.get('change_pct', 0)}%"
                )
    else:
        lines.extend(["", "（TDX 概念板块行情暂不可用）"])

    return "\n".join(lines)
