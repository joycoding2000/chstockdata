"""Contract tests: the ChStockDataProvider anti-corruption adapter.

The adapter consumes a narrow ``ChStockDataClient`` boundary that returns
recorded/synthetic vendor-shaped payloads and produces canonical records plus
provider evidence, or a typed failure. Nothing here touches the network or the
optional ``chstockdata`` package.
"""

import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from systematic_investing.adapters.chstockdata.provider import (
    ChStockDataClient,
    ChStockDataConfigurationError,
    ChStockDataProvider,
    ChStockDataSchemaDriftError,
    ChStockDataUnavailableError,
    LibraryChStockDataClient,
    RawVendorResponse,
    RuleCandidateRequest,
    import_chstockdata_library,
)
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
    DataProviderPort,
    TradabilityRequest,
)
from systematic_investing.domain.identifiers import Exchange, InstrumentId
from systematic_investing.domain.market import (
    DAILY_BAR_SCHEMA_VERSION,
    AdjustmentMode,
    AvailabilityBasis,
    CorporateActionKind,
    DailyBar,
    TradabilityStatusKind,
    TradeSide,
)
from systematic_investing.domain.money import Money
from systematic_investing.instrument_master.models import (
    AdjudicationStatus,
    LotRule,
    RuleCandidate,
    RuleKind,
)
from systematic_investing.instrument_master.repository import default_m0_master

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "chstockdata"

MARKET_TZ = timezone(timedelta(hours=8))
RETRIEVED_AT = datetime(2026, 9, 11, 18, 5, tzinfo=MARKET_TZ)

XSHG_510300 = InstrumentId(exchange=Exchange.XSHG, symbol="510300")
XSHG_600519 = InstrumentId(exchange=Exchange.XSHG, symbol="600519")

DAILY_BAR_REQUEST = DailyBarRequest(
    instrument_ids=(XSHG_510300,),
    start_date=date(2026, 9, 10),
    end_date=date(2026, 9, 11),
)


def load_fixture(name: str) -> RawVendorResponse:
    payload = json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))
    return RawVendorResponse(
        capability=payload["capability"],
        payload=payload["payload"],
        upstream_source=payload["upstream_source"],
        observed_at=(
            None
            if payload["observed_at"] is None
            else datetime.fromisoformat(payload["observed_at"])
        ),
        warnings=tuple(payload["warnings"]),
    )


class StubClient:
    """Deterministic in-memory stand-in for the vendor boundary."""

    def __init__(self, *, version: str = "0.3.0") -> None:
        self._version = version
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.responses: dict[str, RawVendorResponse | BaseException] = {}

    def provider_version(self) -> str:
        return self._version

    def _respond(self, capability: str) -> RawVendorResponse:
        response = self.responses.get(capability)
        if response is None:
            raise AssertionError(f"no stub response configured for {capability}")
        if isinstance(response, BaseException):
            raise response
        return response

    def daily_bars(
        self, *, instrument_id: InstrumentId, start_date: date, end_date: date
    ) -> RawVendorResponse:
        self.calls.append(
            (
                "daily_bars",
                {
                    "instrument_id": instrument_id,
                    "start_date": start_date,
                    "end_date": end_date,
                },
            )
        )
        return self._respond("daily_bars")

    def calendar(self, *, calendar_id: str, start_date: date, end_date: date) -> RawVendorResponse:
        self.calls.append(
            (
                "calendar",
                {"calendar_id": calendar_id, "start_date": start_date, "end_date": end_date},
            )
        )
        return self._respond("trading_calendar")

    def suspension(
        self, *, instrument_id: InstrumentId, session_date: date
    ) -> RawVendorResponse:
        self.calls.append(
            ("suspension", {"instrument_id": instrument_id, "session_date": session_date})
        )
        return self._respond("tradability")

    def corporate_actions(
        self,
        *,
        instrument_id: InstrumentId,
        start_date: date,
        end_date: date,
        instrument_kind: str = "STOCK",
    ) -> RawVendorResponse:
        self.calls.append(
            (
                "corporate_actions",
                {
                    "instrument_id": instrument_id,
                    "start_date": start_date,
                    "end_date": end_date,
                    "instrument_kind": instrument_kind,
                },
            )
        )
        return self._respond("corporate_actions")

    def rule_candidates(
        self, *, instrument_id: InstrumentId, session_date: date
    ) -> RawVendorResponse:
        self.calls.append(
            ("rule_candidates", {"instrument_id": instrument_id, "session_date": session_date})
        )
        return self._respond("rule_candidates")


def provider_with(
    response: RawVendorResponse | BaseException,
    *,
    capability: str = "daily_bars",
    version: str = "0.3.0",
) -> ChStockDataProvider:
    client = StubClient(version=version)
    client.responses[capability] = response
    return ChStockDataProvider(client=client, clock=lambda: RETRIEVED_AT)


def bars_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = dict(load_fixture("daily_bars_vipdoc_xshg_510300.json").payload)
    payload.update(overrides)
    return payload


