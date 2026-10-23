"""Contract tests: canonical daily-bar construction invariants.

Covers: OHLC/pre-close invariants, null-versus-zero, explicit units, RAW
execution basis, distinct information-available/retrieved times, availability
basis including UNKNOWN, and PIT access through information availability only.
"""

import json
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from systematic_investing.data.contracts import (
    InvalidProviderEvidenceError,
    MalformedRecordError,
    ProviderErrorCode,
    ProviderEvidence,
    ProviderFailure,
    ProviderSuccess,
    UnknownSchemaVersionError,
    corporate_action_from_dict,
    corporate_action_to_dict,
    daily_bar_from_dict,
    daily_bar_to_dict,
    tradability_status_from_dict,
    tradability_status_to_dict,
    trading_session_from_dict,
    trading_session_to_dict,
)
from systematic_investing.domain.identifiers import (
    Exchange,
    InstrumentId,
    InvalidSessionDateError,
)
from systematic_investing.domain.market import (
    DAILY_BAR_SCHEMA_VERSION,
    AdjustmentFactor,
    AdjustmentMode,
    Availability,
    AvailabilityBasis,
    CorporateAction,
    CorporateActionKind,
    DailyBar,
    InvalidAvailabilityError,
    InvalidCorporateActionError,
    InvalidDailyBarError,
    InvalidTradabilityError,
    InvalidTradingSessionError,
    MarketCalendar,
    TradabilityStatus,
    TradabilityStatusKind,
    TradeSide,
    TradingSession,
    UnknownSessionError,
)
from systematic_investing.domain.money import Money

XSHG_510300 = InstrumentId(exchange=Exchange.XSHG, symbol="510300")

RETRIEVED_AT = datetime(2026, 9, 11, 18, 5, tzinfo=UTC)
INFORMATION_AT = datetime(2026, 9, 11, 15, 0, tzinfo=UTC)

OBSERVED = Availability(
    information_available_at=INFORMATION_AT,
    retrieved_at=RETRIEVED_AT,
    availability_basis=AvailabilityBasis.OBSERVED,
)


def make_bar(**overrides: object) -> DailyBar:
    values: dict[str, object] = {
        "schema_version": DAILY_BAR_SCHEMA_VERSION,
        "instrument_id": XSHG_510300,
        "session_date": date(2026, 9, 11),
        "open": Decimal("4.00"),
        "high": Decimal("4.10"),
        "low": Decimal("3.95"),
        "close": Decimal("4.05"),
        "pre_close": Decimal("4.02"),
        "volume": Decimal("1000000"),
        "amount": Decimal("4050000"),
        "currency": "CNY",
        "volume_unit": "SHARE",
        "amount_unit": "CNY",
        "adjustment_mode": AdjustmentMode.RAW,
        "adjustment_factor": None,
        "availability": OBSERVED,
        "provider_evidence_id": "evidence-0001",
    }
    values.update(overrides)
    return DailyBar(**values)  # type: ignore[arg-type]


class TestDailyBarConstruction:
    def test_canonical_bar_retains_all_declared_fields(self) -> None:
        bar = make_bar()

        assert bar.schema_version == "v1"
        assert bar.instrument_id == XSHG_510300
        assert bar.close == Decimal("4.05")
        assert bar.volume_unit == "SHARE"
        assert bar.amount_unit == "CNY"
        assert bar.provider_evidence_id == "evidence-0001"

    def test_canonical_execution_bar_is_raw(self) -> None:
        bar = make_bar()

        assert bar.adjustment_mode is AdjustmentMode.RAW

    def test_datetimes_are_rejected_as_session_dates(self) -> None:
        with pytest.raises(InvalidSessionDateError):
            make_bar(session_date=datetime(2026, 9, 11, tzinfo=UTC))

    def test_bar_is_immutable(self) -> None:
        bar = make_bar()

        with pytest.raises(Exception, match="cannot assign"):
            bar.close = Decimal("9.99")  # type: ignore[misc]


