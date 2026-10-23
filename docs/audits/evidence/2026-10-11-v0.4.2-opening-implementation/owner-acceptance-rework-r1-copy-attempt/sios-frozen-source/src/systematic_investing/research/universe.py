"""Research universe views: one decision-time eligible instrument set.

A view is immutable and canonicalized to sorted canonical ``InstrumentId``
order, so neither input ordering nor iteration order can change a decision.
An empty view fails closed at construction instead of silently yielding no
candidates.

The annual PIT Stock schedule reconstitutes one cohort per calendar year
from year-end formation facts. A cohort for calendar year ``Y`` is formed
exclusively from facts knowable at the last formation session of year
``Y-1``; it is frozen for all of ``Y`` and never backfilled by later years,
so a newly eligible stock can only enter at a later formation.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
from types import MappingProxyType

from systematic_investing.domain.identifiers import (
    InstrumentId,
    require_session_date,
)
from systematic_investing.domain.market import TradabilityStatusKind


class UniverseError(Exception):
    """Base class for research-universe contract errors."""


class InvalidUniverseViewError(UniverseError):
    """Raised when a universe view violates its contract."""


class AnnualScheduleError(UniverseError):
    """Base class for annual PIT schedule contract errors."""


class InvalidFormationFactError(AnnualScheduleError):
    """Raised when a formation fact violates its contract."""


class InvalidAnnualPolicyError(AnnualScheduleError):
    """Raised when an annual universe policy violates its contract."""


class AmbiguousFormationError(AnnualScheduleError):
    """Raised when formation facts make one formation year ambiguous."""


class NoCohortFormedError(AnnualScheduleError):
    """Raised when a date has no preceding year-end formation to govern it."""


class AnnualCohortFailedError(AnnualScheduleError):
    """Raised when a formation year's eligible pool was below the real-run
    minimum; that calendar year fails closed instead of shrinking the rule."""


@dataclass(frozen=True)
class UniverseView:
    """The eligible instruments a strategy may address for one decision."""

    instrument_ids: tuple[InstrumentId, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.instrument_ids, tuple):
            raise InvalidUniverseViewError("instrument_ids must be a tuple")
        seen: set[InstrumentId] = set()
        for instrument_id in self.instrument_ids:
            if not isinstance(instrument_id, InstrumentId):
                raise InvalidUniverseViewError(
                    f"instrument_ids must contain InstrumentId, got {instrument_id!r}"
                )
            if instrument_id in seen:
                raise InvalidUniverseViewError(f"duplicate instrument {instrument_id}")
            seen.add(instrument_id)
        if not self.instrument_ids:
            raise InvalidUniverseViewError("a universe view must name at least one instrument")
        object.__setattr__(self, "instrument_ids", tuple(sorted(self.instrument_ids)))

    def contains(self, instrument_id: InstrumentId) -> bool:
        if not isinstance(instrument_id, InstrumentId):
            raise InvalidUniverseViewError(
                f"instrument_id must be an InstrumentId, got {instrument_id!r}"
            )
        return instrument_id in self.instrument_ids


class StockIdentityStatus(StrEnum):
    """Point-in-time identity status as known at a formation cutoff. Only
    ``NORMAL`` names are eligible; ST and delisting-process names are
    excluded, never inferred from symbol strings."""

    NORMAL = "NORMAL"
    ST = "ST"
    DELISTING_PROCESS = "DELISTING_PROCESS"


@dataclass(frozen=True)
class TrailingAmount:
    """One known session amount of the trailing liquidity window."""

    session_date: date
    amount: Decimal

    def __post_init__(self) -> None:
        require_session_date(self.session_date)
        if (
            not isinstance(self.amount, Decimal)
            or not self.amount.is_finite()
            or self.amount <= 0
        ):
            raise InvalidFormationFactError(
                f"amount must be a finite positive Decimal, got {self.amount!r}"
            )


@dataclass(frozen=True)
class StockFormationFact:
    """One instrument's formation facts as known at one year-end cutoff.

    ``listed_sessions`` counts the open listed sessions known at the cutoff;
    ``tradability`` is the formation-session status; ``trailing_amounts`` are
    the known amounts of the trailing liquidity window. Amounts dated after
    the formation session fail closed: future data can never enter a cohort
    through a formation fact.
    """

    instrument_id: InstrumentId
    formation_session: date
    listed_sessions: int
    identity_status: StockIdentityStatus
    tradability: TradabilityStatusKind
    trailing_amounts: tuple[TrailingAmount, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.instrument_id, InstrumentId):
            raise InvalidFormationFactError(
                f"instrument_id must be an InstrumentId, got {self.instrument_id!r}"
            )
        require_session_date(self.formation_session)
        if (
            not isinstance(self.listed_sessions, int)
            or isinstance(self.listed_sessions, bool)
            or self.listed_sessions < 1
        ):
            raise InvalidFormationFactError(
                "listed_sessions must be a positive integer, got "
                f"{self.listed_sessions!r}"
            )
        if not isinstance(self.identity_status, StockIdentityStatus):
            raise InvalidFormationFactError(
                f"identity_status must be a StockIdentityStatus, got "
                f"{self.identity_status!r}"
            )
        if not isinstance(self.tradability, TradabilityStatusKind):
            raise InvalidFormationFactError(
                f"tradability must be a TradabilityStatusKind, got {self.tradability!r}"
            )
        if not isinstance(self.trailing_amounts, tuple) or not all(
            isinstance(amount, TrailingAmount) for amount in self.trailing_amounts
        ):
            raise InvalidFormationFactError(
                "trailing_amounts must be a tuple of TrailingAmount"
            )
        seen: set[date] = set()
        for amount in self.trailing_amounts:
            if amount.session_date > self.formation_session:
                raise InvalidFormationFactError(
                    f"{self.instrument_id} carries a trailing amount for "
                    f"{amount.session_date} after formation cutoff "
                    f"{self.formation_session}"
                )
            if amount.session_date in seen:
                raise InvalidFormationFactError(
                    f"{self.instrument_id} carries duplicate trailing amounts for "
                    f"{amount.session_date}"
                )
            seen.add(amount.session_date)


@dataclass(frozen=True)
class AnnualUniversePolicy:
    """The frozen annual reconstitution policy. The M1 standard policy is
    the real one: at least 250 listed open sessions, a trailing 60-session
    median amount, top 50 by median amount, and a hard minimum of 20 eligible
    names per year that fails the year closed."""

    minimum_listing_sessions: int
    trailing_amount_sessions: int
    minimum_cohort_size: int
    maximum_cohort_size: int

    def __post_init__(self) -> None:
        for name in (
            "minimum_listing_sessions",
            "trailing_amount_sessions",
            "minimum_cohort_size",
            "maximum_cohort_size",
        ):
            value = getattr(self, name)
            if (
                not isinstance(value, int)
                or isinstance(value, bool)
                or value < 1
            ):
                raise InvalidAnnualPolicyError(f"{name} must be a positive integer")
        if self.minimum_cohort_size > self.maximum_cohort_size:
            raise InvalidAnnualPolicyError(
                "minimum_cohort_size must not exceed maximum_cohort_size"
            )

    @classmethod
    def standard(cls) -> "AnnualUniversePolicy":
        return cls(
            minimum_listing_sessions=250,
            trailing_amount_sessions=60,
            minimum_cohort_size=20,
            maximum_cohort_size=50,
        )


def _median(amounts: Sequence[Decimal]) -> Decimal:
    ordered = sorted(amounts)
    middle = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / Decimal("2")


@dataclass(frozen=True)
class AnnualUniverseSchedule:
    """Immutable, deterministic annual cohorts.

    The cohort for calendar year ``Y`` was formed at the year-end cutoff of
    ``Y-1`` and is frozen for every date of ``Y``. Formation years whose
    eligible pool fell below the policy minimum fail closed when addressed.
    Internally only derived immutable structures are kept: the caller's
    record sequence is never retained.
    """

    _cohorts: Mapping[int, tuple[InstrumentId, ...]]
    _failed_cohort_sizes: Mapping[int, int]

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "_cohorts", MappingProxyType(dict(self._cohorts))
        )
        object.__setattr__(
            self, "_failed_cohort_sizes", MappingProxyType(dict(self._failed_cohort_sizes))
        )

    def view_for(self, session_date: date) -> UniverseView:
        """The frozen cohort governing ``session_date``'s calendar year.

        Governed by the formation of the preceding year end; a year with no
        formation or a below-minimum cohort fails closed with a typed error.
        """
        require_session_date(session_date)
        formation_year = session_date.year - 1
        if formation_year not in self._cohorts:
            if formation_year in self._failed_cohort_sizes:
                raise AnnualCohortFailedError(
                    f"calendar year {session_date.year} fails closed: its "
                    f"{formation_year} formation produced only "
                    f"{self._failed_cohort_sizes[formation_year]} eligible "
                    "instruments, below the policy minimum"
                )
            raise NoCohortFormedError(
                f"no annual cohort was formed for calendar year {session_date.year}"
            )
        return UniverseView(self._cohorts[formation_year])

    @property
    def formation_years(self) -> tuple[int, ...]:
        return tuple(sorted(self._cohorts))

    def content_digest(self) -> str:
        """Content digest over the formed cohorts, independent of input
        ordering. A changed membership for any formation year produces a new
        schedule identity."""
        lines = ["research_annual_schedule_v1"]
        for formation_year in sorted(self._cohorts):
            lines.append(
                f"{formation_year}="
                + ",".join(
                    str(instrument_id)
                    for instrument_id in sorted(self._cohorts[formation_year])
                )
            )
        return "sha256:" + sha256("\n".join(lines).encode("utf-8")).hexdigest()


def form_annual_schedule(
    records: Sequence[StockFormationFact],
    policy: AnnualUniversePolicy,
) -> AnnualUniverseSchedule:
    """Form the annual PIT schedule from year-end formation facts.

    Every fact must be one instrument's cutoff-time snapshot; facts are
    grouped by formation year, ranked by ``(-median_amount, InstrumentId)``
    over the eligible pool, and truncated to the policy maximum. A pool
    below the policy minimum marks that year as failed closed. Nothing but
    derived immutable cohorts survives into the schedule.
    """
    if not isinstance(policy, AnnualUniversePolicy):
        raise InvalidAnnualPolicyError(f"policy must be an AnnualUniversePolicy, got {policy!r}")
    if not isinstance(records, (list, tuple)) or not all(
        isinstance(record, StockFormationFact) for record in records
    ):
        raise InvalidFormationFactError(
            "records must be a sequence of StockFormationFact"
        )
    by_year: dict[int, dict[InstrumentId, StockFormationFact]] = {}
    session_by_year: dict[int, date] = {}
    for record in records:
        formation_year = record.formation_session.year
        year_records = by_year.setdefault(formation_year, {})
        if record.instrument_id in year_records:
            raise AmbiguousFormationError(
                f"{record.instrument_id} has duplicate formation facts for "
                f"{formation_year}"
            )
        previous = session_by_year.get(formation_year)
        if previous is not None and previous != record.formation_session:
            raise AmbiguousFormationError(
                f"formation year {formation_year} mixes formation sessions "
                f"{previous} and {record.formation_session}"
            )
        session_by_year[formation_year] = record.formation_session
        year_records[record.instrument_id] = record

    cohorts: dict[int, tuple[InstrumentId, ...]] = {}
    failed_cohort_sizes: dict[int, int] = {}
    for formation_year in sorted(by_year):
        eligible: list[tuple[Decimal, InstrumentId]] = []
        for instrument_id, record in by_year[formation_year].items():
            if record.identity_status is not StockIdentityStatus.NORMAL:
                continue
            if record.tradability is not TradabilityStatusKind.TRADABLE:
                continue
            if record.listed_sessions < policy.minimum_listing_sessions:
                continue
            if len(record.trailing_amounts) != policy.trailing_amount_sessions:
                continue
            eligible.append(
                (
                    _median([amount.amount for amount in record.trailing_amounts]),
                    instrument_id,
                )
            )
        if len(eligible) < policy.minimum_cohort_size:
            failed_cohort_sizes[formation_year] = len(eligible)
            continue
        ranked = sorted(eligible, key=lambda item: (-item[0], item[1]))
        cohorts[formation_year] = tuple(
            instrument_id for _, instrument_id in ranked[: policy.maximum_cohort_size]
        )
    return AnnualUniverseSchedule(
        _cohorts=cohorts, _failed_cohort_sizes=failed_cohort_sizes
    )
