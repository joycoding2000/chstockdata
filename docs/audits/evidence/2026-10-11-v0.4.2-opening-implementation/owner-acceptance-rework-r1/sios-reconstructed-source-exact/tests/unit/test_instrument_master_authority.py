"""Unit tests: system-owned Instrument Master authority semantics."""

from datetime import date
from decimal import Decimal
from typing import ClassVar

import pytest

from systematic_investing.domain.identifiers import InstrumentId
from systematic_investing.domain.instruments import FundSubtype, Instrument, InstrumentType
from systematic_investing.instrument_master.models import (
    AdjudicationStatus,
    InstrumentMasterError,
    LotRule,
    MarketFeeTaxRule,
    OddLotSellPolicy,
    PriceLimitBasis,
    PriceLimitRule,
    RuleCandidate,
    RuleKind,
    RuleSource,
    SettlementRule,
    UnknownInstrumentError,
    UnknownRuleError,
    UnsupportedClassificationError,
)
from systematic_investing.instrument_master.repository import InstrumentMaster, default_m0_master

SOURCE = RuleSource(
    authority="MOF/STA", reference="Announcement [2023] No.39", accessed_on=date(2026, 9, 1)
)
SSE_SOURCE = RuleSource(authority="SSE", reference="Trading rules", accessed_on=date(2026, 9, 1))


def make_instrument(
    instrument_id: InstrumentId,
    *,
    instrument_type: InstrumentType = InstrumentType.A_SHARE,
    fund_subtype: FundSubtype | None = None,
    valid_from: date = date(2022, 1, 4),
    valid_to: date | None = None,
    market_fee_tax_profile_id: str = "FEE:TAX-A",
    reference_data_version: str = "FIXTURE-1",
) -> Instrument:
    return Instrument(
        instrument_id=instrument_id,
        display_name="Fixture instrument",
        currency="CNY",
        instrument_type=instrument_type,
        fund_subtype=fund_subtype,
        list_date=date(2001, 8, 27),
        delist_date=None,
        trading_calendar_id=instrument_id.exchange.value,
        lot_rule_profile_id="LOT:CN-STANDARD",
        settlement_rule_profile_id="SETTLE:T1",
        price_limit_rule_profile_id="PLIMIT:A-MAIN-10PCT",
        market_fee_tax_profile_id=market_fee_tax_profile_id,
        reference_data_version=reference_data_version,
        valid_from=valid_from,
        valid_to=valid_to,
    )


def make_stamp_rule(
    stamp: str, effective_from: date, effective_to: date | None
) -> MarketFeeTaxRule:
    return MarketFeeTaxRule(
        profile_id="FEE:TAX-A",
        effective_from=effective_from,
        effective_to=effective_to,
        source=SOURCE,
        stamp_tax_sell_rate=Decimal(stamp),
        transfer_fee_rate=Decimal("0.00001"),
    )


class TestRegistrationAndInstrumentResolution:
    def test_registered_instrument_resolves_by_valid_interval(self) -> None:
        master = InstrumentMaster()
        instrument = make_instrument(InstrumentId.parse("XSHG:600519"))
        master.register_instrument(instrument)

        resolved = master.resolve_instrument(InstrumentId.parse("XSHG:600519"), date(2024, 6, 3))

        assert resolved == instrument

    def test_unknown_instrument_is_typed_error(self) -> None:
        master = InstrumentMaster()

        with pytest.raises(UnknownInstrumentError):
            master.resolve_instrument(InstrumentId.parse("XSHE:000001"), date(2024, 6, 3))

    def test_reference_data_versions_select_by_valid_interval(self) -> None:
        master = InstrumentMaster()
        v1 = make_instrument(
            InstrumentId.parse("XSHG:600519"),
            valid_from=date(2022, 1, 4),
            valid_to=date(2023, 12, 29),
        )
        v2 = make_instrument(
            InstrumentId.parse("XSHG:600519"),
            valid_from=date(2024, 1, 2),
            reference_data_version="FIXTURE-2",
        )
        master.register_instrument(v1)
        master.register_instrument(v2)

        assert master.resolve_instrument(InstrumentId.parse("XSHG:600519"), date(2023, 6, 1)) == v1
        assert master.resolve_instrument(InstrumentId.parse("XSHG:600519"), date(2024, 6, 3)) == v2

    def test_gap_in_instrument_versions_fails_closed(self) -> None:
        master = InstrumentMaster()
        master.register_instrument(
            make_instrument(
                InstrumentId.parse("XSHG:600519"),
                valid_from=date(2022, 1, 4),
                valid_to=date(2023, 12, 29),
            )
        )

        with pytest.raises(UnknownInstrumentError):
            master.resolve_instrument(InstrumentId.parse("XSHG:600519"), date(2024, 6, 3))

    def test_overlapping_instrument_versions_are_rejected(self) -> None:
        master = InstrumentMaster()
        master.register_instrument(make_instrument(InstrumentId.parse("XSHG:600519")))

        with pytest.raises(InstrumentMasterError):
            master.register_instrument(make_instrument(InstrumentId.parse("XSHG:600519")))


