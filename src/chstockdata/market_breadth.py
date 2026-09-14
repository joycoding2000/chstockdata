"""F2 免费市场广度数据（v0.5.0）— 独立数据获取模块。

范围（docs/releases/v0.5.0/data-coverage-roadmap.md §3 F2）：
  上涨/下跌/平盘家数、涨停/跌停家数、炸板统计、连板分布与最高连板。

来源（均为免费公开直连，2026-09-07 实测字段核对）：
  - 涨停/炸板/跌停/连板：东财 push2ex 专题池（getTopicZTPool / getTopicZBPool /
    getTopicDTPool），源端聚合 + 源端涨跌停标识。注意：push2ex 是涨停池专题接口，
    与 push2 解耦铁律针对的 push2 四档资金流/全市场行情是不同端点；本模块不含任何
    push2 / push2his 域名的请求（源码级守卫见 tests/test_free_market_breadth.py）。
    所有请求走 ``a_stock._em_get`` 串行限流（东财铁律 5）。
  - 上涨/下跌/平盘：新浪 ``Market_Center.getHQNodeData``（node=hs_a，含沪深A股与
    北交所）有界分页全市场快照；``num`` 上限 100，~5.6k 股票 ≈ 56 页顺序抓取，
    页间 0.15s+ 间隔，不并发。快照交易日经新浪上证指数行情尾部的日期字段锚定
    （休市时该日期即最近实际交易日，不冒充今日）。

2026-09-07 实测的源端语义（写死在实现里，避免误读）：
  - 池接口 ``date`` 参数过滤生效（同池不同日期返回不同内容）；响应内 ``qdate`` 是
    服务端查询日期戳而非数据日期（查 2026-09-04 数据返回 qdate=2026-09-07），
    因此池的交易日以请求参数为准，qdate 仅作披露。
  - 非交易日/超出保留窗口的日期返回 ``tc=0`` 空池（不是 data=null）。空池与
    "交易日合法零值"的区分：周末直接判定非交易日不请求；三池同时全空在真实交易日
    实际不可能（每日必有涨停/炸板），按"该日期无数据"处理，不报 0。
  - 跌停池按 fbt 排序会返回空池（DT 行无 fbt 字段），必须用 zdp:asc。

本模块是 F2 的数据层交付，公共包装 `a_stock.get_market_breadth` 已接线
（interface 路由、tool plan、hot_money 数据面），Registry 归属
`cap_free_market_breadth`；工具输出携带结构化 Evidence 注释块
（`build_market_breadth_evidence`，CR-EVIDENCE-WIRING-F2-F4）。
语义沿用现有 ProviderAttempt 状态枚举（evidence.py），不新建平行状态体系。
"""

from __future__ import annotations

import json
import logging
import random
import re
import time
from datetime import date as _date, datetime, timedelta, timezone
from typing import Any, Mapping

from .a_stock import _UA, _em_get, _source_http_get
from .provenance import (
    ATTEMPT_FAILED_NETWORK,
    ATTEMPT_FAILED_STRUCTURE,
    ATTEMPT_NORMAL_EMPTY,
    ATTEMPT_SKIPPED,
    ATTEMPT_SUCCESS,
    COMPLETENESS_FULL,
    COMPLETENESS_MINIMAL,
    COMPLETENESS_PARTIAL,
    EvidenceEnvelope,
    ProviderAttempt,
    make_attempt,
)
from .vendor_errors import DeadlineExceeded as SourceContextDeadlineExceeded

logger = logging.getLogger(__name__)

# A 股市场固定 UTC+8（无夏令时），避免宿主机时区差异。
_CST = timezone(timedelta(hours=8))

# ── 东财 push2ex 专题池 ──────────────────────────────────────────────────────
_EM_POOL_URL = "https://push2ex.eastmoney.com/getTopic{pool}Pool"
_EM_POOL_UT = "7eea3edcaed734bea9cbfc24409ed989"
_EM_POOL_CONFIG: dict[str, dict[str, str]] = {
    "limit_up": {"pool": "ZT", "sort": "fbt:asc", "label": "涨停池"},
    "failed_board": {"pool": "ZB", "sort": "fbt:asc", "label": "炸板池"},
    "limit_down": {"pool": "DT", "sort": "zdp:asc", "label": "跌停池"},
}

