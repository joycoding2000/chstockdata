"""Backtest accounting: ledger posting, position updates, valuation, NAV.

Accounting is pure and deterministic: fills post itemized cash entries and
dated holdings entries; positions fold those movements FIFO; corporate actions
post their economic effect (cash and/or share events) exactly once; valuation
marks held instruments at the session close, at the last valid RAW close with
an explicit ``STALE_MARK`` when suspended, or reports an incomplete valuation
when no defensible price exists.
"""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_FLOOR, Decimal
from enum import StrEnum

from systematic_investing import DEFAULT_INITIAL_CAPITAL
from systematic_investing.domain.execution import MONETARY_EXPONENT, MONETARY_ROUNDING
from systematic_investing.domain.identifiers import InstrumentId, require_session_date
from systematic_investing.domain.ledger import (
    AcquisitionLot,
    CashLedgerCategory,
    CashLedgerEntry,
    HoldingsLedgerEntry,
    IncompleteValuationReason,
    LedgerError,
    NavPoint,
    PortfolioSnapshot,
    Position,
    StaleMark,
    ValuationStatus,
)
from systematic_investing.domain.market import CorporateAction, TradeSide
from systematic_investing.domain.money import Money


class AccountingError(LedgerError):
    """Raised when accounting posting would violate its contract."""


class CorporateActionAccountingError(AccountingError):
    """Raised when a corporate action cannot be applied exactly."""


class AccountingSemantics(StrEnum):
    """Selectable corporate-action accounting contracts."""

    LEGACY_M0_ACCOUNTING_1 = "m0-accounting-1"
    CURRENT_M0_ACCOUNTING_2 = "m0-accounting-2"


class InsufficientSellableError(AccountingError):
    """Raised when a sale exceeds the sellable quantity derived from lots."""

    def __init__(
        self,
        instrument_id: InstrumentId,
        requested: int,
        sellable: int,
        as_of: date,
    ) -> None:
        self.instrument_id = instrument_id
        self.requested = requested
        self.sellable = sellable
        self.as_of = as_of
        super().__init__(
            f"sale of {requested} {instrument_id} exceeds sellable quantity "
            f"{sellable} on {as_of}"
        )


def sellable_from(
    *,
    calendar,
    acquired_session: date,
    sessions_until_sellable: int,
) -> date:
    """Resolve when an acquisition becomes sellable, using the calendar
    snapshot only; the snapshot end fails closed."""
    require_session_date(acquired_session)
    if (
        not isinstance(sessions_until_sellable, int)
        or isinstance(sessions_until_sellable, bool)
        or sessions_until_sellable < 0
    ):
        raise AccountingError("sessions_until_sellable must be a non-negative integer")
    current = acquired_session
    for _ in range(sessions_until_sellable):
        current = calendar.next_session(current).session_date
    return current


def _lot_order(lot: AcquisitionLot) -> tuple[date, Decimal, date]:
    return (lot.acquired_session, lot.acquisition_price, lot.sellable_from)


@dataclass(frozen=True)
class CorporateActionPosting:
    """The exact posting of one corporate action: updated cash and position
    plus the append-only ledger entries and their deltas."""

    cash: Money
    position: Position | None
    cash_delta: Money
    quantity_delta: int
    cash_entry: CashLedgerEntry | None
    holdings_entry: HoldingsLedgerEntry | None


ACCOUNTING_SEMANTICS_VERSION: str = AccountingSemantics.CURRENT_M0_ACCOUNTING_2.value


