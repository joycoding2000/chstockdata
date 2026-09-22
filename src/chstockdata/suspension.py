"""Structured Eastmoney suspension snapshot retrieval.

The upstream endpoint is one market-wide snapshot per date.  Its provider
observation is deliberately cached with the completed snapshot so a second
ticker lookup reuses the original attempt rather than claiming a new fetch.
"""

from __future__ import annotations

import math
import time
from collections.abc import Mapping
from datetime import date
from typing import Any

from . import a_stock as _legacy_a_stock
from .fetch_result import (
    FETCH_FAILED_NETWORK,
    FETCH_FAILED_STRUCTURE,
    FETCH_NORMAL_EMPTY,
    FETCH_SUCCESS,
    FetchAttempt,
    FetchMetadata,
    FetchResult,
)
from .routing_observation import elapsed_ms, record_fetch_observation, utc_now_iso

_PROVIDER = "eastmoney"
_PROVIDER_CAPABILITY = "eastmoney:suspension_snapshot"
_CAPABILITY = "suspension"

# Keep the historic cache object so existing cache-reset test seams retain
# their meaning. Keying by the live request callable is intentional: tests
# monkeypatch ``a_stock._em_get`` and must not inherit another transport's
# snapshot.
_suspension_snapshot_cache: dict[tuple[str, Any], dict[str, Any]] = _legacy_a_stock._suspension_snapshot_cache


def _astock():
    """Return the legacy endpoint helpers used by the single provider."""
    return _legacy_a_stock


def _snapshot_failure(
    *,
    status: str,
    reason: str,
    rows: list[Mapping[str, Any]],
    reported_count: int | None,
    snapshot_pages: int,
    attempts: list[FetchAttempt],
    started_at: str,
    elapsed: int,
) -> dict[str, Any]:
    record_fetch_observation(
        attempts,
        provider=_PROVIDER,
        capability_id=_PROVIDER_CAPABILITY,
        status=status,
        started_at=started_at,
        elapsed_ms=elapsed,
        record_count=len(rows) if rows else None,
        error_type=reason,
        message=reason,
        error_summary=reason,
    )
    return {
        "status": status,
        "reason": reason,
        "rows": rows,
        "reported_count": reported_count,
        "snapshot_pages": snapshot_pages,
        "attempts": attempts,
        "retrieved_at": utc_now_iso(),
    }


def _fetch_suspension_snapshot_uncached(snapshot_date: str) -> dict[str, Any]:
    """Fetch, page, and validate one full snapshot; record exactly once."""
    astock = _astock()
    attempts: list[FetchAttempt] = []
    clock = time.monotonic
    started = clock()
    started_at = utc_now_iso()
    raw_rows: list[Mapping[str, Any]] = []
    reported_count: int | None = None
    snapshot_pages = 0
    try:
        raw_rows, reported_count = astock._suspension_snapshot_page(snapshot_date, 1)
        snapshot_pages = 1
        if reported_count is None:
            if len(raw_rows) >= astock._SUSPEND_PAGE_SIZE:
                return _snapshot_failure(
                    status=FETCH_FAILED_STRUCTURE,
                    reason="snapshot_count_missing",
                    rows=list(raw_rows),
                    reported_count=None,
                    snapshot_pages=snapshot_pages,
                    attempts=attempts,
                    started_at=started_at,
                    elapsed=elapsed_ms(clock, started),
                )
            reported_count = len(raw_rows)
        reported_count = max(reported_count, len(raw_rows))
        expected_pages = max(1, math.ceil(reported_count / astock._SUSPEND_PAGE_SIZE))
        pages_to_fetch = min(expected_pages, astock._SUSPEND_MAX_PAGES)
        for page in range(2, pages_to_fetch + 1):
            page_rows, page_count = astock._suspension_snapshot_page(snapshot_date, page)
            raw_rows.extend(page_rows)
            snapshot_pages = page
            if page_count is not None:
                reported_count = max(reported_count, page_count)

        if expected_pages > astock._SUSPEND_MAX_PAGES or len(raw_rows) < reported_count:
            return _snapshot_failure(
                status=FETCH_FAILED_STRUCTURE,
                reason="snapshot_truncated",
                rows=list(raw_rows),
                reported_count=reported_count,
                snapshot_pages=pages_to_fetch,
                attempts=attempts,
                started_at=started_at,
                elapsed=elapsed_ms(clock, started),
            )

    except (astock._requests.RequestException, TimeoutError, ConnectionError) as exc:
        return _snapshot_failure(
            status=FETCH_FAILED_NETWORK,
            reason=type(exc).__name__,
            rows=[],
            reported_count=None,
            snapshot_pages=0,
            attempts=attempts,
            started_at=started_at,
            elapsed=elapsed_ms(clock, started),
        )
    except (ValueError, TypeError, astock._json.JSONDecodeError) as exc:
        return _snapshot_failure(
            status=FETCH_FAILED_STRUCTURE,
            reason=type(exc).__name__,
            rows=[],
            reported_count=None,
            snapshot_pages=0,
            attempts=attempts,
            started_at=started_at,
            elapsed=elapsed_ms(clock, started),
        )
    except Exception as exc:  # noqa: BLE001 - legacy contract classifies unknown failures as network
        return _snapshot_failure(
            status=FETCH_FAILED_NETWORK,
            reason=type(exc).__name__,
            rows=[],
            reported_count=None,
            snapshot_pages=0,
            attempts=attempts,
            started_at=started_at,
            elapsed=elapsed_ms(clock, started),
        )

    record_fetch_observation(
        attempts,
        provider=_PROVIDER,
        capability_id=_PROVIDER_CAPABILITY,
        status=FETCH_SUCCESS,
        started_at=started_at,
        elapsed_ms=elapsed_ms(clock, started),
        record_count=len(raw_rows),
    )
    return {
        "status": FETCH_SUCCESS,
        "reason": None,
        "rows": list(raw_rows),
        "reported_count": reported_count,
        "snapshot_pages": snapshot_pages,
        "attempts": attempts,
        "retrieved_at": utc_now_iso(),
    }


