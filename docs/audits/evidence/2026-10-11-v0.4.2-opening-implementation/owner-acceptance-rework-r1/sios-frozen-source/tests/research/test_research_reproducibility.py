"""Deterministic replay and typed failure retention for Basic runs.

The same manifest identity rerun against the same wiring must produce the
same result digest and be retained as a new immutable attempt, never an
overwrite. Provider-shaped failures are typed: an empty or partial snapshot
fails closed at the wiring, ambiguous or missing market facts are retained as
``RUN_FAILED_DATA``, kernel/compile failures as ``RUN_FAILED_KERNEL`` — and a
provider failure is never representable as a successful run with empty
metrics. Every identity field of a ``ResearchRunManifest`` participates in
the run identity: mutating any one of them yields a new identity.
"""

import dataclasses
from datetime import UTC, date, datetime, time
from decimal import Decimal
from pathlib import Path

import pytest
from test_candidate_intent import _minimal_intent_payload

from systematic_investing.data.quality import CanonicalDataset
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
from systematic_investing.research.artifacts import (
    canonical_json_bytes,
    digest_of_bytes,
    next_attempt_for,
    run_id_for,
    write_new_json,
)
from systematic_investing.research.catalog import append_entry, read_entries, verify_catalog
from systematic_investing.research.contracts import (
    _RUN_MANIFEST_IDENTITY_FIELDS,
    RUN_MANIFEST_SCHEMA_VERSION,
    CandidateIntent,
    InvalidResearchRunManifestError,
    ResearchRunManifest,
)
from systematic_investing.research.intake import BasicSnapshotReceipt
from systematic_investing.research.runner import (
    RUN_STATUS_BASIC_PASS,
    RUN_STATUS_REJECTED_BASIC,
    RUN_STATUS_RUN_FAILED_DATA,
    RUN_STATUS_RUN_FAILED_KERNEL,
    BasicRunOutcome,
    BasicWiring,
    RunWiringError,
    build_basic_wiring,
    run_basic_variant,
)

BASIC_START = date(2024, 1, 2)
BASIC_END = date(2024, 3, 29)
INSTRUMENT = InstrumentId.parse("XSHG:510300")
VARIANT_ID = "sma-2"
LINEAGE_ID = "test-etf-absolute-trend"


# --- shared offline helpers ---------------------------------------------------


def _weekday_sessions(start: date, end: date) -> tuple[date, ...]:
    sessions: list[date] = []
    cursor = start
    while cursor <= end:
        if cursor.weekday() < 5:
            sessions.append(cursor)
        cursor = date.fromordinal(cursor.toordinal() + 1)
    return tuple(sessions)


def _basic_sessions() -> tuple[date, ...]:
    return _weekday_sessions(BASIC_START, BASIC_END)


def _bar(session_date: date, close: Decimal, previous_close: Decimal | None) -> DailyBar:
    available_at = datetime.combine(session_date, time(15, 5), tzinfo=UTC)
    return DailyBar(
        schema_version="v1",
        instrument_id=INSTRUMENT,
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
        provider_evidence_id="replay-test-bars",
    )


def _dataset(
    sessions: tuple[date, ...], *, duplicate_bar_on: date | None = None
) -> CanonicalDataset:
    """One canonical dataset over ``sessions``; ``duplicate_bar_on`` injects
    the ambiguous-fact condition a corrupted provider snapshot could carry."""
    bars: list[DailyBar] = []
    previous_close: Decimal | None = None
    for index, session_date in enumerate(sessions):
        close = Decimal("2.00") + Decimal(index) * Decimal("0.01")
        bar = _bar(session_date, close, previous_close)
        bars.append(bar)
        if session_date == duplicate_bar_on:
            bars.append(bar)
        previous_close = close
    session_records = tuple(
        TradingSession(
            calendar_id="XSHG",
            session_date=session_date,
            is_open=True,
            note=None,
            snapshot_version="REPLAY-CAL-1",
        )
        for session_date in sessions
    )
    tradability = tuple(
        TradabilityStatus(
            instrument_id=INSTRUMENT,
            session_date=session_date,
            status=TradabilityStatusKind.TRADABLE,
            reason=None,
            availability=Availability(
                information_available_at=datetime.combine(
                    session_date, time(9, 0), tzinfo=UTC
                ),
                retrieved_at=datetime.combine(session_date, time(9, 0), tzinfo=UTC),
                availability_basis=AvailabilityBasis.OBSERVED,
            ),
            provenance="replay-test",
        )
        for session_date in sessions
    )
    return CanonicalDataset(
        daily_bars=tuple(bars),
        sessions=session_records,
        tradability=tradability,
        corporate_actions=(),
        rule_candidates=(),
    )


