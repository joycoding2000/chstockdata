"""Physical OOS exposure gate tests: scope, snapshot boundaries, and the
freeze-gated owner materializer.

The OOS exposure boundary mirrors the Basic one in both directions: a Basic
snapshot may never contain rows after the Basic end, and an OOS snapshot or
OOS materialization request may never contain rows inside the Basic window.
The owner materializer accepts exactly one verified freeze artifact and
refuses missing, mutated, or mismatched freezes strictly BEFORE any provider
access; the provider seam is injected so every refusal and the full
OOS-scope write path run offline.
"""

import json
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from test_candidate_intent import _minimal_intent_payload

from systematic_investing.data.contracts import ProviderEvidence, ProviderSuccess
from systematic_investing.data.ports import (
    CalendarRequest,
    CorporateActionRequest,
    DailyBarRequest,
    TradabilityRequest,
)
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
from systematic_investing.instrument_master.repository import default_m0_master
from systematic_investing.research.artifacts import read_json, write_new_json
from systematic_investing.research.catalog import append_entry
from systematic_investing.research.contracts import CandidateIntent
from systematic_investing.research.intake import (
    BasicSnapshotBoundaryError,
    validate_basic_snapshot,
)
from systematic_investing.research.materializer import (
    REASON_OUTPUT_EXISTS,
    MaterializationError,
    materialize_oos_snapshot,
    prepare_oos_materialization,
)
from systematic_investing.research.oos import (
    REASON_FREEZE_DIGEST_MISMATCH,
    REASON_FREEZE_INTENT_MISMATCH,
    REASON_FREEZE_MISSING,
    REASON_FREEZE_SCOPE_MISMATCH,
    REASON_OOS_EMPTY_SNAPSHOT,
    REASON_OOS_END_EXCEEDED,
    REASON_OOS_END_UNCOVERED,
    REASON_OOS_ROWS_BEFORE_OOS_START,
    REASON_OOS_SNAPSHOT_QUALITY_NOT_PASS,
    REASON_OOS_WARMUP_AFTER_BASIC_END,
    REASON_STOCK_OOS_UNSUPPORTED,
    OosError,
    build_freeze_payload,
    build_oos_wiring,
    persist_freeze,
    rebuild_revealed_oos_window_ledger,
    record_reveal,
    reject_contaminated_oos_request,
    reveal_payload,
    validate_oos_snapshot,
)

MARKET_TIMEZONE = timezone(timedelta(hours=8))

OOS_START = date(2023, 1, 3)
OOS_END = date(2023, 3, 31)
BASIC_END = date(2022, 12, 30)

_FAKE_IMPLEMENTATION_DIGEST = "sha256:" + "a" * 64
_FAKE_KERNEL_DIGEST = "sha256:" + "b" * 64


def _intent_payload() -> dict:
    payload = _minimal_intent_payload()
    payload["oos_start"] = OOS_START.isoformat()
    payload["oos_end"] = OOS_END.isoformat()
    return payload


def _intent() -> CandidateIntent:
    return CandidateIntent.from_dict(_intent_payload())


def _stock_intent_payload() -> dict:
    payload = _intent_payload()
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
    payload["known_limitations"] = (
        "DIVIDEND_TAX_NOT_MODELED: personal-investor dividend tax is not modeled.",
    )
    return payload


def _freeze_payload(intent_payload: dict) -> dict:
    intent = CandidateIntent.from_dict(intent_payload)
    return build_freeze_payload(
        intent,
        intent_payload=intent_payload,
        selected_variant_id="sma-2",
        strategy_version="v1",
        implementation_digest=_FAKE_IMPLEMENTATION_DIGEST,
        parameters_digest="sha256:" + "e" * 64,
        kernel_identity_digest=_FAKE_KERNEL_DIGEST,
        basic_selection_digest="sha256:" + "d" * 64,
        basic_snapshot_digest="sha256:" + "c" * 64,
    )


