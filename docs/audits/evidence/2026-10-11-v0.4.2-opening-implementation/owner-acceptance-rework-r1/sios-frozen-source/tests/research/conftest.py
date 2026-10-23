"""Offline harness for Research tests.

Every fact here is explicit, hand-auditable, and offline: fixed sessions,
synthetic RAW bars, the M0 seed Instrument Master, and a run-owned broker
profile. No strategy logic lives in this file; test-only smoke strategies are
defined in ``smoke_strategies.py`` and never enter canonical Basic/OOS.
"""

from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

import pytest

from systematic_investing.backtest.engine import EngineClock
from systematic_investing.backtest.execution import ExecutionModel
from systematic_investing.domain.execution import AccountFeeConfig, BrokerFeeProfile
from systematic_investing.domain.identifiers import Exchange, InstrumentId
from systematic_investing.domain.instruments import Instrument, InstrumentType
from systematic_investing.domain.market import (
    AdjustmentMode,
    Availability,
    AvailabilityBasis,
    DailyBar,
    MarketCalendar,
    TradabilityStatus,
    TradabilityStatusKind,
    TradingSession,
)
from systematic_investing.instrument_master.repository import default_m0_master
from systematic_investing.research.universe import UniverseView

MARKET_TZ = UTC

STOCK_SYMBOLS: tuple[str, ...] = tuple(
    [f"60000{index}" for index in range(1, 7)]
    + [f"6000{index:02d}" for index in range(11, 27)]
    + ["600099"]
)


@pytest.fixture
def research_clock() -> EngineClock:
    return EngineClock(timezone=MARKET_TZ)


@pytest.fixture
def research_master() -> Any:
    return default_m0_master()


@pytest.fixture
def stock_master() -> Any:
    """Run-owned master with the 22 annual-cohort smoke A-shares registered
    against the seed M0 rule profiles (lot, T+1 settlement, price limit,
    stamp tax). Classification is explicit; never inferred from symbols."""
    master = default_m0_master()
    for symbol in STOCK_SYMBOLS:
        master.register_instrument(
            Instrument(
                instrument_id=InstrumentId(exchange=Exchange.XSHG, symbol=symbol),
                display_name=f"Smoke A-share {symbol}",
                currency="CNY",
                instrument_type=InstrumentType.A_SHARE,
                fund_subtype=None,
                list_date=date(2000, 1, 4),
                delist_date=None,
                trading_calendar_id="XSHG",
                lot_rule_profile_id="LOT:CN-STANDARD",
                settlement_rule_profile_id="SETTLE:T1",
                price_limit_rule_profile_id="PLIMIT:A-MAIN-10PCT",
                market_fee_tax_profile_id="FEE:TAX-A-STANDARD",
                reference_data_version="M1-RESEARCH-TEST-1",
                valid_from=date(2022, 1, 4),
                valid_to=None,
            )
        )
    return master


@pytest.fixture
def account_fees_factory() -> Any:
    """Build a run-owned broker profile from explicit fixture amounts."""

    def build(commission_rate: str, minimum_commission: str) -> AccountFeeConfig:
        return AccountFeeConfig(
            config_id="RUN-M1-RESEARCH-TEST",
            config_version="1",
            broker_profiles=(
                BrokerFeeProfile(
                    profile_id="ACCT:MAIN",
                    version="1",
                    commission_rate=Decimal(commission_rate),
                    minimum_commission=Decimal(minimum_commission),
                    agreement_reference="research-test-agreement",
                    effective_from=date(2022, 1, 4),
                    effective_to=None,
                ),
            ),
        )

    return build


@pytest.fixture
def execution_model_factory() -> Any:
    def build(slippage_rate: str) -> ExecutionModel:
        return ExecutionModel(
            slippage_rate_buy=Decimal(slippage_rate),
            slippage_rate_sell=Decimal(slippage_rate),
        )

    return build


@pytest.fixture
def bar_factory() -> Any:
    """Build a canonical RAW daily bar with info available after the close.

    Default availability is 15:05 on the session, which is knowable at the
    15:30 decision cutoff but not before the session close.
    """

    def build(
        instrument_id: InstrumentId,
        session_date: date,
        *,
        open: str,
        close: str,
        high: str | None = None,
        low: str | None = None,
        pre_close: str | None = None,
        available_at: datetime | None = None,
    ) -> DailyBar:
        open_price = Decimal(open)
        close_price = Decimal(close)
        information_available_at = available_at or datetime.combine(
            session_date, time(15, 5), tzinfo=MARKET_TZ
        )
        return DailyBar(
            schema_version="v1",
            instrument_id=instrument_id,
            session_date=session_date,
            open=open_price,
            high=Decimal(high) if high is not None else max(open_price, close_price),
            low=Decimal(low) if low is not None else min(open_price, close_price),
            close=close_price,
            pre_close=Decimal(pre_close) if pre_close is not None else None,
            volume=Decimal("1000000"),
            amount=Decimal("4000000"),
            currency="CNY",
            volume_unit="shares",
            amount_unit="CNY",
            adjustment_mode=AdjustmentMode.RAW,
            adjustment_factor=None,
            availability=Availability(
                information_available_at=information_available_at,
                retrieved_at=information_available_at + timedelta(minutes=1),
                availability_basis=AvailabilityBasis.OBSERVED,
            ),
            provider_evidence_id="fixture:research-bars",
        )

    return build


@pytest.fixture
def tradability_factory() -> Any:
    """Build a point-in-time tradability fact known before the session open."""

    def build(
        instrument_id: InstrumentId,
        session_date: date,
        status: TradabilityStatusKind = TradabilityStatusKind.TRADABLE,
    ) -> TradabilityStatus:
        information_available_at = datetime.combine(
            session_date, time(9, 0), tzinfo=MARKET_TZ
        )
        return TradabilityStatus(
            instrument_id=instrument_id,
            session_date=session_date,
            status=status,
            reason=None,
            availability=Availability(
                information_available_at=information_available_at,
                retrieved_at=information_available_at + timedelta(minutes=1),
                availability_basis=AvailabilityBasis.OBSERVED,
            ),
            provenance="exchange-fact",
        )

    return build


@pytest.fixture
def calendar_factory() -> Any:
    def build(calendar_id: str, session_dates: tuple[date, ...]) -> MarketCalendar:
        return MarketCalendar(
            calendar_id=calendar_id,
            snapshot_version="CAL-M1-RESEARCH-TEST-1",
            sessions=tuple(
                TradingSession(
                    calendar_id=calendar_id,
                    session_date=session_date,
                    is_open=True,
                    note=None,
                    snapshot_version="CAL-M1-RESEARCH-TEST-1",
                )
                for session_date in session_dates
            ),
        )

    return build


@pytest.fixture
def etf_universe() -> UniverseView:
    """The M1 smoke ETF universe: one M0-qualified broad-based equity ETF."""
    return UniverseView((InstrumentId.parse("XSHG:510300"),))
