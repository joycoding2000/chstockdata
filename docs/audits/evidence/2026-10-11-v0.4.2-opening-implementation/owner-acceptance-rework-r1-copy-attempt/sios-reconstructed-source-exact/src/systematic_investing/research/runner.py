"""Adapter from typed Research strategies to the M0 ``TargetSource`` port,
and the Basic backtest runner.

``StrategyTargetSource`` is the only seam between a ``StrategyContract`` and
the frozen M0 ``DailyBarEngine``. It maps ``TARGETS`` to contributions and a
typed ``NO_DECISION`` to M0 ``None`` while retaining every evaluation so
reason semantics survive into Research artifacts. Contract violations raise
loudly; they never become silent decisions.

The injected universe is either a fixed ``UniverseView`` (ETF) or an
``AnnualUniverseSchedule`` (Stock), which is resolved per target trade date
so a decision always sees the cohort governing its own calendar year. A
strategy may additionally address an instrument it currently holds that is
outside the resolved view, but only with an explicit zero-weight exit
target; opening or growing outside exposure stays a loud run failure.

The Basic runner composes one frozen canonical snapshot with one canonical
strategy per parameter variant, runs the M0 kernel over warm-up plus Basic,
computes metrics strictly from the Basic window, evaluates the
pre-registered promotion gate, and selects the OOS candidate strictly by the
CandidateIntent priority list. Every attempt (pass, rejection, or failure)
is retained as content-derived evidence; the runner never decides verdicts
beyond the frozen gate.
"""

import importlib
import json
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from typing import cast

from systematic_investing.backtest.engine import (
    AmbiguousMarketFactError,
    DailyBarEngine,
    DecisionContext,
    EngineClock,
    UnknownFactError,
)
from systematic_investing.backtest.execution import (
    ExecutionModel,
)
from systematic_investing.data.quality import CanonicalDataset
from systematic_investing.domain.historical_opening import (
    HistoricalOpeningEvidence,
    ExecutionEligibilityMode,
    OPENING_POLICY,
    OPENING_CLOCK_ID,
    opening_evidence_digest,
    execution_identity,
)
from systematic_investing.domain.execution import (
    AccountFeeConfig,
    BrokerFeeProfile,
)
from systematic_investing.domain.ledger import CashLedgerEntry, NavPoint
from systematic_investing.domain.market import (
    CorporateAction,
    DailyBar,
    MarketCalendar,
    TradabilityStatus,
)
from systematic_investing.domain.money import Money
from systematic_investing.domain.portfolio import TargetContribution
from systematic_investing.instrument_master.repository import InstrumentMaster
from systematic_investing.metrics.performance import (
    MetricConventions,
    compute_metrics,
)
from systematic_investing.research.artifacts import canonical_json_bytes, digest_of_bytes
from systematic_investing.research.benchmarks import (
    BENCHMARK_REBALANCE_ANNUAL,
    BENCHMARK_SCHEMA_VERSION,
    BenchmarkKind,
    BenchmarkSpec,
)
from systematic_investing.research.contracts import (
    BENCHMARK_REBALANCE_INCEPTION,
    RUN_MANIFEST_SCHEMA_VERSION,
    CandidateIntent,
    ResearchRunManifest,
    StrategyContract,
    StrategyEvaluation,
    StrategyEvaluationStatus,
    StrategyIdentity,
    implementation_digest_of,
    split_digest_of,
    universe_view_digest,
)
from systematic_investing.research.intake import BasicSnapshotReceipt
from systematic_investing.research.kernel_replay import (
    KernelReplayProfile,
    current_kernel_replay_profile,
)
from systematic_investing.research.strategies import month_end_sessions
from systematic_investing.research.universe import (
    AnnualUniverseSchedule,
    NoCohortFormedError,
    UniverseView,
)

REASON_NOT_DECISION_SESSION: str = "NOT_DECISION_SESSION"

RUN_STATUS_BASIC_PASS: str = "BASIC_PASS"
RUN_STATUS_REJECTED_BASIC: str = "REJECTED_BASIC"
RUN_STATUS_RUN_FAILED_KERNEL: str = "RUN_FAILED_KERNEL"
RUN_STATUS_RUN_FAILED_DATA: str = "RUN_FAILED_DATA"
BASIC_OUTPUT_SCOPE: str = "BASIC"

GATE_MIN_NAV_OBSERVATIONS: str = "MIN_NAV_OBSERVATIONS"
GATE_MIN_EXCESS_TOTAL_RETURN: str = "MIN_EXCESS_TOTAL_RETURN"
GATE_MAX_DRAWDOWN_FLOOR: str = "MAX_DRAWDOWN_FLOOR"
GATE_MAX_TURNOVER: str = "MAX_TURNOVER"

GATE_VERDICT_PASS: str = "PASS"
GATE_VERDICT_FAIL: str = "FAIL"

