"""Canonical Stock breakout strategy (M1 seed candidate).

Rule (pre-registered in ``research/candidates/m1-stock-breakout-v1.json``):
on the last open session of each month, a resolved annual PIT cohort
instrument breaks out when it has at least ``breakout_sessions + 1`` known
sessions and its T close is strictly above the highest high of the
``breakout_sessions`` sessions strictly before T — the decision session is
never inside its own channel window. Breakout instruments are ranked by the
descending median amount of their trailing ``liquidity_sessions`` known
sessions with canonical ``InstrumentId`` tie-breaks, and the first ``top_n``
are targeted at equal weight ``1/top_n`` each. Every held instrument outside
the picks receives an explicit zero-weight exit. When history exists but no
instrument breaks out, held instruments are exited and an empty sleeve
stands in cash through the typed ``NO_ELIGIBLE_BREAKOUT`` no-decision (only
when nothing is held); an instrument without enough history is never
rankable, and a session outside the month-end schedule is a typed
``NOT_DECISION_SESSION`` no-decision.

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
    InvalidStrategyIdentityError,
    StrategyEvaluation,
    StrategyEvaluationStatus,
    StrategyIdentity,
    canonical_parameters_digest,
)
from systematic_investing.research.strategies.etf_absolute_trend import int_parameter
from systematic_investing.research.universe import UniverseView

STRATEGY_ID: str = "stock-breakout"
STRATEGY_VERSION: str = "v1"
_BREAKOUT_KEY: str = "breakout_sessions"
_LIQUIDITY_KEY: str = "liquidity_sessions"
_TOP_N_KEY: str = "top_n"
REASON_NO_ELIGIBLE_BREAKOUT: str = "NO_ELIGIBLE_BREAKOUT"
_DIRECT_FACTORY_FALLBACK_DIGEST: str = "sha256:" + sha256(
    b"direct-factory-fallback:stock-breakout:v1"
).hexdigest()


def _parse_parameters(parameters: Mapping[str, str]) -> tuple[int, int, int]:
    breakout_sessions = int_parameter(parameters, _BREAKOUT_KEY)
    liquidity_sessions = int_parameter(parameters, _LIQUIDITY_KEY)
    top_n = int_parameter(parameters, _TOP_N_KEY)
    if liquidity_sessions > breakout_sessions:
        raise InvalidStrategyIdentityError(
            f"{_LIQUIDITY_KEY} must not exceed {_BREAKOUT_KEY}"
        )
    return breakout_sessions, liquidity_sessions, top_n


def _median(amounts: Sequence[Decimal]) -> Decimal:
    ordered = sorted(amounts)
    middle = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / Decimal("2")


def _series_by_instrument(
    context: DecisionContext, universe: UniverseView
) -> dict[InstrumentId, tuple[tuple[Decimal, ...], tuple[Decimal, ...], tuple[Decimal, ...]]]:
    """T-known ``(closes, highs, amounts)`` per cohort member, oldest first.

    The context carries every known bar; indexing is restricted to the
    resolved cohort and sorted by session, so neither context bar order nor
    input ordering can change a decision.
    """
    members = set(universe.instrument_ids)
    collected: dict[
        InstrumentId, list[tuple[date, Decimal, Decimal, Decimal]]
    ] = {}
    for bar in context.bars:
        if bar.instrument_id in members:
            collected.setdefault(bar.instrument_id, []).append(
                (bar.session_date, bar.close, bar.high, bar.amount)
            )
    series: dict[
        InstrumentId, tuple[tuple[Decimal, ...], tuple[Decimal, ...], tuple[Decimal, ...]]
    ] = {}
    for instrument_id, records in collected.items():
        ordered = sorted(records, key=lambda item: item[0])
        series[instrument_id] = (
            tuple(record[1] for record in ordered),
            tuple(record[2] for record in ordered),
            tuple(record[3] for record in ordered),
        )
    return series


class StockBreakoutStrategy:
    """New N-session-high breakout, liquidity-ranked top-N equal weight."""

    def __init__(
        self,
        breakout_sessions: int,
        liquidity_sessions: int,
        top_n: int,
        decision_sessions: Sequence[date],
        *,
        implementation_digest: str | None = None,
    ) -> None:
        parameters: dict[str, str] = {
            _BREAKOUT_KEY: str(breakout_sessions),
            _LIQUIDITY_KEY: str(liquidity_sessions),
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
            required_history_sessions=breakout_sessions + 1,
            decision_frequency=DECISION_FREQUENCY_MONTHLY_LAST_SESSION,
        )
        self._breakout_sessions = breakout_sessions
        self._liquidity_sessions = liquidity_sessions
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
        series = _series_by_instrument(context, universe)
        ranked: list[tuple[Decimal, InstrumentId]] = []
        any_rankable = False
        for instrument_id in universe.instrument_ids:
            closes, highs, amounts = series.get(
                instrument_id, ((), (), ())
            )
            if len(closes) < self._breakout_sessions + 1:
                continue
            any_rankable = True
            window = highs[-(self._breakout_sessions + 1) : -1]
            if closes[-1] > max(window):
                liquidity = amounts[-self._liquidity_sessions :]
                ranked.append((_median(liquidity), instrument_id))
        if not any_rankable:
            return StrategyEvaluation(
                status=StrategyEvaluationStatus.NO_DECISION,
                contributions=(),
                reason_codes=(REASON_INSUFFICIENT_HISTORY,),
            )
        ranked.sort(key=lambda item: (-item[0], item[1]))
        picks = [instrument_id for _liquidity, instrument_id in ranked[: self._top_n]]
        held = {
            position.instrument_id
            for position in context.positions
            if position.total_quantity > 0
        }
        if not picks and not held:
            return StrategyEvaluation(
                status=StrategyEvaluationStatus.NO_DECISION,
                contributions=(),
                reason_codes=(REASON_NO_ELIGIBLE_BREAKOUT,),
            )
        weight = Decimal("1") / Decimal(self._top_n)
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
) -> StockBreakoutStrategy:
    """Build the canonical strategy from one frozen parameter variant."""
    breakout_sessions, liquidity_sessions, top_n = _parse_parameters(parameters)
    return StockBreakoutStrategy(
        breakout_sessions=breakout_sessions,
        liquidity_sessions=liquidity_sessions,
        top_n=top_n,
        decision_sessions=decision_sessions,
        implementation_digest=implementation_digest,
    )
