"""Structured daily-bars routing engine (tdx_vipdoc → mootdx → Sina).

v0.4.0 Phase 2 vertical slice (Phase 2.1 contract-hardened): the raw/D
historical daily-bars fallback chain is the second real data path rebuilt on
the generic structured core.  Layering::

    fetch_daily_bars()               structured FetchResult (this module)
        ↓
    a_stock.get_stock_data()         legacy compatibility renderer (unchanged
                                     output contract)

Provider health vs routing health are separated exactly as in
:mod:`chstockdata.quote_chain`: every provider attempt produces a
:class:`~chstockdata.fetch_result.FetchAttempt` and one capability-health
observation through the single ``fetch_status_to_health_status`` mapping, so
``mootdx:bars`` failing is visible even when the Sina fallback saves the
chain — and it never touches ``mootdx:finance``/``mootdx:xdxr``.

Canonical schema (ENFORCED, not just declared — every provider frame passes
:func:`canonicalize_daily_bars_frame` on both the routing and the probe path
before it may be recorded as ``success``):

- Required columns: ``Date, Open, High, Low, Close, Volume``.  A non-empty
  frame missing any of them is a ``failed_structure`` attempt (and the chain
  falls through to the next provider) — never a silent success.
- ``Date``: parsed with ``errors="coerce"``; any unparseable value is a
  ``failed_structure`` attempt (strict — malformed dates are never silently
  dropped).  Valid values are normalized to daily granularity
  (``datetime64[ns]``, midnight, timezone-naive exchange business date).
- Required numeric fields: coerced with ``errors="coerce"``; any originally
  non-null value that is not numeric (e.g. ``"abc"``) is a
  ``failed_structure`` attempt.  Valid numeric strings (``"10.25"``) are
  converted; null numeric cells stay ``NaN`` (documented, never fabricated).
- Duplicate business dates: deduplicated keep-last, deterministically, in
  the provider's native row order — no re-sorting.
- Optional column ``pre_close`` — present only when the contributing
  provider actually supplies it (today: ``tdx_vipdoc``'s ``.day`` file
  semantics = previous trading day's raw close **as recorded in the file**;
  never synthesized by this engine, never ``previous row close`` of another
  provider).  Rows merged from providers without it carry ``NaN`` — a Sina
  row that takes over a date never inherits the vipdoc ``pre_close``.
- ``Amount`` is deliberately NOT carried: no provider path in the legacy
  raw/D output ever exposed it (vipdoc's reader column is dropped exactly as
  before), and carrying it would leak a new column into the legacy CSV.
- Ordering: single-provider base frames keep the provider's native row order
  (vipdoc/sina ascend; mootdx keeps wire order) — the legacy output contract
  is frozen, and this engine does not reorder what the provider returned.
  Merged (supplement) frames are deduped keep-last and sorted ascending by
  the legacy ``_merge_ohlcv`` semantics (supplement rows win on overlap).

Volume unit semantics (never guessed, never unified by fiat):

- values are provider-native passthrough — no ×100/÷100 scaling anywhere;
- the engine stamps the resolved unit on the returned frame
  (``frame.attrs["volume_unit"]``) and mirrors it as a
  ``volume_unit:<value>`` limitation (the durable serialized channel):
  ``shares`` for ``tdx_vipdoc`` / ``sina``, ``provider_native_unknown`` for
  ``mootdx`` (the TDX wire ``vol`` unit is NOT verified — requires a
  reachable TDX TCP environment), and ``mixed_provider_native`` when
  contributing providers carry different unit classes.  Consumers must not
  compare ``Volume`` absolutes across sources (``adjusted_bars`` red line).

Provider provenance truth (``providers_used``):

- lists every provider that actually contributed rows to the final payload —
  including a Sina supplement that only overlapped existing dates (its
  keep-last rows replace the base rows), not just one that advanced the
  last bar date;
- the legacy ``# Data source`` label stays a presentation rule and is keyed
  off the explicit ``sina_supplement_advanced_end`` limitation sentinel —
  never re-derived from ``providers_used``.

Request outcome vs provider success (two explicit levels):

- ``result.succeeded`` — the provider route completed (attempt-derived);
- ``result.is_normal_empty`` — the request itself produced no bars.  When
  providers answered but the requested window filtered everything away, the
  engine declares ``metadata.outcome_status = "normal_empty"`` (generic,
  consumer-neutral ``FetchMetadata`` field) instead of leaving consumers to
  inspect an empty dataframe.

Routing policy (THIS engine's, not the generic model's):

- vipdoc normal_empty / not_configured → try mootdx → then sina;
- ``not_configured`` (local layer disabled / package or file missing) is a
  fact, not a hard failure — it never marks the result degraded;
- first provider producing usable rows wins the base frame (no cross-provider
  history stitching beyond the legacy tail supplement);
- after a base frame exists, the legacy supplement contract runs verbatim:
  when the base's last bar is behind the requested end date, Sina is fetched
  over the full requested window and merged (supplement rows win on
  overlapping dates); a failed supplement keeps the base frame;
- window filtering (inclusive both ends) happens after the supplement step,
  exactly where the legacy renderer filtered;
- stale-coverage policy stays with the caller-visible contract: a frame whose
  coverage lags the requested end by more than ``_OHLCV_MAX_STALENESS_DAYS``
  is still returned as a successful result with ``metadata.stale=True`` —
  the legacy renderer turns that into the historical_ohlcv_stale marker.

``data_as_of`` is derived from the returned bars themselves (the last
business date inside the requested window) — this is the bars' own business
date and is reliably derivable.  ``observed_at`` stays ``None``: no provider
in this chain reports an observation timestamp, and none is fabricated.
"""

