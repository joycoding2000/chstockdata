"""The Data Quality Gate: deterministic, purpose-scoped checks over a
canonical dataset.

The gate is the only component that declares a dataset eligible for a run
purpose. Checks are deterministic and versioned; any blocking failure
prevents the purpose-specific action (a new target, or a pre-open risk
increase). A reduction is permitted only with independently reliable
identity, holding, sellability, tradability, and conservative price/cost
evidence; otherwise no order is emitted and urgent manual review is
required. Provider rule candidates are adjudicated against the approved
Instrument Master and can never become authority here.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from hashlib import sha256
from types import MappingProxyType

from systematic_investing.domain.identifiers import InstrumentId, require_session_date
from systematic_investing.domain.market import (
    CANONICAL_RECORD_SCHEMA_VERSION,
    Availability,
    AvailabilityBasis,
    CorporateAction,
    DailyBar,
    TradabilityStatus,
    TradingSession,
)
from systematic_investing.domain.runs import RunPurpose
from systematic_investing.instrument_master.models import (
    AdjudicationStatus,
    RuleCandidate,
    UnknownInstrumentError,
    UnknownRuleError,
)
from systematic_investing.instrument_master.repository import InstrumentMaster


class QualityGateError(Exception):
    """Base class for Data Quality Gate errors."""


class InvalidGateRequestError(QualityGateError):
    """Raised when a gate evaluation request violates its contract."""


class CheckStatus(StrEnum):
    """Status of one deterministic check."""

    PASS = "PASS"
    FAIL = "FAIL"
    WARN = "WARN"


class CheckSeverity(StrEnum):
    """Whether a failing check blocks the gated purpose or only warns."""

    BLOCKING = "BLOCKING"
    WARNING = "WARNING"


class GateStatus(StrEnum):
    """Aggregate gate status."""

    PASS = "PASS"
    FAIL = "FAIL"
    WARN = "WARN"


class GateAction(StrEnum):
    """Purpose-specific action implied by the gate outcome."""

    PROCEED = "PROCEED"
    BLOCK_NEW_TARGET = "BLOCK_NEW_TARGET"
    BLOCK_RISK_INCREASE = "BLOCK_RISK_INCREASE"
    NO_ORDER_MANUAL_REVIEW = "NO_ORDER_MANUAL_REVIEW"


class UnknownHandling(StrEnum):
    """Versioned policy for facts whose availability basis is UNKNOWN."""

    REJECT = "REJECT"
    ACCEPT_EXPLICIT = "ACCEPT_EXPLICIT"


# Blocking reason codes, versioned by the gate version.
REASON_UNSUPPORTED_SCHEMA_VERSION = "UNSUPPORTED_SCHEMA_VERSION"
REASON_MISSING_REQUIRED_FIELD = "MISSING_REQUIRED_FIELD"
REASON_DUPLICATE_BAR_KEY = "DUPLICATE_BAR_KEY"
REASON_BAR_ON_CLOSED_SESSION = "BAR_ON_CLOSED_SESSION"
REASON_CALENDAR_NOT_PROVIDED = "CALENDAR_NOT_PROVIDED"
REASON_INFORMATION_NOT_AVAILABLE_AT_CUTOFF = "INFORMATION_NOT_AVAILABLE_AT_CUTOFF"
REASON_UNKNOWN_INFORMATION_AVAILABILITY = "UNKNOWN_INFORMATION_AVAILABILITY"
REASON_DISALLOWED_AVAILABILITY_BASIS = "DISALLOWED_AVAILABILITY_BASIS"
REASON_SESSION_AFTER_INTENDED_DECISION = "SESSION_AFTER_INTENDED_DECISION"
REASON_STALE_INFORMATION = "STALE_INFORMATION"
REASON_UNKNOWN_INSTRUMENT_CLASSIFICATION = "UNKNOWN_INSTRUMENT_CLASSIFICATION"
REASON_UNKNOWN_RULE_PROFILE = "UNKNOWN_RULE_PROFILE"
REASON_RULE_CANDIDATE_FAIL_CLOSED = "RULE_CANDIDATE_FAIL_CLOSED"
REASON_APPROVED_PROFILE_GOVERNS = "APPROVED_PROFILE_GOVERNS"
REASON_PRE_CLOSE_MISMATCH_WITHOUT_ACTION = "PRE_CLOSE_MISMATCH_WITHOUT_ACTION"
REASON_REDUCTION_EVIDENCE_COMPLETE = "REDUCTION_EVIDENCE_COMPLETE"
REASON_INSUFFICIENT_REDUCTION_EVIDENCE = "INSUFFICIENT_REDUCTION_EVIDENCE"
REASON_URGENT_MANUAL_REVIEW_REQUIRED = "URGENT_MANUAL_REVIEW_REQUIRED"


def _aware_datetime(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise InvalidGateRequestError(
            f"{field_name} must be a timezone-aware datetime, got {value!r}"
        )
    return value


def _digest(lines: list[str]) -> str:
    return sha256("\n".join(lines).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CanonicalDataset:
    """An immutable bundle of canonical records for gating."""

    daily_bars: tuple[DailyBar, ...]
    sessions: tuple[TradingSession, ...]
    tradability: tuple[TradabilityStatus, ...]
    corporate_actions: tuple[CorporateAction, ...]
    rule_candidates: tuple[RuleCandidate, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.daily_bars, tuple) or not all(
            isinstance(item, DailyBar) for item in self.daily_bars
        ):
            raise QualityGateError("daily_bars must be a tuple of DailyBar records")
        if not isinstance(self.sessions, tuple) or not all(
            isinstance(item, TradingSession) for item in self.sessions
        ):
            raise QualityGateError("sessions must be a tuple of TradingSession records")
        if not isinstance(self.tradability, tuple) or not all(
            isinstance(item, TradabilityStatus) for item in self.tradability
        ):
            raise QualityGateError("tradability must be a tuple of TradabilityStatus records")
        if not isinstance(self.corporate_actions, tuple) or not all(
            isinstance(item, CorporateAction) for item in self.corporate_actions
        ):
            raise QualityGateError("corporate_actions must be a tuple of CorporateAction records")
        if not isinstance(self.rule_candidates, tuple) or not all(
            isinstance(item, RuleCandidate) for item in self.rule_candidates
        ):
            raise QualityGateError("rule_candidates must be a tuple of RuleCandidate records")

    def content_digest(self) -> str:
        """Deterministic digest over canonical dataset content, independent
        of input ordering."""
        lines = ["canonical_dataset_v1"]
        for kind, records in (
            ("daily_bar", self.daily_bars),
            ("trading_session", self.sessions),
            ("tradability_status", self.tradability),
            ("corporate_action", self.corporate_actions),
            ("rule_candidate", self.rule_candidates),
        ):
            for record in sorted(records, key=repr):
                lines.append(f"{kind}={record!r}")
        return _digest(lines)


@dataclass(frozen=True)
class DatasetPolicy:
    """Versioned gate thresholds; never undocumented constants."""

    schema_version: str = "m0-dataset-policy-1"
    require_pre_close: bool = True
    max_information_age_sessions: int = 0
    allowed_bases: frozenset = frozenset(
        {
            AvailabilityBasis.OBSERVED,
            AvailabilityBasis.EXCHANGE_RULE,
            AvailabilityBasis.INFERRED,
        }
    )
    unknown_handling: UnknownHandling = UnknownHandling.REJECT

    def content_digest(self) -> str:
        lines = [
            f"schema_version={self.schema_version}",
            f"require_pre_close={self.require_pre_close}",
            f"max_information_age_sessions={self.max_information_age_sessions}",
            "allowed_bases=" + ",".join(sorted(basis.value for basis in self.allowed_bases)),
            f"unknown_handling={self.unknown_handling.value}",
        ]
        return _digest(lines)


@dataclass(frozen=True)
class CheckResult:
    """Outcome of one check: status, severity, affected scope, observed and
    expected values, reason code, and evidence ids."""

    check_id: str
    status: CheckStatus
    severity: CheckSeverity
    reason_code: str
    affected_scope: tuple[str, ...] = ()
    observed: str | None = None
    expected: str | None = None
    evidence_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "affected_scope", tuple(self.affected_scope))
        object.__setattr__(self, "evidence_ids", tuple(self.evidence_ids))


@dataclass(frozen=True)
class GateResult:
    """The persisted gate decision for one declared purpose."""

    gate_name: str
    gate_version: str
    purpose: RunPurpose
    status: GateStatus
    action: GateAction
    evaluated_at: datetime
    checks: tuple[CheckResult, ...]
    reason_codes: tuple[str, ...]
    input_digests: Mapping[str, str]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "input_digests",
            MappingProxyType(dict(self.input_digests)),
        )

    def content_digest(self) -> str:
        """Deterministic digest of the gate decision content."""
        lines = [
            f"gate={self.gate_name},{self.gate_version}",
            f"purpose={self.purpose.value}",
            f"status={self.status.value}",
            f"action={self.action.value}",
            *self.reason_codes,
        ]
        for check in sorted(self.checks, key=lambda item: item.check_id):
            lines.append(
                f"check={check.check_id},{check.status.value},{check.severity.value},"
                f"{check.reason_code},{','.join(check.affected_scope)},"
                f"{check.observed},{check.expected},{','.join(check.evidence_ids)}"
            )
        for name in sorted(self.input_digests):
            lines.append(f"input_digest={name},{self.input_digests[name]}")
        return _digest(lines)


@dataclass(frozen=True)
class ReductionEvidence:
    """Traceable evidence statements required before any reduction order.

    Each member is an evidence id proving that one requirement is
    independently reliable; a reduction order is only permitted when all
    five are present."""

    identity_evidence_id: str | None = None
    holding_evidence_id: str | None = None
    sellability_evidence_id: str | None = None
    tradability_evidence_id: str | None = None
    price_cost_evidence_id: str | None = None

    def is_complete(self) -> bool:
        return all(
            getattr(self, field_name) is not None
            for field_name in (
                "identity_evidence_id",
                "holding_evidence_id",
                "sellability_evidence_id",
                "tradability_evidence_id",
                "price_cost_evidence_id",
            )
        )


def _check_bar_schema(dataset: CanonicalDataset) -> list[CheckResult]:
    results = []
    for bar in dataset.daily_bars:
        if bar.schema_version != CANONICAL_RECORD_SCHEMA_VERSION:
            results.append(
                CheckResult(
                    check_id="SCHEMA_VERSION",
                    status=CheckStatus.FAIL,
                    severity=CheckSeverity.BLOCKING,
                    reason_code=REASON_UNSUPPORTED_SCHEMA_VERSION,
                    affected_scope=(str(bar.instrument_id), bar.session_date.isoformat()),
                    observed=bar.schema_version,
                    expected=CANONICAL_RECORD_SCHEMA_VERSION,
                )
            )
    return results


def _check_required_fields(dataset: CanonicalDataset, policy: DatasetPolicy) -> list[CheckResult]:
    results = []
    if policy.require_pre_close:
        for bar in dataset.daily_bars:
            if bar.pre_close is None:
                results.append(
                    CheckResult(
                        check_id="REQUIRED_FIELDS",
                        status=CheckStatus.FAIL,
                        severity=CheckSeverity.BLOCKING,
                        reason_code=REASON_MISSING_REQUIRED_FIELD,
                        affected_scope=(str(bar.instrument_id), bar.session_date.isoformat()),
                        observed="pre_close=None",
                        expected="pre_close present; missing values are never converted to zero",
                    )
                )
    return results


def _check_unique_bar_keys(dataset: CanonicalDataset) -> list[CheckResult]:
    results = []
    seen: set[tuple[InstrumentId, date]] = set()
    for bar in dataset.daily_bars:
        key = (bar.instrument_id, bar.session_date)
        if key in seen:
            results.append(
                CheckResult(
                    check_id="UNIQUE_BAR_KEYS",
                    status=CheckStatus.FAIL,
                    severity=CheckSeverity.BLOCKING,
                    reason_code=REASON_DUPLICATE_BAR_KEY,
                    affected_scope=(str(bar.instrument_id), bar.session_date.isoformat()),
                    observed="duplicate (instrument_id, session_date) key",
                    expected="unique (instrument_id, session_date) keys",
                )
            )
        seen.add(key)
    return results


def _check_session_alignment(dataset: CanonicalDataset) -> list[CheckResult]:
    results = []
    if not dataset.sessions:
        results.append(
            CheckResult(
                check_id="SESSION_ALIGNMENT",
                status=CheckStatus.FAIL,
                severity=CheckSeverity.BLOCKING,
                reason_code=REASON_CALENDAR_NOT_PROVIDED,
                affected_scope=(),
                observed="no calendar sessions provided",
                expected="a calendar snapshot covering every bar session",
            )
        )
        return results
    open_dates = {session.session_date for session in dataset.sessions if session.is_open}
    for bar in dataset.daily_bars:
        if bar.session_date not in open_dates:
            results.append(
                CheckResult(
                    check_id="SESSION_ALIGNMENT",
                    status=CheckStatus.FAIL,
                    severity=CheckSeverity.BLOCKING,
                    reason_code=REASON_BAR_ON_CLOSED_SESSION,
                    affected_scope=(str(bar.instrument_id), bar.session_date.isoformat()),
                    observed=f"session {bar.session_date.isoformat()} is not an open session",
                    expected="bars only on open sessions of the instrument's calendar",
                )
            )
    return results


def _check_pre_close_consistency(dataset: CanonicalDataset) -> list[CheckResult]:
    """Compare each bar's ``pre_close`` with the prior session's close when
    the two sessions are adjacent open sessions of the same calendar. A
    mismatch is only tolerated when a corporate action is effective on the
    bar's session date."""
    results = []
    if not dataset.sessions:
        return results
    bars_by_calendar: dict[str, list[DailyBar]] = {}
    for bar in dataset.daily_bars:
        bars_by_calendar.setdefault(bar.instrument_id.exchange.value, []).append(bar)
    open_dates_by_calendar: dict[str, list[date]] = {}
    for session in dataset.sessions:
        if session.is_open:
            open_dates_by_calendar.setdefault(session.calendar_id, []).append(
                session.session_date
            )
    effective_actions: dict[tuple[str, InstrumentId], set[date]] = {}
    for action in dataset.corporate_actions:
        key = (action.instrument_id.exchange.value, action.instrument_id)
        effective_actions.setdefault(key, set()).add(action.ex_date)
    for calendar_id, bars in bars_by_calendar.items():
        open_dates = sorted(open_dates_by_calendar.get(calendar_id, []))
        ordered = sorted(bars, key=lambda bar: bar.session_date)
        for index in range(1, len(ordered)):
            previous_bar = ordered[index - 1]
            current_bar = ordered[index]
            prior_open_dates = [
                open_date for open_date in open_dates if open_date < current_bar.session_date
            ]
            if not prior_open_dates or previous_bar.session_date != prior_open_dates[-1]:
                continue
            if current_bar.pre_close is None:
                continue
            if current_bar.pre_close == previous_bar.close:
                continue
            actions = effective_actions.get((calendar_id, current_bar.instrument_id), set())
            if current_bar.session_date in actions:
                continue
            results.append(
                CheckResult(
                    check_id="PRE_CLOSE_CONSISTENCY",
                    status=CheckStatus.FAIL,
                    severity=CheckSeverity.BLOCKING,
                    reason_code=REASON_PRE_CLOSE_MISMATCH_WITHOUT_ACTION,
                    affected_scope=(
                        str(current_bar.instrument_id),
                        current_bar.session_date.isoformat(),
                    ),
                    observed=f"pre_close={current_bar.pre_close}",
                    expected=f"prior session close {previous_bar.close}",
                )
            )
    return results


