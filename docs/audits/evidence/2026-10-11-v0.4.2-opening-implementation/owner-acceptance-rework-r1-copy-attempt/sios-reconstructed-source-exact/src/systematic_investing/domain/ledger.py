"""Immutable accounting objects: cash/holdings ledger entries, positions,
portfolio snapshots, and NAV points.

Ledger entries are append-only facts; positions derive total and sellable
quantities from dated acquisition lots and settlement rules, never from an
assumption that everything held is sellable. A suspended instrument is
marked at its last valid RAW close with an explicit ``STALE_MARK``; the
portfolio valuation is incomplete only when no defensible price exists, a
corporate action invalidates the prior price, or identity is unresolved.
"""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256

from systematic_investing.domain.identifiers import InstrumentId, require_session_date
from systematic_investing.domain.money import Money


class LedgerError(Exception):
    """Base class for ledger/accounting contract errors."""


class InvalidLedgerEntryError(LedgerError):
    """Raised when a ledger entry violates its contract."""


def _digest(lines) -> str:
    return sha256("\n".join(lines).encode("utf-8")).hexdigest()


class CashLedgerCategory(StrEnum):
    """Cash movement categories (signed amounts: outflows negative)."""

    DEPOSIT = "DEPOSIT"
    BUY_CONSIDERATION = "BUY_CONSIDERATION"
    SELL_PROCEEDS = "SELL_PROCEEDS"
    BROKER_COMMISSION = "BROKER_COMMISSION"
    STAMP_TAX = "STAMP_TAX"
    TRANSFER_FEE = "TRANSFER_FEE"
    DIVIDEND = "DIVIDEND"


