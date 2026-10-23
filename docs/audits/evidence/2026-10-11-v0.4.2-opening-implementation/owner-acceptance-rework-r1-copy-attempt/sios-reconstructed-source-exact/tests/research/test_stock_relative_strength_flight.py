"""M1-K02 Stock smoke flight: the annual PIT cohort flies through M0.

A 22-instrument annual cohort (formed with the real M1 policy at the
2021-12-31 year-end cutoff) is injected into a test-only SATELLITE
relative-strength strategy. Every SATELLITE contribution must reach the
frozen M0 kernel: lot-sized planned orders, the global affordability pass,
T+1 settlement, sell-side stamp tax, and suspension rejections. The strategy
never builds orders, fees, or NAV. Expected amounts come from the
hand-audited fixture and were derived independently of engine output.

The cross-year test proves the seam that Task 4 needs: the adapter resolves
the cohort governing each decision session, and a holding whose instrument
left the cohort in the next year can still be exited with an explicit
zero-weight target instead of being stuck forever.
"""

import json
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from smoke_strategies import STOCK_SMOKE_IDENTITY, StockRelativeStrengthSmokeStrategy

from systematic_investing.backtest.engine import DailyBarEngine
from systematic_investing.domain.execution import RejectionCode
from systematic_investing.domain.identifiers import InstrumentId, SleeveId
from systematic_investing.domain.market import TradabilityStatusKind, TradeSide
from systematic_investing.domain.money import Money
from systematic_investing.metrics.performance import compute_metrics
from systematic_investing.research.runner import StrategyTargetSource
from systematic_investing.research.universe import (
    AnnualUniversePolicy,
    StockFormationFact,
    StockIdentityStatus,
    TrailingAmount,
    form_annual_schedule,
)

FIXTURE_PATH = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "research"
    / "stock_relative_strength_smoke.json"
)


def load_fixture() -> dict:
    with FIXTURE_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


def _sessions(fixture: dict) -> tuple[date, ...]:
    return tuple(date.fromisoformat(text) for text in fixture["sessions"])


def _instrument_ids(fixture: dict) -> tuple[InstrumentId, ...]:
    symbols = [*fixture["roles"], *fixture["fillers"]]
    return tuple(InstrumentId.parse(symbol) for symbol in symbols)


def _trailing_dates(fixture: dict) -> tuple[date, ...]:
    count = fixture["universe"]["trailing_sessions_count"]
    cursor = date.fromisoformat(fixture["universe"]["trailing_sessions_start"])
    session_dates: list[date] = []
    while len(session_dates) < count:
        if cursor.weekday() < 5:
            session_dates.append(cursor)
        cursor = cursor + timedelta(days=1)
    return tuple(session_dates)


def _build_bars(fixture: dict, bar_factory) -> tuple:
    sessions = _sessions(fixture)
    bars = []
    for symbol, spec in fixture["roles"].items():
        instrument_id = InstrumentId.parse(symbol)
        closes = spec["closes"]
        for index, session_date in enumerate(sessions):
            close = Decimal(closes[index])
            open_price = Decimal(closes[index - 1]) if index else close
            bars.append(
                bar_factory(
                    instrument_id,
                    session_date,
                    open=str(open_price),
                    close=str(close),
                    high=str(max(open_price, close)),
                    low=str(min(open_price, close)),
                    pre_close=str(open_price) if index else None,
                )
            )
    for symbol in fixture["fillers"]:
        instrument_id = InstrumentId.parse(symbol)
        for session_date in sessions:
            bars.append(
                bar_factory(
                    instrument_id,
                    session_date,
                    open=fixture["filler_close"],
                    close=fixture["filler_close"],
                )
            )
    return tuple(bars)


def _build_tradability(fixture: dict, tradability_factory) -> tuple:
    sessions = _sessions(fixture)
    suspended = {
        record["instrument"]: set(record["sessions"])
        for record in fixture["suspensions"]
    }
    records = []
    for symbol in [*fixture["roles"], *fixture["fillers"]]:
        instrument_id = InstrumentId.parse(symbol)
        for session_date in sessions:
            status = (
                TradabilityStatusKind.SUSPENDED
                if session_date.isoformat() in suspended.get(symbol, set())
                else TradabilityStatusKind.TRADABLE
            )
            records.append(tradability_factory(instrument_id, session_date, status))
    return tuple(records)


