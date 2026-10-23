"""Typed StrategyContract tests (M1-S01/S02/S03/S04 shape, Task 1 scope).

The contract must distinguish a typed ``NO_DECISION`` with reason codes from
an explicit zero-weight target, keep determinism under input reordering, and
raise loudly on contract violations instead of producing silent decisions.
The engine-seam regressions additionally prove that ``NO_DECISION`` crosses
the M0 kernel unchanged while an actual ``TARGETS`` result that omits a
current holding is failed by the M0 complete-target boundary.
"""

from datetime import UTC, date, datetime, time
from decimal import Decimal

import pytest
from smoke_strategies import SMOKE_IDENTITY, CloseAboveSmaStrategy

from systematic_investing.backtest.engine import (
    DailyBarEngine,
    DecisionBlockReason,
    DecisionContext,
)
from systematic_investing.domain.identifiers import InstrumentId, SleeveId
from systematic_investing.domain.ledger import AcquisitionLot, Position
from systematic_investing.domain.money import Money
from systematic_investing.domain.portfolio import TargetContribution
from systematic_investing.research.contracts import (
    REASON_INSUFFICIENT_HISTORY,
    InvalidStrategyIdentityError,
    StrategyEvaluation,
    StrategyEvaluationStatus,
    StrategyIdentity,
    canonical_parameters_digest,
    implementation_digest_of,
)
from systematic_investing.research.runner import (
    StrategyContractViolationError,
    StrategyTargetSource,
)
from systematic_investing.research.universe import InvalidUniverseViewError, UniverseView

ETF = InstrumentId.parse("XSHG:510300")
GOLD = InstrumentId.parse("XSHG:518880")

_SHIFTED_IDENTITY = StrategyIdentity(
    strategy_id=SMOKE_IDENTITY.strategy_id,
    strategy_version="v2",
    implementation_digest="sha256:" + "a" * 64,
    parameters=dict(SMOKE_IDENTITY.parameters),
    parameters_digest=SMOKE_IDENTITY.parameters_digest,
    sleeve=SMOKE_IDENTITY.sleeve,
    required_history_sessions=SMOKE_IDENTITY.required_history_sessions,
    decision_frequency=SMOKE_IDENTITY.decision_frequency,
)


def decision_context(bars, *, session_date, next_session) -> DecisionContext:
    return DecisionContext(
        session_date=session_date,
        decision_for_trade_date=next_session,
        information_cutoff=datetime.combine(session_date, time(15, 30), tzinfo=UTC),
        cash=Money(Decimal("100000")),
        valuation_equity=Money(Decimal("100000")),
        positions=(),
        bars=tuple(bars),
    )


def test_insufficient_history_is_typed_no_decision(
    bar_factory, etf_universe: UniverseView
) -> None:
    bars = (
        bar_factory(ETF, date(2026, 9, 9), open="99.50", close="100.00"),
        bar_factory(ETF, date(2026, 9, 10), open="100.50", close="101.00"),
    )
    context = decision_context(
        bars, session_date=date(2026, 9, 10), next_session=date(2026, 9, 11)
    )
    strategy = CloseAboveSmaStrategy()

    evaluation = strategy.evaluate(context, etf_universe)

    assert evaluation.status is StrategyEvaluationStatus.NO_DECISION
    assert evaluation.reason_codes == (REASON_INSUFFICIENT_HISTORY,)
    assert evaluation.contributions == ()


def test_explicit_cash_target_is_not_no_decision(
    bar_factory, etf_universe: UniverseView
) -> None:
    bars = (
        bar_factory(ETF, date(2026, 9, 9), open="104.50", close="105.00"),
        bar_factory(ETF, date(2026, 9, 10), open="103.50", close="104.00"),
        bar_factory(ETF, date(2026, 9, 11), open="100.50", close="100.00"),
    )
    context = decision_context(
        bars, session_date=date(2026, 9, 11), next_session=date(2026, 9, 14)
    )
    strategy = CloseAboveSmaStrategy()

    evaluation = strategy.evaluate(context, etf_universe)

    assert evaluation.status is StrategyEvaluationStatus.TARGETS
    assert len(evaluation.contributions) == 1
    assert evaluation.contributions[0].target_weight == Decimal("0")
    assert evaluation.contributions[0].instrument_id == ETF
    assert evaluation.contributions[0].sleeve is SMOKE_IDENTITY.sleeve


