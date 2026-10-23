"""Owner-controlled snapshot materialization (not a Research tool).

This module is the only code path allowed to touch a provider, and it is
meant to run only in the owner's controlled data environment with the pinned
``chstockdata`` release and the local raw data mounted. The Research actor's
workspace has neither the provider package, credentials, nor the raw tree;
the Research CLI never imports or calls this module.

``--mode BASIC`` materializes the frozen M1 first-batch ETF universe from the
declared warm-up start through the CandidateIntent Basic end and refuses any
later end date, so the physical Basic snapshot can never contain
out-of-sample rows.

``--mode OOS`` accepts exactly ONE verified freeze artifact (produced by the
Research CLI's ``oos-freeze``), verifies its self-digest, its embedded
intent, and its scope bindings strictly BEFORE any provider access, then
materializes ONLY the frozen OOS window through the same ``SnapshotWriter``
path and writes a freeze-specific receipt beside the snapshot. The output is
a freeze-specific immutable OOS snapshot directory; the command is one-shot
— no service, scheduler, or rewrite path exists. The first OOS bar's
``pre_close`` necessarily belongs to the Basic window and is never exposed,
so the OOS quality gate runs with ``require_pre_close=False`` (no M0
engine/execution/metric path consumes the bar's ``pre_close`` field).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from time import sleep
from typing import Final, Protocol, cast

from systematic_investing.adapters.chstockdata.provider import (
    ChStockDataClient,
    ChStockDataProvider,
    LibraryChStockDataClient,
)
from systematic_investing.data.contracts import ProviderFailure, ProviderSuccess
from systematic_investing.data.ports import (
    CalendarRequest,
    CorporateActionRequest,
    DailyBarRequest,
    TradabilityRequest,
)
from systematic_investing.data.quality import (
    REASON_UNKNOWN_INSTRUMENT_CLASSIFICATION,
    REASON_UNKNOWN_RULE_PROFILE,
    CanonicalDataset,
    CheckResult,
    CheckSeverity,
    CheckStatus,
    DataQualityGate,
    DatasetPolicy,
    GateResult,
)
from systematic_investing.data.snapshots import (
    DataSnapshotManifest,
    SnapshotWriter,
)
from systematic_investing.domain.identifiers import Exchange, InstrumentId
from systematic_investing.domain.instruments import FundSubtype, InstrumentType
from systematic_investing.domain.market import (
    Availability,
    AvailabilityBasis,
    CorporateAction,
    DailyBar,
    TradabilityStatus,
    TradabilityStatusKind,
    TradingSession,
)
from systematic_investing.domain.runs import RunPurpose
from systematic_investing.instrument_master.models import (
    UnknownInstrumentError,
    UnknownRuleError,
)
from systematic_investing.instrument_master.repository import (
    InstrumentMaster,
    default_m0_master,
)
from systematic_investing.research.artifacts import (
    ArtifactIntegrityError,
    read_json,
    write_new_json,
)
from systematic_investing.research.contracts import (
    M1_APPROVED_ETF_SYMBOLS,
    CandidateIntent,
)
from systematic_investing.research.intake import StockInstrumentReference
from systematic_investing.research.oos import (
    REASON_FREEZE_MISSING,
    REASON_STOCK_OOS_UNSUPPORTED,
    OosError,
    freeze_intent,
    validate_oos_scope,
    verify_freeze_against_intent,
    verify_freeze_payload,
)

MATERIALIZER_SCHEMA_VERSION: Final[str] = "research-materializer-1"
MODE_BASIC: Final[str] = "BASIC"
MODE_OOS: Final[str] = "OOS"
ASSET_ETF: Final[str] = "ETF"
ASSET_STOCK: Final[str] = "STOCK"
SNAPSHOT_QUALITY_PASS: Final[str] = "PASS"

MARKET_TIMEZONE: Final[timezone] = timezone(timedelta(hours=8))

REASON_UNKNOWN_MODE: str = "UNKNOWN_MODE"
REASON_ASSET_CLASS_MISMATCH: str = "ASSET_CLASS_MISMATCH"
REASON_END_AFTER_BASIC_END: str = "BASIC_MODE_REFUSES_POST_BASIC_END"
REASON_START_AFTER_WARMUP: str = "START_AFTER_WARMUP_START"
REASON_OUTPUT_EXISTS: str = "OUTPUT_PATH_EXISTS"
REASON_PROVIDER_FAILURE: str = "PROVIDER_FAILURE"
REASON_QUALITY_GATE_FAILED: str = "QUALITY_GATE_FAILED"
REASON_UNDECLARED_INSTRUMENT_SCOPE: str = "UNDECLARED_INSTRUMENT_SCOPE"
REASON_STOCK_COHORT_YEAR_FAILED: str = "STOCK_ANNUAL_COHORT_FAILED"
REASON_ARGUMENT_MISSING: str = "MATERIALIZER_ARGUMENT_MISSING"
REASON_ARGUMENT_MISMATCH: str = "MATERIALIZER_ARGUMENT_MISMATCH"

INSTRUMENT_MASTER_QUALIFICATION_NOTE: Final[str] = (
    "The M0 seed Instrument Master must cover every materialized instrument "
    "for the whole requested window; qualification gates run before any "
    "snapshot is written."
)


class MaterializationError(Exception):
    """Typed materialization failure; messages carry no secrets."""


@dataclass(frozen=True)
class MaterializationPlan:
    """The validated request scope for one Basic materialization."""

    intent: CandidateIntent
    start: date
    end: date
    instrument_symbols: tuple[str, ...]

    def to_payload(self) -> dict[str, object]:
        return {
            "materializer_schema_version": MATERIALIZER_SCHEMA_VERSION,
            "mode": MODE_BASIC,
            "asset_class": self.intent.asset_class.value,
            "lineage_id": self.intent.lineage_id,
            "intent_digest": self.intent.intent_digest,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "instrument_symbols": list(self.instrument_symbols),
        }


def validate_materialization_request(
    intent: CandidateIntent,
    *,
    mode: str,
    asset_class: str,
    start: date,
    end: date,
) -> MaterializationPlan:
    """Validate the requested scope against the frozen CandidateIntent.

    ``--mode BASIC`` refuses any end after the intent's Basic end and any
    start after the warm-up start; anything else would physically extend a
    Basic snapshot into out-of-sample territory.
    """
    if mode != MODE_BASIC:
        raise MaterializationError(
            f"{REASON_UNKNOWN_MODE}: mode {mode!r} is not implemented; M1 "
            "materialization accepts only BASIC and OOS"
        )
    if intent.asset_class.value != asset_class:
        raise MaterializationError(
            f"{REASON_ASSET_CLASS_MISMATCH}: requested asset class "
            f"{asset_class!r} does not match the intent {intent.asset_class.value!r}"
        )
    if end > intent.basic_end:
        raise MaterializationError(
            f"{REASON_END_AFTER_BASIC_END}: BASIC materialization may not "
            f"reach past the CandidateIntent Basic end "
            f"{intent.basic_end.isoformat()} (requested end "
            f"{end.isoformat()})"
        )
    if start > intent.warm_up_start:
        raise MaterializationError(
            f"{REASON_START_AFTER_WARMUP}: a Basic snapshot must include the "
            f"warm-up window from {intent.warm_up_start.isoformat()} "
            f"(requested start {start.isoformat()})"
        )
    if intent.asset_class.value == ASSET_STOCK:
        # Stock membership is data-derived: the owner-side PIT formation
        # below fixes the materialized instrument scope, never the intent.
        return MaterializationPlan(
            intent=intent, start=start, end=end, instrument_symbols=()
        )
    return MaterializationPlan(
        intent=intent,
        start=start,
        end=end,
        instrument_symbols=tuple(
            M1_APPROVED_ETF_SYMBOLS if intent.asset_class.value == ASSET_ETF else ()
        ),
    )


class _ScopedPlan(Protocol):
    """The window/instrument surface the shared provider-fetch helpers need."""

    @property
    def start(self) -> date: ...

    @property
    def end(self) -> date: ...

    @property
    def instrument_symbols(self) -> tuple[str, ...]: ...


@dataclass(frozen=True)
class OosMaterializationPlan:
    """The validated one-freeze request scope for one OOS materialization.

    Built exclusively by :func:`prepare_oos_materialization` from a verified
    freeze artifact; every field is derived from the freeze, never from CLI
    arguments.
    """

    freeze_id: str
    freeze_digest: str
    intent: CandidateIntent
    selected_variant_id: str
    start: date
    end: date
    instrument_symbols: tuple[str, ...]
    output_dir: Path

    def to_payload(self) -> dict[str, object]:
        return {
            "materializer_schema_version": MATERIALIZER_SCHEMA_VERSION,
            "mode": MODE_OOS,
            "freeze_id": self.freeze_id,
            "freeze_digest": self.freeze_digest,
            "lineage_id": self.intent.lineage_id,
            "intent_digest": self.intent.intent_digest,
            "selected_variant_id": self.selected_variant_id,
            "requested_oos_start": self.start.isoformat(),
            "requested_oos_end": self.end.isoformat(),
            "instrument_symbols": list(self.instrument_symbols),
        }


def _wrap_oos_error(error: OosError) -> MaterializationError:
    return MaterializationError(str(error))


def prepare_oos_materialization(
    freeze_path: Path,
    output_dir: Path,
) -> OosMaterializationPlan:
    """Validate one freeze artifact into an OOS materialization plan.

    Pure validation, offline and strictly BEFORE any provider exists: the
    freeze file must exist, verify against its own digest, embed a valid
    intent, and bind the intent's declared OOS scope and specs. The output
    path must not exist; snapshots are immutable and never rewritten.
    """
    freeze_path = Path(freeze_path)
    output_dir = Path(output_dir)
    if not freeze_path.exists():
        raise MaterializationError(
            f"{REASON_FREEZE_MISSING}: no freeze artifact at {freeze_path}; "
            "OOS materialization accepts exactly one verified freeze"
        )
    try:
        payload = read_json(freeze_path)
    except ArtifactIntegrityError as error:
        raise MaterializationError(
            f"OOS_FREEZE_INVALID: the freeze artifact is unreadable: {error}"
        ) from error
    try:
        payload = verify_freeze_payload(payload)
        intent = freeze_intent(payload)
        verify_freeze_against_intent(payload, intent)
    except OosError as error:
        raise _wrap_oos_error(error) from error
    if intent.asset_class.value == ASSET_STOCK:
        raise MaterializationError(
            f"{REASON_STOCK_OOS_UNSUPPORTED}: Stock OOS materialization "
            "requires data-derived annual schedule semantics that M1 has "
            "not defined; refusing instead of inventing a universe"
        )
    start = date.fromisoformat(str(payload["requested_oos_start"]))
    end = date.fromisoformat(str(payload["requested_oos_end"]))
    try:
        validate_oos_scope(intent, start=start, end=end)
    except OosError as error:
        raise _wrap_oos_error(error) from error
    plan = OosMaterializationPlan(
        freeze_id=str(payload["freeze_id"]),
        freeze_digest=str(payload["freeze_digest"]),
        intent=intent,
        selected_variant_id=str(payload["selected_variant_id"]),
        start=start,
        end=end,
        instrument_symbols=tuple(
            sorted(str(item) for item in intent.universe_policy.instrument_ids)
        ),
        output_dir=output_dir,
    )
    _oos_preflight(plan, output_dir, master=default_m0_master())
    return plan


def _oos_preflight(
    plan: OosMaterializationPlan,
    output_dir: Path,
    *,
    master: InstrumentMaster,
) -> dict[str, object]:
    """Offline OOS preflight: output immutability, scope, and Instrument
    Master authority over the whole requested window — no provider calls."""
    _require_unused_output_directory(
        output_dir,
        refused_because=(
            "the OOS snapshot is freeze-specific, immutable, and never rewritten"
        ),
    )
    universe_symbols = tuple(
        sorted(str(item) for item in plan.intent.universe_policy.instrument_ids)
    )
    if tuple(sorted(plan.instrument_symbols)) != universe_symbols:
        raise MaterializationError(
            f"{REASON_UNDECLARED_INSTRUMENT_SCOPE}: OOS materialization is "
            f"scoped to the frozen universe {list(universe_symbols)}, got "
            f"{list(plan.instrument_symbols)}"
        )
    _require_instrument_master_coverage(
        instrument_symbols=plan.instrument_symbols,
        session_dates=_window_dates(plan.start, plan.end),
        master=master,
    )
    _require_approved_etf_subtypes(plan.instrument_symbols, plan.start, master)
    return {
        **plan.to_payload(),
        "status": SNAPSHOT_QUALITY_PASS,
        "preflight_only": True,
        "checked_start": plan.start.isoformat(),
        "checked_end": plan.end.isoformat(),
        "checked_instrument_count": len(plan.instrument_symbols),
    }


def _require_approved_etf_subtypes(
    instrument_symbols: tuple[str, ...],
    as_of: date,
    master: InstrumentMaster,
) -> None:
    approved_subtypes = {
        FundSubtype.BROAD_BASED_EQUITY,
        FundSubtype.GOLD,
        FundSubtype.BOND,
    }
    for symbol in instrument_symbols:
        instrument = master.resolve_instrument(InstrumentId.parse(symbol), as_of)
        if (
            instrument.instrument_type is not InstrumentType.EXCHANGE_TRADED_FUND
            or instrument.fund_subtype not in approved_subtypes
        ):
            raise MaterializationError(
                f"{REASON_UNDECLARED_INSTRUMENT_SCOPE}: {symbol} is not an "
                "explicitly approved ETF subtype"
            )


def materialize_oos_snapshot(
    plan: OosMaterializationPlan,
    *,
    provider_factory: Callable[[], ChStockDataProvider] | None = None,
) -> dict[str, object]:
    """Materialize the freeze-scoped OOS snapshot in the controlled
    environment.

    One-shot: the provider is asked for exactly the frozen OOS window, the
    canonical dataset passes the data quality gate, and the snapshot plus
    gate and freeze receipts are written create-new into the empty output
    directory. ``provider_factory`` is a test seam only; production uses the
    real pinned provider.
    """
    master = default_m0_master()
    _oos_preflight(plan, plan.output_dir, master=master)
    provider = provider_factory() if provider_factory is not None else _provider()
    provider_version = _provider_version(provider)
    dataset = _fetch_canonical_dataset(
        plan,
        provider,
        window_label="requested OOS window",
        scope_label="frozen OOS scope",
    )
    # require_pre_close=False: the first OOS bar's pre_close belongs to the
    # Basic window and must never be exposed; no M0 engine path consumes it.
    gate_result, manifest = _persist_gated_snapshot(
        dataset,
        intended_decision_session=plan.end,
        output_dir=plan.output_dir,
        master=master,
        policy=DatasetPolicy(require_pre_close=False),
        provider_name=provider.PROVIDER_NAME,
        provider_version=provider_version,
        adapter_version=provider.ADAPTER_VERSION,
    )
    receipt = {
        **_oos_receipt_payload(plan, dataset, snapshot_id=str(manifest.snapshot_id)),
        "snapshot_dir": str(plan.output_dir),
    }
    _write_snapshot_receipts(
        plan.output_dir,
        gate_result,
        snapshot_id=str(manifest.snapshot_id),
        extra_receipts=(("oos-receipt.json", receipt),),
        failure_label="OOS receipt",
    )
    return receipt


def _oos_receipt_payload(
    plan: OosMaterializationPlan,
    dataset: CanonicalDataset,
    *,
    snapshot_id: str,
) -> dict[str, object]:
    """The freeze-specific receipt binding snapshot content to the freeze."""
    return {
        "receipt_schema_version": "research-oos-receipt-1",
        "materializer_schema_version": MATERIALIZER_SCHEMA_VERSION,
        "mode": MODE_OOS,
        "freeze_id": plan.freeze_id,
        "freeze_digest": plan.freeze_digest,
        "lineage_id": plan.intent.lineage_id,
        "intent_digest": plan.intent.intent_digest,
        "selected_variant_id": plan.selected_variant_id,
        "requested_oos_start": plan.start.isoformat(),
        "requested_oos_end": plan.end.isoformat(),
        "snapshot_id": snapshot_id,
        "min_session": min(bar.session_date for bar in dataset.daily_bars).isoformat(),
        "max_session": max(bar.session_date for bar in dataset.daily_bars).isoformat(),
        "bar_count": len(dataset.daily_bars),
        "tradability_count": len(dataset.tradability),
        "corporate_action_count": len(dataset.corporate_actions),
        "quality_status": SNAPSHOT_QUALITY_PASS,
        "gate_receipt": "gate-receipt.json",
    }


def _require_unused_output_directory(output_dir: Path, *, refused_because: str) -> None:
    """Snapshots are immutable: an existing output directory is a typed
    refusal, never a rewrite."""
    if output_dir.exists():
        raise MaterializationError(
            f"{REASON_OUTPUT_EXISTS}: {output_dir} already exists; {refused_because}"
        )


def _window_dates(start: date, end: date) -> tuple[date, ...]:
    """Every calendar date in the requested window; instrument and rule
    profiles are effective-dated, so authority is checked per date."""
    return tuple(
        start + timedelta(days=offset)
        for offset in range((end - start).days + 1)
    )


def _require_instrument_master_coverage(
    *,
    instrument_symbols: tuple[str, ...],
    session_dates: tuple[date, ...],
    master: InstrumentMaster,
) -> None:
    """The first approved-profile coverage failure fails the request closed."""
    coverage_checks = _instrument_master_coverage_checks(
        instrument_symbols=instrument_symbols,
        session_dates=session_dates,
        master=master,
    )
    if coverage_checks:
        _raise_quality_check_failures(coverage_checks)


def _fetch_canonical_dataset(
    plan: _ScopedPlan,
    provider: ChStockDataProvider,
    *,
    window_label: str,
    scope_label: str,
) -> CanonicalDataset:
    """Shared fetch sequence for every mode: merged calendar, open-session
    guard, bars guard, tradability, corporate actions, canonical dataset.
    Basic and OOS cannot silently diverge on fetch semantics."""
    _calendar_id, sessions = _merged_calendar(plan, provider)
    open_dates = tuple(
        session.session_date for session in sessions if session.is_open
    )
    if not open_dates:
        raise MaterializationError(
            f"{REASON_PROVIDER_FAILURE}: the {window_label} has no open "
            f"sessions between {plan.start.isoformat()} and "
            f"{plan.end.isoformat()}"
        )
    bars = _daily_bars(plan, provider)
    if not bars:
        raise MaterializationError(
            f"{REASON_PROVIDER_FAILURE}: provider returned an empty daily "
            f"bar set for the {scope_label}"
        )
    tradability = _tradability(plan, provider, open_dates)
    actions = _corporate_actions(plan, provider)
    return CanonicalDataset(
        daily_bars=tuple(bars),
        sessions=tuple(sessions),
        tradability=tuple(tradability),
        corporate_actions=tuple(actions),
        rule_candidates=(),
    )


def _persist_gated_snapshot(
    dataset: CanonicalDataset,
    *,
    intended_decision_session: date,
    output_dir: Path,
    master: InstrumentMaster,
    policy: DatasetPolicy,
    provider_name: str,
    provider_version: str,
    adapter_version: str,
) -> tuple[GateResult, DataSnapshotManifest]:
    """Shared gate-and-persist tail for every mode: data quality gate, status
    check, immutable snapshot write. Basic and OOS cannot silently diverge on
    cutoff, writer identity, or quality binding."""
    final_decision_cutoff = datetime.combine(
        max(bar.session_date for bar in dataset.daily_bars),
        datetime.min.time(),
        tzinfo=MARKET_TIMEZONE,
    ).replace(hour=15, minute=30)
    gate = DataQualityGate(master=master, policy=policy)
    gate_result = gate.evaluate(
        dataset,
        purpose=RunPurpose.DECISION,
        intended_decision_session=intended_decision_session,
        information_cutoff=final_decision_cutoff,
        evaluated_at=datetime.now(MARKET_TIMEZONE),
    )
    if gate_result.status.value != SNAPSHOT_QUALITY_PASS:
        _raise_quality_gate_failure(gate_result)
    writer = SnapshotWriter(
        provider_name=provider_name,
        provider_version=provider_version,
        adapter_version=adapter_version,
    )
    cutoff = datetime.combine(
        intended_decision_session, datetime.min.time(), tzinfo=MARKET_TIMEZONE
    ).replace(hour=15, minute=30)
    manifest = writer.persist(
        dataset,
        snapshot_dir=output_dir,
        created_at=datetime.now(MARKET_TIMEZONE),
        knowledge_cutoff=cutoff,
        retrieved_at=datetime.now(MARKET_TIMEZONE),
        quality_report_id=gate_result.content_digest(),
        quality_status=gate_result.status.value,
    )
    return gate_result, manifest


def _write_snapshot_receipts(
    output_dir: Path,
    gate_result: GateResult,
    *,
    snapshot_id: str,
    extra_receipts: Sequence[tuple[str, Mapping[str, object]]] = (),
    failure_label: str,
) -> None:
    """Persist the qualification receipts create-new beside the snapshot.

    Extra receipts (freeze-specific, instrument reference) are written before
    the gate receipt; a partial receipt set fails closed."""
    try:
        for filename, payload in extra_receipts:
            write_new_json(Path(output_dir) / filename, payload)
        write_gate_receipt(output_dir, gate_result, snapshot_id=snapshot_id)
    except ArtifactIntegrityError as error:
        raise MaterializationError(
            f"{REASON_OUTPUT_EXISTS}: the {failure_label} could not be "
            f"persisted: {error}; the snapshot exists without its "
            "qualification evidence"
        ) from error


def _provider() -> ChStockDataProvider:
    client: LibraryChStockDataClient = LibraryChStockDataClient()
    return ChStockDataProvider(
        client=cast("ChStockDataClient", client),
        clock=lambda: datetime.now(MARKET_TIMEZONE),
    )


def _require_success[ResultT](
    outcome: ProviderSuccess[ResultT] | ProviderFailure,
    capability: str,
) -> ProviderSuccess[ResultT]:
    if isinstance(outcome, ProviderFailure):
        raise MaterializationError(
            f"{REASON_PROVIDER_FAILURE}: {capability} failed with "
            f"{outcome.error_code.value}: {outcome.message}"
        )
    return outcome


def _merged_calendar(
    plan: _ScopedPlan,
    provider: ChStockDataProvider,
    exchanges: tuple[str, ...] | None = None,
) -> tuple[str, tuple[TradingSession, ...]]:
    """One merged calendar across the plan's exchanges.

    Cross-exchange alignment is verified, never assumed: both exchanges must
    agree on every date in the requested window or the materialization fails
    closed.
    """
    open_dates: dict[date, set[str]] = {}
    for exchange in exchanges if exchanges is not None else _exchange_symbols(plan):
        outcome = _require_success(
            provider.fetch_calendar(
                CalendarRequest(
                    calendar_id=exchange,
                    start_date=plan.start,
                    end_date=plan.end,
                )
            ),
            f"calendar:{exchange}",
        )
        for session in outcome.records:
            state = open_dates.setdefault(session.session_date, set())
            state.add(exchange if session.is_open else "CLOSED:" + exchange)
    sessions: list[TradingSession] = []
    merged_id = "CN-ETF-M1-V1"
    for session_date in sorted(open_dates):
        flags = open_dates[session_date]
        open_exchanges = {flag for flag in flags if not flag.startswith("CLOSED:")}
        closed_exchanges = {
            flag.removeprefix("CLOSED:") for flag in flags if flag.startswith("CLOSED:")
        }
        if open_exchanges and closed_exchanges:
            raise MaterializationError(
                f"cross-exchange calendar misalignment on {session_date.isoformat()}: "
                f"open on {sorted(open_exchanges)}, closed on {sorted(closed_exchanges)}"
            )
        is_open = bool(open_exchanges)
        sessions.append(
            _trading_session(merged_id, session_date, is_open)
        )
    return merged_id, tuple(sessions)


def _exchange_symbols(plan: _ScopedPlan) -> tuple[str, ...]:
    exchanges: set[str] = set()
    for symbol in plan.instrument_symbols:
        exchanges.add(symbol.partition(":")[0])
    return tuple(sorted(exchanges))


def _trading_session(
    calendar_id: str, session_date: date, is_open: bool
) -> TradingSession:
    from systematic_investing.domain.market import TradingSession

    return TradingSession(
        calendar_id=calendar_id,
        session_date=session_date,
        is_open=is_open,
        note=None,
        snapshot_version="CN-ETF-M1-CAL-1",
    )


def _daily_bars(
    plan: _ScopedPlan, provider: ChStockDataProvider
) -> tuple[DailyBar, ...]:
    from systematic_investing.domain.identifiers import InstrumentId

    symbols = sorted(plan.instrument_symbols)
    request = DailyBarRequest(
        instrument_ids=tuple(InstrumentId.parse(symbol) for symbol in symbols),
        start_date=plan.start,
        end_date=plan.end,
    )
    outcome = _require_success(provider.fetch_daily_bars(request), "daily_bars")
    return outcome.records


def _tradability(
    plan: _ScopedPlan,
    provider: ChStockDataProvider,
    open_dates: tuple[date, ...],
) -> tuple[TradabilityStatus, ...]:
    from systematic_investing.domain.identifiers import InstrumentId

    records: list[TradabilityStatus] = []
    symbols = sorted(plan.instrument_symbols)
    for session_date in open_dates:
        request = TradabilityRequest(
            instrument_ids=tuple(InstrumentId.parse(symbol) for symbol in symbols),
            session_date=session_date,
        )
        outcome = _require_success(
            provider.fetch_tradability(request), f"tradability:{session_date}"
        )
        records.extend(outcome.records)
    return tuple(records)


def _corporate_actions(
    plan: _ScopedPlan,
    provider: ChStockDataProvider,
    *,
    instrument_kind: str = "ETF",
) -> tuple[CorporateAction, ...]:
    from systematic_investing.domain.identifiers import InstrumentId

    symbols = sorted(plan.instrument_symbols)
    request = CorporateActionRequest(
        instrument_ids=tuple(InstrumentId.parse(symbol) for symbol in symbols),
        start_date=plan.start,
        end_date=plan.end,
        instrument_kind=instrument_kind,
    )
    outcome = _require_success(
        provider.fetch_corporate_actions(request), "corporate_actions"
    )
    return outcome.records


def _instrument_master_coverage_checks(
    *,
    instrument_symbols: tuple[str, ...],
    session_dates: tuple[date, ...],
    master: InstrumentMaster,
) -> tuple[CheckResult, ...]:
    """Return the first approved-profile coverage failure per instrument.

    This is a cheap owner-boundary preflight over the same Instrument Master
    instance later passed to the Data Quality Gate. It prevents thousands of
    provider calls when the approved authority cannot cover the requested
    historical window; the full gate still evaluates the canonical dataset.
    """
    from systematic_investing.domain.identifiers import InstrumentId

    failures: list[CheckResult] = []
    for instrument_symbol in sorted(instrument_symbols):
        instrument_id = InstrumentId.parse(instrument_symbol)
        for session_date in sorted(session_dates):
            try:
                master.resolve_rules(instrument_id, session_date)
            except UnknownInstrumentError as error:
                failures.append(
                    CheckResult(
                        check_id="INSTRUMENT_MASTER_AUTHORITY",
                        status=CheckStatus.FAIL,
                        severity=CheckSeverity.BLOCKING,
                        reason_code=REASON_UNKNOWN_INSTRUMENT_CLASSIFICATION,
                        affected_scope=(str(instrument_id), session_date.isoformat()),
                        observed=f"classification/profile lookup failed: {error}",
                        expected="approved Instrument Master classification",
                    )
                )
                break
            except UnknownRuleError as error:
                failures.append(
                    CheckResult(
                        check_id="INSTRUMENT_MASTER_AUTHORITY",
                        status=CheckStatus.FAIL,
                        severity=CheckSeverity.BLOCKING,
                        reason_code=REASON_UNKNOWN_RULE_PROFILE,
                        affected_scope=(str(instrument_id), session_date.isoformat()),
                        observed=f"rule-profile lookup failed: {error}",
                        expected=(
                            "approved lot/settlement/price-limit/market-fee profiles"
                        ),
                    )
                )
                break
    return tuple(failures)


def _check_diagnostic(check: CheckResult) -> str:
    instrument_id = check.affected_scope[0] if check.affected_scope else "UNKNOWN"
    session_date = (
        check.affected_scope[1] if len(check.affected_scope) > 1 else "UNKNOWN"
    )
    lookup = (
        "classification/profile"
        if check.reason_code == REASON_UNKNOWN_INSTRUMENT_CLASSIFICATION
        else "rule-profile"
        if check.reason_code == REASON_UNKNOWN_RULE_PROFILE
        else "quality-gate"
    )
    return (
        f"check={check.check_id},reason={check.reason_code},"
        f"instrument_id={instrument_id},session_date={session_date},lookup={lookup},"
        f"observed={check.observed or 'unspecified'}"
    )


def _raise_quality_check_failures(checks: tuple[CheckResult, ...]) -> None:
    reasons = list(dict.fromkeys(check.reason_code for check in checks))
    details = "; ".join(_check_diagnostic(check) for check in checks[:20])
    raise MaterializationError(
        f"{REASON_QUALITY_GATE_FAILED}: blocking preflight returned reasons "
        f"{reasons}; details [{details}]; no snapshot was written"
    )


def preflight_materialization(
    plan: MaterializationPlan,
    output_dir: Path,
    *,
    master: InstrumentMaster,
) -> dict[str, object]:
    """Validate the complete static scope without constructing a provider.

    This check deliberately covers every calendar date in the requested
    interval. Instrument and rule profiles are effective-dated reference data,
    so their authority can be established without downloading a trading
    calendar or any historical market facts.
    """
    _require_unused_output_directory(
        output_dir, refused_because="snapshots are immutable and never rewritten"
    )

    if plan.intent.asset_class.value == ASSET_STOCK:
        # The stock instrument scope is data-derived at materialization time;
        # preflight can only bind the frozen policy and the static window.
        from systematic_investing.research.contracts import STOCK_ANNUAL_POLICY_NAME
        from systematic_investing.research.universe import AnnualUniversePolicy

        if plan.intent.universe_policy.policy_name != STOCK_ANNUAL_POLICY_NAME:
            raise MaterializationError(
                f"{REASON_UNDECLARED_INSTRUMENT_SCOPE}: STOCK materialization "
                f"requires the frozen {STOCK_ANNUAL_POLICY_NAME} policy"
            )
        policy = AnnualUniversePolicy.standard()
        return {
            "materializer_schema_version": MATERIALIZER_SCHEMA_VERSION,
            "mode": MODE_BASIC,
            "asset_class": ASSET_STOCK,
            "status": SNAPSHOT_QUALITY_PASS,
            "preflight_only": True,
            "lineage_id": plan.intent.lineage_id,
            "intent_digest": plan.intent.intent_digest,
            "checked_start": plan.start.isoformat(),
            "checked_end": plan.end.isoformat(),
            "universe_policy": STOCK_ANNUAL_POLICY_NAME,
            "policy_thresholds": {
                "minimum_listing_sessions": policy.minimum_listing_sessions,
                "trailing_amount_sessions": policy.trailing_amount_sessions,
                "minimum_cohort_size": policy.minimum_cohort_size,
                "maximum_cohort_size": policy.maximum_cohort_size,
            },
        }

    approved_scope = tuple(sorted(M1_APPROVED_ETF_SYMBOLS))
    requested_scope = tuple(sorted(plan.instrument_symbols))
    if requested_scope != approved_scope:
        raise MaterializationError(
            f"{REASON_UNDECLARED_INSTRUMENT_SCOPE}: ETF Basic materialization "
            f"requires exactly {list(approved_scope)}, got {list(requested_scope)}"
        )

    intent_scope = {str(item) for item in plan.intent.universe_policy.instrument_ids}
    outside_intent = sorted(intent_scope - set(requested_scope))
    if outside_intent:
        raise MaterializationError(
            f"{REASON_UNDECLARED_INSTRUMENT_SCOPE}: CandidateIntent instruments "
            f"are outside the materialization scope: {outside_intent}"
        )

    _require_instrument_master_coverage(
        instrument_symbols=plan.instrument_symbols,
        session_dates=_window_dates(plan.start, plan.end),
        master=master,
    )

    _require_approved_etf_subtypes(requested_scope, plan.start, master)

    return {
        "materializer_schema_version": MATERIALIZER_SCHEMA_VERSION,
        "mode": MODE_BASIC,
        "status": SNAPSHOT_QUALITY_PASS,
        "preflight_only": True,
        "lineage_id": plan.intent.lineage_id,
        "intent_digest": plan.intent.intent_digest,
        "checked_start": plan.start.isoformat(),
        "checked_end": plan.end.isoformat(),
        "checked_instrument_count": len(requested_scope),
        "instrument_symbols": list(requested_scope),
    }


def _raise_quality_gate_failure(gate_result: GateResult) -> None:
    blocking = tuple(
        check
        for check in gate_result.checks
        if check.status is CheckStatus.FAIL
        and check.severity is CheckSeverity.BLOCKING
    )
    details = "; ".join(_check_diagnostic(check) for check in blocking[:20])
    raise MaterializationError(
        f"{REASON_QUALITY_GATE_FAILED}: the data quality gate returned "
        f"{gate_result.status.value} with reasons {list(gate_result.reason_codes)}; "
        f"details [{details}]; no snapshot was written"
    )


def materialize_basic_snapshot(
    plan: MaterializationPlan, output_dir: Path
) -> dict[str, object]:
    """Materialize the Basic-only canonical snapshot in the controlled
    environment.

    Provider failure, empty data, and partial coverage stay distinct typed
    failures; the data quality gate must PASS before any snapshot is written;
    and the output path is created once, never overwritten.
    """
    master = default_m0_master()
    preflight_materialization(plan, output_dir, master=master)
    if plan.intent.asset_class.value == ASSET_STOCK:
        return materialize_stock_basic_snapshot(plan, output_dir)
    provider = _provider()
    provider_version = _provider_version(provider)
    dataset = _fetch_canonical_dataset(
        plan,
        provider,
        window_label="requested window",
        scope_label="requested scope",
    )
    gate_result, manifest = _persist_gated_snapshot(
        dataset,
        intended_decision_session=plan.end,
        output_dir=output_dir,
        master=master,
        policy=DatasetPolicy(),
        provider_name=provider.PROVIDER_NAME,
        provider_version=provider_version,
        adapter_version=provider.ADAPTER_VERSION,
    )
    _write_snapshot_receipts(
        output_dir,
        gate_result,
        snapshot_id=str(manifest.snapshot_id),
        failure_label="gate receipt",
    )
    max_session = max(bar.session_date for bar in dataset.daily_bars)
    return {
        "materializer_schema_version": MATERIALIZER_SCHEMA_VERSION,
        "mode": MODE_BASIC,
        "lineage_id": plan.intent.lineage_id,
        "intent_digest": plan.intent.intent_digest,
        "snapshot_id": manifest.snapshot_id,
        "snapshot_dir": str(output_dir),
        "min_session": min(bar.session_date for bar in dataset.daily_bars).isoformat(),
        "max_session": max_session.isoformat(),
        "bar_count": len(dataset.daily_bars),
        "tradability_count": len(dataset.tradability),
        "corporate_action_count": len(dataset.corporate_actions),
        "quality_status": SNAPSHOT_QUALITY_PASS,
        "gate_receipt": "gate-receipt.json",
    }


# --- Stock Basic materialization ---------------------------------------------

STOCK_REFERENCE_VERSION: Final[str] = "M1-STOCK-REF-V1"
STOCK_REFERENCE_SCHEMA: Final[str] = "research-stock-reference-1"
MAIN_BOARD_SH_PREFIX: Final[str] = "60"
MAIN_BOARD_SZ_PREFIX: Final[str] = "00"


@dataclass(frozen=True)
class _StockFormationOutcome:
    """Owner-side PIT formation over the raw local market history."""

    cohort_sizes: dict[int, int]
    union: tuple[InstrumentId, ...]


def _stock_candidate_instruments() -> tuple[InstrumentId, ...]:
    """Every main-board A-share with local vipdoc history.

    Shanghai ``60xxxx`` and Shenzhen ``00xxxx`` symbols only: ChiNext,
    STAR Market and BSE names are outside the attested M1 scope, and the
    enumeration source is the pinned local vipdoc manifest itself.
    """
    from systematic_investing.adapters.chstockdata.provider import (
        import_chstockdata_library,
    )

    library = import_chstockdata_library()
    status_probe = getattr(library, "vipdoc_history_status", None)
    if not callable(status_probe):
        raise MaterializationError(
            f"{REASON_PROVIDER_FAILURE}: the pinned chstockdata release does "
            "not expose vipdoc_history_status"
        )
    status = cast("dict[str, object]", status_probe())
    manifest = status.get("manifest") if isinstance(status, dict) else None
    tickers: object = None
    if isinstance(manifest, dict):
        tickers = manifest.get("max_bar_date")
    if not isinstance(tickers, dict) or not tickers:
        raise MaterializationError(
            f"{REASON_PROVIDER_FAILURE}: the local vipdoc manifest is "
            "unavailable; the pinned local market history must be mounted"
        )
    candidates: list[InstrumentId] = []
    for ticker in sorted(tickers):
        symbol = str(ticker)
        if not symbol.isdigit() or len(symbol) != 6:
            continue
        if symbol.startswith(MAIN_BOARD_SH_PREFIX):
            exchange = "XSHG"
        elif symbol.startswith(MAIN_BOARD_SZ_PREFIX):
            exchange = "XSHE"
        else:
            continue
        candidates.append(InstrumentId(exchange=Exchange(exchange), symbol=symbol))
    if not candidates:
        raise MaterializationError(
            f"{REASON_PROVIDER_FAILURE}: the local vipdoc manifest names no "
            "main-board A-share symbols"
        )
    return tuple(candidates)


def _vipdoc_amount_history(
    library: object, instrument_id: InstrumentId, start: date, end: date
) -> tuple[tuple[date, Decimal], ...]:
    """One instrument's raw ``(session, amount)`` history from vipdoc."""
    from systematic_investing.adapters.chstockdata.provider import _frame_records

    market = "sh" if instrument_id.exchange.value == "XSHG" else "sz"
    load = getattr(library, "load_vipdoc_daily", None)
    if not callable(load):
        raise MaterializationError(
            f"{REASON_PROVIDER_FAILURE}: the pinned chstockdata release does "
            "not expose load_vipdoc_daily"
        )
    try:
        frame = load(
            instrument_id.symbol,
            start.isoformat(),
            end.isoformat(),
            market=market,
        )
        if frame is None or bool(getattr(frame, "empty", True)):
            return ()
        _columns, rows = _frame_records(frame)
    except MaterializationError:
        raise
    except Exception as error:
        raise MaterializationError(
            f"{REASON_PROVIDER_FAILURE}: vipdoc history for {instrument_id} "
            f"failed: {type(error).__name__}: {error}"
        ) from error
    history: list[tuple[date, Decimal]] = []
    for row in rows:
        raw_date = row.get("Date")
        raw_amount = row.get("Amount")
        if not isinstance(raw_date, str) or raw_amount is None:
            continue
        amount = Decimal(str(raw_amount))
        if not amount.is_finite() or amount <= 0:
            continue
        history.append((date.fromisoformat(raw_date[:10]), amount))
    history.sort(key=lambda item: item[0])
    return tuple(history)


