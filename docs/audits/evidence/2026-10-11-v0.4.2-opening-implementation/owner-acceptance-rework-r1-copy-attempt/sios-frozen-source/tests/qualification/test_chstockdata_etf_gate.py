"""ETF qualification gate: chstockdata capability scope (M0 scope).

Offline tests run recorded vendor-shaped payloads through the real adapter and
the approved Instrument Master and never touch the network. They verify the
domestic broad-based equity, gold, and bond ETF matrices, prove that passing
one subtype never approves another, and emit a deterministic,
capability-scoped qualification report.

Live tests are opt-in: they run only with
``SIOS_CHSTOCKDATA_LIVE_QUALIFICATION=1`` and a pinned ``chstockdata``
installation with a local vipdoc tree, and belong to the controlled release
environment rather than normal CI.
"""

from __future__ import annotations

import copy
import os
from pathlib import Path

import pytest
from etf_qualification import (
    APPROVED_SUBTYPES,
    DEFAULT_REPORT_DIR,
    OFFLINE_REPORT_NAME,
    evaluate_offline,
    load_matrix,
    load_payloads,
    render_report,
    report_status_of,
    write_report,
)

from systematic_investing.adapters.chstockdata.provider import (
    PINNED_CHSTOCKDATA_VERSION,
    ChStockDataProvider,
    LibraryChStockDataClient,
)
from systematic_investing.data.contracts import ProviderEvidence
from systematic_investing.domain.identifiers import InstrumentId
from systematic_investing.domain.instruments import FundSubtype
from systematic_investing.instrument_master.models import UnknownInstrumentError
from systematic_investing.instrument_master.repository import default_m0_master

MATRIX = load_matrix()
PAYLOADS = load_payloads()
EVALUATION_SESSION = MATRIX["evaluation_session"]

LIVE_ENABLED = os.environ.get("SIOS_CHSTOCKDATA_LIVE_QUALIFICATION") == "1"
live_qualification = pytest.mark.skipif(
    not LIVE_ENABLED,
    reason=(
        "opt-in live qualification: set SIOS_CHSTOCKDATA_LIVE_QUALIFICATION=1 and "
        "install the pinned chstockdata release with a local vipdoc tree"
    ),
)


class TestQualificationScope:
    def test_matrix_declares_only_the_three_approved_m0_subtypes(self) -> None:
        declared = {entry["subtype"] for entry in MATRIX["subtypes"]}

        assert declared == {"BROAD_BASED_EQUITY", "GOLD", "BOND"}
        assert declared == {subtype.value for subtype in APPROVED_SUBTYPES}

    def test_matrix_instruments_use_canonical_ids_and_vendor_symbols(self) -> None:
        for entry in MATRIX["subtypes"]:
            for instrument in entry["instruments"]:
                instrument_id = InstrumentId.parse(instrument["instrument_id"])
                prefix = "sh" if instrument_id.exchange.value == "XSHG" else "sz"

                assert instrument["vendor_symbol"] == f"{prefix}{instrument_id.symbol}"

    def test_rejected_scope_is_explicit_and_never_approved(self) -> None:
        rejected_scope = {entry["scope"] for entry in MATRIX["rejected_scope"]}

        assert rejected_scope >= {
            "CROSS_BORDER_QDII",
            "MONEY_MARKET",
            "OTHER_UNVERIFIED",
        }
        master = default_m0_master()
        for entry in MATRIX["rejected_scope"]:
            instrument_id = InstrumentId.parse(entry["representative"])
            with pytest.raises(UnknownInstrumentError):
                master.resolve_rules(instrument_id, EVALUATION_SESSION)

    def test_unverified_subtypes_are_not_even_expressible(self) -> None:
        with pytest.raises(ValueError):
            FundSubtype("CROSS_BORDER_QDII")
        with pytest.raises(ValueError):
            FundSubtype("MONEY_MARKET")


