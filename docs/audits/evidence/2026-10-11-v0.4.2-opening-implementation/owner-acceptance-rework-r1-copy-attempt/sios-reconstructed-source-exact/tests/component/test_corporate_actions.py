"""Component tests: effective-dated corporate actions in the event loop.

Cash dividends credit exactly once and never through a derived adjusted
series; quantity-changing actions scale acquisition lots and preserve
settlement dates; an intervening quantity-changing action invalidates the
affected pending execution with ``CORPORATE_ACTION_REPLAN_REQUIRED`` without
resynthesizing or mutating the locked target; and a quantity-changing action
invalidates a prior price that predates it.
"""

from datetime import UTC, date, datetime
from decimal import Decimal

from systematic_investing.backtest.engine import DecisionBlockReason
from systematic_investing.domain.execution import (
    ORDER_INVALIDATION_CORPORATE_ACTION,
    OrderStatus,
)
from systematic_investing.domain.identifiers import Exchange, InstrumentId
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
    CorporateAction,
    CorporateActionKind,
    TradabilityStatusKind,
)
from systematic_investing.domain.money import Money

XSHE_000001 = InstrumentId(exchange=Exchange.XSHE, symbol="000001")

S_0910 = date(2026, 9, 10)
S_0911 = date(2026, 9, 11)
S_0914 = date(2026, 9, 14)

ANNOUNCED_BEFORE = datetime(2026, 9, 1, 8, 0, tzinfo=UTC)
ANNOUNCED_AFTER_DECISION = datetime(2026, 9, 10, 20, 0, tzinfo=UTC)


def held_position(quantity: int = 1000) -> Position:
    """1000 shares acquired 2026-09-01, sellable from 2026-09-02, cost 12.00."""
    return Position(
        instrument_id=XSHE_000001,
        lots=(
            AcquisitionLot(
                quantity=quantity,
                acquired_session=date(2026, 9, 1),
                sellable_from=date(2026, 9, 2),
                acquisition_price=Decimal("12.00"),
            ),
        ),
    )


def corporate_action(
    *,
    action_kind: CorporateActionKind,
    ex_date: date = S_0911,
    cash_amount: Money | None = None,
    share_ratio: Decimal | None = None,
    information_available_at: datetime = ANNOUNCED_BEFORE,
) -> CorporateAction:
    return CorporateAction(
        action_id=f"ca:{action_kind.value}:{ex_date.isoformat()}",
        instrument_id=XSHE_000001,
        action_kind=action_kind,
        ex_date=ex_date,
        record_date=date(2026, 9, 10),
        pay_date=ex_date,
        cash_amount=cash_amount,
        share_ratio=share_ratio,
        revision=1,
        availability=Availability(
            information_available_at=information_available_at,
            retrieved_at=information_available_at,
            availability_basis=AvailabilityBasis.OBSERVED,
        ),
        provenance="sse-disclosure",
    )


class TestCashDividend:
    """Hold 1,000 shares through a 0.50 CNY/share dividend on 2026-09-11.

    Cash: 1,000 * 0.50 = 500.00 credited once. Holdings unchanged. The
    2026-09-11 RAW close 11.75 values the position (a declared adjustment
    factor must never produce a second account credit).
    """

    def engine(
        self, make_engine, bar_factory, predetermined_targets
    ):
        bars = (
            bar_factory(
                XSHE_000001,
                S_0910,
                open="12.00",
                close="12.00",
            ),
            bar_factory(
                XSHE_000001,
                S_0911,
                open="11.75",
                close="11.75",
                pre_close="12.00",
                factor="0.99",
            ),
        )
        return make_engine(
            bars=bars,
            corporate_actions=(
                corporate_action(
                    action_kind=CorporateActionKind.CASH_DIVIDEND,
                    cash_amount=Money(Decimal("0.50")),
                ),
            ),
            target_source=predetermined_targets({}),
            initial_cash=Money(Decimal("1000")),
            initial_positions=(held_position(),),
        )

    def test_dividend_credits_cash_exactly_once(
        self, make_engine, bar_factory, predetermined_targets
    ):
        engine = self.engine(
            make_engine, bar_factory, predetermined_targets
        )

        result = engine.run(start_session=S_0910, end_session=S_0911)

        effects = result.session(S_0911).corporate_action_effects
        assert len(effects) == 1
        assert effects[0].cash_delta == Money(Decimal("500.00"))
        assert effects[0].quantity_delta == 0
        assert effects[0].holdings_entry is None

        dividends = [
            entry
            for entry in result.cash_entries
            if entry.category is CashLedgerCategory.DIVIDEND
        ]
        assert len(dividends) == 1
        assert dividends[0].amount == Money(Decimal("500.00"))
        assert dividends[0].session_date == S_0911
        assert dividends[0].source_id == effects[0].action_id

    def test_holdings_are_unchanged_and_valued_at_the_raw_close(
        self, make_engine, bar_factory, predetermined_targets
    ):
        engine = self.engine(
            make_engine, bar_factory, predetermined_targets
        )

        result = engine.run(start_session=S_0910, end_session=S_0911)

        t1 = result.session(S_0911)
        assert t1.snapshot.positions[0].total_quantity == 1000
        assert t1.snapshot.cash == Money(Decimal("1500.00"))
        assert t1.snapshot.market_value == Money(Decimal("11750.00"))
        assert t1.snapshot.total_equity == Money(Decimal("13250.00"))