def _form_owner_stock_cohorts(
    plan: MaterializationPlan,
    candidates: tuple[InstrumentId, ...],
    open_dates: tuple[date, ...],
) -> _StockFormationOutcome:
    """Form the annual PIT cohorts from raw facts with the frozen policy.

    Every formation uses only facts knowable at its year-end cutoff, the
    same :func:`form_annual_schedule` code the Research side re-runs on the
    materialized snapshot, and the standard M1 thresholds (>=250 listed
    sessions, trailing 60-session median amount, top 50, minimum 20). The
    eligible pool is the whole local main-board market, so the persisted
    cohort union is a PIT-safe reduction: any later re-formation on the
    snapshot alone reproduces every Basic-window cohort exactly.
    """
    from systematic_investing.research.universe import (
        AnnualUniversePolicy,
        StockFormationFact,
        StockIdentityStatus,
        TrailingAmount,
        form_annual_schedule,
    )

    policy = AnnualUniversePolicy.standard()
    formation_years = tuple(
        range(plan.intent.basic_start.year - 1, plan.intent.basic_end.year + 1)
    )
    cutoffs: dict[int, date] = {}
    for year in formation_years:
        december = [
            session_date
            for session_date in open_dates
            if session_date.year == year and session_date.month == 12
        ]
        if december:
            cutoffs[year] = max(december)
    if not cutoffs:
        raise MaterializationError(
            f"{REASON_PROVIDER_FAILURE}: the calendar window carries no "
            "year-end formation cutoffs"
        )
    from systematic_investing.adapters.chstockdata.provider import (
        import_chstockdata_library,
    )

    library = import_chstockdata_library()
    facts: list[StockFormationFact] = []
    for instrument_id in candidates:
        history = _vipdoc_amount_history(library, instrument_id, plan.start, plan.end)
        if not history:
            continue
        for _formation_year, cutoff in sorted(cutoffs.items()):
            through = [item for item in history if item[0] <= cutoff]
            if not through:
                continue
            window = through[-policy.trailing_amount_sessions :]
            facts.append(
                StockFormationFact(
                    instrument_id=instrument_id,
                    formation_session=cutoff,
                    listed_sessions=len(through),
                    identity_status=StockIdentityStatus.NORMAL,
                    tradability=(
                        TradabilityStatusKind.TRADABLE
                        if through[-1][0] == cutoff
                        else TradabilityStatusKind.UNKNOWN
                    ),
                    trailing_amounts=tuple(
                        TrailingAmount(session_date=session_date, amount=amount)
                        for session_date, amount in window
                    ),
                )
            )
    schedule = form_annual_schedule(facts, policy)
    cohort_sizes: dict[int, int] = {}
    union: set[InstrumentId] = set()
    for year in range(plan.intent.basic_start.year, plan.intent.basic_end.year + 1):
        try:
            view = schedule.view_for(date(year, 1, 15))
        except Exception as error:
            raise MaterializationError(
                f"{REASON_STOCK_COHORT_YEAR_FAILED}: calendar year {year} "
                f"failed the frozen policy: {error}"
            ) from error
        cohort_sizes[year] = len(view.instrument_ids)
        union.update(view.instrument_ids)
    return _StockFormationOutcome(
        cohort_sizes=cohort_sizes, union=tuple(sorted(union))
    )


