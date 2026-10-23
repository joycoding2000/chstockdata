"""市场热度：同花顺热榜 + 东财人气榜 + 东财个股概念命中。

来源与口径（2026-09-14 实测，移植自上游 a-stock-data v3.7.1 §10.2）：

- 同花顺热榜：``dq.10jqka.com.cn`` 单接口返回 排名/人气值/概念标签/排名变化
  （``hour`` / ``day`` 两种周期）。
- 东财人气榜：``emappdata.eastmoney.com/stockrank/getAllCurrentList`` 只给带
  前缀代码（SZ/SH/BJ）与排名，**名称/价格需另行补齐**。本模块用包内
  ``a_stock._get_realtime_quotes``（腾讯→mootdx→新浪链）补齐，而不是上游的
  push2 ``ulist.np``——push2 已按解耦铁律移出本包。
- 东财个股概念命中：``getHotStockRankList``，返回该票当下被市场归到哪些概念
  在炒及命中热度。
- 两个东财 POST 均走 ``a_stock._em_post``（与 ``_em_get`` 共用串行限流锁）。
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

_THS_HOT_URL = "https://dq.10jqka.com.cn/fuyao/hot_list_data/out/hot_list/v1/stock"
_THS_PERIODS = ("hour", "day")

_EM_HOT_BODY = {"appId": "appId01", "globalId": "786e4c21-70dc-435a-93bb-38"}
_EM_RANK_URL = "https://emappdata.eastmoney.com/stockrank/getAllCurrentList"
_EM_CONCEPT_URL = "https://emappdata.eastmoney.com/stockrank/getHotStockRankList"


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


def _text(value: Any) -> str:
    return str(value or "").strip()


def _json_payload(response, vendor: str, method: str) -> Any:
    status_code = getattr(response, "status_code", None)
    if status_code is not None and int(status_code) >= 400:
        raise VendorNoDataError(
            f"{vendor} 返回 HTTP {status_code}",
            vendor=vendor,
            method=method,
            http_status=int(status_code),
        )
    try:
        return response.json()
    except Exception as exc:
        raise VendorNoDataError(
            f"{vendor} 载荷不是合法 JSON：{type(exc).__name__}",
            vendor=vendor,
            method=method,
        ) from exc


def get_hot_rank(period: str = "hour") -> dict[str, Any]:
    """同花顺热榜（排名 / 人气值 / 概念标签 / 排名变化）。

    Args:
        period: ``hour`` 小时榜 / ``day`` 日榜。
    """
    period_key = str(period or "").strip().lower()
    if period_key not in _THS_PERIODS:
        raise ValueError(f"未知周期 '{period}'：可选 {sorted(_THS_PERIODS)}")
    try:
        response = a_stock._source_http_get(
            "ths",
            _THS_HOT_URL,
            params={"stock_type": "a", "type": period_key, "list_type": "normal"},
            headers={"User-Agent": a_stock._UA},
            timeout=10,
        )
    except DeadlineExceeded:
        raise
    except VendorError:
        raise
    except Exception as exc:
        raise VendorNetworkError(
            f"同花顺热榜请求失败：{type(exc).__name__}",
            vendor="ths",
            method="hot_list",
        ) from exc

    payload = _json_payload(response, "ths", "hot_list")
    data = payload.get("data") if isinstance(payload, dict) else None
    stock_list = data.get("stock_list") if isinstance(data, dict) else None
    if not isinstance(stock_list, list):
        raise VendorNoDataError(
            "同花顺热榜载荷结构异常：data.stock_list 不是列表",
            vendor="ths",
            method="hot_list",
        )
    rows: list[dict[str, Any]] = []
    for item in stock_list:
        if not isinstance(item, dict):
            continue
        tag = item.get("tag") if isinstance(item.get("tag"), dict) else {}
        concepts = tag.get("concept_tag")
        rows.append(
            {
                "rank": _num(item.get("order")),
                "code": _text(item.get("code")),
                "name": _text(item.get("name")),
                "heat": _num(item.get("rate")),
                "pct": _num(item.get("rise_and_fall")),
                "rank_change": _num(item.get("hot_rank_chg")),
                "concepts": list(concepts) if isinstance(concepts, list) else [],
                "tag": _text(tag.get("popularity_tag")) or None,
            }
        )
    return {
        "period": period_key,
        "count": len(rows),
        "rows": rows,
        "empty_reason": None if rows else "源端返回空榜单（非交易时段或接口更新中）",
        "source": "10jqka hot_list",
        "observed_at": datetime.now(_CST).isoformat(timespec="seconds"),
    }


def get_em_hot_rank(top: int = 50) -> dict[str, Any]:
    """东财人气榜（排名 + 排名变化；名称/价格用腾讯链补齐）。

    补齐失败时行内 ``name`` / ``price`` 为 None 并在 ``hydration_error``
    披露，不把榜单本身当失败，也不伪造价格。
    """
    if not 1 <= int(top) <= 100:
        raise ValueError(f"top 需在 1~100 之间，收到 {top}")
    try:
        response = a_stock._em_post(
            _EM_RANK_URL,
            json={**_EM_HOT_BODY, "marketType": "", "pageNo": 1, "pageSize": int(top)},
            headers={"User-Agent": a_stock._UA},
            timeout=10,
        )
    except DeadlineExceeded:
        raise
    except VendorError:
        raise
    except Exception as exc:
        raise VendorNetworkError(
            f"东财人气榜请求失败：{type(exc).__name__}",
            vendor="eastmoney_emappdata",
            method="getAllCurrentList",
        ) from exc

    payload = _json_payload(response, "eastmoney_emappdata", "getAllCurrentList")
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, list):
        raise VendorNoDataError(
            "东财人气榜载荷结构异常：data 不是列表",
            vendor="eastmoney_emappdata",
            method="getAllCurrentList",
        )

    entries: list[dict[str, Any]] = []
    codes: list[str] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        security = _text(item.get("sc")).upper()
        code = security[2:] if security[:2] in {"SZ", "SH", "BJ"} else security
        if not code:
            continue
        entries.append(
            {
                "rank": _num(item.get("rk")),
                "code": code,
                "market": security[:2] if security[:2] in {"SZ", "SH", "BJ"} else None,
                "rank_change": _num(item.get("hisRc")),
            }
        )
        codes.append(code)

    hydration_error: str | None = None
    quotes: dict[str, dict] = {}
    if codes:
        try:
            quotes = a_stock._get_realtime_quotes(codes)
        except Exception as exc:  # 人气榜本身可用，价格补齐失败单独披露
            hydration_error = f"{type(exc).__name__}"
    for entry in entries:
        quote = quotes.get(entry["code"]) or {}
        entry["name"] = _text(quote.get("name")) or None
        entry["price"] = _num(quote.get("price"))
        entry["pct"] = _num(quote.get("change_pct"))
    if hydration_error is not None:
        for entry in entries:
            entry["hydration_failed"] = True

    return {
        "count": len(entries),
        "rows": entries,
        "hydration_error": hydration_error,
        "empty_reason": None if entries else "源端返回空榜单（非交易时段或接口更新中）",
        "source": "eastmoney emappdata getAllCurrentList + tencent hydration",
        "observed_at": datetime.now(_CST).isoformat(timespec="seconds"),
    }


def get_hot_concepts(ticker: str) -> dict[str, Any]:
    """东财个股热门概念命中（该票当下被市场归到哪些概念在炒）。"""
    try:
        code = a_stock._normalize_ticker(ticker)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"非法 ticker: {ticker!r} ({type(exc).__name__})") from exc
    src_code = f"{a_stock._get_prefix(code).upper()}{code}"
    try:
        response = a_stock._em_post(
            _EM_CONCEPT_URL,
            json={**_EM_HOT_BODY, "srcSecurityCode": src_code},
            headers={"User-Agent": a_stock._UA},
            timeout=10,
        )
    except DeadlineExceeded:
        raise
    except VendorError:
        raise
    except Exception as exc:
        raise VendorNetworkError(
            f"东财个股概念命中请求失败：{type(exc).__name__}",
            vendor="eastmoney_emappdata",
            method="getHotStockRankList",
        ) from exc

    payload = _json_payload(response, "eastmoney_emappdata", "getHotStockRankList")
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, list):
        raise VendorNoDataError(
            "东财个股概念命中载荷结构异常：data 不是列表",
            vendor="eastmoney_emappdata",
            method="getHotStockRankList",
        )
    rows = [
        {
            "concept": _text(item.get("conceptName")),
            "board_code": _text(item.get("conceptId")) or None,
            "hit": _num(item.get("hitCount")),
        }
        for item in data
        if isinstance(item, dict) and _text(item.get("conceptName"))
    ]
    rows.sort(key=lambda item: item["hit"] or 0.0, reverse=True)
    return {
        "ticker": code,
        "src_code": src_code,
        "count": len(rows),
        "rows": rows,
        "empty_reason": None if rows else "该标的当前无概念命中记录",
        "source": "eastmoney emappdata getHotStockRankList",
        "observed_at": datetime.now(_CST).isoformat(timespec="seconds"),
    }


__all__ = ["get_em_hot_rank", "get_hot_concepts", "get_hot_rank"]
