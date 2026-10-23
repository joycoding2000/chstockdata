"""Risk rule port: versioned, deterministic, order-explicit rules."""

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Protocol, runtime_checkable

from systematic_investing.domain.identifiers import InstrumentId, SleeveId


class RiskRuleStatus(StrEnum):
    """Rule output is one of pass, cap/transform, or block."""

    PASS = "PASS"
    CAP_TRANSFORM = "CAP_TRANSFORM"
    BLOCK = "BLOCK"


@dataclass(frozen=True)
class RiskRuleOutcome:
    """Before/after values with a reason code, kept for audit output."""

    rule_id: str
    rule_version: str
    status: RiskRuleStatus
    before_weights: tuple[tuple[InstrumentId, Decimal], ...]
    after_weights: tuple[tuple[InstrumentId, Decimal], ...]
    reason_code: str


@runtime_checkable
class RiskRule(Protocol):
    """One deterministic risk rule. A rule may pass, cap/transform (reduce
    only), or block; it can never increase exposure."""

    rule_id: str
    rule_version: str

    def evaluate(
        self,
        weights: Mapping[InstrumentId, Decimal],
        sleeve_of: Mapping[InstrumentId, SleeveId],
    ) -> RiskRuleOutcome: ...
