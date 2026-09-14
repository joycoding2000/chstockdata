"""Layered settings for chstockdata (zero-config by default).

Priority per key (highest first):

1. Values injected via :func:`configure` — host applications (such as
   TradingAgents) call this at startup to route the package to their own
   cache locations.
2. ``CHSTOCKDATA_*`` environment variables.
3. Legacy ``TRADINGAGENTS_*`` environment variables — kept so deployments
   migrating from TradingAgents-astock keep working unattended.
4. Built-in defaults.

Only the keys the data layer actually reads are managed here. This module
never reads yaml files and depends on the standard library only.
"""

from __future__ import annotations

import os
import threading
from typing import Any, Iterator, Mapping

__all__ = ["configure", "reset_config", "get_setting", "get_config", "validate_vipdoc_history_config"]

_LOCK = threading.Lock()
_INJECTED: dict[str, Any] = {}

_DEFAULT_CACHE_DIR = os.path.join(os.path.expanduser("~"), ".chstockdata", "cache")

_DEFAULTS: dict[str, Any] = {
    "data_cache_dir": _DEFAULT_CACHE_DIR,
    "northbound_store_path": None,
    "vipdoc_history_enabled": True,
    "vipdoc_history_dir": None,
    "vipdoc_history_max_staleness_days": 5,
    "vipdoc_history_url": "https://data.tdx.com.cn/vipdoc/hsjday.zip",
}

# Per-key env aliases, checked left to right.
_ENV_ALIASES: dict[str, tuple[str, ...]] = {
    "data_cache_dir": (
        "CHSTOCKDATA_CACHE_DIR",
        "CHSTOCKDATA_DATA_CACHE_DIR",
        "TRADINGAGENTS_CACHE_DIR",
    ),
    "northbound_store_path": (
        "CHSTOCKDATA_NORTHBOUND_STORE_PATH",
        "TRADINGAGENTS_NORTHBOUND_STORE_PATH",
    ),
    "vipdoc_history_enabled": (
        "CHSTOCKDATA_VIPDOC_HISTORY_ENABLED",
        "TRADINGAGENTS_VIPDOC_HISTORY_ENABLED",
    ),
    "vipdoc_history_dir": (
        "CHSTOCKDATA_VIPDOC_HISTORY_DIR",
        "TRADINGAGENTS_VIPDOC_HISTORY_DIR",
    ),
    "vipdoc_history_max_staleness_days": (
        "CHSTOCKDATA_VIPDOC_HISTORY_MAX_STALENESS_DAYS",
        "TRADINGAGENTS_VIPDOC_HISTORY_MAX_STALENESS_DAYS",
    ),
    "vipdoc_history_url": (
        "CHSTOCKDATA_VIPDOC_HISTORY_URL",
        "TRADINGAGENTS_VIPDOC_HISTORY_URL",
    ),
}

_TRUTHY = frozenset({"1", "true", "yes", "on"})


def validate_vipdoc_history_config(cfg: Mapping) -> None:
    """Validate the local official-TDX-vipdoc daily-history layer keys.

    Ported verbatim from the source repository: a malformed value must fail
    the config load instead of silently disabling or misdirecting the
    local-first raw-daily path.
    """
    import math

    enabled = cfg.get("vipdoc_history_enabled", True)
    if not isinstance(enabled, bool):
        raise ValueError("vipdoc_history_enabled must be a boolean")

    staleness = cfg.get("vipdoc_history_max_staleness_days", 5)
    try:
        staleness_value = float(staleness)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "vipdoc_history_max_staleness_days must be a number"
        ) from exc
    if not math.isfinite(staleness_value) or staleness_value < 0:
        raise ValueError(
            "vipdoc_history_max_staleness_days must be finite and >= 0"
        )

    for key in ("vipdoc_history_dir", "vipdoc_history_url"):
        value = cfg.get(key)
        if value is not None and not isinstance(value, str):
            raise ValueError(f"{key} must be a string or null")


def configure(**settings: Any) -> None:
    """Inject or update settings (host applications call this at startup).

    Accepted keys: ``data_cache_dir``, ``northbound_store_path``,
    ``vipdoc_history_enabled``, ``vipdoc_history_dir``,
    ``vipdoc_history_max_staleness_days``, ``vipdoc_history_url``.
    Unknown keys are rejected loudly to catch typos.
    """
    unknown = set(settings) - set(_DEFAULTS)
    if unknown:
        raise ValueError(f"unknown chstockdata settings: {sorted(unknown)}")
    with _LOCK:
        _INJECTED.update(settings)


def reset_config() -> None:
    """Clear all injected settings (test helper)."""
    with _LOCK:
        _INJECTED.clear()


def _coerce(key: str, raw: str) -> Any:
    if key == "vipdoc_history_enabled":
        return raw.strip().lower() in _TRUTHY
    if key == "vipdoc_history_max_staleness_days":
        try:
            return float(raw)
        except ValueError:
            return _DEFAULTS[key]
    return raw


def get_setting(key: str, default: Any = None) -> Any:
    """Resolve one setting through the injection > env > default chain."""
    if key not in _DEFAULTS:
        return default
    with _LOCK:
        injected = dict(_INJECTED)
    if key in injected:
        return injected[key]
    for env in _ENV_ALIASES[key]:
        raw = os.environ.get(env)
        if raw is not None and raw != "":
            return _coerce(key, raw)
    return _DEFAULTS[key]


class _ConfigView(Mapping):
    """Read-only Mapping façade; ``get_config().get(key, default)`` is the
    call-site contract carried over from the source repository."""

    def __getitem__(self, key: str) -> Any:
        if key not in _DEFAULTS:
            raise KeyError(key)
        return get_setting(key)

    def __iter__(self) -> Iterator[str]:
        return iter(_DEFAULTS)

    def __len__(self) -> int:
        return len(_DEFAULTS)

    def get(self, key: str, default: Any = None) -> Any:
        if key in _DEFAULTS:
            return get_setting(key)
        return default

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"chstockdata.config.view({dict(_DEFAULTS)!r}, injected={len(_INJECTED)})"


def get_config() -> Mapping:
    """Return a read-only settings mapping (see module docstring for priority)."""
    return _ConfigView()