# 指标定义（用户可读，随结果原样输出，消费者不得改写口径）。
_DEFINITIONS: dict[str, str] = {
    "advance_decline": (
        "上涨/下跌/平盘按新浪快照 pricechange（现价-昨收）符号分类；分母=三类家数之和；"
        "停牌/无有效报价（trade<=0）、无昨收参考价（settlement<=0，如上市首日）、"
        "零成交且零涨跌（停牌或全天无成交，快照无法区分）、涨跌字段缺失的股票一律排除在"
        "分母外并逐项计数，绝不默认计为平盘。"
    ),
    "limit_up": (
        "涨停家数=东财涨停池（getTopicZTPool）源端标识的当日封住涨停股票数"
        "（盘中快照=当前封板中，收盘后为最终口径）；"
        "主板10%/创业板与科创板20%/ST 5%/北交所30% 按各板块实际规则由源端判定，"
        "本模块不做 ±10% 推算。池日期以请求参数为准（源端 qdate 为查询时间戳）。"
    ),
    "limit_down": (
        "跌停家数=东财跌停池（getTopicDTPool）源端标识的当日封住跌停股票数；"
        "days 字段为连续跌停交易日数（含当日）。跌停为 0 是常见合法零值。"
    ),
    "failed_board": (
        "炸板=东财炸板池（getTopicZBPool）：盘中曾触及涨停但收盘未封住涨停的股票数"
        "（含曾封板后开板；盘中快照=曾触板且当前未封住，收盘后为最终口径；"
        "计数对象为股票数，非开板次数，每股盘中开板次数 zbc 另计）；"
        "仅统计涨停方向，跌停方向开板不在本口径内。盘中事件依赖源端标记，"
        "不能仅凭收盘快照推断。"
    ),
    "consecutive_limit_up": (
        "连板分布基于涨停池 lbc 字段（连续涨停交易日数，含当日，东财口径），与涨停池"
        "同池同口径，盘中快照为暂态值；zttj={days,ct} 为'days 天 ct 板'（如 11 天 7 板），"
        "与 lbc 不可互相换算；lbc 缺失的个股计入 unknown 桶不猜板数；N 前缀（上市首日）"
        "与 C 前缀（次新）股票单独披露不剔除。连续收阳天数不是连板，本模块不输出该口径。"
    ),
}

# ── 新浪全市场快照 ──────────────────────────────────────────────────────────
_SINA_NODE_URL = (
    "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/"
    "Market_Center.getHQNodeData"
)
_SINA_COUNT_URL = (
    "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/"
    "Market_Center.getHQNodeStockCount?node=hs_a"
)
_SINA_INDEX_URL = "https://hq.sinajs.cn/list=sh000001"
_SINA_INDEX_KLINE_URL = (
    "http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/"
    "CN_MarketData.getKLineData"
)
_SINA_HEADERS = {
    "User-Agent": _UA,
    "Referer": "https://vip.stock.finance.sina.com.cn/mkt/",
}
_SINA_PAGE_SIZE = 100          # 源端实测上限：num>100 只返回 100 行
_SINA_MAX_PAGES = 80           # 有界分页上限（~5.6k 股票需 56 页，留缓冲）
_SINA_PAGE_GAP_S = 0.15        # 顺序分页的页间礼貌间隔（另有随机抖动）


def _num(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed


def _now_cst() -> datetime:
    return datetime.now(_CST)


def _normalize_date(curr_date: str | None) -> str:
    """归一化请求日期为 YYYY-MM-DD；空值取北京时间今日。非法输入抛 ValueError。"""
    text = str(curr_date or "").strip()
    if not text:
        return _now_cst().strftime("%Y-%m-%d")
    text = text.replace("/", "-").replace(".", "-")
    if re.fullmatch(r"\d{8}", text):
        text = f"{text[:4]}-{text[4:6]}-{text[6:]}"
    parsed = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", text)
    if parsed is None:
        raise ValueError(f"invalid date {curr_date!r}, expect YYYY-MM-DD")
    _date(int(parsed.group(1)), int(parsed.group(2)), int(parsed.group(3)))
    return text


def _is_weekend(day: str) -> bool:
    """周六/周日必非 A 股交易日（节假日无法离线判定，靠三池全空规则兜底）。"""
    y, m, d = (int(x) for x in day.split("-"))
    return _date(y, m, d).weekday() >= 5


def _calendar_is_trading_day(day: str) -> bool | None:
    """交易日历判定；日历不可用或区间外返回 None（回落既有启发式）。

    DEC-P1-27：日历是支持性能力——这里的任何失败都不得影响广度请求，
    因此全部异常吞掉并返回 None。区间外日期同样返回 None：禁止把
    "本地包未刷新" 表达成 "当天没交易"。
    """
    try:
        from .trading_calendar import (
            is_trading_day,
            load_trading_calendar,
        )

        return is_trading_day(load_trading_calendar(), day)
    except Exception:  # noqa: BLE001 - supportive capability never fails the tool
        return None


def _phase_for(trade_date: str | None, source_time: str | None) -> str | None:
    """快照阶段：交易日当天 15:00 前为盘中，其余为收盘口径。"""
    if not trade_date:
        return None
    today = _now_cst().strftime("%Y-%m-%d")
    if trade_date != today:
        return "close"
    clock = source_time or _now_cst().strftime("%H:%M:%S")
    return "intraday" if clock < "15:00:00" else "close"


def _is_st(name: Any) -> bool:
    return "ST" in str(name or "").upper()


def _is_new_listing(name: Any) -> bool:
    """源端命名约定：N 前缀=上市首日，C 前缀=上市次日至数日（次新）。"""
    return str(name or "").strip().startswith(("N", "C"))


def _is_bse_code(code: Any) -> bool:
    """北交所代码段：43/83/87/92 开头（沪 60/68、深 00/30 不冲突）。"""
    return str(code or "").strip().startswith(("43", "83", "87", "92"))


# ── 东财专题池 ──────────────────────────────────────────────────────────────


def _fetch_em_pool(kind: str, date_compact: str) -> tuple[dict[str, Any] | None, str | None, ProviderAttempt]:
    """抓取一个东财专题池。

    返回 (parsed, failure, attempt)。parsed 非 None 时含 pool/tc/qdate（qdate 仅
    查询时间戳）。failure 为 None 表示拿到数据或空池；"network" / "no_data" 分别
    表示请求失败与 data=null（该日期无数据）。空池（tc=0）的交易日判定交给调用方
    （三池全空≈非交易日），本函数不猜测。
    """
    cfg = _EM_POOL_CONFIG[kind]
    method = f"push2ex.getTopic{cfg['pool']}Pool"
    started = time.monotonic()
    try:
        resp = _em_get(
            _EM_POOL_URL.format(pool=cfg["pool"]),
            params={
                "ut": _EM_POOL_UT,
                "dpt": "wz.ztzt",
                "Pageindex": "0",
                "pagesize": "1000",
                "sort": cfg["sort"],
                "date": date_compact,
            },
            timeout=15,
        )
        payload = resp.json()
    except Exception as exc:
        logger.warning("市场广度：东财%s获取失败（%s）", cfg["label"], type(exc).__name__)
        return None, "network", make_attempt(
            "a_stock_eastmoney",
            ATTEMPT_FAILED_NETWORK,
            method=method,
            duration_ms=int((time.monotonic() - started) * 1000),
            error_summary=f"eastmoney {cfg['label']} request failed: {type(exc).__name__}",
        )
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict) or not isinstance(data.get("pool"), list):
        # v0.5.0 CR-EVIDENCE-WIRING-F2-F4: a null pool payload means the source
        # has no data for that date — a failed observation, not a legal empty.
        return None, "no_data", make_attempt(
            "a_stock_eastmoney",
            ATTEMPT_FAILED_STRUCTURE,
            method=method,
            duration_ms=int((time.monotonic() - started) * 1000),
            error_summary=f"data=null for {date_compact} (no data for date)",
            record_count=0,
        )
    return data, None, make_attempt(
        "a_stock_eastmoney",
        ATTEMPT_SUCCESS,
        method=method,
        duration_ms=int((time.monotonic() - started) * 1000),
        record_count=len(data.get("pool") or []),
    )


