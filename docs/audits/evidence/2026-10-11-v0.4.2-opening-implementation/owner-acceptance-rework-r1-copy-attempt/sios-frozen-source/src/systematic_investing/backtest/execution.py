"""Backtest execution: the T+1 activation model.

Pending plans sized from the finalized T close are activated at the
execution session's open. Every candidate is priced at open plus
side-aware slippage with explicit tick rounding, fees are composed from the
Instrument Master market rules and the run-owned account configuration, and
affordability is solved globally under the approved priority (reductions
and exits first, then buys ranked by descending absolute target-weight
deficit with canonical InstrumentId as tie-breaker), reducing
``submitted_quantity`` by complete lots only. Submitted M0 daily-bar
orders are all-or-none. This never recalculates or mutates the T-close
``planned_quantity`` evidence or the locked theoretical target.
"""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from enum import StrEnum

from systematic_investing.backtest.accounting import apply_fill_to_position
from systematic_investing.domain.execution import (
    EXECUTION_CONVENTION_VERSION,
    FILL_PRICE_MODEL_NEXT_SESSION_OPEN,
    ExecutionError,
    FeeBreakdown,
    Fill,
    InvalidOrderError,
    Order,
    OrderStatus,
    Rejection,
    RejectionCode,
    compute_fees,
)
from systematic_investing.domain.identifiers import InstrumentId
from systematic_investing.domain.ledger import (
    CashLedgerCategory,
    CashLedgerEntry,
    HoldingsLedgerEntry,
    Position,
)
from systematic_investing.domain.market import TradeSide
from systematic_investing.domain.money import Money
from systematic_investing.domain.portfolio import SizingPriceBasis
from systematic_investing.instrument_master.models import LotRule, OddLotSellPolicy


def legal_buy_quantity(quantity: int, lot_rule: LotRule) -> int:
    """Buys must be complete lots of the buy increment."""
    if (
        not isinstance(quantity, int)
        or isinstance(quantity, bool)
        or quantity <= 0
        or quantity % lot_rule.buy_increment != 0
    ):
        raise InvalidOrderError(
            f"{quantity} is not a complete buy lot of {lot_rule.buy_increment}"
        )
    return quantity


def legal_sell_quantity(quantity: int, lot_rule: LotRule) -> int:
    """Sell quantities follow the profile's odd-lot sell policy."""
    if (
        not isinstance(quantity, int)
        or isinstance(quantity, bool)
        or quantity <= 0
    ):
        raise InvalidOrderError(f"{quantity} is not a positive sell quantity")
    if lot_rule.odd_lot_sell_policy is OddLotSellPolicy.ALLOWED:
        return quantity
    return quantity // lot_rule.board_lot * lot_rule.board_lot


class ActivationError(ExecutionError):
    """Raised when activation would violate the execution contract."""


class ActivationReason(StrEnum):
    """Per-order constraint reasons recorded at T+1 activation."""

    FILLED_AS_PLANNED = "FILLED_AS_PLANNED"
    REDUCED_TO_AFFORD_T1_GAP = "REDUCED_TO_AFFORD_T1_GAP"


@dataclass(frozen=True)
class ExecutionModel:
    """Versioned execution model: M0 fixes ``NEXT_SESSION_OPEN`` with
    side-aware slippage and conservative tick rounding (buys round up,
    sells round down)."""

    slippage_rate_buy: Decimal
    slippage_rate_sell: Decimal
    fill_price_model: str = FILL_PRICE_MODEL_NEXT_SESSION_OPEN
    version: str = EXECUTION_CONVENTION_VERSION

    def execution_price(
        self, open_price: Decimal, side: TradeSide, tick_size: Decimal
    ) -> Decimal:
        if not isinstance(open_price, Decimal) or not open_price.is_finite() or open_price <= 0:
            raise ExecutionError(
                f"open price must be a finite positive Decimal, got {open_price!r}"
            )
        if not isinstance(tick_size, Decimal) or not tick_size.is_finite() or tick_size <= 0:
            raise ExecutionError(f"tick size must be a positive Decimal, got {tick_size!r}")
        if side is TradeSide.BUY:
            raw = open_price * (Decimal("1") + self.slippage_rate_buy)
            ticks = (raw / tick_size).to_integral_value(rounding=ROUND_CEILING)
        else:
            raw = open_price * (Decimal("1") - self.slippage_rate_sell)
            ticks = (raw / tick_size).to_integral_value(rounding=ROUND_FLOOR)
        return ticks * tick_size


