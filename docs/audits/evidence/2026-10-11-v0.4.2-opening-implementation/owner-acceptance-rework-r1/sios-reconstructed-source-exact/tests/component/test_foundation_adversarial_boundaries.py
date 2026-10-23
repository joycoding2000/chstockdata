from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from systematic_investing.backtest.engine import DecisionContext, InvalidDecisionContextError
from systematic_investing.domain.identifiers import InstrumentId, SleeveId
from systematic_investing.domain.ledger import AcquisitionLot, Position
from systematic_investing.domain.market import (
    Availability,
    AvailabilityBasis,
    CorporateAction,
    CorporateActionKind,
    TradabilityStatus,
    TradabilityStatusKind,
)
from systematic_investing.domain.money import Money
from systematic_investing.domain.portfolio import (
    TargetContribution,
    TheoreticalTargetPortfolio,
)
from systematic_investing.portfolio.allocation import (
    CurrentHolding,
    CurrentPortfolio,
)
from systematic_investing.risk.decisions import (
    RiskTransformation,
    RiskTransformationError,
)
from systematic_investing.risk.ports import RiskRuleOutcome, RiskRuleStatus

ETF = InstrumentId.parse("XSHG:510300")
SESSION = date(2026, 9, 17)
NEXT_SESSION = date(2026, 9, 18)
NOW = datetime(2026, 9, 17, 16, 0, tzinfo=UTC)


def _availability() -> Availability:
    return Availability(
        information_available_at=NOW,
        retrieved_at=NOW,
        availability_basis=AvailabilityBasis.OBSERVED,
    )


def _target(weight: str = "0.50") -> TheoreticalTargetPortfolio:
    return TheoreticalTargetPortfolio(
        target_id="target:adversarial",
        revision=1,
        decision_for_trade_date=NEXT_SESSION,
        generated_at=NOW,
        information_cutoff=NOW,
        valuation_equity=Money(Decimal("100000")),
        contributions=(
            TargetContribution(
                instrument_id=ETF,
                sleeve=SleeveId.CORE,
                strategy_id="fixture-not-strategy",
                strategy_version="v1",
                target_weight=Decimal(weight),
            ),
        ),
    )


class _ForgedBeforeRule:
    rule_id = "forged-before"
    rule_version = "v1"

    def evaluate(self, weights, sleeve_of) -> RiskRuleOutcome:
        del weights, sleeve_of
        return RiskRuleOutcome(
            rule_id=self.rule_id,
            rule_version=self.rule_version,
            status=RiskRuleStatus.CAP_TRANSFORM,
            before_weights=((ETF, Decimal("1.00")),),
            after_weights=((ETF, Decimal("0.80")),),
            reason_code="FORGED_INPUT",
        )


class _NegativeWeightRule:
    rule_id = "negative-weight"
    rule_version = "v1"

    def evaluate(self, weights, sleeve_of) -> RiskRuleOutcome:
        del weights, sleeve_of
        return RiskRuleOutcome(
            rule_id=self.rule_id,
            rule_version=self.rule_version,
            status=RiskRuleStatus.CAP_TRANSFORM,
            before_weights=((ETF, Decimal("0.50")),),
            after_weights=((ETF, Decimal("-0.10")),),
            reason_code="INVALID_NEGATIVE",
        )


class _MissingExposureRule:
    rule_id = "missing-exposure"
    rule_version = "v1"

    def evaluate(self, weights, sleeve_of) -> RiskRuleOutcome:
        del weights, sleeve_of
        return RiskRuleOutcome(
            rule_id=self.rule_id,
            rule_version=self.rule_version,
            status=RiskRuleStatus.CAP_TRANSFORM,
            before_weights=((ETF, Decimal("0.50")),),
            after_weights=(),
            reason_code="DROPPED_KEY",
        )


class _PassMutationRule:
    rule_id = "pass-mutation"
    rule_version = "v1"

    def evaluate(self, weights, sleeve_of) -> RiskRuleOutcome:
        del weights, sleeve_of
        return RiskRuleOutcome(
            rule_id=self.rule_id,
            rule_version=self.rule_version,
            status=RiskRuleStatus.PASS,
            before_weights=((ETF, Decimal("0.50")),),
            after_weights=((ETF, Decimal("0.40")),),
            reason_code="SILENT_PASS_MUTATION",
        )


