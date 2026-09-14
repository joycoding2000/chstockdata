"""Free, per-security Eastmoney block-trade retrieval.

This module deliberately has no tool-plan, Registry, data-plane, or UI wiring.
It owns only the bounded datacenter request and its normalized, auditable result.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
import math
import re
import time
from typing import Any, Callable, Mapping

from .a_stock import _DATACENTER_URL, _em_get
from .provenance import (
    ATTEMPT_FAILED_NETWORK,
    ATTEMPT_FAILED_STRUCTURE,
    ATTEMPT_NORMAL_EMPTY,
    ATTEMPT_SUCCESS,
    COMPLETENESS_FULL,
    COMPLETENESS_PARTIAL,
    EvidenceEnvelope,
    ProviderAttempt,
)


_REPORT_NAME = "RPT_DATA_BLOCKTRADE"
_SOURCE = f"eastmoney_datacenter:{_REPORT_NAME}"
_COLUMNS = (
    "TRADE_DATE,SECURITY_CODE,SECURITY_NAME_ABBR,DEAL_PRICE,PREMIUM_RATIO,"
    "DEAL_VOLUME,DEAL_AMT,BUYER_NAME,SELLER_NAME"
)
_TICKER_RE = re.compile(r"\d{6}\Z")
_MAX_WINDOW_DAYS = 366
_MAX_PAGE_SIZE = 500
_MAX_PAGES = 10

# Eastmoney's current RPT_DATA_BLOCKTRADE response was field-checked with the
# 2025-12-12 600519 record: 1420.65 × 5300 ~= reported 7,529,400.  The values
# are therefore shares and yuan, not 万股/万元.  Keep this source evidence with
# every normalized record instead of inferring units from English field names.
_RAW_UNITS = {
    "deal_volume": "股",
    "deal_amount": "元",
    "deal_price": "元/股",
    "premium_ratio": "小数比率",
}

ReferencePriceLookup = Callable[[str, str], tuple[float, str] | None]


@dataclass(frozen=True)
class BlockTradeFetchResult:
    """The isolated F4 output; state is derived from the shared EvidenceEnvelope."""

    records: tuple[dict[str, Any], ...]
    evidence: EvidenceEnvelope

    @property
    def cacheable(self) -> bool:
        """Only a completed terminal outcome may be cached by a future caller."""
        return (
            self.evidence.completeness == COMPLETENESS_FULL
            and self.evidence.final_status in {"success", "normal_empty"}
        )


def fetch_free_block_trades(
    ticker: str,
    start_date: str,
    end_date: str,
    *,
    page_size: int = 100,
    max_pages: int = 10,
    reference_price_lookup: ReferencePriceLookup | None = None,
    now: datetime | None = None,
) -> BlockTradeFetchResult:
    """Fetch one security's block trades in an inclusive, bounded date window.

    ``reference_price_lookup`` is optional and must return a same-day,
    unadjusted ``(price, date)`` tuple.  It is never replaced with realtime or
    adjusted prices when unavailable.  Public integration will provide that
    lookup after F4's isolated adapter is accepted.
    """
    code = str(ticker).strip()
    if not _TICKER_RE.fullmatch(code):
        raise ValueError("ticker must be a 6-digit A-share code")
    start = _parse_iso_date(start_date, "start_date")
    end = _parse_iso_date(end_date, "end_date")
    if start > end:
        raise ValueError("start_date must not be after end_date")
    if (end - start).days > _MAX_WINDOW_DAYS:
        raise ValueError(f"date window must not exceed {_MAX_WINDOW_DAYS} days")
    page_size = _positive_int(page_size, "page_size")
    max_pages = _positive_int(max_pages, "max_pages")
    if page_size > _MAX_PAGE_SIZE:
        raise ValueError(f"page_size must not exceed {_MAX_PAGE_SIZE}")
    if max_pages > _MAX_PAGES:
        raise ValueError(f"max_pages must not exceed {_MAX_PAGES}")

    observed_at = _as_utc(now)
    observed_iso = observed_at.isoformat()
    attempts: list[ProviderAttempt] = []
    limitations: list[str] = []
    records: list[dict[str, Any]] = []
    stable_ids: set[str] = set()
    missing_stable_id = False
    total_pages: int | None = None
    total_count: int | None = None
    complete = True
    if end > observed_at.date():
        complete = False
        limitations.append(
            "The requested window extends into the future; it cannot be asserted as a complete no-trade window."
        )
    accepted_source_rows = 0

    for page_number in range(1, max_pages + 1):
        params = _request_params(code, start, end, page_number, page_size)
        started = time.perf_counter()
        try:
            response = _em_get(_DATACENTER_URL, params=params, timeout=15)
        except Exception as exc:
            complete = False
            attempts.append(_attempt(ATTEMPT_FAILED_NETWORK, observed_iso, started, exc))
            limitations.append(
                f"Eastmoney page {page_number} failed ({type(exc).__name__}); returned rows are partial."
            )
            break

        try:
            payload = response.json()
        except Exception as exc:
            complete = False
            attempts.append(_attempt(ATTEMPT_FAILED_STRUCTURE, observed_iso, started, exc))
            limitations.append(
                f"Eastmoney page {page_number} did not contain parseable JSON; returned rows are partial."
            )
            break

        try:
            rows, reported_pages, reported_count = _parse_page(payload)
        except (TypeError, ValueError) as exc:
            complete = False
            attempts.append(_attempt(ATTEMPT_FAILED_STRUCTURE, observed_iso, started, exc))
            limitations.append(
                f"Eastmoney page {page_number} had an invalid response structure; returned rows are partial."
            )
            break

        if total_pages is None:
            total_pages = reported_pages
            total_count = reported_count
        elif total_pages != reported_pages:
            complete = False
            limitations.append(
                "Eastmoney reported an inconsistent page count; returned rows are partial."
            )
            total_pages = max(total_pages, reported_pages)
        if total_count is not None and total_count != reported_count:
            complete = False
            limitations.append("Eastmoney reported an inconsistent record count; returned rows are partial.")

        attempts.append(
            _attempt(ATTEMPT_SUCCESS, observed_iso, started, record_count=len(rows))
        )
        accepted_source_rows += len(rows)
        for row in rows:
            normalized, row_limitation, lacked_stable_id = _normalize_row(
                row,
                ticker=code,
                start=start,
                end=end,
                today=observed_at.date(),
                fetched_at=observed_iso,
                reference_price_lookup=reference_price_lookup,
            )
            if row_limitation:
                complete = False
                limitations.append(row_limitation)
                continue
            if normalized is None:  # defensive; _normalize_row always explains exclusion
                complete = False
                limitations.append("Eastmoney returned an unusable row; returned rows are partial.")
                continue
            source_id = normalized["source_record_id"]
            if source_id is not None:
                if source_id in stable_ids:
                    continue
                stable_ids.add(source_id)
            elif lacked_stable_id:
                missing_stable_id = True
            records.append(normalized)

        if total_pages is None or page_number >= total_pages:
            break
    else:
        complete = False
        limitations.append(
            f"Eastmoney reports more than max_pages={max_pages}; returned rows are partial."
        )

    if total_pages is not None and total_pages > max_pages:
        complete = False
        if not any("max_pages" in limitation for limitation in limitations):
            limitations.append(
                f"Eastmoney reports {total_pages} pages, exceeding max_pages={max_pages}; returned rows are partial."
            )
    if total_count is not None and accepted_source_rows != total_count:
        complete = False
        limitations.append(
            "Eastmoney reported a record count that does not match fetched pages; returned rows are partial."
        )
    if missing_stable_id:
        limitations.append(
            "One or more Eastmoney rows lack a stable source ID; same-valued rows were retained rather than merged."
        )

    # A valid, fully-covered query that has no raw source rows is the only
    # normal-empty case.  Filtering malformed/out-of-window source rows never
    # becomes an apparently complete no-trade assertion.
    if complete and accepted_source_rows == 0:
        attempts[-1] = _attempt(
            ATTEMPT_NORMAL_EMPTY,
            observed_iso,
            duration_ms=attempts[-1].duration_ms,
            record_count=0,
        )

    completeness = COMPLETENESS_FULL if complete else COMPLETENESS_PARTIAL
    coverage = "full" if complete else "partial"
    stamped_records = tuple({**record, "coverage_status": coverage} for record in records)
    evidence = EvidenceEnvelope(
        capability_id="cap_free_block_trades",
        evidence_category="资金",
        evidence_domain="资金与筹码",
        original_tool="get_block_trades",
        attempts=attempts,
        observation_date=end.isoformat(),
        data_cutoff_date=end.isoformat(),
        completeness=completeness,
        limitations=_ordered_unique(limitations),
    )
    return BlockTradeFetchResult(records=stamped_records, evidence=evidence)


def _request_params(
    ticker: str, start: date, end: date, page_number: int, page_size: int
) -> dict[str, str]:
    return {
        "reportName": _REPORT_NAME,
        "columns": _COLUMNS,
        "filter": (
            f'(SECURITY_CODE="{ticker}")'
            f"(TRADE_DATE>='{start.isoformat()}')"
            f"(TRADE_DATE<='{end.isoformat()}')"
        ),
        "pageNumber": str(page_number),
        "pageSize": str(page_size),
        # DAILY_RANK is a deterministic per-trade-date tie-breaker, so pagination
        # becomes a total order instead of "same date, server-defined order".
        # Live check 2026-09-13 (301358): the rank is unique within each date
        # (2026-09-11 returned 27 rows / 27 distinct ranks) and the provider
        # accepts sorting by it even when it is absent from ``columns``.  Without
        # it a row can be duplicated or skipped across a page boundary with no
        # way to detect it, because the report exposes no stable record ID
        # (verified via columns=ALL; see _stable_source_id).
        "sortColumns": "TRADE_DATE,DAILY_RANK",
        "sortTypes": "-1,1",
        "source": "WEB",
        "client": "WEB",
    }


def _parse_page(payload: Any) -> tuple[list[dict[str, Any]], int, int]:
    if not isinstance(payload, Mapping):
        raise ValueError("payload is not an object")
    result = payload.get("result")
    # The datacenter currently confirms an empty completed query as
    # {code: 9201, success: false, message: "返回数据为空", result: null} rather
    # than result.data=[].  Require all of these facts; arbitrary false/error
    # responses remain structure failures and can never become normal-empty.
    if (
        result is None
        and str(payload.get("code")) == "9201"
        and str(payload.get("message") or "").strip() == "返回数据为空"
    ):
        return [], 1, 0
    if payload.get("success") is not True:
        raise ValueError("payload.success is not true")
    if not isinstance(result, Mapping):
        raise ValueError("payload.result is missing")
    rows = result.get("data")
    if not isinstance(rows, list) or not all(isinstance(row, Mapping) for row in rows):
        raise ValueError("payload.result.data is not a row list")
    try:
        pages = int(result.get("pages"))
    except (TypeError, ValueError) as exc:
        raise ValueError("payload.result.pages is missing") from exc
    if pages < 1:
        raise ValueError("payload.result.pages is invalid")
    try:
        count = int(result.get("count"))
    except (TypeError, ValueError) as exc:
        raise ValueError("payload.result.count is missing") from exc
    if count < len(rows):
        raise ValueError("payload.result.count is smaller than page rows")
    return [dict(row) for row in rows], pages, count


def _normalize_row(
    row: Mapping[str, Any],
    *,
    ticker: str,
    start: date,
    end: date,
    today: date,
    fetched_at: str,
    reference_price_lookup: ReferencePriceLookup | None,
) -> tuple[dict[str, Any] | None, str | None, bool]:
    trade_date = _row_trade_date(row.get("TRADE_DATE"))
    source_code = _nonempty_text(row.get("SECURITY_CODE"))
    if trade_date is None or source_code != ticker or not (start <= trade_date <= end) or trade_date > today:
        return (
            None,
            "Eastmoney returned an out-of-window or future/mismatched-security row; it was filtered and coverage is partial.",
            False,
        )

    price = _number(row.get("DEAL_PRICE"))
    raw_volume = _number(row.get("DEAL_VOLUME"))
    raw_amount = _number(row.get("DEAL_AMT"))
    if price is None or raw_volume is None or raw_amount is None:
        return (
            None,
            "Eastmoney returned a row without numeric price, quantity, or amount; it was filtered and coverage is partial.",
            False,
        )
    quantity = raw_volume
    amount = raw_amount
    source_record_id = _stable_source_id(row)
    premium = _premium(
        source_value=_number(row.get("PREMIUM_RATIO")),
        price=price,
        ticker=ticker,
        trade_date=trade_date.isoformat(),
        reference_price_lookup=reference_price_lookup,
    )
    return (
        {
            "source_record_id": source_record_id,
            "trade_date": trade_date.isoformat(),
            "ticker": ticker,
            "security_name": _nonempty_text(row.get("SECURITY_NAME_ABBR")),
            "deal_price_cny_per_share": price,
            "deal_quantity_shares": quantity,
            "deal_amount_cny": amount,
            "raw_values": {"deal_volume": raw_volume, "deal_amount": raw_amount},
            "raw_units": dict(_RAW_UNITS),
            "premium": premium,
            "buyer_name": _nonempty_text(row.get("BUYER_NAME")),
            "seller_name": _nonempty_text(row.get("SELLER_NAME")),
            "source": _SOURCE,
            "fetched_at": fetched_at,
            "amount_check": _amount_check(price, quantity, amount),
        },
        None,
        source_record_id is None,
    )


def _premium(
    *,
    source_value: float | None,
    price: float | None,
    ticker: str,
    trade_date: str,
    reference_price_lookup: ReferencePriceLookup | None,
) -> dict[str, Any]:
    if source_value is not None:
        # The provider expresses PREMIUM_RATIO as a decimal fraction (verified
        # live: 301358 on 2026-09-11 returned -0.150046772685 for 45.43 vs a
        # 53.45 close).  Convert to percentage points so both branches of this
        # function emit the same unit for ``ratio_pct``.
        return {
            "ratio_pct": source_value * 100.0,
            "source": "eastmoney_PREMIUM_RATIO",
            "definition": "Eastmoney source field; the provider decimal fraction is converted to percentage points. Source sign convention retained (positive premium, negative discount).",
            "reference_price": None,
            "reference_date": None,
            "formula": "eastmoney_PREMIUM_RATIO * 100",
        }
    reference = reference_price_lookup(ticker, trade_date) if reference_price_lookup else None
    if reference is None or price is None:
        return {
            "ratio_pct": None,
            "source": "unavailable",
            "definition": "No source premium ratio and no same-day unadjusted reference price were available.",
            "reference_price": None,
            "reference_date": None,
            "formula": None,
        }
    try:
        reference_price, reference_date = reference
        reference_price = float(reference_price)
    except (TypeError, ValueError):
        reference_price = 0.0
        reference_date = None
    if not math.isfinite(reference_price) or reference_price <= 0 or reference_date != trade_date:
        return {
            "ratio_pct": None,
            "source": "unavailable",
            "definition": "Same-day unadjusted reference price was unavailable or could not be verified.",
            "reference_price": None,
            "reference_date": None,
            "formula": None,
        }
    return {
        "ratio_pct": (price / reference_price - 1) * 100,
        "source": "calculated_same_day_unadjusted_reference",
        "definition": "Positive is premium and negative is discount versus the same-day unadjusted reference price.",
        "reference_price": reference_price,
        "reference_date": reference_date,
        "formula": "(deal_price / unadjusted_reference_price - 1) * 100",
    }


def _amount_check(
    price: float | None, quantity: float | None, amount: float | None
) -> dict[str, Any]:
    implied = price * quantity if price is not None and quantity is not None else None
    difference = implied - amount if implied is not None and amount is not None else None
    tolerance = max(100.0, abs(amount or 0.0) * 0.0001)
    comparison = (
        "not_comparable"
        if difference is None
        else "within_source_rounding_tolerance"
        if abs(difference) <= tolerance
        else "outside_source_rounding_tolerance"
    )
    return {
        "price_times_quantity_cny": implied,
        "reported_amount_cny": amount,
        "difference_cny": difference,
        "comparison": comparison,
    }


def _attempt(
    status: str,
    observed_at: str,
    started: float | None = None,
    exc: Exception | None = None,
    *,
    duration_ms: int | None = None,
    record_count: int | None = None,
) -> ProviderAttempt:
    elapsed = duration_ms if duration_ms is not None else round((time.perf_counter() - (started or time.perf_counter())) * 1000)
    return ProviderAttempt(
        provider="eastmoney_datacenter",
        method=_REPORT_NAME,
        status=status,
        attempted_at=observed_at,
        duration_ms=max(0, elapsed),
        error_summary=(f"{type(exc).__name__}" if exc else None),
        record_count=record_count,
    )


def _stable_source_id(row: Mapping[str, Any]) -> str | None:
    for field in ("ID", "TRADE_ID", "BLOCKTRADE_ID"):
        value = _nonempty_text(row.get(field))
        if value is not None:
            return value
    return None


def _row_trade_date(value: Any) -> date | None:
    text = _nonempty_text(value)
    if text is None:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _nonempty_text(value: Any) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _parse_iso_date(value: str, name: str) -> date:
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise ValueError(f"{name} must be YYYY-MM-DD") from exc


def _positive_int(value: int, name: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise ValueError(f"{name} must be at least 1")
    return parsed


def _as_utc(value: datetime | None) -> datetime:
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None:
        return current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc)


def _ordered_unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))
