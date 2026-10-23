"""Unit tests: deterministic risk rules and the transformation pipeline.

Covers: risk never increasing upstream theoretical exposure, cap/transform
with before/after values and reason codes, explicit rule order and versions,
deterministic CORE/SATELLITE sleeve caps, and veto (block) outcomes.
"""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from systematic_investing.domain.identifiers import Exchange, InstrumentId, SleeveId
from systematic_investing.domain.money import Money
from systematic_investing.domain.portfolio import TargetContribution, TheoreticalTargetPortfolio
from systematic_investing.risk.decisions import (
    RiskTransformation,
    RiskTransformationError,
    RiskTransformationStatus,
    SleeveCapRule,
)
from systematic_investing.risk.ports import RiskRuleOutcome, RiskRuleStatus

XSHG_510300 = InstrumentId(exchange=Exchange.XSHG, symbol="510300")
XSHG_518880 = InstrumentId(exchange=Exchange.XSHG, symbol="518880")
XSHE_159915 = InstrumentId(exchange=Exchange.XSHE, symbol="159915")

GENERATED_AT = datetime(2026, 9, 11, 17, 30, tzinfo=UTC)
CUTOFF = datetime(2026, 9, 11, 15, 0, tzinfo=UTC)


def contribution(instrument_id=XSHG_510300, sleeve=SleeveId.CORE, weight="0.45",
                 strategy="core-etf-alpha") -> TargetContribution:
    return TargetContribution(
        instrument_id=instrument_id,
        sleeve=sleeve,
        strategy_id=strategy,
        strategy_version="1.0.0",
        target_weight=Decimal(weight),
    )


def make_target(contributions=None) -> TheoreticalTargetPortfolio:
    return TheoreticalTargetPortfolio(
        target_id="target-2026-09-11",
        revision=1,
        decision_for_trade_date=date(2026, 9, 14),
        generated_at=GENERATED_AT,
        information_cutoff=CUTOFF,
        valuation_equity=Money(Decimal("100000")),
        contributions=contributions
        if contributions is not None
        else (
            contribution(),
            contribution(instrument_id=XSHG_518880, weight="0.15", strategy="core-gold"),
            contribution(
                instrument_id=XSHE_159915,
                sleeve=SleeveId.SATELLITE,
                weight="0.15",
                strategy="satellite-momentum",
            ),
        ),
    )


class IncreasingRule:
    """A rule that tries to raise exposure; the pipeline must refuse it."""

    rule_id = "RISK-EVIL"
    rule_version = "9.9.9"

    def evaluate(self, weights, sleeve_of) -> RiskRuleOutcome:  # type: ignore[no-untyped-def]
        after = {key: value + Decimal("0.01") for key, value in weights.items()}
        return RiskRuleOutcome(
            rule_id=self.rule_id,
            rule_version=self.rule_version,
            status=RiskRuleStatus.CAP_TRANSFORM,
            before_weights=tuple(sorted(weights.items())),
            after_weights=tuple(sorted(after.items())),
            reason_code="NOT_ALLOWED",
        )


class BlockingRule:
    rule_id = "RISK-KILL-SWITCH"
    rule_version = "1.0.0"

    def evaluate(self, weights, sleeve_of) -> RiskRuleOutcome:  # type: ignore[no-untyped-def]
        return RiskRuleOutcome(
            rule_id=self.rule_id,
            rule_version=self.rule_version,
            status=RiskRuleStatus.BLOCK,
            before_weights=tuple(sorted(weights.items())),
            after_weights=tuple(sorted(weights.items())),
            reason_code="STRATEGY_HEALTH_KILLED",
        )


