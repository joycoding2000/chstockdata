"""Vendor data-error taxonomy (P4-VENDOR-01, DEC-P4-03 option B).

A single hierarchy so the routing layer reacts by *behavior*, not by vendor:
every condition where a data vendor cannot return usable data derives from
``VendorError``, and the router catches the base types.  A new vendor raises
one of these (or a thin vendor-named subclass) and needs no new ``except``
clause in ``route_to_vendor``.

    VendorError
    ├── VendorNoDataError          no usable rows (empty result or stale data)
    ├── VendorRateLimitError       transient throttle -> skip to next vendor
    ├── VendorNotConfiguredError   missing API key/config -> vendor unavailable
    └── VendorNetworkError         transport-level failure -> next vendor

Design constraints (kept intentionally minimal, see
``docs/releases/v0.5.0/audits/vendor-error-routing-gap-audit-20260913.md`` §4B):

* Existing raise sites keep their signatures: every field is optional and the
  positional ``message`` argument is the only required shape.
* ``VendorNotConfiguredError`` is also a ``ValueError`` so legacy
  ``except ValueError`` callers keep working.
* These classes carry provenance metadata only (``vendor`` / ``method`` /
  ``kind`` / ``retryable`` / ``http_status``); they do not change vendor-internal
  fallback chains, evidence classification, or report disclosure semantics.
"""

from __future__ import annotations

from .fetch_result import (
    FETCH_FAILED_NETWORK,
    FETCH_FAILED_RATE_LIMIT,
    FETCH_FAILED_STRUCTURE,
    FETCH_NORMAL_EMPTY,
    FETCH_NOT_CONFIGURED,
)


class VendorError(Exception):
    """Base for any condition where a vendor could not return usable data.

    ``vendor`` and ``method`` identify the failing provider call when the raise
    site knows them (legacy raise sites may leave them unset).  ``kind`` is the
    stable behavior category; ``retryable`` tells the routing layer whether a
    later attempt could plausibly succeed; ``http_status`` records the HTTP
    status when the failure came from an HTTP boundary.
    """

    kind: str = "vendor_error"
    retryable: bool = False

    def __init__(
        self,
        message: str = "",
        *,
        vendor: str | None = None,
        method: str | None = None,
        kind: str | None = None,
        retryable: bool | None = None,
        http_status: int | None = None,
    ) -> None:
        super().__init__(message)
        self.vendor = vendor
        self.method = method
        if kind is not None:
            self.kind = kind
        if retryable is not None:
            self.retryable = retryable
        self.http_status = http_status


class VendorNoDataError(VendorError):
    """A vendor returned no usable rows for a symbol (empty result or stale)."""

    kind = "no_data"
    retryable = False


class VendorRateLimitError(VendorError):
    """A vendor throttled the request; retrying later or elsewhere may work."""

    kind = "rate_limit"
    retryable = True


class VendorNotConfiguredError(VendorError, ValueError):
    """A vendor was selected but its API key/configuration is missing.

    Also a ``ValueError`` so existing callers that catch ``ValueError`` keep
    working while the routing layer treats it as "vendor unavailable".
    """

    kind = "not_configured"
    retryable = False


class VendorNetworkError(VendorError):
    """A vendor failed at the network/transport boundary."""

    kind = "network"
    retryable = True


class DeadlineExceeded(TimeoutError):
    """A data-collection step could not fit within its deadline budget.

    Host frameworks subclass this for their own source-context deadline
    exceptions so vendor code can catch the package-level base regardless
    of which layer raised it.
    """

    kind = "deadline_exceeded"
    retryable = True


class SourceContextDeadlineExceeded(DeadlineExceeded):
    """Kept under its historical name so error summaries and log lines that
    embed ``type(exc).__name__`` stay byte-stable; host frameworks subclass
    the ``DeadlineExceeded`` base with this same name."""

    kind = "source_context_deadline_exceeded"


def exception_to_fetch_status(exc: BaseException) -> str:
    """Map a provider exception to a structured fetch-attempt status.

    Single shared classification for every routing engine (quote chain,
    daily bars, ...) so identical failure behaviors never diverge into
    per-engine mappings.  Returns the fetch-attempt vocabulary (which
    ``fetch_status_to_health_status`` accepts directly, keeping one
    observation consistent across the fetch and health layers).
    """
    if isinstance(exc, VendorRateLimitError):
        return FETCH_FAILED_RATE_LIMIT
    if isinstance(exc, VendorNoDataError):
        return FETCH_NORMAL_EMPTY
    if isinstance(exc, VendorNotConfiguredError):
        return FETCH_NOT_CONFIGURED
    if isinstance(exc, VendorNetworkError):
        return FETCH_FAILED_NETWORK
    if isinstance(exc, DeadlineExceeded):
        # A deadline budget failure is a transport-level failure for routing
        # purposes (not a structure error, not "no data").
        return FETCH_FAILED_NETWORK
    # Structure failures are deterministic value/shape errors; everything
    # else (timeouts, connection resets, unknown vendors) stays network.
    if isinstance(exc, (ValueError, KeyError, TypeError)):
        return FETCH_FAILED_STRUCTURE
    return FETCH_FAILED_NETWORK


__all__ = [
    "DeadlineExceeded",
    "SourceContextDeadlineExceeded",
    "VendorError",
    "VendorNetworkError",
    "VendorNoDataError",
    "VendorNotConfiguredError",
    "VendorRateLimitError",
    "exception_to_fetch_status",
]
