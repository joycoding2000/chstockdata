"""Unit tests: itemized fee composition from two separate authorities.

Market/regulatory fee/tax truth comes from the effective-dated Instrument
Master; broker commission/minimum comes from run-owned ``AccountFeeConfig``.
All expected numbers are hand-calculated; Decimal quantization uses explicit
ROUND_HALF_UP to CNY cents. No network.
"""

from datetime import date
from decimal import Decimal

import pytest

from systematic_investing.domain.execution import (
    AccountFeeConfig,
    BrokerFeeProfile,
    UnknownBrokerProfileError,
    compute_fees,
)
from systematic_investing.domain.identifiers import Exchange, InstrumentId
from systematic_investing.domain.market import TradeSide
from systematic_investing.instrument_master.repository import default_m0_master

XSHG_600519 = InstrumentId(exchange=Exchange.XSHG, symbol="600519")
XSHG_510300 = InstrumentId(exchange=Exchange.XSHG, symbol="510300")

SESSION = date(2026, 9, 14)

BROKER = BrokerFeeProfile(
    profile_id="ACCT:MAIN",
    version="1",
    commission_rate=Decimal("0.0003"),
    minimum_commission=Decimal("5"),
    agreement_reference="broker-agreement-2026",
    effective_from=date(2022, 1, 4),
    effective_to=None,
)

ACCOUNT = AccountFeeConfig(
    config_id="RUN-MAIN",
    config_version="1",
    broker_profiles=(BROKER,),
)


def market_rules(instrument_id: InstrumentId):
    return default_m0_master().resolve_rules(instrument_id, SESSION).market_fee_tax


class TestFeeComposition:
    def test_small_buy_hits_the_minimum_commission(self) -> None:
        fees = compute_fees(
            market_rules(XSHG_600519), BROKER, TradeSide.BUY, 100, Decimal("10.00")
        )

        # Notional 1000.00: commission 0.30 below the CNY 5 minimum; the
        # minimum adjustment tops the commission up; stamp tax is sell-side
        # only; transfer fee 0.01.
        assert fees.commission.amount == Decimal("0.30")
        assert fees.minimum_commission_adjustment.amount == Decimal("4.70")
        assert fees.stamp_tax.amount == Decimal("0.00")
        assert fees.transfer_fee.amount == Decimal("0.01")
        assert fees.total.amount == Decimal("5.01")

    def test_large_buy_commission_exceeds_the_minimum(self) -> None:
        fees = compute_fees(
            market_rules(XSHG_600519), BROKER, TradeSide.BUY, 10000, Decimal("10.00")
        )

        # Notional 100000.00: commission 30.00 above the minimum, no
        # adjustment; transfer fee 1.00.
        assert fees.commission.amount == Decimal("30.00")
        assert fees.minimum_commission_adjustment.amount == Decimal("0.00")
        assert fees.stamp_tax.amount == Decimal("0.00")
        assert fees.transfer_fee.amount == Decimal("1.00")
        assert fees.total.amount == Decimal("31.00")

    def test_stock_sell_carries_stamp_tax(self) -> None:
        fees = compute_fees(
            market_rules(XSHG_600519), BROKER, TradeSide.SELL, 1000, Decimal("10.00")
        )

        # Notional 10000.00: commission 3.00 + 2.00 minimum adjustment;
        # stamp tax 0.0005 * 10000 = 5.00; transfer fee 0.10.
        assert fees.commission.amount == Decimal("3.00")
        assert fees.minimum_commission_adjustment.amount == Decimal("2.00")
        assert fees.stamp_tax.amount == Decimal("5.00")
        assert fees.transfer_fee.amount == Decimal("0.10")
        assert fees.total.amount == Decimal("10.10")

    def test_etf_profile_has_no_stamp_tax_or_transfer_fee(self) -> None:
        fees = compute_fees(
            market_rules(XSHG_510300), BROKER, TradeSide.SELL, 1000, Decimal("10.00")
        )

        # ETF market fee/tax truth: stamp duty scope excludes fund trades
        # and the transfer fee scope covers stocks only. Broker commission
        # is still run-owned and applies.
        assert fees.stamp_tax.amount == Decimal("0.00")
        assert fees.transfer_fee.amount == Decimal("0.00")
        assert fees.commission.amount == Decimal("3.00")
        assert fees.minimum_commission_adjustment.amount == Decimal("2.00")
        assert fees.total.amount == Decimal("5.00")

    def test_behavior_follows_the_rule_profile_not_the_instrument_type(self) -> None:
        # An A-share instrument carried through the ETF fee family produces
        # the ETF outcome, proving nothing branches on "is ETF" alone.
        etf_rule = market_rules(XSHG_510300)

        fees = compute_fees(etf_rule, BROKER, TradeSide.SELL, 1000, Decimal("10.00"))

        assert fees.stamp_tax.amount == Decimal("0.00")
        assert fees.transfer_fee.amount == Decimal("0.00")

    def test_monetary_rounding_is_half_up_to_cents(self) -> None:
        fees = compute_fees(
            market_rules(XSHG_600519), BROKER, TradeSide.SELL, 100, Decimal("10.005")
        )

        # Notional 1000.50: commission 0.300150 -> 0.30 (half-up), minimum
        # adjustment 4.70; stamp 0.500250 -> 0.50; transfer 0.010005 -> 0.01.
        assert fees.commission.amount == Decimal("0.30")
        assert fees.minimum_commission_adjustment.amount == Decimal("4.70")
        assert fees.stamp_tax.amount == Decimal("0.50")
        assert fees.transfer_fee.amount == Decimal("0.01")
        assert fees.total.amount == Decimal("5.51")

    def test_stamp_tax_is_zero_for_buys(self) -> None:
        fees = compute_fees(
            market_rules(XSHG_600519), BROKER, TradeSide.BUY, 1000, Decimal("10.00")
        )

        assert fees.stamp_tax.amount == Decimal("0.00")