def _build_formation_records(fixture: dict) -> tuple[StockFormationFact, ...]:
    trailing_dates = _trailing_dates(fixture)
    formation_session = date.fromisoformat(fixture["universe"]["formation_session"])
    assert trailing_dates[-1] == formation_session
    records = []
    for symbol in [*fixture["roles"], *fixture["fillers"]]:
        median = fixture["universe"]["role_median_amounts"].get(
            symbol, fixture["universe"]["filler_median_amount"]
        )
        records.append(
            StockFormationFact(
                instrument_id=InstrumentId.parse(symbol),
                formation_session=formation_session,
                listed_sessions=fixture["universe"]["listed_sessions"],
                identity_status=StockIdentityStatus.NORMAL,
                tradability=TradabilityStatusKind.TRADABLE,
                trailing_amounts=tuple(
                    TrailingAmount(session_date, Decimal(median))
                    for session_date in trailing_dates
                ),
            )
        )
    return tuple(records)


def _real_policy_matches_fixture(fixture: dict) -> AnnualUniversePolicy:
    policy = AnnualUniversePolicy.standard()
    declared = fixture["universe"]["policy"]
    assert policy.minimum_listing_sessions == declared["minimum_listing_sessions"]
    assert policy.trailing_amount_sessions == declared["trailing_amount_sessions"]
    assert policy.minimum_cohort_size == declared["minimum_cohort_size"]
    assert policy.maximum_cohort_size == declared["maximum_cohort_size"]
    return policy


@pytest.fixture
def stock_flight(
    bar_factory,
    tradability_factory,
    calendar_factory,
    research_clock,
    stock_master,
    account_fees_factory,
    execution_model_factory,
):
    fixture = load_fixture()
    sessions = _sessions(fixture)
    schedule = form_annual_schedule(
        _build_formation_records(fixture), _real_policy_matches_fixture(fixture)
    )
    strategy = StockRelativeStrengthSmokeStrategy()
    # The schedule is injected whole; the adapter resolves the cohort
    # governing each decision session (per-decision-date resolution).
    adapter = StrategyTargetSource(strategy, schedule)
    engine = DailyBarEngine(
        calendar=calendar_factory(fixture["calendar_id"], sessions),
        clock=research_clock,
        master=stock_master,
        account_fees=account_fees_factory(
            fixture["account"]["commission_rate"],
            fixture["account"]["minimum_commission"],
        ),
        execution_model=execution_model_factory(fixture["execution"]["slippage_rate"]),
        bars=_build_bars(fixture, bar_factory),
        tradability=_build_tradability(fixture, tradability_factory),
        corporate_actions=(),
        target_source=adapter,
        initial_cash=Money(Decimal(fixture["account"]["initial_cash"])),
    )
    result = engine.run(start_session=sessions[0], end_session=sessions[-1])
    return fixture, schedule, adapter, result


def test_real_policy_cohort_is_flown_for_the_year(stock_flight) -> None:
    _fixture, schedule, _adapter, _result = stock_flight
    fixture = load_fixture()

    universe_view = schedule.view_for(_sessions(fixture)[0])
    assert len(universe_view.instrument_ids) == 22
    assert (
        len(universe_view.instrument_ids)
        >= fixture["universe"]["policy"]["minimum_cohort_size"]
    )
    last = _sessions(fixture)[-1]
    schedule = form_annual_schedule(
        _build_formation_records(fixture), AnnualUniversePolicy.standard()
    )
    assert schedule.view_for(last).instrument_ids == universe_view.instrument_ids


def test_typed_evaluations_match_hand_audited_expectations(stock_flight) -> None:
    _fixture, _schedule, adapter, _result = stock_flight
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
            contributions = record.evaluation.contributions
            assert len(contributions) == len(want["contributions"])
            for contribution, expected_contribution in zip(
                contributions, want["contributions"], strict=True
            ):
                assert (
                    str(contribution.instrument_id) == expected_contribution["instrument"]
                )
                assert contribution.sleeve.value == expected_contribution["sleeve"]
                assert contribution.target_weight == Decimal(
                    expected_contribution["target_weight"]
                )
                assert contribution.strategy_id == STOCK_SMOKE_IDENTITY.strategy_id
                assert (
                    contribution.strategy_version == STOCK_SMOKE_IDENTITY.strategy_version
                )