class TestQuantityChangingActions:
    """A 2:1 split on 2026-09-11 scales 1,000 shares to 2,000 at 6.00 cost."""

    def engine(
        self,
        make_engine,
        bar_factory,
        predetermined_targets,
        *,
        information_available_at: datetime = ANNOUNCED_BEFORE,
        extra_session: bool = False,
    ):
        bars = [
            bar_factory(XSHE_000001, S_0910, open="12.00", close="12.00"),
            bar_factory(
                XSHE_000001, S_0911, open="6.00", close="6.00", pre_close="12.00"
            ),
        ]
        if extra_session:
            bars.append(
                bar_factory(
                    XSHE_000001, S_0914, open="6.00", close="6.00", pre_close="6.00"
                )
            )
        return make_engine(
            bars=tuple(bars),
            corporate_actions=(
                corporate_action(
                    action_kind=CorporateActionKind.SPLIT,
                    share_ratio=Decimal("2.0"),
                    information_available_at=information_available_at,
                ),
            ),
            target_source=predetermined_targets({}),
            initial_cash=Money(Decimal("1000")),
            initial_positions=(held_position(),),
        )

    def test_split_scales_lots_and_preserves_sellability(
        self, make_engine, bar_factory, predetermined_targets
    ):
        engine = self.engine(make_engine, bar_factory, predetermined_targets)

        result = engine.run(start_session=S_0910, end_session=S_0911)

        t1 = result.session(S_0911)
        position = t1.snapshot.positions[0]
        assert position.total_quantity == 2000
        assert position.sellable_quantity(S_0911) == 2000
        assert position.average_cost == Decimal("6")
        entry = result.holdings_entries[0]
        assert entry.quantity_delta == 1000
        assert entry.instrument_id == XSHE_000001
        assert t1.snapshot.cash == Money(Decimal("1000.00"))
        assert t1.snapshot.market_value == Money(Decimal("12000.00"))

    def test_action_unknown_at_activation_is_applied_when_first_known(
        self, make_engine, bar_factory, predetermined_targets
    ):
        # Announced at 10:00 on the ex-date, after the 09:15 activation cutoff:
        # the ledger must not apply it retroactively at 2026-09-11.
        engine = self.engine(
            make_engine,
            bar_factory,
            predetermined_targets,
            information_available_at=datetime(2026, 9, 11, 10, 0, tzinfo=UTC),
            extra_session=True,
        )

        result = engine.run(start_session=S_0910, end_session=S_0914)

        assert result.session(S_0911).snapshot.positions[0].total_quantity == 1000
        assert result.session(S_0914).snapshot.positions[0].total_quantity == 2000