class _DuplicateWeightRule:
    rule_id = "duplicate-weight"
    rule_version = "v1"

    def evaluate(self, weights, sleeve_of) -> RiskRuleOutcome:
        del weights, sleeve_of
        return RiskRuleOutcome(
            rule_id=self.rule_id,
            rule_version=self.rule_version,
            status=RiskRuleStatus.CAP_TRANSFORM,
            before_weights=((ETF, Decimal("0.50")),),
            after_weights=((ETF, Decimal("0.40")), (ETF, Decimal("0.30"))),
            reason_code="DUPLICATE_OUTPUT",
        )


class _MismatchedIdentityRule:
    rule_id = "declared-rule"
    rule_version = "v1"

    def evaluate(self, weights, sleeve_of) -> RiskRuleOutcome:
        del weights, sleeve_of
        return RiskRuleOutcome(
            rule_id="different-rule",
            rule_version="v9",
            status=RiskRuleStatus.PASS,
            before_weights=((ETF, Decimal("0.50")),),
            after_weights=((ETF, Decimal("0.50")),),
            reason_code="IDENTITY_MISMATCH",
        )


@pytest.mark.parametrize(
    "rule",
    [
        _ForgedBeforeRule(),
        _NegativeWeightRule(),
        _MissingExposureRule(),
        _PassMutationRule(),
        _DuplicateWeightRule(),
        _MismatchedIdentityRule(),
    ],
    ids=[
        "forged-before",
        "negative-weight",
        "missing-exposure",
        "pass-mutation",
        "duplicate-weight",
        "mismatched-identity",
    ],
)
def test_risk_transform_rejects_adversarial_rule_outcomes(rule) -> None:
    transformation = RiskTransformation((rule,), "adversarial-v1")

    with pytest.raises(RiskTransformationError):
        transformation.transform(_target())


def test_current_portfolio_copies_caller_owned_holdings() -> None:
    holdings = [CurrentHolding(instrument_id=ETF, quantity=100)]
    portfolio = CurrentPortfolio(
        cash=Money(Decimal("99600")),
        holdings=holdings,  # type: ignore[arg-type]
    )

    holdings.clear()

    assert portfolio.holdings == (CurrentHolding(instrument_id=ETF, quantity=100),)


def test_decision_context_rejects_future_tradability_and_corporate_actions() -> None:
    future_tradability = TradabilityStatus(
        instrument_id=ETF,
        session_date=NEXT_SESSION,
        status=TradabilityStatusKind.TRADABLE,
        reason=None,
        availability=_availability(),
        provenance="exchange",
    )
    future_action = CorporateAction(
        action_id="action:future",
        instrument_id=ETF,
        action_kind=CorporateActionKind.SPLIT,
        ex_date=NEXT_SESSION,
        record_date=None,
        pay_date=None,
        cash_amount=None,
        share_ratio=Decimal("2"),
        revision=1,
        availability=_availability(),
        provenance="issuer",
    )
    position = Position(
        instrument_id=ETF,
        lots=(
            AcquisitionLot(
                quantity=100,
                acquired_session=SESSION,
                sellable_from=NEXT_SESSION,
                acquisition_price=Decimal("4.00"),
            ),
        ),
    )

    with pytest.raises(InvalidDecisionContextError, match="after the decision session"):
        DecisionContext(
            session_date=SESSION,
            decision_for_trade_date=NEXT_SESSION,
            information_cutoff=NOW,
            cash=Money(Decimal("99600")),
            valuation_equity=Money(Decimal("100000")),
            positions=(position,),
            tradability=(future_tradability,),
        )
    with pytest.raises(InvalidDecisionContextError, match="effective after"):
        DecisionContext(
            session_date=SESSION,
            decision_for_trade_date=NEXT_SESSION,
            information_cutoff=NOW,
            cash=Money(Decimal("99600")),
            valuation_equity=Money(Decimal("100000")),
            positions=(position,),
            corporate_actions=(future_action,),
        )