from __future__ import annotations

import time
from collections.abc import Callable

import pandas as pd

from .fetch_result import (
    FETCH_FAILED_NETWORK,
    FETCH_FAILED_RATE_LIMIT,
    FETCH_FAILED_STRUCTURE,
    FETCH_NORMAL_EMPTY,
    FETCH_NOT_CONFIGURED,
    FETCH_SUCCESS,
    FetchAttempt,
    FetchMetadata,
    FetchResult,
)
from .routing_observation import (
    elapsed_ms,
    record_fetch_observation,
    utc_now_iso,
)
from .vendor_errors import (
    VendorNoDataError,
    VendorNotConfiguredError,
    exception_to_fetch_status,
)

__all__ = [
    "ADAPTERS",
    "CANONICAL_OPTIONAL_COLUMNS",
    "CANONICAL_REQUIRED_COLUMNS",
    "DAILY_BARS_CAPABILITY",
    "DAILY_BAR_PROVIDERS",
    "VOLUME_UNIT_MIXED",
    "DailyBarsRoutingError",
    "canonicalize_daily_bars_frame",
    "fetch_daily_bars",
    "legacy_source_label",
    "probe_daily_bars_provider",
]

DAILY_BARS_CAPABILITY = "daily_bars"

# Explicit free-source order: local official vipdoc package → TDX (mootdx) →
# Sina.  This mirrors the audited legacy raw/D route (issues/023 方案 A).
DAILY_BAR_PROVIDERS: tuple[tuple[str, str], ...] = (
    ("tdx_vipdoc", "tdx_vipdoc:daily_bars"),
    ("mootdx", "mootdx:bars"),
    ("sina", "sina:bars"),
)

CANONICAL_REQUIRED_COLUMNS = ("Date", "Open", "High", "Low", "Close", "Volume")
CANONICAL_OPTIONAL_COLUMNS = ("pre_close",)

# Volume unit semantics — resolved per contributing provider, never guessed:
# - vipdoc: .day file uint32 = 股 (project-verified reader semantics);
# - sina: getKLineData volume = 股;
# - mootdx: TDX wire `vol` unit NOT verified (requires a reachable TDX TCP
#   environment).  It must never be described as a unified canonical unit.
_VOLUME_UNIT_BY_PROVIDER = {
    "tdx_vipdoc": "shares",
    "sina": "shares",
    "mootdx": "provider_native_unknown",
}
VOLUME_UNIT_MIXED = "mixed_provider_native"


class DailyBarsRoutingError(RuntimeError):
    """All daily-bars providers failed; no usable bars could be routed.

    Mirrors the sanitized-error contract of the quote chain: the message
    never carries vendor URLs, exception details or internals (those live in
    ``attempts`` for diagnostics).
    """

    def __init__(self, attempts: list[FetchAttempt]):
        self.attempts = list(attempts)
        super().__init__("日线数据不可用：本地vipdoc、mootdx、新浪均未返回有效日线数据")