def _pool_summary(kind: str, data: dict[str, Any]) -> dict[str, Any]:
    """把一个池的行聚合为计数统计（源端标识，不做涨跌幅推算）。

    count 以实际返回行数为准（可核对），源端总数 tc 单独披露；不一致时写入
    limitations，绝不静默取其一。
    """
    rows: list[dict] = data.get("pool") or []
    tc = _num(data.get("tc"))
    summary: dict[str, Any] = {
        "count": len(rows),
        "source_total_count": int(tc) if tc is not None else None,
        "source": "eastmoney push2ex getTopic%sPool" % _EM_POOL_CONFIG[kind]["pool"],
        "source_query_date": str(data.get("qdate") or "") or None,
        "st_count": sum(1 for r in rows if _is_st(r.get("n"))),
        "new_listing_count": sum(1 for r in rows if _is_new_listing(r.get("n"))),
        "bse_count": sum(1 for r in rows if _is_bse_code(r.get("c"))),
    }
    if tc is not None and int(tc) != len(rows):
        summary["limitations"] = [
            f"源端总数 tc={int(tc)} 与返回行数 {len(rows)} 不一致，count 以可核对的返回行数为准"
        ]
    else:
        summary["limitations"] = []

    if kind == "limit_up":
        distribution: dict[str, int] = {}
        max_boards = 0
        known = 0
        top: list[dict[str, Any]] = []
        for row in rows:
            lbc = _num(row.get("lbc"))
            if lbc is None or lbc <= 0:
                # lbc 缺失不猜板数：进 unknown 桶（首板占池内绝大多数，但缺失就是缺失）。
                distribution["unknown"] = distribution.get("unknown", 0) + 1
                boards = None
            else:
                boards = int(lbc)
                distribution[str(boards)] = distribution.get(str(boards), 0) + 1
                max_boards = max(max_boards, boards)
                known += 1
            zttj = row.get("zttj") or {}
            top.append(
                {
                    "code": str(row.get("c") or ""),
                    "name": str(row.get("n") or ""),
                    "boards": boards,
                    "days_boards": (
                        f"{zttj.get('days')}天{zttj.get('ct')}板"
                        if zttj.get("days") is not None
                        else None
                    ),
                }
            )
        top.sort(key=lambda item: (-(item["boards"] or 0), item["code"]))
        # 空池=0 家涨停 → 最高 0 板（合法零值）；行存在但全部缺 lbc 才是 None。
        summary["consecutive"] = {
            "max_boards": max_boards if (known or not rows) else None,
            "distribution": dict(sorted(distribution.items(), key=lambda kv: int(kv[0]) if kv[0].isdigit() else 10**9)),
            "top": top[:5],
        }
    elif kind == "failed_board":
        zbc_total = 0
        missing_zbc = 0
        for row in rows:
            zbc = _num(row.get("zbc"))
            if zbc is None:
                missing_zbc += 1
            else:
                zbc_total += int(zbc)
        summary["open_count_total"] = zbc_total
        summary["missing_open_count_fields"] = missing_zbc
    elif kind == "limit_down":
        max_days = 0
        missing_days = 0
        for row in rows:
            days = _num(row.get("days"))
            if days is None:
                missing_days += 1
            else:
                max_days = max(max_days, int(days))
        summary["max_consecutive_days"] = max_days if rows else None
        summary["missing_days_fields"] = missing_days
    return summary


