"""Thin append-only Research catalog.

The catalog only indexes immutable artifacts: lineage, artifact type,
relative reference, status, and content digests, under a strictly increasing
zero-padded sequence. Entries are never edited or deleted; a sequence that
already exists fails closed. Verification recomputes every recorded digest
from the artifact bytes so any mutation is detected.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from systematic_investing.research.artifacts import (
    digest_of_bytes,
    read_json,
    write_new_json,
)

CATALOG_SCHEMA_VERSION: Final[str] = "research-catalog-1"
_SEQUENCE_DIGITS: Final[int] = 6


class CatalogError(Exception):
    """Base class for catalog contract errors."""


def _sequence_path(catalog_dir: Path, sequence: int) -> Path:
    return catalog_dir / f"{sequence:0{_SEQUENCE_DIGITS}d}.json"


def _existing_sequences(catalog_dir: Path) -> tuple[int, ...]:
    directory = Path(catalog_dir)
    if not directory.exists():
        return ()
    sequences: list[int] = []
    for path in directory.glob("*.json"):
        try:
            sequences.append(int(path.stem))
        except ValueError as error:
            raise CatalogError(
                f"catalog contains a non-numeric entry name {path.name}"
            ) from error
    return tuple(sorted(sequences))


def append_entry(
    catalog_dir: Path,
    entry: Mapping[str, object],
    *,
    sequence: int | None = None,
) -> dict[str, object]:
    """Append one create-new catalog entry with the next sequence number.

    ``sequence`` may only be passed as an explicit expected value by callers
    verifying no race; any mismatch fails closed instead of reusing a
    sequence.
    """
    directory = Path(catalog_dir)
    existing = _existing_sequences(directory)
    next_sequence = (max(existing) + 1) if existing else 1
    if next_sequence in existing:
        raise CatalogError(f"catalog sequence {next_sequence} already exists")
    if sequence is not None and sequence != next_sequence:
        raise CatalogError(
            f"catalog sequence {sequence} cannot be appended: the next free "
            f"sequence is {next_sequence}; sequences are never reused"
        )
    payload: dict[str, object] = {
        **dict(entry),
        "catalog_schema_version": CATALOG_SCHEMA_VERSION,
        "sequence": next_sequence,
    }
    write_new_json(_sequence_path(directory, next_sequence), payload)
    return payload


def read_entries(catalog_dir: Path) -> tuple[dict[str, object], ...]:
    """All catalog entries ordered by sequence.

    Sequences must be unique and contiguous from 1; gaps or duplicates mean
    the catalog was tampered with and fail closed.
    """
    directory = Path(catalog_dir)
    existing = _existing_sequences(directory)
    if existing and existing != tuple(range(1, len(existing) + 1)):
        raise CatalogError(
            f"catalog sequences are not contiguous from 1: {existing}"
        )
    entries: list[dict[str, object]] = []
    for sequence in existing:
        payload = read_json(_sequence_path(directory, sequence))
        recorded = payload.get("sequence")
        if not isinstance(recorded, int) or recorded != sequence:
            raise CatalogError(
                f"catalog entry {sequence} records sequence {recorded!r}"
            )
        entries.append(payload)
    return tuple(entries)


@dataclass(frozen=True)
class CatalogVerifyReport:
    """Outcome of catalog verification with located findings."""

    status: str
    findings: tuple[str, ...]


def verify_catalog(catalog_dir: Path, experiments_root: Path) -> CatalogVerifyReport:
    """Verify every entry's referenced artifact digests against content.

    A missing artifact, a digest mismatch, or an unreadable catalog fails
    verification; findings name the offending paths.
    """
    findings: list[str] = []
    try:
        entries = read_entries(catalog_dir)
    except CatalogError as error:
        return CatalogVerifyReport(status="FAIL", findings=(str(error),))
    for entry in entries:
        reference = entry.get("ref")
        digests = entry.get("digests")
        if not isinstance(reference, str) or not reference:
            findings.append(f"catalog sequence {entry.get('sequence')} has no ref")
            continue
        artifact_path = Path(experiments_root) / reference
        if not artifact_path.exists():
            findings.append(f"missing artifact {reference}")
            continue
        if not isinstance(digests, dict):
            findings.append(f"catalog entry {reference} has no digests")
            continue
        for name in sorted(digests):
            recorded = digests[name]
            if not isinstance(recorded, str):
                findings.append(
                    f"catalog digest {name} for {reference} is not a string"
                )
                continue
            try:
                content = artifact_path.read_bytes()
            except OSError as error:
                findings.append(f"artifact {reference} unreadable: {error}")
                continue
            actual = digest_of_bytes(content)
            if actual != recorded:
                findings.append(
                    f"digest mismatch for {reference} ({name}): recorded "
                    f"{recorded}, content {actual}"
                )
    status = "FAIL" if findings else "PASS"
    return CatalogVerifyReport(status=status, findings=tuple(findings))
