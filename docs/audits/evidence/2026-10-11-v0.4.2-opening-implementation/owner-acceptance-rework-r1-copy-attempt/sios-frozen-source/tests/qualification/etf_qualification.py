"""Offline ETF qualification runner (test-side helper).

Runs recorded vendor-shaped payloads through the real ``ChStockDataProvider``
adapter and the approved Instrument Master, then renders a deterministic,
capability-scoped qualification report. This module is test support only: it
is never imported by the packaged core, and the generated report lives under
``tests/qualification/reports`` (or an environment override) so it is excluded
from core package imports by construction.

Passing one subtype never approves another: every subtype is evaluated
independently and the report records each scope's own status.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from typing import Any

from systematic_investing.adapters.chstockdata.provider import (
    PINNED_CHSTOCKDATA_VERSION,
    ChStockDataProvider,
    LibraryChStockDataClient,
    RawVendorResponse,
)
from systematic_investing.data.contracts import ProviderFailure, ProviderSuccess
from systematic_investing.data.ports import (
    CalendarRequest,
    CorporateActionRequest,
    DailyBarRequest,
    TradabilityRequest,
)
from systematic_investing.domain.identifiers import InstrumentId
from systematic_investing.domain.instruments import FundSubtype
from systematic_investing.domain.market import (
    AdjustmentMode,
    AvailabilityBasis,
    TradabilityStatus,
    TradeSide,
)

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "qualification"
DEFAULT_REPORT_DIR = Path(__file__).resolve().parent / "reports"
REPORT_DIR_ENV = "SIOS_QUALIFICATION_REPORT_DIR"
OFFLINE_REPORT_NAME = "m0-etf-qualification-offline-v1.json"
REPORT_SCHEMA_VERSION = "m0-etf-qualification-report-1"
APPROVED_SUBTYPES = (
    FundSubtype.BROAD_BASED_EQUITY,
    FundSubtype.GOLD,
    FundSubtype.BOND,
)
CHECK_ORDER = (
    "ROUTING",
    "OHLCV_PRE_CLOSE",
    "UNITS",
    "CALENDAR",
    "TRADABILITY",
    "ADJUSTMENT_ACTIONS",
    "FRESHNESS",
    "PROVIDER_VERSION",
)


class QualificationError(Exception):
    """Raised when the qualification matrix or payloads are malformed."""


def load_matrix() -> dict[str, Any]:
    return json.loads((FIXTURE_DIR / "etf_matrix.json").read_text(encoding="utf-8"))


def load_payloads() -> dict[str, Any]:
    return json.loads(
        (FIXTURE_DIR / "recorded_etf_payloads.json").read_text(encoding="utf-8")
    )


@dataclass(frozen=True)
class QualificationCheck:
    """One capability check outcome for one instrument and subtype."""

    subtype: str
    instrument_id: str
    check_id: str
    status: str
    observed: str
    expected: str
    evidence_ids: tuple[str, ...] = ()

    def to_payload(self) -> dict[str, Any]:
        return {
            "subtype": self.subtype,
            "instrument_id": self.instrument_id,
            "check_id": self.check_id,
            "status": self.status,
            "observed": self.observed,
            "expected": self.expected,
            "evidence_ids": list(self.evidence_ids),
        }


@dataclass(frozen=True)
class QualificationReport:
    """A rendered capability-scoped report plus its evaluation details."""

    payload: dict[str, Any]
    checks: tuple[QualificationCheck, ...]
    statuses: dict[str, str]


class _RecordedClient:
    """Deterministic stand-in for the pinned vendor boundary."""

    def __init__(self, payloads: dict[str, Any]) -> None:
        self._payloads = payloads

    def provider_version(self) -> str:
        return str(self._payloads["provider_version"])

    def _response(self, entry: dict[str, Any]) -> RawVendorResponse:
        return RawVendorResponse(
            capability=entry["capability"],
            payload=entry["payload"],
            upstream_source=entry["upstream_source"],
            observed_at=(
                None
                if entry.get("observed_at") is None
                else datetime.fromisoformat(entry["observed_at"])
            ),
            warnings=tuple(entry.get("warnings", ())),
        )

    def daily_bars(
        self, *, instrument_id: InstrumentId, start_date: date, end_date: date
    ) -> RawVendorResponse:
        del start_date, end_date
        entry = self._payloads["daily_bars"].get(str(instrument_id))
        if entry is None:
            raise QualificationError(f"no recorded daily bars for {instrument_id}")
        return self._response(entry)

    def calendar(self, *, calendar_id: str, start_date: date, end_date: date) -> RawVendorResponse:
        del start_date, end_date
        entry = self._payloads["trading_calendar"].get(calendar_id)
        if entry is None:
            raise QualificationError(f"no recorded calendar for {calendar_id}")
        return self._response(entry)

    def suspension(
        self, *, instrument_id: InstrumentId, session_date: date
    ) -> RawVendorResponse:
        keyed = f"{instrument_id}@{session_date.isoformat()}"
        entry = self._payloads["tradability"].get(keyed) or self._payloads[
            "tradability"
        ].get(str(instrument_id))
        if entry is None:
            raise QualificationError(f"no recorded tradability for {instrument_id}")
        return self._response(entry)

    def corporate_actions(
        self,
        *,
        instrument_id: InstrumentId,
        start_date: date,
        end_date: date,
        instrument_kind: str = "STOCK",
    ) -> RawVendorResponse:
        del start_date, end_date, instrument_kind
        entry = self._payloads["corporate_actions"].get(str(instrument_id))
        if entry is None:
            raise QualificationError(f"no recorded corporate actions for {instrument_id}")
        return self._response(entry)

    def rule_candidates(
        self, *, instrument_id: InstrumentId, session_date: date
    ) -> RawVendorResponse:
        del instrument_id, session_date
        return RawVendorResponse(
            capability="rule_candidates",
            payload={"profiles": (), "source": "recorded: no rule capability"},
            upstream_source="recorded: pinned chstockdata publishes no rule profiles",
        )


def build_provider(
    payloads: dict[str, Any], *, retrieved_at: datetime
) -> ChStockDataProvider:
    return ChStockDataProvider(
        client=_RecordedClient(payloads), clock=lambda: retrieved_at
    )


class _StubFrame:
    """Minimal stand-in for the vendor's tabular frame shape."""

    def __init__(self, rows: list[dict[str, object]], columns: list[str]) -> None:
        self._rows = rows
        self.columns = columns

    @property
    def empty(self) -> bool:
        return not self._rows

    def to_dict(self, orient: str = "dict") -> list[dict[str, object]]:
        assert orient == "records"
        return [dict(row) for row in self._rows]


