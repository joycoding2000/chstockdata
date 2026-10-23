"""Task 7 asset-class OOS selection and final-outcome contracts."""

import json
from pathlib import Path

import pytest
from test_candidate_intent import _minimal_intent_payload

from systematic_investing.research.artifacts import read_json
from systematic_investing.research.catalog import read_entries
from systematic_investing.research.cli import main
from systematic_investing.research.oos import OosError
from systematic_investing.research.reporting import (
    AssetClassOutcome,
    persist_asset_class_outcome,
)


def _write_candidate(
    root: Path,
    *,
    asset_class: str = "ETF",
    lineage_id: str = "test-lineage",
    selected_variant_id: str | None = None,
    attempts: list[dict[str, str]] | None = None,
) -> Path:
    payload = _minimal_intent_payload()
    payload["asset_class"] = asset_class
    payload["lineage_id"] = lineage_id
    payload["intent_id"] = f"{lineage_id}-v1"
    if asset_class == "STOCK":
        payload["sleeve"] = "SATELLITE"
        payload["universe_policy"] = {
            "policy_name": "STOCK_ANNUAL_PIT_TOP50_V1",
            "instrument_ids": [],
        }
        payload["benchmark"] = {
            "kind": "STOCK_ANNUAL_SCHEDULE_EQUAL_WEIGHT",
            "instrument_ids": [],
            "rebalance": "ANNUAL",
        }
        payload["known_limitations"] = [
            "DIVIDEND_TAX_NOT_MODELED: test limitation",
        ]

    lineage_dir = root / lineage_id
    lineage_dir.mkdir(parents=True, exist_ok=True)
    (lineage_dir / "intent.json").write_text(
        json.dumps(payload, sort_keys=True), encoding="utf-8"
    )
    selection = {
        "selection_schema_version": "research-basic-selection-1",
        "selected_variant_id": selected_variant_id,
        "status": "SELECTED" if selected_variant_id else "NO_BASIC_PASS",
        "attempts": attempts or [],
    }
    selection_dir = lineage_dir / "basic-selection"
    selection_dir.mkdir()
    (selection_dir / "selection.json").write_text(
        json.dumps(selection, sort_keys=True), encoding="utf-8"
    )
    return lineage_dir / "intent.json"


def test_select_oos_reports_no_candidate_without_materializing_oos(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "experiments"
    _write_candidate(root, attempts=[{"variant_id": "sma-2", "status": "REJECTED_BASIC"}])

    assert main(["select-oos", "--asset", "ETF", "--root", str(root)]) == 0

    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "NO_OOS_ELIGIBLE_CANDIDATE"
    assert output["asset_class"] == "ETF"
    assert not (root / "outcomes").exists()
    assert not any(path.name == "oos" for path in root.rglob("oos"))


def test_select_oos_exposes_the_priority_selected_variant(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "experiments"
    _write_candidate(
        root,
        selected_variant_id="sma-2",
        attempts=[
            {"variant_id": "sma-2", "status": "BASIC_PASS"},
            {"variant_id": "sma-3", "status": "BASIC_PASS"},
        ],
    )

    assert main(["select-oos", "--asset", "ETF", "--root", str(root)]) == 0

    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "OOS_ELIGIBLE"
    assert output["candidate_id"] == "test-lineage"
    assert output["selected_variant"] == "sma-2"
    assert output["priority_rank"] == 0


def test_select_oos_refuses_two_independent_eligible_lineages(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "experiments"
    for lineage_id in ("first-lineage", "second-lineage"):
        _write_candidate(
            root,
            lineage_id=lineage_id,
            selected_variant_id="sma-2",
            attempts=[{"variant_id": "sma-2", "status": "BASIC_PASS"}],
        )

    assert main(["select-oos", "--asset", "ETF", "--root", str(root)]) != 0

    error = capsys.readouterr().err
    assert "OOS_CANDIDATE_AMBIGUOUS" in error


def test_no_oos_eligible_is_idempotent_and_catalogues_one_outcome(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "experiments"
    _write_candidate(root, attempts=[{"variant_id": "sma-2", "status": "REJECTED_BASIC"}])

    argv = ["no-oos-eligible", "--asset", "ETF", "--root", str(root)]
    assert main(argv) == 0
    capsys.readouterr()
    assert main(argv) == 0
    capsys.readouterr()

    outcome_files = list((root / "outcomes").glob("*.json"))
    assert len(outcome_files) == 1
    assert read_json(outcome_files[0])["status"] == "NO_OOS_ELIGIBLE_CANDIDATE"
    entries = read_entries(root / "catalog")
    assert len([entry for entry in entries if entry["artifact_type"] == "OOS_OUTCOME"]) == 1


def test_asset_class_outcome_is_immutable_after_first_canonical_verdict(
    tmp_path: Path,
) -> None:
    root = tmp_path / "experiments"
    survivor = AssetClassOutcome(
        asset_class="ETF",
        status="SURVIVOR",
        candidate_id="test-lineage",
        selected_variant_id="sma-2",
        freeze_id="freeze-test",
        reason_codes=(),
        known_limitations=(),
    )
    persist_asset_class_outcome(root, survivor)

    with pytest.raises(OosError):
        persist_asset_class_outcome(
            root,
            AssetClassOutcome(
                asset_class="ETF",
                status="REJECTED_OOS",
                candidate_id="other-lineage",
                selected_variant_id="sma-3",
                freeze_id="freeze-other",
                reason_codes=("different-verdict",),
                known_limitations=(),
            ),
        )