def make_settlement_rule() -> SettlementRule:
    return SettlementRule(
        profile_id="SETTLE:T1",
        effective_from=date(2022, 4, 29),
        effective_to=None,
        source=SSE_SOURCE,
        sessions_until_sellable=1,
    )


def register_standard_bundle(
    master: InstrumentMaster, fee_family: str, stamp_versions: list
) -> None:
    master.add_rule_profile(
        LotRule(
            profile_id="LOT:CN-STANDARD",
            effective_from=date(2022, 4, 29),
            effective_to=None,
            source=SSE_SOURCE,
            board_lot=100,
            buy_increment=100,
        )
    )
    master.add_rule_profile(make_settlement_rule())
    master.add_rule_profile(
        PriceLimitRule(
            profile_id="PLIMIT:A-MAIN-10PCT",
            effective_from=date(2022, 4, 29),
            effective_to=None,
            source=SSE_SOURCE,
        )
    )
    for rule in stamp_versions:
        master.add_rule_profile(rule)


class TestEffectiveDateRuleSelection:
    def build_stamp_tax_history(self) -> tuple[InstrumentMaster, InstrumentId]:
        master = InstrumentMaster()
        instrument_id = InstrumentId.parse("XSHG:600519")
        master.register_instrument(make_instrument(instrument_id))
        # Real effective-dated history: stamp duty on sells was 0.1% before
        # 2023-08-28 and 0.05% from 2023-08-28 (MOF/STA Announcement No.39).
        register_standard_bundle(
            master,
            "FEE:TAX-A",
            [
                make_stamp_rule("0.001", date(2022, 4, 29), date(2023, 8, 27)),
                make_stamp_rule("0.0005", date(2023, 8, 28), None),
            ],
        )
        return master, instrument_id

    def test_profile_version_is_selected_by_session_date(self) -> None:
        master, instrument_id = self.build_stamp_tax_history()

        before = master.resolve_rules(instrument_id, date(2023, 8, 25))
        after = master.resolve_rules(instrument_id, date(2023, 8, 28))

        assert before.market_fee_tax.stamp_tax_sell_rate == Decimal("0.001")
        assert after.market_fee_tax.stamp_tax_sell_rate == Decimal("0.0005")

    def test_resolved_bundle_reports_session_and_all_four_rules(self) -> None:
        master, instrument_id = self.build_stamp_tax_history()

        rules = master.resolve_rules(instrument_id, date(2024, 6, 3))

        assert rules.session_date == date(2024, 6, 3)
        assert rules.lot.board_lot == 100
        assert rules.settlement.sessions_until_sellable == 1
        assert rules.price_limit.limit_percent == Decimal("0.10")
        assert rules.market_fee_tax.profile_id == "FEE:TAX-A"

    def test_date_not_covered_by_any_version_fails_closed(self) -> None:
        master, instrument_id = self.build_stamp_tax_history()

        # Inside the instrument's validity (from 2022-01-04) but before any
        # rule profile version becomes effective (from 2022-04-29).
        with pytest.raises(UnknownRuleError):
            master.resolve_rules(instrument_id, date(2022, 2, 1))

    def test_overlapping_rule_versions_are_rejected(self) -> None:
        master, _ = self.build_stamp_tax_history()

        with pytest.raises(InstrumentMasterError):
            master.add_rule_profile(make_stamp_rule("0.0008", date(2023, 1, 1), None))

    def test_missing_family_profile_fails_closed_for_that_instrument_only(self) -> None:
        # An ETF fee family with no coverage must not silently inherit the
        # A-share profile that exists in the same master.
        master = InstrumentMaster()
        etf_id = InstrumentId.parse("XSHG:510300")
        master.register_instrument(
            make_instrument(
                etf_id,
                instrument_type=InstrumentType.EXCHANGE_TRADED_FUND,
                fund_subtype=FundSubtype.BROAD_BASED_EQUITY,
                market_fee_tax_profile_id="FEE:TAX-ETF-EQUITY",
            )
        )
        register_standard_bundle(
            master, "FEE:TAX-A", [make_stamp_rule("0.0005", date(2022, 4, 29), None)]
        )

        with pytest.raises(UnknownRuleError):
            master.resolve_rules(etf_id, date(2024, 6, 3))