RESULT_SCHEMA_VERSION: str = "research-basic-result-1"
REPORT_SCHEMA_VERSION: str = "research-basic-report-1"

CODE_COMMIT_UNCOMMITTED: str = "WORKTREE"

def dependency_digest_of(
    declared_files: Sequence[tuple[str, bytes]],
    *,
    python_compatibility: str = "3.12+",
    qualified_providers: Sequence[str] = ("chstockdata==0.3.0",),
) -> str:
    """Digest only declared dependency inputs, never ambient machine state."""
    lines = ["dependency_identity_v2", f"python-compatibility={python_compatibility}"]
    for relative_path, content in sorted(declared_files, key=lambda item: item[0]):
        if not relative_path or not isinstance(content, bytes):
            raise ValueError("declared dependency inputs must be named byte strings")
        lines.append(relative_path)
        lines.append(sha256(content).hexdigest())
    lines.extend(f"qualified-provider={provider}" for provider in sorted(qualified_providers))
    return "sha256:" + sha256("\n".join(lines).encode("utf-8")).hexdigest()


def _declared_dependency_digest() -> str:
    project_root = Path(__file__).resolve().parents[3]
    declaration_paths = ("pyproject.toml", "third_party/SOURCES.yaml")
    declared_files = tuple(
        (relative_path, (project_root / relative_path).read_bytes())
        for relative_path in declaration_paths
    )
    return dependency_digest_of(declared_files)


DEPENDENCY_DIGEST: str = _declared_dependency_digest()


class StrategyAdapterError(Exception):
    """Base class for strategy-to-M0 adapter errors."""


class StrategyContractViolationError(StrategyAdapterError):
    """Raised when a strategy output violates its declared identity or
    contract; the run fails instead of continuing with a silent decision."""


@dataclass(frozen=True)
class SessionEvaluation:
    """One retained evaluation: which session asked and what was decided."""

    session_date: date
    decision_for_trade_date: date
    evaluation: StrategyEvaluation


class StrategyTargetSource:
    """The only StrategyContract-to-M0 adapter.

    Implements the M0 ``TargetSource`` port. The strategy identity is bound
    once at construction and every session is validated against that bound
    identity; a mid-run identity change fails the run instead of mixing
    versions into one result. An annual schedule is resolved to the universe
    view governing each decision's trade date before the strategy sees it. Every
    evaluation is retained in order; a contribution outside the resolved
    view and the current holdings, or foreign to the bound identity, raises
    instead of producing a target.
    """

    def __init__(
        self,
        strategy: StrategyContract,
        universe: UniverseView | AnnualUniverseSchedule,
    ) -> None:
        self._strategy = strategy
        self._universe = universe
        self._identity = strategy.identity
        self._evaluations: list[SessionEvaluation] = []

    @property
    def identity(self) -> StrategyIdentity:
        return self._identity

    @property
    def universe(self) -> UniverseView | AnnualUniverseSchedule:
        return self._universe

    @property
    def evaluations(self) -> tuple[SessionEvaluation, ...]:
        return tuple(self._evaluations)

    def _view_for(self, context: DecisionContext) -> UniverseView | None:
        """The universe view governing the session this decision serves.

        A T-close decision produces targets for ``decision_for_trade_date``,
        so an annual schedule resolves the cohort of that trade date's
        calendar year: the year-end reconstitution takes effect for the
        first decision whose trade date falls in the new year, not one
        session later. A trade date before any formation returns ``None``
        (see ``contributions_for``); a FAILED formation year still raises.
        """
        universe = self._universe
        if isinstance(universe, UniverseView):
            return universe
        try:
            return universe.view_for(context.decision_for_trade_date)
        except NoCohortFormedError:
            return None

    def contributions_for(
        self, context: DecisionContext
    ) -> tuple[TargetContribution, ...] | None:
        self._require_bound_identity()
        view = self._view_for(context)
        if view is None:
            # Before the first year-end formation there is no governed
            # universe, so no decision can be addressed. Stock intake
            # guarantees a within-policy cohort for every Basic-window
            # calendar year, so only warm-up sessions land here; a year
            # whose formation FAILED still raises through ``view_for``.
            return None
        evaluation = self._strategy.evaluate(context, view)
        self._require_bound_identity()
        self._validate(evaluation, view, context)
        self._evaluations.append(
            SessionEvaluation(
                session_date=context.session_date,
                decision_for_trade_date=context.decision_for_trade_date,
                evaluation=evaluation,
            )
        )
        if evaluation.status is StrategyEvaluationStatus.NO_DECISION:
            return None
        return evaluation.contributions

    def _require_bound_identity(self) -> None:
        current = self._strategy.identity
        if current != self._identity:
            raise StrategyContractViolationError(
                f"strategy identity changed during the run: bound "
                f"{self._identity.strategy_id}/{self._identity.strategy_version}, now "
                f"{current.strategy_id}/{current.strategy_version}"
            )

    def _validate(
        self,
        evaluation: StrategyEvaluation,
        view: UniverseView,
        context: DecisionContext,
    ) -> None:
        identity = self._identity
        held = {
            position.instrument_id
            for position in context.positions
            if position.total_quantity > 0
        }
        for contribution in evaluation.contributions:
            if not view.contains(contribution.instrument_id) and (
                contribution.instrument_id not in held
                or contribution.target_weight != Decimal("0")
            ):
                raise StrategyContractViolationError(
                    f"contribution for {contribution.instrument_id} is outside the "
                    f"universe view governing {context.session_date}; only an "
                    "explicit zero-weight exit for a current holding may leave "
                    "the resolved view"
                )
            if (
                contribution.strategy_id != identity.strategy_id
                or contribution.strategy_version != identity.strategy_version
            ):
                raise StrategyContractViolationError(
                    f"contribution for {contribution.instrument_id} carries "
                    f"{contribution.strategy_id}/{contribution.strategy_version}, not the "
                    f"declared identity {identity.strategy_id}/{identity.strategy_version}"
                )
            if contribution.sleeve is not identity.sleeve:
                raise StrategyContractViolationError(
                    f"contribution for {contribution.instrument_id} uses sleeve "
                    f"{contribution.sleeve.value}, not the declared sleeve "
                    f"{identity.sleeve.value}"
                )


