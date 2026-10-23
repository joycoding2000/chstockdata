"""M1 Basic snapshot boundary and artifact immutability tests.

A physical Basic snapshot is acceptable only when its maximum session equals
the CandidateIntent Basic end; any later row fails closed. Immutable run
directories, intent copies, and catalog entries can never be overwritten, and
catalog verification detects any content mutation.
"""

import hashlib
import json
from datetime import UTC, date, datetime, time
from decimal import Decimal
from pathlib import Path

import pytest
from test_candidate_intent import _minimal_intent_payload

from systematic_investing.data.quality import CanonicalDataset
from systematic_investing.data.snapshots import SnapshotReader, SnapshotWriter
from systematic_investing.domain.identifiers import InstrumentId
from systematic_investing.domain.market import (
    AdjustmentMode,
    Availability,
    AvailabilityBasis,
    DailyBar,
    TradabilityStatus,
    TradabilityStatusKind,
    TradingSession,
)
from systematic_investing.research.artifacts import (
    ArtifactIntegrityError,
    create_new_directory,
    write_new_json,
)
from systematic_investing.research.catalog import (
    CatalogError,
    append_entry,
    read_entries,
    verify_catalog,
)
from systematic_investing.research.contracts import CandidateIntent
from systematic_investing.research.intake import (
    BasicSnapshotBoundaryError,
    validate_basic_snapshot,
)


def _weekdays_between(start: date, end: date) -> tuple[date, ...]:
    sessions: list[date] = []
    day = start
    while day <= end:
        if day.weekday() < 5:
            sessions.append(day)
        day = date.fromordinal(day.toordinal() + 1)
    return tuple(sessions)


def _dataset(
    instrument_ids: tuple[InstrumentId, ...],
    sessions: tuple[date, ...],
) -> CanonicalDataset:
    bars: list[DailyBar] = []
    for instrument_id in instrument_ids:
        previous_close = None
        for index, session_date in enumerate(sessions):
            close = Decimal("2.00") + Decimal(index) * Decimal("0.01")
            available_at = datetime.combine(session_date, time(15, 5), tzinfo=UTC)
            bars.append(
                DailyBar(
                    schema_version="v1",
                    instrument_id=instrument_id,
                    session_date=session_date,
                    open=close,
                    high=close,
                    low=close,
                    close=close,
                    pre_close=previous_close,
                    volume=Decimal("1000000"),
                    amount=Decimal("4000000"),
                    currency="CNY",
                    volume_unit="shares",
                    amount_unit="CNY",
                    adjustment_mode=AdjustmentMode.RAW,
                    adjustment_factor=None,
                    availability=Availability(
                        information_available_at=available_at,
                        retrieved_at=available_at,
                        availability_basis=AvailabilityBasis.OBSERVED,
                    ),
                    provider_evidence_id="boundary-test-bars",
                )
            )
            previous_close = close
    session_records = tuple(
        TradingSession(
            calendar_id="XSHG",
            session_date=session_date,
            is_open=True,
            note=None,
            snapshot_version="BOUNDARY-CAL-1",
        )
        for session_date in sessions
    )
    return CanonicalDataset(
        daily_bars=tuple(bars),
        sessions=session_records,
        tradability=(),
        corporate_actions=(),
        rule_candidates=(),
    )


def _write_snapshot(dataset: CanonicalDataset, directory: Path) -> Path:
    writer = SnapshotWriter(
        provider_name="boundary-test",
        provider_version="v1",
        adapter_version="boundary-test-1",
    )
    cutoff = datetime.combine(date(2022, 12, 30), time(15, 30), tzinfo=UTC)
    writer.persist(
        dataset,
        snapshot_dir=directory,
        created_at=cutoff,
        knowledge_cutoff=cutoff,
        retrieved_at=cutoff,
    )
    return directory


def _intent_with_window(basic_end: str, basic_start: str, warm_up_start: str):
    payload = _minimal_intent_payload()
    payload["basic_start"] = basic_start
    payload["basic_end"] = basic_end
    payload["warm_up_start"] = warm_up_start
    return CandidateIntent.from_dict(payload)


