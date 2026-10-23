"""Same-kernel benchmark specs, target sources, and the CASH_0 comparator.

Every candidate benchmark is computed through the same M0 kernel inputs as
the strategy run: the target sources only emit ``TargetContribution`` tuples
and the kernel owns sizing, fees, execution, and accounting. The benchmark
identity is content-derived; ``CASH_0`` is the zero-yield cash comparator —
exactly zero, not an instrument, and not a kernel run.
"""

from datetime import UTC, date, datetime, time
from decimal import Decimal

import pytest

from systematic_investing.backtest.engine import DailyBarEngine, DecisionContext
from systematic_investing.domain.identifiers import InstrumentId, SleeveId
from systematic_investing.domain.ledger import AcquisitionLot, Position
from systematic_investing.domain.market import TradabilityStatusKind
from systematic_investing.domain.money import Money
from systematic_investing.research.benchmarks import (
    BENCHMARK_REBALANCE_ANNUAL,
    BENCHMARK_REBALANCE_INCEPTION,
    BENCHMARK_SCHEMA_VERSION,
    CASH_0,
    BenchmarkKind,
    BenchmarkSpec,
    BenchmarkTargetSource,
    StockAnnualBenchmarkTargetSource,
    UnsupportedBenchmarkError,
    stock_annual_inception_sessions,
)
from systematic_investing.research.universe import (
    AnnualUniversePolicy,
    StockFormationFact,
    StockIdentityStatus,
    TrailingAmount,
    form_annual_schedule,
)

ETF = InstrumentId.parse("XSHG:510300")
ETF2 = InstrumentId.parse("XSHE:159915")
SINGLE_ETF = BenchmarkKind.SINGLE_ETF_BUY_AND_HOLD.value
ETF_UNIVERSE = BenchmarkKind.ETF_UNIVERSE_EQUAL_WEIGHT.value
STOCK_ANNUAL = BenchmarkKind.STOCK_ANNUAL_SCHEDULE_EQUAL_WEIGHT.value

ANNUAL_POLICY = AnnualUniversePolicy(
    minimum_listing_sessions=10,
    trailing_amount_sessions=4,
    minimum_cohort_size=2,
    maximum_cohort_size=3,
)


# --- helpers ---------------------------------------------------------------------


def _inception_spec(
    *instruments: InstrumentId, kind: str = SINGLE_ETF
) -> BenchmarkSpec:
    return BenchmarkSpec(
        benchmark_schema_version=BENCHMARK_SCHEMA_VERSION,
        kind=kind,
        instrument_ids=instruments,
        rebalance=BENCHMARK_REBALANCE_INCEPTION,
    )


def _annual_spec() -> BenchmarkSpec:
    return BenchmarkSpec(
        benchmark_schema_version=BENCHMARK_SCHEMA_VERSION,
        kind=STOCK_ANNUAL,
        instrument_ids=(),
        rebalance=BENCHMARK_REBALANCE_ANNUAL,
    )


def _context(
    session_date: date,
    decision_for_trade_date: date,
    *,
    positions: tuple[Position, ...] = (),
) -> DecisionContext:
    return DecisionContext(
        session_date=session_date,
        decision_for_trade_date=decision_for_trade_date,
        information_cutoff=datetime.combine(session_date, time(15, 30), tzinfo=UTC),
        cash=Money(Decimal("100000")),
        valuation_equity=Money(Decimal("100000")),
        positions=positions,
        bars=(),
        tradability=(),
        corporate_actions=(),
    )


def _position(symbol: str) -> Position:
    return Position(
        instrument_id=InstrumentId.parse(symbol),
        lots=(
            AcquisitionLot(
                quantity=100,
                acquired_session=date(2020, 12, 1),
                sellable_from=date(2020, 12, 2),
                acquisition_price=Decimal("10"),
            ),
        ),
    )


def _trailing(amount: str, count: int, *, end: date) -> tuple[TrailingAmount, ...]:
    session_dates: list[date] = []
    cursor = end
    while len(session_dates) < count:
        if cursor.weekday() < 5:
            session_dates.append(cursor)
        cursor = date.fromordinal(cursor.toordinal() - 1)
    session_dates.reverse()
    return tuple(
        TrailingAmount(session_date, Decimal(amount)) for session_date in session_dates
    )


def _fact(symbol: str, formation_session: date, median: str) -> StockFormationFact:
    return StockFormationFact(
        instrument_id=InstrumentId.parse(symbol),
        formation_session=formation_session,
        listed_sessions=300,
        identity_status=StockIdentityStatus.NORMAL,
        tradability=TradabilityStatusKind.TRADABLE,
        trailing_amounts=_trailing(median, 4, end=formation_session),
    )


