"""Instrument Master record models: effective-dated rule profiles and provenance.

The system-owned Instrument Master is the Production authority for approved
classification, ETF subtype, and lot/settlement/price-limit/market fee-tax
rules. Every profile version carries an authoritative source and an
effective-date interval; changing rules creates a new version rather than
rewriting history.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum

from systematic_investing.domain.identifiers import (
    InstrumentId,
    require_session_date,
)


class InstrumentMasterError(Exception):
    """Base class for Instrument Master authority errors."""


class InvalidRuleProfileError(InstrumentMasterError):
    """Raised when a rule profile record is internally inconsistent."""


class UnknownInstrumentError(InstrumentMasterError):
    """Raised when no approved instrument version covers the requested date."""


class UnknownRuleError(InstrumentMasterError):
    """Raised when no approved rule profile version covers the requested date."""


class ConflictingVersionsError(InstrumentMasterError):
    """Raised when two approved versions claim overlapping effective intervals."""


class UnsupportedClassificationError(InstrumentMasterError):
    """Raised when a classification is not an approved Instrument Master scope."""


def _required_text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise InvalidRuleProfileError(f"{field_name} must be a non-empty string")
    return value


def _non_negative_decimal(value: Decimal, field_name: str) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite() or value < 0:
        raise InvalidRuleProfileError(f"{field_name} must be a finite non-negative Decimal")
    return value


def _positive_int(value: int, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise InvalidRuleProfileError(f"{field_name} must be a positive integer")
    return value


class RuleKind(StrEnum):
    """Kinds of market/regulatory rule the Instrument Master owns."""

    LOT = "LOT"
    SETTLEMENT = "SETTLEMENT"
    PRICE_LIMIT = "PRICE_LIMIT"
    MARKET_FEE_TAX = "MARKET_FEE_TAX"


@dataclass(frozen=True)
class RuleSource:
    """Authoritative provenance for a rule profile version."""

    authority: str
    reference: str
    accessed_on: date

    def __post_init__(self) -> None:
        _required_text(self.authority, "authority")
        _required_text(self.reference, "reference")
        require_session_date(self.accessed_on)


@dataclass(frozen=True)
class EffectiveDatedRule:
    """Common shape of every versioned rule profile: a stable profile family
    id plus the effective interval this version governs. Correcting or
    changing a rule adds a new version with a new interval; history is never
    rewritten."""

    profile_id: str
    effective_from: date
    effective_to: date | None
    source: RuleSource

    def __post_init__(self) -> None:
        _required_text(self.profile_id, "profile_id")
        require_session_date(self.effective_from)
        if self.effective_to is not None:
            require_session_date(self.effective_to)
            if self.effective_to < self.effective_from:
                raise InvalidRuleProfileError("effective_to must not precede effective_from")
        if not isinstance(self.source, RuleSource):
            raise InvalidRuleProfileError("source must be a RuleSource")

    def covers(self, session_date: date) -> bool:
        if session_date < self.effective_from:
            return False
        return self.effective_to is None or session_date <= self.effective_to


class OddLotSellPolicy(StrEnum):
    """Whether selling an odd lot (below board lot) is permitted."""

    ALLOWED = "ALLOWED"
    PROHIBITED = "PROHIBITED"


@dataclass(frozen=True)
class LotRule(EffectiveDatedRule):
    """Board-lot size, buy increment, and odd-lot sell policy."""

    board_lot: int = 100
    buy_increment: int = 100
    odd_lot_sell_policy: OddLotSellPolicy = OddLotSellPolicy.ALLOWED

    def __post_init__(self) -> None:
        super().__post_init__()
        _positive_int(self.board_lot, "board_lot")
        _positive_int(self.buy_increment, "buy_increment")
        if not isinstance(self.odd_lot_sell_policy, OddLotSellPolicy):
            raise InvalidRuleProfileError(
                f"odd_lot_sell_policy must be an OddLotSellPolicy, got {self.odd_lot_sell_policy!r}"
            )


@dataclass(frozen=True)
class SettlementRule(EffectiveDatedRule):
    """When acquired quantity becomes sellable, configured per instrument/subtype."""

    sessions_until_sellable: int = 1

    def __post_init__(self) -> None:
        super().__post_init__()
        if (
            not isinstance(self.sessions_until_sellable, int)
            or isinstance(self.sessions_until_sellable, bool)
            or self.sessions_until_sellable < 0
        ):
            raise InvalidRuleProfileError(
                "sessions_until_sellable must be a non-negative integer"
            )


class PriceLimitBasis(StrEnum):
    """Basis on which daily price limits are computed."""

    PREVIOUS_CLOSE = "PREVIOUS_CLOSE"


@dataclass(frozen=True)
class PriceLimitRule(EffectiveDatedRule):
    """Daily price-limit basis, percentage, and the tick size limit prices
    round to. Tick size is exchange truth, not broker configuration."""

    basis: PriceLimitBasis = PriceLimitBasis.PREVIOUS_CLOSE
    limit_percent: Decimal = Decimal("0.10")
    tick_size: Decimal = Decimal("0.01")

    def __post_init__(self) -> None:
        super().__post_init__()
        if not isinstance(self.basis, PriceLimitBasis):
            raise InvalidRuleProfileError(f"basis must be a PriceLimitBasis, got {self.basis!r}")
        _non_negative_decimal(self.limit_percent, "limit_percent")
        if not isinstance(self.tick_size, Decimal) or self.tick_size <= 0:
            raise InvalidRuleProfileError("tick_size must be a positive Decimal")


@dataclass(frozen=True)
class MarketFeeTaxRule(EffectiveDatedRule):
    """Regulatory/exchange/tax truth such as stamp tax and transfer fees.
    Account-specific broker commissions are never modeled here."""

    stamp_tax_sell_rate: Decimal = Decimal("0")
    transfer_fee_rate: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        super().__post_init__()
        _non_negative_decimal(self.stamp_tax_sell_rate, "stamp_tax_sell_rate")
        _non_negative_decimal(self.transfer_fee_rate, "transfer_fee_rate")


_RULE_KINDS_BY_TYPE: dict[type, RuleKind] = {
    LotRule: RuleKind.LOT,
    SettlementRule: RuleKind.SETTLEMENT,
    PriceLimitRule: RuleKind.PRICE_LIMIT,
    MarketFeeTaxRule: RuleKind.MARKET_FEE_TAX,
}


def rule_kind_of(profile: "EffectiveDatedRule") -> RuleKind:
    kind = _RULE_KINDS_BY_TYPE.get(type(profile))
    if kind is None:
        raise InvalidRuleProfileError(f"unsupported rule profile type {type(profile).__name__}")
    return kind


@dataclass(frozen=True)
class InstrumentRules:
    """The complete approved rule bundle in force for one instrument on one
    session date. Any missing member means the session is not covered and
    must fail closed upstream."""

    session_date: date
    lot: LotRule
    settlement: SettlementRule
    price_limit: PriceLimitRule
    market_fee_tax: MarketFeeTaxRule


class AdjudicationStatus(StrEnum):
    """Outcome of adjudicating a provider candidate against the authority."""

    APPROVED_PROFILE_GOVERNS = "APPROVED_PROFILE_GOVERNS"
    FAIL_CLOSED_NO_APPROVED_PROFILE = "FAIL_CLOSED_NO_APPROVED_PROFILE"


@dataclass(frozen=True)
class RuleCandidate:
    """A rule value proposed by an external provider. Candidates are advisory
    input for adjudication only; they can never become authority."""

    instrument_id: InstrumentId
    session_date: date
    rule_kind: RuleKind
    proposed_value: LotRule | SettlementRule | PriceLimitRule | MarketFeeTaxRule
    proposed_by: str

    def __post_init__(self) -> None:
        require_session_date(self.session_date)
        if not isinstance(self.rule_kind, RuleKind):
            raise InvalidRuleProfileError(f"rule_kind must be a RuleKind, got {self.rule_kind!r}")
        if not isinstance(self.proposed_value, EffectiveDatedRule):
            raise InvalidRuleProfileError("proposed_value must be a rule profile")
        _required_text(self.proposed_by, "proposed_by")


@dataclass(frozen=True)
class RuleAdjudication:
    """Result of adjudication: either the approved bundle governs (the
    candidate is ignored entirely) or the session is not covered and the
    caller must fail closed. A candidate is never merged into the result."""

    status: AdjudicationStatus
    approved_rules: InstrumentRules | None
