"""Immutable Research artifact persistence: canonical JSON, content digests,
create-new directories and files.

Every artifact is written once; an existing path is never overwritten. The
digest of an artifact is the sha256 of its canonical JSON bytes, so a later
content change always breaks catalog verification. Nothing here records wall
clock time: run identity stays content-derived and rerun-stable.
"""

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Final

ARTIFACT_SCHEMA_VERSION: Final[str] = "research-artifact-1"

# A run directory is complete only with all three artifacts; anything less is
# a half-persisted run that must never be counted or re-attempted silently.
RUN_ARTIFACT_FILES: Final[tuple[str, ...]] = (
    "manifest.json",
    "result.json",
    "report.json",
)


class ArtifactError(Exception):
    """Base class for artifact persistence errors."""


class ArtifactIntegrityError(ArtifactError):
    """Raised when an artifact path already exists or its content does not
    match its recorded digest; artifacts are immutable."""


def canonical_json_bytes(payload: Mapping[str, object]) -> bytes:
    """Deterministic JSON bytes for an artifact payload."""
    rendered = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False)
    return rendered.encode("utf-8")


def digest_of_bytes(content: bytes) -> str:
    """Canonical content digest of artifact bytes."""
    import hashlib

    return "sha256:" + hashlib.sha256(content).hexdigest()


def write_new_json(path: Path, payload: Mapping[str, object]) -> str:
    """Write one create-new JSON artifact and return its digest.

    The parent directory is created as needed; an existing path fails closed
    instead of being overwritten.
    """
    target = Path(path)
    if target.exists():
        raise ArtifactIntegrityError(
            f"artifact {target} already exists; research artifacts are immutable"
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    content = canonical_json_bytes(payload)
    target.write_bytes(content)
    return digest_of_bytes(content)


def create_new_directory(path: Path) -> Path:
    """Create one directory or fail if it already exists."""
    target = Path(path)
    if target.exists():
        raise ArtifactIntegrityError(
            f"artifact directory {target} already exists; research artifacts "
            "are immutable"
        )
    target.mkdir(parents=True, exist_ok=True)
    return target


def read_json(path: Path) -> dict[str, object]:
    target = Path(path)
    if not target.exists():
        raise ArtifactIntegrityError(f"artifact {target} does not exist")
    try:
        parsed = json.loads(target.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ArtifactIntegrityError(
            f"artifact {target} is not valid JSON: {error}"
        ) from error
    if not isinstance(parsed, dict):
        raise ArtifactIntegrityError(f"artifact {target} must be a JSON mapping")
    return parsed


def run_id_for(manifest_identity_digest: str, attempt: int) -> str:
    """Deterministic, opaque run-directory id for one manifest attempt."""
    import hashlib

    seed = f"{manifest_identity_digest}|attempt={attempt}".encode()
    return "run-" + hashlib.sha256(seed).hexdigest()[:16]


def next_attempt_for(runs_root: Path, manifest_identity_digest: str) -> int:
    """One plus the number of already-persisted attempts of the manifest.

    Every existing run directory must be complete (manifest, result, and
    report): a half-persisted run fails closed loudly instead of being
    counted, skipped, or silently re-attempted.
    """
    root = Path(runs_root)
    if not root.exists():
        return 1
    attempts = 0
    for run_dir in sorted(root.iterdir()):
        if not run_dir.is_dir():
            continue
        for artifact_name in RUN_ARTIFACT_FILES:
            if not (run_dir / artifact_name).exists():
                raise ArtifactIntegrityError(
                    f"run directory {run_dir} is missing {artifact_name}; a "
                    "half-persisted run can never be counted or re-attempted "
                    "silently"
                )
        payload = read_json(run_dir / "manifest.json")
        if payload.get("identity_digest") == manifest_identity_digest:
            attempts += 1
    return attempts + 1