class TestDailyBarMapping:
    def test_maps_canonical_identity_session_and_decimal_prices(self) -> None:
        provider = provider_with(load_fixture("daily_bars_vipdoc_xshg_510300.json"))

        result = provider.fetch_daily_bars(DAILY_BAR_REQUEST)

        assert isinstance(result, ProviderSuccess)
        first, second = result.records
        assert isinstance(first, DailyBar)
        assert first.schema_version == DAILY_BAR_SCHEMA_VERSION
        assert first.instrument_id == XSHG_510300
        assert first.session_date == date(2026, 9, 10)
        assert second.session_date == date(2026, 9, 11)
        assert second.open == Decimal("4.04")
        assert second.high == Decimal("4.1")
        assert second.low == Decimal("3.95")
        assert second.close == Decimal("4.05")
        assert second.adjustment_mode is AdjustmentMode.RAW
        assert second.pre_close == Decimal("4.04")
        assert first.pre_close == Decimal("4.02")
        assert second.currency == "CNY"

    def test_normalizes_declared_vendor_units_exactly_once(self) -> None:
        provider = provider_with(
            RawVendorResponse(
                capability="daily_bars",
                payload=bars_payload(volume_unit="LOT"),
                upstream_source="synthetic lot-unit fixture",
            )
        )

        result = provider.fetch_daily_bars(DAILY_BAR_REQUEST)

        assert isinstance(result, ProviderSuccess)
        second = result.records[1]
        assert second.volume == Decimal("10000000")
        assert second.volume_unit == "SHARE"
        assert second.amount == Decimal("4050000.0")
        assert second.amount_unit == "CNY"

    def test_declares_exchange_rule_close_availability_with_retrieval_time(self) -> None:
        provider = provider_with(load_fixture("daily_bars_vipdoc_xshg_510300.json"))

        result = provider.fetch_daily_bars(DAILY_BAR_REQUEST)

        assert isinstance(result, ProviderSuccess)
        availability = result.records[1].availability
        assert availability.information_available_at == datetime(
            2026, 9, 11, 15, 0, tzinfo=MARKET_TZ
        )
        assert availability.retrieved_at == RETRIEVED_AT
        assert availability.availability_basis is AvailabilityBasis.EXCHANGE_RULE

    def test_attaches_requested_identity_and_normalizes_input_ordering(self) -> None:
        xshen_159915 = InstrumentId(exchange=Exchange.XSHE, symbol="159915")
        client = StubClient()
        client.responses["daily_bars"] = RawVendorResponse(
            capability="daily_bars",
            payload=bars_payload(),
            upstream_source="synthetic universe fixture",
        )
        provider = ChStockDataProvider(client=client, clock=lambda: RETRIEVED_AT)
        request = DailyBarRequest(
            instrument_ids=(XSHG_510300, xshen_159915),
            start_date=date(2026, 9, 10),
            end_date=date(2026, 9, 11),
        )

        result = provider.fetch_daily_bars(request)

        assert isinstance(result, ProviderSuccess)
        assert [record.instrument_id for record in result.records] == [
            xshen_159915,
            xshen_159915,
            XSHG_510300,
            XSHG_510300,
        ]
        assert [call[1]["instrument_id"] for call in client.calls] == [
            xshen_159915,
            XSHG_510300,
        ]


class TestProviderEvidence:
    def test_evidence_records_identity_counts_and_stable_checksums(self) -> None:
        provider = provider_with(load_fixture("daily_bars_vipdoc_xshg_510300.json"))

        result = provider.fetch_daily_bars(DAILY_BAR_REQUEST)
        repeat = provider.fetch_daily_bars(DAILY_BAR_REQUEST)

        assert isinstance(result, ProviderSuccess)
        evidence = result.evidence
        assert isinstance(evidence, ProviderEvidence)
        assert evidence.provider_name == "chstockdata"
        assert evidence.provider_version == "0.3.0"
        assert evidence.adapter_name == ChStockDataProvider.ADAPTER_NAME
        assert evidence.adapter_version == ChStockDataProvider.ADAPTER_VERSION
        assert evidence.capability == "daily_bars"
        assert evidence.record_count == 2
        assert evidence.retrieved_at == RETRIEVED_AT
        assert evidence.upstream_source == "vipdoc local (TDX official hsjday package)"
        assert evidence.request_digest
        assert evidence.payload_checksum
        assert isinstance(repeat, ProviderSuccess)
        assert repeat.evidence.evidence_id == evidence.evidence_id

    def test_evidence_checksum_changes_with_payload_content(self) -> None:
        baseline = provider_with(load_fixture("daily_bars_vipdoc_xshg_510300.json"))
        mutated = provider_with(
            RawVendorResponse(
                capability="daily_bars",
                payload=bars_payload(covered_end="2026-09-10"),
                upstream_source="synthetic mutated fixture",
            )
        )

        baseline_result = baseline.fetch_daily_bars(DAILY_BAR_REQUEST)
        mutated_result = mutated.fetch_daily_bars(DAILY_BAR_REQUEST)

        assert isinstance(baseline_result, ProviderSuccess)
        assert isinstance(mutated_result, ProviderFailure)
        assert mutated_result.evidence is not None
        assert (
            mutated_result.evidence.payload_checksum
            != baseline_result.evidence.payload_checksum
        )

    def test_provider_failure_is_a_value_with_typed_code(self) -> None:
        provider = provider_with(
            RuntimeError("vendor exploded"),
            capability="daily_bars",
        )

        result = provider.fetch_daily_bars(DAILY_BAR_REQUEST)

        assert isinstance(result, ProviderFailure)
        assert result.error_code is ProviderErrorCode.INTERNAL_ADAPTER_ERROR
        assert isinstance(result.cause, RuntimeError)


