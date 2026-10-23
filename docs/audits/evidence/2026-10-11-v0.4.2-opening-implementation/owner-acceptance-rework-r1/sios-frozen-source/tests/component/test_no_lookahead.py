"""Component tests: point-in-time decision slices and no-lookahead.

The T decision may observe only facts knowable at the T decision cutoff.
Mutating every fact after T must leave the T decision and pending order digest
byte-identical, while requesting a future slice from the decision context must
fail loudly instead of returning data.
"""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from systematic_investing.backtest.engine import (
    DecisionBlockReason,
    DecisionContext,
    FutureDataAccessError,
    InvalidDecisionContextError,
    UnknownFactError,
)
from systematic_investing.domain.identifiers import Exchange, InstrumentId
from systematic_investing.domain.market import (
    Availability,
    AvailabilityBasis,
    CorporateAction,
    CorporateActionKind,
    TradabilityStatusKind,
)
from systematic_investing.domain.money import Money

XSHE_000001 = InstrumentId(exchange=Exchange.XSHE, symbol="000001")

S_0910 = date(2026, 9, 10)
S_0911 = date(2026, 9, 11)
S_0914 = date(2026, 9, 14)
S_0915 = date(2026, 9, 15)

BUY_WEIGHT = "0.012"


def split_action(ex_date: date = S_0914) -> CorporateAction:
    announced = datetime(2026, 9, 1, 8, 0, tzinfo=UTC)
    return CorporateAction(
        action_id="ca:split:0914",
        instrument_id=XSHE_000001,
        action_kind=CorporateActionKind.SPLIT,
        ex_date=ex_date,
        record_date=None,
        pay_date=None,
        cash_amount=None,
        share_ratio=Decimal("2.0"),
        revision=1,
        availability=Availability(
            information_available_at=announced,
            retrieved_at=announced,
            availability_basis=AvailabilityBasis.OBSERVED,
        ),
        provenance="sse-disclosure",
    )


class TestNoLookahead:
    def baseline_engine(
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
            bar_factory(XSHE_000001, S_0915, open="12.40", close="12.40"),
        )
        source = predetermined_targets(
            {
                S_0910: (target_contribution(XSHE_000001, BUY_WEIGHT),),
                S_0911: (target_contribution(XSHE_000001, "0"),),
            }
        )
        return make_engine(
            bars=bars,
            tradability=(
                tradability_factory(XSHE_000001, S_0911),
                tradability_factory(XSHE_000001, S_0914),
            ),
            target_source=source,
        )

    def mutated_engine(
        self,
        make_engine,
        bar_factory,
        target_contribution,
        predetermined_targets,
        tradability_factory,
    ):
        """Identical through 2026-09-11; every later fact is different."""
        bars = (
            bar_factory(XSHE_000001, S_0910, open="11.90", close="12.00"),
            bar_factory(XSHE_000001, S_0911, open="12.00", close="12.20"),
            bar_factory(XSHE_000001, S_0914, open="99.00", close="99.00"),
            bar_factory(XSHE_000001, S_0915, open="98.00", close="98.00"),
        )
        source = predetermined_targets(
            {
                S_0910: (target_contribution(XSHE_000001, BUY_WEIGHT),),
                S_0911: (target_contribution(XSHE_000001, "0"),),
                S_0914: (target_contribution(XSHE_000001, "0.5"),),
            }
        )
        return make_engine(
            bars=bars,
            tradability=(
                tradability_factory(XSHE_000001, S_0911),
                # Mutated after T: the session is suspended there.
                tradability_factory(
                    XSHE_000001, S_0914, TradabilityStatusKind.SUSPENDED
                ),
            ),
            corporate_actions=(split_action(),),
            target_source=source,
        )

    def test_mutating_all_data_after_t_leaves_the_t_decision_identical(
        self,
        make_engine,
        bar_factory,
        target_contribution,
        predetermined_targets,
        tradability_factory,
    ):
        baseline = self.baseline_engine(
            make_engine,
            bar_factory,
            target_contribution,
            predetermined_targets,
            tradability_factory,
        ).run(start_session=S_0910, end_session=S_0914)
        mutated = self.mutated_engine(
            make_engine,
            bar_factory,
            target_contribution,
            predetermined_targets,
            tradability_factory,
        ).run(start_session=S_0910, end_session=S_0914)

        assert baseline.session(S_0910) == mutated.session(S_0910)
        assert baseline.session(S_0911) == mutated.session(S_0911)
        assert (
            baseline.session(S_0911).decision_digest
            == mutated.session(S_0911).decision_digest
        )
        # The mutation did change the later sessions, so the comparison above
        # is not vacuous.
        assert baseline.content_digest() != mutated.content_digest()

    def test_next_open_change_moves_the_fill_not_the_plan(
        self,
        make_engine,
        bar_factory,
        target_contribution,
        predetermined_targets,
        tradability_factory,
    ):
        def engine(open_price: str):
            bars = (
                bar_factory(XSHE_000001, S_0910, open="11.90", close="12.00"),
                bar_factory(XSHE_000001, S_0911, open=open_price, close=open_price),
            )
            source = predetermined_targets(
                {S_0910: (target_contribution(XSHE_000001, BUY_WEIGHT),)}
            )
            return make_engine(
                bars=bars,
                tradability=(tradability_factory(XSHE_000001, S_0911),),
                target_source=source,
            ).run(start_session=S_0910, end_session=S_0911)

        cheap = engine("12.30")
        expensive = engine("48.00")

        assert cheap.session(S_0910).plans == expensive.session(S_0910).plans
        assert (
            cheap.session(S_0910).decision_digest
            == expensive.session(S_0910).decision_digest
        )
        assert cheap.session(S_0911).activation.fills[0].quantity == 100
        assert expensive.session(S_0911).activation.fills[0].quantity == 100
        assert (
            cheap.session(S_0911).activation.fills[0].fill_price
            == Decimal("12.32")
        )
        assert (
            expensive.session(S_0911).activation.fills[0].fill_price
            == Decimal("48.05")
        )


