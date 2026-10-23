"""Research CLI: the external Agent boundary for the M1 research loop.

Commands (all success outputs are versioned JSON; failures exit non-zero
with a typed reason on stderr and never contain secrets):

- ``screen --intent <intent.json> --root <dir>``: cheap-screen a frozen
  CandidateIntent and persist the verdict artifact immutably;
- ``source-screen --source-record <source.json> --root <dir>``: validate a
  real external-source flight record and persist the pre-implementation verdict;
- ``basic-backtest --intent <intent.json> --snapshot <manifest.json>
  --root <dir>``: validate the physical snapshot boundary, run every
  parameter variant through the M0 kernel, retain each attempt immutably,
  and select strictly by the predeclared priority list;
- ``oos-freeze --candidate-id <id> --root <dir>``: freeze the OOS
  candidate after a Basic PASS; the freeze binds the intent, the selected
  implementation/parameters, the requested OOS scope, and the
  universe/benchmark/cost/kernel identities — never an OOS snapshot
  digest, which cannot exist before materialization;
- ``oos-run --freeze-id <id> --snapshot <manifest.json> --root <dir>``:
  persist the reveal intent BEFORE opening the materialized OOS snapshot,
  validate the OOS boundary, run the selected variant once, and record the
  single SURVIVOR/REJECTED_OOS verdict decided by the frozen
  oos_survivor_rule;
- ``select-oos --asset <ETF|STOCK> --root <dir>``: select the one
  priority-qualified Basic candidate without opening OOS data;
- ``no-oos-eligible --asset <ETF|STOCK> --root <dir>``: record the honest
  asset-class outcome when no candidate earned a Basic PASS;
- ``verify --root <dir>``: verify the artifact catalog against content.

The CLI never fetches provider or raw data, has no network access, never
imports the owner materializer, and has no bypass flags: there is no way to
skip a gate, rewrite an artifact, force a verdict, or un-freeze a candidate.
"""

import argparse
import hashlib
import json
import shutil
import sys
from collections.abc import Callable, Mapping, Sequence
from decimal import Decimal
from pathlib import Path
from typing import NoReturn

from systematic_investing.backtest.engine import DailyBarEngine
from systematic_investing.data.snapshots import (
    SnapshotIntegrityError,
    SnapshotReader,
)
from systematic_investing.instrument_master.repository import default_m0_master
from systematic_investing.metrics.performance import compute_metrics
from systematic_investing.research.artifacts import (
    ArtifactIntegrityError,
    canonical_json_bytes,
    digest_of_bytes,
    next_attempt_for,
    read_json,
    run_id_for,
    write_new_json,
)
from systematic_investing.research.benchmarks import (
    BenchmarkKind,
    BenchmarkTargetSource,
    StockAnnualBenchmarkTargetSource,
    stock_annual_inception_sessions,
)
from systematic_investing.research.catalog import (
    CATALOG_SCHEMA_VERSION,
    append_entry,
    read_entries,
    verify_catalog,
)
from systematic_investing.research.contracts import (
    FORBIDDEN_INTENT_FIELDS,
    INTENT_SCHEMA_VERSION,
    CandidateIntent,
    canonical_payload_digest,
)
from systematic_investing.research.intake import (
    BasicSnapshotBoundaryError,
    build_stock_run_master,
    load_stock_instrument_reference,
    stock_instrument_reference_digest,
    validate_basic_snapshot,
)
from systematic_investing.research.oos import (
    REASON_FREEZE_KERNEL_UNSUPPORTED,
    REASON_FREEZE_REQUIRES_BASIC_PASS,
    OosError,
    build_freeze_payload,
    build_oos_wiring,
    enforce_freeze_strategy_identity,
    find_freeze,
    freeze_intent,
    oos_benchmark_total_return,
    persist_freeze,
    record_result,
    record_reveal,
    record_verdict,
    reject_contaminated_oos_request,
    require_no_existing_verdict,
    require_selected_oos_candidate,
    resolve_freeze_kernel_replay_profile,
    reveal_payload,
    run_oos_variant,
    select_oos_candidate,
    validate_oos_snapshot,
    verdict_payload,
)
from systematic_investing.research.reporting import (
    AssetClassOutcome,
    persist_asset_class_outcome,
    persist_source_screen,
    read_asset_class_outcome,
    screen_source_record,
)
from systematic_investing.research.runner import (
    RUN_STATUS_RUN_FAILED_DATA,
    RUN_STATUS_RUN_FAILED_KERNEL,
    BasicRunOutcome,
    BasicSelection,
    BasicWiring,
    RunWiringError,
    build_basic_wiring,
    run_basic_variant,
    select_basic_candidate,
)
from systematic_investing.research.universe import AnnualUniverseSchedule

CLI_OUTPUT_SCHEMA_VERSION: str = "research-cli-output-1"
VERDICT_SCREEN_PASS: str = "SCREEN_PASS"
VERDICT_REJECTED_BEFORE_IMPLEMENTATION: str = "REJECTED_BEFORE_IMPLEMENTATION"
VERDICT_OOS_FROZEN: str = "OOS_FROZEN"
OUTCOME_NO_OOS_ELIGIBLE: str = "NO_OOS_ELIGIBLE_CANDIDATE"
OUTCOME_OOS_ELIGIBLE: str = "OOS_ELIGIBLE"
REASON_CANDIDATE_NOT_FOUND: str = "CANDIDATE_NOT_FOUND"
REASON_OOS_ELIGIBLE_CANDIDATE_EXISTS: str = "OOS_ELIGIBLE_CANDIDATE_EXISTS"
REASON_OOS_ASSET_OUTCOME_EXISTS: str = "OOS_ASSET_OUTCOME_ALREADY_RECORDED"
REASON_ATTEMPT_PERSISTENCE_FAILED: str = "RUN_PERSISTENCE_FAILED"
PRE_FLIGHT_VARIANT_ID: str = "__preflight__"

_REQUIRED_INTENT_FIELDS: tuple[str, ...] = (
    "intent_schema_version",
    "intent_id",
    "lineage_id",
    "asset_class",
    "sleeve",
    "strategy_id",
    "decision_frequency",
    "economic_rationale",
    "rule_pseudocode",
    "parameter_variants",
    "parameter_priority",
    "parameter_selection_rule",
    "universe_policy",
    "warm_up_start",
    "basic_start",
    "basic_end",
    "oos_start",
    "oos_end",
    "benchmark",
    "risk_off_choice",
    "initial_capital",
    "cost_convention",
    "metric_convention",
    "basic_promotion_rule",
    "oos_survivor_rule",
    "known_limitations",
    "source",
    "created_at",
)


class CliFailure(Exception):
    """Typed CLI failure; messages are safe for stderr (no secrets)."""


def _load_intent(intent_path: Path) -> CandidateIntent:
    payload = read_json(intent_path)
    try:
        return CandidateIntent.from_dict(payload)
    except Exception as error:
        raise CliFailure(
            f"CANDIDATE_INTENT_INVALID: {type(error).__name__}: {error}"
        ) from error


def _lineage_dir(root: Path, lineage_id: str) -> Path:
    return root / lineage_id


