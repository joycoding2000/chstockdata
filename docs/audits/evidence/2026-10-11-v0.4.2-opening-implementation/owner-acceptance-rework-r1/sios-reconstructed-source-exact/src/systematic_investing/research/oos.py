"""The physical OOS exposure gate: freeze identity, exposure classification,
contamination checks, and the OOS run/verdict boundary.

OOS protection must control data exposure, not merely labels and hashes.
This module is the single authority for that boundary:

- **Exposure classification is one-way.** OOS-window data accessed without a
  verified freeze artifact can only ever be labeled
  ``HISTORICAL_VALIDATION``; no hash, label, or later freeze can convert
  already-happened exposure into a controlled OOS claim.
- **The freeze is a two-phase identity.** ``build_freeze_payload`` binds the
  frozen CandidateIntent (embedded and digest-checked), the selected
  implementation/parameters identity, the requested OOS scope, and the
  universe/benchmark/cost/kernel identities — after a Basic PASS and before
  any OOS data exists. It deliberately carries no OOS snapshot digest,
  because that digest cannot exist before materialization; the verifier
  rejects any freeze that claims one.
- **Verifiers fail closed.** ``verify_freeze_payload`` accepts only a
  self-digest-consistent freeze whose derived ``freeze_id`` matches; a
  mutated or re-signed-but-intent-swapped freeze is refused.
  ``verify_freeze_against_intent`` refuses scope drift and spec binding
  drift. ``validate_oos_scope`` refuses any request reaching back into the
  Basic window; ``validate_oos_snapshot`` refuses OOS snapshots containing
  Basic-window rows or rows beyond the declared OOS end.
- **The runner records intent before it opens data.** The reveal artifact is
  persisted before the runner opens the materialized OOS snapshot, and the
  survivor gate (``evaluate_oos_gate``) is decided strictly by the frozen
  ``oos_survivor_rule``; a freeze receives exactly one verdict. A failed
  oos-run retains only its reveal evidence — no result and no verdict — by
  design, mirroring the Basic failed-run retention contract.

This module never fetches provider or raw data and never imports the owner
materializer; the materializer imports THIS module for its freeze
validation. Nothing here observes wall-clock time: all identities are
content-derived.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

from systematic_investing.backtest.engine import (
    AmbiguousMarketFactError,
    DailyBarEngine,
    EngineClock,
    UnknownFactError,
)
from systematic_investing.backtest.execution import ExecutionModel
from systematic_investing.data.quality import CanonicalDataset
from systematic_investing.domain.historical_opening import (
    HistoricalOpeningEvidence,
    ExecutionEligibilityMode,
    OPENING_POLICY,
    OPENING_CLOCK_ID,
    opening_evidence_digest,
    execution_identity,
)
from systematic_investing.data.snapshots import DataSnapshotManifest
from systematic_investing.domain.execution import AccountFeeConfig, BrokerFeeProfile
from systematic_investing.domain.identifiers import InstrumentId
from systematic_investing.domain.ledger import CashLedgerEntry, NavPoint
from systematic_investing.domain.market import (
    CorporateAction,
    DailyBar,
    MarketCalendar,
    TradabilityStatus,
)
from systematic_investing.domain.money import Money
from systematic_investing.instrument_master.repository import InstrumentMaster
from systematic_investing.metrics.performance import (
    MetricConventions,
    compute_metrics,
)
from systematic_investing.research.artifacts import (
    ArtifactIntegrityError,
    canonical_json_bytes,
    digest_of_bytes,
    read_json,
    write_new_json,
)
from systematic_investing.research.benchmarks import (
    BENCHMARK_REBALANCE_INCEPTION,
    BENCHMARK_SCHEMA_VERSION,
    BenchmarkKind,
    BenchmarkSpec,
    BenchmarkTargetSource,
)
from systematic_investing.research.catalog import read_entries
from systematic_investing.research.contracts import (
    M1_APPROVED_ETF_SYMBOLS,
    REASON_INSUFFICIENT_HISTORY,
    RUN_MANIFEST_SCHEMA_VERSION,
    CandidateIntent,
    ResearchRunManifest,
    canonical_parameters_digest,
    canonical_payload_digest,
    split_digest_of,
    universe_view_digest,
)
from systematic_investing.research.kernel_replay import (
    KernelReplayProfile,
    UnsupportedKernelReplayError,
    current_kernel_replay_profile,
    resolve_kernel_replay_profile,
    SUPPORTED_KERNEL_REPLAY_PROFILES,
)
from systematic_investing.research.runner import (
    DEPENDENCY_DIGEST,
    StrategyTargetSource,
    build_canonical_strategy,
    cost_spec_digest,
    kernel_identity_digest,
    resolve_code_commit,
)
from systematic_investing.research.strategies import month_end_sessions
from systematic_investing.research.universe import UniverseView

FREEZE_SCHEMA_VERSION: str = "research-oos-freeze-1"
REVEAL_SCHEMA_VERSION: str = "research-oos-reveal-1"
VERDICT_SCHEMA_VERSION: str = "research-oos-verdict-1"
OOS_RESULT_SCHEMA_VERSION: str = "research-oos-result-1"

OOS_DIRNAME: str = "oos"
FREEZE_FILENAME: str = "freeze.json"
REVEAL_FILENAME: str = "reveal.json"
RESULT_FILENAME: str = "result.json"
VERDICT_FILENAME: str = "verdict.json"

OOS_OUTPUT_SCOPE: str = "OOS"
OOS_VERDICT_SURVIVOR: str = "SURVIVOR"
OOS_VERDICT_REJECTED_OOS: str = "REJECTED_OOS"
OOS_ELIGIBLE: str = "OOS_ELIGIBLE"
NO_OOS_ELIGIBLE_CANDIDATE: str = "NO_OOS_ELIGIBLE_CANDIDATE"
EXPOSURE_CONTROLLED_OOS: str = "CONTROLLED_OOS"
EXPOSURE_HISTORICAL_VALIDATION: str = "HISTORICAL_VALIDATION"
REVEAL_STATUS: str = "OOS_REVEALED"

FREEZE_ID_PREFIX: str = "freeze-"
FREEZE_ID_HEX_LENGTH: int = 16

# The OOS snapshot digest cannot exist when a freeze is written; a freeze
# that claims one is forged or confused and is always rejected.
FORBIDDEN_FREEZE_FIELDS: tuple[str, ...] = (
    "oos_snapshot_digest",
    "snapshot_digest",
)

REASON_FREEZE_MISSING: str = "OOS_FREEZE_MISSING"
REASON_FREEZE_INVALID: str = "OOS_FREEZE_INVALID"
REASON_FREEZE_DIGEST_MISMATCH: str = "OOS_FREEZE_DIGEST_MISMATCH"
REASON_FREEZE_ID_MISMATCH: str = "OOS_FREEZE_ID_MISMATCH"
REASON_FREEZE_FORBIDDEN_FIELD: str = "OOS_FREEZE_FORBIDDEN_FIELD"
REASON_FREEZE_INTENT_MISMATCH: str = "OOS_FREEZE_INTENT_MISMATCH"
REASON_FREEZE_SCOPE_MISMATCH: str = "OOS_FREEZE_SCOPE_MISMATCH"
REASON_FREEZE_BINDING_MISMATCH: str = "OOS_FREEZE_BINDING_MISMATCH"
REASON_FREEZE_IMPLEMENTATION_MISMATCH: str = "OOS_FREEZE_IMPLEMENTATION_MISMATCH"
REASON_FREEZE_KERNEL_MISMATCH: str = "OOS_FREEZE_KERNEL_MISMATCH"
REASON_FREEZE_KERNEL_UNSUPPORTED: str = "OOS_FREEZE_KERNEL_UNSUPPORTED"
REASON_FREEZE_AMBIGUOUS: str = "OOS_FREEZE_AMBIGUOUS"
REASON_FREEZE_REQUIRES_BASIC_PASS: str = "OOS_FREEZE_REQUIRES_BASIC_PASS"
REASON_OOS_SCOPE_OVERLAPS_BASIC: str = "OOS_SCOPE_OVERLAPS_BASIC"
REASON_OOS_SCOPE_OUTSIDE_DECLARED: str = "OOS_SCOPE_OUTSIDE_DECLARED_WINDOW"
REASON_OOS_EMPTY_SNAPSHOT: str = "OOS_EMPTY_SNAPSHOT"
REASON_OOS_ROWS_BEFORE_OOS_START: str = "OOS_ROWS_BEFORE_OOS_START"
REASON_OOS_END_EXCEEDED: str = "OOS_END_EXCEEDED"
REASON_OOS_END_UNCOVERED: str = "OOS_END_UNCOVERED"
REASON_OOS_INSTRUMENT_OUTSIDE_ASSET_CLASS: str = "OOS_INSTRUMENT_OUTSIDE_ASSET_CLASS"
REASON_OOS_INSTRUMENT_UNCOVERED: str = "OOS_INSTRUMENT_UNCOVERED"
REASON_OOS_INSTRUMENT_ENDS_EARLY: str = "OOS_INSTRUMENT_ENDS_BEFORE_OOS_END"
REASON_OOS_SNAPSHOT_QUALITY_NOT_PASS: str = "OOS_SNAPSHOT_QUALITY_NOT_PASS"
REASON_OOS_INVALID_SNAPSHOT: str = "OOS_SNAPSHOT_MANIFEST_INVALID"
REASON_STOCK_OOS_UNSUPPORTED: str = "STOCK_OOS_UNSUPPORTED"
REASON_OOS_HISTORY_INSUFFICIENT: str = "OOS_HISTORY_INSUFFICIENT"
REASON_OOS_NO_DECISION_SESSIONS: str = "OOS_NO_DECISION_SESSIONS"
REASON_OOS_SURVIVOR_RULE_INVALID: str = "OOS_SURVIVOR_RULE_INVALID"
REASON_OOS_RUN_FAILED_DATA: str = "OOS_RUN_FAILED_DATA"
REASON_OOS_RUN_FAILED_KERNEL: str = "OOS_RUN_FAILED_KERNEL"
REASON_OOS_ARTIFACT_CONFLICT: str = "OOS_ARTIFACT_IMMUTABILITY_CONFLICT"
REASON_OOS_VERDICT_EXISTS: str = "OOS_VERDICT_ALREADY_RECORDED"
REASON_OOS_WARMUP_AFTER_BASIC_END: str = "OOS_WARMUP_DATA_AFTER_BASIC_END"
REASON_OOS_WARMUP_CONFLICT: str = "OOS_WARMUP_SNAPSHOT_CONFLICT"
REASON_OOS_WARMUP_SNAPSHOT_DIGEST_MISMATCH: str = "OOS_WARMUP_SNAPSHOT_DIGEST_MISMATCH"
REASON_OOS_SELECTION_INVALID: str = "OOS_SELECTION_INVALID"
REASON_OOS_CANDIDATE_AMBIGUOUS: str = "OOS_CANDIDATE_AMBIGUOUS"
REASON_OOS_ASSET_OUTCOME_EXISTS: str = "OOS_ASSET_OUTCOME_ALREADY_RECORDED"
REASON_OOS_CONTAMINATED: str = "OOS_CONTAMINATED"
REASON_OOS_REVEALED_LEDGER_INVALID: str = "OOS_REVEALED_LEDGER_INVALID"


class OosError(Exception):
    """Base class for OOS exposure-gate errors."""


class OosFreezeError(OosError):
    """Raised when a freeze artifact is missing, forged, or drifts from the
    frozen intent."""


class OosExposureError(OosError):
    """Raised when a scope, snapshot, or run would expose OOS data outside
    the controlled boundary."""


class OosSelectionError(OosError):
    """Raised when Basic evidence cannot yield one auditable OOS candidate."""


@dataclass(frozen=True)
class RevealedOosWindow:
    """One immutable OOS interval already revealed for a stable lineage."""

    lineage_id: str
    freeze_id: str
    requested_oos_start: date
    requested_oos_end: date
    reveal_sequence: int
    reveal_digest: str
    terminal_status: str | None


@dataclass(frozen=True)
class OosCandidateSelection:
    """One asset-class candidate selected from immutable Basic evidence.

    The selected variant is already resolved by the candidate's declared
    ``parameter_priority``.  The asset-class selector never looks at returns
    or opens an OOS snapshot; it only chooses among retained Basic evidence.
    """

    asset_class: str
    lineage_id: str
    intent_id: str
    intent_digest: str
    selected_variant_id: str
    priority_rank: int
    selection_digest: str
    created_at: str
    known_limitations: tuple[str, ...]

    def to_payload(self) -> dict[str, object]:
        return {
            "asset_class": self.asset_class,
            "lineage_id": self.lineage_id,
            "intent_id": self.intent_id,
            "intent_digest": self.intent_digest,
            "selected_variant_id": self.selected_variant_id,
            "priority_rank": self.priority_rank,
            "selection_digest": self.selection_digest,
            "created_at": self.created_at,
            "known_limitations": list(self.known_limitations),
        }


def _selection_artifact(
    lineage_dir: Path,
) -> tuple[Path, dict[str, object]] | None:
    """Return the one unambiguous Basic selection for a lineage.

    Rejected Basic attempts may be retried and therefore leave several
    ``NO_BASIC_PASS`` selection artifacts.  They are all non-eligible and can
    be ignored.  More than one selected artifact is different: a candidate
    cannot enter OOS while its Basic evidence disagrees.
    """
    selection_dir = lineage_dir / "basic-selection"
    if not selection_dir.exists():
        return None
    paths = sorted(selection_dir.glob("*.json"))
    if not paths:
        return None
    payloads = [(path, read_json(path)) for path in paths]
    statuses = {payload.get("status") for _path, payload in payloads}
    if statuses == {"NO_BASIC_PASS"}:
        return None
    if statuses != {"SELECTED"} or len(payloads) != 1:
        raise OosSelectionError(
            f"{REASON_OOS_SELECTION_INVALID}: lineage {lineage_dir.name} has "
            "missing, mixed, or disagreeing Basic selection artifacts"
        )
    return payloads[0]


def _candidate_from_lineage(
    lineage_dir: Path,
    *,
    asset_class: str,
) -> OosCandidateSelection | None:
    intent_path = lineage_dir / "intent.json"
    if not intent_path.exists():
        return None
    try:
        intent_payload = read_json(intent_path)
        intent = CandidateIntent.from_dict(intent_payload)
    except Exception as error:
        raise OosSelectionError(
            f"{REASON_OOS_SELECTION_INVALID}: candidate {lineage_dir.name} "
            f"has an invalid frozen intent: {type(error).__name__}: {error}"
        ) from error
    if intent.asset_class.value != asset_class:
        return None

    selection = _selection_artifact(lineage_dir)
    if selection is None:
        return None
    selection_path, selection_payload = selection
    selected_variant = selection_payload.get("selected_variant_id")
    if not isinstance(selected_variant, str) or not selected_variant:
        raise OosSelectionError(
            f"{REASON_OOS_SELECTION_INVALID}: selected Basic candidate for "
            f"{lineage_dir.name} has no variant id"
        )
    try:
        priority_rank = intent.parameter_priority.index(selected_variant)
    except ValueError as error:
        raise OosSelectionError(
            f"{REASON_OOS_SELECTION_INVALID}: selected variant "
            f"{selected_variant!r} is not declared by {intent.lineage_id}"
        ) from error

    attempts = selection_payload.get("attempts")
    if attempts is not None:
        if not isinstance(attempts, list):
            raise OosSelectionError(
                f"{REASON_OOS_SELECTION_INVALID}: Basic attempts for "
                f"{intent.lineage_id} are not a list"
            )
        pass_by_variant: dict[str, bool] = {}
        for attempt in attempts:
            if not isinstance(attempt, dict):
                raise OosSelectionError(
                    f"{REASON_OOS_SELECTION_INVALID}: Basic attempt in "
                    f"{intent.lineage_id} is not an object"
                )
            variant_id = attempt.get("variant_id")
            status = attempt.get("status")
            if not isinstance(variant_id, str) or not isinstance(status, str):
                raise OosSelectionError(
                    f"{REASON_OOS_SELECTION_INVALID}: Basic attempt in "
                    f"{intent.lineage_id} lacks variant/status"
                )
            if variant_id in pass_by_variant:
                raise OosSelectionError(
                    f"{REASON_OOS_SELECTION_INVALID}: duplicate Basic attempt "
                    f"for {variant_id!r} in {intent.lineage_id}"
                )
            pass_by_variant[variant_id] = status == "BASIC_PASS"
        first_pass = next(
            (
                variant_id
                for variant_id in intent.parameter_priority
                if pass_by_variant.get(variant_id, False)
            ),
            None,
        )
        if first_pass != selected_variant:
            raise OosSelectionError(
                f"{REASON_OOS_SELECTION_INVALID}: {intent.lineage_id} selected "
                f"{selected_variant!r}, but priority selects {first_pass!r}"
            )

    return OosCandidateSelection(
        asset_class=asset_class,
        lineage_id=intent.lineage_id,
        intent_id=intent.intent_id,
        intent_digest=intent.intent_digest,
        selected_variant_id=selected_variant,
        priority_rank=priority_rank,
        selection_digest=digest_of_bytes(selection_path.read_bytes()),
        created_at=intent.created_at.isoformat(),
        known_limitations=tuple(intent.known_limitations),
    )


def collect_oos_candidates(root: Path, asset_class: str) -> tuple[OosCandidateSelection, ...]:
    """Collect eligible candidates from retained Basic evidence only."""
    if asset_class not in {"ETF", "STOCK"}:
        raise OosSelectionError(
            f"{REASON_OOS_SELECTION_INVALID}: unsupported asset class "
            f"{asset_class!r}"
        )
    experiment_root = Path(root)
    if not experiment_root.exists():
        return ()
    candidates: list[OosCandidateSelection] = []
    for lineage_dir in sorted(experiment_root.iterdir()):
        if (
            not lineage_dir.is_dir()
            or lineage_dir.name.startswith(".")
            or lineage_dir.name in {"catalog", "outcomes"}
        ):
            continue
        candidate = _candidate_from_lineage(lineage_dir, asset_class=asset_class)
        if candidate is not None:
            candidates.append(candidate)
    return tuple(candidates)


def select_oos_candidate(
    root: Path,
    asset_class: str,
) -> OosCandidateSelection | None:
    """Select one OOS candidate without opening any OOS data.

    The selected variant's rank comes from the frozen CandidateIntent.  Two
    independent lineages have no cross-strategy priority in M1, so their
    presence is an explicit ambiguity rather than an invitation to choose by
    returns, creation date, or filesystem order.
    """
    candidates = collect_oos_candidates(root, asset_class)
    if not candidates:
        return None
    if len(candidates) > 1:
        candidate_ids = ", ".join(candidate.lineage_id for candidate in candidates)
        raise OosSelectionError(
            f"{REASON_OOS_CANDIDATE_AMBIGUOUS}: {asset_class} has multiple "
            f"independent Basic-qualified lineages ({candidate_ids}); M1 "
            "declares parameter priority within one CandidateIntent only"
        )
    return candidates[0]


def require_selected_oos_candidate(
    root: Path,
    intent: CandidateIntent,
    selected_variant_id: str,
) -> OosCandidateSelection:
    """Fail closed unless a frozen candidate is the asset-class selection."""
    selected = select_oos_candidate(root, intent.asset_class.value)
    if selected is None:
        raise OosSelectionError(
            f"{NO_OOS_ELIGIBLE_CANDIDATE}: {intent.asset_class.value} has no "
            "priority-selected Basic PASS candidate"
        )
    if (
        selected.lineage_id != intent.lineage_id
        or selected.selected_variant_id != selected_variant_id
    ):
        raise OosSelectionError(
            f"{REASON_OOS_CANDIDATE_AMBIGUOUS}: candidate "
            f"{intent.lineage_id}/{selected_variant_id} is not the selected "
            f"{intent.asset_class.value} OOS candidate "
            f"{selected.lineage_id}/{selected.selected_variant_id}"
        )
    return selected


# --- exposure classification --------------------------------------------------


def classify_exposure(*, freeze_verified: bool) -> str:
    """Classify OOS-window data exposure.

    Without a verified freeze the classification is permanently
    ``HISTORICAL_VALIDATION``: hashes and labels cannot retroactively turn
    happened exposure into a controlled OOS claim.
    """
    return EXPOSURE_CONTROLLED_OOS if freeze_verified else EXPOSURE_HISTORICAL_VALIDATION


# --- scope validation ----------------------------------------------------------


def validate_oos_scope(
    intent: CandidateIntent,
    *,
    start: date,
    end: date,
) -> None:
    """Validate a requested OOS materialization/run scope against the intent.

    The scope may never reach back into the Basic window and must stay
    inside the declared OOS window; anything else is refused before any data
    access.
    """
    if start <= intent.basic_end:
        raise OosExposureError(
            f"{REASON_OOS_SCOPE_OVERLAPS_BASIC}: the requested OOS scope "
            f"starts at {start.isoformat()}, at or before the Basic end "
            f"{intent.basic_end.isoformat()}; an OOS request may never "
            "reach back into the Basic window"
        )
    if start > end:
        raise OosExposureError(
            f"{REASON_OOS_SCOPE_OUTSIDE_DECLARED}: the requested OOS scope "
            f"starts after it ends ({start.isoformat()} > {end.isoformat()})"
        )
    if start < intent.oos_start or end > intent.oos_end:
        raise OosExposureError(
            f"{REASON_OOS_SCOPE_OUTSIDE_DECLARED}: the requested OOS scope "
            f"[{start.isoformat()}, {end.isoformat()}] leaves the declared "
            f"OOS window [{intent.oos_start.isoformat()}, "
            f"{intent.oos_end.isoformat()}]"
        )


# --- freeze artifact model -----------------------------------------------------


def _freeze_body(
    intent: CandidateIntent,
    *,
    intent_payload: Mapping[str, object],
    selected_variant_id: str,
    strategy_version: str,
    implementation_digest: str,
    parameters_digest: str,
    kernel_identity_digest: str,
    basic_selection_digest: str,
    basic_snapshot_digest: str,
) -> dict[str, object]:
    return {
        "freeze_schema_version": FREEZE_SCHEMA_VERSION,
        "lineage_id": intent.lineage_id,
        "intent_id": intent.intent_id,
        "intent_digest": intent.intent_digest,
        "intent_payload": dict(intent_payload),
        "strategy_id": intent.strategy_id,
        "selected_variant_id": selected_variant_id,
        "strategy_version": strategy_version,
        "implementation_digest": implementation_digest,
        "parameters_digest": parameters_digest,
        "kernel_identity_digest": kernel_identity_digest,
        "basic_selection_digest": basic_selection_digest,
        "basic_snapshot_digest": basic_snapshot_digest,
        "requested_oos_start": intent.oos_start.isoformat(),
        "requested_oos_end": intent.oos_end.isoformat(),
        "universe_policy_digest": intent.universe_policy.digest(),
        "benchmark_digest": intent.benchmark.digest(),
        "cost_spec_digest": cost_spec_digest(intent),
        "split_digest": split_digest_of(
            intent.warm_up_start,
            intent.basic_start,
            intent.basic_end,
            intent.oos_start,
            intent.oos_end,
        ),
    }


def build_freeze_payload(
    intent: CandidateIntent,
    *,
    intent_payload: Mapping[str, object],
    selected_variant_id: str,
    strategy_version: str,
    implementation_digest: str,
    parameters_digest: str,
    kernel_identity_digest: str,
    basic_selection_digest: str,
    basic_snapshot_digest: str,
) -> dict[str, object]:
    """Build the freeze artifact payload from the frozen candidate and the
    selected Basic identity.

    The OOS snapshot digest is deliberately absent: it cannot exist before
    the owner materializes the controlled OOS snapshot. ``freeze_id`` and
    ``freeze_digest`` are content-derived, with no wall-clock input.
    """
    body = _freeze_body(
        intent,
        intent_payload=intent_payload,
        selected_variant_id=selected_variant_id,
        strategy_version=strategy_version,
        implementation_digest=implementation_digest,
        parameters_digest=parameters_digest,
        kernel_identity_digest=kernel_identity_digest,
        basic_selection_digest=basic_selection_digest,
        basic_snapshot_digest=basic_snapshot_digest,
    )
    core_digest = canonical_payload_digest(body)
    freeze_id = FREEZE_ID_PREFIX + core_digest.removeprefix("sha256:")[
        :FREEZE_ID_HEX_LENGTH
    ]
    payload = {**body, "freeze_id": freeze_id}
    payload["freeze_digest"] = canonical_payload_digest(payload)
    return payload


_REQUIRED_FREEZE_TEXT_FIELDS: tuple[str, ...] = (
    "lineage_id",
    "intent_id",
    "intent_digest",
    "strategy_id",
    "selected_variant_id",
    "strategy_version",
    "implementation_digest",
    "parameters_digest",
    "kernel_identity_digest",
    "basic_selection_digest",
    "basic_snapshot_digest",
    "requested_oos_start",
    "requested_oos_end",
    "universe_policy_digest",
    "benchmark_digest",
    "cost_spec_digest",
    "split_digest",
    "freeze_id",
    "freeze_digest",
)


def _require_sha256(value: object, field_name: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 71
        or not value.startswith("sha256:")
        or not all(character in "0123456789abcdef" for character in value[7:])
    ):
        raise OosFreezeError(
            f"{REASON_FREEZE_INVALID}: freeze field {field_name} must be a "
            f"sha256:<64 hex> digest, got {value!r}"
        )
    return value


def verify_freeze_payload(payload: Mapping[str, object]) -> dict[str, object]:
    """Verify one freeze artifact payload and return it unchanged.

    Fail-closed order: forbidden fields (a claimed OOS snapshot digest),
    schema version, required fields, self-digest, derived ``freeze_id``, and
    the embedded intent payload (which must hash to the recorded intent
    digest). A self-consistent swap of both the embedding and the recorded
    digest is detectable only against the lineage's frozen intent and Basic
    evidence, which the OOS runner cross-checks.
    """
    if not isinstance(payload, Mapping):
        raise OosFreezeError(
            f"{REASON_FREEZE_INVALID}: the freeze payload must be a mapping"
        )
    for forbidden in FORBIDDEN_FREEZE_FIELDS:
        if forbidden in payload:
            raise OosFreezeError(
                f"{REASON_FREEZE_FORBIDDEN_FIELD}: the freeze claims "
                f"{forbidden!r}; the OOS snapshot digest cannot exist "
                "before materialization"
            )
    if payload.get("freeze_schema_version") != FREEZE_SCHEMA_VERSION:
        raise OosFreezeError(
            f"{REASON_FREEZE_INVALID}: unsupported freeze_schema_version "
            f"{payload.get('freeze_schema_version')!r}"
        )
    for field_name in _REQUIRED_FREEZE_TEXT_FIELDS:
        if not isinstance(payload.get(field_name), str) or not payload[field_name]:
            raise OosFreezeError(
                f"{REASON_FREEZE_INVALID}: freeze field {field_name} is "
                "missing or empty"
            )
    for field_name in _REQUIRED_FREEZE_TEXT_FIELDS:
        if field_name.endswith("_digest"):
            _require_sha256(payload[field_name], field_name)

    recorded_digest = str(payload["freeze_digest"])
    body = {key: value for key, value in payload.items() if key != "freeze_digest"}
    if canonical_payload_digest(body) != recorded_digest:
        raise OosFreezeError(
            f"{REASON_FREEZE_DIGEST_MISMATCH}: the freeze content does not "
            "match its recorded freeze_digest; the artifact was mutated"
        )
    core = {key: value for key, value in body.items() if key != "freeze_id"}
    derived_id = FREEZE_ID_PREFIX + canonical_payload_digest(core).removeprefix(
        "sha256:"
    )[:FREEZE_ID_HEX_LENGTH]
    if str(payload["freeze_id"]) != derived_id:
        raise OosFreezeError(
            f"{REASON_FREEZE_ID_MISMATCH}: freeze_id {payload['freeze_id']!r} "
            f"does not match the content-derived id {derived_id!r}"
        )

    embedded = payload.get("intent_payload")
    if not isinstance(embedded, Mapping):
        raise OosFreezeError(
            f"{REASON_FREEZE_INVALID}: the freeze must embed the frozen "
            "intent payload"
        )
    try:
        reconstructed = CandidateIntent.from_dict(embedded)
    except Exception as error:
        raise OosFreezeError(
            f"{REASON_FREEZE_INVALID}: the embedded intent payload does not "
            f"validate: {type(error).__name__}: {error}"
        ) from error
    if reconstructed.intent_digest != payload["intent_digest"]:
        raise OosFreezeError(
            f"{REASON_FREEZE_INTENT_MISMATCH}: the embedded intent payload "
            f"hashes to {reconstructed.intent_digest} but the freeze records "
            f"{payload['intent_digest']}"
        )
    return dict(payload)


def freeze_intent(payload: Mapping[str, object]) -> CandidateIntent:
    """Reconstruct the frozen CandidateIntent embedded in a verified freeze."""
    embedded = payload.get("intent_payload")
    if not isinstance(embedded, Mapping):
        raise OosFreezeError(
            f"{REASON_FREEZE_INVALID}: the freeze carries no intent payload"
        )
    return CandidateIntent.from_dict(embedded)


def verify_freeze_against_intent(
    payload: Mapping[str, object],
    intent: CandidateIntent,
) -> None:
    """Verify a verified freeze's bindings against the lineage's intent.

    The requested scope must equal the intent's declared OOS window and every
    pre-registered spec digest must match; any drift means the freeze
    describes a different candidate and fails closed.
    """
    if payload.get("lineage_id") != intent.lineage_id or payload.get(
        "intent_id"
    ) != intent.intent_id:
        raise OosFreezeError(
            f"{REASON_FREEZE_BINDING_MISMATCH}: the freeze names "
            f"{payload.get('lineage_id')!r}/{payload.get('intent_id')!r}, not "
            f"the lineage {intent.lineage_id!r}/{intent.intent_id!r}"
        )
    if payload.get("intent_digest") != intent.intent_digest:
        raise OosFreezeError(
            f"{REASON_FREEZE_INTENT_MISMATCH}: the freeze records "
            f"{payload.get('intent_digest')!r} but the lineage intent is "
            f"{intent.intent_digest}"
        )
    expected_scope = (intent.oos_start.isoformat(), intent.oos_end.isoformat())
    actual_scope = (
        payload.get("requested_oos_start"),
        payload.get("requested_oos_end"),
    )
    if actual_scope != expected_scope:
        raise OosFreezeError(
            f"{REASON_FREEZE_SCOPE_MISMATCH}: the freeze requests OOS scope "
            f"{actual_scope} but the intent declares {expected_scope}"
        )
    bindings: tuple[tuple[str, object, object], ...] = (
        ("universe_policy_digest", payload.get("universe_policy_digest"),
         intent.universe_policy.digest()),
        ("benchmark_digest", payload.get("benchmark_digest"),
         intent.benchmark.digest()),
        ("cost_spec_digest", payload.get("cost_spec_digest"),
         cost_spec_digest(intent)),
        (
            "split_digest",
            payload.get("split_digest"),
            split_digest_of(
                intent.warm_up_start,
                intent.basic_start,
                intent.basic_end,
                intent.oos_start,
                intent.oos_end,
            ),
        ),
    )
    for field_name, recorded, expected in bindings:
        if recorded != expected:
            raise OosFreezeError(
                f"{REASON_FREEZE_BINDING_MISMATCH}: freeze field "
                f"{field_name} ({recorded!r}) does not match the intent "
                f"({expected!r})"
            )


def _intent_execution_model(intent: CandidateIntent) -> ExecutionModel:
    """The kernel execution model derived from the intent's frozen cost
    conventions — the same derivation the Basic wiring uses."""
    slippage = Decimal(intent.cost_convention["slippage_rate"])
    return ExecutionModel(slippage_rate_buy=slippage, slippage_rate_sell=slippage)


def oos_kernel_identity_digest(
    intent: CandidateIntent,
    *,
    profile: KernelReplayProfile = current_kernel_replay_profile,
    execution_eligibility_mode: ExecutionEligibilityMode = ExecutionEligibilityMode.LEGACY,
) -> str:
    """The selected kernel identity for an intent's frozen cost conventions."""
    return kernel_identity_digest(
        _intent_execution_model(intent),
        profile=profile,
        execution_eligibility_mode=execution_eligibility_mode,
    )