def test_every_contribution_respects_the_resolved_view(stock_flight) -> None:
    _fixture, schedule, adapter, _result = stock_flight

    for record in adapter.evaluations:
        # A T-close decision serves the decision_for_trade_date, so the
        # governing cohort is the one for that trade date's calendar year.
        view = schedule.view_for(record.decision_for_trade_date)
        for contribution in record.evaluation.contributions:
            if contribution.target_weight == 0:
                continue
            assert view.contains(contribution.instrument_id)


def test_satellite_plans_match_hand_audited_lot_sizing(stock_flight) -> None:
    _fixture, _schedule, _adapter, result = stock_flight
    fixture = load_fixture()

    for want_session in fixture["expected"]["plans"]:
        session = result.session(date.fromisoformat(want_session["session"]))
        assert session.target is not None
        assert session.decision_digest is not None
        assert len(session.plans) == len(want_session["plans"])
        for plan, want_plan in zip(session.plans, want_session["plans"], strict=True):
            assert str(plan.instrument_id) == want_plan["instrument"]
            assert plan.side.value == want_plan["side"]
            assert plan.order_quantity == want_plan["quantity"]
            assert plan.sizing_reference_price == Decimal(
                want_plan["sizing_reference_price"]
            )
            assert plan.sleeve is SleeveId.SATELLITE


def test_all_planned_quantities_are_complete_lots(stock_flight) -> None:
    _fixture, _schedule, _adapter, result = stock_flight

    for session_record in result.sessions:
        for plan in session_record.plans:
            assert plan.order_quantity % 100 == 0


def test_first_buy_fills_at_t1_open_with_fees(stock_flight) -> None:
    _fixture, _schedule, _adapter, result = stock_flight
    fixture = load_fixture()

    for want_session in fixture["expected"]["fills"]:
        session = result.session(date.fromisoformat(want_session["session"]))
        fills = session.activation.fills
        assert len(fills) == len(want_session["fills"])
        for fill, want_fill in zip(fills, want_session["fills"], strict=True):
            assert str(fill.instrument_id) == want_fill["instrument"]
            assert fill.side.value == want_fill["side"]
            assert fill.quantity == want_fill["quantity"]
            assert fill.fill_price == Decimal(want_fill["fill_price"])
            assert fill.reference_open == Decimal(want_fill["reference_open"])
            assert fill.fees.commission.amount == Decimal(want_fill["commission"])
            assert fill.fees.minimum_commission_adjustment.amount == Decimal(
                want_fill["minimum_commission_adjustment"]
            )
            assert fill.fees.stamp_tax.amount == Decimal(want_fill["stamp_tax"])
            assert fill.fees.transfer_fee.amount == Decimal(want_fill["transfer_fee"])


def test_suspended_target_is_rejected_not_filled(stock_flight) -> None:
    _fixture, _schedule, _adapter, result = stock_flight
    fixture = load_fixture()

    rejections = result.rejections
    assert len(rejections) == len(fixture["expected"]["rejections"])
    for rejection, want in zip(
        rejections, fixture["expected"]["rejections"], strict=True
    ):
        assert rejection.session_date.isoformat() == want["session"]
        assert str(rejection.instrument_id) == want["instrument"]
        assert rejection.side.value == want["side"]
        assert rejection.code is RejectionCode[want["code"]]
        assert rejection.order_id.endswith(want["instrument"])
        order = next(
            order
            for order in result.orders
            if order.order_id == rejection.order_id
        )
        assert order.planned_quantity == want["planned_quantity"]
        assert order.status.value == "REJECTED"


def test_t1_settlement_gates_each_rotation_sell(stock_flight) -> None:
    _fixture, _schedule, _adapter, result = stock_flight
    fixture = load_fixture()

    buy_entries = [
        entry
        for entry in result.holdings_entries
        if entry.quantity_delta > 0
    ]
    for want in fixture["expected"]["t1_settlement"]:
        entry = next(
            candidate
            for candidate in buy_entries
            if candidate.instrument_id == InstrumentId.parse(want["instrument"])
            and candidate.session_date == date.fromisoformat(want["fill_session"])
        )
        assert entry.quantity_delta == want["quantity"]
        assert entry.acquisition_session == date.fromisoformat(want["fill_session"])
        assert entry.sellable_from == date.fromisoformat(want["sellable_from"])

    # Every stamp-tax rotation sell happened on or after the session the
    # acquired lot became sellable (T+1 settlement cleared), and no sell was
    # ever refused for insufficient sellable quantity.
    assert all(
        rejection.code is RejectionCode.SUSPENDED
        for rejection in result.rejections
    )
    sell_fills = [fill for fill in result.fills if fill.side is TradeSide.SELL]
    assert sell_fills
    for fill in sell_fills:
        earliest_sellable = min(
            (
                entry.sellable_from
                for entry in buy_entries
                if entry.instrument_id == fill.instrument_id
            ),
        )
        assert fill.session_date >= earliest_sellable


