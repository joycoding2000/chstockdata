"""Golden tests: hand-calculated scenarios G01-G21 (test-plan section 4).

Every scenario is declared under ``tests/fixtures/golden/GNN`` with its
predetermined target, frozen market facts, and a README that contains the
manual calculation. Expected values were reviewed by hand from the declared
facts and the architecture semantics; the kernel never generates its own
oracle. The driver below is a test-only predetermined-target driver and is
explicitly not a strategy.
"""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from golden_harness import (
    PredeterminedTargetDriver,
    assert_expected,
    assert_metrics_path_expected,
    assert_scenario_files,
    discover_scenarios,
    draft_executable,
    load_scenario,
    normalized_digest,
    normalized_metrics_path,
    normalized_output,
    run_metrics_path,
    run_scenario,
)

from systematic_investing.backtest.engine import DecisionBlockReason
from systematic_investing.data.quality import (
    REASON_UNKNOWN_INSTRUMENT_CLASSIFICATION,
    DataQualityGate,
    DatasetPolicy,
    GateAction,
    GateStatus,
)
from systematic_investing.domain.execution import OrderStatus
from systematic_investing.domain.identifiers import Exchange, InstrumentId, SleeveId
from systematic_investing.domain.ledger import CashLedgerCategory
from systematic_investing.domain.market import AvailabilityBasis
from systematic_investing.domain.money import Money
from systematic_investing.domain.runs import RunPurpose
from systematic_investing.instrument_master.models import AdjudicationStatus
from systematic_investing.metrics.performance import (
    IncompleteNavError,
    TerminalMode,
    compute_metrics,
)

XSHG_510300 = InstrumentId(exchange=Exchange.XSHG, symbol="510300")
XSHG_510500 = InstrumentId(exchange=Exchange.XSHG, symbol="510500")
XSHG_511010 = InstrumentId(exchange=Exchange.XSHG, symbol="511010")
XSHG_518880 = InstrumentId(exchange=Exchange.XSHG, symbol="518880")
XSHG_600519 = InstrumentId(exchange=Exchange.XSHG, symbol="600519")
XSHE_000001 = InstrumentId(exchange=Exchange.XSHE, symbol="000001")

S_0910 = date(2026, 9, 10)
S_0911 = date(2026, 9, 11)
S_0914 = date(2026, 9, 14)
S_0915 = date(2026, 9, 15)

DECISION_CUTOFF_0911 = datetime(2026, 9, 11, 15, 30, tzinfo=UTC)

SCENARIOS = discover_scenarios()


def test_scenario_index_covers_g01_through_g21() -> None:
    assert tuple(f"G{index:02d}" for index in range(1, 22)) == SCENARIOS


def test_golden_driver_is_documented_as_a_non_strategy() -> None:
    doc = PredeterminedTargetDriver.__doc__ or ""
    assert "not a strategy" in doc.lower()


@pytest.mark.parametrize("scenario_id", SCENARIOS)
def test_scenario_manifest_and_expected_outputs_are_complete(scenario_id: str) -> None:
    scenario = load_scenario(scenario_id)

    assert_scenario_files(scenario)
    assert scenario.payload["schema_version"] == "golden-scenario-v1"
    assert scenario.expected["schema_version"] == "golden-expected-v1"


@pytest.mark.parametrize("scenario_id", SCENARIOS)
def test_scenario_matches_its_hand_calculated_expectations(scenario_id: str) -> None:
    scenario = load_scenario(scenario_id)

    for run_name in scenario.expected["runs"]:
        if scenario.kind == "metrics":
            outcome = run_metrics_path(scenario, run_name=run_name)
            assert_metrics_path_expected(outcome, scenario.expected["runs"][run_name])
            continue
        outcome = run_scenario(scenario, run_name=run_name)
        assert_expected(outcome, scenario.expected["runs"][run_name])


@pytest.mark.parametrize("scenario_id", SCENARIOS)
def test_scenario_runs_are_deterministic_in_process(scenario_id: str) -> None:
    scenario = load_scenario(scenario_id)

    for run_name in scenario.expected["runs"]:
        if scenario.kind == "metrics":
            first = normalized_metrics_path(run_metrics_path(scenario, run_name=run_name))
            second = normalized_metrics_path(run_metrics_path(scenario, run_name=run_name))
            assert first == second
            continue
        first = run_scenario(scenario, run_name=run_name)
        second = run_scenario(scenario, run_name=run_name)

        first_normalized = normalized_output(first)
        second_normalized = normalized_output(second)

        assert first_normalized == second_normalized
        assert normalized_digest(first) == normalized_digest(second)