def _write_freeze(tmp_path: Path, intent_payload: dict) -> Path:
    freeze_path = tmp_path / "freeze.json"
    write_new_json(freeze_path, _freeze_payload(intent_payload))
    return freeze_path


def _record_revealed_window(
    root: Path,
    intent_payload: dict,
) -> dict:
    """Create the immutable freeze/reveal/catalog evidence used by the ledger."""
    freeze = _freeze_payload(intent_payload)
    freeze_path, _ = persist_freeze(root, str(intent_payload["lineage_id"]), freeze)
    reveal = reveal_payload(freeze, warm_up_snapshot_digest=None)
    reveal_path, reveal_digest = record_reveal(freeze_path.parent, reveal)
    append_entry(
        root / "catalog",
        {
            "lineage_id": intent_payload["lineage_id"],
            "artifact_type": "OOS_REVEALED",
            "ref": reveal_path.relative_to(root).as_posix(),
            "status": "OOS_REVEALED",
            "digests": {"reveal": reveal_digest},
        },
    )
    return freeze


def _weekdays(start: date, end: date) -> tuple[date, ...]:
    sessions: list[date] = []
    day = start
    while day <= end:
        if day.weekday() < 5:
            sessions.append(day)
        day = date.fromordinal(day.toordinal() + 1)
    return tuple(sessions)


OOS_SESSIONS: tuple[date, ...] = _weekdays(OOS_START, OOS_END)


def _oos_dataset(
    *,
    extra_sessions: tuple[date, ...] = (),
    stop_early: bool = False,
) -> CanonicalDataset:
    """One instrument's OOS-window dataset; the first OOS bar carries no
    pre_close, because the previous close lives inside the Basic window and
    must never be exposed."""
    instrument_id = InstrumentId.parse("XSHG:510300")
    sessions = OOS_SESSIONS if not stop_early else OOS_SESSIONS[:-1]
    all_sessions = (*extra_sessions, *sessions)
    bars: list[DailyBar] = []
    previous_close: Decimal | None = None
    for index, session_date in enumerate(all_sessions):
        close = Decimal("4.00") + Decimal(index) * Decimal("0.01")
        available_at = datetime.combine(
            session_date, time(15, 5), tzinfo=MARKET_TIMEZONE
        )
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
                provider_evidence_id="oos-gate-test-bars",
            )
        )
        previous_close = close
    session_records = tuple(
        TradingSession(
            calendar_id="XSHG",
            session_date=session_date,
            is_open=True,
            note=None,
            snapshot_version="OOS-GATE-TEST-CAL-1",
        )
        for session_date in all_sessions
    )
    tradability = tuple(
        TradabilityStatus(
            instrument_id=instrument_id,
            session_date=session_date,
            status=TradabilityStatusKind.TRADABLE,
            reason=None,
            availability=Availability(
                information_available_at=datetime.combine(
                    session_date, time(9, 0), tzinfo=MARKET_TIMEZONE
                ),
                retrieved_at=datetime.combine(
                    session_date, time(9, 1), tzinfo=MARKET_TIMEZONE
                ),
                availability_basis=AvailabilityBasis.OBSERVED,
            ),
            provenance="oos-gate-test",
        )
        for session_date in all_sessions
    )
    return CanonicalDataset(
        daily_bars=tuple(bars),
        sessions=session_records,
        tradability=tradability,
        corporate_actions=(),
        rule_candidates=(),
    )


def _write_snapshot(dataset: CanonicalDataset, directory: Path) -> Path:
    writer = SnapshotWriter(
        provider_name="oos-gate-test",
        provider_version="v1",
        adapter_version="oos-gate-test-1",
    )
    cutoff = datetime.combine(
        max(session.session_date for session in dataset.sessions),
        time(15, 30),
        tzinfo=UTC,
    )
    writer.persist(
        dataset,
        snapshot_dir=directory,
        created_at=cutoff,
        knowledge_cutoff=cutoff,
        retrieved_at=cutoff,
    )
    return directory