class _StubLibrary:
    """Minimal stand-in for the pinned vendor library module surface."""

    __version__ = PINNED_CHSTOCKDATA_VERSION

    def __init__(self, frames: dict[str, _StubFrame]) -> None:
        self.frames = frames
        self.calls: list[tuple[str, str, str, str]] = []
        self.markets: list[str] = []

    def load_vipdoc_daily(
        self,
        code: str,
        start_date: str | None = None,
        end_date: str | None = None,
        *,
        market: str | None = None,
        **kwargs: object,
    ) -> _StubFrame | None:
        del kwargs
        assert start_date is not None and end_date is not None
        self.calls.append(("load_vipdoc_daily", code, start_date, end_date))
        self.markets.append(str(market))
        return self.frames.get(code)


def _window_of(matrix: dict[str, Any]) -> tuple[date, date]:
    window = matrix["window"]
    return date.fromisoformat(window["start"]), date.fromisoformat(window["end"])


def _calendar_window_of(matrix: dict[str, Any]) -> tuple[date, date]:
    window = matrix["calendar_window"]
    return date.fromisoformat(window["start"]), date.fromisoformat(window["end"])


def _success_or_fail(
    result: ProviderSuccess | ProviderFailure,
) -> str | None:
    if isinstance(result, ProviderFailure):
        return f"{result.error_code.value}: {result.message}"
    return None


