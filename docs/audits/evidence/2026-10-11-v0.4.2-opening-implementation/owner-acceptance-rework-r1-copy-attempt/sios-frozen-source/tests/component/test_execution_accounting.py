"""Component tests: T+1 activation (global affordability) and accounting.

Every expected number below is hand-calculated from the fixture facts:
T+1 opens, side-aware slippage, tick rounding, Instrument Master market
fee/tax rules, the run-owned broker profile, and CNY 2,500 cash. The
activator is exercised directly; the full event loop is a later task.
"""

from datetime import UTC, date, datetime
from decimal import Decimal

from systematic_investing.backtest.accounting import (
    mark_to_market,
    nav_point_of,
)
from systematic_investing.backtest.execution import (
    ActivationReason,
    ExecutionModel,
    PendingPlan,
    activate_pending_plans,
)
from systematic_investing.domain.execution import (
    AccountFeeConfig,
    BrokerFeeProfile,
    RejectionCode,
)
from systematic_investing.domain.identifiers import Exchange, InstrumentId, SleeveId
from systematic_investing.domain.ledger import (
    AcquisitionLot,
    CashLedgerCategory,
    IncompleteValuationReason,
    Position,
    ValuationStatus,
)
from systematic_investing.domain.market import (
    Availability,
    AvailabilityBasis,
    TradabilityStatus,
    TradabilityStatusKind,
    TradeSide,
)
from systematic_investing.domain.money import Money
from systematic_investing.instrument_master.repository import default_m0_master

XSHG_510300 = InstrumentId(exchange=Exchange.XSHG, symbol="510300")
XSHE_000001 = InstrumentId(exchange=Exchange.XSHE, symbol="000001")

DECISION_SESSION = date(2026, 9, 11)
EXECUTION_SESSION = date(2026, 9, 14)
RECORDED_AT = datetime(2026, 9, 14, 9, 30, tzinfo=UTC)
GENERATED_AT = datetime(2026, 9, 11, 15, 30, tzinfo=UTC)

MASTER = default_m0_master()

EXECUTION_MODEL = ExecutionModel(
    slippage_rate_buy=Decimal("0.001"),
    slippage_rate_sell=Decimal("0.001"),
)

BROKER = BrokerFeeProfile(
    profile_id="ACCT:MAIN",
    version="1",
    commission_rate=Decimal("0.0003"),
    minimum_commission=Decimal("5"),
    agreement_reference="broker-agreement-2026",
    effective_from=date(2022, 1, 4),
    effective_to=None,
)
ACCOUNT_FEES = AccountFeeConfig(
    config_id="RUN-MAIN",
    config_version="1",
    broker_profiles=(BROKER,),
)


def xshg_calendar():
    from systematic_investing.domain.market import MarketCalendar, TradingSession

    sessions = (
        date(2026, 9, 11),
        date(2026, 9, 14),
        date(2026, 9, 15),
    )
    return MarketCalendar(
        calendar_id="XSHG",
        snapshot_version="CAL-TEST-1",
        sessions=tuple(
            TradingSession(
                calendar_id="XSHG",
                session_date=session_date,
                is_open=True,
                note=None,
                snapshot_version="CAL-TEST-1",
            )
            for session_date in sessions
        ),
    )


def rules_for(instrument_id: InstrumentId):
    return MASTER.resolve_rules(instrument_id, EXECUTION_SESSION)


def tradable(instrument_id: InstrumentId) -> TradabilityStatus:
    return TradabilityStatus(
        instrument_id=instrument_id,
        session_date=EXECUTION_SESSION,
        status=TradabilityStatusKind.TRADABLE,
        reason=None,
        availability=Availability(
            information_available_at=datetime(2026, 9, 11, 15, 0, tzinfo=UTC),
            retrieved_at=RECORDED_AT,
            availability_basis=AvailabilityBasis.OBSERVED,
        ),
        provenance="exchange-fact",
    )


