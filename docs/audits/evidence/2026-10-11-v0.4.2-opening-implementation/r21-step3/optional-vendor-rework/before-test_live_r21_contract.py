"""Deterministic checks of mandatory orchestration, never live substitutes."""

import pytest

import live_qualification as live


def test_capability_failure_does_not_short_circuit_other_securities_or_actions(tmp_path):
    outcomes = live.CapabilityOutcomes("contract", directory=tmp_path)
    reached = []

    def failed():
        reached.append("old")
        raise AssertionError("historical API cannot establish PIT")

    outcomes.check("XSHG:510300", "LEGACY_PIT", failed)
    outcomes.check("XSHG:510300", "ACTIONS", lambda: reached.append("actions"))
    outcomes.check("XSHE:159915", "OPENING", lambda: reached.append("next"))
    with pytest.raises(AssertionError, match="LEGACY_PIT"):
        outcomes.finish()
    assert reached == ["old", "actions", "next"]
    assert [item["status"] for item in outcomes.results] == ["FAIL", "PASS", "PASS"]
    assert (tmp_path / "contract.json").exists()


def test_actual_candidate_client_is_explicit_and_pin_remains_legacy():
    import chstockdata
    from systematic_investing.adapters.chstockdata.provider import (
        PINNED_CHSTOCKDATA_VERSION,
        ChStockDataConfigurationError,
        LibraryChStockDataClient,
    )

    assert chstockdata.__version__ == "0.4.2"
    assert PINNED_CHSTOCKDATA_VERSION == "0.3.0"
    with pytest.raises(ChStockDataConfigurationError):
        LibraryChStockDataClient()
    assert live.live_provider().capability_evidence().provider_version == "0.4.2"


def test_mandatory_orchestrator_attempts_all_actions_after_source_failures(monkeypatch, tmp_path):
    from test_chstockdata_etf_gate import TestLiveEtfQualification
    calls = []

    class FailedProvider:
        def __getattr__(self, capability):
            def invoke(request):
                calls.append((capability, request))
                raise RuntimeError("deterministic injected source failure")
            return invoke

    monkeypatch.setattr(live, "live_provider", lambda: FailedProvider())
    monkeypatch.setenv("SIOS_LIVE_EVIDENCE_DIR", str(tmp_path))
    with pytest.raises(AssertionError, match="LEGACY_PIT_FAIL_CLOSED"):
        TestLiveEtfQualification().test_live_tradability_adjustment_and_freshness()
    actions = [request for name, request in calls if name == "fetch_corporate_actions"]
    assert len(actions) == 4
    assert {str(request.instrument_ids[0]) for request in actions} >= {
        "XSHG:510300", "XSHE:159915", "XSHG:518880", "XSHG:511010"}
    import json
    report = json.loads((tmp_path / "test_live_tradability_adjustment_and_freshness.json").read_text(encoding="utf-8"))
    assert len(report["outcomes"]) == 38
    assert all(item["status"] == "FAIL" for item in report["outcomes"])


@pytest.mark.parametrize("symbol", ["510300", "511010"])
def test_recorded_helper_chain_proves_real_engine_fill_before_live(tmp_path, symbol):
    import json
    from dataclasses import replace
    from datetime import date, datetime
    from pathlib import Path
    from etf_qualification import build_provider, load_payloads, load_matrix
    from systematic_investing.data.contracts import ProviderSuccess
    from systematic_investing.domain.historical_opening import HistoricalOpeningEvidence, HISTORICAL_SUSPENSION_GAP
    from systematic_investing.domain.market import Availability, AvailabilityBasis, TradabilityStatus, TradabilityStatusKind
    request = next(request for request in live.matrix_requests(load_matrix()) if request.instrument_id.symbol == symbol)
    now = datetime.now(live.MARKET_TIMEZONE)
    provider = build_provider(load_payloads(), retrieved_at=now)
    bars = provider.fetch_daily_bars(request.bar_request)
    calendar = provider.fetch_calendar(request.calendar_request)
    sessions = calendar.records + (replace(calendar.records[-1], session_date=date(2026, 9, 14), is_open=True),)
    calendar = replace(calendar, records=sessions)
    actions = provider.fetch_corporate_actions(request.corporate_action_request)
    fixture = Path(__file__).resolve().parents[1] / f"fixtures/chstockdata/historical_opening/{symbol}-2026-09-11.json"
    fact = HistoricalOpeningEvidence.from_payload(json.loads(fixture.read_text(encoding="utf-8"))["data"])
    opening = ProviderSuccess((fact,), bars.evidence)
    gap = TradabilityStatus(request.instrument_id, request.tradability_request.session_date,
        TradabilityStatusKind.UNKNOWN, HISTORICAL_SUSPENSION_GAP,
        Availability(None, now, AvailabilityBasis.UNKNOWN), "recorded-gap")
    proof = live.execution_proof(request.instrument_id, request.tradability_request.session_date,
        bars, calendar, actions, (None, (gap,)), opening, directory=tmp_path)
    assert proof["plans"] and proof["fills"]
    assert proof["snapshot_manifest"]["snapshot_schema_version"] == "v3-historical-opening"
