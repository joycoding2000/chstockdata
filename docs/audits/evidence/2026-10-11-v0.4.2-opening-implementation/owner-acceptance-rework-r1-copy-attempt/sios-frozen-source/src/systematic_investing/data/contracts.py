"""Canonical provider evidence, typed results, and record serialization.

Provider evidence records what a provider call did (capability, request
digest, retrieval time, payload checksum, warnings). Typed results keep empty
success and provider failure distinct; vendor frames never cross this
boundary. Serialization renders canonical records as versioned JSON-safe
mappings that preserve Decimal/date/time/enum/schema values exactly.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from systematic_investing.domain.identifiers import InstrumentId
from systematic_investing.domain.market import (
    CANONICAL_RECORD_SCHEMA_VERSION,
    AdjustmentFactor,
    AdjustmentMode,
    Availability,
    AvailabilityBasis,
    CorporateAction,
    CorporateActionKind,
    DailyBar,
    MarketDataError,
    TradabilityStatus,
    TradabilityStatusKind,
    TradingSession,
)
from systematic_investing.domain.money import Money, MoneyError


class ProviderContractError(Exception):
    """Base class for provider-contract and serialization errors."""


class InvalidProviderEvidenceError(ProviderContractError):
    """Raised when provider evidence violates its contract."""


class MalformedRecordError(ProviderContractError):
    """Raised when a serialized record is missing keys or has wrong types."""


class UnknownSchemaVersionError(ProviderContractError):
    """Raised when a serialized record carries an unsupported schema version."""


class ProviderErrorCode(StrEnum):
    """Typed provider failure categories."""

    AUTHENTICATION_OR_CONFIGURATION = "AUTHENTICATION_OR_CONFIGURATION"
    UNAVAILABLE_OR_RATE_LIMITED = "UNAVAILABLE_OR_RATE_LIMITED"
    SCHEMA_DRIFT = "SCHEMA_DRIFT"
    MALFORMED_DATA = "MALFORMED_DATA"
    PARTIAL_RESULT = "PARTIAL_RESULT"
    UNSUPPORTED_CAPABILITY = "UNSUPPORTED_CAPABILITY"
    INTERNAL_ADAPTER_ERROR = "INTERNAL_ADAPTER_ERROR"


def _require_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise InvalidProviderEvidenceError(f"{field_name} must be a non-empty string")
    return value


def _optional_text(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _require_text(value, field_name)


@dataclass(frozen=True)
class ProviderEvidence:
    """What one provider call did, kept separate from record-level PIT
    availability."""

    evidence_id: str
    provider_name: str
    provider_version: str | None
    adapter_name: str
    adapter_version: str
    capability: str
    request_digest: str
    retrieved_at: datetime
    upstream_source: str | None
    record_count: int
    payload_checksum: str
    warnings: tuple[str, ...] = field(default=())

    def __post_init__(self) -> None:
        for text_field in (
            "evidence_id",
            "provider_name",
            "adapter_name",
            "adapter_version",
            "capability",
            "request_digest",
            "payload_checksum",
        ):
            _require_text(getattr(self, text_field), text_field)
        _optional_text(self.provider_version, "provider_version")
        _optional_text(self.upstream_source, "upstream_source")
        if not isinstance(self.retrieved_at, datetime) or self.retrieved_at.tzinfo is None:
            raise InvalidProviderEvidenceError(
                f"retrieved_at must be a timezone-aware datetime, got {self.retrieved_at!r}"
            )
        if not isinstance(self.record_count, int) or isinstance(self.record_count, bool):
            raise InvalidProviderEvidenceError("record_count must be an integer")
        if self.record_count < 0:
            raise InvalidProviderEvidenceError("record_count must be non-negative")
        if not isinstance(self.warnings, tuple) or not all(
            isinstance(warning, str) and warning for warning in self.warnings
        ):
            raise InvalidProviderEvidenceError(
                "warnings must be a tuple of non-empty strings"
            )


@dataclass(frozen=True)
class ProviderSuccess[T]:
    """Canonical records plus evidence. An empty record tuple is still a
    success: empty and failure are distinct outcomes."""

    records: tuple[T, ...]
    evidence: ProviderEvidence

    def __post_init__(self) -> None:
        object.__setattr__(self, "records", tuple(self.records))

    @property
    def is_success(self) -> bool:
        return True


@dataclass(frozen=True)
class ProviderFailure:
    """A typed provider failure; expected failures are values, not crashes."""

    error_code: ProviderErrorCode
    message: str
    evidence: ProviderEvidence | None
    cause: BaseException | None = None

    @property
    def is_success(self) -> bool:
        return False


def _require_mapping(data: object) -> dict[str, object]:
    if not isinstance(data, dict):
        raise MalformedRecordError(f"expected a mapping, got {type(data).__name__}")
    return data


def _require_key(data: dict[str, object], key: str) -> object:
    if key not in data:
        raise MalformedRecordError(f"missing required key {key!r}")
    return data[key]


def _require_schema_version(data: dict[str, object]) -> None:
    version = _require_key(data, "schema_version")
    if version != CANONICAL_RECORD_SCHEMA_VERSION:
        raise UnknownSchemaVersionError(
            f"unsupported record schema version {version!r}; reader supports "
            f"{CANONICAL_RECORD_SCHEMA_VERSION!r}"
        )


def _decimal(value: object, field_name: str) -> Decimal:
    try:
        return Decimal(str(value))
    except Exception as error:
        raise MalformedRecordError(f"{field_name} is not a Decimal value: {value!r}") from error


def _optional_decimal(value: object, field_name: str) -> Decimal | None:
    return None if value is None else _decimal(value, field_name)


def _date(value: object, field_name: str) -> date:
    if not isinstance(value, str):
        raise MalformedRecordError(f"{field_name} must be an ISO date string")
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise MalformedRecordError(f"{field_name} is not an ISO date: {value!r}") from error


def _optional_date(value: object, field_name: str) -> date | None:
    return None if value is None else _date(value, field_name)


def _datetime(value: object, field_name: str) -> datetime:
    if not isinstance(value, str):
        raise MalformedRecordError(f"{field_name} must be an ISO datetime string")
    try:
        return datetime.fromisoformat(value)
    except ValueError as error:
        raise MalformedRecordError(
            f"{field_name} is not an ISO datetime: {value!r}"
        ) from error


def _optional_datetime(value: object, field_name: str) -> datetime | None:
    return None if value is None else _datetime(value, field_name)


def _instrument_id(value: object, field_name: str) -> InstrumentId:
    try:
        return InstrumentId.parse(_require_text(value, field_name))
    except ValueError as error:
        raise MalformedRecordError(f"{field_name} is not a canonical id: {value!r}") from error


def _money(value: object, field_name: str) -> Money:
    try:
        return Money(_decimal(value, field_name))
    except (ValueError, MoneyError) as error:
        raise MalformedRecordError(f"{field_name} is not a Money value") from error


def _optional_money(value: object, field_name: str) -> Money | None:
    return None if value is None else _money(value, field_name)


def _availability_to_dict(availability: Availability) -> dict[str, object]:
    return {
        "information_available_at": (
            availability.information_available_at.isoformat()
            if availability.information_available_at is not None
            else None
        ),
        "retrieved_at": availability.retrieved_at.isoformat(),
        "availability_basis": availability.availability_basis.value,
    }


def _availability_from_dict(data: dict[str, object]) -> Availability:
    try:
        return Availability(
            information_available_at=_optional_datetime(
                _require_key(data, "information_available_at"), "information_available_at"
            ),
            retrieved_at=_datetime(_require_key(data, "retrieved_at"), "retrieved_at"),
            availability_basis=AvailabilityBasis(
                _require_text(_require_key(data, "availability_basis"), "availability_basis")
            ),
        )
    except (ValueError, MarketDataError) as error:
        raise MalformedRecordError(f"invalid availability payload: {error}") from error


def _adjustment_factor_to_dict(factor: AdjustmentFactor) -> dict[str, object]:
    return {
        "factor": str(factor.factor),
        "convention": factor.convention,
        "version": factor.version,
        "as_of": factor.as_of.isoformat(),
    }


def _adjustment_factor_from_dict(data: dict[str, object]) -> AdjustmentFactor:
    try:
        return AdjustmentFactor(
            factor=_decimal(_require_key(data, "factor"), "factor"),
            convention=str(_require_key(data, "convention")),
            version=str(_require_key(data, "version")),
            as_of=_date(_require_key(data, "as_of"), "as_of"),
        )
    except (ValueError, MarketDataError) as error:
        raise MalformedRecordError(f"invalid adjustment factor payload: {error}") from error


def daily_bar_to_dict(record: DailyBar) -> dict[str, object]:
    return {
        "schema_version": record.schema_version,
        "instrument_id": str(record.instrument_id),
        "session_date": record.session_date.isoformat(),
        "open": str(record.open),
        "high": str(record.high),
        "low": str(record.low),
        "close": str(record.close),
        "pre_close": str(record.pre_close) if record.pre_close is not None else None,
        "volume": str(record.volume),
        "amount": str(record.amount),
        "currency": record.currency,
        "volume_unit": record.volume_unit,
        "amount_unit": record.amount_unit,
        "adjustment_mode": record.adjustment_mode.value,
        "adjustment_factor": (
            _adjustment_factor_to_dict(record.adjustment_factor)
            if record.adjustment_factor is not None
            else None
        ),
        "availability": _availability_to_dict(record.availability),
        "provider_evidence_id": record.provider_evidence_id,
    }


def daily_bar_from_dict(data: object) -> DailyBar:
    data = _require_mapping(data)
    _require_schema_version(data)
    try:
        adjustment_factor = _require_key(data, "adjustment_factor")
        return DailyBar(
            schema_version=str(_require_key(data, "schema_version")),
            instrument_id=_instrument_id(_require_key(data, "instrument_id"), "instrument_id"),
            session_date=_date(_require_key(data, "session_date"), "session_date"),
            open=_decimal(_require_key(data, "open"), "open"),
            high=_decimal(_require_key(data, "high"), "high"),
            low=_decimal(_require_key(data, "low"), "low"),
            close=_decimal(_require_key(data, "close"), "close"),
            pre_close=_optional_decimal(_require_key(data, "pre_close"), "pre_close"),
            volume=_decimal(_require_key(data, "volume"), "volume"),
            amount=_decimal(_require_key(data, "amount"), "amount"),
            currency=str(_require_key(data, "currency")),
            volume_unit=str(_require_key(data, "volume_unit")),
            amount_unit=str(_require_key(data, "amount_unit")),
            adjustment_mode=AdjustmentMode(str(_require_key(data, "adjustment_mode"))),
            adjustment_factor=(
                None
                if adjustment_factor is None
                else _adjustment_factor_from_dict(adjustment_factor)
            ),
            availability=_availability_from_dict(data["availability"]),  # type: ignore[arg-type]
            provider_evidence_id=str(_require_key(data, "provider_evidence_id")),
        )
    except (ValueError, MarketDataError) as error:
        raise MalformedRecordError(f"invalid daily bar payload: {error}") from error


def trading_session_to_dict(record: TradingSession) -> dict[str, object]:
    return {
        "schema_version": CANONICAL_RECORD_SCHEMA_VERSION,
        "calendar_id": record.calendar_id,
        "session_date": record.session_date.isoformat(),
        "is_open": record.is_open,
        "note": record.note,
        "snapshot_version": record.snapshot_version,
    }


def trading_session_from_dict(data: object) -> TradingSession:
    data = _require_mapping(data)
    _require_schema_version(data)
    try:
        return TradingSession(
            calendar_id=str(_require_key(data, "calendar_id")),
            session_date=_date(_require_key(data, "session_date"), "session_date"),
            is_open=bool(_require_key(data, "is_open")),
            note=(None if data.get("note") is None else str(data["note"])),
            snapshot_version=str(_require_key(data, "snapshot_version")),
        )
    except (ValueError, MarketDataError) as error:
        raise MalformedRecordError(f"invalid trading session payload: {error}") from error


def tradability_status_to_dict(record: TradabilityStatus) -> dict[str, object]:
    return {
        "schema_version": CANONICAL_RECORD_SCHEMA_VERSION,
        "instrument_id": str(record.instrument_id),
        "session_date": record.session_date.isoformat(),
        "status": record.status.value,
        "reason": record.reason,
        "availability": _availability_to_dict(record.availability),
        "provenance": record.provenance,
    }


def tradability_status_from_dict(data: object) -> TradabilityStatus:
    data = _require_mapping(data)
    _require_schema_version(data)
    try:
        return TradabilityStatus(
            instrument_id=_instrument_id(_require_key(data, "instrument_id"), "instrument_id"),
            session_date=_date(_require_key(data, "session_date"), "session_date"),
            status=TradabilityStatusKind(str(_require_key(data, "status"))),
            reason=(None if data.get("reason") is None else str(data["reason"])),
            availability=_availability_from_dict(data["availability"]),  # type: ignore[arg-type]
            provenance=str(_require_key(data, "provenance")),
        )
    except (ValueError, MarketDataError) as error:
        raise MalformedRecordError(f"invalid tradability payload: {error}") from error


def corporate_action_to_dict(record: CorporateAction) -> dict[str, object]:
    return {
        "schema_version": CANONICAL_RECORD_SCHEMA_VERSION,
        "action_id": record.action_id,
        "instrument_id": str(record.instrument_id),
        "action_kind": record.action_kind.value,
        "ex_date": record.ex_date.isoformat(),
        "record_date": record.record_date.isoformat() if record.record_date else None,
        "pay_date": record.pay_date.isoformat() if record.pay_date else None,
        "cash_amount": str(record.cash_amount.amount) if record.cash_amount else None,
        "share_ratio": str(record.share_ratio) if record.share_ratio is not None else None,
        "revision": record.revision,
        "availability": _availability_to_dict(record.availability),
        "provenance": record.provenance,
    }


def corporate_action_from_dict(data: object) -> CorporateAction:
    data = _require_mapping(data)
    _require_schema_version(data)
    try:
        return CorporateAction(
            action_id=str(_require_key(data, "action_id")),
            instrument_id=_instrument_id(_require_key(data, "instrument_id"), "instrument_id"),
            action_kind=CorporateActionKind(str(_require_key(data, "action_kind"))),
            ex_date=_date(_require_key(data, "ex_date"), "ex_date"),
            record_date=_optional_date(_require_key(data, "record_date"), "record_date"),
            pay_date=_optional_date(_require_key(data, "pay_date"), "pay_date"),
            cash_amount=_optional_money(_require_key(data, "cash_amount"), "cash_amount"),
            share_ratio=_optional_decimal(_require_key(data, "share_ratio"), "share_ratio"),
            revision=int(_require_key(data, "revision")),  # type: ignore[arg-type]
            availability=_availability_from_dict(data["availability"]),  # type: ignore[arg-type]
            provenance=str(_require_key(data, "provenance")),
        )
    except (ValueError, MarketDataError) as error:
        raise MalformedRecordError(f"invalid corporate action payload: {error}") from error