def _annual_schedule():
    """2020 formation -> {600001, 600002, 600003}; 2021 -> {600001, 600002,
    600004}, so 600003 leaves and 600004 enters the cohort for 2022."""
    records = [
        _fact("XSHG:600001", date(2020, 12, 31), "5000000"),
        _fact("XSHG:600002", date(2020, 12, 31), "4500000"),
        _fact("XSHG:600003", date(2020, 12, 31), "4000000"),
        _fact("XSHG:600001", date(2021, 12, 31), "5000000"),
        _fact("XSHG:600002", date(2021, 12, 31), "4500000"),
        _fact("XSHG:600004", date(2021, 12, 31), "4000000"),
    ]
    return form_annual_schedule(records, ANNUAL_POLICY)


# --- BenchmarkSpec contract -------------------------------------------------------


def test_benchmark_spec_rejects_contract_violations() -> None:
    violations = [
        {"benchmark_schema_version": "research-benchmark-0", "kind": SINGLE_ETF,
         "instrument_ids": (ETF,), "rebalance": BENCHMARK_REBALANCE_INCEPTION},
        {"benchmark_schema_version": BENCHMARK_SCHEMA_VERSION, "kind": "MAGIC_PORTFOLIO",
         "instrument_ids": (ETF,), "rebalance": BENCHMARK_REBALANCE_INCEPTION},
        {"benchmark_schema_version": BENCHMARK_SCHEMA_VERSION, "kind": STOCK_ANNUAL,
         "instrument_ids": (ETF,), "rebalance": BENCHMARK_REBALANCE_ANNUAL},
        {"benchmark_schema_version": BENCHMARK_SCHEMA_VERSION, "kind": STOCK_ANNUAL,
         "instrument_ids": (), "rebalance": BENCHMARK_REBALANCE_INCEPTION},
        {"benchmark_schema_version": BENCHMARK_SCHEMA_VERSION, "kind": SINGLE_ETF,
         "instrument_ids": (), "rebalance": BENCHMARK_REBALANCE_INCEPTION},
        {"benchmark_schema_version": BENCHMARK_SCHEMA_VERSION, "kind": SINGLE_ETF,
         "instrument_ids": (ETF,), "rebalance": BENCHMARK_REBALANCE_ANNUAL},
        {"benchmark_schema_version": BENCHMARK_SCHEMA_VERSION, "kind": ETF_UNIVERSE,
         "instrument_ids": (ETF,), "rebalance": BENCHMARK_REBALANCE_ANNUAL},
        {"benchmark_schema_version": BENCHMARK_SCHEMA_VERSION, "kind": SINGLE_ETF,
         "instrument_ids": ("XSHG:510300",), "rebalance": BENCHMARK_REBALANCE_INCEPTION},
    ]
    for kwargs in violations:
        with pytest.raises(UnsupportedBenchmarkError):
            BenchmarkSpec(**kwargs)


def test_spec_digest_is_content_derived() -> None:
    base = _inception_spec(ETF)

    assert _inception_spec(ETF).digest() == base.digest()
    assert _inception_spec(ETF2).digest() != base.digest()
    assert _inception_spec(ETF, ETF2, kind=ETF_UNIVERSE).digest() != base.digest()
    assert _annual_spec().digest().startswith("sha256:")


def test_fixed_spec_weights_are_equal_and_canonical() -> None:
    spec = _inception_spec(ETF, ETF2, kind=ETF_UNIVERSE)

    weights = spec.weights()

    assert weights[ETF] == Decimal("0.5")
    assert weights[ETF2] == Decimal("0.5")
    assert sum(weights.values(), Decimal("0")) == Decimal("1")
    assert list(weights) == sorted(weights)
    assert spec.sleeve is SleeveId.CORE


def test_inception_target_addresses_each_instrument_once() -> None:
    spec = _inception_spec(ETF, ETF2, kind=ETF_UNIVERSE)

    targets = spec.inception_target(date(2024, 1, 2))

    assert len(targets) == 2
    assert {target.instrument_id for target in targets} == {ETF, ETF2}
    for target in targets:
        assert target.target_weight == Decimal("0.5")
        assert target.sleeve is SleeveId.CORE
        assert target.strategy_id.startswith("benchmark:")


# --- inception benchmark target source --------------------------------------------


def test_inception_source_contributes_once_then_stays_silent() -> None:
    inception = date(2024, 1, 2)
    source = BenchmarkTargetSource(_inception_spec(ETF), inception)

    at_inception = source.contributions_for(_context(inception, date(2024, 1, 3)))
    assert at_inception is not None
    assert [target.target_weight for target in at_inception] == [Decimal("1")]
    assert at_inception[0].instrument_id == ETF

    assert source.contributions_for(_context(date(2024, 1, 3), date(2024, 1, 4))) is None
    assert source.contributions_for(_context(date(2024, 2, 29), date(2024, 3, 1))) is None


