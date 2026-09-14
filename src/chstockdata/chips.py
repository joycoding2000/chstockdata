"""CYQ 筹码分布 — 获利比例 / 平均成本 / 成本区间 / 筹码峰（本地推演）。

算法与口径（1:1 移植上游 a-stock-data v3.7.1 §4.6，含其全部实测修正）：

- 东财没有公开 CYQ 接口（``push2/api/qt/stock/cyq/get`` 实测 404），业界通行
  做法是本地推演：历史筹码按换手率衰减，当日成交量按**三角分布**撒入
  ``[low, high]`` 区间（峰值在均价）。
- :func:`chip_distribution` 为纯函数，输入 DataFrame 必需列
  ``date/high/low/close/turn``（``turn`` 为百分数，0.31 表示 0.31%），内部强制
  按时间升序重排——换手衰减是有方向的时序递推，倒序输入会完全错算却不报错。
- **首日分布 = 期初全部流通筹码**（不是从零播种）。从零起步等于假设窗口之前
  没有任何持仓：两个 1% 换手日（价 10 与价 100）会被算成约 50/50，真实情况
  是约 99% 仍在 10 附近。
- 输入价格必须用**前复权**（baostock ``adjustflag="2"``）；用不复权价跨除权日
  会把成本算错。停牌日（``tradestatus == "0"``）不参与换手衰减。
- 这是推演不是实测持仓：券商软件各家衰减系数与分布模型不同，数值不会完全
  一致。看的是**形态与相对变化**（获利盘在增加还是减少、筹码峰在上方还是
  下方），不是绝对值对齐。

依赖：纯算法仅需 numpy/pandas；:func:`get_chip_distribution` 的换手率输入需要
可选依赖 baostock（``pip install "chstockdata[baostock]"``），未安装时抛
``VendorNotConfiguredError``，绝不静默降级成近似口径。
"""

from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone
from typing import Any

import numpy as np
import pandas as pd

from . import a_stock
from .vendor_errors import (
    DeadlineExceeded,
    VendorError,
    VendorNetworkError,
    VendorNoDataError,
    VendorNotConfiguredError,
)

_CST = timezone(timedelta(hours=8))

_BAOSTOCK_HINT = (
    "筹码分布需要 baostock 提供历史换手率（turn），当前环境未安装。"
    '安装：pip install "chstockdata[baostock]"（baostock 不支持北交所）。'
)

# baostock 是全局登录态客户端；进程内串行化 login→query→logout，避免并发
# 交叉登出。与 mootdx 的 _mootdx_call_lock 同类做法，互不相关。
_baostock_lock = threading.Lock()

_REQUIRED_COLUMNS = ("date", "high", "low", "close", "turn")


def _triangular_weights(
    grid: np.ndarray, low: float, high: float, avg: float
) -> np.ndarray:
    """当日筹码在价格网格上的三角分布权重（峰值在均价，面积归一）。"""
    weights = np.zeros_like(grid)
    if not np.isfinite([low, high, avg]).all() or high < low:
        return weights
    if high - low < 1e-9:  # 一字板：全部堆在一个价位
        weights[np.argmin(np.abs(grid - low))] = 1.0
        return weights
    avg = min(max(avg, low), high)  # 均价必须落在当日区间内
    left = (grid >= low) & (grid <= avg)
    right = (grid > avg) & (grid <= high)
    if avg - low > 1e-9:
        weights[left] = (grid[left] - low) / (avg - low)
    else:
        weights[left] = 1.0
    if high - avg > 1e-9:
        weights[right] = (high - grid[right]) / (high - avg)
    else:
        weights[right] = 1.0
    total = weights.sum()
    if total > 0:
        return weights / total
    # 兜底：当日振幅窄于网格步长时可能一个网格点都没落进 [low, high]，权重
    # 全为 0。若就此跳过该日，连它的换手衰减也会一并丢失——低波动标的
    # （银行股等）+ 长窗口下会累积成很大偏差。映射到最近网格点。
    weights[np.argmin(np.abs(grid - avg))] = 1.0
    return weights


