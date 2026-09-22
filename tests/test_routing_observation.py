"""Shared structured provider-observation plumbing contracts."""

import pytest

from chstockdata.capabilities import capability_health_snapshot, reset_capability_health
from chstockdata.fetch_result import (
    FETCH_FAILED_STRUCTURE,
    FETCH_NORMAL_EMPTY,
    FETCH_NOT_CONFIGURED,
    FETCH_SUCCESS,
)
from chstockdata.routing_observation import record_fetch_observation


@pytest.fixture(autouse=True)
def _clean_health_store():
    reset_capability_health()
    yield
    reset_capability_health()


@pytest.mark.parametrize(
    ("status", "expected_health"),
    [
        (FETCH_SUCCESS, "success"),
        (FETCH_NORMAL_EMPTY, "normal_empty"),
        (FETCH_NOT_CONFIGURED, "not_configured"),
    ],
)
def test_records_one_attempt_and_the_mapped_capability_health(status, expected_health):
    attempts = []

    attempt = record_fetch_observation(
        attempts,
        provider="mootdx",
        capability_id="mootdx:bars",
        status=status,
        started_at="2026-09-21T00:00:00+00:00",
        elapsed_ms=7,
        record_count=10 if status == FETCH_SUCCESS else 0,
    )

    assert attempts == [attempt]
    assert attempt.status == status
    assert attempt.record_count == (10 if status == FETCH_SUCCESS else 0)
    assert capability_health_snapshot()["mootdx:bars"].status == expected_health


def test_preserves_structure_failure_details_while_recording_failed_health():
    attempts = []

    attempt = record_fetch_observation(
        attempts,
        provider="mootdx",
        capability_id="mootdx:bars",
        status=FETCH_FAILED_STRUCTURE,
        started_at="2026-09-21T00:00:00+00:00",
        elapsed_ms=7,
        error_type="ValueError",
        message="missing Close",
        error_summary="missing Close",
    )

    assert attempt.error_type == "ValueError"
    assert attempt.message == "missing Close"
    health = capability_health_snapshot()["mootdx:bars"]
    assert health.status == "failed"
    assert health.error_summary == "missing Close"
