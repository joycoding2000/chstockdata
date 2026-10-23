"""Contract tests: the narrow provider port.

The port returns canonical records plus evidence or a typed failure — never
vendor frames. Requests declare universe, date range, and adjustment intent;
responses keep empty success and typed failure distinct.
"""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

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
from systematic_investing.domain.identifiers import Exchange, InstrumentId, InvalidSessionDateError
from systematic_investing.domain.market import (
    DAILY_BAR_SCHEMA_VERSION,
    AdjustmentMode,
    Availability,
    AvailabilityBasis,
    CorporateAction,
    CorporateActionKind,
    DailyBar,
    TradabilityStatus,
    TradabilityStatusKind,
    TradingSession,
)

XSHG_510300 = InstrumentId(exchange=Exchange.XSHG, symbol="510300")

INFORMATION_AT = datetime(2026, 9, 11, 15, 0, tzinfo=UTC)
RETRIEVED_AT = datetime(2026, 9, 11, 18, 5, tzinfo=UTC)


def make_bar() -> DailyBar:
    return DailyBar(
        schema_version=DAILY_BAR_SCHEMA_VERSION,
        instrument_id=XSHG_510300,
        session_date=date(2026, 9, 11),
        open=Decimal("4.00"),
        high=Decimal("4.10"),
        low=Decimal("3.95"),
        close=Decimal("4.05"),
        pre_close=Decimal("4.02"),
        volume=Decimal("1000000"),
        amount=Decimal("4050000"),
        currency="CNY",
        volume_unit="SHARE",
        amount_unit="CNY",
        adjustment_mode=AdjustmentMode.RAW,
        adjustment_factor=None,
        availability=availability(),
        provider_evidence_id="evidence-0001",
    )


def make_evidence(**overrides: object) -> ProviderEvidence:
    values: dict[str, object] = {
        "evidence_id": "ev-0001",
        "provider_name": "chstockdata",
        "provider_version": "1.2.3",
        "adapter_name": "chstockdata-adapter",
        "adapter_version": "0.1.0",
        "capability": "daily_bars",
        "request_digest": "req-digest-001",
        "retrieved_at": RETRIEVED_AT,
        "upstream_source": "eastmoney",
        "record_count": 1,
        "payload_checksum": "sha256:abc123",
        "warnings": (),
    }
    values.update(overrides)
    return ProviderEvidence(**values)  # type: ignore[arg-type]


def availability() -> Availability:
    return Availability(
        information_available_at=INFORMATION_AT,
        retrieved_at=RETRIEVED_AT,
        availability_basis=AvailabilityBasis.OBSERVED,
    )


def trading_session() -> TradingSession:
    return TradingSession(
        calendar_id="XSHG",
        session_date=date(2026, 9, 11),
        is_open=True,
        note=None,
        snapshot_version="cal-v1",
    )


def tradability() -> TradabilityStatus:
    return TradabilityStatus(
        instrument_id=XSHG_510300,
        session_date=date(2026, 9, 11),
        status=TradabilityStatusKind.TRADABLE,
        reason=None,
        availability=availability(),
        provenance="exchange-notice",
    )


def corporate_action() -> CorporateAction:
    return CorporateAction(
        action_id="CA-510300-2026-D1",
        instrument_id=XSHG_510300,
        action_kind=CorporateActionKind.CASH_DIVIDEND,
        ex_date=date(2026, 7, 15),
        record_date=None,
        pay_date=None,
        cash_amount=None,
        share_ratio=None,
        revision=1,
        availability=availability(),
        provenance="fund-announcement",
    )