class DataQualityGate:
    """Deterministic, purpose-scoped quality gate over a canonical dataset."""

    GATE_NAME: str = "DATA_QUALITY_GATE"
    GATE_VERSION: str = "m0-quality-gate-1"

    def __init__(self, master: InstrumentMaster, policy: DatasetPolicy) -> None:
        self._master = master
        self._policy = policy

    def evaluate(
        self,
        dataset: CanonicalDataset,
        *,
        purpose: RunPurpose,
        intended_decision_session: date,
        information_cutoff: datetime,
        evaluated_at: datetime,
        reduction_intended: bool = False,
        reduction_evidence: ReductionEvidence | None = None,
    ) -> GateResult:
        if not isinstance(purpose, RunPurpose):
            raise InvalidGateRequestError(f"purpose must be a RunPurpose, got {purpose!r}")
        require_session_date(intended_decision_session)
        _aware_datetime(information_cutoff, "information_cutoff")
        _aware_datetime(evaluated_at, "evaluated_at")
        if information_cutoff > evaluated_at:
            raise InvalidGateRequestError("information_cutoff must not be after evaluated_at")

        checks = [
            *_check_bar_schema(dataset),
            *_check_required_fields(dataset, self._policy),
            *_check_unique_bar_keys(dataset),
            *_check_session_alignment(dataset),
            *_check_pre_close_consistency(dataset),
            *self._check_information_time(dataset, information_cutoff),
            *self._check_freshness(
                dataset, intended_decision_session, information_cutoff
            ),
            *self._check_instrument_master_authority(dataset),
            *self._check_reduction_evidence(reduction_intended, reduction_evidence),
        ]
        blocking = [
            check
            for check in checks
            if check.status is CheckStatus.FAIL and check.severity is CheckSeverity.BLOCKING
        ]
        if blocking:
            status = GateStatus.FAIL
        elif any(check.status is CheckStatus.WARN for check in checks):
            status = GateStatus.WARN
        else:
            status = GateStatus.PASS

        reduction_blocked = reduction_intended and (
            reduction_evidence is None or not reduction_evidence.is_complete()
        )
        if reduction_blocked:
            action = GateAction.NO_ORDER_MANUAL_REVIEW
        elif purpose is RunPurpose.DECISION:
            action = GateAction.BLOCK_NEW_TARGET if blocking else GateAction.PROCEED
        else:
            action = GateAction.BLOCK_RISK_INCREASE if blocking else GateAction.PROCEED

        reason_codes = tuple(dict.fromkeys(check.reason_code for check in blocking))
        if reduction_blocked and REASON_URGENT_MANUAL_REVIEW_REQUIRED not in reason_codes:
            reason_codes = (
                *reason_codes,
                REASON_INSUFFICIENT_REDUCTION_EVIDENCE,
                REASON_URGENT_MANUAL_REVIEW_REQUIRED,
            )

        return GateResult(
            gate_name=self.GATE_NAME,
            gate_version=self.GATE_VERSION,
            purpose=purpose,
            status=status,
            action=action,
            evaluated_at=evaluated_at,
            checks=tuple(checks),
            reason_codes=reason_codes,
            input_digests={
                "dataset": dataset.content_digest(),
                "policy": self._policy.content_digest(),
            },
        )

    def _check_information_time(
        self, dataset: CanonicalDataset, information_cutoff: datetime
    ) -> list[CheckResult]:
        """Point-in-time access uses only information availability:
        ``retrieved_at`` never substitutes, and an UNKNOWN basis is handled
        by the versioned policy (never treated as knowable)."""
        results = []
        pit_records: list[tuple[str, tuple[str, ...], Availability]] = []
        for bar in dataset.daily_bars:
            pit_records.append(
                (
                    "daily_bar",
                    (str(bar.instrument_id), bar.session_date.isoformat()),
                    bar.availability,
                )
            )
        for record in dataset.tradability:
            pit_records.append(
                (
                    "tradability_status",
                    (str(record.instrument_id), record.session_date.isoformat()),
                    record.availability,
                )
            )
        for action in dataset.corporate_actions:
            pit_records.append(
                (
                    "corporate_action",
                    (str(action.instrument_id), action.ex_date.isoformat()),
                    action.availability,
                )
            )
        for _, scope, availability in pit_records:
            known = availability.information_known_at(information_cutoff)
            if known is False:
                available_at = availability.information_available_at
                results.append(
                    CheckResult(
                        check_id="INFORMATION_TIME",
                        status=CheckStatus.FAIL,
                        severity=CheckSeverity.BLOCKING,
                        reason_code=REASON_INFORMATION_NOT_AVAILABLE_AT_CUTOFF,
                        affected_scope=scope,
                        observed=(
                            "information_available_at="
                            f"{available_at.isoformat() if available_at is not None else 'None'}"
                        ),
                        expected=f"information available by {information_cutoff.isoformat()}",
                    )
                )
            elif known is None and self._policy.unknown_handling is UnknownHandling.REJECT:
                results.append(
                    CheckResult(
                        check_id="INFORMATION_TIME",
                        status=CheckStatus.FAIL,
                        severity=CheckSeverity.BLOCKING,
                        reason_code=REASON_UNKNOWN_INFORMATION_AVAILABILITY,
                        affected_scope=scope,
                        observed="availability_basis=UNKNOWN",
                        expected="a known availability basis under the versioned policy",
                    )
                )
        return results

    def _check_freshness(
        self,
        dataset: CanonicalDataset,
        intended_decision_session: date,
        information_cutoff: datetime,
    ) -> list[CheckResult]:
        """Freshness is measured against the intended decision session with
        the injected decision cutoff; facts dated after the intended session
        are future data and always block."""
        results = []
        open_dates_by_calendar: dict[str, list[date]] = {}
        for session in dataset.sessions:
            if session.is_open:
                open_dates_by_calendar.setdefault(session.calendar_id, []).append(
                    session.session_date
                )
        for bar in dataset.daily_bars:
            if bar.session_date > intended_decision_session:
                results.append(
                    CheckResult(
                        check_id="FRESHNESS",
                        status=CheckStatus.FAIL,
                        severity=CheckSeverity.BLOCKING,
                        reason_code=REASON_SESSION_AFTER_INTENDED_DECISION,
                        affected_scope=(str(bar.instrument_id), bar.session_date.isoformat()),
                        observed=f"bar session {bar.session_date.isoformat()}",
                        expected=(
                            f"no information after the intended session "
                            f"{intended_decision_session.isoformat()}"
                        ),
                    )
                )
        knowable_by_instrument: dict[InstrumentId, list[DailyBar]] = {}
        for bar in dataset.daily_bars:
            if bar.availability.information_known_at(information_cutoff) is True:
                knowable_by_instrument.setdefault(bar.instrument_id, []).append(bar)
        for instrument_id, bars in sorted(knowable_by_instrument.items()):
            latest = max(bar.session_date for bar in bars)
            open_dates = sorted(
                open_dates_by_calendar.get(instrument_id.exchange.value, [])
            )
            age = sum(
                1
                for open_date in open_dates
                if latest < open_date <= intended_decision_session
            )
            if age > self._policy.max_information_age_sessions:
                results.append(
                    CheckResult(
                        check_id="FRESHNESS",
                        status=CheckStatus.FAIL,
                        severity=CheckSeverity.BLOCKING,
                        reason_code=REASON_STALE_INFORMATION,
                        affected_scope=(str(instrument_id),),
                        observed=(
                            f"latest knowable session {latest.isoformat()}; "
                            f"information age {age} open session(s)"
                        ),
                        expected=(
                            f"information age at most "
                            f"{self._policy.max_information_age_sessions} open session(s)"
                        ),
                    )
                )
        return results

    def _check_instrument_master_authority(self, dataset: CanonicalDataset) -> list[CheckResult]:
        """Bars must be covered by approved Instrument Master profiles, and
        provider rule candidates are adjudicated: when an approved profile
        governs, the candidate is ignored; when nothing approved covers the
        session, the gate fails closed. A candidate is never promoted."""
        results = []
        resolved: set[tuple[InstrumentId, date]] = set()
        for bar in dataset.daily_bars:
            key = (bar.instrument_id, bar.session_date)
            if key in resolved:
                continue
            resolved.add(key)
            try:
                self._master.resolve_rules(bar.instrument_id, bar.session_date)
            except UnknownInstrumentError:
                results.append(
                    CheckResult(
                        check_id="INSTRUMENT_MASTER_AUTHORITY",
                        status=CheckStatus.FAIL,
                        severity=CheckSeverity.BLOCKING,
                        reason_code=REASON_UNKNOWN_INSTRUMENT_CLASSIFICATION,
                        affected_scope=(str(bar.instrument_id), bar.session_date.isoformat()),
                        observed="no approved instrument version covers the session",
                        expected="approved Instrument Master classification",
                    )
                )
            except UnknownRuleError:
                results.append(
                    CheckResult(
                        check_id="INSTRUMENT_MASTER_AUTHORITY",
                        status=CheckStatus.FAIL,
                        severity=CheckSeverity.BLOCKING,
                        reason_code=REASON_UNKNOWN_RULE_PROFILE,
                        affected_scope=(str(bar.instrument_id), bar.session_date.isoformat()),
                        observed="no approved rule profile covers the session",
                        expected="approved lot/settlement/price-limit/market-fee profiles",
                    )
                )
        for candidate in sorted(dataset.rule_candidates, key=repr):
            adjudication = self._master.adjudicate_rule_candidate(candidate)
            scope = (str(candidate.instrument_id), candidate.session_date.isoformat())
            if adjudication.status is AdjudicationStatus.FAIL_CLOSED_NO_APPROVED_PROFILE:
                results.append(
                    CheckResult(
                        check_id="INSTRUMENT_MASTER_AUTHORITY",
                        status=CheckStatus.FAIL,
                        severity=CheckSeverity.BLOCKING,
                        reason_code=REASON_RULE_CANDIDATE_FAIL_CLOSED,
                        affected_scope=scope,
                        observed="provider candidate without an approved profile",
                        expected="approved Instrument Master authority or fail closed",
                    )
                )
            else:
                results.append(
                    CheckResult(
                        check_id="INSTRUMENT_MASTER_AUTHORITY",
                        status=CheckStatus.PASS,
                        severity=CheckSeverity.BLOCKING,
                        reason_code=REASON_APPROVED_PROFILE_GOVERNS,
                        affected_scope=scope,
                        observed="provider candidate proposed conflicting values",
                        expected="the approved profile governs; the candidate is ignored",
                    )
                )
        return results

    def _check_reduction_evidence(
        self, reduction_intended: bool, reduction_evidence: ReductionEvidence | None
    ) -> list[CheckResult]:
        if not reduction_intended:
            return []
        if reduction_evidence is not None and reduction_evidence.is_complete():
            return [
                CheckResult(
                    check_id="REDUCTION_EVIDENCE",
                    status=CheckStatus.PASS,
                    severity=CheckSeverity.BLOCKING,
                    reason_code=REASON_REDUCTION_EVIDENCE_COMPLETE,
                    affected_scope=(),
                    evidence_ids=tuple(
                        evidence_id
                        for evidence_id in (
                            reduction_evidence.identity_evidence_id,
                            reduction_evidence.holding_evidence_id,
                            reduction_evidence.sellability_evidence_id,
                            reduction_evidence.tradability_evidence_id,
                            reduction_evidence.price_cost_evidence_id,
                        )
                        if evidence_id is not None
                    ),
                )
            ]
        missing = [
            field_name
            for field_name in (
                "identity_evidence_id",
                "holding_evidence_id",
                "sellability_evidence_id",
                "tradability_evidence_id",
                "price_cost_evidence_id",
            )
            if reduction_evidence is None or getattr(reduction_evidence, field_name) is None
        ]
        return [
            CheckResult(
                check_id="REDUCTION_EVIDENCE",
                status=CheckStatus.FAIL,
                severity=CheckSeverity.BLOCKING,
                reason_code=REASON_INSUFFICIENT_REDUCTION_EVIDENCE,
                affected_scope=tuple(missing),
                observed="reduction evidence incomplete",
                expected=(
                    "independently reliable identity, holding, sellability, "
                    "tradability, and conservative price/cost evidence"
                ),
            )
        ]
