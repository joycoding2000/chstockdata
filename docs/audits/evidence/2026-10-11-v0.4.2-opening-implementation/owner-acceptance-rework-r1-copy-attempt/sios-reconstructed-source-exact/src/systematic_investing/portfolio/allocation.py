"""Deterministic executable conversion of risk-approved targets.

Conversion order: reductions/exits first, then approved portfolio/sleeve
budgets, then buys ranked by descending absolute target-weight deficit with
canonical InstrumentId as tie-breaker. Quantities accept complete lots only,
reserve separated market and broker fee estimates, keep residual cash
explicit, and never renormalize the theoretical target. No order may make
available cash negative.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Protocol

from systematic_investing.domain.identifiers import InstrumentId, SleeveId
from systematic_investing.domain.market import TradeSide
from systematic_investing.domain.money import Money
from systematic_investing.domain.portfolio import PortfolioError, SizingPriceBasis
from systematic_investing.instrument_master.models import LotRule, OddLotSellPolicy
from systematic_investing.risk.decisions import RiskApprovedTargetPortfolio


class AllocationError(PortfolioError):
    """Raised when executable conversion would violate a cash invariant."""


class MissingPriceError(PortfolioError):
    """Raised when a valued instrument has no finalized T-close price."""

    def __init__(self, instrument_id: InstrumentId) -> None:
        self.instrument_id = instrument_id
        super().__init__(
            f"no finalized T-close price for {instrument_id}; valuation fails closed"
        )


class AllocationReasonCode(StrEnum):
    """Deterministic constraint/action reason codes on executable positions."""

    REDUCE_TO_TARGET = "REDUCE_TO_TARGET"
    EXIT_FULL_POSITION = "EXIT_FULL_POSITION"
    BUY_FULL_TARGET = "BUY_FULL_TARGET"
    BUY_REDUCED_TO_AFFORD = "BUY_REDUCED_TO_AFFORD"
    INSUFFICIENT_CASH_FOR_ONE_LOT = "INSUFFICIENT_CASH_FOR_ONE_LOT"
    HOLD_BELOW_ONE_LOT = "HOLD_BELOW_ONE_LOT"
    HOLD_AT_TARGET = "HOLD_AT_TARGET"
    HOLD_ODD_LOT_PROFILE = "HOLD_ODD_LOT_PROFILE"


@dataclass(frozen=True)
class CurrentHolding:
    """One held instrument's total quantity at the valuation point."""

    instrument_id: InstrumentId
    quantity: int


@dataclass(frozen=True)
class CurrentPortfolio:
    """Reconciled cash and holdings valued at the target's price basis."""

    cash: Money
    holdings: tuple[CurrentHolding, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "holdings", tuple(self.holdings))
        if not isinstance(self.cash, Money):
            raise AllocationError("cash must be Money")
        if self.cash.amount < 0:
            raise AllocationError("current cash must not be negative")
        seen: set[InstrumentId] = set()
        for holding in self.holdings:
            if not isinstance(holding, CurrentHolding):
                raise AllocationError("holdings must be CurrentHolding records")
            if holding.instrument_id in seen:
                raise AllocationError(
                    f"duplicate holding for {holding.instrument_id}"
                )
            seen.add(holding.instrument_id)
            if not isinstance(holding.quantity, int) or isinstance(holding.quantity, bool):
                raise AllocationError("holding quantity must be an integer")
            if holding.quantity < 0:
                raise AllocationError("holding quantity must be non-negative")


@dataclass(frozen=True)
class FeeEstimate:
    """Separated market/regulatory and account/broker fee estimates."""

    market_fees: Money
    broker_fees: Money


class FeeEstimator(Protocol):
    """Fee estimation port; run configuration composes the two authorities
    behind it, never inside the allocation policy."""

    def estimate(
        self,
        instrument_id: InstrumentId,
        side: TradeSide,
        quantity: int,
        price: Decimal,
    ) -> FeeEstimate: ...


@dataclass(frozen=True)
class ExecutablePosition:
    """One instrument's discrete target: whole-lot quantity sized from the
    finalized T close, with reserved fee estimates and constraint reasons."""

    instrument_id: InstrumentId
    sleeve: SleeveId
    theoretical_weight: Decimal
    current_weight: Decimal
    executable_weight: Decimal
    target_amount: Money
    planned_quantity: int
    sizing_reference_price_basis: SizingPriceBasis
    sizing_reference_price: Decimal
    estimated_market_fees: Money
    estimated_broker_fees: Money
    reason_codes: tuple[AllocationReasonCode, ...]


