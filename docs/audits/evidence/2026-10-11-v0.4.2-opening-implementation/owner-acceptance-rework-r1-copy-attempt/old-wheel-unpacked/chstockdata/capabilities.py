"""Capability identity + per-capability provider health (consumer-neutral).

v0.4.0 foundation: health is recorded per ``provider + capability`` pair
(``mootdx:bars``, ``mootdx:finance``, ``tencent:quote``, ...) instead of a
single provider-wide verdict.  One capability failing must never mark the
other capabilities of the same provider unhealthy — e.g. a ``mootdx.bars``
outage says nothing about ``mootdx.finance`` / ``mootdx.xdxr``.

Design constraints:

- Consumer-neutral: capability names describe the *data operation*, never a
  downstream tool name (no TradingAgents tool ids here).
- Capability ids are stable colon-separated composite identifiers;
  ``ProviderCapability.id()`` is ``"<provider>:<capability>"`` (e.g.
  ``"mootdx:bars"``) and is the key used by the health store, caches,
  probes and live tests.
- The health store is an in-process registry with a clock seam so tests are
  deterministic (no sleeps).  It records *provider health observations*;
  whether a user request ultimately succeeded (the fallback chain) is
  *routing health* and is expressed by
  :mod:`chstockdata.fetch_result` instead.
- Attempt status (fetch layer) and capability health status (this layer)
  share one mapping: :func:`fetch_status_to_health_status`.  One provider
  observation must never produce conflicting statuses in
  ``FetchAttempt`` and ``CapabilityHealth``.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone

from .fetch_result import (
    FETCH_FAILED_NETWORK,
    FETCH_FAILED_RATE_LIMIT,
    FETCH_FAILED_STRUCTURE,
    FETCH_NORMAL_EMPTY,
    FETCH_NOT_CONFIGURED,
    FETCH_SKIPPED,
    FETCH_SUCCESS,
)

__all__ = [
    "HEALTH_FAILED",
    "HEALTH_NORMAL_EMPTY",
    "HEALTH_NOT_CONFIGURED",
    "HEALTH_SKIPPED",
    "HEALTH_SUCCESS",
    "CapabilityHealth",
    "ProviderCapability",
    "capability_health_snapshot",
    "fetch_status_to_health_status",
    "get_capability_health",
    "known_capabilities",
    "record_capability_health",
    "reset_capability_health",
    "set_health_clock",
]

# ── Health status vocabulary ────────────────────────────────────────────────
# Reuses the provenance attempt-status semantics (success / normal_empty are
# terminal; failures carry the failure class) but lives at the capability
# level rather than per single call.
HEALTH_SUCCESS = "success"
HEALTH_NORMAL_EMPTY = "normal_empty"
HEALTH_FAILED = "failed"
HEALTH_NOT_CONFIGURED = "not_configured"
HEALTH_SKIPPED = "skipped"

_TERMINAL_HEALTH = frozenset({HEALTH_SUCCESS, HEALTH_NORMAL_EMPTY})

# ── Single status mapping: fetch attempt ↔ capability health ────────────────
# One provider observation must produce consistent statuses across the fetch
# layer (FetchAttempt.status) and the health layer (CapabilityHealth.status).
# This is the ONLY place the two vocabularies meet — no scattered ifs.
_FETCH_TO_HEALTH: dict[str, str] = {
    FETCH_SUCCESS: HEALTH_SUCCESS,
    FETCH_NORMAL_EMPTY: HEALTH_NORMAL_EMPTY,
    FETCH_NOT_CONFIGURED: HEALTH_NOT_CONFIGURED,
    FETCH_SKIPPED: HEALTH_SKIPPED,
    FETCH_FAILED_NETWORK: HEALTH_FAILED,
    FETCH_FAILED_RATE_LIMIT: HEALTH_FAILED,
    FETCH_FAILED_STRUCTURE: HEALTH_FAILED,
}


def fetch_status_to_health_status(status: str) -> str:
    """Map a fetch-attempt status to its capability-health status.

    Health-layer statuses pass through unchanged (idempotent), so callers
    may hand in either vocabulary.  Failure subtypes collapse to
    ``HEALTH_FAILED`` — the health layer records the observation outcome,
    the failure class stays in the fetch attempt.
    """
    mapped = _FETCH_TO_HEALTH.get(status)
    if mapped is not None:
        return mapped
    if status in _VALID_HEALTH_STATUSES:
        return status
    raise ValueError(f"unknown fetch/health status: {status!r}")


@dataclass(frozen=True)
class ProviderCapability:
    """Identity of one provider capability: ``provider`` + ``capability``.

    ``capability`` names the data operation in provider-neutral terms:
    ``quote``, ``bars``, ``finance``, ``xdxr``, ``daily_bars``, ...  The
    pair is deliberately NOT a downstream tool name; consumer-specific
    capability ids stay in the consumer's own registry.
    """

    provider: str
    capability: str

    def __post_init__(self) -> None:
        if not self.provider or not self.provider.strip():
            raise ValueError("provider must not be empty")
        if not self.capability or not self.capability.strip():
            raise ValueError("capability must not be empty")
        for part in (self.provider, self.capability):
            if any(ch in part for ch in ":/\\ \t\n"):
                raise ValueError(
                    f"invalid capability component {part!r}: "
                    "':/\\\\' and whitespace are not allowed"
                )

    def id(self) -> str:
        """Stable composite key, e.g. ``"mootdx:bars"``."""
        return f"{self.provider}:{self.capability}"


@dataclass(frozen=True)
class CapabilityHealth:
    """Latest health observation for one ``provider + capability`` pair."""

    capability_id: str
    status: str
    observed_at: str  # ISO 8601 UTC, when the observation was made
    error_summary: str | None = None

    @property
    def is_healthy(self) -> bool:
        """The capability last completed successfully (or normal-empty)."""
        return self.status in _TERMINAL_HEALTH


# ── In-process health store ────────────────────────────────────────────────

_LOCK = threading.Lock()
_LATEST: dict[str, CapabilityHealth] = {}

# Clock seam for deterministic tests; defaults to the real clock. Used for
# ``observed_at`` so a fake clock makes health observations deterministic.
_clock: Callable[[], float] = time.time

_VALID_HEALTH_STATUSES = frozenset({
    HEALTH_SUCCESS, HEALTH_NORMAL_EMPTY, HEALTH_FAILED,
    HEALTH_NOT_CONFIGURED, HEALTH_SKIPPED,
})


def set_health_clock(clock: Callable[[], float]) -> None:
    """Replace the store's clock (test seam; pass ``time.time`` to restore)."""
    global _clock
    _clock = clock