class TestOfflineEtfGate:
    def test_gate_passes_every_check_for_every_approved_instrument(self) -> None:
        report = evaluate_offline(MATRIX, PAYLOADS)
        approved_subtypes = {entry["subtype"] for entry in MATRIX["subtypes"]}

        for entry in MATRIX["subtypes"]:
            assert report_status_of(report, entry["subtype"]) == "PASS"
        for check in report.checks:
            if check.subtype not in approved_subtypes:
                assert check.status == "REJECTED"
                continue
            assert check.status == "PASS", f"{check.check_id} failed for {check.instrument_id}"

    def test_every_subtype_carries_the_full_capability_check_set(self) -> None:
        report = evaluate_offline(MATRIX, PAYLOADS)
        required = {
            "ROUTING",
            "OHLCV_PRE_CLOSE",
            "UNITS",
            "CALENDAR",
            "TRADABILITY",
            "ADJUSTMENT_ACTIONS",
            "FRESHNESS",
            "PROVIDER_VERSION",
        }

        for entry in MATRIX["subtypes"]:
            for instrument in entry["instruments"]:
                checks = {
                    check.check_id
                    for check in report.checks
                    if check.instrument_id == instrument["instrument_id"]
                }
                assert required <= checks, f"{instrument['instrument_id']}: {sorted(checks)}"

    def test_recorded_edge_events_are_qualified(self) -> None:
        report = evaluate_offline(MATRIX, PAYLOADS)
        edge_cases = MATRIX["edge_events"]

        assert edge_cases
        for case in edge_cases:
            checks = [
                check
                for check in report.checks
                if check.instrument_id == case["instrument_id"]
                and check.check_id == "EDGE_EVENTS"
            ]
            assert checks, f"no edge-event check for {case['instrument_id']}"
            assert checks[0].status == "PASS", checks[0].observed
            assert case["case_id"] in checks[0].observed

    def test_a_broken_capability_fails_only_its_own_subtype(self) -> None:
        broken = copy.deepcopy(PAYLOADS)
        gold = next(
            entry for entry in MATRIX["subtypes"] if entry["subtype"] == "GOLD"
        )
        instrument_id = gold["instruments"][0]["instrument_id"]
        for row in broken["daily_bars"][instrument_id]["payload"]["rows"]:
            row.pop("pre_close", None)

        report = evaluate_offline(MATRIX, broken)

        assert report_status_of(report, "GOLD") == "FAIL"
        assert report_status_of(report, "BROAD_BASED_EQUITY") == "PASS"
        assert report_status_of(report, "BOND") == "PASS"

    def test_report_is_capability_scoped_and_records_evidence(self) -> None:
        report = evaluate_offline(MATRIX, PAYLOADS)
        payload = report.payload

        assert payload["report_schema_version"] == "m0-etf-qualification-report-1"
        assert payload["matrix_version"] == MATRIX["matrix_version"]
        assert payload["evaluation_scope"] == "OFFLINE_RECORDED"
        assert payload["provider"]["version"] == PINNED_CHSTOCKDATA_VERSION
        assert payload["provider"]["pinned_version"] == PINNED_CHSTOCKDATA_VERSION
        assert {
            entry["subtype"]: entry["status"] for entry in payload["approved_scope"]
        } == {"BROAD_BASED_EQUITY": "PASS", "GOLD": "PASS", "BOND": "PASS"}
        assert payload["excluded_scope"]
        assert payload["tolerances"]["calendar_alignment"] == "exact"
        assert payload["independent_evidence"]
        assert payload["credentials_prerequisites"]
        assert payload["commands"]
        assert payload["report_digest"].startswith("sha256:")

    def test_report_generation_is_deterministic(self) -> None:
        first = render_report(evaluate_offline(MATRIX, PAYLOADS))
        second = render_report(evaluate_offline(MATRIX, PAYLOADS))

        assert first == second

    def test_generated_report_matches_the_committed_offline_evidence(
        self, tmp_path: Path
    ) -> None:
        report = evaluate_offline(MATRIX, PAYLOADS)
        generated = write_report(report, directory=tmp_path)
        committed = DEFAULT_REPORT_DIR / OFFLINE_REPORT_NAME

        assert generated.read_bytes() == committed.read_bytes()

    def test_report_path_is_outside_the_core_package(self) -> None:
        repository_root = Path(__file__).resolve().parents[2]
        report_dir = DEFAULT_REPORT_DIR.resolve()

        assert report_dir.is_relative_to(repository_root / "tests")
        assert not report_dir.is_relative_to(repository_root / "src")


class TestLiveEtfQualification:
    """Opt-in live capability checks for the controlled release environment."""

    @live_qualification
    def test_live_routing_and_ohlcv_pre_close(self) -> None:
        from live_qualification import live_provider, matrix_requests

        provider = live_provider()
        requests = matrix_requests(MATRIX)

        for request in requests:
            result = provider.fetch_daily_bars(request.bar_request)
            assert result.is_success, f"{request.instrument_id}: {result}"
            assert result.records, f"{request.instrument_id}: no bars in the window"
            for bar in result.records:
                assert bar.instrument_id == request.instrument_id
                assert bar.high >= max(bar.open, bar.close)
                assert bar.low <= min(bar.open, bar.close)
                assert bar.pre_close is None or bar.pre_close > 0

    @live_qualification
    def test_live_units_calendar_and_history_coverage(self) -> None:
        from live_qualification import live_provider, matrix_requests

        provider = live_provider()
        for request in matrix_requests(MATRIX):
            result = provider.fetch_daily_bars(request.bar_request)
            assert result.is_success
            assert {bar.volume_unit for bar in result.records} == {"SHARE"}
            assert {bar.amount_unit for bar in result.records} == {"CNY"}
            assert {bar.currency for bar in result.records} == {"CNY"}

            calendar = provider.fetch_calendar(request.calendar_request)
            assert calendar.is_success
            open_days = {session.session_date for session in calendar.records if session.is_open}
            for bar in result.records:
                assert bar.session_date in open_days

    @live_qualification
    def test_live_tradability_adjustment_and_freshness(self) -> None:
        from live_qualification import live_provider, matrix_requests

        provider = live_provider()
        for request in matrix_requests(MATRIX):
            tradability = provider.fetch_tradability(request.tradability_request)
            assert tradability.is_success
            assert tradability.records

            actions = provider.fetch_corporate_actions(request.corporate_action_request)
            assert actions.is_success

            bars = provider.fetch_daily_bars(request.bar_request)
            for bar in bars.records:
                assert bar.adjustment_mode.value == "RAW"
                assert bar.availability.retrieved_at is not None
                if bar.availability.information_available_at is not None:
                    assert bar.availability.information_available_at <= (
                        bar.availability.retrieved_at
                    )

    @live_qualification
    def test_live_provider_version_evidence(self) -> None:
        from live_qualification import live_provider

        provider = live_provider()
        evidence = provider.capability_evidence()

        assert isinstance(evidence, ProviderEvidence)
        assert evidence.provider_version == PINNED_CHSTOCKDATA_VERSION
        assert evidence.adapter_version == ChStockDataProvider.ADAPTER_VERSION

    @live_qualification
    def test_live_client_requires_the_pinned_release(self) -> None:
        import chstockdata

        assert chstockdata.__version__ == PINNED_CHSTOCKDATA_VERSION
        LibraryChStockDataClient()
