"""Component tests: tradability evaluation inside the daily event loop.

Suspension, unknown status, price-limit blocks, PIT availability, T+1
sellability, and stale-mark valuation are all exercised through the engine.
Expected cash/holdings/NAV numbers are hand-calculated from the fixture facts.
"""

from datetime import UTC, date, datetime
from decimal import Decimal

from systematic_investing.backtest.engine import DecisionBlockReason
from systematic_investing.domain.execution import RejectionCode
from systematic_investing.domain.identifiers import Exchange, InstrumentId
from systematic_investing.domain.ledger import AcquisitionLot, Position, ValuationStatus
from systematic_investing.domain.market import TradabilityStatusKind
from systematic_investing.domain.money import Money

XSHE_000001 = InstrumentId(exchange=Exchange.XSHE, symbol="000001")

S_0910 = date(2026, 9, 10)
S_0911 = date(2026, 9, 11)
S_0914 = date(2026, 9, 14)

BUY_WEIGHT_000001 = "0.012"


def held_position(quantity: int = 1000) -> Position:
    """1000 shares acquired 2026-09-01, sellable from 2026-09-02, cost 10.00."""
    return Position(
        instrument_id=XSHE_000001,
        lots=(
            AcquisitionLot(
                quantity=quantity,
                acquired_session=date(2026, 9, 1),
                sellable_from=date(2026, 9, 2),
                acquisition_price=Decimal("10.00"),
            ),
        ),
    )


class TestSuspendedAndUnknown:
    """A pending buy on a suspended session: no fill, typed rejection, no
    position change, and the locked target stays unmet."""

    def engine(
        self,
        make_engine,
        bar_factory,
        target_contribution,
        predetermined_targets,
        tradability_factory,
        status,
        *,
        tradability_available_at=None,
    ):
        bars = (bar_factory(XSHE_000001, S_0911, open="12.10", close="12.00"),)
        source = predetermined_targets(
            {S_0911: (target_contribution(XSHE_000001, BUY_WEIGHT_000001),)}
        )
        return make_engine(
            bars=bars,
            tradability=(
                tradability_factory(
                    XSHE_000001,
                    S_0914,
                    status,
                    reason="test fact",
                    available_at=tradability_available_at,
                ),
            ),
            target_source=source,
        )

    def test_suspended_buy_is_rejected_without_a_fill(
        self,
        make_engine,
        bar_factory,
        target_contribution,
        predetermined_targets,
        tradability_factory,
    ):
        engine = self.engine(
            make_engine,
            bar_factory,
            target_contribution,
            predetermined_targets,
            tradability_factory,
            TradabilityStatusKind.SUSPENDED,
        )

        result = engine.run(start_session=S_0911, end_session=S_0914)

        planned = result.session(S_0911).plans
        assert planned[0].order_quantity == 100
        t1 = result.session(S_0914)
        assert t1.activation.fills == ()
        assert t1.activation.rejections[0].code is RejectionCode.SUSPENDED
        assert t1.snapshot.cash == Money(Decimal("100000"))
        assert t1.snapshot.positions == ()

    def test_unknown_status_blocks_exposure(
        self,
        make_engine,
        bar_factory,
        target_contribution,
        predetermined_targets,
        tradability_factory,
    ):
        engine = self.engine(
            make_engine,
            bar_factory,
            target_contribution,
            predetermined_targets,
            tradability_factory,
            TradabilityStatusKind.UNKNOWN,
        )

        result = engine.run(start_session=S_0911, end_session=S_0914)

        assert (
            result.session(S_0914).activation.rejections[0].code
            is RejectionCode.TRADABILITY_UNKNOWN
        )

    def test_missing_tradability_fact_fails_closed_as_unknown(
        self, make_engine, bar_factory, target_contribution, predetermined_targets
    ):
        bars = (bar_factory(XSHE_000001, S_0911, open="12.10", close="12.00"),)
        source = predetermined_targets(
            {S_0911: (target_contribution(XSHE_000001, BUY_WEIGHT_000001),)}
        )
        engine = make_engine(bars=bars, tradability=(), target_source=source)

        result = engine.run(start_session=S_0911, end_session=S_0914)

        assert (
            result.session(S_0914).activation.rejections[0].code
            is RejectionCode.TRADABILITY_UNKNOWN
        )

    def test_fact_not_knowable_at_the_activation_cutoff_is_unknown(
        self,
        make_engine,
        bar_factory,
        target_contribution,
        predetermined_targets,
        tradability_factory,
    ):
        # Announced at 10:00 while activation happens at the 09:15 cutoff:
        # the engine must not use a fact it could not yet know.
        engine = self.engine(
            make_engine,
            bar_factory,
            target_contribution,
            predetermined_targets,
            tradability_factory,
            TradabilityStatusKind.TRADABLE,
            tradability_available_at=datetime(2026, 9, 14, 10, 0, tzinfo=UTC),
        )

        result = engine.run(start_session=S_0911, end_session=S_0914)

        assert (
            result.session(S_0914).activation.rejections[0].code
            is RejectionCode.TRADABILITY_UNKNOWN
        )