# ── 新浪全市场快照 ──────────────────────────────────────────────────────────


def _sina_index_anchor() -> tuple[str | None, str | None]:
    """用新浪上证指数行情尾部日期/时间锚定快照交易日（休市时为最近实际交易日）。"""
    try:
        resp = _source_http_get(
            "sina", _SINA_INDEX_URL,
            headers={"User-Agent": _UA, "Referer": "https://finance.sina.com.cn/"},
            timeout=10,
        )
        resp.raise_for_status()
        raw = getattr(resp, "content", b"").decode("gbk", errors="replace")
    except Exception as exc:
        logger.warning("市场广度：新浪指数快照锚定失败（%s），尝试同源日线锚点", type(exc).__name__)
    else:
        match = re.search(r"(\d{4}-\d{2}-\d{2}),(\d{2}:\d{2}:\d{2})", raw)
        if match is not None:
            return match.group(1), match.group(2)

    # hq.sinajs.cn may reject a server IP while Sina's existing daily-K-line
    # endpoint remains available.  It can only identify the latest completed
    # session, so retain the close-time precision rather than claiming an
    # intraday timestamp.
    try:
        resp = _source_http_get(
            "sina",
            _SINA_INDEX_KLINE_URL,
            params={"symbol": "sh000001", "scale": "240", "ma": "no", "datalen": "2"},
            timeout=10,
        )
        resp.raise_for_status()
        rows = json.loads(resp.text)
        if not isinstance(rows, list) or not rows:
            raise ValueError("empty index K-line payload")
        latest = rows[-1]
        if not isinstance(latest, dict):
            raise ValueError("invalid index K-line row")
        match = re.search(r"\d{4}-\d{2}-\d{2}", str(latest.get("day") or ""))
        if match is None:
            raise ValueError("index K-line row has no date")
        return match.group(0), "15:00:00"
    except Exception as exc:
        logger.warning("市场广度：新浪指数日线锚定失败（%s）", type(exc).__name__)
        return None, None


def _sina_universe_count() -> int | None:
    try:
        resp = _source_http_get(
            "sina", _SINA_COUNT_URL, headers=_SINA_HEADERS, timeout=10
        )
        resp.raise_for_status()
        return int(str(resp.text).strip().strip('"'))
    except Exception as exc:
        logger.warning("市场广度：新浪股票总数获取失败（%s）", type(exc).__name__)
        return None


def _classify_snapshot_rows(rows: list[dict]) -> dict[str, Any]:
    """按 pricechange 符号分类全市场快照；停牌/无参考价/字段缺失不默认计为平盘。"""
    adv = dec = flat = 0
    st = {"advancing": 0, "declining": 0, "flat": 0}
    excluded = {
        "no_valid_quote": 0,           # trade<=0：停牌/无有效报价
        "missing_reference_price": 0,  # settlement<=0：上市首日等无昨收参考
        "untraded_zero_change": 0,     # 零成交且零涨跌：停牌或全天无成交，无法区分
        "missing_change_field": 0,     # 涨跌字段缺失，不是 0
    }
    markets = {"sh": 0, "sz": 0, "bj": 0}
    seen: set[str] = set()
    duplicates = 0
    for row in rows:
        symbol = str(row.get("symbol") or "").strip()
        if not symbol:
            continue
        if symbol in seen:
            duplicates += 1
            continue
        seen.add(symbol)
        prefix = symbol[:2]
        if prefix not in markets:
            continue
        trade = _num(row.get("trade"))
        settlement = _num(row.get("settlement"))
        change = _num(row.get("pricechange"))
        volume = _num(row.get("volume"))
        if trade is None or trade <= 0:
            excluded["no_valid_quote"] += 1
            continue
        if settlement is None or settlement <= 0:
            excluded["missing_reference_price"] += 1
            continue
        if change is None:
            excluded["missing_change_field"] += 1
            continue
        markets[prefix] += 1
        if volume == 0 and change == 0:
            excluded["untraded_zero_change"] += 1
            continue
        is_st = _is_st(row.get("name"))
        if change > 0:
            adv += 1
            st["advancing"] += int(is_st)
        elif change < 0:
            dec += 1
            st["declining"] += int(is_st)
        else:
            flat += 1
            st["flat"] += int(is_st)
    return {
        "advancing": adv,
        "declining": dec,
        "flat": flat,
        "denominator": adv + dec + flat,
        "st_counts": st,
        "excluded": excluded,
        "valid_quote_by_market": markets,
        "unique_rows": len(seen),
        "duplicates": duplicates,
    }


