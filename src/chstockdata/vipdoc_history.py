"""Local vipdoc daily-history reader (TDX official after-hours package).

issues/023 / 实施计划（docs/superpowers/plans/2026-09-11-tdx-official-vipdoc-history-layer.md）：
公共 HQ 7709 服务器池会周期性整体失效，历史日线不应继续依赖在线协议。本模块只读
``data.tdx.com.cn`` 官方盘后数据包解压出的本地 ``vipdoc`` 树，为
``get_stock_data`` 的 raw/D 口径提供确定性 base：

- ``.day`` 记录 32B 小端定长：``date``(uint32 YYYYMMDD)、``open/high/low/close``
  (uint32 ×100 元)、``amount``(float32 元)、``volume``(uint32 股)、``reserved``。
- 纯本地、零网络、零副作用；文件缺失返回 ``None``，交给调用方回落现有链。
- ``amount``/``volume`` 的单位口径以 Task 4 与在线源（新浪）实测对齐为准；
  本层不做任何复权，raw 就是不复权。
"""

from __future__ import annotations

import json
import logging
import os
import re
import struct
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from .tdx_bridge import market_for_code

logger = logging.getLogger(__name__)

# 官方盘后日线包（沪深京）。HTTPS 走 EdgeOne JS 反爬挑战，刷新工具默认用 HTTP
# 变体（同源同文件，见 scripts/refresh_vipdoc_history.py）。
VIPDOC_SOURCE_URL = "https://data.tdx.com.cn/vipdoc/hsjday.zip"

MANIFEST_SCHEMA_VERSION = 1

DAY_COLUMNS = ["Date", "Open", "High", "Low", "Close", "Volume", "Amount"]

# record: date(uint32) open high low close(uint32 ×100) amount(float32) volume(uint32) reserved(uint32)
_DAY_RECORD = struct.Struct("<IIIIIfII")
_DAY_RECORD_SIZE = _DAY_RECORD.size  # 32

_CODE_RE = re.compile(r"\d{6}")
_DAY_FILE_RE = re.compile(r"(sh|sz|bj)(\d{6})", re.IGNORECASE)
_MANIFEST_NAME = "manifest.json"
_MARKET_TZ = timezone(timedelta(hours=8))


def _market_today() -> date:
    return datetime.now(_MARKET_TZ).date()


def _empty_frame() -> pd.DataFrame:
    return pd.DataFrame({column: pd.Series(dtype=object) for column in DAY_COLUMNS})


# ── 目录派生 ────────────────────────────────────────────────────────────────


def vipdoc_history_dir() -> str:
    """本地 vipdoc 根目录。显式配置优先；否则派生 ``{data_cache_dir}/vipdoc``。"""
    from .config import get_config

    cfg = get_config()
    explicit = cfg.get("vipdoc_history_dir")
    if explicit:
        return os.path.abspath(os.path.expanduser(str(explicit)))
    cache_dir = cfg.get("data_cache_dir") or os.path.join(
        os.path.expanduser("~"), ".chstockdata", "cache"
    )
    return os.path.join(os.path.abspath(os.path.expanduser(str(cache_dir))), "vipdoc")


# ── 解析器（纯 stdlib struct，确定性） ───────────────────────────────────────


def parse_day_file(path: str | os.PathLike[str]) -> pd.DataFrame:
    """解析单个 ``.day`` 文件为 ``Date/Open/High/Low/Close/Volume/Amount``。

    价格 uint32 ÷100 得元；``amount`` float32 元；``volume`` uint32 股。
    坏日期/截断记录跳过并计数（不可让一个坏文件中断整个分析）。
    """
    rows: list[tuple[Any, ...]] = []
    invalid = 0
    with open(path, "rb") as fh:
        while True:
            chunk = fh.read(_DAY_RECORD_SIZE)
            if not chunk:
                break
            if len(chunk) < _DAY_RECORD_SIZE:
                invalid += 1
                break
            (
                date_raw,
                open_raw,
                high_raw,
                low_raw,
                close_raw,
                amount,
                volume,
                _reserved,
            ) = _DAY_RECORD.unpack(chunk)
            try:
                stamp = datetime.strptime(str(date_raw), "%Y%m%d")
            except ValueError:
                invalid += 1
                continue
            rows.append(
                (
                    stamp,
                    open_raw / 100.0,
                    high_raw / 100.0,
                    low_raw / 100.0,
                    close_raw / 100.0,
                    int(volume),
                    float(amount),
                )
            )

    if invalid:
        logger.warning("vipdoc .day skipped %d invalid records: %s", invalid, path)

    if not rows:
        return _empty_frame()

    frame = pd.DataFrame(rows, columns=DAY_COLUMNS)
    frame["Date"] = pd.to_datetime(frame["Date"])
    frame = (
        frame.drop_duplicates(subset=["Date"], keep="last")
        .sort_values("Date")
        .reset_index(drop=True)
    )
    return frame


