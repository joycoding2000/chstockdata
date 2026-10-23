"""Deterministic risk transformation and approved targets.

Rules compose in an explicit, versioned order. Each rule evaluation may pass,
cap/transform (reduce only), or block. The pipeline enforces the core
invariant itself: no rule may increase any instrument's weight or invent a
new exposure, so risk can only reduce or veto upstream theoretical exposure.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType

from systematic_investing.domain.identifiers import InstrumentId, SleeveId
from systematic_investing.domain.money import Money
from systematic_investing.domain.portfolio import TheoreticalTargetPortfolio
from systematic_investing.risk.ports import RiskRule, RiskRuleOutcome, RiskRuleStatus


class RiskTransformationError(Exception):
    """Raised when a rule violates the risk contract, for example by
    increasing exposure."""

    def __init__(self, rule_id: str, message: str) -> None:
        self.rule_id = rule_id
        super().__init__(f"rule {rule_id}: {message}")


class RiskTransformationStatus(StrEnum):
    APPROVED = "APPROVED"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class ApprovedPosition:
    """One instrument's theoretical vs risk-approved weight with the sleeve
    the exposure belongs to."""

    instrument_id: InstrumentId
    sleeve: SleeveId
    theoretical_weight: Decimal
    approved_weight: Decimal
    reason_codes: tuple[str, ...] = ()


@dataclass(frozen=True)
class RiskApprovedTargetPortfolio:
    """Output of the deterministic risk transformation: same identity as the
    theoretical target, weights only reduced, decisions recorded."""

    target_id: str
    revision: int
    decision_for_trade_date: date
    information_cutoff: datetime
    valuation_equity: Money
    positions: tuple[ApprovedPosition, ...]
    approved_cash_weight: Decimal
    applied_rules: tuple[RiskRuleOutcome, ...]
    composition_version: str


class SleeveCapRule:
    """Cap the aggregate approved exposure of one sleeve.

    Deterministic reduction policy: instruments in the sleeve are walked in
    descending current weight with canonical InstrumentId as tie-breaker, and
    each is capped at the remaining budget. Bump ``rule_version`` to change
    the policy."""

    def __init__(
        self,
        rule_id: str,
        rule_version: str,
        sleeve: SleeveId,
        max_weight: Decimal,
    ) -> None:
        if not isinstance(rule_id, str) or not rule_id:
            raise ValueError("rule_id must be a non-empty string")
        if not isinstance(rule_version, str) or not rule_version:
            raise ValueError("rule_version must be a non-empty string")
        if not isinstance(sleeve, SleeveId):
            raise ValueError("sleeve must be a SleeveId")
        if not isinstance(max_weight, Decimal) or not max_weight.is_finite() or max_weight < 0:
            raise ValueError("max_weight must be a finite non-negative Decimal")
        self.rule_id = rule_id
        self.rule_version = rule_version
        self.sleeve = sleeve
        self.max_weight = max_weight

    def evaluate(
        self,
        weights: Mapping[InstrumentId, Decimal],
        sleeve_of: Mapping[InstrumentId, SleeveId],
    ) -> RiskRuleOutcome:
        before = dict(weights)
        sleeve_members = [
            instrument_id
            for instrument_id, sleeve in sleeve_of.items()
            if sleeve is self.sleeve and instrument_id in before
        ]
        sleeve_total = sum((before[item] for item in sleeve_members), Decimal("0"))
        if sleeve_total <= self.max_weight:
            after = dict(before)
            status = RiskRuleStatus.PASS
            reason = "SLEEVE_CAP_UNBOUND"
        else:
            after = dict(before)
            remaining = self.max_weight
            for instrument_id in sorted(
                sleeve_members, key=lambda item: (-before[item], item)
            ):
                approved = min(before[instrument_id], remaining)
                after[instrument_id] = approved
                remaining -= approved
            status = RiskRuleStatus.CAP_TRANSFORM
            reason = "SLEEVE_CAP_BOUND"
        return RiskRuleOutcome(
            rule_id=self.rule_id,
            rule_version=self.rule_version,
            status=status,
            before_weights=tuple(sorted(before.items())),
            after_weights=tuple(sorted(after.items())),
            reason_code=reason,
        )


@dataclass(frozen=True)
class RiskTransformationResult:
    """Either an approved target or a veto with the blocking rule recorded."""

    status: RiskTransformationStatus
    approved: RiskApprovedTargetPortfolio | None
    applied_rules: tuple[RiskRuleOutcome, ...]
    composition_version: str
    blocking_rule_id: str | None = None
    block_reason_code: str | None = None


class RiskTransformation:
    """Compose versioned rules in explicit order over a theoretical target."""

    def __init__(self, rules: Sequence[RiskRule], composition_version: str) -> None:
        if not isinstance(composition_version, str) or not composition_version:
            raise ValueError("composition_version must be a non-empty string")
        for rule in rules:
            if not isinstance(rule.rule_id, str) or not rule.rule_id:
                raise ValueError("every risk rule needs a non-empty rule_id")
            if not isinstance(rule.rule_version, str) or not rule.rule_version:
                raise ValueError("every risk rule needs a non-empty rule_version")
        self._rules = tuple(rules)
        self.composition_version = composition_version

    def transform(self, target: TheoreticalTargetPortfolio) -> RiskTransformationResult:
        working: dict[InstrumentId, Decimal] = dict(target.weights_by_instrument)
        sleeve_of = {item: target.sleeve_of(item) for item in working}
        applied: list[RiskRuleOutcome] = []

        for rule in self._rules:
            outcome = rule.evaluate(MappingProxyType(working), MappingProxyType(sleeve_of))
            self._verify_outcome(rule, outcome, working)
            applied.append(outcome)
            if outcome.status is RiskRuleStatus.BLOCK:
                return RiskTransformationResult(
                    status=RiskTransformationStatus.BLOCKED,
                    approved=None,
                    applied_rules=tuple(applied),
                    composition_version=self.composition_version,
                    blocking_rule_id=rule.rule_id,
                    block_reason_code=outcome.reason_code,
                )
            working = dict(outcome.after_weights)

        approved_weights = working
        positions = tuple(
            ApprovedPosition(
                instrument_id=instrument_id,
                sleeve=sleeve_of[instrument_id],
                theoretical_weight=target.weights_by_instrument[instrument_id],
                approved_weight=approved_weights[instrument_id],
                reason_codes=tuple(
                    outcome.reason_code
                    for outcome in applied
                    if outcome.status is RiskRuleStatus.CAP_TRANSFORM
                    and dict(outcome.before_weights)[instrument_id]
                    != dict(outcome.after_weights)[instrument_id]
                ),
            )
            for instrument_id in sorted(approved_weights)
        )
        approved_cash = Decimal("1") - sum(approved_weights.values(), Decimal("0"))
        approved = RiskApprovedTargetPortfolio(
            target_id=target.target_id,
            revision=target.revision,
            decision_for_trade_date=target.decision_for_trade_date,
            information_cutoff=target.information_cutoff,
            valuation_equity=target.valuation_equity,
            positions=positions,
            approved_cash_weight=approved_cash,
            applied_rules=tuple(applied),
            composition_version=self.composition_version,
        )
        return RiskTransformationResult(
            status=RiskTransformationStatus.APPROVED,
            approved=approved,
            applied_rules=tuple(applied),
            composition_version=self.composition_version,
        )

    @staticmethod
    def _verify_outcome(
        rule: RiskRule,
        outcome: RiskRuleOutcome,
        expected_before: Mapping[InstrumentId, Decimal],
    ) -> None:
        if outcome.rule_id != rule.rule_id or outcome.rule_version != rule.rule_version:
            raise RiskTransformationError(
                rule.rule_id,
                "rule outcome identity/version does not match the invoked rule",
            )
        before_pairs = tuple(outcome.before_weights)
        after_pairs = tuple(outcome.after_weights)
        before = dict(before_pairs)
        after = dict(outcome.after_weights)
        if len(before) != len(before_pairs) or len(after) != len(after_pairs):
            raise RiskTransformationError(
                outcome.rule_id,
                "rule outcome contains duplicate instrument weights",
            )
        if before != dict(expected_before):
            raise RiskTransformationError(
                outcome.rule_id,
                "rule outcome before_weights do not match the actual pipeline input",
            )
        for instrument_id, approved_weight in after.items():
            if (
                not isinstance(approved_weight, Decimal)
                or not approved_weight.is_finite()
                or approved_weight < 0
            ):
                raise RiskTransformationError(
                    outcome.rule_id,
                    f"rule produced invalid weight {approved_weight!r} for {instrument_id}",
                )
        if outcome.status is RiskRuleStatus.BLOCK:
            return
        if set(after) != set(before):
            raise RiskTransformationError(
                outcome.rule_id,
                "non-blocking risk rules must retain every upstream instrument key",
            )
        if outcome.status is RiskRuleStatus.PASS and after != before:
            raise RiskTransformationError(
                outcome.rule_id,
                "a PASS outcome must not transform weights",
            )
        for instrument_id, approved_weight in after.items():
            theoretical = before.get(instrument_id)
            assert theoretical is not None
            if approved_weight > theoretical:
                raise RiskTransformationError(
                    outcome.rule_id,
                    f"rule increased {instrument_id} from {theoretical} to "
                    f"{approved_weight}; risk may only reduce or veto",
                )