@dataclass(frozen=True)
class PendingPlan:
    """The locked decision-time execution plan for one instrument: the
    T-close-sized order quantity with its ranking inputs. Activation may
    reduce ``submitted_quantity`` but never mutates this plan."""

    instrument_id: InstrumentId
    sleeve: object
    side: TradeSide
    order_quantity: int
    target_weight: Decimal
    current_weight: Decimal
    target_id: str
    target_revision: int
    decision_for_trade_date: date
    sizing_reference_price: Decimal

    @property
    def sizing_reference_price_basis(self) -> SizingPriceBasis:
        return SizingPriceBasis.T_CLOSE


_REJECTION_BY_STATUS = {
    "SUSPENDED": RejectionCode.SUSPENDED,
    "NOT_LISTED": RejectionCode.NOT_LISTED,
    "DELISTED": RejectionCode.DELISTED,
    "BUY_BLOCKED_UPPER_LIMIT": RejectionCode.BUY_BLOCKED_UPPER_LIMIT,
    "SELL_BLOCKED_LOWER_LIMIT": RejectionCode.SELL_BLOCKED_LOWER_LIMIT,
    "UNKNOWN": RejectionCode.TRADABILITY_UNKNOWN,
}


@dataclass(frozen=True)
class ActivationResult:
    """Deterministic activation output: final order states, fills,
    rejections, itemized ledger entries, and the resulting positions and
    cash."""

    orders: tuple[Order, ...]
    fills: tuple[Fill, ...]
    rejections: tuple[Rejection, ...]
    cash_entries: tuple[CashLedgerEntry, ...]
    holdings_entries: tuple[HoldingsLedgerEntry, ...]
    positions: tuple[Position, ...]
    cash: Money


def _cash_entries_for(fill: Fill, recorded_at: datetime) -> list[CashLedgerEntry]:
    entries = []
    notional = Decimal(fill.quantity) * fill.fill_price
    if fill.side is TradeSide.BUY:
        consideration_category = CashLedgerCategory.BUY_CONSIDERATION
        entries.append(
            CashLedgerEntry(
                entry_id=f"cash:{fill.order_id}:{consideration_category.value}",
                category=consideration_category,
                amount=Money(-notional),
                session_date=fill.session_date,
                recorded_at=recorded_at,
                source_id=fill.order_id,
            )
        )
    else:
        entries.append(
            CashLedgerEntry(
                entry_id=f"cash:{fill.order_id}:{CashLedgerCategory.SELL_PROCEEDS.value}",
                category=CashLedgerCategory.SELL_PROCEEDS,
                amount=Money(notional),
                session_date=fill.session_date,
                recorded_at=recorded_at,
                source_id=fill.order_id,
            )
        )
    commission_total = fill.fees.commission + fill.fees.minimum_commission_adjustment
    if commission_total.amount != 0:
        entries.append(
            CashLedgerEntry(
                entry_id=f"cash:{fill.order_id}:{CashLedgerCategory.BROKER_COMMISSION.value}",
                category=CashLedgerCategory.BROKER_COMMISSION,
                amount=-commission_total,
                session_date=fill.session_date,
                recorded_at=recorded_at,
                source_id=fill.order_id,
            )
        )
    if fill.fees.stamp_tax.amount != 0:
        entries.append(
            CashLedgerEntry(
                entry_id=f"cash:{fill.order_id}:{CashLedgerCategory.STAMP_TAX.value}",
                category=CashLedgerCategory.STAMP_TAX,
                amount=-fill.fees.stamp_tax,
                session_date=fill.session_date,
                recorded_at=recorded_at,
                source_id=fill.order_id,
            )
        )
    if fill.fees.transfer_fee.amount != 0:
        entries.append(
            CashLedgerEntry(
                entry_id=f"cash:{fill.order_id}:{CashLedgerCategory.TRANSFER_FEE.value}",
                category=CashLedgerCategory.TRANSFER_FEE,
                amount=-fill.fees.transfer_fee,
                session_date=fill.session_date,
                recorded_at=recorded_at,
                source_id=fill.order_id,
            )
        )
    return entries


def pending_order_for(
    plan: PendingPlan,
    execution_session: date,
    execution_model,
    reason_codes: tuple[str, ...] = (),
) -> Order:
    return Order(
        order_id=f"order:{execution_session.isoformat()}:{plan.instrument_id}",
        instrument_id=plan.instrument_id,
        side=plan.side,
        planned_quantity=plan.order_quantity,
        submitted_quantity=None,
        execution_session=execution_session,
        sizing_reference_price_basis=SizingPriceBasis.T_CLOSE,
        sizing_reference_price=plan.sizing_reference_price,
        fill_price_model=execution_model.fill_price_model,
        target_id=plan.target_id,
        target_revision=plan.target_revision,
        decision_for_trade_date=plan.decision_for_trade_date,
        status=OrderStatus.PENDING_ACTIVATION,
        reason_codes=reason_codes,
    )


