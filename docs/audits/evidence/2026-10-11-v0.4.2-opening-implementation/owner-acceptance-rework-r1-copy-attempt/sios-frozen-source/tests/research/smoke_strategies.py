"""Test-only smoke strategies for the Research seam (never canonical).

``CloseAboveSmaStrategy`` proves the StrategyContract -> M0 adapter -> kernel
seam with a real, small, hand-auditable single-instrument algorithm.
``StockRelativeStrengthSmokeStrategy`` proves the same seam for a
cross-sectional Stock strategy over an annual PIT cohort with SATELLITE
sleeve contributions. Smoke strategies must never enter canonical
Basic/OOS runs: canonical strategies live in
``systematic_investing.research.strategies`` and are the only ones wired
into the Research CLI runner.
"""

from decimal import Decimal
from pathlib import Path

from systematic_investing.backtest.engine import DecisionContext
from systematic_investing.domain.identifiers import InstrumentId, SleeveId
from systematic_investing.domain.portfolio import TargetContribution
from systematic_investing.research.contracts import (
    REASON_INSUFFICIENT_HISTORY,
    StrategyEvaluation,
    StrategyEvaluationStatus,
    StrategyIdentity,
    canonical_parameters_digest,
    implementation_digest_of,
)
from systematic_investing.research.universe import UniverseView

_SMOKE_PARAMETERS: dict[str, str] = {"sma_sessions": "3"}
_SMOKE_REQUIRED_HISTORY = 3

_STOCK_SMOKE_PARAMETERS: dict[str, str] = {
    "return_sessions": "4",
    "top_n": "2",
    "equal_weight": "0.5",
}
_STOCK_SMOKE_REQUIRED_HISTORY = 5  # one 4-session return needs 5 closes


def _build_identity() -> StrategyIdentity:
    """Identity whose implementation digest covers this module's own bytes,
    addressed by its repo-relative path."""
    path = Path(__file__).resolve()
    return StrategyIdentity(
        strategy_id="smoke-close-above-sma",
        strategy_version="v1",
        implementation_digest=implementation_digest_of(
            [(path.relative_to(path.parents[2]).as_posix(), path.read_bytes())]
        ),
        parameters=_SMOKE_PARAMETERS,
        parameters_digest=canonical_parameters_digest(_SMOKE_PARAMETERS),
        sleeve=SleeveId.CORE,
        required_history_sessions=_SMOKE_REQUIRED_HISTORY,
        decision_frequency="EVERY_SESSION",
    )


SMOKE_IDENTITY = _build_identity()


def _build_stock_identity() -> StrategyIdentity:
    path = Path(__file__).resolve()
    return StrategyIdentity(
        strategy_id="smoke-stock-relative-strength",
        strategy_version="v1",
        implementation_digest=implementation_digest_of(
            [(path.relative_to(path.parents[2]).as_posix(), path.read_bytes())]
        ),
        parameters=_STOCK_SMOKE_PARAMETERS,
        parameters_digest=canonical_parameters_digest(_STOCK_SMOKE_PARAMETERS),
        sleeve=SleeveId.SATELLITE,
        required_history_sessions=_STOCK_SMOKE_REQUIRED_HISTORY,
        decision_frequency="EVERY_SESSION",
    )


STOCK_SMOKE_IDENTITY = _build_stock_identity()