@pytest.mark.parametrize("scenario_id", SCENARIOS)
def test_scenario_runs_never_produce_negative_cash(scenario_id: str) -> None:
    scenario = load_scenario(scenario_id)
    if scenario.kind == "metrics":
        return

    for run_name in scenario.run_names:
        outcome = run_scenario(scenario, run_name=run_name)

        assert outcome.result.cash.amount >= 0
        for record in outcome.result.sessions:
            assert record.snapshot.cash.amount >= 0


class TestG03ResidualCash:
    def test_residual_cash_and_executable_weight_are_explicit(self) -> None:
        outcome = run_scenario(load_scenario("G03"))

        draft = draft_executable(outcome)

        position = draft.positions[0]
        assert position.theoretical_weight == Decimal("0.05")
        assert position.executable_weight == Decimal("0.048")
        assert position.planned_quantity == 400
        assert position.sizing_reference_price == Decimal("12.00")
        assert draft.residual_cash == Money(Decimal("95194.95"))


class TestG04StockCosts:
    def test_itemized_cash_entries_and_effective_dated_market_provenance(self) -> None:
        outcome = run_scenario(load_scenario("G04"))

        totals: dict[CashLedgerCategory, Decimal] = {}
        for entry in outcome.result.cash_entries:
            totals.setdefault(entry.category, Decimal("0"))
            totals[entry.category] += entry.amount.amount
        assert totals[CashLedgerCategory.BUY_CONSIDERATION] == Decimal("-14544.00")
        assert totals[CashLedgerCategory.SELL_PROCEEDS] == Decimal("15096.00")
        assert totals[CashLedgerCategory.BROKER_COMMISSION] == Decimal("-10.00")
        assert totals[CashLedgerCategory.STAMP_TAX] == Decimal("-7.55")
        assert totals[CashLedgerCategory.TRANSFER_FEE] == Decimal("-0.30")

        rules = outcome.master.resolve_rules(XSHE_000001, S_0914)
        assert rules.market_fee_tax.profile_id == "FEE:TAX-A-STANDARD"
        assert rules.market_fee_tax.stamp_tax_sell_rate == Decimal("0.0005")
        assert rules.market_fee_tax.transfer_fee_rate == Decimal("0.00001")
        assert rules.market_fee_tax.source.authority == "MOF/STA"


class TestG05EtfFeeProfiles:
    def test_each_subtype_uses_its_own_approved_market_fee_family(self) -> None:
        outcome = run_scenario(load_scenario("G05"))

        profiles = {
            str(instrument_id): outcome.master.resolve_rules(instrument_id, S_0911).market_fee_tax
            for instrument_id in (XSHG_510300, XSHG_511010, XSHG_518880)
        }

        assert profiles["XSHG:510300"].profile_id == "FEE:TAX-ETF-EQUITY"
        assert profiles["XSHG:518880"].profile_id == "FEE:TAX-ETF-GOLD"
        assert profiles["XSHG:511010"].profile_id == "FEE:TAX-ETF-BOND"
        for profile in profiles.values():
            assert profile.stamp_tax_sell_rate == Decimal("0")
            assert profile.transfer_fee_rate == Decimal("0")


class TestG09Settlement:
    def test_sellable_dates_are_profile_driven(self) -> None:
        outcome = run_scenario(load_scenario("G09"))

        lots = {
            position.instrument_id: position.lots[0]
            for position in outcome.result.session(S_0911).snapshot.positions
        }

        assert lots[XSHE_000001].sellable_from == S_0914
        assert lots[XSHG_510500].sellable_from == S_0915


class TestG10NoLookahead:
    def test_mutating_future_bars_cannot_change_the_t_decision(self) -> None:
        scenario = load_scenario("G10")
        baseline = run_scenario(scenario)
        mutated = run_scenario(
            scenario,
            bar_overrides={
                ("XSHG:510300", "2026-09-14"): {"open": "4.80", "close": "5.20"},
                ("XSHG:510300", "2026-09-15"): {"open": "5.50", "close": "5.50"},
            },
        )

        reference = baseline.result.session(S_0911)
        other = mutated.result.session(S_0911)
        assert reference.decision_digest == other.decision_digest
        assert reference.target == other.target
        assert reference.plans == other.plans
        assert baseline.result.content_digest() != mutated.result.content_digest()
        assert [probe["error"] for probe in baseline.driver.probe_results] == [
            "FutureDataAccessError",
            "FutureDataAccessError",
        ]


