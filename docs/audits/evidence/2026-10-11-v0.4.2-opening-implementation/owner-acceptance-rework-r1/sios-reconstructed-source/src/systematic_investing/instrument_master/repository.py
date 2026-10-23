"""Instrument Master repository: registration and effective-dated resolution.

Resolution uses only approved profiles registered in this master. Provider
candidates may be adjudicated against the authority, but no provider input
is ever promoted implicitly; uncovered sessions fail closed.
"""

from datetime import date
from decimal import Decimal

from systematic_investing.domain.identifiers import Exchange, InstrumentId
from systematic_investing.domain.instruments import (
    FundSubtype,
    Instrument,
    InstrumentType,
)
from systematic_investing.instrument_master.models import (
    AdjudicationStatus,
    ConflictingVersionsError,
    EffectiveDatedRule,
    InstrumentRules,
    LotRule,
    MarketFeeTaxRule,
    OddLotSellPolicy,
    PriceLimitBasis,
    PriceLimitRule,
    RuleAdjudication,
    RuleCandidate,
    RuleKind,
    RuleSource,
    SettlementRule,
    UnknownInstrumentError,
    UnknownRuleError,
    UnsupportedClassificationError,
    rule_kind_of,
)

_END_OF_TIME = date(9999, 12, 31)


def _covers(valid_from: date, valid_to: date | None, as_of: date) -> bool:
    return valid_from <= as_of <= (valid_to if valid_to is not None else _END_OF_TIME)


def _overlaps(
    from_a: date, to_a: date | None, from_b: date, to_b: date | None
) -> bool:
    end_a = to_a if to_a is not None else _END_OF_TIME
    end_b = to_b if to_b is not None else _END_OF_TIME
    return from_a <= end_b and from_b <= end_a


class InstrumentMaster:
    """The system-owned Production authority for instrument classification
    and market/regulatory rule profiles. Every record is registered with
    source provenance and an explicit effective/valid interval."""

    def __init__(self) -> None:
        self._instruments: dict[InstrumentId, list[Instrument]] = {}
        self._rule_profiles: dict[RuleKind, dict[str, list[EffectiveDatedRule]]] = {}

    def register_instrument(self, instrument: Instrument) -> None:
        if (
            instrument.instrument_type is InstrumentType.EXCHANGE_TRADED_FUND
            and instrument.fund_subtype is None
        ):
            raise UnsupportedClassificationError(
                f"{instrument.instrument_id}: an ETF requires an explicit approved fund "
                "subtype; classification is never inferred from the symbol"
            )
        versions = self._instruments.setdefault(instrument.instrument_id, [])
        for existing in versions:
            if _overlaps(
                existing.valid_from, existing.valid_to, instrument.valid_from, instrument.valid_to
            ):
                raise ConflictingVersionsError(
                    f"{instrument.instrument_id} already has an approved version covering "
                    f"[{instrument.valid_from}, {instrument.valid_to}]"
                )
        versions.append(instrument)

    def resolve_instrument(self, instrument_id: InstrumentId, as_of: date) -> Instrument:
        matches = [
            instrument
            for instrument in self._instruments.get(instrument_id, [])
            if _covers(instrument.valid_from, instrument.valid_to, as_of)
        ]
        if not matches:
            raise UnknownInstrumentError(
                f"no approved instrument version covers {instrument_id} on {as_of}"
            )
        if len(matches) > 1:
            raise ConflictingVersionsError(
                f"multiple approved instrument versions cover {instrument_id} on {as_of}"
            )
        return matches[0]

    def add_rule_profile(self, profile: EffectiveDatedRule) -> None:
        """Register one version of a rule profile family. Versions of the
        same family must not overlap; the effective interval decides which
        version governs a session, so history is never rewritten."""
        kind = rule_kind_of(profile)
        family = self._rule_profiles.setdefault(kind, {}).setdefault(profile.profile_id, [])
        for existing in family:
            if _overlaps(
                existing.effective_from,
                existing.effective_to,
                profile.effective_from,
                profile.effective_to,
            ):
                raise ConflictingVersionsError(
                    f"rule profile {profile.profile_id} already has an approved version "
                    f"covering [{profile.effective_from}, {profile.effective_to}]"
                )
        family.append(profile)

    def resolve_rules(self, instrument_id: InstrumentId, session_date: date) -> InstrumentRules:
        instrument = self.resolve_instrument(instrument_id, session_date)
        selected = {}
        for kind, reference in (
            (RuleKind.LOT, instrument.lot_rule_profile_id),
            (RuleKind.SETTLEMENT, instrument.settlement_rule_profile_id),
            (RuleKind.PRICE_LIMIT, instrument.price_limit_rule_profile_id),
            (RuleKind.MARKET_FEE_TAX, instrument.market_fee_tax_profile_id),
        ):
            candidates = [
                profile
                for profile in self._rule_profiles.get(kind, {}).get(reference, [])
                if profile.covers(session_date)
            ]
            if not candidates:
                raise UnknownRuleError(
                    f"no approved {kind.value} profile covers {reference} for "
                    f"{instrument_id} on {session_date}"
                )
            if len(candidates) > 1:
                raise ConflictingVersionsError(
                    f"multiple approved {kind.value} profile versions cover {reference} "
                    f"for {instrument_id} on {session_date}"
                )
            selected[kind] = candidates[0]
        return InstrumentRules(
            session_date=session_date,
            lot=selected[RuleKind.LOT],
            settlement=selected[RuleKind.SETTLEMENT],
            price_limit=selected[RuleKind.PRICE_LIMIT],
            market_fee_tax=selected[RuleKind.MARKET_FEE_TAX],
        )

    def adjudicate_rule_candidate(self, candidate: RuleCandidate) -> RuleAdjudication:
        """Adjudicate a provider candidate against the approved authority.

        When an approved profile covers the session, the approved bundle
        governs and the candidate values are ignored entirely. When nothing
        approved covers the session, the result fails closed; the candidate
        is never promoted, merged, or used as a fallback.
        """
        try:
            approved = self.resolve_rules(candidate.instrument_id, candidate.session_date)
        except (UnknownInstrumentError, UnknownRuleError):
            return RuleAdjudication(
                status=AdjudicationStatus.FAIL_CLOSED_NO_APPROVED_PROFILE,
                approved_rules=None,
            )
        return RuleAdjudication(
            status=AdjudicationStatus.APPROVED_PROFILE_GOVERNS,
            approved_rules=approved,
        )