def _stock_inferred_tradability(
    union: tuple[InstrumentId, ...],
    open_dates: tuple[date, ...],
    bars: tuple[DailyBar, ...],
) -> tuple[TradabilityStatus, ...]:
    """Session-level tradability inferred from canonical bar presence.

    A session with a canonical bar is ``TRADABLE``; an open session inside
    the instrument's first-to-last bar span without a bar is ``SUSPENDED``;
    open sessions before the first bar are ``NOT_LISTED`` and after the
    last bar ``DELISTED``. Every record carries the ``INFERRED`` availability
    basis with the session-close knowledge time, and the inference is
    conservative: unknown tradability never becomes tradable.
    """
    bar_dates: dict[InstrumentId, set[date]] = {}
    for bar in bars:
        bar_dates.setdefault(bar.instrument_id, set()).add(bar.session_date)
    records: list[TradabilityStatus] = []
    for instrument_id in union:
        sessions = bar_dates.get(instrument_id, set())
        first = min(sessions) if sessions else None
        last = max(sessions) if sessions else None
        for session_date in open_dates:
            if first is None or session_date < first:
                status = TradabilityStatusKind.NOT_LISTED
            elif session_date in sessions:
                status = TradabilityStatusKind.TRADABLE
            elif last is not None and session_date <= last:
                status = TradabilityStatusKind.SUSPENDED
            else:
                status = TradabilityStatusKind.DELISTED
            available_at = datetime.combine(
                session_date, time(15, 5), tzinfo=MARKET_TIMEZONE
            )
            records.append(
                TradabilityStatus(
                    instrument_id=instrument_id,
                    session_date=session_date,
                    status=status,
                    reason=None,
                    availability=Availability(
                        information_available_at=available_at,
                        retrieved_at=available_at,
                        availability_basis=AvailabilityBasis.INFERRED,
                    ),
                    provenance=(
                        "owner-materialized vipdoc bar-presence inference "
                        f"({STOCK_REFERENCE_VERSION})"
                    ),
                )
            )
    return tuple(records)