# --- Basic backtest runner ---------------------------------------------------


def worktree_identity(
    head: str,
    diff: bytes,
    untracked: "Sequence[tuple[str, str]]",
) -> str:
    """One unique code-state identity for a run.

    A clean tree binds exactly the HEAD commit. A dirty tree appends a
    content-derived fingerprint over the tracked diff and the untracked
    files (path plus content digest), so two different dirty states can
    never share one run identity.
    """
    fingerprint_lines = [f"head={head}", f"tracked_diff={sha256(diff).hexdigest()}"]
    for relative_path, content_digest in sorted(untracked):
        fingerprint_lines.append(f"untracked={relative_path},{content_digest}")
    fingerprint = sha256("\n".join(fingerprint_lines).encode("utf-8")).hexdigest()
    if not diff and not untracked:
        return head
    return f"{head}+worktree:{fingerprint[:16]}"


def resolve_code_commit() -> str:
    """The exact code state of the implementation under test.

    A clean worktree resolves to the HEAD commit; a dirty worktree gets a
    unique fingerprint over the tracked diff and every untracked file's
    content digest, so two different dirty states cannot share one run
    identity.
    """
    try:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        diff = subprocess.run(
            ["git", "diff", "HEAD", "--binary"],
            capture_output=True,
            check=True,
        ).stdout
        untracked_output = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard", "-z"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except (OSError, subprocess.SubprocessError) as error:
        raise StrategyRunError(f"code commit could not be resolved: {error}") from error
    untracked: list[tuple[str, str]] = []
    for relative_path in sorted(untracked_output.split("\0")):
        if not relative_path:
            continue
        try:
            content = Path(relative_path).read_bytes()
        except OSError as error:
            raise StrategyRunError(
                f"untracked file {relative_path} could not be fingerprinted: {error}"
            ) from error
        untracked.append(
            (relative_path, "sha256:" + sha256(content).hexdigest())
        )
    return worktree_identity(head, diff=diff, untracked=untracked)


class StrategyRunError(Exception):
    """Base class for Basic/OOS run orchestration errors."""


class RunWiringError(StrategyRunError):
    """Raised when a frozen run wiring violates its contract."""


def cost_spec_digest(intent: "CandidateIntent") -> str:
    """Content digest over the declared execution/cost conventions."""
    lines = [
        "research_cost_spec_v1",
        f"commission_rate={intent.cost_convention['commission_rate']}",
        f"minimum_commission={intent.cost_convention['minimum_commission']}",
        f"slippage_rate={intent.cost_convention['slippage_rate']}",
    ]
    return "sha256:" + sha256("\n".join(lines).encode("utf-8")).hexdigest()


def universe_schedule_identity_digest(
    universe: "UniverseView | AnnualUniverseSchedule",
) -> str:
    """The run-time universe identity: a fixed view or the annual schedule
    content (every formation year and its frozen cohort)."""
    if isinstance(universe, AnnualUniverseSchedule):
        return universe.content_digest()
    return universe_view_digest(universe.instrument_ids)


def kernel_identity_digest(
    execution_model: ExecutionModel,
    *,
    profile: KernelReplayProfile = current_kernel_replay_profile,
    execution_eligibility_mode: ExecutionEligibilityMode = ExecutionEligibilityMode.LEGACY,
) -> str:
    """Content digest of a selected frozen kernel replay profile."""
    base = profile.identity_digest(execution_model)
    if execution_eligibility_mode is ExecutionEligibilityMode.LEGACY:
        return base
    return (
        "sha256:"
        + sha256(
            execution_identity(base, execution_eligibility_mode, ()).encode("utf-8")
        ).hexdigest()
    )


