"""ETF 期权数据（新浪源）— 合约清单 / T 型报价 / 希腊字母 + IV。

来源与口径（2026-09-14 实测钉死，移植并校对自上游 a-stock-data v3.7.1 §9.1）：

- 合约月份：``stock.finance.sina.com.cn`` 的 ``StockOptionService.getStockName``，
  返回形如 ``["2026-09","2026-09","2026-10","2026-12","2027-03"]``（首条与月份
  列表重复，需**按返回去重**而不是机械丢首个）；转 ``YYMM`` 后按序即近月在前。
- 合约链：``hq.sinajs.cn/list=OP_UP_{underlying}{YYMM}`` / ``OP_DOWN_...``，
  载荷为 ``var hq_str_XXX="CON_OP_10009556,..."``，只取 ``CON_OP_`` 前缀项。
- T 型报价：``CON_OP_{id}``，51 字段（实测逐位核对：v5=持仓量、v7=行权价、
  v37=名称、v41=成交量、v42=成交额）。
- 希腊字母：``CON_SO_{id}``，17 字段；``raw[1:4]`` 是 3 个空串，**必须**
  用 ``[raw[0]] + raw[4:]`` 对齐，否则 Delta/IV 全部错位。

硬性约定：

- 新浪源是 **GBK** 编码且必带 ``Referer: https://stock.finance.sina.com.cn/``
  （否则 403）；
- 字段数不足（T 型 <43、希腊字母 <16）或壳体裁剪失败 → ``VendorNoDataError``，
  绝不返回半截字典让调用方误读；
- 未知 underlying / 非法合约代码 / 月份不在清单内 → ``ValueError``；
- 数值字段解析失败为 ``None``（显式缺失），名称/代码类字段保持字符串；
- ``iv`` 是小数（0.1484 = 14.84%），不做百分比换算，由消费方决定展示口径。
"""

from __future__ import annotations

import re as _re
from datetime import datetime, timedelta, timezone
from typing import Any

from . import a_stock
from .vendor_errors import (
    DeadlineExceeded,
    VendorError,
    VendorNetworkError,
    VendorNoDataError,
)

# A 股市场固定 UTC+8（无夏令时），避免宿主机时区差异。
_CST = timezone(timedelta(hours=8))

_OPTION_UNDERLYINGS: dict[str, str] = {
    "510050": "50ETF",
    "510300": "300ETF",
    "588000": "科创50ETF",
    "510500": "500ETF",
}

_MONTH_URL = (
    "https://stock.finance.sina.com.cn/futures/api/openapi.php/"
    "StockOptionService.getStockName"
)
_HQ_URL = "https://hq.sinajs.cn/list={param}"
_SINA_HEADERS = {
    "User-Agent": a_stock._UA,
    "Referer": "https://stock.finance.sina.com.cn/",
}

_CONTRACT_CODE_RE = _re.compile(r"^\d{8}$")
_CONTRACT_MONTH_RE = _re.compile(r"^\d{4}$")
_CONTRACT_LIST_ITEM_RE = _re.compile(r"^CON_OP_(\d{8})$")
_MONTH_LABEL_RE = _re.compile(r"^(\d{4})-(\d{2})$")

_TQUOTE_MIN_FIELDS = 43
_GREEKS_MIN_FIELDS = 16