def _check_routing(
    *,
    subtype: str,
    instrument: dict[str, Any],
    payloads: dict[str, Any],
    start: date,
    end: date,
) -> QualificationCheck:
    instrument_id = InstrumentId.parse(instrument["instrument_id"])
    vendor_symbol = instrument["vendor_symbol"]
    pure_code = instrument_id.symbol
    market = vendor_symbol[:2]
    recorded = payloads["daily_bars"][instrument["instrument_id"]]["payload"]
    frame = _StubFrame(
        [dict(row) for row in recorded["rows"]], list(recorded["columns"])
    )
    library = _StubLibrary(frames={pure_code: frame})
    client = LibraryChStockDataClient(library=library)

    response = client.daily_bars(
        instrument_id=instrument_id, start_date=start, end_date=end
    )

    expected_call = ("load_vipdoc_daily", pure_code, start.isoformat(), end.isoformat())
    passed = (
        library.calls == [expected_call]
        and library.markets == [market]
        and bool(response.payload["rows"])
    )
    return QualificationCheck(
        subtype=subtype,
        instrument_id=str(instrument_id),
        check_id="ROUTING",
        status="PASS" if passed else "FAIL",
        observed=(
            f"calls={library.calls}, markets={library.markets}, "
            f"rows={len(response.payload['rows'])}"
        ),
        expected=(
            f"single load_vipdoc_daily call for {pure_code} with market={market} "
            "and rows"
        ),
        evidence_ids=(f"{instrument_id}:vendor-routing",),
    )


def _check_ohlcv_pre_close(
    *,
    subtype: str,
    instrument: dict[str, Any],
    provider: ChStockDataProvider,
    payloads: dict[str, Any],
    start: date,
    end: date,
    requirements: dict[str, Any],
) -> QualificationCheck:
    instrument_id = InstrumentId.parse(instrument["instrument_id"])
    result = provider.fetch_daily_bars(
        DailyBarRequest(instrument_ids=(instrument_id,), start_date=start, end_date=end)
    )
    failure = _success_or_fail(result)
    if failure is not None:
        return QualificationCheck(
            subtype=subtype,
            instrument_id=str(instrument_id),
            check_id="OHLCV_PRE_CLOSE",
            status="FAIL",
            observed=failure,
            expected="canonical bars with positive OHLC and a declared pre_close",
        )
    rows = payloads["daily_bars"][instrument["instrument_id"]]["payload"]["rows"]
    bars = result.records
    problems: list[str] = []
    if len(bars) != len(rows):
        problems.append(f"row count {len(bars)} != {len(rows)}")
    for bar, row in zip(bars, rows, strict=False):
        declared_pre_close = row.get("pre_close")
        if requirements["pre_close"] == "required" and bar.pre_close is None:
            problems.append(f"{bar.session_date}: pre_close missing")
        elif declared_pre_close is not None and bar.pre_close != Decimal(
            str(declared_pre_close)
        ):
            problems.append(
                f"{bar.session_date}: pre_close {bar.pre_close} != {declared_pre_close}"
            )
        elif declared_pre_close is None and bar.pre_close is not None:
            problems.append(f"{bar.session_date}: fabricated pre_close")
        if bar.high < max(bar.open, bar.close) or bar.low > min(bar.open, bar.close):
            problems.append(f"{bar.session_date}: OHLC invariant violated")
    passed = not problems
    return QualificationCheck(
        subtype=subtype,
        instrument_id=str(instrument_id),
        check_id="OHLCV_PRE_CLOSE",
        status="PASS" if passed else "FAIL",
        observed="; ".join(problems) if problems else f"{len(bars)} bars verified",
        expected=(
            "positive OHLC, high/low consistency, and pre_close present "
            "(null is never converted to zero)"
        ),
        evidence_ids=(result.evidence.evidence_id,),
    )


