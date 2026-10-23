"""Unit tests: target contributions, the theoretical aggregate, completeness.

Covers: theoretical weights plus cash, zero versus absent targets, explicit
strategy/sleeve contributions, CORE/SATELLITE aggregation, held-instrument
completeness, long-only limits, immutable lock/revision identity, and content
digest determinism under input reordering.
"""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from systematic_investing.domain.identifiers import Exchange, InstrumentId, SleeveId
from systematic_investing.domain.money import Money
from systematic_investing.domain.portfolio import (
    WEIGHT_SUM_TOLERANCE,
    InvalidTargetError,
    TargetContribution,
    TheoreticalTargetPortfolio,
)
from systematic_investing.portfolio.validation import (
    TargetNotCompleteError,
    validate_target_completeness,
)

XSHG_510300 = InstrumentId(exchange=Exchange.XSHG, symbol="510300")
XSHE_159915 = InstrumentId(exchange=Exchange.XSHE, symbol="159915")
XSHG_518880 = InstrumentId(exchange=Exchange.XSHG, symbol="518880")

GENERATED_AT = datetime(2026, 9, 11, 17, 30, tzinfo=UTC)
INFORMATION_CUTOFF = datetime(2026, 9, 11, 15, 0, tzinfo=UTC)
EQUITY = Money(Decimal("100000"))


def contribution(instrument_id=XSHG_510300, sleeve=SleeveId.CORE, weight="0.60",
                 strategy="core-etf-alpha", version="1.0.0") -> TargetContribution:
    return TargetContribution(
        instrument_id=instrument_id,
        sleeve=sleeve,
        strategy_id=strategy,
        strategy_version=version,
        target_weight=Decimal(weight),
        evidence_ids=("snapshot-001",),
    )


def make_target(contributions=None, **overrides) -> TheoreticalTargetPortfolio:
    values = {
        "target_id": "target-2026-09-11",
        "revision": 1,
        "decision_for_trade_date": date(2026, 9, 14),
        "generated_at": GENERATED_AT,
        "information_cutoff": INFORMATION_CUTOFF,
        "valuation_equity": EQUITY,
        "contributions": contributions
        if contributions is not None
        else (
            contribution(),
            contribution(instrument_id=XSHE_159915, sleeve=SleeveId.SATELLITE, weight="0.25",
                         strategy="satellite-momentum"),
        ),
    }
    values.update(overrides)
    return TheoreticalTargetPortfolio(**values)


class TestTargetContribution:
    def test_contribution_retains_strategy_sleeve_and_weight(self) -> None:
        item = contribution()

        assert item.sleeve is SleeveId.CORE
        assert item.strategy_id == "core-etf-alpha"
        assert item.strategy_version == "1.0.0"
        assert item.target_weight == Decimal("0.60")
        assert item.evidence_ids == ("snapshot-001",)

    def test_sleeve_is_never_inferred_from_strategy_name(self) -> None:
        item = contribution(strategy="satellite-alpha", sleeve=SleeveId.CORE)

        assert item.sleeve is SleeveId.CORE

    def test_negative_weight_is_rejected(self) -> None:
        with pytest.raises(InvalidTargetError):
            contribution(weight="-0.10")

    def test_float_weight_is_rejected(self) -> None:
        with pytest.raises(InvalidTargetError):
            TargetContribution(
                instrument_id=XSHG_510300,
                sleeve=SleeveId.CORE,
                strategy_id="core-etf-alpha",
                strategy_version="1.0.0",
                target_weight=0.6,  # type: ignore[arg-type]
            )

    def test_empty_strategy_identity_is_rejected(self) -> None:
        with pytest.raises(InvalidTargetError):
            contribution(strategy="")


class TestTheoreticalWeightsAndCash:
    def test_instrument_weights_plus_cash_sum_to_exactly_one(self) -> None:
        target = make_target()

        weights = target.weights_by_instrument
        total = sum(weights.values(), Decimal("0")) + target.cash_weight

        assert total == Decimal("1")
        assert target.weights_by_instrument[XSHG_510300] == Decimal("0.60")
        assert target.cash_weight == Decimal("0.15")

    def test_multiple_strategies_aggregate_on_one_instrument(self) -> None:
        target = make_target(
            contributions=(
                contribution(weight="0.40", strategy="core-etf-alpha"),
                contribution(weight="0.20", strategy="core-momentum-overlay"),
            )
        )

        assert target.weights_by_instrument[XSHG_510300] == Decimal("0.60")

    def test_core_and_satellite_aggregate_from_explicit_sleeves(self) -> None:
        target = make_target()

        assert target.sleeve_weights == {
            SleeveId.CORE: Decimal("0.60"),
            SleeveId.SATELLITE: Decimal("0.25"),
        }

    def test_one_instrument_must_not_belong_to_two_sleeves(self) -> None:
        with pytest.raises(InvalidTargetError, match="sleeve"):
            make_target(
                contributions=(
                    contribution(sleeve=SleeveId.CORE, weight="0.30"),
                    contribution(sleeve=SleeveId.SATELLITE, weight="0.30"),
                )
            )

    def test_total_exposure_above_100_percent_is_rejected(self) -> None:
        with pytest.raises(InvalidTargetError, match="100"):
            make_target(
                contributions=(
                    contribution(weight="0.70"),
                    contribution(instrument_id=XSHE_159915, weight="0.40"),
                )
            )

    def test_exposure_within_declared_tolerance_is_accepted(self) -> None:
        target = make_target(
            contributions=(
                contribution(weight=str(Decimal("0.5") + WEIGHT_SUM_TOLERANCE)),
                contribution(instrument_id=XSHE_159915, weight="0.5"),
            )
        )

        assert target.cash_weight >= -WEIGHT_SUM_TOLERANCE


