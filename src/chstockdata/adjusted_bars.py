"""F1 免费复权行情与周/月线（v0.5.0 独立模块，尚未接入生产消费链路）。

在既有原始日线链路（``a_stock._load_ohlcv_astock``：CSV/PIT 兼容层 →
structured daily-bars engine，两分支均为未复权价）之上叠加：

1. 原始 / QFQ（前复权）/ HFQ（后复权）日线序列；
2. 基于统一日线的周 / 月 OHLCV 聚合；
3. 来源、复权方式、锚定日、因子覆盖与周期完整性元数据。

因子来源与语义（2026-09-07 用真实数据钉死，样本贵州茅台 600519，33 个除权事件）
--------------------------------------------------------------------------------

新浪因子文件 ``https://finance.sina.com.cn/realstock/company/{sh|sz|bj}{code}/hfq.js``
载荷形如::

    var sh600519hfq={"total":33,"data":[{"d":"2026-06-26","f":"8.8825..."},...]}

即按日期**降序**的稀疏事件表：每项 = 除权除息日 + 自该日起生效的**累计后复权
因子**；尾部哨兵 ``("1900-01-01", 1.0)`` 表示最早事件之前因子为 1.0（上市以来
未发生公司行为）。QFQ 无需单独请求：33 个事件点上
``qfq_factor(t) = hfq_factor(t) / hfq_factor(最新事件日)`` 与 qfq.js 文件值
逐一吻合（误差 < 1e-12）。

变换公式（新因子在除权日**当日**生效——当日已按除权除息参考价开盘）::

    HFQ: price_adj(t) = price_raw(t) × hfq_factor(t)
    QFQ: price_adj(t) = price_raw(t) × hfq_factor(t) / hfq_factor(anchor)

其中 anchor = 因子文件最新事件日。等价说法：qfq.js 文件值是**除数**不是乘数。
方向验证（600519，2025-12-19 除权日）：原始收益 −1.47%；腾讯 qfq 真值收益
+0.21%；本公式 +0.21%；若把 qfq 文件值直接当乘数会得到 −3.1%（双倍跳变）。
mootdx 自带 ``factor_reversion`` 对 qfq 正是直接相乘，故本模块不复用它。

锚定与可比性：

- QFQ 在 anchor 及之后与原始价一致（因子=1）；anchor 随每次新除权事件整体
  重定标，不同时点、不同锚的 QFQ 序列**绝对水平不可直接混比**（收益率可比）。
- HFQ 锚定"上市前 = 1.0"（哨兵行），历史值稳定，不随新事件重定标。
- 不同供应商的复权绝对水平不可直接混比（实测腾讯 hfq 与新浪差常数倍），
  收益率/趋势口径一致。

口径红线：

- 成交量 / 成交额**不随价格因子缩放**（两分支 Volume 单位沿用既有日线路径
  原样，跨源绝对值不作横向比较）。
- 估值、参考交易价与 ``_resolve_price`` 的历史收盘价继续使用**原始价**；本
  模块输出仅供趋势 / 技术指标等复权口径分析（见交接文档）。
- 因子缺失、无效或请求失败时显式抛 ``ValueError``，绝不把原始行情标记为
  QFQ/HFQ。
"""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from . import a_stock

logger = logging.getLogger(__name__)

ADJUST_RAW = "raw"
ADJUST_QFQ = "qfq"
ADJUST_HFQ = "hfq"
VALID_ADJUST = (ADJUST_RAW, ADJUST_QFQ, ADJUST_HFQ)

PERIOD_DAILY = "D"
PERIOD_WEEKLY = "W"
PERIOD_MONTHLY = "M"
VALID_PERIODS = (PERIOD_DAILY, PERIOD_WEEKLY, PERIOD_MONTHLY)

_SINA_FACTOR_URL = "https://finance.sina.com.cn/realstock/company/{symbol}/hfq.js"
_FACTOR_URL_TIMEOUT_S = 15

# 因子只在新的公司行为发生后变化；进程内按代码做短 TTL 缓存，避免同一分析
# 内对同一代码反复请求。跨股票/跨运行不共享。
_FACTOR_CACHE_TTL_S = 3600.0
_factor_cache: dict[str, tuple[float, AdjustmentFactors]] = {}
_factor_cache_lock = threading.Lock()

