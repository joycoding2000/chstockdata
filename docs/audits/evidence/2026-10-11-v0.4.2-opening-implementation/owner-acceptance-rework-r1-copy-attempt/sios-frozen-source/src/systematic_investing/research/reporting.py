"""Immutable M1 source-flight, period, and asset-class reporting helpers.

The module keeps the Task 7 terminal asset-class decision auditable while
adding the Task 8 source provenance and descriptive yearly/subperiod output.
Neither report can replace a gate verdict or introduce a regime router.
"""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Final
from urllib.parse import urlparse

from systematic_investing.domain.ledger import CashLedgerEntry, NavPoint
from systematic_investing.metrics.performance import MetricsError, compute_metrics
from systematic_investing.research.artifacts import (
    ArtifactIntegrityError,
    canonical_json_bytes,
    digest_of_bytes,
    read_json,
    write_new_json,
)
from systematic_investing.research.catalog import append_entry, read_entries
from systematic_investing.research.oos import (
    NO_OOS_ELIGIBLE_CANDIDATE,
    OOS_VERDICT_REJECTED_OOS,
    OOS_VERDICT_SURVIVOR,
    OosError,
)

ASSET_CLASS_OUTCOME_SCHEMA_VERSION: Final[str] = "research-oos-outcome-1"
OUTCOME_PATH_DIRNAME: Final[str] = "outcomes"
OUTCOME_STATUSES: frozenset[str] = frozenset(
    {
        NO_OOS_ELIGIBLE_CANDIDATE,
        OOS_VERDICT_SURVIVOR,
        OOS_VERDICT_REJECTED_OOS,
    }
)
ASSET_CLASSES: frozenset[str] = frozenset({"ETF", "STOCK"})

SOURCE_FLIGHT_SCHEMA_VERSION: Final[str] = "m1-ai-source-flight-1"
SOURCE_SCREEN_SCHEMA_VERSION: Final[str] = "research-source-screen-1"
SOURCE_SCREEN_PASS: Final[str] = "SCREEN_PASS"
SOURCE_SCREEN_REJECTED: Final[str] = "REJECTED_BEFORE_IMPLEMENTATION"
SOURCE_SCREEN_VERDICTS: frozenset[str] = frozenset(
    {SOURCE_SCREEN_PASS, SOURCE_SCREEN_REJECTED}
)
PERIOD_REPORT_SCHEMA_VERSION: Final[str] = "research-period-report-1"


class SourceFlightError(ValueError):
    """Raised when an AI source-flight record violates its small contract."""


def _source_value(payload: Mapping[str, object], *keys: str) -> object | None:
    for key in keys:
        if key in payload:
            return payload[key]
    return None


def _source_screen_parts(payload: Mapping[str, object]) -> tuple[object | None, object]:
    nested = payload.get("cheap_screen")
    if isinstance(nested, Mapping):
        return nested.get("verdict"), nested.get("reason_codes", [])
    return (
        _source_value(payload, "cheap_screen_verdict"),
        _source_value(payload, "cheap_screen_reason_codes") or [],
    )


