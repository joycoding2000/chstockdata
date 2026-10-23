"""Typed strategy contract and candidate lifecycle: identity, evaluation
result, pre-code CandidateIntent, run-time ResearchRunManifest, and digest
helpers.

A Research strategy is a thin, deterministic adapter target: it turns the
T-known ``DecisionContext`` and the current ``UniverseView`` into either
explicit target contributions or a typed no-decision with reason codes. It
never executes, sizes, fees, settles, downloads data, or touches a clock;
those remain M0 kernel responsibilities.

A typed ``NO_DECISION`` is not a strategy judgment: it must carry reason
codes (for example ``INSUFFICIENT_HISTORY``) and never degenerates into an
ambiguous ``None``. Invalid or future access stays a loud run failure.

The lifecycle is split in two: a ``CandidateIntent`` is frozen before any
implementation exists and must never contain implementation, code-commit, or
snapshot digests; a ``ResearchRunManifest`` binds exactly those runtime
identities immediately before a run and fails closed when any required
digest is missing. Any manifest mutation produces a new run identity.
"""

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from hashlib import sha256
from types import MappingProxyType
from typing import Protocol

from systematic_investing.backtest.engine import DecisionContext
from systematic_investing.domain.identifiers import InstrumentId, SleeveId
from systematic_investing.domain.portfolio import TargetContribution
from systematic_investing.research.universe import UniverseView

REASON_INSUFFICIENT_HISTORY: str = "INSUFFICIENT_HISTORY"
REASON_NOT_DECISION_SESSION: str = "NOT_DECISION_SESSION"

INTENT_SCHEMA_VERSION: str = "research-candidate-intent-1"
RUN_MANIFEST_SCHEMA_VERSION: str = "research-run-manifest-1"

PARAMETER_SELECTION_RULE: str = "PRIORITY_FIRST_BASIC_PASS"
BENCHMARK_REBALANCE_INCEPTION: str = "INCEPTION"
BENCHMARK_REBALANCE_ANNUAL: str = "ANNUAL"
DECISION_FREQUENCY_MONTHLY_LAST_SESSION: str = "MONTHLY_LAST_SESSION"

CASH_0_LABEL: str = "CASH_0"
REASON_DIVIDEND_TAX_NOT_MODELED: str = "DIVIDEND_TAX_NOT_MODELED"

# M1-D01: the M1 first-batch ETF universe is the M0-qualified representative
# set. Candidate universes may only use subsets of these instruments.
M1_APPROVED_ETF_SYMBOLS: tuple[str, ...] = (
    "XSHG:510300",
    "XSHE:159915",
    "XSHG:518880",
    "XSHG:511010",
)

# M1 architecture 6.3: the Stock universe is data-derived (annual PIT
# reconstitution), so a Stock intent declares the frozen policy by name and
# an explicitly empty instrument list instead of a pre-known membership.
STOCK_ANNUAL_POLICY_NAME: str = "STOCK_ANNUAL_PIT_TOP50_V1"


class StrategyContractError(Exception):
    """Base class for strategy contract errors."""


class InvalidStrategyIdentityError(StrategyContractError):
    """Raised when a strategy identity violates its contract."""


class InvalidStrategyEvaluationError(StrategyContractError):
    """Raised when a strategy evaluation violates its contract."""


def implementation_digest_of(files: Sequence[tuple[str, bytes]]) -> str:
    """Normalized sha256 over ``(relative_path, content)`` implementation files.

    The digest changes whenever any implementing file changes. Callers own the
    relative-path strings and real bytes; the digest never depends on their
    input order.
    """
    lines = ["implementation_v1"]
    for relative_path, content in sorted(files, key=lambda item: item[0]):
        if not isinstance(relative_path, str) or not relative_path:
            raise InvalidStrategyIdentityError(
                "implementation relative paths must be non-empty strings"
            )
        if not isinstance(content, bytes):
            raise InvalidStrategyIdentityError("implementation content must be bytes")
        lines.append(relative_path)
        lines.append(sha256(content).hexdigest())
    return "sha256:" + sha256("\n".join(lines).encode("utf-8")).hexdigest()