def resolve_freeze_kernel_replay_profile(
    freeze_payload: Mapping[str, object],
    intent: CandidateIntent,
    *,
    unsupported_reason: str = REASON_FREEZE_KERNEL_MISMATCH,
    execution_eligibility_mode: ExecutionEligibilityMode = ExecutionEligibilityMode.LEGACY,
) -> KernelReplayProfile:
    """Resolve and validate the exact executable profile bound by a freeze."""
    digest = freeze_payload.get("kernel_identity_digest")
    if not isinstance(digest, str) or not digest:
        raise OosFreezeError(
            f"{unsupported_reason}: the freeze has no kernel identity digest"
        )
    try:
        if execution_eligibility_mode is ExecutionEligibilityMode.HISTORICAL_OPENING_R21:
            for profile in SUPPORTED_KERNEL_REPLAY_PROFILES:
                if (
                    oos_kernel_identity_digest(
                        intent,
                        profile=profile,
                        execution_eligibility_mode=execution_eligibility_mode,
                    )
                    == digest
                ):
                    return profile
            raise UnsupportedKernelReplayError(
                "no historical opening replay profile matches the explicitly selected mode"
            )
        return resolve_kernel_replay_profile(
            digest, _intent_execution_model(intent)
        )
    except UnsupportedKernelReplayError as error:
        raise OosFreezeError(
            f"{unsupported_reason}: no executable replay profile matches "
            f"the freeze-bound kernel identity {digest!r}: {error}"
        ) from error