@dataclass(frozen=True)
class BasicWiring:
    """One frozen run wiring: snapshot facts plus kernel and account inputs.

    Everything is derived deterministically from the canonical snapshot and
    the frozen CandidateIntent; nothing observes wall-clock time.
    """

    calendar: MarketCalendar
    master: InstrumentMaster
    account_fees: AccountFeeConfig
    execution_model: ExecutionModel
    clock: EngineClock
    bars: tuple[DailyBar, ...]
    tradability: tuple[TradabilityStatus, ...]
    corporate_actions: tuple[CorporateAction, ...]
    initial_cash: Money
    warm_up_start: date
    basic_start: date
    basic_end: date
    decision_sessions: tuple[date, ...]
    universe: UniverseView | AnnualUniverseSchedule
    snapshot_digest: str
    benchmark_spec: BenchmarkSpec
    benchmark_inception_session: date
    code_commit: str
    dependency_digest: str
    kernel_profile: KernelReplayProfile = current_kernel_replay_profile
    historical_opening_evidence: tuple[HistoricalOpeningEvidence, ...] = ()
    execution_eligibility_mode: ExecutionEligibilityMode = ExecutionEligibilityMode.LEGACY
    instrument_reference_digest: str | None = None


def _account_fee_config(intent: "CandidateIntent") -> AccountFeeConfig:
    return AccountFeeConfig(
        config_id=f"RUN-{intent.intent_id}",
        config_version="1",
        broker_profiles=(
            BrokerFeeProfile(
                profile_id="ACCT:RESEARCH-MAIN",
                version="1",
                commission_rate=Decimal(intent.cost_convention["commission_rate"]),
                minimum_commission=Decimal(intent.cost_convention["minimum_commission"]),
                agreement_reference=intent.intent_id,
                effective_from=intent.warm_up_start,
                effective_to=None,
            ),
        ),
    )


def build_basic_wiring(
    dataset: CanonicalDataset,
    intent: "CandidateIntent",
    receipt: BasicSnapshotReceipt,
    *,
    master: InstrumentMaster,
    instrument_reference_digest: str | None = None,
    execution_eligibility_mode: ExecutionEligibilityMode = ExecutionEligibilityMode.LEGACY,
) -> BasicWiring:
    """Freeze the full Basic run wiring from snapshot and intent.

    A snapshot whose calendar stops before the Basic end is a partial
    provider delivery and fails closed: a shorter window can never silently
    become a successful run.
    """
    if execution_eligibility_mode is ExecutionEligibilityMode.HISTORICAL_OPENING_R21:
        if (
            not dataset.historical_opening_evidence
            or receipt.execution_policy != OPENING_POLICY
            or receipt.execution_clock != OPENING_CLOCK_ID
            or receipt.execution_evidence_digest
            != opening_evidence_digest(dataset.historical_opening_evidence)
            or receipt.dataset_digest != dataset.content_digest()
        ):
            raise RunWiringError(
                "historical opening wiring requires verified snapshot policy/clock/evidence identity"
            )
    if not dataset.sessions:
        raise RunWiringError(
            "the canonical snapshot carries no calendar sessions"
        )
    sessions = tuple(
        sorted(
            {
                session.session_date
                for session in dataset.sessions
                if session.is_open
                and intent.basic_start <= session.session_date <= intent.basic_end
            }
        )
    )
    if not sessions:
        raise RunWiringError(
            "no open calendar sessions inside the Basic window of the intent"
        )
    snapshot_last_session = max(session.session_date for session in dataset.sessions)
    if snapshot_last_session < intent.basic_end:
        raise RunWiringError(
            f"the canonical snapshot stops at {snapshot_last_session.isoformat()} "
            f"before the Basic end {intent.basic_end.isoformat()}; a partial "
            "snapshot can never be run as a successful Basic window"
        )
    calendar_id = dataset.sessions[0].calendar_id
    snapshot_versions = {session.snapshot_version for session in dataset.sessions}
    if len(snapshot_versions) != 1:
        raise RunWiringError(
            f"snapshot sessions span multiple calendar versions: {sorted(snapshot_versions)}"
        )
    calendar = MarketCalendar(
        calendar_id=calendar_id,
        snapshot_version=next(iter(snapshot_versions)),
        sessions=tuple(
            session
            for session in sorted(dataset.sessions, key=lambda item: item.session_date)
            if session.is_open
        ),
    )
    instrument_ids = tuple(intent.universe_policy.instrument_ids)
    slippage = Decimal(intent.cost_convention["slippage_rate"])
    execution_model = ExecutionModel(
        slippage_rate_buy=slippage, slippage_rate_sell=slippage
    )
    benchmark_kind = intent.benchmark.kind
    benchmark_rebalance = (
        BENCHMARK_REBALANCE_ANNUAL
        if benchmark_kind.value == BenchmarkKind.STOCK_ANNUAL_SCHEDULE_EQUAL_WEIGHT.value
        else BENCHMARK_REBALANCE_INCEPTION
    )
    benchmark_spec = BenchmarkSpec(
        benchmark_schema_version=BENCHMARK_SCHEMA_VERSION,
        kind=benchmark_kind.value,
        instrument_ids=tuple(intent.benchmark.instrument_ids),
        rebalance=benchmark_rebalance,
    )
    universe: UniverseView | AnnualUniverseSchedule
    if intent.asset_class.value == "STOCK":
        if receipt.annual_schedule is None:
            raise RunWiringError(
                "a STOCK Basic run requires the intake-validated annual "
                "PIT schedule on the snapshot receipt"
            )
        universe = receipt.annual_schedule
    else:
        universe = UniverseView(instrument_ids)
    return BasicWiring(
        calendar=calendar,
        master=master,
        account_fees=_account_fee_config(intent),
        execution_model=execution_model,
        clock=EngineClock.shanghai()
        if execution_eligibility_mode is ExecutionEligibilityMode.HISTORICAL_OPENING_R21
        else EngineClock(),
        execution_eligibility_mode=execution_eligibility_mode,
        historical_opening_evidence=dataset.historical_opening_evidence,
        bars=tuple(dataset.daily_bars),
        tradability=tuple(dataset.tradability),
        corporate_actions=tuple(dataset.corporate_actions),
        initial_cash=Money(intent.initial_capital),
        warm_up_start=intent.warm_up_start,
        basic_start=intent.basic_start,
        basic_end=intent.basic_end,
        decision_sessions=month_end_sessions(sessions),
        universe=universe,
        snapshot_digest="sha256:" + receipt.snapshot_id,
        benchmark_spec=benchmark_spec,
        benchmark_inception_session=sessions[0],
        code_commit=resolve_code_commit(),
        dependency_digest=DEPENDENCY_DIGEST,
        instrument_reference_digest=instrument_reference_digest,
    )


