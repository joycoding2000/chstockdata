"""Immutable retention of failed and successful runs.

Every run — pass, rejection, or failure — is retained exactly once: one
immutable run directory (manifest, result, report) plus one catalog entry per
artifact whose recorded digest verifies against the artifact bytes. Deleting
a retained experiment, reusing a catalog sequence, overwriting an artifact,
or counting a half-persisted run directory is a loud failure, never a silent
state.
"""

import shutil
from decimal import Decimal
from pathlib import Path

import pytest
from test_research_reproducibility import (
    LINEAGE_ID,
    _basic_intent,
    _basic_wiring,
    _persist_outcome,
)

from systematic_investing.research.artifacts import (
    ArtifactIntegrityError,
    canonical_json_bytes,
    create_new_directory,
    digest_of_bytes,
    next_attempt_for,
    read_json,
    run_id_for,
    write_new_json,
)
from systematic_investing.research.catalog import (
    CatalogError,
    append_entry,
    read_entries,
    verify_catalog,
)
from systematic_investing.research.runner import (
    RUN_STATUS_BASIC_PASS,
    RUN_STATUS_RUN_FAILED_KERNEL,
    run_basic_variant,
)


def _write_complete_run(runs_root: Path, identity: str, name: str) -> None:
    payload = {"identity_digest": identity}
    write_new_json(runs_root / name / "manifest.json", payload)
    write_new_json(runs_root / name / "result.json", payload)
    write_new_json(runs_root / name / "report.json", payload)


def _append_run_entry(catalog_dir: Path, ref: str) -> dict[str, object]:
    return append_entry(
        catalog_dir,
        {
            "lineage_id": "lineage-a",
            "artifact_type": "BASIC_RUN",
            "ref": ref,
            "status": "BASIC_PASS",
            "digests": {"manifest": "sha256:" + "1" * 64},
        },
    )


# --- create-new artifact semantics ---------------------------------------------


def test_write_new_json_is_create_new_with_canonical_digest(tmp_path: Path) -> None:
    path = tmp_path / "artifacts" / "result.json"
    payload = {"status": "BASIC_PASS", "observation_count": 62}

    digest = write_new_json(path, payload)

    assert digest == digest_of_bytes(path.read_bytes())
    assert digest == digest_of_bytes(canonical_json_bytes(payload))
    assert read_json(path) == payload


def test_existing_artifact_paths_are_never_overwritten(tmp_path: Path) -> None:
    path = tmp_path / "result.json"
    original = {"status": "BASIC_PASS"}
    write_new_json(path, original)
    original_bytes = path.read_bytes()

    with pytest.raises(ArtifactIntegrityError):
        write_new_json(path, {"status": "RUN_FAILED_KERNEL"})
    assert path.read_bytes() == original_bytes

    directory = tmp_path / "runs"
    create_new_directory(directory)
    marker = directory / "keep.txt"
    marker.write_text("keep", encoding="utf-8")
    with pytest.raises(ArtifactIntegrityError):
        create_new_directory(directory)
    assert marker.read_text(encoding="utf-8") == "keep"


# --- attempt counts and deterministic run ids -----------------------------------


