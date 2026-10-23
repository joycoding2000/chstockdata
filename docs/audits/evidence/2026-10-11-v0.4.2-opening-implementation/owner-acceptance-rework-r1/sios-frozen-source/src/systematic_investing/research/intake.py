"""Validation of already-materialized canonical snapshots for Research runs.

``intake`` is deliberately narrow: it never fetches provider or raw data and
never writes snapshots. It verifies that an owner-materialized canonical M0
snapshot physically covers the candidate's warm-up window and stops exactly
at the Basic end; any row after the Basic end fails closed, because a Basic
run may never see out-of-sample rows.

For Stock intents the snapshot carries the owner-materialized cohort union,
so intake additionally re-derives the annual PIT formation facts from the
canonical data alone (bar-presence listing age, trailing amount windows,
formation-session tradability) and re-forms the schedule with the same
frozen :func:`form_annual_schedule` code the owner used. Every Basic-window
calendar year must have a within-policy cohort or the intake fails closed
with a typed year-level reason. Stock runs also require the owner-attested
instrument reference mounted beside the snapshot: the seed M0 Instrument
Master covers only two representative A-shares, so the materializer attests
the classification and standard rule-profile coverage of every materialized
stock, and intake refuses any bar instrument the reference does not cover.
"""

import json
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from systematic_investing.data.quality import CanonicalDataset
from systematic_investing.data.snapshots import DataSnapshotManifest
from systematic_investing.domain.identifiers import InstrumentId, require_session_date
from systematic_investing.domain.instruments import Instrument, InstrumentType
from systematic_investing.domain.market import (
    DailyBar,
    TradabilityStatus,
    TradabilityStatusKind,
)
from systematic_investing.instrument_master.repository import (
    InstrumentMaster,
    default_m0_master,
)
from systematic_investing.research.artifacts import digest_of_bytes
from systematic_investing.research.contracts import (
    M1_APPROVED_ETF_SYMBOLS,
    CandidateIntent,
)
from systematic_investing.research.universe import (
    AnnualCohortFailedError,
    AnnualUniversePolicy,
    AnnualUniverseSchedule,
    NoCohortFormedError,
    StockFormationFact,
    StockIdentityStatus,
    TrailingAmount,
    form_annual_schedule,
)

REASON_BASIC_END_EXCEEDED: str = "BASIC_END_EXCEEDED"
REASON_BASIC_END_UNCOVERED: str = "BASIC_END_UNCOVERED"
REASON_WARMUP_COVERAGE_SHORT: str = "WARMUP_COVERAGE_SHORT"
REASON_INSTRUMENT_OUTSIDE_ASSET_CLASS: str = "INSTRUMENT_OUTSIDE_ASSET_CLASS"
REASON_INSTRUMENT_UNCOVERED: str = "INSTRUMENT_UNCOVERED"
REASON_INSTRUMENT_ENDS_EARLY: str = "INSTRUMENT_ENDS_BEFORE_BASIC_END"
REASON_SNAPSHOT_QUALITY_NOT_PASS: str = "SNAPSHOT_QUALITY_NOT_PASS"
REASON_EMPTY_SNAPSHOT: str = "EMPTY_SNAPSHOT"
REASON_STOCK_MASTER_REQUIRED: str = "STOCK_MASTER_REQUIRED"
REASON_STOCK_ANNUAL_COHORT_FAILED: str = "STOCK_ANNUAL_COHORT_FAILED"
REASON_STOCK_ANNUAL_COHORT_MISSING: str = "STOCK_ANNUAL_COHORT_MISSING"
REASON_STOCK_REFERENCE_MISSING: str = "STOCK_INSTRUMENT_REFERENCE_MISSING"
REASON_STOCK_REFERENCE_INVALID: str = "STOCK_INSTRUMENT_REFERENCE_INVALID"

STOCK_REFERENCE_SCHEMA_VERSION: str = "research-stock-reference-1"
_FAR_FUTURE: date = date(2099, 12, 31)


