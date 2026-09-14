"""独立的北向公开数据获取与口径标准化。

本模块刻意不注册 vendor、工具计划或数据面。调用方显式抓取，再决定是否写入
``NorthboundStore``；存储查询永不触网。
"""

from __future__ import annotations

from dataclasses import dataclass, replace as _replace
from datetime import date, datetime, timedelta, timezone
import json
import math
import re
from typing import Any, Callable, Literal

import requests


SSE_NORTHBOUND_TURNOVER_URL = "https://query.sse.com.cn/ggt/getQuatationInfo.do"
SZSE_NORTHBOUND_TURNOVER_URL = "https://www.szse.cn/api/report/ShowReport/data"
SZSE_SGT_CATALOG_ID = "SGT_SGTJYRB"
HKEX_HOLDINGS_URLS = {
    "northbound_sh": "https://www3.hkexnews.hk/sdw/search/mutualmarket.aspx?t=sh",
    "northbound_sz": "https://www3.hkexnews.hk/sdw/search/mutualmarket.aspx?t=sz",
}
_VALID_METRICS = {
    "turnover_total": "CNY_100M",
    "turnover_trade_count": "COUNT_10000_TRADES",
    "turnover_etf": "CNY_100M",
    "holding_shares": "SHARES",
    "holding_percent": "PERCENT",
}
_VALID_SCOPES = frozenset(HKEX_HOLDINGS_URLS)
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_SECURITY_ID = re.compile(r"^\d{6}$")


def _require_date(value: str, field: str) -> str:
    if not isinstance(value, str) or not _ISO_DATE.fullmatch(value):
        raise ValueError(f"{field} must be YYYY-MM-DD")
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field} must be a calendar date") from exc
    return value