def test_same_slice_same_targets_regardless_of_input_order(
    bar_factory, etf_universe: UniverseView
) -> None:
    bars = (
        bar_factory(ETF, date(2026, 9, 9), open="99.50", close="100.00"),
        bar_factory(ETF, date(2026, 9, 10), open="100.50", close="101.00"),
        bar_factory(ETF, date(2026, 9, 11), open="101.50", close="102.00"),
    )
    ordered = decision_context(
        bars, session_date=date(2026, 9, 11), next_session=date(2026, 9, 14)
    )
    shuffled = decision_context(
        tuple(reversed(bars)),
        session_date=date(2026, 9, 11),
        next_session=date(2026, 9, 14),
    )
    strategy = CloseAboveSmaStrategy()

    first = strategy.evaluate(ordered, etf_universe)
    second = strategy.evaluate(shuffled, etf_universe)

    assert first == second
    assert first.contributions[0].target_weight == Decimal("1")


def test_universe_view_is_canonical_order_free_and_validated() -> None:
    bond = InstrumentId.parse("XSHG:511010")
    gold = InstrumentId.parse("XSHG:518880")

    view = UniverseView((gold, bond))

    assert view.instrument_ids == (bond, gold)
    assert view.contains(gold)
    assert not view.contains(ETF)
    with pytest.raises(InvalidUniverseViewError):
        UniverseView(())
    with pytest.raises(InvalidUniverseViewError):
        UniverseView((bond, bond))


def test_identity_digests_change_with_content() -> None:
    assert SMOKE_IDENTITY.parameters_digest == canonical_parameters_digest(
        SMOKE_IDENTITY.parameters
    )
    changed = dict(SMOKE_IDENTITY.parameters)
    changed["sma_sessions"] = "4"
    assert canonical_parameters_digest(changed) != SMOKE_IDENTITY.parameters_digest

    base = implementation_digest_of([("module.py", b"content")])
    assert base.startswith("sha256:")
    assert implementation_digest_of([("module.py", b"other")]) != base
    assert implementation_digest_of([("other.py", b"content")]) != base


def test_identity_freezes_parameters_against_external_mutation() -> None:
    parameters = {"sma_sessions": "3"}
    identity = StrategyIdentity(
        strategy_id="smoke-close-above-sma",
        strategy_version="v1",
        implementation_digest="sha256:" + "0" * 64,
        parameters=parameters,
        parameters_digest=canonical_parameters_digest(parameters),
        sleeve=SleeveId.CORE,
        required_history_sessions=3,
        decision_frequency="EVERY_SESSION",
    )
    bound_digest = identity.content_digest()

    parameters["sma_sessions"] = "9"
    parameters["extra"] = "sneaky"

    assert dict(identity.parameters) == {"sma_sessions": "3"}
    assert identity.parameters_digest == canonical_parameters_digest({"sma_sessions": "3"})
    assert identity.content_digest() == bound_digest


def test_identity_rejects_mismatched_parameters_digest() -> None:
    with pytest.raises(InvalidStrategyIdentityError):
        StrategyIdentity(
            strategy_id="smoke-close-above-sma",
            strategy_version="v1",
            implementation_digest="sha256:" + "0" * 64,
            parameters={"sma_sessions": "3"},
            parameters_digest="sha256:" + "1" * 64,
            sleeve=SleeveId.CORE,
            required_history_sessions=3,
            decision_frequency="EVERY_SESSION",
        )


class _ForeignIdentityStrategy:
    """Emits a contribution that does not belong to the declared identity."""

    @property
    def identity(self) -> StrategyIdentity:
        return SMOKE_IDENTITY

    def evaluate(self, context: DecisionContext, universe: UniverseView) -> StrategyEvaluation:
        foreign = TargetContribution(
            instrument_id=ETF,
            sleeve=SleeveId.CORE,
            strategy_id="not-the-strategy",
            strategy_version="v1",
            target_weight=Decimal("1"),
        )
        return StrategyEvaluation(
            status=StrategyEvaluationStatus.TARGETS,
            contributions=(foreign,),
        )


def test_adapter_maps_no_decision_to_none_and_retains_evaluation(
    bar_factory, etf_universe: UniverseView
) -> None:
    short_bars = (
        bar_factory(ETF, date(2026, 9, 9), open="99.50", close="100.00"),
        bar_factory(ETF, date(2026, 9, 10), open="100.50", close="101.00"),
    )
    short_context = decision_context(
        short_bars, session_date=date(2026, 9, 10), next_session=date(2026, 9, 11)
    )
    trend_bars = (
        bar_factory(ETF, date(2026, 9, 9), open="99.50", close="100.00"),
        bar_factory(ETF, date(2026, 9, 10), open="100.50", close="101.00"),
        bar_factory(ETF, date(2026, 9, 11), open="101.50", close="102.00"),
    )
    trend_context = decision_context(
        trend_bars, session_date=date(2026, 9, 11), next_session=date(2026, 9, 14)
    )
    adapter = StrategyTargetSource(CloseAboveSmaStrategy(), etf_universe)

    assert adapter.contributions_for(short_context) is None
    assert adapter.evaluations[-1].evaluation.status is StrategyEvaluationStatus.NO_DECISION
    assert adapter.evaluations[-1].session_date == date(2026, 9, 10)

    contributions = adapter.contributions_for(trend_context)
    assert contributions is not None
    assert contributions == adapter.evaluations[-1].evaluation.contributions
    assert adapter.evaluations[-1].decision_for_trade_date == date(2026, 9, 14)
    assert len(adapter.evaluations) == 2