def _intent_payload() -> dict:
    payload = _minimal_intent_payload()
    payload["warm_up_start"] = BASIC_START.isoformat()
    payload["basic_start"] = BASIC_START.isoformat()
    payload["basic_end"] = BASIC_END.isoformat()
    payload["oos_start"] = "2024-04-01"
    payload["oos_end"] = "2024-06-28"
    # Deliberately lenient gate so a healthy deterministic run is BASIC_PASS.
    payload["basic_promotion_rule"] = {
        "min_nav_observations": "20",
        "min_excess_total_return_vs_benchmark": "-1.00",
        "max_drawdown_floor": "-1.00",
        "max_turnover": "100",
    }
    return payload


def _basic_intent() -> CandidateIntent:
    return CandidateIntent.from_dict(_intent_payload())


def _receipt(dataset: CanonicalDataset) -> BasicSnapshotReceipt:
    session_dates = [session.session_date for session in dataset.sessions]
    return BasicSnapshotReceipt(
        snapshot_id="0" * 64,
        dataset_digest="sha256:" + "0" * 64,
        min_session=min(session_dates) if session_dates else BASIC_START,
        max_session=max(session_dates) if session_dates else BASIC_END,
        instrument_ids=(INSTRUMENT,),
        quality_status="PASS",
        annual_schedule=None,
    )


def _basic_wiring(dataset: CanonicalDataset | None = None) -> BasicWiring:
    resolved = dataset if dataset is not None else _dataset(_basic_sessions())
    return build_basic_wiring(
        resolved, _basic_intent(), _receipt(resolved), master=default_m0_master()
    )


def _run_variant(wiring: BasicWiring, intent: CandidateIntent) -> BasicRunOutcome:
    return run_basic_variant(
        wiring,
        intent,
        VARIANT_ID,
        intent.variant_parameters[VARIANT_ID],
        benchmark_total_return=Decimal("0.05"),
    )


def _persist_outcome(
    outcome: BasicRunOutcome, *, root: Path, lineage_id: str
) -> Path:
    """Persist one outcome the way the architecture requires: an immutable
    run directory plus one catalog entry per artifact. Unit-level mirror of
    the CLI persistence path."""
    runs_root = root / lineage_id / "runs"
    identity = str(outcome.manifest_payload["identity_digest"])
    attempt = next_attempt_for(runs_root, identity)
    run_dir = runs_root / run_id_for(identity, attempt)
    run_dir.mkdir(parents=True)
    digests = {
        "manifest.json": write_new_json(run_dir / "manifest.json", outcome.manifest_payload),
        "result.json": write_new_json(run_dir / "result.json", outcome.result_payload),
        "report.json": write_new_json(run_dir / "report.json", outcome.report_payload),
    }
    for name, digest in digests.items():
        append_entry(
            root / "catalog",
            {
                "lineage_id": lineage_id,
                "artifact_type": "BASIC_RUN",
                "ref": run_dir.relative_to(root).as_posix() + "/" + name,
                "status": outcome.status,
                "variant_id": outcome.variant_id,
                "digests": {name: digest},
            },
        )
    return run_dir


def _field_digest(seed: int) -> str:
    return "sha256:" + f"{seed:064x}"


def _manifest() -> ResearchRunManifest:
    return ResearchRunManifest(
        manifest_schema_version=RUN_MANIFEST_SCHEMA_VERSION,
        lineage_id="replay-lineage",
        intent_digest=_field_digest(1),
        strategy_id="etf-absolute-trend",
        strategy_version="v1",
        strategy_identity_digest=_field_digest(2),
        implementation_digest=_field_digest(3),
        parameters_digest=_field_digest(4),
        code_commit="9ba86e4",
        dependency_digest=_field_digest(5),
        split_digest=_field_digest(6),
        snapshot_digest=_field_digest(7),
        universe_schedule_digest=_field_digest(8),
        benchmark_spec_digest=_field_digest(9),
        cost_spec_digest=_field_digest(10),
        metric_convention_digest=_field_digest(11),
        kernel_identity_digest=_field_digest(12),
        output_scope="BASIC",
        random_seed=0,
    )