_SENTINEL_DATE = pd.Timestamp("1900-01-01")


def _real_events(factors: AdjustmentFactors) -> pd.DataFrame:
    """剔除哨兵行后的真实除权事件表（哨兵不是除权事件）。"""
    if not factors.has_events:
        return factors.events
    return factors.events[factors.events["Date"] > _SENTINEL_DATE]


class _FactorPayloadError(ValueError):
    """新浪因子载荷结构异常（不重试，直接失败闭合）。"""


@dataclass(frozen=True)
class AdjustmentFactors:
    """一只股票的复权因子事件表（新浪 hfq.js 口径）。

    Attributes:
        code: 6 位代码。
        symbol: 新浪符号（sh600519 / sz000001 / bj...）。
        events: 升序事件表，列 ``Date``（除权除息日）、``hfq``（自该日起
            生效的累计后复权因子）。最早事件之前因子恒为 1.0，由
            :func:`factor_multipliers` 的步进映射保证，不依赖哨兵行存在。
        anchor_date: 最新事件日（QFQ 锚）。全历史无事件时为 None。
        anchor_factor: anchor 日的 hfq 因子（无事件时为 None）。
        fetched_at: epoch 秒。
    """

    code: str
    symbol: str
    events: pd.DataFrame
    anchor_date: pd.Timestamp | None
    anchor_factor: float | None
    fetched_at: float
    source: str = "sina hfq.js"

    @property
    def has_events(self) -> bool:
        return self.events is not None and not self.events.empty


