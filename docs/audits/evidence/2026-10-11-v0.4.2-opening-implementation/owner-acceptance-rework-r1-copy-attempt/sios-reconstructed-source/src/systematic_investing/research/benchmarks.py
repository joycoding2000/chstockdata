"""Candidate-local benchmark specs and their same-kernel target sources.

M1-D03/OQ-22: every candidate uses a pre-registered candidate-local
benchmark computed through the same M0 kernel, snapshot, calendar, cost,
and execution semantics as the strategy run — never a percentage over
adjusted closes compared against a net strategy NAV. All reports additionally
carry the ``CASH_0`` comparator: zero-yield account cash, not an instrument.
The benchmark identity is content-derived; replacing a benchmark after seeing
results creates a new spec and a new run identity.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256

from systematic_investing.backtest.engine import DecisionContext
from systematic_investing.domain.identifiers import InstrumentId, SleeveId
from systematic_investing.domain.portfolio import TargetContribution
from systematic_investing.research.universe import AnnualUniverseSchedule

BENCHMARK_REBALANCE_INCEPTION: str = "INCEPTION"
BENCHMARK_REBALANCE_ANNUAL: str = "ANNUAL"
BENCHMARK_SCHEMA_VERSION: str = "research-benchmark-1"


class BenchmarkError(Exception):
    """Base class for benchmark contract errors."""


class UnsupportedBenchmarkError(BenchmarkError):
    """Raised when a benchmark spec violates its contract."""


@dataclass(frozen=True)
class BenchmarkSpec:
    """The frozen candidate-local benchmark identity.

    ``INCEPTION`` rebalance means the benchmark buys its declared
    instruments once at the first open session of the performance window and
    never trades again; the same kernel fees and execution semantics apply.
    ``ANNUAL`` rebalance (the Stock same-schedule benchmark) means the
    benchmark holds each calendar year's annual PIT cohort at equal weight,
    trading only at the first open session of each year; the cohort
    membership is data-derived, so the spec declares no instrument list.
    """

    benchmark_schema_version: str
    kind: str
    instrument_ids: tuple[InstrumentId, ...]
    rebalance: str

    def __post_init__(self) -> None:
        if self.benchmark_schema_version != BENCHMARK_SCHEMA_VERSION:
            raise UnsupportedBenchmarkError(
                f"unsupported benchmark_schema_version {self.benchmark_schema_version!r}"
            )
        if self.kind not in (
            BenchmarkKind.SINGLE_ETF_BUY_AND_HOLD.value,
            BenchmarkKind.ETF_UNIVERSE_EQUAL_WEIGHT.value,
            BenchmarkKind.STOCK_ANNUAL_SCHEDULE_EQUAL_WEIGHT.value,
        ):
            raise UnsupportedBenchmarkError(
                f"unsupported benchmark kind {self.kind!r}"
            )
        if self.kind == BenchmarkKind.STOCK_ANNUAL_SCHEDULE_EQUAL_WEIGHT.value:
            if self.instrument_ids:
                raise UnsupportedBenchmarkError(
                    "the same-schedule annual benchmark declares no fixed "
                    "instrument list"
                )
            if self.rebalance != BENCHMARK_REBALANCE_ANNUAL:
                raise UnsupportedBenchmarkError(
                    f"the same-schedule annual benchmark rebalances "
                    f"{BENCHMARK_REBALANCE_ANNUAL} only"
                )
            return
        if not self.instrument_ids or not all(
            isinstance(item, InstrumentId) for item in self.instrument_ids
        ):
            raise UnsupportedBenchmarkError(
                "instrument_ids must be a non-empty tuple of InstrumentId"
            )
        if self.rebalance != BENCHMARK_REBALANCE_INCEPTION:
            raise UnsupportedBenchmarkError(
                f"fixed-universe benchmarks rebalance "
                f"{BENCHMARK_REBALANCE_INCEPTION} only"
            )

    def digest(self) -> str:
        lines = [
            "research_benchmark_spec_v1",
            f"schema_version={self.benchmark_schema_version}",
            f"kind={self.kind}",
            "instruments="
            + ",".join(str(item) for item in sorted(self.instrument_ids)),
            f"rebalance={self.rebalance}",
        ]
        return "sha256:" + sha256("\n".join(lines).encode("utf-8")).hexdigest()

    def weights(self) -> Mapping[InstrumentId, Decimal]:
        count = Decimal(len(self.instrument_ids))
        weights: dict[InstrumentId, Decimal] = {}
        for instrument_id in sorted(self.instrument_ids):
            weights[instrument_id] = Decimal("1") / count
        return weights

    @property
    def sleeve(self) -> SleeveId:
        if self.kind == BenchmarkKind.STOCK_ANNUAL_SCHEDULE_EQUAL_WEIGHT.value:
            return SleeveId.SATELLITE
        return SleeveId.CORE

    def inception_target(self, inception_session: date) -> tuple[TargetContribution, ...]:
        weights = self.weights()
        return tuple(
            TargetContribution(
                instrument_id=instrument_id,
                sleeve=self.sleeve,
                strategy_id=f"benchmark:{self.kind.lower()}",
                strategy_version=BENCHMARK_SCHEMA_VERSION,
                target_weight=weight,
            )
            for instrument_id, weight in sorted(weights.items())
        )


class BenchmarkKind(StrEnum):
    """The benchmark kinds admitted for M1 candidates."""

    SINGLE_ETF_BUY_AND_HOLD = "SINGLE_ETF_BUY_AND_HOLD"
    ETF_UNIVERSE_EQUAL_WEIGHT = "ETF_UNIVERSE_EQUAL_WEIGHT"
    STOCK_ANNUAL_SCHEDULE_EQUAL_WEIGHT = "STOCK_ANNUAL_SCHEDULE_EQUAL_WEIGHT"


class CASH_0:
    """The zero-yield cash comparator.

    Not a kernel run and not an instrument position: cash stays cash with a
    zero return, per M1-D04. ``total_return`` and ``cagr`` are exactly zero;
    drawdown never occurs.
    """

    LABEL: str = "CASH_0"

    @staticmethod
    def total_return() -> Decimal:
        return Decimal("0")

    @staticmethod
    def cagr() -> Decimal:
        return Decimal("0")

    @staticmethod
    def max_drawdown() -> Decimal:
        return Decimal("0")


class BenchmarkTargetSource:
    """Same-kernel benchmark target source for one inception rebalance.

    Implements the M0 ``TargetSource`` port: it addresses the frozen
    benchmark weights exactly once at the inception session and stays silent
    afterwards, so the benchmark is bought at T close / T+1 open with the
    same fees as any strategy and never rebalanced again.
    """

    def __init__(
        self,
        spec: BenchmarkSpec,
        inception_session: date,
    ) -> None:
        self._spec = spec
        self._inception_session = inception_session

    def contributions_for(
        self, context: DecisionContext
    ) -> tuple[TargetContribution, ...] | None:
        if context.session_date == self._inception_session:
            return self._spec.inception_target(context.session_date)
        return None


def stock_annual_inception_sessions(
    session_dates: Sequence[date],
    *,
    basic_start: date,
    basic_end: date,
) -> tuple[date, ...]:
    """The first open session of every Basic-window calendar year.

    The same-schedule benchmark trades only at these sessions; derivation
    uses the frozen calendar snapshot alone, so which session opens a year
    is calendar knowledge available at that session's close.
    """
    first_by_year: dict[int, date] = {}
    for session_date in sorted(session_dates):
        if session_date < basic_start or session_date > basic_end:
            continue
        current = first_by_year.get(session_date.year)
        if current is None or session_date < current:
            first_by_year[session_date.year] = session_date
    return tuple(sorted(first_by_year.values()))


class StockAnnualBenchmarkTargetSource:
    """Same-kernel equal-weight benchmark over the annual PIT cohort schedule.

    At the first open session of each Basic-window calendar year it targets
    that year's cohort at weight ``1/len(cohort)`` each and explicitly exits
    every holding that left the cohort, so the benchmark tracks the same
    reconstitution as the strategy through the same fees, lots, settlement,
    and accounting. Non-inception sessions stay silent.
    """

    def __init__(
        self,
        spec: BenchmarkSpec,
        schedule: AnnualUniverseSchedule,
        inception_sessions: Sequence[date],
    ) -> None:
        if spec.kind != BenchmarkKind.STOCK_ANNUAL_SCHEDULE_EQUAL_WEIGHT.value:
            raise UnsupportedBenchmarkError(
                "the annual-schedule benchmark source requires the "
                f"{BenchmarkKind.STOCK_ANNUAL_SCHEDULE_EQUAL_WEIGHT.value} kind"
            )
        self._spec = spec
        self._schedule = schedule
        self._inception_sessions = frozenset(inception_sessions)

    def contributions_for(
        self, context: DecisionContext
    ) -> tuple[TargetContribution, ...] | None:
        if context.session_date not in self._inception_sessions:
            return None
        cohort = self._schedule.view_for(context.decision_for_trade_date)
        weight = Decimal("1") / Decimal(len(cohort.instrument_ids))
        held = {
            position.instrument_id
            for position in context.positions
            if position.total_quantity > 0
        }
        contributions = [
            TargetContribution(
                instrument_id=instrument_id,
                sleeve=SleeveId.SATELLITE,
                strategy_id=f"benchmark:{self._spec.kind.lower()}",
                strategy_version=BENCHMARK_SCHEMA_VERSION,
                target_weight=weight,
            )
            for instrument_id in cohort.instrument_ids
        ]
        contributions.extend(
            TargetContribution(
                instrument_id=instrument_id,
                sleeve=SleeveId.SATELLITE,
                strategy_id=f"benchmark:{self._spec.kind.lower()}",
                strategy_version=BENCHMARK_SCHEMA_VERSION,
                target_weight=Decimal("0"),
            )
            for instrument_id in sorted(held - set(cohort.instrument_ids))
        )
        return tuple(contributions)
