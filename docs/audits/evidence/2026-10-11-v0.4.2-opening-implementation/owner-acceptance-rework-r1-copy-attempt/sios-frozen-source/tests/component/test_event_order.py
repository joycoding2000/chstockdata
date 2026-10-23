"""Component tests: the documented ten-step daily event order.

The engine sizes from the finalized T close, creates a pending plan for
``calendar.next_session(T)``, activates it at the next open with side-aware
slippage plus tick rounding, values the account at the session close, and only
then accepts the next predetermined target. Every number below is
hand-calculated from the fixture facts.
"""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from systematic_investing.backtest.engine import AmbiguousMarketFactError
from systematic_investing.backtest.execution import ActivationReason
from systematic_investing.domain.identifiers import Exchange, InstrumentId, SleeveId
from systematic_investing.domain.market import TradeSide
from systematic_investing.domain.money import Money

XSHG_510300 = InstrumentId(exchange=Exchange.XSHG, symbol="510300")
XSHE_000001 = InstrumentId(exchange=Exchange.XSHE, symbol="000001")

S_0911 = date(2026, 9, 11)
S_0914 = date(2026, 9, 14)

DECISION_CUTOFF_0911 = datetime(2026, 9, 11, 15, 30, tzinfo=UTC)


class TestTCloseSizing:
    """CNY 100,000 cash; target 1% of the Huatai-PineBridge CSI 300 ETF.

    Hand calculation at the 2026-09-11 close 4.00: 0.01 * 100,000 = 1,000 CNY
    -> 250 shares -> floor to the 100-share board lot -> ``planned_quantity``
    200 (executable weight 0.008, theoretical weight unchanged at 0.01).
    """

    def one_session_engine(
        self,
        make_engine,
        bar_factory,
        target_contribution,
        predetermined_targets,
        tradability_factory,
    ):
        bars = (bar_factory(XSHG_510300, S_0911, open="4.20", close="4.00"),)
        source = predetermined_targets(
            {S_0911: (target_contribution(XSHG_510300, "0.01"),)}
        )
        return make_engine(
            bars=bars,
            tradability=(tradability_factory(XSHG_510300, S_0914),),
            target_source=source,
        )

    def test_decision_sizes_from_the_finalized_t_close(
        self,
        make_engine,
        bar_factory,
        target_contribution,
        predetermined_targets,
        tradability_factory,
    ):
        engine = self.one_session_engine(
            make_engine,
            bar_factory,
            target_contribution,
            predetermined_targets,
            tradability_factory,
        )

        result = engine.run(start_session=S_0911, end_session=S_0911)

        t = result.session(S_0911)
        assert t.plans[0].instrument_id == XSHG_510300
        assert t.plans[0].side is TradeSide.BUY
        assert t.plans[0].sleeve is SleeveId.CORE
        assert t.plans[0].order_quantity == 200
        assert t.plans[0].sizing_reference_price == Decimal("4.00")
        assert t.plans[0].target_weight == Decimal("0.01")
        assert t.plans[0].current_weight == Decimal("0")
        assert t.plans[0].decision_for_trade_date == S_0911

    def test_target_locks_the_t_decision_identity_and_cash_weight(
        self,
        make_engine,
        bar_factory,
        target_contribution,
        predetermined_targets,
        tradability_factory,
    ):
        engine = self.one_session_engine(
            make_engine,
            bar_factory,
            target_contribution,
            predetermined_targets,
            tradability_factory,
        )

        result = engine.run(start_session=S_0911, end_session=S_0911)

        target = result.session(S_0911).target
        assert target is not None
        assert target.target_id == "target:2026-09-11"
        assert target.revision == 1
        assert target.decision_for_trade_date == S_0914
        assert target.generated_at == DECISION_CUTOFF_0911
        assert target.information_cutoff == DECISION_CUTOFF_0911
        assert target.valuation_equity == Money(Decimal("100000.00"))
        assert target.cash_weight == Decimal("0.99")

    def test_no_order_fills_on_the_decision_session(
        self,
        make_engine,
        bar_factory,
        target_contribution,
        predetermined_targets,
        tradability_factory,
    ):
        engine = self.one_session_engine(
            make_engine,
            bar_factory,
            target_contribution,
            predetermined_targets,
            tradability_factory,
        )

        result = engine.run(start_session=S_0911, end_session=S_0911)

        t = result.session(S_0911)
        assert t.activation.orders == ()
        assert t.activation.fills == ()
        assert t.snapshot.positions == ()
        assert t.snapshot.cash == Money(Decimal("100000"))


