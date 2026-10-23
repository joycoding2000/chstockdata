"""Integration tests: immutable snapshot persistence and checksum replay.

The snapshot format is JSON Lines with SHA-256 content checksums recorded in
a versioned manifest. Every expected digest below is derived from the
declared normalization contract (canonical JSON, sorted records, exact file
bytes), not from running an implementation as its own oracle. Runs use fixed
injected timestamps and temporary directories only.
"""

import json
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from systematic_investing.data.quality import CanonicalDataset
from systematic_investing.data.snapshots import (
    ADJUSTMENT_POLICY_RAW_WITH_PIT_FACTORS,
    DataSnapshotManifest,
    SnapshotIntegrityError,
    SnapshotReader,
    SnapshotWriter,
)
from systematic_investing.domain.identifiers import Exchange, InstrumentId
from systematic_investing.domain.market import (
    AdjustmentMode,
    Availability,
    AvailabilityBasis,
    DailyBar,
    TradingSession,
)

XSHG_510300 = InstrumentId(exchange=Exchange.XSHG, symbol="510300")
XSHE_000001 = InstrumentId(exchange=Exchange.XSHE, symbol="000001")

CREATED_AT = datetime(2026, 9, 14, 16, 5, tzinfo=UTC)
KNOWLEDGE_CUTOFF = datetime(2026, 9, 14, 15, 0, tzinfo=UTC)
RETRIEVED_AT = datetime(2026, 9, 14, 16, 0, tzinfo=UTC)


def bar(instrument_id, session_date, close, pre_close) -> DailyBar:
    close_value = Decimal(close)
    return DailyBar(
        schema_version="v1",
        instrument_id=instrument_id,
        session_date=session_date,
        open=close_value,
        high=close_value,
        low=close_value,
        close=close_value,
        pre_close=Decimal(pre_close),
        volume=Decimal("1000"),
        amount=close_value * Decimal("1000"),
        currency="CNY",
        volume_unit="share",
        amount_unit="CNY",
        adjustment_mode=AdjustmentMode.RAW,
        adjustment_factor=None,
        availability=Availability(
            information_available_at=datetime(2026, 9, 14, 15, 0, tzinfo=UTC),
            retrieved_at=RETRIEVED_AT,
            availability_basis=AvailabilityBasis.OBSERVED,
        ),
        provider_evidence_id="ev-snapshot-test",
    )


def calendar_sessions() -> tuple[TradingSession, ...]:
    records = []
    for calendar_id in ("XSHG", "XSHE"):
        for day in (date(2026, 9, 11), date(2026, 9, 14)):
            records.append(
                TradingSession(
                    calendar_id=calendar_id,
                    session_date=day,
                    is_open=True,
                    note=None,
                    snapshot_version="CAL-TEST-1",
                )
            )
    return tuple(records)


def dataset() -> CanonicalDataset:
    return CanonicalDataset(
        daily_bars=(
            bar(XSHG_510300, date(2026, 9, 11), "4.00", "3.95"),
            bar(XSHG_510300, date(2026, 9, 14), "4.10", "4.00"),
            bar(XSHE_000001, date(2026, 9, 11), "12.00", "11.88"),
            bar(XSHE_000001, date(2026, 9, 14), "12.20", "12.00"),
        ),
        sessions=calendar_sessions(),
        tradability=(),
        corporate_actions=(),
        rule_candidates=(),
    )


def writer() -> SnapshotWriter:
    return SnapshotWriter(
        provider_name="chstockdata",
        provider_version="commit-review-1",
        adapter_version="0.1.0",
    )


def persist_to(directory: Path) -> DataSnapshotManifest:
    return writer().persist(
        dataset(),
        snapshot_dir=directory,
        created_at=CREATED_AT,
        knowledge_cutoff=KNOWLEDGE_CUTOFF,
        retrieved_at=RETRIEVED_AT,
    )


class TestSnapshotRoundTrip:
    def test_persist_then_replay_preserves_records_and_checksums(self, tmp_path: Path) -> None:
        manifest = persist_to(tmp_path / "snapshot")

        assert manifest.quality_report_id == "sha256:" + "0" * 64
        assert manifest.quality_status == "PASS"
        assert manifest.adjustment_policy == ADJUSTMENT_POLICY_RAW_WITH_PIT_FACTORS

        loaded_manifest, loaded_dataset = SnapshotReader().load(tmp_path / "snapshot")

        assert loaded_manifest == manifest
        assert sorted(loaded_dataset.daily_bars, key=repr) == sorted(
            dataset().daily_bars, key=repr
        )
        assert sorted(loaded_dataset.sessions, key=repr) == sorted(
            dataset().sessions, key=repr
        )