_SEED_ACCESSED_ON = date(2026, 9, 14)
_SEED_VALID_FROM = date(2022, 1, 4)
_SEED_REFERENCE_VERSION = "M0-SEED-1"
_ETF_HISTORY_VALID_FROM = date(2015, 1, 5)
_ETF_HISTORY_ACCESSED_ON = date(2026, 9, 17)
_ETF_HISTORY_REFERENCE_VERSION = "M0-ETF-HISTORY-1"


def _source(authority: str, reference: str) -> RuleSource:
    return RuleSource(authority=authority, reference=reference, accessed_on=_SEED_ACCESSED_ON)


def _etf_history_source(authority: str, reference: str) -> RuleSource:
    return RuleSource(
        authority=authority,
        reference=reference,
        accessed_on=_ETF_HISTORY_ACCESSED_ON,
    )


def _seed_market_fee_tax_versions() -> list[MarketFeeTaxRule]:
    """Stamp-duty history for A-shares: 0.1% on sells before 2023-08-28 and
    0.05% from 2023-08-28 (MOF/STA Announcement [2023] No.39). The CSDC
    transfer fee has been 0.001% per side since 2022-04-29. Earlier windows
    are intentionally not covered: unknown scope fails closed."""
    return [
        MarketFeeTaxRule(
            profile_id="FEE:TAX-A-STANDARD",
            effective_from=date(2022, 4, 29),
            effective_to=date(2023, 8, 27),
            source=_source("MOF/STA", "Securities transaction stamp duty 0.1% on sells"),
            stamp_tax_sell_rate=Decimal("0.001"),
            transfer_fee_rate=Decimal("0.00001"),
        ),
        MarketFeeTaxRule(
            profile_id="FEE:TAX-A-STANDARD",
            effective_from=date(2023, 8, 28),
            effective_to=None,
            source=_source(
                "MOF/STA", "Announcement [2023] No.39: stamp duty halved to 0.05% on sells"
            ),
            stamp_tax_sell_rate=Decimal("0.0005"),
            transfer_fee_rate=Decimal("0.00001"),
        ),
    ]