# ---------------------------------------------------------------------------
# Canonicalization boundary (shared by routing + probe paths)
# ---------------------------------------------------------------------------


def canonicalize_daily_bars_frame(
    frame: pd.DataFrame, *, provider: str
) -> pd.DataFrame:
    """Validate and normalize one provider frame into the canonical shape.

    THE single canonicalization boundary: a provider frame is only allowed
    to be recorded as ``success`` (and reach the routing chain or a probe
    result) after passing this validation.  Malformed payloads raise
    ``ValueError`` so the shared classification records
    ``failed_structure`` and the routing chain falls through to the next
    provider — a non-empty malformed frame must never masquerade as usable
    data.

    Validation rules (strict, see module docstring):

    - the payload must be a ``pd.DataFrame`` (a list/dict/tuple from a
      provider is a payload-shape bug → ``ValueError`` → classified
      ``failed_structure``, never misreported as a network failure);
    - required columns ``Date/Open/High/Low/Close/Volume`` must exist;
    - ``Date`` parses with ``errors="coerce"`` — any unparseable value is a
      structure failure; valid values are normalized to daily granularity
      (``datetime64[ns]``, midnight, timezone-naive business date);
    - required numeric fields coerce with ``errors="coerce"`` — any
      originally non-null non-numeric value (``"abc"``) is a structure
      failure; valid numeric strings (``"10.25"``) are converted; null
      numeric cells stay ``NaN`` (documented, never fabricated);
    - duplicate business dates are deduplicated keep-last, deterministically
      and in the provider's native row order (no re-sorting);
    - ``pre_close`` (optional) passes through untouched.
    """
    if not isinstance(frame, pd.DataFrame):
        raise ValueError(  # noqa: TRY004 - structure failures use ValueError taxonomy
            f"{provider} bars payload must be a pandas DataFrame"
        )
    if frame.empty:
        raise ValueError(f"{provider} returned no rows to canonicalize")

    missing = [
        column
        for column in CANONICAL_REQUIRED_COLUMNS
        if column not in frame.columns
    ]
    if missing:
        raise ValueError(
            f"{provider} bars frame missing required columns: "
            + ", ".join(missing)
        )

    out = frame.copy()

    raw_dates = out["Date"]
    parsed_dates = pd.to_datetime(raw_dates, errors="coerce")
    if parsed_dates.isna().any():
        bad = raw_dates[parsed_dates.isna()].astype(str).head(3).tolist()
        raise ValueError(
            f"{provider} bars frame has unparseable Date values: {bad}"
        )
    out["Date"] = parsed_dates.dt.normalize()

    for column in ("Open", "High", "Low", "Close", "Volume"):
        raw_values = out[column]
        numeric = pd.to_numeric(raw_values, errors="coerce")
        invalid = numeric.isna() & raw_values.notna()
        if invalid.any():
            bad = raw_values[invalid].astype(str).head(3).tolist()
            raise ValueError(
                f"{provider} bars frame has non-numeric {column} values: {bad}"
            )
        out[column] = numeric

    if out["Date"].duplicated().any():
        # Deterministic keep-last dedupe; preserves the provider's native
        # row order for the surviving rows (no re-sorting — the legacy
        # output contract is frozen).
        out = out.drop_duplicates(subset="Date", keep="last")

    return out.reset_index(drop=True)


def _volume_unit_for(providers_used: list[str]) -> str:
    """Resolve the Volume unit semantics for the contributing providers.

    A single contributing provider reports its own unit class; providers
    with different unit classes in one payload resolve to
    ``mixed_provider_native`` — the result never claims a unified unit that
    no single provider actually guaranteed.
    """
    units = {
        _VOLUME_UNIT_BY_PROVIDER.get(provider, "provider_native_unknown")
        for provider in providers_used
    }
    if len(units) == 1:
        return next(iter(units))
    return VOLUME_UNIT_MIXED


# ---------------------------------------------------------------------------
# Provider adapters (raise structured vendor errors; return frames on success)
# ---------------------------------------------------------------------------