def _number(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _fetch_option_text(url: str, *, timeout: float = 10) -> str:
    """One Sina GET decoded as GBK (hq.sinajs.cn serves GBK payloads)."""
    try:
        response = a_stock._source_http_get(
            "sina", url, headers=dict(_SINA_HEADERS), timeout=timeout
        )
    except DeadlineExceeded:
        raise
    except Exception as exc:
        raise VendorNetworkError(
            f"新浪期权接口请求失败：{type(exc).__name__}",
            vendor="sina_options",
            method="http_get",
        ) from exc

    status_code = getattr(response, "status_code", None)
    if status_code is not None and int(status_code) >= 400:
        raise VendorNoDataError(
            f"新浪期权接口返回 HTTP {status_code}",
            vendor="sina_options",
            method="http_get",
            http_status=int(status_code),
        )

    content = getattr(response, "content", None)
    if isinstance(content, bytes):
        return content.decode("gbk", errors="replace")
    return str(getattr(response, "text", ""))


def _fetch_option_months(underlying: str) -> list[str]:
    cate = _OPTION_UNDERLYINGS[underlying]
    try:
        response = a_stock._source_http_get(
            "sina",
            _MONTH_URL,
            params={"exchange": "null", "cate": cate},
            headers=dict(_SINA_HEADERS),
            timeout=10,
        )
    except DeadlineExceeded:
        raise
    except Exception as exc:
        raise VendorNetworkError(
            f"新浪期权月份接口请求失败：{type(exc).__name__}",
            vendor="sina_options",
            method="http_get",
        ) from exc

    status_code = getattr(response, "status_code", None)
    if status_code is not None and int(status_code) >= 400:
        raise VendorNoDataError(
            f"新浪期权月份接口返回 HTTP {status_code}",
            vendor="sina_options",
            method="http_get",
            http_status=int(status_code),
        )
    try:
        payload = response.json()
    except Exception as exc:
        raise VendorNoDataError(
            f"新浪期权月份载荷不是合法 JSON：{type(exc).__name__}",
            vendor="sina_options",
            method="getStockName",
        ) from exc
    months = _parse_months(payload)
    if not months:
        raise VendorNoDataError(
            "新浪期权月份载荷为空（合约清单可能已下线或结构变更）",
            vendor="sina_options",
            method="getStockName",
        )
    return months


def _parse_months(payload: Any) -> list[str]:
    """``{"result": {"data": {"contractMonth": [...]}}}`` → 去重后的 YYMM 列表。"""
    data = ((payload or {}).get("result") or {}).get("data") or {}
    raw_months = data.get("contractMonth") or []
    months: list[str] = []
    for item in raw_months:
        match = _MONTH_LABEL_RE.match(str(item or "").strip())
        if match is None:
            continue
        yymm = match.group(1)[2:4] + match.group(2)
        if yymm not in months:
            months.append(yymm)
    return months


def _parse_hq_list(text: str) -> list[str]:
    """Strip ``var hq_str_XXX="..."`` shell and split the CSV payload."""
    if '"' not in text:
        return []
    return text.split('"')[1].split(",")


def _parse_tquote_fields(fields: list[str]) -> dict[str, Any]:
    if len(fields) < _TQUOTE_MIN_FIELDS:
        raise VendorNoDataError(
            f"新浪 T 型报价字段数不足：期望 >= {_TQUOTE_MIN_FIELDS}，实得 {len(fields)}"
            "（名称部分可能已下线或结构变更）",
            vendor="sina_options",
            method="CON_OP",
        )
    return {
        "bid_vol": _number(fields[0]),
        "bid": _number(fields[1]),
        "last": _number(fields[2]),
        "ask": _number(fields[3]),
        "ask_vol": _number(fields[4]),
        "open_interest": _number(fields[5]),
        "pct": _number(fields[6]),
        "strike": _number(fields[7]),
        "prev_close": _number(fields[8]),
        "open": _number(fields[9]),
        "limit_up": _number(fields[10]),
        "limit_down": _number(fields[11]),
        "name": str(fields[37] or "").strip(),
        "amplitude": _number(fields[38]),
        "high": _number(fields[39]),
        "low": _number(fields[40]),
        "volume": _number(fields[41]),
        "amount": _number(fields[42]),
        "source": "sina CON_OP",
    }


def _parse_greeks_fields(raw: list[str]) -> dict[str, Any]:
    if len(raw) < _GREEKS_MIN_FIELDS:
        raise VendorNoDataError(
            f"新浪希腊字母字段数不足：期望 >= {_GREEKS_MIN_FIELDS}，实得 {len(raw)}"
            "（名称部分可能已下线或结构变更）",
            vendor="sina_options",
            method="CON_SO",
        )
    # raw[1:4] 是 3 个空串，跳过否则字段整体错位。
    fields = [raw[0], *raw[4:]]
    return {
        "name": str(fields[0] or "").strip(),
        "volume": _number(fields[1]),
        "delta": _number(fields[2]),
        "gamma": _number(fields[3]),
        "theta": _number(fields[4]),
        "vega": _number(fields[5]),
        "iv": _number(fields[6]),
        "high": _number(fields[7]),
        "low": _number(fields[8]),
        "trade_code": str(fields[9] or "").strip(),
        "strike": _number(fields[10]),
        "last": _number(fields[11]),
        "theory": _number(fields[12]),
        "source": "sina CON_SO",
    }


def _validate_underlying(underlying: str) -> str:
    code = str(underlying or "").strip()
    if code not in _OPTION_UNDERLYINGS:
        raise ValueError(
            f"不支持的期权标的 '{underlying}'：可选 "
            f"{sorted(_OPTION_UNDERLYINGS)}（分别对应 "
            f"{', '.join(_OPTION_UNDERLYINGS.values())}）"
        )
    return code


def _validate_contract_code(code: str) -> str:
    text = str(code or "").strip()
    if not _CONTRACT_CODE_RE.match(text):
        raise ValueError(
            f"无效的期权合约代码 '{code}'：应为 8 位数字（如 '10010974'，"
            f"不带 CON_OP_ 前缀）"
        )
    return text


def list_etf_option_contracts(
    underlying: str = "510050", call: bool = True
) -> dict[str, list[str]]:
    """ETF 期权合约清单，按月份分组（YYMM → 8 位合约代码列表）。

    Args:
        underlying: 510050 / 510300 / 588000 / 510500。
        call: True 认购 / False 认沽。

    Returns:
        ``{"2609": ["10010974", ...], ...}``；dict 顺序即近月在前。
    """
    code = _validate_underlying(underlying)
    months = _fetch_option_months(code)
    flag = "OP_UP_" if call else "OP_DOWN_"
    result: dict[str, list[str]] = {}
    for month in months:
        text = _fetch_option_text(_HQ_URL.format(param=f"{flag}{code}{month}"))
        contracts = [
            match.group(1)
            for item in _parse_hq_list(text)
            if (match := _CONTRACT_LIST_ITEM_RE.match(str(item or "").strip()))
        ]
        if contracts:
            result[month] = contracts
    if not result:
        raise VendorNoDataError(
            f"新浪未返回 {code} 任何月份的{'认购' if call else '认沽'}合约",
            vendor="sina_options",
            method="OP_UP" if call else "OP_DOWN",
        )
    return result


def get_etf_option_tquote(code: str) -> dict[str, Any]:
    """期权 T 型报价（买卖五档首档 / 持仓量 / 行权价 / 最新价 / 成交量额）。"""
    contract = _validate_contract_code(code)
    text = _fetch_option_text(_HQ_URL.format(param=f"CON_OP_{contract}"))
    fields = _parse_hq_list(text)
    result = _parse_tquote_fields(fields)
    result["code"] = contract
    result["observed_at"] = datetime.now(_CST).isoformat(timespec="seconds")
    return result


def get_etf_option_greeks(code: str) -> dict[str, Any]:
    """期权希腊字母 + 隐含波动率（交易所预算值，无需本地 BSM）。"""
    contract = _validate_contract_code(code)
    text = _fetch_option_text(_HQ_URL.format(param=f"CON_SO_{contract}"))
    fields = _parse_hq_list(text)
    result = _parse_greeks_fields(fields)
    result["code"] = contract
    result["observed_at"] = datetime.now(_CST).isoformat(timespec="seconds")
    return result


def get_etf_option_chain(
    underlying: str = "510050", month: str | None = None
) -> dict[str, Any]:
    """单月认购+认沽全链：每份合约合并 T 型报价与希腊字母。

    单合约失败不拖垮整链：失败项进 ``failed_contracts`` 并在返回中披露；
    月份清单本身获取失败或指定月份不存在时抛错。
    """
    code = _validate_underlying(underlying)
    calls = list_etf_option_contracts(code, call=True)
    puts = list_etf_option_contracts(code, call=False)

    available = sorted({*calls, *puts})
    if month is None:
        selected = available[0] if available else None
    else:
        text = str(month).strip()
        if not _CONTRACT_MONTH_RE.match(text):
            raise ValueError(
                f"无效的月份 '{month}'：应为 4 位 YYMM（如 '2609'）"
            )
        selected = text if text in available else None
        if selected is None:
            raise ValueError(
                f"标的 {code} 无 {text} 月合约；可选月份 {available}"
            )
    if selected is None:
        raise VendorNoDataError(
            f"标的 {code} 无可用期权月份", vendor="sina_options", method="chain"
        )

    rows: list[dict[str, Any]] = []
    failed: list[dict[str, str]] = []
    for direction, contracts in (
        ("call", calls.get(selected, [])),
        ("put", puts.get(selected, [])),
    ):
        for contract in contracts:
            try:
                row: dict[str, Any] = {
                    "direction": direction,
                    "code": contract,
                    **get_etf_option_tquote(contract),
                }
                row["greeks"] = get_etf_option_greeks(contract)
                rows.append(row)
            except VendorError as exc:
                failed.append(
                    {
                        "direction": direction,
                        "code": contract,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )

    if not rows and failed:
        raise VendorNoDataError(
            f"标的 {code} {selected} 月全部合约报价失败（{len(failed)} 个）",
            vendor="sina_options",
            method="chain",
        )
    return {
        "underlying": code,
        "underlying_name": _OPTION_UNDERLYINGS[code],
        "month": selected,
        "call_contracts": calls.get(selected, []),
        "put_contracts": puts.get(selected, []),
        "rows": rows,
        "failed_contracts": failed,
        "observed_at": datetime.now(_CST).isoformat(timespec="seconds"),
        "source": "sina StockOptionService + hq.sinajs.cn",
        "note": (
            "T 型报价/希腊字母/IV 均为新浪转发的交易所预算值；iv 为小数"
            "（0.1484 = 14.84%）。期权行情仅供参考，不构成投资建议。"
        ),
    }


__all__ = [
    "get_etf_option_chain",
    "get_etf_option_greeks",
    "get_etf_option_tquote",
    "list_etf_option_contracts",
]