def _check_units(
    *,
    subtype: str,
    instrument: dict[str, Any],
    provider: ChStockDataProvider,
    payloads: dict[str, Any],
    start: date,
    end: date,
    requirements: dict[str, Any],
) -> QualificationCheck:
    instrument_id = InstrumentId.parse(instrument["instrument_id"])
    result = provider.fetch_daily_bars(
        DailyBarRequest(instrument_ids=(instrument_id,), start_date=start, end_date=end)
    )
    failure = _success_or_fail(result)
    if failure is not None:
        return QualificationCheck(
            subtype=subtype,
            instrument_id=str(instrument_id),
            check_id="UNITS",
            status="FAIL",
            observed=failure,
            expected="declared SHARE/CNY units normalized exactly once",
        )
    rows = payloads["daily_bars"][instrument["instrument_id"]]["payload"]["rows"]
    problems: list[str] = []
    for bar, row in zip(result.records, rows, strict=False):
        if bar.volume_unit != requirements["volume_unit"]:
            problems.append(f"{bar.session_date}: volume_unit={bar.volume_unit}")
        if bar.amount_unit != requirements["amount_unit"]:
            problems.append(f"{bar.session_date}: amount_unit={bar.amount_unit}")
        if bar.currency != "CNY":
            problems.append(f"{bar.session_date}: currency={bar.currency}")
        if bar.volume != Decimal(str(row["Volume"])):
            problems.append(f"{bar.session_date}: volume conversion mismatch")
        if bar.amount != Decimal(str(row["Amount"])):
            problems.append(f"{bar.session_date}: amount conversion mismatch")
        if not isinstance(bar.volume, Decimal) or not isinstance(bar.amount, Decimal):
            problems.append(f"{bar.session_date}: non-Decimal units")
    passed = not problems
    return QualificationCheck(
        subtype=subtype,
        instrument_id=str(instrument_id),
        check_id="UNITS",
        status="PASS" if passed else "FAIL",
        observed="; ".join(problems) if problems else f"{len(result.records)} rows exact",
        expected="SHARE volume, CNY amount, Decimal values, factor applied once",
        evidence_ids=(result.evidence.evidence_id,),
    )


def _check_calendar(
    *,
    subtype: str,
    instrument: dict[str, Any],
    provider: ChStockDataProvider,
    payloads: dict[str, Any],
    start: date,
    end: date,
    calendar_start: date,
    calendar_end: date,
) -> QualificationCheck:
    instrument_id = InstrumentId.parse(instrument["instrument_id"])
    calendar_result = provider.fetch_calendar(
        CalendarRequest(
            calendar_id=instrument_id.exchange.value,
            start_date=calendar_start,
            end_date=calendar_end,
        )
    )
    failure = _success_or_fail(calendar_result)
    if failure is not None:
        return QualificationCheck(
            subtype=subtype,
            instrument_id=str(instrument_id),
            check_id="CALENDAR",
            status="FAIL",
            observed=failure,
            expected="a covering calendar snapshot with explicit open/closed days",
        )
    sessions = {session.session_date: session for session in calendar_result.records}
    expected_days = (calendar_end - calendar_start).days + 1
    bars_result = provider.fetch_daily_bars(
        DailyBarRequest(instrument_ids=(instrument_id,), start_date=start, end_date=end)
    )
    failure = _success_or_fail(bars_result)
    problems: list[str] = []
    if failure is not None:
        problems.append(failure)
    if len(sessions) != expected_days:
        problems.append(f"calendar covers {len(sessions)} of {expected_days} days")
    weekend = date(2026, 9, 5)
    if weekend in sessions and sessions[weekend].is_open:
        problems.append("2026-09-05 is not an open session")
    if failure is None:
        for bar in bars_result.records:
            session = sessions.get(bar.session_date)
            if session is None or not session.is_open:
                problems.append(f"{bar.session_date}: bar on a non-open session")
    passed = not problems
    return QualificationCheck(
        subtype=subtype,
        instrument_id=str(instrument_id),
        check_id="CALENDAR",
        status="PASS" if passed else "FAIL",
        observed="; ".join(problems) if problems else f"{len(sessions)} days explicit",
        expected="calendar covers every bar session and marks closed days explicitly",
        evidence_ids=(calendar_result.evidence.evidence_id,),
    )