def validate_source_flight(payload: object) -> tuple[str, ...]:
    """Return stable reason codes for a pre-implementation source record.

    This is deliberately a structural screen.  It records provenance and a
    project-authored hypothesis, but it never interprets the source as proof
    that a strategy works and never requires a regime classifier.
    """
    if not isinstance(payload, Mapping):
        return ("SOURCE_RECORD_MUST_BE_OBJECT",)

    reasons: list[str] = []
    schema_version = payload.get("source_flight_schema_version")
    if schema_version is None:
        reasons.append("MISSING_SOURCE_FLIGHT_SCHEMA_VERSION")
    elif schema_version != SOURCE_FLIGHT_SCHEMA_VERSION:
        reasons.append("UNSUPPORTED_SOURCE_FLIGHT_SCHEMA_VERSION")

    text_fields: tuple[tuple[str, tuple[str, ...]], ...] = (
        ("source_id", ("source_id",)),
        ("url", ("url",)),
        ("title", ("title",)),
        ("author_or_publisher", ("author_or_publisher", "author", "publisher")),
        (
            "license_or_rights_posture",
            ("license_or_rights_posture", "rights_posture", "license"),
        ),
        ("summary", ("summary", "project_summary")),
        ("hypothesis", ("hypothesis", "falsifiable_hypothesis")),
        ("asset", ("asset", "asset_class")),
        ("horizon", ("horizon",)),
    )
    text_values: dict[str, str] = {}
    for canonical_name, keys in text_fields:
        value = _source_value(payload, *keys)
        if not isinstance(value, str) or not value.strip():
            reasons.append(f"MISSING_{canonical_name.upper()}")
        else:
            text_values[canonical_name] = value

    source_id = text_values.get("source_id")
    if source_id is not None and (
        source_id in {".", ".."} or "/" in source_id or "\\" in source_id
    ):
        reasons.append("INVALID_SOURCE_ID")

    url = text_values.get("url")
    if url is not None:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            reasons.append("INVALID_URL")

    accessed = _source_value(payload, "accessed_date", "accessed_on")
    if accessed is None:
        reasons.append("MISSING_ACCESSED_DATE")
    elif not isinstance(accessed, str):
        reasons.append("INVALID_ACCESSED_DATE")
    else:
        try:
            date.fromisoformat(accessed)
        except ValueError:
            reasons.append("INVALID_ACCESSED_DATE")

    requirements = _source_value(payload, "data_requirements")
    if not isinstance(requirements, list) or not requirements:
        reasons.append("MISSING_DATA_REQUIREMENTS")
    elif not all(isinstance(item, str) and item.strip() for item in requirements):
        reasons.append("INVALID_DATA_REQUIREMENTS")

    screen_verdict, screen_reasons = _source_screen_parts(payload)
    if not isinstance(screen_verdict, str) or not screen_verdict:
        reasons.append("MISSING_CHEAP_SCREEN_VERDICT")
    elif screen_verdict not in SOURCE_SCREEN_VERDICTS:
        reasons.append("INVALID_CHEAP_SCREEN_VERDICT")
    if not isinstance(screen_reasons, list) or not all(
        isinstance(item, str) and item.strip() for item in screen_reasons
    ):
        reasons.append("INVALID_CHEAP_SCREEN_REASON_CODES")
    elif screen_verdict == SOURCE_SCREEN_REJECTED and not screen_reasons:
        reasons.append("CHEAP_SCREEN_REJECTION_REQUIRES_REASON")

    return tuple(dict.fromkeys(reasons))


@dataclass(frozen=True)
class SourceFlightRecord:
    """Auditable provenance and hypothesis metadata written before code."""

    source_id: str
    url: str
    title: str
    author_or_publisher: str
    accessed_date: date
    license_or_rights_posture: str
    summary: str
    hypothesis: str
    asset: str
    horizon: str
    data_requirements: tuple[str, ...]
    cheap_screen_verdict: str
    cheap_screen_reason_codes: tuple[str, ...] = ()

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> "SourceFlightRecord":
        reasons = validate_source_flight(payload)
        if reasons:
            raise SourceFlightError(
                "source flight record is invalid: " + ", ".join(reasons)
            )

        def text_field(*keys: str) -> str:
            value = _source_value(payload, *keys)
            if not isinstance(value, str):
                raise SourceFlightError(f"source flight field {keys[0]!r} is not text")
            return value

        screen_verdict, screen_reasons = _source_screen_parts(payload)
        if not isinstance(screen_verdict, str) or not isinstance(screen_reasons, list):
            raise SourceFlightError("source flight cheap-screen fields are invalid")
        accessed = _source_value(payload, "accessed_date", "accessed_on")
        requirements = _source_value(payload, "data_requirements")
        if not isinstance(accessed, str) or not isinstance(requirements, list):
            raise SourceFlightError("source flight date or requirements are invalid")
        return cls(
            source_id=text_field("source_id"),
            url=text_field("url"),
            title=text_field("title"),
            author_or_publisher=text_field(
                "author_or_publisher", "author", "publisher"
            ),
            accessed_date=date.fromisoformat(accessed),
            license_or_rights_posture=text_field(
                "license_or_rights_posture", "rights_posture", "license"
            ),
            summary=text_field("summary", "project_summary"),
            hypothesis=text_field("hypothesis", "falsifiable_hypothesis"),
            asset=text_field("asset", "asset_class"),
            horizon=text_field("horizon"),
            data_requirements=tuple(str(item) for item in requirements),
            cheap_screen_verdict=screen_verdict,
            cheap_screen_reason_codes=tuple(str(item) for item in screen_reasons),
        )

    def to_payload(self) -> dict[str, object]:
        return {
            "source_flight_schema_version": SOURCE_FLIGHT_SCHEMA_VERSION,
            "source_id": self.source_id,
            "url": self.url,
            "title": self.title,
            "author_or_publisher": self.author_or_publisher,
            "accessed_date": self.accessed_date.isoformat(),
            "license_or_rights_posture": self.license_or_rights_posture,
            "summary": self.summary,
            "hypothesis": self.hypothesis,
            "asset": self.asset,
            "horizon": self.horizon,
            "data_requirements": list(self.data_requirements),
            "cheap_screen_verdict": self.cheap_screen_verdict,
            "cheap_screen_reason_codes": list(self.cheap_screen_reason_codes),
        }