def chip_distribution(
    df: pd.DataFrame, grid_size: int = 300, decay: float = 1.0
) -> dict[str, Any]:
    """筹码分布 — 输入需含 ``high/low/close/turn`` 与 ``date``（turn 为百分数）。

    Args:
        df: 日线明细；``turn`` 0.31 表示 0.31%。价格须为前复权口径。
        grid_size: 价格网格点数（>= 10）。
        decay: 换手衰减系数。1.0=按真实换手率换手；同花顺口径常用 1.5~2.0
            加快历史筹码消散。

    Returns:
        ``price / profit_ratio / avg_cost / cost_90 / cost_70 /
        concentration_90 / concentration_70 / peak_price / histogram``。
        硬约束（可作为断言）：``profit_ratio ∈ [0,1]``、``avg_cost`` 落在网格
        区间内、``cost_90`` 包含 ``cost_70``、``concentration_90 >
        concentration_70``。
    """
    if not isinstance(df, pd.DataFrame):
        raise TypeError("chip_distribution 需要 pandas DataFrame 输入")
    if int(grid_size) < 10:
        raise ValueError(f"grid_size 至少为 10，收到 {grid_size}")
    if float(decay) < 0:
        raise ValueError(f"decay 不能为负，收到 {decay}")

    missing = [column for column in _REQUIRED_COLUMNS if column not in df.columns]
    if missing:
        raise ValueError(
            f"chip_distribution 缺少列: {missing}"
            "（date 用于强制时间升序，turn 为换手率百分数）"
        )
    frame = df.dropna(subset=["high", "low", "close", "turn"]).copy()
    frame = frame[frame["high"] > 0]
    if frame.empty:
        raise ValueError(
            "chip_distribution: 有效行数为 0"
            "（检查是否全是停牌日，或字段类型不对）"
        )
    frame = frame.sort_values("date").reset_index(drop=True)

    low_price = float(frame["low"].min())
    high_price = float(frame["high"].max())
    pad = (high_price - low_price) * 0.02 or max(low_price * 0.02, 0.01)
    grid = np.linspace(low_price - pad, high_price + pad, int(grid_size))

    chips: np.ndarray | None = None
    for row in frame.itertuples(index=False):
        turnover = float(row.turn) / 100.0 * float(decay)
        turnover = min(max(turnover, 0.0), 1.0)  # 兜到 [0,1]，防异常值清零
        avg = (float(row.high) + float(row.low) + float(row.close)) / 3.0
        weights = _triangular_weights(grid, float(row.low), float(row.high), avg)
        if weights.sum() <= 0:
            continue
        if chips is None:
            chips = weights.copy()  # 首日分布 = 期初全部流通筹码
            continue
        chips = chips * (1.0 - turnover) + weights * turnover
    if chips is None:
        raise ValueError("chip_distribution: 所有交易日的价格区间都无效，无法构建分布")

    total = chips.sum()
    if total <= 0:
        raise ValueError("chip_distribution: 筹码总量为 0，无法计算指标")
    chips = chips / total

    price = float(frame["close"].iloc[-1])
    cumulative = np.cumsum(chips)

    def price_at(quantile: float) -> float:
        return float(np.interp(quantile, cumulative, grid))

    p05, p15, p85, p95 = (price_at(q) for q in (0.05, 0.15, 0.85, 0.95))
    peak_index = int(np.argmax(chips))
    return {
        "price": price,
        "profit_ratio": float(chips[grid <= price].sum()),
        "avg_cost": float((grid * chips).sum()),
        "cost_90": (p05, p95),
        "cost_70": (p15, p85),
        "concentration_90": (
            float((p95 - p05) / (p95 + p05)) if p95 + p05 else None
        ),
        "concentration_70": (
            float((p85 - p15) / (p85 + p15)) if p85 + p15 else None
        ),
        "peak_price": float(grid[peak_index]),
        "histogram": [
            (float(price_point), float(weight))
            for price_point, weight in zip(grid, chips)
            if weight > 1e-6
        ],
    }


def _bs_code(code: str) -> str:
    """6 位代码 → baostock 格式；北交所等在登录前拦截。"""
    text = str(code).zfill(6)
    if text[:2] in ("60", "68", "90"):
        return f"sh.{text}"
    if text[:2] in ("00", "30", "20"):
        return f"sz.{text}"
    raise ValueError(
        f"baostock 不支持该代码: {text}（北交所 4/8/92/920 号段会被服务端拒绝，"
        f"报 10004011 股票代码未标识 sh 或 sz）。北交所标的请改用其他数据源。"
    )


def _load_baostock():
    """惰性加载可选依赖；缺失时给出可操作的安装提示。"""
    try:
        import baostock  # type: ignore[import-not-found]
    except ImportError as exc:
        raise VendorNotConfiguredError(_BAOSTOCK_HINT) from exc
    return baostock