def build_canonical_strategy(
    intent: "CandidateIntent",
    parameters: Mapping[str, str],
    decision_sessions: Sequence[date],
) -> "StrategyContract":
    """Build the canonical strategy named by the intent with frozen
    parameters; an unknown strategy id fails the run closed."""
    strategy_modules = {
        "etf-absolute-trend": (
            "systematic_investing.research.strategies.etf_absolute_trend",
            "build_strategy",
        ),
        "etf-relative-momentum": (
            "systematic_investing.research.strategies.etf_relative_momentum",
            "build_strategy",
        ),
        "stock-relative-strength": (
            "systematic_investing.research.strategies.stock_relative_strength",
            "build_strategy",
        ),
        "stock-breakout": (
            "systematic_investing.research.strategies.stock_breakout",
            "build_strategy",
        ),
    }
    module_spec = strategy_modules.get(intent.strategy_id)
    if module_spec is None:
        raise RunWiringError(
            f"unknown canonical strategy id {intent.strategy_id!r}; the Basic "
            "runner refuses non-canonical strategies"
        )
    module_name, builder_name = module_spec
    module = importlib.import_module(module_name)
    source_name = getattr(module, "__file__", None)
    if not isinstance(source_name, str):
        raise RunWiringError(
            f"canonical strategy module {module_name!r} has no source file"
        )
    source_path = Path(source_name).resolve()
    source_root = Path(__file__).resolve().parents[2]
    try:
        relative_source = source_path.relative_to(source_root).as_posix()
    except ValueError as error:
        raise RunWiringError(
            f"canonical strategy source {source_path} is outside the project source root"
        ) from error
    implementation_digest = implementation_digest_of(
        [(relative_source, source_path.read_bytes())]
    )
    builder = getattr(module, builder_name, None)
    if not callable(builder):
        raise RunWiringError(
            f"canonical strategy module {module_name!r} has no callable {builder_name!r}"
        )
    return cast(
        StrategyContract,
        builder(
            parameters,
            decision_sessions,
            implementation_digest=implementation_digest,
        ),
    )


@dataclass(frozen=True)
class BasicRunOutcome:
    """One retained Basic attempt with its content-derived artifacts."""

    variant_id: str
    status: str
    reason_codes: tuple[str, ...]
    manifest_payload: Mapping[str, object]
    result_payload: Mapping[str, object]
    result_digest: str
    report_payload: Mapping[str, object]


