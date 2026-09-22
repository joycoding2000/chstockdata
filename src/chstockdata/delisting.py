"""Structured exchange-official delisting status retrieval.

This module is the structured vertical slice for the legacy
``get_delisting_info`` endpoint.  It keeps the existing SSE/SZSE terminated
listing sources and the existing same-day ``delist-list.json`` cache format.
The result is intentionally narrower than listing or tradability status:
``eligible_by_delisting`` only means that the stock was not excluded by the
covered official terminated-listing reference.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import time
from typing import Any, Callable, Mapping

from .fetch_result import (
    FETCH_FAILED_NETWORK,
    FETCH_FAILED_RATE_LIMIT,
    FETCH_FAILED_STRUCTURE,
    FETCH_NORMAL_EMPTY,
    FETCH_SUCCESS,
    FetchAttempt,
    FetchMetadata,
    FetchResult,
)
from .routing_observation import (
    elapsed_ms,
    record_fetch_observation,
    utc_now_iso,
)
from .vendor_errors import exception_to_fetch_status

__all__ = ["fetch_delisting_status"]


_CAPABILITY = "delisting"
_PROVIDERS: tuple[tuple[str, str], ...] = (
    ("sse", "sse:delisting"),
    ("szse", "szse:delisting"),
)
_HARD_FAILURES = frozenset(
    {
        FETCH_FAILED_NETWORK,
        FETCH_FAILED_RATE_LIMIT,
        FETCH_FAILED_STRUCTURE,
    }
)


def _astock():
    """Return legacy seams without importing ``a_stock`` during its import."""
    from . import a_stock

    return a_stock


def _source_http_get(*args, **kwargs):
    """Use the existing source HTTP boundary (and its host hooks/retries)."""
    return _astock()._source_http_get(*args, **kwargs)


def _normalize_ticker(ticker: str) -> str:
    return _astock()._normalize_ticker(ticker)


def _delist_market_for(code: str) -> str:
    return _astock()._delist_market_for(code)


def _today():
    return _astock()._today()


def _market_observed_at() -> str:
    astock = _astock()
    return datetime.now(astock._MARKET_TZ).isoformat(timespec="seconds")


def _delist_cache_path() -> str:
    """Keep the legacy cache location seam and file name unchanged."""
    return _astock()._delist_cache_path()


def _sse_delist_rows(http_get) -> list[dict[str, Any]]:
    """Reuse the existing SSE parser and endpoint shape."""
    return _astock()._sse_delist_rows(http_get)


def _szse_delist_rows(http_get) -> list[dict[str, Any]]:
    """Reuse the existing SZSE parser and endpoint shape."""
    return _astock()._szse_delist_rows(http_get)


@dataclass(frozen=True)
class _ReferenceSnapshot:
    rows: list[dict[str, Any]]
    statuses: dict[str, str]
    attempts: list[FetchAttempt]
    observed_at: str
    reference_date: str
    cache_hit: bool

    @property
    def failed_sources(self) -> list[str]:
        return [
            provider
            for provider, _capability in _PROVIDERS
            if self.statuses.get(provider) in _HARD_FAILURES
        ]


@dataclass(frozen=True)
class _LegacyContext:
    reference_rows: int = 0
    failed_sources: tuple[str, ...] = ()
    observed_at: str | None = None
    reference_date: str | None = None


def _read_same_day_cache() -> _ReferenceSnapshot | None:
    """Read the current legacy cache without producing provider observations."""
    cache_date = _today().isoformat()
    try:
        with open(_delist_cache_path(), encoding="utf-8") as handle:
            cached = json.load(handle)
    except (OSError, ValueError):
        return None

    rows = cached.get("rows") if isinstance(cached, Mapping) else None
    if not (
        isinstance(cached, Mapping)
        and cached.get("cache_date") == cache_date
        and isinstance(rows, list)
        and rows
        and all(isinstance(row, Mapping) for row in rows)
    ):
        return None

    # Copy mappings into ordinary dicts so the payload is stable and cannot
    # retain a custom JSON-decoder mapping implementation.
    normalized_rows = [dict(row) for row in rows]
    return _ReferenceSnapshot(
        rows=normalized_rows,
        statuses={provider: FETCH_SUCCESS for provider, _ in _PROVIDERS},
        attempts=[],
        observed_at=str(cached.get("observed_at") or _market_observed_at()),
        reference_date=cache_date,
        cache_hit=True,
    )


def _write_same_day_cache(
    *,
    reference_date: str,
    observed_at: str,
    rows: list[dict[str, Any]],
) -> None:
    """Write exactly the existing ``delist-list.json`` envelope."""
    if not rows:
        return
    try:
        payload = json.dumps(
            {
                "cache_date": reference_date,
                "observed_at": observed_at,
                "rows": rows,
            },
            ensure_ascii=False,
        )
        with open(_delist_cache_path(), "w", encoding="utf-8") as handle:
            handle.write(payload)
    except OSError:
        # A cache write is an optimization; a successful source fetch remains
        # a successful request when the disk is unavailable.
        return


def _observe_source(
    provider: str,
    capability_id: str,
    parser: Callable[[Callable[..., Any]], list[dict[str, Any]]],
    attempts: list[FetchAttempt],
) -> tuple[str, list[dict[str, Any]]]:
    """Fetch one official source and record exactly one provider observation."""
    started = time.monotonic()
    started_at = utc_now_iso()
    try:
        rows = parser(_source_http_get)
        if not isinstance(rows, list) or not all(isinstance(row, Mapping) for row in rows):
            raise ValueError(f"{provider} delisting rows must be a list of objects")
        normalized_rows = [dict(row) for row in rows]
    except Exception as exc:  # noqa: BLE001 - shared taxonomy owns classification
        status = exception_to_fetch_status(exc)
        record_fetch_observation(
            attempts,
            provider=provider,
            capability_id=capability_id,
            status=status,
            started_at=started_at,
            elapsed_ms=elapsed_ms(time.monotonic, started),
            error_type=type(exc).__name__,
            message=str(exc),
            error_summary=str(exc),
        )
        return status, []

    record_fetch_observation(
        attempts,
        provider=provider,
        capability_id=capability_id,
        status=FETCH_SUCCESS,
        started_at=started_at,
        elapsed_ms=elapsed_ms(time.monotonic, started),
        record_count=len(normalized_rows),
    )
    return FETCH_SUCCESS, normalized_rows


def _fetch_reference() -> _ReferenceSnapshot:
    cached = _read_same_day_cache()
    if cached is not None:
        return cached

    attempts: list[FetchAttempt] = []
    statuses: dict[str, str] = {}
    rows: list[dict[str, Any]] = []
    fetchers = {
        "sse": _sse_delist_rows,
        "szse": _szse_delist_rows,
    }
    for provider, capability_id in _PROVIDERS:
        status, source_rows = _observe_source(
            provider,
            capability_id,
            fetchers[provider],
            attempts,
        )
        statuses[provider] = status
        if status == FETCH_SUCCESS:
            rows.extend(source_rows)

    reference_date = _today().isoformat()
    observed_at = _market_observed_at()
    snapshot = _ReferenceSnapshot(
        rows=rows,
        statuses=statuses,
        attempts=attempts,
        observed_at=observed_at,
        reference_date=reference_date,
        cache_hit=False,
    )
    if all(statuses.get(provider) == FETCH_SUCCESS for provider, _ in _PROVIDERS):
        _write_same_day_cache(
            reference_date=reference_date,
            observed_at=observed_at,
            rows=rows,
        )
    return snapshot


def _payload(
    ticker: str,
    market: str,
    *,
    delisted: bool | None,
    eligible_by_delisting: bool | None,
    record: dict[str, Any] | None,
    reference_date: str | None,
) -> dict[str, Any]:
    """Build the deliberately minimal public structured payload."""
    return {
        "ticker": ticker,
        "market": market,
        "coverage": "covered" if market in {"sh", "sz"} else "uncovered",
        "delisted": delisted,
        "eligible_by_delisting": eligible_by_delisting,
        "record": record,
        "reference_date": reference_date,
    }


def _metadata(
    snapshot: _ReferenceSnapshot | None,
    *,
    outcome_status: str,
    data_as_of: str | None,
    limitations: list[str] | None = None,
    attempts: list[FetchAttempt] | None = None,
    providers_used: list[str] | None = None,
) -> FetchMetadata:
    attempts = list(attempts if attempts is not None else (snapshot.attempts if snapshot else []))
    providers_used = list(
        providers_used
        if providers_used is not None
        else (
            [provider for provider, _ in _PROVIDERS if snapshot and snapshot.statuses.get(provider) == FETCH_SUCCESS]
            if snapshot
            else []
        )
    )
    return FetchMetadata(
        capability=_CAPABILITY,
        final_provider=providers_used[0] if len(providers_used) == 1 else None,
        retrieved_at=utc_now_iso(),
        observed_at=snapshot.observed_at if snapshot else None,
        data_as_of=data_as_of,
        partial=bool(snapshot and snapshot.failed_sources and providers_used),
        limitations=list(limitations or ()),
        attempts=attempts,
        providers_used=providers_used,
        outcome_status=outcome_status,
    )


def _fetch_delisting_status(ticker: str) -> tuple[FetchResult[dict], _LegacyContext]:
    try:
        code = _normalize_ticker(ticker)
    except (TypeError, ValueError) as exc:
        result = FetchResult(
            data={},
            metadata=_metadata(
                None,
                outcome_status=FETCH_FAILED_STRUCTURE,
                data_as_of=None,
                limitations=[type(exc).__name__],
                attempts=[],
                providers_used=[],
            ),
        )
        return result, _LegacyContext()

    market = _delist_market_for(code)
    if market == "bse":
        result = FetchResult(
            data=_payload(
                code,
                market,
                delisted=None,
                eligible_by_delisting=None,
                record=None,
                reference_date=None,
            ),
            metadata=_metadata(
                None,
                outcome_status=FETCH_NORMAL_EMPTY,
                data_as_of=None,
                limitations=["market_uncovered"],
                attempts=[],
                providers_used=[],
            ),
        )
        return result, _LegacyContext()

    snapshot = _fetch_reference()
    own_provider = "sse" if market == "sh" else "szse"
    own_status = snapshot.statuses.get(own_provider, FETCH_FAILED_NETWORK)
    failed_sources = snapshot.failed_sources
    limitations: list[str] = []

    if own_status in _HARD_FAILURES:
        limitations.append(f"own_market_source_failed:{own_provider}")
        for provider in failed_sources:
            if provider != own_provider:
                limitations.append(f"cross_market_source_failed:{provider}")
        result = FetchResult(
            data={},
            metadata=_metadata(
                snapshot,
                outcome_status=own_status,
                data_as_of=None,
                limitations=limitations,
            ),
        )
        return result, _LegacyContext(
            reference_rows=len(snapshot.rows),
            failed_sources=tuple(failed_sources),
            observed_at=snapshot.observed_at,
            reference_date=snapshot.reference_date,
        )

    for provider in failed_sources:
        if provider != own_provider:
            limitations.append(f"cross_market_source_failed:{provider}")

    matched = next(
        (
            row
            for row in snapshot.rows
            if row.get("code") == code and row.get("market") == market
        ),
        None,
    )
    outcome_status = FETCH_SUCCESS if matched is not None else FETCH_NORMAL_EMPTY
    result = FetchResult(
        data=_payload(
            code,
            market,
            delisted=matched is not None,
            eligible_by_delisting=matched is None,
            record=dict(matched) if matched is not None else None,
            reference_date=snapshot.reference_date,
        ),
        metadata=_metadata(
            snapshot,
            outcome_status=outcome_status,
            data_as_of=snapshot.reference_date,
            limitations=(["reference_cache_hit"] if snapshot.cache_hit else []) + limitations,
        ),
    )
    return result, _LegacyContext(
        reference_rows=len(snapshot.rows),
        failed_sources=tuple(failed_sources),
        observed_at=snapshot.observed_at,
        reference_date=snapshot.reference_date,
    )


def fetch_delisting_status(ticker: str) -> FetchResult[dict]:
    """Return official terminated-listing status for one A-share ticker.

    ``eligible_by_delisting=True`` means only that the ticker was not found in
    the covered official terminated-listing reference.  It is not a claim
    that the security is currently listed or tradable.
    """
    return _fetch_delisting_status(ticker)[0]


def render_legacy_delisting_info(ticker: str) -> str:
    """Render the unchanged legacy JSON/string envelope."""
    result, context = _fetch_delisting_status(ticker)
    astock = _astock()
    label = astock._DELIST_LABEL
    request_status = result.metadata.request_status

    # ``FetchResult`` has no invalid-input status; preserve the old marker and
    # envelope at this compatibility boundary when validation produced no
    # provider attempt.
    if request_status == "failed_structure" and not result.metadata.attempts:
        reason = result.metadata.limitations[0] if result.metadata.limitations else "ValueError"
        return astock._dc_result("invalid_input", label, reason=reason)

    if result.data.get("market") == "bse":
        return astock._dc_result(
            "normal_empty",
            label,
            source="SSE/SZSE exchange official terminated listings",
            observed_at=context.observed_at or _market_observed_at(),
            as_of_date=_today().isoformat(),
            searched_market="bse",
            coverage_note="北交所退市名单无沪深交易所官方零鉴权来源，本工具未覆盖；未覆盖不是未退市。",
            delisted=None,
            record=None,
        )

    if not result.data and request_status in _HARD_FAILURES:
        # The legacy implementation classified every source exception as a
        # failed_network envelope, even when parsing failed.  Keep that public
        # behavior while the structured layer retains the finer status.
        return astock._dc_result(
            "failed_network",
            label,
            reason="reference_source_unavailable",
            failed_sources=list(context.failed_sources),
        )

    data = result.data
    legacy_payload = {
        "source": "SSE/SZSE exchange official terminated listings",
        "observed_at": context.observed_at or result.metadata.observed_at,
        "as_of_date": _today().isoformat(),
        "reference_date": data.get("reference_date"),
        "searched_market": data.get("market"),
        "reference_rows": context.reference_rows,
        "cross_market_source_failed": bool(context.failed_sources),
        "delisted": data.get("delisted"),
        "record": data.get("record"),
    }
    if data.get("delisted") is False:
        legacy_payload["coverage_note"] = "在覆盖市场内未命中退市名单；名单为交易所官方已终止上市板，不含在市股票。"
    return astock._dc_result(request_status, label, **legacy_payload)