def _vipdoc_public_columns(frame: pd.DataFrame) -> pd.DataFrame:
    """Keep the reader's ``pre_close``; drop ``Amount`` as the legacy path did."""
    columns = [
        column
        for column in (*CANONICAL_REQUIRED_COLUMNS[:5], "pre_close", "Volume")
        if column in frame.columns
    ]
    return frame[columns].reset_index(drop=True)


def fetch_vipdoc_daily_bars(
    code: str, start_date: str, end_date: str
) -> pd.DataFrame:
    """Local official TDX vipdoc package adapter (read-only, zero network).

    Outcome classification for a *local* source deliberately avoids network
    semantics: configuration-disabled / missing package or file →
    ``VendorNotConfiguredError``; unreadable/corrupt file → ``ValueError``
    (structure); requested window empty or the local package lags the
    requested end beyond ``vipdoc_history_max_staleness_days`` (and the
    trading calendar cannot confirm the market has no newer session,
    DEC-P1-27) → ``VendorNoDataError`` with the reason in the message.
    """
    from . import a_stock

    try:
        from .config import get_config

        cfg = get_config()
    except Exception as exc:  # pragma: no cover - config failure must not kill the chain
        raise VendorNotConfiguredError("vipdoc history configuration unavailable") from exc
    if not cfg.get("vipdoc_history_enabled", True):
        raise VendorNotConfiguredError("vipdoc history disabled by configuration")
    try:
        max_staleness = float(cfg.get("vipdoc_history_max_staleness_days", 5))
    except (TypeError, ValueError):
        max_staleness = 5.0

    try:
        from .vipdoc_history import load_vipdoc_daily

        frame = load_vipdoc_daily(code, start_date, end_date)
    except Exception as exc:
        raise ValueError(
            f"vipdoc day file unreadable ({type(exc).__name__})"
        ) from exc
    if frame is None:
        # Layer enabled but nothing installed for this code.
        raise VendorNotConfiguredError("vipdoc day file missing")
    if frame.empty:
        raise VendorNoDataError("no vipdoc rows in the requested window")
    last = a_stock._last_ohlcv_date(frame)
    if last is None:
        raise VendorNoDataError("vipdoc rows carry no valid dates")
    target = pd.to_datetime(end_date).normalize()
    if (target - last).days > max_staleness:
        reference = a_stock._calendar_reference_last_bar(end_date)
        if reference is not None:
            try:
                reference_stamp = pd.to_datetime(reference).normalize()
            except (TypeError, ValueError):
                reference_stamp = None
            if reference_stamp is not None and last >= reference_stamp:
                return _vipdoc_public_columns(frame)
        raise VendorNoDataError(
            f"vipdoc package ends {last.date()}, more than {max_staleness:g} "
            f"days behind requested {pd.Timestamp(target).date()}"
        )
    return _vipdoc_public_columns(frame)


def fetch_mootdx_daily_bars(
    code: str,
    start_date: str,
    end_date: str,
    *,
    _observe_capability_health: bool = True,
) -> pd.DataFrame:
    """mootdx TCP daily bars adapter.

    Reuses ``a_stock._fetch_mootdx_bars`` verbatim, so the Phase 1.1/1.1.1
    readiness semantics (``_get_mootdx_client`` bars readiness, negative
    cache tiering, bounded bypass isolation for other capabilities) apply
    unchanged.  The provider contract is the most recent 800 daily bars —
    no date-window filtering happens here (legacy behavior; window filtering
    belongs to the engine/renderer).
    """
    from . import a_stock

    return a_stock._fetch_mootdx_bars(
        code,
        offset=800,
        _observe_capability_health=_observe_capability_health,
    )


def _fetch_structured_mootdx_daily_bars(
    code: str, start_date: str, end_date: str
) -> pd.DataFrame:
    """Invoke the mootdx bars adapter with structured health ownership."""
    return fetch_mootdx_daily_bars(
        code,
        start_date,
        end_date,
        _observe_capability_health=False,
    )


def fetch_sina_daily_bars(
    code: str, start_date: str, end_date: str
) -> pd.DataFrame:
    """Sina HTTP daily K-line adapter (unchanged request semantics).

    Same endpoint, parameters, units and window filtering as the audited
    legacy ``a_stock._sina_kline_fallback``; an empty answer is surfaced as
    ``VendorNoDataError`` (normal_empty) instead of an empty frame.
    """
    from . import a_stock

    frame = a_stock._sina_kline_fallback(code, start_date, end_date)
    if frame is None or frame.empty:
        raise VendorNoDataError("no sina kline rows in the requested window")
    return frame