class TestDefaultM0EtfHistory:
    @pytest.mark.parametrize(
        ("instrument_text", "subtype", "sessions_until_sellable"),
        [
            ("XSHG:510300", FundSubtype.BROAD_BASED_EQUITY, 1),
            ("XSHE:159915", FundSubtype.BROAD_BASED_EQUITY, 1),
            ("XSHG:518880", FundSubtype.GOLD, 0),
            ("XSHG:511010", FundSubtype.BOND, 0),
        ],
    )
    def test_approved_etf_history_covers_the_m1_basic_window(
        self,
        instrument_text: str,
        subtype: FundSubtype,
        sessions_until_sellable: int,
    ) -> None:
        master = default_m0_master()
        instrument_id = InstrumentId.parse(instrument_text)

        instrument = master.resolve_instrument(instrument_id, date(2015, 1, 5))
        rules = master.resolve_rules(instrument_id, date(2015, 1, 5))

        assert instrument.fund_subtype is subtype
        assert instrument.valid_from <= date(2015, 1, 5)
        assert rules.lot.profile_id == "LOT:ETF-STANDARD"
        assert rules.price_limit.limit_percent == Decimal("0.10")
        assert rules.settlement.sessions_until_sellable == sessions_until_sellable

    def test_bond_etf_uses_its_exchange_listing_date(self) -> None:
        instrument = default_m0_master().resolve_instrument(
            InstrumentId.parse("XSHG:511010"), date(2015, 1, 5)
        )

        assert instrument.list_date == date(2013, 3, 25)

    def test_chinext_etf_price_limit_changes_to_twenty_percent_on_2020_08_24(
        self,
    ) -> None:
        master = default_m0_master()
        instrument_id = InstrumentId.parse("XSHE:159915")

        before = master.resolve_rules(instrument_id, date(2020, 8, 21)).price_limit
        after = master.resolve_rules(instrument_id, date(2020, 8, 24)).price_limit

        assert before.limit_percent == Decimal("0.10")
        assert after.limit_percent == Decimal("0.20")
        assert before.effective_to == date(2020, 8, 23)
        assert after.effective_from == date(2020, 8, 24)

    def test_pre_correction_seed_reproduces_the_phase4_unknown_classification(
        self,
    ) -> None:
        """Root-cause evidence for the 4h44m Phase-4 materialization failure.

        The pre-correction seed registered every instrument and rule family
        with valid/effective intervals starting 2022-01-04. A 2015-01-05
        Basic request therefore resolved no approved classification for any
        of the four shared-scope ETFs, and the gate reported
        UNKNOWN_INSTRUMENT_CLASSIFICATION after the full provider download.
        """
        pre_correction_valid_from = date(2022, 1, 4)
        master = InstrumentMaster()
        master.add_rule_profile(
            LotRule(
                profile_id="LOT:CN-STANDARD",
                effective_from=pre_correction_valid_from,
                effective_to=None,
                source=SSE_SOURCE,
                board_lot=100,
                buy_increment=100,
                odd_lot_sell_policy=OddLotSellPolicy.ALLOWED,
            )
        )
        master.add_rule_profile(
            SettlementRule(
                profile_id="SETTLE:T1",
                effective_from=pre_correction_valid_from,
                effective_to=None,
                source=SSE_SOURCE,
                sessions_until_sellable=1,
            )
        )
        master.add_rule_profile(
            PriceLimitRule(
                profile_id="PLIMIT:ETF-10PCT",
                effective_from=pre_correction_valid_from,
                effective_to=None,
                source=SSE_SOURCE,
                basis=PriceLimitBasis.PREVIOUS_CLOSE,
                limit_percent=Decimal("0.10"),
                tick_size=Decimal("0.001"),
            )
        )
        master.add_rule_profile(
            MarketFeeTaxRule(
                profile_id="FEE:TAX-ETF-EQUITY",
                effective_from=pre_correction_valid_from,
                effective_to=None,
                source=SSE_SOURCE,
                stamp_tax_sell_rate=Decimal("0"),
                transfer_fee_rate=Decimal("0"),
            )
        )
        shared_scope = (
            "XSHG:510300",
            "XSHE:159915",
            "XSHG:518880",
            "XSHG:511010",
        )
        for text in shared_scope:
            instrument_id = InstrumentId.parse(text)
            with pytest.raises(UnknownInstrumentError):
                master.resolve_instrument(instrument_id, date(2015, 1, 5))
            master.register_instrument(
                make_instrument(
                    instrument_id,
                    instrument_type=InstrumentType.EXCHANGE_TRADED_FUND,
                    fund_subtype=FundSubtype.BROAD_BASED_EQUITY,
                    valid_from=pre_correction_valid_from,
                    market_fee_tax_profile_id="FEE:TAX-ETF-EQUITY",
                )
            )
            with pytest.raises(UnknownInstrumentError):
                master.resolve_instrument(instrument_id, date(2015, 1, 5))