def _stock_intent_payload() -> dict:
    payload = _minimal_intent_payload()
    payload["intent_id"] = "test-stock-annual-v1"
    payload["lineage_id"] = "test-stock-annual"
    payload["asset_class"] = "STOCK"
    payload["sleeve"] = "SATELLITE"
    payload["strategy_id"] = "stock-relative-strength"
    payload["universe_policy"] = {
        "policy_name": "STOCK_ANNUAL_PIT_TOP50_V1",
        "instrument_ids": [],
    }
    payload["benchmark"] = {
        "kind": "STOCK_ANNUAL_SCHEDULE_EQUAL_WEIGHT",
        "instrument_ids": [],
        "rebalance": "ANNUAL",
    }
    payload["warm_up_start"] = "2018-01-02"
    payload["basic_start"] = "2019-01-02"
    payload["basic_end"] = "2019-01-31"
    payload["oos_start"] = "2019-02-01"
    payload["oos_end"] = "2019-12-31"
    payload["known_limitations"] = (
        "DIVIDEND_TAX_NOT_MODELED: personal-investor dividend tax is not "
        "modeled in M1 stock backtests.",
    )
    return payload


def _stock_intent() -> CandidateIntent:
    return CandidateIntent.from_dict(_stock_intent_payload())


def _stock_symbols(count: int) -> tuple[InstrumentId, ...]:
    return tuple(
        InstrumentId.parse(f"XSHG:6{index:05d}") for index in range(1, count + 1)
    )


def _stock_tradability(
    instrument_ids: tuple[InstrumentId, ...], sessions: tuple[date, ...]
) -> tuple:
    records = []
    for instrument_id in instrument_ids:
        for session_date in sessions:
            available_at = datetime.combine(session_date, time(9, 0), tzinfo=UTC)
            records.append(
                TradabilityStatus(
                    instrument_id=instrument_id,
                    session_date=session_date,
                    status=TradabilityStatusKind.TRADABLE,
                    reason=None,
                    availability=Availability(
                        information_available_at=available_at,
                        retrieved_at=available_at,
                        availability_basis=AvailabilityBasis.OBSERVED,
                    ),
                    provenance="boundary-test-stock",
                )
            )
    return tuple(records)


