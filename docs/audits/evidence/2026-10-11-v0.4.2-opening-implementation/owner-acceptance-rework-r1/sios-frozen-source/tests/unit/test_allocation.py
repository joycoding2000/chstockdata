"""Unit tests: deterministic executable conversion of risk-approved targets.

Covers: T-close sizing contract, complete lots and explicit residual cash,
reductions/exits before buys, descending-deficit buy ranking with canonical
InstrumentId tie-breaker, separated market/broker fee reserves, ordering
invariance, HOLD for sub-lot deltas, and CNY 100,000 fixtures that never
create negative cash. All expected numbers are hand-calculated.
"""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from systematic_investing.domain.identifiers import Exchange, InstrumentId, SleeveId
from systematic_investing.domain.money import Money
from systematic_investing.domain.portfolio import (
    PortfolioError,
    SizingPriceBasis,
)
from systematic_investing.instrument_master.models import LotRule, OddLotSellPolicy, RuleSource
from systematic_investing.portfolio.allocation import (
    AllocationReasonCode,
    CurrentHolding,
    CurrentPortfolio,
    FeeEstimate,
    MissingPriceError,
    build_executable_target,
)
from systematic_investing.risk.decisions import (
    ApprovedPosition,
    RiskApprovedTargetPortfolio,
)

XSHG_510300 = InstrumentId(exchange=Exchange.XSHG, symbol="510300")
XSHE_159915 = InstrumentId(exchange=Exchange.XSHE, symbol="159915")

CUTOFF = datetime(2026, 9, 11, 15, 0, tzinfo=UTC)
TRADE_DATE = date(2026, 9, 14)
EQUITY = Money(Decimal("100000"))

LOT_RULE = LotRule(
    profile_id="LOT:CN-STANDARD",
    effective_from=date(2022, 1, 4),
    effective_to=None,
    source=RuleSource(authority="SSE/SZSE", reference="test", accessed_on=date(2026, 9, 11)),
)


class HandFeeEstimator:
    """Deterministic fixture estimator: market 0.01% of notional, broker
    commission 0.025% with a CNY 5 minimum. Never merges the two authorities."""

    def estimate(self, instrument_id, side, quantity, price) -> FeeEstimate:  # type: ignore[no-untyped-def]
        notional = Decimal(quantity) * price
        market = notional * Decimal("0.0001")
        broker = max(Decimal("5"), notional * Decimal("0.00025"))
        return FeeEstimate(market_fees=Money(market), broker_fees=Money(broker))


def approved_position(instrument_id=XSHG_510300, sleeve=SleeveId.CORE,
                      theoretical="0.60", approved="0.60") -> ApprovedPosition:
    return ApprovedPosition(
        instrument_id=instrument_id,
        sleeve=sleeve,
        theoretical_weight=Decimal(theoretical),
        approved_weight=Decimal(approved),
    )


def make_approved(positions, equity: Money | None = None) -> RiskApprovedTargetPortfolio:
    return RiskApprovedTargetPortfolio(
        target_id="target-2026-09-11",
        revision=1,
        decision_for_trade_date=TRADE_DATE,
        information_cutoff=CUTOFF,
        valuation_equity=equity if equity is not None else EQUITY,
        positions=tuple(positions),
        approved_cash_weight=Decimal("1")
        - sum(position.approved_weight for position in positions),
        applied_rules=(),
        composition_version="m0-risk-1",
    )


def flat_portfolio(cash: str = "100000") -> CurrentPortfolio:
    return CurrentPortfolio(cash=Money(Decimal(cash)), holdings=())


def prices(quotes: dict) -> dict:
    return quotes


def build(approved, current, price_map, lot_rules=None, equity=None):
    if equity is not None:
        approved = make_approved(list(approved.positions), equity=Money(equity))
    return build_executable_target(
        approved_target=approved,
        current_portfolio=current,
        t_close_prices=price_map,
        lot_rules=lot_rules or {XSHG_510300: LOT_RULE, XSHE_159915: LOT_RULE},
        fee_estimator=HandFeeEstimator(),
    )


