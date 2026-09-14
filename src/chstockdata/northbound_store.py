"""F5 北向记录的最小、可迁移 SQLite 存储；查询路径从不发起网络请求。"""

from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterable

from .northbound_data import NorthboundRecord


ARCHIVE_FORMAT = "tradingagents.northbound.archive"
ARCHIVE_VERSION = 1


class NorthboundArchiveError(ValueError):
    """Rejected untrusted archive; its content is never executed."""


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _record_digest(record: dict[str, Any]) -> str:
    """Observation time is provenance, not a source-data revision dimension."""

    return _digest({key: value for key, value in record.items() if key != "observed_at"})


class NorthboundStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), timeout=10, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 10000")
        return conn

    def _initialize(self) -> None:
        with closing(self._connect()) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS northbound_records (
                    business_key TEXT PRIMARY KEY,
                    record_json TEXT NOT NULL,
                    payload_hash TEXT NOT NULL,
                    revision INTEGER NOT NULL CHECK(revision >= 1),
                    first_observed_at TEXT NOT NULL,
                    last_observed_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS northbound_record_revisions (
                    business_key TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    observed_at TEXT NOT NULL,
                    record_json TEXT NOT NULL,
                    payload_hash TEXT NOT NULL,
                    PRIMARY KEY (business_key, revision),
                    FOREIGN KEY (business_key) REFERENCES northbound_records(business_key)
                );
            """)

    @staticmethod
    def _validated(records: Iterable[NorthboundRecord]) -> list[NorthboundRecord]:
        materialized = list(records)
        if not materialized:
            return []
        for record in materialized:
            if not isinstance(record, NorthboundRecord):
                raise ValueError("records must contain NorthboundRecord instances")
            # Revalidation also rejects objects forged through object.__new__.
            NorthboundRecord.from_dict(record.to_dict())
        keys = [record.business_key() for record in materialized]
        if len(keys) != len(set(keys)):
            raise ValueError("batch has duplicate business keys")
        return materialized

    def write(self, records: Iterable[NorthboundRecord]) -> dict[str, int]:
        records = self._validated(records)
        counts = {"inserted": 0, "revised": 0, "unchanged": 0}
        if not records:
            return counts
        with closing(self._connect()) as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                for record in records:
                    business_key = record.business_key()
                    payload = record.to_dict()
                    record_json = _canonical_json(payload)
                    payload_hash = _record_digest(payload)
                    existing = conn.execute(
                        "SELECT payload_hash, revision, first_observed_at FROM northbound_records WHERE business_key = ?",
                        (business_key,),
                    ).fetchone()
                    if existing is None:
                        conn.execute(
                            "INSERT INTO northbound_records VALUES (?, ?, ?, 1, ?, ?)",
                            (business_key, record_json, payload_hash, record.observed_at, record.observed_at),
                        )
                        conn.execute(
                            "INSERT INTO northbound_record_revisions VALUES (?, 1, ?, ?, ?)",
                            (business_key, record.observed_at, record_json, payload_hash),
                        )
                        counts["inserted"] += 1
                    elif existing["payload_hash"] == payload_hash:
                        conn.execute(
                            "UPDATE northbound_records SET record_json = ?, last_observed_at = ? WHERE business_key = ?",
                            (record_json, record.observed_at, business_key),
                        )
                        counts["unchanged"] += 1
                    else:
                        revision = int(existing["revision"]) + 1
                        conn.execute(
                            "UPDATE northbound_records SET record_json = ?, payload_hash = ?, revision = ?, last_observed_at = ? WHERE business_key = ?",
                            (record_json, payload_hash, revision, record.observed_at, business_key),
                        )
                        conn.execute(
                            "INSERT INTO northbound_record_revisions VALUES (?, ?, ?, ?, ?)",
                            (business_key, revision, record.observed_at, record_json, payload_hash),
                        )
                        counts["revised"] += 1
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return counts

    def query(
        self,
        *,
        metric: str | None = None,
        market_scope: str | None = None,
        as_of_before: str | None = None,
        security_id: str | None = None,
    ) -> list[dict[str, Any]]:
        if as_of_before is not None:
            from .northbound_data import _require_date
            _require_date(as_of_before, "as_of_before")
        rows = []
        with closing(self._connect()) as conn:
            for row in conn.execute("SELECT * FROM northbound_records ORDER BY business_key"):
                payload = json.loads(row["record_json"])
                if metric is not None and payload["metric"] != metric:
                    continue
                if market_scope is not None and payload["market_scope"] != market_scope:
                    continue
                if security_id is not None and payload["security_id"] != security_id:
                    continue
                if as_of_before is not None and payload["as_of_date"] > as_of_before:
                    continue
                rows.append({
                    **payload, "business_key": row["business_key"], "revision": row["revision"],
                    "first_observed_at": row["first_observed_at"], "last_observed_at": row["last_observed_at"],
                })
        return rows

    def revisions(self, business_key: str) -> list[dict[str, Any]]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT revision, observed_at, record_json, payload_hash FROM northbound_record_revisions WHERE business_key = ? ORDER BY revision",
                (business_key,),
            ).fetchall()
        return [{"revision": row["revision"], "observed_at": row["observed_at"], "payload_hash": row["payload_hash"], "record": json.loads(row["record_json"])} for row in rows]

    def export_archive(self, path: str | Path) -> Path:
        destination = Path(path)
        records = self.query()
        payload = {
            "format": ARCHIVE_FORMAT,
            "format_version": ARCHIVE_VERSION,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "records": [{key: value for key, value in row.items() if key not in {"business_key", "revision", "first_observed_at", "last_observed_at"}} for row in records],
        }
        payload["checksum_sha256"] = _digest(payload)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(_canonical_json(payload), encoding="utf-8")
        return destination

    def import_archive(self, path: str | Path) -> dict[str, int]:
        try:
            raw = Path(path).read_text(encoding="utf-8")
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise NorthboundArchiveError("invalid JSON archive") from exc
        except OSError as exc:
            raise NorthboundArchiveError("archive cannot be read") from exc
        if not isinstance(payload, dict) or payload.get("format") != ARCHIVE_FORMAT:
            raise NorthboundArchiveError("unsupported archive format")
        if payload.get("format_version") != ARCHIVE_VERSION:
            raise NorthboundArchiveError("unsupported format_version")
        checksum = payload.get("checksum_sha256")
        unsigned = {key: value for key, value in payload.items() if key != "checksum_sha256"}
        if not isinstance(checksum, str) or checksum != _digest(unsigned):
            raise NorthboundArchiveError("archive checksum mismatch")
        records = payload.get("records")
        if not isinstance(records, list):
            raise NorthboundArchiveError("archive records must be a list")
        try:
            normalized = [NorthboundRecord.from_dict(record) for record in records]
        except ValueError as exc:
            raise NorthboundArchiveError(f"invalid archive record: {exc}") from exc
        return self.write(normalized)

    def backup_to(self, path: str | Path) -> Path:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as source, closing(sqlite3.connect(str(destination))) as target:
            source.backup(target)
        return destination