def enforce_freeze_strategy_identity(
    freeze_payload: Mapping[str, object],
    intent: CandidateIntent,
    *,
    execution_eligibility_mode: ExecutionEligibilityMode = ExecutionEligibilityMode.LEGACY,
) -> str:
    """Enforce the freeze-bound strategy/kernel identity against the CURRENT
    code, before any OOS data is opened.

    The freeze binds the selected variant's parameters, implementation
    digest, strategy version, and kernel identity from the retained Basic
    run. This verifier re-derives all four from the frozen intent and the
    running code, resolving a supported historical replay profile when
    needed, and refuses any drift with typed reasons. Code edited between
    ``oos-freeze`` and ``oos-run`` can therefore never execute over OOS data
    under an unverified identity. Returns the validated selected variant id.
    """
    selected_variant_id = str(freeze_payload.get("selected_variant_id"))
    if selected_variant_id not in intent.variant_parameters:
        raise OosFreezeError(
            f"{REASON_FREEZE_BINDING_MISMATCH}: the freeze selects variant "
            f"{selected_variant_id!r}, which the frozen intent does not declare"
        )
    variant_parameters = intent.variant_parameters[selected_variant_id]
    parameters_digest = canonical_parameters_digest(variant_parameters)
    if parameters_digest != freeze_payload.get("parameters_digest"):
        raise OosFreezeError(
            f"{REASON_FREEZE_BINDING_MISMATCH}: the freeze's parameters_digest "
            f"{freeze_payload.get('parameters_digest')!r} does not match the "
            f"selected variant's canonical parameters {parameters_digest}"
        )
    try:
        strategy = build_canonical_strategy(intent, variant_parameters, ())
    except Exception as error:
        raise OosFreezeError(
            f"{REASON_FREEZE_INVALID}: the canonical strategy for "
            f"{intent.strategy_id!r} could not be built: "
            f"{type(error).__name__}: {error}"
        ) from error
    identity = strategy.identity
    if identity.implementation_digest != freeze_payload.get(
        "implementation_digest"
    ) or identity.strategy_version != freeze_payload.get("strategy_version"):
        raise OosFreezeError(
            f"{REASON_FREEZE_IMPLEMENTATION_MISMATCH}: the running "
            f"implementation {identity.implementation_digest} "
            f"({identity.strategy_version!r}) does not match the freeze-bound "
            f"implementation {freeze_payload.get('implementation_digest')!r} "
            f"({freeze_payload.get('strategy_version')!r}); the implementation "
            "changed after the freeze"
        )
    kernel_profile = resolve_freeze_kernel_replay_profile(
        freeze_payload, intent, execution_eligibility_mode=execution_eligibility_mode
    )
    kernel_digest = oos_kernel_identity_digest(
        intent, profile=kernel_profile, execution_eligibility_mode=execution_eligibility_mode
    )
    if kernel_digest != freeze_payload.get("kernel_identity_digest"):
        raise OosFreezeError(
            f"{REASON_FREEZE_KERNEL_MISMATCH}: the running kernel identity "
            f"{kernel_digest} does not match the freeze-bound kernel identity "
            f"{freeze_payload.get('kernel_identity_digest')!r}; the kernel "
            "changed after the freeze"
        )
    return selected_variant_id