class TestTCloseSizingContract:
    def test_sizing_uses_and_records_the_finalized_t_close_price(self) -> None:
        approved = make_approved([approved_position()])
        result = build(approved, flat_portfolio(), prices({XSHG_510300: Decimal("4.00")}))

        position = result.positions[0]
        assert position.sizing_reference_price_basis == SizingPriceBasis.T_CLOSE
        assert position.sizing_reference_price == Decimal("4.00")
        # 0.60 * 100000 = 60000; 60000 / 4.00 = 15000 shares = 150 complete lots.
        assert position.planned_quantity == 15000
        assert position.executable_weight == Decimal("0.60")

    def test_market_and_broker_fees_are_reserved_separately(self) -> None:
        approved = make_approved([approved_position()])
        result = build(approved, flat_portfolio(), prices({XSHG_510300: Decimal("4.00")}))

        position = result.positions[0]
        # Notional 60000: market 0.01% = 6.00; broker 0.025% = 15.00.
        assert position.estimated_market_fees == Money(Decimal("6.00"))
        assert position.estimated_broker_fees == Money(Decimal("15.00"))

    def test_residual_cash_is_explicit_after_exact_affordability(self) -> None:
        approved = make_approved(
            [
                approved_position(),
                approved_position(
                    instrument_id=XSHE_159915,
                    sleeve=SleeveId.SATELLITE,
                    theoretical="0.25",
                    approved="0.25",
                ),
            ]
        )
        result = build(
            approved,
            flat_portfolio(),
            prices({XSHG_510300: Decimal("4.00"), XSHE_159915: Decimal("2.50")}),
        )

        # A: 60000 + 6.00 + 15.00 = 60021.00
        # B: 25000 + 2.50 + 6.25 = 25008.75
        # Residual: 100000 - 60021.00 - 25008.75 = 14970.25
        assert result.residual_cash == Money(Decimal("14970.25"))
        assert result.residual_cash.amount >= 0
        # Target amounts are retained alongside quantities; positions are
        # ordered by canonical InstrumentId (XSHE sorts before XSHG).
        amounts = {p.instrument_id: p.target_amount for p in result.positions}
        assert amounts[XSHG_510300] == Money(Decimal("60000"))
        assert amounts[XSHE_159915] == Money(Decimal("25000"))


class TestCompleteLotsAndResidual:
    def test_amount_not_lot_divisible_keeps_theoretical_weight_and_floors_quantity(self) -> None:
        approved = make_approved(
            [approved_position(theoretical="0.3333", approved="0.3333")]
        )
        result = build(approved, flat_portfolio(), prices({XSHG_510300: Decimal("4.00")}))

        position = result.positions[0]
        # 33330 / 4.00 = 8332.5 shares -> 83 complete lots = 8300 shares.
        assert position.planned_quantity == 8300
        assert position.theoretical_weight == Decimal("0.3333")
        assert position.executable_weight == Decimal("0.332")
        # 33200 + 3.32 + 8.30 = 33211.62
        assert result.residual_cash == Money(Decimal("66788.38"))


class TestReductionsFirst:
    def test_sell_releases_cash_before_buys_are_sized(self) -> None:
        approved = make_approved(
            [
                approved_position(theoretical="0.10", approved="0.10"),
                approved_position(
                    instrument_id=XSHE_159915,
                    sleeve=SleeveId.SATELLITE,
                    theoretical="0.70",
                    approved="0.70",
                ),
            ]
        )
        current = CurrentPortfolio(
            cash=Money(Decimal("60000")),
            holdings=(CurrentHolding(instrument_id=XSHG_510300, quantity=10000),),
        )
        result = build(
            approved,
            current,
            prices({XSHG_510300: Decimal("4.00"), XSHE_159915: Decimal("2.50")}),
        )

        by_instrument = {position.instrument_id: position for position in result.positions}
        sell = by_instrument[XSHG_510300]
        buy = by_instrument[XSHE_159915]

        assert sell.reason_codes == (AllocationReasonCode.REDUCE_TO_TARGET,)
        assert sell.planned_quantity == 2500
        assert buy.reason_codes == (AllocationReasonCode.BUY_FULL_TARGET,)
        assert buy.planned_quantity == 28000
        # Proceeds 30000 - 3.00 - 7.50 = 29989.50 -> available 89989.50
        # Buy cost 70000 + 7.00 + 17.50 = 70024.50 -> residual 19965.00
        assert result.residual_cash == Money(Decimal("19965.00"))