class TestPriceLimits:
    def test_upper_limit_buy_is_rejected(
        self,
        make_engine,
        bar_factory,
        target_contribution,
        predetermined_targets,
        tradability_factory,
    ):
        bars = (
            bar_factory(XSHE_000001, S_0911, open="12.10", close="12.00"),
            bar_factory(XSHE_000001, S_0914, open="13.20", close="13.20"),
        )
        source = predetermined_targets(
            {S_0911: (target_contribution(XSHE_000001, BUY_WEIGHT_000001),)}
        )
        engine = make_engine(
            bars=bars,
            tradability=(
                tradability_factory(
                    XSHE_000001,
                    S_0914,
                    TradabilityStatusKind.BUY_BLOCKED_UPPER_LIMIT,
                ),
            ),
            target_source=source,
        )

        result = engine.run(start_session=S_0911, end_session=S_0914)

        t1 = result.session(S_0914)
        assert t1.activation.fills == ()
        assert (
            t1.activation.rejections[0].code is RejectionCode.BUY_BLOCKED_UPPER_LIMIT
        )
        assert t1.snapshot.positions == ()

    def test_lower_limit_sell_is_rejected_and_position_is_retained(
        self,
        make_engine,
        bar_factory,
        target_contribution,
        predetermined_targets,
        tradability_factory,
    ):
        bars = (
            bar_factory(XSHE_000001, S_0911, open="12.10", close="12.00"),
            bar_factory(
                XSHE_000001,
                S_0914,
                open="10.80",
                close="10.80",
                pre_close="12.00",
            ),
        )
        source = predetermined_targets(
            {S_0911: (target_contribution(XSHE_000001, "0"),)}
        )
        engine = make_engine(
            bars=bars,
            tradability=(
                tradability_factory(
                    XSHE_000001,
                    S_0914,
                    TradabilityStatusKind.SELL_BLOCKED_LOWER_LIMIT,
                ),
            ),
            target_source=source,
            initial_positions=(held_position(),),
        )

        result = engine.run(start_session=S_0911, end_session=S_0914)

        assert result.session(S_0911).plans[0].order_quantity == 1000
        t1 = result.session(S_0914)
        assert t1.activation.fills == ()
        assert (
            t1.activation.rejections[0].code is RejectionCode.SELL_BLOCKED_LOWER_LIMIT
        )
        assert t1.snapshot.positions[0].total_quantity == 1000
        assert t1.snapshot.market_value == Money(Decimal("10800.00"))
        assert t1.snapshot.total_equity == Money(Decimal("110800.00"))