# --- stable-lineage revealed-window contamination ----------------------------


@pytest.mark.parametrize(
    ("start", "end"),
    (
        (OOS_START, OOS_END),
        (date(2023, 3, 1), date(2023, 4, 14)),
        (date(2023, 2, 1), date(2023, 3, 1)),
        (date(2023, 1, 3), date(2023, 4, 28)),
    ),
    ids=("same", "partial", "contained", "superset"),
)
def test_same_lineage_revealed_window_overlap_is_contaminated(
    tmp_path: Path, start: date, end: date
) -> None:
    original = _intent_payload()
    _record_revealed_window(tmp_path, original)
    new_version = _intent_payload()
    new_version["intent_id"] = "test-etf-absolute-trend-v2-renamed"
    new_version["oos_start"] = start.isoformat()
    new_version["oos_end"] = end.isoformat()

    with pytest.raises(OosError, match="OOS_CONTAMINATED"):
        reject_contaminated_oos_request(
            tmp_path,
            _freeze_payload(new_version),
        )


def test_revealed_window_ledger_uses_stable_lineage_not_candidate_name(
    tmp_path: Path,
) -> None:
    original = _intent_payload()
    freeze = _record_revealed_window(tmp_path, original)
    ledger = rebuild_revealed_oos_window_ledger(tmp_path)

    assert len(ledger) == 1
    assert ledger[0].lineage_id == original["lineage_id"]
    assert ledger[0].freeze_id == freeze["freeze_id"]
    assert ledger[0].reveal_sequence == 1
    assert ledger[0].requested_oos_start == OOS_START
    assert ledger[0].requested_oos_end == OOS_END
    assert ledger[0].reveal_digest.startswith("sha256:")


def test_nonoverlapping_or_different_lineage_oos_request_is_not_contaminated(
    tmp_path: Path,
) -> None:
    _record_revealed_window(tmp_path, _intent_payload())
    future = _intent_payload()
    future["intent_id"] = "test-etf-absolute-trend-v2"
    future["oos_start"] = "2023-04-03"
    future["oos_end"] = "2023-06-30"
    reject_contaminated_oos_request(tmp_path, _freeze_payload(future))

    independent = _intent_payload()
    independent["lineage_id"] = "independent-research-lineage"
    independent["intent_id"] = "independent-research-v1"
    reject_contaminated_oos_request(tmp_path, _freeze_payload(independent))


def test_same_freeze_retry_remains_legal_after_its_reveal(tmp_path: Path) -> None:
    freeze = _record_revealed_window(tmp_path, _intent_payload())

    reject_contaminated_oos_request(tmp_path, freeze)


# --- OOS snapshot boundary (both directions of the split) --------------------


def test_basic_snapshot_row_after_basic_end_still_fails_closed(tmp_path: Path) -> None:
    """The Basic-side boundary holds unchanged: a Basic snapshot with a row
    after the Basic end is rejected."""
    dataset = _oos_dataset()
    intent = _intent()
    loaded_manifest, loaded_dataset = SnapshotReader().load(
        _write_snapshot(dataset, tmp_path / "snapshot")
    )
    with pytest.raises(BasicSnapshotBoundaryError):
        validate_basic_snapshot(loaded_manifest, loaded_dataset, intent)


def test_oos_snapshot_with_basic_window_rows_fails_closed(tmp_path: Path) -> None:
    """An OOS snapshot may never contain rows inside the Basic window."""
    contaminated = _oos_dataset(extra_sessions=(BASIC_END,))
    intent = _intent()
    loaded_manifest, loaded_dataset = SnapshotReader().load(
        _write_snapshot(contaminated, tmp_path / "snapshot")
    )
    with pytest.raises(OosError) as error:
        validate_oos_snapshot(loaded_manifest, loaded_dataset, intent)
    assert REASON_OOS_ROWS_BEFORE_OOS_START in str(error.value)