def test_global_affordability_keeps_cash_non_negative(stock_flight) -> None:
    _fixture, _schedule, _adapter, result = stock_flight
    fixture = load_fixture()

    running = Decimal(fixture["account"]["initial_cash"])
    for session_record in result.sessions:
        running = session_record.activation.cash.amount
        assert running >= 0
    for want in fixture["expected"]["cash_after"]:
        session = result.session(date.fromisoformat(want["session"]))
        assert session.activation.cash.amount == Decimal(want["cash"])


def test_nav_series_matches_hand_audited_expectations(stock_flight) -> None:
    _fixture, _schedule, _adapter, result = stock_flight
    fixture = load_fixture()

    for want in fixture["expected"]["equity_at_close"]:
        record = result.session(date.fromisoformat(want["session"]))
        assert record.snapshot.total_equity.amount == Decimal(want["equity"])


def test_final_account_state_matches_hand_audited_expectations(stock_flight) -> None:
    _fixture, _schedule, _adapter, result = stock_flight
    fixture = load_fixture()
    want = fixture["expected"]["final"]

    assert result.cash.amount == Decimal(want["cash"])
    assert len(result.positions) == len(want["positions"])
    for position, want_position in zip(result.positions, want["positions"], strict=True):
        assert str(position.instrument_id) == want_position["instrument"]
        assert position.total_quantity == want_position["quantity"]


def test_metrics_match_hand_audited_expectations(stock_flight) -> None:
    _fixture, _schedule, _adapter, result = stock_flight
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
    stock_flight,
    bar_factory,
    tradability_factory,
    calendar_factory,
    research_clock,
    stock_master,
    account_fees_factory,
    execution_model_factory,
) -> None:
    _fixture, _schedule, _adapter, _result = stock_flight
    fixture = load_fixture()
    sessions = _sessions(fixture)
    schedule = form_annual_schedule(
        _build_formation_records(fixture), AnnualUniversePolicy.standard()
    )

    second = DailyBarEngine(
        calendar=calendar_factory(fixture["calendar_id"], sessions),
        clock=research_clock,
        master=stock_master,
        account_fees=account_fees_factory(
            fixture["account"]["commission_rate"],
            fixture["account"]["minimum_commission"],
        ),
        execution_model=execution_model_factory(fixture["execution"]["slippage_rate"]),
        bars=tuple(reversed(_build_bars(fixture, bar_factory))),
        tradability=tuple(reversed(_build_tradability(fixture, tradability_factory))),
        corporate_actions=(),
        target_source=StrategyTargetSource(
            StockRelativeStrengthSmokeStrategy(), schedule
        ),
        initial_cash=Money(Decimal(fixture["account"]["initial_cash"])),
    ).run(start_session=sessions[0], end_session=sessions[-1])

    assert _result.content_digest() == second.content_digest()


_CROSS_YEAR_2022_ID = "XSHG:600001"  # role W1: kept in both cohorts
_CROSS_YEAR_2022_EXIT = "XSHG:600002"  # role W2: ST at the 2022 formation
_CROSS_YEAR_NEW_ID = "XSHG:600099"  # newly eligible for 2023


def _cross_year_trailing(
    amount: str, count: int, *, end: date
) -> tuple[TrailingAmount, ...]:
    session_dates: list[date] = []
    cursor = end
    while len(session_dates) < count:
        if cursor.weekday() < 5:
            session_dates.append(cursor)
        cursor = cursor - timedelta(days=1)
    session_dates.reverse()
    return tuple(
        TrailingAmount(session_date, Decimal(amount))
        for session_date in session_dates
    )