def _require_text(value, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise InvalidLedgerEntryError(f"{field_name} must be a non-empty string")
    return value


def _aware(value, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise InvalidLedgerEntryError(
            f"{field_name} must be a timezone-aware datetime, got {value!r}"
        )
    return value


@dataclass(frozen=True)
class CashLedgerEntry:
    """One immutable cash movement with its category and source trace."""

    entry_id: str
    category: CashLedgerCategory
    amount: "Money"
    session_date: date
    recorded_at: datetime
    source_id: str

    def __post_init__(self) -> None:
        from systematic_investing.domain.money import Money

        _require_text(self.entry_id, "entry_id")
        if not isinstance(self.category, CashLedgerCategory):
            raise InvalidLedgerEntryError(
                f"category must be a CashLedgerCategory, got {self.category!r}"
            )
        if not isinstance(self.amount, Money):
            raise InvalidLedgerEntryError("amount must be Money")
        require_session_date(self.session_date)
        _aware(self.recorded_at, "recorded_at")
        _require_text(self.source_id, "source_id")


@dataclass(frozen=True)
class HoldingsLedgerEntry:
    """One immutable quantity movement linked to a fill or corporate action."""

    entry_id: str
    instrument_id: InstrumentId
    quantity_delta: int
    acquisition_session: date | None
    sellable_from: date | None
    source_id: str
    session_date: date
    recorded_at: datetime

    def __post_init__(self) -> None:
        _require_text(self.entry_id, "entry_id")
        if not isinstance(self.instrument_id, InstrumentId):
            raise InvalidLedgerEntryError("instrument_id must be an InstrumentId")
        if (
            not isinstance(self.quantity_delta, int)
            or isinstance(self.quantity_delta, bool)
            or self.quantity_delta == 0
        ):
            raise InvalidLedgerEntryError("quantity_delta must be a non-zero integer")
        for field_name in ("acquisition_session", "sellable_from"):
            value = getattr(self, field_name)
            if value is not None:
                require_session_date(value)
        _require_text(self.source_id, "source_id")
        require_session_date(self.session_date)
        _aware(self.recorded_at, "recorded_at")


@dataclass(frozen=True)
class AcquisitionLot:
    """One dated acquisition lot: when it was bought, when it becomes
    sellable, and at what gross acquisition price."""

    quantity: int
    acquired_session: date
    sellable_from: date
    acquisition_price: Decimal

    def __post_init__(self) -> None:
        if (
            not isinstance(self.quantity, int)
            or isinstance(self.quantity, bool)
            or self.quantity <= 0
        ):
            raise InvalidLedgerEntryError("lot quantity must be a positive integer")
        require_session_date(self.acquired_session)
        require_session_date(self.sellable_from)
        if self.sellable_from < self.acquired_session:
            raise InvalidLedgerEntryError("sellable_from must not precede acquired_session")
        price = self.acquisition_price
        if not isinstance(price, Decimal) or not price.is_finite() or price <= 0:
            raise InvalidLedgerEntryError("acquisition_price must be a finite positive Decimal")


@dataclass(frozen=True)
class Position:
    """Actual holdings for one instrument: dated acquisition lots, total
    quantity, derived sellable quantity, and an attribution-only average
    cost. Sellable is derived from lots and settlement rules, never assumed
    equal to total."""

    instrument_id: InstrumentId
    lots: tuple[AcquisitionLot, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.instrument_id, InstrumentId):
            raise LedgerError("instrument_id must be an InstrumentId")
        if not isinstance(self.lots, tuple) or not all(
            isinstance(lot, AcquisitionLot) for lot in self.lots
        ):
            raise LedgerError("lots must be a tuple of AcquisitionLot")

    @property
    def total_quantity(self) -> int:
        return sum(lot.quantity for lot in self.lots)

    def sellable_quantity(self, as_of: date) -> int:
        require_session_date(as_of)
        return sum(lot.quantity for lot in self.lots if lot.sellable_from <= as_of)

    @property
    def average_cost(self) -> Decimal | None:
        total = self.total_quantity
        if total == 0:
            return None
        cost = sum(
            (Decimal(lot.quantity) * lot.acquisition_price for lot in self.lots),
            Decimal("0"),
        )
        return cost / Decimal(total)


class ValuationStatus(StrEnum):
    """Portfolio valuation completeness."""

    COMPLETE = "COMPLETE"
    INCOMPLETE = "INCOMPLETE"


class IncompleteValuationReason(StrEnum):
    """Why a portfolio NAV is incomplete; only these block metrics."""

    NO_DEFENSIBLE_PRICE = "NO_DEFENSIBLE_PRICE"
    CORPORATE_ACTION_INVALIDATED_PRICE = "CORPORATE_ACTION_INVALIDATED_PRICE"
    IDENTITY_UNRESOLVED = "IDENTITY_UNRESOLVED"


@dataclass(frozen=True)
class StaleMark:
    """Explicit stale-mark metadata for a position valued at its last valid
    RAW close."""

    instrument_id: InstrumentId
    marked_price: Decimal
    last_valid_session: date
    age_sessions: int

    def __post_init__(self) -> None:
        if not isinstance(self.instrument_id, InstrumentId):
            raise LedgerError("instrument_id must be an InstrumentId")
        price = self.marked_price
        if not isinstance(price, Decimal) or not price.is_finite() or price <= 0:
            raise LedgerError("marked_price must be a finite positive Decimal")
        require_session_date(self.last_valid_session)
        if (
            not isinstance(self.age_sessions, int)
            or isinstance(self.age_sessions, bool)
            or self.age_sessions < 0
        ):
            raise LedgerError("age_sessions must be a non-negative integer")


@dataclass(frozen=True)
class PortfolioSnapshot:
    """As-of valuation of simulated holdings: a fact, never a target."""

    session_date: date
    generated_at: datetime
    cash: "Money"
    positions: tuple[Position, ...]
    market_value: "Money"
    total_equity: "Money"
    valuation_status: ValuationStatus
    stale_marks: tuple[StaleMark, ...] = ()
    incomplete_reasons: tuple[IncompleteValuationReason, ...] = ()

    def __post_init__(self) -> None:
        from systematic_investing.domain.money import Money

        require_session_date(self.session_date)
        _aware(self.generated_at, "generated_at")
        if not isinstance(self.cash, Money):
            raise LedgerError("cash must be Money")
        if not isinstance(self.positions, tuple) or not all(
            isinstance(position, Position) for position in self.positions
        ):
            raise LedgerError("positions must be a tuple of Position")
        if not isinstance(self.market_value, Money) or not isinstance(self.total_equity, Money):
            raise LedgerError("market_value and total_equity must be Money")
        if not isinstance(self.valuation_status, ValuationStatus):
            raise LedgerError("valuation_status must be a ValuationStatus")
        if not isinstance(self.stale_marks, tuple) or not all(
            isinstance(mark, StaleMark) for mark in self.stale_marks
        ):
            raise LedgerError("stale_marks must be a tuple of StaleMark")
        if not isinstance(self.incomplete_reasons, tuple) or not all(
            isinstance(reason, IncompleteValuationReason)
            for reason in self.incomplete_reasons
        ):
            raise LedgerError("incomplete_reasons must be a tuple of IncompleteValuationReason")
        if self.valuation_status is ValuationStatus.INCOMPLETE and not self.incomplete_reasons:
            raise LedgerError("an incomplete valuation must record its reasons")
        if self.valuation_status is ValuationStatus.COMPLETE and self.incomplete_reasons:
            raise LedgerError("a complete valuation must not record incomplete reasons")

    def content_digest(self) -> str:
        lines = [
            f"session={self.session_date.isoformat()}",
            f"generated_at={self.generated_at.isoformat()}",
            f"cash={self.cash.amount},{self.cash.currency}",
            f"market_value={self.market_value.amount},{self.market_value.currency}",
            f"total_equity={self.total_equity.amount},{self.total_equity.currency}",
            f"status={self.valuation_status.value}",
        ]
        for position in sorted(self.positions, key=lambda item: str(item.instrument_id)):
            lines.append(
                f"position={position.instrument_id},{position.total_quantity},"
                f"{position.sellable_quantity(self.session_date)},{position.average_cost}"
            )
            for lot in sorted(
                position.lots,
                key=lambda item: (
                    item.acquired_session,
                    item.sellable_from,
                    item.acquisition_price,
                    item.quantity,
                ),
            ):
                lines.append(
                    f"lot={position.instrument_id},{lot.quantity},"
                    f"{lot.acquired_session.isoformat()},{lot.sellable_from.isoformat()},"
                    f"{lot.acquisition_price}"
                )
        for mark in sorted(self.stale_marks, key=lambda item: str(item.instrument_id)):
            lines.append(
                f"stale_mark={mark.instrument_id},{mark.marked_price},"
                f"{mark.last_valid_session.isoformat()},{mark.age_sessions}"
            )
        for reason in sorted(self.incomplete_reasons, key=lambda item: item.value):
            lines.append(f"incomplete={reason.value}")
        return _digest(lines)


@dataclass(frozen=True)
class NavPoint:
    """One NAV observation relative to the CNY 100,000 initial capital."""

    session_date: date
    cash: "Money"
    market_value: "Money"
    total_equity: "Money"
    nav: Decimal
    valuation_status: ValuationStatus
    stale_marks: tuple[StaleMark, ...] = ()
    incomplete_reasons: tuple[IncompleteValuationReason, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "stale_marks", tuple(self.stale_marks))
        object.__setattr__(self, "incomplete_reasons", tuple(self.incomplete_reasons))