def test_oos_snapshot_row_after_oos_end_fails_closed(tmp_path: Path) -> None:
    dataset = _oos_dataset(extra_sessions=(date(2023, 4, 3),))
    intent = _intent()
    loaded_manifest, loaded_dataset = SnapshotReader().load(
        _write_snapshot(dataset, tmp_path / "snapshot")
    )
    with pytest.raises(OosError) as error:
        validate_oos_snapshot(loaded_manifest, loaded_dataset, intent)
    assert REASON_OOS_END_EXCEEDED in str(error.value)


def test_oos_snapshot_ending_before_oos_end_fails_closed(tmp_path: Path) -> None:
    dataset = _oos_dataset(stop_early=True)
    intent = _intent()
    loaded_manifest, loaded_dataset = SnapshotReader().load(
        _write_snapshot(dataset, tmp_path / "snapshot")
    )
    with pytest.raises(OosError) as error:
        validate_oos_snapshot(loaded_manifest, loaded_dataset, intent)
    assert REASON_OOS_END_UNCOVERED in str(error.value)


def test_oos_snapshot_with_failing_quality_status_fails_closed(
    tmp_path: Path,
) -> None:
    dataset = _oos_dataset()
    writer = SnapshotWriter(
        provider_name="oos-gate-test",
        provider_version="v1",
        adapter_version="oos-gate-test-1",
    )
    cutoff = datetime.combine(OOS_END, time(15, 30), tzinfo=UTC)
    writer.persist(
        dataset,
        snapshot_dir=tmp_path / "snapshot",
        created_at=cutoff,
        knowledge_cutoff=cutoff,
        retrieved_at=cutoff,
        quality_report_id="sha256:" + "0" * 64,
        quality_status="FAIL",
    )
    intent = _intent()
    loaded_manifest, loaded_dataset = SnapshotReader().load(tmp_path / "snapshot")
    with pytest.raises(OosError) as error:
        validate_oos_snapshot(loaded_manifest, loaded_dataset, intent)
    assert REASON_OOS_SNAPSHOT_QUALITY_NOT_PASS in str(error.value)


def test_stock_oos_snapshot_intake_is_refused(tmp_path: Path) -> None:
    """Stock OOS intake needs data-derived schedule semantics M1 has not
    defined; it refuses instead of inventing a universe digest."""
    dataset = _oos_dataset()
    loaded_manifest, loaded_dataset = SnapshotReader().load(
        _write_snapshot(dataset, tmp_path / "snapshot")
    )
    stock_intent = CandidateIntent.from_dict(_stock_intent_payload())
    with pytest.raises(OosError) as error:
        validate_oos_snapshot(loaded_manifest, loaded_dataset, stock_intent)
    assert REASON_STOCK_OOS_UNSUPPORTED in str(error)


def test_oos_snapshot_receipt_binds_actual_content(tmp_path: Path) -> None:
    dataset = _oos_dataset()
    intent = _intent()
    loaded_manifest, loaded_dataset = SnapshotReader().load(
        _write_snapshot(dataset, tmp_path / "snapshot")
    )
    receipt = validate_oos_snapshot(loaded_manifest, loaded_dataset, intent)
    assert receipt.snapshot_id == loaded_manifest.snapshot_id
    assert receipt.snapshot_digest == "sha256:" + loaded_manifest.snapshot_id
    assert receipt.min_session == OOS_START
    assert receipt.max_session == OOS_END
    assert receipt.universe_schedule_digest.startswith("sha256:")


