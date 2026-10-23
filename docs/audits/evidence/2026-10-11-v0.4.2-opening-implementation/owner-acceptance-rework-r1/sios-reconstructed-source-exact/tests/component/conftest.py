"""Shared fixtures for the deterministic daily-bar engine component tests.

Every fact here is explicit, hand-auditable, and offline: fixed sessions,
synthetic prices, effective-dated Instrument Master profiles, and a run-owned
broker profile. Nothing depends on today's date, the network, or a strategy.

``PredeterminedTargetSource`` is a test driver, not a strategy: tests declare
the theoretical target contributions per decision session and the driver
replays them. It computes no signal and observes no prices.
"""

from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

import pytest

from systematic_investing.backtest.engine import DailyBarEngine, EngineClock
from systematic_investing.backtest.execution import ExecutionModel
from systematic_investing.domain.execution import AccountFeeConfig, BrokerFeeProfile
from systematic_investing.domain.identifiers import SleeveId
from systematic_investing.domain.market import (
    AdjustmentFactor,
    AdjustmentMode,
    Availability,
    AvailabilityBasis,
    DailyBar,
    MarketCalendar,
    TradabilityStatus,
    TradabilityStatusKind,
    TradingSession,
)
from systematic_investing.domain.portfolio import TargetContribution
from systematic_investing.instrument_master.repository import default_m0_master

MARKET_TZ = UTC
CALENDAR_OPEN_SESSIONS = (
    date(2026, 9, 9),
    date(2026, 9, 10),
    date(2026, 9, 11),
    date(2026, 9, 14),
    date(2026, 9, 15),
)


class PredeterminedTargetSource:
    """Test-only predetermined target driver.

    NOT a strategy: it replays the declared target contributions for the
    decision session, records the decision context it was shown for
    no-lookahead checks, and returns ``None`` for sessions with no declared
    decision (no target is addressed, so no pending plan is created).
    """

    def __init__(self, by_session: dict[date, tuple[TargetContribution, ...]]) -> None:
        self._by_session = dict(by_session)
        self.contexts = []

    def contributions_for(self, context):
        self.contexts.append(context)
        return self._by_session.get(context.session_date)


@pytest.fixture
def xshg_calendar() -> MarketCalendar:
    return MarketCalendar(
        calendar_id="XSHG",
        snapshot_version="CAL-M0-TEST-1",
        sessions=tuple(
            TradingSession(
                calendar_id="XSHG",
                session_date=session_date,
                is_open=True,
                note=None,
                snapshot_version="CAL-M0-TEST-1",
            )
            for session_date in CALENDAR_OPEN_SESSIONS
        ),
    )


@pytest.fixture
def engine_clock() -> EngineClock:
    return EngineClock(
        timezone=MARKET_TZ,
        activation_local_time=time(9, 15),
        execution_local_time=time(9, 30),
        decision_local_time=time(15, 30),
    )


@pytest.fixture
def m0_master():
    return default_m0_master()


@pytest.fixture
def account_fees() -> AccountFeeConfig:
    return AccountFeeConfig(
        config_id="RUN-M0-TEST",
        config_version="1",
        broker_profiles=(
            BrokerFeeProfile(
                profile_id="ACCT:MAIN",
                version="1",
                commission_rate=Decimal("0.0003"),
                minimum_commission=Decimal("5"),
                agreement_reference="broker-agreement-2026",
                effective_from=date(2022, 1, 4),
                effective_to=None,
            ),
        ),
    )


@pytest.fixture
def execution_model() -> ExecutionModel:
    return ExecutionModel(
        slippage_rate_buy=Decimal("0.001"),
        slippage_rate_sell=Decimal("0.001"),
    )


@pytest.fixture
def bar_factory():
    """Build a canonical RAW daily bar with info available after the close.

    Default availability is 15:05 on the session (EXCHANGE_RULE style for the
    close), which is knowable at the 15:30 decision cutoff.
    """

    def build(
        instrument_id,
        session_date: date,
        *,
        open: str | Decimal,
        close: str | Decimal,
        high: str | Decimal | None = None,
        low: str | Decimal | None = None,
        pre_close: str | Decimal | None = None,
        available_at: datetime | None = None,
        factor: str | Decimal | None = None,
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
            adjustment_factor=(
                AdjustmentFactor(
                    factor=Decimal(factor),
                    convention="TOTAL_RETURN",
                    version="1",
                    as_of=session_date,
                )
                if factor is not None
                else None
            ),
            availability=Availability(
                information_available_at=information_available_at,
                retrieved_at=information_available_at + timedelta(minutes=1),
                availability_basis=AvailabilityBasis.OBSERVED,
            ),
            provider_evidence_id="fixture:bars",
        )

    return build


@pytest.fixture
def tradability_factory():
    """Build a point-in-time tradability fact known before the session open."""

    def build(
        instrument_id,
        session_date: date,
        status: TradabilityStatusKind = TradabilityStatusKind.TRADABLE,
        *,
        reason: str | None = None,
        available_at: datetime | None = None,
    ) -> TradabilityStatus:
        information_available_at = available_at or datetime.combine(
            session_date, time(9, 0), tzinfo=MARKET_TZ
        )
        return TradabilityStatus(
            instrument_id=instrument_id,
            session_date=session_date,
            status=status,
            reason=reason,
            availability=Availability(
                information_available_at=information_available_at,
                retrieved_at=information_available_at + timedelta(minutes=1),
                availability_basis=AvailabilityBasis.OBSERVED,
            ),
            provenance="exchange-fact",
        )

    return build


@pytest.fixture
def target_contribution():
    """Build one predetermined theoretical target contribution."""

    def build(
        instrument_id,
        target_weight: str | Decimal,
        *,
        sleeve: SleeveId = SleeveId.CORE,
        strategy_id: str = "fixture-target",
        strategy_version: str = "1",
    ) -> TargetContribution:
        return TargetContribution(
            instrument_id=instrument_id,
            sleeve=sleeve,
            strategy_id=strategy_id,
            strategy_version=strategy_version,
            target_weight=Decimal(target_weight),
        )

    return build


@pytest.fixture
def predetermined_targets() -> type[PredeterminedTargetSource]:
    return PredeterminedTargetSource


@pytest.fixture
def make_engine(
    xshg_calendar,
    engine_clock,
    m0_master,
    account_fees,
    execution_model,
    predetermined_targets,
):
    """Build a ``DailyBarEngine`` with the default frozen M0 test harness."""

    def build(**overrides) -> DailyBarEngine:
        inputs = {
            "calendar": xshg_calendar,
            "clock": engine_clock,
            "master": m0_master,
            "account_fees": account_fees,
            "execution_model": execution_model,
            "bars": (),
            "tradability": (),
            "corporate_actions": (),
            "target_source": predetermined_targets({}),
        }
        inputs.update(overrides)
        return DailyBarEngine(**inputs)

    return build