class TestSleeveCapRule:
    def test_cap_within_limit_passes_unchanged(self) -> None:
        rule = SleeveCapRule(
            rule_id="RISK-SAT-CAP",
            rule_version="1.0.0",
            sleeve=SleeveId.SATELLITE,
            max_weight=Decimal("0.20"),
        )
        target = make_target()

        outcome = rule.evaluate(
            target.weights_by_instrument,
            {item: target.sleeve_of(item) for item in target.weights_by_instrument},
        )

        assert outcome.status is RiskRuleStatus.PASS
        assert outcome.after_weights == outcome.before_weights

    def test_cap_reduces_largest_positions_first_until_budget_exhausted(self) -> None:
        rule = SleeveCapRule(
            rule_id="RISK-SAT-CAP",
            rule_version="1.0.0",
            sleeve=SleeveId.SATELLITE,
            max_weight=Decimal("0.10"),
        )
        target = make_target()
        # Satellite sleeve holds only XSHE:159915 at 0.15; cap 0.10 must bind.
        satellite_id = XSHE_159915

        outcome = rule.evaluate(
            target.weights_by_instrument,
            {item: target.sleeve_of(item) for item in target.weights_by_instrument},
        )
        after = dict(outcome.after_weights)

        assert outcome.status is RiskRuleStatus.CAP_TRANSFORM
        assert after[satellite_id] == Decimal("0.10")
        assert outcome.reason_code == "SLEEVE_CAP_BOUND"
        assert dict(outcome.before_weights)[satellite_id] == Decimal("0.15")

    def test_cap_leaves_other_sleeves_untouched(self) -> None:
        rule = SleeveCapRule(
            rule_id="RISK-SAT-CAP",
            rule_version="1.0.0",
            sleeve=SleeveId.SATELLITE,
            max_weight=Decimal("0.05"),
        )
        target = make_target()

        outcome = rule.evaluate(
            target.weights_by_instrument,
            {item: target.sleeve_of(item) for item in target.weights_by_instrument},
        )
        after = dict(outcome.after_weights)

        assert after[XSHG_510300] == Decimal("0.45")
        assert after[XSHG_518880] == Decimal("0.15")
        assert after[XSHE_159915] == Decimal("0.05")


class TestRiskTransformation:
    def test_approved_weights_never_exceed_theoretical_exposure(self) -> None:
        transformation = RiskTransformation(
            rules=(
                SleeveCapRule("RISK-SAT-CAP", "1.0.0", SleeveId.SATELLITE, Decimal("0.10")),
            ),
            composition_version="m0-risk-1",
        )

        result = transformation.transform(make_target())

        assert result.status is RiskTransformationStatus.APPROVED
        approved = result.approved
        assert approved is not None
        for position in approved.positions:
            assert position.approved_weight <= position.theoretical_weight
        assert approved.approved_cash_weight >= make_target().cash_weight

    def test_rule_returning_an_increase_is_refused(self) -> None:
        transformation = RiskTransformation(
            rules=(IncreasingRule(),),
            composition_version="m0-risk-1",
        )

        with pytest.raises(RiskTransformationError):
            transformation.transform(make_target())

    def test_block_vetoes_the_target_without_an_approved_output(self) -> None:
        transformation = RiskTransformation(
            rules=(
                SleeveCapRule("RISK-SAT-CAP", "1.0.0", SleeveId.SATELLITE, Decimal("0.10")),
                BlockingRule(),
            ),
            composition_version="m0-risk-1",
        )

        result = transformation.transform(make_target())

        assert result.status is RiskTransformationStatus.BLOCKED
        assert result.approved is None
        assert result.blocking_rule_id == "RISK-KILL-SWITCH"
        assert result.block_reason_code == "STRATEGY_HEALTH_KILLED"
        # Earlier rule evaluations stay recorded for audit.
        assert [outcome.rule_id for outcome in result.applied_rules] == [
            "RISK-SAT-CAP",
            "RISK-KILL-SWITCH",
        ]

    def test_rule_order_and_versions_are_recorded_in_output(self) -> None:
        transformation = RiskTransformation(
            rules=(
                SleeveCapRule("RISK-CORE-CAP", "1.1.0", SleeveId.CORE, Decimal("0.65")),
                SleeveCapRule("RISK-SAT-CAP", "1.0.0", SleeveId.SATELLITE, Decimal("0.10")),
            ),
            composition_version="m0-risk-1",
        )

        result = transformation.transform(make_target())

        assert [(outcome.rule_id, outcome.rule_version) for outcome in result.applied_rules] == [
            ("RISK-CORE-CAP", "1.1.0"),
            ("RISK-SAT-CAP", "1.0.0"),
        ]
        assert result.composition_version == "m0-risk-1"

    def test_transformation_is_deterministic(self) -> None:
        transformation = RiskTransformation(
            rules=(
                SleeveCapRule("RISK-SAT-CAP", "1.0.0", SleeveId.SATELLITE, Decimal("0.10")),
            ),
            composition_version="m0-risk-1",
        )

        first = transformation.transform(make_target())
        second = transformation.transform(make_target())

        assert first == second

    def test_approved_target_retains_source_identity(self) -> None:
        transformation = RiskTransformation(
            rules=(),
            composition_version="m0-risk-1",
        )
        target = make_target()

        result = transformation.transform(target)

        approved = result.approved
        assert approved is not None
        assert approved.target_id == target.target_id
        assert approved.revision == target.revision
        assert approved.decision_for_trade_date == target.decision_for_trade_date
        assert approved.valuation_equity == target.valuation_equity
        assert approved.approved_cash_weight == target.cash_weight
