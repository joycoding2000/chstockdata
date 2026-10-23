"""Immutable snapshots: versioned manifests, content digests, JSON Lines
artifacts, and checksum-verified replay.

Snapshots are self-validating and immutable: the snapshot id is a digest of
the data content and declared semantics (never of wall-clock creation or
retrieval times), and replay verifies every artifact checksum before any
record is parsed. Corruption is a typed integrity error, never a silent
fallback. A research run may only claim reproducibility when its full input
is reachable through this immutable manifest.
"""

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, datetime
from hashlib import sha256
from pathlib import Path
from types import MappingProxyType
from typing import Final

from systematic_investing.data.contracts import (
    corporate_action_from_dict,
    corporate_action_to_dict,
    daily_bar_from_dict,
    daily_bar_to_dict,
    tradability_status_from_dict,
    tradability_status_to_dict,
    trading_session_from_dict,
    trading_session_to_dict,
)
from systematic_investing.data.quality import CanonicalDataset
from systematic_investing.domain.identifiers import InstrumentId, require_session_date
from systematic_investing.domain.market import (
    CANONICAL_RECORD_SCHEMA_VERSION,
    AvailabilityBasis,
)

SNAPSHOT_SCHEMA_VERSION: Final[str] = "v2"
ADJUSTMENT_POLICY_RAW_WITH_PIT_FACTORS: Final[str] = "RAW_WITH_POINT_IN_TIME_FACTORS"


class SnapshotError(Exception):
    """Base class for snapshot persistence/replay errors."""


class InvalidSnapshotManifestError(SnapshotError):
    """Raised when a manifest violates its versioned contract."""


class SnapshotIntegrityError(SnapshotError):
    """Raised when stored content does not match the recorded identity."""


