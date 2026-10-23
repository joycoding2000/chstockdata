"""Canonical ETF relative-momentum strategy (M1 seed candidate).

Rule (pre-registered in
``research/candidates/m1-etf-relative-momentum-v1.json``): on the last open
session of each month, rank every universe instrument that has at least
``N`` known closes by its trailing N-close return ``close_T / close_{T-N+1}
- 1`` and target the top-1 at the full CORE weight. Ties break by canonical
``InstrumentId``. When a ``trend_gate_sma_sessions`` parameter is declared,
the selected top-1 must additionally close above its own G-session simple
moving average, otherwise the strategy targets an explicit cash exit (a
zero-weight target for the top-1 and every held instrument). Held
instruments outside the selection receive an explicit zero-weight exit.
Fewer than one rankable instrument is a typed ``INSUFFICIENT_HISTORY``
no-decision; a session outside the month-end schedule is a typed
``NOT_DECISION_SESSION`` no-decision.

The strategy owns no execution, accounting, data access, or state; the M0
kernel owns sizing at T close, T+1 open execution, fees, lot, settlement,
tradability, corporate actions, and accounting.
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
    InvalidStrategyIdentityError,
    StrategyEvaluation,
    StrategyEvaluationStatus,
    StrategyIdentity,
    canonical_parameters_digest,
)
from systematic_investing.research.strategies.etf_absolute_trend import int_parameter
from systematic_investing.research.universe import UniverseView

STRATEGY_ID: str = "etf-relative-momentum"
STRATEGY_VERSION: str = "v1"
_RETURN_KEY: str = "return_sessions"
_GATE_KEY: str = "trend_gate_sma_sessions"
_DIRECT_FACTORY_FALLBACK_DIGEST: str = "sha256:" + sha256(
    b"direct-factory-fallback:etf-relative-momentum:v1"
).hexdigest()


def _parse_parameters(parameters: Mapping[str, str]) -> tuple[int, int | None]:
    return_sessions = int_parameter(parameters, _RETURN_KEY)
    gate_raw = parameters.get(_GATE_KEY)
    if gate_raw is None:
        return return_sessions, None
    try:
        gate_sessions = int(gate_raw)
    except (TypeError, ValueError) as error:
        raise InvalidStrategyIdentityError(
            f"{_GATE_KEY} must be an integer, got {gate_raw!r}"
        ) from error
    if gate_sessions < 1:
        raise InvalidStrategyIdentityError(f"{_GATE_KEY} must be a positive integer")
    return return_sessions, gate_sessions


class RelativeMomentumStrategy:
    """Trailing N-close return rotation to the top-1 ETF, monthly."""

    def __init__(
        self,
        return_sessions: int,
        gate_sessions: int | None,
        decision_sessions: Sequence[date],
        *,
        implementation_digest: str | None = None,
    ) -> None:
        parameters: dict[str, str] = {_RETURN_KEY: str(return_sessions)}
        if gate_sessions is not None:
            parameters[_GATE_KEY] = str(gate_sessions)
        required_history = max(return_sessions, gate_sessions or 0)
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
            sleeve=SleeveId.CORE,
            required_history_sessions=required_history,
            decision_frequency=DECISION_FREQUENCY_MONTHLY_LAST_SESSION,
        )
        self._return_sessions = return_sessions
        self._gate_sessions = gate_sessions
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
        ranked: list[tuple[Decimal, InstrumentId]] = []
        closes_by_instrument: dict[InstrumentId, tuple[Decimal, ...]] = {}
        for instrument_id in universe.instrument_ids:
            closes = tuple(bar.close for bar in context.bars_for(instrument_id))
            if len(closes) < self._return_sessions:
                continue
            base = closes[-self._return_sessions]
            ranked.append(((closes[-1] - base) / base, instrument_id))
            closes_by_instrument[instrument_id] = closes
        if not ranked:
            return StrategyEvaluation(
                status=StrategyEvaluationStatus.NO_DECISION,
                contributions=(),
                reason_codes=(REASON_INSUFFICIENT_HISTORY,),
            )
        ranked.sort(key=lambda item: (-item[0], item[1]))
        top_instrument = ranked[0][1]
        top_closes = closes_by_instrument[top_instrument]
        gate_passed = True
        if self._gate_sessions is not None:
            if len(top_closes) < self._gate_sessions:
                return StrategyEvaluation(
                    status=StrategyEvaluationStatus.NO_DECISION,
                    contributions=(),
                    reason_codes=(REASON_INSUFFICIENT_HISTORY,),
                )
            gate_window = top_closes[-self._gate_sessions :]
            gate_sma = sum(gate_window, Decimal("0")) / Decimal(self._gate_sessions)
            gate_passed = top_closes[-1] > gate_sma
        held = {
            position.instrument_id
            for position in context.positions
            if position.total_quantity > 0
        }
        if not gate_passed:
            return StrategyEvaluation(
                status=StrategyEvaluationStatus.TARGETS,
                contributions=tuple(
                    TargetContribution(
                        instrument_id=instrument_id,
                        sleeve=self._identity.sleeve,
                        strategy_id=self._identity.strategy_id,
                        strategy_version=self._identity.strategy_version,
                        target_weight=Decimal("0"),
                    )
                    for instrument_id in sorted({top_instrument} | held)
                ),
            )
        contributions = [
            TargetContribution(
                instrument_id=top_instrument,
                sleeve=self._identity.sleeve,
                strategy_id=self._identity.strategy_id,
                strategy_version=self._identity.strategy_version,
                target_weight=Decimal("1"),
            )
        ]
        contributions.extend(
            TargetContribution(
                instrument_id=instrument_id,
                sleeve=self._identity.sleeve,
                strategy_id=self._identity.strategy_id,
                strategy_version=self._identity.strategy_version,
                target_weight=Decimal("0"),
            )
            for instrument_id in sorted(held - {top_instrument})
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
) -> RelativeMomentumStrategy:
    """Build the canonical strategy from one frozen parameter variant."""
    return_sessions, gate_sessions = _parse_parameters(parameters)
    return RelativeMomentumStrategy(
        return_sessions=return_sessions,
        gate_sessions=gate_sessions,
        decision_sessions=decision_sessions,
        implementation_digest=implementation_digest,
    )