@dataclass(frozen=True)
class ExecutableTargetPortfolio:
    """Whole-lot conversion of a risk-approved target; the theoretical and
    approved weights upstream are never mutated by this stage."""

    target_id: str
    revision: int
    decision_for_trade_date: date
    information_cutoff: datetime
    valuation_equity: Money
    positions: tuple[ExecutablePosition, ...]
    residual_cash: Money
    composition_version: str


def _floor_to_lot(shares: Decimal, lot: int) -> int:
    return int(shares // lot) * lot


def build_executable_target(
    approved_target: RiskApprovedTargetPortfolio,
    current_portfolio: CurrentPortfolio,
    t_close_prices: Mapping[InstrumentId, Decimal],
    lot_rules: Mapping[InstrumentId, LotRule],
    fee_estimator: FeeEstimator,
) -> ExecutableTargetPortfolio:
    equity = approved_target.valuation_equity.amount
    if equity <= 0:
        raise AllocationError("valuation equity must be positive")
    holdings = {holding.instrument_id: holding.quantity for holding in current_portfolio.holdings}
    approved = {position.instrument_id: position for position in approved_target.positions}

    prices: dict[InstrumentId, Decimal] = {}
    for instrument_id in sorted(set(approved) | set(holdings)):
        price = t_close_prices.get(instrument_id)
        if price is None:
            raise MissingPriceError(instrument_id)
        prices[instrument_id] = price

    current_weight = {
        instrument_id: Decimal(holdings.get(instrument_id, 0)) * prices[instrument_id] / equity
        for instrument_id in prices
    }

    available = current_portfolio.cash
    decisions: dict[InstrumentId, tuple[int, tuple[AllocationReasonCode, ...], FeeEstimate]] = {}

    def lot_rule_for(instrument_id: InstrumentId) -> LotRule:
        rule = lot_rules.get(instrument_id)
        if rule is None:
            raise AllocationError(f"no lot rule for {instrument_id}")
        return rule

    def reserve(instrument_id: InstrumentId, side: TradeSide, quantity: int, price: Decimal):
        if quantity == 0:
            return FeeEstimate(market_fees=Money(Decimal("0")), broker_fees=Money(Decimal("0")))
        return fee_estimator.estimate(instrument_id, side, quantity, price)

    # Pass 1: reductions/exits first so released cash is available to buys.
    for instrument_id in sorted(approved):
        position = approved[instrument_id]
        rule = lot_rule_for(instrument_id)
        price = prices[instrument_id]
        current_qty = holdings.get(instrument_id, 0)
        target_amount = position.approved_weight * equity
        target_qty = _floor_to_lot(target_amount / price, rule.board_lot)
        if target_qty >= current_qty:
            continue
        if target_qty == 0 and rule.odd_lot_sell_policy is OddLotSellPolicy.ALLOWED:
            sell_qty = current_qty
            reason = AllocationReasonCode.EXIT_FULL_POSITION
        else:
            sell_qty = current_qty - target_qty
            if rule.odd_lot_sell_policy is OddLotSellPolicy.PROHIBITED:
                sell_qty = sell_qty // rule.board_lot * rule.board_lot
            reason = AllocationReasonCode.REDUCE_TO_TARGET
        if sell_qty == 0:
            decisions[instrument_id] = (
                current_qty,
                (AllocationReasonCode.HOLD_ODD_LOT_PROFILE,),
                reserve(instrument_id, TradeSide.SELL, 0, price),
            )
            continue
        fees = reserve(instrument_id, TradeSide.SELL, sell_qty, price)
        proceeds = Money(Decimal(sell_qty) * price) - fees.market_fees - fees.broker_fees
        available = available + proceeds
        decisions[instrument_id] = (current_qty - sell_qty, (reason,), fees)

    # Pass 2: buys under the remaining budget, ranked by descending absolute
    # target-weight deficit, canonical InstrumentId as tie-breaker.
    buy_candidates = [
        instrument_id
        for instrument_id in sorted(approved)
        if instrument_id not in decisions
        and approved[instrument_id].approved_weight > current_weight[instrument_id]
    ]
    for instrument_id in sorted(
        buy_candidates,
        key=lambda item: (
            -(approved[item].approved_weight - current_weight[item]),
            item,
        ),
    ):
        position = approved[instrument_id]
        rule = lot_rule_for(instrument_id)
        price = prices[instrument_id]
        current_qty = holdings.get(instrument_id, 0)
        unrounded_shares = position.approved_weight * equity / price
        target_qty = _floor_to_lot(unrounded_shares, rule.buy_increment)
        desired = target_qty - current_qty
        if desired <= 0:
            reason = (
                AllocationReasonCode.HOLD_BELOW_ONE_LOT
                if unrounded_shares > current_qty
                else AllocationReasonCode.HOLD_AT_TARGET
            )
            decisions[instrument_id] = (
                current_qty,
                (reason,),
                reserve(instrument_id, TradeSide.BUY, 0, price),
            )
            continue
        if desired < rule.buy_increment:
            decisions[instrument_id] = (
                current_qty,
                (AllocationReasonCode.HOLD_BELOW_ONE_LOT,),
                reserve(instrument_id, TradeSide.BUY, 0, price),
            )
            continue
        accepted = 0
        fees = reserve(instrument_id, TradeSide.BUY, 0, price)
        lots = desired // rule.buy_increment
        while lots >= 1:
            quantity = lots * rule.buy_increment
            candidate_fees = fee_estimator.estimate(
                instrument_id, TradeSide.BUY, quantity, price
            )
            total = (
                Money(Decimal(quantity) * price)
                + candidate_fees.market_fees
                + candidate_fees.broker_fees
            )
            if total <= available:
                accepted = quantity
                fees = candidate_fees
                break
            lots -= 1
        if accepted == 0:
            decisions[instrument_id] = (
                current_qty,
                (AllocationReasonCode.INSUFFICIENT_CASH_FOR_ONE_LOT,),
                fees,
            )
            continue
        available = (
            available
            - Money(Decimal(accepted) * price)
            - fees.market_fees
            - fees.broker_fees
        )
        reason = (
            AllocationReasonCode.BUY_FULL_TARGET
            if accepted == desired
            else AllocationReasonCode.BUY_REDUCED_TO_AFFORD
        )
        decisions[instrument_id] = (current_qty + accepted, (reason,), fees)

    # Any approved instrument left is an exact hold at the lot-adjusted target.
    for instrument_id in sorted(approved):
        if instrument_id in decisions:
            continue
        position = approved[instrument_id]
        rule = lot_rule_for(instrument_id)
        price = prices[instrument_id]
        current_qty = holdings.get(instrument_id, 0)
        decisions[instrument_id] = (
            current_qty,
            (AllocationReasonCode.HOLD_AT_TARGET,),
            reserve(instrument_id, TradeSide.BUY, 0, price),
        )
        del rule, price

    if available.amount < 0:
        raise AllocationError(
            f"executable conversion produced negative cash {available.amount}"
        )

    positions = []
    for instrument_id in sorted(approved):
        position = approved[instrument_id]
        planned_quantity, reasons, fees = decisions[instrument_id]
        price = prices[instrument_id]
        positions.append(
            ExecutablePosition(
                instrument_id=instrument_id,
                sleeve=position.sleeve,
                theoretical_weight=position.theoretical_weight,
                current_weight=current_weight[instrument_id],
                executable_weight=Decimal(planned_quantity) * price / equity,
                target_amount=Money(position.approved_weight * equity),
                planned_quantity=planned_quantity,
                sizing_reference_price_basis=SizingPriceBasis.T_CLOSE,
                sizing_reference_price=price,
                estimated_market_fees=fees.market_fees,
                estimated_broker_fees=fees.broker_fees,
                reason_codes=reasons,
            )
        )
    return ExecutableTargetPortfolio(
        target_id=approved_target.target_id,
        revision=approved_target.revision,
        decision_for_trade_date=approved_target.decision_for_trade_date,
        information_cutoff=approved_target.information_cutoff,
        valuation_equity=approved_target.valuation_equity,
        positions=tuple(positions),
        residual_cash=available,
        composition_version=approved_target.composition_version,
    )