def _cross_year_formation_records() -> tuple[StockFormationFact, ...]:
    """Two real-policy formations: 2021-12-31 (22 names) and 2022-12-30
    (21 names after XSHG:600002 turns ST, plus XSHG:600099 becoming
    eligible). Each fact is the cutoff-time snapshot for its year."""
    cutoff_2021 = date(2021, 12, 31)
    cutoff_2022 = date(2022, 12, 30)
    members = [
        "XSHG:600001",
        "XSHG:600002",
        "XSHG:600003",
        "XSHG:600004",
        "XSHG:600005",
        "XSHG:600006",
        *[f"XSHG:6000{index:02d}" for index in range(11, 27)],
    ]
    records = [
        StockFormationFact(
            instrument_id=InstrumentId.parse(symbol),
            formation_session=cutoff_2021,
            listed_sessions=300,
            identity_status=StockIdentityStatus.NORMAL,
            tradability=TradabilityStatusKind.TRADABLE,
            trailing_amounts=_cross_year_trailing("4500000", 60, end=cutoff_2021),
        )
        for symbol in members
    ]
    for symbol in members:
        records.append(
            StockFormationFact(
                instrument_id=InstrumentId.parse(symbol),
                formation_session=cutoff_2022,
                listed_sessions=300,
                identity_status=(
                    StockIdentityStatus.ST
                    if symbol == _CROSS_YEAR_2022_EXIT
                    else StockIdentityStatus.NORMAL
                ),
                tradability=TradabilityStatusKind.TRADABLE,
                trailing_amounts=_cross_year_trailing("4500000", 60, end=cutoff_2022),
            )
        )
    records.append(
        StockFormationFact(
            instrument_id=InstrumentId.parse(_CROSS_YEAR_NEW_ID),
            formation_session=cutoff_2022,
            listed_sessions=300,
            identity_status=StockIdentityStatus.NORMAL,
            tradability=TradabilityStatusKind.TRADABLE,
            trailing_amounts=_cross_year_trailing("4600000", 60, end=cutoff_2022),
        )
    )
    return tuple(records)


def test_cross_year_schedule_rotates_at_the_year_end_cutoff() -> None:
    schedule = form_annual_schedule(
        _cross_year_formation_records(), AnnualUniversePolicy.standard()
    )

    cohort_2022 = schedule.view_for(date(2022, 12, 30))
    cohort_2023 = schedule.view_for(date(2023, 1, 3))

    assert len(cohort_2022.instrument_ids) == 22
    assert InstrumentId.parse(_CROSS_YEAR_2022_EXIT) in cohort_2022.instrument_ids
    assert InstrumentId.parse(_CROSS_YEAR_NEW_ID) not in cohort_2022.instrument_ids
    assert InstrumentId.parse(_CROSS_YEAR_2022_EXIT) not in cohort_2023.instrument_ids
    assert InstrumentId.parse(_CROSS_YEAR_NEW_ID) in cohort_2023.instrument_ids
    assert len(cohort_2023.instrument_ids) == 22


