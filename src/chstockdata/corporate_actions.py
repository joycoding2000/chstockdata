"""Bounded, free company-action and announcement indexes.

F3 intentionally exposes provider-normalised records only.  Public tool-plan,
capability and data-plane registration belongs to the later shared integration
package; this module neither downloads announcements nor infers event stages.
"""

from __future__ import annotations

import re

from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from hashlib import sha256
from html.parser import HTMLParser
from typing import Any

from .a_stock import _DATACENTER_URL, _em_get
from .utils import safe_ticker_component


_ANNOUNCEMENT_URL = "https://np-anotice-stock.eastmoney.com/api/security/ann"
_ANNOUNCEMENT_REFERER = "https://data.eastmoney.com/notices/"
_ANNOUNCEMENT_PDF_HOST = "https://pdf.dfcfw.com"
_SOURCE = "eastmoney"
_ACTION_SOURCE = "eastmoney_datacenter:RPT_SHAREBONUS_DET"
_FUND_ACTION_SOURCE = "eastmoney_fund_f10:FHSP+FHGG"
_ANNOUNCEMENT_SOURCE = "eastmoney_announcement_index"
_FUND_FHSP_URL = "https://fundf10.eastmoney.com/fhsp_{code}.html"
_FUND_FHGG_URL = "https://api.fund.eastmoney.com/f10/FHGG"
_FUND_ANNOUNCEMENT_PAGE_SIZE = 100
_FUND_MAX_ANNOUNCEMENT_PAGES = 12

_PLAN_STATUS = (
    ("取消", "cancelled"),
    ("终止", "cancelled"),
    ("变更", "amended"),
    ("调整", "amended"),
    ("实施", "implemented"),
    ("执行", "implemented"),
    ("股东大会", "shareholder_approved"),
    ("预案", "proposed"),
    ("董事会", "proposed"),
)
_ACTION_ID_FIELDS = ("DETAIL_ID", "REPORT_ID", "ANNOUNCEMENT_ID", "ID")
_DATE_FIELDS = (
    "announcement_date",
    "equity_record_date",
    "ex_dividend_date",
    "implementation_date",
    "payment_date",
)


RequestGet = Callable[..., Any]