class TestDecisionContextContract:
    def test_context_rejects_a_bar_that_is_not_knowable_at_the_cutoff(
        self,
        bar_factory,
    ):
        with pytest.raises(InvalidDecisionContextError):
            DecisionContext(
                session_date=S_0911,
                decision_for_trade_date=S_0914,
                information_cutoff=datetime(2026, 9, 11, 15, 30, tzinfo=UTC),
                cash=Money(Decimal("100000")),
                valuation_equity=Money(Decimal("100000")),
                positions=(),
                # The bar is retrieved after the cutoff and must be refused.
                bars=(
                    bar_factory(
                        XSHE_000001,
                        S_0911,
                        open="12.00",
                        close="12.20",
                        available_at=datetime(2026, 9, 11, 16, 0, tzinfo=UTC),
                    ),
                ),
            )

    def test_context_rejects_a_bar_after_the_decision_session(
        self,
        bar_factory,
    ):
        with pytest.raises(InvalidDecisionContextError):
            DecisionContext(
                session_date=S_0911,
                decision_for_trade_date=S_0914,
                information_cutoff=datetime(2026, 9, 11, 15, 30, tzinfo=UTC),
                cash=Money(Decimal("100000")),
                valuation_equity=Money(Decimal("100000")),
                positions=(),
                bars=(bar_factory(XSHE_000001, S_0914, open="12.30", close="12.30"),),
            )


class TestDecisionSlice:
    def capture(
        self,
        predetermined_targets,
        make_engine,
        bar_factory,
        target_contribution,
        tradability_factory,
    ):
        bars = (
            bar_factory(XSHE_000001, S_0910, open="11.90", close="12.00"),
            bar_factory(XSHE_000001, S_0911, open="12.00", close="12.20"),
        )
        source = predetermined_targets(
            {S_0911: (target_contribution(XSHE_000001, BUY_WEIGHT),)}
        )
        engine = make_engine(
            bars=bars,
            tradability=(tradability_factory(XSHE_000001, S_0911),),
            target_source=source,
        )
        engine.run(start_session=S_0911, end_session=S_0911)
        return source.contexts[0]

    def test_future_slice_request_fails_loudly(
        self,
        predetermined_targets,
        make_engine,
        bar_factory,
        target_contribution,
        tradability_factory,
    ):
        context = self.capture(
            predetermined_targets,
            make_engine,
            bar_factory,
            target_contribution,
            tradability_factory,
        )

        assert context.require_bar(XSHE_000001, S_0910).session_date == S_0910
        with pytest.raises(FutureDataAccessError):
            context.require_bar(XSHE_000001, S_0914)
        with pytest.raises(UnknownFactError):
            context.require_bar(XSHE_000001, date(2026, 9, 9))
        assert context.session_date == S_0911
        assert context.decision_for_trade_date == S_0914
        assert context.t_close_prices == {XSHE_000001: Decimal("12.20")}
        assert len(context.bars_for(XSHE_000001)) == 2

    def test_fact_unavailable_at_the_cutoff_is_not_in_the_slice(
        self,
        make_engine,
        bar_factory,
        target_contribution,
        predetermined_targets,
        tradability_factory,
    ):
        # The 2026-09-11 bar was only retrievable at 16:00, after the 15:30
        # decision cutoff: it cannot size the decision and the conversion
        # fails closed instead of using a stale or fabricated price.
        bars = (
            bar_factory(XSHE_000001, S_0910, open="11.90", close="12.00"),
            bar_factory(
                XSHE_000001,
                S_0911,
                open="12.00",
                close="12.20",
                available_at=datetime(2026, 9, 11, 16, 0, tzinfo=UTC),
            ),
        )
        source = predetermined_targets(
            {S_0911: (target_contribution(XSHE_000001, BUY_WEIGHT),)}
        )
        engine = make_engine(bars=bars, target_source=source)

        result = engine.run(start_session=S_0911, end_session=S_0911)

        context = source.contexts[0]
        assert context.t_close_prices == {}
        with pytest.raises(UnknownFactError):
            context.require_bar(XSHE_000001, S_0911)
        assert result.session(S_0911).decision_blocked_reason is (
            DecisionBlockReason.MISSING_T_CLOSE_PRICE
        )
        assert result.session(S_0911).plans == ()