def canonical_parameters_digest(parameters: Mapping[str, str]) -> str:
    """Canonical JSON digest over sorted string parameters."""
    canonical = json.dumps(
        {key: parameters[key] for key in sorted(parameters)},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return "sha256:" + sha256(canonical.encode("utf-8")).hexdigest()


def _require_sha256_digest(value: object, field_name: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 71
        or not value.startswith("sha256:")
        or not all(character in "0123456789abcdef" for character in value[7:])
    ):
        raise InvalidStrategyIdentityError(
            f"{field_name} must be a sha256:<64 hex> digest, got {value!r}"
        )


@dataclass(frozen=True)
class StrategyIdentity:
    """Immutable strategy identity: semantics, implementation bytes, and
    parameters. Changing rules, parameters, or universe semantics produces a
    new identity rather than rewriting history."""

    strategy_id: str
    strategy_version: str
    implementation_digest: str
    parameters: Mapping[str, str]
    parameters_digest: str
    sleeve: SleeveId
    required_history_sessions: int
    decision_frequency: str

    def __post_init__(self) -> None:
        for name in ("strategy_id", "strategy_version", "decision_frequency"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value:
                raise InvalidStrategyIdentityError(f"{name} must be a non-empty string")
        _require_sha256_digest(self.implementation_digest, "implementation_digest")
        _require_sha256_digest(self.parameters_digest, "parameters_digest")
        if not isinstance(self.parameters, Mapping) or not all(
            isinstance(key, str) and key and isinstance(value, str) and value
            for key, value in self.parameters.items()
        ):
            raise InvalidStrategyIdentityError(
                "parameters must map non-empty string keys to non-empty string values"
            )
        if self.parameters_digest != canonical_parameters_digest(self.parameters):
            raise InvalidStrategyIdentityError(
                "parameters_digest must equal the canonical parameters digest"
            )
        if not isinstance(self.sleeve, SleeveId):
            raise InvalidStrategyIdentityError(f"sleeve must be a SleeveId, got {self.sleeve!r}")
        if (
            not isinstance(self.required_history_sessions, int)
            or isinstance(self.required_history_sessions, bool)
            or self.required_history_sessions < 1
        ):
            raise InvalidStrategyIdentityError(
                "required_history_sessions must be a positive integer"
            )
        # Freeze parameters into a private read-only copy: later mutation of
        # the caller's mapping can never desynchronize identity content from
        # its digest.
        object.__setattr__(self, "parameters", MappingProxyType(dict(self.parameters)))

    def content_digest(self) -> str:
        """Content-derived identity digest; parameters are covered by
        ``parameters_digest`` and implementation bytes by
        ``implementation_digest``."""
        lines = [
            "strategy_identity_v1",
            f"strategy_id={self.strategy_id}",
            f"strategy_version={self.strategy_version}",
            f"implementation_digest={self.implementation_digest}",
            f"parameters_digest={self.parameters_digest}",
            f"sleeve={self.sleeve.value}",
            f"required_history_sessions={self.required_history_sessions}",
            f"decision_frequency={self.decision_frequency}",
        ]
        return "sha256:" + sha256("\n".join(lines).encode("utf-8")).hexdigest()


class StrategyEvaluationStatus(StrEnum):
    """Outcome kinds of one strategy evaluation.

    ``TARGETS`` means the strategy addressed explicit target weights (zero is
    an addressed exit/cash target). ``NO_DECISION`` means the strategy could
    not decide and must say why; it is never interchangeable with an explicit
    cash target.
    """

    TARGETS = "TARGETS"
    NO_DECISION = "NO_DECISION"


@dataclass(frozen=True)
class StrategyEvaluation:
    """Thin typed result of one strategy evaluation.

    ``TARGETS`` carries at least one contribution. ``NO_DECISION`` carries no
    contributions and at least one reason code. Invalid input or future-data
    access never becomes a ``NO_DECISION``; it raises at the access site.
    """

    status: StrategyEvaluationStatus
    contributions: tuple[TargetContribution, ...] = ()
    reason_codes: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.status, StrategyEvaluationStatus):
            raise InvalidStrategyEvaluationError(
                f"status must be a StrategyEvaluationStatus, got {self.status!r}"
            )
        if not isinstance(self.contributions, tuple) or not all(
            isinstance(item, TargetContribution) for item in self.contributions
        ):
            raise InvalidStrategyEvaluationError(
                "contributions must be a tuple of TargetContribution"
            )
        for field_name in ("reason_codes", "evidence_ids"):
            value = getattr(self, field_name)
            if not isinstance(value, tuple) or not all(
                isinstance(item, str) and item for item in value
            ):
                raise InvalidStrategyEvaluationError(
                    f"{field_name} must be a tuple of non-empty strings"
                )
        if self.status is StrategyEvaluationStatus.NO_DECISION:
            if self.contributions:
                raise InvalidStrategyEvaluationError(
                    "NO_DECISION must not carry contributions"
                )
            if not self.reason_codes:
                raise InvalidStrategyEvaluationError(
                    "NO_DECISION requires at least one reason code"
                )
        else:
            if not self.contributions:
                raise InvalidStrategyEvaluationError(
                    "TARGETS requires at least one explicit contribution"
                )


class StrategyContract(Protocol):
    """The thin Research strategy interface.

    Strategies observe only the decision-context slice and the current
    universe view; they never touch provider, filesystem, network, wall
    clock, or execution/accounting internals.
    """

    @property
    def identity(self) -> StrategyIdentity: ...

    def evaluate(
        self, context: DecisionContext, universe: UniverseView
    ) -> StrategyEvaluation: ...


# --- candidate lifecycle -----------------------------------------------------


class ResearchLifecycleError(Exception):
    """Base class for CandidateIntent / ResearchRunManifest contract errors."""


class InvalidCandidateIntentError(ResearchLifecycleError):
    """Raised when a pre-code candidate intent violates its contract."""


class InvalidResearchRunManifestError(ResearchLifecycleError):
    """Raised when a run-time manifest is missing a required digest or binds
    an inconsistent identity."""


def canonical_payload_digest(payload: Mapping[str, object]) -> str:
    """Canonical JSON digest of a raw payload; input ordering never matters."""
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )
    return "sha256:" + sha256(canonical.encode("utf-8")).hexdigest()


