"""Unit tests: performance metrics over immutable NAV series and ledgers.

Expected values are hand-calculated from the documented conventions
(daily close-to-close returns, 252-session annualization, zero risk-free and
Sortino target, sample standard deviation, actual-calendar-day CAGR,
half-gross-notional turnover). Tests declare the tolerance used per statistic;
no expected value is generated from the implementation under test.
"""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from systematic_investing import DEFAULT_INITIAL_CAPITAL
from systematic_investing.domain.identifiers import Exchange, InstrumentId
from systematic_investing.domain.ledger import (
    CashLedgerCategory,
    CashLedgerEntry,
    IncompleteValuationReason,
    NavPoint,
    StaleMark,
    ValuationStatus,
)
from systematic_investing.domain.money import Money
from systematic_investing.metrics.performance import (
    BenchmarkIdentity,
    IncompleteNavError,
    InsufficientHistoryError,
    InvalidNavSeriesError,
    MetricConventions,
    ReturnBasis,
    TerminalMode,
    UnsupportedBenchmarkError,
    average_equity,
    cagr,
    calmar,
    compute_metrics,
    cost_drag,
    daily_close_returns,
    drawdown_series,
    gross_traded_notional,
    max_drawdown,
    sample_volatility,
    sharpe,
    sortino,
    total_costs,
    total_return,
    turnover,
    underwater_duration,
)

MARKET_TZ = timezone(timedelta(hours=8))
RECORDED_AT = datetime(2026, 9, 11, 18, 5, tzinfo=MARKET_TZ)

INSTRUMENT = "XSHG:510300"


def cash_entry(
    category: CashLedgerCategory, amount: str, day: int, *, month: int = 9
) -> CashLedgerEntry:
    return CashLedgerEntry(
        entry_id=f"{category.value}:{day}:{amount}",
        category=category,
        amount=Money(Decimal(amount)),
        session_date=date(2026, month, day),
        recorded_at=RECORDED_AT,
        source_id=f"fill-{day}",
    )


def nav_point(
    day: int,
    nav: str,
    *,
    month: int = 9,
    year: int = 2026,
    stale_marks: tuple[StaleMark, ...] = (),
    incomplete_reasons: tuple[IncompleteValuationReason, ...] = (),
) -> NavPoint:
    nav_value = Decimal(nav)
    total_equity = nav_value * DEFAULT_INITIAL_CAPITAL
    return NavPoint(
        session_date=date(year, month, day),
        cash=Money(total_equity),
        market_value=Money(Decimal("0")),
        total_equity=Money(total_equity),
        nav=nav_value,
        valuation_status=(
            ValuationStatus.INCOMPLETE if incomplete_reasons else ValuationStatus.COMPLETE
        ),
        stale_marks=stale_marks,
        incomplete_reasons=incomplete_reasons,
    )


def observed_series() -> tuple[NavPoint, ...]:
    return tuple(
        nav_point(day, nav)
        for day, nav in (
            (1, "1.00"),
            (2, "1.20"),
            (3, "0.90"),
            (4, "1.10"),
            (5, "1.00"),
        )
    )


def annual_series() -> tuple[NavPoint, ...]:
    return (
        nav_point(1, "1.00", month=1, year=2026),
        nav_point(1, "1.10", month=1, year=2027),
    )


def two_year_series() -> tuple[NavPoint, ...]:
    return (
        nav_point(1, "1.00", month=1, year=2026),
        nav_point(1, "1.21", month=1, year=2028),
    )


def assert_relative_close(
    actual: Decimal,
    expected: Decimal,
    tolerance: Decimal = Decimal("1e-15"),
) -> None:
    assert abs(actual / expected - Decimal(1)) <= tolerance, f"{actual} != {expected}"