def _fetch_sina_advance_decline(
    anchor_date: str | None, anchor_time: str | None
) -> tuple[dict[str, Any] | None, str | None, ProviderAttempt]:
    """有界分页抓取新浪 hs_a 全市场快照并统计涨/跌/平。

    完整性规则：分页去重后与源端总数核对，截断/漏页/未知总数时降级 partial 并注明
    分母来源，绝不把部分快照宣称为全市场覆盖。返回 (result, failure, attempt)。
    """
    started = time.monotonic()
    method = "Market_Center.getHQNodeData"
    expected: int | None = None
    rows: list[dict] = []
    truncated = False
    deadline_after_rows: SourceContextDeadlineExceeded | None = None
    try:
        expected = _sina_universe_count()
        for page in range(1, _SINA_MAX_PAGES + 1):
            resp = _source_http_get(
                "sina",
                _SINA_NODE_URL,
                params={
                    "page": page,
                    "num": _SINA_PAGE_SIZE,
                    "sort": "symbol",
                    "asc": 1,
                    "node": "hs_a",
                    "symbol": "",
                    "_s_r_a": "page",
                },
                headers=_SINA_HEADERS,
                timeout=15,
            )
            resp.raise_for_status()
            payload = json.loads(resp.text)
            if not isinstance(payload, list):
                return None, "structure", make_attempt(
                    "a_stock_sina",
                    ATTEMPT_FAILED_STRUCTURE,
                    method=method,
                    duration_ms=int((time.monotonic() - started) * 1000),
                    error_summary="sina hs_a payload is not a list",
                )
            rows.extend(r for r in payload if isinstance(r, dict))
            if len(payload) < _SINA_PAGE_SIZE:
                break
            if page == _SINA_MAX_PAGES:
                truncated = True
            time.sleep(_SINA_PAGE_GAP_S + random.uniform(0.0, 0.1))
    except SourceContextDeadlineExceeded as exc:
        if not rows:
            logger.warning("市场广度：新浪全市场快照失败（%s）", type(exc).__name__)
            return None, "network", make_attempt(
                "a_stock_sina",
                ATTEMPT_FAILED_NETWORK,
                method=method,
                duration_ms=int((time.monotonic() - started) * 1000),
                error_summary=f"sina hs_a snapshot failed: {type(exc).__name__}",
            )
        # Keep the rows that were already fetched.  The result is explicitly
        # partial and can never be promoted to full-market coverage.
        deadline_after_rows = exc
    except Exception as exc:
        logger.warning("市场广度：新浪全市场快照失败（%s）", type(exc).__name__)
        return None, "network", make_attempt(
            "a_stock_sina",
            ATTEMPT_FAILED_NETWORK,
            method=method,
            duration_ms=int((time.monotonic() - started) * 1000),
            error_summary=f"sina hs_a snapshot failed: {type(exc).__name__}",
        )

    if not rows:
        # 空载荷不能解释为全市场零上涨/零下跌。
        return None, "structure", make_attempt(
            "a_stock_sina",
            ATTEMPT_FAILED_STRUCTURE,
            method=method,
            duration_ms=int((time.monotonic() - started) * 1000),
            error_summary="sina hs_a snapshot returned zero rows",
        )

    stats = _classify_snapshot_rows(rows)
    completeness = "full"
    limitations: list[str] = []
    if deadline_after_rows is not None:
        completeness = "partial"
        limitations.append(
            "分页在工具 source context deadline 前未完成；仅保留已获取页，不能宣称全市场覆盖"
        )
    if truncated:
        completeness = "partial"
        limitations.append(f"分页达到上限 {_SINA_MAX_PAGES} 页，快照被截断")
    if expected is None:
        completeness = "unknown" if completeness == "full" else completeness
        limitations.append("源端股票总数不可用，完整性未验证，不能宣称全市场覆盖")
    elif stats["unique_rows"] != expected:
        completeness = "partial"
        limitations.append(
            f"分页去重后 {stats['unique_rows']} 只 != 源端总数 {expected} 只（漏页/重复/盘中进出），不能宣称全市场覆盖"
        )
    if stats["duplicates"]:
        limitations.append(f"分页发现 {stats['duplicates']} 条重复行，已按 symbol 去重")

    result = {
        **stats,
        "expected_universe": expected,
        "completeness": completeness,
        "source": "sina Market_Center.getHQNodeData node=hs_a (bounded pagination)",
        "universe": (
            "沪深A股+北交所（新浪 hs_a 节点；沪 sh/深 sz/北交所 bj 的有效报价家数见 valid_quote_by_market，"
            "ST 与上市首日含在内；停牌/无参考价等排除项见 excluded）"
        ),
        "trade_date": anchor_date,
        "source_time": anchor_time,
        "phase": _phase_for(anchor_date, anchor_time),
        "limitations": limitations,
    }
    # A snapshot truncated by the tool deadline still delivered usable rows, so
    # the attempt succeeded; the truncation is disclosed by completeness=partial,
    # the limitation line, the error_summary and record_count.  ProviderAttempt
    # has no "partial" status, and marking this failed_network contradicted the
    # item status and made it inconsistent with the page-cap truncation above
    # (which keeps ATTEMPT_SUCCESS).  The kind is None because data was returned.
    return result, None, make_attempt(
        "a_stock_sina",
        ATTEMPT_SUCCESS,
        method=method,
        duration_ms=int((time.monotonic() - started) * 1000),
        error_summary=(
            "sina hs_a snapshot retained partial rows after tool deadline"
            if deadline_after_rows is not None
            else None
        ),
        record_count=stats["unique_rows"],
    )


