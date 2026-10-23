"""ChStockDataProvider: the anti-corruption adapter for ``chstockdata``.

The adapter is the only place in this repository allowed to touch the vendor
library, and that import happens lazily inside adapter construction. It maps
vendor symbols, dates, units, nulls, classifications, and exceptions into
canonical market contracts explicitly; provider classification, ETF subtype,
and trading rules are never promoted into Instrument Master authority.

Two layers share this module:

* :class:`ChStockDataClient` 鈥?the narrow vendor boundary. The optional
  default implementation wraps the pinned ``chstockdata`` package; tests and
  recorded fixtures supply a deterministic stand-in.
* :class:`ChStockDataProvider` 鈥?canonical mapping, provider evidence,
  request digests, and typed failures over canonical requests.

Raw payload shapes (recorded in ``third_party/SOURCES.yaml``):

``daily_bars``
    ``{"columns": [...], "rows": [{"Date", "Open", "High", "Low", "Close",
    "Volume", "Amount"}], "volume_unit", "amount_unit", "covered_start",
    "covered_end"}``. Units are declared by the client from the vendor's
    documented fact; the mapping normalizes them exactly once and fails
    closed on unknown or unproven units.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from typing import Protocol, cast, runtime_checkable

from systematic_investing import BASE_CURRENCY
from systematic_investing.data.contracts import (
    ProviderErrorCode,
    ProviderEvidence,
    ProviderFailure,
    ProviderSuccess,
)
from systematic_investing.data.ports import (
    CalendarRequest,
    CorporateActionRequest,
    DailyBarRequest,
    TradabilityRequest,
)
from systematic_investing.domain.identifiers import InstrumentId, require_session_date
from systematic_investing.domain.market import (
    DAILY_BAR_SCHEMA_VERSION,
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
from systematic_investing.domain.money import Money
from systematic_investing.instrument_master.models import (
    InvalidRuleProfileError,
    LotRule,
    MarketFeeTaxRule,
    OddLotSellPolicy,
    PriceLimitBasis,
    PriceLimitRule,
    RuleCandidate,
    RuleKind,
    RuleSource,
    SettlementRule,
)

# The pinned provider release this adapter was reviewed and qualified against.
# ``third_party/SOURCES.yaml`` records the exact commit and license review.
PINNED_CHSTOCKDATA_VERSION = "0.3.0"

# Exchange-local time used for derived information-availability timestamps.
# A fixed UTC+8 offset matches the pinned provider package and mainland China
# exchange practice (no daylight saving since 1991).
MARKET_TIMEZONE = timezone(timedelta(hours=8))
EXCHANGE_SESSION_OPEN = time(9, 30)
EXCHANGE_SESSION_CLOSE = time(15, 0)

_VOLUME_UNITS: Mapping[str, tuple[Decimal, str]] = {
    "SHARE": (Decimal(1), "SHARE"),
    "LOT": (Decimal(100), "SHARE"),
}
_AMOUNT_UNITS: Mapping[str, tuple[Decimal, str]] = {
    "CNY": (Decimal(1), BASE_CURRENCY),
    "YUAN": (Decimal(1), BASE_CURRENCY),
}
_UNKNOWN_UNIT = "UNKNOWN"

_DAILY_BAR_REQUIRED_COLUMNS = (
    "Date",
    "Open",
    "High",
    "Low",
    "Close",
    "pre_close",
    "Volume",
    "Amount",
)
_DAILY_BAR_REQUIRED_ROW_KEYS = ("Date", "Open", "High", "Low", "Close", "Volume", "Amount")


class ChStockDataAdapterError(Exception):
    """Base class for vendor-boundary errors raised by the adapter client."""


class ChStockDataUnavailableError(ChStockDataAdapterError):
    """The vendor could not supply the requested fact (network, rate limit, empty)."""


class ChStockDataConfigurationError(ChStockDataAdapterError):
    """The vendor library is missing, misconfigured, or not the pinned release."""


class ChStockDataSchemaDriftError(ChStockDataAdapterError):
    """The vendor returned a shape or enum outside the documented contract."""


class ChStockDataMalformedError(ChStockDataAdapterError):
    """The vendor returned unusable values inside the documented shape."""


class ChStockDataPartialCoverageError(ChStockDataAdapterError):
    """The vendor answered with an incomplete window; a half dataset is a failure."""


class ChStockDataUnsupportedCapabilityError(ChStockDataAdapterError):
    """The vendor response carries a fact outside the M0 supported scope."""


def _require_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


@dataclass(frozen=True)
class RawVendorResponse:
    """One vendor call's raw, vendor-shaped payload plus its provenance.

    Raw shapes never enter domain APIs; this object exists only inside the
    adapter boundary and its fixtures.
    """

    capability: str
    payload: Mapping[str, object]
    upstream_source: str
    observed_at: datetime | None = None
    warnings: tuple[str, ...] = field(default=())

    def __post_init__(self) -> None:
        _require_text(self.capability, "capability")
        _require_text(self.upstream_source, "upstream_source")
        if not isinstance(self.payload, Mapping):
            raise ValueError("payload must be a mapping")
        if self.observed_at is not None and (
            not isinstance(self.observed_at, datetime) or self.observed_at.tzinfo is None
        ):
            raise ValueError("observed_at must be a timezone-aware datetime or None")
        if not isinstance(self.warnings, tuple) or not all(
            isinstance(warning, str) and warning for warning in self.warnings
        ):
            raise ValueError("warnings must be a tuple of non-empty strings")


@runtime_checkable
class ChStockDataClient(Protocol):
    """The narrow vendor boundary the adapter consumes.

    Implementations return raw payloads (never canonical records) and raise
    :class:`ChStockDataAdapterError` for expected vendor failures.
    """

    def provider_version(self) -> str:
        """The resolved vendor library version, for evidence and pin checks."""
        ...

    def daily_bars(
        self, *, instrument_id: InstrumentId, start_date: date, end_date: date
    ) -> RawVendorResponse:
        """Raw daily bars for one canonical instrument identity."""
        ...

    def calendar(
        self, *, calendar_id: str, start_date: date, end_date: date
    ) -> RawVendorResponse:
        """Raw open-session days plus the vendor's covered window."""
        ...

    def suspension(
        self, *, instrument_id: InstrumentId, session_date: date
    ) -> RawVendorResponse:
        """Raw per-session suspension snapshot for one instrument."""
        ...

    def corporate_actions(
        self,
        *,
        instrument_id: InstrumentId,
        start_date: date,
        end_date: date,
        instrument_kind: str,
    ) -> RawVendorResponse:
        """Raw dividend/distribution action records for one instrument."""
        ...


    def rule_candidates(
        self, *, instrument_id: InstrumentId, session_date: date
    ) -> RawVendorResponse:
        """Raw advisory rule profiles for one instrument and session."""
        ...