class TestDailyCloseReturns:
    def test_maps_consecutive_close_to_close_observations(self) -> None:
        returns = daily_close_returns(observed_series())

        assert len(returns) == 4
        assert returns[0] == Decimal("0.2")
        assert returns[1] == Decimal("-0.25")
        assert_relative_close(returns[2], Decimal("0.22222222222222222222222222222"))
        assert_relative_close(returns[3], Decimal("-0.090909090909090909090909090909"))

    def test_result_is_independent_of_input_ordering(self) -> None:
        points = observed_series()

        ordered = daily_close_returns(points)
        shuffled = daily_close_returns((points[2], points[0], points[4], points[1], points[3]))

        assert shuffled == ordered

    def test_duplicate_sessions_are_rejected(self) -> None:
        points = observed_series()
        duplicate = (points[0], points[0], points[1])

        with pytest.raises(InvalidNavSeriesError, match="duplicate"):
            daily_close_returns(duplicate)

    def test_incomplete_portfolio_nav_is_refused(self) -> None:
        points = observed_series()
        broken = (
            points[0],
            nav_point(
                2,
                "1.20",
                incomplete_reasons=(IncompleteValuationReason.NO_DEFENSIBLE_PRICE,),
            ),
            points[2],
        )

        with pytest.raises(IncompleteNavError, match="NO_DEFENSIBLE_PRICE"):
            daily_close_returns(broken)


class TestReturnStatistics:
    def test_total_return_is_ending_over_beginning_minus_one(self) -> None:
        assert total_return(annual_series()) == Decimal("0.10")
        assert total_return(observed_series()) == Decimal("0")

    def test_cagr_annualizes_over_actual_calendar_days(self) -> None:
        # 2026-01-01 to 2027-01-01 is exactly 365 calendar days: CAGR == 10%.
        assert cagr(annual_series()) == Decimal("0.10")
        # 2026-01-01 to 2028-01-01 is 730 days: sqrt(1.21) - 1 == 10%.
        assert cagr(two_year_series()) == Decimal("0.10")

    def test_cagr_refuses_single_observation_history(self) -> None:
        with pytest.raises(InsufficientHistoryError):
            cagr((nav_point(1, "1.00"),))

    def test_sample_volatility_is_annualized_by_252_sessions(self) -> None:
        returns = (
            Decimal("0.01"),
            Decimal("-0.02"),
            Decimal("0.03"),
            Decimal("0.00"),
        )

        actual = sample_volatility(returns)

        assert_relative_close(actual, Decimal("0.3304542328371661212363485262523244082567"))
        assert actual < Decimal("1")

    def test_volatility_refuses_a_single_return(self) -> None:
        with pytest.raises(InsufficientHistoryError, match="sample"):
            sample_volatility((Decimal("0.01"),))

    def test_sharpe_uses_zero_risk_free_and_252_annualization(self) -> None:
        returns = (
            Decimal("0.01"),
            Decimal("-0.02"),
            Decimal("0.03"),
            Decimal("0.00"),
        )

        actual = sharpe(returns)

        assert actual is not None
        assert_relative_close(actual, Decimal("3.812933455813455245034790687526820095271"))

    def test_sharpe_is_undefined_without_volatility(self) -> None:
        returns = (Decimal("0.01"), Decimal("0.01"), Decimal("0.01"))

        assert sharpe(returns) is None

    def test_sortino_uses_zero_target_and_downside_deviation(self) -> None:
        returns = (
            Decimal("0.01"),
            Decimal("-0.02"),
            Decimal("0.03"),
            Decimal("0.00"),
        )

        actual = sortino(returns)

        assert actual is not None
        assert_relative_close(actual, Decimal("7.937253933193771771504847260917781277130"))

    def test_sortino_is_undefined_without_downside_deviation(self) -> None:
        returns = (Decimal("0.01"), Decimal("0.02"), Decimal("0.03"))

        assert sortino(returns) is None


def drawdown_series_points() -> tuple[NavPoint, ...]:
    # A week with a weekend gap: 09-03 falls below the 09-02 peak, recovers
    # on 09-07, and the final observation stays below the 09-07 peak.
    return (
        nav_point(1, "1.00"),
        nav_point(2, "1.20"),
        nav_point(3, "1.10"),
        nav_point(4, "1.15"),
        nav_point(7, "1.30"),
        nav_point(8, "1.25"),
    )


