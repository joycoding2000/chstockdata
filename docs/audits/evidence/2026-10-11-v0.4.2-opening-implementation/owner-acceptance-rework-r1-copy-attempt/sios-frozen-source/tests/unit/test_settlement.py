"""Unit tests: settlement, sellability, and side-specific lot behavior.

Sellable quantity is derived from dated acquisition lots and the
instrument's settlement profile; it is never assumed equal to total
holdings. Expected values are hand-derived from the fixed calendar and the
approved Instrument Master profiles. No network.
"""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from systematic_investing.backtest.accounting import (
    InsufficientSellableError,
    apply_fill_to_position,
    sellable_from,
)
from systematic_investing.backtest.execution import legal_buy_quantity, legal_sell_quantity
from systematic_investing.domain.execution import InvalidOrderError
from systematic_investing.domain.identifiers import Exchange, InstrumentId
from systematic_investing.domain.market import TradeSide
from systematic_investing.instrument_master.repository import default_m0_master

XSHG_510300 = InstrumentId(exchange=Exchange.XSHG, symbol="510300")

OPEN_SESSIONS = (
    date(2026, 9, 11),
    date(2026, 9, 14),
    date(2026, 9, 15),
    date(2026, 9, 16),
)

RECORDED_AT = datetime(2026, 9, 14, 9, 35, tzinfo=UTC)


def xshg_calendar():
    from systematic_investing.domain.market import MarketCalendar, TradingSession

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
            for session_date in OPEN_SESSIONS
        ),
    )


def settlement_rule() -> int:
    return (
        default_m0_master()
        .resolve_rules(XSHG_510300, date(2026, 9, 14))
        .settlement.sessions_until_sellable
    )


def lot_rule():
    from systematic_investing.instrument_master.models import LotRule, RuleSource

    return LotRule(
        profile_id="LOT:CN-STANDARD",
        effective_from=date(2022, 1, 4),
        effective_to=None,
        source=RuleSource(authority="SSE/SZSE", reference="test", accessed_on=date(2026, 9, 11)),
    )


class TestSellableFromSettlement:
    def test_t_plus_one_acquisition_becomes_sellable_next_session(self) -> None:
        sessions_until_sellable = settlement_rule()
        assert sessions_until_sellable == 1

        sellable = sellable_from(
            calendar=xshg_calendar(),
            acquired_session=date(2026, 9, 14),
            sessions_until_sellable=sessions_until_sellable,
        )

        assert sellable == date(2026, 9, 15)

    def test_same_day_rule_makes_the_acquisition_immediately_sellable(self) -> None:
        assert (
            sellable_from(
                calendar=xshg_calendar(),
                acquired_session=date(2026, 9, 14),
                sessions_until_sellable=0,
            )
            == date(2026, 9, 14)
        )

    def test_settlement_beyond_the_calendar_snapshot_fails_closed(self) -> None:
        from systematic_investing.domain.market import UnknownSessionError

        with pytest.raises(UnknownSessionError):
            sellable_from(
                calendar=xshg_calendar(),
                acquired_session=date(2026, 9, 16),
                sessions_until_sellable=1,
            )