def _load_suspension_snapshot(snapshot_date: str) -> dict[str, Any]:
    """Return the cached snapshot, preserving its original provenance."""
    astock = _astock()
    cache_key = (snapshot_date, astock._em_get)
    with astock._suspension_snapshot_cache_lock:
        cached = _suspension_snapshot_cache.get(cache_key)
        if cached is None:
            cached = _fetch_suspension_snapshot_uncached(snapshot_date)
            _suspension_snapshot_cache[cache_key] = cached
        return cached


def _result_from_snapshot(snapshot_date: str, snapshot: dict[str, Any], code: str) -> FetchResult[dict]:
    """Derive a ticker result without turning its absence into provider empty."""
    astock = _astock()
    provider_ok = snapshot["status"] == FETCH_SUCCESS
    rows = snapshot["rows"]
    matched = next(
        (
            row for row in rows
            if astock._dc_row_text(row, "SECURITY_CODE", "security_code") == code
        ),
        None,
    ) if provider_ok else None
    outcome_status = FETCH_SUCCESS if matched is not None else FETCH_NORMAL_EMPTY
    derivation_reason: str | None = None
    data: dict[str, Any]
    if not provider_ok:
        outcome_status = snapshot["status"]
        data = {}
    elif matched is None:
        data = {
            "suspended": False,
            "security_name": None,
            "suspend_start_date": None,
            "suspend_start_time": None,
            "suspend_expire": None,
            "suspend_reason": None,
            "trade_market": None,
            "predict_resume_date": None,
            "snapshot_date": snapshot_date,
            "snapshot_rows": len(rows),
            "reported_count": snapshot["reported_count"],
            "snapshot_pages": snapshot["snapshot_pages"],
        }
    else:
        start_date = astock._dc_row_date(
            astock._dc_row_field(
                matched, "SUSPEND_START_DATE", "suspend_start_date"
            )
        )
        if start_date is None:
            outcome_status = FETCH_FAILED_STRUCTURE
            derivation_reason = "ValueError"
            data = {}
        else:
            data = {
                "suspended": True,
                "security_name": astock._dc_row_text(matched, "SECURITY_NAME_ABBR", "security_name_abbr", limit=20),
                "suspend_start_date": start_date,
                "suspend_start_time": astock._dc_row_text(matched, "SUSPEND_START_TIME", "suspend_start_time"),
                "suspend_expire": astock._dc_row_text(matched, "SUSPEND_EXPIRE", "suspend_expire", limit=30),
                "suspend_reason": astock._dc_row_text(matched, "SUSPEND_REASON", "suspend_reason", limit=80),
                "trade_market": astock._dc_row_text(matched, "TRADE_MARKET", "trade_market", limit=20),
                "predict_resume_date": astock._dc_row_date(astock._dc_row_field(matched, "PREDICT_RESUME_DATE", "predict_resume_date")),
                "snapshot_date": snapshot_date,
                "snapshot_rows": len(rows),
                "reported_count": snapshot["reported_count"],
                "snapshot_pages": snapshot["snapshot_pages"],
            }
    metadata = FetchMetadata(
        capability=_CAPABILITY,
        final_provider=_PROVIDER if provider_ok else None,
        retrieved_at=snapshot["retrieved_at"],
        observed_at=None,
        data_as_of=snapshot_date if provider_ok else None,
        limitations=[snapshot["reason"] or derivation_reason]
        if snapshot["reason"] or derivation_reason
        else [],
        attempts=list(snapshot["attempts"]),
        providers_used=[_PROVIDER] if provider_ok else [],
        outcome_status=outcome_status,
    )
    return FetchResult(data=data, metadata=metadata)


def fetch_suspension_info(ticker: str, curr_date: str) -> FetchResult[dict]:
    """Return a structured per-ticker view of Eastmoney's date snapshot."""
    astock = _astock()
    try:
        code = astock._normalize_ticker(ticker)
        snapshot_date = date.fromisoformat(str(curr_date)[:10]).isoformat()
    except (TypeError, ValueError) as exc:
        metadata = FetchMetadata(
            capability=_CAPABILITY,
            final_provider=None,
            retrieved_at=utc_now_iso(),
            limitations=[type(exc).__name__],
            attempts=[],
            providers_used=[],
            outcome_status=FETCH_FAILED_STRUCTURE,
        )
        return FetchResult(data={}, metadata=metadata)
    return _result_from_snapshot(snapshot_date, _load_suspension_snapshot(snapshot_date), code)


__all__ = ["fetch_suspension_info"]