# ── 汇总入口 ────────────────────────────────────────────────────────────────


def _subitem(definition_key: str, **fields: Any) -> dict[str, Any]:
    item = {"definition": _DEFINITIONS[definition_key]}
    item.update(fields)
    return item


def get_market_breadth(curr_date: str = "") -> dict[str, Any]:
    """获取一个交易日的免费市场广度统计（v0.5.0 F2，独立数据层，未接线）。

    参数 ``curr_date``：YYYY-MM-DD（默认北京时间今日；非法格式抛 ValueError）。
    返回 JSON 可序列化 dict：

    - 顶层 ``status``：success / partial / unavailable（按子项可用性汇总）。
    - ``advance_decline``：涨/跌/平 + 可解释分母 + 排除明细（新浪快照，仅最近
      交易日；历史日期请求时该子项 unavailable，不用池子数据伪装）。
    - ``limit_up`` / ``limit_down`` / ``failed_board`` / ``consecutive_limit_up``：
      东财专题池源端聚合（支持历史日期，约一个月保留窗口）。
    - 每个子项独立携带 status/source/trade_date/覆盖计数/定义/limitations。

    语义约定（与 F2 数据契约一一对应）：
    - 正常零值（如全市场无跌停）是合法值；三池同时全空按"该日期无数据"处理
      （真实交易日必有涨停/炸板），周末直接判非交易日，不报 0。
    - 休市请求今日时以新浪指数日期锚定实际交易日，池子改查实际交易日并显式
      标注，不冒充今日实时；盘中抓取 phase=intraday。
    - 池数据日期以请求参数为准（源端 qdate 为查询时间戳，仅披露）。
    - ``attempts`` 为 ProviderAttempt 序列化（evidence.py 枚举），供后续接线
      EvidenceEnvelope 使用；本模块不伪造未注册的 capability_id。
    """
    requested = _normalize_date(curr_date)
    attempts: list[ProviderAttempt] = []
    limitations: list[str] = []
    now = _now_cst()

    anchor_date, anchor_time = _sina_index_anchor()
    if anchor_date is None:
        limitations.append("新浪指数日期锚定失败，快照交易日以各子项披露为准")
    is_today = requested == now.strftime("%Y-%m-%d")
    actual_date = requested
    if is_today and anchor_date is not None and anchor_date != requested:
        actual_date = anchor_date
        limitations.append(
            f"请求日 {requested} 非交易时段，源端返回最近交易日 {anchor_date} 数据（不冒充今日实时）"
        )

    result: dict[str, Any] = {
        "requested_date": requested,
        "actual_trade_date": None,  # 各子项日期一致时填充；不一致保持 None 并记录
        "fetched_at": now.isoformat(),
        "snapshot": {
            "sina_anchor_date": anchor_date,
            "sina_anchor_time": anchor_time,
            "phase": _phase_for(actual_date if is_today else requested, anchor_time),
        },
    }

    # ── 涨/跌/平（新浪快照，仅最近交易日）───────────────────────────────
    if is_today or requested == anchor_date:
        adv_dec, failure, attempt = _fetch_sina_advance_decline(anchor_date, anchor_time)
        attempts.append(attempt)
        if adv_dec is not None:
            result["advance_decline"] = _subitem(
                "advance_decline",
                status="success" if adv_dec["completeness"] == "full" else "partial",
                **adv_dec,
            )
        else:
            reason = (
                "新浪全市场快照结构异常（空载荷或非列表载荷），不能解释为零上涨/零下跌"
                if failure == "structure"
                else f"新浪全市场快照请求失败（{attempt.error_summary}）"
            )
            result["advance_decline"] = _subitem("advance_decline", status="unavailable", reason=reason)
    else:
        result["advance_decline"] = _subitem(
            "advance_decline",
            status="unavailable",
            reason="新浪快照仅支持最近交易日，历史日期无全市场涨跌家数；不使用池子样本伪装",
        )

    # ── 东财三池 ────────────────────────────────────────────────────────
    calendar_verdict = _calendar_is_trading_day(actual_date)
    if calendar_verdict is False:
        # 交易日历（本地 vipdoc 上证指数）确认非交易日：不发请求，直接无数据语义。
        for kind in ("limit_up", "failed_board", "limit_down"):
            result[kind] = _subitem(
                kind,
                status="unavailable",
                reason=(
                    f"{actual_date} 非交易日（交易日历：上证指数无 bar），"
                    "无池数据（不是 0 家）"
                ),
            )
        pool_dates: dict[str, str | None] = {}
    elif calendar_verdict is None and _is_weekend(actual_date):
        # 周末必非交易日：不发请求，直接无数据语义（节假日无法离线判定，走三池全空规则）。
        for kind in ("limit_up", "failed_board", "limit_down"):
            result[kind] = _subitem(
                kind,
                status="unavailable",
                reason=f"{actual_date} 为周末，非 A 股交易日，无池数据（不是 0 家）",
            )
        pool_dates: dict[str, str | None] = {}
    else:
        date_compact = actual_date.replace("-", "")
        pool_failures = {}
        pool_dates = {}
        pool_attempts: dict[str, ProviderAttempt] = {}
        pool_data: dict[str, dict[str, Any] | None] = {}
        for kind in ("limit_up", "failed_board", "limit_down"):
            data, failure, attempt = _fetch_em_pool(kind, date_compact)
            attempts.append(attempt)
            pool_attempts[kind] = attempt
            pool_data[kind] = data
            pool_failures[kind] = failure
            pool_dates[kind] = actual_date if failure is None else None

        all_empty = all(
            isinstance(d, dict) and not (d.get("pool") or []) for d in pool_data.values()
        ) and any(isinstance(d, dict) for d in pool_data.values())
        if all_empty:
            if calendar_verdict is True:
                limitations.append(
                    "三池同时全空：交易日历确认该日为交易日，疑似超出源端保留窗口，不报 0 家"
                )
            else:
                limitations.append(
                    "三池同时全空：按'该日期无数据'处理（真实交易日必有涨停/炸板；"
                    "疑似节假日或超出源端保留窗口），不报 0 家"
                )

        for kind in ("limit_up", "failed_board", "limit_down"):
            data = pool_data[kind]
            if data is None:
                if pool_failures[kind] == "no_data":
                    reason = f"东财{_EM_POOL_CONFIG[kind]['label']}该日期无数据（data=null）"
                else:
                    reason = (
                        f"东财{_EM_POOL_CONFIG[kind]['label']}请求失败"
                        f"（{pool_attempts[kind].error_summary}）"
                    )
                result[kind] = _subitem(kind, status="unavailable", reason=reason)
                continue
            summary = _pool_summary(kind, data)
            is_empty = summary["count"] == 0
            if is_empty and all_empty:
                if calendar_verdict is True:
                    reason = "该日期三池全空，但交易日历确认是交易日，疑似超出源端保留窗口，不报 0 家"
                else:
                    reason = "该日期三池全空，判定为非交易日/无数据，不报 0 家"
                result[kind] = _subitem(kind, status="unavailable", reason=reason)
                pool_dates[kind] = None
                continue
            status = "normal_empty" if is_empty else "success"
            if is_empty and kind == "limit_up":
                summary["limitations"] = summary["limitations"] + [
                    "涨停池为 0 在真实交易日极罕见，消费前请复核该日期是否交易日"
                ]
            result[kind] = _subitem(
                kind,
                status=status,
                trade_date=actual_date,
                **summary,
            )

    # 连板分布与最高连板来自涨停池（同池同口径，定义一致）。
    limit_up_result = result.get("limit_up") or {}
    if limit_up_result.get("status") in ("success", "normal_empty") and limit_up_result.get("consecutive"):
        result["consecutive_limit_up"] = _subitem(
            "consecutive_limit_up",
            status=limit_up_result["status"],
            trade_date=limit_up_result.get("trade_date"),
            source=limit_up_result.get("source"),
            **limit_up_result["consecutive"],
        )
    else:
        result["consecutive_limit_up"] = _subitem(
            "consecutive_limit_up",
            status="unavailable",
            reason="涨停池不可用，连板分布随之不可用（连板口径与涨停池绑定，不用其他样本替代）",
        )

    # ── 同日同范围核对 ──────────────────────────────────────────────────
    known_dates = {d for d in pool_dates.values() if d}
    adv = result.get("advance_decline") or {}
    if adv.get("status") in ("success", "partial") and adv.get("trade_date"):
        known_dates.add(adv["trade_date"])
    if len(known_dates) == 1:
        result["actual_trade_date"] = known_dates.pop()
    elif len(known_dates) > 1:
        limitations.append(
            "子项交易日不一致（" + ", ".join(sorted(known_dates)) + "）：各子项保留各自日期，不合并伪装成统一快照"
        )
    result["coverage"] = {
        "sh_sz": "沪深两市（东财池 60/68/00/30 代码 + 新浪 sh/sz 前缀）",
        "bse_pools": (
            "北交所是否进入东财池以当日 bse_count 实测为准（43/83/87/92 代码段）；"
            "bse_count=0 不代表北交所无行情，仅代表该日无该状态个股"
        ),
        "bse_advance_decline": "北交所计入涨/跌/平（新浪 hs_a 含 bj 前缀股票，家数见 valid_quote_by_market）",
        "st_rule": "ST/*ST 含在全部统计内并单独计数（ST 涨跌停幅 5% 由源端规则判定）",
        "new_listing_rule": (
            "上市首日（N 前缀）无涨跌幅限制且常无昨收参考：池内单独披露 new_listing_count；"
            "涨/跌/平快照中无昨收参考者排除出分母（missing_reference_price）"
        ),
    }

    subitem_keys = ("advance_decline", "limit_up", "limit_down", "failed_board", "consecutive_limit_up")
    statuses = [result[k].get("status") for k in subitem_keys]
    ok = [s for s in statuses if s in ("success", "normal_empty", "partial")]
    if statuses and len(ok) == len(statuses):
        result["status"] = "partial" if "partial" in ok else "success"
    elif ok:
        result["status"] = "partial"
    else:
        result["status"] = "unavailable"

    result["limitations"] = limitations
    result["attempts"] = [
        {
            "provider": a.provider,
            "method": a.method,
            "status": a.status,
            "attempted_at": a.attempted_at,
            "duration_ms": a.duration_ms,
            "error_summary": a.error_summary,
            "record_count": a.record_count,
        }
        for a in attempts
    ]
    return result