def _metrics_summary_payload(
    nav_points: Sequence[NavPoint],
    cash_entries: Sequence[CashLedgerEntry],
) -> dict[str, object]:
    report = compute_metrics(nav_points, cash_entries=cash_entries)
    return {
        "observation_count": report.observation_count,
        "first_session": report.first_session.isoformat(),
        "last_session": report.last_session.isoformat(),
        "total_return": str(report.total_return),
        "cagr": str(report.cagr),
        "max_drawdown": str(report.max_drawdown),
        "turnover": str(report.turnover),
        "stale_observation_count": report.stale_observation_count,
        "cost_drag": str(report.cost_drag.drag),
        "total_costs": str(report.cost_drag.total_costs.amount),
    }


def run_basic_variant(
    wiring: BasicWiring,
    intent: "CandidateIntent",
    variant_id: str,
    variant_parameters: Mapping[str, str],
    benchmark_total_return: Decimal,
) -> BasicRunOutcome:
    """Run one parameter variant through the M0 kernel and gate it.

    The kernel runs warm-up plus Basic; metrics are computed strictly from
    NAV observations inside the Basic window. The pre-registered promotion
    gate decides ``BASIC_PASS`` or ``REJECTED_BASIC``. Failures are retained
    as typed failed runs: ambiguous or missing market facts are provider data
    failures (``RUN_FAILED_DATA``), everything else — compile errors, wiring
    violations, kernel errors — is ``RUN_FAILED_KERNEL``. No failure is ever
    representable as a successful run with empty metrics. No verdict is
    decided beyond the gate.
    """
    # Imported lazily because the OOS module imports this runner for its
    # strategy wiring; keeping the reporting dependency here avoids a module
    # initialization cycle while still binding the report to the run's NAV.
    from systematic_investing.research.reporting import build_yearly_subperiod_report

    try:
        strategy = build_canonical_strategy(
            intent, variant_parameters, wiring.decision_sessions
        )
        adapter = StrategyTargetSource(strategy, wiring.universe)
        engine = DailyBarEngine(
            calendar=wiring.calendar,
            clock=wiring.clock,
            master=wiring.master,
            account_fees=wiring.account_fees,
            execution_model=wiring.execution_model,
            accounting_semantics=wiring.kernel_profile.accounting_semantics,
            bars=wiring.bars,
            tradability=wiring.tradability,
            historical_opening_evidence=wiring.historical_opening_evidence,
            execution_eligibility_mode=wiring.execution_eligibility_mode,
            corporate_actions=wiring.corporate_actions,
            target_source=adapter,
            initial_cash=wiring.initial_cash,
        )
        result = engine.run(start_session=wiring.warm_up_start, end_session=wiring.basic_end)
        nav_points = tuple(
            record.nav
            for record in result.sessions
            if record.session_date >= wiring.basic_start
        )
        cash_entries = tuple(
            entry
            for entry in result.cash_entries
            if entry.session_date >= wiring.basic_start
        )
        metrics = _metrics_summary_payload(nav_points, cash_entries)
        period_report = build_yearly_subperiod_report(
            nav_points, cash_entries=cash_entries
        )
        metrics["trade_count"] = len(result.fills)
        metrics["rejection_count"] = len(result.rejections)
        decision_session_count = sum(
            1
            for record in adapter.evaluations
            if record.session_date in set(wiring.decision_sessions)
        )
        no_decision_count = sum(
            1
            for record in adapter.evaluations
            if record.evaluation.status is StrategyEvaluationStatus.NO_DECISION
        )
    except (AmbiguousMarketFactError, UnknownFactError) as error:
        reason = f"{type(error).__name__}: {error}"
        return _failed_basic_outcome(
            wiring, intent, variant_id, variant_parameters, reason, RUN_STATUS_RUN_FAILED_DATA
        )
    except Exception as error:
        reason = f"{type(error).__name__}: {error}"
        return _failed_basic_outcome(
            wiring, intent, variant_id, variant_parameters, reason, RUN_STATUS_RUN_FAILED_KERNEL
        )

    verdicts, status = evaluate_basic_gate(
        intent, metrics, benchmark_total_return
    )
    identity = strategy.identity
    manifest = ResearchRunManifest(
        manifest_schema_version=RUN_MANIFEST_SCHEMA_VERSION,
        lineage_id=intent.lineage_id,
        intent_digest=intent.intent_digest,
        strategy_id=identity.strategy_id,
        strategy_version=identity.strategy_version,
        strategy_identity_digest=identity.content_digest(),
        implementation_digest=identity.implementation_digest,
        parameters_digest=identity.parameters_digest,
        code_commit=wiring.code_commit,
        dependency_digest=wiring.dependency_digest,
        split_digest=split_digest_of(
            intent.warm_up_start,
            intent.basic_start,
            intent.basic_end,
            intent.oos_start,
            intent.oos_end,
        ),
        snapshot_digest=(
            wiring.snapshot_digest
            if wiring.instrument_reference_digest is None
            else "sha256:"
            + sha256(
                (wiring.snapshot_digest + "|" + wiring.instrument_reference_digest).encode()
            ).hexdigest()
        ),
        universe_schedule_digest=universe_schedule_identity_digest(wiring.universe),
        benchmark_spec_digest=wiring.benchmark_spec.digest(),
        cost_spec_digest=cost_spec_digest(intent),
        metric_convention_digest=MetricConventions().digest(),
        kernel_identity_digest=kernel_identity_digest(
            wiring.execution_model,
            profile=wiring.kernel_profile,
            execution_eligibility_mode=wiring.execution_eligibility_mode,
        ),
        output_scope=BASIC_OUTPUT_SCOPE,
        random_seed=0,
    )
    result_payload: dict[str, object] = {
        "result_schema_version": RESULT_SCHEMA_VERSION,
        "lineage_id": intent.lineage_id,
        "intent_id": intent.intent_id,
        "intent_digest": intent.intent_digest,
        "variant_id": variant_id,
        "variant_parameters": dict(variant_parameters),
        "status": status,
        "gate_verdicts": verdicts,
        "reason_codes": () if status == RUN_STATUS_BASIC_PASS else (status,),
        "window": {
            "warm_up_start": intent.warm_up_start.isoformat(),
            "basic_start": intent.basic_start.isoformat(),
            "basic_end": intent.basic_end.isoformat(),
        },
        "snapshot_digest": manifest.snapshot_digest,
        "universe_schedule_digest": manifest.universe_schedule_digest,
        "benchmark_spec_digest": manifest.benchmark_spec_digest,
        "benchmark_kind": wiring.benchmark_spec.kind,
        "benchmark_total_return": str(benchmark_total_return),
        "cost_spec_digest": manifest.cost_spec_digest,
        "metric_convention_digest": manifest.metric_convention_digest,
        "kernel_identity_digest": manifest.kernel_identity_digest,
        "code_commit": wiring.code_commit,
        "dependency_digest": wiring.dependency_digest,
        "metrics": dict(metrics),
    }
    result_digest = digest_of_bytes(canonical_json_bytes(result_payload))
    report_payload: dict[str, object] = {
        "report_schema_version": REPORT_SCHEMA_VERSION,
        "lineage_id": intent.lineage_id,
        "variant_id": variant_id,
        "status": status,
        "decision_session_count": decision_session_count,
        "evaluation_count": len(adapter.evaluations),
        "no_decision_count": no_decision_count,
        "fill_count": len(result.fills),
        "rejection_count": len(result.rejections),
        "order_count": len(result.orders),
        "final_cash": str(result.cash.amount),
        "final_positions": {
            str(position.instrument_id): position.total_quantity
            for position in result.positions
        },
        "gate_verdicts": verdicts,
        "metrics": dict(metrics),
        "period_report_schema_version": period_report["report_schema_version"],
        "yearly": period_report["yearly"],
        "subperiods": period_report["subperiods"],
        "benchmark_total_return": str(benchmark_total_return),
    }
    return BasicRunOutcome(
        variant_id=variant_id,
        status=status,
        reason_codes=() if status == RUN_STATUS_BASIC_PASS else (status,),
        manifest_payload=manifest.to_payload(),
        result_payload=result_payload,
        result_digest=result_digest,
        report_payload=report_payload,
    )