def _require_observed_at(value: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("observed_at is required")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("observed_at must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError("observed_at must include timezone")
    return value


def _observed_at(value: str | None) -> str:
    return _require_observed_at(value or datetime.now(timezone.utc).isoformat())


@dataclass(frozen=True)
class NorthboundRecord:
    """One atomic observable, never an inferred net-flow or trading intent."""

    metric: str
    value: int | float
    unit: str
    market_scope: str
    as_of_date: str
    observed_at: str
    source_id: str
    source_url: str
    source_fields: dict[str, str]
    coverage: str
    disclosure_time_precision: Literal["date", "unknown"]
    security_id: str | None = None
    security_name: str | None = None
    disclosed_at: str | None = None
    limitations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.metric not in _VALID_METRICS:
            raise ValueError(f"unsupported metric: {self.metric}")
        if self.unit != _VALID_METRICS[self.metric]:
            raise ValueError(f"unit does not match metric {self.metric}")
        if self.market_scope not in _VALID_SCOPES:
            raise ValueError(f"unsupported market_scope: {self.market_scope}")
        _require_date(self.as_of_date, "as_of_date")
        _require_observed_at(self.observed_at)
        if self.disclosed_at is not None:
            _require_observed_at(self.disclosed_at)
        if self.disclosure_time_precision not in {"date", "unknown"}:
            raise ValueError("unsupported disclosure_time_precision")
        if not isinstance(self.value, (int, float)) or isinstance(self.value, bool) or not math.isfinite(float(self.value)):
            raise ValueError("value must be finite")
        if not self.source_id or not self.source_url.startswith("https://"):
            raise ValueError("source_id and HTTPS source_url are required")
        if not isinstance(self.source_fields, dict) or not self.source_fields:
            raise ValueError("source_fields are required")
        if not self.coverage:
            raise ValueError("coverage is required")
        if self.metric.startswith("holding_"):
            if not self.security_id or not _SECURITY_ID.fullmatch(self.security_id):
                raise ValueError("holding records require a six-digit security_id")
        elif self.security_id is not None:
            raise ValueError("turnover records cannot carry security_id")

    def replace(self, **changes: Any) -> "NorthboundRecord":
        return _replace(self, **changes)

    def business_key(self) -> str:
        return "|".join(
            (self.source_id, self.metric, self.market_scope, self.as_of_date, self.security_id or "")
        )

    def to_dict(self) -> dict[str, Any]:
        result = {
            "metric": self.metric,
            "value": self.value,
            "unit": self.unit,
            "market_scope": self.market_scope,
            "as_of_date": self.as_of_date,
            "observed_at": self.observed_at,
            "source_id": self.source_id,
            "source_url": self.source_url,
            "source_fields": self.source_fields,
            "coverage": self.coverage,
            "disclosure_time_precision": self.disclosure_time_precision,
            "security_id": self.security_id,
            "security_name": self.security_name,
            "disclosed_at": self.disclosed_at,
            "limitations": list(self.limitations),
        }
        return result

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "NorthboundRecord":
        if not isinstance(value, dict):
            raise ValueError("record must be an object")
        accepted = {
            "metric", "value", "unit", "market_scope", "as_of_date", "observed_at",
            "source_id", "source_url", "source_fields", "coverage", "disclosure_time_precision",
            "security_id", "security_name", "disclosed_at", "limitations",
        }
        if set(value) != accepted:
            raise ValueError("record fields are invalid")
        limitations = value["limitations"]
        if not isinstance(limitations, list) or not all(isinstance(item, str) for item in limitations):
            raise ValueError("limitations must be a text list")
        return cls(**{**value, "limitations": tuple(limitations)})


@dataclass(frozen=True)
class NorthboundFetchResult:
    status: Literal["success", "normal_empty", "partial", "failed"]
    records: list[NorthboundRecord]
    errors: list[dict[str, str]]
    requested_start: str | None
    requested_end: str | None
    complete: bool


def northbound_availability_catalog() -> list[dict[str, str]]:
    """Fixed, user-visible availability statement checked against 2026-09-09 sources."""

    return [
        {
            "metric": "turnover_total", "source": "SSE/SZSE public northbound endpoints",
            "frequency": "trading_day", "market_scope": "northbound_sh,northbound_sz",
            "latest_date": "source-dependent", "backfill": "bounded_explicit_dates",
            "availability": "available", "definition": "day-end total turnover, not net inflow",
        },
        {
            "metric": "holding_shares", "source": "HKEX CCASS Northbound Shareholding Search",
            "frequency": "quarterly", "market_scope": "northbound_sh,northbound_sz",
            "latest_date": "source-dependent", "backfill": "bounded_12_months",
            "availability": "available", "definition": "CCASS participants aggregate holding snapshot",
        },
        {
            "metric": "net_buy", "source": "2024 disclosure adjustment",
            "frequency": "not_applicable", "market_scope": "northbound_sh,northbound_sz",
            "latest_date": "not_disclosed", "backfill": "no", "availability": "unavailable",
            "definition": "not reconstructed from turnover, quota or holding deltas",
        },
        {
            "metric": "quota_balance", "source": "2024 disclosure adjustment",
            "frequency": "threshold_only", "market_scope": "northbound_sh,northbound_sz",
            "latest_date": "not_disclosed", "backfill": "no", "availability": "unavailable",
            "definition": "only shown publicly below threshold; not persisted as a time series",
        },
    ]


def _default_http_get(source_id: str, url: str, **kwargs: Any):
    # Reuse the existing bounded GET/source-context boundary without changing it.
    from .a_stock import _source_http_get

    return _source_http_get(source_id, url, **kwargs)


def _jsonp_object(text: str) -> dict[str, Any]:
    match = re.fullmatch(r"\s*[\w.]+\((.*)\)\s*;?\s*", text, re.DOTALL)
    if not match:
        raise ValueError("response is not JSONP")
    value = json.loads(match.group(1))
    if not isinstance(value, dict):
        raise ValueError("JSONP payload must be an object")
    return value


def _turnover_records(payload: dict[str, Any], observed_at: str) -> list[NorthboundRecord]:
    rows = payload.get("result")
    if not isinstance(rows, list):
        raise ValueError("result must be a list")
    if not rows:
        return []
    # Closed-market days: SSE answers with result: [null] (live-verified on
    # 2026-09-12, a Saturday) rather than [].  That is a confirmed no-trade
    # day, not a response-structure failure; only malformed non-null rows
    # fail closed.
    if all(row is None for row in rows):
        return []
    if len(rows) != 1 or not isinstance(rows[0], dict):
        raise ValueError("expected one turnover row")
    row = rows[0]
    raw_date = str(row.get("TRADE_DATE", ""))
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw_date):
        raise ValueError("TRADE_DATE missing")
    base = {
        "market_scope": "northbound_sh", "as_of_date": raw_date, "observed_at": observed_at,
        "source_id": "sse_hgt_turnover", "source_url": SSE_NORTHBOUND_TURNOVER_URL,
        "coverage": "shanghai_connect_northbound_all_reported_securities",
        "disclosure_time_precision": "date", "limitations": (
            "成交总额不等于净买入、资金净流入或买卖额。",
            "本来源只代表沪股通；深股通日终成交由深交所同口径官方来源另行接入。",
        ),
    }
    fields = (
        ("turnover_total", "TOTAL_AMOUNT", "CNY_100M"),
        ("turnover_trade_count", "TOTAL_VOLUME", "COUNT_10000_TRADES"),
        ("turnover_etf", "ETF_TOTAL_AMOUNT", "CNY_100M"),
    )
    records = []
    for metric, field, unit in fields:
        try:
            numeric = float(str(row[field]).replace(",", ""))
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"{field} missing or invalid") from exc
        records.append(NorthboundRecord(
            metric=metric, value=numeric, unit=unit,
            source_fields={field: field}, **base,
        ))
    return records


