"""Canonical Stock relative-strength strategy (M1 seed candidate).

Rule (pre-registered in
``research/candidates/m1-stock-relative-strength-v1.json``): on the last
open session of each month, rank every instrument of the resolved annual PIT
cohort that has at least ``return_sessions`` known closes by its trailing
N-close return ``close_T / close_{T-N+1} - 1``, and target the first
``top_n`` names at equal weight ``1/top_n`` each. Ties break by canonical
``InstrumentId``. Every held instrument outside the picks receives an
explicit zero-weight exit. Fewer than one rankable cohort instrument is a
typed ``INSUFFICIENT_HISTORY`` no-decision; a session outside the month-end
schedule is a typed ``NOT_DECISION_SESSION`` no-decision.

The strategy observes only the T-known ``DecisionContext`` and the resolved
cohort view; it owns no execution, accounting, data access, or state. The M0
kernel owns sizing at T close, T+1 open execution, fees, lots, T+1
settlement, stamp tax, tradability, corporate actions, and accounting.
"""

from collections.abc import Mapping, Sequence
from datetime import date
from decimal import Decimal
from hashlib import sha256

from systematic_investing.backtest.engine import DecisionContext
from systematic_investing.domain.identifiers import InstrumentId, SleeveId
from systematic_investing.domain.portfolio import TargetContribution
from systematic_investing.research.contracts import (
    DECISION_FREQUENCY_MONTHLY_LAST_SESSION,
    REASON_INSUFFICIENT_HISTORY,
    REASON_NOT_DECISION_SESSION,
    StrategyEvaluation,
    StrategyEvaluationStatus,
    StrategyIdentity,
    canonical_parameters_digest,
)
from systematic_investing.research.strategies.etf_absolute_trend import int_parameter
from systematic_investing.research.universe import UniverseView

STRATEGY_ID: str = "stock-relative-strength"
STRATEGY_VERSION: str = "v1"
_RETURN_KEY: str = "return_sessions"
_TOP_N_KEY: str = "top_n"
_DIRECT_FACTORY_FALLBACK_DIGEST: str = "sha256:" + sha256(
    b"direct-factory-fallback:stock-relative-strength:v1"
).hexdigest()


def _parse_parameters(parameters: Mapping[str, str]) -> tuple[int, int]:
    return_sessions = int_parameter(parameters, _RETURN_KEY)
    top_n = int_parameter(parameters, _TOP_N_KEY)
    return return_sessions, top_n


def _closes_by_instrument(
    context: DecisionContext, universe: UniverseView
) -> dict[InstrumentId, tuple[Decimal, ...]]:
    """T-known close series per cohort member, oldest session first.

    The context carries every known bar; indexing is restricted to the
    resolved cohort and sorted by session, so neither context bar order nor
    input ordering can change a decision.
    """
    members = set(universe.instrument_ids)
    collected: dict[InstrumentId, list[tuple[date, Decimal]]] = {}
    for bar in context.bars:
        if bar.instrument_id in members:
            collected.setdefault(bar.instrument_id, []).append(
                (bar.session_date, bar.close)
            )
    return {
        instrument_id: tuple(
            close
            for _session_date, close in sorted(series, key=lambda item: item[0])
        )
        for instrument_id, series in collected.items()
    }


class StockRelativeStrengthStrategy:
    """Trailing N-close return top-N equal weight, monthly, annual cohort."""

    def __init__(
        self,
        return_sessions: int,
        top_n: int,
        decision_sessions: Sequence[date],
        *,
        implementation_digest: str | None = None,
    ) -> None:
        parameters: dict[str, str] = {
            _RETURN_KEY: str(return_sessions),
            _TOP_N_KEY: str(top_n),
        }
        self._identity = StrategyIdentity(
            strategy_id=STRATEGY_ID,
            strategy_version=STRATEGY_VERSION,
            implementation_digest=(
                _DIRECT_FACTORY_FALLBACK_DIGEST
                if implementation_digest is None
                else implementation_digest
            ),
            parameters=parameters,
            parameters_digest=canonical_parameters_digest(parameters),
            sleeve=SleeveId.SATELLITE,
            required_history_sessions=return_sessions,
            decision_frequency=DECISION_FREQUENCY_MONTHLY_LAST_SESSION,
        )
        self._return_sessions = return_sessions
        self._top_n = top_n
        self._decision_sessions = frozenset(decision_sessions)

    @property
    def identity(self) -> StrategyIdentity:
        return self._identity

    def evaluate(
        self, context: DecisionContext, universe: UniverseView
    ) -> StrategyEvaluation:
        if context.session_date not in self._decision_sessions:
            return StrategyEvaluation(
                status=StrategyEvaluationStatus.NO_DECISION,
                contributions=(),
                reason_codes=(REASON_NOT_DECISION_SESSION,),
            )
        closes_by_instrument = _closes_by_instrument(context, universe)
        ranked: list[tuple[Decimal, InstrumentId]] = []
        for instrument_id in universe.instrument_ids:
            closes = closes_by_instrument.get(instrument_id, ())
            if len(closes) < self._return_sessions:
                continue
            base = closes[-self._return_sessions]
            ranked.append(((closes[-1] - base) / base, instrument_id))
        if not ranked:
            return StrategyEvaluation(
                status=StrategyEvaluationStatus.NO_DECISION,
                contributions=(),
                reason_codes=(REASON_INSUFFICIENT_HISTORY,),
            )
        ranked.sort(key=lambda item: (-item[0], item[1]))
        picks = [instrument_id for _return, instrument_id in ranked[: self._top_n]]
        weight = Decimal("1") / Decimal(self._top_n)
        held = {
            position.instrument_id
            for position in context.positions
            if position.total_quantity > 0
        }
        contributions = [
            TargetContribution(
                instrument_id=instrument_id,
                sleeve=self._identity.sleeve,
                strategy_id=self._identity.strategy_id,
                strategy_version=self._identity.strategy_version,
                target_weight=weight,
            )
            for instrument_id in picks
        ]
        contributions.extend(
            TargetContribution(
                instrument_id=instrument_id,
                sleeve=self._identity.sleeve,
                strategy_id=self._identity.strategy_id,
                strategy_version=self._identity.strategy_version,
                target_weight=Decimal("0"),
            )
            for instrument_id in sorted(held - set(picks))
        )
        return StrategyEvaluation(
            status=StrategyEvaluationStatus.TARGETS,
            contributions=tuple(contributions),
        )


def build_strategy(
    parameters: Mapping[str, str],
    decision_sessions: Sequence[date],
    *,
    implementation_digest: str | None = None,
) -> StockRelativeStrengthStrategy:
    """Build the canonical strategy from one frozen parameter variant."""
    return_sessions, top_n = _parse_parameters(parameters)
    return StockRelativeStrengthStrategy(
        return_sessions=return_sessions,
        top_n=top_n,
        decision_sessions=decision_sessions,
        implementation_digest=implementation_digest,
    )