class TestInterveningActionInvalidation:
    """A split becomes effective between the 2026-09-10 exit decision and the
    2026-09-11 activation: the pending sell is invalidated, no substitute is
    submitted, holdings receive the split, and the locked target is unchanged.
    """

    def engine(
        self,
        make_engine,
        bar_factory,
        target_contribution,
        predetermined_targets,
        tradability_factory,
        *,
        with_split: bool,
    ):
        bars = (
            bar_factory(XSHE_000001, S_0910, open="12.00", close="12.00"),
            bar_factory(
                XSHE_000001, S_0911, open="6.00", close="6.00", pre_close="12.00"
            ),
        )
        actions = (
            (
                corporate_action(
                    action_kind=CorporateActionKind.SPLIT,
                    share_ratio=Decimal("2.0"),
                    information_available_at=ANNOUNCED_AFTER_DECISION,
                ),
            )
            if with_split
            else ()
        )
        source = predetermined_targets(
            {S_0910: (target_contribution(XSHE_000001, "0"),)}
        )
        return make_engine(
            bars=bars,
            tradability=(tradability_factory(XSHE_000001, S_0911),),
            corporate_actions=actions,
            target_source=source,
            initial_cash=Money(Decimal("1000")),
            initial_positions=(held_position(),),
        )

    def test_pending_sell_is_invalidated_without_a_substitute(
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
            with_split=True,
        )

        result = engine.run(start_session=S_0910, end_session=S_0911)

        assert result.session(S_0910).plans[0].order_quantity == 1000
        t1 = result.session(S_0911)
        invalidated = t1.invalidated_orders[0]
        assert invalidated.status is OrderStatus.INVALIDATED
        assert ORDER_INVALIDATION_CORPORATE_ACTION in invalidated.reason_codes
        assert invalidated.planned_quantity == 1000
        assert invalidated.submitted_quantity is None
        assert t1.activation.orders == ()
        assert t1.activation.fills == ()
        assert t1.snapshot.positions[0].total_quantity == 2000
        assert t1.snapshot.cash == Money(Decimal("1000.00"))

    def test_locked_target_is_untouched_by_the_intervening_action(
        self,
        make_engine,
        bar_factory,
        target_contribution,
        predetermined_targets,
        tradability_factory,
    ):
        with_split = self.engine(
            make_engine,
            bar_factory,
            target_contribution,
            predetermined_targets,
            tradability_factory,
            with_split=True,
        )
        without_split = self.engine(
            make_engine,
            bar_factory,
            target_contribution,
            predetermined_targets,
            tradability_factory,
            with_split=False,
        )

        split_result = with_split.run(start_session=S_0910, end_session=S_0911)
        plain_result = without_split.run(start_session=S_0910, end_session=S_0911)

        # The action was not knowable at the 2026-09-10 decision cutoff, so the
        # T decision and pending order digest must be byte-identical.
        assert (
            split_result.session(S_0910).decision_digest
            == plain_result.session(S_0910).decision_digest
        )
        assert split_result.session(S_0910).target == plain_result.session(S_0910).target
        # The action is applied and the plan is invalidated, not rescaled.
        assert split_result.session(S_0910).plans[0].order_quantity == 1000
        assert split_result.session(S_0911).invalidated_orders[0].planned_quantity == 1000


class TestNonQuantityChangingAction:
    def test_cash_dividend_does_not_invalidate_a_pending_buy(
        self,
        make_engine,
        bar_factory,
        target_contribution,
        predetermined_targets,
        tradability_factory,
    ):
        bars = (
            bar_factory(XSHE_000001, S_0910, open="12.00", close="12.00"),
            bar_factory(
                XSHE_000001, S_0911, open="12.00", close="12.00", pre_close="12.00"
            ),
        )
        source = predetermined_targets(
            {S_0910: (target_contribution(XSHE_000001, "0.012"),)}
        )
        engine = make_engine(
            bars=bars,
            tradability=(tradability_factory(XSHE_000001, S_0911),),
            corporate_actions=(
                corporate_action(
                    action_kind=CorporateActionKind.CASH_DIVIDEND,
                    cash_amount=Money(Decimal("0.50")),
                    information_available_at=ANNOUNCED_AFTER_DECISION,
                ),
            ),
            target_source=source,
        )

        result = engine.run(start_session=S_0910, end_session=S_0911)

        t1 = result.session(S_0911)
        assert t1.invalidated_orders == ()
        assert t1.activation.orders[0].status is OrderStatus.FILLED
        assert t1.activation.orders[0].submitted_quantity == 100
        assert t1.snapshot.cash == Money(Decimal("98792.99"))