def _write_stock_reference(
    snapshot_dir: Path, instrument_ids: tuple[InstrumentId, ...]
) -> None:
    payload = {
        "reference_schema_version": "research-stock-reference-1",
        "snapshot_id": "sha256:" + "0" * 64,
        "provenance": "boundary-test owner materialization",
        "instruments": [
            {
                "instrument_id": str(instrument_id),
                "display_name": f"Boundary test A-share {instrument_id.symbol}",
                "list_date": "2018-01-02",
                "lot_rule_profile_id": "LOT:CN-STANDARD",
                "settlement_rule_profile_id": "SETTLE:T1",
                "price_limit_rule_profile_id": "PLIMIT:A-MAIN-10PCT",
                "market_fee_tax_profile_id": "FEE:TAX-A-STANDARD",
                "reference_data_version": "BOUNDARY-STOCK-REF-1",
                "provenance": "boundary-test owner materialization",
                "valid_from": "2018-01-02",
                "valid_to": None,
            }
            for instrument_id in instrument_ids
        ],
    }
    (snapshot_dir / "instrument-reference.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )


def _read(snapshot_dir: Path):
    return SnapshotReader().load(snapshot_dir)


def test_basic_snapshot_at_basic_end_is_accepted(tmp_path: Path) -> None:
    sessions = _weekdays_between(date(2022, 12, 1), date(2022, 12, 30))
    dataset = _dataset((InstrumentId.parse("XSHG:510300"),), sessions)
    snapshot_dir = _write_snapshot(dataset, tmp_path / "snapshot")
    intent = _intent_with_window(
        basic_end="2022-12-30",
        basic_start="2022-12-01",
        warm_up_start="2022-12-01",
    )

    loaded_manifest, loaded_dataset = _read(snapshot_dir)
    receipt = validate_basic_snapshot(loaded_manifest, loaded_dataset, intent)

    assert receipt.max_session == date(2022, 12, 30)
    assert receipt.min_session == date(2022, 12, 1)
    assert receipt.snapshot_id == loaded_manifest.snapshot_id
    assert receipt.dataset_digest == loaded_dataset.content_digest()


def test_basic_snapshot_row_after_basic_end_fails_closed(tmp_path: Path) -> None:
    sessions = (
        *_weekdays_between(date(2022, 12, 1), date(2022, 12, 30)),
        date(2023, 1, 3),
    )
    dataset = _dataset((InstrumentId.parse("XSHG:510300"),), sessions)
    snapshot_dir = _write_snapshot(dataset, tmp_path / "snapshot")
    intent = _intent_with_window(
        basic_end="2022-12-30",
        basic_start="2022-12-01",
        warm_up_start="2022-12-01",
    )

    loaded_manifest, loaded_dataset = _read(snapshot_dir)
    with pytest.raises(BasicSnapshotBoundaryError):
        validate_basic_snapshot(loaded_manifest, loaded_dataset, intent)


def test_basic_snapshot_short_coverage_fails_closed(tmp_path: Path) -> None:
    sessions = _weekdays_between(date(2022, 12, 1), date(2022, 12, 20))
    dataset = _dataset((InstrumentId.parse("XSHG:510300"),), sessions)
    snapshot_dir = _write_snapshot(dataset, tmp_path / "snapshot")
    intent = _intent_with_window(
        basic_end="2022-12-30",
        basic_start="2022-12-01",
        warm_up_start="2022-12-01",
    )

    loaded_manifest, loaded_dataset = _read(snapshot_dir)
    with pytest.raises(BasicSnapshotBoundaryError):
        validate_basic_snapshot(loaded_manifest, loaded_dataset, intent)


def test_basic_snapshot_outside_approved_asset_class_fails(tmp_path: Path) -> None:
    sessions = _weekdays_between(date(2022, 12, 1), date(2022, 12, 30))
    dataset = _dataset(
        (InstrumentId.parse("XSHG:510300"), InstrumentId.parse("XSHG:513100")),
        sessions,
    )
    snapshot_dir = _write_snapshot(dataset, tmp_path / "snapshot")
    intent = _intent_with_window(
        basic_end="2022-12-30",
        basic_start="2022-12-01",
        warm_up_start="2022-12-01",
    )

    loaded_manifest, loaded_dataset = _read(snapshot_dir)
    with pytest.raises(BasicSnapshotBoundaryError):
        validate_basic_snapshot(loaded_manifest, loaded_dataset, intent)


def test_snapshot_covering_more_than_intent_universe_is_accepted(
    tmp_path: Path,
) -> None:
    """The asset-class snapshot is shared by every candidate of the class.

    The absolute-trend intent names one ETF while the materialized snapshot
    covers the frozen M1 first-batch ETF set; intake accepts the superset as
    long as it stays inside the M0-qualified asset-class authority and fully
    covers the intent's own universe.
    """
    sessions = _weekdays_between(date(2022, 12, 1), date(2022, 12, 30))
    dataset = _dataset(
        (
            InstrumentId.parse("XSHG:510300"),
            InstrumentId.parse("XSHE:159915"),
            InstrumentId.parse("XSHG:518880"),
            InstrumentId.parse("XSHG:511010"),
        ),
        sessions,
    )
    snapshot_dir = _write_snapshot(dataset, tmp_path / "snapshot")
    intent = _intent_with_window(
        basic_end="2022-12-30",
        basic_start="2022-12-01",
        warm_up_start="2022-12-01",
    )

    loaded_manifest, loaded_dataset = _read(snapshot_dir)
    receipt = validate_basic_snapshot(loaded_manifest, loaded_dataset, intent)

    assert receipt.max_session == date(2022, 12, 30)
    assert len(receipt.instrument_ids) == 4


def test_universe_instrument_ending_before_basic_end_fails_closed(
    tmp_path: Path,
) -> None:
    """Coverage is judged per instrument, not by the bundle's global maximum.

    A universe instrument whose own bars stop before the Basic end is a
    truncated instrument (for example an early delisting or a provider gap),
    not a complete snapshot: the global maximum alone would hide it.
    """
    full_sessions = _weekdays_between(date(2022, 12, 1), date(2022, 12, 30))
    short_sessions = _weekdays_between(date(2022, 12, 1), date(2022, 12, 29))
    bars = _dataset((InstrumentId.parse("XSHG:510300"),), full_sessions).daily_bars
    bond_bars = _dataset((InstrumentId.parse("XSHG:511010"),), short_sessions).daily_bars
    dataset = CanonicalDataset(
        daily_bars=bars + bond_bars,
        sessions=_dataset((InstrumentId.parse("XSHG:510300"),), full_sessions).sessions,
        tradability=(),
        corporate_actions=(),
        rule_candidates=(),
    )
    snapshot_dir = _write_snapshot(dataset, tmp_path / "snapshot")
    payload = dict(_minimal_intent_payload())
    payload["universe_policy"]["instrument_ids"] = ["XSHG:510300", "XSHG:511010"]
    payload["basic_start"] = "2022-12-01"
    payload["basic_end"] = "2022-12-30"
    payload["warm_up_start"] = "2022-12-01"
    intent = CandidateIntent.from_dict(payload)

    loaded_manifest, loaded_dataset = _read(snapshot_dir)
    with pytest.raises(BasicSnapshotBoundaryError):
        validate_basic_snapshot(loaded_manifest, loaded_dataset, intent)


def test_run_artifacts_and_directories_cannot_be_overwritten(tmp_path: Path) -> None:
    write_new_json(tmp_path / "manifest.json", {"version": 1})
    with pytest.raises(ArtifactIntegrityError):
        write_new_json(tmp_path / "manifest.json", {"version": 2})

    create_new_directory(tmp_path / "runs")
    with pytest.raises(ArtifactIntegrityError):
        create_new_directory(tmp_path / "runs")


def test_catalog_is_append_only_with_unique_sequences(tmp_path: Path) -> None:
    catalog_dir = tmp_path / "catalog"
    first = append_entry(
        catalog_dir,
        {
            "lineage_id": "lineage-a",
            "artifact_type": "BASIC_RUN",
            "ref": "lineage-a/runs/r1/manifest.json",
            "status": "BASIC_PASS",
            "digests": {"manifest": "sha256:" + "1" * 64},
        },
    )
    second = append_entry(
        catalog_dir,
        {
            "lineage_id": "lineage-a",
            "artifact_type": "BASIC_RUN",
            "ref": "lineage-a/runs/r2/manifest.json",
            "status": "REJECTED_BASIC",
            "digests": {"manifest": "sha256:" + "2" * 64},
        },
    )

    assert first["sequence"] == 1
    assert second["sequence"] == 2
    entries = read_entries(catalog_dir)
    assert [entry["sequence"] for entry in entries] == [1, 2]

    with pytest.raises(CatalogError):
        append_entry(
            catalog_dir,
            {
                "lineage_id": "lineage-b",
                "artifact_type": "BASIC_RUN",
                "ref": "lineage-b/runs/r1/manifest.json",
                "status": "BASIC_PASS",
                "digests": {"manifest": "sha256:" + "3" * 64},
            },
            sequence=1,
        )


def test_catalog_verification_detects_content_mutation(tmp_path: Path) -> None:
    catalog_dir = tmp_path / "catalog"
    artifact = tmp_path / "lineage-a" / "runs" / "r1" / "manifest.json"
    artifact.parent.mkdir(parents=True)
    write_new_json(artifact, {"payload": "original"})
    entry_digest = "sha256:" + hashlib.sha256(artifact.read_bytes()).hexdigest()

    append_entry(
        catalog_dir,
        {
            "lineage_id": "lineage-a",
            "artifact_type": "BASIC_RUN",
            "ref": "lineage-a/runs/r1/manifest.json",
            "status": "BASIC_PASS",
            "digests": {"manifest": entry_digest},
        },
    )
    assert verify_catalog(catalog_dir, tmp_path).status == "PASS"

    artifact.write_bytes(b'{"payload": "tampered"}')
    report = verify_catalog(catalog_dir, tmp_path)
    assert report.status == "FAIL"
    assert any("manifest.json" in finding for finding in report.findings)


# --- Stock annual PIT intake -------------------------------------------------


def _stock_dataset(
    instrument_ids: tuple[InstrumentId, ...], sessions: tuple[date, ...]
) -> CanonicalDataset:
    """Continuous in-snapshot bars plus TRADABLE facts, so the standard
    annual policy (250 listed sessions, 60-session trailing window) can be
    exercised from 2018 year-end facts alone."""
    bars: list[DailyBar] = []
    for instrument_id in instrument_ids:
        previous_close = None
        for index, session_date in enumerate(sessions):
            close = Decimal("10.00") + Decimal(index) * Decimal("0.01")
            available_at = datetime.combine(session_date, time(15, 5), tzinfo=UTC)
            bars.append(
                DailyBar(
                    schema_version="v1",
                    instrument_id=instrument_id,
                    session_date=session_date,
                    open=close,
                    high=close,
                    low=close,
                    close=close,
                    pre_close=previous_close,
                    volume=Decimal("1000000"),
                    amount=Decimal("4000000") + Decimal(index),
                    currency="CNY",
                    volume_unit="shares",
                    amount_unit="CNY",
                    adjustment_mode=AdjustmentMode.RAW,
                    adjustment_factor=None,
                    availability=Availability(
                        information_available_at=available_at,
                        retrieved_at=available_at,
                        availability_basis=AvailabilityBasis.OBSERVED,
                    ),
                    provider_evidence_id="boundary-test-stock-bars",
                )
            )
            previous_close = close
    session_records = tuple(
        TradingSession(
            calendar_id="XSHG",
            session_date=session_date,
            is_open=True,
            note=None,
            snapshot_version="BOUNDARY-STOCK-CAL-1",
        )
        for session_date in sessions
    )
    return CanonicalDataset(
        daily_bars=tuple(bars),
        sessions=session_records,
        tradability=_stock_tradability(instrument_ids, sessions),
        corporate_actions=(),
        rule_candidates=(),
    )


def _stock_sessions(start: date, end: date) -> tuple[date, ...]:
    return _weekdays_between(start, end)


def _load_stock_snapshot(
    dataset: CanonicalDataset, directory: Path, instrument_ids: tuple[InstrumentId, ...]
) -> Path:
    snapshot_dir = _write_snapshot(dataset, directory)
    _write_stock_reference(snapshot_dir, instrument_ids)
    return snapshot_dir


def _stock_run_master(snapshot_dir: Path):
    from systematic_investing.research.intake import (
        build_stock_run_master,
        load_stock_instrument_reference,
    )

    records = load_stock_instrument_reference(snapshot_dir)
    return build_stock_run_master(records)


def test_stock_snapshot_forms_the_annual_pit_schedule(tmp_path: Path) -> None:
    """The 2018 year-end facts alone must form the governing 2019 cohort."""
    from systematic_investing.research.intake import validate_basic_snapshot

    instrument_ids = _stock_symbols(21)
    sessions = _stock_sessions(date(2018, 1, 2), date(2019, 1, 31))
    dataset = _stock_dataset(instrument_ids, sessions)
    snapshot_dir = _load_stock_snapshot(dataset, tmp_path / "snapshot", instrument_ids)
    intent = _stock_intent()
    master = _stock_run_master(snapshot_dir)

    loaded_manifest, loaded_dataset = _read(snapshot_dir)
    receipt = validate_basic_snapshot(
        loaded_manifest, loaded_dataset, intent, master=master
    )

    assert receipt.max_session == date(2019, 1, 31)
    assert receipt.annual_schedule is not None
    view = receipt.annual_schedule.view_for(date(2019, 1, 2))
    assert set(view.instrument_ids) == set(instrument_ids)


def test_stock_snapshot_row_after_basic_end_fails_closed(tmp_path: Path) -> None:
    from systematic_investing.research.intake import (
        BasicSnapshotBoundaryError,
        validate_basic_snapshot,
    )

    instrument_ids = _stock_symbols(21)
    sessions = _stock_sessions(date(2018, 1, 2), date(2019, 2, 1))
    dataset = _stock_dataset(instrument_ids, sessions)
    snapshot_dir = _load_stock_snapshot(dataset, tmp_path / "snapshot", instrument_ids)
    intent = _stock_intent()
    master = _stock_run_master(snapshot_dir)

    loaded_manifest, loaded_dataset = _read(snapshot_dir)
    with pytest.raises(BasicSnapshotBoundaryError):
        validate_basic_snapshot(
            loaded_manifest, loaded_dataset, intent, master=master
        )


def test_stock_schedule_below_minimum_year_fails_closed(tmp_path: Path) -> None:
    """A formation year with fewer than 20 eligible names fails the year."""
    from systematic_investing.research.intake import (
        BasicSnapshotBoundaryError,
        validate_basic_snapshot,
    )

    instrument_ids = _stock_symbols(19)
    sessions = _stock_sessions(date(2018, 1, 2), date(2019, 1, 31))
    dataset = _stock_dataset(instrument_ids, sessions)
    snapshot_dir = _load_stock_snapshot(dataset, tmp_path / "snapshot", instrument_ids)
    intent = _stock_intent()
    master = _stock_run_master(snapshot_dir)

    loaded_manifest, loaded_dataset = _read(snapshot_dir)
    with pytest.raises(BasicSnapshotBoundaryError) as error:
        validate_basic_snapshot(
            loaded_manifest, loaded_dataset, intent, master=master
        )
    assert "STOCK_ANNUAL_COHORT" in str(error.value)


def test_stock_snapshot_without_instrument_reference_fails(tmp_path: Path) -> None:
    from systematic_investing.research.intake import (
        BasicSnapshotBoundaryError,
        validate_basic_snapshot,
    )

    instrument_ids = _stock_symbols(21)
    sessions = _stock_sessions(date(2018, 1, 2), date(2019, 1, 31))
    dataset = _stock_dataset(instrument_ids, sessions)
    snapshot_dir = _write_snapshot(dataset, tmp_path / "snapshot")
    intent = _stock_intent()

    loaded_manifest, loaded_dataset = _read(snapshot_dir)
    with pytest.raises(BasicSnapshotBoundaryError):
        validate_basic_snapshot(
            loaded_manifest,
            loaded_dataset,
            intent,
            master=default_m0_master_for_stock_test(),
        )


def default_m0_master_for_stock_test():
    from systematic_investing.instrument_master.repository import default_m0_master

    return default_m0_master()


def test_stock_snapshot_unregistered_instrument_fails(tmp_path: Path) -> None:
    """Every bar instrument must be covered by the attested reference."""
    from systematic_investing.research.intake import (
        BasicSnapshotBoundaryError,
        validate_basic_snapshot,
    )

    instrument_ids = _stock_symbols(21)
    sessions = _stock_sessions(date(2018, 1, 2), date(2019, 1, 31))
    dataset = _stock_dataset(instrument_ids, sessions)
    snapshot_dir = _write_snapshot(dataset, tmp_path / "snapshot")
    _write_stock_reference(snapshot_dir, instrument_ids[:-1])
    intent = _stock_intent()
    master = _stock_run_master(snapshot_dir)

    loaded_manifest, loaded_dataset = _read(snapshot_dir)
    with pytest.raises(BasicSnapshotBoundaryError):
        validate_basic_snapshot(
            loaded_manifest, loaded_dataset, intent, master=master
        )
