"""Instrument identity and classification.

``Instrument`` describes identity and references Instrument Master
market/regulatory rule profiles. It never references broker/account fees:
account commissions belong to run configuration, not instrument identity.
"""

from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from systematic_investing.domain.identifiers import (
    InstrumentId,
    require_session_date,
)


class InstrumentError(Exception):
    """Base class for instrument identity/classification errors."""


class InvalidInstrumentError(InstrumentError):
    """Raised when instrument identity or classification is inconsistent."""


class InstrumentType(StrEnum):
    """Instrument types in M0 scope."""

    A_SHARE = "A_SHARE"
    EXCHANGE_TRADED_FUND = "EXCHANGE_TRADED_FUND"


class FundSubtype(StrEnum):
    """Approved ETF subtypes only.

    Membership is the fail-closed qualification boundary: cross-border/QDII,
    money-market, and every other unverified subtype are not expressible and
    therefore can never enter the Instrument Master. Passing one subtype
    never approves another.
    """

    BROAD_BASED_EQUITY = "BROAD_BASED_EQUITY"
    GOLD = "GOLD"
    BOND = "BOND"


def _required_text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise InvalidInstrumentError(f"{field_name} must be a non-empty string")
    return value


@dataclass(frozen=True)
class Instrument:
    """Immutable instrument identity.

    ETF ``fund_subtype`` is always an explicit approved classification, never
    inferred from the symbol. Rule behavior lives in the effective-dated
    Instrument Master profiles referenced here by profile family id; broker
    or account fees are not part of instrument identity. A reference-data
    correction creates a new version with its own valid interval instead of
    rewriting this record.
    """

    instrument_id: InstrumentId
    display_name: str
    currency: str
    instrument_type: InstrumentType
    fund_subtype: FundSubtype | None
    list_date: date
    delist_date: date | None
    trading_calendar_id: str
    lot_rule_profile_id: str
    settlement_rule_profile_id: str
    price_limit_rule_profile_id: str
    market_fee_tax_profile_id: str
    reference_data_version: str
    valid_from: date
    valid_to: date | None

    def __post_init__(self) -> None:
        if not isinstance(self.instrument_id, InstrumentId):
            raise InvalidInstrumentError("instrument_id must be an InstrumentId")
        if not isinstance(self.instrument_type, InstrumentType):
            raise InvalidInstrumentError(
                f"instrument_type must be an InstrumentType, got {self.instrument_type!r}"
            )
        if self.fund_subtype is not None and not isinstance(self.fund_subtype, FundSubtype):
            raise InvalidInstrumentError(
                f"fund_subtype must be an approved FundSubtype or None, got {self.fund_subtype!r}"
            )
        if self.instrument_type is InstrumentType.A_SHARE and self.fund_subtype is not None:
            raise InvalidInstrumentError("an A_SHARE instrument must not declare a fund_subtype")
        _required_text(self.currency, "currency")
        _required_text(self.display_name, "display_name")
        _required_text(self.trading_calendar_id, "trading_calendar_id")
        for reference in (
            "lot_rule_profile_id",
            "settlement_rule_profile_id",
            "price_limit_rule_profile_id",
            "market_fee_tax_profile_id",
            "reference_data_version",
        ):
            _required_text(getattr(self, reference), reference)
        require_session_date(self.list_date)
        if self.delist_date is not None:
            require_session_date(self.delist_date)
            if self.delist_date < self.list_date:
                raise InvalidInstrumentError("delist_date must not precede list_date")
        require_session_date(self.valid_from)
        if self.valid_to is not None:
            require_session_date(self.valid_to)
            if self.valid_to < self.valid_from:
                raise InvalidInstrumentError("valid_to must not precede valid_from")