class TestClientBoundary:
    def test_client_protocol_is_structural(self) -> None:
        assert isinstance(StubClient(), ChStockDataClient)


def bars_response(**overrides: object) -> RawVendorResponse:
    return RawVendorResponse(
        capability="daily_bars",
        payload=bars_payload(**overrides),
        upstream_source="synthetic fixture",
    )


class TestDailyBarFailureModes:
    def test_empty_rows_with_complete_coverage_are_an_empty_success(self) -> None:
        provider = provider_with(bars_response(rows=()))

        result = provider.fetch_daily_bars(DAILY_BAR_REQUEST)

        assert isinstance(result, ProviderSuccess)
        assert result.records == ()
        assert result.evidence.record_count == 0

    def test_partial_coverage_fails_closed_as_partial_result(self) -> None:
        provider = provider_with(bars_response(covered_end="2026-09-10"))

        result = provider.fetch_daily_bars(DAILY_BAR_REQUEST)

        assert isinstance(result, ProviderFailure)
        assert result.error_code is ProviderErrorCode.PARTIAL_RESULT
        assert result.evidence is not None
        assert result.evidence.payload_checksum

    def test_missing_required_column_is_schema_drift(self) -> None:
        provider = provider_with(
            bars_response(columns=["Date", "Open", "High", "Low", "Close", "Volume"])
        )

        result = provider.fetch_daily_bars(DAILY_BAR_REQUEST)

        assert isinstance(result, ProviderFailure)
        assert result.error_code is ProviderErrorCode.SCHEMA_DRIFT
        assert "Amount" in result.message

    def test_additive_columns_are_recorded_and_ignored(self) -> None:
        mutated = [dict(row, TurnoverRate=0.01) for row in bars_payload()["rows"]]
        provider = provider_with(
            bars_response(
                columns=[*bars_payload()["columns"], "TurnoverRate"],
                rows=mutated,
            )
        )

        result = provider.fetch_daily_bars(DAILY_BAR_REQUEST)

        assert isinstance(result, ProviderSuccess)
        assert any("TurnoverRate" in warning for warning in result.evidence.warnings)
        assert result.records[0].close == Decimal("4.04")

    @pytest.mark.parametrize("broken_value", [None, "not-a-number"])
    def test_unusable_required_value_is_malformed_data(self, broken_value: object) -> None:
        rows = [dict(row) for row in bars_payload()["rows"]]
        rows[1]["Close"] = broken_value
        provider = provider_with(bars_response(rows=rows))

        result = provider.fetch_daily_bars(DAILY_BAR_REQUEST)

        assert isinstance(result, ProviderFailure)
        assert result.error_code is ProviderErrorCode.MALFORMED_DATA

    def test_duplicate_session_rows_are_malformed_data(self) -> None:
        rows = [dict(row) for row in bars_payload()["rows"]]
        rows[1]["Date"] = rows[0]["Date"]
        provider = provider_with(bars_response(rows=rows))

        result = provider.fetch_daily_bars(DAILY_BAR_REQUEST)

        assert isinstance(result, ProviderFailure)
        assert result.error_code is ProviderErrorCode.MALFORMED_DATA

    def test_datetime_session_values_are_rejected(self) -> None:
        rows = [dict(row) for row in bars_payload()["rows"]]
        rows[1]["Date"] = "2026-09-11T15:00:00+08:00"
        provider = provider_with(bars_response(rows=rows))

        result = provider.fetch_daily_bars(DAILY_BAR_REQUEST)

        assert isinstance(result, ProviderFailure)
        assert result.error_code is ProviderErrorCode.MALFORMED_DATA

    def test_unknown_unit_token_is_schema_drift(self) -> None:
        provider = provider_with(bars_response(volume_unit="PICUL"))

        result = provider.fetch_daily_bars(DAILY_BAR_REQUEST)

        assert isinstance(result, ProviderFailure)
        assert result.error_code is ProviderErrorCode.SCHEMA_DRIFT
        assert "volume_unit" in result.message

    def test_unproven_unit_contract_fails_closed(self) -> None:
        provider = provider_with(bars_response(volume_unit="UNKNOWN"))

        result = provider.fetch_daily_bars(DAILY_BAR_REQUEST)

        assert isinstance(result, ProviderFailure)
        assert result.error_code is ProviderErrorCode.UNAVAILABLE_OR_RATE_LIMITED

    def test_declared_vendor_unavailability_is_typed(self) -> None:
        provider = provider_with(ChStockDataUnavailableError("tcp pool exhausted"))

        result = provider.fetch_daily_bars(DAILY_BAR_REQUEST)

        assert isinstance(result, ProviderFailure)
        assert result.error_code is ProviderErrorCode.UNAVAILABLE_OR_RATE_LIMITED
        assert isinstance(result.cause, ChStockDataUnavailableError)

    def test_declared_misconfiguration_is_typed(self) -> None:
        provider = provider_with(ChStockDataConfigurationError("library version mismatch"))

        result = provider.fetch_daily_bars(DAILY_BAR_REQUEST)

        assert isinstance(result, ProviderFailure)
        assert result.error_code is ProviderErrorCode.AUTHENTICATION_OR_CONFIGURATION

    def test_vendor_schema_error_is_typed_schema_drift(self) -> None:
        provider = provider_with(ChStockDataSchemaDriftError("unexpected frame columns"))

        result = provider.fetch_daily_bars(DAILY_BAR_REQUEST)

        assert isinstance(result, ProviderFailure)
        assert result.error_code is ProviderErrorCode.SCHEMA_DRIFT

    def test_bar_whose_session_close_is_after_retrieval_is_malformed(self) -> None:
        client = StubClient()
        client.responses["daily_bars"] = bars_response()
        provider = ChStockDataProvider(
            client=client,
            clock=lambda: datetime(2026, 9, 11, 10, 0, tzinfo=MARKET_TZ),
        )

        result = provider.fetch_daily_bars(DAILY_BAR_REQUEST)

        assert isinstance(result, ProviderFailure)
        assert result.error_code is ProviderErrorCode.MALFORMED_DATA
        assert "information_available_at" in result.message