class TestSnapshotIdentity:
    def test_identical_runs_in_two_directories_yield_identical_manifest_bytes(
        self, tmp_path: Path
    ) -> None:
        first = persist_to(tmp_path / "first")
        second = persist_to(tmp_path / "second")

        assert first == second
        assert (tmp_path / "first" / "manifest.json").read_bytes() == (
            tmp_path / "second" / "manifest.json"
        ).read_bytes()

    def test_record_ordering_does_not_change_the_snapshot_identity(self, tmp_path: Path) -> None:
        first = persist_to(tmp_path / "first")
        reversed_dataset = CanonicalDataset(
            daily_bars=tuple(reversed(dataset().daily_bars)),
            sessions=calendar_sessions(),
            tradability=(),
            corporate_actions=(),
            rule_candidates=(),
        )
        second = writer().persist(
            reversed_dataset,
            snapshot_dir=tmp_path / "second",
            created_at=CREATED_AT,
            knowledge_cutoff=KNOWLEDGE_CUTOFF,
            retrieved_at=RETRIEVED_AT,
        )

        assert first.snapshot_id == second.snapshot_id

    def test_mutating_one_price_yields_a_new_snapshot_id(self, tmp_path: Path) -> None:
        first = persist_to(tmp_path / "first")
        bars = list(dataset().daily_bars)
        bars[1] = bar(XSHG_510300, date(2026, 9, 14), "4.11", "4.00")
        second = writer().persist(
            CanonicalDataset(
                daily_bars=tuple(bars),
                sessions=calendar_sessions(),
                tradability=(),
                corporate_actions=(),
                rule_candidates=(),
            ),
            snapshot_dir=tmp_path / "second",
            created_at=CREATED_AT,
            knowledge_cutoff=KNOWLEDGE_CUTOFF,
            retrieved_at=RETRIEVED_AT,
        )

        assert first.snapshot_id != second.snapshot_id


class TestSnapshotIntegrity:
    def test_corrupted_artifact_is_detected_on_replay(self, tmp_path: Path) -> None:
        persist_to(tmp_path / "snapshot")
        artifact = tmp_path / "snapshot" / "artifacts" / "daily_bar.jsonl"
        original = artifact.read_bytes()
        artifact.write_bytes(original.replace(b'"close":"4.10"', b'"close":"9.99"'))

        with pytest.raises(SnapshotIntegrityError):
            SnapshotReader().load(tmp_path / "snapshot")

    def test_manifest_snapshot_id_mismatch_is_detected_on_replay(self, tmp_path: Path) -> None:
        persist_to(tmp_path / "snapshot")
        manifest_path = tmp_path / "snapshot" / "manifest.json"
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        payload["snapshot_id"] = "0" * 64
        manifest_path.write_text(
            json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False),
            encoding="utf-8",
        )

        with pytest.raises(SnapshotIntegrityError):
            SnapshotReader().load(tmp_path / "snapshot")

    def test_writer_refuses_to_overwrite_an_existing_manifest(self, tmp_path: Path) -> None:
        persist_to(tmp_path / "snapshot")

        with pytest.raises(SnapshotIntegrityError):
            persist_to(tmp_path / "snapshot")


class TestQualityEvidenceBinding:
    GATE_DIGEST = "3" * 64

    def test_persist_binds_gate_evidence_into_manifest_and_replay(
        self, tmp_path: Path
    ) -> None:
        manifest = writer().persist(
            dataset(),
            snapshot_dir=tmp_path / "snapshot",
            created_at=CREATED_AT,
            knowledge_cutoff=KNOWLEDGE_CUTOFF,
            retrieved_at=RETRIEVED_AT,
            quality_report_id="sha256:" + self.GATE_DIGEST,
            quality_status="PASS",
        )

        assert manifest.quality_report_id == "sha256:" + self.GATE_DIGEST
        assert manifest.quality_status == "PASS"

        loaded_manifest, _ = SnapshotReader().load(tmp_path / "snapshot")
        assert loaded_manifest == manifest

    def test_quality_evidence_is_part_of_the_snapshot_identity(
        self, tmp_path: Path
    ) -> None:
        bound = writer().persist(
            dataset(),
            snapshot_dir=tmp_path / "bound",
            created_at=CREATED_AT,
            knowledge_cutoff=KNOWLEDGE_CUTOFF,
            retrieved_at=RETRIEVED_AT,
            quality_report_id="sha256:" + self.GATE_DIGEST,
            quality_status="PASS",
        )
        unbound = writer().persist(
            dataset(),
            snapshot_dir=tmp_path / "unbound",
            created_at=CREATED_AT,
            knowledge_cutoff=KNOWLEDGE_CUTOFF,
            retrieved_at=RETRIEVED_AT,
        )
        failed = writer().persist(
            dataset(),
            snapshot_dir=tmp_path / "failed",
            created_at=CREATED_AT,
            knowledge_cutoff=KNOWLEDGE_CUTOFF,
            retrieved_at=RETRIEVED_AT,
            quality_report_id="sha256:" + self.GATE_DIGEST,
            quality_status="FAIL",
        )

        assert unbound.snapshot_id != bound.snapshot_id
        assert failed.snapshot_id != bound.snapshot_id
