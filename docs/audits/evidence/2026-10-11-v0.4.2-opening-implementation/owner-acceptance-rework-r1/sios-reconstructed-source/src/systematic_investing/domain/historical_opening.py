"""Execution-only historical opening facts; never strategy PIT tradability."""

import json
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from enum import StrEnum
from hashlib import sha256
from systematic_investing.domain.identifiers import InstrumentId
from systematic_investing.domain.market import Availability, AvailabilityBasis

HISTORICAL_SUSPENSION_GAP = "HISTORICAL_SUSPENSION_COVERAGE_UNAVAILABLE"
OPENING_POLICY = "R2.1"
OPENING_SCHEMA = "historical-opening-evidence/1"
SHANGHAI = timezone(timedelta(hours=8), "Asia/Shanghai")
OPENING_CLOCK_ID = "Asia/Shanghai|09:15:00|09:30:00|15:30:00"


class ExecutionEligibilityMode(StrEnum):
    LEGACY = "LEGACY"
    HISTORICAL_OPENING_R21 = "HISTORICAL_OPENING_R21"


def _aware(text):
    value = datetime.fromisoformat(text)
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("historical opening timestamps must be aware")
    return value


def _json(data):
    return json.dumps(
        data, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )


@dataclass(frozen=True)
class HistoricalOpeningEvidence:
    """Immutable full source payload. Accessors return copies, preserving hashes."""

    payload_json: str

    def __post_init__(self):
        data = json.loads(self.payload_json)
        expected = data.pop("evidence_hash")
        if expected != sha256(_json(data).encode("utf-8")).hexdigest():
            raise ValueError("historical opening evidence_hash mismatch")
        data["evidence_hash"] = expected
        if (
            data["schema_version"] != OPENING_SCHEMA
            or data["policy_version"] != OPENING_POLICY
            or data["purpose"] != "historical_opening_execution_constraint"
        ):
            raise ValueError("unsupported historical opening policy/schema/purpose")
        self.instrument_id
        day = self.session_date
        target = self.target_execution_at
        expected_target = datetime.combine(day, time(9, 30), tzinfo=SHANGHAI)
        window = data["execution_effect_window"]
        if (
            target != expected_target
            or _aware(window["start"]) != target
            or _aware(window["end"]) != target + timedelta(minutes=1)
        ):
            raise ValueError("historical opening target must be Shanghai [09:30,09:31)")
        self.availability
        if data["opening_status"] not in (
            "OPEN_ACTIVITY_CONFIRMED",
            "BLOCKED_CONFIRMED",
            "UNKNOWN",
        ):
            raise ValueError("unknown opening_status")
        if not isinstance(data["source_conflict"], bool) or not isinstance(
            data["official_block_at_target"], bool
        ):
            raise ValueError("opening block/conflict flags must be boolean")
        if data["opening_status"] == "OPEN_ACTIVITY_CONFIRMED":
            query = data["official_query"]
            tdx = data["tdx_activity"]
            if data["source_conflict"] or data["official_block_at_target"]:
                raise ValueError("positive opening evidence conflicts with official block")
            if (
                query["status"] not in ("success", "normal_empty")
                or query["pagination_complete"] is not True
                or query["all_returned_rows_considered"] is not True
                or query["instrument"] != data["instrument"]
                or query["market"] != data["market"]
                or query["query_range"] != [day.isoformat(), day.isoformat()]
                or not query.get("range_kind")
            ):
                raise ValueError("opening evidence needs successful bounded official query")
            if (
                tdx["qualified"] is not True
                or tdx["instrument"] != data["instrument"]
                or tdx["session_date"] != day.isoformat()
                or tdx["opening_volume_lots"] <= 0
                or tdx["command"] != "0x0fb5"
                or tdx.get("opening_crosscheck_complete") is not True
            ):
                raise ValueError("opening evidence needs certified positive TDX activity")
            for event in data["official_events"]:
                if (
                    event["instrument"] != data["instrument"]
                    or event["market"] != data["market"]
                    or event.get("secondary_market") is not True
                ):
                    raise ValueError("official interval identity/scope unknown")
                start = _aware(event["effective_start"])
                end = _aware(event["effective_end"]) if event["effective_end"] else None
                if target < start < target + timedelta(minutes=1) or (
                    end is not None and target < end < target + timedelta(minutes=1)
                ):
                    raise ValueError("official boundary inside activity window cannot be ordered")
                if start <= target and (end is None or target < end):
                    raise ValueError("official interval vetoes opening execution")
        object.__setattr__(self, "payload_json", _json(data))

    @classmethod
    def from_payload(cls, payload):
        return cls(_json(dict(payload)))

    @property
    def payload(self):
        return json.loads(self.payload_json)

    @property
    def instrument_id(self):
        data = self.payload
        market = {"SSE": "XSHG", "SZSE": "XSHE"}.get(data["market"])
        if market is None:
            raise ValueError("unknown opening market")
        return InstrumentId.parse(market + ":" + data["instrument"])

    @property
    def session_date(self):
        return date.fromisoformat(self.payload["session_date"])

    @property
    def target_execution_at(self):
        return _aware(self.payload["target_execution_at"])

    @property
    def availability(self):
        data = self.payload
        return Availability(
            _aware(data["information_available_at"]) if data["information_available_at"] else None,
            _aware(data["retrieved_at"]),
            AvailabilityBasis(data["information_basis"]),
        )

    @property
    def opening_status(self):
        return self.payload["opening_status"]

    @property
    def evidence_hash(self):
        return self.payload["evidence_hash"]


def opening_evidence_digest(facts):
    return sha256(
        "\n".join(sorted(fact.payload_json for fact in facts)).encode("utf-8")
    ).hexdigest()


def execution_identity(base, mode, facts, clock_id=OPENING_CLOCK_ID):
    if mode is ExecutionEligibilityMode.LEGACY:
        return base
    return (
        base
        + "|"
        + mode.value
        + "|"
        + OPENING_POLICY
        + "|"
        + clock_id
        + "|"
        + opening_evidence_digest(facts)
    )