def _parse_factor_payload(text: str) -> list[tuple[str, float]]:
    """解析 ``var shXXXXXXhfq={...}`` 载荷，返回 (date_str, factor) 列表。

    只做结构解析，不做 eval。载荷主体是合法 JSON；正文后可能跟随 /*...*/
    注释，因此从第一个 ``{`` 起做括号配平截取。
    """
    start = text.find("{")
    if start < 0:
        raise _FactorPayloadError("payload has no JSON object")
    depth = 0
    end = -1
    for idx in range(start, len(text)):
        ch = text[idx]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = idx
                break
    if end < 0:
        raise _FactorPayloadError("payload JSON object is unbalanced")
    try:
        payload = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise _FactorPayloadError(f"payload is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict) or "data" not in payload:
        raise _FactorPayloadError("payload missing 'data' field")
    data = payload["data"]
    if not isinstance(data, list):
        raise _FactorPayloadError("payload 'data' is not a list")

    rows: list[tuple[str, float]] = []
    for item in data:
        # 现行格式 {"d": "...", "f": "..."}；兼容旧版 ["date", "factor"] 数组。
        if isinstance(item, dict):
            date_raw = item.get("d")
            factor_raw = item.get("f")
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            date_raw, factor_raw = item[0], item[1]
        else:
            raise _FactorPayloadError(f"unrecognized factor entry: {item!r}")
        if not isinstance(date_raw, str) or not date_raw:
            raise _FactorPayloadError(f"factor entry has invalid date: {item!r}")
        try:
            factor = float(factor_raw)
        except (TypeError, ValueError) as exc:
            raise _FactorPayloadError(
                f"factor entry has non-numeric factor: {item!r}"
            ) from exc
        if not (factor > 0) or factor != factor or factor == float("inf"):
            raise _FactorPayloadError(
                f"factor entry has non-positive/non-finite factor: {item!r}"
            )
        rows.append((date_raw, factor))
    return rows


def fetch_adjust_factors(code: str, *, force: bool = False) -> AdjustmentFactors:
    """拉取一只股票的复权因子事件表（新浪 hfq.js，含进程内 TTL 缓存）。

    失败语义：HTTP 失败、载荷不可解析、因子值非正/非有限 → 抛 ``ValueError``
    （调用方不得把原始行情当成已复权结果继续）。**合法空表**（该股票从未有
    过除权事件）返回 ``has_events=False`` 的事件表，复权退化为恒等变换。
    """
    code = a_stock._normalize_ticker(code)
    symbol = a_stock._sina_stock_code(code)

    if not force:
        with _factor_cache_lock:
            cached = _factor_cache.get(code)
            if cached is not None and time.time() - cached[0] < _FACTOR_CACHE_TTL_S:
                return cached[1]

    url = _SINA_FACTOR_URL.format(symbol=symbol)
    try:
        response = a_stock._source_http_get("sina", url, timeout=_FACTOR_URL_TIMEOUT_S)
        if hasattr(response, "raise_for_status"):
            response.raise_for_status()
        rows = _parse_factor_payload(response.text)
    except _FactorPayloadError:
        raise
    except Exception as exc:  # 网络/HTTP 失败：显式失败，不静默降级
        raise ValueError(f"复权因子获取失败（{code}, {symbol}）：{exc}") from exc

    if rows:
        events = pd.DataFrame(rows, columns=["Date", "hfq"])
        events["Date"] = pd.to_datetime(events["Date"], errors="raise").dt.normalize()
        # 同日多次事件去重（保留最后一条），并按日期升序。
        events = (
            events.drop_duplicates(subset=["Date"], keep="last")
            .sort_values("Date")
            .reset_index(drop=True)
        )
        if events.empty or events["Date"].isna().any():
            raise _FactorPayloadError(f"factor dates unparseable for {code}")
        anchor_date = events["Date"].max()
        anchor_factor = float(events.loc[events["Date"] == anchor_date, "hfq"].item())
    else:
        events = pd.DataFrame(columns=["Date", "hfq"])
        anchor_date = None
        anchor_factor = None

    factors = AdjustmentFactors(
        code=code,
        symbol=symbol,
        events=events,
        anchor_date=anchor_date,
        anchor_factor=anchor_factor,
        fetched_at=time.time(),
    )
    with _factor_cache_lock:
        _factor_cache[code] = (time.time(), factors)
    return factors


def factor_multipliers(
    factors: AdjustmentFactors,
    dates: pd.Series,
    method: str,
) -> pd.Series:
    """把因子事件表映射为逐日乘数（与 ``dates`` 等长、同索引）。

    步进规则：``multiplier(t)`` 取**日期 ≤ t 的最新事件**的因子（除权日当日
    生效）；早于最早事件 → 1.0。``method='qfq'`` 再整体除以 anchor 因子，
    保证 anchor 及之后乘数恒为 1；``method='raw'`` 恒为 1。
    """
    if method not in VALID_ADJUST:
        raise ValueError(f"未知复权方式: {method}（可选 {VALID_ADJUST}）")
    dates = pd.to_datetime(dates, errors="coerce").dt.normalize()
    if dates.isna().any():
        # merge_asof rejects null keys, so an unparsed date would surface as an
        # opaque "Merge keys contain null values on left side" ValueError.
        # Refuse explicitly instead of silently returning unadjusted values for
        # the affected rows.
        raise ValueError(
            "复权乘数输入含无法解析的日期，无法对齐除权事件；拒绝静默产出未复权值"
        )
    multiplier = pd.Series(1.0, index=dates.index)

    if method == ADJUST_RAW or not factors.has_events:
        return multiplier

    events = factors.events.sort_values("Date")
    merged = pd.merge_asof(
        pd.DataFrame({"Date": dates}),
        events.rename(columns={"hfq": "__hfq"}),
        on="Date",
        direction="backward",
    )
    # 早于最早事件（含哨兵缺失的情况）→ 1.0。
    hfq = merged["__hfq"].fillna(1.0).astype(float)
    if method == ADJUST_QFQ:
        if factors.anchor_factor is None or factors.anchor_factor <= 0:
            raise ValueError("QFQ 锚定因子缺失，无法前复权")
        hfq = hfq / factors.anchor_factor
    multiplier = pd.Series(hfq.to_numpy(), index=dates.index, dtype=float)
    return multiplier


def adjust_daily_bars(
    daily_bars: pd.DataFrame,
    factors: AdjustmentFactors,
    method: str,
    *,
    expected_input: str = ADJUST_RAW,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """对**原始**日线应用复权因子，返回 (新 DataFrame, 元数据)。

    纯函数：输入帧不被原地修改。OHLC 乘以逐日乘数后保留完整精度（展示层
    再四舍五入）；Volume / Amount 不缩放。``expected_input`` 必须是
    ``'raw'``——把已复权序列再次送入会二次复权，直接拒绝。
    """
    if method not in VALID_ADJUST:
        raise ValueError(f"未知复权方式: {method}（可选 {VALID_ADJUST}）")
    if expected_input != ADJUST_RAW:
        raise ValueError(
            "复权输入必须是原始（未复权）日线；传入已复权序列会造成二次复权"
        )
    if daily_bars is None or daily_bars.empty:
        raise ValueError("日线数据为空，无法复权")
    required = ["Date", "Open", "High", "Low", "Close", "Volume"]
    missing = [c for c in required if c not in daily_bars.columns]
    if missing:
        raise ValueError(f"日线缺少必要列: {missing}")

    # 归一日期（丢无效日期行）并保留 Amount（若存在），按日期升序。
    frame = a_stock._normalize_ohlcv_dates(daily_bars.copy())
    if frame.empty:
        raise ValueError("日线无有效日期，无法复权")
    keep = required + (["Amount"] if "Amount" in frame.columns else [])
    frame = frame[keep].sort_values("Date").reset_index(drop=True)

    raw_close = pd.to_numeric(frame["Close"], errors="coerce").to_numpy()
    dates = frame["Date"]
    multipliers = factor_multipliers(factors, dates, method)
    for col in ("Open", "High", "Low", "Close"):
        frame[col] = pd.to_numeric(frame[col], errors="coerce") * multipliers

    meta: dict[str, Any] = {
        "adjust": method,
        "factor_source": factors.source if method != ADJUST_RAW else None,
        "factor_symbol": factors.symbol if method != ADJUST_RAW else None,
        "anchor_date": (
            factors.anchor_date.strftime("%Y-%m-%d")
            if method == ADJUST_QFQ and factors.anchor_date is not None
            else None
        ),
        "anchor_basis": (
            "最新除权日起 QFQ 因子=1（随新除权事件整体重定标）"
            if method == ADJUST_QFQ
            else (
                "最早因子记录前按 1.0；来源未证明上市前完整覆盖"
                if method == ADJUST_HFQ else None
            )
        ),
        "factor_events_total": None,
        "factor_first_event": None,
        "factor_last_event": None,
    }
    real = _real_events(factors)
    if method != ADJUST_RAW and not real.empty:
        meta["factor_events_total"] = int(len(real))
        meta["factor_first_event"] = real["Date"].min().strftime("%Y-%m-%d")
        meta["factor_last_event"] = real["Date"].max().strftime("%Y-%m-%d")

    if method != ADJUST_RAW and not real.empty:
        window_events = real[
            (real["Date"] >= dates.min()) & (real["Date"] <= dates.max())
        ]["Date"]
        meta["factor_events_in_window"] = [
            d.strftime("%Y-%m-%d") for d in window_events
        ]
        if dates.min() < real["Date"].min():
            meta.setdefault("limitations", []).append(
                "窗口早于最早可用因子事件，该区间按 1.0 仅表示载荷前无记录；"
                "不证明上市以来完整覆盖"
            )
        if not meta["factor_events_in_window"]:
            meta.setdefault("limitations", []).append(
                "窗口内无除权事件，复权序列与原始价一致"
            )
    else:
        meta["factor_events_in_window"] = []
    meta.setdefault("limitations", [])

    if method == ADJUST_QFQ and factors.anchor_date is not None:
        # QFQ 恒等式：anchor 及之后的行乘数必须为 1，调整后价格与原始一致。
        at_or_after = (dates >= factors.anchor_date).to_numpy()
        if bool(at_or_after.any()):
            adjusted_close = pd.to_numeric(frame["Close"], errors="coerce").to_numpy()
            delta = pd.Series(
                adjusted_close[at_or_after] - raw_close[at_or_after]
            ).abs().max()
            if delta is not None and pd.notna(delta) and delta > 1e-6:
                raise ValueError(
                    f"QFQ 恒等式校验失败：anchor 之后的调整价应等于原始价，"
                    f"最大偏差 {delta}"
                )

    return frame, meta


def resample_ohlcv(
    daily: pd.DataFrame,
    period: str,
    *,
    window_start: pd.Timestamp | str | None = None,
    window_end: pd.Timestamp | str | None = None,
    today: pd.Timestamp | str | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """把（已统一口径的）日线聚合成周 / 月 OHLCV。纯函数，不修改输入。

    规则：open=周期内首个交易日、high=max、low=min、close=周期内最后交易
    日、volume/amount=有效值求和（全缺失 → NaN，不造伪零）；``Date`` = 周期
    内最后交易日（市场图表惯例），``period_start`` = 周期内首个交易日，
    ``trade_days`` = 交易日数。停牌周期没有日线行，自然不产生周期行。

    周期边界：周 = 周一至周日（自然周），月 = 自然月。完整性标记：
    ``complete=False`` 出现在（a）窗口从周期中段开始（首周期缺头）或
    （b）末周期未闭合（窗口截断或周期尚未走完，按自然日判断，保守偏严）。
    """
    if period not in VALID_PERIODS:
        raise ValueError(f"未知周期: {period}（可选 {VALID_PERIODS}）")
    meta: dict[str, Any] = {"period": period, "limitations": []}
    if daily is None or daily.empty:
        meta["limitations"].append("日线为空，无周期聚合结果")
        return pd.DataFrame(), meta
    if period == PERIOD_DAILY:
        meta["row_count"] = int(len(daily))
        return daily.copy(), meta

    required = ["Date", "Open", "High", "Low", "Close", "Volume"]
    missing = [c for c in required if c not in daily.columns]
    if missing:
        raise ValueError(f"日线缺少必要列: {missing}")

    frame = a_stock._normalize_ohlcv_dates(daily.copy())
    frame = frame.sort_values("Date").reset_index(drop=True)
    if frame.empty:
        meta["limitations"].append("日线无有效日期，无周期聚合结果")
        return pd.DataFrame(), meta

    has_amount = "Amount" in frame.columns
    dates = frame["Date"]

    if period == PERIOD_WEEKLY:
        period_start_cal = dates - pd.to_timedelta(dates.dt.dayofweek, unit="D")
    else:
        period_start_cal = dates.dt.to_period("M").dt.to_timestamp()

    work = frame.assign(__period_start=period_start_cal)

    def _sum_min_count(series: pd.Series) -> float:
        values = pd.to_numeric(series, errors="coerce")
        if values.notna().sum() == 0:
            return float("nan")
        return float(values.sum())

    grouped = work.groupby("__period_start", sort=True)
    rows = []
    for period_key, group in grouped:
        group = group.sort_values("Date")
        row: dict[str, Any] = {
            "period_start": period_key,
            "Date": group["Date"].iloc[-1],
            "Open": float(pd.to_numeric(group["Open"], errors="coerce").iloc[0]),
            "High": float(pd.to_numeric(group["High"], errors="coerce").max()),
            "Low": float(pd.to_numeric(group["Low"], errors="coerce").min()),
            "Close": float(pd.to_numeric(group["Close"], errors="coerce").iloc[-1]),
            "Volume": _sum_min_count(group["Volume"]),
            "trade_days": int(len(group)),
        }
        if has_amount:
            row["Amount"] = _sum_min_count(group["Amount"])
        rows.append(row)

    result = pd.DataFrame(rows)
    first_key = result["period_start"].iloc[0]
    last_key = result["period_start"].iloc[-1]
    first_bar_date = frame["Date"].iloc[0]
    last_bar_date = frame["Date"].iloc[-1]
    # 周期键即周期日历起点（周一 / 月首日）；末周期日历终点按同一规则推算。
    if period == PERIOD_WEEKLY:
        last_cal_end = last_key + pd.Timedelta(days=6)
    else:
        last_cal_end = last_key + pd.offsets.MonthEnd(0)

    win_start = (
        pd.to_datetime(window_start).normalize()
        if window_start is not None
        else first_bar_date
    )
    win_end = (
        pd.to_datetime(window_end).normalize()
        if window_end is not None
        else last_bar_date
    )
    today_ts = (
        pd.to_datetime(today).normalize() if today is not None else a_stock._today()
    )

    head_partial = bool(first_key < win_start) or bool(first_key < first_bar_date)
    tail_unclosed = bool(last_cal_end > win_end) or bool(last_cal_end >= today_ts)

    result["complete"] = True
    if head_partial:
        result.loc[0, "complete"] = False
        meta["limitations"].append(
            "首周期从周期中段开始（窗口缺头），覆盖不完整"
        )
    if tail_unclosed:
        result.loc[result.index[-1], "complete"] = False
        meta["limitations"].append(
            "末周期未闭合（窗口截断或周期尚未走完）"
        )
    meta["row_count"] = int(len(result))
    meta["head_partial"] = head_partial
    meta["tail_unclosed"] = tail_unclosed
    meta["window_start"] = win_start.strftime("%Y-%m-%d")
    meta["window_end"] = win_end.strftime("%Y-%m-%d")
    return result, meta


@dataclass
class AdjustedBars:
    """一次复权/周期行情查询的完整结果与元数据。"""

    code: str
    adjust: str
    period: str
    frame: pd.DataFrame
    observed_start: str
    observed_end: str
    daily_source: str
    factor_source: str | None = None
    factor_symbol: str | None = None
    anchor_date: str | None = None
    anchor_basis: str | None = None
    factor_events_total: int | None = None
    factor_events_in_window: list[str] = field(default_factory=list)
    factor_first_event: str | None = None
    factor_last_event: str | None = None
    limitations: list[str] = field(default_factory=list)

    def to_metadata(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "adjust": self.adjust,
            "period": self.period,
            "observed_start": self.observed_start,
            "observed_end": self.observed_end,
            "daily_source": self.daily_source,
            "factor_source": self.factor_source,
            "factor_symbol": self.factor_symbol,
            "anchor_date": self.anchor_date,
            "anchor_basis": self.anchor_basis,
            "factor_events_total": self.factor_events_total,
            "factor_events_in_window": self.factor_events_in_window,
            "factor_first_event": self.factor_first_event,
            "factor_last_event": self.factor_last_event,
            "limitations": list(self.limitations),
        }


def get_adjusted_bars(
    symbol: str,
    start_date: str,
    end_date: str,
    *,
    adjust: str = ADJUST_QFQ,
    period: str = PERIOD_DAILY,
    daily_bars: pd.DataFrame | None = None,
    daily_source: str | None = None,
) -> AdjustedBars:
    """获取原始 / QFQ / HFQ 日线或周 / 月线。

    ``daily_bars`` 可传入调用方已有的**原始**日线（Date/Open/High/Low/Close
    [/Volume 已含]/[Amount] 可选，mootdx 与新浪两分支的帧形状均可）；缺省时
    经 ``a_stock._load_ohlcv_astock`` CSV/PIT 兼容层（底层委托
    ``daily_bars.fetch_daily_bars``，含陈旧覆盖检查）获取，再按
    ``[start_date, end_date]`` 截窗。
    估值 / 参考交易价请继续用原始价链路（``_resolve_price``），不要拿本函数
    的复权序列当真实成交价。
    """
    if adjust not in VALID_ADJUST:
        raise ValueError(f"未知复权方式: {adjust}（可选 {VALID_ADJUST}）")
    if period not in VALID_PERIODS:
        raise ValueError(f"未知周期: {period}（可选 {VALID_PERIODS}）")
    code = a_stock._normalize_ticker(symbol)
    start_ts = pd.to_datetime(start_date)
    end_ts = pd.to_datetime(end_date)
    if start_ts > end_ts:
        raise ValueError(f"起始日期晚于结束日期: {start_date} > {end_date}")

    fetched_here = daily_bars is None
    if fetched_here:
        raw_all = a_stock._load_ohlcv_astock(code, end_date)
        resolved_daily_source = (
            "a_stock._load_ohlcv_astock（CSV/PIT → structured daily-bars engine）"
        )
    else:
        raw_all = daily_bars
        resolved_daily_source = daily_source or "调用方注入（须为原始未复权日线）"
    if raw_all is None or raw_all.empty:
        raise ValueError(f"{code} 日线数据为空，无法生成复权序列")

    raw = a_stock._normalize_ohlcv_dates(raw_all)
    raw = raw[(raw["Date"] >= start_ts) & (raw["Date"] <= end_ts)]
    raw = raw.sort_values("Date").reset_index(drop=True)
    if raw.empty:
        raise ValueError(
            f"{code} 在 {start_date}~{end_date} 无日线数据"
        )

    limitations: list[str] = []
    if fetched_here:
        coverage = a_stock._ohlcv_coverage(raw, end_date)
        if coverage["stale"]:
            raise ValueError(a_stock._stale_ohlcv_message(code, coverage))

    factors = None
    if adjust != ADJUST_RAW:
        factors = fetch_adjust_factors(code)
        frame, adjust_meta = adjust_daily_bars(raw, factors, adjust)
        limitations.extend(adjust_meta.get("limitations", []))
        anchor_date = adjust_meta.get("anchor_date")
        anchor_basis = adjust_meta.get("anchor_basis")
        factor_source = adjust_meta.get("factor_source")
        factor_symbol = adjust_meta.get("factor_symbol")
        events_total = adjust_meta.get("factor_events_total")
        events_window = adjust_meta.get("factor_events_in_window", [])
        first_event = adjust_meta.get("factor_first_event")
        last_event = adjust_meta.get("factor_last_event")
    else:
        frame = raw.copy()
        anchor_date = anchor_basis = None
        factor_source = factor_symbol = None
        events_total = None
        events_window = []
        first_event = last_event = None
        limitations.append("raw=未复权序列，除权跳变未消除")

    if period != PERIOD_DAILY:
        frame, resample_meta = resample_ohlcv(
            frame,
            period,
            window_start=start_ts,
            window_end=end_ts,
        )
        limitations.extend(resample_meta.get("limitations", []))
        observed_end = (
            frame["Date"].max().strftime("%Y-%m-%d")
            if not frame.empty
            else None
        )
        observed_start = (
            frame["period_start"].min().strftime("%Y-%m-%d")
            if not frame.empty
            else None
        )
    else:
        observed_start = frame["Date"].min().strftime("%Y-%m-%d")
        observed_end = frame["Date"].max().strftime("%Y-%m-%d")

    return AdjustedBars(
        code=code,
        adjust=adjust,
        period=period,
        frame=frame,
        observed_start=observed_start,
        observed_end=observed_end,
        daily_source=resolved_daily_source,
        factor_source=factor_source,
        factor_symbol=factor_symbol,
        anchor_date=anchor_date,
        anchor_basis=anchor_basis,
        factor_events_total=events_total,
        factor_events_in_window=events_window,
        factor_first_event=first_event,
        factor_last_event=last_event,
        limitations=limitations,
    )


def format_adjusted_bars_text(result: AdjustedBars, *, round_precision: int = 2) -> str:
    """把结果渲染成带元数据头的 CSV 文本（与 ``get_stock_data`` 头部风格一致）。

    供后续工具接线与冒烟核对使用；元数据头明确复权方式、锚定与限制，防止
    复权价被误读为真实交易价。
    """
    frame = result.frame
    if frame is None or frame.empty:
        return f"# {result.code} 无 {result.period} 周期数据\n"
    columns = [
        c
        for c in (
            "Date",
            "period_start",
            "Open",
            "High",
            "Low",
            "Close",
            "Volume",
            "Amount",
            "trade_days",
            "complete",
        )
        if c in frame.columns
    ]
    out = frame[columns].copy()
    for col in ("Open", "High", "Low", "Close", "Amount"):
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce").round(round_precision)

    header = f"# Adjusted bars for {result.code} ({result.adjust.upper()})"
    header += f", period={result.period}, rows={len(out)}\n"
    header += (
        f"# Observed range: {result.observed_start} ~ {result.observed_end}"
        f" (daily source: {result.daily_source})\n"
    )
    if result.adjust != ADJUST_RAW:
        header += (
            f"# Factors: {result.factor_source} ({result.factor_symbol}), "
            f"events_total={result.factor_events_total}\n"
        )
        if result.adjust == ADJUST_QFQ:
            anchor = result.anchor_date or "无除权事件（复权退化为恒等）"
            header += f"# QFQ anchor: {anchor}（anchor 起 QFQ=原始价）\n"
        if result.factor_events_in_window:
            header += (
                "# Ex-dividend events in window: "
                + ", ".join(result.factor_events_in_window)
                + "\n"
            )
    if result.limitations:
        header += "# Limitations: " + "; ".join(result.limitations) + "\n"
    header += (
        "# 注意：复权价仅供趋势/指标分析，不是可成交的真实价格；"
        "参考交易价请使用原始价链路。\n"
    )
    return header + out.to_csv(index=False)