def _seed_etf_fee_family(profile_id: str) -> list[MarketFeeTaxRule]:
    """Domestic ETF market fee/tax truth: no stamp duty (it covers securities
    transfer documents for stocks, not fund trades) and no CSDC transfer fee."""
    return [
        MarketFeeTaxRule(
            profile_id=profile_id,
            effective_from=_ETF_HISTORY_VALID_FROM,
            effective_to=None,
            source=_etf_history_source(
                "MOF/STA + CSDC",
                "Finance/Tax [2002] 128 exempts fund-unit trading from stamp tax; "
                "ChinaClear investor transaction transfer fees cover A-shares, not ETF trades",
            ),
            stamp_tax_sell_rate=Decimal("0"),
            transfer_fee_rate=Decimal("0"),
        )
    ]


def default_m0_master() -> InstrumentMaster:
    """Seed the M0 Instrument Master scopes: standard Shanghai/Shenzhen
    A-shares plus the approved domestic broad-based equity, gold, and bond
    ETF subtypes. Cross-border/QDII, money-market, and every other subtype
    have no seed profile and fail closed."""
    master = InstrumentMaster()

    master.add_rule_profile(
        LotRule(
            profile_id="LOT:CN-STANDARD",
            effective_from=_SEED_VALID_FROM,
            effective_to=None,
            source=_source(
                "SSE/SZSE", "Trading rules: buy in board lots of 100; odd-lot sells allowed"
            ),
            board_lot=100,
            buy_increment=100,
            odd_lot_sell_policy=OddLotSellPolicy.ALLOWED,
        )
    )
    master.add_rule_profile(
        LotRule(
            profile_id="LOT:ETF-STANDARD",
            effective_from=_ETF_HISTORY_VALID_FROM,
            effective_to=None,
            source=_etf_history_source(
                "SSE/SZSE",
                "Exchange fund trading rules: ETF buys use lots of 100 units; "
                "a residual odd lot may be sold in one order",
            ),
            board_lot=100,
            buy_increment=100,
            odd_lot_sell_policy=OddLotSellPolicy.ALLOWED,
        )
    )
    master.add_rule_profile(
        SettlementRule(
            profile_id="SETTLE:T1",
            effective_from=_SEED_VALID_FROM,
            effective_to=None,
            source=_source("SSE/SZSE", "Trading rules: A-share/ETF T+1 settlement"),
            sessions_until_sellable=1,
        )
    )
    master.add_rule_profile(
        SettlementRule(
            profile_id="SETTLE:ETF-EQUITY-T1",
            effective_from=_ETF_HISTORY_VALID_FROM,
            effective_to=None,
            source=_etf_history_source(
                "SSE/SZSE",
                "Domestic stock ETF units bought on T become sellable on the next open session",
            ),
            sessions_until_sellable=1,
        )
    )
    master.add_rule_profile(
        SettlementRule(
            profile_id="SETTLE:ETF-INTRADAY",
            effective_from=_ETF_HISTORY_VALID_FROM,
            effective_to=None,
            source=_etf_history_source(
                "SSE",
                "2013 SSE bond ETF and gold ETF rules permit same-day sale "
                "of units bought that day",
            ),
            sessions_until_sellable=0,
        )
    )
    price_limit_seeds = (
        ("PLIMIT:A-MAIN-10PCT", Decimal("0.01"), _SEED_VALID_FROM, _source),
        (
            "PLIMIT:ETF-10PCT",
            Decimal("0.001"),
            _ETF_HISTORY_VALID_FROM,
            _etf_history_source,
        ),
    )
    for profile_id, tick, effective_from, source_factory in price_limit_seeds:
        master.add_rule_profile(
            PriceLimitRule(
                profile_id=profile_id,
                effective_from=effective_from,
                effective_to=None,
                source=source_factory(
                    "SSE/SZSE", "Trading rules: +/-10% daily price limit vs previous close"
                ),
                basis=PriceLimitBasis.PREVIOUS_CLOSE,
                limit_percent=Decimal("0.10"),
                tick_size=tick,
            )
        )
    for effective_from, effective_to, limit_percent, reference in (
        (
            _ETF_HISTORY_VALID_FROM,
            date(2020, 8, 23),
            Decimal("0.10"),
            "SZSE fund trading rules: ChiNext ETF price limit was +/-10%",
        ),
        (
            date(2020, 8, 24),
            None,
            Decimal("0.20"),
            "SZSE published list effective 2020-08-24: 159915 price limit is +/-20%",
        ),
    ):
        master.add_rule_profile(
            PriceLimitRule(
                profile_id="PLIMIT:ETF-CHINEXT",
                effective_from=effective_from,
                effective_to=effective_to,
                source=_etf_history_source("SZSE", reference),
                basis=PriceLimitBasis.PREVIOUS_CLOSE,
                limit_percent=limit_percent,
                tick_size=Decimal("0.001"),
            )
        )
    for rule in _seed_market_fee_tax_versions():
        master.add_rule_profile(rule)
    for family in ("FEE:TAX-ETF-EQUITY", "FEE:TAX-ETF-GOLD", "FEE:TAX-ETF-BOND"):
        for rule in _seed_etf_fee_family(family):
            master.add_rule_profile(rule)

    seed_instruments = [
        (
            InstrumentId(exchange=Exchange.XSHG, symbol="600519"),
            "Kweichow Moutai",
            InstrumentType.A_SHARE,
            None,
            date(2001, 8, 27),
            "PLIMIT:A-MAIN-10PCT",
            "FEE:TAX-A-STANDARD",
        ),
        (
            InstrumentId(exchange=Exchange.XSHE, symbol="000001"),
            "Ping An Bank",
            InstrumentType.A_SHARE,
            None,
            date(1991, 4, 3),
            "PLIMIT:A-MAIN-10PCT",
            "FEE:TAX-A-STANDARD",
        ),
        (
            InstrumentId(exchange=Exchange.XSHG, symbol="510300"),
            "Huatai-PineBridge CSI 300 ETF",
            InstrumentType.EXCHANGE_TRADED_FUND,
            FundSubtype.BROAD_BASED_EQUITY,
            date(2012, 5, 28),
            "PLIMIT:ETF-10PCT",
            "FEE:TAX-ETF-EQUITY",
        ),
        (
            InstrumentId(exchange=Exchange.XSHE, symbol="159915"),
            "E Fund ChiNext ETF",
            InstrumentType.EXCHANGE_TRADED_FUND,
            FundSubtype.BROAD_BASED_EQUITY,
            date(2011, 12, 9),
            "PLIMIT:ETF-CHINEXT",
            "FEE:TAX-ETF-EQUITY",
        ),
        (
            InstrumentId(exchange=Exchange.XSHG, symbol="518880"),
            "Huaan Gold ETF",
            InstrumentType.EXCHANGE_TRADED_FUND,
            FundSubtype.GOLD,
            date(2013, 7, 29),
            "PLIMIT:ETF-10PCT",
            "FEE:TAX-ETF-GOLD",
        ),
        (
            InstrumentId(exchange=Exchange.XSHG, symbol="511010"),
            "Guotai SSE 5-Year Treasury Bond ETF",
            InstrumentType.EXCHANGE_TRADED_FUND,
            FundSubtype.BOND,
            date(2013, 3, 25),
            "PLIMIT:ETF-10PCT",
            "FEE:TAX-ETF-BOND",
        ),
    ]
    for record in seed_instruments:
        (
            instrument_id,
            name,
            instrument_type,
            subtype,
            list_date,
            price_limit_family,
            fee_family,
        ) = record
        is_etf = instrument_type is InstrumentType.EXCHANGE_TRADED_FUND
        settlement_family = (
            "SETTLE:ETF-INTRADAY"
            if subtype in (FundSubtype.GOLD, FundSubtype.BOND)
            else "SETTLE:ETF-EQUITY-T1"
        )
        master.register_instrument(
            Instrument(
                instrument_id=instrument_id,
                display_name=name,
                currency="CNY",
                instrument_type=instrument_type,
                fund_subtype=subtype,
                list_date=list_date,
                delist_date=None,
                trading_calendar_id=instrument_id.exchange.value,
                lot_rule_profile_id=(
                    "LOT:ETF-STANDARD" if is_etf else "LOT:CN-STANDARD"
                ),
                settlement_rule_profile_id=(
                    settlement_family if is_etf else "SETTLE:T1"
                ),
                price_limit_rule_profile_id=price_limit_family,
                market_fee_tax_profile_id=fee_family,
                reference_data_version=(
                    _ETF_HISTORY_REFERENCE_VERSION
                    if is_etf
                    else _SEED_REFERENCE_VERSION
                ),
                valid_from=(
                    _ETF_HISTORY_VALID_FROM if is_etf else _SEED_VALID_FROM
                ),
                valid_to=None,
            )
        )
    return master