def buy_plan(
    instrument_id: InstrumentId,
    order_quantity: int,
    target_weight: str,
    sizing_close: str,
) -> PendingPlan:
    return PendingPlan(
        instrument_id=instrument_id,
        sleeve=SleeveId.CORE,
        side=TradeSide.BUY,
        order_quantity=order_quantity,
        target_weight=Decimal(target_weight),
        current_weight=Decimal("0"),
        target_id="target-2026-09-11",
        target_revision=1,
        decision_for_trade_date=DECISION_SESSION,
        sizing_reference_price=Decimal(sizing_close),
    )


def sell_plan(instrument_id: InstrumentId, order_quantity: int, current_weight: str) -> PendingPlan:
    return PendingPlan(
        instrument_id=instrument_id,
        sleeve=SleeveId.CORE,
        side=TradeSide.SELL,
        order_quantity=order_quantity,
        target_weight=Decimal("0"),
        current_weight=Decimal(current_weight),
        target_id="target-2026-09-11",
        target_revision=1,
        decision_for_trade_date=DECISION_SESSION,
        sizing_reference_price=Decimal("4.00"),
    )


def activate(plans, cash, opens, tradability=None, positions=()):
    if tradability is None:
        tradability = {instrument: tradable(instrument) for instrument in opens}
    return activate_pending_plans(
        plans=plans,
        cash=cash,
        positions=positions,
        opens=opens,
        tradability=tradability,
        rules={instrument: rules_for(instrument) for instrument in opens},
        account_fees=ACCOUNT_FEES,
        execution_model=EXECUTION_MODEL,
        calendar=xshg_calendar(),
        execution_session=EXECUTION_SESSION,
        recorded_at=RECORDED_AT,
    )


class TestGlobalAffordabilityGap:
    """CNY 2,500 cash; simultaneous T+1 gap-up buys.

    Hand calculation, buys ranked by descending deficit (000001: 0.024 >
    510300: 0.004):

    - 000001 open 12.60 -> 12.60*1.001 = 12.6126 -> ceil tick 0.01 = 12.62.
      Planned 200: 2524.00 + fees 5.03 = 2529.03 > 2500 -> 1 lot (100):
      1262.00 + fees (0.38 + 4.62 + 0.01) = 1267.01 -> submitted 100,
      cash left 1232.99.
    - 510300 open 4.40 -> 4.40*1.001 = 4.4044 -> ceil tick 0.001 = 4.405.
      100 shares: 440.50 + fees 5.00 = 445.50 -> submitted 100,
      cash left 787.49.
    """

    def opens(self):
        return {XSHE_000001: Decimal("12.60"), XSHG_510300: Decimal("4.40")}

    def test_planned_quantities_are_reduced_by_complete_lots_globally(self) -> None:
        plans = [
            buy_plan(XSHE_000001, 200, "0.024", "12.00"),
            buy_plan(XSHG_510300, 100, "0.004", "4.00"),
        ]

        result = activate(plans, Money(Decimal("2500")), self.opens())

        orders = {order.instrument_id: order for order in result.orders}
        stock_order = orders[XSHE_000001]
        etf_order = orders[XSHG_510300]
        assert stock_order.planned_quantity == 200
        assert stock_order.submitted_quantity == 100
        assert etf_order.planned_quantity == 100
        assert etf_order.submitted_quantity == 100
        assert result.cash == Money(Decimal("787.49"))

    def test_per_order_constraint_reasons_record_the_gap(self) -> None:
        plans = [
            buy_plan(XSHE_000001, 200, "0.024", "12.00"),
            buy_plan(XSHG_510300, 100, "0.004", "4.00"),
        ]

        result = activate(plans, Money(Decimal("2500")), self.opens())

        orders = {order.instrument_id: order for order in result.orders}
        assert ActivationReason.REDUCED_TO_AFFORD_T1_GAP in orders[XSHE_000001].reason_codes
        assert ActivationReason.FILLED_AS_PLANNED in orders[XSHG_510300].reason_codes

    def test_fills_are_all_or_none_at_the_execution_price(self) -> None:
        plans = [
            buy_plan(XSHE_000001, 200, "0.024", "12.00"),
            buy_plan(XSHG_510300, 100, "0.004", "4.00"),
        ]

        result = activate(plans, Money(Decimal("2500")), self.opens())

        fills = {fill.instrument_id: fill for fill in result.fills}
        assert fills[XSHE_000001].quantity == 100
        assert fills[XSHE_000001].fill_price == Decimal("12.62")
        assert fills[XSHG_510300].quantity == 100
        assert fills[XSHG_510300].fill_price == Decimal("4.405")

    def test_itemized_costs_and_holdings_ledger(self) -> None:
        plans = [
            buy_plan(XSHE_000001, 200, "0.024", "12.00"),
            buy_plan(XSHG_510300, 100, "0.004", "4.00"),
        ]

        result = activate(plans, Money(Decimal("2500")), self.opens())

        by_category = {}
        for entry in result.cash_entries:
            by_category.setdefault(entry.category, Decimal("0"))
            by_category[entry.category] += entry.amount.amount
        assert by_category[CashLedgerCategory.BUY_CONSIDERATION] == Decimal("-1702.50")
        assert by_category[CashLedgerCategory.BROKER_COMMISSION] == Decimal("-10.00")
        assert by_category[CashLedgerCategory.TRANSFER_FEE] == Decimal("-0.01")

        instrument_ids = tuple(
            sorted(str(entry.instrument_id) for entry in result.holdings_entries)
        )
        assert instrument_ids == ("XSHE:000001", "XSHG:510300")
        for entry in result.holdings_entries:
            assert entry.quantity_delta == 100
            assert entry.acquisition_session == EXECUTION_SESSION
            assert entry.sellable_from == date(2026, 9, 15)

    def test_input_ordering_does_not_change_the_activation(self) -> None:
        plans = [
            buy_plan(XSHG_510300, 100, "0.004", "4.00"),
            buy_plan(XSHE_000001, 200, "0.024", "12.00"),
        ]
        reversed_plans = list(reversed(plans))

        first = activate(plans, Money(Decimal("2500")), self.opens())
        second = activate(reversed_plans, Money(Decimal("2500")), self.opens())

        assert first.orders == second.orders
        assert first.fills == second.fills
        assert first.cash == second.cash