def test_warm_up_snapshot_with_rows_after_basic_end_fails_closed(
    tmp_path: Path,
) -> None:
    """Composed warm-up data may never carry rows past the Basic end: the
    warm-up door must not smuggle OOS-window facts into the run."""
    intent = _intent()
    loaded_manifest, loaded_dataset = SnapshotReader().load(
        _write_snapshot(_oos_dataset(), tmp_path / "snapshot")
    )
    receipt = validate_oos_snapshot(loaded_manifest, loaded_dataset, intent)

    with pytest.raises(OosError) as error:
        build_oos_wiring(
            loaded_dataset,
            intent,
            receipt,
            master=default_m0_master(),
            warm_up_dataset=loaded_dataset,
        )
    assert REASON_OOS_WARMUP_AFTER_BASIC_END in str(error.value)


def test_oos_wiring_with_empty_sessions_fails_typed(tmp_path: Path) -> None:
    """An OOS snapshot without calendar sessions is a typed refusal, never an
    IndexError, even when a warm-up dataset is composed."""
    intent = _intent()
    loaded_manifest, loaded_dataset = SnapshotReader().load(
        _write_snapshot(_oos_dataset(), tmp_path / "snapshot")
    )
    receipt = validate_oos_snapshot(loaded_manifest, loaded_dataset, intent)
    empty = CanonicalDataset(
        daily_bars=(),
        sessions=(),
        tradability=(),
        corporate_actions=(),
        rule_candidates=(),
    )

    with pytest.raises(OosError) as error:
        build_oos_wiring(
            empty,
            intent,
            receipt,
            master=default_m0_master(),
            warm_up_dataset=loaded_dataset,
        )
    assert REASON_OOS_EMPTY_SNAPSHOT in str(error.value)


# --- materializer refusals (strictly before any provider access) -------------


class _ExplodingProviderFactory:
    """Fails the test if the materializer constructs a provider during a
    refusal path."""

    def __init__(self) -> None:
        self.called = False

    def __call__(self) -> Any:
        self.called = True
        raise AssertionError("provider must not be constructed before validation")


def _write_payload_file(tmp_path: Path, name: str, payload: dict) -> bytes:
    path = tmp_path / name
    write_new_json(path, payload)
    return path.read_bytes()


def _resign(payload: dict) -> dict:
    """Recompute the freeze_id/freeze_digest over a mutated body, exactly as
    build_freeze_payload derives them."""
    from systematic_investing.research.contracts import canonical_payload_digest

    body = {key: value for key, value in payload.items() if key != "freeze_digest"}
    body["freeze_id"] = (
        "freeze-"
        + canonical_payload_digest(
            {key: value for key, value in body.items() if key != "freeze_id"}
        ).removeprefix("sha256:")[:16]
    )
    body["freeze_digest"] = canonical_payload_digest(body)
    return body


def _refuse(tmp_path: Path, freeze_bytes: bytes | None) -> MaterializationError:
    """prepare_oos_materialization must refuse without ever constructing a
    provider."""
    factory = _ExplodingProviderFactory()
    freeze_path = tmp_path / "freeze.json"
    if freeze_bytes is not None:
        freeze_path.write_bytes(freeze_bytes)
    with pytest.raises(MaterializationError) as error:
        prepare_oos_materialization(
            freeze_path if freeze_bytes is not None else tmp_path / "missing.json",
            tmp_path / "oos-out",
        )
    assert not factory.called
    return error.value


def test_materializer_refuses_missing_freeze(tmp_path: Path) -> None:
    error = _refuse(tmp_path, None)
    assert REASON_FREEZE_MISSING in str(error)


def test_materializer_refuses_mutated_freeze(tmp_path: Path) -> None:
    """A real field mutation keeps the JSON well-formed but breaks the
    recorded self-digest."""
    freeze_path = _write_freeze(tmp_path, _intent_payload())
    mutated = read_json(freeze_path)
    mutated["requested_oos_end"] = "2023-12-31"
    freeze_path.write_bytes(json.dumps(mutated, sort_keys=True).encode("utf-8"))
    error = _refuse(tmp_path, freeze_path.read_bytes())
    assert REASON_FREEZE_DIGEST_MISMATCH in str(error)