class TestDailyBarPriceInvariants:
    @pytest.mark.parametrize("field", ["open", "high", "low", "close"])
    def test_non_positive_ohlc_price_is_rejected(self, field: str) -> None:
        with pytest.raises(InvalidDailyBarError):
            make_bar(**{field: Decimal("0")})

    def test_low_above_open_is_rejected(self) -> None:
        with pytest.raises(InvalidDailyBarError):
            make_bar(low=Decimal("4.01"), open=Decimal("4.00"))

    def test_close_above_high_is_rejected(self) -> None:
        with pytest.raises(InvalidDailyBarError):
            make_bar(high=Decimal("4.04"), close=Decimal("4.05"))

    def test_open_above_high_is_rejected(self) -> None:
        with pytest.raises(InvalidDailyBarError):
            make_bar(high=Decimal("4.09"), open=Decimal("4.10"))

    def test_low_above_close_is_rejected(self) -> None:
        with pytest.raises(InvalidDailyBarError):
            make_bar(low=Decimal("4.06"), close=Decimal("4.05"))

    def test_touching_extremes_are_valid(self) -> None:
        bar = make_bar(
            open=Decimal("3.95"),
            high=Decimal("4.10"),
            low=Decimal("3.95"),
            close=Decimal("4.10"),
        )

        assert bar.close == Decimal("4.10")


class TestDailyBarPreCloseNullVersusZero:
    def test_pre_close_is_optional_without_defaulting_to_zero(self) -> None:
        bar = make_bar(pre_close=None)

        assert bar.pre_close is None

    def test_zero_pre_close_is_rejected_because_zero_is_not_a_close(self) -> None:
        with pytest.raises(InvalidDailyBarError):
            make_bar(pre_close=Decimal("0"))

    def test_negative_pre_close_is_rejected(self) -> None:
        with pytest.raises(InvalidDailyBarError):
            make_bar(pre_close=Decimal("-4.02"))


class TestDailyBarVolumeAmountUnits:
    def test_genuine_zero_volume_is_preserved_not_nulled(self) -> None:
        bar = make_bar(volume=Decimal("0"), amount=Decimal("0"))

        assert bar.volume == Decimal("0")
        assert bar.amount == Decimal("0")

    def test_negative_volume_is_rejected(self) -> None:
        with pytest.raises(InvalidDailyBarError):
            make_bar(volume=Decimal("-1"))

    def test_negative_amount_is_rejected(self) -> None:
        with pytest.raises(InvalidDailyBarError):
            make_bar(amount=Decimal("-1"))

    def test_float_volume_is_rejected(self) -> None:
        with pytest.raises(InvalidDailyBarError):
            make_bar(volume=1000000.0)  # type: ignore[arg-type]

    def test_missing_unit_names_are_rejected(self) -> None:
        with pytest.raises(InvalidDailyBarError):
            make_bar(volume_unit="")

        with pytest.raises(InvalidDailyBarError):
            make_bar(amount_unit="")

    def test_non_cny_currency_is_rejected_in_m0(self) -> None:
        with pytest.raises(InvalidDailyBarError):
            make_bar(currency="HKD")


class TestDailyBarAvailability:
    def test_information_time_and_retrieval_time_stay_distinct(self) -> None:
        bar = make_bar()

        assert bar.availability.information_available_at == INFORMATION_AT
        assert bar.availability.retrieved_at == RETRIEVED_AT
        assert bar.availability.information_available_at != bar.availability.retrieved_at

    def test_naive_retrieval_time_is_rejected(self) -> None:
        with pytest.raises(InvalidAvailabilityError):
            Availability(
                information_available_at=INFORMATION_AT,
                retrieved_at=datetime(2026, 9, 11, 18, 5),
                availability_basis=AvailabilityBasis.OBSERVED,
            )

    def test_unknown_basis_requires_no_information_time(self) -> None:
        availability = Availability(
            information_available_at=None,
            retrieved_at=RETRIEVED_AT,
            availability_basis=AvailabilityBasis.UNKNOWN,
        )

        assert availability.availability_basis is AvailabilityBasis.UNKNOWN
        assert availability.information_available_at is None

    def test_unknown_basis_never_acquires_a_fabricated_time(self) -> None:
        with pytest.raises(InvalidAvailabilityError):
            Availability(
                information_available_at=INFORMATION_AT,
                retrieved_at=RETRIEVED_AT,
                availability_basis=AvailabilityBasis.UNKNOWN,
            )

    @pytest.mark.parametrize(
        "basis",
        [
            AvailabilityBasis.OBSERVED,
            AvailabilityBasis.EXCHANGE_RULE,
            AvailabilityBasis.INFERRED,
        ],
    )
    def test_known_bases_require_the_information_time(self, basis: AvailabilityBasis) -> None:
        with pytest.raises(InvalidAvailabilityError):
            Availability(
                information_available_at=None,
                retrieved_at=RETRIEVED_AT,
                availability_basis=basis,
            )

    def test_information_time_after_retrieval_time_is_rejected(self) -> None:
        with pytest.raises(InvalidAvailabilityError):
            Availability(
                information_available_at=datetime(2026, 9, 12, tzinfo=UTC),
                retrieved_at=RETRIEVED_AT,
                availability_basis=AvailabilityBasis.OBSERVED,
            )

    def test_pit_access_uses_information_availability_only(self) -> None:
        availability = OBSERVED

        assert availability.information_known_at(datetime(2026, 9, 11, 16, tzinfo=UTC)) is True
        assert availability.information_known_at(datetime(2026, 9, 11, 14, tzinfo=UTC)) is False

    def test_pit_access_of_unknown_basis_stays_unknown(self) -> None:
        availability = Availability(
            information_available_at=None,
            retrieved_at=RETRIEVED_AT,
            availability_basis=AvailabilityBasis.UNKNOWN,
        )

        assert availability.information_known_at(datetime(2027, 1, 1, tzinfo=UTC)) is None

    def test_naive_cutoff_is_rejected_for_pit_access(self) -> None:
        with pytest.raises(InvalidAvailabilityError):
            OBSERVED.information_known_at(datetime(2026, 9, 11, 16))