class TestBuyRanking:
    def test_equal_deficits_use_canonical_instrument_id_tie_breaker(self) -> None:
        approved = make_approved(
            [
                approved_position(instrument_id=XSHG_510300, approved="0.50"),
                approved_position(
                    instrument_id=XSHE_159915,
                    sleeve=SleeveId.SATELLITE,
                    theoretical="0.50",
                    approved="0.50",
                ),
            ]
        )
        result = build(
            approved,
            flat_portfolio(cash="40000"),
            prices({XSHG_510300: Decimal("4.00"), XSHE_159915: Decimal("4.00")}),
            equity=Decimal("40000"),
        )

        by_instrument = {position.instrument_id: position for position in result.positions}
        # Equal deficits: canonical InstrumentId order is (exchange, symbol),
        # so XSHE:159915 sorts before XSHG:510300 and is funded first.
        assert by_instrument[XSHE_159915].planned_quantity == 5000
        assert by_instrument[XSHE_159915].reason_codes == (
            AllocationReasonCode.BUY_FULL_TARGET,
        )
        assert by_instrument[XSHG_510300].planned_quantity == 4900
        assert by_instrument[XSHG_510300].reason_codes == (
            AllocationReasonCode.BUY_REDUCED_TO_AFFORD,
        )

    def test_larger_target_weight_deficit_is_funded_before_the_canonical_first(self) -> None:
        # XSHG:510300 carries deficit 0.70 but sorts AFTER XSHE:159915; deficit
        # ranking must still fund it first. Hand calculation (equity 40000):
        # XSHG amount 28000 @2.50 = 11200 shares, fully affordable (28009.80);
        # XSHE amount 12000 @4.00 = 3000 shares, but lot 30 costs 12004.20 vs
        # 11990.20 remaining -> 29 lots = 2900 shares.
        approved = make_approved(
            [
                approved_position(theoretical="0.70", approved="0.70"),
                approved_position(
                    instrument_id=XSHE_159915,
                    sleeve=SleeveId.SATELLITE,
                    theoretical="0.30",
                    approved="0.30",
                ),
            ]
        )
        result = build(
            approved,
            flat_portfolio(cash="40000"),
            prices({XSHG_510300: Decimal("2.50"), XSHE_159915: Decimal("4.00")}),
            equity=Decimal("40000"),
        )

        by_instrument = {position.instrument_id: position for position in result.positions}
        assert by_instrument[XSHG_510300].planned_quantity == 11200
        assert by_instrument[XSHG_510300].reason_codes == (
            AllocationReasonCode.BUY_FULL_TARGET,
        )
        assert by_instrument[XSHE_159915].planned_quantity == 2900
        assert by_instrument[XSHE_159915].reason_codes == (
            AllocationReasonCode.BUY_REDUCED_TO_AFFORD,
        )

    def test_input_ordering_does_not_change_the_executable_output(self) -> None:
        positions = [
            approved_position(),
            approved_position(
                instrument_id=XSHE_159915,
                sleeve=SleeveId.SATELLITE,
                theoretical="0.25",
                approved="0.25",
            ),
        ]
        first = build(
            make_approved(positions),
            flat_portfolio(),
            prices({XSHG_510300: Decimal("4.00"), XSHE_159915: Decimal("2.50")}),
        )
        second = build(
            make_approved(list(reversed(positions))),
            CurrentPortfolio(
                cash=Money(Decimal("100000")),
                holdings=(),
            ),
            prices({XSHE_159915: Decimal("2.50"), XSHG_510300: Decimal("4.00")}),
        )

        assert first == second