def _check_tradability(
    *,
    subtype: str,
    instrument: dict[str, Any],
    provider: ChStockDataProvider,
    session_date: date,
) -> QualificationCheck:
    instrument_id = InstrumentId.parse(instrument["instrument_id"])
    result = provider.fetch_tradability(
        TradabilityRequest(instrument_ids=(instrument_id,), session_date=session_date)
    )
    failure = _success_or_fail(result)
    if failure is not None:
        return QualificationCheck(
            subtype=subtype,
            instrument_id=str(instrument_id),
            check_id="TRADABILITY",
            status="FAIL",
            observed=failure,
            expected="a point-in-time tradability record for the requested session",
        )
    record: TradabilityStatus = result.records[0]
    problems: list[str] = []
    if record.status.value != "TRADABLE":
        problems.append(f"status={record.status.value}")
    if record.session_date != session_date:
        problems.append(f"session_date={record.session_date}")
    if record.availability.availability_basis not in (
        AvailabilityBasis.OBSERVED,
        AvailabilityBasis.EXCHANGE_RULE,
    ):
        problems.append(f"basis={record.availability.availability_basis.value}")
    if not record.permits(TradeSide.BUY) or not record.permits(TradeSide.SELL):
        problems.append("side permissions missing")
    if not record.provenance:
        problems.append("provenance missing")
    passed = not problems
    return QualificationCheck(
        subtype=subtype,
        instrument_id=str(instrument_id),
        check_id="TRADABILITY",
        status="PASS" if passed else "FAIL",
        observed="; ".join(problems) if problems else record.provenance,
        expected="TRADABLE for both sides with explicit availability and provenance",
        evidence_ids=(result.evidence.evidence_id,),
    )


def _check_adjustment_actions(
    *,
    subtype: str,
    instrument: dict[str, Any],
    provider: ChStockDataProvider,
    payloads: dict[str, Any],
    start: date,
    end: date,
) -> QualificationCheck:
    instrument_id = InstrumentId.parse(instrument["instrument_id"])
    bars_result = provider.fetch_daily_bars(
        DailyBarRequest(instrument_ids=(instrument_id,), start_date=start, end_date=end)
    )
    failure = _success_or_fail(bars_result)
    if failure is not None:
        return QualificationCheck(
            subtype=subtype,
            instrument_id=str(instrument_id),
            check_id="ADJUSTMENT_ACTIONS",
            status="FAIL",
            observed=failure,
            expected="RAW bars plus separate corporate-action facts",
        )
    problems: list[str] = []
    for bar in bars_result.records:
        if bar.adjustment_mode is not AdjustmentMode.RAW:
            problems.append(f"{bar.session_date}: mode={bar.adjustment_mode.value}")
        if bar.adjustment_factor is not None:
            problems.append(f"{bar.session_date}: unexpected adjustment factor")
    actions_result = provider.fetch_corporate_actions(
        CorporateActionRequest(
            instrument_ids=(instrument_id,), start_date=start, end_date=end
        )
    )
    failure = _success_or_fail(actions_result)
    if failure is not None:
        problems.append(failure)
        records = ()
        items = ()
    else:
        records = actions_result.records
        items = payloads["corporate_actions"][instrument["instrument_id"]]["payload"]["items"]
        if len(records) != len(items):
            problems.append(f"{len(records)} actions for {len(items)} declared items")
        for record, item in zip(records, items, strict=False):
            if (
                record.availability.availability_basis
                not in (
                    AvailabilityBasis.OBSERVED,
                    AvailabilityBasis.EXCHANGE_RULE,
                    AvailabilityBasis.INFERRED,
                )
            ):
                problems.append(f"{record.action_id}: availability basis")
            if not record.provenance:
                problems.append(f"{record.action_id}: provenance missing")
            declared_cash = item.get("cash_dividend")
            if declared_cash is not None:
                expected_per_share = Decimal(str(declared_cash["value"])) / Decimal("10")
                if record.cash_amount is None or record.cash_amount.amount != expected_per_share:
                    problems.append(f"{record.action_id}: per-share cash normalization")
    passed = not problems
    return QualificationCheck(
        subtype=subtype,
        instrument_id=str(instrument_id),
        check_id="ADJUSTMENT_ACTIONS",
        status="PASS" if passed else "FAIL",
        observed=(
            "; ".join(problems)
            if problems
            else f"{len(bars_result.records)} RAW bars, {len(records)} actions"
        ),
        expected="RAW execution bars and separate per-share-normalized action facts",
        evidence_ids=(bars_result.evidence.evidence_id, actions_result.evidence.evidence_id)
        if isinstance(actions_result, ProviderSuccess)
        else (bars_result.evidence.evidence_id,),
    )