class TestDailyBarAdjustmentFactor:
    def test_optional_point_in_time_factor_is_retained(self) -> None:
        factor = AdjustmentFactor(
            factor=Decimal("1.05"),
            convention="BACKWARD",
            version="v1",
            as_of=date(2026, 9, 11),
        )
        bar = make_bar(adjustment_factor=factor)

        assert bar.adjustment_factor == factor

    def test_non_positive_factor_is_rejected(self) -> None:
        with pytest.raises(InvalidDailyBarError):
            make_bar(
                adjustment_factor=AdjustmentFactor(
                    factor=Decimal("0"),
                    convention="BACKWARD",
                    version="v1",
                    as_of=date(2026, 9, 11),
                )
            )


def trading_session(day: str, is_open: bool, *, calendar_id: str = "XSHG", note: str | None = None):
    return TradingSession(
        calendar_id=calendar_id,
        session_date=date.fromisoformat(day),
        is_open=is_open,
        note=note,
        snapshot_version="cal-v1",
    )


def xshg_calendar() -> MarketCalendar:
    """One snapshot week: closed weekend plus a closed Monday holiday."""
    return MarketCalendar(
        calendar_id="XSHG",
        snapshot_version="cal-v1",
        sessions=(
            trading_session("2026-09-04", True),
            trading_session("2026-09-05", False, note="WEEKEND"),
            trading_session("2026-09-06", False, note="WEEKEND"),
            trading_session("2026-09-07", False, note="HOLIDAY"),
            trading_session("2026-09-08", True),
            trading_session("2026-09-09", True),
        ),
    )


class TestTradingSession:
    def test_session_retains_identity_and_status(self) -> None:
        closed = trading_session("2026-09-05", False, note="WEEKEND")

        assert closed.calendar_id == "XSHG"
        assert closed.session_date == date(2026, 9, 5)
        assert closed.is_open is False
        assert closed.note == "WEEKEND"
        assert closed.snapshot_version == "cal-v1"

    def test_session_date_rejects_datetimes(self) -> None:
        with pytest.raises(InvalidSessionDateError):
            TradingSession(
                calendar_id="XSHG",
                session_date=datetime(2026, 9, 5),
                is_open=True,
                note=None,
                snapshot_version="cal-v1",
            )

    def test_calendar_identity_is_required(self) -> None:
        with pytest.raises(InvalidTradingSessionError):
            TradingSession(
                calendar_id="",
                session_date=date(2026, 9, 5),
                is_open=True,
                note=None,
                snapshot_version="cal-v1",
            )

    def test_snapshot_version_is_required(self) -> None:
        with pytest.raises(InvalidTradingSessionError):
            TradingSession(
                calendar_id="XSHG",
                session_date=date(2026, 9, 5),
                is_open=True,
                note=None,
                snapshot_version="",
            )


