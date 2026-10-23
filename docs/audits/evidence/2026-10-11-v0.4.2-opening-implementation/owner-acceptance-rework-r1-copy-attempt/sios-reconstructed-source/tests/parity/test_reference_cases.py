"""Independent parity: frozen public-rule evidence versus kernel computations.

Every expected value was frozen by hand from public regulations and exchange
trading rules before the kernel ran; the kernel is never its own oracle. Each
case records its source, access date, semantics, and tolerance, and any delta
is reported as explained/expected or as a defect. The test emits a
deterministic, immutable parity report under ``tests/parity/reports`` (or an
environment override), which is excluded from core package imports by
construction.

Licensed independent engines (for example JoinQuant validation-only research
access) are not embedded here; they remain a release-environment parity step
under their own data terms.
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from typing import Any

import pytest

from systematic_investing.backtest.accounting import sellable_from
from systematic_investing.backtest.execution import ExecutionModel
from systematic_investing.domain.execution import BrokerFeeProfile, compute_fees
from systematic_investing.domain.identifiers import InstrumentId
from systematic_investing.domain.market import (
    Availability,
    AvailabilityBasis,
    MarketCalendar,
    TradeSide,
    TradingSession,
)
from systematic_investing.instrument_master.repository import default_m0_master

FIXTURE_PATH = (
    Path(__file__).resolve().parents[1] / "fixtures" / "parity" / "reference_cases.json"
)
DEFAULT_REPORT_DIR = Path(__file__).resolve().parent / "reports"
REPORT_DIR_ENV = "SIOS_PARITY_REPORT_DIR"
OFFLINE_REPORT_NAME = "m0-parity-offline-v1.json"
REPORT_SCHEMA_VERSION = "m0-parity-report-1"

PARITY = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
CASES = {case["case_id"]: case for case in PARITY["cases"]}
MASTER = default_m0_master()


def _broker_of(inputs: dict[str, Any]) -> BrokerFeeProfile:
    return BrokerFeeProfile(
        profile_id="PARITY-BROKER",
        version="1",
        commission_rate=Decimal(inputs["broker"]["commission_rate"]),
        minimum_commission=Decimal(inputs["broker"]["minimum_commission"]),
        agreement_reference="parity-fixture",
        effective_from=date(2022, 1, 4),
        effective_to=None,
    )


def _observe_fees(inputs: dict[str, Any]) -> dict[str, Decimal]:
    instrument_id = InstrumentId.parse(inputs["instrument_id"])
    session = date.fromisoformat(inputs["session_date"])
    rules = MASTER.resolve_rules(instrument_id, session)
    fees = compute_fees(
        rules.market_fee_tax,
        _broker_of(inputs),
        TradeSide(inputs["side"]),
        int(inputs["quantity"]),
        Decimal(inputs["price"]),
    )
    return {
        "stamp_tax": fees.stamp_tax.amount,
        "transfer_fee": fees.transfer_fee.amount,
        "commission": fees.commission.amount,
        "minimum_commission_adjustment": fees.minimum_commission_adjustment.amount,
        "total": fees.total.amount,
    }


def _observe_price_limit(inputs: dict[str, Any]) -> dict[str, Any]:
    instrument_id = InstrumentId.parse(inputs["instrument_id"])
    session = date.fromisoformat(inputs["session_date"])
    rule = MASTER.resolve_rules(instrument_id, session).price_limit
    pre_close = Decimal(inputs["pre_close"])
    return {
        "limit_percent": rule.limit_percent,
        "tick_size": rule.tick_size,
        "basis": rule.basis.value,
        "upper_limit": pre_close * (Decimal("1") + rule.limit_percent),
        "lower_limit": pre_close * (Decimal("1") - rule.limit_percent),
    }


def _observe_settlement(inputs: dict[str, Any]) -> dict[str, Any]:
    instrument_id = InstrumentId.parse(inputs["instrument_id"])
    session = date.fromisoformat(inputs["session_date"])
    rule = MASTER.resolve_rules(instrument_id, session).settlement
    calendar = MarketCalendar(
        calendar_id="XSHG",
        snapshot_version="PARITY-CAL",
        sessions=tuple(
            TradingSession(
                calendar_id="XSHG",
                session_date=date.fromisoformat(day),
                is_open=True,
                note=None,
                snapshot_version="PARITY-CAL",
            )
            for day in inputs["open_sessions"]
        ),
    )
    return {
        "sessions_until_sellable": rule.sessions_until_sellable,
        "sellable_from": sellable_from(
            calendar=calendar,
            acquired_session=date.fromisoformat(inputs["acquired_session"]),
            sessions_until_sellable=rule.sessions_until_sellable,
        ),
    }


def _observe_availability(inputs: dict[str, Any]) -> dict[str, Any]:
    retrieved_at = datetime.fromisoformat(inputs["retrieved_at"])
    early = Availability(
        information_available_at=datetime.fromisoformat(
            inputs["early_fact_information_at"]
        ),
        retrieved_at=retrieved_at,
        availability_basis=AvailabilityBasis.OBSERVED,
    )
    late = Availability(
        information_available_at=datetime.fromisoformat(
            inputs["late_fact_information_at"]
        ),
        retrieved_at=retrieved_at,
        availability_basis=AvailabilityBasis.OBSERVED,
    )
    unknown = Availability(
        information_available_at=None,
        retrieved_at=retrieved_at,
        availability_basis=AvailabilityBasis.UNKNOWN,
    )
    early_cutoff = datetime.fromisoformat(inputs["cutoff_early"])
    late_cutoff = datetime.fromisoformat(inputs["cutoff_late"])
    return {
        "early_fact_known_at_early_cutoff": early.information_known_at(early_cutoff),
        "late_fact_known_at_early_cutoff": late.information_known_at(early_cutoff),
        "late_fact_known_at_late_cutoff": late.information_known_at(late_cutoff),
        "unknown_basis_known_at_early_cutoff": unknown.information_known_at(
            early_cutoff
        ),
    }


def _observe_execution_price(inputs: dict[str, Any]) -> dict[str, Decimal]:
    session = date.fromisoformat(inputs["session_date"])
    model = ExecutionModel(
        slippage_rate_buy=Decimal(inputs["slippage_rate_buy"]),
        slippage_rate_sell=Decimal(inputs["slippage_rate_sell"]),
    )
    observed: dict[str, Decimal] = {}
    for quote in inputs["quotes"]:
        instrument_id = InstrumentId.parse(quote["instrument_id"])
        side = TradeSide(quote["side"])
        tick = MASTER.resolve_rules(instrument_id, session).price_limit.tick_size
        observed[f"{instrument_id}:{side.value}"] = model.execution_price(
            Decimal(quote["open"]), side, tick
        )
    return observed


def _observe_lot_rules(inputs: dict[str, Any]) -> dict[str, Any]:
    instrument_id = InstrumentId.parse(inputs["instrument_id"])
    session = date.fromisoformat(inputs["session_date"])
    rule = MASTER.resolve_rules(instrument_id, session).lot
    return {
        "board_lot": rule.board_lot,
        "buy_increment": rule.buy_increment,
        "odd_lot_sell_policy": rule.odd_lot_sell_policy.value,
    }


_OBSERVERS = {
    "fees": _observe_fees,
    "price_limit": _observe_price_limit,
    "settlement": _observe_settlement,
    "availability": _observe_availability,
    "execution_price": _observe_execution_price,
    "lot_rules": _observe_lot_rules,
}


def observe(case: dict[str, Any]) -> dict[str, Any]:
    try:
        observer = _OBSERVERS[case["kind"]]
    except KeyError as error:
        raise AssertionError(f"unknown parity case kind {case['kind']!r}") from error
    return observer(case["inputs"])


def compare(case: dict[str, Any], observed: dict[str, Any]) -> list[dict[str, Any]]:
    """Per-key comparison with the case's declared tolerance."""
    tolerance = Decimal(case["tolerance"]) if _numeric_tolerance(case) else None
    deltas: list[dict[str, Any]] = []
    for key, expected_value in case["expected"].items():
        if key not in observed:
            deltas.append(
                {"key": key, "expected": expected_value, "observed": None, "delta": None}
            )
            continue
        actual = observed[key]
        if isinstance(expected_value, bool) or expected_value is None:
            matched = actual is expected_value
            delta: str | None = None
        elif isinstance(actual, date):
            matched = actual.isoformat() == expected_value
            delta = None
        elif isinstance(actual, str) or isinstance(expected_value, int):
            matched = actual == expected_value
            delta = None
        else:
            expected_decimal = Decimal(str(expected_value))
            actual_decimal = Decimal(str(actual))
            delta_decimal = actual_decimal - expected_decimal
            matched = tolerance is not None and abs(delta_decimal) <= tolerance
            delta = str(delta_decimal)
        deltas.append(
            {
                "key": key,
                "expected": str(expected_value),
                "observed": str(actual),
                "delta": delta,
                "matched": matched,
            }
        )
    return deltas