def canonical_payload_text(payload: object) -> str:
    """Render a raw payload as canonical JSON for stable checksumming."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


_VENDOR_EXCHANGE_PREFIXES: Mapping[str, str] = {"XSHG": "sh", "XSHE": "sz"}


def import_chstockdata_library() -> object:
    """Import the optional vendor library. This is the only vendor import site."""
    try:
        import chstockdata
    except ImportError as error:
        raise ChStockDataConfigurationError(
            "chstockdata is not installed; install the pinned release recorded in "
            "third_party/SOURCES.yaml or inject a client explicitly"
        ) from error
    return chstockdata


def validate_library_version(
    version: str, *, pinned: str = PINNED_CHSTOCKDATA_VERSION
) -> str:
    """Fail closed unless the resolved vendor release is the pinned one."""
    if version != pinned:
        raise ChStockDataConfigurationError(
            f"chstockdata {version!r} does not match the pinned qualified release "
            f"{pinned!r}; upgrades require contract, ETF, golden, and smoke re-qualification"
        )
    return version


def _vendor_symbol(instrument_id: InstrumentId) -> str:
    prefix = _VENDOR_EXCHANGE_PREFIXES.get(instrument_id.exchange.value)
    if prefix is None:
        raise ChStockDataConfigurationError(
            f"no vendor symbol mapping for exchange {instrument_id.exchange.value!r}"
        )
    return f"{prefix}{instrument_id.symbol}"


def _frame_records(
    frame: object,
) -> tuple[tuple[str, ...], tuple[Mapping[str, object], ...]]:
    """Extract vendor rows without leaking frame types past this boundary."""
    columns = getattr(frame, "columns", None)
    to_dict = getattr(frame, "to_dict", None)
    if columns is None or not callable(to_dict):
        raise ChStockDataSchemaDriftError(
            "vendor frame does not expose the documented columns/to_dict surface"
        )
    records = to_dict(orient="records")
    if not isinstance(records, list):
        raise ChStockDataSchemaDriftError("vendor frame did not produce record rows")
    rows: list[Mapping[str, object]] = []
    for record in records:
        if not isinstance(record, Mapping):
            raise ChStockDataSchemaDriftError("vendor frame row is not a mapping")
        row = dict(record)
        stamped = row.get("Date")
        if isinstance(stamped, datetime):
            row["Date"] = stamped.date().isoformat()
        elif isinstance(stamped, date):
            row["Date"] = stamped.isoformat()
        rows.append(row)
    return tuple(str(column) for column in columns), tuple(rows)


class LibraryChStockDataClient:
    """Vendor-boundary client over the pinned ``chstockdata`` package.

    The library import is optional and happens only when no ``library`` object
    is injected, so the whole offline test suite runs without the package.
    Supported methods and raw shapes are recorded in ``third_party/SOURCES.yaml``.
    """

    def __init__(self, *, library: object | None = None) -> None:
        resolved = library if library is not None else import_chstockdata_library()
        version = getattr(resolved, "__version__", None)
        if not isinstance(version, str) or not version:
            raise ChStockDataConfigurationError(
                "chstockdata library did not report a version; refusing to proceed"
            )
        validate_library_version(version)
        self._library = resolved
        self._version = version

    def provider_version(self) -> str:
        return self._version

    def daily_bars(
        self, *, instrument_id: InstrumentId, start_date: date, end_date: date
    ) -> RawVendorResponse:
        """Raw daily bars from the local TDX vipdoc package.

        ``chstockdata.load_vipdoc_daily`` documents volume in shares and amount
        in yuan, so this path has a proven unit contract. The vendor reader
        validates a pure six-digit code and resolves the market from the
        explicit ``market`` argument; prefixed vendor symbols are never
        passed to it. The vendor's online fallback paths do not publish
        their units; they are not used here and must not be used until
        qualification establishes their contract.
        """
        load = getattr(self._library, "load_vipdoc_daily", None)
        if not callable(load):
            raise ChStockDataConfigurationError(
                "pinned chstockdata does not expose load_vipdoc_daily"
            )
        market = _VENDOR_EXCHANGE_PREFIXES[instrument_id.exchange.value]
        frame = load(
            instrument_id.symbol,
            start_date.isoformat(),
            end_date.isoformat(),
            market=market,
        )
        if frame is None or bool(getattr(frame, "empty", True)):
            raise ChStockDataUnavailableError(
                f"chstockdata has no local vipdoc daily history for "
                f"{instrument_id} in "
                f"[{start_date.isoformat()}, {end_date.isoformat()}]; online fallbacks "
                "remain unusable until qualification proves their unit contract"
            )
        columns, rows = _frame_records(frame)
        return RawVendorResponse(
            capability="daily_bars",
            payload={
                "columns": columns,
                "rows": rows,
                "volume_unit": "SHARE",
                "amount_unit": "CNY",
                "covered_start": start_date.isoformat(),
                "covered_end": end_date.isoformat(),
            },
            upstream_source="chstockdata.load_vipdoc_daily (local TDX .day package)",
        )

    def rule_candidates(
        self, *, instrument_id: InstrumentId, session_date: date
    ) -> RawVendorResponse:
        """The pinned vendor publishes no trading-rule profiles at all.

        This is a normal empty result, not a failure: the approved Instrument
        Master remains the only source of lot/settlement/price-limit/fee rules.
        """
        del instrument_id, session_date
        return RawVendorResponse(
            capability="rule_candidates",
            payload={
                "profiles": (),
                "source": "chstockdata publishes no trading-rule profiles",
            },
            upstream_source="chstockdata (no trading-rule profile capability)",
            warnings=(
                "chstockdata publishes no trading-rule profiles; candidates can never "
                "become Instrument Master authority",
            ),
        )

    def _vendor_function(self, name: str) -> Callable[..., object]:
        function = getattr(self._library, name, None)
        if not callable(function):
            raise ChStockDataConfigurationError(
                f"pinned chstockdata does not expose {name}"
            )
        return cast(Callable[..., object], function)

    @staticmethod
    def _vendor_json_payload(text: object, capability: str) -> Mapping[str, object]:
        """Parse a labeled vendor text envelope into its JSON body.

        The vendor's public tools return a text payload with a terminal-status
        marker line before (and, for some capabilities, an evidence comment
        after) the JSON body; the body itself carries the structured status.
        """
        if not isinstance(text, str):
            raise ChStockDataSchemaDriftError(
                f"vendor {capability} payload is not text: {type(text).__name__}"
            )
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise ChStockDataSchemaDriftError(
                f"vendor {capability} payload carries no JSON body"
            )
        try:
            parsed = json.loads(text[start : end + 1])
        except json.JSONDecodeError as error:
            raise ChStockDataSchemaDriftError(
                f"vendor {capability} payload is not parsable JSON: {error}"
            ) from error
        if not isinstance(parsed, dict):
            raise ChStockDataSchemaDriftError(
                f"vendor {capability} payload is not a JSON mapping"
            )
        return parsed

    def calendar(
        self, *, calendar_id: str, start_date: date, end_date: date
    ) -> RawVendorResponse:
        """Whole-market trading calendar from the vendor's local-first
        derivation (labelled online fallback when the local index days are
        stale). Coverage shortfalls are judged by the adapter's coverage
        check, never silently clipped.
        """
        del calendar_id
        load = self._vendor_function("load_trading_calendar")
        calendar = load()
        trading_days = getattr(calendar, "trading_days", None) if calendar else None
        if calendar is None or not trading_days:
            raise ChStockDataUnavailableError(
                "chstockdata trading calendar is unavailable; refresh the local "
                "vipdoc package or provide a qualified calendar source"
            )
        covered_range = getattr(calendar, "covered_range", None) or (
            trading_days[0],
            trading_days[-1],
        )
        limitations = tuple(getattr(calendar, "limitations", ()) or ())
        source = str(getattr(calendar, "source", "unknown"))
        return RawVendorResponse(
            capability="trading_calendar",
            payload={
                "open_days": [str(day) for day in trading_days],
                "covered_start": str(covered_range[0]),
                "covered_end": str(covered_range[1]),
                "source": source,
                "stale": bool(getattr(calendar, "stale", False)),
                "limitations": [str(item) for item in limitations],
            },
            upstream_source=f"chstockdata.load_trading_calendar ({source})",
        )

    def suspension(
        self, *, instrument_id: InstrumentId, session_date: date
    ) -> RawVendorResponse:
        """One instrument's suspension snapshot for exactly one session.

        The vendor fetches the market-wide suspend/resume snapshot for the
        requested date and matches the 6-digit code; absence is a normal
        not-suspended answer for that date. Failed or truncated snapshots
        fail closed instead of becoming silent tradable facts.
        """
        capability = "suspension"
        query = self._vendor_function("get_suspension_info")
        text = query(instrument_id.symbol, session_date.isoformat())
        payload = self._vendor_json_payload(text, capability)
        status = str(payload.get("status", "success"))
        reason = payload.get("reason") or payload.get("error_summary")
        if status.startswith("failed"):
            if "structure" in status:
                raise ChStockDataSchemaDriftError(
                    f"vendor suspension snapshot failed: {status}: {reason}"
                )
            raise ChStockDataUnavailableError(
                f"vendor suspension snapshot unavailable: {status}: {reason}"
            )
        if status == "invalid_input":
            raise ChStockDataConfigurationError(
                f"vendor suspension request rejected: {reason}"
            )
        return RawVendorResponse(
            capability="tradability",
            payload=payload,
            upstream_source=str(
                payload.get("source") or "chstockdata.get_suspension_info"
            ),
        )

    def corporate_actions(
        self,
        *,
        instrument_id: InstrumentId,
        start_date: date,
        end_date: date,
        instrument_kind: str,
    ) -> RawVendorResponse:
        """One bounded page of dividend/distribution records for the
        announcement window; coverage stays complete-or-typed-failure.

        The declared instrument kind routes the vendor capability: stocks
        come from the A-share dividend report, ETF/fund distributions from
        the vendor's fund F10 dividend surface; a missing declaration fails
        closed instead of silently querying the wrong report.
        """
        capability = "corporate_actions"
        if instrument_kind == "ETF":
            vendor_name = "get_fund_corporate_actions"
        elif instrument_kind == "STOCK":
            vendor_name = "get_corporate_actions"
        else:
            raise ChStockDataConfigurationError(
                f"unsupported corporate-actions instrument_kind {instrument_kind!r}"
            )
        query = self._vendor_function(vendor_name)
        text = query(
            instrument_id.symbol,
            start_date.isoformat(),
            end_date.isoformat(),
        )
        payload = self._vendor_json_payload(text, capability)
        status = str(payload.get("status", "success"))
        coverage = payload.get("coverage")
        if status.startswith("failed") or coverage == "unavailable":
            raise ChStockDataUnavailableError(
                f"vendor corporate actions unavailable: status={status}, "
                f"coverage={coverage}: {payload.get('error_summary')}"
            )
        if status == "invalid_input":
            raise ChStockDataConfigurationError(
                f"vendor corporate-actions request rejected: "
                f"{payload.get('error_summary')}"
            )
        return RawVendorResponse(
            capability=capability,
            payload=payload,
            upstream_source=str(
                payload.get("source") or f"chstockdata.{vendor_name}"
            ),
        )


def _payload_checksum(payload: object) -> str:
    return "sha256:" + sha256(canonical_payload_text(payload).encode("utf-8")).hexdigest()


def _request_digest(capability: str, request: Mapping[str, object]) -> str:
    rendered = {"capability": capability, **{key: str(value) for key, value in request.items()}}
    return "sha256:" + sha256(canonical_payload_text(rendered).encode("utf-8")).hexdigest()


def _decimal(value: object, field_name: str) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise ChStockDataMalformedError(f"{field_name} is not a numeric value: {value!r}")
    if isinstance(value, Decimal):
        parsed = value
    elif isinstance(value, (int, float, str)):
        try:
            parsed = Decimal(str(value))
        except InvalidOperation as error:
            raise ChStockDataMalformedError(
                f"{field_name} is not a Decimal value: {value!r}"
            ) from error
    else:
        raise ChStockDataMalformedError(f"{field_name} is not a Decimal value: {value!r}")
    if not parsed.is_finite():
        raise ChStockDataMalformedError(f"{field_name} must be finite, got {value!r}")
    return parsed


def _session_close_availability(session_date: date, retrieved_at: datetime) -> Availability:
    """Daily session facts are final at the exchange close (declared rule)."""
    return Availability(
        information_available_at=datetime.combine(
            session_date, EXCHANGE_SESSION_CLOSE, tzinfo=MARKET_TIMEZONE
        ),
        retrieved_at=retrieved_at,
        availability_basis=AvailabilityBasis.EXCHANGE_RULE,
    )


def _row_availability(
    row: Mapping[str, object],
    *,
    session_date: date,
    retrieved_at: datetime,
) -> Availability:
    declared_basis = row.get("availability_basis")
    declared_time = row.get("information_available_at")
    basis: AvailabilityBasis | None = None
    if declared_basis is not None:
        try:
            basis = AvailabilityBasis(str(declared_basis))
        except ValueError as error:
            raise ChStockDataSchemaDriftError(
                f"unknown availability_basis {declared_basis!r}"
            ) from error
    if declared_time is None and basis is None:
        try:
            return _session_close_availability(session_date, retrieved_at)
        except (MarketDataError, ValueError) as error:
            raise ChStockDataMalformedError(str(error)) from error
    information_at: datetime | None = None
    if declared_time is not None:
        try:
            information_at = datetime.fromisoformat(str(declared_time))
        except ValueError as error:
            raise ChStockDataMalformedError(
                f"information_available_at is not an ISO datetime: {declared_time!r}"
            ) from error
        if information_at.tzinfo is None:
            raise ChStockDataMalformedError("information_available_at must be timezone-aware")
    try:
        return Availability(
            information_available_at=information_at,
            retrieved_at=retrieved_at,
            availability_basis=(
                basis
                if basis is not None
                else (
                    AvailabilityBasis.OBSERVED
                    if information_at is not None
                    else AvailabilityBasis.UNKNOWN
                )
            ),
        )
    except (MarketDataError, ValueError) as error:
        raise ChStockDataMalformedError(str(error)) from error


@dataclass(frozen=True)
class RuleCandidateRequest:
    """Ask the vendor for advisory trading-rule candidates for one session.

    Candidates are adjudicated against the approved Instrument Master and can
    never become authority; see ``third_party/SOURCES.yaml`` for the boundary.
    """

    instrument_id: InstrumentId
    session_date: date

    def __post_init__(self) -> None:
        if not isinstance(self.instrument_id, InstrumentId):
            raise ValueError("instrument_id must be an InstrumentId")
        require_session_date(self.session_date)


class ChStockDataProvider:
    """Canonical provider-port implementation over the vendor boundary.

    Every call returns canonical records plus :class:`ProviderEvidence`, or a
    typed :class:`ProviderFailure`. Empty success and failure stay distinct.
    """

    PROVIDER_NAME = "chstockdata"
    ADAPTER_NAME = "chstockdata-provider"
    ADAPTER_VERSION = "0.1.0"
    CAPABILITIES = (
        "daily_bars",
        "trading_calendar",
        "tradability",
        "corporate_actions",
        "rule_candidates",
    )

    def __init__(self, *, client: ChStockDataClient, clock: Callable[[], datetime]) -> None:
        self._client = client
        self._clock = clock

    def capability_evidence(self) -> ProviderEvidence | ProviderFailure:
        """Declare the mapped capability surface and the resolved version."""
        capability = "provider_capability"
        request_digest = _request_digest(capability, {})
        try:
            retrieved_at = self._retrieved_at()
            version = self._client.provider_version()
        except ChStockDataAdapterError as error:
            translated = self._translate_exception(error)
            assert translated is not None
            return self._failure(
                error_code=translated[0],
                message=translated[1],
                capability=capability,
                request_digest=request_digest,
                cause=error,
            )
        except Exception as error:
            return self._failure(
                error_code=ProviderErrorCode.INTERNAL_ADAPTER_ERROR,
                message=f"unexpected vendor boundary error: {type(error).__name__}: {error}",
                capability=capability,
                request_digest=request_digest,
                cause=error,
            )
        payload = {"provider_version": version, "capabilities": list(self.CAPABILITIES)}
        return self._evidence(
            capability=capability,
            payload=payload,
            upstream_source=f"{self.PROVIDER_NAME} {version}",
            request_digest=request_digest,
            record_count=len(self.CAPABILITIES),
            retrieved_at=retrieved_at,
        )

    def _retrieved_at(self) -> datetime:
        retrieved_at = self._clock()
        if not isinstance(retrieved_at, datetime) or retrieved_at.tzinfo is None:
            raise ChStockDataConfigurationError(
                "adapter clock must return a timezone-aware datetime"
            )
        return retrieved_at

    def _collect_frames(
        self,
        *,
        capability: str,
        request_digest: str,
        calls: Sequence[tuple[InstrumentId, Callable[[], RawVendorResponse]]],
    ) -> tuple[list[dict[str, object]], datetime, list[str]] | ProviderFailure:
        """Invoke the vendor once per canonical instrument, canonically ordered.

        Returns the recorded frames plus the single retrieval time, or the
        first typed failure. A vendor failure is never mixed with partial
        records: the caller either maps a complete frame set or fails closed.
        """
        frames: list[dict[str, object]] = []
        warnings: list[str] = []
        retrieved_at: datetime | None = None
        for instrument_id, call in calls:
            invocation = self._invoke(
                capability=capability, request_digest=request_digest, call=call
            )
            if isinstance(invocation, ProviderFailure):
                return invocation
            response, retrieved_at = invocation
            frames.append(
                {
                    "instrument_id": str(instrument_id),
                    "upstream_source": response.upstream_source,
                    "payload": response.payload,
                }
            )
            warnings.extend(response.warnings)
        if not frames or retrieved_at is None:
            return self._failure(
                error_code=ProviderErrorCode.INTERNAL_ADAPTER_ERROR,
                message=(
                    "vendor boundary produced no frame for a validated non-empty universe"
                ),
                capability=capability,
                request_digest=request_digest,
            )
        return frames, retrieved_at, warnings

    @staticmethod
    def _composite(frames: Sequence[Mapping[str, object]]) -> tuple[dict[str, object], str]:
        composite_payload: dict[str, object] = {"frames": list(frames)}
        upstream_source = ", ".join(str(frame["upstream_source"]) for frame in frames)
        return composite_payload, upstream_source

    def _evidence(
        self,
        *,
        capability: str,
        payload: Mapping[str, object],
        upstream_source: str,
        request_digest: str,
        record_count: int,
        retrieved_at: datetime,
        warnings: tuple[str, ...] = (),
        evidence_id: str | None = None,
    ) -> ProviderEvidence:
        payload_checksum = _payload_checksum(payload)
        return ProviderEvidence(
            evidence_id=(
                evidence_id
                if evidence_id is not None
                else self._evidence_id(capability, request_digest, payload_checksum)
            ),
            provider_name=self.PROVIDER_NAME,
            provider_version=self._client.provider_version(),
            adapter_name=self.ADAPTER_NAME,
            adapter_version=self.ADAPTER_VERSION,
            capability=capability,
            request_digest=request_digest,
            retrieved_at=retrieved_at,
            upstream_source=upstream_source,
            record_count=record_count,
            payload_checksum=payload_checksum,
            warnings=warnings,
        )

    @classmethod
    def _evidence_id(cls, capability: str, request_digest: str, payload_checksum: str) -> str:
        return (
            f"{cls.PROVIDER_NAME}:{capability}:"
            f"{request_digest.removeprefix('sha256:')[:16]}:"
            f"{payload_checksum.removeprefix('sha256:')[:16]}"
        )

    def _failure(
        self,
        *,
        error_code: ProviderErrorCode,
        message: str,
        capability: str,
        request_digest: str,
        payload: Mapping[str, object] | None = None,
        upstream_source: str | None = None,
        retrieved_at: datetime | None = None,
        cause: BaseException | None = None,
    ) -> ProviderFailure:
        evidence = None
        if payload is not None and upstream_source is not None and retrieved_at is not None:
            try:
                evidence = self._evidence(
                    capability=capability,
                    payload=payload,
                    upstream_source=upstream_source,
                    request_digest=request_digest,
                    record_count=0,
                    retrieved_at=retrieved_at,
                )
            except ChStockDataAdapterError:
                evidence = None
        return ProviderFailure(
            error_code=error_code, message=message, evidence=evidence, cause=cause
        )

    def _translate_exception(
        self, error: BaseException
    ) -> tuple[ProviderErrorCode, str] | None:
        if isinstance(error, ChStockDataUnavailableError):
            return ProviderErrorCode.UNAVAILABLE_OR_RATE_LIMITED, str(error)
        if isinstance(error, ChStockDataConfigurationError):
            return ProviderErrorCode.AUTHENTICATION_OR_CONFIGURATION, str(error)
        if isinstance(error, ChStockDataSchemaDriftError):
            return ProviderErrorCode.SCHEMA_DRIFT, str(error)
        if isinstance(error, ChStockDataMalformedError):
            return ProviderErrorCode.MALFORMED_DATA, str(error)
        if isinstance(error, ChStockDataPartialCoverageError):
            return ProviderErrorCode.PARTIAL_RESULT, str(error)
        if isinstance(error, ChStockDataUnsupportedCapabilityError):
            return ProviderErrorCode.UNSUPPORTED_CAPABILITY, str(error)
        if isinstance(error, ChStockDataAdapterError):
            return ProviderErrorCode.INTERNAL_ADAPTER_ERROR, str(error)
        return None

    def _invoke(
        self,
        *,
        capability: str,
        request_digest: str,
        call: Callable[[], RawVendorResponse],
    ) -> tuple[RawVendorResponse, datetime] | ProviderFailure:
        try:
            retrieved_at = self._retrieved_at()
            response = call()
        except ChStockDataAdapterError as error:
            translated = self._translate_exception(error)
            assert translated is not None
            return self._failure(
                error_code=translated[0],
                message=translated[1],
                capability=capability,
                request_digest=request_digest,
                cause=error,
            )
        except Exception as error:
            return self._failure(
                error_code=ProviderErrorCode.INTERNAL_ADAPTER_ERROR,
                message=f"unexpected vendor boundary error: {type(error).__name__}: {error}",
                capability=capability,
                request_digest=request_digest,
                cause=error,
            )
        if response.capability != capability:
            return self._failure(
                error_code=ProviderErrorCode.INTERNAL_ADAPTER_ERROR,
                message=(
                    f"vendor boundary returned capability {response.capability!r} for "
                    f"request {capability!r}"
                ),
                capability=capability,
                request_digest=request_digest,
            )
        return response, retrieved_at

    def fetch_daily_bars(
        self, request: DailyBarRequest
    ) -> ProviderSuccess[DailyBar] | ProviderFailure:
        """Canonical end-of-session bars for the requested universe and range.

        The vendor reports one frame per instrument; every record receives the
        requested canonical identity, and the result is sorted by canonically
        ordered ``(instrument_id, session_date)`` regardless of input order.
        """
        capability = "daily_bars"
        request_digest = _request_digest(
            capability,
            {
                "instrument_ids": ",".join(
                    str(item) for item in sorted(request.instrument_ids)
                ),
                "start_date": request.start_date.isoformat(),
                "end_date": request.end_date.isoformat(),
                "adjustment_mode": request.adjustment_mode.value,
            },
        )
        collected = self._collect_frames(
            capability=capability,
            request_digest=request_digest,
            calls=tuple(
                (
                    instrument_id,
                    lambda instrument_id=instrument_id: self._client.daily_bars(
                        instrument_id=instrument_id,
                        start_date=request.start_date,
                        end_date=request.end_date,
                    ),
                )
                for instrument_id in sorted(request.instrument_ids)
            ),
        )
        if isinstance(collected, ProviderFailure):
            return collected
        frames, retrieved_at, warnings = collected
        composite_payload, upstream_source = self._composite(frames)
        payload_checksum = _payload_checksum(composite_payload)
        evidence_id = self._evidence_id(capability, request_digest, payload_checksum)
        records: list[DailyBar] = []
        try:
            for frame in frames:
                mapped, mapping_warnings = self._map_daily_bars(
                    payload=frame["payload"],
                    instrument_id=InstrumentId.parse(str(frame["instrument_id"])),
                    request=request,
                    retrieved_at=retrieved_at,
                    evidence_id=evidence_id,
                )
                records.extend(mapped)
                warnings.extend(mapping_warnings)
        except ChStockDataAdapterError as error:
            translated = self._translate_exception(error)
            assert translated is not None
            return self._failure(
                error_code=translated[0],
                message=translated[1],
                capability=capability,
                request_digest=request_digest,
                payload=composite_payload,
                upstream_source=upstream_source,
                retrieved_at=retrieved_at,
                cause=error,
            )
        records.sort(key=lambda record: (record.instrument_id, record.session_date))
        evidence = self._evidence(
            capability=capability,
            payload=composite_payload,
            upstream_source=upstream_source,
            request_digest=request_digest,
            record_count=len(records),
            retrieved_at=retrieved_at,
            warnings=tuple(dict.fromkeys(warnings)),
            evidence_id=evidence_id,
        )
        return ProviderSuccess(records=tuple(records), evidence=evidence)

    def fetch_calendar(
        self, request: CalendarRequest
    ) -> ProviderSuccess[TradingSession] | ProviderFailure:
        """Canonical session records for one named calendar identity.

        The vendor publishes open trading days only; every other date inside
        its covered window is emitted as an explicitly inferred closed session
        (never as silence), and coverage short of the request fails closed.
        """
        capability = "trading_calendar"
        request_digest = _request_digest(
            capability,
            {
                "calendar_id": request.calendar_id,
                "start_date": request.start_date.isoformat(),
                "end_date": request.end_date.isoformat(),
            },
        )
        invocation = self._invoke(
            capability=capability,
            request_digest=request_digest,
            call=lambda: self._client.calendar(
                calendar_id=request.calendar_id,
                start_date=request.start_date,
                end_date=request.end_date,
            ),
        )
        if isinstance(invocation, ProviderFailure):
            return invocation
        response, retrieved_at = invocation
        payload = response.payload
        try:
            records, warnings = self._map_calendar(payload=payload, request=request)
        except ChStockDataAdapterError as error:
            translated = self._translate_exception(error)
            assert translated is not None
            return self._failure(
                error_code=translated[0],
                message=translated[1],
                capability=capability,
                request_digest=request_digest,
                payload=payload,
                upstream_source=response.upstream_source,
                retrieved_at=retrieved_at,
                cause=error,
            )
        records = tuple(sorted(records, key=lambda record: record.session_date))
        evidence = self._evidence(
            capability=capability,
            payload=payload,
            upstream_source=response.upstream_source,
            request_digest=request_digest,
            record_count=len(records),
            retrieved_at=retrieved_at,
            warnings=tuple(dict.fromkeys((*response.warnings, *warnings))),
        )
        return ProviderSuccess(records=records, evidence=evidence)

    def fetch_tradability(
        self, request: TradabilityRequest
    ) -> ProviderSuccess[TradabilityStatus] | ProviderFailure:
        """Canonical point-in-time tradability for the requested universe.

        The vendor snapshot must describe exactly the requested session; a
        same-day snapshot is observed evidence, while a historical session is
        known by the exchange's pre-open suspension-disclosure rule.
        """
        capability = "tradability"
        request_digest = _request_digest(
            capability,
            {
                "instrument_ids": ",".join(
                    str(item) for item in sorted(request.instrument_ids)
                ),
                "session_date": request.session_date.isoformat(),
            },
        )
        collected = self._collect_frames(
            capability=capability,
            request_digest=request_digest,
            calls=tuple(
                (
                    instrument_id,
                    lambda instrument_id=instrument_id: self._client.suspension(
                        instrument_id=instrument_id, session_date=request.session_date
                    ),
                )
                for instrument_id in sorted(request.instrument_ids)
            ),
        )
        if isinstance(collected, ProviderFailure):
            return collected
        frames, retrieved_at, warnings = collected
        composite_payload, upstream_source = self._composite(frames)
        payload_checksum = _payload_checksum(composite_payload)
        evidence_id = self._evidence_id(capability, request_digest, payload_checksum)
        records: list[TradabilityStatus] = []
        try:
            for frame in frames:
                record, frame_warnings = self._map_tradability(
                    payload=frame["payload"],
                    instrument_id=InstrumentId.parse(str(frame["instrument_id"])),
                    request=request,
                    retrieved_at=retrieved_at,
                )
                records.append(record)
                warnings.extend(frame_warnings)
        except ChStockDataAdapterError as error:
            translated = self._translate_exception(error)
            assert translated is not None
            return self._failure(
                error_code=translated[0],
                message=translated[1],
                capability=capability,
                request_digest=request_digest,
                payload=composite_payload,
                upstream_source=upstream_source,
                retrieved_at=retrieved_at,
                cause=error,
            )
        records.sort(key=lambda record: record.instrument_id)
        evidence = self._evidence(
            capability=capability,
            payload=composite_payload,
            upstream_source=upstream_source,
            request_digest=request_digest,
            record_count=len(records),
            retrieved_at=retrieved_at,
            warnings=tuple(dict.fromkeys(warnings)),
            evidence_id=evidence_id,
        )
        return ProviderSuccess(records=tuple(records), evidence=evidence)

    def fetch_corporate_actions(
        self, request: CorporateActionRequest
    ) -> ProviderSuccess[CorporateAction] | ProviderFailure:
        """Canonical, versioned corporate actions for the requested universe.

        Amounts are normalized to per-share terms exactly once: the vendor
        reports per-10-share cash and share ratios. Rights issues are outside
        M0 scope and fail closed rather than being silently dropped. The
        declared instrument kind routes the vendor capability (stocks vs
        ETF/fund distributions) and binds the request identity; it is an
        Instrument-Master-resolved fact, never a symbol inference.
        """
        capability = "corporate_actions"
        request_digest = _request_digest(
            capability,
            {
                "instrument_ids": ",".join(
                    str(item) for item in sorted(request.instrument_ids)
                ),
                "start_date": request.start_date.isoformat(),
                "end_date": request.end_date.isoformat(),
                "instrument_kind": request.instrument_kind,
            },
        )
        collected = self._collect_frames(
            capability=capability,
            request_digest=request_digest,
            calls=tuple(
                (
                    instrument_id,
                    lambda instrument_id=instrument_id: self._client.corporate_actions(
                        instrument_id=instrument_id,
                        start_date=request.start_date,
                        end_date=request.end_date,
                        instrument_kind=request.instrument_kind,
                    ),
                )
                for instrument_id in sorted(request.instrument_ids)
            ),
        )
        if isinstance(collected, ProviderFailure):
            return collected
        frames, retrieved_at, warnings = collected
        composite_payload, upstream_source = self._composite(frames)
        payload_checksum = _payload_checksum(composite_payload)
        evidence_id = self._evidence_id(capability, request_digest, payload_checksum)
        records: list[CorporateAction] = []
        try:
            for frame in frames:
                mapped, frame_warnings = self._map_corporate_actions(
                    payload=frame["payload"],
                    instrument_id=InstrumentId.parse(str(frame["instrument_id"])),
                    request=request,
                    retrieved_at=retrieved_at,
                )
                records.extend(mapped)
                warnings.extend(frame_warnings)
        except ChStockDataAdapterError as error:
            translated = self._translate_exception(error)
            assert translated is not None
            return self._failure(
                error_code=translated[0],
                message=translated[1],
                capability=capability,
                request_digest=request_digest,
                payload=composite_payload,
                upstream_source=upstream_source,
                retrieved_at=retrieved_at,
                cause=error,
            )
        records.sort(key=lambda record: (record.ex_date, record.action_id))
        evidence = self._evidence(
            capability=capability,
            payload=composite_payload,
            upstream_source=upstream_source,
            request_digest=request_digest,
            record_count=len(records),
            retrieved_at=retrieved_at,
            warnings=tuple(dict.fromkeys(warnings)),
            evidence_id=evidence_id,
        )
        return ProviderSuccess(records=tuple(records), evidence=evidence)

    def _map_calendar(
        self,
        *,
        payload: Mapping[str, object],
        request: CalendarRequest,
    ) -> tuple[list[TradingSession], list[str]]:
        open_days_raw = payload.get("open_days")
        if not isinstance(open_days_raw, Sequence) or isinstance(open_days_raw, (str, bytes)):
            raise ChStockDataSchemaDriftError(
                "trading-calendar payload must declare its open_days"
            )
        covered_start = self._coverage_date(
            payload.get("covered_start"), "covered_start"
        )
        covered_end = self._coverage_date(payload.get("covered_end"), "covered_end")
        if covered_start > request.start_date or covered_end < request.end_date:
            raise ChStockDataPartialCoverageError(
                f"vendor coverage [{covered_start}, {covered_end}] does not cover the "
                f"requested [{request.start_date}, {request.end_date}]"
            )
        open_days: set[date] = set()
        for value in open_days_raw:
            day = self._coverage_date(value, "open_days")
            if day < covered_start or day > covered_end:
                raise ChStockDataMalformedError(
                    f"open day {day} lies outside the vendor covered window "
                    f"[{covered_start}, {covered_end}]"
                )
            if day in open_days:
                raise ChStockDataMalformedError(f"duplicate open day {day} in vendor calendar")
            open_days.add(day)
        snapshot_version = "cal-" + _payload_checksum(payload).removeprefix("sha256:")[:16]
        sessions: list[TradingSession] = []
        current = request.start_date
        while current <= request.end_date:
            is_open = current in open_days
            sessions.append(
                TradingSession(
                    calendar_id=request.calendar_id,
                    session_date=current,
                    is_open=is_open,
                    note=(
                        None
                        if is_open
                        else "inferred closed: absent from the vendor open-session list"
                    ),
                    snapshot_version=snapshot_version,
                )
            )
            current = current + timedelta(days=1)
        warnings = (
            ["vendor calendar is marked stale; downstream freshness gating must decide"]
            if bool(payload.get("stale"))
            else []
        )
        return sessions, warnings

    def _map_tradability(
        self,
        *,
        payload: Mapping[str, object],
        instrument_id: InstrumentId,
        request: TradabilityRequest,
        retrieved_at: datetime,
    ) -> tuple[TradabilityStatus, list[str]]:
        suspended = payload.get("suspended")
        if not isinstance(suspended, bool):
            raise ChStockDataMalformedError(
                "tradability payload must declare a boolean suspended flag"
            )
        snapshot_date = self._coverage_date(payload.get("snapshot_date"), "snapshot_date")
        if snapshot_date != request.session_date:
            raise ChStockDataMalformedError(
                f"vendor suspension snapshot describes {snapshot_date}, not the "
                f"requested session {request.session_date}"
            )
        reason = payload.get("suspend_reason")
        if reason is not None and (not isinstance(reason, str) or not reason):
            raise ChStockDataMalformedError(
                "suspend_reason must be a non-empty string or null"
            )
        availability = self._tradability_availability(
            payload=payload, session_date=request.session_date, retrieved_at=retrieved_at
        )
        provenance = payload.get("source")
        if not isinstance(provenance, str) or not provenance:
            raise ChStockDataMalformedError("tradability payload must declare its source")
        return (
            TradabilityStatus(
                instrument_id=instrument_id,
                session_date=request.session_date,
                status=(
                    TradabilityStatusKind.SUSPENDED
                    if suspended
                    else TradabilityStatusKind.TRADABLE
                ),
                reason=str(reason) if suspended and reason is not None else None,
                availability=availability,
                provenance=provenance,
            ),
            [],
        )

    @staticmethod
    def _tradability_availability(
        *,
        payload: Mapping[str, object],
        session_date: date,
        retrieved_at: datetime,
    ) -> Availability:
        observed_text = payload.get("observed_at")
        observed_at: datetime | None = None
        if observed_text is not None:
            if not isinstance(observed_text, str):
                raise ChStockDataMalformedError("observed_at must be an ISO datetime string")
            try:
                observed_at = datetime.fromisoformat(observed_text)
            except ValueError as error:
                raise ChStockDataMalformedError(
                    f"observed_at is not an ISO datetime: {observed_text!r}"
                ) from error
            if observed_at.tzinfo is None:
                raise ChStockDataMalformedError("observed_at must be timezone-aware")
        try:
            if observed_at is not None and observed_at.astimezone(MARKET_TIMEZONE).date() == (
                session_date
            ):
                return Availability(
                    information_available_at=observed_at,
                    retrieved_at=retrieved_at,
                    availability_basis=AvailabilityBasis.OBSERVED,
                )
            return Availability(
                information_available_at=datetime.combine(
                    session_date, EXCHANGE_SESSION_OPEN, tzinfo=MARKET_TIMEZONE
                ),
                retrieved_at=retrieved_at,
                availability_basis=AvailabilityBasis.EXCHANGE_RULE,
            )
        except (MarketDataError, ValueError) as error:
            raise ChStockDataMalformedError(str(error)) from error

    def _map_corporate_actions(
        self,
        *,
        payload: Mapping[str, object],
        instrument_id: InstrumentId,
        request: CorporateActionRequest,
        retrieved_at: datetime,
    ) -> tuple[list[CorporateAction], list[str]]:
        coverage = payload.get("coverage", "complete")
        if coverage not in ("complete", "partial"):
            raise ChStockDataSchemaDriftError(f"unknown corporate-action coverage {coverage!r}")
        if coverage == "partial":
            raise ChStockDataPartialCoverageError(
                "vendor corporate-action coverage is partial; refusing to treat a "
                "truncated page as complete"
            )
        items = payload.get("items")
        if not isinstance(items, Sequence) or isinstance(items, (str, bytes)):
            raise ChStockDataSchemaDriftError(
                "corporate-action payload must declare its items"
            )
        default_source = payload.get("source")
        records: list[CorporateAction] = []
        seen_ids: set[str] = set()
        for index, raw_item in enumerate(items):
            if not isinstance(raw_item, Mapping):
                raise ChStockDataSchemaDriftError(
                    f"corporate-action item {index} is not a mapping"
                )
            action_id = raw_item.get("source_identifier")
            if not isinstance(action_id, str) or not action_id:
                raise ChStockDataMalformedError(
                    f"corporate-action item {index} has no stable source identifier"
                )
            if action_id in seen_ids:
                raise ChStockDataMalformedError(
                    f"duplicate corporate action {action_id} in one vendor response"
                )
            seen_ids.add(action_id)
            rights = self._per_ten_value(raw_item.get("rights_issue"), "rights_issue")
            if rights not in (None, Decimal("0")):
                raise ChStockDataUnsupportedCapabilityError(
                    f"corporate action {action_id} is a rights issue, which is outside "
                    "the M0 supported scope"
                )
            cash_per_ten = self._per_ten_value(raw_item.get("cash_dividend"), "cash_dividend")
            stock_per_ten = self._per_ten_value(
                raw_item.get("stock_dividend"), "stock_dividend"
            )
            transfer_per_ten = self._per_ten_value(
                raw_item.get("capital_reserve_transfer"), "capital_reserve_transfer"
            )
            share_grant = (stock_per_ten or Decimal("0")) + (
                transfer_per_ten or Decimal("0")
            )
            has_cash = cash_per_ten is not None and cash_per_ten > 0
            has_shares = share_grant > 0
            if not has_cash and not has_shares:
                raise ChStockDataMalformedError(
                    f"corporate action {action_id} carries no economic terms"
                )
            ratio = (Decimal("1") + share_grant / Decimal("10")) if has_shares else None
            if has_cash and has_shares:
                action_kind = CorporateActionKind.DISTRIBUTION
            elif has_cash:
                action_kind = CorporateActionKind.CASH_DIVIDEND
            elif ratio is not None and ratio > 1:
                action_kind = CorporateActionKind.SPLIT
            elif ratio is not None and ratio < 1:
                action_kind = CorporateActionKind.CONSOLIDATION
            else:
                raise ChStockDataMalformedError(
                    f"corporate action {action_id} has a non-economic share ratio"
                )
            ex_date = self._required_iso_date(raw_item.get("ex_dividend_date"), "ex_dividend_date")
            announcement_date = self._required_iso_date(
                raw_item.get("announcement_date"), "announcement_date"
            )
            record_date = self._optional_iso_date(raw_item.get("equity_record_date"))
            pay_date = self._optional_iso_date(raw_item.get("payment_date"))
            source = raw_item.get("source") or default_source
            if not isinstance(source, str) or not source:
                raise ChStockDataMalformedError(
                    f"corporate action {action_id} has no provenance source"
                )
            identifier_kind = raw_item.get("source_identifier_kind")
            provenance = (
                f"{source} ({identifier_kind})" if isinstance(identifier_kind, str) else source
            )
            availability = self._corporate_action_availability(
                announcement_date=announcement_date, retrieved_at=retrieved_at
            )
            try:
                record = CorporateAction(
                    action_id=action_id,
                    instrument_id=instrument_id,
                    action_kind=action_kind,
                    ex_date=ex_date,
                    record_date=record_date,
                    pay_date=pay_date,
                    cash_amount=(
                        Money(cash_per_ten / Decimal("10")) if has_cash else None
                    ),
                    share_ratio=ratio,
                    revision=1,
                    availability=availability,
                    provenance=provenance,
                )
            except (MarketDataError, ValueError) as error:
                raise ChStockDataMalformedError(
                    f"corporate action {action_id} violates the canonical contract: {error}"
                ) from error
            records.append(record)
        return records, []

    @staticmethod
    def _per_ten_value(value: object, field_name: str) -> Decimal | None:
        if value in (None, ""):
            return None
        if not isinstance(value, Mapping):
            raise ChStockDataSchemaDriftError(
                f"{field_name} must be a per-10-share mapping or null"
            )
        unit = value.get("unit")
        if unit != "per_10_shares":
            raise ChStockDataSchemaDriftError(
                f"{field_name} declares an unknown unit {unit!r}; expected 'per_10_shares'"
            )
        amount = value.get("value")
        if amount is None:
            return None
        return _decimal(amount, f"{field_name}.value")

    @staticmethod
    def _required_iso_date(value: object, field_name: str) -> date:
        if not isinstance(value, str) or not value:
            raise ChStockDataMalformedError(f"{field_name} must be an ISO date")
        try:
            return date.fromisoformat(value)
        except ValueError as error:
            raise ChStockDataMalformedError(
                f"{field_name} is not an ISO date: {value!r}"
            ) from error

    @classmethod
    def _optional_iso_date(cls, value: object) -> date | None:
        if value in (None, ""):
            return None
        return cls._required_iso_date(value, "date")

    @staticmethod
    def _corporate_action_availability(
        *, announcement_date: date, retrieved_at: datetime
    ) -> Availability:
        """A date-granular announcement is treated as knowable no earlier than
        the end of its announcement day."""
        try:
            return Availability(
                information_available_at=datetime.combine(
                    announcement_date,
                    time(23, 59, 59),
                    tzinfo=MARKET_TIMEZONE,
                ),
                retrieved_at=retrieved_at,
                availability_basis=AvailabilityBasis.INFERRED,
            )
        except (MarketDataError, ValueError) as error:
            raise ChStockDataMalformedError(str(error)) from error

    def fetch_rule_candidates(
        self, request: RuleCandidateRequest
    ) -> ProviderSuccess[RuleCandidate] | ProviderFailure:
        """Advisory rule candidates mapped to canonical candidate contracts.

        A candidate is provider evidence only. Consumers must adjudicate it
        against the approved Instrument Master, which either governs the
        session or fails closed; a candidate is never promoted.
        """
        capability = "rule_candidates"
        request_digest = _request_digest(
            capability,
            {
                "instrument_id": str(request.instrument_id),
                "session_date": request.session_date.isoformat(),
            },
        )
        invocation = self._invoke(
            capability=capability,
            request_digest=request_digest,
            call=lambda: self._client.rule_candidates(
                instrument_id=request.instrument_id, session_date=request.session_date
            ),
        )
        if isinstance(invocation, ProviderFailure):
            return invocation
        response, retrieved_at = invocation
        payload = response.payload
        try:
            records = self._map_rule_candidates(payload=payload, request=request)
        except ChStockDataAdapterError as error:
            translated = self._translate_exception(error)
            assert translated is not None
            return self._failure(
                error_code=translated[0],
                message=translated[1],
                capability=capability,
                request_digest=request_digest,
                payload=payload,
                upstream_source=response.upstream_source,
                retrieved_at=retrieved_at,
                cause=error,
            )
        records = tuple(
            sorted(
                records,
                key=lambda record: (
                    record.rule_kind.value,
                    record.proposed_value.profile_id,
                    record.proposed_value.effective_from,
                ),
            )
        )
        evidence = self._evidence(
            capability=capability,
            payload=payload,
            upstream_source=response.upstream_source,
            request_digest=request_digest,
            record_count=len(records),
            retrieved_at=retrieved_at,
            warnings=response.warnings,
        )
        return ProviderSuccess(records=records, evidence=evidence)

    def _map_rule_candidates(
        self,
        *,
        payload: Mapping[str, object],
        request: RuleCandidateRequest,
    ) -> list[RuleCandidate]:
        profiles = payload.get("profiles")
        if not isinstance(profiles, Sequence) or isinstance(profiles, (str, bytes)):
            raise ChStockDataSchemaDriftError(
                "rule-candidate payload must declare its profiles"
            )
        source_label = payload.get("source")
        candidates: list[RuleCandidate] = []
        for index, raw_profile in enumerate(profiles):
            if not isinstance(raw_profile, Mapping):
                raise ChStockDataSchemaDriftError(
                    f"rule-candidate profile {index} is not a mapping"
                )
            rule_kind = self._rule_kind(raw_profile.get("rule_kind"))
            profile_id = raw_profile.get("profile_id")
            if not isinstance(profile_id, str) or not profile_id:
                raise ChStockDataSchemaDriftError(
                    f"rule-candidate profile {index} needs a profile_id"
                )
            effective_from = self._required_iso_date(
                raw_profile.get("effective_from"), "effective_from"
            )
            effective_to = self._optional_iso_date(raw_profile.get("effective_to"))
            source = self._rule_source(raw_profile.get("source"))
            values = raw_profile.get("values")
            if not isinstance(values, Mapping):
                raise ChStockDataSchemaDriftError(
                    f"rule-candidate profile {index} must declare values"
                )
            proposed_value = self._build_rule_candidate(
                rule_kind=rule_kind,
                profile_id=profile_id,
                effective_from=effective_from,
                effective_to=effective_to,
                source=source,
                values=values,
            )
            candidates.append(
                RuleCandidate(
                    instrument_id=request.instrument_id,
                    session_date=request.session_date,
                    rule_kind=rule_kind,
                    proposed_value=proposed_value,
                    proposed_by=(
                        f"{self.PROVIDER_NAME}:{source_label}"
                        if isinstance(source_label, str) and source_label
                        else self.PROVIDER_NAME
                    ),
                )
            )
        return candidates

    @staticmethod
    def _rule_kind(value: object) -> RuleKind:
        try:
            return RuleKind(str(value))
        except ValueError as error:
            raise ChStockDataSchemaDriftError(
                f"unknown vendor rule kind {value!r}"
            ) from error

    @staticmethod
    def _rule_source(value: object) -> RuleSource:
        if not isinstance(value, Mapping):
            raise ChStockDataSchemaDriftError("rule-candidate source must be a mapping")
        authority = value.get("authority")
        reference = value.get("reference")
        accessed_on = value.get("accessed_on")
        if not isinstance(authority, str) or not authority:
            raise ChStockDataSchemaDriftError("rule-candidate source needs an authority")
        if not isinstance(reference, str) or not reference:
            raise ChStockDataSchemaDriftError("rule-candidate source needs a reference")
        try:
            return RuleSource(
                authority=authority,
                reference=reference,
                accessed_on=ChStockDataProvider._required_iso_date(accessed_on, "accessed_on"),
            )
        except (ValueError, InvalidRuleProfileError) as error:
            raise ChStockDataSchemaDriftError(str(error)) from error

    @staticmethod
    def _build_rule_candidate(
        *,
        rule_kind: RuleKind,
        profile_id: str,
        effective_from: date,
        effective_to: date | None,
        source: RuleSource,
        values: Mapping[str, object],
    ) -> LotRule | SettlementRule | PriceLimitRule | MarketFeeTaxRule:
        common = {
            "profile_id": profile_id,
            "effective_from": effective_from,
            "effective_to": effective_to,
            "source": source,
        }
        try:
            if rule_kind is RuleKind.LOT:
                ChStockDataProvider._reject_unknown_keys(
                    values, {"board_lot", "buy_increment", "odd_lot_sell_policy"}, "LOT"
                )
                return LotRule(
                    **common,
                    board_lot=int(values.get("board_lot", 100)),
                    buy_increment=int(values.get("buy_increment", 100)),
                    odd_lot_sell_policy=OddLotSellPolicy(
                        str(values.get("odd_lot_sell_policy", "ALLOWED"))
                    ),
                )
            if rule_kind is RuleKind.SETTLEMENT:
                ChStockDataProvider._reject_unknown_keys(
                    values, {"sessions_until_sellable"}, "SETTLEMENT"
                )
                return SettlementRule(
                    **common,
                    sessions_until_sellable=int(values.get("sessions_until_sellable", 1)),
                )
            if rule_kind is RuleKind.PRICE_LIMIT:
                ChStockDataProvider._reject_unknown_keys(
                    values, {"basis", "limit_percent", "tick_size"}, "PRICE_LIMIT"
                )
                return PriceLimitRule(
                    **common,
                    basis=PriceLimitBasis(str(values.get("basis", "PREVIOUS_CLOSE"))),
                    limit_percent=_decimal(values.get("limit_percent", "0.10"), "limit_percent"),
                    tick_size=_decimal(values.get("tick_size", "0.01"), "tick_size"),
                )
            ChStockDataProvider._reject_unknown_keys(
                values, {"stamp_tax_sell_rate", "transfer_fee_rate"}, "MARKET_FEE_TAX"
            )
            return MarketFeeTaxRule(
                **common,
                stamp_tax_sell_rate=_decimal(
                    values.get("stamp_tax_sell_rate", "0"), "stamp_tax_sell_rate"
                ),
                transfer_fee_rate=_decimal(
                    values.get("transfer_fee_rate", "0"), "transfer_fee_rate"
                ),
            )
        except (ValueError, TypeError, InvalidRuleProfileError) as error:
            raise ChStockDataSchemaDriftError(
                f"vendor rule candidate violates the canonical contract: {error}"
            ) from error

    @staticmethod
    def _reject_unknown_keys(
        values: Mapping[str, object], allowed: set[str], rule_kind: str
    ) -> None:
        unknown = sorted(set(values) - allowed)
        if unknown:
            raise ChStockDataSchemaDriftError(
                f"unknown {rule_kind} candidate fields {unknown}"
            )

    def _map_daily_bars(
        self,
        *,
        payload: Mapping[str, object],
        instrument_id: InstrumentId,
        request: DailyBarRequest,
        retrieved_at: datetime,
        evidence_id: str,
    ) -> tuple[list[DailyBar], list[str]]:
        columns = payload.get("columns")
        if not isinstance(columns, Sequence) or isinstance(columns, (str, bytes)):
            raise ChStockDataSchemaDriftError("daily-bars payload must declare its columns")
        column_names = tuple(str(column) for column in columns)
        missing_columns = [
            column for column in _DAILY_BAR_REQUIRED_COLUMNS if column not in column_names
        ]
        if missing_columns:
            raise ChStockDataSchemaDriftError(
                f"daily-bars payload is missing required columns {missing_columns}"
            )
        unknown_columns = sorted(set(column_names) - set(_DAILY_BAR_REQUIRED_COLUMNS))
        warnings = (
            [f"ignored additive vendor columns {unknown_columns}"] if unknown_columns else []
        )
        rows = payload.get("rows")
        if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
            raise ChStockDataSchemaDriftError("daily-bars payload must declare its rows")
        volume_factor, volume_unit = self._normalized_unit(
            payload.get("volume_unit"), _VOLUME_UNITS, "volume"
        )
        amount_factor, amount_unit = self._normalized_unit(
            payload.get("amount_unit"), _AMOUNT_UNITS, "amount"
        )
        covered_start = self._coverage_date(payload.get("covered_start"), "covered_start")
        covered_end = self._coverage_date(payload.get("covered_end"), "covered_end")
        if covered_start > request.start_date or covered_end < request.end_date:
            raise ChStockDataPartialCoverageError(
                f"vendor coverage [{covered_start}, {covered_end}] does not cover the "
                f"requested [{request.start_date}, {request.end_date}]"
            )
        records: list[DailyBar] = []
        seen_sessions: set[date] = set()
        for index, raw_row in enumerate(rows):
            if not isinstance(raw_row, Mapping):
                raise ChStockDataSchemaDriftError(f"daily-bars row {index} is not a mapping")
            row: Mapping[str, object] = raw_row
            for required in _DAILY_BAR_REQUIRED_ROW_KEYS:
                if required not in row or row[required] is None:
                    raise ChStockDataMalformedError(
                        f"daily-bars row {index} is missing required field {required}"
                    )
            session_date = self._row_session_date(row, index)
            if session_date in seen_sessions:
                raise ChStockDataMalformedError(
                    f"duplicate daily bar for {instrument_id} on {session_date}"
                )
            seen_sessions.add(session_date)
            availability = _row_availability(
                row, session_date=session_date, retrieved_at=retrieved_at
            )
            try:
                raw_pre_close = row.get("pre_close")
                if isinstance(raw_pre_close, float) and raw_pre_close != raw_pre_close:
                    # A vendor NaN pre_close is a missing previous close (a
                    # listing's first local session or a data gap), which the
                    # canonical bar schema represents as None.
                    raw_pre_close = None
                pre_close = (
                    None
                    if raw_pre_close in (None, "")
                    else _decimal(raw_pre_close, "pre_close")
                )
                record = DailyBar(
                    schema_version=DAILY_BAR_SCHEMA_VERSION,
                    instrument_id=instrument_id,
                    session_date=session_date,
                    open=_decimal(row["Open"], "Open"),
                    high=_decimal(row["High"], "High"),
                    low=_decimal(row["Low"], "Low"),
                    close=_decimal(row["Close"], "Close"),
                    pre_close=pre_close,
                    volume=_decimal(row["Volume"], "Volume") * volume_factor,
                    amount=_decimal(row["Amount"], "Amount") * amount_factor,
                    currency=BASE_CURRENCY,
                    volume_unit=volume_unit,
                    amount_unit=amount_unit,
                    adjustment_mode=AdjustmentMode.RAW,
                    adjustment_factor=None,
                    availability=availability,
                    provider_evidence_id=evidence_id,
                )
            except (MarketDataError, ValueError) as error:
                raise ChStockDataMalformedError(
                    f"daily-bars row {index} violates the canonical bar contract: {error}"
                ) from error
            records.append(record)
        return records, warnings

    @staticmethod
    def _normalized_unit(
        declared: object,
        table: Mapping[str, tuple[Decimal, str]],
        field_name: str,
    ) -> tuple[Decimal, str]:
        if declared is None:
            raise ChStockDataSchemaDriftError(
                f"daily-bars payload must declare its {field_name}_unit"
            )
        token = str(declared).strip().upper()
        if token == _UNKNOWN_UNIT:
            raise ChStockDataUnavailableError(
                f"vendor has no proven {field_name} unit contract for this source; "
                "qualification must establish it before use"
            )
        unit = table.get(token)
        if unit is None:
            raise ChStockDataSchemaDriftError(
                f"unknown vendor {field_name}_unit {declared!r}; supported: {sorted(table)}"
            )
        return unit

    @staticmethod
    def _coverage_date(value: object, field_name: str) -> date:
        if not isinstance(value, str) or not value:
            raise ChStockDataSchemaDriftError(
                f"daily-bars payload must declare {field_name} as an ISO date"
            )
        try:
            return date.fromisoformat(value)
        except ValueError as error:
            raise ChStockDataSchemaDriftError(
                f"{field_name} is not an ISO date: {value!r}"
            ) from error

    @staticmethod
    def _row_session_date(row: Mapping[str, object], index: int) -> date:
        value = row.get("Date")
        if isinstance(value, datetime):
            raise ChStockDataMalformedError(
                f"daily-bars row {index} carries a datetime where an exchange-local "
                "session date is required"
            )
        if not isinstance(value, str) or not value:
            raise ChStockDataMalformedError(
                f"daily-bars row {index} must declare Date as an ISO session date"
            )
        try:
            session_date = date.fromisoformat(value)
        except ValueError as error:
            raise ChStockDataMalformedError(
                f"daily-bars row {index} has an invalid session date {value!r}"
            ) from error
        require_session_date(session_date)
        return session_date
