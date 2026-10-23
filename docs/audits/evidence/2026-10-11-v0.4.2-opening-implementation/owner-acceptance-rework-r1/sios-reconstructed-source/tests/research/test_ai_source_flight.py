"""M1 Task 8: real-source provenance and cheap-screen flight tests."""

import json
from pathlib import Path

import pytest

from systematic_investing.research.catalog import read_entries
from systematic_investing.research.cli import main


def _valid_source_record() -> dict[str, object]:
    return {
        "source_flight_schema_version": "m1-ai-source-flight-1",
        "source_id": "source-flight-test-1",
        "url": "https://example.com/research/time-series-momentum",
        "title": "Time-Series Momentum",
        "author_or_publisher": "Example Research",
        "accessed_date": "2026-09-21",
        "license_or_rights_posture": (
            "Public source metadata only; repository stores no copied paper text."
        ),
        "summary": (
            "The project-authored summary says own past returns may contain a "
            "persistent trend signal."
        ),
        "hypothesis": (
            "A pre-registered monthly trend rule over the M1 ETF set can improve "
            "risk-adjusted returns after declared costs versus CASH_0."
        ),
        "asset": "ETF",
        "horizon": "monthly decisions with a 6-to-12 month lookback",
        "data_requirements": [
            "point-in-time daily closes",
            "trading calendar",
            "execution and cost facts",
        ],
        "cheap_screen_verdict": "SCREEN_PASS",
        "cheap_screen_reason_codes": [],
    }


def _run_main(argv: list[str]) -> int:
    """Keep argparse's missing-command failure visible as a test failure."""
    try:
        return main(argv)
    except SystemExit as error:
        return int(error.code)


def test_source_screen_records_real_source_provenance_and_verdict(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source_path = tmp_path / "source.json"
    source_path.write_text(
        json.dumps(_valid_source_record(), ensure_ascii=False), encoding="utf-8"
    )
    root = tmp_path / "experiments"

    assert (
        _run_main(
            [
                "source-screen",
                "--source-record",
                str(source_path),
                "--root",
                str(root),
            ]
        )
        == 0
    )

    output = json.loads(capsys.readouterr().out)
    assert output["command"] == "source-screen"
    assert output["verdict"] == "SCREEN_PASS"
    assert output["source_id"] == "source-flight-test-1"
    assert output["source_digest"].startswith("sha256:")
    assert output["screen_digest"].startswith("sha256:")
    entries = read_entries(root / "catalog")
    assert len(entries) == 1
    assert entries[0]["artifact_type"] == "AI_SOURCE_SCREEN"
    assert entries[0]["status"] == "SCREEN_PASS"


def test_source_screen_rejects_missing_rights_before_any_implementation(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    payload = _valid_source_record()
    del payload["license_or_rights_posture"]
    source_path = tmp_path / "source.json"
    source_path.write_text(json.dumps(payload), encoding="utf-8")

    assert (
        _run_main(
            [
                "source-screen",
                "--source-record",
                str(source_path),
                "--root",
                str(tmp_path / "experiments"),
            ]
        )
        == 0
    )

    output = json.loads(capsys.readouterr().out)
    assert output["verdict"] == "REJECTED_BEFORE_IMPLEMENTATION"
    assert "MISSING_LICENSE_OR_RIGHTS_POSTURE" in output["reason_codes"]


def test_source_screen_requires_a_declared_falsifiable_hypothesis(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    payload = _valid_source_record()
    del payload["hypothesis"]
    source_path = tmp_path / "source.json"
    source_path.write_text(json.dumps(payload), encoding="utf-8")

    assert (
        _run_main(
            [
                "source-screen",
                "--source-record",
                str(source_path),
                "--root",
                str(tmp_path / "experiments"),
            ]
        )
        == 0
    )

    output = json.loads(capsys.readouterr().out)
    assert output["verdict"] == "REJECTED_BEFORE_IMPLEMENTATION"
    assert "MISSING_HYPOTHESIS" in output["reason_codes"]


def test_committed_real_source_flight_record_is_screenable(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repository_root = Path(__file__).parents[2]
    source_path = repository_root / "research" / "source-flights" / (
        "m1-ai-source-flight-1.json"
    )

    assert (
        _run_main(
            [
                "source-screen",
                "--source-record",
                str(source_path),
                "--root",
                str(tmp_path / "experiments"),
            ]
        )
        == 0
    )

    output = json.loads(capsys.readouterr().out)
    assert output["verdict"] == "SCREEN_PASS"
    assert output["source_id"] == "m1-ai-source-flight-1"