class TestAccountFeeConfig:
    def test_effective_dated_broker_profile_resolution(self) -> None:
        cheap = BrokerFeeProfile(
            profile_id="ACCT:MAIN",
            version="1",
            commission_rate=Decimal("0.0003"),
            minimum_commission=Decimal("5"),
            agreement_reference="broker-agreement-2026",
            effective_from=date(2022, 1, 4),
            effective_to=date(2026, 8, 31),
        )
        standard = BrokerFeeProfile(
            profile_id="ACCT:MAIN",
            version="2",
            commission_rate=Decimal("0.0005"),
            minimum_commission=Decimal("5"),
            agreement_reference="broker-agreement-2027",
            effective_from=date(2026, 9, 1),
            effective_to=None,
        )
        config = AccountFeeConfig(
            config_id="RUN-MAIN",
            config_version="2",
            broker_profiles=(cheap, standard),
        )

        assert config.resolve_broker_profile(date(2026, 8, 15)) is cheap
        assert config.resolve_broker_profile(SESSION) is standard

    def test_uncovered_broker_profile_date_fails_closed(self) -> None:
        with pytest.raises(UnknownBrokerProfileError):
            ACCOUNT.resolve_broker_profile(date(2021, 12, 31))

    def test_config_digest_is_deterministic_and_input_sensitive(self) -> None:
        other = AccountFeeConfig(
            config_id="RUN-MAIN",
            config_version="1",
            broker_profiles=(
                BrokerFeeProfile(
                    profile_id="ACCT:MAIN",
                    version="1",
                    commission_rate=Decimal("0.0004"),
                    minimum_commission=Decimal("5"),
                    agreement_reference="broker-agreement-2026",
                    effective_from=date(2022, 1, 4),
                    effective_to=None,
                ),
            ),
        )

        assert ACCOUNT.content_digest() == ACCOUNT.content_digest()
        assert other.content_digest() != ACCOUNT.content_digest()


class TestAuthoritySeparation:
    def test_instrument_master_market_rules_never_own_broker_fees(self) -> None:
        rules = default_m0_master().resolve_rules(XSHG_600519, SESSION)

        assert not hasattr(rules.market_fee_tax, "commission_rate")
        assert not hasattr(rules.market_fee_tax, "minimum_commission")
        assert not any(
            "broker" in field_name.lower() for field_name in rules.__dataclass_fields__
        )