class TestNextSessionOpenActivation:
    """The 200-share plan activates at the 2026-09-14 open 4.40.

    Hand calculation: 4.40 * 1.001 = 4.4044 -> ceil to the 0.001 ETF tick =
    4.405; 200 shares = 881.00 CNY notional; commission 881 * 0.0003 = 0.26
    (minimum 5.00 -> 4.74 adjustment); ETF stamp/transfer fees are zero, so
    total fees are 5.00 and cash is 100,000 - 886.00 = 99,114.00. At the
    2026-09-14 close 4.50 the position is worth 900.00 and equity is
    100,014.00 (NAV 1.00014).
    """

    def two_session_engine(
        self,
        make_engine,
        bar_factory,
        target_contribution,
        predetermined_targets,
        tradability_factory,
    ):
        bars = (
            bar_factory(XSHG_510300, S_0911, open="4.20", close="4.00"),
            bar_factory(XSHG_510300, S_0914, open="4.40", close="4.50"),
        )
        source = predetermined_targets(
            {S_0911: (target_contribution(XSHG_510300, "0.01"),)}
        )
        return make_engine(
            bars=bars,
            tradability=(tradability_factory(XSHG_510300, S_0914),),
            target_source=source,
        )

    def test_pending_order_fills_at_the_next_open_slippage_price(
        self,
        make_engine,
        bar_factory,
        target_contribution,
        predetermined_targets,
        tradability_factory,
    ):
        engine = self.two_session_engine(
            make_engine,
            bar_factory,
            target_contribution,
            predetermined_targets,
            tradability_factory,
        )

        result = engine.run(start_session=S_0911, end_session=S_0914)

        t1 = result.session(S_0914)
        assert len(t1.activation.fills) == 1
        fill = t1.activation.fills[0]
        assert fill.quantity == 200
        assert fill.reference_open == Decimal("4.40")
        assert fill.fill_price == Decimal("4.405")
        assert fill.fees.total == Money(Decimal("5.00"))

        order = t1.activation.orders[0]
        assert order.planned_quantity == 200
        assert order.submitted_quantity == 200
        assert order.execution_session == S_0914
        assert order.sizing_reference_price == Decimal("4.00")
        assert order.fill_price_model == "NEXT_SESSION_OPEN"

    def test_fill_precedes_close_valuation(
        self,
        make_engine,
        bar_factory,
        target_contribution,
        predetermined_targets,
        tradability_factory,
    ):
        engine = self.two_session_engine(
            make_engine,
            bar_factory,
            target_contribution,
            predetermined_targets,
            tradability_factory,
        )

        result = engine.run(start_session=S_0911, end_session=S_0914)

        snapshot = result.session(S_0914).snapshot
        assert snapshot.positions[0].total_quantity == 200
        assert snapshot.cash == Money(Decimal("99114.00"))
        assert snapshot.market_value == Money(Decimal("900.00"))
        assert snapshot.total_equity == Money(Decimal("100014.00"))
        assert result.session(S_0914).nav.nav == Decimal("1.00014")

    def test_next_decision_valued_on_post_fill_equity(
        self,
        make_engine,
        bar_factory,
        target_contribution,
        predetermined_targets,
        tradability_factory,
    ):
        bars = (
            bar_factory(XSHG_510300, S_0911, open="4.20", close="4.00"),
            bar_factory(XSHG_510300, S_0914, open="4.40", close="4.50"),
        )
        source = predetermined_targets(
            {
                S_0911: (target_contribution(XSHG_510300, "0.01"),),
                S_0914: (target_contribution(XSHG_510300, "0.02"),),
            }
        )
        engine = make_engine(
            bars=bars,
            tradability=(tradability_factory(XSHG_510300, S_0914),),
            target_source=source,
        )

        result = engine.run(start_session=S_0911, end_session=S_0914)

        # 0.02 * 100,014.00 = 2,000.28 CNY at the 4.50 close -> 444 shares
        # floored to 400; current 200 -> buy 200 more.
        t1 = result.session(S_0914)
        assert t1.target is not None
        assert t1.target.valuation_equity == Money(Decimal("100014.00"))
        assert t1.plans[0].order_quantity == 200
        assert t1.plans[0].sizing_reference_price == Decimal("4.50")