# --- provider empty/partial snapshot distinctions ------------------------------


def test_empty_snapshot_fails_typed() -> None:
    empty = CanonicalDataset(
        daily_bars=(), sessions=(), tradability=(), corporate_actions=(), rule_candidates=()
    )

    with pytest.raises(RunWiringError, match="no calendar sessions"):
        _basic_wiring(empty)


def test_no_open_sessions_inside_basic_window_fails_typed() -> None:
    outside = _dataset(_weekday_sessions(date(2024, 4, 1), date(2024, 4, 30)))

    with pytest.raises(
        RunWiringError, match="no open calendar sessions inside the Basic window"
    ):
        _basic_wiring(outside)


def test_partial_snapshot_stopping_inside_basic_window_fails_typed() -> None:
    """Data stopping inside the Basic window is a provider failure, never a
    shorter successful window: the wiring refuses it typed."""
    partial = _dataset(_weekday_sessions(BASIC_START, date(2024, 2, 15)))

    with pytest.raises(RunWiringError, match="before the Basic end"):
        _basic_wiring(partial)


# --- typed failure retention: data vs kernel -----------------------------------


def test_provider_data_failure_is_retained_as_run_failed_data() -> None:
    """Ambiguous market facts are a provider data failure: the run is
    retained as a typed ``RUN_FAILED_DATA`` outcome, not a kernel failure."""
    sessions = _basic_sessions()
    dataset = _dataset(sessions, duplicate_bar_on=sessions[5])

    outcome = _run_variant(_basic_wiring(dataset), _basic_intent())

    assert outcome.status == RUN_STATUS_RUN_FAILED_DATA
    assert any("AmbiguousMarketFactError" in reason for reason in outcome.reason_codes)
    assert outcome.result_payload["status"] == RUN_STATUS_RUN_FAILED_DATA
    assert outcome.report_payload["status"] == RUN_STATUS_RUN_FAILED_DATA
    assert str(outcome.manifest_payload["identity_digest"]).startswith("sha256:")
    assert outcome.result_digest == digest_of_bytes(
        canonical_json_bytes(outcome.result_payload)
    )


def test_provider_failure_is_never_recorded_as_a_successful_run() -> None:
    sessions = _basic_sessions()
    dataset = _dataset(sessions, duplicate_bar_on=sessions[5])

    outcome = _run_variant(_basic_wiring(dataset), _basic_intent())

    assert outcome.status not in (RUN_STATUS_BASIC_PASS, RUN_STATUS_REJECTED_BASIC)
    assert "metrics" not in outcome.result_payload
    assert outcome.reason_codes


def test_compile_failure_is_retained_as_run_failed_kernel() -> None:
    """An unknown canonical strategy id fails the run closed and is retained
    as a typed ``RUN_FAILED_KERNEL`` outcome with its full artifact set."""
    payload = _intent_payload()
    payload["strategy_id"] = "no-such-strategy"

    outcome = _run_variant(_basic_wiring(), CandidateIntent.from_dict(payload))

    assert outcome.status == RUN_STATUS_RUN_FAILED_KERNEL
    assert "RunWiringError" in outcome.reason_codes[0]
    assert "unknown canonical strategy id" in outcome.reason_codes[0]
    assert outcome.result_payload["status"] == RUN_STATUS_RUN_FAILED_KERNEL
    assert outcome.report_payload["status"] == RUN_STATUS_RUN_FAILED_KERNEL
    assert str(outcome.manifest_payload["identity_digest"]).startswith("sha256:")
    assert outcome.result_digest == digest_of_bytes(
        canonical_json_bytes(outcome.result_payload)
    )


# --- deterministic replay -------------------------------------------------------


def test_same_kernel_rerun_produces_identical_result_digest() -> None:
    """Two isolated runs of the same variant against the same wiring replay
    byte-identically: same result digest, payloads, and status."""
    wiring = _basic_wiring()
    intent = _basic_intent()

    first = _run_variant(wiring, intent)
    second = _run_variant(wiring, intent)

    assert first.status == second.status == RUN_STATUS_BASIC_PASS
    assert first.result_digest == second.result_digest
    assert first.result_payload == second.result_payload
    assert first.manifest_payload == second.manifest_payload
    assert first.report_payload == second.report_payload