def calmar_series() -> tuple[NavPoint, ...]:
    # 365 calendar days, ending 10% above the start, with a mid-path peak.
    return (
        nav_point(1, "1.00", month=1, year=2026),
        nav_point(1, "1.20", month=7, year=2026),
        nav_point(1, "1.10", month=1, year=2027),
    )


class TestDrawdownAndUnderwater:
    def test_drawdown_series_measures_decline_from_the_running_peak(self) -> None:
        drawdowns = drawdown_series(drawdown_series_points())

        assert drawdowns[0] == Decimal("0")
        assert drawdowns[1] == Decimal("0")
        assert_relative_close(drawdowns[2], Decimal("-1") / Decimal("12"))
        assert_relative_close(drawdowns[3], Decimal("-1") / Decimal("24"))
        assert drawdowns[4] == Decimal("0")
        assert_relative_close(drawdowns[5], Decimal("-1") / Decimal("26"))

    def test_max_drawdown_is_the_deepest_running_peak_decline(self) -> None:
        actual = max_drawdown(drawdown_series_points())

        # Division-derived statistic: tolerance 1e-24 (declared per statistic).
        assert_relative_close(
            actual, Decimal("-1") / Decimal("12"), tolerance=Decimal("1e-24")
        )

    def test_underwater_duration_reports_sessions_and_calendar_days(self) -> None:
        duration = underwater_duration(drawdown_series_points())

        assert duration.sessions == 2
        assert duration.calendar_days == 4

    def test_underwater_duration_of_a_never_recovered_tail_runs_to_the_end(self) -> None:
        points = (
            nav_point(1, "1.00"),
            nav_point(2, "1.50"),
            nav_point(3, "1.40"),
            nav_point(4, "1.30"),
        )

        duration = underwater_duration(points)

        # One session step (09-03 to 09-04) below the 1.50 peak, unrecovered.
        assert duration.sessions == 1
        assert duration.calendar_days == 1

    def test_calmar_divides_cagr_by_absolute_max_drawdown(self) -> None:
        # CAGR == 10% and the deepest decline is 1.20 -> 1.10 (1/12).
        assert calmar(calmar_series()) == Decimal("1.2")

    def test_calmar_is_undefined_without_a_drawdown(self) -> None:
        assert calmar(annual_series()) is None


class TestTurnover:
    def test_turnover_is_half_gross_notional_over_average_equity(self) -> None:
        points = (
            nav_point(1, "1.00"),
            nav_point(2, "1.10"),
            nav_point(3, "1.00"),
        )
        entries = (
            cash_entry(CashLedgerCategory.BUY_CONSIDERATION, "-30000", 1),
            cash_entry(CashLedgerCategory.SELL_PROCEEDS, "20000", 2),
            cash_entry(CashLedgerCategory.BROKER_COMMISSION, "-20", 2),
        )

        actual = turnover(points, entries)

        # 0.5 * 50000 / (310000 / 3) == 75000 / 310000 == 15 / 62.
        assert actual == Decimal("15") / Decimal("62")

    def test_average_equity_is_the_mean_of_observed_equity(self) -> None:
        points = (
            nav_point(1, "1.00"),
            nav_point(2, "1.10"),
            nav_point(3, "1.00"),
        )

        assert average_equity(points) == Money(Decimal("310000") / Decimal("3"))

    def test_cost_entries_do_not_change_gross_traded_notional(self) -> None:
        entries = (
            cash_entry(CashLedgerCategory.BUY_CONSIDERATION, "-30000", 1),
            cash_entry(CashLedgerCategory.SELL_PROCEEDS, "20000", 2),
            cash_entry(CashLedgerCategory.BROKER_COMMISSION, "-20", 2),
            cash_entry(CashLedgerCategory.STAMP_TAX, "-10", 2),
            cash_entry(CashLedgerCategory.TRANSFER_FEE, "-1", 2),
        )

        assert gross_traded_notional(entries) == Money(Decimal("50000"))
        assert total_costs(entries) == Money(Decimal("31"))

    def test_non_positive_nav_history_is_refused(self) -> None:
        points = (nav_point(1, "1.00"), nav_point(2, "0.00"))

        with pytest.raises(InvalidNavSeriesError, match="positive"):
            daily_close_returns(points)