def _require_text(value, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise InvalidSnapshotManifestError(f"{field_name} must be a non-empty string")
    return value


def _require_aware(value, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise InvalidSnapshotManifestError(
            f"{field_name} must be a timezone-aware datetime, got {value!r}"
        )
    return value


def _digest(lines) -> str:
    return sha256("\n".join(lines).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SnapshotAvailabilityPolicy:
    """Declared availability semantics: which bases are allowed and how
    UNKNOWN availability is handled."""

    allowed_bases: frozenset
    unknown_handling: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "allowed_bases", frozenset(self.allowed_bases))
        for basis in self.allowed_bases:
            if not isinstance(basis, AvailabilityBasis):
                raise InvalidSnapshotManifestError(
                    f"allowed_bases must contain AvailabilityBasis members, got {basis!r}"
                )
        if self.unknown_handling not in ("explicit", "reject"):
            raise InvalidSnapshotManifestError(
                f"unknown_handling must be 'explicit' or 'reject', got {self.unknown_handling!r}"
            )

    def render(self) -> str:
        return (
            ",".join(sorted(basis.value for basis in self.allowed_bases))
            + "|"
            + self.unknown_handling
        )


@dataclass(frozen=True)
class SnapshotArtifact:
    """One immutable artifact partition with its content checksum."""

    logical_partition: str
    checksum: str
    row_count: int

    def __post_init__(self) -> None:
        _require_text(self.logical_partition, "logical_partition")
        _require_text(self.checksum, "checksum")
        if not isinstance(self.row_count, int) or isinstance(self.row_count, bool):
            raise InvalidSnapshotManifestError("row_count must be an integer")
        if self.row_count < 0:
            raise InvalidSnapshotManifestError("row_count must be non-negative")

    def render(self) -> str:
        return f"{self.logical_partition}:{self.checksum}:{self.row_count}"


def snapshot_id_of(
    *,
    knowledge_cutoff: datetime,
    provider_name: str,
    provider_version: str | None,
    adapter_version: str,
    schemas: Mapping[str, str],
    scope_instrument_ids: tuple[InstrumentId, ...],
    scope_start: date,
    scope_end: date,
    adjustment_policy: str,
    availability_policy: SnapshotAvailabilityPolicy,
    artifacts: tuple[SnapshotArtifact, ...],
    quality_report_id: str | None,
    quality_status: str | None,
) -> str:
    """Content digest over data semantics: deliberately excludes the
    wall-clock ``created_at``/``retrieved_at`` so identical content acquired
    at different times shares one identity, while any data, metadata,
    availability-semantics, or artifact change yields a new id."""
    lines = [
        f"snapshot_schema_version={SNAPSHOT_SCHEMA_VERSION}",
        f"knowledge_cutoff={knowledge_cutoff.isoformat()}",
        f"provider={provider_name},{provider_version}",
        f"adapter_version={adapter_version}",
        "schemas=" + ",".join(f"{kind}:{version}" for kind, version in sorted(schemas.items())),
        "scope="
        + ",".join(str(item) for item in sorted(scope_instrument_ids))
        + f"|{scope_start.isoformat()},{scope_end.isoformat()}",
        f"adjustment_policy={adjustment_policy}",
        f"availability_policy={availability_policy.render()}",
        f"quality_report_id={quality_report_id}",
        f"quality_status={quality_status}",
    ]
    for artifact in sorted(artifacts, key=lambda item: item.render()):
        lines.append(f"artifact={artifact.render()}")
    return _digest(lines)


@dataclass(frozen=True)
class DataSnapshotManifest:
    """An immutable, content-derived snapshot identity and manifest."""

    created_at: datetime
    knowledge_cutoff: datetime
    provider_name: str
    provider_version: str | None
    adapter_version: str
    schemas: Mapping[str, str]
    scope_instrument_ids: tuple[InstrumentId, ...]
    scope_start: date
    scope_end: date
    adjustment_policy: str
    availability_policy: SnapshotAvailabilityPolicy
    retrieved_at: datetime
    artifacts: tuple[SnapshotArtifact, ...]
    quality_report_id: str | None = None
    quality_status: str | None = None
    snapshot_schema_version: str = SNAPSHOT_SCHEMA_VERSION
    snapshot_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "schemas", MappingProxyType(dict(self.schemas)))
        if self.snapshot_schema_version != SNAPSHOT_SCHEMA_VERSION:
            raise InvalidSnapshotManifestError(
                f"unsupported snapshot manifest schema version "
                f"{self.snapshot_schema_version!r}"
            )
        _require_aware(self.created_at, "created_at")
        _require_aware(self.knowledge_cutoff, "knowledge_cutoff")
        _require_aware(self.retrieved_at, "retrieved_at")
        _require_text(self.provider_name, "provider_name")
        if self.provider_version is not None:
            _require_text(self.provider_version, "provider_version")
        _require_text(self.adapter_version, "adapter_version")
        if not self.schemas:
            raise InvalidSnapshotManifestError("schemas must be a non-empty mapping")
        if not isinstance(self.scope_instrument_ids, tuple) or not all(
            isinstance(item, InstrumentId) for item in self.scope_instrument_ids
        ):
            raise InvalidSnapshotManifestError(
                "scope_instrument_ids must be a tuple of InstrumentId"
            )
        require_session_date(self.scope_start)
        require_session_date(self.scope_end)
        if self.scope_start > self.scope_end:
            raise InvalidSnapshotManifestError("scope_start must not be after scope_end")
        _require_text(self.adjustment_policy, "adjustment_policy")
        if not isinstance(self.availability_policy, SnapshotAvailabilityPolicy):
            raise InvalidSnapshotManifestError(
                "availability_policy must be a SnapshotAvailabilityPolicy"
            )
        if not isinstance(self.artifacts, tuple) or not all(
            isinstance(item, SnapshotArtifact) for item in self.artifacts
        ):
            raise InvalidSnapshotManifestError("artifacts must be a tuple of SnapshotArtifact")
        for optional in (self.quality_report_id, self.quality_status):
            if optional is not None and (not isinstance(optional, str) or not optional):
                raise InvalidSnapshotManifestError(
                    "quality_report_id/quality_status must be non-empty strings or None"
                )
        if (self.quality_report_id is None) != (self.quality_status is None):
            raise InvalidSnapshotManifestError(
                "quality_report_id and quality_status must be declared together"
            )
        computed = snapshot_id_of(
            knowledge_cutoff=self.knowledge_cutoff,
            provider_name=self.provider_name,
            provider_version=self.provider_version,
            adapter_version=self.adapter_version,
            schemas=self.schemas,
            scope_instrument_ids=self.scope_instrument_ids,
            scope_start=self.scope_start,
            scope_end=self.scope_end,
            adjustment_policy=self.adjustment_policy,
            availability_policy=self.availability_policy,
            artifacts=self.artifacts,
            quality_report_id=self.quality_report_id,
            quality_status=self.quality_status,
        )
        if self.snapshot_id is None:
            object.__setattr__(self, "snapshot_id", computed)
        elif self.snapshot_id != computed:
            raise SnapshotIntegrityError(
                "manifest snapshot_id does not match its declared content"
            )


# --- canonical serialization ------------------------------------------------


def _canonical_json(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


_RECORD_SERIALIZERS: Final[
    dict[str, tuple[Callable, Callable]]
] = {
    "daily_bar": (daily_bar_to_dict, daily_bar_from_dict),
    "trading_session": (trading_session_to_dict, trading_session_from_dict),
    "tradability_status": (tradability_status_to_dict, tradability_status_from_dict),
    "corporate_action": (corporate_action_to_dict, corporate_action_from_dict),
}

_RECORD_KINDS: Final[tuple[str, ...]] = tuple(_RECORD_SERIALIZERS)


def _records_of_kind(dataset: CanonicalDataset, kind: str) -> tuple:
    return {
        "daily_bar": dataset.daily_bars,
        "trading_session": dataset.sessions,
        "tradability_status": dataset.tradability,
        "corporate_action": dataset.corporate_actions,
    }[kind]


def manifest_to_dict(manifest: DataSnapshotManifest) -> dict:
    return {
        "snapshot_schema_version": manifest.snapshot_schema_version,
        "snapshot_id": manifest.snapshot_id,
        "created_at": manifest.created_at.isoformat(),
        "knowledge_cutoff": manifest.knowledge_cutoff.isoformat(),
        "provider_name": manifest.provider_name,
        "provider_version": manifest.provider_version,
        "adapter_version": manifest.adapter_version,
        "schemas": [[kind, version] for kind, version in sorted(manifest.schemas.items())],
        "scope_instrument_ids": [str(item) for item in sorted(manifest.scope_instrument_ids)],
        "scope_start": manifest.scope_start.isoformat(),
        "scope_end": manifest.scope_end.isoformat(),
        "adjustment_policy": manifest.adjustment_policy,
        "availability_policy": {
            "allowed_bases": [
                basis.value for basis in sorted(manifest.availability_policy.allowed_bases)
            ],
            "unknown_handling": manifest.availability_policy.unknown_handling,
        },
        "retrieved_at": manifest.retrieved_at.isoformat(),
        "artifacts": [
            {
                "logical_partition": artifact.logical_partition,
                "checksum": artifact.checksum,
                "row_count": artifact.row_count,
            }
            for artifact in sorted(manifest.artifacts, key=lambda item: item.logical_partition)
        ],
        "quality_report_id": manifest.quality_report_id,
        "quality_status": manifest.quality_status,
    }


def manifest_from_dict(data) -> DataSnapshotManifest:
    if not isinstance(data, dict):
        raise InvalidSnapshotManifestError("manifest payload must be a mapping")
    try:
        return DataSnapshotManifest(
            created_at=datetime.fromisoformat(data["created_at"]),
            knowledge_cutoff=datetime.fromisoformat(data["knowledge_cutoff"]),
            provider_name=data["provider_name"],
            provider_version=data["provider_version"],
            adapter_version=data["adapter_version"],
            schemas={str(kind): str(version) for kind, version in data["schemas"]},
            scope_instrument_ids=tuple(
                InstrumentId.parse(text) for text in data["scope_instrument_ids"]
            ),
            scope_start=date.fromisoformat(data["scope_start"]),
            scope_end=date.fromisoformat(data["scope_end"]),
            adjustment_policy=data["adjustment_policy"],
            availability_policy=SnapshotAvailabilityPolicy(
                allowed_bases=frozenset(
                    AvailabilityBasis(basis)
                    for basis in data["availability_policy"]["allowed_bases"]
                ),
                unknown_handling=data["availability_policy"]["unknown_handling"],
            ),
            retrieved_at=datetime.fromisoformat(data["retrieved_at"]),
            artifacts=tuple(
                SnapshotArtifact(
                    logical_partition=artifact["logical_partition"],
                    checksum=artifact["checksum"],
                    row_count=int(artifact["row_count"]),
                )
                for artifact in data["artifacts"]
            ),
            quality_report_id=data.get("quality_report_id"),
            quality_status=data.get("quality_status"),
            snapshot_id=data["snapshot_id"],
        )
    except SnapshotError:
        raise
    except (KeyError, TypeError, ValueError) as error:
        raise InvalidSnapshotManifestError(f"invalid manifest payload: {error}") from error


@dataclass(frozen=True)
class SnapshotWriter:
    """Writes an immutable snapshot: JSON Lines artifacts plus a manifest."""

    provider_name: str
    provider_version: str | None
    adapter_version: str

    def persist(
        self,
        dataset: CanonicalDataset,
        *,
        snapshot_dir,
        created_at: datetime,
        knowledge_cutoff: datetime,
        retrieved_at: datetime,
        quality_report_id: str | None = "sha256:" + "0" * 64,
        quality_status: str | None = "PASS",
    ) -> DataSnapshotManifest:
        if not dataset.daily_bars:
            raise InvalidSnapshotManifestError(
                "a snapshot requires at least one daily bar to scope its identity"
            )
        directory = Path(snapshot_dir)
        manifest_path = directory / "manifest.json"
        if manifest_path.exists():
            raise SnapshotIntegrityError(
                f"snapshot {manifest_path} already exists; snapshots are immutable"
            )
        artifacts_dir = directory / "artifacts"
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        artifacts: list[SnapshotArtifact] = []
        for kind in _RECORD_KINDS:
            to_dict, _ = _RECORD_SERIALIZERS[kind]
            records = _records_of_kind(dataset, kind)
            lines = sorted(_canonical_json(to_dict(record)) for record in records)
            content = ("\n".join(lines) + "\n").encode("utf-8") if records else b""
            file_path = artifacts_dir / f"{kind}.jsonl"
            file_path.write_bytes(content)
            artifacts.append(
                SnapshotArtifact(
                    logical_partition=kind,
                    checksum=sha256(content).hexdigest(),
                    row_count=len(records),
                )
            )
        manifest = DataSnapshotManifest(
            created_at=created_at,
            knowledge_cutoff=knowledge_cutoff,
            provider_name=self.provider_name,
            provider_version=self.provider_version,
            adapter_version=self.adapter_version,
            schemas={kind: CANONICAL_RECORD_SCHEMA_VERSION for kind in _RECORD_KINDS},
            scope_instrument_ids=tuple(sorted({bar.instrument_id for bar in dataset.daily_bars})),
            scope_start=min(bar.session_date for bar in dataset.daily_bars),
            scope_end=max(bar.session_date for bar in dataset.daily_bars),
            adjustment_policy=ADJUSTMENT_POLICY_RAW_WITH_PIT_FACTORS,
            availability_policy=SnapshotAvailabilityPolicy(
                allowed_bases=frozenset(_observed_bases(dataset)),
                unknown_handling="explicit",
            ),
            retrieved_at=retrieved_at,
            artifacts=tuple(sorted(artifacts, key=lambda item: item.logical_partition)),
            quality_report_id=quality_report_id,
            quality_status=quality_status,
        )
        manifest_path.write_bytes(_canonical_json(manifest_to_dict(manifest)).encode("utf-8"))
        return manifest


def _observed_bases(dataset: CanonicalDataset) -> list[AvailabilityBasis]:
    bases: set[AvailabilityBasis] = set()
    for record in (
        *dataset.daily_bars,
        *dataset.tradability,
        *dataset.corporate_actions,
    ):
        bases.add(record.availability.availability_basis)
    return sorted(bases, key=lambda basis: basis.value)


@dataclass(frozen=True)
class SnapshotReader:
    """Load a snapshot directory, verifying content against the manifest."""

    def load(self, snapshot_dir) -> tuple[DataSnapshotManifest, CanonicalDataset]:
        directory = Path(snapshot_dir)
        manifest_path = directory / "manifest.json"
        if not manifest_path.exists():
            raise SnapshotIntegrityError(f"no manifest at {manifest_path}")
        manifest = manifest_from_dict(json.loads(manifest_path.read_text(encoding="utf-8")))
        records_by_kind: dict[str, list] = {kind: [] for kind in _RECORD_KINDS}
        for artifact in manifest.artifacts:
            file_path = directory / "artifacts" / f"{artifact.logical_partition}.jsonl"
            if not file_path.exists():
                raise SnapshotIntegrityError(f"missing artifact {file_path}")
            content = file_path.read_bytes()
            if sha256(content).hexdigest() != artifact.checksum:
                raise SnapshotIntegrityError(
                    f"artifact checksum mismatch for {file_path}: manifest records "
                    f"{artifact.checksum}"
                )
            _, from_dict = _RECORD_SERIALIZERS[artifact.logical_partition]
            for line in content.decode("utf-8").splitlines():
                if not line:
                    continue
                try:
                    record = from_dict(json.loads(line))
                except Exception as error:
                    raise SnapshotIntegrityError(
                        f"artifact record in {file_path} does not parse: {error}"
                    ) from error
                records_by_kind[artifact.logical_partition].append(record)
        dataset = CanonicalDataset(
            daily_bars=tuple(records_by_kind["daily_bar"]),
            sessions=tuple(records_by_kind["trading_session"]),
            tradability=tuple(records_by_kind["tradability_status"]),
            corporate_actions=tuple(records_by_kind["corporate_action"]),
            rule_candidates=(),
        )
        return manifest, dataset