class StubProvider:
    """Minimal port implementation over canonical records only."""

    def capability_evidence(self) -> ProviderEvidence | ProviderFailure:
        return make_evidence(capability="capability_evidence")

    def fetch_daily_bars(
        self, request: DailyBarRequest
    ) -> ProviderSuccess[DailyBar] | ProviderFailure:
        return ProviderSuccess(records=(make_bar(),), evidence=make_evidence(record_count=1))

    def fetch_calendar(
        self, request: CalendarRequest
    ) -> ProviderSuccess[TradingSession] | ProviderFailure:
        return ProviderSuccess(records=(trading_session(),), evidence=make_evidence(record_count=1))

    def fetch_tradability(
        self, request: TradabilityRequest
    ) -> ProviderSuccess[TradabilityStatus] | ProviderFailure:
        return ProviderSuccess(records=(tradability(),), evidence=make_evidence(record_count=1))

    def fetch_corporate_actions(
        self, request: CorporateActionRequest
    ) -> ProviderSuccess[CorporateAction] | ProviderFailure:
        record = corporate_action()
        return ProviderSuccess(records=(record,), evidence=make_evidence(record_count=1))


class TestDataProviderPort:
    def test_canonical_stub_satisfies_the_port_protocol(self) -> None:
        assert isinstance(StubProvider(), DataProviderPort)

    def test_capability_evidence_returns_provider_evidence(self) -> None:
        evidence = StubProvider().capability_evidence()

        assert isinstance(evidence, ProviderEvidence)

    def test_daily_bar_result_carries_canonical_bars(self) -> None:
        result = StubProvider().fetch_daily_bars(
            DailyBarRequest(
                instrument_ids=(XSHG_510300,),
                start_date=date(2026, 9, 11),
                end_date=date(2026, 9, 11),
            )
        )

        assert isinstance(result, ProviderSuccess)
        assert result.records[0].adjustment_mode is AdjustmentMode.RAW
        assert result.records[0].schema_version == DAILY_BAR_SCHEMA_VERSION

    def test_empty_success_stays_distinct_from_typed_failure(self) -> None:
        class EmptyProvider(StubProvider):
            def fetch_daily_bars(self, request):  # type: ignore[no-untyped-def]
                return ProviderSuccess(records=(), evidence=make_evidence(record_count=0))

        result = EmptyProvider().fetch_daily_bars(
            DailyBarRequest(
                instrument_ids=(XSHG_510300,),
                start_date=date(2026, 9, 11),
                end_date=date(2026, 9, 11),
            )
        )

        assert isinstance(result, ProviderSuccess)
        assert result.records == ()

    def test_typed_failure_is_a_value_not_an_exception(self) -> None:
        class FailingProvider(StubProvider):
            def fetch_daily_bars(self, request):  # type: ignore[no-untyped-def]
                return ProviderFailure(
                    error_code=ProviderErrorCode.SCHEMA_DRIFT,
                    message="unexpected column",
                    evidence=make_evidence(record_count=0),
                    cause=None,
                )

        result = FailingProvider().fetch_daily_bars(
            DailyBarRequest(
                instrument_ids=(XSHG_510300,),
                start_date=date(2026, 9, 11),
                end_date=date(2026, 9, 11),
            )
        )

        assert isinstance(result, ProviderFailure)
        assert result.error_code is ProviderErrorCode.SCHEMA_DRIFT


class TestPortRequestContracts:
    def test_request_requires_a_universe(self) -> None:
        with pytest.raises(ValueError, match="universe"):
            DailyBarRequest(
                instrument_ids=(),
                start_date=date(2026, 9, 11),
                end_date=date(2026, 9, 11),
            )

    def test_request_rejects_inverted_date_range(self) -> None:
        with pytest.raises(ValueError, match="range"):
            DailyBarRequest(
                instrument_ids=(XSHG_510300,),
                start_date=date(2026, 9, 12),
                end_date=date(2026, 9, 11),
            )

    def test_request_rejects_datetimes_as_session_dates(self) -> None:
        with pytest.raises(InvalidSessionDateError):
            DailyBarRequest(
                instrument_ids=(XSHG_510300,),
                start_date=datetime(2026, 9, 11, tzinfo=UTC),
                end_date=date(2026, 9, 11),
            )

    def test_request_declares_adjustment_intent(self) -> None:
        request = DailyBarRequest(
            instrument_ids=(XSHG_510300,),
            start_date=date(2026, 9, 11),
            end_date=date(2026, 9, 11),
        )

        assert request.adjustment_mode is AdjustmentMode.RAW
