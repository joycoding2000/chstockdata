"""R2.1 execution-only regressions with recorded Step1 source payloads."""

import copy
import json
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
import pytest
from systematic_investing.adapters.chstockdata.provider import (
    ChStockDataProvider,
    LibraryChStockDataClient,
)
from systematic_investing.domain.identifiers import InstrumentId
from systematic_investing.domain.market import (
    Availability,
    AvailabilityBasis,
    TradabilityStatus,
    TradabilityStatusKind,
)
from systematic_investing.data.quality import CanonicalDataset
from systematic_investing.data.snapshots import (
    SnapshotWriter,
    SnapshotReader,
    SnapshotIntegrityError,
)

W = Path(__file__).resolve().parents[1] / "fixtures/chstockdata/historical_opening"
S0, S1 = date(2026, 9, 10), date(2026, 9, 11)
I = InstrumentId.parse("XSHG:510300")


def payload(symbol="510300", day="2026-09-11"):
    return json.loads((W / f"{symbol}-{day}.json").read_text(encoding="utf-8"))["data"]


def seal(data):
    data = copy.deepcopy(data)
    data.pop("evidence_hash", None)
    data["evidence_hash"] = sha256(
        json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    return data


def api():
    from systematic_investing.domain import historical_opening as h

    return h


def mapped(data):
    from systematic_investing.data.ports import HistoricalOpeningRequest

    # Uses real FetchResult and library boundary, replaying the full certified response.
    from chstockdata.fetch_result import FetchResult, FetchMetadata

    result = FetchResult(
        data=data,
        metadata=FetchMetadata(
            capability="historical_opening_evidence",
            final_provider="recorded-step1",
            providers_used=["recorded-step1"],
            retrieved_at=data["retrieved_at"],
            outcome_status="success",
        ),
    )
    lib = SimpleNamespace(
        __version__="0.3.0", fetch_historical_opening_evidence=lambda *a, **kw: result
    )
    provider = ChStockDataProvider(
        client=LibraryChStockDataClient(library=lib),
        clock=lambda: datetime(2026, 10, 12, tzinfo=UTC),
    )
    response = provider.fetch_historical_opening_evidence(
        HistoricalOpeningRequest(
            (
                InstrumentId.parse(
                    ("XSHG:" if data["market"] == "SSE" else "XSHE:") + data["instrument"]
                ),
            ),
            date.fromisoformat(data["session_date"]),
        )
    )
    assert response.is_success
    return response.records[0]


def gap(instrument=I, day=S1, reason=None, status=TradabilityStatusKind.UNKNOWN):
    return TradabilityStatus(
        instrument,
        day,
        status,
        reason or api().HISTORICAL_SUSPENSION_GAP,
        Availability(None, datetime(2026, 10, 12, tzinfo=UTC), AvailabilityBasis.UNKNOWN),
        "vendor:historical_suspension_unavailable",
    )


def run(
    facts, statuses, make_engine, bar_factory, target_contribution, predetermined_targets, **kw
):
    from systematic_investing.backtest.engine import EngineClock

    source = predetermined_targets({S0: (target_contribution(I, "0.10"),)})
    tz = EngineClock.shanghai().timezone
    bars = tuple(
        bar_factory(
            I,
            s,
            open="4.00",
            close="4.00",
            pre_close="4.00",
            available_at=datetime.combine(s, datetime.min.time(), tzinfo=tz)
            + timedelta(hours=15, minutes=5),
        )
        for s in (S0, S1)
    )
    engine = make_engine(
        clock=EngineClock.shanghai(),
        bars=bars,
        tradability=statuses,
        target_source=source,
        historical_opening_evidence=facts,
        execution_eligibility_mode=kw.pop(
            "execution_eligibility_mode", api().ExecutionEligibilityMode.HISTORICAL_OPENING_R21
        ),
        **kw,
    )
    return engine.run(start_session=S0, end_session=S1), source


def test_full_payload_adapter_hash_and_unknown_pit():
    fact = mapped(payload())
    assert fact.payload == payload()
    assert fact.availability.information_known_at(datetime(2026, 9, 11, 1, 15, tzinfo=UTC)) is None
    bad = payload()
    bad["tdx_activity"]["reason"] = "tampered"
    with pytest.raises(ValueError):
        api().HistoricalOpeningEvidence.from_payload(bad)


def test_execution_fact_only_changes_t_plus_one(
    make_engine, bar_factory, target_contribution, predetermined_targets
):
    inputs = (make_engine, bar_factory, target_contribution, predetermined_targets)
    original = payload()
    changed = copy.deepcopy(original)
    changed["opening_status"] = "UNKNOWN"
    changed["reason"] = "unknown_activity"
    a, sa = run((mapped(original),), (gap(),), *inputs)
    b, sb = run((mapped(seal(changed)),), (gap(),), *inputs)
    assert a.session(S0).plans == b.session(S0).plans
    assert a.session(S0).target == b.session(S0).target
    assert sa.contexts[0] == sb.contexts[0]
    assert all(not hasattr(c, "historical_opening_evidence") for c in sa.contexts)
    assert a.session(S1).activation.fills
    assert not b.session(S1).activation.fills


@pytest.mark.parametrize(
    "status,reason",
    [
        (TradabilityStatusKind.UNKNOWN, "generic_missing"),
        (TradabilityStatusKind.NOT_LISTED, "not_listed"),
        (TradabilityStatusKind.DELISTED, "delisted"),
        (TradabilityStatusKind.BUY_BLOCKED_UPPER_LIMIT, "side_block"),
        (TradabilityStatusKind.SUSPENDED, "suspended"),
    ],
)
def test_positive_does_not_override_other_unknown_or_blocks(
    status, reason, make_engine, bar_factory, target_contribution, predetermined_targets
):
    result, _ = run(
        (mapped(payload()),),
        (gap(status=status, reason=reason),),
        make_engine,
        bar_factory,
        target_contribution,
        predetermined_targets,
    )
    assert not result.fills


def test_positive_does_not_override_absence(
    make_engine, bar_factory, target_contribution, predetermined_targets
):
    result, _ = run(
        (mapped(payload()),),
        (),
        make_engine,
        bar_factory,
        target_contribution,
        predetermined_targets,
    )
    assert not result.fills


def test_new_clock_rejects_utc_default(make_engine):
    with pytest.raises(ValueError, match="Shanghai"):
        make_engine(
            execution_eligibility_mode=api().ExecutionEligibilityMode.HISTORICAL_OPENING_R21,
            historical_opening_evidence=(mapped(payload()),),
        )


@pytest.mark.parametrize("target", ["2026-09-11T09:30:00", "2026-09-11T09:30:00+00:00"])
def test_bad_target_rejected(target):
    data = payload()
    data["target_execution_at"] = target
    with pytest.raises(ValueError):
        api().HistoricalOpeningEvidence.from_payload(seal(data))


def test_utc_equivalent_target_accepted():
    data = payload()
    data["target_execution_at"] = "2026-09-11T01:30:00+00:00"
    assert api().HistoricalOpeningEvidence.from_payload(seal(data)).target_execution_at == datetime(
        2026, 9, 11, 1, 30, tzinfo=UTC
    )


def test_snapshot_full_partition_roundtrip_and_v2_compat(tmp_path, bar_factory):
    h = api()
    fact = mapped(payload())
    base = CanonicalDataset((bar_factory(I, S1, open="4", close="4"),), (), (), (), ())
    current = replace(base, historical_opening_evidence=(fact,))
    writer = SnapshotWriter("chstockdata", "0.3.0", "r21")
    args = dict(
        created_at=datetime(2026, 10, 12, tzinfo=UTC),
        knowledge_cutoff=datetime(2026, 9, 10, tzinfo=UTC),
        retrieved_at=datetime(2026, 10, 12, tzinfo=UTC),
    )
    old = writer.persist(base, snapshot_dir=tmp_path / "old", **args)
    assert old.snapshot_schema_version == "v2"
    manifest = writer.persist(
        current,
        snapshot_dir=tmp_path / "new",
        execution_eligibility_mode=h.ExecutionEligibilityMode.HISTORICAL_OPENING_R21,
        **args,
    )
    loaded, replayed = SnapshotReader().load(
        tmp_path / "new",
        execution_eligibility_mode=h.ExecutionEligibilityMode.HISTORICAL_OPENING_R21,
    )
    assert loaded == manifest and replayed == current
    assert manifest.snapshot_schema_version == "v3-historical-opening"
    assert current.content_digest() != base.content_digest()
    with pytest.raises(SnapshotIntegrityError):
        SnapshotReader().load(
            tmp_path / "old",
            execution_eligibility_mode=h.ExecutionEligibilityMode.HISTORICAL_OPENING_R21,
        )
    part = tmp_path / "new/artifacts/historical_opening_evidence.jsonl"
    part.write_text(
        part.read_text(encoding="utf-8").replace("certified_positive_0930_activity", "tampered"),
        encoding="utf-8",
    )
    with pytest.raises(SnapshotIntegrityError):
        SnapshotReader().load(tmp_path / "new")


def test_old_availability_does_not_invent_exchange_rule():
    result = ChStockDataProvider._tradability_availability(
        payload={}, session_date=S1, retrieved_at=datetime(2026, 10, 12, tzinfo=UTC)
    )
    assert result.information_available_at is None
    assert result.availability_basis is AvailabilityBasis.UNKNOWN


@pytest.mark.parametrize(
    "field,value",
    [
        ("information_available_at", "2026-09-11T10:30:00+08:00"),
        ("retrieved_at", "2026-10-12T08:00:00+00:00"),
    ],
)
def test_late_execution_information_never_changes_t_decision(
    field, value, make_engine, bar_factory, target_contribution, predetermined_targets
):
    data = payload()
    data[field] = value
    if field == "information_available_at":
        data["information_basis"] = "OBSERVED"
    args = (make_engine, bar_factory, target_contribution, predetermined_targets)
    a, sa = run((mapped(payload()),), (gap(),), *args)
    b, sb = run((mapped(seal(data)),), (gap(),), *args)
    assert a.session(S0) == b.session(S0)
    assert sa.contexts[0] == sb.contexts[0]
    assert a.fills == b.fills


def test_qualified_new_ledger_matches_legacy_and_volume_is_not_quota(
    make_engine, bar_factory, target_contribution, predetermined_targets
):
    args = (make_engine, bar_factory, target_contribution, predetermined_targets)
    tz = api().SHANGHAI
    known = TradabilityStatus(
        I,
        S1,
        TradabilityStatusKind.TRADABLE,
        None,
        Availability(
            datetime(2026, 9, 11, 9, 0, tzinfo=tz),
            datetime(2026, 9, 11, 9, 0, tzinfo=tz),
            AvailabilityBasis.OBSERVED,
        ),
        "qualified-baseline",
    )
    baseline, _ = run(
        (), (known,), *args, execution_eligibility_mode=api().ExecutionEligibilityMode.LEGACY
    )
    new, _ = run((mapped(payload()),), (gap(),), *args)
    data = payload()
    data["tdx_activity"]["opening_volume_lots"] = 1
    altered, _ = run((mapped(seal(data)),), (gap(),), *args)
    assert baseline.fills == new.fills == altered.fills
    assert baseline.cash_entries == new.cash_entries == altered.cash_entries
    assert baseline.holdings_entries == new.holdings_entries
    assert new.fills[0].quantity == new.session(S0).plans[0].order_quantity
    assert (
        new.fills[0].fill_price
        != api()
        .HistoricalOpeningEvidence.from_payload(payload())
        .payload["tdx_activity"]["last_opening_price"]
    )


def test_missing_rules_still_rejects(
    make_engine, bar_factory, target_contribution, predetermined_targets
):
    from systematic_investing.instrument_master.repository import InstrumentMaster

    result, _ = run(
        (mapped(payload()),),
        (gap(),),
        make_engine,
        bar_factory,
        target_contribution,
        predetermined_targets,
        master=InstrumentMaster(),
    )
    assert not result.fills


@pytest.mark.parametrize("symbol", ["513100", "159509"])
def test_real_halt_controls_never_fill_or_retry_after_resume(
    symbol, make_engine, bar_factory, target_contribution, predetermined_targets
):
    from systematic_investing.backtest.engine import EngineClock
    from systematic_investing.domain.market import MarketCalendar, TradingSession

    instrument = InstrumentId.parse(("XSHG:" if symbol.startswith("5") else "XSHE:") + symbol)
    # Registration reuses approved ETF rules; event eligibility is the subject.
    from systematic_investing.instrument_master.repository import default_m0_master

    master = default_m0_master()
    reference = master.resolve_instrument(I, S1)
    master.register_instrument(
        replace(reference, instrument_id=instrument, display_name="halt-control")
    )
    source = predetermined_targets({S0: (target_contribution(instrument, "0.10"),)})
    tz = api().SHANGHAI
    bars = tuple(
        bar_factory(
            instrument,
            s,
            open="4",
            close="4",
            pre_close="4",
            available_at=datetime(s.year, s.month, s.day, 15, 5, tzinfo=tz),
        )
        for s in (S0, S1)
    )
    exchange = instrument.exchange.value
    calendar = MarketCalendar(
        exchange,
        "r21-control",
        tuple(TradingSession(exchange, s, True, None, "r21-control") for s in (S0, S1)),
    )
    result = make_engine(
        calendar=calendar,
        master=master,
        clock=EngineClock.shanghai(),
        bars=bars,
        tradability=(gap(instrument),),
        historical_opening_evidence=(mapped(payload(symbol)),),
        execution_eligibility_mode=api().ExecutionEligibilityMode.HISTORICAL_OPENING_R21,
        target_source=source,
    ).run(start_session=S0, end_session=S1)
    assert not result.fills
    assert len(result.session(S1).activation.rejections) == 1
    assert result.session(S1).activation.rejections[0].code.value == "SUSPENDED"


def test_late_and_unknown_strategy_pit_still_blocks(bar_factory, m0_master):
    from systematic_investing.data.quality import (
        DataQualityGate,
        DatasetPolicy,
        UnknownHandling,
        GateAction,
    )

    # Execution facts do not participate in required strategy PIT checks.
    base = CanonicalDataset(
        (bar_factory(I, S1, open="4", close="4"),), (), (gap(),), (), (), (mapped(payload()),)
    )
    gate = DataQualityGate(m0_master, DatasetPolicy())
    from systematic_investing.domain.runs import RunPurpose

    result = gate.evaluate(
        base,
        purpose=RunPurpose.DECISION,
        intended_decision_session=S1,
        information_cutoff=datetime(2026, 9, 11, 8, tzinfo=UTC),
        evaluated_at=datetime(2026, 10, 12, tzinfo=UTC),
    )
    assert result.status.value != "PASS"


def test_unsortable_official_boundary_inside_opening_window_refuses_positive():
    data = payload()
    event = payload("000002", "2015-12-18")["official_events"][0]
    event.update(instrument="510300", market="SSE", effective_start="2026-09-11T09:30:30+08:00")
    data["official_events"] = [event]
    with pytest.raises(ValueError, match="boundary"):
        api().HistoricalOpeningEvidence.from_payload(seal(data))


def test_reader_checks_all_artifact_hashes_before_any_parse(tmp_path, bar_factory, monkeypatch):
    from systematic_investing.data import snapshots

    base = CanonicalDataset(
        (bar_factory(I, S1, open="4", close="4"),), (), (), (), (), (mapped(payload()),)
    )
    now = datetime(2026, 10, 12, tzinfo=UTC)
    writer = SnapshotWriter("recorded", "0.4.2", "r21")
    writer.persist(
        base,
        snapshot_dir=tmp_path / "snapshot",
        created_at=now,
        knowledge_cutoff=now,
        retrieved_at=now,
    )
    seen = []
    to_dict, reader = snapshots._RECORD_SERIALIZERS["historical_opening_evidence"]
    monkeypatch.setitem(
        snapshots._RECORD_SERIALIZERS,
        "historical_opening_evidence",
        (to_dict, lambda data: seen.append(data) or reader(data)),
    )
    (tmp_path / "snapshot/artifacts/trading_session.jsonl").write_text("corrupt", encoding="utf-8")
    with pytest.raises(SnapshotIntegrityError):
        SnapshotReader().load(tmp_path / "snapshot")
    assert seen == []


def test_real_afternoon_halt_does_not_retroactively_cancel_open(
    make_engine, bar_factory, target_contribution, predetermined_targets, account_fees
):
    from systematic_investing.backtest.engine import EngineClock
    from systematic_investing.domain.market import MarketCalendar, TradingSession
    from systematic_investing.instrument_master.repository import (
        InstrumentMaster,
        default_m0_master,
    )
    from decimal import Decimal

    instrument = InstrumentId.parse("XSHE:000002")
    previous, session = date(2015, 12, 17), date(2015, 12, 18)
    # Synthetic approved test rules isolate execution arithmetic; this is not a historical rule qualification.
    seed = default_m0_master()
    master = InstrumentMaster()
    reference = seed.resolve_instrument(InstrumentId.parse("XSHE:000001"), S1)
    master.register_instrument(
        replace(
            reference,
            instrument_id=instrument,
            list_date=date(2000, 1, 1),
            valid_from=date(2000, 1, 1),
            display_name="afternoon-halt-control",
        )
    )
    rules = seed.resolve_rules(InstrumentId.parse("XSHE:000001"), S1)
    for profile in (rules.lot, rules.settlement, rules.price_limit, rules.market_fee_tax):
        master.add_rule_profile(replace(profile, effective_from=date(2000, 1, 1)))
    fees = replace(
        account_fees,
        broker_profiles=tuple(
            replace(profile, effective_from=date(2000, 1, 1))
            for profile in account_fees.broker_profiles
        ),
    )
    calendar = MarketCalendar(
        "XSHE",
        "afternoon",
        tuple(
            TradingSession("XSHE", day, True, None, "afternoon")
            for day in (previous, session, date(2015, 12, 21))
        ),
    )
    bars = tuple(
        bar_factory(
            instrument,
            day,
            open="20",
            close="20",
            pre_close="20",
            available_at=datetime(day.year, day.month, day.day, 15, 5, tzinfo=api().SHANGHAI),
        )
        for day in (previous, session)
    )
    source = predetermined_targets({previous: (target_contribution(instrument, "0.10"),)})
    result = make_engine(
        calendar=calendar,
        master=master,
        account_fees=fees,
        clock=EngineClock.shanghai(),
        bars=bars,
        tradability=(gap(instrument, session),),
        historical_opening_evidence=(mapped(payload("000002", "2015-12-18")),),
        execution_eligibility_mode=api().ExecutionEligibilityMode.HISTORICAL_OPENING_R21,
        target_source=source,
    ).run(start_session=previous, end_session=session)
    assert len(result.fills) == 1
    assert result.fills[0].session_date == session
    assert result.fills[0].reference_open == Decimal("20")


@pytest.mark.parametrize("listing", ["not_listed", "delisted"])
def test_master_listing_dates_veto_positive_opening_gap(
    listing, make_engine, bar_factory, target_contribution, predetermined_targets
):
    from systematic_investing.instrument_master.repository import (
        InstrumentMaster,
        default_m0_master,
    )

    seed = default_m0_master()
    master = InstrumentMaster()
    reference = seed.resolve_instrument(I, S1)
    reference = (
        replace(reference, list_date=date(2026, 9, 12))
        if listing == "not_listed"
        else replace(reference, delist_date=S0)
    )
    master.register_instrument(reference)
    rules = seed.resolve_rules(I, S1)
    for profile in (rules.lot, rules.settlement, rules.price_limit, rules.market_fee_tax):
        master.add_rule_profile(profile)
    result, _ = run(
        (mapped(payload()),),
        (gap(),),
        make_engine,
        bar_factory,
        target_contribution,
        predetermined_targets,
        master=master,
    )
    assert not result.fills