def _check_edge_events(
    *,
    subtype: str,
    instrument: dict[str, Any],
    provider: ChStockDataProvider,
    matrix: dict[str, Any],
) -> QualificationCheck | None:
    cases = [
        case
        for case in matrix.get("edge_events", ())
        if case["instrument_id"] == instrument["instrument_id"]
    ]
    if not cases:
        return None
    instrument_id = InstrumentId.parse(instrument["instrument_id"])
    problems: list[str] = []
    observed: list[str] = []
    evidence_ids: list[str] = []
    for case in cases:
        result = provider.fetch_tradability(
            TradabilityRequest(
                instrument_ids=(instrument_id,),
                session_date=date.fromisoformat(case["session_date"]),
            )
        )
        failure = _success_or_fail(result)
        if failure is not None:
            problems.append(f"{case['case_id']}: {failure}")
            continue
        record = result.records[0]
        if record.status.value != case["expected_status"]:
            problems.append(f"{case['case_id']}: status={record.status.value}")
        expected_permitted = frozenset(
            TradeSide(side) for side in case["expected_permitted_sides"]
        )
        if record.permitted_sides != expected_permitted:
            permitted = sorted(
                side.value for side in record.permitted_sides or ()
            )
            problems.append(f"{case['case_id']}: permitted={permitted}")
        observed.append(f"{case['case_id']}={record.status.value}")
        evidence_ids.append(result.evidence.evidence_id)
    return QualificationCheck(
        subtype=subtype,
        instrument_id=str(instrument_id),
        check_id="EDGE_EVENTS",
        status="PASS" if not problems else "FAIL",
        observed="; ".join(problems) if problems else ", ".join(observed),
        expected="recorded edge events map to their declared tradability state",
        evidence_ids=tuple(evidence_ids),
    )


def _check_freshness(
    *,
    subtype: str,
    instrument: dict[str, Any],
    provider: ChStockDataProvider,
    payloads: dict[str, Any],
    start: date,
    end: date,
    evaluation_session: date,
    retrieved_at: datetime,
    requirements: dict[str, Any],
) -> QualificationCheck:
    instrument_id = InstrumentId.parse(instrument["instrument_id"])
    result = provider.fetch_daily_bars(
        DailyBarRequest(instrument_ids=(instrument_id,), start_date=start, end_date=end)
    )
    failure = _success_or_fail(result)
    if failure is not None:
        return QualificationCheck(
            subtype=subtype,
            instrument_id=str(instrument_id),
            check_id="FRESHNESS",
            status="FAIL",
            observed=failure,
            expected="information available no later than retrieval and no future sessions",
        )
    problems: list[str] = []
    latest = None
    for bar in result.records:
        if bar.session_date > evaluation_session:
            problems.append(f"{bar.session_date}: session after the evaluation session")
        information_at = bar.availability.information_available_at
        if information_at is None:
            problems.append(f"{bar.session_date}: no information availability")
        elif information_at > retrieved_at:
            problems.append(f"{bar.session_date}: information after retrieval")
        latest = bar.session_date if latest is None else max(latest, bar.session_date)
    if latest != end:
        problems.append(f"latest bar session {latest} is not the window end {end}")
    open_days = [
        date.fromisoformat(day)
        for day in payloads["trading_calendar"][instrument_id.exchange.value]["payload"][
            "open_days"
        ]
    ]
    age = sum(1 for day in open_days if latest is not None and latest < day <= evaluation_session)
    if age > requirements["max_information_age_sessions"]:
        problems.append(f"information age {age} sessions")
    passed = not problems
    return QualificationCheck(
        subtype=subtype,
        instrument_id=str(instrument_id),
        check_id="FRESHNESS",
        status="PASS" if passed else "FAIL",
        observed=(
            "; ".join(problems)
            if problems
            else f"latest={latest}, retrieved={retrieved_at.isoformat()}"
        ),
        expected="information-time freshness with an injected clock, never wall-clock",
        evidence_ids=(result.evidence.evidence_id,),
    )


