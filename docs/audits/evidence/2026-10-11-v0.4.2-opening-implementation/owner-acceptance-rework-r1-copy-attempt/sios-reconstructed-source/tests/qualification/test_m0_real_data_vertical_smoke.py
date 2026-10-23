"""Owner-controlled real-data vertical smoke for the M0 kernel.

This qualification test never fetches data and never writes a snapshot.  It
loads the immutable Basic ETF snapshot, re-runs its quality gate, drives one
small deterministic target through the ordinary kernel, computes metrics,
and proves an identical replay has the same result digest.
"""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from systematic_investing.backtest.engine import DailyBarEngine, EngineClock
from systematic_investing.backtest.execution import ExecutionModel
from systematic_investing.data.quality import (
    DataQualityGate,
    DatasetPolicy,
    GateStatus,
)
from systematic_investing.data.snapshots import SnapshotReader
from systematic_investing.domain.execution import AccountFeeConfig, BrokerFeeProfile
from systematic_investing.domain.identifiers import InstrumentId, SleeveId
from systematic_investing.domain.market import MarketCalendar
from systematic_investing.domain.money import Money
from systematic_investing.domain.portfolio import TargetContribution
from systematic_investing.domain.runs import RunPurpose
from systematic_investing.instrument_master.repository import default_m0_master
from systematic_investing.metrics.performance import compute_metrics

SNAPSHOT_DIR = Path("var/research/snapshots/basic-etf-v1")
MATERIALIZE_COMMAND = (
    "python -m systematic_investing.research.materializer --mode BASIC "
    "--asset ETF --start 2015-01-05 --end 2022-12-30 "
    "--request research/candidates/m1-etf-absolute-trend-v1.json "
    "--output var/research/snapshots/basic-etf-v1"
)


class _OneShotTarget:
    def __init__(self, session_date: date, instrument_id: InstrumentId) -> None:
        self._session_date = session_date
        self._instrument_id = instrument_id

    def contributions_for(self, context):
        if context.session_date != self._session_date:
            return None
        return (
            TargetContribution(
                instrument_id=self._instrument_id,
                sleeve=SleeveId.CORE,
                strategy_id="m0-real-data-smoke",
                strategy_version="1",
                target_weight=Decimal("0.10"),
            ),
        )


def _calendar(dataset) -> MarketCalendar:
    sessions = tuple(
        sorted(
            (session for session in dataset.sessions if session.is_open),
            key=lambda session: session.session_date,
        )
    )
    assert sessions
    versions = {session.snapshot_version for session in sessions}
    calendar_ids = {session.calendar_id for session in sessions}
    assert len(versions) == 1
    assert len(calendar_ids) == 1
    return MarketCalendar(
        calendar_id=next(iter(calendar_ids)),
        snapshot_version=next(iter(versions)),
        sessions=sessions,
    )


def _smoke_instrument(dataset, run_sessions: tuple[date, ...]) -> InstrumentId:
    bar_dates: dict[InstrumentId, set[date]] = {}
    for bar in dataset.daily_bars:
        bar_dates.setdefault(bar.instrument_id, set()).add(bar.session_date)
    tradable_on_execution = {
        status.instrument_id
        for status in dataset.tradability
        if status.session_date == run_sessions[-1]
    }
    candidates = sorted(
        instrument_id
        for instrument_id, dates in bar_dates.items()
        if set(run_sessions) <= dates and instrument_id in tradable_on_execution
    )
    assert candidates, "snapshot has no instrument usable for the three-session smoke"
    return candidates[0]


def _run(dataset, calendar: MarketCalendar, run_sessions: tuple[date, ...], instrument_id):
    fees = AccountFeeConfig(
        config_id="M0-REAL-DATA-SMOKE",
        config_version="1",
        broker_profiles=(
            BrokerFeeProfile(
                profile_id="M0-REAL-DATA-SMOKE",
                version="1",
                commission_rate=Decimal("0.0003"),
                minimum_commission=Decimal("5"),
                agreement_reference="M0-foundation-hardening",
                effective_from=date(1990, 1, 1),
                effective_to=None,
            ),
        ),
    )
    result = DailyBarEngine(
        calendar=calendar,
        clock=EngineClock(),
        master=default_m0_master(),
        account_fees=fees,
        execution_model=ExecutionModel(
            slippage_rate_buy=Decimal("0"),
            slippage_rate_sell=Decimal("0"),
        ),
        bars=tuple(dataset.daily_bars),
        tradability=tuple(dataset.tradability),
        corporate_actions=tuple(dataset.corporate_actions),
        # The one-shot decision fires on the first run session so the fill
        # executes on the middle session: resolving T+1 sellability for an
        # execution on the snapshot's final session would need an open
        # session beyond the data horizon, which no snapshot can contain.
        target_source=_OneShotTarget(run_sessions[0], instrument_id),
        initial_cash=Money(Decimal("100000")),
    ).run(start_session=run_sessions[0], end_session=run_sessions[-1])
    metrics = compute_metrics(
        tuple(session.nav for session in result.sessions),
        cash_entries=result.cash_entries,
    )
    return result, metrics


def test_owner_snapshot_passes_the_real_data_vertical_smoke() -> None:
    if not (SNAPSHOT_DIR / "manifest.json").exists():
        pytest.skip(
            "OWNER_ACTION_REQUIRED: materialize the immutable Basic ETF snapshot with: "
            + MATERIALIZE_COMMAND
        )

    manifest, dataset = SnapshotReader().load(SNAPSHOT_DIR)
    assert manifest.quality_status == "PASS"

    calendar = _calendar(dataset)
    run_sessions = tuple(session.session_date for session in calendar.sessions[-3:])
    assert len(run_sessions) == 3
    instrument_id = _smoke_instrument(dataset, run_sessions)

    # The independent re-evaluation must mirror the materializer's recorded
    # decision: knowledge at the final session's close (the manifest cutoff)
    # covers a decision FOR that same final session. Deciding for an earlier
    # session while holding later facts would be a look-ahead contradiction,
    # and the gate correctly fails it (SESSION_AFTER_INTENDED_DECISION).
    gate = DataQualityGate(master=default_m0_master(), policy=DatasetPolicy()).evaluate(
        dataset,
        purpose=RunPurpose.DECISION,
        intended_decision_session=run_sessions[-1],
        information_cutoff=manifest.knowledge_cutoff,
        evaluated_at=manifest.created_at,
    )
    assert gate.status is GateStatus.PASS

    first, first_metrics = _run(dataset, calendar, run_sessions, instrument_id)
    second, second_metrics = _run(dataset, calendar, run_sessions, instrument_id)

    assert first.fills
    assert len(first.sessions) == 3
    assert first_metrics.observation_count == 3
    assert first.content_digest() == second.content_digest()
    assert first_metrics == second_metrics