def fetch_sse_northbound_turnover(
    start_date: str,
    end_date: str,
    *,
    http_get: Callable[..., Any] | None = None,
    observed_at: str | None = None,
) -> NorthboundFetchResult:
    """Fetch at most 31 explicit Shanghai Connect dates.

    Weekends are skipped without a request.  Exchange holidays are not
    guessed offline: the source answers them with a null row, which counts
    as a confirmed no-trade day rather than a structure error.
    """

    start_date = _require_date(start_date, "start_date")
    end_date = _require_date(end_date, "end_date")
    start, end = date.fromisoformat(start_date), date.fromisoformat(end_date)
    if end < start or (end - start).days > 30:
        raise ValueError("date range must be between one and 31 calendar days")
    observed = _observed_at(observed_at)
    get = http_get or _default_http_get
    records: list[NorthboundRecord] = []
    errors: list[dict[str, str]] = []
    empty_count = 0
    skipped_weekend_count = 0
    current = start
    while current <= end:
        if current.weekday() >= 5:
            skipped_weekend_count += 1
            current += timedelta(days=1)
            continue
        requested = current.isoformat()
        try:
            response = get(
                "sse", SSE_NORTHBOUND_TURNOVER_URL,
                params={"jsonCallBack": "northboundCallback", "tradeDate": current.strftime("%Y%m%d")},
                headers={"Referer": "https://www.sse.com.cn/services/hkexsc/hgtscsj/hgtcjgk/"},
                timeout=15,
            )
            if hasattr(response, "raise_for_status"):
                response.raise_for_status()
            parsed = _turnover_records(_jsonp_object(str(response.text)), observed)
            if not parsed:
                empty_count += 1
            elif any(record.as_of_date != requested for record in parsed):
                raise ValueError("source trade date mismatch")
            else:
                records.extend(parsed)
        except (OSError, requests.RequestException) as exc:
            errors.append({"date": requested, "kind": "network_failure", "detail": type(exc).__name__})
        except Exception as exc:
            errors.append({"date": requested, "kind": "structure_error", "detail": type(exc).__name__})
        current += timedelta(days=1)
    requested_days = (end - start).days + 1 - skipped_weekend_count
    if errors and records:
        status: Literal["partial", "failed", "normal_empty", "success"] = "partial"
    elif errors:
        status = "failed"
    elif not records and (empty_count or requested_days == 0):
        status = "normal_empty"
    else:
        status = "success"
    return NorthboundFetchResult(status, records, errors, start_date, end_date, status in {"success", "normal_empty"})