class _ForeignUniverseStrategy:
    """Emits a valid-identity contribution for an instrument outside the
    injected universe."""

    @property
    def identity(self) -> StrategyIdentity:
        return SMOKE_IDENTITY

    def evaluate(self, context: DecisionContext, universe: UniverseView) -> StrategyEvaluation:
        outside = TargetContribution(
            instrument_id=InstrumentId.parse("XSHG:511010"),
            sleeve=SleeveId.CORE,
            strategy_id=SMOKE_IDENTITY.strategy_id,
            strategy_version=SMOKE_IDENTITY.strategy_version,
            target_weight=Decimal("1"),
        )
        return StrategyEvaluation(
            status=StrategyEvaluationStatus.TARGETS,
            contributions=(outside,),
        )


def test_adapter_rejects_contribution_outside_universe(
    bar_factory, etf_universe: UniverseView
) -> None:
    bars = (
        bar_factory(ETF, date(2026, 9, 9), open="99.50", close="100.00"),
        bar_factory(ETF, date(2026, 9, 10), open="100.50", close="101.00"),
        bar_factory(ETF, date(2026, 9, 11), open="101.50", close="102.00"),
    )
    context = decision_context(
        bars, session_date=date(2026, 9, 11), next_session=date(2026, 9, 14)
    )
    adapter = StrategyTargetSource(_ForeignUniverseStrategy(), etf_universe)

    with pytest.raises(StrategyContractViolationError):
        adapter.contributions_for(context)
    assert adapter.evaluations == ()


class _ShiftingIdentityStrategy:
    """Emits a contribution valid for the bound identity, then shifts its
    identity mid-run."""

    def __init__(self) -> None:
        self._shifted = False

    @property
    def identity(self) -> StrategyIdentity:
        if self._shifted:
            return _SHIFTED_IDENTITY
        return SMOKE_IDENTITY

    def evaluate(self, context: DecisionContext, universe: UniverseView) -> StrategyEvaluation:
        contribution = TargetContribution(
            instrument_id=ETF,
            sleeve=SleeveId.CORE,
            strategy_id=SMOKE_IDENTITY.strategy_id,
            strategy_version=SMOKE_IDENTITY.strategy_version,
            target_weight=Decimal("1"),
        )
        self._shifted = True
        return StrategyEvaluation(
            status=StrategyEvaluationStatus.TARGETS,
            contributions=(contribution,),
        )


def test_adapter_rejects_identity_change_during_run(
    bar_factory, etf_universe: UniverseView
) -> None:
    bars = (
        bar_factory(ETF, date(2026, 9, 9), open="99.50", close="100.00"),
        bar_factory(ETF, date(2026, 9, 10), open="100.50", close="101.00"),
        bar_factory(ETF, date(2026, 9, 11), open="101.50", close="102.00"),
    )
    context = decision_context(
        bars, session_date=date(2026, 9, 11), next_session=date(2026, 9, 14)
    )
    adapter = StrategyTargetSource(_ShiftingIdentityStrategy(), etf_universe)

    with pytest.raises(StrategyContractViolationError):
        adapter.contributions_for(context)
    assert adapter.evaluations == ()


def test_adapter_rejects_foreign_identity_contributions(
    bar_factory, etf_universe: UniverseView
) -> None:
    bars = (
        bar_factory(ETF, date(2026, 9, 9), open="99.50", close="100.00"),
        bar_factory(ETF, date(2026, 9, 10), open="100.50", close="101.00"),
        bar_factory(ETF, date(2026, 9, 11), open="101.50", close="102.00"),
    )
    context = decision_context(
        bars, session_date=date(2026, 9, 11), next_session=date(2026, 9, 14)
    )
    adapter = StrategyTargetSource(_ForeignIdentityStrategy(), etf_universe)

    with pytest.raises(StrategyContractViolationError):
        adapter.contributions_for(context)
    assert adapter.evaluations == ()