def split_digest_of(
    warm_up_start: date,
    basic_start: date,
    basic_end: date,
    oos_start: date,
    oos_end: date,
) -> str:
    """Content digest of the pre-registered split windows."""
    lines = [
        "research_split_v1",
        f"warm_up_start={warm_up_start.isoformat()}",
        f"basic_start={basic_start.isoformat()}",
        f"basic_end={basic_end.isoformat()}",
        f"oos_start={oos_start.isoformat()}",
        f"oos_end={oos_end.isoformat()}",
    ]
    return "sha256:" + sha256("\n".join(lines).encode("utf-8")).hexdigest()


def universe_view_digest(instrument_ids: tuple[InstrumentId, ...]) -> str:
    """Content digest of a frozen universe instrument set."""
    lines = ["research_universe_view_v1"]
    lines.extend(str(item) for item in sorted(instrument_ids))
    return "sha256:" + sha256("\n".join(lines).encode("utf-8")).hexdigest()


class ResearchAssetClass(StrEnum):
    """Asset classes admitted in M1 research."""

    ETF = "ETF"
    STOCK = "STOCK"


class BenchmarkKind(StrEnum):
    """Candidate-local benchmark kinds decided by M1-D03. Stock candidates
    use the same-schedule annual equal-weight benchmark; ETF candidates use
    the fixed-universe kinds."""

    SINGLE_ETF_BUY_AND_HOLD = "SINGLE_ETF_BUY_AND_HOLD"
    ETF_UNIVERSE_EQUAL_WEIGHT = "ETF_UNIVERSE_EQUAL_WEIGHT"
    STOCK_ANNUAL_SCHEDULE_EQUAL_WEIGHT = "STOCK_ANNUAL_SCHEDULE_EQUAL_WEIGHT"


