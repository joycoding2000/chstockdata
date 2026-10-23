"""Unit tests: Instrument identity, classification consistency, profile references."""

from dataclasses import fields
from datetime import date, datetime
from decimal import Decimal

import pytest

from systematic_investing.domain.identifiers import Exchange, InstrumentId
from systematic_investing.domain.instruments import (
    FundSubtype,
    Instrument,
    InstrumentError,
    InstrumentType,
)
from systematic_investing.instrument_master.models import (
    InstrumentMasterError,
    LotRule,
    MarketFeeTaxRule,
    OddLotSellPolicy,
    PriceLimitBasis,
    PriceLimitRule,
    RuleSource,
    SettlementRule,
)


def make_market_fee_tax_rule(**overrides):
    values = {
        "profile_id": "FEE:TAX-A",
        "effective_from": date(2023, 8, 28),
        "effective_to": None,
        "source": RuleSource(
            authority="MOF/STA",
            reference="Announcement [2023] No.39",
            accessed_on=date(2026, 9, 1),
        ),
        "stamp_tax_sell_rate": Decimal("0.0005"),
        "transfer_fee_rate": Decimal("0.00001"),
    }
    values.update(overrides)
    return MarketFeeTaxRule(**values)


def make_lot_rule(**overrides):
    values = {
        "profile_id": "LOT:CN-STANDARD",
        "effective_from": date(2022, 1, 4),
        "effective_to": None,
        "source": RuleSource(
            authority="SSE/SZSE", reference="Trading rules", accessed_on=date(2026, 9, 1)
        ),
        "board_lot": 100,
        "buy_increment": 100,
        "odd_lot_sell_policy": OddLotSellPolicy.ALLOWED,
    }
    values.update(overrides)
    return LotRule(**values)


def make_settlement_rule(**overrides):
    values = {
        "profile_id": "SETTLE:T1",
        "effective_from": date(2022, 1, 4),
        "effective_to": None,
        "source": RuleSource(
            authority="SSE/SZSE", reference="Settlement rules", accessed_on=date(2026, 9, 1)
        ),
        "sessions_until_sellable": 1,
    }
    values.update(overrides)
    return SettlementRule(**values)


def make_price_limit_rule(**overrides):
    values = {
        "profile_id": "PLIMIT:ETF-10PCT",
        "effective_from": date(2022, 1, 4),
        "effective_to": None,
        "source": RuleSource(
            authority="SSE", reference="Trading rules", accessed_on=date(2026, 9, 1)
        ),
        "basis": PriceLimitBasis.PREVIOUS_CLOSE,
        "limit_percent": Decimal("0.10"),
        "tick_size": Decimal("0.001"),
    }
    values.update(overrides)
    return PriceLimitRule(**values)


def make_instrument(**overrides):
    values = {
        "instrument_id": InstrumentId(exchange=Exchange.XSHG, symbol="600519"),
        "display_name": "Kweichow Moutai A",
        "currency": "CNY",
        "instrument_type": InstrumentType.A_SHARE,
        "fund_subtype": None,
        "list_date": date(2001, 8, 27),
        "delist_date": None,
        "trading_calendar_id": "XSHG",
        "lot_rule_profile_id": "LOT:CN-STANDARD",
        "settlement_rule_profile_id": "SETTLE:T1",
        "price_limit_rule_profile_id": "PLIMIT:A-MAIN-10PCT",
        "market_fee_tax_profile_id": "FEE:TAX-A",
        "reference_data_version": "M0-SEED-1",
        "valid_from": date(2022, 1, 4),
        "valid_to": None,
    }
    values.update(overrides)
    return Instrument(**values)