class CloseAboveSmaStrategy:
    """Smoke strategy: TARGETS the first universe instrument with weight 1
    when the T close is above its N-session simple moving average (T
    included) and weight 0 when at or below. Fewer than N known closes yields
    a typed ``INSUFFICIENT_HISTORY`` no-decision.

    It owns no execution, accounting, data access, or state; it is a seam
    proof only.
    """

    @property
    def identity(self) -> StrategyIdentity:
        return SMOKE_IDENTITY

    def evaluate(
        self, context: DecisionContext, universe: UniverseView
    ) -> StrategyEvaluation:
        instrument_id = universe.instrument_ids[0]
        bars = context.bars_for(instrument_id)
        closes = tuple(bar.close for bar in bars)
        sessions = SMOKE_IDENTITY.required_history_sessions
        if len(closes) < sessions:
            return StrategyEvaluation(
                status=StrategyEvaluationStatus.NO_DECISION,
                contributions=(),
                reason_codes=(REASON_INSUFFICIENT_HISTORY,),
            )
        window = closes[-sessions:]
        sma = sum(window, Decimal("0")) / Decimal(sessions)
        weight = Decimal("1") if closes[-1] > sma else Decimal("0")
        contribution = TargetContribution(
            instrument_id=instrument_id,
            sleeve=SMOKE_IDENTITY.sleeve,
            strategy_id=SMOKE_IDENTITY.strategy_id,
            strategy_version=SMOKE_IDENTITY.strategy_version,
            target_weight=weight,
        )
        return StrategyEvaluation(
            status=StrategyEvaluationStatus.TARGETS,
            contributions=(contribution,),
        )


class StockRelativeStrengthSmokeStrategy:
    """Smoke strategy: rank the current universe cohort by the 4-session
    close return (T included) and TARGET the top 2 at an equal 0.5 weight in
    the SATELLITE sleeve. A held instrument that falls out of the top 2 gets
    an explicit zero-weight exit target; a held instrument still selected is
    re-addressed at the equal weight. Fewer than ``top_n`` rankable
    instruments (at least 5 closes) is a typed ``INSUFFICIENT_HISTORY``
    no-decision, never an implicit cash target.

    It owns no execution, accounting, data access, or state; it is a seam
    proof only and must never enter canonical Basic/OOS.
    """

    @property
    def identity(self) -> StrategyIdentity:
        return STOCK_SMOKE_IDENTITY

    def evaluate(
        self, context: DecisionContext, universe: UniverseView
    ) -> StrategyEvaluation:
        required = STOCK_SMOKE_IDENTITY.required_history_sessions
        top_n = int(STOCK_SMOKE_IDENTITY.parameters["top_n"])
        equal_weight = Decimal(STOCK_SMOKE_IDENTITY.parameters["equal_weight"])
        ranked: list[tuple[Decimal, InstrumentId]] = []
        for instrument_id in universe.instrument_ids:
            closes = tuple(bar.close for bar in context.bars_for(instrument_id))
            if len(closes) < required:
                continue
            base = closes[-required]
            ranked.append(((closes[-1] - base) / base, instrument_id))
        if len(ranked) < top_n:
            return StrategyEvaluation(
                status=StrategyEvaluationStatus.NO_DECISION,
                contributions=(),
                reason_codes=(REASON_INSUFFICIENT_HISTORY,),
            )
        ranked.sort(key=lambda item: (-item[0], item[1]))
        selected = [instrument_id for _, instrument_id in ranked[:top_n]]
        held = {
            position.instrument_id
            for position in context.positions
            if position.total_quantity > 0
        }
        contributions = [
            TargetContribution(
                instrument_id=instrument_id,
                sleeve=STOCK_SMOKE_IDENTITY.sleeve,
                strategy_id=STOCK_SMOKE_IDENTITY.strategy_id,
                strategy_version=STOCK_SMOKE_IDENTITY.strategy_version,
                target_weight=equal_weight,
            )
            for instrument_id in selected
        ]
        contributions.extend(
            TargetContribution(
                instrument_id=instrument_id,
                sleeve=STOCK_SMOKE_IDENTITY.sleeve,
                strategy_id=STOCK_SMOKE_IDENTITY.strategy_id,
                strategy_version=STOCK_SMOKE_IDENTITY.strategy_version,
                target_weight=Decimal("0"),
            )
            for instrument_id in sorted(held.difference(selected))
        )
        return StrategyEvaluation(
            status=StrategyEvaluationStatus.TARGETS,
            contributions=tuple(contributions),
        )