class IntakeError(Exception):
    """Base class for Research snapshot intake errors."""


class BasicSnapshotBoundaryError(IntakeError):
    """Raised when a physical Basic snapshot violates its declared boundary."""


@dataclass(frozen=True)
class BasicSnapshotReceipt:
    """What the intake verified about one Basic snapshot."""

    snapshot_id: str
    dataset_digest: str
    min_session: date
    max_session: date
    instrument_ids: tuple[InstrumentId, ...]
    quality_status: str | None
    annual_schedule: AnnualUniverseSchedule | None = None


def validate_basic_snapshot(
    manifest: DataSnapshotManifest,
    dataset: CanonicalDataset,
    intent: "CandidateIntent",
    *,
    master: InstrumentMaster | None = None,
) -> BasicSnapshotReceipt:
    """Validate one materialized canonical Basic snapshot for an intent.

    Checks, in fail-closed order:

    1. the snapshot carries at least one bar;
    2. no row exists after ``intent.basic_end`` (physical Basic boundary);
    3. the bundle's maximum session equals ``intent.basic_end``;
    4. the bundle starts no later than ``intent.warm_up_start`` (warm-up);
    5. bar instruments stay inside the M0-qualified asset-class authority
       (for ETF, the frozen M1 first-batch set; for STOCK, the run master
       attested by the owner's instrument reference must classify every bar
       instrument as an A-share; the asset-class snapshot is shared, so it
       may cover more instruments than one intent's universe);
    6. for ETF, every intent-universe instrument has bars and its own
       maximum session equals ``intent.basic_end`` — per instrument, never
       only by the bundle's global maximum; for STOCK, the annual PIT
       schedule is re-derived from canonical facts and every Basic-window
       calendar year must have a within-policy cohort;
    7. the recorded quality status, when present, is ``PASS``.
    """
    if not dataset.daily_bars:
        raise BasicSnapshotBoundaryError(
            f"{REASON_EMPTY_SNAPSHOT}: the Basic snapshot contains no daily bars"
        )
    max_session = max(bar.session_date for bar in dataset.daily_bars)
    min_session = min(bar.session_date for bar in dataset.daily_bars)
    if max_session > intent.basic_end:
        raise BasicSnapshotBoundaryError(
            f"{REASON_BASIC_END_EXCEEDED}: the Basic snapshot contains rows "
            f"after the Basic end {intent.basic_end.isoformat()} "
            f"(latest row {max_session.isoformat()}); a Basic run may never "
            "see out-of-sample rows"
        )
    if max_session < intent.basic_end:
        raise BasicSnapshotBoundaryError(
            f"{REASON_BASIC_END_UNCOVERED}: the Basic snapshot ends at "
            f"{max_session.isoformat()}, before the Basic end "
            f"{intent.basic_end.isoformat()}"
        )
    fact_dates = (
        *(session.session_date for session in dataset.sessions),
        *(record.session_date for record in dataset.tradability),
        *(action.ex_date for action in dataset.corporate_actions),
    )
    future_fact_dates = [fact_date for fact_date in fact_dates if fact_date > intent.basic_end]
    if future_fact_dates:
        raise BasicSnapshotBoundaryError(
            f"{REASON_BASIC_END_EXCEEDED}: canonical facts extend past the "
            f"Basic end {intent.basic_end.isoformat()} (latest fact "
            f"{max(future_fact_dates).isoformat()})"
        )
    if min_session > intent.warm_up_start:
        raise BasicSnapshotBoundaryError(
            f"{REASON_WARMUP_COVERAGE_SHORT}: the Basic snapshot starts at "
            f"{min_session.isoformat()}, after the warm-up start "
            f"{intent.warm_up_start.isoformat()}"
        )
    bar_instruments = {bar.instrument_id for bar in dataset.daily_bars}
    annual_schedule: AnnualUniverseSchedule | None = None
    if intent.asset_class.value == "STOCK":
        if master is None:
            raise BasicSnapshotBoundaryError(
                f"{REASON_STOCK_MASTER_REQUIRED}: a STOCK snapshot intake "
                "requires the run master built from the owner-attested "
                "instrument reference"
            )
        _require_stock_master_authority(bar_instruments, intent, master)
        annual_schedule = _require_stock_annual_schedule(
            dataset, intent
        )
    else:
        approved = {InstrumentId.parse(item) for item in M1_APPROVED_ETF_SYMBOLS}
        outside_asset_class = set(bar_instruments) - approved
        if outside_asset_class:
            raise BasicSnapshotBoundaryError(
                f"{REASON_INSTRUMENT_OUTSIDE_ASSET_CLASS}: snapshot instruments "
                "outside the M0-qualified asset-class authority: "
                + ", ".join(str(item) for item in sorted(outside_asset_class))
            )
        universe = set(intent.universe_policy.instrument_ids)
        uncovered = sorted(universe - bar_instruments)
        if uncovered:
            raise BasicSnapshotBoundaryError(
                f"{REASON_INSTRUMENT_UNCOVERED}: universe instruments without "
                "bars: " + ", ".join(str(item) for item in uncovered)
            )
        last_session_by_instrument: dict[InstrumentId, date] = {}
        for bar in dataset.daily_bars:
            current = last_session_by_instrument.get(bar.instrument_id)
            if current is None or bar.session_date > current:
                last_session_by_instrument[bar.instrument_id] = bar.session_date
        truncated = sorted(
            instrument_id
            for instrument_id in universe
            if last_session_by_instrument.get(instrument_id) != intent.basic_end
        )
        if truncated:
            raise BasicSnapshotBoundaryError(
                f"{REASON_INSTRUMENT_ENDS_EARLY}: universe instruments whose own "
                f"bars end before the Basic end "
                f"{intent.basic_end.isoformat()}: "
                + ", ".join(
                    f"{instrument_id}@{last_session_by_instrument.get(instrument_id)}"
                    for instrument_id in truncated
                )
            )
    quality = manifest.quality_status
    if quality != "PASS":
        raise BasicSnapshotBoundaryError(
            f"{REASON_SNAPSHOT_QUALITY_NOT_PASS}: snapshot quality status is "
            f"{quality!r}"
        )
    require_session_date(max_session)
    snapshot_id = manifest.snapshot_id
    if snapshot_id is None:
        raise BasicSnapshotBoundaryError(
            "the snapshot manifest has no computed snapshot id"
        )
    return BasicSnapshotReceipt(
        snapshot_id=snapshot_id,
        dataset_digest=dataset.content_digest(),
        min_session=min_session,
        max_session=max_session,
        instrument_ids=tuple(sorted(bar_instruments)),
        quality_status=manifest.quality_status,
        annual_schedule=annual_schedule,
    )


