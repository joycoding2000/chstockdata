#!/usr/bin/env python3
"""A small JSON bridge for an isolated easy-tdx runtime.

The main application intentionally keeps pandas 3.x.  easy-tdx 1.20.6
declares pandas<3, so this program is executed by ``EASY_TDX_PYTHON`` from a
separate virtual environment rather than imported by the application process.
"""

from __future__ import annotations

import json
import math
import os
import sys
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any


# 全池选优（from_best_host 会并发 ping 全部 ~52 台候选）的限频窗口。issues/023
# 止血：此前每次桥调用都全池扫描（资金流一次最多 2 轮 ≈ 104 个并发 TCP 连接），
# 从机房风控视角等同端口扫描。缓存 best_host 连不上时才允许一次选优，且全机
# （所有桥子进程共享该 stamp 文件）每窗口最多一次。
_BEST_HOST_REFRESH_INTERVAL_S = float(
    os.environ.get("TDX_BEST_HOST_REFRESH_INTERVAL_S", str(6 * 3600))
)


def _refresh_stamp_path() -> Path:
    base = Path(os.environ.get("EASY_TDX_CONFIG_DIR", str(Path.home() / ".easy_tdx")))
    return base / "besthost-refresh.stamp"


def _best_host_refresh_allowed() -> bool:
    try:
        return time.time() - _refresh_stamp_path().stat().st_mtime >= (
            _BEST_HOST_REFRESH_INTERVAL_S
        )
    except OSError:
        return True


def _mark_best_host_refresh() -> None:
    try:
        stamp = _refresh_stamp_path()
        stamp.parent.mkdir(parents=True, exist_ok=True)
        stamp.touch()
    except OSError:
        pass


def _load_clients():
    """Return delayed easy-tdx client factories without importing at module load.

    Each factory accepts ``refresh=False``: 默认返回绑定 config.json 缓存
    best_host 的未连接 client；``refresh=True`` 才做全池选优（from_best_host）。
    """
    from easy_tdx import MacClient, Market, TdxClient

    def _factory(cls):
        def make(refresh: bool = False):
            return cls.from_best_host() if refresh else cls()

        return make

    return _factory(MacClient), _factory(TdxClient), Market


def _market(market_name: str, market_enum):
    name = market_name.upper()
    if name not in {"SH", "SZ", "BJ"}:
        raise ValueError(f"unsupported market: {market_name}")
    return getattr(market_enum, name)


def _records(frame) -> list[dict[str, Any]]:
    """Normalize a pandas DataFrame or record-like payload to JSON scalars."""
    if frame is None:
        return []
    to_dict = getattr(frame, "to_dict", None)
    raw = to_dict("records") if callable(to_dict) else list(frame)

    def clean(value: Any):
        if value is None or isinstance(value, (str, bool, int)):
            return value
        if isinstance(value, float):
            return value if math.isfinite(value) else None
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        item = getattr(value, "item", None)
        if callable(item):
            return clean(item())
        return str(value)

    return [{str(key): clean(value) for key, value in row.items()} for row in raw]


def _change_pct(close: Any, pre_close: Any) -> float | None:
    """板块涨跌幅 = (close - pre_close) / pre_close * 100；缺值/零基准返回 None。"""
    try:
        close_value = float(close)
        pre_close_value = float(pre_close)
    except (TypeError, ValueError):
        return None
    if (
        not math.isfinite(close_value)
        or not math.isfinite(pre_close_value)
        or pre_close_value == 0
    ):
        return None
    return round((close_value - pre_close_value) / pre_close_value * 100, 2)


def _board_type_enum():
    """延迟导入 BoardType：本模块只在隔离 easy-tdx 环境中执行。"""
    from easy_tdx import BoardType

    return BoardType


def _run_on(factory, operation, *, refresh: bool = False):
    client = factory(refresh=refresh)
    client.connect()
    try:
        return operation(client)
    finally:
        try:
            client.close()
        except Exception:
            pass


def _with_client(factory, operation):
    """Run ``operation`` on one connected client, cached best_host first.

    缓存 host 上连接或取数失败（含"TCP 通、协议拒"的 issues/023 形态）且选优
    窗口允许时，才做一次全池选优重试；窗口内失败直接上抛，由主进程熔断器接管。
    """
    try:
        return _run_on(factory, operation)
    except Exception:
        if not _best_host_refresh_allowed():
            raise
        _mark_best_host_refresh()
        return _run_on(factory, operation, refresh=True)


