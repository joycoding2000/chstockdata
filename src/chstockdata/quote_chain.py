"""Structured realtime-quote routing chain (Tencent → mootdx → Sina).

v0.4.0 vertical slice: the realtime-quote fallback chain is the first real
data path rebuilt on the generic structured core.  Layering::

    fetch_realtime_quotes()          structured FetchResult (this module)
        ↓
    a_stock._get_realtime_quotes()   legacy compatibility wrapper
        ↓
    a_stock.get_realtime_snapshot()  existing public API (unchanged)

Provider health vs routing health are separated here:

- Each provider's attempt is recorded as a :class:`FetchAttempt` (and fed to
  the capability health store through the single status mapping), so
  ``tencent:quote`` failing is visible even when the Sina fallback saves
  the chain.
- ``FetchResult.metadata.final_status`` answers routing health: did the
  chain, as a whole, satisfy the request?

Routing policy lives HERE, not in the generic model: a ``normal_empty``
attempt is a fact ("provider answered, nothing usable"), and this chain's
policy is to fall through to the next source on it.  Other capabilities
(a suspension snapshot, corporate actions) may legitimately treat empty as
terminal — that is their engine's decision.

The per-code semantics carried over verbatim from ``a_stock``: fallback is
per code, stale snapshots prefer a fresh next source with the first stale
candidate retained as last resort, and failure is raised only when no
requested code has a usable positive-price snapshot.

``probe_quote_provider`` is the isolated single-provider execution path for
live capability probes: it updates ONLY the probed capability's health and
never records ``not_configured`` for providers that are not part of the
probe.
"""

from __future__ import annotations

import time
from typing import Callable

from .capabilities import (
    ProviderCapability,
    fetch_status_to_health_status,
    record_capability_health,
)
from .fetch_result import (
    FETCH_NORMAL_EMPTY,
    FETCH_NOT_CONFIGURED,
    FETCH_SUCCESS,
    FetchAttempt,
    FetchMetadata,
    FetchResult,
)

__all__ = [
    "QUOTE_PROVIDERS",
    "fetch_realtime_quotes",
    "probe_quote_provider",
    "RealtimeQuoteRoutingError",
]

QUOTE_CAPABILITY = "quote"

# Explicit free-source order: Tencent → TDX (mootdx) → Sina.
QUOTE_PROVIDERS: tuple[tuple[str, str], ...] = (
    ("tencent", "tencent:quote"),
    ("mootdx", "mootdx:quote"),
    ("sina", "sina:quote"),
)


class RealtimeQuoteRoutingError(RuntimeError):
    """All free realtime-quote providers failed or returned no usable price.

    Mirrors the sanitized-error contract of
    ``a_stock._RealtimeQuoteUnavailable``: the message never carries provider
    exception details (those live in ``attempts`` for diagnostics).
    """

    def __init__(self, attempts: list[FetchAttempt]):
        self.attempts = list(attempts)
        super().__init__("实时行情不可用：腾讯、mootdx、新浪均未返回有效价格")


def _classify_status(exc: Exception) -> str:
    """Map a provider exception to a structured attempt status."""
    from .vendor_errors import (
        VendorNetworkError,
        VendorNoDataError,
        VendorNotConfiguredError,
        VendorRateLimitError,
    )

    if isinstance(exc, VendorRateLimitError):
        return "failed_rate_limit"
    if isinstance(exc, VendorNoDataError):
        return "normal_empty"
    if isinstance(exc, VendorNotConfiguredError):
        return "not_configured"
    if isinstance(exc, VendorNetworkError):
        return "failed_network"
    # Structure failures are deterministic value/shape errors; everything
    # else (timeouts, connection resets, unknown vendors) stays network.
    if isinstance(exc, (ValueError, KeyError, TypeError)):
        return "failed_structure"
    return "failed_network"


def _capability_for_provider(provider: str) -> tuple[ProviderCapability, str]:
    """provider 名 → (ProviderCapability, capability_id)；未知名字报错。"""
    for name, capability_id in QUOTE_PROVIDERS:
        if name == provider:
            return ProviderCapability(*capability_id.split(":", 1)), capability_id
    raise ValueError(f"unknown quote provider: {provider!r}")


def _observe_health(capability: ProviderCapability, status: str, *, error_summary: str | None = None) -> None:
    """单点写入 capability health：fetch status 经唯一映射转为 health status。"""
    record_capability_health(
        capability,
        fetch_status_to_health_status(status),
        error_summary=error_summary,
    )


def _dedupe_codes(codes: list[str]) -> list[str]:
    return list(
        dict.fromkeys(str(code).strip() for code in codes if str(code).strip())
    )