# Provider name → adapter.  Resolved at call time from this module-level
# registry so tests can stub single providers via ``monkeypatch.setitem``.
ADAPTERS: dict[str, Callable[..., pd.DataFrame]] = {
    "tdx_vipdoc": fetch_vipdoc_daily_bars,
    "mootdx": _fetch_structured_mootdx_daily_bars,
    "sina": fetch_sina_daily_bars,
}


# ---------------------------------------------------------------------------
# Routing engine
# ---------------------------------------------------------------------------


def _empty_canonical_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Date": pd.Series(dtype="datetime64[ns]"),
            "Open": pd.Series(dtype="float64"),
            "High": pd.Series(dtype="float64"),
            "Low": pd.Series(dtype="float64"),
            "Close": pd.Series(dtype="float64"),
            "Volume": pd.Series(dtype="float64"),
        }
    )


def _run_adapter(
    provider: str,
    capability_id: str,
    adapter: Callable[..., pd.DataFrame],
    code: str,
    start_date: str,
    end_date: str,
    attempts: list[FetchAttempt],
    *,
    clock: Callable[[], float],
) -> pd.DataFrame | None:
    """Run one provider adapter, append its attempt + health observation.

    Returns the canonicalized provider frame on success, ``None`` otherwise
    (the attempt list always carries the factual outcome).  A frame is only
    recorded as ``success`` after passing
    :func:`canonicalize_daily_bars_frame` — a non-empty malformed payload is
    a ``failed_structure`` attempt, never a success.
    """
    start = clock()
    started_at = utc_now_iso()
    try:
        frame = adapter(code, start_date, end_date)
    except Exception as exc:  # noqa: BLE001 - classified below
        elapsed = elapsed_ms(clock, start)
        status = exception_to_fetch_status(exc)
        record_fetch_observation(
            attempts,
            provider=provider,
            capability_id=capability_id,
            status=status,
            started_at=started_at,
            elapsed_ms=elapsed,
            error_type=type(exc).__name__,
            message=str(exc),
            error_summary=str(exc),
        )
        return None

    elapsed = elapsed_ms(clock, start)
    if frame is None or (hasattr(frame, "empty") and frame.empty):
        record_fetch_observation(
            attempts,
            provider=provider,
            capability_id=capability_id,
            status=FETCH_NORMAL_EMPTY,
            started_at=started_at,
            elapsed_ms=elapsed,
            record_count=0,
            message="provider returned no rows",
        )
        return None

    try:
        frame = canonicalize_daily_bars_frame(frame, provider=provider)
    except Exception as exc:  # noqa: BLE001 - classified below
        status = exception_to_fetch_status(exc)
        record_fetch_observation(
            attempts,
            provider=provider,
            capability_id=capability_id,
            status=status,
            started_at=started_at,
            elapsed_ms=elapsed,
            error_type=type(exc).__name__,
            message=str(exc),
            error_summary=str(exc),
        )
        return None

    record_fetch_observation(
        attempts,
        provider=provider,
        capability_id=capability_id,
        status=FETCH_SUCCESS,
        started_at=started_at,
        elapsed_ms=elapsed,
        record_count=len(frame),
    )
    return frame


