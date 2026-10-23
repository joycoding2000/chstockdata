"""The narrow provider port: canonical requests in, canonical results out.

The port never exposes vendor frames, vendor column names, batch conversion,
or fallback routing — those live inside adapters. Every method returns a
``ProviderSuccess`` of canonical records plus evidence, provider evidence, or
a typed ``ProviderFailure``; empty success and failure are distinct values.
"""

from dataclasses import dataclass
from datetime import date
from typing import Protocol, runtime_checkable

from systematic_investing.data.contracts import (
    ProviderEvidence,
    ProviderFailure,
    ProviderSuccess,
)
from systematic_investing.domain.identifiers import InstrumentId, require_session_date
from systematic_investing.domain.market import (
    AdjustmentMode,
    CorporateAction,
    DailyBar,
    TradabilityStatus,
    TradingSession,
)


class InvalidPortRequestError(ValueError):
    """Raised when a port request violates its contract."""


def _validated_universe(instrument_ids: tuple[InstrumentId, ...]) -> tuple[InstrumentId, ...]:
    if not instrument_ids or not all(isinstance(item, InstrumentId) for item in instrument_ids):
        raise InvalidPortRequestError("request universe must be non-empty InstrumentId values")
    return instrument_ids


def _validated_range(start_date: date, end_date: date) -> tuple[date, date]:
    require_session_date(start_date)
    require_session_date(end_date)
    if start_date > end_date:
        raise InvalidPortRequestError(
            f"request date range is inverted: {start_date} > {end_date}"
        )
    return start_date, end_date


@dataclass(frozen=True)
class DailyBarRequest:
    """Declare universe, date range, and adjustment intent; responses satisfy
    the canonical daily-bar schema."""

    instrument_ids: tuple[InstrumentId, ...]
    start_date: date
    end_date: date
    adjustment_mode: AdjustmentMode = AdjustmentMode.RAW

    def __post_init__(self) -> None:
        _validated_universe(self.instrument_ids)
        _validated_range(self.start_date, self.end_date)
        if not isinstance(self.adjustment_mode, AdjustmentMode):
            raise InvalidPortRequestError(
                f"adjustment_mode must be an AdjustmentMode, got {self.adjustment_mode!r}"
            )


@dataclass(frozen=True)
class CalendarRequest:
    """One named calendar identity over one date range; cross-exchange
    assumptions are forbidden."""

    calendar_id: str
    start_date: date
    end_date: date

    def __post_init__(self) -> None:
        if not isinstance(self.calendar_id, str) or not self.calendar_id:
            raise InvalidPortRequestError("calendar_id must be a non-empty string")
        _validated_range(self.start_date, self.end_date)


@dataclass(frozen=True)
class TradabilityRequest:
    """Point-in-time tradability for a universe on one session."""

    instrument_ids: tuple[InstrumentId, ...]
    session_date: date

    def __post_init__(self) -> None:
        _validated_universe(self.instrument_ids)
        require_session_date(self.session_date)


@dataclass(frozen=True)
class CorporateActionRequest:
    """Corporate actions and adjustment metadata for a universe over a range.

    ``instrument_kind`` is the declared instrument class the caller resolves
    through the Instrument Master — never inferred from the symbol. The
    vendor serves stocks and ETF/fund distributions through distinct
    reports, so the kind routes the vendor capability and binds the request
    identity; classification itself stays an Instrument Master fact.
    """

    instrument_ids: tuple[InstrumentId, ...]
    start_date: date
    end_date: date
    instrument_kind: str = "STOCK"

    def __post_init__(self) -> None:
        _validated_universe(self.instrument_ids)
        _validated_range(self.start_date, self.end_date)
        if self.instrument_kind not in ("STOCK", "ETF"):
            raise InvalidPortRequestError(
                "instrument_kind must be STOCK or ETF, got "
                f"{self.instrument_kind!r}"
            )


@runtime_checkable
class DataProviderPort(Protocol):
    """Market-data capability surface every adapter must satisfy."""

    def capability_evidence(self) -> ProviderEvidence | ProviderFailure:
        """Provider capability/version evidence for qualification records."""
        ...

    def fetch_daily_bars(
        self, request: DailyBarRequest
    ) -> ProviderSuccess[DailyBar] | ProviderFailure:
        """Canonical end-of-session bars, never vendor frames."""
        ...

    def fetch_calendar(
        self, request: CalendarRequest
    ) -> ProviderSuccess[TradingSession] | ProviderFailure:
        """Exchange-local session/open records for one calendar identity."""
        ...

    def fetch_tradability(
        self, request: TradabilityRequest
    ) -> ProviderSuccess[TradabilityStatus] | ProviderFailure:
        """Point-in-time tradability/suspension state."""
        ...

    def fetch_corporate_actions(
        self, request: CorporateActionRequest
    ) -> ProviderSuccess[CorporateAction] | ProviderFailure:
        """Versioned corporate actions and adjustment metadata."""
        ...