def _failed_basic_outcome(
    wiring: BasicWiring,
    intent: "CandidateIntent",
    variant_id: str,
    variant_parameters: Mapping[str, str],
    reason: str,
    status: str,
) -> BasicRunOutcome:
    """Build a typed failed-run outcome with as much identity as is known."""
    snapshot_digest = wiring.snapshot_digest
    manifest = ResearchRunManifest(
        manifest_schema_version=RUN_MANIFEST_SCHEMA_VERSION,
        lineage_id=intent.lineage_id,
        intent_digest=intent.intent_digest,
        strategy_id=intent.strategy_id,
        strategy_version="unresolved",
        strategy_identity_digest="sha256:"
        + sha256(f"failed-strategy:{variant_id}".encode()).hexdigest(),
        implementation_digest="sha256:"
        + sha256(f"failed-implementation:{variant_id}".encode()).hexdigest(),
        parameters_digest="sha256:"
        + sha256(json.dumps(dict(variant_parameters), sort_keys=True).encode("utf-8")).hexdigest(),
        code_commit=wiring.code_commit,
        dependency_digest=wiring.dependency_digest,
        split_digest=split_digest_of(
            intent.warm_up_start,
            intent.basic_start,
            intent.basic_end,
            intent.oos_start,
            intent.oos_end,
        ),
        snapshot_digest=snapshot_digest,
        universe_schedule_digest=universe_schedule_identity_digest(wiring.universe),
        benchmark_spec_digest=wiring.benchmark_spec.digest(),
        cost_spec_digest=cost_spec_digest(intent),
        metric_convention_digest=MetricConventions().digest(),
        kernel_identity_digest=kernel_identity_digest(
            wiring.execution_model,
            profile=wiring.kernel_profile,
            execution_eligibility_mode=wiring.execution_eligibility_mode,
        ),
        output_scope=BASIC_OUTPUT_SCOPE,
        random_seed=0,
    )
    result_payload: dict[str, object] = {
        "result_schema_version": RESULT_SCHEMA_VERSION,
        "lineage_id": intent.lineage_id,
        "intent_id": intent.intent_id,
        "intent_digest": intent.intent_digest,
        "variant_id": variant_id,
        "variant_parameters": dict(variant_parameters),
        "status": status,
        "reason_codes": (reason,),
        "window": {
            "warm_up_start": intent.warm_up_start.isoformat(),
            "basic_start": intent.basic_start.isoformat(),
            "basic_end": intent.basic_end.isoformat(),
        },
        "snapshot_digest": snapshot_digest,
        "code_commit": wiring.code_commit,
        "dependency_digest": wiring.dependency_digest,
    }
    result_digest = digest_of_bytes(canonical_json_bytes(result_payload))
    return BasicRunOutcome(
        variant_id=variant_id,
        status=status,
        reason_codes=(reason,),
        manifest_payload=manifest.to_payload(),
        result_payload=result_payload,
        result_digest=result_digest,
        report_payload={
            "report_schema_version": REPORT_SCHEMA_VERSION,
            "lineage_id": intent.lineage_id,
            "variant_id": variant_id,
            "status": status,
            "reason": reason,
        },
    )