def _numeric_tolerance(case: dict[str, Any]) -> bool:
    try:
        Decimal(case["tolerance"])
    except Exception:
        return False
    return True


def evaluate_cases() -> list[dict[str, Any]]:
    results = []
    for case in PARITY["cases"]:
        observed = observe(case)
        deltas = compare(case, observed)
        results.append(
            {
                "case_id": case["case_id"],
                "title": case["title"],
                "kind": case["kind"],
                "source": case["source"],
                "semantics": case["semantics"],
                "tolerance": case["tolerance"],
                "expected": case["expected"],
                "observed": {key: str(value) for key, value in observed.items()},
                "deltas": deltas,
                "status": "PASS" if all(delta["matched"] for delta in deltas) else "FAIL",
            }
        )
    return results


def _digest(payload: dict[str, Any]) -> str:
    rendered = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + sha256(rendered.encode("utf-8")).hexdigest()


def build_report() -> dict[str, Any]:
    results = evaluate_cases()
    passed = sum(1 for result in results if result["status"] == "PASS")
    payload: dict[str, Any] = {
        "report_schema_version": REPORT_SCHEMA_VERSION,
        "cases_version": PARITY["cases_version"],
        "evaluation_scope": "OFFLINE_FROZEN_PUBLIC_RULES",
        "generated_at": PARITY["evaluated_at"],
        "source_statement": PARITY["source_statement"],
        "tolerances": PARITY["tolerances"],
        "cases": results,
        "summary": {
            "case_count": len(results),
            "passed": passed,
            "failed": len(results) - passed,
        },
        "excluded_scope": PARITY["excluded_scope"],
        "credentials_prerequisites": PARITY["credentials_prerequisites"],
        "commands": PARITY["commands"],
    }
    payload["report_digest"] = _digest(payload)
    return payload