def build_market_breadth_evidence(result: Mapping[str, Any]) -> dict[str, Any]:
    """Build the validated EvidenceEnvelope dict for one completed breadth result.

    Reshapes facts the request already produced — no provider call, no new
    state.  The public adapter attaches the result as a system-generated
    ``<!-- EVIDENCE: ... -->`` trailer so the execution ledger can capture it.
    """
    attempts: list[ProviderAttempt] = []
    for item in result.get("attempts") or []:
        if not isinstance(item, Mapping):
            continue
        try:
            attempts.append(ProviderAttempt(
                provider=str(item.get("provider") or ""),
                method=item.get("method"),
                status=str(item.get("status") or ""),
                attempted_at=str(item.get("attempted_at") or ""),
                duration_ms=int(item.get("duration_ms") or 0),
                error_summary=item.get("error_summary"),
                record_count=item.get("record_count"),
            ))
        except (TypeError, ValueError):
            continue
    if not attempts:
        # A request fully answered from non-provider branches (for example a
        # weekend date) still needs one explicit attempt for the envelope.
        attempts.append(make_attempt(
            "a_stock",
            ATTEMPT_SKIPPED,
            method="get_market_breadth",
            error_summary="no provider call was made for this request",
        ))

    status = str(result.get("status") or "")
    if status == "success":
        completeness = COMPLETENESS_FULL
    elif status == "partial":
        completeness = COMPLETENESS_PARTIAL
    else:
        completeness = COMPLETENESS_MINIMAL
    observation_date = str(
        result.get("actual_trade_date") or result.get("requested_date") or ""
    ).strip() or None
    envelope = EvidenceEnvelope(
        capability_id="cap_free_market_breadth",
        evidence_category="市场广度",
        evidence_domain="游资与市场热度",
        original_tool="get_market_breadth",
        attempts=attempts,
        observation_date=observation_date,
        data_cutoff_date=observation_date,
        completeness=completeness,
        limitations=[str(line) for line in (result.get("limitations") or [])],
    )
    return envelope.to_dict()


