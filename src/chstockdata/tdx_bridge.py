"""Client for the isolated :mod:`easy_tdx` provider process.

``easy-tdx==1.20.6`` requires pandas<3 while the application runs pandas 3.
This module therefore owns the process boundary and exposes only normalized
JSON dictionaries to the A-share vendor.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from typing import Any

from .vendor_errors import VendorNetworkError


TDX_BRIDGE_TIMEOUT_SECONDS = 45
# Shipped inside the package so installed wheels resolve it (a repo-level
# scripts/ directory does not exist under site-packages).
_BRIDGE_SCRIPT = Path(__file__).with_name("_easy_tdx_bridge.py")

# 健康短路：TDX 已知不可用（如未配置 EASY_TDX_PYTHON、服务器屏蔽 TCP 7709）时，
# 每次调用仍要等满 45s 超时。连续失败达到阈值后进入冷却期，期间直接返回不可用
# （调用方走新浪降级），冷却期满放行一次真实探测，成功即恢复。
_FAILURE_THRESHOLD = 2
_COOLDOWN_SECONDS = 600.0
_health_lock = threading.Lock()
_consecutive_failures = 0
_cooldown_until = 0.0

# issues/023 止血：桥子进程调用串行化 + 最小间隔。七分析师并行分支可能同时发起
# 资金流与行业排名两个桥调用（= 两个子进程各自全池选优的扫描突发）；串行化后
# 排队执行，间隔补足把突发变成慢速请求。间隔每次调用时读 env，便于测试置 0。
_bridge_launch_lock = threading.Lock()
_last_bridge_launch = float("-inf")


def _bridge_min_interval() -> float:
    try:
        return float(os.environ.get("TDX_BRIDGE_MIN_INTERVAL", "1.0"))
    except ValueError:
        return 1.0


class TdxBridgeUnavailable(VendorNetworkError):
    """The optional isolated TDX provider cannot produce a valid payload.

    ``category`` keeps the underlying failure class name (e.g. ``TimeoutExpired``,
    ``ValueError``) so callers can report sanitized error granularity without
    holding the original exception.
    """

    category: str = "TdxBridgeUnavailable"


def _health_allows_attempt() -> bool:
    with _health_lock:
        return time.monotonic() >= _cooldown_until


def _record_health_failure() -> None:
    global _consecutive_failures, _cooldown_until
    with _health_lock:
        _consecutive_failures += 1
        if _consecutive_failures >= _FAILURE_THRESHOLD:
            _cooldown_until = time.monotonic() + _COOLDOWN_SECONDS
            _consecutive_failures = 0


def _record_health_success() -> None:
    global _consecutive_failures, _cooldown_until
    with _health_lock:
        _consecutive_failures = 0
        _cooldown_until = 0.0


def _reset_health() -> None:
    """Test hook: clear the in-process circuit state."""
    global _consecutive_failures, _cooldown_until
    with _health_lock:
        _consecutive_failures = 0
        _cooldown_until = 0.0


def _source_call(
    operation: str,
    function,
    *,
    attempt_no: int = 1,
):
    """Use the optional Prefetch source context without importing providers."""

    try:
        from .source_context import call_source
    except ImportError:  # pragma: no cover - compatibility with partial installs
        return function()
    return call_source("tdx", operation, function, attempt_no=attempt_no)


def run_tdx_bridge(command: str, *args: str) -> dict[str, Any]:
    """Execute a fixed bridge command without a shell and validate its JSON."""
    if not _health_allows_attempt():
        error = TdxBridgeUnavailable("TDX provider circuit open")
        error.category = "CircuitOpen"
        raise error
    python = os.environ.get("EASY_TDX_PYTHON", "").strip() or sys.executable

    def _run_once() -> dict[str, Any]:
        global _last_bridge_launch
        wait = _bridge_min_interval() - (time.monotonic() - _last_bridge_launch)
        if wait > 0:
            time.sleep(wait)
        _last_bridge_launch = time.monotonic()
        completed = subprocess.run(
            [python, str(_BRIDGE_SCRIPT), command, *args],
            capture_output=True,
            check=False,
            shell=False,
            text=True,
            timeout=TDX_BRIDGE_TIMEOUT_SECONDS,
        )
        if completed.returncode != 0:
            raise RuntimeError("TDX helper returned a non-zero exit status")
        try:
            payload = json.loads(completed.stdout)
        except (TypeError, json.JSONDecodeError) as exc:
            raise ValueError("TDX helper returned invalid JSON") from exc
        if not isinstance(payload, dict) or payload.get("source") != "tdx":
            raise ValueError("TDX helper returned an invalid payload")
        return payload

    # 串行化整个"最多两次有界重试"的逻辑调用：并发分支排队而非各自起子进程。
    with _bridge_launch_lock:
        for attempt in range(1, 3):
            try:
                payload = _source_call("bridge", _run_once, attempt_no=attempt)
            except Exception as exc:
                if exc.__class__.__name__ == "SourceContextDeadlineExceeded":
                    raise
                error = TdxBridgeUnavailable("TDX provider unavailable")
                if isinstance(exc, (ValueError, json.JSONDecodeError)):
                    error = TdxBridgeUnavailable("TDX provider returned invalid data")
                    error.category = "ValueError"
                elif isinstance(exc, subprocess.TimeoutExpired):
                    error.category = "TimeoutExpired"
                elif isinstance(exc, OSError):
                    error.category = type(exc).__name__
                else:
                    error.category = "RuntimeError"
                if attempt < 2:
                    continue
                # One logical bridge call owns both bounded attempts.  Count one
                # health failure only after the retry is exhausted; otherwise a
                # single transient outage would trip the legacy circuit threshold.
                _record_health_failure()
                raise error from exc
            else:
                _record_health_success()
                return payload
    raise TdxBridgeUnavailable("TDX provider unavailable")  # pragma: no cover


def market_for_code(code: str) -> str:
    """6-digit A-stock/ETF code -> TDX market tag ("SH" / "SZ" / "BJ").

    北交所 920xxx 号段须先于 9 判断；4x/8x 为北交所老号段。
    5x 为沪市 ETF/LOF（510050/510300/588000/510500 等），必须归沪市，
    否则实时行情会拼出 sz510050 静默取不到数。
    """
    if code.startswith("92"):
        return "BJ"
    if code.startswith(("5", "6", "9")):
        return "SH"
    if code.startswith(("4", "8")):
        return "BJ"
    return "SZ"


def get_tdx_fund_flow(code: str, include_history: bool) -> dict[str, Any]:
    return run_tdx_bridge(
        "fund-flow", market_for_code(code), code, "20" if include_history else "0"
    )


def get_tdx_industry_ranking(top_n: int) -> dict[str, Any]:
    return run_tdx_bridge("industry-ranking", str(top_n), str(top_n))


def get_tdx_belong_board(code: str) -> dict[str, Any]:
    """个股所属板块 + 当日涨跌幅（TDX 板块快照，单次调用）。"""
    return run_tdx_bridge("belong-board", market_for_code(code), code)


def get_tdx_concept_ranking(top_n: int) -> dict[str, Any]:
    """概念板块涨跌幅 top/bottom（TDX 全量 board_list 本地计算，无成分聚合）。"""
    return run_tdx_bridge("concept-ranking", str(top_n), str(top_n))
