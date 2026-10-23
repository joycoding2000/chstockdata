"""板块资金流（东财 bkzj 非 push2 端点）— 行业/概念/地域 × 今日/5日/10日。

口径与限制（2026-09-14 活体探测钉死）：

- 端点 ``data.eastmoney.com/dataapi/bkzj/getbkzj``（本仓概念示例已在用的
  非 push2 域名）支持 ``key=f62``（今日主力净额）/``f164``（5日）/``f174``
  （10日）× ``code=m:90+t:2``（行业）/``t:3``（概念）/``t:1``（地域）。
- **只有主力净额单值**：载荷仅含 ``f12/f13/f14`` + 所查 key；上游 push2 版的
  四档（超大/大/中/小单）、主力净占比、领涨股字段在本端点不存在。
  本模块绝不回退 push2/push2his（解耦铁律），缺失字段在 ``limitations``
  中如实披露，不伪造、不置零。
- 所有请求走 ``a_stock._em_get`` 串行限流。
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any

from . import a_stock
from .vendor_errors import (
    DeadlineExceeded,
    VendorError,
    VendorNetworkError,
    VendorNoDataError,
)

_CST = timezone(timedelta(hours=8))

_BKZJ_URL = "https://data.eastmoney.com/dataapi/bkzj/getbkzj"
_BOARD_SCOPES: dict[str, dict[str, str]] = {
    "industry": {"code": "m:90+t:2", "referer": "https://data.eastmoney.com/bkzj/hy.html"},
    "concept": {"code": "m:90+t:3", "referer": "https://data.eastmoney.com/bkzj/gn.html"},
    "region": {"code": "m:90+t:1", "referer": "https://data.eastmoney.com/bkzj/dy.html"},
}
_BOARD_PERIODS: dict[str, dict[str, str]] = {
    "today": {"key": "f62", "label": "今日"},
    "5d": {"key": "f164", "label": "5日"},
    "10d": {"key": "f174", "label": "10日"},
}

_LIMITATIONS = [
    "本端点仅提供主力净额（超大单+大单合计），无四档明细/主力净占比/领涨股",
    "主力净额单位为元；板块分类与命名以源端为准",
]


def _num(value: Any) -> float | None:
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(result):
        return None
    return result


def get_board_fund_flow(
    board_type: str = "industry", period: str = "today", top_n: int = 20
) -> dict[str, Any]:
    """板块资金流向排名（按主力净额降序）。

    Args:
        board_type: ``industry`` 行业 / ``concept`` 概念 / ``region`` 地域。
        period: ``today`` 今日 / ``5d`` 5日 / ``10d`` 10日。
        top_n: 返回条数（1~200）。

    Returns:
        ``{board_type, period, key, total_count, count, rows, limitations,
        source, observed_at}``；行内 ``main_net_yuan`` 为主力净额（元），
        ``main_net_yi`` 为其亿元换算（仅展示便利，不改变口径）。
    """
    board_key = str(board_type or "").strip().lower()
    period_key = str(period or "").strip().lower()
    if board_key not in _BOARD_SCOPES:
        raise ValueError(
            f"未知板块类型 '{board_type}'：可选 {sorted(_BOARD_SCOPES)}"
        )
    if period_key not in _BOARD_PERIODS:
        raise ValueError(f"未知周期 '{period}'：可选 {sorted(_BOARD_PERIODS)}")
    if not 1 <= int(top_n) <= 200:
        raise ValueError(f"top_n 需在 1~200 之间，收到 {top_n}")

    scope = _BOARD_SCOPES[board_key]
    key = _BOARD_PERIODS[period_key]["key"]
    try:
        response = a_stock._em_get(
            _BKZJ_URL,
            params={"key": key, "code": scope["code"]},
            headers={"Referer": scope["referer"]},
            timeout=10,
            retries=3,
        )
        payload = response.json()
    except DeadlineExceeded:
        raise
    except VendorError:
        raise
    except Exception as exc:
        raise VendorNetworkError(
            f"东财板块资金流请求失败：{type(exc).__name__}",
            vendor="eastmoney_bkzj",
            method="getbkzj",
        ) from exc

    data = payload.get("data") if isinstance(payload, dict) else None
    raw_rows = data.get("diff") if isinstance(data, dict) else None
    if not isinstance(raw_rows, list):
        raise VendorNoDataError(
            "东财板块资金流载荷结构异常：data.diff 不是列表",
            vendor="eastmoney_bkzj",
            method="getbkzj",
        )

    parsed: list[tuple[str, str, float]] = []
    for raw in raw_rows:
        if not isinstance(raw, dict):
            continue
        code = str(raw.get("f12") or "").strip()
        name = str(raw.get("f14") or "").strip()
        net = _num(raw.get(key))
        if not code or not name or net is None:
            continue
        parsed.append((code, name, net))
    # 显式按主力净额降序重排：不依赖源端默认顺序（上游 push2 版曾因缺 fid
    # 排序字段而 top 顺序不可靠）。
    parsed.sort(key=lambda item: item[2], reverse=True)

    selected = parsed[: int(top_n)]
    rows = [
        {
            "rank": index + 1,
            "code": code,
            "name": name,
            "main_net_yuan": net,
            "main_net_yi": round(net / 100_000_000, 4),
        }
        for index, (code, name, net) in enumerate(selected)
    ]
    total = data.get("total") if isinstance(data, dict) else None
    try:
        total_count = int(total) if total is not None else len(parsed)
    except (TypeError, ValueError):
        total_count = len(parsed)

    return {
        "board_type": board_key,
        "period": period_key,
        "key": key,
        "total_count": max(total_count, len(parsed)),
        "count": len(rows),
        "rows": rows,
        "limitations": list(_LIMITATIONS),
        "source": "eastmoney bkzj getbkzj",
        "observed_at": datetime.now(_CST).isoformat(timespec="seconds"),
    }


__all__ = ["get_board_fund_flow"]