def format_market_breadth(result: dict[str, Any]) -> str:
    """把 ``get_market_breadth`` 结果渲染为紧凑文本（数据面/冒烟核对用）。

    只做确定性投影，不截断为审计桩；分布/Top 有界。
    """
    lines: list[str] = []
    date_label = result.get("actual_trade_date") or result.get("requested_date")
    phase = (result.get("snapshot") or {}).get("phase")
    phase_label = {"intraday": "盘中", "close": "已收盘"}.get(str(phase), "")
    lines.append(f"# 市场广度（{date_label} {phase_label}）")
    adv = result.get("advance_decline") or {}
    if adv.get("status") in ("success", "partial"):
        st_total = sum((adv.get("st_counts") or {}).values())
        lines.append(
            f"涨/跌/平: {adv.get('advancing')}/{adv.get('declining')}/{adv.get('flat')}"
            f"（分母 {adv.get('denominator')}，ST {st_total}，完整性 {adv.get('completeness')}，"
            f"分市场 {adv.get('valid_quote_by_market')}）"
        )
    else:
        lines.append(f"涨/跌/平: 不可用（{adv.get('reason', '未知原因')}）")
    for key, label in (("limit_up", "涨停"), ("limit_down", "跌停"), ("failed_board", "炸板")):
        item = result.get(key) or {}
        if item.get("status") in ("success", "normal_empty", "partial"):
            extra = ""
            if key == "failed_board" and item.get("open_count_total") is not None:
                extra = f"（盘中开板累计 {item['open_count_total']} 次）"
            if key == "limit_down" and item.get("max_consecutive_days") is not None:
                extra = f"（最长连续跌停 {item['max_consecutive_days']} 日）"
            lines.append(f"{label}: {item.get('count')}{extra}")
        else:
            lines.append(f"{label}: 不可用（{item.get('reason', '未知原因')}）")
    cons = result.get("consecutive_limit_up") or {}
    if cons.get("status") in ("success", "normal_empty", "partial"):
        dist = " ".join(f"{k}板:{v}" for k, v in (cons.get("distribution") or {}).items())
        lines.append(f"连板: 最高 {cons.get('max_boards')} 板；分布 {dist}")
        for top in cons.get("top") or []:
            boards = top.get("boards")
            boards_label = f"{boards}板" if boards is not None else "板数未知"
            suffix = f" {top.get('days_boards')}" if top.get("days_boards") else ""
            lines.append(f"  {top.get('code')} {top.get('name')} {boards_label}{suffix}")
    else:
        lines.append(f"连板: 不可用（{cons.get('reason', '未知原因')}）")
    for note in result.get("limitations") or []:
        lines.append(f"限制: {note}")
    return "\n".join(lines)
