"""Conservative tradability verdict derived from calendar and suspension."""

from __future__ import annotations

from typing import Any, Mapping

from .fetch_result import (
    FETCH_FAILED_NETWORK,
    FETCH_FAILED_RATE_LIMIT,
    FETCH_FAILED_STRUCTURE,
    FETCH_NORMAL_EMPTY,
    FETCH_SUCCESS,
    FetchMetadata,
    FetchResult,
)
from .routing_observation import utc_now_iso
from .suspension import fetch_suspension_info
from .trading_calendar import fetch_trading_calendar, is_trading_day


_CAPABILITY = "tradability"
_HARD_FAILURES = frozenset(
    {
        FETCH_FAILED_NETWORK,
        FETCH_FAILED_RATE_LIMIT,
        FETCH_FAILED_STRUCTURE,
    }
)


def _verdict(
    ticker: str,
    curr_date: str,
    *,
    tradable: bool | None,
    market_open: bool | None,
    suspended: bool | None,
    reason: str,
) -> dict[str, Any]:
    return {
        "ticker": ticker,
        "date": curr_date,
        "tradable": tradable,
        "market_open": market_open,
        "suspended": suspended,
        "reason": reason,
    }


def _unknown_status(metadata: FetchMetadata) -> str:
    """Keep an upstream failure; downgrade an unusable success to normal-empty."""

    status = metadata.request_status
    return FETCH_NORMAL_EMPTY if status == FETCH_SUCCESS else status


def _derived_metadata(
    curr_date: str,
    child_results: list[FetchResult[Any]],
    *,
    known: bool,
    request_status: str,
) -> FetchMetadata:
    attempts = []
    providers_used = []
    limitations = []
    for child in child_results:
        attempts.extend(child.metadata.attempts)
        providers_used.extend(child.metadata.providers_used)
        limitations.extend(child.metadata.limitations)

    return FetchMetadata(
        capability=_CAPABILITY,
        final_provider=None,
        retrieved_at=utc_now_iso(),
        data_as_of=curr_date if known else None,
        stale=any(child.metadata.stale for child in child_results),
        partial=any(child.metadata.partial for child in child_results),
        limitations=limitations,
        attempts=attempts,
        providers_used=providers_used,
        outcome_status=request_status,
    )


def _result(
    data: dict[str, Any],
    curr_date: str,
    child_results: list[FetchResult[Any]],
    *,
    known: bool,
    request_status: str,
) -> FetchResult[dict]:
    return FetchResult(
        data=data,
        metadata=_derived_metadata(
            curr_date,
            child_results,
            known=known,
            request_status=request_status,
        ),
    )


def fetch_tradability(
    ticker: str,
    curr_date: str,
    *,
    root: Any = None,
) -> FetchResult[dict]:
    """Return a conservative per-ticker tradability verdict for one date.

    A calendar answer is authoritative about whether the market is open.  A
    suspension snapshot is consulted only after the calendar confirms a
    trading day; it can therefore refine an open-day answer but can never
    establish market openness by itself.
    """

    requested_date = str(curr_date)
    calendar_result = fetch_trading_calendar(root=root, today=requested_date)
    child_results: list[FetchResult[Any]] = [calendar_result]
    if calendar_result.metadata.request_status != FETCH_SUCCESS:
        return _result(
            _verdict(
                ticker,
                requested_date,
                tradable=None,
                market_open=None,
                suspended=None,
                reason="calendar_unknown",
            ),
            requested_date,
            child_results,
            known=False,
            request_status=_unknown_status(calendar_result.metadata),
        )

    calendar_open = is_trading_day(calendar_result.data, requested_date)

    if calendar_open is False and not calendar_result.metadata.partial:
        return _result(
            _verdict(
                ticker,
                requested_date,
                tradable=False,
                market_open=False,
                suspended=None,
                reason="market_closed",
            ),
            requested_date,
            child_results,
            known=True,
            request_status=FETCH_SUCCESS,
        )

    if calendar_open is not True:
        return _result(
            _verdict(
                ticker,
                requested_date,
                tradable=None,
                market_open=None,
                suspended=None,
                reason="calendar_unknown",
            ),
            requested_date,
            child_results,
            known=False,
            request_status=_unknown_status(calendar_result.metadata),
        )

    suspension_result = fetch_suspension_info(ticker, requested_date)
    child_results.append(suspension_result)
    suspension_status = suspension_result.metadata.request_status
    suspension_data = suspension_result.data
    suspended = (
        suspension_data.get("suspended")
        if isinstance(suspension_data, Mapping)
        else None
    )

    if suspension_status == FETCH_NORMAL_EMPTY or (
        suspension_status == FETCH_SUCCESS and suspended is False
    ):
        return _result(
            _verdict(
                ticker,
                requested_date,
                tradable=True,
                market_open=True,
                suspended=False,
                reason="open_not_suspended",
            ),
            requested_date,
            child_results,
            known=True,
            request_status=FETCH_SUCCESS,
        )

    if suspension_status == FETCH_SUCCESS and suspended is True:
        return _result(
            _verdict(
                ticker,
                requested_date,
                tradable=False,
                market_open=True,
                suspended=True,
                reason="suspended",
            ),
            requested_date,
            child_results,
            known=True,
            request_status=FETCH_SUCCESS,
        )

    request_status = (
        suspension_status
        if suspension_status in _HARD_FAILURES
        else _unknown_status(suspension_result.metadata)
    )
    return _result(
        _verdict(
            ticker,
            requested_date,
            tradable=None,
            market_open=True,
            suspended=None,
            reason="suspension_unknown",
        ),
        requested_date,
        child_results,
        known=False,
        request_status=request_status,
    )


__all__ = ["fetch_tradability"]