def test_benchmark_runs_through_the_same_kernel_with_the_same_costs(
    bar_factory,
    tradability_factory,
    calendar_factory,
    research_clock,
    research_master,
    account_fees_factory,
    execution_model_factory,
) -> None:
    """The benchmark is a kernel run, not a percentage: the same calendar,
    fees, and execution model produce one planned order, one T+1 open fill
    with commission, and a held position."""
    sessions = (date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4), date(2024, 1, 5))
    closes = ("2.00", "2.01", "2.02", "2.03")
    bars = tuple(
        bar_factory(
            ETF,
            session_date,
            open=closes[index],
            close=closes[index],
            pre_close=closes[index - 1] if index else None,
        )
        for index, session_date in enumerate(sessions)
    )
    engine = DailyBarEngine(
        calendar=calendar_factory("XSHG", sessions),
        clock=research_clock,
        master=research_master,
        account_fees=account_fees_factory("0.00025", "5"),
        execution_model=execution_model_factory("0.0005"),
        bars=bars,
        tradability=tuple(
            tradability_factory(ETF, session_date) for session_date in sessions
        ),
        corporate_actions=(),
        target_source=BenchmarkTargetSource(_inception_spec(ETF), sessions[0]),
        initial_cash=Money(Decimal("100000")),
    )

    result = engine.run(start_session=sessions[0], end_session=sessions[-1])

    assert len(result.orders) == 1
    assert len(result.fills) == 1
    fill = result.fills[0]
    # T+1 open reference with the same slippage any strategy pays.
    assert fill.reference_open == Decimal("2.01")
    assert fill.fill_price > fill.reference_open
    assert fill.fees.commission.amount > 0
    assert any(
        position.instrument_id == ETF and position.total_quantity > 0
        for position in result.positions
    )
    assert result.cash.amount < Decimal("100000")


# --- annual PIT cohort benchmark ---------------------------------------------------


def test_stock_annual_inception_sessions_picks_first_open_session_per_year() -> None:
    session_dates = (
        date(2023, 12, 29),
        date(2024, 1, 2),
        date(2024, 1, 3),
        date(2024, 6, 5),
        date(2025, 1, 2),
        date(2025, 3, 3),
    )

    assert stock_annual_inception_sessions(
        session_dates, basic_start=date(2024, 1, 2), basic_end=date(2025, 6, 30)
    ) == (date(2024, 1, 2), date(2025, 1, 2))
    assert stock_annual_inception_sessions(
        session_dates, basic_start=date(2024, 1, 3), basic_end=date(2025, 6, 30)
    ) == (date(2024, 1, 3), date(2025, 1, 2))


def test_stock_annual_source_targets_cohort_and_exits_departed_holdings() -> None:
    schedule = _annual_schedule()
    source = StockAnnualBenchmarkTargetSource(
        _annual_spec(), schedule, (date(2021, 1, 4), date(2022, 1, 3))
    )
    held = (_position("XSHG:600003"), _position("XSHG:600099"))

    first = source.contributions_for(_context(date(2021, 1, 4), date(2021, 1, 5), positions=held))
    assert first is not None
    weights = {contribution.instrument_id: contribution.target_weight for contribution in first}
    assert set(weights) == {
        InstrumentId.parse("XSHG:600001"),
        InstrumentId.parse("XSHG:600002"),
        InstrumentId.parse("XSHG:600003"),
        InstrumentId.parse("XSHG:600099"),
    }
    for symbol in ("XSHG:600001", "XSHG:600002", "XSHG:600003"):
        contribution = next(
            item for item in first if item.instrument_id == InstrumentId.parse(symbol)
        )
        assert contribution.target_weight == Decimal("1") / Decimal("3")
        assert contribution.sleeve is SleeveId.SATELLITE
        assert contribution.strategy_id == "benchmark:stock_annual_schedule_equal_weight"
    assert weights[InstrumentId.parse("XSHG:600099")] == Decimal("0")

    second = source.contributions_for(_context(date(2022, 1, 3), date(2022, 1, 4), positions=held))
    assert second is not None
    second_weights = {
        contribution.instrument_id: contribution.target_weight for contribution in second
    }
    assert second_weights[InstrumentId.parse("XSHG:600004")] == Decimal("1") / Decimal("3")
    assert second_weights[InstrumentId.parse("XSHG:600003")] == Decimal("0")
    assert second_weights[InstrumentId.parse("XSHG:600099")] == Decimal("0")

    assert (
        source.contributions_for(
            _context(date(2021, 6, 1), date(2021, 6, 2), positions=held)
        )
        is None
    )


def test_stock_annual_source_requires_annual_spec_kind() -> None:
    with pytest.raises(UnsupportedBenchmarkError):
        StockAnnualBenchmarkTargetSource(_inception_spec(ETF), _annual_schedule(), ())


# --- CASH_0 comparator --------------------------------------------------------------


def test_cash_0_is_exactly_zero_and_not_a_kernel_participant() -> None:
    assert CASH_0.LABEL == "CASH_0"
    assert CASH_0.total_return() == Decimal("0")
    assert CASH_0.cagr() == Decimal("0")
    assert CASH_0.max_drawdown() == Decimal("0")
    # Not an instrument, not a spec, and not a kernel target source: cash
    # stays cash and is never run through the engine.
    assert not hasattr(CASH_0, "instrument_ids")
    assert not callable(getattr(CASH_0, "contributions_for", None))