# --- freeze persistence and location -------------------------------------------


def freeze_dir_for(root: Path, lineage_id: str, freeze_id: str) -> Path:
    return Path(root) / lineage_id / OOS_DIRNAME / freeze_id


def _write_immutable(path: Path, payload: Mapping[str, object]) -> str:
    """Write one fixed-name immutable artifact, or confirm an identical
    existing one. Different existing content fails closed."""
    content_digest = digest_of_bytes(canonical_json_bytes(payload))
    if path.exists():
        existing = read_json(path)
        existing_digest = digest_of_bytes(canonical_json_bytes(existing))
        if existing_digest != content_digest:
            raise OosExposureError(
                f"{REASON_OOS_ARTIFACT_CONFLICT}: {path} exists with "
                "different content; OOS artifacts are immutable"
            )
        return existing_digest
    write_new_json(path, payload)
    return content_digest


def persist_freeze(
    root: Path,
    lineage_id: str,
    payload: Mapping[str, object],
) -> tuple[Path, str]:
    """Persist the freeze at ``<root>/<lineage_id>/oos/<freeze_id>/freeze.json``
    and return its path and content digest."""
    verified = verify_freeze_payload(payload)
    freeze_id = str(verified["freeze_id"])
    directory = freeze_dir_for(root, lineage_id, freeze_id)
    path = directory / FREEZE_FILENAME
    try:
        digest = _write_immutable(path, payload)
    except ArtifactIntegrityError as error:
        raise OosExposureError(
            f"{REASON_OOS_ARTIFACT_CONFLICT}: the freeze could not be "
            f"persisted: {error}"
        ) from error
    return path, digest