def _stock_corporate_actions(
    plan: _ScopedPlan,
    provider: ChStockDataProvider,
    union: tuple[InstrumentId, ...],
) -> tuple[tuple[CorporateAction, ...], tuple[str, ...], list[str]]:
    """Owner-side per-instrument stock corporate actions.

    Long-delisted names have no vendor dividend page (an explicit
    ``coverage=unavailable`` answer), and some live pages carry unscheduled
    announcement items without an ``ex_dividend_date``. The canonical
    contract requires an ex date, and the M0 provider deliberately fails
    such pages closed. The owner therefore applies its own disclosed rule on
    the raw vendor payload before reusing the provider's canonical mapping:
    stable no-coverage answers become an empty history, and unscheduled
    no-ex-date items are dropped (they can never post a ledger event). Both
    rules are disclosed in the materialization receipt; every other vendor
    failure fails the materialization closed.
    """

    from systematic_investing.adapters.chstockdata.provider import (
        import_chstockdata_library,
    )
    from systematic_investing.data.ports import CorporateActionRequest

    library = import_chstockdata_library()
    query = getattr(library, "get_corporate_actions", None)
    if not callable(query):
        raise MaterializationError(
            f"{REASON_PROVIDER_FAILURE}: the pinned chstockdata release does "
            "not expose get_corporate_actions"
        )
    vendor_payload = LibraryChStockDataClient._vendor_json_payload
    map_actions = provider._map_corporate_actions
    records: list[CorporateAction] = []
    no_coverage: list[str] = []
    dropped_unscheduled: list[str] = []
    for instrument_id in union:
        payload: dict[str, object] | None = None
        stable_no_coverage = True
        for _attempt in range(3):
            try:
                text = query(
                    instrument_id.symbol,
                    plan.start.isoformat(),
                    plan.end.isoformat(),
                )
                candidate = vendor_payload(text, "corporate_actions")
            except MaterializationError:
                raise
            except Exception as error:
                candidate = None
                stable_no_coverage = False
                last_error = f"{type(error).__name__}: {error}"
            if isinstance(candidate, dict):
                status = str(candidate.get("status", "success"))
                coverage = candidate.get("coverage")
                if status.startswith("failed") or coverage == "unavailable":
                    if coverage == "unavailable":
                        sleep(2.0)
                        continue
                    raise MaterializationError(
                        f"{REASON_PROVIDER_FAILURE}: corporate actions for "
                        f"{instrument_id} failed: status={status}: "
                        f"{candidate.get('error_summary')}"
                    )
                payload = candidate
                stable_no_coverage = False
                break
            sleep(2.0)
        if payload is None:
            if stable_no_coverage:
                no_coverage.append(str(instrument_id))
                continue
            raise MaterializationError(
                f"{REASON_PROVIDER_FAILURE}: corporate actions for "
                f"{instrument_id} ended without coverage evidence: {last_error}"
            )
        items = payload.get("items")
        kept: list[object] = []
        if isinstance(items, list):
            for item in items:
                if not isinstance(item, dict):
                    kept.append(item)
                    continue
                ex_date = item.get("ex_dividend_date")
                if ex_date in (None, "") or (
                    isinstance(ex_date, float) and ex_date != ex_date
                ):
                    dropped_unscheduled.append(
                        f"{instrument_id}:{item.get('source_identifier')}"
                    )
                    continue
                kept.append(item)
        cleaned = {**payload, "items": kept}
        try:
            mapped, _warnings = map_actions(
                payload=cleaned,
                instrument_id=instrument_id,
                request=CorporateActionRequest(
                    instrument_ids=(instrument_id,),
                    start_date=plan.start,
                    end_date=plan.end,
                    instrument_kind="STOCK",
                ),
                retrieved_at=datetime.now(MARKET_TIMEZONE),
            )
        except Exception as error:
            raise MaterializationError(
                f"{REASON_PROVIDER_FAILURE}: corporate actions for "
                f"{instrument_id} violate the canonical contract: "
                f"{type(error).__name__}: {error}"
            ) from error
        records.extend(mapped)
    return tuple(records), tuple(no_coverage), dropped_unscheduled