class TestMarketCalendar:
    def test_calendar_rejects_foreign_calendar_sessions(self) -> None:
        with pytest.raises(InvalidTradingSessionError):
            MarketCalendar(
                calendar_id="XSHG",
                snapshot_version="cal-v1",
                sessions=(trading_session("2026-09-04", True, calendar_id="XSHE"),),
            )

    def test_calendar_rejects_duplicate_session_dates(self) -> None:
        with pytest.raises(InvalidTradingSessionError):
            MarketCalendar(
                calendar_id="XSHG",
                snapshot_version="cal-v1",
                sessions=(
                    trading_session("2026-09-04", True),
                    trading_session("2026-09-04", True),
                ),
            )

    def test_calendar_rejects_unsorted_sessions(self) -> None:
        with pytest.raises(InvalidTradingSessionError):
            MarketCalendar(
                calendar_id="XSHG",
                snapshot_version="cal-v1",
                sessions=(trading_session("2026-09-08", True), trading_session("2026-09-04", True)),
            )

    def test_next_session_skips_closed_sessions_in_the_snapshot(self) -> None:
        calendar = xshg_calendar()

        next_session = calendar.next_session(date(2026, 9, 4))

        # Friday close -> next open session is Tuesday, not Saturday or Monday.
        assert next_session.session_date == date(2026, 9, 8)
        assert next_session.is_open is True

    def test_next_session_is_resolved_from_the_snapshot_not_weekday_math(self) -> None:
        calendar = xshg_calendar()

        next_session = calendar.next_session(date(2026, 9, 8))

        assert next_session.session_date == date(2026, 9, 9)

    def test_next_session_after_snapshot_end_fails_closed(self) -> None:
        calendar = xshg_calendar()

        with pytest.raises(UnknownSessionError):
            calendar.next_session(date(2026, 9, 9))

    def test_next_session_rejects_datetime_argument(self) -> None:
        calendar = xshg_calendar()

        with pytest.raises(InvalidSessionDateError):
            calendar.next_session(datetime(2026, 9, 4))

    def test_session_lookup_on_the_snapshot(self) -> None:
        calendar = xshg_calendar()

        assert calendar.session_on(date(2026, 9, 7)).is_open is False
        assert calendar.session_on(date(2026, 9, 10)) is None


XSHE_000001 = InstrumentId(exchange=Exchange.XSHE, symbol="000001")


def tradability(**overrides: object):
    values: dict[str, object] = {
        "instrument_id": XSHE_000001,
        "session_date": date(2026, 9, 11),
        "status": TradabilityStatusKind.TRADABLE,
        "reason": None,
        "availability": Availability(
            information_available_at=INFORMATION_AT,
            retrieved_at=RETRIEVED_AT,
            availability_basis=AvailabilityBasis.OBSERVED,
        ),
        "provenance": "exchange-notice-2026-09-10",
    }
    values.update(overrides)
    return TradabilityStatus(**values)  # type: ignore[arg-type]


class TestTradabilityStatus:
    def test_tradable_status_permits_both_sides(self) -> None:
        status = tradability()

        assert status.permits(TradeSide.BUY) is True
        assert status.permits(TradeSide.SELL) is True

    def test_suspension_blocks_both_sides_and_keeps_the_reason(self) -> None:
        status = tradability(
            status=TradabilityStatusKind.SUSPENDED,
            reason="MAJOR_EVENT_ANNOUNCEMENT",
        )

        assert status.permits(TradeSide.BUY) is False
        assert status.permits(TradeSide.SELL) is False
        assert status.reason == "MAJOR_EVENT_ANNOUNCEMENT"

    def test_unknown_status_is_a_real_value_and_permits_nothing(self) -> None:
        status = tradability(status=TradabilityStatusKind.UNKNOWN)

        assert status.status is TradabilityStatusKind.UNKNOWN
        assert status.permitted_sides is None
        assert status.permits(TradeSide.BUY) is False
        assert status.permits(TradeSide.SELL) is False

    def test_upper_limit_blocks_buys_but_allows_sells(self) -> None:
        status = tradability(
            status=TradabilityStatusKind.BUY_BLOCKED_UPPER_LIMIT,
            reason="AT_UPPER_LIMIT",
        )

        assert status.permits(TradeSide.BUY) is False
        assert status.permits(TradeSide.SELL) is True

    def test_lower_limit_blocks_sells_but_allows_buys(self) -> None:
        status = tradability(
            status=TradabilityStatusKind.SELL_BLOCKED_LOWER_LIMIT,
            reason="AT_LOWER_LIMIT",
        )

        assert status.permits(TradeSide.BUY) is True
        assert status.permits(TradeSide.SELL) is False

    def test_not_listed_and_delisted_block_both_sides(self) -> None:
        not_listed = tradability(status=TradabilityStatusKind.NOT_LISTED)
        delisted = tradability(status=TradabilityStatusKind.DELISTED)

        for status in (not_listed, delisted):
            assert status.permits(TradeSide.BUY) is False
            assert status.permits(TradeSide.SELL) is False

    def test_provenance_is_required(self) -> None:
        with pytest.raises(InvalidTradabilityError):
            tradability(provenance="")

    def test_availability_is_required(self) -> None:
        with pytest.raises(InvalidTradabilityError):
            tradability(availability=None)