def fetch_realtime_quotes(
    codes: list[str],
    fetchers: dict[str, Callable[..., dict]],
    *,
    quote_number: Callable[[object], float | None],
    clock: Callable[[], float] = time.monotonic,
) -> FetchResult[dict[str, dict]]:
    """Run the realtime-quote routing chain and return a structured result.

    ``fetchers`` maps provider name → the provider quote function with the
    historical signature ``fetcher(codes, fallback_from=...)`` (the real
    implementations are injected from ``a_stock``; tests inject fakes).
    ``quote_number`` is the shared finite-float coercion helper.

    Per-code semantics (unchanged from the legacy implementation):

    - fallback is per code — a partial provider response keeps valid data;
    - stale snapshots prefer a fresh next source; the first stale candidate
      is retained only as a last resort (``stale_last_resort``);
    - the chain fails only when *no* requested code has a usable price.

    Providers not present in ``fetchers`` are recorded as ``not_configured``
    attempts (they ARE part of this routing chain and their absence is a
    fact about the chain); their health entries are updated accordingly.
    Use :func:`probe_quote_provider` for isolated single-provider probes
    that must not touch other capabilities' health.
    """
    requested = _dedupe_codes(codes)
    attempts: list[FetchAttempt] = []
    if not requested:
        raise RealtimeQuoteRoutingError(attempts)

    remaining = set(requested)
    result: dict[str, dict] = {}
    stale_candidates: dict[str, dict] = {}
    per_code_failures: dict[str, list[str]] = {code: [] for code in requested}
    fallback_from: str | None = None

    for provider, capability_id in QUOTE_PROVIDERS:
        if not remaining:
            break
        fetcher = fetchers.get(provider)
        capability = ProviderCapability(*capability_id.split(":", 1))
        if fetcher is None:
            attempts.append(FetchAttempt(
                provider=provider,
                capability=capability_id,
                status=FETCH_NOT_CONFIGURED,
                started_at=_now_iso(),
                elapsed_ms=0,
                message="provider not available in this chain",
            ))
            _observe_health(capability, FETCH_NOT_CONFIGURED)
            continue

        current = sorted(remaining)
        start = clock()
        started_at = _now_iso()
        try:
            payload = fetcher(current, fallback_from=fallback_from) or {}
        except Exception as exc:
            elapsed = int((clock() - start) * 1000)
            status = _classify_status(exc)
            attempts.append(FetchAttempt(
                provider=provider,
                capability=capability_id,
                status=status,
                started_at=started_at,
                elapsed_ms=elapsed,
                error_type=type(exc).__name__,
                message=str(exc),
            ))
            _observe_health(capability, status, error_summary=str(exc))
            for code in current:
                per_code_failures[code].append(type(exc).__name__)
            fallback_from = provider
            continue

        elapsed = int((clock() - start) * 1000)
        if not isinstance(payload, dict):
            payload = {}

        got_any = False
        for code in current:
            quote = payload.get(code)
            if not isinstance(quote, dict):
                per_code_failures[code].append("empty")
                continue
            price = quote_number(quote.get("price"))
            if price is None or price <= 0:
                per_code_failures[code].append("invalid_price")
                continue
            got_any = True
            if quote.get("is_stale"):
                # Prefer a fresh next source; keep the first stale candidate
                # only as a last resort (legitimate off-hours last close).
                stale_candidates.setdefault(code, dict(quote))
                per_code_failures[code].append("stale")
                continue
            normalized = dict(quote)
            normalized.setdefault("source", provider)
            normalized["fallback_attempts"] = list(per_code_failures[code])
            result[code] = normalized
            remaining.discard(code)

        if got_any:
            attempts.append(FetchAttempt(
                provider=provider,
                capability=capability_id,
                status=FETCH_SUCCESS,
                started_at=started_at,
                elapsed_ms=elapsed,
                record_count=len(payload),
            ))
            _observe_health(capability, FETCH_SUCCESS)
        else:
            # Provider responded but gave nothing usable for the remaining
            # codes: a normal-empty observation for this capability.  This
            # chain's POLICY is to fall through to the next source; the
            # attempt itself only records the fact.
            attempts.append(FetchAttempt(
                provider=provider,
                capability=capability_id,
                status=FETCH_NORMAL_EMPTY,
                started_at=started_at,
                elapsed_ms=elapsed,
                record_count=0,
                message="no usable quote for requested codes",
            ))
            _observe_health(capability, FETCH_NORMAL_EMPTY)
        fallback_from = provider

    # Stale last resort (unchanged legacy semantics).
    for code, quote in stale_candidates.items():
        if code in result:
            continue
        quote["fallback_attempts"] = list(per_code_failures[code])
        quote["quote_status"] = "stale_last_resort"
        result[code] = quote

    if not result:
        had_failure = any(a.is_failure() for a in attempts)
        if had_failure:
            # Chain-level failure: providers broke and no code got a usable price.
            raise RealtimeQuoteRoutingError(attempts)
        # All providers responded normally but gave no usable quote:
        # a legitimate normal-empty routing outcome (not a failure).
        metadata = FetchMetadata(
            capability=QUOTE_CAPABILITY,
            final_provider=None,
            retrieved_at=_now_iso(),
            attempts=attempts,
            limitations=["all_sources_normal_empty"],
        )
        return FetchResult(data={}, metadata=metadata)

    # Multi-provider contract: providers_used lists every contributing
    # provider (first-contribution order); final_provider is set only when
    # exactly one provider contributed (FetchMetadata enforces this).
    providers_used: list[str] = []
    for quote in result.values():
        source = str(quote.get("source") or "")
        if source and source not in providers_used:
            providers_used.append(source)

    saw_stale_resort = any(
        q.get("quote_status") == "stale_last_resort" for q in result.values()
    )
    partial = len(result) < len(requested)
    metadata = FetchMetadata(
        capability=QUOTE_CAPABILITY,
        final_provider=None,
        retrieved_at=_now_iso(),
        stale=saw_stale_resort,
        partial=partial,
        limitations=(
            ["stale_last_resort"] if saw_stale_resort else []
        ) + (
            [f"missing_quotes:{code}" for code in requested if code not in result]
        ),
        attempts=attempts,
        providers_used=providers_used,
    )
    if partial:
        metadata.limitations = metadata.limitations or ["partial_response"]
    return FetchResult(data=result, metadata=metadata)