class TestClassificationFailClosed:
    def test_etf_without_explicit_approved_subtype_is_refused(self) -> None:
        # Classification is never inferred from the symbol: an ETF without an
        # explicit approved subtype cannot enter the authority.
        master = InstrumentMaster()

        with pytest.raises(UnsupportedClassificationError):
            master.register_instrument(
                make_instrument(
                    InstrumentId.parse("XSHG:513100"),
                    instrument_type=InstrumentType.EXCHANGE_TRADED_FUND,
                    fund_subtype=None,
                )
            )

    def test_etf_with_each_approved_subtype_is_accepted(self) -> None:
        master = InstrumentMaster()
        approved = [
            (InstrumentId.parse("XSHG:510300"), FundSubtype.BROAD_BASED_EQUITY),
            (InstrumentId.parse("XSHG:518880"), FundSubtype.GOLD),
            (InstrumentId.parse("XSHG:511010"), FundSubtype.BOND),
        ]

        for instrument_id, subtype in approved:
            master.register_instrument(
                make_instrument(
                    instrument_id,
                    instrument_type=InstrumentType.EXCHANGE_TRADED_FUND,
                    fund_subtype=subtype,
                )
            )

        resolved_gold = master.resolve_instrument(
            InstrumentId.parse("XSHG:518880"), date(2024, 6, 3)
        )
        assert resolved_gold.fund_subtype is FundSubtype.GOLD

    def test_unapproved_subtype_cannot_be_constructed_at_all(self) -> None:
        with pytest.raises(ValueError):
            FundSubtype("CROSS_BORDER_QDII")


class TestProviderCandidateAdjudication:
    def build_master_with_approved_stamp(self) -> tuple[InstrumentMaster, InstrumentId]:
        master = InstrumentMaster()
        instrument_id = InstrumentId.parse("XSHG:600519")
        master.register_instrument(make_instrument(instrument_id))
        register_standard_bundle(
            master, "FEE:TAX-A", [make_stamp_rule("0.0005", date(2022, 4, 29), None)]
        )
        return master, instrument_id

    def test_conflicting_candidate_does_not_override_approved_profile(self) -> None:
        master, instrument_id = self.build_master_with_approved_stamp()
        # Provider claims ETF-like zero stamp tax; the approved profile says
        # 0.0005. The candidate must lose.
        candidate = RuleCandidate(
            instrument_id=instrument_id,
            session_date=date(2024, 6, 3),
            rule_kind=RuleKind.MARKET_FEE_TAX,
            proposed_value=make_stamp_rule("0", date(2024, 1, 1), None),
            proposed_by="chstockdata",
        )

        adjudication = master.adjudicate_rule_candidate(candidate)

        assert adjudication.status is AdjudicationStatus.APPROVED_PROFILE_GOVERNS
        assert adjudication.approved_rules is not None
        assert adjudication.approved_rules.market_fee_tax.stamp_tax_sell_rate == Decimal("0.0005")

    def test_candidate_without_approved_coverage_fails_closed(self) -> None:
        master, instrument_id = self.build_master_with_approved_stamp()
        candidate = RuleCandidate(
            instrument_id=instrument_id,
            session_date=date(2021, 6, 1),  # before any approved coverage
            rule_kind=RuleKind.MARKET_FEE_TAX,
            proposed_value=make_stamp_rule("0", date(2021, 1, 1), None),
            proposed_by="chstockdata",
        )

        adjudication = master.adjudicate_rule_candidate(candidate)

        assert adjudication.status is AdjudicationStatus.FAIL_CLOSED_NO_APPROVED_PROFILE
        assert adjudication.approved_rules is None

    def test_candidate_for_unknown_instrument_fails_closed(self) -> None:
        master, _ = self.build_master_with_approved_stamp()
        candidate = RuleCandidate(
            instrument_id=InstrumentId.parse("XSHE:300750"),
            session_date=date(2024, 6, 3),
            rule_kind=RuleKind.MARKET_FEE_TAX,
            proposed_value=make_stamp_rule("0", date(2024, 1, 1), None),
            proposed_by="chstockdata",
        )

        adjudication = master.adjudicate_rule_candidate(candidate)

        assert adjudication.status is AdjudicationStatus.FAIL_CLOSED_NO_APPROVED_PROFILE
        assert adjudication.approved_rules is None