def corporate_action(**overrides: object):
    values: dict[str, object] = {
        "action_id": "CA-510300-2026-D1",
        "instrument_id": XSHG_510300,
        "action_kind": CorporateActionKind.CASH_DIVIDEND,
        "ex_date": date(2026, 7, 15),
        "record_date": date(2026, 7, 14),
        "pay_date": date(2026, 7, 16),
        "cash_amount": Money(Decimal("0.12")),
        "share_ratio": None,
        "revision": 1,
        "availability": Availability(
            information_available_at=datetime(2026, 7, 10, tzinfo=UTC),
            retrieved_at=RETRIEVED_AT,
            availability_basis=AvailabilityBasis.OBSERVED,
        ),
        "provenance": "fund-announcement-2026-07-09",
    }
    values.update(overrides)
    return CorporateAction(**values)  # type: ignore[arg-type]


class TestCorporateAction:
    def test_action_retains_declared_fields(self) -> None:
        action = corporate_action()

        assert action.action_id == "CA-510300-2026-D1"
        assert action.action_kind is CorporateActionKind.CASH_DIVIDEND
        assert action.ex_date == date(2026, 7, 15)
        assert action.record_date == date(2026, 7, 14)
        assert action.pay_date == date(2026, 7, 16)
        assert action.cash_amount == Money(Decimal("0.12"))

    def test_split_carries_share_ratio_without_cash(self) -> None:
        action = corporate_action(
            action_kind=CorporateActionKind.SPLIT,
            cash_amount=None,
            share_ratio=Decimal("1.5"),
        )

        assert action.share_ratio == Decimal("1.5")
        assert action.cash_amount is None

    def test_action_without_economic_terms_is_rejected(self) -> None:
        with pytest.raises(InvalidCorporateActionError):
            corporate_action(cash_amount=None, share_ratio=None)

    def test_non_positive_ratio_is_rejected(self) -> None:
        with pytest.raises(InvalidCorporateActionError):
            corporate_action(cash_amount=None, share_ratio=Decimal("0"))

    def test_revision_must_be_positive(self) -> None:
        with pytest.raises(InvalidCorporateActionError):
            corporate_action(revision=0)

    def test_correction_creates_a_new_record_instead_of_mutating(self) -> None:
        original = corporate_action()
        correction = corporate_action(revision=2, cash_amount=Money(Decimal("0.15")))

        # Both immutable facts coexist; the original record is unchanged.
        assert original.revision == 1
        assert original.cash_amount == Money(Decimal("0.12"))
        assert correction.revision == 2
        assert correction.cash_amount == Money(Decimal("0.15"))
        assert correction.action_id == original.action_id

    def test_record_is_immutable(self) -> None:
        action = corporate_action()

        with pytest.raises(Exception, match="cannot assign"):
            action.revision = 2  # type: ignore[misc]

    def test_provenance_is_required(self) -> None:
        with pytest.raises(InvalidCorporateActionError):
            corporate_action(provenance="")

    def test_unknown_availability_is_expressible(self) -> None:
        action = corporate_action(
            availability=Availability(
                information_available_at=None,
                retrieved_at=RETRIEVED_AT,
                availability_basis=AvailabilityBasis.UNKNOWN,
            ),
        )

        assert action.availability.availability_basis is AvailabilityBasis.UNKNOWN


def make_evidence(**overrides: object):
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