def record_capability_health(
    capability: ProviderCapability,
    status: str,
    *,
    error_summary: str | None = None,
    observed_at: str | None = None,
) -> CapabilityHealth:
    """Record one health observation for a single capability.

    Other capabilities of the same provider are untouched — this is the
    core isolation guarantee of the capability model.  ``status`` may be
    given in either the health vocabulary or the fetch-attempt vocabulary
    (mapped via :func:`fetch_status_to_health_status`, so a
    ``VendorNoDataError`` observation can never record ``failed``).
    """
    status = fetch_status_to_health_status(status)
    health = CapabilityHealth(
        capability_id=capability.id(),
        status=status,
        observed_at=observed_at
        or datetime.fromtimestamp(_clock(), timezone.utc).isoformat(),
        error_summary=str(error_summary)[:500] if error_summary else None,
    )
    with _LOCK:
        _LATEST[capability.id()] = health
    return health


def get_capability_health(capability: ProviderCapability) -> CapabilityHealth | None:
    """Latest observation for one capability, or ``None`` if never probed."""
    with _LOCK:
        return _LATEST.get(capability.id())


def capability_health_snapshot() -> dict[str, CapabilityHealth]:
    """Copy of all recorded per-capability health (for live-gate reports)."""
    with _LOCK:
        return dict(_LATEST)


def known_capabilities() -> list[str]:
    """Sorted capability ids currently recorded (diagnostics/tests)."""
    with _LOCK:
        return sorted(_LATEST)


def reset_capability_health() -> None:
    """Clear all recorded health (test helper)."""
    with _LOCK:
        _LATEST.clear()