def find_freeze(root: Path, freeze_id: str) -> tuple[Path, dict[str, object]]:
    """Locate and verify the freeze artifact for ``freeze_id`` under root.

    Exactly one verified freeze must match; zero is missing and more than
    one is ambiguous. Both fail closed.
    """
    matches: list[tuple[Path, dict[str, object]]] = []
    for candidate in sorted(Path(root).glob(f"*/{OOS_DIRNAME}/{freeze_id}/{FREEZE_FILENAME}")):
        payload = read_json(candidate)
        if payload.get("freeze_id") == freeze_id:
            matches.append((candidate, payload))
    if not matches:
        raise OosFreezeError(
            f"{REASON_FREEZE_MISSING}: no freeze artifact {freeze_id!r} exists "
            f"under {root}"
        )
    if len(matches) > 1:
        raise OosFreezeError(
            f"{REASON_FREEZE_AMBIGUOUS}: {len(matches)} freeze artifacts "
            f"claim freeze_id {freeze_id!r}"
        )
    path, payload = matches[0]
    verify_freeze_payload(payload)
    return path, payload


def require_no_existing_verdict(freeze_directory: Path) -> None:
    """A freeze receives exactly one verdict, ever; a recorded verdict makes
    any further OOS run fail closed."""
    verdict_path = freeze_directory / VERDICT_FILENAME
    if verdict_path.exists():
        raise OosExposureError(
            f"{REASON_OOS_VERDICT_EXISTS}: verdict {verdict_path} already "
            "exists; a freeze receives exactly one OOS verdict and is never "
            "re-run"
        )


def record_reveal(
    freeze_directory: Path,
    payload: Mapping[str, object],
) -> tuple[Path, str]:
    """Persist the reveal artifact (create-new or identical confirm).

    The caller must invoke this BEFORE opening any OOS snapshot data; the
    reveal is the durable evidence that the runner committed to opening the
    controlled OOS snapshot for this freeze.
    """
    path = freeze_directory / REVEAL_FILENAME
    try:
        digest = _write_immutable(path, payload)
    except ArtifactIntegrityError as error:
        raise OosExposureError(
            f"{REASON_OOS_ARTIFACT_CONFLICT}: the reveal artifact could not "
            f"be persisted: {error}"
        ) from error
    return path, digest


def rebuild_revealed_oos_window_ledger(root: Path) -> tuple[RevealedOosWindow, ...]:
    """Rebuild revealed OOS intervals from immutable reveal/catalog evidence.

    The catalog is the authoritative ordering source.  Each entry is checked
    against the referenced reveal bytes before it can contribute an interval;
    malformed historical evidence blocks a future OOS request rather than
    leaving a bypass path.
    """
    entries = read_entries(Path(root) / "catalog")
    verdicts_by_freeze: dict[str, str] = {}
    for entry in entries:
        if entry.get("artifact_type") != "OOS_VERDICT":
            continue
        reference = entry.get("ref")
        status = entry.get("status")
        if not isinstance(reference, str) or not isinstance(status, str):
            raise OosExposureError(
                f"{REASON_OOS_REVEALED_LEDGER_INVALID}: malformed OOS verdict catalog entry"
            )
        freeze_id = Path(reference).parent.name
        if not freeze_id:
            raise OosExposureError(
                f"{REASON_OOS_REVEALED_LEDGER_INVALID}: verdict reference has no freeze id"
            )
        verdicts_by_freeze[freeze_id] = status

    windows: list[RevealedOosWindow] = []
    for entry in entries:
        if entry.get("artifact_type") != REVEAL_STATUS:
            continue
        sequence = entry.get("sequence")
        reference = entry.get("ref")
        digests = entry.get("digests")
        if (
            not isinstance(sequence, int)
            or isinstance(sequence, bool)
            or not isinstance(reference, str)
            or not isinstance(digests, dict)
            or not isinstance(digests.get("reveal"), str)
        ):
            raise OosExposureError(
                f"{REASON_OOS_REVEALED_LEDGER_INVALID}: malformed OOS reveal catalog entry"
            )
        reveal_path = Path(root) / reference
        try:
            reveal_bytes = reveal_path.read_bytes()
            reveal = read_json(reveal_path)
        except (OSError, ArtifactIntegrityError) as error:
            raise OosExposureError(
                f"{REASON_OOS_REVEALED_LEDGER_INVALID}: unreadable reveal {reference}"
            ) from error
        reveal_digest = digest_of_bytes(reveal_bytes)
        if reveal_digest != digests["reveal"]:
            raise OosExposureError(
                f"{REASON_OOS_REVEALED_LEDGER_INVALID}: reveal digest mismatch for {reference}"
            )
        lineage_id = reveal.get("lineage_id")
        reveal_freeze_id = reveal.get("freeze_id")
        start_text = reveal.get("requested_oos_start")
        end_text = reveal.get("requested_oos_end")
        if (
            not isinstance(lineage_id, str)
            or not lineage_id
            or not isinstance(reveal_freeze_id, str)
            or not reveal_freeze_id
            or not isinstance(start_text, str)
            or not start_text
            or not isinstance(end_text, str)
            or not end_text
        ):
            raise OosExposureError(
                f"{REASON_OOS_REVEALED_LEDGER_INVALID}: reveal {reference} "
                "is missing stable-window fields"
            )
        if (
            entry.get("lineage_id") != lineage_id
            or reveal_path.parent.name != reveal_freeze_id
        ):
            raise OosExposureError(
                f"{REASON_OOS_REVEALED_LEDGER_INVALID}: reveal/catalog "
                "lineage or freeze binding mismatch"
            )
        try:
            start = date.fromisoformat(start_text)
            end = date.fromisoformat(end_text)
        except ValueError as error:
            raise OosExposureError(
                f"{REASON_OOS_REVEALED_LEDGER_INVALID}: reveal {reference} has invalid OOS dates"
            ) from error
        if start > end:
            raise OosExposureError(
                f"{REASON_OOS_REVEALED_LEDGER_INVALID}: reveal {reference} has inverted OOS window"
            )
        windows.append(
            RevealedOosWindow(
                lineage_id=lineage_id,
                freeze_id=reveal_freeze_id,
                requested_oos_start=start,
                requested_oos_end=end,
                reveal_sequence=sequence,
                reveal_digest=reveal_digest,
                terminal_status=verdicts_by_freeze.get(reveal_freeze_id),
            )
        )
    return tuple(windows)


def reject_contaminated_oos_request(root: Path, freeze_payload: Mapping[str, object]) -> None:
    """Reject a new freeze whose stable lineage overlaps a revealed interval.

    A byte-identical existing freeze is a retry of the original commitment,
    not new research.  Any distinct freeze under the same lineage is compared
    by inclusive calendar interval, independent of intent/candidate labels.
    """
    freeze = verify_freeze_payload(freeze_payload)
    lineage_id = str(freeze["lineage_id"])
    freeze_id = str(freeze["freeze_id"])
    try:
        start = date.fromisoformat(str(freeze["requested_oos_start"]))
        end = date.fromisoformat(str(freeze["requested_oos_end"]))
    except ValueError as error:
        raise OosExposureError(
            f"{REASON_OOS_CONTAMINATED}: requested OOS window is invalid"
        ) from error
    for revealed in rebuild_revealed_oos_window_ledger(root):
        if revealed.lineage_id != lineage_id or revealed.freeze_id == freeze_id:
            continue
        if start <= revealed.requested_oos_end and revealed.requested_oos_start <= end:
            raise OosExposureError(
                f"{REASON_OOS_CONTAMINATED}: stable lineage {lineage_id!r} requested "
                f"{start.isoformat()}..{end.isoformat()} overlaps revealed freeze "
                f"{revealed.freeze_id!r} ({revealed.requested_oos_start.isoformat()}.."
                f"{revealed.requested_oos_end.isoformat()})"
            )


def record_result(
    freeze_directory: Path,
    payload: Mapping[str, object],
) -> tuple[Path, str]:
    """Persist the OOS run result artifact (create-new or identical
    confirm), before the one-shot verdict is recorded."""
    path = freeze_directory / RESULT_FILENAME
    try:
        digest = _write_immutable(path, payload)
    except ArtifactIntegrityError as error:
        raise OosExposureError(
            f"{REASON_OOS_ARTIFACT_CONFLICT}: the OOS result could not be "
            f"persisted: {error}"
        ) from error
    return path, digest


def record_verdict(
    freeze_directory: Path,
    payload: Mapping[str, object],
) -> tuple[Path, str]:
    """Persist the one verdict artifact, create-new."""
    path = freeze_directory / VERDICT_FILENAME
    try:
        write_new_json(path, payload)
    except ArtifactIntegrityError as error:
        raise OosExposureError(
            f"{REASON_OOS_ARTIFACT_CONFLICT}: the verdict could not be "
            f"persisted: {error}"
        ) from error
    return path, digest_of_bytes(canonical_json_bytes(payload))


def reveal_payload(
    freeze_payload: Mapping[str, object],
    *,
    warm_up_snapshot_digest: str | None,
) -> dict[str, object]:
    """The reveal-intent payload: persisted before any OOS data is opened.

    It records what is about to be revealed and for which frozen identity —
    never a snapshot digest, because the OOS snapshot has not been opened.
    No wall-clock input keeps a retry byte-identical.
    """
    return {
        "reveal_schema_version": REVEAL_SCHEMA_VERSION,
        "status": REVEAL_STATUS,
        "freeze_id": freeze_payload.get("freeze_id"),
        "freeze_digest": freeze_payload.get("freeze_digest"),
        "lineage_id": freeze_payload.get("lineage_id"),
        "intent_digest": freeze_payload.get("intent_digest"),
        "selected_variant_id": freeze_payload.get("selected_variant_id"),
        "requested_oos_start": freeze_payload.get("requested_oos_start"),
        "requested_oos_end": freeze_payload.get("requested_oos_end"),
        "warm_up_snapshot_digest": warm_up_snapshot_digest,
    }


