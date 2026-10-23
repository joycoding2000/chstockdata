"""Live qualification helpers (opt-in release-environment runs only).

These helpers are imported only by the opt-in live tests. They require the
pinned ``chstockdata`` release installed with a local vipdoc tree; the package
needs no API keys, and no credentials or secret values are read, logged, or
recorded here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any

from systematic_investing.adapters.chstockdata.provider import (
    ChStockDataProvider,
    LibraryChStockDataClient,
)
from systematic_investing.data.ports import (
    CalendarRequest,
    CorporateActionRequest,
    DailyBarRequest,
    TradabilityRequest,
)
from systematic_investing.domain.identifiers import InstrumentId

MARKET_TIMEZONE = timezone(timedelta(hours=8))


def live_provider() -> ChStockDataProvider:
    """A provider over the real pinned vendor library and wall-clock retrieval."""
    client = LibraryChStockDataClient()
    return ChStockDataProvider(client=client, clock=lambda: datetime.now(MARKET_TIMEZONE))


@dataclass(frozen=True)
class MatrixRequest:
    """One matrix instrument with every live capability request prepared."""

    subtype: str
    instrument_id: InstrumentId
    bar_request: DailyBarRequest
    calendar_request: CalendarRequest
    tradability_request: TradabilityRequest
    corporate_action_request: CorporateActionRequest


def matrix_requests(
    matrix: dict[str, Any],
    *,
    window: dict[str, str] | None = None,
    evaluation_session: str | None = None,
) -> tuple[MatrixRequest, ...]:
    """Build live requests for every approved matrix instrument."""
    resolved_window = window or matrix["window"]
    start = date.fromisoformat(resolved_window["start"])
    end = date.fromisoformat(resolved_window["end"])
    session = date.fromisoformat(evaluation_session or matrix["evaluation_session"])
    requests: list[MatrixRequest] = []
    for entry in matrix["subtypes"]:
        for instrument in entry["instruments"]:
            instrument_id = InstrumentId.parse(instrument["instrument_id"])
            requests.append(
                MatrixRequest(
                    subtype=entry["subtype"],
                    instrument_id=instrument_id,
                    bar_request=DailyBarRequest(
                        instrument_ids=(instrument_id,), start_date=start, end_date=end
                    ),
                    calendar_request=CalendarRequest(
                        calendar_id=instrument_id.exchange.value,
                        start_date=start,
                        end_date=end,
                    ),
                    tradability_request=TradabilityRequest(
                        instrument_ids=(instrument_id,), session_date=session
                    ),
                    corporate_action_request=CorporateActionRequest(
                        instrument_ids=(instrument_id,),
                        start_date=start,
                        end_date=end,
                        instrument_kind="ETF",
                    ),
                )
            )
    return tuple(requests)