def _supplement_with_sina(
    code: str,
    start_date: str,
    end_date: str,
    base_frame: pd.DataFrame,
    adapters: dict[str, Callable[..., pd.DataFrame]],
    attempts: list[FetchAttempt],
    *,
    clock: Callable[[], float],
) -> tuple[pd.DataFrame, bool, bool, bool]:
    """Legacy tail-supplement contract, verbatim — with truthful provenance.

    When the base frame's last bar is behind the requested end date, Sina is
    fetched over the full requested window and merged (supplement rows win on
    overlapping dates; dedupe keep-last; ascending).  A failed or empty
    supplement keeps the base frame — it never fails the routing (legacy
    behavior), but hard supplement failures remain visible as failed attempts
    (and hence as a degraded routing result).

    Returns ``(frame, sina_contributed, advanced_end, supplement_failed)``
    as three DISTINCT facts:

    - ``sina_contributed`` — Sina returned rows that were merged into the
      final payload.  True even when it only overlapped existing dates (its
      keep-last rows replace the base rows there): ``providers_used`` must
      list Sina in that case, not just when the last bar date advanced.
    - ``advanced_end`` — the merged last bar date moved forward.  This is
      the ONLY fact the legacy ``# Data source`` suffix rule keys off.
    - ``supplement_failed`` — a hard (non-empty) failure occurred while
      supplementing; the base frame stands (legacy swallow).
    """
    from . import a_stock

    if not a_stock._needs_sina_supplement(base_frame, end_date):
        return base_frame, False, False, False

    adapter = adapters.get("sina")
    provider, capability_id = "sina", "sina:bars"
    start = clock()
    started_at = utc_now_iso()
    if adapter is None:
        record_fetch_observation(
            attempts,
            provider=provider,
            capability_id=capability_id,
            status=FETCH_NOT_CONFIGURED,
            started_at=started_at,
            elapsed_ms=0,
            message="sina adapter not available in this chain",
        )
        return base_frame, False, False, False
    try:
        supplement = adapter(code, start_date, end_date)
    except Exception as exc:  # noqa: BLE001 - supplement failure must not kill the base
        elapsed = elapsed_ms(clock, start)
        status = exception_to_fetch_status(exc)
        record_fetch_observation(
            attempts,
            provider=provider,
            capability_id=capability_id,
            status=status,
            started_at=started_at,
            elapsed_ms=elapsed,
            error_type=type(exc).__name__,
            message=str(exc),
            error_summary=str(exc),
        )
        return base_frame, False, False, status in (
            FETCH_FAILED_NETWORK,
            FETCH_FAILED_RATE_LIMIT,
            FETCH_FAILED_STRUCTURE,
        )

    elapsed = elapsed_ms(clock, start)
    if supplement is None or (
        isinstance(supplement, pd.DataFrame) and supplement.empty
    ):
        record_fetch_observation(
            attempts,
            provider=provider,
            capability_id=capability_id,
            status=FETCH_NORMAL_EMPTY,
            started_at=started_at,
            elapsed_ms=elapsed,
            record_count=0,
            message="supplement returned no rows",
        )
        return base_frame, False, False, False

    # Supplement payloads are provider ingress too: they must pass the SAME
    # canonicalization boundary as base routing and probes BEFORE any
    # success may be recorded — a non-empty malformed supplement is a
    # failed_structure attempt, never merged, never a contributor.
    try:
        supplement = canonicalize_daily_bars_frame(supplement, provider=provider)
    except Exception as exc:  # noqa: BLE001 - classified below
        status = exception_to_fetch_status(exc)
        record_fetch_observation(
            attempts,
            provider=provider,
            capability_id=capability_id,
            status=status,
            started_at=started_at,
            elapsed_ms=elapsed,
            error_type=type(exc).__name__,
            message=str(exc),
            error_summary=str(exc),
        )
        # Base stands (legacy swallow); the malformed payload never merges.
        return base_frame, False, False, True

    record_fetch_observation(
        attempts,
        provider=provider,
        capability_id=capability_id,
        status=FETCH_SUCCESS,
        started_at=started_at,
        elapsed_ms=elapsed,
        record_count=len(supplement),
    )
    merged = a_stock._merge_ohlcv(base_frame, supplement)
    advanced_end = a_stock._last_ohlcv_date(merged) != a_stock._last_ohlcv_date(
        base_frame
    )
    return merged, True, advanced_end, False