def test_engine_preserves_no_decision_without_target_or_block(
    bar_factory,
    tradability_factory,
    calendar_factory,
    research_clock,
    research_master,
    account_fees_factory,
    execution_model_factory,
    etf_universe: UniverseView,
) -> None:
    """A typed NO_DECISION must cross the kernel as no decision at all.

    It is not CASH (no target object exists), not an explicit zero target,
    and not TARGET_INCOMPLETE: the complete-target boundary is only entered
    by an actual TargetPortfolio.
    """
    sessions = (date(2026, 9, 9), date(2026, 9, 10), date(2026, 9, 11))
    bars = tuple(
        bar_factory(ETF, session_date, open="100.00", close="101.00")
        for session_date in sessions
    )
    result = DailyBarEngine(
        calendar=calendar_factory("XSHG", sessions),
        clock=research_clock,
        master=research_master,
        account_fees=account_fees_factory("0.0003", "5"),
        execution_model=execution_model_factory("0.001"),
        bars=bars,
        tradability=tuple(
            tradability_factory(ETF, session_date) for session_date in sessions
        ),
        corporate_actions=(),
        target_source=StrategyTargetSource(CloseAboveSmaStrategy(), etf_universe),
        initial_cash=Money(Decimal("100000")),
    ).run(start_session=sessions[0], end_session=sessions[-1])

    insufficient = result.session(sessions[0])
    assert insufficient.target is None
    assert insufficient.decision_blocked_reason is None
    assert insufficient.plans == ()
    assert result.session(sessions[1]).activation.orders == ()
    assert result.session(sessions[1]).activation.fills == ()


class _OmittingHoldingStrategy:
    """Emits a valid TARGETS result that addresses the universe instrument
    but silently omits a currently held instrument outside the universe."""

    @property
    def identity(self) -> StrategyIdentity:
        return SMOKE_IDENTITY

    def evaluate(self, context: DecisionContext, universe: UniverseView) -> StrategyEvaluation:
        return StrategyEvaluation(
            status=StrategyEvaluationStatus.TARGETS,
            contributions=(
                TargetContribution(
                    instrument_id=universe.instrument_ids[0],
                    sleeve=SMOKE_IDENTITY.sleeve,
                    strategy_id=SMOKE_IDENTITY.strategy_id,
                    strategy_version=SMOKE_IDENTITY.strategy_version,
                    target_weight=Decimal("1"),
                ),
            ),
        )


def test_incomplete_targets_result_fails_the_m0_complete_target_boundary(
    bar_factory,
    tradability_factory,
    calendar_factory,
    research_clock,
    research_master,
    account_fees_factory,
    execution_model_factory,
    etf_universe: UniverseView,
) -> None:
    """A TARGETS result that omits a held instrument reaches M0 and fails.

    The adapter passes identity-valid, in-universe contributions through;
    the M0 complete-target boundary—not the adapter—must reject the target
    with TARGET_INCOMPLETE and produce no executable plan, so the holding is
    physically retained without absence ever being read as HOLD or SELL.
    """
    sessions = (date(2026, 9, 11), date(2026, 9, 14))
    bars = tuple(
        bar_factory(instrument_id, session_date, open="4.00", close="4.00")
        for instrument_id in (ETF, GOLD)
        for session_date in sessions
    )
    result = DailyBarEngine(
        calendar=calendar_factory("XSHG", sessions),
        clock=research_clock,
        master=research_master,
        account_fees=account_fees_factory("0.0003", "5"),
        execution_model=execution_model_factory("0.001"),
        bars=bars,
        tradability=tuple(
            tradability_factory(instrument_id, session_date)
            for instrument_id in (ETF, GOLD)
            for session_date in sessions
        ),
        corporate_actions=(),
        target_source=StrategyTargetSource(_OmittingHoldingStrategy(), etf_universe),
        initial_cash=Money(Decimal("0")),
        initial_positions=(
            Position(
                instrument_id=ETF,
                lots=(
                    AcquisitionLot(
                        quantity=1000,
                        acquired_session=date(2026, 9, 1),
                        sellable_from=date(2026, 9, 2),
                        acquisition_price=Decimal("4.00"),
                    ),
                ),
            ),
            Position(
                instrument_id=GOLD,
                lots=(
                    AcquisitionLot(
                        quantity=1000,
                        acquired_session=date(2026, 9, 1),
                        sellable_from=date(2026, 9, 2),
                        acquisition_price=Decimal("4.00"),
                    ),
                ),
            ),
        ),
    ).run(start_session=sessions[0], end_session=sessions[-1])

    decision = result.session(sessions[0])
    assert decision.target is not None
    assert decision.target.addressed_instruments == frozenset({ETF})
    assert decision.decision_blocked_reason is DecisionBlockReason.TARGET_INCOMPLETE
    assert decision.plans == ()
    assert result.orders == ()
    final = {position.instrument_id: position for position in result.positions}
    assert final[ETF].total_quantity == 1000
    assert final[GOLD].total_quantity == 1000