def verdict_payload(
    freeze_payload: Mapping[str, object],
    *,
    verdict: str,
    gate_verdicts: tuple[Mapping[str, str], ...],
    result_digest: str,
) -> dict[str, object]:
    """The one-shot verdict artifact payload for a freeze."""
    return {
        "verdict_schema_version": VERDICT_SCHEMA_VERSION,
        "freeze_id": freeze_payload.get("freeze_id"),
        "freeze_digest": freeze_payload.get("freeze_digest"),
        "lineage_id": freeze_payload.get("lineage_id"),
        "verdict": verdict,
        "gate_verdicts": [dict(verdict) for verdict in gate_verdicts],
        "result_digest": result_digest,
    }


# --- OOS snapshot intake --------------------------------------------------------


@dataclass(frozen=True)
class OosSnapshotReceipt:
    """What the OOS intake verified about one materialized OOS snapshot."""

    snapshot_id: str
    snapshot_digest: str
    dataset_digest: str
    min_session: date
    max_session: date
    instrument_ids: tuple[InstrumentId, ...]
    quality_status: str | None
    universe: UniverseView
    universe_schedule_digest: str
    execution_policy: str | None = None
    execution_clock: str | None = None
    execution_evidence_digest: str | None = None


def validate_oos_snapshot(
    manifest: DataSnapshotManifest,
    dataset: CanonicalDataset,
    intent: CandidateIntent,
) -> OosSnapshotReceipt:
    """Validate one materialized OOS snapshot against the frozen intent.

    The OOS boundary mirrors the Basic one in the opposite direction: no row
    may exist at or before the Basic end (the Basic window stays closed),
    the bundle must reach exactly the OOS end, and bar instruments must stay
    inside the qualified asset-class authority and cover the intent
    universe, per instrument. Stock OOS intake needs data-derived schedule
    semantics M1 has not defined and refuses instead of inventing a universe
    digest.
    """
    if intent.asset_class.value == "STOCK":
        raise OosExposureError(
            f"{REASON_STOCK_OOS_UNSUPPORTED}: Stock OOS intake requires "
            "data-derived annual schedule semantics that M1 has not defined; "
            "refusing instead of inventing a universe digest"
        )
    if not dataset.daily_bars:
        raise OosExposureError(
            f"{REASON_OOS_EMPTY_SNAPSHOT}: the OOS snapshot contains no bars"
        )
    min_session = min(bar.session_date for bar in dataset.daily_bars)
    max_session = max(bar.session_date for bar in dataset.daily_bars)
    if min_session < intent.oos_start or min_session <= intent.basic_end:
        raise OosExposureError(
            f"{REASON_OOS_ROWS_BEFORE_OOS_START}: the OOS snapshot contains "
            f"rows from {min_session.isoformat()}, before the OOS start "
            f"{intent.oos_start.isoformat()}; the Basic window ending "
            f"{intent.basic_end.isoformat()} stays closed to the OOS runner"
        )
    if max_session > intent.oos_end:
        raise OosExposureError(
            f"{REASON_OOS_END_EXCEEDED}: the OOS snapshot reaches "
            f"{max_session.isoformat()}, beyond the declared OOS end "
            f"{intent.oos_end.isoformat()}"
        )
    if max_session < intent.oos_end:
        raise OosExposureError(
            f"{REASON_OOS_END_UNCOVERED}: the OOS snapshot ends at "
            f"{max_session.isoformat()}, before the declared OOS end "
            f"{intent.oos_end.isoformat()}"
        )
    bar_instruments = {bar.instrument_id for bar in dataset.daily_bars}
    approved = {InstrumentId.parse(item) for item in M1_APPROVED_ETF_SYMBOLS}
    outside_asset_class = bar_instruments - approved
    if outside_asset_class:
        raise OosExposureError(
            f"{REASON_OOS_INSTRUMENT_OUTSIDE_ASSET_CLASS}: OOS snapshot "
            "instruments outside the qualified asset-class authority: "
            + ", ".join(str(item) for item in sorted(outside_asset_class))
        )
    universe_ids = tuple(intent.universe_policy.instrument_ids)
    uncovered = sorted(set(universe_ids) - bar_instruments)
    if uncovered:
        raise OosExposureError(
            f"{REASON_OOS_INSTRUMENT_UNCOVERED}: universe instruments without "
            "OOS bars: " + ", ".join(str(item) for item in uncovered)
        )
    last_session_by_instrument: dict[InstrumentId, date] = {}
    for bar in dataset.daily_bars:
        current = last_session_by_instrument.get(bar.instrument_id)
        if current is None or bar.session_date > current:
            last_session_by_instrument[bar.instrument_id] = bar.session_date
    truncated = sorted(
        instrument_id
        for instrument_id in universe_ids
        if last_session_by_instrument.get(instrument_id) != intent.oos_end
    )
    if truncated:
        raise OosExposureError(
            f"{REASON_OOS_INSTRUMENT_ENDS_EARLY}: universe instruments whose "
            f"own bars end before the OOS end "
            f"{intent.oos_end.isoformat()}: "
            + ", ".join(
                f"{instrument_id}@{last_session_by_instrument.get(instrument_id)}"
                for instrument_id in truncated
            )
        )
    quality = manifest.quality_status
    if quality != "PASS":
        raise OosExposureError(
            f"{REASON_OOS_SNAPSHOT_QUALITY_NOT_PASS}: OOS snapshot quality "
            f"status is {quality!r}"
        )
    snapshot_id = manifest.snapshot_id
    if snapshot_id is None:
        raise OosExposureError(
            f"{REASON_OOS_INVALID_SNAPSHOT}: the OOS snapshot manifest has "
            "no computed snapshot id"
        )
    universe = UniverseView(universe_ids)
    return OosSnapshotReceipt(
        snapshot_id=snapshot_id,
        snapshot_digest="sha256:" + snapshot_id,
        dataset_digest=dataset.content_digest(),
        min_session=min_session,
        max_session=max_session,
        instrument_ids=tuple(sorted(bar_instruments)),
        quality_status=quality,
        universe=universe,
        universe_schedule_digest=universe_view_digest(universe.instrument_ids),
        execution_policy=manifest.execution_policy,
        execution_clock=manifest.execution_clock,
        execution_evidence_digest=manifest.execution_evidence_digest,
    )


# --- OOS wiring and run ----------------------------------------------------------


@dataclass(frozen=True)
class OosWiring:
    """One frozen OOS run wiring: snapshot facts plus kernel and account
    inputs, derived deterministically from the verified OOS snapshot (and the
    digest-bound warm-up snapshot, when composed). Nothing observes
    wall-clock time."""

    calendar: MarketCalendar
    master: InstrumentMaster
    account_fees: AccountFeeConfig
    execution_model: ExecutionModel
    clock: EngineClock
    bars: tuple[DailyBar, ...]
    tradability: tuple[TradabilityStatus, ...]
    corporate_actions: tuple[CorporateAction, ...]
    initial_cash: Money
    run_start: date
    oos_start: date
    oos_end: date
    decision_sessions: tuple[date, ...]
    universe: UniverseView
    snapshot_digest: str
    warm_up_snapshot_digest: str | None
    benchmark_spec: BenchmarkSpec
    benchmark_inception_session: date
    code_commit: str
    dependency_digest: str
    kernel_profile: KernelReplayProfile = current_kernel_replay_profile
    historical_opening_evidence: tuple[HistoricalOpeningEvidence, ...] = ()
    execution_eligibility_mode: ExecutionEligibilityMode = ExecutionEligibilityMode.LEGACY


def _merged_oos_dataset(
    intent: CandidateIntent,
    dataset: CanonicalDataset,
    warm_up_dataset: CanonicalDataset | None,
) -> CanonicalDataset:
    """Compose the OOS snapshot with the digest-bound warm-up snapshot.

    The warm-up snapshot may only contain rows at or before the Basic end;
    anything later would smuggle OOS data in through the warm-up door.
    Calendar identity must agree across the two snapshots; a disagreement is
    a typed failure, never a silent merge.
    """
    if not dataset.sessions:
        raise OosExposureError(
            f"{REASON_OOS_EMPTY_SNAPSHOT}: the OOS snapshot carries no "
            "calendar sessions"
        )
    if warm_up_dataset is None:
        return dataset
    if not warm_up_dataset.sessions:
        raise OosExposureError(
            f"{REASON_OOS_WARMUP_CONFLICT}: the warm-up snapshot carries no "
            "calendar sessions"
        )
    warm_up_last_session = max(
        session.session_date for session in warm_up_dataset.sessions
    )
    if warm_up_last_session > intent.basic_end:
        raise OosExposureError(
            f"{REASON_OOS_WARMUP_AFTER_BASIC_END}: the warm-up snapshot "
            f"reaches {warm_up_last_session.isoformat()}, past the Basic end "
            f"{intent.basic_end.isoformat()}; warm-up data may never extend "
            "into the OOS window"
        )
    if not warm_up_dataset.daily_bars:
        raise OosExposureError(
            f"{REASON_OOS_WARMUP_CONFLICT}: the warm-up snapshot carries no "
            "daily bars; it can never prime strategy history"
        )
    warm_up_last_bar = max(bar.session_date for bar in warm_up_dataset.daily_bars)
    if warm_up_last_bar > intent.basic_end:
        raise OosExposureError(
            f"{REASON_OOS_WARMUP_AFTER_BASIC_END}: the warm-up snapshot "
            f"contains rows from {warm_up_last_bar.isoformat()}, past the "
            f"Basic end {intent.basic_end.isoformat()}; warm-up data may "
            "never reach into the OOS window"
        )
    oos_calendar = dataset.sessions[0]
    warm_up_calendar = warm_up_dataset.sessions[0]
    if oos_calendar.calendar_id != warm_up_calendar.calendar_id:
        raise OosExposureError(
            f"{REASON_OOS_WARMUP_CONFLICT}: the OOS snapshot calendar "
            f"{oos_calendar.calendar_id!r} differs from the warm-up snapshot "
            f"calendar {warm_up_calendar.calendar_id!r}"
        )
    if oos_calendar.snapshot_version != warm_up_calendar.snapshot_version:
        raise OosExposureError(
            f"{REASON_OOS_WARMUP_CONFLICT}: the OOS snapshot calendar "
            f"version {oos_calendar.snapshot_version!r} differs from the "
            f"warm-up snapshot version {warm_up_calendar.snapshot_version!r}"
        )
    return CanonicalDataset(
        daily_bars=(*warm_up_dataset.daily_bars, *dataset.daily_bars),
        sessions=(*warm_up_dataset.sessions, *dataset.sessions),
        tradability=(*warm_up_dataset.tradability, *dataset.tradability),
        corporate_actions=(*warm_up_dataset.corporate_actions, *dataset.corporate_actions),
        rule_candidates=(),
        historical_opening_evidence=(
            *warm_up_dataset.historical_opening_evidence,
            *dataset.historical_opening_evidence,
        ),
    )


