"""Optional host-provided source-execution context hooks.

Standalone use: no hooks installed — :func:`call_source` is a passthrough
and :func:`get_source_execution_context` returns ``None``. Server selection
then does full-table probing and no source-attempt tracing happens, which is
the correct behavior for plain library use.

Hosts (e.g. TradingAgents) install their implementation at process start::

    import chstockdata.source_context as sc
    sc.install(
        call_source=host_call_source,
        get_source_execution_context=host_get_context,
    )

Installing keeps tool-call probe budgets (the host decides how long a single
tool invocation may spend on server selection) and source-attempt tracing
active while the package runs inside the host process — the ContextVar
machinery lives in the host implementation, shared by both sides.
"""

from __future__ import annotations

from typing import Any, Callable

__all__ = ["install", "call_source", "get_source_execution_context"]

_call_source_impl: Callable[..., Any] | None = None
_get_context_impl: Callable[[], Any] | None = None


def install(
    *,
    call_source: Callable[..., Any] | None = None,
    get_source_execution_context: Callable[[], Any] | None = None,
) -> None:
    """Install host implementations (None leaves that hook unchanged)."""
    global _call_source_impl, _get_context_impl
    if call_source is not None:
        _call_source_impl = call_source
    if get_source_execution_context is not None:
        _get_context_impl = get_source_execution_context


def reset() -> None:
    """Remove installed hooks (test helper)."""
    global _call_source_impl, _get_context_impl
    _call_source_impl = None
    _get_context_impl = None


def call_source(source_id, operation, function, *, attempt_no: int = 1,
                fallback_from: str | None = None):
    """Route one source I/O call through the host if hooks are installed."""
    if _call_source_impl is None:
        return function()
    return _call_source_impl(
        source_id, operation, function,
        attempt_no=attempt_no, fallback_from=fallback_from,
    )


def get_source_execution_context():
    """Return the host's active source-execution context, or ``None``."""
    if _get_context_impl is None:
        return None
    return _get_context_impl()