def apply_corporate_action(
    *,
    action: CorporateAction,
    position: Position | None,
    cash: Money,
    session_date: date,
    recorded_at: datetime,
    fraction_price: Decimal | None = None,
    accounting_semantics: AccountingSemantics = (
        AccountingSemantics.CURRENT_M0_ACCOUNTING_2
    ),
) -> CorporateActionPosting:
    """Apply one effective corporate action to the account exactly once.

    M0 convention: the full economic effect (cash and shares) is credited at
    the session where the action is applied; receivables and withholding are
    not modeled. Cash is computed on the pre-change quantity, and a share
    ratio scales every acquisition lot while preserving its acquired and
    sellable sessions and its total cost basis.

    Accounting semantics ``m0-accounting-2`` (owner-approved M1 stock
    extension): a share ratio that produces a fractional lot quantity
    credits the whole-share floor to the lot and pays cash in lieu of the
    sub-share remainder at ``fraction_price``, folded into the action's
    single cash ledger entry; a lot whose floor is zero is removed. Without
    a positive ``fraction_price`` the fractional case still fails closed,
    which keeps every integral outcome and every earlier caller byte-for-
    byte on ``m0-accounting-1`` behavior.
    """
    require_session_date(session_date)
    if not isinstance(action, CorporateAction):
        raise AccountingError("action must be a CorporateAction")
    if not isinstance(cash, Money):
        raise AccountingError("cash must be Money")
    if not isinstance(accounting_semantics, AccountingSemantics):
        raise AccountingError(
            f"accounting_semantics must be an AccountingSemantics, got "
            f"{accounting_semantics!r}"
        )
    if position is not None and position.instrument_id != action.instrument_id:
        raise AccountingError(
            f"position {position.instrument_id} does not match corporate action "
            f"{action.instrument_id}"
        )
    quantity = position.total_quantity if position is not None else 0
    cash_delta = Money(Decimal("0"), currency=cash.currency)
    cash_entry: CashLedgerEntry | None = None
    fractional_shares = Decimal("0")
    if quantity > 0 and action.cash_amount is not None:
        amount = (Decimal(quantity) * action.cash_amount.amount).quantize(
            MONETARY_EXPONENT, rounding=MONETARY_ROUNDING
        )
        if amount != 0:
            cash_delta = Money(amount, currency=cash.currency)
            cash_entry = CashLedgerEntry(
                entry_id=f"cash:ca:{action.action_id}",
                category=CashLedgerCategory.DIVIDEND,
                amount=cash_delta,
                session_date=session_date,
                recorded_at=recorded_at,
                source_id=action.action_id,
            )
    new_position = position
    quantity_delta = 0
    holdings_entry: HoldingsLedgerEntry | None = None
    if quantity > 0 and action.share_ratio is not None:
        if position is None:
            raise CorporateActionAccountingError(
                f"corporate action {action.action_id} has positive quantity without a position"
            )
        ratio = action.share_ratio
        scaled_lots: list[AcquisitionLot] = []
        for lot in position.lots:
            scaled = Decimal(lot.quantity) * ratio
            if scaled != scaled.to_integral_value():
                if accounting_semantics is AccountingSemantics.LEGACY_M0_ACCOUNTING_1:
                    raise CorporateActionAccountingError(
                        f"corporate action {action.action_id} at ratio {ratio} would turn a "
                        f"{lot.quantity}-share lot into {scaled} shares"
                    )
                if fraction_price is None or fraction_price <= 0:
                    raise CorporateActionAccountingError(
                        f"corporate action {action.action_id} at ratio {ratio} would turn a "
                        f"{lot.quantity}-share lot into {scaled} shares and no "
                        "fraction price is available for cash in lieu"
                    )
                fractional_shares += scaled - scaled.to_integral_value(
                    rounding=ROUND_FLOOR
                )
                scaled = scaled.to_integral_value(rounding=ROUND_FLOOR)
            if scaled <= 0:
                if accounting_semantics is AccountingSemantics.LEGACY_M0_ACCOUNTING_1:
                    raise CorporateActionAccountingError(
                        f"corporate action {action.action_id} at ratio {ratio} would turn a "
                        f"{lot.quantity}-share lot into {scaled} shares"
                    )
                continue
            scaled_lots.append(
                AcquisitionLot(
                    quantity=int(scaled),
                    acquired_session=lot.acquired_session,
                    sellable_from=lot.sellable_from,
                    acquisition_price=lot.acquisition_price / ratio,
                )
            )
        if fractional_shares > 0:
            if fraction_price is None or fraction_price <= 0:
                raise CorporateActionAccountingError(
                    f"corporate action {action.action_id} requires a positive "
                    "fraction price for cash in lieu"
                )
            compensation = (
                fractional_shares * fraction_price
            ).quantize(MONETARY_EXPONENT, rounding=MONETARY_ROUNDING)
            if compensation != 0:
                cash_delta = Money(
                    cash_delta.amount + compensation, currency=cash.currency
                )
                cash_entry = CashLedgerEntry(
                    entry_id=f"cash:ca:{action.action_id}",
                    category=CashLedgerCategory.DIVIDEND,
                    amount=cash_delta,
                    session_date=session_date,
                    recorded_at=recorded_at,
                    source_id=action.action_id,
                )
        new_lots = tuple(sorted(scaled_lots, key=_lot_order))
        new_quantity = sum(lot.quantity for lot in new_lots)
        quantity_delta = new_quantity - quantity
        new_position = (
            Position(instrument_id=position.instrument_id, lots=new_lots)
            if new_lots
            else None
        )
        if quantity_delta != 0:
            holdings_entry = HoldingsLedgerEntry(
                entry_id=f"hold:ca:{action.action_id}",
                instrument_id=position.instrument_id,
                quantity_delta=quantity_delta,
                acquisition_session=None,
                sellable_from=None,
                source_id=action.action_id,
                session_date=session_date,
                recorded_at=recorded_at,
            )
    return CorporateActionPosting(
        cash=cash + cash_delta,
        position=new_position,
        cash_delta=cash_delta,
        quantity_delta=quantity_delta,
        cash_entry=cash_entry,
        holdings_entry=holdings_entry,
    )