def render_report(payload: dict[str, Any]) -> bytes:
    return (
        json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def write_report(payload: dict[str, Any], *, directory: Path | None = None) -> Path:
    target = directory
    if target is None:
        override = os.environ.get(REPORT_DIR_ENV)
        target = Path(override) if override else DEFAULT_REPORT_DIR
    target.mkdir(parents=True, exist_ok=True)
    path = target / OFFLINE_REPORT_NAME
    path.write_bytes(render_report(payload))
    return path


class TestParityReferenceCases:
    @pytest.mark.parametrize("case", PARITY["cases"], ids=lambda case: case["case_id"])
    def test_case_matches_frozen_independent_evidence(
        self, case: dict[str, Any]
    ) -> None:
        observed = observe(case)
        deltas = compare(case, observed)

        assert all(delta["matched"] for delta in deltas), deltas

    def test_no_case_is_missing_its_source_semantics_or_tolerance(self) -> None:
        for case in PARITY["cases"]:
            assert case["source"]["authority"]
            assert case["source"]["reference"]
            assert case["source"]["accessed_on"]
            assert case["source"]["rights"]
            assert case["semantics"]
            assert case["tolerance"]

    def test_report_is_immutable_and_reproducible(self, tmp_path: Path) -> None:
        first = write_report(build_report(), directory=tmp_path)
        second = write_report(build_report(), directory=tmp_path)

        assert first.read_bytes() == second.read_bytes()
        assert render_report(build_report()) == first.read_bytes()

    def test_generated_report_matches_the_committed_parity_evidence(
        self, tmp_path: Path
    ) -> None:
        generated = write_report(build_report(), directory=tmp_path)
        committed = DEFAULT_REPORT_DIR / OFFLINE_REPORT_NAME

        assert generated.read_bytes() == committed.read_bytes()

    def test_report_records_sources_excluded_scope_and_zero_unexplained_delta(self) -> None:
        payload = build_report()

        assert payload["summary"] == {
            "case_count": len(PARITY["cases"]),
            "passed": len(PARITY["cases"]),
            "failed": 0,
        }
        assert payload["excluded_scope"]
        assert payload["credentials_prerequisites"]
        assert payload["commands"]
        assert payload["report_digest"].startswith("sha256:")
        for result in payload["cases"]:
            assert result["source"]["authority"]
            assert result["source"]["accessed_on"]
            assert result["semantics"]
            assert result["tolerance"]
            assert result["status"] == "PASS"