def evaluate_basic_gate(
    intent: "CandidateIntent",
    metrics: Mapping[str, object],
    benchmark_total_return: Decimal,
) -> tuple[tuple[Mapping[str, str], ...], str]:
    """Apply the pre-registered Basic promotion gate to one attempt."""
    rule = intent.basic_promotion_rule
    strategy_total = Decimal(str(metrics["total_return"]))
    excess = strategy_total - benchmark_total_return
    observation_count = int(str(metrics["observation_count"]))
    drawdown = Decimal(str(metrics["max_drawdown"]))
    turnover = Decimal(str(metrics["turnover"]))
    verdicts = (
        _verdict(
            GATE_MIN_NAV_OBSERVATIONS,
            observation_count,
            int(rule["min_nav_observations"]),
            observation_count >= int(rule["min_nav_observations"]),
            ">=",
        ),
        _verdict(
            GATE_MIN_EXCESS_TOTAL_RETURN,
            excess,
            Decimal(rule["min_excess_total_return_vs_benchmark"]),
            excess >= Decimal(rule["min_excess_total_return_vs_benchmark"]),
            ">=",
        ),
        _verdict(
            GATE_MAX_DRAWDOWN_FLOOR,
            drawdown,
            Decimal(rule["max_drawdown_floor"]),
            drawdown >= Decimal(rule["max_drawdown_floor"]),
            ">=",
        ),
        _verdict(
            GATE_MAX_TURNOVER,
            turnover,
            Decimal(rule["max_turnover"]),
            turnover <= Decimal(rule["max_turnover"]),
            "<=",
        ),
    )
    status = (
        RUN_STATUS_BASIC_PASS
        if all(verdict["verdict"] == GATE_VERDICT_PASS for verdict in verdicts)
        else RUN_STATUS_REJECTED_BASIC
    )
    return verdicts, status


def _verdict(
    criterion: str,
    observed: object,
    threshold: object,
    passed: bool,
    comparator: str,
) -> Mapping[str, str]:
    return {
        "criterion": criterion,
        "observed": str(observed),
        "comparator": comparator,
        "threshold": str(threshold),
        "verdict": GATE_VERDICT_PASS if passed else GATE_VERDICT_FAIL,
    }


@dataclass(frozen=True)
class BasicSelection:
    """The pre-registered selection over one Basic attempt set."""

    selected_variant_id: str | None
    status: str

    def to_payload(self) -> Mapping[str, object]:
        return {
            "selection_schema_version": "research-basic-selection-1",
            "selected_variant_id": self.selected_variant_id,
            "status": self.status,
        }


def select_basic_candidate(
    intent: "CandidateIntent",
    outcomes: Sequence[BasicRunOutcome],
) -> BasicSelection:
    """Select the OOS candidate strictly by the predeclared priority list.

    The first ``BASIC_PASS`` variant in ``parameter_priority`` order wins,
    regardless of which other variant has the higher return. Zero passes is
    a valid selection outcome and never triggers a re-search.
    """
    outcomes_by_variant = {outcome.variant_id: outcome for outcome in outcomes}
    for variant_id in intent.parameter_priority:
        outcome = outcomes_by_variant.get(variant_id)
        if outcome is not None and outcome.status == RUN_STATUS_BASIC_PASS:
            return BasicSelection(
                selected_variant_id=variant_id, status="SELECTED"
            )
    return BasicSelection(selected_variant_id=None, status="NO_BASIC_PASS")