def screen_source_record(payload: object) -> tuple[str, tuple[str, ...]]:
    """Cheap-screen one source record without implementing its hypothesis."""
    reasons = validate_source_flight(payload)
    if reasons:
        return SOURCE_SCREEN_REJECTED, reasons
    if not isinstance(payload, Mapping):
        return SOURCE_SCREEN_REJECTED, ("SOURCE_RECORD_MUST_BE_OBJECT",)
    record = SourceFlightRecord.from_payload(payload)
    return record.cheap_screen_verdict, record.cheap_screen_reason_codes


def persist_source_screen(
    root: Path,
    *,
    source_id: str,
    source_digest: str,
    verdict: str,
    reason_codes: Sequence[str],
) -> tuple[Path, str]:
    """Persist one immutable source-screen result under a safe source id."""
    if verdict not in SOURCE_SCREEN_VERDICTS:
        raise SourceFlightError(f"unsupported source-screen verdict {verdict!r}")
    if not source_digest.startswith("sha256:"):
        raise SourceFlightError("source_digest must be a sha256 digest")
    payload: dict[str, object] = {
        "source_screen_schema_version": SOURCE_SCREEN_SCHEMA_VERSION,
        "source_id": source_id,
        "source_digest": source_digest,
        "verdict": verdict,
        "reason_codes": list(reason_codes),
    }
    digest = digest_of_bytes(canonical_json_bytes(payload))
    safe_source_id = (
        source_id
        if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", source_id)
        else "unknown-source"
    )
    path = Path(root) / "source-flights" / safe_source_id / f"{digest[7:23]}.json"
    if path.exists():
        existing = read_json(path)
        if canonical_json_bytes(existing) != canonical_json_bytes(payload):
            raise SourceFlightError(
                f"source-screen artifact {path} exists with different content"
            )
        return path, digest_of_bytes(path.read_bytes())
    try:
        return path, write_new_json(path, payload)
    except ArtifactIntegrityError as error:
        raise SourceFlightError(f"source-screen artifact conflict: {error}") from error