def _account_fee_config(intent: CandidateIntent) -> AccountFeeConfig:
    return AccountFeeConfig(
        config_id=f"OOS-RUN-{intent.intent_id}",
        config_version="1",
        broker_profiles=(
            BrokerFeeProfile(
                profile_id="ACCT:RESEARCH-MAIN",
                version="1",
                commission_rate=Decimal(intent.cost_convention["commission_rate"]),
                minimum_commission=Decimal(intent.cost_convention["minimum_commission"]),
                agreement_reference=intent.intent_id,
                effective_from=intent.warm_up_start,
                effective_to=None,
            ),
        ),
    )


def build_oos_wiring(
    dataset: CanonicalDataset,
    intent: CandidateIntent,
    receipt: OosSnapshotReceipt,
    *,
    master: InstrumentMaster,
    warm_up_dataset: CanonicalDataset | None = None,
    warm_up_snapshot_digest: str | None = None,
    kernel_profile: KernelReplayProfile = current_kernel_replay_profile,
    execution_eligibility_mode: ExecutionEligibilityMode = ExecutionEligibilityMode.LEGACY,
) -> OosWiring:
    """Freeze the full OOS run wiring from the verified snapshot and intent.

    Decisions happen only on the OOS window's month-end sessions; the
    composed warm-up data exists to prime strategy history, never to trade
    or to enter the metrics window. ``warm_up_snapshot_digest`` is the
    digest-bound identity of the composed warm-up snapshot (``None`` when
    the run is OOS-only).
    """
    if intent.asset_class.value == "STOCK":
        raise OosExposureError(
            f"{REASON_STOCK_OOS_UNSUPPORTED}: Stock OOS runs are not "
            "supported by the M1 OOS boundary"
        )
    if execution_eligibility_mode is ExecutionEligibilityMode.HISTORICAL_OPENING_R21:
        if (
            not dataset.historical_opening_evidence
            or receipt.execution_policy != OPENING_POLICY
            or receipt.execution_clock != OPENING_CLOCK_ID
            or receipt.execution_evidence_digest
            != opening_evidence_digest(dataset.historical_opening_evidence)
            or receipt.dataset_digest != dataset.content_digest()
        ):
            raise OosExposureError(
                "historical opening wiring requires verified snapshot policy/clock/evidence identity"
            )
    merged = _merged_oos_dataset(intent, dataset, warm_up_dataset)
    if not merged.sessions:
        raise OosExposureError(
            f"{REASON_OOS_EMPTY_SNAPSHOT}: the OOS snapshot carries no "
            "calendar sessions"
        )
    calendar_id = merged.sessions[0].calendar_id
    snapshot_versions = {session.snapshot_version for session in merged.sessions}
    if len(snapshot_versions) != 1:
        raise OosExposureError(
            f"{REASON_OOS_WARMUP_CONFLICT}: snapshot sessions span multiple "
            f"calendar versions: {sorted(snapshot_versions)}"
        )
    open_sessions = tuple(
        session
        for session in sorted(merged.sessions, key=lambda item: item.session_date)
        if session.is_open
    )
    oos_open_sessions = tuple(
        session
        for session in open_sessions
        if intent.oos_start <= session.session_date <= intent.oos_end
    )
    if not oos_open_sessions:
        raise OosExposureError(
            f"{REASON_OOS_EMPTY_SNAPSHOT}: no open calendar sessions inside "
            "the OOS window"
        )
    decision_sessions = month_end_sessions(
        tuple(session.session_date for session in oos_open_sessions)
    )
    if not decision_sessions:
        raise OosExposureError(
            f"{REASON_OOS_NO_DECISION_SESSIONS}: the OOS window has no "
            "month-end decision sessions"
        )
    benchmark_spec = BenchmarkSpec(
        benchmark_schema_version=BENCHMARK_SCHEMA_VERSION,
        kind=intent.benchmark.kind.value,
        instrument_ids=tuple(intent.benchmark.instrument_ids),
        rebalance=BENCHMARK_REBALANCE_INCEPTION,
    )
    run_start = (
        intent.warm_up_start if warm_up_dataset is not None else intent.oos_start
    )
    return OosWiring(
        calendar=MarketCalendar(
            calendar_id=calendar_id,
            snapshot_version=next(iter(snapshot_versions)),
            sessions=open_sessions,
        ),
        master=master,
        account_fees=_account_fee_config(intent),
        execution_model=_intent_execution_model(intent),
        clock=EngineClock.shanghai()
        if execution_eligibility_mode is ExecutionEligibilityMode.HISTORICAL_OPENING_R21
        else EngineClock(),
        historical_opening_evidence=merged.historical_opening_evidence,
        execution_eligibility_mode=execution_eligibility_mode,
        bars=tuple(merged.daily_bars),
        tradability=tuple(merged.tradability),
        corporate_actions=tuple(merged.corporate_actions),
        initial_cash=Money(intent.initial_capital),
        run_start=run_start,
        oos_start=intent.oos_start,
        oos_end=intent.oos_end,
        decision_sessions=decision_sessions,
        universe=receipt.universe,
        snapshot_digest=receipt.snapshot_digest,
        warm_up_snapshot_digest=warm_up_snapshot_digest,
        benchmark_spec=benchmark_spec,
        benchmark_inception_session=oos_open_sessions[0].session_date,
        code_commit=resolve_code_commit(),
        dependency_digest=DEPENDENCY_DIGEST,
        kernel_profile=kernel_profile,
    )


def oos_benchmark_total_return(wiring: OosWiring) -> Decimal:
    """The same-kernel benchmark return over the OOS metrics window."""
    if (
        wiring.benchmark_spec.kind
        == BenchmarkKind.STOCK_ANNUAL_SCHEDULE_EQUAL_WEIGHT.value
    ):
        raise OosExposureError(
            f"{REASON_STOCK_OOS_UNSUPPORTED}: the annual same-schedule "
            "benchmark belongs to Stock candidates, whose OOS runs are not "
            "supported"
        )
    source = BenchmarkTargetSource(
        wiring.benchmark_spec, wiring.benchmark_inception_session
    )
    engine = DailyBarEngine(
        calendar=wiring.calendar,
        clock=wiring.clock,
        master=wiring.master,
        account_fees=wiring.account_fees,
        execution_model=wiring.execution_model,
        accounting_semantics=wiring.kernel_profile.accounting_semantics,
        bars=wiring.bars,
        tradability=wiring.tradability,
        historical_opening_evidence=wiring.historical_opening_evidence,
        execution_eligibility_mode=wiring.execution_eligibility_mode,
        corporate_actions=wiring.corporate_actions,
        target_source=source,
        initial_cash=wiring.initial_cash,
    )
    result = engine.run(start_session=wiring.run_start, end_session=wiring.oos_end)
    nav_points = tuple(
        record.nav
        for record in result.sessions
        if record.session_date >= wiring.oos_start
    )
    report = compute_metrics(nav_points, cash_entries=result.cash_entries)
    return report.total_return


@dataclass(frozen=True)
class OosRunOutcome:
    """One retained OOS attempt with its content-derived artifacts."""

    variant_id: str
    verdict: str
    gate_verdicts: tuple[Mapping[str, str], ...]
    manifest_payload: Mapping[str, object]
    result_payload: Mapping[str, object]
    result_digest: str
    metrics: Mapping[str, object]


def _metrics_summary_payload(
    nav_points: Sequence[NavPoint],
    cash_entries: Sequence[CashLedgerEntry],
) -> dict[str, object]:
    report = compute_metrics(nav_points, cash_entries=cash_entries)
    return {
        "observation_count": report.observation_count,
        "first_session": report.first_session.isoformat(),
        "last_session": report.last_session.isoformat(),
        "total_return": str(report.total_return),
        "cagr": str(report.cagr),
        "max_drawdown": str(report.max_drawdown),
        "turnover": str(report.turnover),
        "stale_observation_count": report.stale_observation_count,
        "cost_drag": str(report.cost_drag.drag),
        "total_costs": str(report.cost_drag.total_costs.amount),
    }


