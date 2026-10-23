"""Canonical ETF absolute-trend strategy (M1 seed candidate).

Rule (pre-registered in ``research/candidates/m1-etf-absolute-trend-v1.json``):
on the last open session of each month, if the instrument has at least ``N``
known closes, compare the T close with the N-session simple moving average
(T included): a close above the average targets the full weight in the CORE
sleeve; an at-or-below close targets an explicit zero weight (addressed cash
exit, never a silent no-decision). Fewer than ``N`` closes is a typed
``INSUFFICIENT_HISTORY`` no-decision; a session outside the month-end
schedule is a typed ``NOT_DECISION_SESSION`` no-decision.

The strategy owns no execution, accounting, data access, or state; the M0
kernel owns sizing at T close, T+1 open execution, fees, lot, settlement,
tradability, corporate actions, and accounting.
"""

from collections.abc import Mapping, Sequence
from datetime import date
from decimal import Decimal
from hashlib import sha256

from systematic_investing.backtest.engine import DecisionContext
from systematic_investing.domain.identifiers import SleeveId
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
from systematic_investing.research.universe import UniverseView

STRATEGY_ID: str = "etf-absolute-trend"
STRATEGY_VERSION: str = "v1"
_SMA_KEY: str = "sma_sessions"
_DIRECT_FACTORY_FALLBACK_DIGEST: str = "sha256:" + sha256(
    b"direct-factory-fallback:etf-absolute-trend:v1"
).hexdigest()


class AbsoluteTrendStrategy:
    """Close versus N-session SMA at month ends, full weight or cash."""

    def __init__(
        self,
        sma_sessions: int,
        decision_sessions: Sequence[date],
        *,
        implementation_digest: str | None = None,
    ) -> None:
        if (
            not isinstance(sma_sessions, int)
            or isinstance(sma_sessions, bool)
            or sma_sessions < 1
        ):
            raise InvalidStrategyIdentityError("sma_sessions must be a positive integer")
        parameters: dict[str, str] = {_SMA_KEY: str(sma_sessions)}
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
            required_history_sessions=sma_sessions,
            decision_frequency=DECISION_FREQUENCY_MONTHLY_LAST_SESSION,
        )
        self._sma_sessions = sma_sessions
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
        instrument_id = universe.instrument_ids[0]
        closes = tuple(bar.close for bar in context.bars_for(instrument_id))
        if len(closes) < self._sma_sessions:
            return StrategyEvaluation(
                status=StrategyEvaluationStatus.NO_DECISION,
                contributions=(),
                reason_codes=(REASON_INSUFFICIENT_HISTORY,),
            )
        window = closes[-self._sma_sessions :]
        sma = sum(window, Decimal("0")) / Decimal(self._sma_sessions)
        weight = Decimal("1") if closes[-1] > sma else Decimal("0")
        return StrategyEvaluation(
            status=StrategyEvaluationStatus.TARGETS,
            contributions=(
                TargetContribution(
                    instrument_id=instrument_id,
                    sleeve=self._identity.sleeve,
                    strategy_id=self._identity.strategy_id,
                    strategy_version=self._identity.strategy_version,
                    target_weight=weight,
                ),
            ),
        )


def build_strategy(
    parameters: Mapping[str, str],
    decision_sessions: Sequence[date],
    *,
    implementation_digest: str | None = None,
) -> AbsoluteTrendStrategy:
    """Build the canonical strategy from one frozen parameter variant."""
    return AbsoluteTrendStrategy(
        sma_sessions=int_parameter(parameters, _SMA_KEY),
        decision_sessions=decision_sessions,
        implementation_digest=implementation_digest,
    )


def int_parameter(parameters: Mapping[str, str], key: str) -> int:
    """Parse one required positive integer parameter."""
    if key not in parameters:
        raise InvalidStrategyIdentityError(f"missing required parameter {key}")
    try:
        value = int(parameters[key])
    except (TypeError, ValueError) as error:
        raise InvalidStrategyIdentityError(
            f"{key} must be an integer, got {parameters[key]!r}"
        ) from error
    if value < 1:
        raise InvalidStrategyIdentityError(f"{key} must be a positive integer")
    return value