def _metrics_summary(
    nav_points: Sequence[NavPoint], cash_entries: Sequence[CashLedgerEntry]
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


def _period_entry(
    period: str,
    start: date,
    end: date,
    nav_points: Sequence[NavPoint],
    cash_entries: Sequence[CashLedgerEntry],
) -> dict[str, object]:
    selected_points = tuple(
        point for point in nav_points if start <= point.session_date <= end
    )
    payload: dict[str, object] = {
        "period": period,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "observation_count": len(selected_points),
    }
    if len(selected_points) < 3:
        payload.update(
            {
                "status": "INSUFFICIENT_HISTORY",
                "metrics": None,
                "reason_code": "INSUFFICIENT_HISTORY",
            }
        )
        return payload
    selected_cash = tuple(
        entry for entry in cash_entries if start <= entry.session_date <= end
    )
    try:
        metrics = _metrics_summary(selected_points, selected_cash)
    except MetricsError as error:
        payload.update(
            {
                "status": "METRICS_FAILED",
                "metrics": None,
                "reason_code": type(error).__name__,
            }
        )
        return payload
    payload.update({"status": "COMPLETED", "metrics": metrics})
    return payload


def build_yearly_subperiod_report(
    nav_points: Sequence[NavPoint],
    *,
    cash_entries: Sequence[CashLedgerEntry] = (),
) -> dict[str, object]:
    """Build deterministic calendar-year and half-year metric breakdowns.

    The report is intentionally descriptive: it does not infer, require, or
    expose a ``BULL/SIDEWAYS/BEAR`` classifier and cannot change targets or
    execution outcomes.
    """
    ordered = tuple(sorted(nav_points, key=lambda point: point.session_date))
    years = tuple(sorted({point.session_date.year for point in ordered}))
    yearly = [
        _period_entry(
            str(year),
            date(year, 1, 1),
            date(year, 12, 31),
            ordered,
            tuple(cash_entries),
        )
        for year in years
    ]
    subperiods: list[dict[str, object]] = []
    for year in years:
        subperiods.extend(
            (
                _period_entry(
                    f"{year}-H1",
                    date(year, 1, 1),
                    date(year, 6, 30),
                    ordered,
                    tuple(cash_entries),
                ),
                _period_entry(
                    f"{year}-H2",
                    date(year, 7, 1),
                    date(year, 12, 31),
                    ordered,
                    tuple(cash_entries),
                ),
            )
        )
    return {
        "report_schema_version": PERIOD_REPORT_SCHEMA_VERSION,
        "yearly": yearly,
        "subperiods": subperiods,
    }


@dataclass(frozen=True)
class AssetClassOutcome:
    """The one terminal M1 OOS outcome allowed for an asset class."""

    asset_class: str
    status: str
    candidate_id: str | None = None
    selected_variant_id: str | None = None
    freeze_id: str | None = None
    reason_codes: tuple[str, ...] = ()
    known_limitations: tuple[str, ...] = ()
    result_digest: str | None = None

    def __post_init__(self) -> None:
        if self.asset_class not in ASSET_CLASSES:
            raise OosError(
                f"ASSET_CLASS_OUTCOME_INVALID: unsupported asset class "
                f"{self.asset_class!r}"
            )
        if self.status not in OUTCOME_STATUSES:
            raise OosError(
                f"ASSET_CLASS_OUTCOME_INVALID: unsupported outcome status "
                f"{self.status!r}"
            )
        for field_name, values in (
            ("reason_codes", self.reason_codes),
            ("known_limitations", self.known_limitations),
        ):
            if not all(isinstance(value, str) and value for value in values):
                raise OosError(
                    f"ASSET_CLASS_OUTCOME_INVALID: {field_name} must contain "
                    "non-empty strings"
                )

    def to_payload(self) -> dict[str, object]:
        return {
            "outcome_schema_version": ASSET_CLASS_OUTCOME_SCHEMA_VERSION,
            "asset_class": self.asset_class,
            "status": self.status,
            "candidate_id": self.candidate_id,
            "selected_variant_id": self.selected_variant_id,
            "freeze_id": self.freeze_id,
            "result_digest": self.result_digest,
            "reason_codes": list(self.reason_codes),
            "known_limitations": list(self.known_limitations),
        }

    @classmethod
    def from_payload(cls, payload: dict[str, object]) -> "AssetClassOutcome":
        if payload.get("outcome_schema_version") != ASSET_CLASS_OUTCOME_SCHEMA_VERSION:
            raise OosError(
                "ASSET_CLASS_OUTCOME_INVALID: unsupported outcome schema version"
            )
        asset_class = payload.get("asset_class")
        status = payload.get("status")
        if not isinstance(asset_class, str) or not isinstance(status, str):
            raise OosError(
                "ASSET_CLASS_OUTCOME_INVALID: asset_class and status are required"
            )
        reason_codes = payload.get("reason_codes", [])
        limitations = payload.get("known_limitations", [])
        if not isinstance(reason_codes, list) or not all(
            isinstance(value, str) for value in reason_codes
        ):
            raise OosError(
                "ASSET_CLASS_OUTCOME_INVALID: reason_codes must be a string list"
            )
        if not isinstance(limitations, list) or not all(
            isinstance(value, str) for value in limitations
        ):
            raise OosError(
                "ASSET_CLASS_OUTCOME_INVALID: known_limitations must be a string list"
            )

        optional_text: dict[str, str | None] = {}
        for field_name in (
            "candidate_id",
            "selected_variant_id",
            "freeze_id",
            "result_digest",
        ):
            value = payload.get(field_name)
            if value is not None and not isinstance(value, str):
                raise OosError(
                    f"ASSET_CLASS_OUTCOME_INVALID: {field_name} must be a string or null"
                )
            optional_text[field_name] = value
        return cls(
            asset_class=asset_class,
            status=status,
            candidate_id=optional_text["candidate_id"],
            selected_variant_id=optional_text["selected_variant_id"],
            freeze_id=optional_text["freeze_id"],
            result_digest=optional_text["result_digest"],
            reason_codes=tuple(reason_codes),
            known_limitations=tuple(limitations),
        )


def _outcome_candidates(root: Path, asset_class: str) -> tuple[Path, ...]:
    directory = Path(root) / OUTCOME_PATH_DIRNAME
    if not directory.exists():
        return ()
    matches: list[Path] = []
    for path in sorted(directory.glob("*.json")):
        payload = read_json(path)
        if payload.get("asset_class") == asset_class:
            matches.append(path)
    return tuple(matches)


def asset_class_outcome_path(root: Path, asset_class: str) -> Path:
    if asset_class not in ASSET_CLASSES:
        raise OosError(
            f"ASSET_CLASS_OUTCOME_INVALID: unsupported asset class {asset_class!r}"
        )
    return Path(root) / OUTCOME_PATH_DIRNAME / f"{asset_class}.json"


def read_asset_class_outcome(
    root: Path,
    asset_class: str,
) -> tuple[Path, AssetClassOutcome] | None:
    """Read the existing terminal outcome, if any."""
    matches = _outcome_candidates(Path(root), asset_class)
    if len(matches) > 1:
        raise OosError(
            f"ASSET_CLASS_OUTCOME_AMBIGUOUS: {asset_class} has multiple "
            "terminal outcome artifacts"
        )
    if not matches:
        return None
    path = matches[0]
    return path, AssetClassOutcome.from_payload(read_json(path))


def _catalog_outcome_entry(root: Path, path: Path) -> dict[str, object] | None:
    catalog_dir = Path(root) / "catalog"
    reference = path.relative_to(root).as_posix()
    for entry in read_entries(catalog_dir):
        if entry.get("artifact_type") == "OOS_OUTCOME" and entry.get("ref") == reference:
            return entry
    return None


def persist_asset_class_outcome(
    root: Path,
    outcome: AssetClassOutcome,
) -> tuple[Path, str]:
    """Persist one terminal outcome, confirming identical retries only.

    A different status, candidate, or freeze for the same asset class is an
    immutable-artifact conflict.  Identical retries do not append another
    catalog entry, so the asset class still has exactly one canonical record.
    """
    payload = outcome.to_payload()
    existing = read_asset_class_outcome(root, outcome.asset_class)
    path = existing[0] if existing is not None else asset_class_outcome_path(
        root, outcome.asset_class
    )
    if existing is not None:
        existing_payload = read_json(path)
        if canonical_json_bytes(existing_payload) != canonical_json_bytes(payload):
            raise OosError(
                f"OOS_ASSET_OUTCOME_ALREADY_RECORDED: {outcome.asset_class} "
                "already has a different terminal OOS outcome"
            )
        digest = digest_of_bytes(path.read_bytes())
    else:
        try:
            digest = write_new_json(path, payload)
        except ArtifactIntegrityError as error:
            raise OosError(
                f"OOS_ASSET_OUTCOME_IMMUTABILITY_CONFLICT: {error}"
            ) from error

    if _catalog_outcome_entry(root, path) is None:
        append_entry(
            Path(root) / "catalog",
            {
                "lineage_id": outcome.candidate_id or "",
                "artifact_type": "OOS_OUTCOME",
                "ref": path.relative_to(root).as_posix(),
                "status": outcome.status,
                "digests": {"outcome": digest},
            },
        )
    return path, digest
