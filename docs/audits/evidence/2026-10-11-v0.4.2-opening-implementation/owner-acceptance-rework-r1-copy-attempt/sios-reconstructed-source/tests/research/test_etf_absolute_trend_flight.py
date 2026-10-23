"""M1-K01 ETF smoke flight: a typed strategy flies through the frozen M0 kernel.

The strategy never builds orders, fills, fees, or NAV. A ``TARGETS``
evaluation becomes an M0 planned order sized at T close, filled at T+1 open
with fees, valued into NAV, and summarized by M0 metrics. Expected amounts
come from the hand-audited fixture and are asserted against engine output.
"""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from smoke_strategies import CloseAboveSmaStrategy

from systematic_investing.backtest.engine import DailyBarEngine
from systematic_investing.domain.identifiers import InstrumentId, SleeveId
from systematic_investing.domain.market import TradabilityStatusKind, TradeSide
from systematic_investing.domain.money import Money
from systematic_investing.metrics.performance import compute_metrics
from systematic_investing.research.runner import StrategyTargetSource

FIXTURE_PATH = (
    Path(__file__).resolve().parents[1] / "fixtures" / "research" / "etf_absolute_trend_smoke.json"
)


def load_fixture() -> dict:
    with FIXTURE_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


@pytest.fixture
def smoke_result(
    etf_universe,
    bar_factory,
    tradability_factory,
    calendar_factory,
    research_clock,
    research_master,
    account_fees_factory,
    execution_model_factory,
) -> tuple[DailyBarEngine, StrategyTargetSource, dict]:
    fixture = load_fixture()
    instrument_id = InstrumentId.parse("XSHG:510300")
    sessions = tuple(date.fromisoformat(text) for text in fixture["sessions"])
    bars = tuple(
        bar_factory(
            instrument_id,
            date.fromisoformat(record["session_date"]),
            open=record["open"],
            close=record["close"],
            high=record["high"],
            low=record["low"],
            pre_close=record["pre_close"],
        )
        for record in fixture["bars"]
    )
    tradability = tuple(
        tradability_factory(instrument_id, session_date, TradabilityStatusKind.TRADABLE)
        for session_date in sessions
    )
    strategy = CloseAboveSmaStrategy()
    adapter = StrategyTargetSource(strategy, etf_universe)
    engine = DailyBarEngine(
        calendar=calendar_factory(fixture["calendar_id"], sessions),
        clock=research_clock,
        master=research_master,
        account_fees=account_fees_factory(
            fixture["account"]["commission_rate"], fixture["account"]["minimum_commission"]
        ),
        execution_model=execution_model_factory(fixture["execution"]["slippage_rate"]),
        bars=bars,
        tradability=tradability,
        corporate_actions=(),
        target_source=adapter,
        initial_cash=Money(Decimal(fixture["account"]["initial_cash"])),
    )
    result = engine.run(start_session=sessions[0], end_session=sessions[-1])
    return engine, adapter, result


def test_typed_evaluations_match_hand_audited_expectations(smoke_result, etf_universe) -> None:
    _engine, adapter, _result = smoke_result
    fixture = load_fixture()
    expected = fixture["expected"]["evaluations"]

    records = adapter.evaluations
    assert len(records) == len(expected)
    for record, want in zip(records, expected, strict=True):
        assert record.session_date.isoformat() == want["session"]
        assert record.evaluation.status.value == want["status"]
        if want["status"] == "NO_DECISION":
            assert record.evaluation.reason_codes == tuple(want["reason_codes"])
            assert record.evaluation.contributions == ()
        else:
            assert record.evaluation.reason_codes == ()
            assert len(record.evaluation.contributions) == 1
            contribution = record.evaluation.contributions[0]
            assert str(contribution.instrument_id) == want["instrument"]
            assert contribution.sleeve.value == want["sleeve"]
            assert contribution.target_weight == Decimal(want["target_weight"])


def test_targets_evaluation_becomes_m0_planned_order(smoke_result) -> None:
    _engine, _adapter, result = smoke_result
    fixture = load_fixture()
    want = fixture["expected"]["planned_order"]

    session = result.session(date.fromisoformat(want["decision_session"]))
    assert session.target is not None
    assert session.decision_digest is not None
    assert len(session.plans) == 1
    plan = session.plans[0]
    assert plan.side is TradeSide.BUY
    assert plan.order_quantity == want["planned_quantity"]
    assert plan.sizing_reference_price == Decimal(want["sizing_reference_price"])
    assert plan.sleeve is SleeveId.CORE