class TestGlobalAffordabilityGap:
    """CNY 3,000 cash; two simultaneous buys sized at the 2026-09-11 close.

    Hand calculation at the close: 000001 12.00 -> 0.80 * 3,000 = 2,400 ->
    200 shares + 5.02 fees = 2,405.02; 510300 4.00 -> 0.15 * 3,000 = 450 ->
    100 shares + 5.00 fees = 405.00; residual cash 189.98.

    The 2026-09-14 open gaps: 000001 24.00 -> 24.03 execution price, so 200
    shares (4,806.00) is unaffordable; the global pass reduces the largest
    deficit first (0.80) to 100 shares = 2,408.02, leaving 591.98 for 510300
    at 4.405 -> 100 shares = 445.50. ``planned_quantity`` and the locked
    target are never touched and each fill is all-or-none.
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
            bar_factory(XSHE_000001, S_0911, open="12.00", close="12.00"),
            bar_factory(XSHG_510300, S_0911, open="4.00", close="4.00"),
            bar_factory(XSHE_000001, S_0914, open="24.00", close="24.03"),
            bar_factory(XSHG_510300, S_0914, open="4.40", close="4.405"),
        )
        source = predetermined_targets(
            {
                S_0911: (
                    target_contribution(XSHE_000001, "0.8"),
                    target_contribution(XSHG_510300, "0.15"),
                )
            }
        )
        return make_engine(
            bars=bars,
            tradability=(
                tradability_factory(XSHE_000001, S_0914),
                tradability_factory(XSHG_510300, S_0914),
            ),
            target_source=source,
            initial_cash=Money(Decimal("3000")),
        )

    def test_gap_reduces_submitted_quantity_not_the_plan(
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

        result = engine.run(start_session=S_0911, end_session=S_0914)

        planned = {plan.instrument_id: plan for plan in result.session(S_0911).plans}
        assert planned[XSHE_000001].order_quantity == 200
        assert planned[XSHG_510300].order_quantity == 100
        target_digest = result.session(S_0911).target.content_digest

        t1 = result.session(S_0914)
        orders = {order.instrument_id: order for order in t1.activation.orders}
        assert orders[XSHE_000001].planned_quantity == 200
        assert orders[XSHE_000001].submitted_quantity == 100
        assert ActivationReason.REDUCED_TO_AFFORD_T1_GAP in orders[XSHE_000001].reason_codes
        assert orders[XSHG_510300].planned_quantity == 100
        assert orders[XSHG_510300].submitted_quantity == 100

        fills = {fill.instrument_id: fill for fill in t1.activation.fills}
        assert fills[XSHE_000001].quantity == 100
        assert fills[XSHE_000001].fill_price == Decimal("24.03")
        assert fills[XSHG_510300].quantity == 100
        assert fills[XSHG_510300].fill_price == Decimal("4.405")
        assert t1.snapshot.cash == Money(Decimal("146.48"))
        assert result.session(S_0911).target.content_digest == target_digest


class TestFrozenInputContract:
    def test_duplicate_bar_keys_fail_closed(
        self,
        make_engine,
        bar_factory,
        target_contribution,
        predetermined_targets,
        tradability_factory,
    ):
        duplicate = (
            bar_factory(XSHG_510300, S_0911, open="4.20", close="4.00"),
            bar_factory(XSHG_510300, S_0911, open="4.10", close="3.90"),
        )
        source = predetermined_targets({})

        with pytest.raises(AmbiguousMarketFactError):
            make_engine(bars=duplicate, target_source=source)


class TestDeterminism:
    def test_repeated_runs_and_input_ordering_match(
        self,
        make_engine,
        bar_factory,
        target_contribution,
        predetermined_targets,
        tradability_factory,
    ):
        bars = (
            bar_factory(XSHG_510300, S_0911, open="4.20", close="4.00"),
            bar_factory(XSHG_510300, S_0914, open="4.40", close="4.50"),
        )
        tradability = (tradability_factory(XSHG_510300, S_0914),)
        source = predetermined_targets(
            {S_0911: (target_contribution(XSHG_510300, "0.01"),)}
        )

        engine = make_engine(
            bars=bars, tradability=tradability, target_source=source
        )
        first = engine.run(start_session=S_0911, end_session=S_0914)
        repeated = engine.run(start_session=S_0911, end_session=S_0914)
        shuffled = make_engine(
            bars=tuple(reversed(bars)),
            tradability=tuple(reversed(tradability)),
            target_source=source,
        ).run(start_session=S_0911, end_session=S_0914)

        assert first == repeated
        assert first == shuffled
        assert first.content_digest() == shuffled.content_digest()
