"""Unit tests: exchange-qualified IDs, explicit sleeves, session-date discipline."""

from datetime import UTC, date, datetime

import pytest

from systematic_investing.domain.identifiers import (
    Exchange,
    InstrumentId,
    InvalidInstrumentIdError,
    InvalidSessionDateError,
    SleeveId,
    require_session_date,
)


class TestInstrumentId:
    def test_canonical_form_is_exchange_colon_symbol(self) -> None:
        instrument_id = InstrumentId(exchange=Exchange.XSHG, symbol="510300")

        assert str(instrument_id) == "XSHG:510300"

    def test_parse_accepts_canonical_form(self) -> None:
        instrument_id = InstrumentId.parse("XSHE:159915")

        assert instrument_id == InstrumentId(exchange=Exchange.XSHE, symbol="159915")

    def test_bare_six_digit_symbol_is_rejected(self) -> None:
        with pytest.raises(InvalidInstrumentIdError):
            InstrumentId.parse("510300")

    def test_unknown_exchange_code_is_rejected(self) -> None:
        with pytest.raises(InvalidInstrumentIdError):
            InstrumentId.parse("SSE:510300")

    def test_wrong_symbol_shape_is_rejected(self) -> None:
        with pytest.raises(InvalidInstrumentIdError):
            InstrumentId.parse("XSHG:5103")

    def test_lowercase_exchange_is_rejected(self) -> None:
        with pytest.raises(InvalidInstrumentIdError):
            InstrumentId.parse("xshg:510300")

    def test_non_exchange_enum_is_rejected_at_construction(self) -> None:
        with pytest.raises(InvalidInstrumentIdError):
            InstrumentId(exchange="XSHG", symbol="510300")  # type: ignore[arg-type]

    def test_ids_are_value_objects_and_immutble(self) -> None:
        instrument_id = InstrumentId.parse("XSHG:510300")

        assert instrument_id == InstrumentId.parse("XSHG:510300")
        assert hash(instrument_id) == hash(InstrumentId.parse("XSHG:510300"))
        with pytest.raises(Exception, match="cannot assign"):
            instrument_id.symbol = "600519"  # type: ignore[misc]

    def test_canonical_ordering_is_exchange_then_symbol(self) -> None:
        shanghai = InstrumentId.parse("XSHG:510300")
        shanghai_b = InstrumentId.parse("XSHG:510500")
        shenzhen = InstrumentId.parse("XSHE:159915")

        assert sorted([shanghai_b, shenzhen, shanghai]) == [shenzhen, shanghai, shanghai_b]


class TestSleeveId:
    def test_m0_values_are_exactly_core_and_satellite(self) -> None:
        assert {member.value for member in SleeveId} == {"CORE", "SATELLITE"}

    def test_sleeve_cannot_be_created_from_arbitrary_name(self) -> None:
        with pytest.raises(ValueError):
            SleeveId("core-etf")

    def test_sleeve_is_never_derived_from_a_strategy_name_prefix(self) -> None:
        # The contract is that SleeveId is passed explicitly; there is no
        # constructor/factory deriving it from a strategy name or instrument
        # type. Deriving would require a helper that does not exist.
        assert not any(
            name.startswith("from_") or "infer" in name.lower()
            for name in dir(SleeveId)
            if not name.startswith("__")
        )


class TestSessionDate:
    def test_calendar_date_is_accepted_and_returned(self) -> None:
        assert require_session_date(date(2023, 8, 28)) == date(2023, 8, 28)

    def test_datetime_is_rejected_even_when_timezone_aware(self) -> None:
        aware = datetime(2023, 8, 28, 15, 0, tzinfo=UTC)

        with pytest.raises(InvalidSessionDateError):
            require_session_date(aware)

    def test_plain_string_is_rejected(self) -> None:
        with pytest.raises(InvalidSessionDateError):
            require_session_date("2023-08-28")  # type: ignore[arg-type]