def test_next_attempt_counts_complete_runs_per_manifest_identity(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    identity_a = "sha256:" + "a" * 64
    identity_b = "sha256:" + "b" * 64
    _write_complete_run(runs_root, identity_a, "run-1")
    _write_complete_run(runs_root, identity_a, "run-2")
    _write_complete_run(runs_root, identity_b, "run-3")

    assert next_attempt_for(runs_root, identity_a) == 3
    assert next_attempt_for(runs_root, identity_b) == 2
    assert next_attempt_for(runs_root, "sha256:" + "c" * 64) == 1


def test_run_id_is_deterministic_and_attempt_scoped() -> None:
    identity = "sha256:" + "a" * 64

    assert run_id_for(identity, 1) == run_id_for(identity, 1)
    assert run_id_for(identity, 1).startswith("run-")
    assert run_id_for(identity, 2) != run_id_for(identity, 1)
    assert run_id_for(identity, 1) != run_id_for("sha256:" + "b" * 64, 1)


# --- report-persistence failures fail closed ------------------------------------


def test_next_attempt_fails_closed_when_run_directory_missing_result(
    tmp_path: Path,
) -> None:
    """A run directory without result.json is half-persisted: it can never be
    counted as an attempt or silently re-attempted."""
    runs_root = tmp_path / "runs"
    identity = "sha256:" + "a" * 64
    write_new_json(runs_root / "run-1" / "manifest.json", {"identity_digest": identity})

    with pytest.raises(ArtifactIntegrityError, match=r"missing result\.json"):
        next_attempt_for(runs_root, identity)


def test_next_attempt_fails_closed_when_run_directory_missing_report(
    tmp_path: Path,
) -> None:
    runs_root = tmp_path / "runs"
    identity = "sha256:" + "a" * 64
    write_new_json(runs_root / "run-1" / "manifest.json", {"identity_digest": identity})
    write_new_json(runs_root / "run-1" / "result.json", {"status": "BASIC_PASS"})

    with pytest.raises(ArtifactIntegrityError, match=r"missing report\.json"):
        next_attempt_for(runs_root, identity)


def test_half_persisted_run_is_detected_not_silently_counted(tmp_path: Path) -> None:
    """The loud failure names the offending run directory even when complete
    sibling runs exist."""
    runs_root = tmp_path / "runs"
    identity = "sha256:" + "a" * 64
    _write_complete_run(runs_root, identity, "run-1")
    write_new_json(runs_root / "run-2" / "manifest.json", {"identity_digest": identity})

    with pytest.raises(ArtifactIntegrityError, match="run-2"):
        next_attempt_for(runs_root, identity)


# --- catalog sequence uniqueness and fail-closed reads ---------------------------


def test_catalog_gap_non_numeric_and_misrecorded_entries_fail_closed(
    tmp_path: Path,
) -> None:
    catalog_dir = tmp_path / "catalog"
    _append_run_entry(catalog_dir, "lineage-a/runs/run-1/manifest.json")
    _append_run_entry(catalog_dir, "lineage-a/runs/run-2/manifest.json")
    _append_run_entry(catalog_dir, "lineage-a/runs/run-3/manifest.json")
    (catalog_dir / "000002.json").unlink()
    with pytest.raises(CatalogError, match="not contiguous"):
        read_entries(catalog_dir)

    non_numeric = tmp_path / "catalog-non-numeric"
    _append_run_entry(non_numeric, "lineage-a/runs/run-1/manifest.json")
    (non_numeric / "notes.json").write_text("{}", encoding="utf-8")
    with pytest.raises(CatalogError, match="non-numeric"):
        read_entries(non_numeric)

    misrecorded = tmp_path / "catalog-misrecorded"
    entry = _append_run_entry(misrecorded, "lineage-a/runs/run-1/manifest.json")
    tampered = dict(entry)
    tampered["sequence"] = 99
    (misrecorded / "000001.json").write_bytes(canonical_json_bytes(tampered))
    with pytest.raises(CatalogError, match="records sequence"):
        read_entries(misrecorded)


def test_failed_catalog_append_never_reuses_or_skips_sequences(tmp_path: Path) -> None:
    catalog_dir = tmp_path / "catalog"
    first = _append_run_entry(catalog_dir, "lineage-a/runs/run-1/manifest.json")
    second = _append_run_entry(catalog_dir, "lineage-a/runs/run-2/manifest.json")
    assert (first["sequence"], second["sequence"]) == (1, 2)

    with pytest.raises(CatalogError):
        append_entry(
            catalog_dir,
            {
                "lineage_id": "lineage-a",
                "artifact_type": "BASIC_RUN",
                "ref": "lineage-a/runs/run-1/manifest.json",
                "status": "BASIC_PASS",
                "digests": {"manifest": "sha256:" + "9" * 64},
            },
            sequence=1,
        )

    third = _append_run_entry(catalog_dir, "lineage-a/runs/run-3/manifest.json")
    assert third["sequence"] == 3


# --- digest mutation and deletion detection --------------------------------------


def test_verify_catalog_fails_on_missing_and_mutated_artifacts(tmp_path: Path) -> None:
    root = tmp_path
    artifact = root / "lineage-a" / "runs" / "run-1" / "result.json"
    digest = write_new_json(artifact, {"status": "BASIC_PASS"})
    catalog_dir = root / "catalog"
    append_entry(
        catalog_dir,
        {
            "lineage_id": "lineage-a",
            "artifact_type": "BASIC_RUN",
            "ref": "lineage-a/runs/run-1/result.json",
            "status": "BASIC_PASS",
            "digests": {"result": digest},
        },
    )
    assert verify_catalog(catalog_dir, root).status == "PASS"

    artifact.write_bytes(b'{"status": "tampered"}')
    report = verify_catalog(catalog_dir, root)
    assert report.status == "FAIL"
    assert any("result.json" in finding for finding in report.findings)

    missing_root = tmp_path / "missing"
    missing_catalog = missing_root / "catalog"
    append_entry(
        missing_catalog,
        {
            "lineage_id": "lineage-a",
            "artifact_type": "BASIC_RUN",
            "ref": "lineage-a/runs/run-1/result.json",
            "status": "BASIC_PASS",
            "digests": {"result": "sha256:" + "2" * 64},
        },
    )
    missing_report = verify_catalog(missing_catalog, missing_root)
    assert missing_report.status == "FAIL"
    assert any("missing artifact" in finding for finding in missing_report.findings)


# --- failed-run retention ---------------------------------------------------------


def test_failed_run_is_retained_as_immutable_artifacts_and_catalog_entries(
    tmp_path: Path,
) -> None:
    """A kernel failure is retained exactly like a pass: a typed status, a
    complete manifest/result/report set, and its own catalog entries."""
    root = tmp_path / "experiments"
    wiring = _basic_wiring()
    intent = _basic_intent()

    outcome = run_basic_variant(
        wiring, intent, "broken", {"sma_sessions": "abc"}, benchmark_total_return=Decimal("0.05")
    )

    assert outcome.status == RUN_STATUS_RUN_FAILED_KERNEL
    assert outcome.reason_codes
    assert outcome.result_payload["status"] == RUN_STATUS_RUN_FAILED_KERNEL
    assert outcome.report_payload["status"] == RUN_STATUS_RUN_FAILED_KERNEL
    assert str(outcome.manifest_payload["identity_digest"]).startswith("sha256:")
    assert outcome.result_digest == digest_of_bytes(
        canonical_json_bytes(outcome.result_payload)
    )

    run_dir = _persist_outcome(outcome, root=root, lineage_id=LINEAGE_ID)
    for name in ("manifest.json", "result.json", "report.json"):
        assert (run_dir / name).exists()
    entries = read_entries(root / "catalog")
    assert len(entries) == 3
    assert all(entry["status"] == RUN_STATUS_RUN_FAILED_KERNEL for entry in entries)
    assert all(entry["status"] != RUN_STATUS_BASIC_PASS for entry in entries)
    assert verify_catalog(root / "catalog", root).status == "PASS"


def test_deleting_a_failed_experiment_breaks_verification(tmp_path: Path) -> None:
    """Deleting a retained failed experiment is detectable: the catalog still
    references the missing artifacts and verification fails naming them."""
    root = tmp_path / "experiments"
    outcome = run_basic_variant(
        _basic_wiring(),
        _basic_intent(),
        "broken",
        {"sma_sessions": "abc"},
        benchmark_total_return=Decimal("0.05"),
    )
    run_dir = _persist_outcome(outcome, root=root, lineage_id=LINEAGE_ID)
    assert verify_catalog(root / "catalog", root).status == "PASS"

    shutil.rmtree(run_dir)

    report = verify_catalog(root / "catalog", root)
    assert report.status == "FAIL"
    findings = " ".join(report.findings)
    assert "missing artifact" in findings
    assert LINEAGE_ID in findings


def test_failed_run_and_successful_run_are_retained_side_by_side(tmp_path: Path) -> None:
    """A failed attempt and a successful attempt bind different manifest
    identities (placeholder vs resolved strategy identity); each is counted
    per its own identity and both stay retained."""
    root = tmp_path / "experiments"
    intent = _basic_intent()
    failed = run_basic_variant(
        _basic_wiring(),
        intent,
        "broken",
        {"sma_sessions": "abc"},
        benchmark_total_return=Decimal("0.05"),
    )
    failed_dir = _persist_outcome(failed, root=root, lineage_id=LINEAGE_ID)
    replayed = run_basic_variant(
        _basic_wiring(),
        intent,
        "sma-2",
        intent.variant_parameters["sma-2"],
        benchmark_total_return=Decimal("0.05"),
    )
    replayed_dir = _persist_outcome(replayed, root=root, lineage_id=LINEAGE_ID)

    runs_root = root / LINEAGE_ID / "runs"
    failed_identity = str(failed.manifest_payload["identity_digest"])
    replayed_identity = str(replayed.manifest_payload["identity_digest"])
    assert failed.status == RUN_STATUS_RUN_FAILED_KERNEL
    assert replayed.status == RUN_STATUS_BASIC_PASS
    assert failed_identity != replayed_identity
    assert failed_dir.name == run_id_for(failed_identity, 1)
    assert replayed_dir.name == run_id_for(replayed_identity, 1)
    assert failed_dir != replayed_dir
    assert next_attempt_for(runs_root, failed_identity) == 2
    assert next_attempt_for(runs_root, replayed_identity) == 2
    assert len(read_entries(root / "catalog")) == 6