def test_materializer_refuses_freeze_intent_mismatch(tmp_path: Path) -> None:
    """A fully re-signed freeze cannot disguise an intent swap: the embedded
    intent payload no longer hashes to the recorded intent digest."""
    payload = _freeze_payload(_intent_payload())
    payload["intent_payload"]["economic_rationale"] = "Swapped after signing."
    freeze_bytes = _write_payload_file(tmp_path, "resigned.json", _resign(payload))
    error = _refuse(tmp_path, freeze_bytes)
    assert REASON_FREEZE_INTENT_MISMATCH in str(error)


def test_materializer_refuses_scope_reaching_into_basic_window(
    tmp_path: Path,
) -> None:
    """A freeze requesting an OOS scope that overlaps the Basic window is
    refused before any provider access."""
    payload = _freeze_payload(_intent_payload())
    payload["requested_oos_start"] = BASIC_END.isoformat()
    freeze_bytes = _write_payload_file(
        tmp_path, "overlapping.json", _resign(payload)
    )
    error = _refuse(tmp_path, freeze_bytes)
    assert REASON_FREEZE_SCOPE_MISMATCH in str(error)


def test_materializer_refuses_existing_output_directory(tmp_path: Path) -> None:
    freeze_path = _write_freeze(tmp_path, _intent_payload())
    output_dir = tmp_path / "oos-out"
    output_dir.mkdir()
    with pytest.raises(MaterializationError) as error:
        prepare_oos_materialization(freeze_path, output_dir)
    assert REASON_OUTPUT_EXISTS in str(error.value)


def test_materializer_refuses_stock_oos_materialization(tmp_path: Path) -> None:
    freeze_path = _write_freeze(tmp_path, _stock_intent_payload())
    with pytest.raises(MaterializationError) as error:
        prepare_oos_materialization(freeze_path, tmp_path / "oos-out")
    assert REASON_STOCK_OOS_UNSUPPORTED in str(error)


# --- materializer write path (offline fake provider) --------------------------


@dataclass
class _RecordedRequests:
    calendar: list[CalendarRequest] = field(default_factory=list)
    daily_bars: list[DailyBarRequest] = field(default_factory=list)
    tradability: list[TradabilityRequest] = field(default_factory=list)
    corporate_actions: list[CorporateActionRequest] = field(default_factory=list)


class _FakeOosProvider:
    """A deterministic offline provider over the same canonical port the
    real owner materializer consumes."""

    PROVIDER_NAME = "fake-oos"
    ADAPTER_VERSION = "fake-oos-1"

    def __init__(self, dataset: CanonicalDataset) -> None:
        self.requests = _RecordedRequests()
        self._dataset = dataset

    def _evidence(self, capability: str) -> ProviderEvidence:
        return ProviderEvidence(
            evidence_id=f"fake-{capability}",
            provider_name=self.PROVIDER_NAME,
            provider_version="fake-v1",
            adapter_name="fake-adapter",
            adapter_version=self.ADAPTER_VERSION,
            capability=capability,
            request_digest="sha256:fake",
            retrieved_at=datetime(2026, 9, 19, tzinfo=UTC),
            upstream_source="fake",
            record_count=1,
            payload_checksum="fake",
        )

    def capability_evidence(self) -> ProviderEvidence:
        return self._evidence("provider_capability")

    def fetch_calendar(self, request: CalendarRequest) -> ProviderSuccess:
        self.requests.calendar.append(request)
        records = tuple(
            session
            for session in self._dataset.sessions
            if request.start_date <= session.session_date <= request.end_date
        )
        return ProviderSuccess(records=records, evidence=self._evidence("calendar"))

    def fetch_daily_bars(self, request: DailyBarRequest) -> ProviderSuccess:
        self.requests.daily_bars.append(request)
        records = tuple(
            bar
            for bar in self._dataset.daily_bars
            if request.start_date <= bar.session_date <= request.end_date
            and bar.instrument_id in set(request.instrument_ids)
        )
        return ProviderSuccess(records=records, evidence=self._evidence("daily_bars"))

    def fetch_tradability(self, request: TradabilityRequest) -> ProviderSuccess:
        self.requests.tradability.append(request)
        records = tuple(
            record
            for record in self._dataset.tradability
            if record.session_date == request.session_date
            and record.instrument_id in set(request.instrument_ids)
        )
        return ProviderSuccess(records=records, evidence=self._evidence("tradability"))

    def fetch_corporate_actions(
        self, request: CorporateActionRequest
    ) -> ProviderSuccess:
        self.requests.corporate_actions.append(request)
        return ProviderSuccess(records=(), evidence=self._evidence("corporate_actions"))