class TestCostDrag:
    def test_compares_gross_and_net_performance_under_the_same_fills(self) -> None:
        points = (nav_point(1, "1.00"), nav_point(2, "0.99"))
        entries = (
            cash_entry(CashLedgerCategory.BUY_CONSIDERATION, "-30000", 2),
            cash_entry(CashLedgerCategory.SELL_PROCEEDS, "30000", 2),
            cash_entry(CashLedgerCategory.BROKER_COMMISSION, "-20", 2),
            cash_entry(CashLedgerCategory.STAMP_TAX, "-10", 2),
        )

        drag = cost_drag(points, entries)

        assert drag.net_total_return == Decimal("-0.01")
        assert drag.gross_total_return == Decimal("-0.0097")
        assert drag.drag == Decimal("0.0003")
        assert drag.total_costs == Money(Decimal("30"))

    def test_costs_recorded_after_the_final_observation_are_excluded(self) -> None:
        points = (nav_point(1, "1.00"), nav_point(2, "0.99"))
        entries = (cash_entry(CashLedgerCategory.BROKER_COMMISSION, "-20", 3),)

        drag = cost_drag(points, entries)

        assert drag.gross_total_return == drag.net_total_return
        assert drag.drag == Decimal("0")

    def test_no_modeled_costs_means_no_drag(self) -> None:
        drag = cost_drag(observed_series(), ())

        assert drag.total_costs == Money(Decimal("0"))
        assert drag.drag == Decimal("0")


class TestStaleAndIncompleteValuation:
    def stale_mark(self) -> StaleMark:
        return StaleMark(
            instrument_id=InstrumentId(exchange=Exchange.XSHG, symbol="510300"),
            marked_price=Decimal("4.00"),
            last_valid_session=date(2026, 8, 28),
            age_sessions=5,
        )

    def test_stale_mark_nav_is_retained_and_reported(self) -> None:
        stale = self.stale_mark()
        points = (
            nav_point(1, "1.00"),
            nav_point(2, "1.10", stale_marks=(stale,)),
            nav_point(3, "1.00"),
        )

        report = compute_metrics(points)

        assert report.stale_observation_count == 1
        assert report.stale_marks == (stale,)
        assert report.total_return == Decimal("0")

    def test_truly_incomplete_nav_is_refused_with_its_reasons(self) -> None:
        points = (
            nav_point(1, "1.00"),
            nav_point(
                2,
                "1.10",
                incomplete_reasons=(
                    IncompleteValuationReason.CORPORATE_ACTION_INVALIDATED_PRICE,
                ),
            ),
            nav_point(3, "1.00"),
        )

        with pytest.raises(IncompleteNavError, match="CORPORATE_ACTION_INVALIDATED_PRICE"):
            compute_metrics(points)