def fetch_daily_bars(
    code: str,
    start_date: str,
    end_date: str,
    *,
    adapters: dict[str, Callable[..., pd.DataFrame]] | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> FetchResult[pd.DataFrame]:
    """Fetch canonical daily bars through the structured routing chain.

    Providers are tried in ``DAILY_BAR_PROVIDERS`` order; the first frame
    that passes canonical validation becomes the base (single source of
    truth — no cross-provider history stitching beyond the legacy Sina tail
    supplement).  Every real provider call produces a ``FetchAttempt`` plus
    one capability-health observation; routing outcomes are expressed by
    ``FetchMetadata`` (``final_status`` / ``degraded`` /
    ``providers_used``), and the request-level outcome by
    ``outcome_status``/``is_normal_empty`` (see module docstring).

    ``adapters`` replaces the whole provider chain (tests inject fakes);
    by default the module-level ``ADAPTERS`` registry is used.
    """
    from . import a_stock

    chain = ADAPTERS if adapters is None else adapters
    attempts: list[FetchAttempt] = []

    base_frame: pd.DataFrame | None = None
    base_provider: str | None = None
    for provider, capability_id in DAILY_BAR_PROVIDERS:
        adapter = chain.get(provider)
        if adapter is None:
            record_fetch_observation(
                attempts,
                provider=provider,
                capability_id=capability_id,
                status=FETCH_NOT_CONFIGURED,
                started_at=utc_now_iso(),
                elapsed_ms=0,
                message="provider not available in this chain",
            )
            continue
        frame = _run_adapter(
            provider,
            capability_id,
            adapter,
            code,
            start_date,
            end_date,
            attempts,
            clock=clock,
        )
        if frame is not None:
            base_frame = frame
            base_provider = provider
            break

    if base_frame is None:
        if any(a.is_failure() for a in attempts):
            # Chain-level failure: providers broke and nothing usable arrived.
            raise DailyBarsRoutingError(attempts)
        limitations = ["all_sources_normal_empty"]
        if any(a.status == FETCH_NOT_CONFIGURED for a in attempts) and not any(
            a.status == FETCH_NORMAL_EMPTY for a in attempts
        ):
            limitations = ["all_sources_not_configured"]
        metadata = FetchMetadata(
            capability=DAILY_BARS_CAPABILITY,
            final_provider=None,
            retrieved_at=utc_now_iso(),
            data_as_of=None,
            limitations=limitations,
            attempts=attempts,
        )
        return FetchResult(data=_empty_canonical_frame(), metadata=metadata)

    # Legacy tail-supplement contract (see _supplement_with_sina).
    base_frame, sina_contributed, advanced_end, supplement_failed = (
        _supplement_with_sina(
            code,
            start_date,
            end_date,
            base_frame,
            chain,
            attempts,
            clock=clock,
        )
    )

    # Truthful provenance: every provider that contributed rows to the final
    # payload — including an overlap-only Sina supplement whose keep-last
    # rows replace base rows without advancing the last bar date.
    providers_used = [base_provider]
    if sina_contributed and base_provider != "sina":
        providers_used.append("sina")

    volume_unit = _volume_unit_for(providers_used)

    # Structured limitation sentinels (documented, consumer-neutral).  The
    # supplement facts are recorded separately from providers_used so the
    # legacy label can keep its presentation-only rule without the
    # structured provenance lying about (or hiding) contributions.
    limitations: list[str] = [f"volume_unit:{volume_unit}"]
    if advanced_end:
        limitations.append("sina_supplement_advanced_end")
    elif sina_contributed:
        limitations.append("sina_supplement_overlap_only")
    if supplement_failed:
        limitations.append("sina_supplement_failed")

    # Window filter (inclusive both ends), applied after the supplement step
    # exactly where the legacy renderer filtered.  Comparison values mirror
    # the legacy expression (un-normalized to_datetime) so datetime-bearing
    # arguments keep their historical semantics.
    start_dt = pd.to_datetime(start_date)
    end_dt = pd.to_datetime(end_date)
    frame = a_stock._normalize_ohlcv_dates(base_frame)
    frame = frame[(frame["Date"] >= start_dt) & (frame["Date"] <= end_dt)]
    frame = frame.reset_index(drop=True)

    stale = False
    data_as_of: str | None = None
    outcome_status: str | None = None
    if frame.empty:
        # Providers answered (possibly successfully) but the requested
        # window filtered everything away: the REQUEST produced no bars.
        # Declared explicitly via the generic outcome override so consumers
        # never have to guess from an empty dataframe.
        limitations.append("no_bars_in_requested_window")
        outcome_status = FETCH_NORMAL_EMPTY
    else:
        data_as_of = frame["Date"].max().strftime("%Y-%m-%d")
        coverage = a_stock._ohlcv_coverage(frame, end_date)
        if coverage["stale"]:
            # Bars-staleness policy: still a successful result (legacy never
            # hard-fails here); the flag travels in metadata and the legacy
            # renderer emits the historical_ohlcv_stale marker.
            stale = True
            limitations.append(
                "stale_coverage:"
                f"requested_end={coverage['requested_end']}"
                f",observed_max={coverage['observed_max']}"
                f",gap_days={coverage['gap_days']}"
            )

    # Volume unit contract travels on the frame (attrs) AND in metadata
    # (limitation above) — set last so the returned object carries it
    # regardless of intermediate pandas ops.
    frame.attrs["volume_unit"] = volume_unit

    metadata = FetchMetadata(
        capability=DAILY_BARS_CAPABILITY,
        final_provider=None,
        retrieved_at=utc_now_iso(),
        data_as_of=data_as_of,
        stale=stale,
        partial=False,
        limitations=limitations,
        attempts=attempts,
        providers_used=providers_used,
        outcome_status=outcome_status,
    )
    return FetchResult(data=frame, metadata=metadata)


# ---------------------------------------------------------------------------
# Isolated single-provider probe (live capability observability)
# ---------------------------------------------------------------------------


def probe_daily_bars_provider(
    provider: str,
    code: str,
    start_date: str,
    end_date: str,
    adapter: Callable[..., pd.DataFrame],
    *,
    clock: Callable[[], float] = time.monotonic,
) -> FetchResult[pd.DataFrame]:
    """Probe ONE provider bars capability in isolation.

    Live capability probes use this instead of the routing chain so that
    probing ``mootdx`` updates only ``mootdx:bars`` — never any other
    capability's health entry — and providers not part of the probe are NOT
    recorded as ``not_configured``.  The probe exercises the REAL
    capability contract: the adapter's frame must pass
    :func:`canonicalize_daily_bars_frame` exactly as in the routing chain —
    a non-empty malformed frame is ``failed_structure``, never a green
    probe.  Provider-level policies still apply inside the adapter (a stale
    vipdoc package is a policy rejection, not a hard failure); the probe
    reports the attempt's factual outcome.
    """
    capability_id = dict(DAILY_BAR_PROVIDERS)[provider]
    attempts: list[FetchAttempt] = []
    result = _run_adapter(
        provider,
        capability_id,
        adapter,
        code,
        start_date,
        end_date,
        attempts,
        clock=clock,
    )
    if result is not None:
        volume_unit = _volume_unit_for([provider])
        result.attrs["volume_unit"] = volume_unit
        metadata = FetchMetadata(
            capability=DAILY_BARS_CAPABILITY,
            final_provider=None,
            retrieved_at=utc_now_iso(),
            data_as_of=result["Date"].max().strftime("%Y-%m-%d"),
            limitations=[f"volume_unit:{volume_unit}"],
            attempts=attempts,
            providers_used=[provider],
        )
        return FetchResult(data=result, metadata=metadata)
    metadata = FetchMetadata(
        capability=DAILY_BARS_CAPABILITY,
        final_provider=None,
        retrieved_at=utc_now_iso(),
        attempts=attempts,
        limitations=[f"probe_unusable:{provider}"],
    )
    return FetchResult(data=_empty_canonical_frame(), metadata=metadata)


# ---------------------------------------------------------------------------
# Legacy renderer support
# ---------------------------------------------------------------------------

_SOURCE_LABELS = {
    "tdx_vipdoc": "vipdoc local (TDX official hsjday package)",
    "mootdx": "mootdx (TCP)",
    "sina": "sina HTTP (fallback)",
}


def legacy_source_label(metadata: FetchMetadata) -> str:
    """Map the routing result onto the frozen legacy ``# Data source`` label.

    Deliberately DECOUPLED from structured provenance (Phase 2.1):
    ``metadata.providers_used`` truthfully lists every payload contributor
    (including an overlap-only Sina supplement), but the legacy suffix rule
    is a presentation contract — the suffix appears only when Sina actually
    advanced the last bar date.  The label therefore keys off the engine's
    explicit ``sina_supplement_advanced_end`` limitation sentinel, never off
    ``providers_used``.
    """
    providers = list(metadata.providers_used)
    if not providers:
        return _SOURCE_LABELS["mootdx"]
    base = _SOURCE_LABELS.get(providers[0], providers[0])
    if "sina_supplement_advanced_end" in metadata.limitations:
        return f"{base} + sina HTTP supplement"
    return base