class TestDefaultM0Seed:
    """Seed fixtures: standard Shanghai/Shenzhen A-shares and the approved
    domestic broad-based equity/gold/bond ETF scopes only."""

    SCOPE: ClassVar[tuple] = (
        ("XSHG:600519", InstrumentType.A_SHARE, None),
        ("XSHE:000001", InstrumentType.A_SHARE, None),
        ("XSHG:510300", InstrumentType.EXCHANGE_TRADED_FUND, FundSubtype.BROAD_BASED_EQUITY),
        ("XSHE:159915", InstrumentType.EXCHANGE_TRADED_FUND, FundSubtype.BROAD_BASED_EQUITY),
        ("XSHG:518880", InstrumentType.EXCHANGE_TRADED_FUND, FundSubtype.GOLD),
        ("XSHG:511010", InstrumentType.EXCHANGE_TRADED_FUND, FundSubtype.BOND),
    )

    def test_all_seed_instruments_resolve_rules_on_a_recent_session_date(self) -> None:
        master = default_m0_master()
        session_date = date(2024, 6, 3)

        for code, instrument_type, subtype in self.SCOPE:
            instrument_id = InstrumentId.parse(code)
            instrument = master.resolve_instrument(instrument_id, session_date)

            assert instrument.instrument_type is instrument_type
            assert instrument.fund_subtype is subtype

            rules = master.resolve_rules(instrument_id, session_date)
            assert rules.lot.board_lot == 100
            assert rules.settlement.sessions_until_sellable == (
                0 if subtype in (FundSubtype.GOLD, FundSubtype.BOND) else 1
            )
            assert rules.price_limit.limit_percent == (
                Decimal("0.20") if code == "XSHE:159915" else Decimal("0.10")
            )

    def test_seed_uses_effective_dated_stamp_tax_history(self) -> None:
        master = default_m0_master()
        instrument_id = InstrumentId.parse("XSHG:600519")

        before = master.resolve_rules(instrument_id, date(2023, 8, 25)).market_fee_tax
        after = master.resolve_rules(instrument_id, date(2023, 8, 28)).market_fee_tax

        assert before.stamp_tax_sell_rate == Decimal("0.001")
        assert after.stamp_tax_sell_rate == Decimal("0.0005")

    def test_each_approved_etf_subtype_has_its_own_fee_profile_family(self) -> None:
        # Passing one subtype never approves another: each approved ETF
        # subtype references its own fee/tax profile family, while instruments
        # within the same subtype share that family.
        master = default_m0_master()
        session_date = date(2024, 6, 3)

        families_by_subtype = {}
        for code, instrument_type, subtype in self.SCOPE:
            if instrument_type is not InstrumentType.EXCHANGE_TRADED_FUND:
                continue
            instrument = master.resolve_instrument(InstrumentId.parse(code), session_date)
            families_by_subtype[subtype] = instrument.market_fee_tax_profile_id
        subtypes = {subtype for _, _, subtype in self.SCOPE if subtype is not None}

        assert set(families_by_subtype) == subtypes
        assert len(set(families_by_subtype.values())) == len(subtypes)

    def test_seed_rule_profiles_carry_authoritative_sources(self) -> None:
        master = default_m0_master()
        rules = master.resolve_rules(InstrumentId.parse("XSHE:159915"), date(2024, 6, 3))

        assert rules.market_fee_tax.source.authority
        assert rules.lot.source.reference
        assert rules.settlement.source.accessed_on <= date(2026, 9, 17)