class TestDailyBarAvailabilityEdgeCases:
    def test_explicit_unknown_availability_stays_explicit(self) -> None:
        rows = [dict(row) for row in bars_payload()["rows"]]
        rows[1]["availability_basis"] = "UNKNOWN"
        provider = provider_with(bars_response(rows=rows))

        result = provider.fetch_daily_bars(DAILY_BAR_REQUEST)

        assert isinstance(result, ProviderSuccess)
        availability = result.records[1].availability
        assert availability.availability_basis is AvailabilityBasis.UNKNOWN
        assert availability.information_available_at is None
        assert availability.retrieved_at == RETRIEVED_AT

    def test_vendor_observed_information_time_is_preserved(self) -> None:
        rows = [dict(row) for row in bars_payload()["rows"]]
        rows[1]["information_available_at"] = "2026-09-11T15:30:00+08:00"
        provider = provider_with(bars_response(rows=rows))

        result = provider.fetch_daily_bars(DAILY_BAR_REQUEST)

        assert isinstance(result, ProviderSuccess)
        availability = result.records[1].availability
        assert availability.availability_basis is AvailabilityBasis.OBSERVED
        assert availability.information_available_at == datetime(
            2026, 9, 11, 15, 30, tzinfo=MARKET_TZ
        )

    def test_unknown_availability_basis_token_is_schema_drift(self) -> None:
        rows = [dict(row) for row in bars_payload()["rows"]]
        rows[1]["availability_basis"] = "VIBES"
        provider = provider_with(bars_response(rows=rows))

        result = provider.fetch_daily_bars(DAILY_BAR_REQUEST)

        assert isinstance(result, ProviderFailure)
        assert result.error_code is ProviderErrorCode.SCHEMA_DRIFT


class StubFrame:
    """Minimal stand-in for the vendor's tabular frame shape."""

    def __init__(self, rows: list[dict[str, object]], columns: list[str]) -> None:
        self._rows = rows
        self.columns = columns

    @property
    def empty(self) -> bool:
        return not self._rows

    def to_dict(self, orient: str = "dict") -> list[dict[str, object]]:
        assert orient == "records"
        return [dict(row) for row in self._rows]


class StubLibrary:
    """Minimal stand-in for the pinned vendor library module surface."""

    __version__ = "0.3.0"

    def __init__(self, frames: dict[str, StubFrame | None] | None = None) -> None:
        self.frames = frames or {}
        self.calls: list[tuple[str, str, str, str]] = []
        self.markets: list[str] = []

    def load_vipdoc_daily(
        self,
        code: str,
        start_date: str | None = None,
        end_date: str | None = None,
        *,
        market: str | None = None,
        **kwargs: object,
    ) -> StubFrame | None:
        del kwargs
        assert start_date is not None and end_date is not None
        self.calls.append(("load_vipdoc_daily", code, start_date, end_date))
        self.markets.append(str(market))
        return self.frames.get(code)


def vipdoc_frame() -> StubFrame:
    payload = load_fixture("daily_bars_vipdoc_xshg_510300.json").payload
    return StubFrame([dict(row) for row in payload["rows"]], list(payload["columns"]))