class TestProviderEvidence:
    def test_evidence_retains_provider_and_request_identity(self) -> None:
        evidence = make_evidence()

        assert evidence.provider_name == "chstockdata"
        assert evidence.capability == "daily_bars"
        assert evidence.request_digest == "req-digest-001"
        assert evidence.record_count == 1
        assert evidence.payload_checksum == "sha256:abc123"

    def test_naive_retrieval_time_is_rejected(self) -> None:
        with pytest.raises(InvalidProviderEvidenceError):
            make_evidence(retrieved_at=datetime(2026, 9, 11, 18, 5))

    def test_negative_record_count_is_rejected(self) -> None:
        with pytest.raises(InvalidProviderEvidenceError):
            make_evidence(record_count=-1)

    def test_missing_checksum_is_rejected(self) -> None:
        with pytest.raises(InvalidProviderEvidenceError):
            make_evidence(payload_checksum="")

    def test_warnings_are_immutable(self) -> None:
        evidence = make_evidence(warnings=("unit-heuristic",))

        assert evidence.warnings == ("unit-heuristic",)
        with pytest.raises(AttributeError):
            evidence.warnings = ()  # type: ignore[misc]


class TestProviderResults:
    def test_empty_success_is_a_success_not_a_failure(self) -> None:
        success = ProviderSuccess(records=(), evidence=make_evidence(record_count=0))

        assert success.records == ()
        assert success.is_success is True

    def test_success_carries_canonical_records_and_evidence(self) -> None:
        bar = make_bar()
        success = ProviderSuccess(records=(bar,), evidence=make_evidence())

        assert success.records == (bar,)

    def test_failure_carries_typed_error_code_and_cause(self) -> None:
        failure = ProviderFailure(
            error_code=ProviderErrorCode.SCHEMA_DRIFT,
            message="unexpected column 'zsz'",
            evidence=make_evidence(record_count=0),
            cause=None,
        )

        assert failure.is_success is False
        assert failure.error_code is ProviderErrorCode.SCHEMA_DRIFT

    def test_every_documented_error_category_exists(self) -> None:
        assert {member.value for member in ProviderErrorCode} == {
            "AUTHENTICATION_OR_CONFIGURATION",
            "UNAVAILABLE_OR_RATE_LIMITED",
            "SCHEMA_DRIFT",
            "MALFORMED_DATA",
            "PARTIAL_RESULT",
            "UNSUPPORTED_CAPABILITY",
            "INTERNAL_ADAPTER_ERROR",
        }


class TestCanonicalSerialization:
    def test_daily_bar_round_trip_preserves_decimal_date_time_enum_schema(self) -> None:
        bar = make_bar(
            adjustment_factor=AdjustmentFactor(
                factor=Decimal("1.05"),
                convention="BACKWARD",
                version="v1",
                as_of=date(2026, 9, 11),
            ),
        )

        data = json.loads(json.dumps(daily_bar_to_dict(bar)))
        restored = daily_bar_from_dict(data)

        assert restored == bar
        assert str(restored.close) == str(bar.close)
        assert restored.availability.information_available_at.tzinfo == UTC
        assert restored.availability.availability_basis is AvailabilityBasis.OBSERVED
        assert restored.adjustment_mode is AdjustmentMode.RAW
        assert restored.schema_version == DAILY_BAR_SCHEMA_VERSION

    def test_daily_bar_rejects_unknown_schema_version(self) -> None:
        data = daily_bar_to_dict(make_bar())
        data["schema_version"] = "v999"

        with pytest.raises(UnknownSchemaVersionError):
            daily_bar_from_dict(data)

    def test_daily_bar_rejects_missing_required_keys(self) -> None:
        data = daily_bar_to_dict(make_bar())
        del data["close"]

        with pytest.raises(MalformedRecordError):
            daily_bar_from_dict(data)

    def test_trading_session_round_trip(self) -> None:
        record = trading_session("2026-09-04", True)

        restored = trading_session_from_dict(
            json.loads(json.dumps(trading_session_to_dict(record)))
        )

        assert restored == record
        assert restored.session_date == record.session_date

    def test_tradability_round_trip(self) -> None:
        record = tradability(
            status=TradabilityStatusKind.SUSPENDED, reason="MAJOR_EVENT_ANNOUNCEMENT"
        )

        restored = tradability_status_from_dict(
            json.loads(json.dumps(tradability_status_to_dict(record)))
        )

        assert restored == record
        assert restored.status is TradabilityStatusKind.SUSPENDED
        assert str(restored.instrument_id) == "XSHE:000001"

    def test_corporate_action_round_trip(self) -> None:
        record = corporate_action(share_ratio=Decimal("1.5"), cash_amount=None)

        restored = corporate_action_from_dict(
            json.loads(json.dumps(corporate_action_to_dict(record)))
        )

        assert restored == record
        assert restored.share_ratio == Decimal("1.5")
        assert restored.ex_date == record.ex_date