def execute(argv: list[str]) -> dict[str, Any]:
    """Run a bridge command and return the normalized audit payload."""
    if not argv:
        raise ValueError("missing command")
    command = argv[0]
    if command not in {"fund-flow", "industry-ranking", "belong-board", "concept-ranking"}:
        raise ValueError(f"unsupported command: {command}")
    mac_factory, standard_factory, market_enum = _load_clients()

    if command == "fund-flow":
        if len(argv) != 4:
            raise ValueError("fund-flow requires market, ticker, and history count")
        market_name, code, count_text = argv[1:]
        if not code.isdigit() or len(code) != 6:
            raise ValueError("ticker must be a 6-digit A-share code")
        try:
            history_count = min(max(int(count_text), 0), 20)
        except ValueError as exc:
            raise ValueError("history count must be an integer") from exc
        market = _market(market_name, market_enum)
        current = _with_client(
            mac_factory, lambda client: client.get_capital_flow(market, code)
        )
        history = []
        if history_count:
            history = _with_client(
                standard_factory,
                lambda client: client.get_history_fund_flow(
                    market, code, 0, history_count
                ),
            )
        return {
            "source": "tdx",
            "methodology": "tdx_l1_reconstructed",
            "current": _records(current),
            "history": _records(history),
        }

    if command == "industry-ranking":
        if len(argv) != 3:
            raise ValueError("industry-ranking requires top and bottom counts")
        try:
            top_n = min(max(int(argv[1]), 1), 50)
            bottom_n = min(max(int(argv[2]), 0), 50)
        except ValueError as exc:
            raise ValueError("ranking counts must be integers") from exc

        # issues/023 止血：top/bottom 共用同一个 mac 连接（原来各连一次）。
        def _both_rankings(client):
            top = client.get_board_ranking(top_n=top_n, ascending=False)
            bottom = (
                client.get_board_ranking(top_n=bottom_n, ascending=True)
                if bottom_n
                else []
            )
            return top, bottom

        top, bottom = _with_client(mac_factory, _both_rankings)
        return {
            "source": "tdx",
            "methodology": "tdx_board_aggregate",
            "taxonomy": "tdx_industry",
            "top": _records(top),
            "bottom": _records(bottom),
        }

    if command == "belong-board":
        if len(argv) != 3:
            raise ValueError("belong-board requires market and ticker")
        market_name, code = argv[1:]
        if not code.isdigit() or len(code) != 6:
            raise ValueError("ticker must be a 6-digit A-share code")
        market = _market(market_name, market_enum)
        frame = _with_client(
            mac_factory, lambda client: client.get_belong_board(market, code)
        )
        boards = _records(frame)
        for board in boards:
            board["change_pct"] = _change_pct(
                board.get("close"), board.get("pre_close")
            )
        return {
            "source": "tdx",
            "methodology": "tdx_board_snapshot",
            "taxonomy": "tdx_board",
            "boards": boards,
        }

    if command == "concept-ranking":
        if len(argv) != 3:
            raise ValueError("concept-ranking requires top and bottom counts")
        try:
            top_n = min(max(int(argv[1]), 1), 50)
            bottom_n = min(max(int(argv[2]), 0), 50)
        except ValueError as exc:
            raise ValueError("ranking counts must be integers") from exc

        board_type_enum = _board_type_enum()

        def _concept_changes(client):
            frame = client.get_board_list(board_type_enum.GN)
            rows: list[dict[str, Any]] = []
            for record in _records(frame):
                change = _change_pct(record.get("price"), record.get("pre_close"))
                name = str(record.get("name") or "").strip()
                if change is None or not name:
                    continue
                rows.append(
                    {
                        "code": record.get("code", ""),
                        "name": name,
                        "change_pct": change,
                    }
                )
            rows.sort(key=lambda item: item["change_pct"], reverse=True)
            return rows

        # 全市场概念板块一次 board_list 全量返回 price/pre_close，本地算涨跌幅；
        # 不做逐板块成分聚合（概念板块 500+，聚合开销远超行业排行）。
        rows = _with_client(mac_factory, _concept_changes)
        return {
            "source": "tdx",
            "methodology": "tdx_board_snapshot",
            "taxonomy": "tdx_concept",
            "top": rows[:top_n],
            "bottom": rows[-bottom_n:][::-1] if bottom_n else [],
        }

    raise AssertionError("validated command was not handled")


def main() -> int:
    try:
        print(json.dumps(execute(sys.argv[1:]), ensure_ascii=False, allow_nan=False))
        return 0
    except Exception as exc:  # noqa: BLE001 - bridge process boundary
        print(
            json.dumps({"error_type": type(exc).__name__}, ensure_ascii=False),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