class TestCashNeverNegative:
    def test_unaffordable_full_target_reduces_to_affordable_lots(self) -> None:
        approved = make_approved([approved_position(theoretical="1.0", approved="1.0")])
        result = build(approved, flat_portfolio(), prices({XSHG_510300: Decimal("4.00")}))

        position = result.positions[0]
        # 250 lots would cost 100035.00; 249 lots cost 99634.86.
        assert position.planned_quantity == 24900
        assert position.reason_codes == (AllocationReasonCode.BUY_REDUCED_TO_AFFORD,)
        assert result.residual_cash == Money(Decimal("365.14"))
        assert result.residual_cash.amount >= 0

    def test_residual_cash_is_never_negative_across_fixtures(self) -> None:
        cases = [
            make_approved([approved_position(theoretical="0.99", approved="0.99")]),
            make_approved([approved_position(theoretical="0.999", approved="0.999")]),
        ]
        for approved in cases:
            result = build(approved, flat_portfolio(), prices({XSHG_510300: Decimal("4.00")}))

            assert result.residual_cash.amount >= 0


class TestHoldsAndExits:
    def test_delta_below_one_lot_becomes_hold_with_reason(self) -> None:
        approved = make_approved([approved_position(theoretical="0.401", approved="0.401")])
        current = CurrentPortfolio(
            cash=Money(Decimal("60000")),
            holdings=(CurrentHolding(instrument_id=XSHG_510300, quantity=10000),),
        )
        result = build(approved, current, prices({XSHG_510300: Decimal("4.00")}))

        position = result.positions[0]
        assert position.reason_codes == (AllocationReasonCode.HOLD_BELOW_ONE_LOT,)
        assert position.planned_quantity == 10000
        assert result.residual_cash == Money(Decimal("60000"))

    def test_exit_sells_odd_lot_remainder_when_profile_allows(self) -> None:
        approved = make_approved([approved_position(theoretical="0", approved="0")])
        current = CurrentPortfolio(
            cash=Money(Decimal("99400")),
            holdings=(CurrentHolding(instrument_id=XSHG_510300, quantity=150),),
        )
        result = build(approved, current, prices({XSHG_510300: Decimal("4.00")}))

        position = result.positions[0]
        assert position.reason_codes == (AllocationReasonCode.EXIT_FULL_POSITION,)
        assert position.planned_quantity == 0
        assert result.residual_cash == Money(Decimal("99994.94"))

    def test_exit_keeps_odd_lot_when_profile_prohibits_odd_lot_sells(self) -> None:
        prohibited = LotRule(
            profile_id="LOT:NO-ODD",
            effective_from=date(2022, 1, 4),
            effective_to=None,
            source=RuleSource(authority="test", reference="test", accessed_on=date(2026, 9, 11)),
            odd_lot_sell_policy=OddLotSellPolicy.PROHIBITED,
        )
        approved = make_approved([approved_position(theoretical="0", approved="0")])
        current = CurrentPortfolio(
            cash=Money(Decimal("99400")),
            holdings=(CurrentHolding(instrument_id=XSHG_510300, quantity=150),),
        )
        result = build(
            approved,
            current,
            prices({XSHG_510300: Decimal("4.00")}),
            lot_rules={XSHG_510300: prohibited},
        )

        position = result.positions[0]
        assert position.reason_codes == (AllocationReasonCode.REDUCE_TO_TARGET,)
        assert position.planned_quantity == 50


class TestInputValidation:
    def test_held_instrument_without_t_close_price_fails_closed(self) -> None:
        approved = make_approved([approved_position()])
        current = CurrentPortfolio(
            cash=Money(Decimal("100000")),
            holdings=(CurrentHolding(instrument_id=XSHG_510300, quantity=100),),
        )

        with pytest.raises(MissingPriceError):
            build(approved, current, prices({}))

    def test_current_portfolio_rejects_duplicate_holdings(self) -> None:
        with pytest.raises(PortfolioError):
            CurrentPortfolio(
                cash=Money(Decimal("100000")),
                holdings=(
                    CurrentHolding(instrument_id=XSHG_510300, quantity=100),
                    CurrentHolding(instrument_id=XSHG_510300, quantity=200),
                ),
            )
