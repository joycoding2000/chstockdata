"""Run-manifest identity tests for exact M0 replay claims."""

from dataclasses import replace
from hashlib import sha256

import pytest

from systematic_investing.domain import runs


def digest(label: str) -> str:
    return "sha256:" + sha256(label.encode("utf-8")).hexdigest()


def manifest():
    return runs.RunManifest(
        manifest_schema_version="m0-run-manifest-1",
        run_type="BACKTEST",
        code_commit="a" * 40,
        dependency_lock_digest=digest("dependencies-v1"),
        data_snapshot_digest=digest("snapshot-v1"),
        fee_config_digest=digest("fees-v1"),
        calendar_digest=digest("calendar-v1"),
        execution_model_version="NEXT_SESSION_OPEN-v1",
        rule_versions=(
            ("instrument-master", "m0-im-v1"),
            ("portfolio", "m0-portfolio-v1"),
            ("risk", "m0-risk-v1"),
        ),
        metric_convention_digest=digest("metrics-v1"),
        benchmark_identity="NONE",
        random_seed=0,
    )


@pytest.mark.parametrize(
    ("field_name", "changed_value"),
    [
        ("data_snapshot_digest", digest("snapshot-v2")),
        ("fee_config_digest", digest("fees-v2")),
        ("calendar_digest", digest("calendar-v2")),
        ("execution_model_version", "NEXT_SESSION_OPEN-v2"),
        ("dependency_lock_digest", digest("dependencies-v2")),
        (
            "rule_versions",
            (
                ("instrument-master", "m0-im-v2"),
                ("portfolio", "m0-portfolio-v1"),
                ("risk", "m0-risk-v1"),
            ),
        ),
    ],
)
def test_every_replay_input_change_creates_a_new_manifest_identity(
    field_name: str, changed_value: object
) -> None:
    original = manifest()

    changed = replace(original, **{field_name: changed_value})

    assert changed.identity_digest != original.identity_digest


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("code_commit", ""),
        ("dependency_lock_digest", ""),
        ("data_snapshot_digest", ""),
        ("benchmark_identity", "CSI300"),
    ],
)
def test_missing_replay_identity_or_unapproved_benchmark_fails_closed(
    field_name: str, invalid_value: object
) -> None:
    with pytest.raises(runs.InvalidRunManifestError):
        replace(manifest(), **{field_name: invalid_value})