def _tradability_gate(
    plan: PendingPlan, tradability, side: TradeSide
) -> RejectionCode | None:
    status = tradability.get(plan.instrument_id)
    if status is None:
        return RejectionCode.TRADABILITY_UNKNOWN
    if not status.permits(side):
        return _REJECTION_BY_STATUS[status.status.value]
    return None


def activate_pending_plans(
    *,
    plans,
    cash: Money,
    positions: tuple[Position, ...],
    opens,
    tradability,
    rules,
    account_fees,
    execution_model: ExecutionModel,
    calendar,
    execution_session: date,
    recorded_at: datetime,
) -> ActivationResult:
    """Globally affordable, deterministic T+1 activation.

    Reductions/exits are priced and settled first in canonical InstrumentId
    order; buys are then ranked by descending absolute target-weight
    deficit with the canonical InstrumentId as tie-breaker and reduced by
    complete lots until affordable. Submitted orders fill all-or-none. No
    accepted order can make cash negative.
    """
    positions_by_id = {position.instrument_id: position for position in positions}
    orders: list[Order] = []
    fills: list[Fill] = []
    rejections: list[Rejection] = []
    cash_entries: list[CashLedgerEntry] = []
    holdings_entries: list[HoldingsLedgerEntry] = []
    positions_result: dict[InstrumentId, Position] = dict(positions_by_id)
    available = cash

    def reject(plan: PendingPlan, code: RejectionCode, observed: str) -> None:
        order = pending_order_for(plan, execution_session, execution_model)
        rejected_order, rejection = order.rejected(
            code,
            message=f"activation rejected {plan.instrument_id}",
            observed=observed,
        )
        orders.append(rejected_order)
        rejections.append(rejection)

    sells = sorted(
        (plan for plan in plans if plan.side is TradeSide.SELL and plan.order_quantity > 0),
        key=lambda plan: plan.instrument_id,
    )
    buys = sorted(
        (plan for plan in plans if plan.side is TradeSide.BUY and plan.order_quantity > 0),
        key=lambda plan: (
            -(plan.target_weight - plan.current_weight),
            plan.instrument_id,
        ),
    )

    for plan in sells:
        bundle = rules.get(plan.instrument_id)
        if bundle is None:
            reject(plan, RejectionCode.MISSING_RULE, "no approved rule bundle")
            continue
        rejection_code = _tradability_gate(plan, tradability, TradeSide.SELL)
        if rejection_code is not None:
            reject(
                plan,
                rejection_code,
                (
                    "no tradability fact"
                    if plan.instrument_id not in tradability
                    else f"status={tradability[plan.instrument_id].status.value}"
                ),
            )
            continue
        exec_price = execution_model.execution_price(
            opens[plan.instrument_id], TradeSide.SELL, bundle.price_limit.tick_size
        )
        position = positions_by_id.get(plan.instrument_id)
        sellable = position.sellable_quantity(execution_session) if position else 0
        if sellable < plan.order_quantity:
            reject(plan, RejectionCode.INSUFFICIENT_SELLABLE_QUANTITY, f"sellable={sellable}")
            continue
        fees = compute_fees(
            bundle.market_fee_tax,
            account_fees.resolve_broker_profile(execution_session),
            TradeSide.SELL,
            plan.order_quantity,
            exec_price,
        )
        submitted_order = pending_order_for(
            plan,
            execution_session,
            execution_model,
            reason_codes=(ActivationReason.FILLED_AS_PLANNED,),
        ).submit(plan.order_quantity, lot_multiple=1)
        submitted_quantity = submitted_order.submitted_quantity
        if submitted_quantity is None:
            raise ExecutionError(
                f"submitted sell order {submitted_order.order_id} has no quantity"
            )
        fill = Fill(
            fill_id=f"fill:{submitted_order.order_id}",
            order_id=submitted_order.order_id,
            instrument_id=plan.instrument_id,
            side=TradeSide.SELL,
            quantity=submitted_quantity,
            fill_price=exec_price,
            reference_open=opens[plan.instrument_id],
            session_date=execution_session,
            fees=fees,
        )
        proceeds = Money(Decimal(fill.quantity) * fill.fill_price) - fees.total
        available = available + proceeds
        new_position, holdings_entry = apply_fill_to_position(
            instrument_id=plan.instrument_id,
            position=position,
            side=TradeSide.SELL,
            quantity=fill.quantity,
            price=fill.fill_price,
            execution_session=execution_session,
            settlement_rule=bundle.settlement.sessions_until_sellable,
            calendar=calendar,
            source_id=submitted_order.order_id,
            recorded_at=recorded_at,
        )
        positions_result[plan.instrument_id] = new_position
        holdings_entries.append(holdings_entry)
        orders.append(submitted_order)
        fills.append(fill)
        cash_entries.extend(_cash_entries_for(fill, recorded_at))

    for plan in buys:
        bundle = rules.get(plan.instrument_id)
        if bundle is None:
            reject(plan, RejectionCode.MISSING_RULE, "no approved rule bundle")
            continue
        rejection_code = _tradability_gate(plan, tradability, TradeSide.BUY)
        if rejection_code is not None:
            reject(
                plan,
                rejection_code,
                (
                    "no tradability fact"
                    if plan.instrument_id not in tradability
                    else f"status={tradability[plan.instrument_id].status.value}"
                ),
            )
            continue
        exec_price = execution_model.execution_price(
            opens[plan.instrument_id], TradeSide.BUY, bundle.price_limit.tick_size
        )
        broker = account_fees.resolve_broker_profile(execution_session)
        lots = plan.order_quantity // bundle.lot.buy_increment
        accepted_quantity = 0
        accepted_fees: FeeBreakdown | None = None
        while lots >= 1:
            quantity = lots * bundle.lot.buy_increment
            candidate_fees = compute_fees(
                bundle.market_fee_tax, broker, TradeSide.BUY, quantity, exec_price
            )
            total = Money(Decimal(quantity) * exec_price) + candidate_fees.total
            if total <= available:
                accepted_quantity = quantity
                accepted_fees = candidate_fees
                break
            lots -= 1
        if accepted_quantity == 0:
            reject(plan, RejectionCode.INSUFFICIENT_CASH, f"cash={available.amount}")
            continue
        if accepted_fees is None:
            raise ExecutionError(
                f"accepted buy plan {plan.target_id}/{plan.instrument_id} "
                "has no computed fee breakdown"
            )
        fees = accepted_fees
        submitted_order = pending_order_for(
            plan,
            execution_session,
            execution_model,
            reason_codes=(
                ActivationReason.FILLED_AS_PLANNED
                if accepted_quantity == plan.order_quantity
                else ActivationReason.REDUCED_TO_AFFORD_T1_GAP,
            ),
        ).submit(accepted_quantity, lot_multiple=bundle.lot.buy_increment)
        submitted_quantity = submitted_order.submitted_quantity
        if submitted_quantity is None:
            raise ExecutionError(
                f"submitted buy order {submitted_order.order_id} has no quantity"
            )
        fill = Fill(
            fill_id=f"fill:{submitted_order.order_id}",
            order_id=submitted_order.order_id,
            instrument_id=plan.instrument_id,
            side=TradeSide.BUY,
            quantity=submitted_quantity,
            fill_price=exec_price,
            reference_open=opens[plan.instrument_id],
            session_date=execution_session,
            fees=fees,
        )
        total = Money(Decimal(fill.quantity) * fill.fill_price) + fees.total
        available = available - total
        new_position, holdings_entry = apply_fill_to_position(
            instrument_id=plan.instrument_id,
            position=positions_by_id.get(plan.instrument_id),
            side=TradeSide.BUY,
            quantity=fill.quantity,
            price=fill.fill_price,
            execution_session=execution_session,
            settlement_rule=bundle.settlement.sessions_until_sellable,
            calendar=calendar,
            source_id=submitted_order.order_id,
            recorded_at=recorded_at,
        )
        positions_result[plan.instrument_id] = new_position
        holdings_entries.append(holdings_entry)
        orders.append(submitted_order)
        fills.append(fill)
        cash_entries.extend(_cash_entries_for(fill, recorded_at))

    result_positions = tuple(
        positions_result[instrument_id] for instrument_id in sorted(positions_result)
    )
    return ActivationResult(
        orders=tuple(orders),
        fills=tuple(fills),
        rejections=tuple(rejections),
        cash_entries=tuple(cash_entries),
        holdings_entries=tuple(holdings_entries),
        positions=result_positions,
        cash=available,
    )