def build_oos_run_manifest(
    intent: CandidateIntent,
    *,
    selected_variant_id: str,
    strategy_version: str,
    strategy_identity_digest: str,
    implementation_digest: str,
    parameters_digest: str,
    actual_snapshot_digest: str,
    actual_universe_schedule_digest: str,
    kernel_identity_digest: str,
    code_commit: str,
) -> ResearchRunManifest:
    """Bind the OOS run-time identity.

    The snapshot and universe schedule digests are the ACTUAL digests of the
    mounted OOS snapshot — computed from its content after materialization,
    never the freeze's expectations.
    """
    return ResearchRunManifest(
        manifest_schema_version=RUN_MANIFEST_SCHEMA_VERSION,
        lineage_id=intent.lineage_id,
        intent_digest=intent.intent_digest,
        strategy_id=intent.strategy_id,
        strategy_version=strategy_version,
        strategy_identity_digest=strategy_identity_digest,
        implementation_digest=implementation_digest,
        parameters_digest=parameters_digest,
        code_commit=code_commit,
        dependency_digest=DEPENDENCY_DIGEST,
        split_digest=split_digest_of(
            intent.warm_up_start,
            intent.basic_start,
            intent.basic_end,
            intent.oos_start,
            intent.oos_end,
        ),
        snapshot_digest=actual_snapshot_digest,
        universe_schedule_digest=actual_universe_schedule_digest,
        benchmark_spec_digest=intent.benchmark.digest(),
        cost_spec_digest=cost_spec_digest(intent),
        metric_convention_digest=MetricConventions().digest(),
        kernel_identity_digest=kernel_identity_digest,
        output_scope=OOS_OUTPUT_SCOPE,
        random_seed=0,
    )


def run_oos_variant(
    wiring: OosWiring,
    intent: CandidateIntent,
    variant_id: str,
    variant_parameters: Mapping[str, str],
    benchmark_total_return: Decimal,
) -> OosRunOutcome:
    """Run the selected variant over the OOS window and gate the outcome.

    The kernel runs warm-up (when composed) plus OOS; metrics are computed
    strictly from NAV observations inside the OOS window. Any OOS-window
    decision session that must return ``INSUFFICIENT_HISTORY`` fails the
    evaluation closed — a dead decision period would bias the verdict, and
    a wrong one-shot verdict can never be recorded twice.
    """
    try:
        strategy = build_canonical_strategy(
            intent, variant_parameters, wiring.decision_sessions
        )
        adapter = StrategyTargetSource(strategy, wiring.universe)
        engine = DailyBarEngine(
            calendar=wiring.calendar,
            clock=wiring.clock,
            master=wiring.master,
            account_fees=wiring.account_fees,
            execution_model=wiring.execution_model,
            accounting_semantics=wiring.kernel_profile.accounting_semantics,
            bars=wiring.bars,
            tradability=wiring.tradability,
            historical_opening_evidence=wiring.historical_opening_evidence,
            execution_eligibility_mode=wiring.execution_eligibility_mode,
            corporate_actions=wiring.corporate_actions,
            target_source=adapter,
            initial_cash=wiring.initial_cash,
        )
        result = engine.run(start_session=wiring.run_start, end_session=wiring.oos_end)
    except (AmbiguousMarketFactError, UnknownFactError) as error:
        raise OosExposureError(
            f"{REASON_OOS_RUN_FAILED_DATA}: {type(error).__name__}: {error}"
        ) from error
    except Exception as error:
        raise OosExposureError(
            f"{REASON_OOS_RUN_FAILED_KERNEL}: {type(error).__name__}: {error}"
        ) from error

    decision_session_set = set(wiring.decision_sessions)
    decision_evaluations = [
        record
        for record in adapter.evaluations
        if record.session_date in decision_session_set
    ]
    insufficient = [
        record
        for record in decision_evaluations
        if REASON_INSUFFICIENT_HISTORY in record.evaluation.reason_codes
    ]
    if insufficient:
        first = insufficient[0]
        raise OosExposureError(
            f"{REASON_OOS_HISTORY_INSUFFICIENT}: the OOS snapshot cannot "
            f"support the strategy's lookback at {first.session_date.isoformat()}; "
            "a dead decision period would bias the one-shot verdict"
        )
    if not decision_evaluations:
        raise OosExposureError(
            f"{REASON_OOS_NO_DECISION_SESSIONS}: the OOS window produced no "
            "strategy decision; a verdict without decisions is meaningless"
        )
    nav_points = tuple(
        record.nav
        for record in result.sessions
        if record.session_date >= wiring.oos_start
    )
    cash_entries = tuple(
        entry
        for entry in result.cash_entries
        if entry.session_date >= wiring.oos_start
    )
    metrics = _metrics_summary_payload(nav_points, cash_entries)
    metrics["trade_count"] = len(result.fills)
    metrics["rejection_count"] = len(result.rejections)

    gate_verdicts, verdict = evaluate_oos_gate(
        intent.oos_survivor_rule, metrics, benchmark_total_return
    )
    identity = strategy.identity
    manifest = build_oos_run_manifest(
        intent,
        selected_variant_id=variant_id,
        strategy_version=identity.strategy_version,
        strategy_identity_digest=identity.content_digest(),
        implementation_digest=identity.implementation_digest,
        parameters_digest=identity.parameters_digest,
        actual_snapshot_digest=wiring.snapshot_digest,
        actual_universe_schedule_digest=universe_view_digest(wiring.universe.instrument_ids),
        kernel_identity_digest=kernel_identity_digest(
            wiring.execution_model,
            profile=wiring.kernel_profile,
            execution_eligibility_mode=wiring.execution_eligibility_mode,
        ),
        code_commit=wiring.code_commit,
    )
    result_payload: dict[str, object] = {
        "result_schema_version": OOS_RESULT_SCHEMA_VERSION,
        "lineage_id": intent.lineage_id,
        "intent_id": intent.intent_id,
        "intent_digest": intent.intent_digest,
        "variant_id": variant_id,
        "variant_parameters": dict(variant_parameters),
        "verdict": verdict,
        "gate_verdicts": [dict(item) for item in gate_verdicts],
        "window": {
            "oos_start": intent.oos_start.isoformat(),
            "oos_end": intent.oos_end.isoformat(),
        },
        "snapshot_digest": manifest.snapshot_digest,
        "universe_schedule_digest": manifest.universe_schedule_digest,
        "benchmark_spec_digest": manifest.benchmark_spec_digest,
        "benchmark_total_return": str(benchmark_total_return),
        "cost_spec_digest": manifest.cost_spec_digest,
        "kernel_identity_digest": manifest.kernel_identity_digest,
        "code_commit": wiring.code_commit,
        "dependency_digest": wiring.dependency_digest,
        "warm_up_snapshot_digest": wiring.warm_up_snapshot_digest,
        "manifest": manifest.to_payload(),
        "metrics": dict(metrics),
    }
    result_digest = digest_of_bytes(canonical_json_bytes(result_payload))
    return OosRunOutcome(
        variant_id=variant_id,
        verdict=verdict,
        gate_verdicts=gate_verdicts,
        manifest_payload=manifest.to_payload(),
        result_payload=result_payload,
        result_digest=result_digest,
        metrics=metrics,
    )


# --- survivor gate ----------------------------------------------------------------


GATE_MIN_EXCESS_TOTAL_RETURN: str = "MIN_EXCESS_TOTAL_RETURN"
GATE_MAX_DRAWDOWN_FLOOR: str = "MAX_DRAWDOWN_FLOOR"
GATE_VERDICT_PASS: str = "PASS"
GATE_VERDICT_FAIL: str = "FAIL"


def _gate_verdict(
    criterion: str,
    observed: Decimal,
    threshold: Decimal,
    passed: bool,
    comparator: str,
) -> dict[str, str]:
    return {
        "criterion": criterion,
        "observed": str(observed),
        "comparator": comparator,
        "threshold": str(threshold),
        "verdict": GATE_VERDICT_PASS if passed else GATE_VERDICT_FAIL,
    }


def evaluate_oos_gate(
    survivor_rule: Mapping[str, str],
    metrics: Mapping[str, object],
    benchmark_total_return: Decimal,
) -> tuple[tuple[Mapping[str, str], ...], str]:
    """Apply the pre-registered ``oos_survivor_rule`` to one OOS run.

    Supported criteria are ``min_excess_total_return_vs_benchmark`` and
    ``max_drawdown_floor``; anything else fails closed instead of being
    silently ignored. Every criterion must pass for ``SURVIVOR``.
    """
    if not survivor_rule:
        raise OosError(
            f"{REASON_OOS_SURVIVOR_RULE_INVALID}: the oos_survivor_rule is "
            "empty; an empty gate can never decide a verdict"
        )
    verdicts: list[Mapping[str, str]] = []
    for key in sorted(survivor_rule):
        threshold_text = survivor_rule[key]
        try:
            threshold = Decimal(threshold_text)
        except Exception as error:
            raise OosError(
                f"{REASON_OOS_SURVIVOR_RULE_INVALID}: survivor rule {key!r} "
                f"must be a Decimal string, got {threshold_text!r}"
            ) from error
        if key == "min_excess_total_return_vs_benchmark":
            excess = Decimal(str(metrics["total_return"])) - benchmark_total_return
            verdicts.append(
                _gate_verdict(
                    GATE_MIN_EXCESS_TOTAL_RETURN,
                    excess,
                    threshold,
                    excess >= threshold,
                    ">=",
                )
            )
        elif key == "max_drawdown_floor":
            drawdown = Decimal(str(metrics["max_drawdown"]))
            verdicts.append(
                _gate_verdict(
                    GATE_MAX_DRAWDOWN_FLOOR,
                    drawdown,
                    threshold,
                    drawdown >= threshold,
                    ">=",
                )
            )
        else:
            raise OosError(
                f"{REASON_OOS_SURVIVOR_RULE_INVALID}: survivor rule "
                f"{key!r} is not a recognized criterion; unrecognized gates "
                "fail closed"
            )
    verdict_tuple = tuple(verdicts)
    status = (
        OOS_VERDICT_SURVIVOR
        if all(verdict["verdict"] == GATE_VERDICT_PASS for verdict in verdict_tuple)
        else OOS_VERDICT_REJECTED_OOS
    )
    return verdict_tuple, status
