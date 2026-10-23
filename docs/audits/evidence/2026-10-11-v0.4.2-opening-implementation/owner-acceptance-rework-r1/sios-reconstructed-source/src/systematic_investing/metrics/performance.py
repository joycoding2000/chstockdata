"""Performance metrics: pure functions over immutable NAV series and ledgers.

Conventions are versioned and content-digested so a convention change creates a
new run identity (see :class:`MetricConventions`). M0 defaults: daily
close-to-close periodic returns, 252-session annualization, zero risk-free
rate, zero Sortino target, sample standard deviation, actual-calendar-day
CAGR, ``0.5 * gross traded notional / average equity`` turnover, and
underwater duration in both trading sessions and calendar days.

The series functions retain ``STALE_MARK`` NAV (a stale mark is explicit,
complete valuation evidence) and refuse only a truly incomplete portfolio
NAV. All arithmetic runs under a fixed Decimal precision so repeated runs are
bit-identical.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, localcontext
from enum import StrEnum
from hashlib import sha256
from itertools import pairwise

from systematic_investing.domain.ledger import (
    CashLedgerCategory,
    CashLedgerEntry,
    NavPoint,
    StaleMark,
)
from systematic_investing.domain.money import Money

# Fixed arithmetic precision for every published statistic. 28 digits is the
# default decimal context and comfortably exceeds the tolerance declared by
# the metric tests.
DECIMAL_PRECISION = 28


class MetricsError(Exception):
    """Base class for performance-metric errors."""


class InvalidNavSeriesError(MetricsError):
    """Raised when the NAV series itself is malformed (duplicates, wrong type)."""


class IncompleteNavError(MetricsError):
    """Raised when a portfolio NAV is truly incomplete; metrics are blocked.

    A long suspension marked with ``STALE_MARK`` is *not* incomplete evidence
    and never raises.
    """

    def __init__(self, reasons: tuple[str, ...]) -> None:
        self.reasons = reasons
        super().__init__(
            "portfolio NAV is incomplete; metrics are refused for reasons: "
            + ", ".join(reasons)
        )


class InsufficientHistoryError(MetricsError):
    """Raised when a required denominator or observation count is missing."""


def _with_metric_precision[T](operation: Callable[[], T]) -> T:
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        return operation()


def _require_points(nav_points: Sequence[NavPoint]) -> tuple[NavPoint, ...]:
    if not nav_points:
        raise InsufficientHistoryError("at least one NAV observation is required")
    for point in nav_points:
        if not isinstance(point, NavPoint):
            raise InvalidNavSeriesError(
                f"NAV series entries must be NavPoint, got {type(point).__name__}"
            )
    return tuple(nav_points)


def ordered_nav_points(nav_points: Sequence[NavPoint]) -> tuple[NavPoint, ...]:
    """Validate and canonically order a NAV series.

    Ordering is by session date so input ordering never changes output. A
    duplicated session or a non-positive NAV is malformed; a truly incomplete
    valuation refuses.
    """
    points = _require_points(nav_points)
    ordered = tuple(sorted(points, key=lambda point: point.session_date))
    for previous, current in pairwise(ordered):
        if current.session_date == previous.session_date:
            raise InvalidNavSeriesError(
                f"duplicate NAV observation for session {current.session_date}"
            )
    for point in ordered:
        if point.nav <= 0:
            raise InvalidNavSeriesError(
                f"NAV must stay positive for return metrics; got {point.nav} on "
                f"{point.session_date}"
            )
    reasons = tuple(
        sorted(
            {
                reason.value
                for point in ordered
                for reason in point.incomplete_reasons
            }
        )
    )
    if reasons:
        raise IncompleteNavError(reasons)
    return ordered


def daily_close_returns(nav_points: Sequence[NavPoint]) -> tuple[Decimal, ...]:
    """Daily close-to-close periodic returns between consecutive observations."""
    ordered = ordered_nav_points(nav_points)
    if len(ordered) < 2:
        raise InsufficientHistoryError(
            "daily close-to-close returns need at least two NAV observations"
        )
    return _with_metric_precision(
        lambda: tuple(
            current.nav / previous.nav - 1
            for previous, current in pairwise(ordered)
        )
    )


def total_return(nav_points: Sequence[NavPoint]) -> Decimal:
    """Ending equity divided by beginning equity minus one, after costs."""
    ordered = ordered_nav_points(nav_points)
    if len(ordered) < 2:
        raise InsufficientHistoryError(
            "total return needs at least two NAV observations"
        )
    return _with_metric_precision(
        lambda: ordered[-1].nav / ordered[0].nav - 1
    )


def _calendar_day_span(ordered: tuple[NavPoint, ...]) -> int:
    return (ordered[-1].session_date - ordered[0].session_date).days


def cagr(nav_points: Sequence[NavPoint]) -> Decimal:
    """Geometric annualization over the actual calendar-day span."""
    ordered = ordered_nav_points(nav_points)
    if len(ordered) < 2:
        raise InsufficientHistoryError("CAGR needs at least two NAV observations")
    span_days = _calendar_day_span(ordered)
    return _with_metric_precision(
        lambda: (ordered[-1].nav / ordered[0].nav)
        ** (Decimal(365) / Decimal(span_days))
        - 1
    )


@dataclass(frozen=True)
class UnderwaterDuration:
    """Maximum elapsed underwater episode in both declared units.

    Sessions count observation intervals between the first below-peak
    observation and its recovery (or the final observation when unrecovered);
    calendar days use the actual dated span.
    """

    sessions: int
    calendar_days: int


def average_equity(nav_points: Sequence[NavPoint]) -> Money:
    """Arithmetic mean of the observed total equity series."""
    ordered = ordered_nav_points(nav_points)
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        total = sum((point.total_equity.amount for point in ordered), Decimal("0"))
        return Money(total / Decimal(len(ordered)))


def gross_traded_notional(cash_entries: Iterable[CashLedgerEntry]) -> Money:
    """Gross buy-plus-sell consideration; fees and taxes are excluded."""
    traded = Decimal("0")
    for entry in cash_entries:
        if entry.category in (
            CashLedgerCategory.BUY_CONSIDERATION,
            CashLedgerCategory.SELL_PROCEEDS,
        ):
            traded += abs(entry.amount.amount)
    return Money(traded)


def total_costs(cash_entries: Iterable[CashLedgerEntry]) -> Money:
    """Modeled broker commission, stamp tax, and transfer fees."""
    costs = Decimal("0")
    for entry in cash_entries:
        if entry.category in (
            CashLedgerCategory.BROKER_COMMISSION,
            CashLedgerCategory.STAMP_TAX,
            CashLedgerCategory.TRANSFER_FEE,
        ):
            costs += abs(entry.amount.amount)
    return Money(costs)


def turnover(nav_points: Sequence[NavPoint], cash_entries: Iterable[CashLedgerEntry]) -> Decimal:
    """``0.5 * gross traded notional / average equity`` over the series."""
    ordered = ordered_nav_points(nav_points)
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        equity = sum(
            (point.total_equity.amount for point in ordered), Decimal("0")
        ) / Decimal(len(ordered))
        return Decimal("0.5") * gross_traded_notional(cash_entries).amount / equity


def drawdown_series(nav_points: Sequence[NavPoint]) -> tuple[Decimal, ...]:
    """Per-observation ``NAV / running_peak - 1`` (non-positive)."""
    ordered = ordered_nav_points(nav_points)
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        drawdowns: list[Decimal] = []
        peak: Decimal | None = None
        for point in ordered:
            peak = point.nav if peak is None else max(peak, point.nav)
            drawdowns.append(point.nav / peak - 1)
        return tuple(drawdowns)


def max_drawdown(nav_points: Sequence[NavPoint]) -> Decimal:
    """Deepest ``NAV / running_peak - 1`` decline (non-positive)."""
    return min(drawdown_series(nav_points))


def underwater_duration(nav_points: Sequence[NavPoint]) -> UnderwaterDuration:
    """Maximum unrecovered or recovered below-peak episode in both units."""
    ordered = ordered_nav_points(nav_points)
    longest_sessions = 0
    longest_calendar_days = 0
    episode_start: int | None = None
    peak = ordered[0].nav
    for index, point in enumerate(ordered):
        if point.nav < peak:
            if episode_start is None:
                episode_start = index
        else:
            if episode_start is not None:
                sessions = index - episode_start
                calendar_days = (
                    point.session_date - ordered[episode_start].session_date
                ).days
                longest_sessions = max(longest_sessions, sessions)
                longest_calendar_days = max(longest_calendar_days, calendar_days)
                episode_start = None
            peak = max(peak, point.nav)
    if episode_start is not None:
        last = len(ordered) - 1
        sessions = last - episode_start
        calendar_days = (
            ordered[last].session_date - ordered[episode_start].session_date
        ).days
        longest_sessions = max(longest_sessions, sessions)
        longest_calendar_days = max(longest_calendar_days, calendar_days)
    return UnderwaterDuration(sessions=longest_sessions, calendar_days=longest_calendar_days)


def calmar(nav_points: Sequence[NavPoint]) -> Decimal | None:
    """CAGR divided by the absolute maximum drawdown.

    A series without a drawdown has no defined Calmar ratio and returns
    ``None`` rather than an infinite value.
    """
    ordered = ordered_nav_points(nav_points)
    drawdown = max_drawdown(ordered)
    if drawdown == 0:
        return None
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        return cagr(ordered) / abs(drawdown)


def _require_returns(returns: Sequence[Decimal], *, statistic: str) -> tuple[Decimal, ...]:
    if len(returns) < 2:
        raise InsufficientHistoryError(
            f"{statistic} needs at least two returns for a sample estimate"
        )
    for value in returns:
        if not isinstance(value, Decimal) or not value.is_finite():
            raise MetricsError(f"returns must be finite Decimals, got {value!r}")
    return tuple(returns)


def _require_annualization(annualization_sessions: int) -> int:
    if (
        not isinstance(annualization_sessions, int)
        or isinstance(annualization_sessions, bool)
        or annualization_sessions <= 0
    ):
        raise MetricsError("annualization_sessions must be a positive integer")
    return annualization_sessions


def sample_volatility(
    returns: Sequence[Decimal], *, annualization_sessions: int = 252
) -> Decimal:
    """Sample standard deviation of returns, annualized by the declared sessions."""
    values = _require_returns(returns, statistic="sample volatility")
    sessions = _require_annualization(annualization_sessions)
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        mean = sum(values) / Decimal(len(values))
        variance = sum((value - mean) ** 2 for value in values) / Decimal(len(values) - 1)
        return variance.sqrt() * Decimal(sessions).sqrt()


def sharpe(
    returns: Sequence[Decimal],
    *,
    risk_free_rate: Decimal = Decimal("0"),
    annualization_sessions: int = 252,
) -> Decimal | None:
    """Annualized zero-risk-free Sharpe statistic.

    Zero volatility has no defined ratio; the explicit result is ``None``
    rather than an error or a fabricated number.
    """
    values = _require_returns(returns, statistic="Sharpe")
    sessions = _require_annualization(annualization_sessions)
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        excess = tuple(value - risk_free_rate for value in values)
        mean = sum(excess) / Decimal(len(excess))
        variance = sum((value - mean) ** 2 for value in excess) / Decimal(len(excess) - 1)
        deviation = variance.sqrt()
        if deviation == 0:
            return None
        return mean / deviation * Decimal(sessions).sqrt()


def sortino(
    returns: Sequence[Decimal],
    *,
    target_return: Decimal = Decimal("0"),
    annualization_sessions: int = 252,
) -> Decimal | None:
    """Annualized return over downside deviation with the M0 zero target.

    Downside deviation uses the population denominator over all observations
    (every observation contributes a non-positive shortfall). No downside
    shortfall has no defined ratio and returns ``None``.
    """
    values = _require_returns(returns, statistic="Sortino")
    sessions = _require_annualization(annualization_sessions)
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        mean = sum(values) / Decimal(len(values))
        shortfalls = tuple(min(value - target_return, Decimal("0")) for value in values)
        downside = (sum(value**2 for value in shortfalls) / Decimal(len(shortfalls))).sqrt()
        if downside == 0:
            return None
        return mean / downside * Decimal(sessions).sqrt()


def convention_digest(fields: Iterable[tuple[str, object]]) -> str:
    """Content digest of convention fields; identity changes with any field."""
    rendered = ";".join(f"{key}={value}" for key, value in sorted(fields))
    return "sha256:" + sha256(rendered.encode("utf-8")).hexdigest()


class UnsupportedBenchmarkError(MetricsError):
    """Raised when an M0 run declares a benchmark outside the approved values."""


class BenchmarkIdentity(StrEnum):
    """Benchmark identities an M0 run may declare.

    Until OQ-22 is decided before M1, no real investment benchmark exists;
    ``SYNTHETIC_TEST_BENCHMARK`` exists only for tests.
    """

    NONE = "NONE"
    SYNTHETIC_TEST_BENCHMARK = "SYNTHETIC_TEST_BENCHMARK"


class TerminalMode(StrEnum):
    """How the run terminated; metrics and manifests state the mode."""

    MARK_TO_MARKET = "MARK_TO_MARKET"
    FORCED_LIQUIDATION = "FORCED_LIQUIDATION"


class ReturnBasis(StrEnum):
    """Periodic return basis used by the statistics."""

    DAILY_CLOSE_TO_CLOSE = "DAILY_CLOSE_TO_CLOSE"


METRIC_CONVENTION_VERSION = "M0-METRICS-1"


@dataclass(frozen=True)
class MetricConventions:
    """Versioned metric conventions recorded in the run manifest.

    Changing any field changes :meth:`digest`, which changes run identity; a
    convention change never rewrites history.
    """

    convention_version: str = METRIC_CONVENTION_VERSION
    return_basis: ReturnBasis = ReturnBasis.DAILY_CLOSE_TO_CLOSE
    annualization_sessions: int = 252
    risk_free_rate: Decimal = Decimal("0")
    sortino_target: Decimal = Decimal("0")
    volatility_basis: str = "SAMPLE_STANDARD_DEVIATION"
    cagr_basis: str = "ACTUAL_CALENDAR_DAYS"
    turnover_basis: str = "HALF_GROSS_NOTIONAL_OVER_AVERAGE_EQUITY"
    underwater_units: tuple[str, ...] = ("SESSIONS", "CALENDAR_DAYS")
    benchmark: BenchmarkIdentity = BenchmarkIdentity.NONE
    terminal_mode: TerminalMode = TerminalMode.MARK_TO_MARKET

    def __post_init__(self) -> None:
        if not isinstance(self.benchmark, BenchmarkIdentity):
            try:
                object.__setattr__(
                    self, "benchmark", BenchmarkIdentity(str(self.benchmark))
                )
            except ValueError as error:
                raise UnsupportedBenchmarkError(
                    "M0 runs accept benchmark identity NONE or "
                    f"SYNTHETIC_TEST_BENCHMARK only; got {self.benchmark!r}"
                ) from error
        if not isinstance(self.terminal_mode, TerminalMode):
            try:
                object.__setattr__(
                    self, "terminal_mode", TerminalMode(str(self.terminal_mode))
                )
            except ValueError as error:
                raise MetricsError(
                    f"unknown terminal mode {self.terminal_mode!r}"
                ) from error
        if not isinstance(self.return_basis, ReturnBasis):
            try:
                object.__setattr__(
                    self, "return_basis", ReturnBasis(str(self.return_basis))
                )
            except ValueError as error:
                raise MetricsError(f"unknown return basis {self.return_basis!r}") from error
        for field_name in (
            "convention_version",
            "volatility_basis",
            "cagr_basis",
            "turnover_basis",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value:
                raise MetricsError(f"{field_name} must be a non-empty string")
        if (
            not isinstance(self.annualization_sessions, int)
            or isinstance(self.annualization_sessions, bool)
            or self.annualization_sessions <= 0
        ):
            raise MetricsError("annualization_sessions must be a positive integer")
        for field_name in ("risk_free_rate", "sortino_target"):
            value = getattr(self, field_name)
            if not isinstance(value, Decimal) or not value.is_finite():
                raise MetricsError(f"{field_name} must be a finite Decimal")
        if not isinstance(self.underwater_units, tuple) or not self.underwater_units:
            raise MetricsError("underwater_units must be a non-empty tuple")

    def _identity_fields(self) -> tuple[tuple[str, object], ...]:
        return (
            ("convention_version", self.convention_version),
            ("return_basis", self.return_basis.value),
            ("annualization_sessions", self.annualization_sessions),
            ("risk_free_rate", self.risk_free_rate),
            ("sortino_target", self.sortino_target),
            ("volatility_basis", self.volatility_basis),
            ("cagr_basis", self.cagr_basis),
            ("turnover_basis", self.turnover_basis),
            ("underwater_units", ",".join(self.underwater_units)),
            ("benchmark", self.benchmark.value),
            ("terminal_mode", self.terminal_mode.value),
        )

    def digest(self) -> str:
        """Content-derived convention identity."""
        return convention_digest(self._identity_fields())

    def as_manifest_fields(self) -> dict[str, object]:
        """Canonical manifest fields, including benchmark and terminal mode."""
        fields = dict(self._identity_fields())
        fields["conventions_digest"] = self.digest()
        return fields


@dataclass(frozen=True)
class CostDrag:
    """Gross-versus-net performance difference under the same fills."""

    net_total_return: Decimal
    gross_total_return: Decimal
    drag: Decimal
    total_costs: Money


def _costs_through(
    cost_entries: Sequence[CashLedgerEntry], as_of: date
) -> Decimal:
    return sum(
        (
            abs(entry.amount.amount)
            for entry in cost_entries
            if entry.session_date <= as_of
        ),
        Decimal("0"),
    )


def cost_drag(
    nav_points: Sequence[NavPoint], cash_entries: Iterable[CashLedgerEntry]
) -> CostDrag:
    """Compare net returns with the same equity path plus modeled costs.

    Modeled cash costs are added back per observation without reinvestment;
    costs recorded after the final observation do not belong to this series.
    """
    ordered = ordered_nav_points(nav_points)
    if len(ordered) < 2:
        raise InsufficientHistoryError("cost drag needs at least two NAV observations")
    entries = tuple(cash_entries)
    costs = total_costs(entries)
    cost_entries = tuple(
        entry
        for entry in entries
        if entry.category
        in (
            CashLedgerCategory.BROKER_COMMISSION,
            CashLedgerCategory.STAMP_TAX,
            CashLedgerCategory.TRANSFER_FEE,
        )
    )
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        net_return = ordered[-1].nav / ordered[0].nav - 1
        first = ordered[0]
        last = ordered[-1]
        gross_start = first.total_equity.amount + _costs_through(
            cost_entries, first.session_date
        )
        gross_end = last.total_equity.amount + _costs_through(
            cost_entries, last.session_date
        )
        gross_return = gross_end / gross_start - 1
        return CostDrag(
            net_total_return=net_return,
            gross_total_return=gross_return,
            drag=gross_return - net_return,
            total_costs=costs,
        )


@dataclass(frozen=True)
class MetricsReport:
    """Metric values plus the convention metadata recorded in the manifest."""

    observation_count: int
    first_session: date
    last_session: date
    conventions: MetricConventions
    daily_returns: tuple[Decimal, ...]
    total_return: Decimal
    cagr: Decimal
    volatility: Decimal
    sharpe: Decimal | None
    sortino: Decimal | None
    drawdowns: tuple[Decimal, ...]
    max_drawdown: Decimal
    calmar: Decimal | None
    underwater: UnderwaterDuration
    turnover: Decimal
    cost_drag: CostDrag
    stale_observation_count: int
    stale_marks: tuple[StaleMark, ...]


def compute_metrics(
    nav_points: Sequence[NavPoint],
    *,
    cash_entries: Iterable[CashLedgerEntry] = (),
    conventions: MetricConventions | None = None,
) -> MetricsReport:
    """Compute the full M0 metric set over a complete NAV series.

    ``STALE_MARK`` observations are retained and reported; a truly incomplete
    portfolio NAV refuses with :class:`IncompleteNavError`. At least three
    observations (two returns) are required so every published statistic has a
    defined sample estimate.
    """
    resolved = conventions if conventions is not None else MetricConventions()
    if not isinstance(resolved, MetricConventions):
        raise MetricsError("conventions must be a MetricConventions instance")
    ordered = ordered_nav_points(nav_points)
    if len(ordered) < 3:
        raise InsufficientHistoryError(
            "the full metric set needs at least three NAV observations"
        )
    entries = tuple(cash_entries)
    returns = daily_close_returns(ordered)
    drawdowns = drawdown_series(ordered)
    stale_marks = tuple(mark for point in ordered for mark in point.stale_marks)
    return MetricsReport(
        observation_count=len(ordered),
        first_session=ordered[0].session_date,
        last_session=ordered[-1].session_date,
        conventions=resolved,
        daily_returns=returns,
        total_return=total_return(ordered),
        cagr=cagr(ordered),
        volatility=sample_volatility(
            returns, annualization_sessions=resolved.annualization_sessions
        ),
        sharpe=sharpe(
            returns,
            risk_free_rate=resolved.risk_free_rate,
            annualization_sessions=resolved.annualization_sessions,
        ),
        sortino=sortino(
            returns,
            target_return=resolved.sortino_target,
            annualization_sessions=resolved.annualization_sessions,
        ),
        drawdowns=drawdowns,
        max_drawdown=min(drawdowns),
        calmar=calmar(ordered),
        underwater=underwater_duration(ordered),
        turnover=turnover(ordered, entries),
        cost_drag=cost_drag(ordered, entries),
        stale_observation_count=sum(
            1 for point in ordered if point.stale_marks
        ),
        stale_marks=stale_marks,
    )