# SZSE labels are part of the payload contract: a renamed or added label is
# provider drift and must fail closed instead of silently dropping a metric.
_SZSE_TURNOVER_LABELS = (
    ("当日交易总额（亿元人民币）", "turnover_total", "CNY_100M"),
    ("当日交易总笔数（万笔）", "turnover_trade_count", "COUNT_10000_TRADES"),
    ("当日ETF交易总额（亿元人民币）", "turnover_etf", "CNY_100M"),
)


def _szse_turnover_records(
    payload: Any, requested_date: str, observed_at: str
) -> list[NorthboundRecord]:
    """Parse one SZSE 深股通交易日报 (SGT_SGTJYRB) vertical report.

    The verified 2026-09-10 envelope is a single-element array whose
    ``metadata.subname`` echoes the queried trade date and whose ``data``
    holds exactly the three label/value rows above.
    """
    if not isinstance(payload, list) or len(payload) != 1 or not isinstance(payload[0], dict):
        raise ValueError("expected a single-element SZSE report array")
    report = payload[0]
    metadata = report.get("metadata")
    if not isinstance(metadata, dict) or metadata.get("tabkey") != "tab1":
        raise ValueError("SZSE report metadata missing tab1")
    if report.get("error"):
        raise ValueError(f"SZSE report error: {report['error']}")
    rows = report.get("data")
    if not isinstance(rows, list):
        raise ValueError("SZSE report data must be a list")
    if not rows:
        return []
    as_of_date = str(metadata.get("subname", ""))
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", as_of_date):
        raise ValueError("SZSE report subname is not a trade date")
    if as_of_date != requested_date:
        raise ValueError("source trade date mismatch")
    labelled: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict) or "label" not in row or "total" not in row:
            raise ValueError("SZSE report row must carry label/total")
        label = str(row["label"]).strip()
        if label in labelled:
            raise ValueError(f"duplicate SZSE report label: {label}")
        labelled[label] = str(row["total"])
    base = {
        "market_scope": "northbound_sz", "as_of_date": as_of_date, "observed_at": observed_at,
        "source_id": "szse_sgt_turnover", "source_url": SZSE_NORTHBOUND_TURNOVER_URL,
        "coverage": "shenzhen_connect_northbound_all_reported_securities",
        "disclosure_time_precision": "date", "limitations": (
            "成交总额不等于净买入、资金净流入或买卖额。",
            "本来源只代表深股通；披露为深交所日终口径，非实时数据。",
        ),
    }
    records = []
    for label, metric, unit in _SZSE_TURNOVER_LABELS:
        raw = labelled.pop(label, None)
        if raw is None:
            raise ValueError(f"SZSE report missing label {label}")
        try:
            numeric = float(raw.replace(",", ""))
        except ValueError as exc:
            raise ValueError(f"SZSE value invalid for {label}") from exc
        records.append(NorthboundRecord(
            metric=metric, value=numeric, unit=unit,
            source_fields={"label": label}, **base,
        ))
    if labelled:
        raise ValueError(f"unexpected SZSE report labels: {sorted(labelled)}")
    return records