class TestSellSideActivation:
    def test_sell_fills_at_floor_ticked_slippage_price(self) -> None:
        # Sell 100 ETF at open 4.40: 4.40*0.999 = 4.3956 -> floor tick 0.001
        # = 4.395; proceeds 439.50 minus fees 5.00 -> cash 2934.50.
        position = Position(
            instrument_id=XSHG_510300,
            lots=(
                AcquisitionLot(
                    quantity=100,
                    acquired_session=date(2026, 9, 11),
                    sellable_from=date(2026, 9, 14),
                    acquisition_price=Decimal("4.00"),
                ),
            ),
        )

        result = activate(
            [sell_plan(XSHG_510300, 100, "0.004")],
            Money(Decimal("2500")),
            {XSHG_510300: Decimal("4.40")},
            positions=(position,),
        )

        assert result.cash == Money(Decimal("2934.50"))
        assert result.positions[0].total_quantity == 0

    def test_selling_beyond_sellable_quantity_is_rejected(self) -> None:
        position = Position(
            instrument_id=XSHG_510300,
            lots=(
                AcquisitionLot(
                    quantity=100,
                    acquired_session=EXECUTION_SESSION,
                    sellable_from=date(2026, 9, 15),
                    acquisition_price=Decimal("4.00"),
                ),
            ),
        )

        result = activate(
            [sell_plan(XSHG_510300, 100, "0.004")],
            Money(Decimal("2500")),
            {XSHG_510300: Decimal("4.40")},
            positions=(position,),
        )

        rejections = {rejection.instrument_id: rejection for rejection in result.rejections}
        assert rejections[XSHG_510300].code == RejectionCode.INSUFFICIENT_SELLABLE_QUANTITY
        assert result.cash == Money(Decimal("2500"))
        assert result.positions[0].total_quantity == 100