class TestLibraryClientBoundary:
    def test_rejects_a_library_release_other_than_the_pin(self) -> None:
        library = StubLibrary()
        library.__version__ = "9.9.9"

        with pytest.raises(ChStockDataConfigurationError, match=r"0\.3\.0"):
            LibraryChStockDataClient(library=library)

    def test_accepts_the_pinned_release(self) -> None:
        client = LibraryChStockDataClient(library=StubLibrary())

        assert client.provider_version() == "0.3.0"

    @pytest.mark.parametrize(
        ("instrument_id", "pure_code", "market"),
        [
            (XSHG_510300, "510300", "sh"),
            (InstrumentId(exchange=Exchange.XSHE, symbol="159915"), "159915", "sz"),
        ],
    )
    def test_maps_canonical_identity_to_the_vipdoc_call(
        self, instrument_id: InstrumentId, pure_code: str, market: str
    ) -> None:
        library = StubLibrary(frames={pure_code: vipdoc_frame()})
        client = LibraryChStockDataClient(library=library)

        response = client.daily_bars(
            instrument_id=instrument_id,
            start_date=date(2026, 9, 10),
            end_date=date(2026, 9, 11),
        )

        assert library.calls == [
            ("load_vipdoc_daily", pure_code, "2026-09-10", "2026-09-11")
        ]
        assert library.markets == [market]
        assert response.payload["rows"][1]["Date"] == "2026-09-11"
        assert response.payload["volume_unit"] == "SHARE"
        assert response.payload["amount_unit"] == "CNY"
        assert response.payload["covered_start"] == "2026-09-10"
        assert response.payload["covered_end"] == "2026-09-11"
        assert "vipdoc" in response.upstream_source

    def test_missing_local_history_fails_closed(self) -> None:
        client = LibraryChStockDataClient(
            library=StubLibrary(frames={"510300": None})
        )

        with pytest.raises(ChStockDataUnavailableError, match="vipdoc"):
            client.daily_bars(
                instrument_id=XSHG_510300,
                start_date=date(2026, 9, 10),
                end_date=date(2026, 9, 11),
            )

    def test_unexpected_library_errors_propagate_to_the_adapter(self) -> None:
        class ExplodingLibrary(StubLibrary):
            def load_vipdoc_daily(self, *args: object, **kwargs: object) -> None:
                raise RuntimeError("vendor exploded")

        provider = ChStockDataProvider(
            client=LibraryChStockDataClient(library=ExplodingLibrary()),
            clock=lambda: RETRIEVED_AT,
        )

        result = provider.fetch_daily_bars(DAILY_BAR_REQUEST)

        assert isinstance(result, ProviderFailure)
        assert result.error_code is ProviderErrorCode.INTERNAL_ADAPTER_ERROR

    def test_missing_optional_dependency_is_a_configuration_failure(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import sys

        monkeypatch.setitem(sys.modules, "chstockdata", None)

        with pytest.raises(ChStockDataConfigurationError, match="chstockdata"):
            import_chstockdata_library()


CALENDAR_REQUEST = CalendarRequest(
    calendar_id="XSHG", start_date=date(2026, 9, 10), end_date=date(2026, 9, 14)
)
TRADABILITY_REQUEST = TradabilityRequest(
    instrument_ids=(XSHG_600519,), session_date=date(2026, 9, 11)
)
CORPORATE_ACTION_REQUEST = CorporateActionRequest(
    instrument_ids=(XSHG_600519,),
    start_date=date(2026, 1, 1),
    end_date=date(2026, 12, 31),
)
ETF_CORPORATE_ACTION_REQUEST = CorporateActionRequest(
    instrument_ids=(XSHG_510300,),
    start_date=date(2015, 1, 1),
    end_date=date(2022, 12, 31),
    instrument_kind="ETF",
)


class TestCorporateActionRouting:
    def test_etf_requests_bind_the_kind_into_the_request_digest_and_client_call(
        self,
    ) -> None:
        client = StubClient()
        client.responses["corporate_actions"] = load_fixture(
            "corporate_actions_xshg_600519_2026.json"
        )
        provider = ChStockDataProvider(client=client, clock=lambda: RETRIEVED_AT)

        result = provider.fetch_corporate_actions(ETF_CORPORATE_ACTION_REQUEST)

        assert isinstance(result, ProviderSuccess)
        assert client.calls == [
            (
                "corporate_actions",
                {
                    "instrument_id": XSHG_510300,
                    "start_date": date(2015, 1, 1),
                    "end_date": date(2022, 12, 31),
                    "instrument_kind": "ETF",
                },
            )
        ]

    def test_request_kinds_share_the_port_but_not_the_request_digest(self) -> None:
        client = StubClient()
        client.responses["corporate_actions"] = load_fixture(
            "corporate_actions_xshg_600519_2026.json"
        )
        provider = ChStockDataProvider(client=client, clock=lambda: RETRIEVED_AT)

        stock = provider.fetch_corporate_actions(CORPORATE_ACTION_REQUEST)
        etf = provider.fetch_corporate_actions(ETF_CORPORATE_ACTION_REQUEST)
        stock_repeat = provider.fetch_corporate_actions(CORPORATE_ACTION_REQUEST)

        assert isinstance(stock, ProviderSuccess)
        assert isinstance(etf, ProviderSuccess)
        assert stock.evidence.request_digest != etf.evidence.request_digest
        assert stock.evidence.request_digest == stock_repeat.evidence.request_digest


class TestCalendarMapping:
    def test_marks_open_and_inferred_closed_sessions(self) -> None:
        provider = provider_with(
            load_fixture("trading_calendar_xshg_202609.json"),
            capability="trading_calendar",
        )

        result = provider.fetch_calendar(CALENDAR_REQUEST)

        assert isinstance(result, ProviderSuccess)
        assert [(record.session_date, record.is_open) for record in result.records] == [
            (date(2026, 9, 10), True),
            (date(2026, 9, 11), True),
            (date(2026, 9, 12), False),
            (date(2026, 9, 13), False),
            (date(2026, 9, 14), True),
        ]
        assert {record.calendar_id for record in result.records} == {"XSHG"}
        assert len({record.snapshot_version for record in result.records}) == 1
        assert all(record.snapshot_version for record in result.records)
        assert result.evidence.record_count == 5

    def test_partial_coverage_fails_closed(self) -> None:
        fixture = load_fixture("trading_calendar_xshg_202609.json")
        provider = provider_with(
            RawVendorResponse(
                capability="trading_calendar",
                payload={**fixture.payload, "covered_end": "2026-09-11"},
                upstream_source=fixture.upstream_source,
            ),
            capability="trading_calendar",
        )

        result = provider.fetch_calendar(CALENDAR_REQUEST)

        assert isinstance(result, ProviderFailure)
        assert result.error_code is ProviderErrorCode.PARTIAL_RESULT

    def test_stale_calendar_source_is_recorded_as_a_warning(self) -> None:
        fixture = load_fixture("trading_calendar_xshg_202609.json")
        provider = provider_with(
            RawVendorResponse(
                capability="trading_calendar",
                payload={**fixture.payload, "stale": True},
                upstream_source=fixture.upstream_source,
            ),
            capability="trading_calendar",
        )

        result = provider.fetch_calendar(CALENDAR_REQUEST)

        assert isinstance(result, ProviderSuccess)
        assert any("stale" in warning for warning in result.evidence.warnings)

    def test_open_day_outside_the_covered_window_is_malformed(self) -> None:
        fixture = load_fixture("trading_calendar_xshg_202609.json")
        provider = provider_with(
            RawVendorResponse(
                capability="trading_calendar",
                payload={**fixture.payload, "open_days": ["2026-10-01"]},
                upstream_source=fixture.upstream_source,
            ),
            capability="trading_calendar",
        )

        result = provider.fetch_calendar(CALENDAR_REQUEST)

        assert isinstance(result, ProviderFailure)
        assert result.error_code is ProviderErrorCode.MALFORMED_DATA


class TestTradabilityMapping:
    def test_same_day_suspension_snapshot_is_observed(self) -> None:
        provider = provider_with(
            load_fixture("suspension_xshg_600519_20260911.json"),
            capability="tradability",
        )

        result = provider.fetch_tradability(TRADABILITY_REQUEST)

        assert isinstance(result, ProviderSuccess)
        record = result.records[0]
        assert record.instrument_id == XSHG_600519
        assert record.session_date == date(2026, 9, 11)
        assert record.status is TradabilityStatusKind.SUSPENDED
        assert record.reason == "重大事项"
        assert record.provenance == "Eastmoney datacenter RPT_CUSTOM_SUSPEND_DATA_INTERFACE"
        assert record.availability.availability_basis is AvailabilityBasis.OBSERVED
        assert record.availability.information_available_at == datetime(
            2026, 9, 11, 18, 5, tzinfo=MARKET_TZ
        )
        assert record.permitted_sides == frozenset()

    def test_historical_session_uses_the_exchange_rule_open_time(self) -> None:
        fixture = load_fixture("suspension_xshg_600519_20260911.json")
        provider = provider_with(
            RawVendorResponse(
                capability="tradability",
                payload={
                    **fixture.payload,
                    "snapshot_date": "2026-06-01",
                    "as_of_date": "2026-06-01",
                    "observed_at": "2026-09-11T18:05:00+08:00",
                },
                upstream_source=fixture.upstream_source,
            ),
            capability="tradability",
        )
        request = TradabilityRequest(
            instrument_ids=(XSHG_600519,), session_date=date(2026, 6, 1)
        )

        result = provider.fetch_tradability(request)

        assert isinstance(result, ProviderSuccess)
        availability = result.records[0].availability
        assert availability.availability_basis is AvailabilityBasis.EXCHANGE_RULE
        assert availability.information_available_at == datetime(
            2026, 6, 1, 9, 30, tzinfo=MARKET_TZ
        )
        assert availability.retrieved_at == RETRIEVED_AT

    def test_absent_suspension_record_is_tradable(self) -> None:
        fixture = load_fixture("suspension_xshg_600519_20260911.json")
        provider = provider_with(
            RawVendorResponse(
                capability="tradability",
                payload={
                    **fixture.payload,
                    "suspended": False,
                    "suspend_start_date": None,
                    "suspend_reason": None,
                },
                upstream_source=fixture.upstream_source,
            ),
            capability="tradability",
        )

        result = provider.fetch_tradability(TRADABILITY_REQUEST)

        assert isinstance(result, ProviderSuccess)
        record = result.records[0]
        assert record.status is TradabilityStatusKind.TRADABLE
        assert record.reason is None
        assert record.permits(TradeSide.BUY)
        assert record.permits(TradeSide.SELL)

    def test_snapshot_for_a_different_session_fails_closed(self) -> None:
        fixture = load_fixture("suspension_xshg_600519_20260911.json")
        provider = provider_with(
            RawVendorResponse(
                capability="tradability",
                payload={**fixture.payload, "snapshot_date": "2026-09-10"},
                upstream_source=fixture.upstream_source,
            ),
            capability="tradability",
        )

        result = provider.fetch_tradability(TRADABILITY_REQUEST)

        assert isinstance(result, ProviderFailure)
        assert result.error_code is ProviderErrorCode.MALFORMED_DATA

    def test_non_boolean_suspension_flag_is_malformed(self) -> None:
        fixture = load_fixture("suspension_xshg_600519_20260911.json")
        provider = provider_with(
            RawVendorResponse(
                capability="tradability",
                payload={**fixture.payload, "suspended": "yes"},
                upstream_source=fixture.upstream_source,
            ),
            capability="tradability",
        )

        result = provider.fetch_tradability(TRADABILITY_REQUEST)

        assert isinstance(result, ProviderFailure)
        assert result.error_code is ProviderErrorCode.MALFORMED_DATA


class TestCorporateActionMapping:
    def test_cash_dividend_maps_per_share_amount_and_dates(self) -> None:
        provider = provider_with(
            load_fixture("corporate_actions_xshg_600519_2026.json"),
            capability="corporate_actions",
        )

        result = provider.fetch_corporate_actions(CORPORATE_ACTION_REQUEST)

        assert isinstance(result, ProviderSuccess)
        action = next(
            record
            for record in result.records
            if record.action_kind is CorporateActionKind.CASH_DIVIDEND
        )
        assert action.action_id == "eastmoney:cash-2026-600519"
        assert action.instrument_id == XSHG_600519
        assert action.ex_date == date(2026, 6, 26)
        assert action.record_date == date(2026, 6, 25)
        assert action.pay_date == date(2026, 6, 27)
        assert action.cash_amount == Money(Decimal("2.5"))
        assert action.share_ratio is None
        assert action.revision == 1
        assert action.availability.availability_basis is AvailabilityBasis.INFERRED
        assert action.availability.information_available_at == datetime(
            2026, 6, 12, 23, 59, 59, tzinfo=MARKET_TZ
        )
        assert "RPT_SHAREBONUS_DET" in action.provenance

    def test_stock_dividend_maps_to_a_split_share_ratio(self) -> None:
        provider = provider_with(
            load_fixture("corporate_actions_xshg_600519_2026.json"),
            capability="corporate_actions",
        )

        result = provider.fetch_corporate_actions(CORPORATE_ACTION_REQUEST)

        assert isinstance(result, ProviderSuccess)
        action = next(
            record for record in result.records if record.action_kind is CorporateActionKind.SPLIT
        )
        assert action.action_id == "eastmoney:split-2026-600519"
        assert action.ex_date == date(2026, 4, 3)
        assert action.cash_amount is None
        assert action.share_ratio == Decimal("2.0")

    def test_items_are_ordered_canonically_regardless_of_input_order(self) -> None:
        provider = provider_with(
            load_fixture("corporate_actions_xshg_600519_2026.json"),
            capability="corporate_actions",
        )

        result = provider.fetch_corporate_actions(CORPORATE_ACTION_REQUEST)

        assert isinstance(result, ProviderSuccess)
        assert [record.ex_date for record in result.records] == [
            date(2026, 4, 3),
            date(2026, 6, 26),
        ]

    def test_partial_coverage_fails_closed(self) -> None:
        fixture = load_fixture("corporate_actions_xshg_600519_2026.json")
        provider = provider_with(
            RawVendorResponse(
                capability="corporate_actions",
                payload={**fixture.payload, "coverage": "partial"},
                upstream_source=fixture.upstream_source,
            ),
            capability="corporate_actions",
        )

        result = provider.fetch_corporate_actions(CORPORATE_ACTION_REQUEST)

        assert isinstance(result, ProviderFailure)
        assert result.error_code is ProviderErrorCode.PARTIAL_RESULT

    def test_item_without_an_ex_date_fails_closed(self) -> None:
        fixture = load_fixture("corporate_actions_xshg_600519_2026.json")
        broken = [dict(item) for item in fixture.payload["items"]]
        broken[0]["ex_dividend_date"] = None
        provider = provider_with(
            RawVendorResponse(
                capability="corporate_actions",
                payload={**fixture.payload, "items": broken},
                upstream_source=fixture.upstream_source,
            ),
            capability="corporate_actions",
        )

        result = provider.fetch_corporate_actions(CORPORATE_ACTION_REQUEST)

        assert isinstance(result, ProviderFailure)
        assert result.error_code is ProviderErrorCode.MALFORMED_DATA

    def test_rights_issues_are_unsupported_in_m0(self) -> None:
        fixture = load_fixture("corporate_actions_xshg_600519_2026.json")
        broken = [dict(item) for item in fixture.payload["items"]]
        broken[1]["rights_issue"] = {
            "value": 3.0,
            "unit": "per_10_shares",
            "source_field": "ALLOTMENT_RATIO",
            "tax_basis": "unknown",
        }
        provider = provider_with(
            RawVendorResponse(
                capability="corporate_actions",
                payload={**fixture.payload, "items": broken},
                upstream_source=fixture.upstream_source,
            ),
            capability="corporate_actions",
        )

        result = provider.fetch_corporate_actions(CORPORATE_ACTION_REQUEST)

        assert isinstance(result, ProviderFailure)
        assert result.error_code is ProviderErrorCode.UNSUPPORTED_CAPABILITY

    def test_empty_items_is_an_empty_success(self) -> None:
        fixture = load_fixture("corporate_actions_xshg_600519_2026.json")
        provider = provider_with(
            RawVendorResponse(
                capability="corporate_actions",
                payload={**fixture.payload, "items": [], "status": "normal_empty"},
                upstream_source=fixture.upstream_source,
            ),
            capability="corporate_actions",
        )

        result = provider.fetch_corporate_actions(CORPORATE_ACTION_REQUEST)

        assert isinstance(result, ProviderSuccess)
        assert result.records == ()
        assert result.evidence.record_count == 0


RULE_CANDIDATE_REQUEST = RuleCandidateRequest(
    instrument_id=XSHG_600519, session_date=date(2026, 9, 11)
)


class TestRuleCandidateAdjudication:
    def test_vendor_rule_profiles_map_to_canonical_candidates(self) -> None:
        provider = provider_with(
            load_fixture("rule_candidates_xshg_600519_20260911.json"),
            capability="rule_candidates",
        )

        result = provider.fetch_rule_candidates(RULE_CANDIDATE_REQUEST)

        assert isinstance(result, ProviderSuccess)
        lot_candidate, settlement_candidate = result.records
        assert isinstance(lot_candidate, RuleCandidate)
        assert lot_candidate.instrument_id == XSHG_600519
        assert lot_candidate.session_date == date(2026, 9, 11)
        assert lot_candidate.rule_kind is RuleKind.LOT
        assert isinstance(lot_candidate.proposed_value, LotRule)
        assert lot_candidate.proposed_value.board_lot == 200
        assert lot_candidate.proposed_by.startswith("chstockdata")
        assert settlement_candidate.rule_kind is RuleKind.SETTLEMENT
        assert settlement_candidate.proposed_value.sessions_until_sellable == 0

    def test_conflicting_candidate_never_overrides_the_approved_master(self) -> None:
        master = default_m0_master()
        provider = provider_with(
            load_fixture("rule_candidates_xshg_600519_20260911.json"),
            capability="rule_candidates",
        )
        result = provider.fetch_rule_candidates(RULE_CANDIDATE_REQUEST)
        assert isinstance(result, ProviderSuccess)
        lot_candidate = result.records[0]
        assert isinstance(lot_candidate.proposed_value, LotRule)
        assert lot_candidate.proposed_value.board_lot == 200

        adjudication = master.adjudicate_rule_candidate(lot_candidate)
        approved = master.resolve_rules(XSHG_600519, date(2026, 9, 11))

        assert adjudication.status is AdjudicationStatus.APPROVED_PROFILE_GOVERNS
        assert adjudication.approved_rules is not None
        assert adjudication.approved_rules.lot.board_lot == 100
        assert approved.lot.board_lot == 100
        assert approved.settlement.sessions_until_sellable == 1

    def test_candidate_for_an_unapproved_instrument_fails_closed(self) -> None:
        master = default_m0_master()
        provider = provider_with(
            load_fixture("rule_candidates_xshg_600519_20260911.json"),
            capability="rule_candidates",
        )
        result = provider.fetch_rule_candidates(
            RuleCandidateRequest(
                instrument_id=InstrumentId(exchange=Exchange.XSHG, symbol="999999"),
                session_date=date(2026, 9, 11),
            )
        )
        assert isinstance(result, ProviderSuccess)

        adjudication = master.adjudicate_rule_candidate(result.records[1])

        assert adjudication.status is AdjudicationStatus.FAIL_CLOSED_NO_APPROVED_PROFILE
        assert adjudication.approved_rules is None

    def test_unknown_rule_kind_fails_closed(self) -> None:
        fixture = load_fixture("rule_candidates_xshg_600519_20260911.json")
        broken = [dict(profile) for profile in fixture.payload["profiles"]]
        broken[0]["rule_kind"] = "MARGIN"
        provider = provider_with(
            RawVendorResponse(
                capability="rule_candidates",
                payload={**fixture.payload, "profiles": broken},
                upstream_source=fixture.upstream_source,
            ),
            capability="rule_candidates",
        )

        result = provider.fetch_rule_candidates(RULE_CANDIDATE_REQUEST)

        assert isinstance(result, ProviderFailure)
        assert result.error_code is ProviderErrorCode.SCHEMA_DRIFT

    def test_unknown_rule_value_key_fails_closed(self) -> None:
        fixture = load_fixture("rule_candidates_xshg_600519_20260911.json")
        broken = [dict(profile) for profile in fixture.payload["profiles"]]
        broken[0] = {**broken[0], "values": {"board_lot": 200, "surprise": 1}}
        provider = provider_with(
            RawVendorResponse(
                capability="rule_candidates",
                payload={**fixture.payload, "profiles": broken},
                upstream_source=fixture.upstream_source,
            ),
            capability="rule_candidates",
        )

        result = provider.fetch_rule_candidates(RULE_CANDIDATE_REQUEST)

        assert isinstance(result, ProviderFailure)
        assert result.error_code is ProviderErrorCode.SCHEMA_DRIFT


class TestProviderPortConformance:
    def test_adapter_satisfies_the_provider_port(self) -> None:
        provider = provider_with(load_fixture("daily_bars_vipdoc_xshg_510300.json"))

        assert isinstance(provider, DataProviderPort)

    def test_capability_evidence_reports_version_and_capabilities(self) -> None:
        provider = provider_with(load_fixture("daily_bars_vipdoc_xshg_510300.json"))

        evidence = provider.capability_evidence()
        repeat = provider.capability_evidence()

        assert isinstance(evidence, ProviderEvidence)
        assert evidence.capability == "provider_capability"
        assert evidence.provider_version == "0.3.0"
        assert evidence.retrieved_at == RETRIEVED_AT
        assert evidence.record_count == len(ChStockDataProvider.CAPABILITIES)
        assert evidence.payload_checksum
        assert isinstance(repeat, ProviderEvidence)
        assert repeat.evidence_id == evidence.evidence_id

    def test_library_rule_candidates_are_an_empty_advisory_result(self) -> None:
        client = LibraryChStockDataClient(library=StubLibrary())

        response = client.rule_candidates(
            instrument_id=XSHG_600519, session_date=date(2026, 9, 11)
        )

        assert response.capability == "rule_candidates"
        assert tuple(response.payload["profiles"]) == ()
        assert any("never become" in warning for warning in response.warnings)