def _stock_reference_records(
    union: tuple[InstrumentId, ...], bars: tuple[DailyBar, ...]
) -> tuple[StockInstrumentReference, ...]:
    """Attest classification and standard main-board rule coverage."""
    first_bar: dict[InstrumentId, date] = {}
    for bar in bars:
        current = first_bar.get(bar.instrument_id)
        if current is None or bar.session_date < current:
            first_bar[bar.instrument_id] = bar.session_date
    return tuple(
        StockInstrumentReference(
            instrument_id=instrument_id,
            display_name=f"Main-board A-share {instrument_id.symbol}",
            list_date=first_bar[instrument_id],
            lot_rule_profile_id="LOT:CN-STANDARD",
            settlement_rule_profile_id="SETTLE:T1",
            price_limit_rule_profile_id="PLIMIT:A-MAIN-10PCT",
            market_fee_tax_profile_id="FEE:TAX-A-STANDARD",
            reference_data_version=STOCK_REFERENCE_VERSION,
            provenance=(
                "owner-materialized vipdoc-derived reference; list_date is "
                "the first in-window session, not the exchange listing date"
            ),
            valid_from=date(2017, 1, 1),
            valid_to=None,
        )
        for instrument_id in union
    )


def _stock_reference_payload(
    records: tuple[StockInstrumentReference, ...], snapshot_id: str
) -> dict[str, object]:
    return {
        "reference_schema_version": STOCK_REFERENCE_SCHEMA,
        "snapshot_id": "sha256:" + snapshot_id,
        "reference_data_version": STOCK_REFERENCE_VERSION,
        "provenance": (
            "Owner-materialized main-board A-share reference: classification "
            "and standard rule-profile coverage attested at materialization; "
            "PIT ST naming history is unavailable (declared candidate "
            "limitation)."
        ),
        "instruments": [
            {
                "instrument_id": str(record.instrument_id),
                "display_name": record.display_name,
                "list_date": record.list_date.isoformat(),
                "lot_rule_profile_id": record.lot_rule_profile_id,
                "settlement_rule_profile_id": record.settlement_rule_profile_id,
                "price_limit_rule_profile_id": record.price_limit_rule_profile_id,
                "market_fee_tax_profile_id": record.market_fee_tax_profile_id,
                "reference_data_version": record.reference_data_version,
                "provenance": record.provenance,
                "valid_from": record.valid_from.isoformat(),
                "valid_to": None,
            }
            for record in records
        ],
    }