def _materialize_with_fake_provider(tmp_path: Path) -> tuple[Path, _FakeOosProvider]:
    freeze_path = _write_freeze(tmp_path, _intent_payload())
    output_dir = tmp_path / "oos-out"
    plan = prepare_oos_materialization(freeze_path, output_dir)
    provider = _FakeOosProvider(_oos_dataset())
    materialize_oos_snapshot(plan, provider_factory=lambda: provider)
    return output_dir, provider


def test_materializer_fetches_and_writes_only_the_requested_oos_scope(
    tmp_path: Path,
) -> None:
    """The provider is asked for exactly the frozen OOS window and the written
    snapshot covers exactly that window: no Basic-window rows, nothing beyond
    the OOS end."""
    output_dir, provider = _materialize_with_fake_provider(tmp_path)

    assert provider.requests.calendar
    for request in provider.requests.calendar:
        assert request.start_date == OOS_START
        assert request.end_date == OOS_END
    assert provider.requests.daily_bars
    for request in provider.requests.daily_bars:
        assert request.start_date == OOS_START
        assert request.end_date == OOS_END

    loaded_manifest, loaded_dataset = SnapshotReader().load(output_dir)
    assert min(bar.session_date for bar in loaded_dataset.daily_bars) == OOS_START
    assert max(bar.session_date for bar in loaded_dataset.daily_bars) == OOS_END
    assert all(bar.session_date > BASIC_END for bar in loaded_dataset.daily_bars)

    receipt = read_json(output_dir / "oos-receipt.json")
    assert receipt["freeze_id"].startswith("freeze-")
    assert receipt["requested_oos_start"] == OOS_START.isoformat()
    assert receipt["requested_oos_end"] == OOS_END.isoformat()
    # The OOS receipt carries the raw snapshot id, the Basic receipt's
    # convention (the gate receipt keeps its own sha256-prefixed binding).
    assert receipt["snapshot_id"] == loaded_manifest.snapshot_id
    assert (output_dir / "gate-receipt.json").exists()


def test_materialized_oos_snapshot_passes_oos_intake(tmp_path: Path) -> None:
    output_dir, _provider = _materialize_with_fake_provider(tmp_path)
    intent = _intent()
    loaded_manifest, loaded_dataset = SnapshotReader().load(output_dir)
    receipt = validate_oos_snapshot(loaded_manifest, loaded_dataset, intent)
    assert receipt.max_session == OOS_END


def test_oos_snapshot_output_is_immutable(tmp_path: Path) -> None:
    freeze_path = _write_freeze(tmp_path, _intent_payload())
    output_dir = tmp_path / "oos-out"
    plan = prepare_oos_materialization(freeze_path, output_dir)
    provider = _FakeOosProvider(_oos_dataset())
    materialize_oos_snapshot(plan, provider_factory=lambda: provider)

    with pytest.raises(MaterializationError) as error:
        prepare_oos_materialization(freeze_path, output_dir)
    assert REASON_OUTPUT_EXISTS in str(error.value)