class TestTradabilityRejections:
    def suspended(self, instrument_id: InstrumentId) -> TradabilityStatus:
        return TradabilityStatus(
            instrument_id=instrument_id,
            session_date=EXECUTION_SESSION,
            status=TradabilityStatusKind.SUSPENDED,
            reason="halted",
            availability=Availability(
                information_available_at=datetime(2026, 9, 11, 15, 0, tzinfo=UTC),
                retrieved_at=RECORDED_AT,
                availability_basis=AvailabilityBasis.OBSERVED,
            ),
            provenance="exchange-fact",
        )

    def test_suspended_instrument_is_rejected_without_a_fill(self) -> None:
        result = activate(
            [sell_plan(XSHG_510300, 100, "0.004")],
            Money(Decimal("2500")),
            {XSHG_510300: Decimal("4.40")},
            tradability={XSHG_510300: self.suspended(XSHG_510300)},
        )

        assert result.rejections[0].code == RejectionCode.SUSPENDED
        assert result.fills == ()
        assert result.cash == Money(Decimal("2500"))

    def test_missing_tradability_fails_closed_as_unknown(self) -> None:
        result = activate(
            [buy_plan(XSHG_510300, 100, "0.004", "4.00")],
            Money(Decimal("2500")),
            {XSHG_510300: Decimal("4.40")},
            tradability={},
        )

        assert result.rejections[0].code == RejectionCode.TRADABILITY_UNKNOWN


class TestValuation:
    def held_position(self) -> Position:
        return Position(
            instrument_id=XSHG_510300,
            lots=(
                AcquisitionLot(
                    quantity=100,
                    acquired_session=date(2026, 9, 11),
                    sellable_from=date(2026, 9, 14),
                    acquisition_price=Decimal("4.00"),
                ),
            ),
        )

    def test_suspended_position_uses_last_valid_close_with_stale_mark(self) -> None:
        snapshot = mark_to_market(
            cash=Money(Decimal("50000")),
            positions=(self.held_position(),),
            session_date=EXECUTION_SESSION,
            generated_at=GENERATED_AT,
            calendar=xshg_calendar(),
            close_prices={},
            last_valid_closes={XSHG_510300: (Decimal("4.00"), date(2026, 9, 11))},
        )

        assert snapshot.valuation_status is ValuationStatus.COMPLETE
        assert snapshot.market_value == Money(Decimal("400.00"))
        assert snapshot.total_equity == Money(Decimal("50400.00"))
        assert len(snapshot.stale_marks) == 1
        mark = snapshot.stale_marks[0]
        assert mark.marked_price == Decimal("4.00")
        assert mark.age_sessions == 1

    def test_incomplete_valuation_is_recorded_with_its_reason(self) -> None:
        snapshot = mark_to_market(
            cash=Money(Decimal("50000")),
            positions=(self.held_position(),),
            session_date=EXECUTION_SESSION,
            generated_at=GENERATED_AT,
            calendar=xshg_calendar(),
            close_prices={},
            last_valid_closes={},
            incomplete_valuations={
                XSHG_510300: IncompleteValuationReason.CORPORATE_ACTION_INVALIDATED_PRICE
            },
        )

        assert snapshot.valuation_status is ValuationStatus.INCOMPLETE
        assert (
            IncompleteValuationReason.CORPORATE_ACTION_INVALIDATED_PRICE
            in snapshot.incomplete_reasons
        )

    def test_unpriceable_holding_makes_the_valuation_incomplete(self) -> None:
        snapshot = mark_to_market(
            cash=Money(Decimal("50000")),
            positions=(self.held_position(),),
            session_date=EXECUTION_SESSION,
            generated_at=GENERATED_AT,
            calendar=xshg_calendar(),
            close_prices={},
            last_valid_closes={},
        )

        assert snapshot.valuation_status is ValuationStatus.INCOMPLETE
        assert IncompleteValuationReason.NO_DEFENSIBLE_PRICE in snapshot.incomplete_reasons

    def test_nav_point_relates_equity_to_the_initial_capital(self) -> None:
        snapshot = mark_to_market(
            cash=Money(Decimal("50000")),
            positions=(self.held_position(),),
            session_date=EXECUTION_SESSION,
            generated_at=GENERATED_AT,
            calendar=xshg_calendar(),
            close_prices={XSHG_510300: Decimal("4.10")},
        )
        nav_point = nav_point_of(snapshot)

        assert nav_point.nav == Decimal("0.5041")
        assert nav_point.total_equity == Money(Decimal("50410.00"))