class TestInstrumentConstruction:
    def test_identity_fields_are_retained(self) -> None:
        instrument = make_instrument()

        assert instrument.instrument_id == InstrumentId.parse("XSHG:600519")
        assert instrument.currency == "CNY"
        assert instrument.instrument_type is InstrumentType.A_SHARE

    def test_instrument_is_immutable(self) -> None:
        instrument = make_instrument()

        with pytest.raises(Exception, match="cannot assign"):
            instrument.display_name = "Other"  # type: ignore[misc]

    def test_a_share_must_not_declare_a_fund_subtype(self) -> None:
        with pytest.raises(InstrumentError):
            make_instrument(fund_subtype=FundSubtype.GOLD)

    def test_etf_declares_an_explicit_approved_subtype(self) -> None:
        instrument = make_instrument(
            instrument_id=InstrumentId.parse("XSHG:510300"),
            display_name="Huatai-PineBridge CSI 300 ETF",
            instrument_type=InstrumentType.EXCHANGE_TRADED_FUND,
            fund_subtype=FundSubtype.BROAD_BASED_EQUITY,
        )

        assert instrument.fund_subtype is FundSubtype.BROAD_BASED_EQUITY

    def test_unapproved_subtype_concepts_cannot_be_expressed(self) -> None:
        # Cross-border/QDII, money-market, and every other unverified subtype
        # are not members of the approved enum, so they fail closed at
        # construction time instead of being modeled as unsupported states.
        with pytest.raises(ValueError):
            FundSubtype("MONEY_MARKET")

        with pytest.raises(ValueError):
            FundSubtype("QDII")

    def test_invalid_session_date_fields_are_rejected(self) -> None:
        from systematic_investing.domain.identifiers import InvalidSessionDateError

        with pytest.raises(InvalidSessionDateError):
            make_instrument(list_date="2001-08-27")  # type: ignore[arg-type]

        with pytest.raises(InstrumentError):
            make_instrument(valid_from=date(2022, 1, 4), valid_to=date(2020, 1, 1))


class TestProfileReferences:
    def test_references_all_four_market_regulatory_profiles(self) -> None:
        instrument = make_instrument()

        assert instrument.lot_rule_profile_id == "LOT:CN-STANDARD"
        assert instrument.settlement_rule_profile_id == "SETTLE:T1"
        assert instrument.price_limit_rule_profile_id == "PLIMIT:A-MAIN-10PCT"
        assert instrument.market_fee_tax_profile_id == "FEE:TAX-A"

    def test_instrument_never_references_broker_or_account_fees(self) -> None:
        # Broker/account commission belongs to run configuration
        # (AccountFeeConfig/BrokerFeeProfile), never to instrument identity.
        field_names = {field.name for field in fields(Instrument)}

        forbidden = {"broker_fee", "commission", "account_fee_config", "min_commission"}
        assert not field_names & forbidden

        with pytest.raises(TypeError):
            make_instrument(broker_commission_rate="0.0003")  # type: ignore[call-arg]


class TestRuleProfiles:
    def test_market_fee_tax_rule_carries_source_and_effective_interval(self) -> None:
        source = RuleSource(
            authority="MOF/STA",
            reference="Announcement [2023] No.39",
            accessed_on=date(2026, 9, 1),
        )
        rule = MarketFeeTaxRule(
            profile_id="FEE:TAX-A",
            effective_from=date(2023, 8, 28),
            effective_to=None,
            source=source,
            stamp_tax_sell_rate=Decimal("0.0005"),
            transfer_fee_rate=Decimal("0.00001"),
        )

        assert rule.profile_id == "FEE:TAX-A"
        assert rule.effective_from == date(2023, 8, 28)
        assert rule.effective_to is None
        assert rule.source.authority == "MOF/STA"
        assert rule.stamp_tax_sell_rate == Decimal("0.0005")

    def test_rule_profiles_are_immutable(self) -> None:
        rule = make_market_fee_tax_rule()

        with pytest.raises(Exception, match="cannot assign"):
            rule.stamp_tax_sell_rate = Decimal("0")  # type: ignore[misc]

    def test_rule_effective_dates_reject_datetimes(self) -> None:
        from systematic_investing.domain.identifiers import InvalidSessionDateError

        with pytest.raises(InvalidSessionDateError):
            make_market_fee_tax_rule(effective_from=datetime(2023, 8, 28, 15, 0))

    def test_open_ended_interval_must_not_end_before_it_starts(self) -> None:
        with pytest.raises(InstrumentMasterError):
            make_market_fee_tax_rule(
                effective_from=date(2023, 8, 28), effective_to=date(2023, 1, 1)
            )

    def test_standard_lot_rule_fields(self) -> None:
        rule = make_lot_rule()

        assert rule.board_lot == 100
        assert rule.buy_increment == 100
        assert rule.odd_lot_sell_policy is OddLotSellPolicy.ALLOWED

    def test_settlement_rule_records_sessions_until_sellable(self) -> None:
        rule = make_settlement_rule()

        assert rule.sessions_until_sellable == 1

    def test_price_limit_rule_records_basis_percent_and_tick(self) -> None:
        rule = make_price_limit_rule()

        assert rule.basis is PriceLimitBasis.PREVIOUS_CLOSE
        assert rule.limit_percent == Decimal("0.10")
        assert rule.tick_size == Decimal("0.001")

    def test_negative_rate_is_rejected(self) -> None:
        with pytest.raises(InstrumentMasterError):
            make_market_fee_tax_rule(stamp_tax_sell_rate=Decimal("-0.0005"))