class TestG11CorporateAction:
    def test_dividend_is_credited_once_and_adjustment_never_double_counts(self) -> None:
        outcome = run_scenario(load_scenario("G11"))

        dividends = [
            entry
            for entry in outcome.result.cash_entries
            if entry.category is CashLedgerCategory.DIVIDEND
        ]
        assert len(dividends) == 1
        assert dividends[0].amount == Money(Decimal("500.00"))
        assert dividends[0].session_date == S_0911

        bar = next(bar for bar in outcome.dataset.daily_bars if bar.session_date == S_0911)
        assert bar.adjustment_factor is not None
        assert bar.adjustment_factor.factor == Decimal("0.99")
        assert bar.close == Decimal("11.75")


class TestG13TerminalModes:
    def test_terminal_modes_have_distinct_identity_and_costs(self) -> None:
        scenario = load_scenario("G13")
        mark = run_scenario(scenario, run_name="mark_to_market")
        liquidation = run_scenario(scenario, run_name="forced_liquidation")

        assert mark.conventions.terminal_mode is TerminalMode.MARK_TO_MARKET
        assert liquidation.conventions.terminal_mode is TerminalMode.FORCED_LIQUIDATION
        assert mark.conventions.digest() != liquidation.conventions.digest()
        assert mark.result.fills == ()
        assert mark.result.cash_entries == ()
        assert len(liquidation.result.fills) == 1
        assert liquidation.result.cash_entries


class TestG14InputOrdering:
    def test_reordered_facts_do_not_change_the_run(self) -> None:
        scenario = load_scenario("G14")
        baseline = run_scenario(scenario)
        from systematic_investing.data.quality import CanonicalDataset

        reordered = CanonicalDataset(
            daily_bars=tuple(reversed(baseline.dataset.daily_bars)),
            sessions=baseline.dataset.sessions,
            tradability=tuple(reversed(baseline.dataset.tradability)),
            corporate_actions=(),
            rule_candidates=(),
        )

        shuffled = run_scenario(scenario, dataset=reordered)

        assert normalized_output(baseline) == normalized_output(shuffled)


class TestG15TargetCompleteness:
    def test_explicit_zero_exits_and_explicit_unchanged_has_no_delta(self) -> None:
        outcome = run_scenario(load_scenario("G15"), run_name="complete")

        decision = outcome.result.session(S_0911)
        target = decision.target
        assert target is not None
        assert target.addressed_instruments == frozenset(
            {XSHE_000001, XSHG_510300, XSHG_518880}
        )
        assert tuple(plan.instrument_id for plan in decision.plans) == (XSHE_000001,)
        assert decision.plans[0].target_weight == Decimal("0")
        assert decision.decision_blocked_reason is None

        final = {position.instrument_id: position for position in outcome.result.positions}
        assert XSHE_000001 not in final
        assert final[XSHG_510300].total_quantity == 1000
        assert final[XSHG_518880].total_quantity == 1000

    def test_absent_held_instrument_fails_the_complete_target_boundary(self) -> None:
        outcome = run_scenario(load_scenario("G15"), run_name="missing_target")

        decision = outcome.result.session(S_0911)
        target = decision.target
        assert target is not None
        assert XSHG_518880 not in target.addressed_instruments
        assert XSHG_510300 in target.addressed_instruments
        assert decision.decision_blocked_reason is DecisionBlockReason.TARGET_INCOMPLETE
        assert decision.plans == ()
        assert all(order.instrument_id != XSHG_518880 for order in outcome.result.orders)


class TestG16GapReduction:
    def test_affordable_open_keeps_the_t_decision_identical(self) -> None:
        scenario = load_scenario("G16")
        gap = run_scenario(scenario)
        affordable = run_scenario(
            scenario,
            bar_overrides={
                ("XSHE:000001", "2026-09-14"): {"open": "12.00", "close": "12.20"},
            },
        )

        assert (
            gap.result.session(S_0911).decision_digest
            == affordable.result.session(S_0911).decision_digest
        )
        assert gap.result.session(S_0911).plans == affordable.result.session(S_0911).plans

        order = next(
            order
            for order in gap.result.session(S_0914).activation.orders
            if order.instrument_id == XSHE_000001
        )
        assert order.planned_quantity == 200
        assert order.submitted_quantity == 100
        assert order.sizing_reference_price == Decimal("12.00")