def probe_quote_provider(
    provider: str,
    codes: list[str],
    fetcher: Callable[..., dict],
    *,
    quote_number: Callable[[object], float | None],
    clock: Callable[[], float] = time.monotonic,
) -> FetchResult[dict[str, dict]]:
    """Probe ONE provider quote capability in isolation.

    Live capability probes use this instead of the routing chain so that:

    - probing ``mootdx`` updates only ``mootdx:quote`` — never any other
      capability's health entry;
    - providers that are not part of the probe are NOT recorded as
      ``not_configured`` (absence from a probe is not a health fact).

    The attempt normalization mirrors the routing chain (valid positive
    price required); a stale snapshot still proves the capability alive and
    is reported as success with a ``stale_snapshot`` limitation.
    """
    capability, capability_id = _capability_for_provider(provider)
    requested = _dedupe_codes(codes)
    attempts: list[FetchAttempt] = []

    start = clock()
    started_at = _now_iso()
    try:
        payload = fetcher(requested) or {}
    except Exception as exc:
        elapsed = int((clock() - start) * 1000)
        status = _classify_status(exc)
        attempts.append(FetchAttempt(
            provider=provider,
            capability=capability_id,
            status=status,
            started_at=started_at,
            elapsed_ms=elapsed,
            error_type=type(exc).__name__,
            message=str(exc),
        ))
        _observe_health(capability, status, error_summary=str(exc))
        metadata = FetchMetadata(
            capability=QUOTE_CAPABILITY,
            final_provider=None,
            retrieved_at=_now_iso(),
            attempts=attempts,
            limitations=[f"probe_failed:{provider}"],
        )
        return FetchResult(data={}, metadata=metadata)

    elapsed = int((clock() - start) * 1000)
    if not isinstance(payload, dict):
        payload = {}

    result: dict[str, dict] = {}
    saw_stale = False
    for code in requested:
        quote = payload.get(code)
        if not isinstance(quote, dict):
            continue
        price = quote_number(quote.get("price"))
        if price is None or price <= 0:
            continue
        if quote.get("is_stale"):
            saw_stale = True
        normalized = dict(quote)
        normalized.setdefault("source", provider)
        result[code] = normalized

    if result:
        attempts.append(FetchAttempt(
            provider=provider,
            capability=capability_id,
            status=FETCH_SUCCESS,
            started_at=started_at,
            elapsed_ms=elapsed,
            record_count=len(payload),
        ))
        _observe_health(capability, FETCH_SUCCESS)
        metadata = FetchMetadata(
            capability=QUOTE_CAPABILITY,
            final_provider=None,
            retrieved_at=_now_iso(),
            stale=saw_stale,
            limitations=["stale_snapshot"] if saw_stale else [],
            attempts=attempts,
            providers_used=[provider],
        )
    else:
        attempts.append(FetchAttempt(
            provider=provider,
            capability=capability_id,
            status=FETCH_NORMAL_EMPTY,
            started_at=started_at,
            elapsed_ms=elapsed,
            record_count=0,
            message="no usable quote for requested codes",
        ))
        _observe_health(capability, FETCH_NORMAL_EMPTY)
        metadata = FetchMetadata(
            capability=QUOTE_CAPABILITY,
            final_provider=None,
            retrieved_at=_now_iso(),
            attempts=attempts,
            limitations=[f"probe_normal_empty:{provider}"],
        )
    return FetchResult(data=result, metadata=metadata)


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()