def _intent_dir(root: Path, intent: CandidateIntent) -> Path:
    """Return the immutable per-intent home, retaining the legacy v1 path."""
    lineage_dir = _lineage_dir(root, intent.lineage_id)
    legacy = lineage_dir / "intent.json"
    if legacy.exists() and canonical_payload_digest(read_json(legacy)) == intent.intent_digest:
        return lineage_dir
    return lineage_dir / "intents" / intent.intent_id


def _catalog_dir(root: Path) -> Path:
    return root / "catalog"


def _content_digest(payload: Mapping[str, object]) -> str:
    rendered = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return "sha256:" + hashlib.sha256(rendered.encode("utf-8")).hexdigest()


def _failure_payloads(
    *,
    intent: CandidateIntent,
    variant_id: str,
    status: str,
    reason_code: str,
    stage: str,
    identity_seed: str,
    base_manifest: Mapping[str, object] | None = None,
) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    """Build a complete, typed artifact set for an attempt failure.

    Pre-flight failures do not have enough information to construct a normal
    ``ResearchRunManifest``.  They still receive a stable identity and the
    same immutable manifest/result/report shape, so they are countable and
    auditable without being eligible for Basic selection.
    """
    identity_digest = "sha256:" + hashlib.sha256(identity_seed.encode("utf-8")).hexdigest()
    reason_codes = (reason_code,)
    manifest = dict(base_manifest or {})
    manifest.update(
        {
            "manifest_schema_version": "research-basic-attempt-failure-1",
            "lineage_id": intent.lineage_id,
            "intent_digest": intent.intent_digest,
            "strategy_id": intent.strategy_id,
            "strategy_version": "unresolved",
            "identity_digest": identity_digest,
            "output_scope": "BASIC",
            "attempt_boundary": "ATTEMPT_STARTED",
            "attempt_stage": stage,
            "variant_id": variant_id,
            "status": status,
            "reason_codes": list(reason_codes),
        }
    )
    result: dict[str, object] = {
        "result_schema_version": "research-basic-result-1",
        "lineage_id": intent.lineage_id,
        "intent_id": intent.intent_id,
        "intent_digest": intent.intent_digest,
        "variant_id": variant_id,
        "status": status,
        "reason_codes": list(reason_codes),
        "attempt_boundary": "ATTEMPT_STARTED",
        "attempt_stage": stage,
        "manifest_identity_digest": identity_digest,
    }
    report: dict[str, object] = {
        "report_schema_version": "research-basic-report-1",
        "lineage_id": intent.lineage_id,
        "variant_id": variant_id,
        "status": status,
        "reason_codes": list(reason_codes),
        "attempt_boundary": "ATTEMPT_STARTED",
        "attempt_stage": stage,
        "manifest_identity_digest": identity_digest,
    }
    return manifest, result, report