def test_cross_year_run_exits_the_left_cohort_holding(
    bar_factory,
    tradability_factory,
    calendar_factory,
    research_clock,
    stock_master,
    account_fees_factory,
    execution_model_factory,
) -> None:
    """Per-target-trade-date cohort resolution, plus the P1 exit path.

    The W2 holding is bought under a 2022-cohort decision and, on the last
    2022 decision (whose trade date falls into 2023), the resolved 2023
    cohort already governs: the new instrument enters top-2 and the held
    2022-only instrument is explicitly targeted at zero even though it is
    outside the resolved 2023 view, and M0 sells it at T+1."""
    fixture = load_fixture()
    sessions = (
        date(2022, 12, 23),
        date(2022, 12, 26),
        date(2022, 12, 27),
        date(2022, 12, 28),
        date(2022, 12, 29),
        date(2022, 12, 30),
        date(2023, 1, 3),
    )
    calendar_sessions = (*sessions, date(2023, 1, 4))
    paths = {
        _CROSS_YEAR_2022_ID: [
            "9.90", "10.00", "10.10", "10.20", "10.30", "10.40", "10.50"
        ],
        _CROSS_YEAR_2022_EXIT: [
            "19.90", "20.00", "20.10", "20.20", "20.30", "20.40", "20.50"
        ],
        _CROSS_YEAR_NEW_ID: [
            "12.00", "12.10", "12.20", "12.30", "12.40", "13.64", "13.84"
        ],
    }
    members = [
        _CROSS_YEAR_2022_ID,
        _CROSS_YEAR_2022_EXIT,
        "XSHG:600003",
        "XSHG:600004",
        "XSHG:600005",
        "XSHG:600006",
        *[f"XSHG:6000{index:02d}" for index in range(11, 27)],
        _CROSS_YEAR_NEW_ID,
    ]
    bars = []
    for symbol in members:
        instrument_id = InstrumentId.parse(symbol)
        closes = paths.get(symbol, ["10.00"] * 7)
        for index, session_date in enumerate(sessions):
            close = Decimal(closes[index])
            open_price = Decimal(closes[index - 1]) if index else close
            bars.append(
                bar_factory(
                    instrument_id,
                    session_date,
                    open=str(open_price),
                    close=str(close),
                    high=str(max(open_price, close)),
                    low=str(min(open_price, close)),
                    pre_close=str(open_price) if index else None,
                )
            )
    tradability = tuple(
        tradability_factory(
            InstrumentId.parse(symbol), session_date, TradabilityStatusKind.TRADABLE
        )
        for symbol in members
        for session_date in sessions
    )
    schedule = form_annual_schedule(
        _cross_year_formation_records(), AnnualUniversePolicy.standard()
    )
    adapter = StrategyTargetSource(StockRelativeStrengthSmokeStrategy(), schedule)
    engine = DailyBarEngine(
        calendar=calendar_factory("XSHG", calendar_sessions),
        clock=research_clock,
        master=stock_master,
        account_fees=account_fees_factory("0.0003", "5"),
        execution_model=execution_model_factory("0.0005"),
        bars=tuple(bars),
        tradability=tradability,
        corporate_actions=(),
        target_source=adapter,
        initial_cash=Money(Decimal(fixture["account"]["initial_cash"])),
    )
    result = engine.run(start_session=sessions[0], end_session=sessions[-1])

    assert result.rejections == ()

    # The last 2022 decision (session 2022-12-29, trade date 2022-12-30)
    # resolved the 2022 cohort: both picks are 2022 members, the new
    # instrument is invisible before it is reconstituted, and the buys are
    # sized at the T close (150000/10.30 = 14563 -> 14500; 150000/20.30
    # = 7389 -> 7300).
    last_2022_decision = next(
        record
        for record in adapter.evaluations
        if record.decision_for_trade_date == date(2022, 12, 30)
    )
    assert last_2022_decision.session_date == date(2022, 12, 29)
    assert [
        (str(contribution.instrument_id), str(contribution.target_weight))
        for contribution in last_2022_decision.evaluation.contributions
    ] == [
        (_CROSS_YEAR_2022_ID, "0.5"),
        (_CROSS_YEAR_2022_EXIT, "0.5"),
    ]
    plans_2022 = result.session(date(2022, 12, 29)).plans
    assert [
        (str(plan.instrument_id), plan.side.value, plan.order_quantity)
        for plan in plans_2022
    ] == [(_CROSS_YEAR_2022_ID, "BUY", 14500), (_CROSS_YEAR_2022_EXIT, "BUY", 7300)]

    # The year-end session decision (2022-12-30, trade date 2023-01-03) is
    # already governed by the 2023 cohort: the new instrument returns
    # (13.64-12.10)/12.10 = 12.73% and takes the top pick, and the
    # just-acquired 2022-only holding is explicitly targeted at zero even
    # though it is outside the resolved 2023 view. A session-date-based
    # implementation would still resolve the 2022 cohort here and re-target
    # W2 at 0.5, so this assertion kills that off-by-one.
    first_2023_decision = next(
        record
        for record in adapter.evaluations
        if record.decision_for_trade_date == date(2023, 1, 3)
    )
    assert first_2023_decision.session_date == date(2022, 12, 30)
    assert [
        (str(contribution.instrument_id), str(contribution.target_weight))
        for contribution in first_2023_decision.evaluation.contributions
    ] == [
        (_CROSS_YEAR_NEW_ID, "0.5"),
        (_CROSS_YEAR_2022_ID, "0.5"),
        (_CROSS_YEAR_2022_EXIT, "0"),
    ]
    assert not schedule.view_for(date(2023, 1, 3)).contains(
        InstrumentId.parse(_CROSS_YEAR_2022_EXIT)
    )

    exit_plans = [
        plan
        for plan in result.session(date(2022, 12, 30)).plans
        if str(plan.instrument_id) == _CROSS_YEAR_2022_EXIT
    ]
    assert len(exit_plans) == 1
    assert exit_plans[0].side is TradeSide.SELL
    assert exit_plans[0].order_quantity == 7300

    exit_fills = [
        fill
        for fill in result.fills
        if fill.side is TradeSide.SELL
        and str(fill.instrument_id) == _CROSS_YEAR_2022_EXIT
    ]
    assert len(exit_fills) == 1
    assert exit_fills[0].quantity == 7300
    assert not any(
        str(position.instrument_id) == _CROSS_YEAR_2022_EXIT
        for position in result.positions
    )