def materialize_stock_basic_snapshot(
    plan: MaterializationPlan, output_dir: Path
) -> dict[str, object]:
    """Materialize the Basic-only canonical Stock snapshot.

    The owner-side flow: enumerate the local main-board market, form the
    annual PIT cohorts from raw facts with the frozen policy, materialize
    canonical bars only for the cohort union, infer session tradability
    from bar presence, fetch stock corporate actions, gate the canonical
    dataset under the attested run master, and persist snapshot, reference,
    and gate receipt immutably.
    """
    from systematic_investing.research.intake import build_stock_run_master

    master = default_m0_master()
    preflight_materialization(plan, output_dir, master=master)
    candidates = _stock_candidate_instruments()
    provider = _provider()
    _calendar_id, sessions = _merged_calendar(
        plan, provider, exchanges=("XSHG", "XSHE")
    )
    open_dates = tuple(
        session.session_date for session in sessions if session.is_open
    )
    if not open_dates:
        raise MaterializationError(
            f"{REASON_PROVIDER_FAILURE}: the requested window has no open "
            "sessions"
        )
    formation = _form_owner_stock_cohorts(plan, candidates, open_dates)
    union = formation.union
    if not union:
        raise MaterializationError(
            f"{REASON_STOCK_COHORT_YEAR_FAILED}: no annual cohort could be "
            "formed from the local market history"
        )
    scoped_plan = replace(
        plan, instrument_symbols=tuple(str(item) for item in union)
    )
    bars = _daily_bars(scoped_plan, provider)
    if not bars:
        raise MaterializationError(
            f"{REASON_PROVIDER_FAILURE}: provider returned an empty daily "
            "bar set for the formed cohort union"
        )
    tradability = _stock_inferred_tradability(union, open_dates, bars)
    actions, actions_no_coverage, actions_dropped = _stock_corporate_actions(
        plan, provider, union
    )

    dataset = CanonicalDataset(
        daily_bars=tuple(bars),
        sessions=tuple(sessions),
        tradability=tuple(tradability),
        corporate_actions=tuple(actions),
        rule_candidates=(),
    )
    reference_records = _stock_reference_records(union, bars)
    run_master = build_stock_run_master(reference_records)
    # First-listing sessions have no previous close by definition; the
    # versioned policy knob records the relaxed requirement in the gate
    # receipt, and no M0 engine/execution/metric path consumes the bar's
    # pre_close field.
    gate_result, manifest = _persist_gated_snapshot(
        dataset,
        intended_decision_session=plan.end,
        output_dir=output_dir,
        master=run_master,
        policy=DatasetPolicy(require_pre_close=False),
        provider_name=provider.PROVIDER_NAME,
        provider_version=_provider_version(provider),
        adapter_version=provider.ADAPTER_VERSION,
    )
    _write_snapshot_receipts(
        output_dir,
        gate_result,
        snapshot_id=str(manifest.snapshot_id),
        extra_receipts=(
            (
                "instrument-reference.json",
                _stock_reference_payload(
                    reference_records, str(manifest.snapshot_id)
                ),
            ),
        ),
        failure_label="stock receipt",
    )
    max_session = max(bar.session_date for bar in dataset.daily_bars)
    return {
        "materializer_schema_version": MATERIALIZER_SCHEMA_VERSION,
        "mode": MODE_BASIC,
        "asset_class": ASSET_STOCK,
        "lineage_id": plan.intent.lineage_id,
        "intent_digest": plan.intent.intent_digest,
        "snapshot_id": manifest.snapshot_id,
        "snapshot_dir": str(output_dir),
        "min_session": min(
            bar.session_date for bar in dataset.daily_bars
        ).isoformat(),
        "max_session": max_session.isoformat(),
        "bar_count": len(dataset.daily_bars),
        "tradability_count": len(dataset.tradability),
        "corporate_action_count": len(dataset.corporate_actions),
        "corporate_actions_no_coverage": list(actions_no_coverage),
        "corporate_actions_dropped_unscheduled": actions_dropped[:20],
        "corporate_actions_dropped_count": len(actions_dropped),
        "cohort_union_size": len(union),
        "cohort_sizes": {
            str(year): size for year, size in sorted(formation.cohort_sizes.items())
        },
        "quality_status": SNAPSHOT_QUALITY_PASS,
        "instrument_reference": "instrument-reference.json",
        "gate_receipt": "gate-receipt.json",
    }