def _check_provider_version(
    *,
    subtype: str,
    instrument: dict[str, Any],
    provider: ChStockDataProvider,
    matrix: dict[str, Any],
) -> QualificationCheck:
    instrument_id = InstrumentId.parse(instrument["instrument_id"])
    evidence = provider.capability_evidence()
    problems: list[str] = []
    if isinstance(evidence, ProviderFailure):
        problems.append(evidence.message)
    else:
        provider_version = matrix["provider"]["version"]
        if evidence.provider_version != provider_version:
            problems.append(f"provider_version={evidence.provider_version}")
        if evidence.provider_version != PINNED_CHSTOCKDATA_VERSION:
            problems.append("provider version is not the pinned qualified release")
        if evidence.adapter_name != matrix["provider"]["adapter_name"]:
            problems.append(f"adapter_name={evidence.adapter_name}")
        if evidence.adapter_version != matrix["provider"]["adapter_version"]:
            problems.append(f"adapter_version={evidence.adapter_version}")
        if evidence.record_count != len(ChStockDataProvider.CAPABILITIES):
            problems.append(f"record_count={evidence.record_count}")
    passed = not problems
    return QualificationCheck(
        subtype=subtype,
        instrument_id=str(instrument_id),
        check_id="PROVIDER_VERSION",
        status="PASS" if passed else "FAIL",
        observed=(
            "; ".join(problems)
            if problems
            else f"{PINNED_CHSTOCKDATA_VERSION} pinned and reported"
        ),
        expected="pinned provider release plus adapter version evidence",
        evidence_ids=(
            (evidence.evidence_id,) if isinstance(evidence, ProviderSuccess) else ()
        ),
    )