class TestZeroVersusAbsent:
    def test_explicit_zero_is_an_addressed_exit_target(self) -> None:
        target = make_target(
            contributions=(contribution(weight="0"),)
        )

        assert target.weights_by_instrument[XSHG_510300] == Decimal("0")
        assert XSHG_510300 in target.addressed_instruments

    def test_absent_instrument_is_not_addressed(self) -> None:
        target = make_target(contributions=(contribution(),))

        assert XSHE_159915 not in target.addressed_instruments


class TestLongOnlyAndConstruction:
    def test_empty_contributions_is_an_all_cash_target(self) -> None:
        target = make_target(contributions=())

        assert target.cash_weight == Decimal("1")

    def test_identity_fields_are_retained(self) -> None:
        target = make_target()

        assert target.target_id == "target-2026-09-11"
        assert target.revision == 1
        assert target.decision_for_trade_date == date(2026, 9, 14)
        assert target.valuation_equity == EQUITY

    def test_naive_generated_at_is_rejected(self) -> None:
        with pytest.raises(InvalidTargetError):
            make_target(generated_at=datetime(2026, 9, 11, 17, 30))

    def test_information_cutoff_after_generation_is_rejected(self) -> None:
        with pytest.raises(InvalidTargetError):
            make_target(information_cutoff=datetime(2026, 9, 11, 18, 0, tzinfo=UTC))

    def test_target_is_immutable(self) -> None:
        target = make_target()

        with pytest.raises(Exception, match="cannot assign"):
            target.revision = 2  # type: ignore[misc]


class TestLockAndRevisionIdentity:
    def test_supersede_creates_new_revision_and_keeps_the_original(self) -> None:
        original = make_target()
        corrected = original.supersede(
            contributions=(contribution(weight="0.55"),),
            reason_code="REBALANCE_DRIFT_CORRECTION",
            actor="portfolio-builder",
        )

        assert original.revision == 1
        assert corrected.revision == 2
        assert corrected.supersedes_revision == 1
        assert corrected.supersession_reason == "REBALANCE_DRIFT_CORRECTION"
        assert corrected.superseded_by == "portfolio-builder"
        assert corrected.weights_by_instrument[XSHG_510300] == Decimal("0.55")

    def test_identical_inputs_produce_identical_digests(self) -> None:
        assert make_target().content_digest == make_target().content_digest

    def test_input_ordering_does_not_change_the_digest(self) -> None:
        contributions = (
            contribution(),
            contribution(instrument_id=XSHE_159915, sleeve=SleeveId.SATELLITE, weight="0.25",
                         strategy="satellite-momentum"),
        )
        reordered = (contributions[1], contributions[0])

        assert make_target(contributions).content_digest == make_target(reordered).content_digest

    def test_content_change_changes_the_digest(self) -> None:
        base = make_target()
        changed = make_target(
            contributions=(contribution(weight="0.61"),)
        )

        assert base.content_digest != changed.content_digest


class TestHeldInstrumentCompleteness:
    def test_missing_held_instrument_is_never_silently_hold_or_sell(self) -> None:
        target = make_target(contributions=(contribution(),))

        with pytest.raises(TargetNotCompleteError, match="159915"):
            validate_target_completeness(
                target, held_instrument_ids=frozenset({XSHG_510300, XSHE_159915})
            )

    def test_explicit_zero_target_satisfies_completeness(self) -> None:
        target = make_target(
            contributions=(
                contribution(weight="0.60"),
                contribution(instrument_id=XSHE_159915, sleeve=SleeveId.SATELLITE, weight="0"),
                contribution(instrument_id=XSHG_518880, sleeve=SleeveId.CORE, weight="0.20"),
            )
        )

        validate_target_completeness(
            target, held_instrument_ids=frozenset({XSHG_510300, XSHE_159915, XSHG_518880})
        )

    def test_held_instruments_absent_from_target_fail_closed(self) -> None:
        target = make_target(contributions=())

        with pytest.raises(TargetNotCompleteError):
            validate_target_completeness(
                target, held_instrument_ids=frozenset({XSHG_510300})
            )

    def test_complete_target_passes(self) -> None:
        target = make_target()

        validate_target_completeness(target, held_instrument_ids=frozenset({XSHG_510300}))