def gate_receipt_payload(
    gate_result: GateResult,
    *,
    snapshot_id: str,
) -> dict[str, object]:
    """The immutable evidence receipt for one quality-gate decision."""
    return {
        "receipt_schema_version": "research-gate-receipt-1",
        "snapshot_id": "sha256:" + snapshot_id,
        "gate_name": gate_result.gate_name,
        "gate_version": gate_result.gate_version,
        "purpose": gate_result.purpose.value,
        "status": gate_result.status.value,
        "action": gate_result.action.value,
        "reason_codes": list(gate_result.reason_codes),
        "checks": [
            {
                "check_id": check.check_id,
                "status": check.status.value,
                "severity": check.severity.value,
                "reason_code": check.reason_code,
                "affected_scope": list(check.affected_scope),
                "observed": check.observed,
                "expected": check.expected,
            }
            for check in sorted(gate_result.checks, key=lambda item: item.check_id)
        ],
        "input_digests": dict(sorted(gate_result.input_digests.items())),
        "gate_digest": gate_result.content_digest(),
    }


def write_gate_receipt(
    output_dir: Path,
    gate_result: GateResult,
    *,
    snapshot_id: str,
) -> Path:
    """Persist the quality-gate receipt next to its snapshot, create-new."""
    payload = gate_receipt_payload(gate_result, snapshot_id=snapshot_id)
    write_new_json(Path(output_dir) / "gate-receipt.json", payload)
    return Path(output_dir) / "gate-receipt.json"


