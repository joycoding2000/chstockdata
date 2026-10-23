"""Run purposes and immutable replay identity.

A dataset is only ever eligible for a declared purpose; the purpose decides
which gate scope applies (a new target decision or a pre-open risk
evaluation). ``RunManifest`` binds every M0 replay-sensitive input to one
content-derived identity.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
from hmac import compare_digest


class RunPurpose(StrEnum):
    """The declared purpose a dataset is gated for.

    ``DECISION`` covers producing a new target after a session close;
    ``PRE_OPEN`` covers the pre-open risk evaluation before activating
    pending executions. Purpose-specific gating policies are versioned.
    """

    DECISION = "DECISION"
    PRE_OPEN = "PRE_OPEN"


class InvalidRunManifestError(ValueError):
    """Raised when an exact-replay identity is missing or unsupported."""


@dataclass(frozen=True)
class RunManifest:
    """Minimal immutable identity required to claim exact M0 replay.

    Output artifacts are intentionally not inputs to this digest. They are
    compared against it by replay verification rather than making the run
    identity depend on its own result.
    """

    manifest_schema_version: str
    run_type: str
    code_commit: str
    dependency_lock_digest: str
    data_snapshot_digest: str
    fee_config_digest: str
    calendar_digest: str
    execution_model_version: str
    rule_versions: tuple[tuple[str, str], ...]
    metric_convention_digest: str
    benchmark_identity: str
    random_seed: int

    def __post_init__(self) -> None:
        try:
            normalized_rule_versions = tuple(tuple(item) for item in self.rule_versions)
        except TypeError as error:
            raise InvalidRunManifestError(
                "rule_versions must be pairs of non-empty strings"
            ) from error
        if not all(
            len(item) == 2
            and all(isinstance(value, str) and value for value in item)
            for item in normalized_rule_versions
        ):
            raise InvalidRunManifestError(
                "rule_versions must be pairs of non-empty strings"
            )
        object.__setattr__(self, "rule_versions", normalized_rule_versions)
        if not self.code_commit:
            raise InvalidRunManifestError("code_commit is required for exact replay")
        for field_name in (
            "dependency_lock_digest",
            "data_snapshot_digest",
            "fee_config_digest",
            "calendar_digest",
            "metric_convention_digest",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value:
                raise InvalidRunManifestError(
                    f"{field_name} is required for exact replay"
                )
        if self.benchmark_identity not in {
            "NONE",
            "SYNTHETIC_TEST_BENCHMARK",
        }:
            raise InvalidRunManifestError(
                "M0 benchmark_identity must be NONE or SYNTHETIC_TEST_BENCHMARK"
            )

    @property
    def identity_digest(self) -> str:
        """SHA-256 over canonical, replay-sensitive manifest fields."""

        payload = {
            "benchmark_identity": self.benchmark_identity,
            "calendar_digest": self.calendar_digest,
            "code_commit": self.code_commit,
            "data_snapshot_digest": self.data_snapshot_digest,
            "dependency_lock_digest": self.dependency_lock_digest,
            "execution_model_version": self.execution_model_version,
            "fee_config_digest": self.fee_config_digest,
            "manifest_schema_version": self.manifest_schema_version,
            "metric_convention_digest": self.metric_convention_digest,
            "random_seed": self.random_seed,
            "rule_versions": [list(item) for item in sorted(self.rule_versions)],
            "run_type": self.run_type,
        }
        rendered = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        return "sha256:" + sha256(rendered.encode("utf-8")).hexdigest()


class InvalidPromotionRecordError(ValueError):
    """Raised when the minimum owner-controlled promotion evidence is absent."""


class BundleDigestMismatchError(ValueError):
    """Raised when loaded bundle bytes differ from the approved audit digest."""


def _require_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise InvalidPromotionRecordError(f"{field_name} must be a non-empty string")


@dataclass(frozen=True)
class PromotionAuditRecord:
    """Minimum immutable Research-to-Production promotion evidence for M0.

    This is an artifact contract, not a promotion workflow or signing service.
    Later milestones own storage, access control, and operational approval.
    """

    audit_id: str
    bundle_id: str
    bundle_version: str
    content_digest: str
    owner_approval_id: str
    approved_by: str
    approved_at: datetime
    source_authority: str
    destination_authority: str
    reason: str

    def __post_init__(self) -> None:
        for field_name in (
            "audit_id",
            "bundle_id",
            "bundle_version",
            "content_digest",
            "owner_approval_id",
            "approved_by",
            "source_authority",
            "destination_authority",
            "reason",
        ):
            _require_text(getattr(self, field_name), field_name)
        if self.source_authority != "RESEARCH" or self.destination_authority != "PRODUCTION":
            raise InvalidPromotionRecordError(
                "promotion authority must be explicitly separated RESEARCH -> PRODUCTION"
            )
        if self.approved_at.tzinfo is None or self.approved_at.utcoffset() is None:
            raise InvalidPromotionRecordError("approved_at must be timezone-aware")
        prefix, separator, hexadecimal = self.content_digest.partition(":")
        if (
            prefix != "sha256"
            or separator != ":"
            or len(hexadecimal) != 64
            or any(character not in "0123456789abcdef" for character in hexadecimal)
        ):
            raise InvalidPromotionRecordError(
                "content_digest must be a lowercase sha256 digest"
            )


@dataclass(frozen=True)
class ApprovedBundle:
    """Owner-approved bundle reference that verifies bytes before trusted use."""

    audit_record: PromotionAuditRecord

    def verify_content(self, content: bytes) -> None:
        observed = "sha256:" + sha256(content).hexdigest()
        if not compare_digest(observed, self.audit_record.content_digest):
            raise BundleDigestMismatchError(
                f"bundle {self.audit_record.bundle_id!r} content digest mismatch"
            )