def _intent_text(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise InvalidCandidateIntentError(f"{key} must be a non-empty string")
    return value


def _intent_date(payload: Mapping[str, object], key: str) -> date:
    value = _intent_text(payload, key)
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise InvalidCandidateIntentError(
            f"{key} must be an ISO date, got {value!r}"
        ) from error


def _intent_decimal(payload: Mapping[str, object], key: str) -> Decimal:
    value = _intent_text(payload, key)
    try:
        parsed = Decimal(value)
    except InvalidOperation as error:
        raise InvalidCandidateIntentError(
            f"{key} must be a finite Decimal string, got {value!r}"
        ) from error
    if not parsed.is_finite():
        raise InvalidCandidateIntentError(
            f"{key} must be a finite Decimal string, got {value!r}"
        )
    return parsed


def _intent_instruments(value: object, field_name: str) -> tuple[InstrumentId, ...]:
    if not isinstance(value, list) or not value:
        raise InvalidCandidateIntentError(
            f"{field_name} must be a non-empty list of instrument ids"
        )
    parsed: list[InstrumentId] = []
    for item in value:
        if not isinstance(item, str) or not item:
            raise InvalidCandidateIntentError(
                f"{field_name} must contain instrument id strings, got {item!r}"
            )
        try:
            parsed.append(InstrumentId.parse(item))
        except Exception as error:
            raise InvalidCandidateIntentError(
                f"{field_name} contains an invalid instrument id {item!r}"
            ) from error
    return tuple(sorted(set(parsed)))


def _intent_optional_instruments(
    value: object, field_name: str
) -> tuple[InstrumentId, ...]:
    """Parse an instrument list that must be explicitly declared and may be
    empty (data-derived universes name no fixed membership)."""
    if not isinstance(value, list):
        raise InvalidCandidateIntentError(
            f"{field_name} must be an explicitly declared list, got {value!r}"
        )
    return _intent_instruments(value, field_name) if value else ()


def _intent_string_mapping(payload: Mapping[str, object], key: str) -> Mapping[str, str]:
    value = payload.get(key)
    if not isinstance(value, dict) or not value:
        raise InvalidCandidateIntentError(f"{key} must be a non-empty mapping")
    for inner_key, inner_value in value.items():
        if not isinstance(inner_key, str) or not inner_key:
            raise InvalidCandidateIntentError(
                f"{key} keys must be non-empty strings, got {inner_key!r}"
            )
        if not isinstance(inner_value, str):
            raise InvalidCandidateIntentError(
                f"{key} values must be strings, got {inner_value!r}"
            )
    return MappingProxyType({str(k): str(v) for k, v in value.items()})


def _intent_sub_mapping(
    payload: Mapping[str, object], key: str
) -> Mapping[str, object]:
    value = payload.get(key)
    if not isinstance(value, dict) or not value:
        raise InvalidCandidateIntentError(f"{key} must be a non-empty mapping")
    return MappingProxyType(value)


@dataclass(frozen=True)
class UniversePolicySpec:
    """The pre-registered universe formation/reconstitution policy."""

    policy_name: str
    instrument_ids: tuple[InstrumentId, ...]

    def digest(self) -> str:
        return universe_view_digest(self.instrument_ids)


@dataclass(frozen=True)
class BenchmarkDeclaration:
    """The pre-registered benchmark declared before any result was seen."""

    kind: BenchmarkKind
    instrument_ids: tuple[InstrumentId, ...]
    rebalance: str

    def digest(self) -> str:
        lines = [
            "benchmark_declaration_v1",
            f"kind={self.kind.value}",
            "instruments=" + ",".join(str(item) for item in sorted(self.instrument_ids)),
            f"rebalance={self.rebalance}",
        ]
        return "sha256:" + sha256("\n".join(lines).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CandidateIntent:
    """The pre-code research contract, frozen before implementation.

    It records the hypothesis, rule pseudocode, parameter variants, the
    predeclared priority selection rule, universe policy, splits, benchmark,
    cost/metric conventions, and the Basic promotion / OOS survivor gates. It
    must never contain implementation, code-commit, or snapshot digests; those
    belong to the run-time :class:`ResearchRunManifest`.
    """

    intent_schema_version: str
    intent_id: str
    lineage_id: str
    asset_class: ResearchAssetClass
    sleeve: SleeveId
    strategy_id: str
    decision_frequency: str
    economic_rationale: str
    rule_pseudocode: str
    parameters_grid: tuple[str, ...]
    variant_parameters: Mapping[str, Mapping[str, str]]
    parameter_priority: tuple[str, ...]
    parameter_selection_rule: str
    universe_policy: UniversePolicySpec
    warm_up_start: date
    basic_start: date
    basic_end: date
    oos_start: date
    oos_end: date
    benchmark: BenchmarkDeclaration
    risk_off_choice: str
    initial_capital: Decimal
    cost_convention: Mapping[str, str]
    metric_convention: Mapping[str, str]
    basic_promotion_rule: Mapping[str, str]
    oos_survivor_rule: Mapping[str, str]
    known_limitations: tuple[str, ...]
    source: str
    created_at: date
    intent_digest: str

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "CandidateIntent":
        if not isinstance(payload, Mapping):
            raise InvalidCandidateIntentError("intent payload must be a mapping")
        if payload.get("intent_schema_version") != INTENT_SCHEMA_VERSION:
            raise InvalidCandidateIntentError(
                f"unsupported intent_schema_version {payload.get('intent_schema_version')!r}"
            )
        for forbidden in FORBIDDEN_INTENT_FIELDS:
            if forbidden in payload:
                raise InvalidCandidateIntentError(
                    f"a CandidateIntent must not contain the runtime field {forbidden!r}; "
                    "implementation/code/snapshot identities bind at run time only"
                )
        variant_list = payload.get("parameter_variants")
        if not isinstance(variant_list, list) or not variant_list:
            raise InvalidCandidateIntentError(
                "parameter_variants must be a non-empty list"
            )
        variant_parameters: dict[str, Mapping[str, str]] = {}
        for variant in variant_list:
            if not isinstance(variant, dict):
                raise InvalidCandidateIntentError(
                    "each parameter variant must be a mapping"
                )
            variant_id = _intent_text(variant, "variant_id")
            if variant_id in variant_parameters:
                raise InvalidCandidateIntentError(
                    f"duplicate parameter variant {variant_id!r}"
                )
            parameters = variant.get("parameters")
            if not isinstance(parameters, dict) or not parameters:
                raise InvalidCandidateIntentError(
                    f"variant {variant_id!r} must declare non-empty parameters"
                )
            variant_parameters[variant_id] = MappingProxyType(
                {str(k): str(v) for k, v in parameters.items()}
            )
        priority = payload.get("parameter_priority")
        if (
            not isinstance(priority, list)
            or not priority
            or not all(isinstance(item, str) and item for item in priority)
        ):
            raise InvalidCandidateIntentError(
                "parameter_priority must be a non-empty list of variant ids"
            )
        priority_tuple = tuple(priority)
        if len(set(priority_tuple)) != len(priority_tuple) or set(priority_tuple) != set(
            variant_parameters
        ):
            raise InvalidCandidateIntentError(
                "parameter_priority must order exactly the declared variants; "
                "a partial selection rule fails closed"
            )
        selection_rule = _intent_text(payload, "parameter_selection_rule")
        if selection_rule != PARAMETER_SELECTION_RULE:
            raise InvalidCandidateIntentError(
                f"M1 accepts only the {PARAMETER_SELECTION_RULE} selection rule, "
                f"got {selection_rule!r}"
            )

        universe_payload = _intent_sub_mapping(payload, "universe_policy")
        policy_name = _intent_text(universe_payload, "policy_name")
        asset_class = ResearchAssetClass(_intent_text(payload, "asset_class"))
        if asset_class is ResearchAssetClass.STOCK:
            if policy_name != STOCK_ANNUAL_POLICY_NAME:
                raise InvalidCandidateIntentError(
                    f"M1 STOCK candidates declare the frozen "
                    f"{STOCK_ANNUAL_POLICY_NAME} policy, got {policy_name!r}"
                )
            universe_instruments = _intent_optional_instruments(
                universe_payload.get("instrument_ids"),
                "universe_policy.instrument_ids",
            )
            if universe_instruments:
                raise InvalidCandidateIntentError(
                    "a data-derived annual PIT universe declares no fixed "
                    "instrument list; membership is reconstituted from the "
                    "snapshot at run time"
                )
        else:
            universe_instruments = _intent_instruments(
                universe_payload.get("instrument_ids"), "universe_policy.instrument_ids"
            )
        universe_spec = UniversePolicySpec(
            policy_name=policy_name,
            instrument_ids=universe_instruments,
        )
        sleeve = SleeveId(_intent_text(payload, "sleeve"))
        if asset_class is ResearchAssetClass.ETF and sleeve is not SleeveId.CORE:
            raise InvalidCandidateIntentError(
                "M1 ETF candidates use the CORE sleeve"
            )
        if asset_class is ResearchAssetClass.STOCK and sleeve is not SleeveId.SATELLITE:
            raise InvalidCandidateIntentError(
                "M1 STOCK candidates use the SATELLITE sleeve"
            )
        if asset_class is ResearchAssetClass.ETF:
            approved = {InstrumentId.parse(item) for item in M1_APPROVED_ETF_SYMBOLS}
            outside = sorted(set(universe_spec.instrument_ids) - approved)
            if outside:
                raise InvalidCandidateIntentError(
                    "ETF universe leaves the M0-qualified M1 set: "
                    + ", ".join(str(item) for item in outside)
                )

        benchmark_payload = _intent_sub_mapping(payload, "benchmark")
        benchmark_kind = BenchmarkKind(_intent_text(benchmark_payload, "kind"))
        if benchmark_kind is BenchmarkKind.STOCK_ANNUAL_SCHEDULE_EQUAL_WEIGHT:
            if asset_class is not ResearchAssetClass.STOCK:
                raise InvalidCandidateIntentError(
                    "the same-schedule annual benchmark belongs to STOCK "
                    "candidates only"
                )
            benchmark_instruments = _intent_optional_instruments(
                benchmark_payload.get("instrument_ids"), "benchmark.instrument_ids"
            )
            if benchmark_instruments:
                raise InvalidCandidateIntentError(
                    "the same-schedule annual benchmark names no fixed "
                    "instrument list; each year's cohort is the benchmark"
                )
        else:
            if asset_class is ResearchAssetClass.STOCK:
                raise InvalidCandidateIntentError(
                    "M1 STOCK candidates use the same-schedule annual "
                    f"{BenchmarkKind.STOCK_ANNUAL_SCHEDULE_EQUAL_WEIGHT.value} "
                    "benchmark"
                )
            benchmark_instruments = _intent_instruments(
                benchmark_payload.get("instrument_ids"), "benchmark.instrument_ids"
            )
            if not set(benchmark_instruments) <= set(universe_spec.instrument_ids):
                raise InvalidCandidateIntentError(
                    "benchmark instruments must be a subset of the universe"
                )
            if (
                benchmark_kind is BenchmarkKind.SINGLE_ETF_BUY_AND_HOLD
                and len(benchmark_instruments) != 1
            ):
                raise InvalidCandidateIntentError(
                    "SINGLE_ETF_BUY_AND_HOLD names exactly one instrument"
                )
        rebalance = _intent_text(benchmark_payload, "rebalance")
        expected_rebalance = (
            BENCHMARK_REBALANCE_ANNUAL
            if benchmark_kind is BenchmarkKind.STOCK_ANNUAL_SCHEDULE_EQUAL_WEIGHT
            else BENCHMARK_REBALANCE_INCEPTION
        )
        if rebalance != expected_rebalance:
            raise InvalidCandidateIntentError(
                f"M1 {benchmark_kind.value} benchmarks rebalance "
                f"{expected_rebalance} only, got {rebalance!r}"
            )

        warm_up_start = _intent_date(payload, "warm_up_start")
        basic_start = _intent_date(payload, "basic_start")
        basic_end = _intent_date(payload, "basic_end")
        oos_start = _intent_date(payload, "oos_start")
        oos_end = _intent_date(payload, "oos_end")
        if warm_up_start > basic_start:
            raise InvalidCandidateIntentError(
                "warm_up_start must not be after basic_start"
            )
        if basic_start > basic_end:
            raise InvalidCandidateIntentError(
                "basic_start must not be after basic_end"
            )
        if basic_end >= oos_start:
            raise InvalidCandidateIntentError(
                "basic_end must be strictly before oos_start"
            )
        if oos_start > oos_end:
            raise InvalidCandidateIntentError(
                "oos_start must not be after oos_end"
            )

        cost = _intent_string_mapping(payload, "cost_convention")
        for required_cost in ("commission_rate", "minimum_commission", "slippage_rate"):
            if required_cost not in cost:
                raise InvalidCandidateIntentError(
                    f"cost_convention requires {required_cost}"
                )
            value = Decimal(cost[required_cost])
            if not value.is_finite() or value < 0:
                raise InvalidCandidateIntentError(
                    f"cost_convention.{required_cost} must be a non-negative Decimal"
                )
        metric = _intent_string_mapping(payload, "metric_convention")
        if metric.get("return_basis") != "DAILY_CLOSE_TO_CLOSE":
            raise InvalidCandidateIntentError(
                "metric_convention.return_basis must be DAILY_CLOSE_TO_CLOSE"
            )
        try:
            annualization = int(metric.get("annualization_sessions", ""))
        except (TypeError, ValueError) as error:
            raise InvalidCandidateIntentError(
                "metric_convention.annualization_sessions must be a positive integer"
            ) from error
        if annualization <= 0:
            raise InvalidCandidateIntentError(
                "metric_convention.annualization_sessions must be a positive integer"
            )

        promotion = _intent_string_mapping(payload, "basic_promotion_rule")
        for required in PROMOTION_RULE_FIELDS:
            if required not in promotion:
                raise InvalidCandidateIntentError(
                    f"basic_promotion_rule requires {required}"
                )
        for promotion_key, promotion_value in promotion.items():
            try:
                Decimal(promotion_value)
            except InvalidOperation as error:
                raise InvalidCandidateIntentError(
                    f"basic_promotion_rule.{promotion_key} must be a Decimal "
                    f"string, got {promotion_value!r}"
                ) from error
        survivor = _intent_string_mapping(payload, "oos_survivor_rule")

        limitations = payload.get("known_limitations")
        if not isinstance(limitations, (list, tuple)) or not all(
            isinstance(item, str) and item for item in limitations
        ):
            raise InvalidCandidateIntentError(
                "known_limitations must be a non-empty list of strings"
            )
        if asset_class is ResearchAssetClass.STOCK and not any(
            REASON_DIVIDEND_TAX_NOT_MODELED in item for item in limitations
        ):
            raise InvalidCandidateIntentError(
                "M1 STOCK candidates must declare DIVIDEND_TAX_NOT_MODELED "
                "among known_limitations (OQ-24)"
            )
        created_at = _intent_date(payload, "created_at")
        initial_capital = _intent_decimal_field(payload, "initial_capital")
        if initial_capital <= 0:
            raise InvalidCandidateIntentError(
                "initial_capital must be a positive Decimal"
            )

        intent_digest = canonical_payload_digest(payload)
        return cls(
            intent_schema_version=INTENT_SCHEMA_VERSION,
            intent_id=_intent_text(payload, "intent_id"),
            lineage_id=_intent_text(payload, "lineage_id"),
            asset_class=asset_class,
            sleeve=sleeve,
            strategy_id=_intent_text(payload, "strategy_id"),
            decision_frequency=_intent_text(payload, "decision_frequency"),
            economic_rationale=_intent_text(payload, "economic_rationale"),
            rule_pseudocode=_intent_text(payload, "rule_pseudocode"),
            parameters_grid=tuple(variant_parameters),
            variant_parameters=MappingProxyType(dict(variant_parameters)),
            parameter_priority=priority_tuple,
            parameter_selection_rule=selection_rule,
            universe_policy=universe_spec,
            warm_up_start=warm_up_start,
            basic_start=basic_start,
            basic_end=basic_end,
            oos_start=oos_start,
            oos_end=oos_end,
            benchmark=BenchmarkDeclaration(
                kind=benchmark_kind,
                instrument_ids=benchmark_instruments,
                rebalance=rebalance,
            ),
            risk_off_choice=_intent_text(payload, "risk_off_choice"),
            initial_capital=initial_capital,
            cost_convention=cost,
            metric_convention=metric,
            basic_promotion_rule=promotion,
            oos_survivor_rule=survivor,
            known_limitations=tuple(limitations),
            source=_intent_text(payload, "source"),
            created_at=created_at,
            intent_digest=intent_digest,
        )


FORBIDDEN_INTENT_FIELDS: frozenset[str] = frozenset(
    {
        "implementation_digest",
        "code_commit",
        "snapshot_digest",
        "snapshot_id",
        "kernel_identity_digest",
    }
)

PROMOTION_RULE_FIELDS: tuple[str, ...] = (
    "min_nav_observations",
    "min_excess_total_return_vs_benchmark",
    "max_drawdown_floor",
    "max_turnover",
)


def _intent_decimal_field(payload: Mapping[str, object], key: str) -> Decimal:
    value = payload.get(key)
    if isinstance(value, str):
        try:
            return Decimal(value)
        except InvalidOperation as error:
            raise InvalidCandidateIntentError(
                f"{key} must be a Decimal string, got {value!r}"
            ) from error
    raise InvalidCandidateIntentError(f"{key} must be a Decimal string")


class ResearchOutputScope(StrEnum):
    """The output scope a research run may claim for one manifest."""

    BASIC = "BASIC"
    OOS = "OOS"


_RUN_DIGEST_FIELDS: tuple[str, ...] = (
    "intent_digest",
    "strategy_identity_digest",
    "implementation_digest",
    "parameters_digest",
    "split_digest",
    "snapshot_digest",
    "universe_schedule_digest",
    "benchmark_spec_digest",
    "cost_spec_digest",
    "metric_convention_digest",
    "kernel_identity_digest",
)

_RUN_TEXT_FIELDS: tuple[str, ...] = (
    "lineage_id",
    "strategy_id",
    "strategy_version",
    "code_commit",
    "dependency_digest",
)


@dataclass(frozen=True)
class ResearchRunManifest:
    """The run-time identity bound immediately before one research run.

    It binds the frozen CandidateIntent digest, the exact strategy
    implementation/version/parameters digests, the code commit, the
    dependency/kernel identity, the actual snapshot digest, the universe
    schedule digest, benchmark/cost/metric identities, the split digest, and
    the output scope. Modifying any field yields a new run identity; the
    output path is deliberately not part of the identity.
    """

    manifest_schema_version: str
    lineage_id: str
    intent_digest: str
    strategy_id: str
    strategy_version: str
    strategy_identity_digest: str
    implementation_digest: str
    parameters_digest: str
    code_commit: str
    dependency_digest: str
    split_digest: str
    snapshot_digest: str
    universe_schedule_digest: str
    benchmark_spec_digest: str
    cost_spec_digest: str
    metric_convention_digest: str
    kernel_identity_digest: str
    output_scope: str
    random_seed: int

    def __post_init__(self) -> None:
        if self.manifest_schema_version != RUN_MANIFEST_SCHEMA_VERSION:
            raise InvalidResearchRunManifestError(
                f"unsupported manifest_schema_version {self.manifest_schema_version!r}"
            )
        for name in _RUN_TEXT_FIELDS:
            value = getattr(self, name)
            if not isinstance(value, str) or not value:
                raise InvalidResearchRunManifestError(
                    f"{name} is required for exact research replay"
                )
        for name in _RUN_DIGEST_FIELDS:
            try:
                _require_sha256_digest(getattr(self, name), name)
            except InvalidStrategyIdentityError as error:
                raise InvalidResearchRunManifestError(str(error)) from error
        try:
            ResearchOutputScope(self.output_scope)
        except ValueError as error:
            raise InvalidResearchRunManifestError(
                f"output_scope must be BASIC or OOS, got {self.output_scope!r}"
            ) from error
        if not isinstance(self.random_seed, int) or isinstance(self.random_seed, bool):
            raise InvalidResearchRunManifestError("random_seed must be an integer")

    @property
    def identity_digest(self) -> str:
        payload = {
            name: getattr(self, name) for name in _RUN_MANIFEST_IDENTITY_FIELDS
        }
        rendered = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        )
        return "sha256:" + sha256(rendered.encode("utf-8")).hexdigest()

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            name: getattr(self, name)
            for name in _RUN_MANIFEST_IDENTITY_FIELDS
        }
        payload["identity_digest"] = self.identity_digest
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "ResearchRunManifest":
        if not isinstance(payload, Mapping):
            raise InvalidResearchRunManifestError("manifest payload must be a mapping")
        required = (*_RUN_MANIFEST_IDENTITY_FIELDS, "manifest_schema_version")
        for name in required:
            if name not in payload:
                raise InvalidResearchRunManifestError(
                    f"{name} is required for exact research replay"
                )
        for name in ("output_scope", "random_seed"):
            if name not in payload:
                raise InvalidResearchRunManifestError(
                    f"{name} is required for exact research replay"
                )
        scope = payload["output_scope"]
        random_seed = payload["random_seed"]
        if not isinstance(scope, str) or not isinstance(random_seed, int) or isinstance(
            random_seed, bool
        ):
            raise InvalidResearchRunManifestError(
                "output_scope must be a string and random_seed an integer"
            )
        return cls(
            manifest_schema_version=str(payload["manifest_schema_version"]),
            lineage_id=str(payload["lineage_id"]),
            intent_digest=str(payload["intent_digest"]),
            strategy_id=str(payload["strategy_id"]),
            strategy_version=str(payload["strategy_version"]),
            strategy_identity_digest=str(payload["strategy_identity_digest"]),
            implementation_digest=str(payload["implementation_digest"]),
            parameters_digest=str(payload["parameters_digest"]),
            code_commit=str(payload["code_commit"]),
            dependency_digest=str(payload["dependency_digest"]),
            split_digest=str(payload["split_digest"]),
            snapshot_digest=str(payload["snapshot_digest"]),
            universe_schedule_digest=str(payload["universe_schedule_digest"]),
            benchmark_spec_digest=str(payload["benchmark_spec_digest"]),
            cost_spec_digest=str(payload["cost_spec_digest"]),
            metric_convention_digest=str(payload["metric_convention_digest"]),
            kernel_identity_digest=str(payload["kernel_identity_digest"]),
            output_scope=scope,
            random_seed=random_seed,
        )


_RUN_MANIFEST_IDENTITY_FIELDS: tuple[str, ...] = (
    "manifest_schema_version",
    "lineage_id",
    "intent_digest",
    "strategy_id",
    "strategy_version",
    "strategy_identity_digest",
    "implementation_digest",
    "parameters_digest",
    "code_commit",
    "dependency_digest",
    "split_digest",
    "snapshot_digest",
    "universe_schedule_digest",
    "benchmark_spec_digest",
    "cost_spec_digest",
    "metric_convention_digest",
    "kernel_identity_digest",
    "output_scope",
    "random_seed",
)