def _provider_version(provider: ChStockDataProvider) -> str:
    evidence = provider.capability_evidence()
    version = getattr(evidence, "provider_version", None)
    if version is None:
        raise MaterializationError(
            f"{REASON_PROVIDER_FAILURE}: provider capability evidence "
            "unavailable; the pinned release must be qualified first"
        )
    return str(version)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="systematic_investing.research.materializer",
        description=(
            "Owner-controlled snapshot materialization. Run only in the "
            "controlled data environment with the pinned provider and raw "
            "data mounted; the Research actor has no access to this command."
        ),
    )
    parser.add_argument("--mode", required=True, choices=[MODE_BASIC, MODE_OOS])
    parser.add_argument(
        "--asset",
        required=False,
        choices=[ASSET_ETF, ASSET_STOCK],
        help="BASIC mode only: the intent asset class",
    )
    parser.add_argument(
        "--start", required=False, help="BASIC mode only: warm-up start (ISO date)"
    )
    parser.add_argument(
        "--end", required=False, help="BASIC mode only: Basic end (ISO date)"
    )
    parser.add_argument(
        "--request", required=False, help="BASIC mode only: path to the intent JSON"
    )
    parser.add_argument(
        "--freeze",
        required=False,
        help="OOS mode only: path to the single verified freeze artifact",
    )
    parser.add_argument("--output", required=True, help="snapshot output directory")
    parser.add_argument(
        "--preflight-only",
        action="store_true",
        help="validate static scope and Instrument Master coverage without provider calls",
    )
    args = parser.parse_args(argv)

    try:
        receipt = (
            _run_basic_mode(args) if args.mode == MODE_BASIC else _run_oos_mode(args)
        )
    except (MaterializationError, ValueError, KeyError) as error:
        print(
            json.dumps(
                {
                    "materializer_schema_version": MATERIALIZER_SCHEMA_VERSION,
                    "error": str(error),
                }
            ),
            file=sys.stderr,
        )
        return 1
    print(json.dumps(receipt, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
    return 0


def _run_basic_mode(args: argparse.Namespace) -> dict[str, object]:
    missing = [
        flag
        for flag, value in (
            ("--asset", args.asset),
            ("--start", args.start),
            ("--end", args.end),
            ("--request", args.request),
        )
        if not value
    ]
    if missing:
        raise MaterializationError(
            f"{REASON_ARGUMENT_MISSING}: BASIC mode requires {', '.join(missing)}"
        )
    if args.freeze:
        raise MaterializationError(
            f"{REASON_ARGUMENT_MISMATCH}: --freeze belongs to OOS mode only"
        )
    intent_payload = json.loads(Path(args.request).read_text(encoding="utf-8"))
    intent = CandidateIntent.from_dict(intent_payload)
    plan = validate_materialization_request(
        intent,
        mode=args.mode,
        asset_class=args.asset,
        start=date.fromisoformat(args.start),
        end=date.fromisoformat(args.end),
    )
    if args.preflight_only:
        return preflight_materialization(
            plan,
            Path(args.output),
            master=default_m0_master(),
        )
    return materialize_basic_snapshot(plan, Path(args.output))


def _run_oos_mode(args: argparse.Namespace) -> dict[str, object]:
    if not args.freeze:
        raise MaterializationError(
            f"{REASON_ARGUMENT_MISSING}: OOS mode requires exactly one freeze "
            "artifact via --freeze"
        )
    unwanted = [
        flag
        for flag, value in (
            ("--asset", args.asset),
            ("--start", args.start),
            ("--end", args.end),
            ("--request", args.request),
        )
        if value
    ]
    if unwanted:
        raise MaterializationError(
            f"{REASON_ARGUMENT_MISMATCH}: OOS mode accepts only --freeze and "
            f"--output; got {', '.join(unwanted)}"
        )
    if args.preflight_only:
        plan = prepare_oos_materialization(Path(args.freeze), Path(args.output))
        return {
            **plan.to_payload(),
            "status": SNAPSHOT_QUALITY_PASS,
            "preflight_only": True,
        }
    return materialize_oos_freeze(Path(args.freeze), Path(args.output))


def materialize_oos_freeze(freeze_path: Path, output_dir: Path) -> dict[str, object]:
    """One-shot freeze-gated OOS materialization entry point: validate the
    single freeze artifact offline, then materialize in the controlled
    environment."""
    plan = prepare_oos_materialization(freeze_path, output_dir)
    return materialize_oos_snapshot(plan)


if __name__ == "__main__":
    raise SystemExit(main())