def _write_failure_json(path: Path, payload: Mapping[str, object]) -> str:
    """Write a failure artifact without reusing a failed persistence hook."""
    target = Path(path)
    if target.exists():
        raise ArtifactIntegrityError(
            f"artifact {target} already exists; research artifacts are immutable"
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    content = canonical_json_bytes(payload)
    target.write_bytes(content)
    return digest_of_bytes(content)


def _append_run_catalog_entries(
    root: Path,
    intent: CandidateIntent,
    run_dir: Path,
    *,
    status: str,
    variant_id: str,
    digests: Mapping[str, str],
) -> list[Mapping[str, object]]:
    entries: list[Mapping[str, object]] = []
    for name in ("manifest.json", "result.json", "report.json"):
        entries.append(
            append_entry(
                _catalog_dir(root),
                {
                    "lineage_id": intent.lineage_id,
                    "artifact_type": "BASIC_RUN",
                    "ref": _relative_ref(root, run_dir / name),
                    "status": status,
                    "variant_id": variant_id,
                    "digests": {name: digests[name]},
                },
            )
        )
    return entries


def _persist_catalog_failure_marker(
    root: Path,
    intent: CandidateIntent,
    run_dir: Path,
    *,
    reason: str,
) -> None:
    """Explain a catalog append failure with an immutable marker.

    The run artifacts have already been atomically completed at this point.
    A marker is written through the low-level create-new primitive so a
    one-shot injected ``append_entry`` failure cannot leave an unexplained
    catalog gap or an unaccounted run directory.
    """
    marker_path = run_dir / "persistence-failure.json"
    marker_payload = {
        "schema_version": "research-persistence-failure-1",
        "lineage_id": intent.lineage_id,
        "artifact_type": "BASIC_RUN_PERSISTENCE_FAILURE",
        "run_ref": _relative_ref(root, run_dir),
        "status": RUN_STATUS_RUN_FAILED_KERNEL,
        "reason_codes": [reason],
    }
    marker_digest = _write_failure_json(marker_path, marker_payload)
    existing = read_entries(_catalog_dir(root))
    sequences: list[int] = []
    for item in existing:
        value = item.get("sequence")
        if not isinstance(value, int):
            raise ArtifactIntegrityError(
                "catalog entry sequence must be an integer"
            )
        sequences.append(value)
    sequence = max(sequences, default=0) + 1
    catalog_payload = {
        "catalog_schema_version": CATALOG_SCHEMA_VERSION,
        "sequence": sequence,
        "lineage_id": intent.lineage_id,
        "artifact_type": "BASIC_RUN_PERSISTENCE_FAILURE",
        "ref": _relative_ref(root, marker_path),
        "status": RUN_STATUS_RUN_FAILED_KERNEL,
        "digests": {"persistence-failure": marker_digest},
    }
    catalog_path = _catalog_dir(root) / f"{sequence:06d}.json"
    _write_failure_json(catalog_path, catalog_payload)


def _persist_failure_attempt(
    root: Path,
    intent: CandidateIntent,
    *,
    variant_id: str,
    status: str,
    reason_code: str,
    stage: str,
    identity_seed: str,
    base_manifest: Mapping[str, object] | None = None,
) -> tuple[Path, Mapping[str, object]]:
    """Persist one complete typed failure attempt after ATTEMPT_STARTED."""
    manifest, result, report = _failure_payloads(
        intent=intent,
        variant_id=variant_id,
        status=status,
        reason_code=reason_code,
        stage=stage,
        identity_seed=identity_seed,
        base_manifest=base_manifest,
    )
    runs_root = _intent_dir(root, intent) / "runs"
    identity = str(manifest["identity_digest"])
    attempt = next_attempt_for(runs_root, identity)
    run_dir = runs_root / run_id_for(identity, attempt)
    run_dir.mkdir(parents=True, exist_ok=False)
    digests = {
        "manifest.json": _write_failure_json(run_dir / "manifest.json", manifest),
        "result.json": _write_failure_json(run_dir / "result.json", result),
        "report.json": _write_failure_json(run_dir / "report.json", report),
    }
    entries = _append_run_catalog_entries(
        root,
        intent,
        run_dir,
        status=status,
        variant_id=variant_id,
        digests=digests,
    )
    return run_dir, entries[-1]


def screen_intent(payload: Mapping[str, object]) -> tuple[str, tuple[str, ...]]:
    """Cheap screen: fatal pre-code checks over a frozen intent payload."""
    fatal: list[str] = []
    if payload.get("intent_schema_version") != INTENT_SCHEMA_VERSION:
        fatal.append("UNSUPPORTED_INTENT_SCHEMA_VERSION")
    for field_name in _REQUIRED_INTENT_FIELDS:
        if field_name not in payload:
            fatal.append(f"MISSING_{field_name.upper()}")
    for field_name in sorted(FORBIDDEN_INTENT_FIELDS):
        if field_name in payload:
            fatal.append(f"FORBIDDEN_RUNTIME_FIELD_{field_name.upper()}")
    if not fatal:
        try:
            CandidateIntent.from_dict(payload)
        except Exception:
            fatal.append("CANDIDATE_INTENT_VALIDATION_FAILED")
    if fatal:
        return VERDICT_REJECTED_BEFORE_IMPLEMENTATION, tuple(fatal)
    return VERDICT_SCREEN_PASS, ()


def _persist_frozen_intent(
    path: Path,
    payload: Mapping[str, object],
    intent_digest: str,
) -> None:
    """Persist the frozen intent copy under its fixed name.

    An existing copy with different content fails closed: a changed intent
    is a new candidate version, never an overwrite.
    """
    if path.exists():
        existing = read_json(path)
        if canonical_payload_digest(existing) != intent_digest:
            raise CliFailure(
                "ARTIFACT_IMMUTABILITY_VIOLATION: a frozen intent for this "
                "lineage already exists with different content; a changed "
                "intent is a new version and must use a new intent_id"
            )
        return
    write_new_json(path, payload)


def _persist_immutable(
    directory: Path,
    payload: Mapping[str, object],
    *,
    kind: str,
) -> tuple[Path, str]:
    """Write one create-new artifact or confirm an identical existing one.

    Returns the artifact path and digest. An existing artifact with
    different content fails closed; artifacts are immutable.
    """
    digest = _content_digest(payload)
    path = directory / f"{digest.removeprefix('sha256:')[:16]}.json"
    if path.exists():
        existing = read_json(path)
        if _content_digest(existing) != digest:
            raise CliFailure(
                f"ARTIFACT_IMMUTABILITY_VIOLATION: {kind} artifact {path} "
                "exists with different content; artifacts are immutable"
            )
        return path, digest
    write_new_json(path, payload)
    return path, digest


def command_screen(args: argparse.Namespace) -> Mapping[str, object]:
    root = Path(args.root)
    intent_path = Path(args.intent)
    if not intent_path.exists():
        raise CliFailure(f"INTENT_MISSING: intent file does not exist: {intent_path}")
    try:
        payload = read_json(intent_path)
    except ArtifactIntegrityError as error:
        raise CliFailure(f"INTENT_UNREADABLE: {error}") from error
    verdict, reason_codes = screen_intent(payload)
    lineage_id_value = payload.get("lineage_id")
    lineage_id = (
        lineage_id_value
        if isinstance(lineage_id_value, str) and lineage_id_value
        else "unknown-lineage"
    )
    intent_digest = canonical_payload_digest(payload)
    lineage_dir = _lineage_dir(root, lineage_id)

    intent_dir = lineage_dir
    if verdict == VERDICT_SCREEN_PASS and (lineage_dir / "intent.json").exists():
        intent_dir = _intent_dir(root, CandidateIntent.from_dict(payload))
    _persist_frozen_intent(intent_dir / "intent.json", payload, intent_digest)
    screen_payload: dict[str, object] = {
        "screen_schema_version": "research-screen-1",
        "lineage_id": lineage_id,
        "intent_digest": intent_digest,
        "verdict": verdict,
        "reason_codes": list(reason_codes),
    }
    screen_path, screen_digest = _persist_immutable(
        lineage_dir / "screen", screen_payload, kind="screen"
    )
    catalog_entry = append_entry(
        _catalog_dir(root),
        {
            "lineage_id": lineage_id,
            "artifact_type": "CHEAP_SCREEN",
            "ref": _relative_ref(root, screen_path),
            "status": verdict,
            "digests": {"screen": screen_digest},
        },
    )
    return {
        "schema_version": CLI_OUTPUT_SCHEMA_VERSION,
        "command": "screen",
        "verdict": verdict,
        "reason_codes": list(reason_codes),
        "lineage_id": lineage_id,
        "intent_digest": intent_digest,
        "screen_digest": screen_digest,
        "catalog_sequence": catalog_entry["sequence"],
    }


def command_source_screen(args: argparse.Namespace) -> Mapping[str, object]:
    """Validate and retain one external-source discovery flight."""
    root = Path(args.root)
    source_path = Path(args.source_record)
    if not source_path.exists():
        raise CliFailure(
            f"SOURCE_RECORD_MISSING: source record does not exist: {source_path}"
        )
    try:
        payload = read_json(source_path)
    except ArtifactIntegrityError as error:
        raise CliFailure(f"SOURCE_RECORD_UNREADABLE: {error}") from error

    source_digest = canonical_payload_digest(payload)
    verdict, reason_codes = screen_source_record(payload)
    source_id_value = payload.get("source_id")
    source_id = (
        source_id_value
        if isinstance(source_id_value, str) and source_id_value
        else "unknown-source"
    )
    try:
        screen_path, screen_digest = persist_source_screen(
            root,
            source_id=source_id,
            source_digest=source_digest,
            verdict=verdict,
            reason_codes=reason_codes,
        )
    except ValueError as error:
        raise CliFailure(f"SOURCE_SCREEN_INVALID: {error}") from error

    reference = _relative_ref(root, screen_path)
    catalog_entries = read_entries(_catalog_dir(root))
    catalog_entry = next(
        (
            entry
            for entry in catalog_entries
            if entry.get("artifact_type") == "AI_SOURCE_SCREEN"
            and entry.get("ref") == reference
        ),
        None,
    )
    if catalog_entry is None:
        catalog_entry = append_entry(
            _catalog_dir(root),
            {
                "lineage_id": source_id,
                "artifact_type": "AI_SOURCE_SCREEN",
                "ref": reference,
                "status": verdict,
                "digests": {"screen": screen_digest},
            },
        )
    return {
        "schema_version": CLI_OUTPUT_SCHEMA_VERSION,
        "command": "source-screen",
        "status": "COMPLETED",
        "verdict": verdict,
        "reason_codes": list(reason_codes),
        "source_id": source_id,
        "source_digest": source_digest,
        "screen_digest": screen_digest,
        "screen_ref": reference,
        "catalog_sequence": catalog_entry["sequence"],
    }


def _relative_ref(root: Path, artifact_file: Path) -> str:
    return artifact_file.relative_to(root).as_posix()


def _require_screen_pass(root: Path, intent: CandidateIntent) -> None:
    screen_dir = _lineage_dir(root, intent.lineage_id) / "screen"
    if not screen_dir.exists():
        raise CliFailure(
            "CHEAP_SCREEN_PASS_REQUIRED: no screen artifact exists for "
            f"{intent.lineage_id}; run 'screen' before 'basic-backtest'"
        )
    passing: list[Mapping[str, object]] = []
    for path in sorted(screen_dir.glob("*.json")):
        payload = read_json(path)
        if (
            payload.get("verdict") == VERDICT_SCREEN_PASS
            and payload.get("intent_digest") == intent.intent_digest
        ):
            passing.append(payload)
    if not passing:
        raise CliFailure(
            "CHEAP_SCREEN_PASS_REQUIRED: lineage "
            f"{intent.lineage_id} has no SCREEN_PASS artifact; candidates "
            "rejected before implementation cannot run a Basic backtest"
        )


def _check_frozen_intent(root: Path, intent: CandidateIntent) -> None:
    frozen_path = _intent_dir(root, intent) / "intent.json"
    if not frozen_path.exists():
        raise CliFailure(
            f"FROZEN_INTENT_MISSING: no frozen intent.json for "
            f"{intent.lineage_id}; the screened intent must be persisted first"
        )
    frozen = read_json(frozen_path)
    if canonical_payload_digest(frozen) != intent.intent_digest:
        raise CliFailure(
            "INTENT_IMMUTABILITY_VIOLATION: the frozen intent for "
            f"{intent.lineage_id} differs from the intent being run"
        )


def _benchmark_total_return(
    wiring: BasicWiring,
) -> Decimal:
    """The same-kernel benchmark return over the Basic metrics window."""
    if (
        wiring.benchmark_spec.kind
        == BenchmarkKind.STOCK_ANNUAL_SCHEDULE_EQUAL_WEIGHT.value
    ):
        universe = wiring.universe
        if not isinstance(universe, AnnualUniverseSchedule):
            raise CliFailure(
                "RUN_WIRING_INVALID: the same-schedule benchmark requires "
                "the intake-validated annual PIT schedule"
            )
        source: BenchmarkTargetSource | StockAnnualBenchmarkTargetSource = (
            StockAnnualBenchmarkTargetSource(
                wiring.benchmark_spec,
                universe,
                stock_annual_inception_sessions(
                    tuple(
                        session.session_date for session in wiring.calendar.sessions
                    ),
                    basic_start=wiring.basic_start,
                    basic_end=wiring.basic_end,
                ),
            )
        )
    else:
        source = BenchmarkTargetSource(
            wiring.benchmark_spec, wiring.benchmark_inception_session
        )
    engine = DailyBarEngine(
        calendar=wiring.calendar,
        clock=wiring.clock,
        master=wiring.master,
        account_fees=wiring.account_fees,
        execution_model=wiring.execution_model,
        bars=wiring.bars,
        tradability=wiring.tradability,
        corporate_actions=wiring.corporate_actions,
        target_source=source,
        initial_cash=wiring.initial_cash,
    )
    result = engine.run(
        start_session=wiring.warm_up_start, end_session=wiring.basic_end
    )
    nav_points = tuple(
        record.nav
        for record in result.sessions
        if record.session_date >= wiring.basic_start
    )
    report = compute_metrics(nav_points, cash_entries=result.cash_entries)
    return report.total_return


def _persist_run(
    root: Path,
    intent: CandidateIntent,
    outcome: BasicRunOutcome,
) -> tuple[Path, Mapping[str, object]]:
    runs_root = _intent_dir(root, intent) / "runs"
    identity = str(outcome.manifest_payload["identity_digest"])
    attempt = next_attempt_for(runs_root, identity)
    run_id = run_id_for(identity, attempt)
    run_dir = runs_root / run_id
    staging_dir = runs_root / f".{run_id}.staging"
    staging_dir.mkdir(parents=True, exist_ok=False)
    try:
        digests = {
            "manifest.json": write_new_json(
                staging_dir / "manifest.json", outcome.manifest_payload
            ),
            "result.json": write_new_json(
                staging_dir / "result.json", outcome.result_payload
            ),
            "report.json": write_new_json(
                staging_dir / "report.json", outcome.report_payload
            ),
        }
        staging_dir.replace(run_dir)
    except Exception as error:
        if staging_dir.exists():
            shutil.rmtree(staging_dir)
        reason_code = (
            f"{REASON_ATTEMPT_PERSISTENCE_FAILED}: "
            f"{type(error).__name__}: {error}"
        )
        _persist_failure_attempt(
            root,
            intent,
            variant_id=outcome.variant_id,
            status=RUN_STATUS_RUN_FAILED_KERNEL,
            reason_code=reason_code,
            stage="artifact-persistence",
            identity_seed=(
                f"persistence-failure|{intent.intent_digest}|{outcome.variant_id}|"
                f"{identity}|{reason_code}"
            ),
            base_manifest=outcome.manifest_payload,
        )
        raise CliFailure(reason_code) from error
    try:
        entries = _append_run_catalog_entries(
            root,
            intent,
            run_dir,
            status=outcome.status,
            variant_id=outcome.variant_id,
            digests=digests,
        )
    except Exception as error:
        reason_code = (
            f"{REASON_ATTEMPT_PERSISTENCE_FAILED}: catalog append: "
            f"{type(error).__name__}: {error}"
        )
        try:
            _persist_catalog_failure_marker(
                root,
                intent,
                run_dir,
                reason=reason_code,
            )
        except Exception as marker_error:
            retention_reason = (
                f"{reason_code}; ATTEMPT_RETENTION_FAILED: "
                f"{type(marker_error).__name__}: {marker_error}"
            )
            raise CliFailure(retention_reason) from marker_error
        raise CliFailure(reason_code) from error
    return run_dir, entries[-1]


def _persist_selection(
    root: Path,
    intent: CandidateIntent,
    outcomes: Sequence[BasicRunOutcome],
    selection: BasicSelection,
) -> tuple[Path, str]:
    payload: dict[str, object] = {
        **dict(selection.to_payload()),
        "lineage_id": intent.lineage_id,
        "attempts": [
            {
                "variant_id": outcome.variant_id,
                "status": outcome.status,
                "result_digest": outcome.result_digest,
            }
            for outcome in outcomes
        ],
    }
    path, digest = _persist_immutable(
        _intent_dir(root, intent) / "basic-selection",
        payload,
        kind="selection",
    )
    return path, digest


def _raise_retained_basic_failure(
    root: Path,
    intent: CandidateIntent,
    *,
    stage: str,
    reason: str,
    status: str,
) -> NoReturn:
    """Retain a post-boundary CLI failure and raise its typed CLI error."""
    try:
        _persist_failure_attempt(
            root,
            intent,
            variant_id=PRE_FLIGHT_VARIANT_ID,
            status=status,
            reason_code=reason,
            stage=stage,
            identity_seed=(
                f"preflight-failure|{intent.intent_digest}|{stage}|{reason}"
            ),
        )
    except Exception as retention_error:
        raise CliFailure(
            f"{reason}; ATTEMPT_RETENTION_FAILED: "
            f"{type(retention_error).__name__}: {retention_error}"
        ) from retention_error
    raise CliFailure(reason)


def command_basic_backtest(args: argparse.Namespace) -> Mapping[str, object]:
    root = Path(args.root)
    intent = _load_intent(Path(args.intent))
    _require_screen_pass(root, intent)
    _check_frozen_intent(root, intent)

    snapshot_path = Path(args.snapshot)
    if not snapshot_path.exists():
        _raise_retained_basic_failure(
            root,
            intent,
            stage="snapshot-load",
            reason=f"SNAPSHOT_MISSING: snapshot manifest does not exist: {snapshot_path}",
            status=RUN_STATUS_RUN_FAILED_DATA,
        )
    try:
        loaded_manifest, loaded_dataset = SnapshotReader().load(snapshot_path.parent)
    except SnapshotIntegrityError as error:
        _raise_retained_basic_failure(
            root,
            intent,
            stage="snapshot-load",
            reason=(
                f"SNAPSHOT_INTEGRITY_INVALID: snapshot failed integrity verification: {error}"
            ),
            status=RUN_STATUS_RUN_FAILED_DATA,
        )
    except Exception as error:
        _raise_retained_basic_failure(
            root,
            intent,
            stage="snapshot-load",
            reason=f"SNAPSHOT_LOAD_FAILED: {type(error).__name__}: {error}",
            status=RUN_STATUS_RUN_FAILED_DATA,
        )
    master = default_m0_master()
    instrument_reference_digest: str | None = None
    try:
        if intent.asset_class.value == "STOCK":
            master = build_stock_run_master(
                load_stock_instrument_reference(
                    snapshot_path.parent, expected_snapshot_id=loaded_manifest.snapshot_id
                )
            )
            instrument_reference_digest = stock_instrument_reference_digest(
                snapshot_path.parent
            )
    except Exception as error:
        _raise_retained_basic_failure(
            root,
            intent,
            stage="instrument-reference",
            reason=f"INSTRUMENT_REFERENCE_INVALID: {type(error).__name__}: {error}",
            status=RUN_STATUS_RUN_FAILED_DATA,
        )
    try:
        receipt = validate_basic_snapshot(
            loaded_manifest, loaded_dataset, intent, master=master
        )
    except BasicSnapshotBoundaryError as error:
        _raise_retained_basic_failure(
            root,
            intent,
            stage="snapshot-validation",
            reason=f"BASIC_SNAPSHOT_BOUNDARY_REJECTED: {error}",
            status=RUN_STATUS_RUN_FAILED_DATA,
        )
    except Exception as error:
        _raise_retained_basic_failure(
            root,
            intent,
            stage="snapshot-validation",
            reason=f"SNAPSHOT_VALIDATION_FAILED: {type(error).__name__}: {error}",
            status=RUN_STATUS_RUN_FAILED_DATA,
        )
    try:
        wiring = build_basic_wiring(
            loaded_dataset, intent, receipt, master=master,
            instrument_reference_digest=instrument_reference_digest,
        )
    except RunWiringError as error:
        _raise_retained_basic_failure(
            root,
            intent,
            stage="wiring",
            reason=f"RUN_WIRING_INVALID: {error}",
            status=RUN_STATUS_RUN_FAILED_KERNEL,
        )
    except Exception as error:
        _raise_retained_basic_failure(
            root,
            intent,
            stage="wiring",
            reason=f"RUN_WIRING_FAILED: {type(error).__name__}: {error}",
            status=RUN_STATUS_RUN_FAILED_KERNEL,
        )

    try:
        benchmark_total_return = _benchmark_total_return(wiring)
    except Exception as error:
        _raise_retained_basic_failure(
            root,
            intent,
            stage="benchmark",
            reason=f"BENCHMARK_BUILD_FAILED: {type(error).__name__}: {error}",
            status=RUN_STATUS_RUN_FAILED_KERNEL,
        )

    persisted: list[tuple[Path, Mapping[str, object]]] = []
    outcomes: list[BasicRunOutcome] = []
    for variant_id in intent.parameter_priority:
        outcome = run_basic_variant(
            wiring,
            intent,
            variant_id,
            intent.variant_parameters[variant_id],
            benchmark_total_return=benchmark_total_return,
        )
        run_dir, _entry = _persist_run(root, intent, outcome)
        persisted.append((run_dir, _entry))
        outcomes.append(outcome)

    try:
        selection = select_basic_candidate(intent, outcomes)
        selection_path, selection_digest = _persist_selection(
            root, intent, outcomes, selection
        )
        catalog_entry = append_entry(
            _catalog_dir(root),
            {
                "lineage_id": intent.lineage_id,
                "artifact_type": "BASIC_SELECTION",
                "ref": _relative_ref(root, selection_path),
                "status": selection.status,
                "digests": {"selection": selection_digest},
            },
        )
    except Exception as error:
        _raise_retained_basic_failure(
            root,
            intent,
            stage="selection-persistence",
            reason=f"SELECTION_PERSISTENCE_FAILED: {type(error).__name__}: {error}",
            status=RUN_STATUS_RUN_FAILED_KERNEL,
        )
    attempts = [
        {
            "variant_id": outcome.variant_id,
            "status": outcome.status,
            "reason_codes": list(outcome.reason_codes),
            "result_digest": outcome.result_digest,
            "run_id": run_dir.name,
        }
        for outcome, (run_dir, _entry) in zip(outcomes, persisted, strict=True)
    ]
    return {
        "schema_version": CLI_OUTPUT_SCHEMA_VERSION,
        "command": "basic-backtest",
        "status": "COMPLETED",
        "lineage_id": intent.lineage_id,
        "intent_digest": intent.intent_digest,
        "snapshot_digest": wiring.snapshot_digest,
        "selected_variant": selection.selected_variant_id,
        "selection_status": selection.status,
        "attempts": attempts,
        "catalog_sequence": catalog_entry["sequence"],
    }


def _wrap_oos_failure(error: OosError) -> CliFailure:
    return CliFailure(str(error))


def _resolve_candidate_path(root: Path, candidate_id: str) -> Path:
    """Locate the frozen intent for a candidate id.

    The id is either the lineage directory name or the intent_id of a frozen
    candidate under root; an unknown candidate fails closed.
    """
    direct = _lineage_dir(root, candidate_id) / "intent.json"
    if direct.exists():
        return direct
    if root.exists():
        for path in sorted(
            (*root.glob("*/intent.json"), *root.glob("*/intents/*/intent.json"))
        ):
            payload = read_json(path)
            if payload.get("intent_id") == candidate_id:
                return path
    raise CliFailure(
        f"{REASON_CANDIDATE_NOT_FOUND}: no frozen candidate {candidate_id!r} "
        f"exists under {root}"
    )


def _basic_pass_evidence(
    root: Path,
    intent: CandidateIntent,
) -> tuple[str, str, Mapping[str, object]]:
    """The Basic evidence a freeze binds: selection digest, selected variant
    id, and the selected variant's retained run manifest.

    A freeze without a promoted (BASIC_PASS, priority-selected) candidate
    fails closed.
    """
    selection_dir = _intent_dir(root, intent) / "basic-selection"
    selection_paths = (
        sorted(selection_dir.glob("*.json")) if selection_dir.exists() else []
    )
    if not selection_paths:
        raise CliFailure(
            f"{REASON_FREEZE_REQUIRES_BASIC_PASS}: lineage "
            f"{intent.lineage_id} has no Basic selection artifact; run "
            "'basic-backtest' before 'oos-freeze'"
        )
    selections = [read_json(path) for path in selection_paths]
    outcomes = {
        (str(item.get("status")), item.get("selected_variant_id"))
        for item in selections
    }
    if len(outcomes) != 1:
        raise CliFailure(
            f"{REASON_FREEZE_REQUIRES_BASIC_PASS}: lineage "
            f"{intent.lineage_id} carries disagreeing Basic selection "
            "artifacts; a freeze requires one unambiguous selection"
        )
    status, selected_variant_id = next(iter(outcomes))
    if status != "SELECTED" or not isinstance(selected_variant_id, str):
        raise CliFailure(
            f"{REASON_FREEZE_REQUIRES_BASIC_PASS}: lineage "
            f"{intent.lineage_id} has no BASIC_PASS selected variant "
            f"(selection status {status!r}); OOS is only reachable for a "
            "promoted candidate"
        )
    # Beyond the (status, variant) key every selection artifact must carry
    # identical evidence; digest-order file names are not chronology, so the
    # bound artifact is the deterministic lexicographically first one.
    if len({_content_digest(item) for item in selections}) != 1:
        raise CliFailure(
            f"{REASON_FREEZE_REQUIRES_BASIC_PASS}: lineage "
            f"{intent.lineage_id} carries disagreeing Basic selection "
            "artifacts; a freeze requires one unambiguous selection"
        )
    bound_selection = selections[0]
    attempts = bound_selection.get("attempts")
    selected_result_digest = ""
    if isinstance(attempts, list):
        for attempt in attempts:
            if (
                isinstance(attempt, dict)
                and attempt.get("variant_id") == selected_variant_id
                and attempt.get("status") == "BASIC_PASS"
                and isinstance(attempt.get("result_digest"), str)
            ):
                selected_result_digest = str(attempt["result_digest"])
                break
    if not selected_result_digest:
        raise CliFailure(
            f"{REASON_FREEZE_REQUIRES_BASIC_PASS}: the Basic selection of "
            f"{intent.lineage_id} records no BASIC_PASS attempt for the "
            f"selected variant {selected_variant_id!r}"
        )
    # The freeze binds the selection ARTIFACT digest (its persisted bytes),
    # and locates the selected run by the selection's recorded result digest.
    selection_digest = digest_of_bytes(selection_paths[0].read_bytes())
    run_manifest = _retained_run_manifest(
        root, intent, selected_variant_id, selected_result_digest
    )
    return selection_digest, selected_variant_id, run_manifest


def _retained_run_manifest(
    root: Path,
    intent: CandidateIntent,
    selected_variant_id: str,
    selected_result_digest: str,
) -> Mapping[str, object]:
    """Find the retained Basic run manifest of the selected variant.

    The match is content-based: a run's result.json must hash exactly to the
    selection's recorded result digest; identity, scope, and pass status are
    re-verified, never assumed.
    """
    runs_root = _intent_dir(root, intent) / "runs"
    if not runs_root.exists():
        raise CliFailure(
            f"{REASON_FREEZE_REQUIRES_BASIC_PASS}: lineage "
            f"{intent.lineage_id} has no retained Basic runs"
        )
    for run_dir in sorted(runs_root.iterdir()):
        if not run_dir.is_dir():
            continue
        result_path = run_dir / "result.json"
        manifest_path = run_dir / "manifest.json"
        if not result_path.exists() or not manifest_path.exists():
            raise CliFailure(
                f"RUN_ARTIFACT_INCOMPLETE: run directory {run_dir} is not "
                "complete; a half-persisted run can never be frozen over"
            )
        result_payload = read_json(result_path)
        result_digest = _content_digest(result_payload)
        if result_digest != selected_result_digest:
            continue
        if result_payload.get("variant_id") != selected_variant_id:
            continue
        if result_payload.get("status") != "BASIC_PASS":
            raise CliFailure(
                f"{REASON_FREEZE_REQUIRES_BASIC_PASS}: the retained run of "
                f"{selected_variant_id!r} is "
                f"{result_payload.get('status')!r}, not BASIC_PASS"
            )
        manifest = read_json(manifest_path)
        if manifest.get("intent_digest") != intent.intent_digest or manifest.get(
            "output_scope"
        ) != "BASIC":
            raise CliFailure(
                f"{REASON_FREEZE_REQUIRES_BASIC_PASS}: the retained run "
                f"manifest does not bind this lineage's intent at BASIC scope"
            )
        return manifest
    raise CliFailure(
        f"{REASON_FREEZE_REQUIRES_BASIC_PASS}: no retained Basic run of "
        f"{intent.lineage_id} matches the selected variant "
        f"{selected_variant_id!r} result digest"
    )


def command_oos_freeze(args: argparse.Namespace) -> Mapping[str, object]:
    root = Path(args.root)
    intent_path = _resolve_candidate_path(root, args.candidate_id)
    payload = read_json(intent_path)
    intent = _load_intent(intent_path)
    _require_screen_pass(root, intent)
    _check_frozen_intent(root, intent)

    selection_digest, selected_variant_id, run_manifest = _basic_pass_evidence(
        root, intent
    )
    try:
        require_selected_oos_candidate(root, intent, selected_variant_id)
        if read_asset_class_outcome(root, intent.asset_class.value) is not None:
            raise CliFailure(
                f"{REASON_OOS_ASSET_OUTCOME_EXISTS}: asset class "
                f"{intent.asset_class.value} already has a terminal outcome"
            )
    except CliFailure:
        raise
    except OosError as error:
        raise _wrap_oos_failure(error) from error
    freeze = build_freeze_payload(
        intent,
        intent_payload=payload,
        selected_variant_id=selected_variant_id,
        strategy_version=str(run_manifest["strategy_version"]),
        implementation_digest=str(run_manifest["implementation_digest"]),
        parameters_digest=str(run_manifest["parameters_digest"]),
        kernel_identity_digest=str(run_manifest["kernel_identity_digest"]),
        basic_selection_digest=selection_digest,
        basic_snapshot_digest=str(run_manifest["snapshot_digest"]),
    )
    try:
        resolve_freeze_kernel_replay_profile(
            freeze,
            intent,
            unsupported_reason=REASON_FREEZE_KERNEL_UNSUPPORTED,
        )
        reject_contaminated_oos_request(root, freeze)
    except OosError as error:
        raise _wrap_oos_failure(error) from error
    try:
        freeze_path, freeze_digest = persist_freeze(root, intent.lineage_id, freeze)
    except OosError as error:
        raise _wrap_oos_failure(error) from error
    catalog_entry = append_entry(
        _catalog_dir(root),
        {
            "lineage_id": intent.lineage_id,
            "artifact_type": "OOS_FREEZE",
            "ref": _relative_ref(root, freeze_path),
            "status": VERDICT_OOS_FROZEN,
            "digests": {"freeze": freeze_digest},
        },
    )
    return {
        "schema_version": CLI_OUTPUT_SCHEMA_VERSION,
        "command": "oos-freeze",
        "status": "COMPLETED",
        "freeze_id": freeze["freeze_id"],
        "freeze_digest": freeze_digest,
        "freeze_ref": _relative_ref(root, freeze_path),
        "lineage_id": intent.lineage_id,
        "intent_digest": intent.intent_digest,
        "selected_variant": selected_variant_id,
        "requested_oos_start": freeze["requested_oos_start"],
        "requested_oos_end": freeze["requested_oos_end"],
        "basic_selection_digest": selection_digest,
        "catalog_sequence": catalog_entry["sequence"],
    }


def _entry_sequence(entry: Mapping[str, object]) -> int:
    """The strictly increasing sequence number of one catalog entry."""
    sequence = entry.get("sequence")
    if not isinstance(sequence, int) or isinstance(sequence, bool):
        raise CliFailure(
            f"CATALOG_SEQUENCE_INVALID: catalog entry records sequence "
            f"{sequence!r}"
        )
    return sequence


def command_oos_run(args: argparse.Namespace) -> Mapping[str, object]:
    """Run the frozen OOS candidate once and record its single verdict.

    A failed oos-run retains only its reveal evidence — no result and no
    verdict — by design, mirroring the Basic failed-run retention contract;
    the freeze stays unconsumed only while no verdict exists.
    """
    root = Path(args.root)
    try:
        freeze_path, freeze_payload = find_freeze(root, args.freeze_id)
        intent = freeze_intent(freeze_payload)
    except OosError as error:
        raise _wrap_oos_failure(error) from error
    # The lineage's frozen intent must still match the freeze's embedded
    # intent: a self-consistent re-signed freeze cannot pass alone.
    _check_frozen_intent(root, intent)
    freeze_dir = freeze_path.parent
    try:
        selected_variant_from_freeze = freeze_payload.get("selected_variant_id")
        if not isinstance(selected_variant_from_freeze, str):
            raise CliFailure(
                f"{REASON_CANDIDATE_NOT_FOUND}: freeze has no selected variant"
            )
        require_selected_oos_candidate(
            root, intent, selected_variant_from_freeze
        )
        if read_asset_class_outcome(root, intent.asset_class.value) is not None:
            raise CliFailure(
                f"{REASON_OOS_ASSET_OUTCOME_EXISTS}: asset class "
                f"{intent.asset_class.value} already has a terminal outcome"
            )
    except CliFailure:
        raise
    except OosError as error:
        raise _wrap_oos_failure(error) from error
    try:
        require_no_existing_verdict(freeze_dir)
    except OosError as error:
        raise _wrap_oos_failure(error) from error

    # Pure freeze-vs-intent/strategy metadata enforcement runs BEFORE any
    # snapshot is opened: a self-consistent freeze binding an implementation,
    # version, parameters, or kernel identity that differs from the running
    # code is refused here, so edited code can never execute over OOS data
    # under the old identity.
    try:
        selected_variant_id = enforce_freeze_strategy_identity(
            freeze_payload, intent
        )
        kernel_profile = resolve_freeze_kernel_replay_profile(
            freeze_payload, intent
        )
    except OosError as error:
        raise _wrap_oos_failure(error) from error

    warm_up_dataset = None
    warm_up_digest: str | None = None
    if args.warm_up_snapshot:
        warm_up_path = Path(args.warm_up_snapshot)
        if not warm_up_path.exists():
            raise CliFailure(
                f"OOS_WARM_UP_SNAPSHOT_MISSING: warm-up snapshot manifest "
                f"does not exist: {warm_up_path}"
            )
        try:
            warm_up_manifest, warm_up_loaded = SnapshotReader().load(
                warm_up_path.parent
            )
        except SnapshotIntegrityError as error:
            raise CliFailure(
                f"SNAPSHOT_INTEGRITY_INVALID: warm-up snapshot failed "
                f"integrity verification: {error}"
            ) from error
        warm_up_digest = "sha256:" + str(warm_up_manifest.snapshot_id)
        if warm_up_digest != freeze_payload.get("basic_snapshot_digest"):
            raise CliFailure(
                f"OOS_WARM_UP_SNAPSHOT_MISMATCH: the warm-up snapshot "
                f"{warm_up_digest} does not match the freeze-bound Basic "
                f"snapshot {freeze_payload.get('basic_snapshot_digest')}"
            )
        warm_up_dataset = warm_up_loaded

    # The reveal intent is persisted BEFORE the OOS snapshot is opened: it is
    # the durable evidence of what the runner committed to revealing.
    reveal = reveal_payload(freeze_payload, warm_up_snapshot_digest=warm_up_digest)
    try:
        reveal_path, reveal_digest = record_reveal(freeze_dir, reveal)
    except OosError as error:
        raise _wrap_oos_failure(error) from error
    reveal_entry = append_entry(
        _catalog_dir(root),
        {
            "lineage_id": str(freeze_payload["lineage_id"]),
            "artifact_type": "OOS_REVEALED",
            "ref": _relative_ref(root, reveal_path),
            "status": reveal["status"],
            "digests": {"reveal": reveal_digest},
        },
    )

    # Only now may the runner open OOS data.
    snapshot_path = Path(args.snapshot)
    if not snapshot_path.exists():
        raise CliFailure(
            f"OOS_SNAPSHOT_MISSING: OOS snapshot manifest does not exist: "
            f"{snapshot_path}"
        )
    try:
        try:
            loaded_manifest, loaded_dataset = SnapshotReader().load(
                snapshot_path.parent
            )
        except SnapshotIntegrityError as error:
            raise CliFailure(
                f"SNAPSHOT_INTEGRITY_INVALID: OOS snapshot failed integrity "
                f"verification: {error}"
            ) from error
        receipt = validate_oos_snapshot(loaded_manifest, loaded_dataset, intent)
        master = default_m0_master()
        wiring = build_oos_wiring(
            loaded_dataset,
            intent,
            receipt,
            master=master,
            warm_up_dataset=warm_up_dataset,
            warm_up_snapshot_digest=warm_up_digest,
            kernel_profile=kernel_profile,
        )
        benchmark_total_return = oos_benchmark_total_return(wiring)
        outcome = run_oos_variant(
            wiring,
            intent,
            selected_variant_id,
            intent.variant_parameters[selected_variant_id],
            benchmark_total_return=benchmark_total_return,
        )
    except OosError as error:
        raise _wrap_oos_failure(error) from error

    try:
        result_path, result_digest = record_result(freeze_dir, outcome.result_payload)
        verdict = verdict_payload(
            freeze_payload,
            verdict=outcome.verdict,
            gate_verdicts=outcome.gate_verdicts,
            result_digest=result_digest,
        )
        verdict_path, verdict_digest = record_verdict(freeze_dir, verdict)
    except OosError as error:
        raise _wrap_oos_failure(error) from error
    append_entry(
        _catalog_dir(root),
        {
            "lineage_id": intent.lineage_id,
            "artifact_type": "OOS_RUN",
            "ref": _relative_ref(root, result_path),
            "status": outcome.verdict,
            "digests": {"result": result_digest},
        },
    )
    verdict_entry = append_entry(
        _catalog_dir(root),
        {
            "lineage_id": intent.lineage_id,
            "artifact_type": "OOS_VERDICT",
            "ref": _relative_ref(root, verdict_path),
            "status": outcome.verdict,
            "digests": {"verdict": verdict_digest},
        },
    )
    try:
        outcome_path, outcome_digest = persist_asset_class_outcome(
            root,
            AssetClassOutcome(
                asset_class=intent.asset_class.value,
                status=outcome.verdict,
                candidate_id=intent.lineage_id,
                selected_variant_id=outcome.variant_id,
                freeze_id=str(freeze_payload["freeze_id"]),
                reason_codes=tuple(
                    str(gate["criterion"])
                    for gate in outcome.gate_verdicts
                    if gate.get("verdict") != "PASS"
                ),
                known_limitations=tuple(intent.known_limitations),
                result_digest=result_digest,
            ),
        )
    except OosError as error:
        raise _wrap_oos_failure(error) from error
    return {
        "schema_version": CLI_OUTPUT_SCHEMA_VERSION,
        "command": "oos-run",
        "status": "COMPLETED",
        "freeze_id": freeze_payload["freeze_id"],
        "freeze_digest": freeze_payload["freeze_digest"],
        "lineage_id": intent.lineage_id,
        "verdict": outcome.verdict,
        "gate_verdicts": [dict(item) for item in outcome.gate_verdicts],
        "snapshot_digest": receipt.snapshot_digest,
        "universe_schedule_digest": receipt.universe_schedule_digest,
        "metrics": dict(outcome.metrics),
        "result_digest": result_digest,
        "catalog_sequence": _entry_sequence(verdict_entry),
        "reveal_sequence": _entry_sequence(reveal_entry),
        "outcome_ref": _relative_ref(root, outcome_path),
        "outcome_digest": outcome_digest,
    }


def command_select_oos(args: argparse.Namespace) -> Mapping[str, object]:
    """Select the one Basic-qualified candidate without opening OOS data."""
    root = Path(args.root)
    try:
        candidate = select_oos_candidate(root, args.asset)
    except OosError as error:
        raise _wrap_oos_failure(error) from error
    if candidate is None:
        return {
            "schema_version": CLI_OUTPUT_SCHEMA_VERSION,
            "command": "select-oos",
            "status": OUTCOME_NO_OOS_ELIGIBLE,
            "asset_class": args.asset,
            "reason": (
                "no lineage of this asset class holds a priority-selected "
                "Basic PASS candidate"
            ),
        }
    return {
        "schema_version": CLI_OUTPUT_SCHEMA_VERSION,
        "command": "select-oos",
        "status": OUTCOME_OOS_ELIGIBLE,
        "asset_class": candidate.asset_class,
        "candidate_id": candidate.lineage_id,
        "intent_id": candidate.intent_id,
        "selected_variant": candidate.selected_variant_id,
        "priority_rank": candidate.priority_rank,
        "selection_digest": candidate.selection_digest,
        "known_limitations": list(candidate.known_limitations),
    }


def command_no_oos_eligible(args: argparse.Namespace) -> Mapping[str, object]:
    root = Path(args.root)
    asset_class = args.asset
    try:
        candidate = select_oos_candidate(root, asset_class)
        if candidate is not None:
            raise CliFailure(
                f"{REASON_OOS_ELIGIBLE_CANDIDATE_EXISTS}: lineage "
                f"{candidate.lineage_id} holds the selected Basic candidate; "
                f"{OUTCOME_NO_OOS_ELIGIBLE} cannot be recorded for {asset_class}"
            )
        existing = read_asset_class_outcome(root, asset_class)
        if existing is not None and existing[1].status != OUTCOME_NO_OOS_ELIGIBLE:
            raise CliFailure(
                f"{REASON_OOS_ASSET_OUTCOME_EXISTS}: asset class {asset_class} "
                "already has a canonical OOS verdict"
            )
        outcome_path, _outcome_digest = persist_asset_class_outcome(
            root,
            AssetClassOutcome(
                asset_class=asset_class,
                status=OUTCOME_NO_OOS_ELIGIBLE,
                reason_codes=(OUTCOME_NO_OOS_ELIGIBLE,),
            ),
        )
    except CliFailure:
        raise
    except OosError as error:
        raise _wrap_oos_failure(error) from error
    reference = _relative_ref(root, outcome_path)
    catalog_entry = next(
        entry
        for entry in reversed(read_entries(_catalog_dir(root)))
        if entry.get("ref") == reference and entry.get("artifact_type") == "OOS_OUTCOME"
    )
    return {
        "schema_version": CLI_OUTPUT_SCHEMA_VERSION,
        "command": "no-oos-eligible",
        "status": OUTCOME_NO_OOS_ELIGIBLE,
        "asset_class": asset_class,
        "outcome_ref": reference,
        "catalog_sequence": catalog_entry["sequence"],
    }


def command_verify(args: argparse.Namespace) -> Mapping[str, object]:
    root = Path(args.root)
    report = verify_catalog(_catalog_dir(root), root)
    return {
        "schema_version": CLI_OUTPUT_SCHEMA_VERSION,
        "command": "verify",
        "status": report.status,
        "findings": list(report.findings),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="systematic_investing.research.cli",
        description=(
            "Research CLI: cheap screen, Basic backtest, OOS freeze/run, "
            "honest no-candidate outcomes, artifact verification. "
            "No provider fetch, no network, no bypass flags."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    screen = subparsers.add_parser("screen", help="cheap-screen a frozen CandidateIntent")
    screen.add_argument("--intent", required=True, help="path to the intent JSON")
    screen.add_argument("--root", required=True, help="experiments root directory")

    source_screen = subparsers.add_parser(
        "source-screen", help="cheap-screen a real external-source flight record"
    )
    source_screen.add_argument(
        "--source-record", required=True, help="path to the source-flight JSON"
    )
    source_screen.add_argument("--root", required=True, help="experiments root directory")

    basic = subparsers.add_parser(
        "basic-backtest", help="run every parameter variant on a Basic snapshot"
    )
    basic.add_argument("--intent", required=True, help="path to the intent JSON")
    basic.add_argument(
        "--snapshot",
        required=True,
        help="path to the materialized Basic snapshot manifest.json",
    )
    basic.add_argument("--root", required=True, help="experiments root directory")

    verify = subparsers.add_parser(
        "verify", help="verify the artifact catalog against content"
    )
    verify.add_argument("--root", required=True, help="experiments root directory")

    oos_freeze = subparsers.add_parser(
        "oos-freeze",
        help="freeze the OOS candidate after a Basic PASS (no data access)",
    )
    oos_freeze.add_argument(
        "--candidate-id",
        required=True,
        help="lineage id or intent id of the frozen candidate",
    )
    oos_freeze.add_argument("--root", required=True, help="experiments root directory")

    oos_run = subparsers.add_parser(
        "oos-run",
        help="run the frozen OOS candidate on the materialized OOS snapshot",
    )
    oos_run.add_argument("--freeze-id", required=True, help="the freeze id to run")
    oos_run.add_argument(
        "--snapshot",
        required=True,
        help="path to the materialized OOS snapshot manifest.json",
    )
    oos_run.add_argument(
        "--warm-up-snapshot",
        required=False,
        default=None,
        help=(
            "optional path to the Basic snapshot manifest.json; its digest is "
            "verified against the freeze and its data only primes strategy "
            "history before the OOS window"
        ),
    )
    oos_run.add_argument("--root", required=True, help="experiments root directory")

    select_oos = subparsers.add_parser(
        "select-oos",
        help="select the priority-qualified Basic candidate without opening OOS data",
    )
    select_oos.add_argument("--asset", required=True, choices=["ETF", "STOCK"])
    select_oos.add_argument("--root", required=True, help="experiments root directory")

    no_oos = subparsers.add_parser(
        "no-oos-eligible",
        help="record the honest NO_OOS_ELIGIBLE_CANDIDATE outcome (no materialization)",
    )
    no_oos.add_argument("--asset", required=True, choices=["ETF", "STOCK"])
    no_oos.add_argument("--root", required=True, help="experiments root directory")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    handlers: Mapping[
        str, Callable[[argparse.Namespace], Mapping[str, object]]
    ] = {
        "screen": command_screen,
        "source-screen": command_source_screen,
        "basic-backtest": command_basic_backtest,
        "select-oos": command_select_oos,
        "oos-freeze": command_oos_freeze,
        "oos-run": command_oos_run,
        "no-oos-eligible": command_no_oos_eligible,
        "verify": command_verify,
    }
    try:
        output = handlers[args.command](args)
    except CliFailure as error:
        print(
            json.dumps(
                {
                    "schema_version": CLI_OUTPUT_SCHEMA_VERSION,
                    "command": args.command,
                    "error": str(error),
                }
            ),
            file=sys.stderr,
        )
        return 1
    print(json.dumps(output, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
    if output.get("status") == "FAIL":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