def evaluate_offline(
    matrix: dict[str, Any], payloads: dict[str, Any]
) -> QualificationReport:
    """Evaluate every approved subtype against the recorded evidence."""
    evaluation_time = datetime.fromisoformat(matrix["evaluation_time"])
    evaluation_session = date.fromisoformat(matrix["evaluation_session"])
    start, end = _window_of(matrix)
    calendar_start, calendar_end = _calendar_window_of(matrix)
    requirements = matrix["requirements"]
    provider = build_provider(payloads, retrieved_at=evaluation_time)

    checks: list[QualificationCheck] = []
    statuses: dict[str, str] = {}
    approved_scope: list[dict[str, Any]] = []
    for entry in matrix["subtypes"]:
        subtype = entry["subtype"]
        subtype_checks: list[QualificationCheck] = []
        for instrument in entry["instruments"]:
            subtype_checks.extend(
                [
                    _check_routing(
                        subtype=subtype,
                        instrument=instrument,
                        payloads=payloads,
                        start=start,
                        end=end,
                    ),
                    _check_ohlcv_pre_close(
                        subtype=subtype,
                        instrument=instrument,
                        provider=provider,
                        payloads=payloads,
                        start=start,
                        end=end,
                        requirements=requirements,
                    ),
                    _check_units(
                        subtype=subtype,
                        instrument=instrument,
                        provider=provider,
                        payloads=payloads,
                        start=start,
                        end=end,
                        requirements=requirements,
                    ),
                    _check_calendar(
                        subtype=subtype,
                        instrument=instrument,
                        provider=provider,
                        payloads=payloads,
                        start=start,
                        end=end,
                        calendar_start=calendar_start,
                        calendar_end=calendar_end,
                    ),
                    _check_tradability(
                        subtype=subtype,
                        instrument=instrument,
                        provider=provider,
                        session_date=evaluation_session,
                    ),
                    _check_adjustment_actions(
                        subtype=subtype,
                        instrument=instrument,
                        provider=provider,
                        payloads=payloads,
                        start=start,
                        end=end,
                    ),
                    _check_freshness(
                        subtype=subtype,
                        instrument=instrument,
                        provider=provider,
                        payloads=payloads,
                        start=start,
                        end=end,
                        evaluation_session=evaluation_session,
                        retrieved_at=evaluation_time,
                        requirements=requirements,
                    ),
                    _check_provider_version(
                        subtype=subtype,
                        instrument=instrument,
                        provider=provider,
                        matrix=matrix,
                    ),
                ]
            )
            edge = _check_edge_events(
                subtype=subtype,
                instrument=instrument,
                provider=provider,
                matrix=matrix,
            )
            if edge is not None:
                subtype_checks.append(edge)
        status = (
            "PASS" if all(check.status == "PASS" for check in subtype_checks) else "FAIL"
        )
        statuses[subtype] = status
        checks.extend(subtype_checks)
        approved_scope.append(
            {
                "subtype": subtype,
                "status": status,
                "instruments": [item["instrument_id"] for item in entry["instruments"]],
                "checks": sorted({check.check_id for check in subtype_checks}),
            }
        )

    rejected_scope = []
    for entry in matrix["rejected_scope"]:
        checks.append(
            QualificationCheck(
                subtype=entry["scope"],
                instrument_id=entry["representative"],
                check_id="SCOPE_REJECTED",
                status="REJECTED",
                observed=entry["reason"],
                expected="fail closed with no approved capability scope",
            )
        )
        rejected_scope.append(
            {
                "scope": entry["scope"],
                "representative": entry["representative"],
                "status": "UNSUPPORTED",
                "reason": entry["reason"],
            }
        )

    payload: dict[str, Any] = {
        "report_schema_version": REPORT_SCHEMA_VERSION,
        "matrix_version": matrix["matrix_version"],
        "evaluation_scope": "OFFLINE_RECORDED",
        "generated_at": matrix["evaluation_time"],
        "evaluation_session": matrix["evaluation_session"],
        "window": matrix["window"],
        "provider": {
            **matrix["provider"],
            "pinned_version": PINNED_CHSTOCKDATA_VERSION,
        },
        "approved_scope": approved_scope,
        "rejected_scope": rejected_scope,
        "checks": [check.to_payload() for check in checks],
        "tolerances": matrix["tolerances"],
        "independent_evidence": matrix["independent_evidence"],
        "excluded_scope": matrix["excluded_scope"],
        "credentials_prerequisites": matrix["credentials_prerequisites"],
        "commands": matrix["commands"],
    }
    payload["report_digest"] = _digest(payload)
    return QualificationReport(
        payload=payload, checks=tuple(checks), statuses=statuses
    )


def report_status_of(report: QualificationReport, subtype: str) -> str:
    try:
        return report.statuses[subtype]
    except KeyError as error:
        raise QualificationError(f"no approved scope for subtype {subtype!r}") from error


def _digest(payload: dict[str, Any]) -> str:
    rendered = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + sha256(rendered.encode("utf-8")).hexdigest()


def render_report(report: QualificationReport) -> bytes:
    """Deterministic canonical bytes for the immutable report artifact."""
    return (
        json.dumps(report.payload, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def write_report(report: QualificationReport, *, directory: Path | None = None) -> Path:
    target = directory
    if target is None:
        override = os.environ.get(REPORT_DIR_ENV)
        target = Path(override) if override else DEFAULT_REPORT_DIR
    target.mkdir(parents=True, exist_ok=True)
    path = target / OFFLINE_REPORT_NAME
    path.write_bytes(render_report(report))
    return path