def _fetch_turnover_frame(
    code: str, start_date: str, end_date: str
) -> tuple[pd.DataFrame, int]:
    """baostock 日线：前复权 OHLC + 换手率 + 交易状态（隔离登录会话）。

    Returns:
        (停牌日已剔除的 DataFrame, 停牌日计数)。
    """
    bs_code = _bs_code(code)
    baostock = _load_baostock()
    with _baostock_lock:
        login = baostock.login()
        if str(getattr(login, "error_code", "")) != "0":
            raise VendorNetworkError(
                f"baostock 登录失败: {getattr(login, 'error_code', '?')} "
                f"{getattr(login, 'error_msg', '')}",
                vendor="baostock",
                method="login",
            )
        try:
            query = baostock.query_history_k_data_plus(
                bs_code,
                "date,open,high,low,close,turn,tradestatus",
                start_date=start_date,
                end_date=end_date,
                frequency="d",
                adjustflag="2",  # 2=前复权，筹码成本必须用复权价
            )
            if str(getattr(query, "error_code", "")) != "0":
                raise VendorNoDataError(
                    f"baostock 查询失败: {getattr(query, 'error_code', '?')} "
                    f"{getattr(query, 'error_msg', '')}",
                    vendor="baostock",
                    method="query_history_k_data_plus",
                )
            records: list[list[str]] = []
            while query.next():
                records.append(query.get_row_data())
            frame = pd.DataFrame(records, columns=query.fields)
        finally:
            baostock.logout()

    if frame.empty:
        raise VendorNoDataError(
            f"baostock 未返回 {bs_code} 在 {start_date} ~ {end_date} 的日线",
            vendor="baostock",
            method="query_history_k_data_plus",
        )
    for column in ("open", "high", "low", "close", "turn"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    # 停牌日不参与换手衰减（先计数再剔除，供输入质量披露）。
    suspended_days = int(frame["tradestatus"].eq("0").sum())
    frame = frame[frame["tradestatus"] == "1"].copy()
    return frame, suspended_days


def get_chip_distribution(
    ticker: str,
    start_date: str,
    end_date: str,
    decay: float = 1.0,
) -> dict[str, Any]:
    """装配 baostock 换手率输入并计算筹码分布。

    窗口长度决定历史筹码的初始状态：**首日分布 = 期初全部流通筹码**，窗口
    越短，越多的"期初筹码"留在窗口起点价位上。必须把窗口累计换手率一并披露
    给消费方，避免把短窗口结果当全历史筹码。
    """
    try:
        code = a_stock._normalize_ticker(ticker)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"非法 ticker: {ticker!r} ({type(exc).__name__})") from exc
    _bs_code(code)  # 不支持的号段（北交所等）在取数前失败闭合
    for label, value in (("start_date", start_date), ("end_date", end_date)):
        datetime.strptime(str(value), "%Y-%m-%d")  # 非法即 ValueError

    try:
        frame, suspended_days = _fetch_turnover_frame(code, start_date, end_date)
    except DeadlineExceeded:
        raise
    except VendorError:
        raise
    except Exception as exc:
        raise VendorNetworkError(
            f"baostock 取数失败：{type(exc).__name__}", vendor="baostock"
        ) from exc

    trading_days = len(frame)
    cumulative_turnover = float(frame["turn"].clip(lower=0, upper=100).sum())

    metrics = chip_distribution(frame, decay=decay)
    return {
        "ticker": code,
        "start_date": start_date,
        "end_date": end_date,
        "trading_days": trading_days,
        "decay": float(decay),
        "metrics": metrics,
        "input_quality": {
            "turn_source": "baostock query_history_k_data_plus（turn，百分数）",
            "price_basis": "qfq（adjustflag=2）",
            "suspended_days_excluded": suspended_days,
            "cumulative_turnover_pct": cumulative_turnover,
            "note": (
                "窗口累计换手不足 100% 时，多数筹码仍是期初持仓，均成本会向"
                "窗口起点偏移；这是本地推演，不是实测持仓分布。"
            ),
        },
        "source": "baostock OHLC+turn → local CYQ reconstruction",
        "observed_at": datetime.now(_CST).isoformat(timespec="seconds"),
        "disclaimer": (
            "筹码分布为按换手率衰减 + 三角分布的本地推演；不同券商软件数值"
            "不一致，仅用于形态与相对变化判断，不构成投资建议。"
        ),
    }


__all__ = ["chip_distribution", "get_chip_distribution"]