def fetch_szse_northbound_turnover(
    start_date: str,
    end_date: str,
    *,
    http_get: Callable[..., Any] | None = None,
    observed_at: str | None = None,
) -> NorthboundFetchResult:
    """Fetch at most 31 explicit Shenzhen Connect dates.

    Weekends are skipped without a request, mirroring the SSE fetch path.
    """

    start_date = _require_date(start_date, "start_date")
    end_date = _require_date(end_date, "end_date")
    start, end = date.fromisoformat(start_date), date.fromisoformat(end_date)
    if end < start or (end - start).days > 30:
        raise ValueError("date range must be between one and 31 calendar days")
    observed = _observed_at(observed_at)
    get = http_get or _default_http_get
    records: list[NorthboundRecord] = []
    errors: list[dict[str, str]] = []
    empty_count = 0
    skipped_weekend_count = 0
    current = start
    while current <= end:
        if current.weekday() >= 5:
            skipped_weekend_count += 1
            current += timedelta(days=1)
            continue
        requested = current.isoformat()
        try:
            response = get(
                "szse", SZSE_NORTHBOUND_TURNOVER_URL,
                params={
                    "SHOWTYPE": "JSON", "CATALOGID": SZSE_SGT_CATALOG_ID,
                    "TABKEY": "tab1", "txtDate": requested, "random": "0.35",
                },
                headers={
                    "User-Agent": "Mozilla/5.0",
                    "Referer": "https://www.szse.cn/szhk/szhktradeinfo/szdaily/index.html",
                },
                timeout=15,
            )
            if hasattr(response, "raise_for_status"):
                response.raise_for_status()
            parsed = _szse_turnover_records(
                json.loads(str(response.text)), requested, observed
            )
            if not parsed:
                empty_count += 1
            else:
                records.extend(parsed)
        except (OSError, requests.RequestException) as exc:
            errors.append({"date": requested, "kind": "network_failure", "detail": type(exc).__name__})
        except Exception as exc:
            errors.append({"date": requested, "kind": "structure_error", "detail": type(exc).__name__})
        current += timedelta(days=1)
    requested_days = (end - start).days + 1 - skipped_weekend_count
    if errors and records:
        status = "partial"
    elif errors:
        status = "failed"
    elif not records and (empty_count or requested_days == 0):
        status = "normal_empty"
    else:
        status = "success"
    return NorthboundFetchResult(status, records, errors, start_date, end_date, status in {"success", "normal_empty"})


def _hidden_value(html: str, name: str) -> str:
    match = re.search(rf'name=["\']{re.escape(name)}["\'][^>]*value=["\']([^"\']+)', html, re.I)
    if not match:
        raise ValueError(f"missing form field {name}")
    return match.group(1)


def _holding_records(html: str, scope: str, observed_at: str) -> tuple[str, list[NorthboundRecord]]:
    date_match = re.search(r"Shareholding\s+Date\s*:\s*(\d{4}/\d{2}/\d{2})", html, re.I)
    if not date_match:
        raise ValueError("missing shareholding date")
    as_of_date = date_match.group(1).replace("/", "-")
    _require_date(as_of_date, "source shareholding date")
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.I | re.S)
    records: list[NorthboundRecord] = []
    exchange = "sse" if scope == "northbound_sh" else "szse"
    coverage = f"ccass_participants_aggregate_{exchange}_a_shares"
    for row in rows:
        plain = re.sub(r"<[^>]+>", " ", row)
        code = re.search(r"A\s*#\s*(\d{6})", plain)
        shares = re.search(r"Shareholding\s+in\s+CCASS\s*:\s*([\d,]+)", plain, re.I)
        percent = re.search(r"(?:CCASS\s*:\s*[\d,]+\s*</?[^>]*>?.*?|CCASS\s*:\s*[\d,]+\s+)(\d+(?:\.\d+)?)\s*%", plain, re.I | re.S)
        if not (code and shares):
            continue
        name_match = re.search(r"Name\s*:\s*(.*?)\s*\(\s*A\s*#", plain, re.I | re.S)
        name = re.sub(r"\s+", " ", name_match.group(1)).strip() if name_match else None
        base = {
            "market_scope": scope, "as_of_date": as_of_date, "observed_at": observed_at,
            "source_id": "hkex_ccass_northbound_holdings", "source_url": HKEX_HOLDINGS_URLS[scope],
            "coverage": coverage, "disclosure_time_precision": "unknown", "security_id": code.group(1),
            "security_name": name, "limitations": (
                "季度末持股快照不等于当日可见信息；页面不提供精确披露时分。",
                "持股数量变化可能受公司行为或统计调整影响，不能推断交易资金或意图。",
            ),
        }
        records.append(NorthboundRecord(
            metric="holding_shares", value=int(shares.group(1).replace(",", "")), unit="SHARES",
            source_fields={"Shareholding in CCASS": "aggregate shares"}, **base,
        ))
        # HKEX labels percentage as reference-only; include only if an unambiguous percentage follows the row.
        tail = plain[shares.end():]
        value = re.search(r"(\d+(?:\.\d+)?)\s*%", tail)
        if value:
            records.append(NorthboundRecord(
                metric="holding_percent", value=float(value.group(1)), unit="PERCENT",
                source_fields={"% listed and traded shares": "reference percentage"}, **base,
            ))
    if not records:
        raise ValueError("no holding rows in source response")
    return as_of_date, records


