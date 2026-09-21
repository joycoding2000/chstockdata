"""Generic structured fetch results — consumer-neutral (v0.4.0 foundation).

The chain this module belongs to::

    provider call
        ↓
    structured generic result  (this module: FetchResult[T])
        ↓
    legacy renderer / compatibility wrapper
        ↓
    existing public API

Naming note: ``ProviderAttempt``/``EvidenceEnvelope`` in
:mod:`chstockdata.provenance` are TradingAgents-compatibility models and are
frozen API — they must not be reshaped.  This module therefore introduces its
own attempt type (``FetchAttempt``) with strictly provider/retrieval semantics:

- provider, capability, status, timing, record_count, error class/message
- NO consumer-domain fields: no ``original_tool``, ``referenced_by``,
  ``evidence_domain``, research coverage, portfolio/backtest semantics, etc.

Key timing separation enforced by :class:`FetchMetadata`:

- ``retrieved_at``  — when *we* fetched the data (wall clock of the call)
- ``observed_at`` / ``data_as_of`` — when the data itself is valid
  (exchange timestamp, report period, ...).  These are different concepts
  and are never conflated.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Generic, TypeVar

__all__ = [
    "FETCH_SUCCESS",
    "FETCH_NORMAL_EMPTY",
    "FETCH_FAILED_NETWORK",
    "FETCH_FAILED_RATE_LIMIT",
    "FETCH_FAILED_STRUCTURE",
    "FETCH_NOT_CONFIGURED",
    "FETCH_SKIPPED",
    "FetchAttempt",
    "FetchMetadata",
    "FetchResult",
]

# ── Attempt status vocabulary ───────────────────────────────────────────────
# Mirrors the provenance granularity (reused semantics, independent model).
FETCH_SUCCESS = "success"
FETCH_NORMAL_EMPTY = "normal_empty"
FETCH_FAILED_NETWORK = "failed_network"
FETCH_FAILED_RATE_LIMIT = "failed_rate_limit"
FETCH_FAILED_STRUCTURE = "failed_structure"
FETCH_NOT_CONFIGURED = "not_configured"
FETCH_SKIPPED = "skipped"

# Terminal: the attempt produced a usable answer (data or legitimate empty);
# these do not trigger fallback by themselves.
_TERMINAL = frozenset({FETCH_SUCCESS, FETCH_NORMAL_EMPTY})

_MAX_ERROR_LENGTH = 500

T = TypeVar("T")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean_error(message: str | None) -> str | None:
    if message is None:
        return None
    return str(message).strip()[:_MAX_ERROR_LENGTH] or None


@dataclass
class FetchAttempt:
    """One provider call attempt inside a routing chain.

    Purely descriptive — an attempt records what happened on one provider
    call; it does NOT decide routing policy.  In particular,
    ``normal_empty`` does not encode "no fallback needed": whether an empty
    result ends the route is a *capability policy* decision (quote chains
    fall through on empty; a suspension snapshot's empty answer may be the
    legitimate terminal result).  Routing engines decide; this model only
    reports.

    ``capability`` is the stable ``"<provider>:<capability>"`` id from
    :mod:`chstockdata.capabilities` (e.g. ``"tencent:quote"``).
    """

    provider: str
    capability: str  # "<provider>:<capability>"
    status: str
    started_at: str  # ISO 8601 UTC
    elapsed_ms: int  # must be >= 0
    record_count: int | None = None
    error_type: str | None = None  # exception class name (sanitized)
    message: str | None = None  # truncated error/empty summary

    def __post_init__(self) -> None:
        if not self.provider:
            raise ValueError("provider must not be empty")
        if not self.capability:
            raise ValueError("capability must not be empty")
        if self.status not in (
            FETCH_SUCCESS, FETCH_NORMAL_EMPTY, FETCH_FAILED_NETWORK,
            FETCH_FAILED_RATE_LIMIT, FETCH_FAILED_STRUCTURE,
            FETCH_NOT_CONFIGURED, FETCH_SKIPPED,
        ):
            raise ValueError(f"invalid fetch attempt status: {self.status!r}")
        if self.elapsed_ms < 0:
            raise ValueError("elapsed_ms must be >= 0")
        self.message = _clean_error(self.message)

    def is_success(self) -> bool:
        """The attempt produced usable data."""
        return self.status == FETCH_SUCCESS

    def is_failure(self) -> bool:
        """Hard failure (network/rate-limit/structure)."""
        return self.status in (
            FETCH_FAILED_NETWORK,
            FETCH_FAILED_RATE_LIMIT,
            FETCH_FAILED_STRUCTURE,
        )

    def to_dict(self) -> dict:
        """JSON-serializable dict for diagnostics (attempts stay the truth)."""
        return {
            "provider": self.provider,
            "capability": self.capability,
            "status": self.status,
            "started_at": self.started_at,
            "elapsed_ms": self.elapsed_ms,
            "record_count": self.record_count,
            "error_type": self.error_type,
            "message": self.message,
        }


@dataclass
class FetchMetadata:
    """Retrieval metadata for one completed routing chain.

    Distinguishes provider health (per-attempt statuses) from routing health
    (the derived final outcome): a chain succeeds even when earlier providers
    failed, and those failures stay visible in ``attempts``.

    Multi-provider results: a per-code fallback chain can assemble one
    result from several providers.  ``providers_used`` lists every provider
    that contributed data (in first-contribution order); ``final_provider``
    is the *single* provider only when exactly one contributed, else
    ``None`` — it never falsely claims one provider owns a mixed result.
    """

    capability: str  # requested capability, e.g. "quote"
    final_provider: str | None  # sole contributing provider; None = mixed/none
    retrieved_at: str  # when the fetch call completed (our wall clock)
    observed_at: str | None = None  # data's own timestamp (vendor/exchange)
    data_as_of: str | None = None  # business date the data is valid for
    stale: bool = False  # last-resort / stale snapshot used
    partial: bool = False  # only part of the request could be satisfied
    limitations: list[str] = field(default_factory=list)
    attempts: list[FetchAttempt] = field(default_factory=list)
    providers_used: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.capability:
            raise ValueError("capability must not be empty")
        if not isinstance(self.limitations, list):
            raise ValueError("limitations must be a list")
        if not isinstance(self.attempts, list):
            raise ValueError("attempts must be a list")
        if not isinstance(self.providers_used, list):
            raise ValueError("providers_used must be a list")
        # Contract: final_provider set ⟺ exactly one contributing provider.
        if len(self.providers_used) == 1:
            if self.final_provider is None:
                self.final_provider = self.providers_used[0]
            elif self.final_provider != self.providers_used[0]:
                raise ValueError(
                    "final_provider must match the sole entry of providers_used"
                )
        elif self.final_provider is not None:
            raise ValueError(
                "final_provider must be None unless exactly one provider "
                "contributed (use providers_used for mixed results)"
            )

    # ── Routing health (derived from attempts — never serialized as truth) ──

    @property
    def final_status(self) -> str:
        """Final outcome of the whole routing request (not of one attempt).

        Priority order: any provider produced data → ``success``; else any
        hard failure → that failure class (first failure wins, mirroring the
        primary-degradation convention); else any normal-empty observation
        → ``normal_empty``; else not-configured; else ``skipped``.
        """
        if any(a.is_success() for a in self.attempts):
            return FETCH_SUCCESS
        for attempt in self.attempts:
            if attempt.is_failure():
                return attempt.status
        if any(a.status == FETCH_NORMAL_EMPTY for a in self.attempts):
            return FETCH_NORMAL_EMPTY
        if any(a.status == FETCH_NOT_CONFIGURED for a in self.attempts):
            return FETCH_NOT_CONFIGURED
        return FETCH_SKIPPED

    @property
    def succeeded(self) -> bool:
        """Routing chain produced a usable answer (data or normal empty)."""
        return self.final_status in _TERMINAL

    @property
    def degraded(self) -> bool:
        """Chain succeeded but some earlier provider failed (visible, not hidden)."""
        return self.succeeded and any(a.is_failure() for a in self.attempts)

    @property
    def failed_providers(self) -> list[str]:
        """Providers whose attempt failed inside this chain."""
        seen: list[str] = []
        for attempt in self.attempts:
            if attempt.is_failure() and attempt.provider not in seen:
                seen.append(attempt.provider)
        return seen

    def to_dict(self) -> dict:
        return {
            "capability": self.capability,
            "final_provider": self.final_provider,
            "providers_used": list(self.providers_used),
            "final_status": self.final_status,
            "retrieved_at": self.retrieved_at,
            "observed_at": self.observed_at,
            "data_as_of": self.data_as_of,
            "stale": self.stale,
            "partial": self.partial,
            "limitations": list(self.limitations),
            "degraded": self.degraded,
            "failed_providers": self.failed_providers,
            "attempts": [a.to_dict() for a in self.attempts],
        }


@dataclass
class FetchResult(Generic[T]):
    """Structured result of one fetch through the routing chain.

    ``data`` carries the typed payload (a dict of quotes, a DataFrame, ...);
    for ``normal_empty`` it holds the empty container.  ``metadata.attempts``
    is the single source of truth for what happened across providers.
    """

    data: T
    metadata: FetchMetadata

    def __post_init__(self) -> None:
        if not isinstance(self.metadata, FetchMetadata):
            raise ValueError("metadata must be a FetchMetadata")

    @property
    def succeeded(self) -> bool:
        return self.metadata.succeeded

    @property
    def is_normal_empty(self) -> bool:
        return self.metadata.final_status == FETCH_NORMAL_EMPTY

    def to_dict(self) -> dict:
        """Serialize with ``data`` passed through as-is (caller knows T)."""
        return {
            "data": self.data,
            "metadata": self.metadata.to_dict(),
        }