def load_vipdoc_daily(
    code: str,
    start_date: str | None = None,
    end_date: str | None = None,
    *,
    root: str | os.PathLike[str] | None = None,
    market: str | None = None,
) -> pd.DataFrame | None:
    """读取本地日线并过滤到 ``[start_date, end_date]``。

    缺省按 sh/sz/bj（920 号段在前）路由；显式 ``market``（sh/sz/bj）用于
    无法按 6 位代码路由的标的——上证指数为 ``sh000001``，按代码会把
    ``000001`` 判给深市 ``sz000001``（平安银行，DEC-P1-27 实施坑）。
    文件缺失返回 ``None``；文件存在但区间内无记录时返回空 frame。代码必须
    为 6 位数字，防止路径穿越。
    """
    normalized = str(code).strip()
    if not _CODE_RE.fullmatch(normalized):
        logger.warning("vipdoc history rejected non 6-digit code: %r", code)
        return None

    base = Path(root) if root is not None else Path(vipdoc_history_dir())
    if market is None:
        resolved_market = market_for_code(normalized).lower()
    else:
        resolved_market = str(market).strip().lower()
        if resolved_market not in {"sh", "sz", "bj"}:
            logger.warning("vipdoc history rejected unknown market: %r", market)
            return None
    path = base / resolved_market / "lday" / f"{resolved_market}{normalized}.day"
    if not path.is_file():
        return None

    frame = parse_day_file(path)
    if frame.empty:
        return frame
    if start_date:
        frame = frame[frame["Date"] >= pd.to_datetime(start_date)]
    if end_date:
        frame = frame[frame["Date"] <= pd.to_datetime(end_date)]
    return frame.reset_index(drop=True)


# ── manifest / 状态 ─────────────────────────────────────────────────────────


def scan_lday_tree(root: str | os.PathLike[str]) -> dict[str, Any]:
    """扫描 ``<root>/{sh,sz,bj}/lday/*.day``，统计记录数（文件大小 ÷ 32）
    与每只证券的最新 bar 日期（读末尾一条记录，不解析全文）。"""
    base = Path(root)
    record_counts: dict[str, int] = {"sh": 0, "sz": 0, "bj": 0}
    max_bar_date: dict[str, str] = {}

    for market in ("sh", "sz", "bj"):
        lday = base / market / "lday"
        if not lday.is_dir():
            continue
        for path in sorted(lday.glob("*.day")):
            match = _DAY_FILE_RE.fullmatch(path.stem)
            if match is None:
                continue
            try:
                size = path.stat().st_size
            except OSError:
                continue
            record_counts[market] += size // _DAY_RECORD_SIZE
            if size < _DAY_RECORD_SIZE:
                continue
            try:
                with open(path, "rb") as fh:
                    # 按 32B 对齐到最后一个完整记录（文件尾若被截断也不能错位读取）。
                    fh.seek((size // _DAY_RECORD_SIZE - 1) * _DAY_RECORD_SIZE)
                    date_raw = _DAY_RECORD.unpack(fh.read(_DAY_RECORD_SIZE))[0]
                stamp = datetime.strptime(str(date_raw), "%Y%m%d")
            except (OSError, ValueError, struct.error):
                continue
            max_bar_date[match.group(2)] = stamp.strftime("%Y-%m-%d")
    return {"record_counts": record_counts, "max_bar_date": max_bar_date}


def _read_manifest(path: Path) -> dict | None:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def write_manifest(root: str | os.PathLike[str], manifest: Mapping[str, Any]) -> None:
    """原子写入 manifest.json（tmp + ``os.replace``，UTF-8）。"""
    base = Path(root)
    base.mkdir(parents=True, exist_ok=True)
    tmp = base / (_MANIFEST_NAME + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(dict(manifest), fh, ensure_ascii=False, sort_keys=True, indent=2)
    os.replace(tmp, base / _MANIFEST_NAME)


def vipdoc_history_status(*, root: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    """manifest + 新鲜度（只读，零网络）。"""
    from .config import get_config

    cfg = get_config()
    enabled = bool(cfg.get("vipdoc_history_enabled", True))
    try:
        max_staleness = float(cfg.get("vipdoc_history_max_staleness_days", 5))
    except (TypeError, ValueError):
        max_staleness = 5.0

    base = Path(root) if root is not None else Path(vipdoc_history_dir())
    manifest = _read_manifest(base / _MANIFEST_NAME)
    latest: str | None = None
    if manifest:
        dates = [
            value
            for value in (manifest.get("max_bar_date") or {}).values()
            if isinstance(value, str)
        ]
        if dates:
            latest = max(dates)

    age_days: int | None = None
    if latest:
        try:
            age_days = max((_market_today() - datetime.strptime(latest, "%Y-%m-%d").date()).days, 0)
        except ValueError:
            age_days = None

    stale = not enabled or age_days is None or age_days > max_staleness
    return {
        "enabled": enabled,
        "dir": str(base),
        "available": base.is_dir(),
        "manifest": manifest,
        "latest_bar_date": latest,
        "age_days": age_days,
        "max_staleness_days": max_staleness,
        "record_counts": (manifest or {}).get("record_counts"),
        "stale": stale,
    }