class TestInvalidatedPrice:
    """A split effective during a suspension makes the last valid pre-split
    close economically invalid: the portfolio valuation is incomplete and no
    new target is created, while the normal ledger event still applies."""

    def test_quantity_change_invalidates_a_pre_action_price(
        self,
        make_engine,
        bar_factory,
        target_contribution,
        predetermined_targets,
        tradability_factory,
    ):
        bars = (bar_factory(XSHE_000001, S_0910, open="12.00", close="12.00"),)
        source = predetermined_targets(
            {S_0910: (target_contribution(XSHE_000001, "0"),)}
        )
        engine = make_engine(
            bars=bars,
            tradability=(
                tradability_factory(
                    XSHE_000001, S_0911, TradabilityStatusKind.SUSPENDED
                ),
            ),
            corporate_actions=(
                corporate_action(
                    action_kind=CorporateActionKind.SPLIT,
                    share_ratio=Decimal("2.0"),
                ),
            ),
            target_source=source,
            initial_cash=Money(Decimal("1000")),
            initial_positions=(held_position(),),
        )

        result = engine.run(start_session=S_0910, end_session=S_0911)

        t1 = result.session(S_0911)
        assert t1.invalidated_orders[0].planned_quantity == 1000
        assert t1.snapshot.positions[0].total_quantity == 2000
        assert t1.snapshot.valuation_status is ValuationStatus.INCOMPLETE
        assert (
            IncompleteValuationReason.CORPORATE_ACTION_INVALIDATED_PRICE
            in t1.snapshot.incomplete_reasons
        )
        assert t1.decision_blocked_reason is DecisionBlockReason.INCOMPLETE_VALUATION
        assert t1.target is None
        assert t1.plans == ()