class TestSettlementSellability:
    """Buy at T+1 settle: the 2026-09-11 purchase cannot be sold on
    2026-09-11; the exit decided after that close fills on 2026-09-14.

    Hand calculation:
    - 2026-09-10 close 12.00, target 0.012 -> 1,200 CNY -> 100 shares.
    - 2026-09-11 open 12.00 -> 12.00 * 1.001 = 12.012 -> ceil tick 12.02;
      1,202 notional + 5.01 fees -> cash 98,792.99.
    - 2026-09-11 close 12.20 -> equity 100,012.99; exit target 0.
    - 2026-09-14 open 12.30 -> 12.30 * 0.999 = 12.2877 -> floor tick 12.28;
      1,228 proceeds - 5.62 fees (0.61 stamp + 0.37 commission + 4.63
      minimum adjustment + 0.01 transfer) -> cash 100,015.37.
    """

    def engine(
        self,
        make_engine,
        bar_factory,
        target_contribution,
        predetermined_targets,
        tradability_factory,
    ):
        bars = (
            bar_factory(XSHE_000001, S_0910, open="11.90", close="12.00"),
            bar_factory(XSHE_000001, S_0911, open="12.00", close="12.20"),
            bar_factory(XSHE_000001, S_0914, open="12.30", close="12.30"),
        )
        source = predetermined_targets(
            {
                S_0910: (target_contribution(XSHE_000001, BUY_WEIGHT_000001),),
                S_0911: (target_contribution(XSHE_000001, "0"),),
            }
        )
        tradability = tuple(
            tradability_factory(XSHE_000001, session_date)
            for session_date in (S_0911, S_0914)
        )
        return make_engine(
            bars=bars, tradability=tradability, target_source=source
        )

    def test_acquisition_is_not_sellable_on_its_own_session(
        self,
        make_engine,
        bar_factory,
        target_contribution,
        predetermined_targets,
        tradability_factory,
    ):
        engine = self.engine(
            make_engine,
            bar_factory,
            target_contribution,
            predetermined_targets,
            tradability_factory,
        )

        result = engine.run(start_session=S_0910, end_session=S_0914)

        position = result.session(S_0911).snapshot.positions[0]
        assert position.total_quantity == 100
        assert position.sellable_quantity(S_0911) == 0
        assert position.sellable_quantity(S_0914) == 100

    def test_exit_fills_on_the_next_session_once_sellable(
        self,
        make_engine,
        bar_factory,
        target_contribution,
        predetermined_targets,
        tradability_factory,
    ):
        engine = self.engine(
            make_engine,
            bar_factory,
            target_contribution,
            predetermined_targets,
            tradability_factory,
        )

        result = engine.run(start_session=S_0910, end_session=S_0914)

        buy = result.session(S_0911).activation.fills[0]
        assert buy.side.value == "BUY"
        assert buy.fill_price == Decimal("12.02")
        assert result.session(S_0911).snapshot.cash == Money(Decimal("98792.99"))

        t1 = result.session(S_0914)
        sell = t1.activation.fills[0]
        assert sell.side.value == "SELL"
        assert sell.quantity == 100
        assert sell.fill_price == Decimal("12.28")
        assert t1.snapshot.cash == Money(Decimal("100015.37"))
        assert t1.snapshot.positions == ()


class TestStaleMarkValuation:
    """A long suspension is marked at the last valid RAW close with an
    explicit ``STALE_MARK``; valuation stays complete and no new exposure can
    be created, while a missing finalized close blocks the next decision."""

    def engine(
        self,
        make_engine,
        bar_factory,
        target_contribution,
        predetermined_targets,
        tradability_factory,
    ):
        bars = (bar_factory(XSHE_000001, S_0910, open="11.90", close="12.00"),)
        source = predetermined_targets(
            {
                S_0910: (target_contribution(XSHE_000001, "0.15"),),
                S_0914: (target_contribution(XSHE_000001, "0.16"),),
            }
        )
        tradability = tuple(
            tradability_factory(XSHE_000001, session_date, TradabilityStatusKind.SUSPENDED)
            for session_date in (S_0911, S_0914)
        )
        return make_engine(
            bars=bars,
            tradability=tradability,
            target_source=source,
            initial_positions=(held_position(),),
        )

    def test_suspended_holding_is_marked_at_last_valid_close(
        self,
        make_engine,
        bar_factory,
        target_contribution,
        predetermined_targets,
        tradability_factory,
    ):
        engine = self.engine(
            make_engine,
            bar_factory,
            target_contribution,
            predetermined_targets,
            tradability_factory,
        )

        result = engine.run(start_session=S_0910, end_session=S_0914)

        # 0.15 * 112,000 = 16,800 CNY at 12.00 -> 1,400 shares; the account
        # already holds 1,000, so the pending plan buys 400 more.
        assert result.session(S_0910).plans[0].order_quantity == 400

        t1 = result.session(S_0911)
        assert t1.activation.rejections[0].code is RejectionCode.SUSPENDED
        assert t1.snapshot.valuation_status is ValuationStatus.COMPLETE
        mark = t1.snapshot.stale_marks[0]
        assert mark.marked_price == Decimal("12.00")
        assert mark.last_valid_session == S_0910
        assert mark.age_sessions == 1
        assert t1.snapshot.market_value == Money(Decimal("12000.00"))

        t2 = result.session(S_0914)
        assert t2.snapshot.stale_marks[0].age_sessions == 2
        assert t2.snapshot.total_equity == Money(Decimal("112000.00"))

    def test_missing_finalized_close_blocks_the_next_decision(
        self,
        make_engine,
        bar_factory,
        target_contribution,
        predetermined_targets,
        tradability_factory,
    ):
        engine = self.engine(
            make_engine,
            bar_factory,
            target_contribution,
            predetermined_targets,
            tradability_factory,
        )

        result = engine.run(start_session=S_0910, end_session=S_0914)

        t2 = result.session(S_0914)
        assert t2.decision_blocked_reason is DecisionBlockReason.MISSING_T_CLOSE_PRICE
        assert t2.target is not None
        assert t2.target.content_digest
        assert t2.plans == ()