class TestG17PointInTime:
    def test_decision_slice_uses_information_time_only(self) -> None:
        outcome = run_scenario(load_scenario("G17"))

        context = next(
            context for context in outcome.driver.contexts if context.session_date == S_0911
        )
        visible = {
            bar.instrument_id for bar in context.bars if bar.session_date == S_0911
        }
        assert visible == {XSHG_510300}
        assert [probe["error"] for probe in outcome.driver.probe_results] == [
            "UnknownFactError",
            "UnknownFactError",
        ]

        same_session_facts = [
            bar for bar in outcome.dataset.daily_bars if bar.session_date == S_0911
        ]
        assert len({bar.availability.retrieved_at for bar in same_session_facts}) == 1
        unknown = next(
            bar for bar in same_session_facts if bar.instrument_id == XSHG_511010
        )
        assert unknown.availability.availability_basis is AvailabilityBasis.UNKNOWN
        assert unknown.availability.information_available_at is None
        assert unknown.availability.information_known_at(DECISION_CUTOFF_0911) is None


class TestG18Authority:
    def test_provider_candidates_never_become_authority(self) -> None:
        scenario = load_scenario("G18")
        approved = run_scenario(scenario, run_name="approved_profile_governs")

        adjudication = approved.master.adjudicate_rule_candidate(
            approved.dataset.rule_candidates[0]
        )
        assert adjudication.status is AdjudicationStatus.APPROVED_PROFILE_GOVERNS
        assert adjudication.approved_rules is not None
        assert adjudication.approved_rules.lot.board_lot == 100
        assert approved.result.session(S_0914).activation.orders[0].planned_quantity == 100

        closed = run_scenario(scenario, run_name="fail_closed_unknown_profile")
        closed_adjudication = closed.master.adjudicate_rule_candidate(
            closed.dataset.rule_candidates[0]
        )
        assert (
            closed_adjudication.status
            is AdjudicationStatus.FAIL_CLOSED_NO_APPROVED_PROFILE
        )

        gate = DataQualityGate(closed.master, DatasetPolicy()).evaluate(
            closed.dataset,
            purpose=RunPurpose.DECISION,
            intended_decision_session=S_0911,
            information_cutoff=DECISION_CUTOFF_0911,
            evaluated_at=datetime(2026, 9, 11, 15, 35, tzinfo=UTC),
        )
        assert gate.status is GateStatus.FAIL
        assert gate.action is GateAction.BLOCK_NEW_TARGET
        assert REASON_UNKNOWN_INSTRUMENT_CLASSIFICATION in gate.reason_codes


class TestG19Sleeves:
    def test_sleeves_come_only_from_explicit_fields(self) -> None:
        outcome = run_scenario(load_scenario("G19"))

        target = outcome.result.session(S_0911).target
        assert target is not None
        assert target.sleeve_of(XSHG_600519) is SleeveId.CORE
        assert target.sleeve_weights == {
            SleeveId.CORE: Decimal("0.45"),
            SleeveId.SATELLITE: Decimal("0.15"),
        }
        assert target.weights_by_instrument[XSHG_511010] == Decimal("0.07")

        plans = {plan.instrument_id: plan for plan in outcome.result.session(S_0911).plans}
        assert plans[XSHG_511010].target_weight == Decimal("0.02")


class TestG20Valuation:
    def test_stale_nav_is_reportable_but_incomplete_nav_blocks_metrics(self) -> None:
        scenario = load_scenario("G20")
        stale = run_scenario(scenario, run_name="stale_mark")

        report = compute_metrics(
            [record.nav for record in stale.result.sessions],
            cash_entries=stale.result.cash_entries,
            conventions=stale.conventions,
        )
        assert report.stale_observation_count == 2
        assert sorted(mark.age_sessions for mark in report.stale_marks) == [1, 2]

        unpriceable = run_scenario(scenario, run_name="unpriceable")
        with pytest.raises(IncompleteNavError):
            compute_metrics([record.nav for record in unpriceable.result.sessions])


class TestG21InterveningAction:
    def test_intervening_split_keeps_the_locked_target_identity(self) -> None:
        scenario = load_scenario("G21")
        split = run_scenario(scenario, run_name="split_pending_exit")
        plain = run_scenario(scenario, run_name="no_action_variant")

        assert (
            split.result.session(S_0910).decision_digest
            == plain.result.session(S_0910).decision_digest
        )
        assert split.result.session(S_0910).target == plain.result.session(S_0910).target

        invalidated = split.result.session(S_0911).invalidated_orders[0]
        assert invalidated.status is OrderStatus.INVALIDATED
        assert "CORPORATE_ACTION_REPLAN_REQUIRED" in invalidated.reason_codes
        assert invalidated.planned_quantity == 1000
        assert invalidated.submitted_quantity is None
        assert split.result.session(S_0911).activation.orders == ()
        assert (
            plain.result.session(S_0911).activation.orders[0].submitted_quantity == 1000
        )