class TestFractionalShareGrant:
    """m0-accounting-2: a share grant whose ratio produces a fractional lot
    quantity floors the lot to whole shares and pays cash in lieu of the
    sub-share remainder at the supplied fraction price; without a fraction
    price the fractional case still fails closed."""

    def _action(self) -> CorporateAction:
        return corporate_action(
            action_kind=CorporateActionKind.DISTRIBUTION,
            share_ratio=Decimal("1.2"),
        )

    def test_fractional_grant_floors_and_pays_cash_in_lieu(self) -> None:
        from systematic_investing.backtest.accounting import apply_corporate_action

        posting = apply_corporate_action(
            action=self._action(),
            position=held_position(quantity=432),
            cash=Money(Decimal("1000")),
            session_date=S_0911,
            recorded_at=datetime(2026, 9, 11, 16, 0, tzinfo=UTC),
            fraction_price=Decimal("10.00"),
        )

        # 432 * 1.2 = 518.4 -> 518 whole shares; 0.4 shares paid at 10.00.
        assert posting.position is not None
        assert posting.position.total_quantity == 518
        assert posting.quantity_delta == 86
        assert posting.cash_delta.amount == Decimal("4.00")
        assert posting.cash_entry is not None
        assert posting.cash_entry.category is CashLedgerCategory.DIVIDEND
        # The scaled lot preserves its acquisition sessions and cost basis.
        lot = posting.position.lots[0]
        assert lot.quantity == 518
        assert lot.acquired_session == date(2026, 9, 1)
        assert lot.acquisition_price == Decimal("12.00") / Decimal("1.2")

    def test_fractional_cash_folds_into_the_dividend_entry(self) -> None:
        from systematic_investing.backtest.accounting import apply_corporate_action

        action = CorporateAction(
            action_id="ca:DISTRIBUTION:2026-09-11",
            instrument_id=XSHE_000001,
            action_kind=CorporateActionKind.DISTRIBUTION,
            ex_date=S_0911,
            record_date=date(2026, 9, 10),
            pay_date=S_0911,
            cash_amount=Money(Decimal("0.50")),
            share_ratio=Decimal("1.2"),
            revision=1,
            availability=Availability(
                information_available_at=ANNOUNCED_BEFORE,
                retrieved_at=ANNOUNCED_BEFORE,
                availability_basis=AvailabilityBasis.OBSERVED,
            ),
            provenance="sse-disclosure",
        )
        posting = apply_corporate_action(
            action=action,
            position=held_position(quantity=432),
            cash=Money(Decimal("1000")),
            session_date=S_0911,
            recorded_at=datetime(2026, 9, 11, 16, 0, tzinfo=UTC),
            fraction_price=Decimal("10.00"),
        )

        # Dividend 432 * 0.50 = 216.00 plus 0.4 * 10.00 = 4.00 in one entry.
        assert posting.cash_delta.amount == Decimal("220.00")
        assert posting.cash_entry is not None
        assert posting.cash_entry.entry_id == "cash:ca:ca:DISTRIBUTION:2026-09-11"

    def test_missing_fraction_price_still_fails_closed(self) -> None:
        import pytest

        from systematic_investing.backtest.accounting import (
            CorporateActionAccountingError,
            apply_corporate_action,
        )

        with pytest.raises(CorporateActionAccountingError):
            apply_corporate_action(
                action=self._action(),
                position=held_position(quantity=432),
                cash=Money(Decimal("1000")),
                session_date=S_0911,
                recorded_at=datetime(2026, 9, 11, 16, 0, tzinfo=UTC),
            )

    def test_small_lot_floors_and_pays_the_remainder(self) -> None:
        from systematic_investing.backtest.accounting import apply_corporate_action

        posting = apply_corporate_action(
            action=self._action(),
            position=held_position(quantity=4),
            cash=Money(Decimal("1000")),
            session_date=S_0911,
            recorded_at=datetime(2026, 9, 11, 16, 0, tzinfo=UTC),
            fraction_price=Decimal("10.00"),
        )

        # 4 * 1.2 = 4.8 -> 4 whole shares stay; the 0.8-share remainder
        # pays 8.00 cash in lieu.
        assert posting.position is not None
        assert posting.position.total_quantity == 4
        assert posting.quantity_delta == 0
        assert posting.cash_delta.amount == Decimal("8.00")

    def test_integral_ratio_behavior_is_unchanged(self) -> None:
        from systematic_investing.backtest.accounting import apply_corporate_action

        posting = apply_corporate_action(
            action=corporate_action(
                action_kind=CorporateActionKind.SPLIT,
                share_ratio=Decimal("2.0"),
            ),
            position=held_position(quantity=300),
            cash=Money(Decimal("1000")),
            session_date=S_0911,
            recorded_at=datetime(2026, 9, 11, 16, 0, tzinfo=UTC),
            fraction_price=Decimal("6.00"),
        )

        assert posting.position is not None
        assert posting.position.total_quantity == 600
        assert posting.cash_delta.amount == Decimal("0")

    def test_legacy_accounting_rejects_fractional_grant_even_with_price(self) -> None:
        import pytest

        from systematic_investing.backtest.accounting import (
            AccountingSemantics,
            CorporateActionAccountingError,
            apply_corporate_action,
        )

        with pytest.raises(CorporateActionAccountingError):
            apply_corporate_action(
                action=self._action(),
                position=held_position(quantity=432),
                cash=Money(Decimal("1000")),
                session_date=S_0911,
                recorded_at=datetime(2026, 9, 11, 16, 0, tzinfo=UTC),
                fraction_price=Decimal("10.00"),
                accounting_semantics=AccountingSemantics.LEGACY_M0_ACCOUNTING_1,
            )

    def test_current_accounting_selection_keeps_floor_and_cash_in_lieu(self) -> None:
        from systematic_investing.backtest.accounting import (
            AccountingSemantics,
            apply_corporate_action,
        )

        posting = apply_corporate_action(
            action=self._action(),
            position=held_position(quantity=432),
            cash=Money(Decimal("1000")),
            session_date=S_0911,
            recorded_at=datetime(2026, 9, 11, 16, 0, tzinfo=UTC),
            fraction_price=Decimal("10.00"),
            accounting_semantics=AccountingSemantics.CURRENT_M0_ACCOUNTING_2,
        )

        assert posting.position is not None
        assert posting.position.total_quantity == 518
        assert posting.quantity_delta == 86
        assert posting.cash_delta == Money(Decimal("4.00"))

    def test_integral_grant_is_identical_for_both_accounting_profiles(self) -> None:
        from systematic_investing.backtest.accounting import (
            AccountingSemantics,
            apply_corporate_action,
        )

        for semantics in AccountingSemantics:
            posting = apply_corporate_action(
                action=corporate_action(
                    action_kind=CorporateActionKind.SPLIT,
                    share_ratio=Decimal("2.0"),
                ),
                position=held_position(quantity=300),
                cash=Money(Decimal("1000")),
                session_date=S_0911,
                recorded_at=datetime(2026, 9, 11, 16, 0, tzinfo=UTC),
                accounting_semantics=semantics,
            )
            assert posting.position is not None
            assert posting.position.total_quantity == 600
            assert posting.quantity_delta == 300