class TestPositionSellability:
    def buy(self, quantity: int, acquired_session, price: str):
        return apply_fill_to_position(
            instrument_id=XSHG_510300,
            position=None,
            side=TradeSide.BUY,
            quantity=quantity,
            price=Decimal(price),
            execution_session=acquired_session,
            settlement_rule=settlement_rule(),
            calendar=xshg_calendar(),
            source_id=f"order:{acquired_session}",
            recorded_at=RECORDED_AT,
        )

    def test_acquired_quantity_is_not_sellable_on_the_acquisition_session(self) -> None:
        position, _ = self.buy(100, date(2026, 9, 14), "4.10")

        assert position.total_quantity == 100
        assert position.sellable_quantity(date(2026, 9, 14)) == 0
        assert position.lots[0].sellable_from == date(2026, 9, 15)

    def test_sellable_quantity_distinguishes_available_from_total(self) -> None:
        position, _ = self.buy(100, date(2026, 9, 11), "4.00")
        position, _ = apply_fill_to_position(
            instrument_id=XSHG_510300,
            position=position,
            side=TradeSide.BUY,
            quantity=100,
            price=Decimal("4.10"),
            execution_session=date(2026, 9, 14),
            settlement_rule=settlement_rule(),
            calendar=xshg_calendar(),
            source_id="order:2026-09-14",
            recorded_at=RECORDED_AT,
        )

        assert position.total_quantity == 200
        assert position.sellable_quantity(date(2026, 9, 14)) == 100
        assert position.sellable_quantity(date(2026, 9, 15)) == 200

    def test_holding_ledger_entry_carries_settlement_dates(self) -> None:
        _, entry = self.buy(100, date(2026, 9, 14), "4.10")

        assert entry.quantity_delta == 100
        assert entry.acquisition_session == date(2026, 9, 14)
        assert entry.sellable_from == date(2026, 9, 15)
        assert entry.source_id == "order:2026-09-14"

    def test_selling_beyond_sellable_quantity_raises_typed_error(self) -> None:
        position, _ = self.buy(100, date(2026, 9, 14), "4.10")

        with pytest.raises(InsufficientSellableError):
            apply_fill_to_position(
                instrument_id=XSHG_510300,
            position=position,
                side=TradeSide.SELL,
                quantity=100,
                price=Decimal("4.10"),
                execution_session=date(2026, 9, 14),
                settlement_rule=settlement_rule(),
                calendar=xshg_calendar(),
                source_id="order:2026-09-14",
                recorded_at=RECORDED_AT,
            )

    def test_fifo_consumption_removes_the_earliest_sellable_lots(self) -> None:
        position, _ = self.buy(100, date(2026, 9, 11), "4.00")
        position, _ = apply_fill_to_position(
            instrument_id=XSHG_510300,
            position=position,
            side=TradeSide.BUY,
            quantity=100,
            price=Decimal("12.00"),
            execution_session=date(2026, 9, 14),
            settlement_rule=settlement_rule(),
            calendar=xshg_calendar(),
            source_id="order:2026-09-14",
            recorded_at=RECORDED_AT,
        )

        position, _ = apply_fill_to_position(
            instrument_id=XSHG_510300,
            position=position,
            side=TradeSide.SELL,
            quantity=100,
            price=Decimal("12.20"),
            execution_session=date(2026, 9, 14),
            settlement_rule=settlement_rule(),
            calendar=xshg_calendar(),
            source_id="order:sell",
            recorded_at=RECORDED_AT,
        )

        assert position.total_quantity == 100
        assert position.lots[0].acquired_session == date(2026, 9, 14)
        assert position.lots[0].acquisition_price == Decimal("12.00")
        assert position.average_cost == Decimal("12.00")

    def test_average_cost_is_the_weighted_acquisition_price(self) -> None:
        position, _ = self.buy(100, date(2026, 9, 11), "4.10")
        position, _ = apply_fill_to_position(
            instrument_id=XSHG_510300,
            position=position,
            side=TradeSide.BUY,
            quantity=300,
            price=Decimal("12.00"),
            execution_session=date(2026, 9, 11),
            settlement_rule=settlement_rule(),
            calendar=xshg_calendar(),
            source_id="order:second",
            recorded_at=RECORDED_AT,
        )

        assert position.total_quantity == 400
        assert position.average_cost == (100 * Decimal("4.10") + 300 * Decimal("12.00")) / 400


class TestSideSpecificLots:
    def test_buys_accept_only_complete_lots(self) -> None:
        from systematic_investing.instrument_master.models import (
            LotRule,
            RuleSource,
        )

        rule = LotRule(
            profile_id="LOT:CN-STANDARD",
            effective_from=date(2022, 1, 4),
            effective_to=None,
            source=RuleSource(
                authority="SSE/SZSE", reference="test", accessed_on=date(2026, 9, 11)
            ),
        )

        with pytest.raises(InvalidOrderError):
            legal_buy_quantity(130, rule)
        assert legal_buy_quantity(200, rule) == 200

    def test_odd_lot_sells_follow_the_profile_policy(self) -> None:
        from systematic_investing.instrument_master.models import (
            LotRule,
            OddLotSellPolicy,
            RuleSource,
        )

        allowed = LotRule(
            profile_id="LOT:CN-STANDARD",
            effective_from=date(2022, 1, 4),
            effective_to=None,
            source=RuleSource(
                authority="SSE/SZSE", reference="test", accessed_on=date(2026, 9, 11)
            ),
            odd_lot_sell_policy=OddLotSellPolicy.ALLOWED,
        )
        prohibited = LotRule(
            profile_id="LOT:CN-STANDARD",
            effective_from=date(2022, 1, 4),
            effective_to=None,
            source=RuleSource(
                authority="SSE/SZSE", reference="test", accessed_on=date(2026, 9, 11)
            ),
            odd_lot_sell_policy=OddLotSellPolicy.PROHIBITED,
        )

        assert legal_sell_quantity(130, allowed) == 130
        assert legal_sell_quantity(130, prohibited) == 100
        assert legal_sell_quantity(50, prohibited) == 0
