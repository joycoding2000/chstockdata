"""Canonical market-data objects: daily bars, sessions, tradability, actions.

Canonical records carry explicit identity, units, adjustment mode, and the
point-in-time availability triplet. Point-in-time access uses only
``information_available_at``; ``retrieved_at`` never substitutes for it and an
``UNKNOWN`` availability basis never acquires a fabricated exact time.
"""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from systematic_investing import BASE_CURRENCY
from systematic_investing.domain.identifiers import InstrumentId, require_session_date
from systematic_investing.domain.money import Money


class MarketDataError(Exception):
    """Base class for canonical market-data contract errors."""


class InvalidDailyBarError(MarketDataError):
    """Raised when a daily bar violates the canonical schema invariants."""


class InvalidAvailabilityError(MarketDataError):
    """Raised when the point-in-time availability triplet is incoherent."""


class InvalidTradingSessionError(MarketDataError):
    """Raised when a trading session or calendar snapshot is inconsistent."""


class UnknownSessionError(MarketDataError):
    """Raised when the calendar snapshot cannot resolve a requested session."""


class InvalidTradabilityError(MarketDataError):
    """Raised when a tradability record violates the canonical contract."""


class InvalidCorporateActionError(MarketDataError):
    """Raised when a corporate-action record violates the canonical contract."""


CANONICAL_RECORD_SCHEMA_VERSION: str = "v1"
DAILY_BAR_SCHEMA_VERSION: str = CANONICAL_RECORD_SCHEMA_VERSION


class AdjustmentMode(StrEnum):
    """How prices on a record relate to executable market prices.

    ``RAW`` marks the canonical unadjusted execution bar; any derived adjusted
    analysis series must be a separate, explicitly declared contract.
    """

    RAW = "RAW"


class AvailabilityBasis(StrEnum):
    """How the information-availability time of a fact was established."""

    OBSERVED = "OBSERVED"
    EXCHANGE_RULE = "EXCHANGE_RULE"
    INFERRED = "INFERRED"
    UNKNOWN = "UNKNOWN"