class TestConventionsAndIdentity:
    def test_defaults_match_the_m0_metric_decisions(self) -> None:
        conventions = MetricConventions()

        assert conventions.convention_version == "M0-METRICS-1"
        assert conventions.return_basis is ReturnBasis.DAILY_CLOSE_TO_CLOSE
        assert conventions.annualization_sessions == 252
        assert conventions.risk_free_rate == Decimal("0")
        assert conventions.sortino_target == Decimal("0")
        assert conventions.volatility_basis == "SAMPLE_STANDARD_DEVIATION"
        assert conventions.cagr_basis == "ACTUAL_CALENDAR_DAYS"
        assert conventions.turnover_basis == "HALF_GROSS_NOTIONAL_OVER_AVERAGE_EQUITY"
        assert conventions.underwater_units == ("SESSIONS", "CALENDAR_DAYS")
        assert conventions.benchmark is BenchmarkIdentity.NONE
        assert conventions.terminal_mode is TerminalMode.MARK_TO_MARKET

    def test_benchmark_identity_accepts_only_the_m0_values(self) -> None:
        synthetic = MetricConventions(benchmark=BenchmarkIdentity.SYNTHETIC_TEST_BENCHMARK)

        assert synthetic.benchmark is BenchmarkIdentity.SYNTHETIC_TEST_BENCHMARK
        with pytest.raises(UnsupportedBenchmarkError, match="CSI300"):
            MetricConventions(benchmark="CSI300")

    def test_convention_digest_changes_with_any_convention_change(self) -> None:
        baseline = MetricConventions().digest()

        assert MetricConventions().digest() == baseline
        assert (
            MetricConventions(risk_free_rate=Decimal("0.01")).digest() != baseline
        )
        assert MetricConventions(annualization_sessions=250).digest() != baseline
        assert (
            MetricConventions(benchmark=BenchmarkIdentity.SYNTHETIC_TEST_BENCHMARK).digest()
            != baseline
        )
        assert (
            MetricConventions(terminal_mode=TerminalMode.FORCED_LIQUIDATION).digest()
            != baseline
        )
        assert MetricConventions(convention_version="M0-METRICS-2").digest() != baseline

    def test_manifest_fields_record_benchmark_and_terminal_mode(self) -> None:
        conventions = MetricConventions(
            benchmark=BenchmarkIdentity.SYNTHETIC_TEST_BENCHMARK,
            terminal_mode=TerminalMode.FORCED_LIQUIDATION,
        )

        fields = conventions.as_manifest_fields()

        assert fields["benchmark"] == "SYNTHETIC_TEST_BENCHMARK"
        assert fields["terminal_mode"] == "FORCED_LIQUIDATION"
        assert fields["annualization_sessions"] == 252
        assert fields["conventions_digest"] == conventions.digest()


class TestMetricsReport:
    def test_report_statistics_match_hand_calculated_values(self) -> None:
        report = compute_metrics(observed_series())

        assert report.observation_count == 5
        assert report.first_session == date(2026, 9, 1)
        assert report.last_session == date(2026, 9, 5)
        assert report.total_return == Decimal("0")
        assert report.cagr == Decimal("0")
        assert report.turnover == Decimal("0")
        assert report.sharpe is not None
        assert report.sortino is not None
        assert report.max_drawdown == Decimal("-0.25")
        # Peaks at 1.20 on 09-02; 09-03..09-05 stay below it, unrecovered.
        assert report.underwater.sessions == 2
        assert report.underwater.calendar_days == 2

    def test_report_refuses_short_history(self) -> None:
        with pytest.raises(InsufficientHistoryError):
            compute_metrics((nav_point(1, "1.00"), nav_point(2, "1.10")))

    def test_report_includes_cost_drag_over_the_supplied_ledger(self) -> None:
        points = (nav_point(1, "1.00"), nav_point(2, "0.99"), nav_point(3, "0.98"))
        entries = (cash_entry(CashLedgerCategory.BROKER_COMMISSION, "-20", 2),)

        report = compute_metrics(points, cash_entries=entries)

        assert report.cost_drag.total_costs == Money(Decimal("20"))
        assert report.cost_drag.drag > 0

    def test_report_records_the_declared_terminal_mode(self) -> None:
        conventions = MetricConventions(terminal_mode=TerminalMode.FORCED_LIQUIDATION)

        report = compute_metrics(observed_series(), conventions=conventions)

        assert report.conventions.terminal_mode is TerminalMode.FORCED_LIQUIDATION

    def test_report_threads_declared_annualization_into_statistics(self) -> None:
        baseline = compute_metrics(observed_series())
        halved = compute_metrics(
            observed_series(),
            conventions=MetricConventions(annualization_sessions=126),
        )

        assert halved.volatility < baseline.volatility
        assert_relative_close(
            halved.volatility,
            baseline.volatility * (Decimal("126") / Decimal("252")).sqrt(),
        )