def _require_stock_master_authority(
    bar_instruments: set[InstrumentId],
    intent: "CandidateIntent",
    master: InstrumentMaster,
) -> None:
    """Every bar instrument must be an A-share under the run master."""
    outside: list[str] = []
    for instrument_id in sorted(bar_instruments):
        try:
            instrument = master.resolve_instrument(instrument_id, intent.basic_end)
        except Exception as error:
            raise BasicSnapshotBoundaryError(
                f"{REASON_INSTRUMENT_OUTSIDE_ASSET_CLASS}: {instrument_id} is "
                f"not covered by the attested run master ({error})"
            ) from error
        if instrument.instrument_type is not InstrumentType.A_SHARE:
            outside.append(str(instrument_id))
    if outside:
        raise BasicSnapshotBoundaryError(
            f"{REASON_INSTRUMENT_OUTSIDE_ASSET_CLASS}: snapshot instruments "
            "outside the attested main-board A-share authority: "
            + ", ".join(sorted(outside))
        )


def _require_stock_annual_schedule(
    dataset: CanonicalDataset,
    intent: "CandidateIntent",
) -> AnnualUniverseSchedule:
    """Re-form the annual PIT schedule and enforce every Basic-window year."""
    policy = AnnualUniversePolicy.standard()
    schedule = form_stock_annual_schedule(dataset, policy=policy)
    for year in range(intent.basic_start.year, intent.basic_end.year + 1):
        try:
            view = schedule.view_for(date(year, 1, 15))
        except AnnualCohortFailedError as error:
            raise BasicSnapshotBoundaryError(
                f"{REASON_STOCK_ANNUAL_COHORT_FAILED}: {error}"
            ) from error
        except NoCohortFormedError as error:
            raise BasicSnapshotBoundaryError(
                f"{REASON_STOCK_ANNUAL_COHORT_MISSING}: {error}"
            ) from error
        if not (
            policy.minimum_cohort_size
            <= len(view.instrument_ids)
            <= policy.maximum_cohort_size
        ):
            raise BasicSnapshotBoundaryError(
                f"{REASON_STOCK_ANNUAL_COHORT_FAILED}: calendar year {year} "
                f"cohort size {len(view.instrument_ids)} is outside the "
                f"policy range "
                f"[{policy.minimum_cohort_size}, {policy.maximum_cohort_size}]"
            )
    return schedule