def test_rerun_persists_a_new_attempt_and_retains_both_runs(tmp_path: Path) -> None:
    """The rerun shares one manifest identity but is retained as attempt 2 in
    a new deterministic run directory; both attempts verify cleanly."""
    root = tmp_path / "experiments"
    wiring = _basic_wiring()
    intent = _basic_intent()

    first = _run_variant(wiring, intent)
    first_dir = _persist_outcome(first, root=root, lineage_id=LINEAGE_ID)
    second = _run_variant(wiring, intent)
    second_dir = _persist_outcome(second, root=root, lineage_id=LINEAGE_ID)

    identity = str(first.manifest_payload["identity_digest"])
    assert first.status == second.status == RUN_STATUS_BASIC_PASS
    assert first.result_digest == second.result_digest
    assert first_dir != second_dir
    assert first_dir.name == run_id_for(identity, 1)
    assert second_dir.name == run_id_for(identity, 2)
    assert (first_dir / "result.json").read_bytes() == (
        second_dir / "result.json"
    ).read_bytes()
    entries = read_entries(root / "catalog")
    assert [entry["status"] for entry in entries] == [RUN_STATUS_BASIC_PASS] * 6
    assert verify_catalog(root / "catalog", root).status == "PASS"


# --- ResearchRunManifest identity mutation matrix -------------------------------


def test_every_manifest_identity_field_mutation_changes_the_run_identity() -> None:
    manifest = _manifest()
    assert {field.name for field in dataclasses.fields(ResearchRunManifest)} == set(
        _RUN_MANIFEST_IDENTITY_FIELDS
    )
    for index, field_name in enumerate(_RUN_MANIFEST_IDENTITY_FIELDS):
        if field_name == "manifest_schema_version":
            # No alternative schema version validates: any change fails closed
            # instead of silently reusing the run identity.
            with pytest.raises(InvalidResearchRunManifestError):
                dataclasses.replace(
                    manifest, manifest_schema_version="research-run-manifest-0"
                )
            continue
        current = getattr(manifest, field_name)
        if field_name == "output_scope":
            replacement: object = "OOS"
        elif field_name == "random_seed":
            replacement = int(current) + 1
        elif isinstance(current, str) and current.startswith("sha256:"):
            replacement = _field_digest(100 + index)
        else:
            replacement = f"{current}-mutated"
        assert replacement != current, field_name

        mutated = dataclasses.replace(manifest, **{field_name: replacement})  # type: ignore[arg-type]

        assert mutated.identity_digest != manifest.identity_digest, field_name


def test_manifest_round_trips_through_its_payload() -> None:
    manifest = _manifest()

    payload = manifest.to_payload()
    restored = ResearchRunManifest.from_dict(payload)

    assert restored == manifest
    assert restored.identity_digest == manifest.identity_digest
    assert payload["identity_digest"] == manifest.identity_digest


def test_manifest_fails_closed_on_missing_or_invalid_fields() -> None:
    manifest = _manifest()

    missing = manifest.to_payload()
    del missing["split_digest"]
    with pytest.raises(InvalidResearchRunManifestError, match="split_digest"):
        ResearchRunManifest.from_dict(missing)

    missing_seed = manifest.to_payload()
    del missing_seed["random_seed"]
    with pytest.raises(InvalidResearchRunManifestError, match="random_seed"):
        ResearchRunManifest.from_dict(missing_seed)

    invalid_digest = manifest.to_payload()
    invalid_digest["parameters_digest"] = "0123"
    with pytest.raises(InvalidResearchRunManifestError):
        ResearchRunManifest.from_dict(invalid_digest)

    invalid_scope = manifest.to_payload()
    invalid_scope["output_scope"] = "FULL"
    with pytest.raises(InvalidResearchRunManifestError):
        ResearchRunManifest.from_dict(invalid_scope)

    invalid_seed = manifest.to_payload()
    invalid_seed["random_seed"] = "0"
    with pytest.raises(InvalidResearchRunManifestError):
        ResearchRunManifest.from_dict(invalid_seed)
