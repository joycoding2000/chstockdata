"""Internal plumbing for one structured provider observation.

Routing engines retain all provider ordering, canonicalization, empty and
staleness policy.  This module only records the already-classified fact of a
single provider call as both a ``FetchAttempt`` and capability health entry.
"""

from __future__ import annotations

from datetime import datetime, timezone

from .capabilities import (
    ProviderCapability,
    fetch_status_to_health_status,
    record_capability_health,
)
from .fetch_result import FetchAttempt


def utc_now_iso() -> str:
    """Return the current UTC time in ISO-8601 form for attempt timestamps."""
    return datetime.now(timezone.utc).isoformat()


def elapsed_ms(clock, started_monotonic: float) -> int:
    """Normalize a monotonic elapsed duration to a non-negative millisecond int."""
    return max(0, int((clock() - started_monotonic) * 1000))


def record_fetch_observation(
    attempts: list[FetchAttempt],
    *,
    provider: str,
    capability_id: str,
    status: str,
    started_at: str,
    elapsed_ms: int,
    record_count: int | None = None,
    error_type: str | None = None,
    message: str | None = None,
    error_summary: str | None = None,
) -> FetchAttempt:
    """Append one attempt and write its corresponding capability health once."""
    capability = ProviderCapability(*capability_id.split(":", 1))
    attempt = FetchAttempt(
        provider=provider,
        capability=capability_id,
        status=status,
        started_at=started_at,
        elapsed_ms=elapsed_ms,
        record_count=record_count,
        error_type=error_type,
        message=message,
    )
    attempts.append(attempt)
    record_capability_health(
        capability,
        fetch_status_to_health_status(status),
        error_summary=error_summary,
    )
    return attempt