def test_planned_order_fills_at_t1_open_with_fees(smoke_result) -> None:
    _engine, _adapter, result = smoke_result
    fixture = load_fixture()
    want = fixture["expected"]["fill"]

    session = result.session(date.fromisoformat(want["session"]))
    fills = session.activation.fills
    assert len(fills) == 1
    fill = fills[0]
    assert fill.quantity == want["quantity"]
    assert fill.fill_price == Decimal(want["fill_price"])
    assert fill.reference_open == Decimal(want["reference_open"])
    assert fill.fees.commission.amount == Decimal(want["commission"])
    assert fill.fees.minimum_commission_adjustment.amount == Decimal(
        want["minimum_commission_adjustment"]
    )
    assert fill.fees.stamp_tax.amount == Decimal(want["stamp_tax"])
    assert fill.fees.transfer_fee.amount == Decimal(want["transfer_fee"])
    assert session.activation.rejections == ()


def test_nav_series_matches_hand_audited_expectations(smoke_result) -> None:
    _engine, _adapter, result = smoke_result
    fixture = load_fixture()

    for want in fixture["expected"]["nav"]:
        record = result.session(date.fromisoformat(want["session"]))
        assert record.nav.nav == Decimal(want["nav"])


def test_final_account_state_matches_hand_audited_expectations(smoke_result) -> None:
    _engine, _adapter, result = smoke_result
    fixture = load_fixture()
    want = fixture["expected"]["final"]

    assert result.cash.amount == Decimal(want["cash"])
    assert len(result.positions) == 1
    position = result.positions[0]
    assert str(position.instrument_id) == want["position_instrument"]
    assert position.total_quantity == want["position_quantity"]


def test_metrics_match_hand_audited_expectations(smoke_result) -> None:
    _engine, _adapter, result = smoke_result
    fixture = load_fixture()
    want = fixture["expected"]["metrics"]

    nav_points = tuple(record.nav for record in result.sessions)
    report = compute_metrics(nav_points, cash_entries=result.cash_entries)

    assert report.observation_count == want["observation_count"]
    assert report.total_return == Decimal(want["total_return"])
    assert report.max_drawdown == Decimal(want["max_drawdown"])
    assert report.cost_drag.drag == Decimal(want["cost_drag"])
    assert len(result.fills) == want["trade_count"]


def test_identical_run_is_deterministic(
    smoke_result,
    etf_universe,
    bar_factory,
    tradability_factory,
    calendar_factory,
    research_clock,
    research_master,
    account_fees_factory,
    execution_model_factory,
) -> None:
    _engine, _adapter, first = smoke_result
    fixture = load_fixture()
    instrument_id = InstrumentId.parse("XSHG:510300")
    sessions = tuple(date.fromisoformat(text) for text in fixture["sessions"])
    bars = tuple(
        bar_factory(
            instrument_id,
            date.fromisoformat(record["session_date"]),
            open=record["open"],
            close=record["close"],
            high=record["high"],
            low=record["low"],
            pre_close=record["pre_close"],
        )
        for record in fixture["bars"]
    )
    second = DailyBarEngine(
        calendar=calendar_factory(fixture["calendar_id"], sessions),
        clock=research_clock,
        master=research_master,
        account_fees=account_fees_factory(
            fixture["account"]["commission_rate"], fixture["account"]["minimum_commission"]
        ),
        execution_model=execution_model_factory(fixture["execution"]["slippage_rate"]),
        bars=tuple(reversed(bars)),
        tradability=tuple(
            tradability_factory(instrument_id, session_date, TradabilityStatusKind.TRADABLE)
            for session_date in sessions
        ),
        corporate_actions=(),
        target_source=StrategyTargetSource(CloseAboveSmaStrategy(), etf_universe),
        initial_cash=Money(Decimal(fixture["account"]["initial_cash"])),
    ).run(start_session=sessions[0], end_session=sessions[-1])

    assert first.content_digest() == second.content_digest()
