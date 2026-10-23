"""Integration tests: deterministic replay from immutable snapshots.

Every golden scenario is persisted twice in isolated temporary directories,
replayed with checksum verification, and re-run from the replayed canonical
facts. The normalized ledger/order/fill/NAV/metrics evidence and its digest
must be identical to the in-memory run; the snapshot manifest bytes must be
identical between the two isolated directories. Snapshots are immutable, so a
second persist into the same directory fails closed.
"""

from pathlib import Path

import pytest
from golden_harness import (
    assert_expected,
    discover_scenarios,
    load_scenario,
    normalized_digest,
    normalized_output,
    persist_scenario,
    replay_scenario,
    run_scenario,
)

from systematic_investing.data.snapshots import SnapshotIntegrityError

SCENARIOS = discover_scenarios()


@pytest.mark.parametrize("scenario_id", SCENARIOS)
def test_scenario_replays_identically_from_two_isolated_snapshots(
    scenario_id: str, tmp_path: Path
) -> None:
    scenario = load_scenario(scenario_id)
    if scenario.kind == "metrics":
        return

    for run_name in scenario.expected["runs"]:
        in_memory = run_scenario(scenario, run_name=run_name)

        first_manifest = persist_scenario(tmp_path / "first", in_memory)
        second_manifest = persist_scenario(tmp_path / "second", in_memory)

        assert first_manifest == second_manifest
        assert first_manifest.snapshot_id == second_manifest.snapshot_id
        first_manifest_bytes = (
            tmp_path / "first" / f"{scenario_id}-{run_name}" / "manifest.json"
        ).read_bytes()
        second_manifest_bytes = (
            tmp_path / "second" / f"{scenario_id}-{run_name}" / "manifest.json"
        ).read_bytes()
        assert first_manifest_bytes == second_manifest_bytes

        first_dataset = replay_scenario(tmp_path / "first", scenario_id, run_name)
        second_dataset = replay_scenario(tmp_path / "second", scenario_id, run_name)

        first_replay = run_scenario(scenario, run_name=run_name, dataset=first_dataset)
        second_replay = run_scenario(scenario, run_name=run_name, dataset=second_dataset)

        assert normalized_output(first_replay) == normalized_output(second_replay)
        assert normalized_output(first_replay) == normalized_output(in_memory)
        assert normalized_digest(first_replay) == normalized_digest(second_replay)
        assert normalized_digest(first_replay) == normalized_digest(in_memory)

        assert_expected(first_replay, scenario.expected["runs"][run_name])


def test_snapshot_persistence_is_immutable(tmp_path: Path) -> None:
    scenario = load_scenario("G01")
    outcome = run_scenario(scenario)

    persist_scenario(tmp_path, outcome)

    with pytest.raises(SnapshotIntegrityError):
        persist_scenario(tmp_path, outcome)