class _FundDividendTableParser(HTMLParser):
    """Read the stable ``cfxq`` table from the fund F10 HTML page."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self._table_depth = 0
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        if tag == "table" and self._table_depth == 0:
            classes = dict(attrs).get("class", "").split()
            if "cfxq" in classes:
                self._table_depth = 1
            return
        if not self._table_depth:
            return
        if tag == "table":
            self._table_depth += 1
        elif tag == "tr" and self._table_depth == 1:
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            self._cell = []

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if not self._table_depth:
            return
        if tag in {"td", "th"} and self._cell is not None and self._row is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            self.rows.append(self._row)
            self._row = None
        elif tag == "table":
            self._table_depth -= 1


def _fund_date(value: Any) -> str | None:
    return _date(str(value).replace("/", "-")) if value not in (None, "") else None


def _fund_number_from_text(value: str) -> float | None:
    matches = re.findall(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)", value.replace(",", ""))
    if not matches:
        return None
    return _number(matches[-1])


def _parse_fund_distribution_page(text: str) -> tuple[list[dict[str, Any]], int]:
    """Parse the static F10 distribution table and count malformed rows."""
    parser = _FundDividendTableParser()
    parser.feed(text)
    parser.close()
    if not parser.rows:
        if "暂无分红信息" in text:
            return [], 0
        raise ValueError("基金 F10 页面缺少分红表")

    rows: list[dict[str, Any]] = []
    skipped = 0
    cash_header = "每10份分红"
    for cells in parser.rows:
        if not cells:
            continue
        if cells[0] == "年份":
            if len(cells) >= 4 and cells[3]:
                cash_header = cells[3]
            continue
        if any("暂无分红信息" in cell for cell in cells):
            continue
        if len(cells) < 5:
            skipped += 1
            continue
        equity_date = _fund_date(cells[1])
        ex_date = _fund_date(cells[2])
        payment_date = _fund_date(cells[4])
        cash_value = _fund_number_from_text(cells[3])
        if not equity_date or not ex_date or not payment_date or cash_value is None:
            skipped += 1
            continue
        if "每份" in cash_header and "每10份" not in cash_header:
            cash_value *= 10
        rows.append(
            {
                "equity_record_date": equity_date,
                "ex_dividend_date": ex_date,
                "payment_date": payment_date,
                "cash_value": cash_value,
                "cash_source_field": cash_header,
            }
        )
    return rows, skipped


def _is_fund_dividend_announcement(row: Mapping[str, Any]) -> bool:
    title = str(row.get("TITLE") or row.get("ShortTitle") or "")
    return any(marker in title for marker in ("分红", "收益分配", "收益分派"))


def _fetch_fund_announcements(
    request: RequestGet,
    code: str,
) -> tuple[list[dict[str, Any]], bool, int]:
    """Fetch and filter FHGG pages; return rows, truncation, skipped count."""
    announcements: list[dict[str, Any]] = []
    seen: set[str] = set()
    skipped = 0
    page = 1
    total: int | None = None
    truncated = False
    while page <= _FUND_MAX_ANNOUNCEMENT_PAGES:
        response = request(
            _FUND_FHGG_URL,
            params={
                "fundcode": code,
                "pageSize": _FUND_ANNOUNCEMENT_PAGE_SIZE,
                "pageIndex": page,
            },
            headers={"Referer": _FUND_FHSP_URL.format(code=code)},
            timeout=15,
            retries=2,
        )
        raise_for_status = getattr(response, "raise_for_status", None)
        if callable(raise_for_status):
            raise_for_status()
        payload = response.json()
        if not isinstance(payload, Mapping):
            raise ValueError("基金分红公告来源返回结构异常")
        if str(payload.get("ErrCode", "0")) not in {"0", "None", ""}:
            raise ValueError(f"基金分红公告来源返回错误 {payload.get('ErrCode')}")
        raw_rows = payload.get("Data")
        if raw_rows is None:
            raw_rows = []
        if not isinstance(raw_rows, list):
            raise ValueError("基金分红公告来源 Data 不是列表")
        try:
            parsed_total = int(payload.get("TotalCount"))
        except (TypeError, ValueError):
            parsed_total = None
        if parsed_total is not None and parsed_total >= 0:
            total = parsed_total if total is None else max(total, parsed_total)
        for row in raw_rows:
            if not isinstance(row, Mapping) or not _is_fund_dividend_announcement(row):
                continue
            announcement_date = _fund_date(
                row.get("PUBLISHDATE") or row.get("PUBLISHDATEDesc")
            )
            identifier = row.get("ID") or row.get("ANNOUNCEMENT_ID")
            if announcement_date is None:
                skipped += 1
                continue
            key = str(identifier) if identifier not in (None, "") else (
                f"{announcement_date}\x1f{row.get('TITLE') or row.get('ShortTitle') or ''}"
            )
            if key in seen:
                continue
            seen.add(key)
            announcements.append(
                {
                    "source_identifier": str(identifier) if identifier not in (None, "") else None,
                    "announcement_date": announcement_date,
                }
            )
        page_size = _FUND_ANNOUNCEMENT_PAGE_SIZE
        try:
            page_size = max(1, int(payload.get("PageSize") or page_size))
        except (TypeError, ValueError):
            pass
        if not raw_rows or total is None or page * page_size >= total:
            break
        page += 1
    else:
        truncated = total is not None and page * _FUND_ANNOUNCEMENT_PAGE_SIZE < total
    if page >= _FUND_MAX_ANNOUNCEMENT_PAGES and total is not None:
        truncated = truncated or page * _FUND_ANNOUNCEMENT_PAGE_SIZE < total
    return announcements, truncated, skipped


def _fund_action_item(
    code: str,
    distribution: Mapping[str, Any],
    announcement: Mapping[str, Any] | None,
) -> dict[str, Any]:
    announcement_date = announcement.get("announcement_date") if announcement else None
    identifier = announcement.get("source_identifier") if announcement else None
    if identifier is None:
        identifier = "eastmoney_fund:" + code + ":" + ":".join(
            str(distribution.get(field) or "")
            for field in ("equity_record_date", "ex_dividend_date", "payment_date")
        )
        identifier_kind = "source_field_composite"
    else:
        identifier_kind = "provider_identifier"
    return {
        "source_identifier": identifier,
        "source_identifier_kind": identifier_kind,
        "announcement_date": announcement_date,
        "ex_dividend_date": distribution.get("ex_dividend_date"),
        "equity_record_date": distribution.get("equity_record_date"),
        "payment_date": distribution.get("payment_date"),
        "cash_dividend": _per_ten(
            distribution.get("cash_value"),
            source_field=str(distribution.get("cash_source_field") or "每10份分红"),
            tax_basis="unknown",
        ),
        "stock_dividend": None,
        "capital_reserve_transfer": None,
        "rights_issue": None,
    }


def _fund_action_in_window(
    item: Mapping[str, Any], start: str | None, end: str | None
) -> bool:
    if not start and not end:
        return True
    return any(
        _in_window(item.get(field), start, end)
        for field in ("announcement_date", "equity_record_date", "ex_dividend_date", "payment_date")
    )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _market(code: str) -> str:
    if code.startswith(("8", "4", "92")):
        return "bj"
    if code.startswith(("5", "6", "9")):
        return "sh"
    return "sz"


def _date(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return None


def _datetime_precision(value: Any) -> tuple[str | None, str]:
    if value is None:
        return None, "unknown"
    text = str(value).strip()
    parsed = _date(text)
    if parsed is None:
        return None, "unknown"
    return parsed, "datetime" if any(marker in text for marker in (" ", "T")) else "date"


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _first(row: Mapping[str, Any], names: tuple[str, ...]) -> Any:
    for name in names:
        value = row.get(name)
        if value not in (None, ""):
            return value
    return None


def _per_ten_source(row: Mapping[str, Any], names: tuple[str, ...]) -> tuple[Any, str]:
    """Return the first present value together with the field name that supplied it.

    ``source_field`` must name the field the value actually came from.  The
    candidate tuples below carry unverified defensive alternates, so stamping
    the first name unconditionally misreported provenance whenever a value fell
    through to a later field (e.g. a transfer value taken from
    ``CAPITAL_RESERVE`` was reported as ``TRANSFER_IT_RATIO``).
    """
    for name in names:
        value = row.get(name)
        if value not in (None, ""):
            return value, name
    return None, names[0]


def _plan_status(value: Any) -> str:
    text = str(value or "").strip()
    for marker, status in _PLAN_STATUS:
        if marker in text:
            return status
    return "unknown"


def _per_ten(
    value: Any,
    *,
    source_field: str,
    tax_basis: str = "unknown",
) -> dict[str, Any] | None:
    parsed = _number(value)
    if parsed is None:
        return None
    return {
        "value": parsed,
        "unit": "per_10_shares",
        "source_field": source_field,
        "tax_basis": tax_basis,
    }


def _query_error(
    *,
    fetched_at: str,
    failure_kind: str,
    message: str,
    source: str,
) -> dict[str, Any]:
    return {
        "status": "failed",
        "coverage": "unavailable",
        "items": [],
        "source": source,
        "fetched_at": fetched_at,
        "failure_kind": failure_kind,
        "error_summary": message,
        "metadata": {
            "duplicate_count": 0,
            "skipped_row_count": 0,
            "excluded_after_cutoff_count": 0,
            "missing_fields": [],
            "limitations": ["请求失败不代表指定公司不存在相关事件或公告。"],
        },
    }


def _validate_query_dates(*values: str | None) -> None:
    for value in values:
        if value is not None and _date(value) is None:
            raise ValueError("日期必须是 ISO 日期或日期时间")


def _validate_window(start: str | None, end: str | None) -> None:
    if start and end and start > end:
        raise ValueError("开始日期不得晚于结束日期")


def _in_window(value: str | None, start: str | None, end: str | None) -> bool:
    return value is not None and (start is None or value >= start) and (end is None or value <= end)


def _pagination(payload: Mapping[str, Any], page: int, page_size: int) -> dict[str, Any]:
    total_raw = payload.get("count", payload.get("total_hits"))
    total = int(total_raw) if isinstance(total_raw, (int, float, str)) and str(total_raw).isdigit() else None
    return {
        "page": page,
        "page_size": page_size,
        "total": total,
        "truncated": total is not None and page * page_size < total,
    }


def _action_from_row(row: Mapping[str, Any], code: str) -> tuple[dict[str, Any], list[str]]:
    source_identifier = _first(row, _ACTION_ID_FIELDS)
    identifier_kind = "provider_identifier" if source_identifier is not None else "unknown"
    plan_status_source = _first(row, ("ASSIGN_PROGRESS", "PLAN_PROGRESS", "PLAN_STATUS", "STATUS"))
    plan_text = _first(row, ("IMPL_PLAN_PROFILE", "ASSIGN_PLAN", "PLAN_CONTENT"))
    if source_identifier is None:
        composite = [
            _first(row, ("SECURITY_INNER_CODE",)), row.get("REPORT_DATE"),
            _first(row, ("PLAN_NOTICE_DATE", "NOTICE_DATE")), plan_status_source, plan_text,
        ]
        if all(value not in (None, "") for value in composite):
            encoded = "\x1f".join(str(value) for value in composite)
            source_identifier = "eastmoney:" + sha256(encoded.encode("utf-8")).hexdigest()
            identifier_kind = "source_field_composite"
    source_identifier = str(source_identifier) if source_identifier is not None else None
    cash_value, cash_field = _per_ten_source(
        row, ("PRETAX_BONUS_RMB", "CASH_DIVIDEND_RATIO", "CASH_DIVIDEND")
    )
    cash = _per_ten(
        cash_value,
        source_field=cash_field,
        tax_basis="pre_tax" if cash_field == "PRETAX_BONUS_RMB" else "unknown",
    )
    stock_value, stock_field = _per_ten_source(row, ("BONUS_IT_RATIO", "STOCK_DIVIDEND"))
    stock = _per_ten(stock_value, source_field=stock_field)
    transfer_value, transfer_field = _per_ten_source(
        row, ("IT_RATIO", "TRANSFER_IT_RATIO", "CAPITAL_RESERVE")
    )
    transfer = _per_ten(transfer_value, source_field=transfer_field)
    rights_value, rights_field = _per_ten_source(
        row, ("ALLOTMENT_RATIO", "RIGHTS_ISSUE_RATIO")
    )
    rights = _per_ten(rights_value, source_field=rights_field)
    if rights and rights["value"] == 0:
        rights = None
    parts = {
        "cash_dividend": cash,
        "stock_dividend": stock,
        "capital_reserve_transfer": transfer,
        "rights_issue": rights,
    }
    event_types = [name for name, value in parts.items() if value and value["value"] != 0]
    missing = [name for name in _DATE_FIELDS if name != "announcement_date" and not row.get({
        "equity_record_date": "EQUITY_RECORD_DATE",
        "ex_dividend_date": "EX_DIVIDEND_DATE",
        "implementation_date": "IMPLEMENT_DATE",
        "payment_date": "PAYMENT_DATE",
    }.get(name, ""))]
    action = {
        "source_identifier": source_identifier,
        "source_identifier_kind": identifier_kind,
        "source": _ACTION_SOURCE,
        "security_code": code,
        "market": _market(code),
        "security_name": _first(row, ("SECURITY_NAME_ABBR", "SECURITY_NAME")),
        "event_types": event_types or ["distribution_plan"],
        "plan_status": _plan_status(plan_status_source),
        "plan_status_source": str(plan_status_source) if plan_status_source is not None else None,
        "related_source_identifier": _first(row, ("RELATED_ID", "PARENT_ID", "PREVIOUS_ID")),
        "announcement_date": _date(_first(row, ("NOTICE_DATE", "ANNOUNCEMENT_DATE"))),
        "equity_record_date": _date(row.get("EQUITY_RECORD_DATE")),
        "ex_dividend_date": _date(row.get("EX_DIVIDEND_DATE")),
        "implementation_date": _date(row.get("IMPLEMENT_DATE")),
        "payment_date": _date(row.get("PAYMENT_DATE")),
        "report_period_end": _date(row.get("REPORT_DATE")),
        "plan_text": plan_text,
        **parts,
        "missing_fields": missing,
        "limitations": (["来源未提供稳定事件标识；该记录未参与跨行去重或版本合并。"] if source_identifier is None else []),
    }
    return action, missing


def get_corporate_actions(
    ticker: str,
    *,
    announcement_start: str | None = None,
    announcement_end: str | None = None,
    event_start: str | None = None,
    event_end: str | None = None,
    as_of_date: str | None = None,
    page: int = 1,
    page_size: int = 50,
    request_get: RequestGet | None = None,
) -> dict[str, Any]:
    """Return one bounded page of dividend/distribution action records.

    ``announcement_*`` applies only to the source announcement date;
    ``event_*`` applies only to registration/ex-dividend/implementation/payment
    dates.  It does not infer implementation from a date or plan wording.
    """
    fetched_at = _now()
    try:
        code = safe_ticker_component(str(ticker).strip())
        _validate_query_dates(announcement_start, announcement_end, event_start, event_end, as_of_date)
        _validate_window(announcement_start, announcement_end)
        _validate_window(event_start, event_end)
        if page < 1 or not 1 <= page_size <= 100:
            raise ValueError("page 必须从 1 开始，page_size 必须在 1 到 100 之间")
    except (TypeError, ValueError) as exc:
        return _query_error(fetched_at=fetched_at, failure_kind="invalid_input", message=str(exc), source=_ACTION_SOURCE)

    request = request_get or _em_get
    params = {
        "reportName": "RPT_SHAREBONUS_DET", "columns": "ALL",
        "filter": f'(SECURITY_CODE="{code}")', "pageNumber": str(page),
        "pageSize": str(page_size), "sortColumns": "NOTICE_DATE", "sortTypes": "-1",
        "source": "WEB", "client": "WEB",
    }
    try:
        payload = request(_DATACENTER_URL, params=params, timeout=15, retries=2).json()
        result = payload.get("result") if isinstance(payload, Mapping) else None
        rows = result.get("data") if isinstance(result, Mapping) else None
        if rows is None or not isinstance(rows, list):
            return _query_error(fetched_at=fetched_at, failure_kind="structure_error", message="公司行为来源返回结构异常", source=_ACTION_SOURCE)
        page_info = _pagination(result, page, page_size)
    except Exception as exc:
        return _query_error(fetched_at=fetched_at, failure_kind="request_error", message=f"公司行为来源请求失败：{type(exc).__name__}", source=_ACTION_SOURCE)

    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    duplicate_count = skipped = excluded_cutoff = 0
    missing_fields: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            skipped += 1
            continue
        action, missing = _action_from_row(row, code)
        missing_fields.update(missing)
        announcement_date = action["announcement_date"]
        if as_of_date and (announcement_date is None or announcement_date > as_of_date):
            excluded_cutoff += 1
            continue
        if (announcement_start or announcement_end) and not _in_window(announcement_date, announcement_start, announcement_end):
            continue
        event_dates = [action[field] for field in _DATE_FIELDS[1:]]
        if (event_start or event_end) and not any(_in_window(value, event_start, event_end) for value in event_dates):
            continue
        identifier = action["source_identifier"]
        if identifier is not None and identifier in seen:
            duplicate_count += 1
            continue
        if identifier is not None:
            seen.add(identifier)
        items.append(action)
    items.sort(key=lambda item: (item["announcement_date"] is not None, item["announcement_date"] or ""), reverse=True)
    coverage = "partial" if page_info["truncated"] or skipped else "complete"
    return {
        "status": "success" if items else "normal_empty",
        "coverage": coverage,
        "items": items,
        "source": _ACTION_SOURCE,
        "fetched_at": fetched_at,
        "failure_kind": None,
        "error_summary": None,
        "metadata": {
            "query": {"announcement_window": [announcement_start, announcement_end], "event_window": [event_start, event_end], "as_of_date": as_of_date},
            "pagination": page_info, "duplicate_count": duplicate_count,
            "skipped_row_count": skipped, "excluded_after_cutoff_count": excluded_cutoff,
            "missing_fields": sorted(missing_fields),
            "limitations": ["无记录仅表示该来源、本页及指定窗口内无匹配记录，不表示公司不存在其他公司行为或风险。"],
        },
    }


def get_fund_corporate_actions(
    code: str,
    start: str | None = None,
    end: str | None = None,
    as_of_date: str | None = None,
    page: int = 1,
    page_size: int = 50,
    request_get: RequestGet | None = None,
) -> dict[str, Any]:
    """Return normalized ETF/fund cash-distribution records.

    Eastmoney's current fund F10 page exposes the historical distribution
    table at ``FHSP`` and the matching announcement dates at ``FHGG``.  The
    table may say ``每份`` or ``每10份``; both are returned as
    ``cash_dividend.unit == "per_10_shares"``.  ``start``/``end`` include an
    action when any known lifecycle date falls in the inclusive window, while
    ``as_of_date`` is an announcement-date cutoff.

    A missing announcement match is retained with a composite identifier and
    marks the envelope ``coverage`` as ``partial``; the adapter never invents
    an announcement date.  A truly empty F10 distribution table is
    ``normal_empty`` and is not a request failure.
    """
    fetched_at = _now()
    start = start or None
    end = end or None
    as_of_date = as_of_date or None
    try:
        normalized_code = safe_ticker_component(str(code).strip())
        _validate_query_dates(start, end, as_of_date)
        _validate_window(start, end)
        if page < 1 or not 1 <= page_size <= 100:
            raise ValueError("page 必须从 1 开始，page_size 必须在 1 到 100 之间")
    except (TypeError, ValueError) as exc:
        return _query_error(
            fetched_at=fetched_at,
            failure_kind="invalid_input",
            message=str(exc),
            source=_FUND_ACTION_SOURCE,
        )

    request = request_get or _em_get
    try:
        response = request(
            _FUND_FHSP_URL.format(code=normalized_code),
            headers={"Referer": "https://fund.eastmoney.com/"},
            timeout=15,
            retries=2,
        )
        raise_for_status = getattr(response, "raise_for_status", None)
        if callable(raise_for_status):
            raise_for_status()
        html = getattr(response, "text", None)
        if not isinstance(html, str):
            raise ValueError("基金 F10 分红页面缺少文本内容")
        distributions, skipped_distributions = _parse_fund_distribution_page(html)
    except ValueError as exc:
        return _query_error(
            fetched_at=fetched_at,
            failure_kind="structure_error",
            message=f"基金分红来源结构异常：{exc}",
            source=_FUND_ACTION_SOURCE,
        )
    except Exception as exc:
        return _query_error(
            fetched_at=fetched_at,
            failure_kind="request_error",
            message=f"基金分红来源请求失败：{type(exc).__name__}",
            source=_FUND_ACTION_SOURCE,
        )

    if not distributions:
        return {
            "status": "normal_empty",
            "coverage": "partial" if skipped_distributions else "complete",
            "items": [],
            "source": _FUND_ACTION_SOURCE,
            "fetched_at": fetched_at,
            "failure_kind": None,
            "error_summary": None,
            "metadata": {
                "query": {"start": start, "end": end, "as_of_date": as_of_date},
                "pagination": {
                    "page": page,
                    "page_size": page_size,
                    "total": 0,
                    "truncated": False,
                },
                "duplicate_count": 0,
                "skipped_row_count": skipped_distributions,
                "excluded_after_cutoff_count": 0,
                "missing_fields": [],
                "limitations": ["无记录表示该基金 F10 分红表及指定窗口内无匹配记录。"],
            },
        }

    try:
        announcements, announcements_truncated, skipped_announcements = _fetch_fund_announcements(
            request, normalized_code
        )
    except ValueError as exc:
        return _query_error(
            fetched_at=fetched_at,
            failure_kind="structure_error",
            message=f"基金分红公告来源结构异常：{exc}",
            source=_FUND_ACTION_SOURCE,
        )
    except Exception as exc:
        return _query_error(
            fetched_at=fetched_at,
            failure_kind="request_error",
            message=f"基金分红公告来源请求失败：{type(exc).__name__}",
            source=_FUND_ACTION_SOURCE,
        )

    available = sorted(announcements, key=lambda row: row["announcement_date"])
    all_items: list[dict[str, Any]] = []
    missing_announcement_count = 0
    for distribution in sorted(
        distributions,
        key=lambda row: (
            row.get("ex_dividend_date") or row.get("equity_record_date") or ""
        ),
    ):
        anchor = distribution.get("equity_record_date") or distribution.get("ex_dividend_date")
        candidates = [
            row
            for row in available
            if row["announcement_date"] <= (anchor or "9999-12-31")
            and row["announcement_date"][:4] == str(anchor or "")[:4]
        ]
        announcement = max(candidates, key=lambda row: row["announcement_date"]) if candidates else None
        if announcement is None:
            missing_announcement_count += 1
        else:
            available.remove(announcement)
        all_items.append(_fund_action_item(normalized_code, distribution, announcement))

    filtered: list[dict[str, Any]] = []
    excluded_after_cutoff = 0
    for item in all_items:
        if as_of_date and (
            item["announcement_date"] is None or item["announcement_date"] > as_of_date
        ):
            excluded_after_cutoff += 1
            continue
        if not _fund_action_in_window(item, start, end):
            continue
        filtered.append(item)
    filtered.sort(
        key=lambda item: (
            item["announcement_date"] is not None,
            item["announcement_date"] or item["ex_dividend_date"] or "",
        ),
        reverse=True,
    )
    total = len(filtered)
    begin = (page - 1) * page_size
    items = filtered[begin : begin + page_size]
    truncated = page * page_size < total
    coverage = (
        "partial"
        if (
            skipped_distributions
            or skipped_announcements
            or announcements_truncated
            or missing_announcement_count
            or truncated
        )
        else "complete"
    )
    missing_fields = ["announcement_date"] if missing_announcement_count else []
    return {
        "status": "success" if items else "normal_empty",
        "coverage": coverage,
        "items": items,
        "source": _FUND_ACTION_SOURCE,
        "fetched_at": fetched_at,
        "failure_kind": None,
        "error_summary": None,
        "metadata": {
            "query": {"start": start, "end": end, "as_of_date": as_of_date},
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total,
                "truncated": truncated,
            },
            "duplicate_count": 0,
            "skipped_row_count": skipped_distributions + skipped_announcements,
            "excluded_after_cutoff_count": excluded_after_cutoff,
            "missing_fields": missing_fields,
            "limitations": [
                "分红表来自基金 F10；公告日来自 FHGG，若两者无法匹配则覆盖度为 partial。",
                "基金现金分红的税务扣缴口径由来源未提供，tax_basis 保留为 unknown。",
            ],
        },
    }


def build_corporate_action_timeline(actions: Mapping[str, Any]) -> dict[str, Any]:
    """Expand action records into explicit, date-typed timeline entries."""
    items: list[dict[str, Any]] = []
    for action in actions.get("items", []) if isinstance(actions, Mapping) else []:
        if not isinstance(action, Mapping):
            continue
        emitted = False
        for field in _DATE_FIELDS:
            value = action.get(field)
            if value:
                emitted = True
                items.append({"date": value, "date_type": field, "source_identifier": action.get("source_identifier"), "plan_status": action.get("plan_status"), "event_types": action.get("event_types", [])})
        if not emitted:
            items.append({"date": None, "date_type": "unknown", "source_identifier": action.get("source_identifier"), "plan_status": action.get("plan_status"), "event_types": action.get("event_types", []), "missing_date_types": list(_DATE_FIELDS)})
    items.sort(key=lambda item: (item["date"] is None, item["date"] or ""))
    return {"status": actions.get("status", "failed") if isinstance(actions, Mapping) else "failed", "items": items, "source": _ACTION_SOURCE}


def _announcement_link(value: Any, *, code: str, identifier: str | None) -> str | None:
    path = str(value or "").strip()
    if not path:
        return (
            f"https://data.eastmoney.com/notices/detail/{code}/{identifier}.html"
            if identifier else None
        )
    if path.startswith("https://"):
        return path
    return _ANNOUNCEMENT_PDF_HOST + (path if path.startswith("/") else "/" + path)


def get_announcement_index(
    ticker: str,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    as_of_date: str | None = None,
    page: int = 1,
    page_size: int = 50,
    request_get: RequestGet | None = None,
) -> dict[str, Any]:
    """Return one bounded page of titles, categories, dates and source links.

    Only links are indexed: announcement files are never downloaded or parsed.
    A date-only ``display_time`` is labelled ``date``, never intraday-precise.
    """
    fetched_at = _now()
    try:
        code = safe_ticker_component(str(ticker).strip())
        _validate_query_dates(start_date, end_date, as_of_date)
        _validate_window(start_date, end_date)
        if page < 1 or not 1 <= page_size <= 100:
            raise ValueError("page 必须从 1 开始，page_size 必须在 1 到 100 之间")
    except (TypeError, ValueError) as exc:
        return _query_error(fetched_at=fetched_at, failure_kind="invalid_input", message=str(exc), source=_ANNOUNCEMENT_SOURCE)

    request = request_get or _em_get
    params = {"sr": "-1", "page_size": page_size, "page_index": page, "ann_type": "A", "client_source": "web", "stock_list": code}
    if start_date:
        params["begin_time"] = start_date
    if end_date:
        params["end_time"] = end_date
    try:
        payload = request(_ANNOUNCEMENT_URL, params=params, headers={"Referer": _ANNOUNCEMENT_REFERER}, timeout=15, retries=2).json()
        data = payload.get("data") if isinstance(payload, Mapping) else None
        rows = data.get("list") if isinstance(data, Mapping) else None
        if rows is None or not isinstance(rows, list):
            return _query_error(fetched_at=fetched_at, failure_kind="structure_error", message="公告索引来源返回结构异常", source=_ANNOUNCEMENT_SOURCE)
        page_info = _pagination(data, page, page_size)
    except Exception as exc:
        return _query_error(fetched_at=fetched_at, failure_kind="request_error", message=f"公告索引来源请求失败：{type(exc).__name__}", source=_ANNOUNCEMENT_SOURCE)

    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    duplicate_count = skipped = excluded_cutoff = 0
    for row in rows:
        if not isinstance(row, Mapping):
            skipped += 1
            continue
        identifier = _first(row, ("art_code", "announcement_id", "ANNOUNCEMENT_ID"))
        identifier = str(identifier) if identifier is not None else None
        announcement_date, precision = _datetime_precision(_first(row, ("display_time", "notice_date", "ANNOUNCEMENT_DATE")))
        if as_of_date and (announcement_date is None or announcement_date > as_of_date):
            excluded_cutoff += 1
            continue
        if (start_date or end_date) and not _in_window(announcement_date, start_date, end_date):
            continue
        if identifier is not None and identifier in seen:
            duplicate_count += 1
            continue
        if identifier is not None:
            seen.add(identifier)
        columns = row.get("columns")
        categories = [str(item.get("column_name")).strip() for item in columns if isinstance(item, Mapping) and item.get("column_name")] if isinstance(columns, list) else []
        source_link = _announcement_link(
            _first(row, ("attach_path", "ATTACH_PATH", "url")),
            code=code,
            identifier=identifier,
        )
        title = _first(row, ("title", "TITLE"))
        items.append({
            "announcement_id": identifier, "source": _ANNOUNCEMENT_SOURCE,
            "security_code": code, "market": _market(code),
            "title": title, "categories": categories,
            "announcement_date": announcement_date, "publication_time_precision": precision,
            "source_link": source_link,
            "missing_fields": [name for name, value in (("announcement_id", identifier), ("announcement_date", announcement_date), ("title", title), ("source_link", source_link)) if not value],
            "limitations": (["来源未提供稳定公告标识；该记录未参与跨行去重。"] if identifier is None else []),
        })
    items.sort(key=lambda item: (item["announcement_date"] is not None, item["announcement_date"] or ""), reverse=True)
    coverage = "partial" if page_info["truncated"] or skipped else "complete"
    return {
        "status": "success" if items else "normal_empty", "coverage": coverage,
        "items": items, "source": _ANNOUNCEMENT_SOURCE, "fetched_at": fetched_at,
        "failure_kind": None, "error_summary": None,
        "metadata": {
            "query": {"announcement_window": [start_date, end_date], "as_of_date": as_of_date},
            "pagination": page_info, "duplicate_count": duplicate_count,
            "skipped_row_count": skipped, "excluded_after_cutoff_count": excluded_cutoff,
            "missing_fields": sorted({field for item in items for field in item["missing_fields"]}),
            "limitations": ["公告链接仅作索引；本模块不下载、解析或执行公告内容。", "无记录仅表示该来源、本页及指定窗口内无公告记录。"],
        },
    }