def _default_hkex_transport() -> tuple[Callable[..., Any], Callable[..., Any]]:
    """Keep the ASP.NET form's cookies while reusing the source-context boundary.

    The existing shared helper supports GET only.  This source requires a GET+POST
    form round trip, so it is deliberately a single attempt rather than a copied
    retry policy; common POST retry/governance belongs to the later shared wiring.
    """

    from .a_stock import _source_http_get, _source_http_post

    session = requests.Session()
    session.trust_env = False

    def get(source_id: str, url: str, **kwargs: Any):
        return _source_http_get(source_id, url, session=session, **kwargs)

    def post(url: str, data: dict[str, str], headers: dict[str, str]):
        return _source_http_post(
            "hkex", url, data=data, headers=headers, timeout=20, session=session
        )

    return get, post


def fetch_hkex_quarterly_holdings(
    market_scope: str,
    *,
    shareholding_date: str | None = None,
    http_get: Callable[..., Any] | None = None,
    http_post: Callable[..., Any] | None = None,
    observed_at: str | None = None,
) -> NorthboundFetchResult:
    """Fetch one HKEX Northbound CCASS snapshot, retaining its quarterly limitation."""

    if market_scope not in _VALID_SCOPES:
        raise ValueError("market_scope must be northbound_sh or northbound_sz")
    requested = _require_date(shareholding_date, "shareholding_date") if shareholding_date else None
    observed = _observed_at(observed_at)
    url = HKEX_HOLDINGS_URLS[market_scope]
    if http_get is None and http_post is None:
        get, post = _default_hkex_transport()
    else:
        get = http_get or _default_http_get
        post = http_post or _default_hkex_transport()[1]
    headers = {"User-Agent": "Mozilla/5.0", "Referer": url}
    try:
        landing = get("hkex", url, headers=headers, timeout=20)
        if hasattr(landing, "raise_for_status"):
            landing.raise_for_status()
        html = str(landing.text)
        if requested:
            form = {
                "__VIEWSTATE": _hidden_value(html, "__VIEWSTATE"),
                "__VIEWSTATEGENERATOR": _hidden_value(html, "__VIEWSTATEGENERATOR"),
                "originalShareholdingDate": _hidden_value(html, "originalShareholdingDate"),
                "__EVENTTARGET": "btnSearch",
                "txtShareholdingDate": requested.replace("-", "/"),
            }
            response = post(url, data=form, headers=headers)
            if hasattr(response, "raise_for_status"):
                response.raise_for_status()
            html = str(response.text)
        as_of_date, records = _holding_records(html, market_scope, observed)
        if requested and as_of_date != requested:
            return NorthboundFetchResult("failed", [], [{"date": requested, "kind": "source_date_mismatch", "detail": as_of_date}], requested, requested, False)
        return NorthboundFetchResult("success", records, [], requested, requested, True)
    except (OSError, requests.RequestException) as exc:
        return NorthboundFetchResult("failed", [], [{"date": requested or "latest", "kind": "network_failure", "detail": type(exc).__name__}], requested, requested, False)
    except Exception as exc:
        return NorthboundFetchResult("failed", [], [{"date": requested or "latest", "kind": "structure_error", "detail": type(exc).__name__}], requested, requested, False)
