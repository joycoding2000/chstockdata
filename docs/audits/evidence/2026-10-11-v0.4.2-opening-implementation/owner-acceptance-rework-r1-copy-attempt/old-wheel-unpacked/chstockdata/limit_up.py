"""打板层：东财四池个股级明细 + 同花顺涨停揭秘（涨停原因/封板质量）。

来源与口径（2026-09-14 实测，移植自上游 a-stock-data v3.7.1 §8.1–8.3）：

- 四池：东财 ``push2ex.eastmoney.com`` 的 ``getTopicZTPool``（涨停）、
  ``getTopicZBPool``（炸板）、``getTopicDTPool``（跌停）、
  ``getYesterdayZTPool``（昨日涨停）。四池只有 ``sort`` 不同：
  涨停/炸板 ``fbt:asc``、跌停沿用本仓 ``market_breadth`` 的 ``zdp:asc``
  实测结论（``fbt`` 在跌停行不存在）、昨涨停 ``zs:desc``。
  所有请求走 ``a_stock._em_get`` 串行限流。
- 价格字段 ``p`` / ``ztp`` 源端为 ×1000 整数，本模块已 ÷1000。
- 金额字段（amount/fund/fba/ltsz）单位均为元，原样透传不做单位猜测。
- 日期的 ``data=null`` 是源端"该日期无数据"（非交易日或超出保留窗口），
  按空池 + ``empty_reason`` 返回；``data`` 存在但 ``pool`` 非列表才是结构
  异常，抛 ``VendorNoDataError``。qdate 是查询时间戳，不是数据日期，仅披露。
- 同花顺涨停揭秘（``data.10jqka.com.cn``）给涨停原因题材 / 封板成功率 /
  板型 / 封单额；``first_limit_up_time`` 是 Unix 秒，不是 HHMMSS。

与 ``get_market_breadth`` 的分工：后者输出全市场聚合（计数/连板分布），
本模块输出个股级明细与昨日涨停池，两者共享 push2ex 通道但互不改变契约。
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any

from . import a_stock
from .market_breadth import _EM_POOL_UT
from .vendor_errors import (
    DeadlineExceeded,
    VendorError,
    VendorNetworkError,
    VendorNoDataError,
)

_CST = timezone(timedelta(hours=8))

_POOL_URL = "https://push2ex.eastmoney.com/{path}"
_POOL_CONFIG: dict[str, dict[str, str]] = {
    "zt": {"path": "getTopicZTPool", "sort": "fbt:asc", "label": "涨停池"},
    "zb": {"path": "getTopicZBPool", "sort": "fbt:asc", "label": "炸板池"},
    "dt": {"path": "getTopicDTPool", "sort": "zdp:asc", "label": "跌停池"},
    "yzt": {"path": "getYesterdayZTPool", "sort": "zs:desc", "label": "昨日涨停池"},
}

_THS_URL = "https://data.10jqka.com.cn/dataapi/limit_up/limit_up_pool"
# 同花顺内部字段 ID，照抄上游实测值（改动会导致字段错位）。
_THS_FIELDS = (
    "199112,10,9001,330323,330324,330325,9002,330329,133971,133970,"
    "1968584,3475914,9003,9004"
)
_THS_FILTER = "HS,GEM2STAR"


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


def _price(value: Any) -> float | None:
    number = _num(value)
    if number is None:
        return None
    return round(number / 1000.0, 4)


def _int(value: Any) -> int | None:
    number = _num(value)
    if number is None:
        return None
    return int(number)


def _fmt_pool_time(value: Any) -> str | None:
    """东财池时间整数 → ``HH:MM:SS``（92500 → 09:25:00）；0/缺失返回 None。"""
    number = _num(value)
    if number is None or number <= 0:
        return None
    seconds = int(number)
    if seconds < 0 or seconds >= 240000:
        return None
    text = str(seconds).zfill(6)
    return f"{text[0:2]}:{text[2:4]}:{text[4:6]}"


def _zt_stat(zttj: Any) -> str | None:
    """"N天M板" 展示串；days/ct 任一缺失则不猜。"""
    if not isinstance(zttj, dict):
        return None
    days = _int(zttj.get("days"))
    count = _int(zttj.get("ct"))
    if days is None or count is None:
        return None
    return f"{days}天{count}板"


def _normalize_pool_date(curr_date: str | None) -> tuple[str, str]:
    """返回 (ISO 日期, YYYYMMDD)。空值取 A 股市场今天。"""
    text = str(curr_date or "").strip()
    if not text:
        day = datetime.now(_CST).date()
        return day.isoformat(), day.strftime("%Y%m%d")
    for fmt in ("%Y-%m-%d", "%Y%m%d"):
        try:
            day = datetime.strptime(text, fmt).date()
        except ValueError:
            continue
        return day.isoformat(), day.strftime("%Y%m%d")
    raise ValueError(f"非法日期 '{curr_date}'：支持 YYYY-MM-DD 或 YYYYMMDD")


def _row(row: dict[str, Any], fields: dict[str, Any]) -> dict[str, Any]:
    result = {
        "code": _text(row.get("c")),
        "name": _text(row.get("n")),
        "industry": _text(row.get("hybk")),
    }
    result.update(fields)
    return result


def _normalize_zt(row: dict[str, Any]) -> dict[str, Any]:
    return _row(
        row,
        {
            "price": _price(row.get("p")),
            "pct": _num(row.get("zdp")),
            "amount_yuan": _num(row.get("amount")),
            "float_cap_yuan": _num(row.get("ltsz")),
            "turnover_pct": _num(row.get("hs")),
            "limit_days": _int(row.get("lbc")),
            "first_seal": _fmt_pool_time(row.get("fbt")),
            "last_seal": _fmt_pool_time(row.get("lbt")),
            "seal_fund_yuan": _num(row.get("fund")),
            "break_times": _int(row.get("zbc")),
            "zt_stat": _zt_stat(row.get("zttj")),
        },
    )


def _normalize_zb(row: dict[str, Any]) -> dict[str, Any]:
    return _row(
        row,
        {
            "price": _price(row.get("p")),
            "limit_price": _price(row.get("ztp")),
            "pct": _num(row.get("zdp")),
            "turnover_pct": _num(row.get("hs")),
            "first_seal": _fmt_pool_time(row.get("fbt")),
            "break_times": _int(row.get("zbc")),
            "amplitude_pct": _num(row.get("zf")),
            "speed_pct": _num(row.get("zs")),
            "zt_stat": _zt_stat(row.get("zttj")),
        },
    )


def _normalize_dt(row: dict[str, Any]) -> dict[str, Any]:
    return _row(
        row,
        {
            "price": _price(row.get("p")),
            "pct": _num(row.get("zdp")),
            "turnover_pct": _num(row.get("hs")),
            "pe": _num(row.get("pe")),
            "seal_fund_yuan": _num(row.get("fund")),
            "last_seal": _fmt_pool_time(row.get("lbt")),
            "board_amount_yuan": _num(row.get("fba")),
            "dt_days": _int(row.get("days")),
            "open_times": _int(row.get("oc")),
        },
    )


def _normalize_yzt(row: dict[str, Any]) -> dict[str, Any]:
    return _row(
        row,
        {
            "price": _price(row.get("p")),
            "pct": _num(row.get("zdp")),
            "turnover_pct": _num(row.get("hs")),
            "amplitude_pct": _num(row.get("zf")),
            "speed_pct": _num(row.get("zs")),
            "y_first_seal": _fmt_pool_time(row.get("yfbt")),
            "y_limit_days": _int(row.get("ylbc")),
            "amount_yuan": _num(row.get("amount")),
            "float_cap_yuan": _num(row.get("ltsz")),
            "zt_stat": _zt_stat(row.get("zttj")),
        },
    )


_NORMALIZERS = {
    "zt": _normalize_zt,
    "zb": _normalize_zb,
    "dt": _normalize_dt,
    "yzt": _normalize_yzt,
}


def get_limit_up_pool(curr_date: str = "", kind: str = "zt") -> dict[str, Any]:
    """东财打板池个股级明细。

    Args:
        curr_date: YYYY-MM-DD 或 YYYYMMDD；空串取市场今天。
        kind: ``zt`` 涨停 / ``zb`` 炸板 / ``dt`` 跌停 / ``yzt`` 昨日涨停。

    Returns:
        ``{date, query_date, kind, label, count, source_total_count, rows,
        empty_reason, source, observed_at}``。``rows`` 顺序即源端排序
        （zt/zb 按首次封板时间、dt 按 zdp、yzt 按涨速），不重排。
    """
    key = str(kind or "").strip().lower()
    if key not in _POOL_CONFIG:
        raise ValueError(f"未知的池类型 '{kind}'：可选 {sorted(_POOL_CONFIG)}")
    iso_date, compact = _normalize_pool_date(curr_date)
    config = _POOL_CONFIG[key]

    try:
        response = a_stock._em_get(
            _POOL_URL.format(path=config["path"]),
            params={
                "ut": _EM_POOL_UT,
                "dpt": "wz.ztzt",
                "Pageindex": "0",
                "pagesize": "10000",
                "sort": config["sort"],
                "date": compact,
            },
            timeout=15,
        )
        payload = response.json()
    except DeadlineExceeded:
        raise
    except VendorError:
        raise
    except Exception as exc:
        raise VendorNetworkError(
            f"东财{config['label']}请求失败：{type(exc).__name__}",
            vendor="eastmoney_push2ex",
            method=config["path"],
        ) from exc

    data = payload.get("data") if isinstance(payload, dict) else None
    if data is None:
        return {
            "date": iso_date,
            "query_date": compact,
            "kind": key,
            "label": config["label"],
            "count": 0,
            "source_total_count": None,
            "source_query_stamp": None,
            "rows": [],
            "empty_reason": (
                f"源端 data=null：{compact} 非交易日或超出该池保留窗口；"
                f"请先用交易日历确认日期"
            ),
            "source": f"eastmoney push2ex {config['path']}",
            "observed_at": datetime.now(_CST).isoformat(timespec="seconds"),
        }
    pool = data.get("pool")
    if not isinstance(pool, list):
        raise VendorNoDataError(
            f"东财{config['label']}载荷结构异常：data.pool 不是列表",
            vendor="eastmoney_push2ex",
            method=config["path"],
        )

    normalize = _NORMALIZERS[key]
    rows = [
        normalize(item)
        for item in pool
        if isinstance(item, dict) and _text(item.get("c"))
    ]
    source_total = _int(data.get("tc"))
    return {
        "date": iso_date,
        "query_date": compact,
        "kind": key,
        "label": config["label"],
        "count": len(rows),
        "source_total_count": source_total,
        "source_query_stamp": _text(data.get("qdate")) or None,
        "rows": rows,
        "empty_reason": None,
        "source": f"eastmoney push2ex {config['path']}",
        "observed_at": datetime.now(_CST).isoformat(timespec="seconds"),
    }


def _ths_time(value: Any) -> str | None:
    number = _int(value)
    if number is None or number <= 0:
        return None
    try:
        return datetime.fromtimestamp(number, tz=_CST).strftime("%H:%M:%S")
    except (OverflowError, OSError, ValueError):
        return None


def _normalize_ths_row(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "code": _text(item.get("code")),
        "name": _text(item.get("name")),
        "price": _num(item.get("latest")),
        "pct": _num(item.get("change_rate")),
        "reason": _text(item.get("reason_type")),
        "board_type": _text(item.get("limit_up_type")),
        "seal_rate": _num(item.get("limit_up_suc_rate")),
        "break_times": _int(item.get("open_num")) or 0,
        "seal_amount_yuan": _num(item.get("order_amount")),
        "high_days": _text(item.get("high_days")),
        "first_time": _ths_time(item.get("first_limit_up_time")),
        "is_again_limit": _int(item.get("is_again_limit")),
    }


def get_limit_up_reasons(curr_date: str = "") -> dict[str, Any]:
    """同花顺涨停揭秘：涨停原因题材 / 封板成功率 / 板型 / 封单额。

    返回 ``{date, query_date, count, rows, empty_reason, source, observed_at}``；
    空列表表示该日源端无涨停揭秘数据（非交易日/盘后未更新）。字段未回复时
    为 ``None`` 而不是 0/空串，消费方不得把缺失当零值。
    """
    iso_date, compact = _normalize_pool_date(curr_date)
    try:
        response = a_stock._source_http_get(
            "ths",
            _THS_URL,
            params={
                "page": 1,
                "limit": 200,
                "field": _THS_FIELDS,
                "filter": _THS_FILTER,
                "order_field": "330324",
                "order_type": "0",
                "date": compact,
            },
            headers={"User-Agent": a_stock._UA},
            timeout=10,
        )
    except DeadlineExceeded:
        raise
    except VendorError:
        raise
    except Exception as exc:
        raise VendorNetworkError(
            f"同花顺涨停揭秘请求失败：{type(exc).__name__}",
            vendor="ths",
            method="limit_up_pool",
        ) from exc

    status_code = getattr(response, "status_code", None)
    if status_code is not None and int(status_code) >= 400:
        raise VendorNoDataError(
            f"同花顺涨停揭秘返回 HTTP {status_code}",
            vendor="ths",
            method="limit_up_pool",
            http_status=int(status_code),
        )
    try:
        payload = response.json()
    except Exception as exc:
        raise VendorNoDataError(
            f"同花顺涨停揭秘载荷不是合法 JSON：{type(exc).__name__}",
            vendor="ths",
            method="limit_up_pool",
        ) from exc
    data = payload.get("data") if isinstance(payload, dict) else None
    info = (data or {}).get("info") if isinstance(data, dict) else None
    if not isinstance(info, list):
        raise VendorNoDataError(
            "同花顺涨停揭秘载荷结构异常：data.info 不是列表",
            vendor="ths",
            method="limit_up_pool",
        )
    rows = [_normalize_ths_row(item) for item in info if isinstance(item, dict)]
    return {
        "date": iso_date,
        "query_date": compact,
        "count": len(rows),
        "rows": rows,
        "empty_reason": (
            None
            if rows
            else f"源端返回空列表：{compact} 非交易日、盘后未更新或该日无涨停"
        ),
        "source": "10jqka limit_up_pool",
        "observed_at": datetime.now(_CST).isoformat(timespec="seconds"),
        "note": (
            "reason 为编辑部人工/AI 归因摘要，非公司公告；board_type 为板型"
            "（换手板/一字板/T字板）；seal_rate 为封板成功率（0~1）。"
        ),
    }


__all__ = ["get_limit_up_pool", "get_limit_up_reasons"]