def _open_sessions(dataset: CanonicalDataset) -> tuple[date, ...]:
    return tuple(
        sorted(
            session.session_date
            for session in dataset.sessions
            if session.is_open
        )
    )


def stock_formation_cutoffs(
    dataset: CanonicalDataset,
    *,
    policy: AnnualUniversePolicy | None = None,
) -> tuple[date, ...]:
    """The year-end formation cutoffs the snapshot can honestly support.

    A cutoff is the last open session of its calendar year and is admitted
    only when the snapshot reaches December of that year, so the cutoff is
    the year's real year-end session and never a mid-year truncation. Years
    with fewer open in-snapshot sessions than the policy listing threshold
    are skipped entirely: the listed-sessions precondition is structurally
    unmeasurable there, so the year is pre-formation rather than failed.
    """
    resolved_policy = policy or AnnualUniversePolicy.standard()
    open_sessions = _open_sessions(dataset)
    sessions_through: dict[date, int] = {
        session_date: index
        for index, session_date in enumerate(open_sessions, start=1)
    }
    cutoffs: list[date] = []
    for session_date in open_sessions:
        year_last = max(
            candidate
            for candidate in open_sessions
            if candidate.year == session_date.year
        )
        if session_date != year_last or session_date.month != 12:
            continue
        if sessions_through[session_date] < resolved_policy.minimum_listing_sessions:
            continue
        cutoffs.append(session_date)
    return tuple(sorted(set(cutoffs)))


def derive_stock_formation_facts(
    dataset: CanonicalDataset,
    *,
    policy: AnnualUniversePolicy,
) -> tuple[StockFormationFact, ...]:
    """Derive PIT formation facts from canonical snapshot content alone.

    ``listed_sessions`` counts the instrument's own in-snapshot sessions
    through the cutoff; ``trailing_amounts`` are the known session amounts
    of the trailing window; a missing formation-session tradability record
    is ``UNKNOWN`` and therefore ineligible. Identity status is attested
    ``NORMAL``: the owner materialized only instruments passing the frozen
    identity screens, and PIT ST naming history is unavailable (declared as
    a known limitation of the M1 Stock candidates).
    """
    bars_by_instrument: dict[InstrumentId, list[DailyBar]] = {}
    for bar in dataset.daily_bars:
        bars_by_instrument.setdefault(bar.instrument_id, []).append(bar)
    for records in bars_by_instrument.values():
        records.sort(key=lambda bar: bar.session_date)
    tradability_at: dict[tuple[InstrumentId, date], TradabilityStatus] = {
        (record.instrument_id, record.session_date): record
        for record in dataset.tradability
    }
    facts: list[StockFormationFact] = []
    for cutoff in stock_formation_cutoffs(dataset, policy=policy):
        for instrument_id in sorted(bars_by_instrument):
            through = [
                bar for bar in bars_by_instrument[instrument_id]
                if bar.session_date <= cutoff
            ]
            if not through:
                continue
            window = through[-policy.trailing_amount_sessions :]
            record = tradability_at.get((instrument_id, cutoff))
            status = (
                record.status
                if record is not None
                else TradabilityStatusKind.UNKNOWN
            )
            facts.append(
                StockFormationFact(
                    instrument_id=instrument_id,
                    formation_session=cutoff,
                    listed_sessions=len(through),
                    identity_status=StockIdentityStatus.NORMAL,
                    tradability=status,
                    trailing_amounts=tuple(
                        TrailingAmount(session_date=bar.session_date, amount=bar.amount)
                        for bar in window
                    ),
                )
            )
    return tuple(facts)