def apply_fill_to_position(
    *,
    instrument_id: InstrumentId,
    position: Position | None,
    side: TradeSide,
    quantity: int,
    price: Decimal,
    execution_session: date,
    settlement_rule,
    calendar,
    source_id: str,
    recorded_at,
) -> tuple[Position, HoldingsLedgerEntry]:
    """Fold one fill into the position (FIFO consumption for sells) and emit
    the dated holdings ledger entry. Selling beyond the sellable quantity
    raises a typed error; it never pretends total quantity is sellable."""
    require_session_date(execution_session)
    if not isinstance(instrument_id, InstrumentId):
        raise AccountingError("instrument_id must be an InstrumentId")
    if (
        not isinstance(quantity, int)
        or isinstance(quantity, bool)
        or quantity <= 0
    ):
        raise AccountingError(f"fill quantity must be a positive integer, got {quantity!r}")
    if not isinstance(price, Decimal) or not price.is_finite() or price <= 0:
        raise AccountingError(f"fill price must be a finite positive Decimal, got {price!r}")
    if position is not None and position.instrument_id != instrument_id:
        raise AccountingError(
            f"position instrument {position.instrument_id} does not match fill "
            f"{instrument_id}"
        )
    existing = position.lots if position is not None else ()
    entry_id = f"hold:{source_id}"
    if side is TradeSide.BUY:
        sellable = sellable_from(
            calendar=calendar,
            acquired_session=execution_session,
            sessions_until_sellable=settlement_rule,
        )
        lots = (
            *existing,
            AcquisitionLot(
                quantity=quantity,
                acquired_session=execution_session,
                sellable_from=sellable,
                acquisition_price=price,
            ),
        )
        entry = HoldingsLedgerEntry(
            entry_id=entry_id,
            instrument_id=instrument_id,
            quantity_delta=quantity,
            acquisition_session=execution_session,
            sellable_from=sellable,
            source_id=source_id,
            session_date=execution_session,
            recorded_at=recorded_at,
        )
    elif side is TradeSide.SELL:
        as_of = execution_session
        sellable_quantity = sum(
            lot.quantity for lot in existing if lot.sellable_from <= as_of
        )
        if sellable_quantity < quantity:
            raise InsufficientSellableError(instrument_id, quantity, sellable_quantity, as_of)
        remaining = quantity
        kept: list[AcquisitionLot] = []
        for lot in sorted(existing, key=_lot_order):
            if lot.sellable_from <= as_of and remaining > 0:
                take = min(lot.quantity, remaining)
                remaining -= take
                left = lot.quantity - take
                if left > 0:
                    kept.append(
                        AcquisitionLot(
                            quantity=left,
                            acquired_session=lot.acquired_session,
                            sellable_from=lot.sellable_from,
                            acquisition_price=lot.acquisition_price,
                        )
                    )
            else:
                kept.append(lot)
        lots = tuple(kept)
        entry = HoldingsLedgerEntry(
            entry_id=entry_id,
            instrument_id=instrument_id,
            quantity_delta=-quantity,
            acquisition_session=None,
            sellable_from=None,
            source_id=source_id,
            session_date=execution_session,
            recorded_at=recorded_at,
        )
    else:
        raise AccountingError(f"unsupported fill side {side!r}")
    return Position(instrument_id=instrument_id, lots=tuple(sorted(lots, key=_lot_order))), entry


