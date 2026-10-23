"""Deterministic daily-bar backtest kernel (M0).

The kernel walks the open sessions of a frozen canonical input set and applies
the documented ten-step daily event order:

1. apply effective corporate actions to holdings and cash; invalidate affected
   pending executions when an intervening action changes quantity;
2. activate surviving plans created from the previous close decision;
3. evaluate listing, suspension, price-limit, and other tradability facts;
4. derive slippage-adjusted, tick-rounded execution prices and applicable
   fees; evaluate affordability globally and submit legal complete lots;
5. fill the submitted all-or-none order with the next-bar execution model;
6. post fills, fees, taxes, cash, and holdings movements;
7. value the account at the session close using unadjusted executable prices;
8. expose data available through the session decision cutoff;
9. accept the predetermined target for the next session and create a pending
   plan;
10. persist the session ledger/NAV/checksum records.

The kernel implements no investment strategy. A ``TargetSource`` supplies
predetermined theoretical target contributions (``None`` means the session
addresses no target). Sizing happens only from the finalized T close and is
never revised; activation at T+1 prices the locked plan with the declared
``NEXT_SESSION_OPEN`` model and one global affordability pass. A
quantity-changing corporate action effective between the decision and
activation invalidates the affected pending execution with
``CORPORATE_ACTION_REPLAN_REQUIRED``; no rescaled substitute is synthesized
and the locked theoretical target is never mutated.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, tzinfo
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
from typing import Protocol

from systematic_investing import DEFAULT_INITIAL_CAPITAL
from systematic_investing.backtest.accounting import (
    AccountingSemantics,
    apply_corporate_action,
    mark_to_market,
    nav_point_of,
)
from systematic_investing.backtest.execution import (
    ActivationResult,
    ExecutionModel,
    PendingPlan,
    activate_pending_plans,
    pending_order_for,
)
from systematic_investing.domain.execution import (
    AccountFeeConfig,
    BrokerFeeProfile,
    Fill,
    Order,
    Rejection,
    compute_fees,
)
from systematic_investing.domain.identifiers import InstrumentId, require_session_date
from systematic_investing.domain.ledger import (
    CashLedgerEntry,
    HoldingsLedgerEntry,
    IncompleteValuationReason,
    NavPoint,
    PortfolioSnapshot,
    Position,
    ValuationStatus,
)
from systematic_investing.domain.market import (
    CorporateAction,
    CorporateActionKind,
    DailyBar,
    MarketCalendar,
    TradabilityStatus,
    TradeSide,
    UnknownSessionError,
)
from systematic_investing.domain.money import Money
from systematic_investing.domain.portfolio import TargetContribution, TheoreticalTargetPortfolio
from systematic_investing.instrument_master.models import (
    UnknownInstrumentError,
    UnknownRuleError,
)
from systematic_investing.instrument_master.repository import InstrumentMaster
from systematic_investing.portfolio.allocation import (
    CurrentHolding,
    CurrentPortfolio,
    ExecutableTargetPortfolio,
    FeeEstimate,
    build_executable_target,
)
from systematic_investing.portfolio.validation import (
    TargetNotCompleteError,
    validate_target_completeness,
)
from systematic_investing.risk.decisions import (
    RiskApprovedTargetPortfolio,
    RiskTransformation,
    RiskTransformationStatus,
)

IDENTITY_RISK_COMPOSITION_VERSION = "m0-identity-risk-1"


class EngineError(Exception):
    """Base class for deterministic engine contract errors."""


class InvalidEngineInputError(EngineError):
    """Raised when frozen engine inputs are inconsistent or ambiguous."""


class InvalidDecisionContextError(EngineError):
    """Raised when a decision context would expose lookahead data."""


class FutureDataAccessError(EngineError):
    """Raised when a target source requests a future slice loudly."""


class UnknownFactError(EngineError):
    """Raised when a target source requests a fact outside the known slice."""


class AmbiguousMarketFactError(EngineError):
    """Raised when duplicate canonical facts make a session ambiguous."""


def _require_aware(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise InvalidEngineInputError(
            f"{field_name} must be a timezone-aware datetime, got {value!r}"
        )
    return value


@dataclass(frozen=True)
class EngineClock:
    """Injected session clock: explicit local cutoffs, never wall-clock time."""

    timezone: tzinfo = UTC
    activation_local_time: time = time(9, 15)
    execution_local_time: time = time(9, 30)
    decision_local_time: time = time(15, 30)

    def activation_cutoff(self, session_date: date) -> datetime:
        """Knowledge cutoff for facts needed to activate pending plans."""
        return datetime.combine(
            session_date, self.activation_local_time, tzinfo=self.timezone
        )

    def execution_at(self, session_date: date) -> datetime:
        """Recording time of execution fills and their ledger entries."""
        return datetime.combine(
            session_date, self.execution_local_time, tzinfo=self.timezone
        )

    def decision_cutoff(self, session_date: date) -> datetime:
        """Knowledge cutoff of the T-close decision and its data slice."""
        return datetime.combine(
            session_date, self.decision_local_time, tzinfo=self.timezone
        )


class DecisionBlockReason(StrEnum):
    """Why a session produced no executable target."""

    INCOMPLETE_VALUATION = "INCOMPLETE_VALUATION"
    NO_NEXT_SESSION = "NO_NEXT_SESSION"
    MISSING_INSTRUMENT_RULES = "MISSING_INSTRUMENT_RULES"
    MISSING_T_CLOSE_PRICE = "MISSING_T_CLOSE_PRICE"
    RISK_BLOCKED = "RISK_BLOCKED"
    TARGET_INCOMPLETE = "TARGET_INCOMPLETE"


@dataclass(frozen=True)
class DecisionContext:
    """The exact T-known data slice a target source may observe.

    Only facts whose ``information_available_at`` is no later than the
    decision cutoff and whose session is at or before the decision session are
    present. Requesting a future slice fails loudly; requesting an absent fact
    fails as an unknown fact rather than a fabricated value. ``retrieved_at``
    never substitutes for information availability, and ``UNKNOWN``
    availability is never treated as known.
    """

    session_date: date
    decision_for_trade_date: date
    information_cutoff: datetime
    cash: Money
    valuation_equity: Money
    positions: tuple[Position, ...]
    bars: tuple[DailyBar, ...] = ()
    tradability: tuple[TradabilityStatus, ...] = ()
    corporate_actions: tuple[CorporateAction, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "positions", tuple(self.positions))
        object.__setattr__(self, "bars", tuple(self.bars))
        object.__setattr__(self, "tradability", tuple(self.tradability))
        object.__setattr__(self, "corporate_actions", tuple(self.corporate_actions))
        require_session_date(self.session_date)
        require_session_date(self.decision_for_trade_date)
        _require_aware(self.information_cutoff, "information_cutoff")
        for bar in self.bars:
            if bar.session_date > self.session_date:
                raise InvalidDecisionContextError(
                    f"bar {bar.instrument_id} on {bar.session_date} is after the "
                    f"decision session {self.session_date}"
                )
            if bar.availability.information_known_at(self.information_cutoff) is not True:
                raise InvalidDecisionContextError(
                    f"bar {bar.instrument_id} on {bar.session_date} was not knowable at "
                    f"the decision cutoff {self.information_cutoff.isoformat()}"
                )
        for record in self.tradability:
            if record.session_date > self.session_date:
                raise InvalidDecisionContextError(
                    f"tradability for {record.instrument_id} on {record.session_date} "
                    "is after the decision session"
                )
            if record.availability.information_known_at(self.information_cutoff) is not True:
                raise InvalidDecisionContextError(
                    f"tradability for {record.instrument_id} on {record.session_date} "
                    "was not knowable at the decision cutoff"
                )
        for action in self.corporate_actions:
            if action.ex_date > self.session_date:
                raise InvalidDecisionContextError(
                    f"corporate action {action.action_id} is effective after the "
                    "decision session"
                )
            if action.availability.information_known_at(self.information_cutoff) is not True:
                raise InvalidDecisionContextError(
                    f"corporate action {action.action_id} was not knowable at the "
                    "decision cutoff"
                )

    @property
    def t_close_prices(self) -> dict[InstrumentId, Decimal]:
        """Finalized T-close prices known at the decision cutoff."""
        prices = {
            bar.instrument_id: bar.close
            for bar in self.bars
            if bar.session_date == self.session_date
        }
        return dict(sorted(prices.items()))

    def bars_for(self, instrument_id: InstrumentId) -> tuple[DailyBar, ...]:
        """All known bars for one instrument, oldest session first."""
        if not isinstance(instrument_id, InstrumentId):
            raise UnknownFactError(f"instrument_id must be an InstrumentId, got {instrument_id!r}")
        return tuple(
            sorted(
                (bar for bar in self.bars if bar.instrument_id == instrument_id),
                key=lambda bar: bar.session_date,
            )
        )

    def require_bar(self, instrument_id: InstrumentId, session_date: date) -> DailyBar:
        """Return one known bar or fail loudly; future sessions are refused."""
        require_session_date(session_date)
        if session_date > self.session_date:
            raise FutureDataAccessError(
                f"bar {instrument_id} on {session_date} is after the decision session "
                f"{self.session_date}"
            )
        for bar in self.bars:
            if bar.instrument_id == instrument_id and bar.session_date == session_date:
                return bar
        raise UnknownFactError(
            f"bar {instrument_id} on {session_date} is not in the known decision slice"
        )


class TargetSource(Protocol):
    """Predetermined target contributor; never an investment strategy."""

    def contributions_for(
        self, context: DecisionContext
    ) -> tuple[TargetContribution, ...] | None: ...


@dataclass(frozen=True)
class CorporateActionEffect:
    """One corporate action applied to the account at the start of a session."""

    action_id: str
    instrument_id: InstrumentId
    action_kind: CorporateActionKind
    cash_delta: Money
    quantity_delta: int
    cash_entry: CashLedgerEntry | None
    holdings_entry: HoldingsLedgerEntry | None


@dataclass(frozen=True)
class SessionResult:
    """One session of the ten-step event order, with its normalized evidence."""

    session_date: date
    corporate_action_effects: tuple[CorporateActionEffect, ...]
    invalidated_orders: tuple[Order, ...]
    activation: ActivationResult
    snapshot: PortfolioSnapshot
    nav: NavPoint
    target: TheoreticalTargetPortfolio | None
    plans: tuple[PendingPlan, ...]
    decision_digest: str | None
    decision_blocked_reason: DecisionBlockReason | None


@dataclass(frozen=True)
class BacktestResult:
    """Deterministic kernel output over the requested session range."""

    sessions: tuple[SessionResult, ...]
    cash: Money
    positions: tuple[Position, ...]

    def session(self, session_date: date) -> SessionResult:
        require_session_date(session_date)
        for record in self.sessions:
            if record.session_date == session_date:
                return record
        raise KeyError(f"no session record for {session_date}")

    @property
    def orders(self) -> tuple[Order, ...]:
        collected: list[Order] = []
        for record in self.sessions:
            collected.extend(record.invalidated_orders)
            collected.extend(record.activation.orders)
        return tuple(collected)

    @property
    def fills(self) -> tuple[Fill, ...]:
        collected: list[Fill] = []
        for record in self.sessions:
            collected.extend(record.activation.fills)
        return tuple(collected)

    @property
    def rejections(self) -> tuple[Rejection, ...]:
        collected: list[Rejection] = []
        for record in self.sessions:
            collected.extend(record.activation.rejections)
        return tuple(collected)

    @property
    def cash_entries(self) -> tuple[CashLedgerEntry, ...]:
        collected: list[CashLedgerEntry] = []
        for record in self.sessions:
            for effect in record.corporate_action_effects:
                if effect.cash_entry is not None:
                    collected.append(effect.cash_entry)
            collected.extend(record.activation.cash_entries)
        return tuple(collected)

    @property
    def holdings_entries(self) -> tuple[HoldingsLedgerEntry, ...]:
        collected: list[HoldingsLedgerEntry] = []
        for record in self.sessions:
            for effect in record.corporate_action_effects:
                if effect.holdings_entry is not None:
                    collected.append(effect.holdings_entry)
            collected.extend(record.activation.holdings_entries)
        return tuple(collected)

    def content_digest(self) -> str:
        lines = ["backtest_result_v1"]
        for record in self.sessions:
            lines.extend(_session_digest_lines(record))
        lines.append(f"final_cash={self.cash.amount},{self.cash.currency}")
        for position in sorted(self.positions, key=lambda item: item.instrument_id):
            lines.append(
                f"final_position={position.instrument_id},{position.total_quantity},"
                f"{position.average_cost}"
            )
            for lot in sorted(
                position.lots,
                key=lambda item: (
                    item.acquired_session,
                    item.sellable_from,
                    item.acquisition_price,
                    item.quantity,
                ),
            ):
                lines.append(
                    f"final_lot={position.instrument_id},{lot.quantity},"
                    f"{lot.acquired_session.isoformat()},{lot.sellable_from.isoformat()},"
                    f"{lot.acquisition_price}"
                )
        return sha256("\n".join(lines).encode("utf-8")).hexdigest()


def _corporate_action_order(action: CorporateAction) -> tuple[date, int, str]:
    """Order same-session actions: cash first, then share-changing records."""
    return (
        action.ex_date,
        0 if action.action_kind is CorporateActionKind.CASH_DIVIDEND else 1,
        action.action_id,
    )


def _session_digest_lines(record: SessionResult) -> list[str]:
    lines = [f"session={record.session_date.isoformat()}"]
    for effect in sorted(record.corporate_action_effects, key=lambda item: item.action_id):
        lines.append(
            f"effect={effect.action_id},{effect.instrument_id},{effect.action_kind.value},"
            f"{effect.cash_delta.amount},{effect.quantity_delta}"
        )
    for order in sorted(record.invalidated_orders, key=lambda item: item.order_id):
        lines.append(
            f"invalidated={order.order_id},{order.instrument_id},{order.side.value},"
            f"{order.planned_quantity},{order.submitted_quantity},"
            f"{order.execution_session.isoformat()},"
            f"{order.sizing_reference_price_basis.value},{order.sizing_reference_price},"
            f"{order.fill_price_model},{order.target_id},{order.target_revision},"
            f"{order.decision_for_trade_date.isoformat()},{order.status.value},"
            f"{','.join(order.reason_codes)}"
        )
    for order in sorted(record.activation.orders, key=lambda item: item.order_id):
        lines.append(
            f"order={order.order_id},{order.instrument_id},{order.side.value},"
            f"{order.status.value},{order.planned_quantity},{order.submitted_quantity},"
            f"{order.execution_session.isoformat()},"
            f"{order.sizing_reference_price_basis.value},{order.sizing_reference_price},"
            f"{order.fill_price_model},{order.target_id},{order.target_revision},"
            f"{order.decision_for_trade_date.isoformat()},{','.join(order.reason_codes)}"
        )
    for fill in sorted(record.activation.fills, key=lambda item: item.fill_id):
        lines.append(
            f"fill={fill.fill_id},{fill.order_id},{fill.instrument_id},{fill.side.value},"
            f"{fill.quantity},{fill.fill_price},"
            f"{fill.reference_open},{fill.fees.commission.amount},"
            f"{fill.fees.minimum_commission_adjustment.amount},{fill.fees.stamp_tax.amount},"
            f"{fill.fees.transfer_fee.amount},{fill.session_date.isoformat()},{fill.source}"
        )
    for rejection in sorted(record.activation.rejections, key=lambda item: item.rejection_id):
        lines.append(
            f"rejection={rejection.rejection_id},{rejection.order_id},"
            f"{rejection.instrument_id},{rejection.side.value},{rejection.code.value},"
            f"{rejection.message},{rejection.session_date.isoformat()},{rejection.observed}"
        )
    for entry in sorted(record.activation.cash_entries, key=lambda item: item.entry_id):
        lines.append(
            f"cash={entry.entry_id},{entry.category.value},{entry.amount.amount},"
            f"{entry.amount.currency},{entry.session_date.isoformat()},"
            f"{entry.recorded_at.isoformat()},{entry.source_id}"
        )
    for entry in sorted(record.activation.holdings_entries, key=lambda item: item.entry_id):
        lines.append(
            f"holding={entry.entry_id},{entry.instrument_id},{entry.quantity_delta},"
            f"{entry.acquisition_session},{entry.sellable_from},{entry.source_id},"
            f"{entry.session_date.isoformat()},{entry.recorded_at.isoformat()}"
        )
    lines.append(f"activation_cash={record.activation.cash.amount},{record.activation.cash.currency}")
    for position in sorted(record.activation.positions, key=lambda item: item.instrument_id):
        for lot in sorted(
            position.lots,
            key=lambda item: (
                item.acquired_session,
                item.sellable_from,
                item.acquisition_price,
                item.quantity,
            ),
        ):
            lines.append(
                f"activation_lot={position.instrument_id},{lot.quantity},"
                f"{lot.acquired_session.isoformat()},{lot.sellable_from.isoformat()},"
                f"{lot.acquisition_price}"
            )
    lines.append(f"snapshot={record.snapshot.content_digest()}")
    lines.append(
        f"nav={record.nav.session_date.isoformat()},{record.nav.cash.amount},"
        f"{record.nav.cash.currency},{record.nav.market_value.amount},"
        f"{record.nav.market_value.currency},{record.nav.total_equity.amount},"
        f"{record.nav.total_equity.currency},{record.nav.nav},"
        f"{record.nav.valuation_status.value}"
    )
    for mark in sorted(record.nav.stale_marks, key=lambda item: item.instrument_id):
        lines.append(
            f"nav_stale={mark.instrument_id},{mark.marked_price},"
            f"{mark.last_valid_session.isoformat()},{mark.age_sessions}"
        )
    for reason in sorted(record.nav.incomplete_reasons, key=lambda item: item.value):
        lines.append(f"nav_incomplete={reason.value}")
    lines.append(
        f"target={record.target.content_digest if record.target is not None else 'NONE'}"
    )
    lines.append(f"decision={record.decision_digest or 'NONE'}")
    for plan in sorted(record.plans, key=lambda item: item.instrument_id):
        lines.append(
            f"plan={plan.instrument_id},{plan.side.value},{plan.order_quantity},"
            f"{plan.target_weight},{plan.current_weight},{plan.sizing_reference_price},"
            f"{plan.target_id},{plan.target_revision},"
            f"{plan.decision_for_trade_date.isoformat()}"
        )
    blocked = record.decision_blocked_reason.value if record.decision_blocked_reason else "NONE"
    lines.append(f"blocked={blocked}")
    return lines


def decision_digest(
    target: TheoreticalTargetPortfolio,
    executable: ExecutableTargetPortfolio | None,
    plans: tuple[PendingPlan, ...],
) -> str:
    """Normalized digest of the locked T-close decision and its pending orders."""
    lines = [
        "decision_v1",
        f"target={target.content_digest}",
        f"target_id={target.target_id}",
        f"revision={target.revision}",
        f"decision_for_trade_date={target.decision_for_trade_date.isoformat()}",
        f"valuation_equity={target.valuation_equity.amount}",
    ]
    if executable is not None:
        lines.append(f"residual_cash={executable.residual_cash.amount}")
        for position in executable.positions:
            lines.append(
                f"executable={position.instrument_id},{position.sleeve.value},"
                f"{position.executable_weight},{position.planned_quantity},"
                f"{','.join(reason.value for reason in position.reason_codes)}"
            )
    for plan in sorted(plans, key=lambda item: item.instrument_id):
        lines.append(
            f"plan={plan.instrument_id},{plan.sleeve.value},{plan.side.value},"
            f"{plan.order_quantity},{plan.target_weight},{plan.current_weight},"
            f"{plan.sizing_reference_price}"
        )
    return sha256("\n".join(lines).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class _MasterFeeEstimator:
    """Estimates separated market and broker fees for one session."""

    master: InstrumentMaster
    broker: BrokerFeeProfile
    session_date: date

    def estimate(
        self,
        instrument_id: InstrumentId,
        side: TradeSide,
        quantity: int,
        price: Decimal,
    ) -> FeeEstimate:
        rules = self.master.resolve_rules(instrument_id, self.session_date)
        fees = compute_fees(rules.market_fee_tax, self.broker, side, quantity, price)
        return FeeEstimate(
            market_fees=fees.stamp_tax + fees.transfer_fee,
            broker_fees=fees.commission + fees.minimum_commission_adjustment,
        )


@dataclass(frozen=True)
class _DecisionOutcome:
    target: TheoreticalTargetPortfolio | None
    plans: tuple[PendingPlan, ...]
    digest: str | None
    blocked_reason: DecisionBlockReason | None


@dataclass(frozen=True)
class _SessionOutcome:
    record: SessionResult
    cash: Money
    positions: tuple[Position, ...]
    pending: tuple[PendingPlan, ...]


class DailyBarEngine:
    """Frozen-input daily-bar kernel; deterministic, offline, strategy-free."""

    def __init__(
        self,
        *,
        calendar: MarketCalendar,
        clock: EngineClock,
        master: InstrumentMaster,
        account_fees: AccountFeeConfig,
        execution_model: ExecutionModel,
        accounting_semantics: AccountingSemantics = (
            AccountingSemantics.CURRENT_M0_ACCOUNTING_2
        ),
        bars: tuple[DailyBar, ...],
        tradability: tuple[TradabilityStatus, ...],
        corporate_actions: tuple[CorporateAction, ...],
        target_source: TargetSource,
        initial_cash: Money | None = None,
        initial_positions: tuple[Position, ...] = (),
        risk_transformation: RiskTransformation | None = None,
    ) -> None:
        if not isinstance(calendar, MarketCalendar):
            raise InvalidEngineInputError("calendar must be a MarketCalendar")
        if not isinstance(clock, EngineClock):
            raise InvalidEngineInputError("clock must be an EngineClock")
        if not isinstance(master, InstrumentMaster):
            raise InvalidEngineInputError("master must be an InstrumentMaster")
        if not isinstance(account_fees, AccountFeeConfig):
            raise InvalidEngineInputError("account_fees must be an AccountFeeConfig")
        if not isinstance(execution_model, ExecutionModel):
            raise InvalidEngineInputError("execution_model must be an ExecutionModel")
        if not isinstance(accounting_semantics, AccountingSemantics):
            raise InvalidEngineInputError(
                "accounting_semantics must be an AccountingSemantics"
            )
        cash = initial_cash if initial_cash is not None else Money(DEFAULT_INITIAL_CAPITAL)
        if not isinstance(cash, Money) or cash.amount < 0:
            raise InvalidEngineInputError("initial_cash must be non-negative Money")
        self._calendar = calendar
        self._clock = clock
        self._master = master
        self._account_fees = account_fees
        self._execution_model = execution_model
        self._accounting_semantics = accounting_semantics
        self._bars = tuple(sorted(bars, key=lambda bar: (bar.instrument_id, bar.session_date)))
        self._tradability = tuple(
            sorted(tradability, key=lambda record: (record.instrument_id, record.session_date))
        )
        self._corporate_actions = tuple(
            sorted(corporate_actions, key=lambda action: (action.action_id, action.ex_date))
        )
        self._target_source = target_source
        self._initial_cash = cash
        self._initial_positions = tuple(initial_positions)
        self._risk_transformation = (
            risk_transformation
            if risk_transformation is not None
            else RiskTransformation((), IDENTITY_RISK_COMPOSITION_VERSION)
        )
        self._validate_unique_facts()
        self._bars_by_session = self._index_bars_by_session()
        self._bars_by_instrument = self._index_bars_by_instrument()
        self._tradability_by_session = self._index_tradability_by_session()

    def _validate_unique_facts(self) -> None:
        seen_bars: set[tuple[InstrumentId, date]] = set()
        for bar in self._bars:
            key = (bar.instrument_id, bar.session_date)
            if key in seen_bars:
                raise AmbiguousMarketFactError(
                    f"duplicate daily bar for {bar.instrument_id} on {bar.session_date}"
                )
            seen_bars.add(key)
        seen_tradability: set[tuple[InstrumentId, date]] = set()
        for record in self._tradability:
            key = (record.instrument_id, record.session_date)
            if key in seen_tradability:
                raise AmbiguousMarketFactError(
                    f"duplicate tradability fact for {record.instrument_id} on "
                    f"{record.session_date}"
                )
            seen_tradability.add(key)
        seen_actions: set[str] = set()
        for action in self._corporate_actions:
            if action.action_id in seen_actions:
                raise AmbiguousMarketFactError(
                    f"duplicate corporate action {action.action_id}"
                )
            seen_actions.add(action.action_id)
        seen_positions: set[InstrumentId] = set()
        for position in self._initial_positions:
            if position.instrument_id in seen_positions:
                raise InvalidEngineInputError(
                    f"duplicate initial position for {position.instrument_id}"
                )
            seen_positions.add(position.instrument_id)

    def _index_bars_by_session(self) -> dict[date, tuple[DailyBar, ...]]:
        indexed: dict[date, list[DailyBar]] = {}
        for bar in self._bars:
            indexed.setdefault(bar.session_date, []).append(bar)
        return {
            session_date: tuple(sorted(records, key=lambda bar: bar.instrument_id))
            for session_date, records in indexed.items()
        }

    def _index_bars_by_instrument(self) -> dict[InstrumentId, tuple[DailyBar, ...]]:
        indexed: dict[InstrumentId, list[DailyBar]] = {}
        for bar in self._bars:
            indexed.setdefault(bar.instrument_id, []).append(bar)
        return {
            instrument_id: tuple(sorted(records, key=lambda bar: bar.session_date))
            for instrument_id, records in indexed.items()
        }

    def _index_tradability_by_session(self) -> dict[date, tuple[TradabilityStatus, ...]]:
        indexed: dict[date, list[TradabilityStatus]] = {}
        for record in self._tradability:
            indexed.setdefault(record.session_date, []).append(record)
        return {
            session_date: tuple(sorted(records, key=lambda item: item.instrument_id))
            for session_date, records in indexed.items()
        }

    def run(self, *, start_session: date, end_session: date) -> BacktestResult:
        require_session_date(start_session)
        require_session_date(end_session)
        if start_session > end_session:
            raise InvalidEngineInputError(
                f"start_session {start_session} must not be after end_session {end_session}"
            )
        session_dates = tuple(
            trading_session.session_date
            for trading_session in self._calendar.sessions
            if trading_session.is_open
            and start_session <= trading_session.session_date <= end_session
        )
        if not session_dates:
            raise InvalidEngineInputError(
                f"no open sessions between {start_session} and {end_session}"
            )
        cash = self._initial_cash
        positions = self._live_positions(self._initial_positions)
        pending: tuple[PendingPlan, ...] = ()
        applied_action_ids: set[str] = set()
        quantity_change_sessions: dict[InstrumentId, date] = {}
        records: list[SessionResult] = []
        for session_date in session_dates:
            outcome = self._run_session(
                session_date=session_date,
                cash=cash,
                positions=positions,
                pending=pending,
                applied_action_ids=applied_action_ids,
                quantity_change_sessions=quantity_change_sessions,
            )
            records.append(outcome.record)
            cash = outcome.cash
            positions = outcome.positions
            pending = outcome.pending
        return BacktestResult(sessions=tuple(records), cash=cash, positions=positions)

    def _run_session(
        self,
        *,
        session_date: date,
        cash: Money,
        positions: tuple[Position, ...],
        pending: tuple[PendingPlan, ...],
        applied_action_ids: set[str],
        quantity_change_sessions: dict[InstrumentId, date],
    ) -> _SessionOutcome:
        # Step 1: corporate actions apply before any activation; a
        # quantity-changing action invalidates the affected pending execution.
        effects, cash, positions, quantity_changed = self._apply_effective_corporate_actions(
            session_date=session_date,
            cash=cash,
            positions=positions,
            applied_action_ids=applied_action_ids,
            quantity_change_sessions=quantity_change_sessions,
        )
        invalidated = tuple(
            pending_order_for(
                plan, session_date, self._execution_model
            ).invalidated_corporate_action()
            for plan in pending
            if plan.instrument_id in quantity_changed
        )
        surviving = tuple(
            plan for plan in pending if plan.instrument_id not in quantity_changed
        )

        # Steps 2-6: activation of surviving plans.
        activation = self._activate(session_date, surviving, cash, positions)

        # Step 7: value the account at the session close.
        snapshot = self._value_at_close(
            session_date, activation, quantity_change_sessions
        )

        # Steps 8-10: expose T-known data, accept the predetermined target,
        # and persist the session record.
        decision = self._decide(session_date, snapshot)
        record = SessionResult(
            session_date=session_date,
            corporate_action_effects=effects,
            invalidated_orders=invalidated,
            activation=activation,
            snapshot=snapshot,
            nav=nav_point_of(snapshot),
            target=decision.target,
            plans=decision.plans,
            decision_digest=decision.digest,
            decision_blocked_reason=decision.blocked_reason,
        )
        return _SessionOutcome(
            record=record,
            cash=activation.cash,
            positions=self._live_positions(activation.positions),
            pending=decision.plans,
        )

    def _fraction_price_for(
        self, instrument_id: InstrumentId, session_date: date
    ) -> Decimal | None:
        """The cash-in-lieu reference price for a fractional share grant.

        The ex-session RAW close is the post-action share price and the
        session-close fact the action itself posts against; a session
        without a bar (suspension) falls back to the last valid close, and
        a name with no bar at all leaves the price unknown so the
        accounting fails closed instead of guessing.
        """
        for bar in self._bars_by_session.get(session_date, ()):
            if bar.instrument_id == instrument_id:
                return bar.close
        prior = self._latest_bar_before(instrument_id, session_date)
        return prior.close if prior is not None else None

    def _apply_effective_corporate_actions(
        self,
        *,
        session_date: date,
        cash: Money,
        positions: tuple[Position, ...],
        applied_action_ids: set[str],
        quantity_change_sessions: dict[InstrumentId, date],
    ) -> tuple[
        tuple[CorporateActionEffect, ...],
        Money,
        tuple[Position, ...],
        frozenset[InstrumentId],
    ]:
        """Apply every action that is effective and knowable at this session.

        An action whose information was not knowable at the activation cutoff
        is applied at the first later session where it becomes knowable, so
        the ledger never uses information before it existed. Cash dividends
        are applied before share-changing records on the same session so the
        cash is computed on the pre-change quantity.
        """
        cutoff = self._clock.activation_cutoff(session_date)
        effective = tuple(
            action
            for action in self._corporate_actions
            if action.action_id not in applied_action_ids
            and action.ex_date <= session_date
            and action.availability.information_known_at(cutoff) is True
        )
        if not effective:
            return (), cash, positions, frozenset()
        positions_by_id = {position.instrument_id: position for position in positions}
        effects: list[CorporateActionEffect] = []
        quantity_changed: set[InstrumentId] = set()
        for action in sorted(effective, key=_corporate_action_order):
            posting = apply_corporate_action(
                action=action,
                position=positions_by_id.get(action.instrument_id),
                cash=cash,
                session_date=session_date,
                recorded_at=self._clock.execution_at(session_date),
                fraction_price=(
                    self._fraction_price_for(action.instrument_id, session_date)
                    if self._accounting_semantics
                    is AccountingSemantics.CURRENT_M0_ACCOUNTING_2
                    else None
                ),
                accounting_semantics=self._accounting_semantics,
            )
            cash = posting.cash
            if posting.position is not None:
                positions_by_id[action.instrument_id] = posting.position
            applied_action_ids.add(action.action_id)
            if posting.quantity_delta != 0:
                quantity_changed.add(action.instrument_id)
                quantity_change_sessions[action.instrument_id] = session_date
            effects.append(
                CorporateActionEffect(
                    action_id=action.action_id,
                    instrument_id=action.instrument_id,
                    action_kind=action.action_kind,
                    cash_delta=posting.cash_delta,
                    quantity_delta=posting.quantity_delta,
                    cash_entry=posting.cash_entry,
                    holdings_entry=posting.holdings_entry,
                )
            )
        return (
            tuple(effects),
            cash,
            self._live_positions(tuple(positions_by_id.values())),
            frozenset(quantity_changed),
        )

    def _activate(
        self,
        session_date: date,
        plans: tuple[PendingPlan, ...],
        cash: Money,
        positions: tuple[Position, ...],
    ) -> ActivationResult:
        opens = {
            bar.instrument_id: bar.open
            for bar in self._bars_by_session.get(session_date, ())
        }
        cutoff = self._clock.activation_cutoff(session_date)
        tradability: dict[InstrumentId, TradabilityStatus] = {}
        for record in self._tradability_by_session.get(session_date, ()):
            if record.availability.information_known_at(cutoff) is True:
                tradability[record.instrument_id] = record
        rules = {}
        for plan in plans:
            try:
                rules[plan.instrument_id] = self._master.resolve_rules(
                    plan.instrument_id, session_date
                )
            except (UnknownInstrumentError, UnknownRuleError):
                continue
        return activate_pending_plans(
            plans=plans,
            cash=cash,
            positions=positions,
            opens=opens,
            tradability=tradability,
            rules=rules,
            account_fees=self._account_fees,
            execution_model=self._execution_model,
            calendar=self._calendar,
            execution_session=session_date,
            recorded_at=self._clock.execution_at(session_date),
        )

    def _value_at_close(
        self,
        session_date: date,
        activation: ActivationResult,
        quantity_change_sessions: dict[InstrumentId, date],
    ) -> PortfolioSnapshot:
        positions = self._live_positions(activation.positions)
        close_prices = {
            bar.instrument_id: bar.close
            for bar in self._bars_by_session.get(session_date, ())
        }
        last_valid_closes: dict[InstrumentId, tuple[Decimal, date]] = {}
        incomplete_valuations: dict[InstrumentId, IncompleteValuationReason] = {}
        for position in positions:
            if position.instrument_id in close_prices:
                continue
            prior = self._latest_bar_before(position.instrument_id, session_date)
            if prior is None:
                continue
            changed_on = quantity_change_sessions.get(position.instrument_id)
            if changed_on is not None and prior.session_date < changed_on:
                # The last close predates a quantity-changing action, so it no
                # longer describes the held position: the valuation is
                # incomplete rather than stale-valued.
                incomplete_valuations[position.instrument_id] = (
                    IncompleteValuationReason.CORPORATE_ACTION_INVALIDATED_PRICE
                )
                continue
            last_valid_closes[position.instrument_id] = (prior.close, prior.session_date)
        return mark_to_market(
            cash=activation.cash,
            positions=positions,
            session_date=session_date,
            generated_at=self._clock.decision_cutoff(session_date),
            calendar=self._calendar,
            close_prices=close_prices,
            last_valid_closes=last_valid_closes,
            incomplete_valuations=incomplete_valuations,
        )

    def _decide(self, session_date: date, snapshot: PortfolioSnapshot) -> _DecisionOutcome:
        if snapshot.valuation_status is ValuationStatus.INCOMPLETE:
            return _DecisionOutcome(
                target=None,
                plans=(),
                digest=None,
                blocked_reason=DecisionBlockReason.INCOMPLETE_VALUATION,
            )
        try:
            next_session = self._calendar.next_session(session_date).session_date
        except UnknownSessionError:
            return _DecisionOutcome(
                target=None,
                plans=(),
                digest=None,
                blocked_reason=DecisionBlockReason.NO_NEXT_SESSION,
            )
        cutoff = self._clock.decision_cutoff(session_date)
        context = DecisionContext(
            session_date=session_date,
            decision_for_trade_date=next_session,
            information_cutoff=cutoff,
            cash=snapshot.cash,
            valuation_equity=snapshot.total_equity,
            positions=snapshot.positions,
            bars=self._known_bars_through(session_date, cutoff),
            tradability=self._known_tradability_through(session_date, cutoff),
            corporate_actions=self._known_actions_through(session_date, cutoff),
        )
        contributions = self._target_source.contributions_for(context)
        if contributions is None:
            return _DecisionOutcome(target=None, plans=(), digest=None, blocked_reason=None)
        target = TheoreticalTargetPortfolio(
            target_id=f"target:{session_date.isoformat()}",
            revision=1,
            decision_for_trade_date=next_session,
            generated_at=cutoff,
            information_cutoff=cutoff,
            valuation_equity=snapshot.total_equity,
            contributions=tuple(contributions),
        )
        try:
            validate_target_completeness(
                target,
                held_instrument_ids=frozenset(
                    position.instrument_id
                    for position in snapshot.positions
                    if position.total_quantity > 0
                ),
            )
        except TargetNotCompleteError:
            return _DecisionOutcome(
                target=target,
                plans=(),
                digest=decision_digest(target, None, ()),
                blocked_reason=DecisionBlockReason.TARGET_INCOMPLETE,
            )
        risk = self._risk_transformation.transform(target)
        if risk.status is RiskTransformationStatus.BLOCKED:
            return _DecisionOutcome(
                target=target,
                plans=(),
                digest=decision_digest(target, None, ()),
                blocked_reason=DecisionBlockReason.RISK_BLOCKED,
            )
        approved = risk.approved
        if approved is None:
            raise InvalidEngineInputError(
                "a non-blocked risk transformation must provide an approved target"
            )
        holdings = tuple(
            CurrentHolding(instrument_id=position.instrument_id, quantity=position.total_quantity)
            for position in snapshot.positions
        )
        needed = sorted(
            {position.instrument_id for position in approved.positions}
            | {holding.instrument_id for holding in holdings}
        )
        lot_rules = {}
        for instrument_id in needed:
            try:
                lot_rules[instrument_id] = self._master.resolve_rules(
                    instrument_id, session_date
                ).lot
            except (UnknownInstrumentError, UnknownRuleError):
                return _DecisionOutcome(
                    target=target,
                    plans=(),
                    digest=decision_digest(target, None, ()),
                    blocked_reason=DecisionBlockReason.MISSING_INSTRUMENT_RULES,
                )
        close_prices = context.t_close_prices
        if any(instrument_id not in close_prices for instrument_id in needed):
            return _DecisionOutcome(
                target=target,
                plans=(),
                digest=decision_digest(target, None, ()),
                blocked_reason=DecisionBlockReason.MISSING_T_CLOSE_PRICE,
            )
        executable = build_executable_target(
            approved,
            CurrentPortfolio(cash=snapshot.cash, holdings=holdings),
            close_prices,
            lot_rules,
            _MasterFeeEstimator(
                master=self._master,
                broker=self._account_fees.resolve_broker_profile(session_date),
                session_date=session_date,
            ),
        )
        plans = self._plans_from_executable(executable, approved, holdings, session_date)
        return _DecisionOutcome(
            target=target,
            plans=plans,
            digest=decision_digest(target, executable, plans),
            blocked_reason=None,
        )

    @staticmethod
    def _plans_from_executable(
        executable: ExecutableTargetPortfolio,
        approved: RiskApprovedTargetPortfolio,
        holdings: tuple[CurrentHolding, ...],
        session_date: date,
    ) -> tuple[PendingPlan, ...]:
        current_quantities = {
            holding.instrument_id: holding.quantity for holding in holdings
        }
        approved_weights = {
            position.instrument_id: position.approved_weight
            for position in approved.positions
        }
        plans: list[PendingPlan] = []
        for position in executable.positions:
            instrument_id = position.instrument_id
            delta = position.planned_quantity - current_quantities.get(instrument_id, 0)
            if delta == 0:
                continue
            plans.append(
                PendingPlan(
                    instrument_id=instrument_id,
                    sleeve=position.sleeve,
                    side=TradeSide.BUY if delta > 0 else TradeSide.SELL,
                    order_quantity=abs(delta),
                    target_weight=approved_weights[instrument_id],
                    current_weight=position.current_weight,
                    target_id=executable.target_id,
                    target_revision=executable.revision,
                    decision_for_trade_date=session_date,
                    sizing_reference_price=position.sizing_reference_price,
                )
            )
        return tuple(plans)

    def _known_bars_through(self, session_date: date, cutoff: datetime) -> tuple[DailyBar, ...]:
        return tuple(
            bar
            for bar in self._bars
            if bar.session_date <= session_date
            and bar.availability.information_known_at(cutoff) is True
        )

    def _known_tradability_through(
        self, session_date: date, cutoff: datetime
    ) -> tuple[TradabilityStatus, ...]:
        return tuple(
            record
            for record in self._tradability
            if record.session_date <= session_date
            and record.availability.information_known_at(cutoff) is True
        )

    def _known_actions_through(
        self, session_date: date, cutoff: datetime
    ) -> tuple[CorporateAction, ...]:
        return tuple(
            action
            for action in self._corporate_actions
            if action.ex_date <= session_date
            and action.availability.information_known_at(cutoff) is True
        )

    def _latest_bar_before(
        self, instrument_id: InstrumentId, session_date: date
    ) -> DailyBar | None:
        prior = [
            bar
            for bar in self._bars_by_instrument.get(instrument_id, ())
            if bar.session_date < session_date
        ]
        if not prior:
            return None
        return prior[-1]

    @staticmethod
    def _live_positions(positions: tuple[Position, ...]) -> tuple[Position, ...]:
        return tuple(
            sorted(
                (position for position in positions if position.total_quantity > 0),
                key=lambda position: position.instrument_id,
            )
        )