def form_stock_annual_schedule(
    dataset: CanonicalDataset,
    *,
    policy: AnnualUniversePolicy | None = None,
) -> AnnualUniverseSchedule:
    """Re-form the annual PIT schedule from the canonical snapshot.

    The same frozen :func:`form_annual_schedule` code the owner used decides
    eligibility, ranking, and tie-breaks, so the Research-side schedule is
    exactly the owner-side schedule for the materialized cohort union.
    """
    resolved_policy = policy or AnnualUniversePolicy.standard()
    return form_annual_schedule(
        derive_stock_formation_facts(dataset, policy=resolved_policy),
        resolved_policy,
    )


@dataclass(frozen=True)
class StockInstrumentReference:
    """One owner-attested stock instrument registration."""

    instrument_id: InstrumentId
    display_name: str
    list_date: date
    lot_rule_profile_id: str
    settlement_rule_profile_id: str
    price_limit_rule_profile_id: str
    market_fee_tax_profile_id: str
    reference_data_version: str
    provenance: str
    valid_from: date
    valid_to: date | None


def load_stock_instrument_reference(
    snapshot_dir: Path,
    *,
    expected_snapshot_id: str | None = None,
) -> tuple[StockInstrumentReference, ...]:
    """Load the owner-attested instrument reference beside a snapshot."""
    path = Path(snapshot_dir) / "instrument-reference.json"
    if not path.exists():
        raise BasicSnapshotBoundaryError(
            f"{REASON_STOCK_REFERENCE_MISSING}: no instrument-reference.json "
            f"beside the snapshot {Path(snapshot_dir)}; the owner "
            "materialization must attest every stock instrument"
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise BasicSnapshotBoundaryError(
            f"{REASON_STOCK_REFERENCE_INVALID}: the instrument reference is "
            f"unreadable: {error}"
        ) from error
    if not isinstance(payload, dict) or (
        payload.get("reference_schema_version") != STOCK_REFERENCE_SCHEMA_VERSION
    ):
        raise BasicSnapshotBoundaryError(
            f"{REASON_STOCK_REFERENCE_INVALID}: unsupported reference schema "
            f"{payload.get('reference_schema_version')!r}"
            if isinstance(payload, dict)
            else f"{REASON_STOCK_REFERENCE_INVALID}: reference payload is not "
            "a mapping"
        )
    instruments = payload.get("instruments")
    if (
        expected_snapshot_id is not None
        and payload.get("snapshot_id") != "sha256:" + expected_snapshot_id
    ):
        raise BasicSnapshotBoundaryError(
            f"{REASON_STOCK_REFERENCE_INVALID}: snapshot_id does not match the snapshot manifest"
        )
    if not isinstance(instruments, list) or not instruments:
        raise BasicSnapshotBoundaryError(
            f"{REASON_STOCK_REFERENCE_INVALID}: the reference names no instruments"
        )
    records: list[StockInstrumentReference] = []
    for entry in instruments:
        try:
            records.append(_stock_reference_record(entry))
        except Exception as error:
            raise BasicSnapshotBoundaryError(
                f"{REASON_STOCK_REFERENCE_INVALID}: {error}"
            ) from error
    return tuple(records)


def stock_instrument_reference_digest(snapshot_dir: Path) -> str:
    path = Path(snapshot_dir) / "instrument-reference.json"
    return digest_of_bytes(path.read_bytes())


_PROFILE_FIELDS: tuple[str, ...] = (
    "lot_rule_profile_id",
    "settlement_rule_profile_id",
    "price_limit_rule_profile_id",
    "market_fee_tax_profile_id",
)


def _stock_reference_record(entry: object) -> StockInstrumentReference:
    if not isinstance(entry, dict):
        raise ValueError("each reference entry must be a mapping")
    for field in (
        "instrument_id",
        "display_name",
        "list_date",
        "reference_data_version",
        "provenance",
        "valid_from",
        *_PROFILE_FIELDS,
    ):
        value = entry.get(field)
        if not isinstance(value, str) or not value:
            raise ValueError(f"reference field {field} must be a non-empty string")
    valid_to = entry.get("valid_to")
    if valid_to is not None and not isinstance(valid_to, str):
        raise ValueError("reference valid_to must be null or an ISO date string")
    return StockInstrumentReference(
        instrument_id=InstrumentId.parse(entry["instrument_id"]),
        display_name=entry["display_name"],
        list_date=date.fromisoformat(entry["list_date"]),
        lot_rule_profile_id=entry["lot_rule_profile_id"],
        settlement_rule_profile_id=entry["settlement_rule_profile_id"],
        price_limit_rule_profile_id=entry["price_limit_rule_profile_id"],
        market_fee_tax_profile_id=entry["market_fee_tax_profile_id"],
        reference_data_version=entry["reference_data_version"],
        provenance=entry["provenance"],
        valid_from=date.fromisoformat(entry["valid_from"]),
        valid_to=(
            date.fromisoformat(valid_to) if isinstance(valid_to, str) else None
        ),
    )


STOCK_WINDOW_PROFILES_FROM: date = date(2017, 1, 1)
STOCK_WINDOW_PROFILES_TO: date = date(2022, 1, 3)
STOCK_WINDOW_FEES_TO: date = date(2022, 4, 28)
STOCK_WINDOW_ATTESTED_ON: date = date(2026, 9, 19)


def _extend_seed_profiles_for_stock_window(master: InstrumentMaster) -> None:
    """Pre-seed effective-dated versions of the standard A-share rule
    families so the seed authority covers the 2017-2022 research window.

    The M0 seed attests the standard main-board A-share rules only from
    2022-01-04 (fees from 2022-04-29), because earlier windows were outside
    M0 scope and failed closed. The rule CONTENT over the earlier window is
    the same exchange/regulator truth the seed versions carry (board lot
    100, T+1 settlement, +/-10% main-board price limits, 0.1% sell-side
    stamp tax), with one documented difference: the CSDC transfer fee was
    0.002% per side before its 2022-04-29 reduction to 0.001%. Sources are
    recorded per version; without these versions every pre-2022 stock
    session fails closed.
    """
    from decimal import Decimal

    from systematic_investing.instrument_master.models import (
        LotRule,
        MarketFeeTaxRule,
        OddLotSellPolicy,
        PriceLimitBasis,
        PriceLimitRule,
        RuleSource,
        SettlementRule,
    )

    exchange_source = RuleSource(
        authority="SSE/SZSE",
        reference=(
            "Board lot 100 / T+1 settlement / +/-10% main-board price limit, "
            "unchanged over the window; same values as the M0 seed profiles "
            "(M1 stock research window extension)"
        ),
        accessed_on=STOCK_WINDOW_ATTESTED_ON,
    )
    master.add_rule_profile(
        LotRule(
            profile_id="LOT:CN-STANDARD",
            effective_from=STOCK_WINDOW_PROFILES_FROM,
            effective_to=STOCK_WINDOW_PROFILES_TO,
            source=exchange_source,
            board_lot=100,
            buy_increment=100,
            odd_lot_sell_policy=OddLotSellPolicy.ALLOWED,
        )
    )
    master.add_rule_profile(
        SettlementRule(
            profile_id="SETTLE:T1",
            effective_from=STOCK_WINDOW_PROFILES_FROM,
            effective_to=STOCK_WINDOW_PROFILES_TO,
            source=exchange_source,
            sessions_until_sellable=1,
        )
    )
    master.add_rule_profile(
        PriceLimitRule(
            profile_id="PLIMIT:A-MAIN-10PCT",
            effective_from=STOCK_WINDOW_PROFILES_FROM,
            effective_to=STOCK_WINDOW_PROFILES_TO,
            source=exchange_source,
            basis=PriceLimitBasis.PREVIOUS_CLOSE,
            limit_percent=Decimal("0.10"),
            tick_size=Decimal("0.01"),
        )
    )
    master.add_rule_profile(
        MarketFeeTaxRule(
            profile_id="FEE:TAX-A-STANDARD",
            effective_from=STOCK_WINDOW_PROFILES_FROM,
            effective_to=STOCK_WINDOW_FEES_TO,
            source=RuleSource(
                authority="MOF/STA + CSDC",
                reference=(
                    "Securities transaction stamp duty 0.1% on sells; CSDC "
                    "transfer fee 0.002% per side before its 2022-04-29 "
                    "reduction to 0.001%"
                ),
                accessed_on=STOCK_WINDOW_ATTESTED_ON,
            ),
            stamp_tax_sell_rate=Decimal("0.001"),
            transfer_fee_rate=Decimal("0.00002"),
        )
    )


def build_stock_run_master(
    records: tuple[StockInstrumentReference, ...],
) -> InstrumentMaster:
    """The run master: the M0 seed scope plus every attested stock record.

    Rule profiles are the seed M0 main-board families, extended with
    effective-dated pre-seed versions over the research window; the
    reference attests classification and coverage, it never invents market
    rules.
    """
    master = default_m0_master()
    _extend_seed_profiles_for_stock_window(master)
    from systematic_investing.instrument_master.models import (
        ConflictingVersionsError,
    )

    for record in records:
        try:
            master.register_instrument(
                Instrument(
                    instrument_id=record.instrument_id,
                    display_name=record.display_name,
                    currency="CNY",
                    instrument_type=InstrumentType.A_SHARE,
                    fund_subtype=None,
                    list_date=record.list_date,
                    delist_date=None,
                    trading_calendar_id=record.instrument_id.exchange.value,
                    lot_rule_profile_id=record.lot_rule_profile_id,
                    settlement_rule_profile_id=record.settlement_rule_profile_id,
                    price_limit_rule_profile_id=record.price_limit_rule_profile_id,
                    market_fee_tax_profile_id=record.market_fee_tax_profile_id,
                    reference_data_version=record.reference_data_version,
                    valid_from=record.valid_from,
                    valid_to=record.valid_to,
                )
            )
        except ConflictingVersionsError:
            # The seed M0 master already attests this instrument (its two
            # representative A-shares) with an overlapping interval. Attest
            # only the pre-seed stretch of the window: the seed authority
            # prevails from its own effective date onward.
            seed = master.resolve_instrument(record.instrument_id, _FAR_FUTURE)
            if seed.valid_from is None or seed.valid_from <= record.valid_from:
                continue
            master.register_instrument(
                Instrument(
                    instrument_id=record.instrument_id,
                    display_name=record.display_name,
                    currency="CNY",
                    instrument_type=InstrumentType.A_SHARE,
                    fund_subtype=None,
                    list_date=record.list_date,
                    delist_date=None,
                    trading_calendar_id=record.instrument_id.exchange.value,
                    lot_rule_profile_id=record.lot_rule_profile_id,
                    settlement_rule_profile_id=record.settlement_rule_profile_id,
                    price_limit_rule_profile_id=record.price_limit_rule_profile_id,
                    market_fee_tax_profile_id=record.market_fee_tax_profile_id,
                    reference_data_version=record.reference_data_version,
                    valid_from=record.valid_from,
                    valid_to=seed.valid_from - timedelta(days=1),
                )
            )
    return master