def _require_aware_datetime(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise InvalidAvailabilityError(
            f"{field_name} must be a timezone-aware datetime, got {value!r}"
        )
    return value


@dataclass(frozen=True)
class Availability:
    """The point-in-time availability triplet shared by canonical facts.

    ``information_available_at`` is the earliest time a market participant
    could have known the fact and may be unknown. ``retrieved_at`` is when the
    current system acquired the record and never substitutes for PIT
    availability. An ``UNKNOWN`` basis and an exact information time are
    mutually exclusive: an unknown time must not be fabricated.
    """

    information_available_at: datetime | None
    retrieved_at: datetime
    availability_basis: AvailabilityBasis

    def __post_init__(self) -> None:
        if not isinstance(self.availability_basis, AvailabilityBasis):
            raise InvalidAvailabilityError(
                f"availability_basis must be an AvailabilityBasis, got "
                f"{self.availability_basis!r}"
            )
        _require_aware_datetime(self.retrieved_at, "retrieved_at")
        if self.information_available_at is not None:
            information_at = _require_aware_datetime(
                self.information_available_at, "information_available_at"
            )
            if self.availability_basis is AvailabilityBasis.UNKNOWN:
                raise InvalidAvailabilityError(
                    "availability_basis UNKNOWN must not carry a fabricated exact "
                    "information time"
                )
            if information_at > self.retrieved_at:
                raise InvalidAvailabilityError(
                    "information_available_at must not be after retrieved_at"
                )
        elif self.availability_basis is not AvailabilityBasis.UNKNOWN:
            raise InvalidAvailabilityError(
                f"availability_basis {self.availability_basis.value} requires "
                "information_available_at; unknown times must use the UNKNOWN basis"
            )

    def information_known_at(self, cutoff: datetime) -> bool | None:
        """Whether the fact was knowable at ``cutoff``, decided only from
        information availability. ``UNKNOWN`` availability yields ``None`` so
        a decision policy must handle it explicitly, never treat it as known."""
        cutoff = _require_aware_datetime(cutoff, "cutoff")
        if self.availability_basis is AvailabilityBasis.UNKNOWN:
            return None
        assert self.information_available_at is not None
        return self.information_available_at <= cutoff


@dataclass(frozen=True)
class AdjustmentFactor:
    """Optional adjustment factor with convention, version, and as-of date.

    Carried alongside RAW prices so a derived adjusted analysis series stays a
    declared contract and can never be confused with executable prices."""

    factor: Decimal
    convention: str
    version: str
    as_of: date

    def __post_init__(self) -> None:
        if (
            not isinstance(self.factor, Decimal)
            or not self.factor.is_finite()
            or self.factor <= 0
        ):
            raise InvalidDailyBarError(
                f"adjustment factor must be a finite positive Decimal, got {self.factor!r}"
            )
        for text_field in ("convention", "version"):
            value = getattr(self, text_field)
            if not isinstance(value, str) or not value:
                raise InvalidDailyBarError(f"{text_field} must be a non-empty string")
        require_session_date(self.as_of)


@dataclass(frozen=True)
class DailyBar:
    """Canonical end-of-session bar: raw executable prices with explicit units,
    adjustment metadata, and point-in-time availability.

    Required fields are never converted to zero: a missing ``pre_close`` stays
    ``None``, while a recorded zero volume/amount is a genuine zero."""

    schema_version: str
    instrument_id: InstrumentId
    session_date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    pre_close: Decimal | None
    volume: Decimal
    amount: Decimal
    currency: str
    volume_unit: str
    amount_unit: str
    adjustment_mode: AdjustmentMode
    adjustment_factor: AdjustmentFactor | None
    availability: Availability
    provider_evidence_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.schema_version, str) or not self.schema_version:
            raise InvalidDailyBarError("schema_version must be a non-empty string")
        if not isinstance(self.instrument_id, InstrumentId):
            raise InvalidDailyBarError("instrument_id must be an InstrumentId")
        require_session_date(self.session_date)
        for field_name in ("open", "high", "low", "close"):
            value = getattr(self, field_name)
            if not isinstance(value, Decimal) or not value.is_finite() or value <= 0:
                raise InvalidDailyBarError(
                    f"{field_name} must be a finite positive Decimal, got {value!r}"
                )
        lowest = min(self.low, self.open, self.close)
        highest = max(self.high, self.open, self.close)
        if self.low > lowest or self.high < highest:
            raise InvalidDailyBarError(
                "OHLC invariant violated: low must not exceed open/close and high "
                "must not fall below open/close"
            )
        if self.pre_close is not None:
            if not isinstance(self.pre_close, Decimal) or not self.pre_close.is_finite():
                raise InvalidDailyBarError("pre_close must be a finite Decimal or None")
            if self.pre_close <= 0:
                raise InvalidDailyBarError(
                    "pre_close must be positive when present; a missing value stays "
                    "None and is never converted to zero"
                )
        for field_name in ("volume", "amount"):
            value = getattr(self, field_name)
            if not isinstance(value, Decimal) or not value.is_finite() or value < 0:
                raise InvalidDailyBarError(
                    f"{field_name} must be a finite non-negative Decimal, got {value!r}"
                )
        if self.currency != BASE_CURRENCY:
            raise InvalidDailyBarError(
                f"M0 canonical bars are {BASE_CURRENCY}-denominated, got {self.currency!r}"
            )
        for field_name in ("volume_unit", "amount_unit", "provider_evidence_id"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value:
                raise InvalidDailyBarError(f"{field_name} must be a non-empty string")
        if not isinstance(self.adjustment_mode, AdjustmentMode):
            raise InvalidDailyBarError(
                f"adjustment_mode must be an AdjustmentMode, got {self.adjustment_mode!r}"
            )
        if self.adjustment_factor is not None and not isinstance(
            self.adjustment_factor, AdjustmentFactor
        ):
            raise InvalidDailyBarError("adjustment_factor must be an AdjustmentFactor or None")
        if not isinstance(self.availability, Availability):
            raise InvalidDailyBarError("availability must be an Availability")


@dataclass(frozen=True)
class TradingSession:
    """One exchange-local session of one named calendar snapshot."""

    calendar_id: str
    session_date: date
    is_open: bool
    note: str | None
    snapshot_version: str

    def __post_init__(self) -> None:
        if not isinstance(self.calendar_id, str) or not self.calendar_id:
            raise InvalidTradingSessionError("calendar_id must be a non-empty string")
        require_session_date(self.session_date)
        if not isinstance(self.snapshot_version, str) or not self.snapshot_version:
            raise InvalidTradingSessionError("snapshot_version must be a non-empty string")
        if self.note is not None and not isinstance(self.note, str):
            raise InvalidTradingSessionError("note must be a string or None")


@dataclass(frozen=True)
class MarketCalendar:
    """An immutable calendar snapshot; session resolution never assumes that
    another exchange's sessions align."""

    calendar_id: str
    snapshot_version: str
    sessions: tuple[TradingSession, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.calendar_id, str) or not self.calendar_id:
            raise InvalidTradingSessionError("calendar_id must be a non-empty string")
        if not isinstance(self.snapshot_version, str) or not self.snapshot_version:
            raise InvalidTradingSessionError("snapshot_version must be a non-empty string")
        if not isinstance(self.sessions, tuple) or not self.sessions:
            raise InvalidTradingSessionError("sessions must be a non-empty tuple")
        previous_date: date | None = None
        for trading_session in self.sessions:
            if not isinstance(trading_session, TradingSession):
                raise InvalidTradingSessionError("sessions must contain TradingSession records")
            if trading_session.calendar_id != self.calendar_id:
                raise InvalidTradingSessionError(
                    f"session on {trading_session.session_date} belongs to calendar "
                    f"{trading_session.calendar_id!r}, not {self.calendar_id!r}; "
                    "cross-exchange assumptions are forbidden"
                )
            if previous_date is not None and trading_session.session_date <= previous_date:
                raise InvalidTradingSessionError(
                    "session dates must be strictly increasing and unique"
                )
            previous_date = trading_session.session_date

    def session_on(self, session_date: date) -> TradingSession | None:
        require_session_date(session_date)
        for trading_session in self.sessions:
            if trading_session.session_date == session_date:
                return trading_session
        return None

    def next_session(self, after: date) -> TradingSession:
        """The earliest open session strictly after ``after``, resolved only
        from this snapshot; the snapshot end fails closed."""
        require_session_date(after)
        for trading_session in self.sessions:
            if trading_session.session_date > after and trading_session.is_open:
                return trading_session
        raise UnknownSessionError(
            f"calendar {self.calendar_id!r} snapshot {self.snapshot_version!r} has no "
            f"open session after {after}"
        )


class TradeSide(StrEnum):
    """Sides an order may take; tradability facts permit or block them."""

    BUY = "BUY"
    SELL = "SELL"


class TradabilityStatusKind(StrEnum):
    """Point-in-time tradability states. ``UNKNOWN`` is a real value: it is
    never treated as tradable and blocks exposure-increasing actions."""

    TRADABLE = "TRADABLE"
    SUSPENDED = "SUSPENDED"
    NOT_LISTED = "NOT_LISTED"
    DELISTED = "DELISTED"
    BUY_BLOCKED_UPPER_LIMIT = "BUY_BLOCKED_UPPER_LIMIT"
    SELL_BLOCKED_LOWER_LIMIT = "SELL_BLOCKED_LOWER_LIMIT"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class TradabilityStatus:
    """Point-in-time tradability of one instrument on one session."""

    instrument_id: InstrumentId
    session_date: date
    status: TradabilityStatusKind
    reason: str | None
    availability: Availability
    provenance: str

    def __post_init__(self) -> None:
        if not isinstance(self.instrument_id, InstrumentId):
            raise InvalidTradabilityError("instrument_id must be an InstrumentId")
        require_session_date(self.session_date)
        if not isinstance(self.status, TradabilityStatusKind):
            raise InvalidTradabilityError(
                f"status must be a TradabilityStatusKind, got {self.status!r}"
            )
        if self.reason is not None and (not isinstance(self.reason, str) or not self.reason):
            raise InvalidTradabilityError("reason must be a non-empty string or None")
        if not isinstance(self.availability, Availability):
            raise InvalidTradabilityError("availability must be an Availability")
        if not isinstance(self.provenance, str) or not self.provenance:
            raise InvalidTradabilityError("provenance must be a non-empty string")

    @property
    def permitted_sides(self) -> frozenset[TradeSide] | None:
        """Sides known to be permitted; ``None`` means the sides are unknown."""
        both = frozenset({TradeSide.BUY, TradeSide.SELL})
        return {
            TradabilityStatusKind.TRADABLE: both,
            TradabilityStatusKind.SUSPENDED: frozenset(),
            TradabilityStatusKind.NOT_LISTED: frozenset(),
            TradabilityStatusKind.DELISTED: frozenset(),
            TradabilityStatusKind.BUY_BLOCKED_UPPER_LIMIT: frozenset({TradeSide.SELL}),
            TradabilityStatusKind.SELL_BLOCKED_LOWER_LIMIT: frozenset({TradeSide.BUY}),
            TradabilityStatusKind.UNKNOWN: None,
        }[self.status]

    def permits(self, side: TradeSide) -> bool:
        """Whether ``side`` is known to be permitted. Unknown tradability
        permits nothing and must block exposure-increasing actions."""
        if not isinstance(side, TradeSide):
            raise InvalidTradabilityError(f"side must be a TradeSide, got {side!r}")
        permitted = self.permitted_sides
        return permitted is not None and side in permitted


class CorporateActionKind(StrEnum):
    """Versioned corporate-action kinds in M0 scope."""

    CASH_DIVIDEND = "CASH_DIVIDEND"
    SPLIT = "SPLIT"
    CONSOLIDATION = "CONSOLIDATION"
    DISTRIBUTION = "DISTRIBUTION"


@dataclass(frozen=True)
class CorporateAction:
    """Versioned, effective-dated corporate-action fact."""

    action_id: str
    instrument_id: InstrumentId
    action_kind: CorporateActionKind
    ex_date: date
    record_date: date | None
    pay_date: date | None
    cash_amount: Money | None
    share_ratio: Decimal | None
    revision: int
    availability: Availability
    provenance: str

    def __post_init__(self) -> None:
        if not isinstance(self.action_id, str) or not self.action_id:
            raise InvalidCorporateActionError("action_id must be a non-empty string")
        if not isinstance(self.instrument_id, InstrumentId):
            raise InvalidCorporateActionError("instrument_id must be an InstrumentId")
        if not isinstance(self.action_kind, CorporateActionKind):
            raise InvalidCorporateActionError(
                f"action_kind must be a CorporateActionKind, got {self.action_kind!r}"
            )
        require_session_date(self.ex_date)
        for field_name in ("record_date", "pay_date"):
            value = getattr(self, field_name)
            if value is not None:
                require_session_date(value)
        has_cash = self.cash_amount is not None
        has_ratio = self.share_ratio is not None
        if not has_cash and not has_ratio:
            raise InvalidCorporateActionError(
                "a corporate action must carry economic terms: cash_amount and/or "
                "share_ratio"
            )
        if has_cash and not isinstance(self.cash_amount, Money):
            raise InvalidCorporateActionError("cash_amount must be Money or None")
        if has_ratio:
            if not isinstance(self.share_ratio, Decimal) or not self.share_ratio.is_finite():
                raise InvalidCorporateActionError("share_ratio must be a finite Decimal")
            if self.share_ratio <= 0:
                raise InvalidCorporateActionError("share_ratio must be positive")
        if (
            not isinstance(self.revision, int)
            or isinstance(self.revision, bool)
            or self.revision < 1
        ):
            raise InvalidCorporateActionError("revision must be a positive integer")
        if not isinstance(self.availability, Availability):
            raise InvalidCorporateActionError("availability must be an Availability")
        if not isinstance(self.provenance, str) or not self.provenance:
            raise InvalidCorporateActionError("provenance must be a non-empty string")