def _open_session_dates(calendar) -> list[date]:
    return sorted(session.session_date for session in calendar.sessions if session.is_open)


def mark_to_market(
    *,
    cash: Money,
    positions: tuple[Position, ...],
    session_date: date,
    generated_at,
    calendar,
    close_prices=None,
    last_valid_closes=None,
    incomplete_valuations=None,
) -> PortfolioSnapshot:
    """Value the portfolio at the session close; suspended or missing-close
    instruments use their last valid RAW close plus an explicit
    ``STALE_MARK(age)``; engine-declared incomplete valuations contribute no
    marked value and block metrics. A truly unpriceable holding (no
    defensible price ever) also makes the valuation incomplete."""
    require_session_date(session_date)
    close_prices = close_prices or {}
    last_valid_closes = last_valid_closes or {}
    incomplete_valuations = incomplete_valuations or {}
    open_dates = _open_session_dates(calendar)
    market_value = Decimal("0")
    stale_marks: list[StaleMark] = []
    incomplete_reasons: list[IncompleteValuationReason] = []
    for position in sorted(positions, key=lambda item: item.instrument_id):
        instrument_id = position.instrument_id
        if instrument_id in incomplete_valuations:
            incomplete_reasons.append(incomplete_valuations[instrument_id])
            continue
        close = close_prices.get(instrument_id)
        if close is not None:
            market_value += Decimal(position.total_quantity) * close
            continue
        last_valid = last_valid_closes.get(instrument_id)
        if last_valid is None:
            incomplete_reasons.append(IncompleteValuationReason.NO_DEFENSIBLE_PRICE)
            continue
        marked_price, last_session = last_valid
        age = sum(1 for open_date in open_dates if last_session < open_date <= session_date)
        stale_marks.append(
            StaleMark(
                instrument_id=instrument_id,
                marked_price=marked_price,
                last_valid_session=last_session,
                age_sessions=age,
            )
        )
        market_value += Decimal(position.total_quantity) * marked_price
    status = (
        ValuationStatus.INCOMPLETE if incomplete_reasons else ValuationStatus.COMPLETE
    )
    return PortfolioSnapshot(
        session_date=session_date,
        generated_at=generated_at,
        cash=cash,
        positions=tuple(positions),
        market_value=Money(market_value),
        total_equity=cash + Money(market_value),
        valuation_status=status,
        stale_marks=tuple(stale_marks),
        incomplete_reasons=tuple(incomplete_reasons),
    )


def nav_point_of(snapshot: PortfolioSnapshot) -> NavPoint:
    """Project a portfolio snapshot to its NAV point relative to the CNY
    100,000 initial capital."""
    return NavPoint(
        session_date=snapshot.session_date,
        cash=snapshot.cash,
        market_value=snapshot.market_value,
        total_equity=snapshot.total_equity,
        nav=snapshot.total_equity.amount / DEFAULT_INITIAL_CAPITAL,
        valuation_status=snapshot.valuation_status,
        stale_marks=snapshot.stale_marks,
        incomplete_reasons=snapshot.incomplete_reasons,
    )
