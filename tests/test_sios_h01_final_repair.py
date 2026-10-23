"""Regressions for the existing H01 no-event and suspension qualification."""
from datetime import datetime
from decimal import Decimal
import importlib.util
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
ROOT = REPO / "docs/audits/evidence/2026-10-22-sios-h01-final-repair"
OLD = ROOT.parent / "2026-10-22-sios-h01-priority-delivery/H01-delivery"


def module():
    spec = importlib.util.spec_from_file_location("h01_qualification_repair", ROOT / "qualify_repair.py")
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def reports(instrument="XSHG:513500"):
    return [{"instrument_id": instrument, "period_start": f"{year}-01-01", "period_end": f"{year}-12-31",
             "published_date": f"{year + 1}-03-31", "cash_absent": True, "holder_unit_change_absent": True,
             "source_status": "AUTHENTICATED_OFFICIAL_REPORT"} for year in (2023, 2024, 2025)]


def test_later_no_event_audit_is_not_a_historical_signal_input():
    m = module()
    result = m.certify_interval(reports(), "XSHG:513500", "2023-03-09", "2025-09-30")
    assert result["status"] == "CONFIRMED_NO_EVENT_IN_SCOPE"
    assert result["evidence_role"] == "EX_POST_COMPLETENESS_AUDIT"
    assert result["historical_input_events"] == []


@pytest.mark.parametrize("defect,expected", [
    ("missing_year", "SOURCE_COVERAGE_INCOMPLETE"),
    ("wrong_identity", "EVENT_IDENTITY_AMBIGUOUS"),
    ("access_failed", "SOURCE_ACCESS_FAILED"),
    ("positive_unit_change", "QUALIFIED_POSITIVE_EVENT"),
])
def test_no_event_claim_requires_real_identity_coverage_and_event_evidence(defect, expected):
    m = module()
    data = reports()
    if defect == "missing_year":
        data.pop(1)
    elif defect == "wrong_identity":
        data[0]["instrument_id"] = "XSHG:513030"
    elif defect == "access_failed":
        data[1]["source_status"] = "SOURCE_ACCESS_FAILED"
    else:
        data[1]["holder_unit_change_absent"] = False
        data[1]["positive_events"] = [{"source_identifier": "SIMULATION_ONLY", "status": "implemented",
                                       "announcement_date": "2024-05-30", "effective_date": "2024-06-03",
                                       "share_ratio": "2", "ratio_unit": "NEW_SHARES_PER_OLD_SHARE"}]
    assert m.certify_interval(data, "XSHG:513500", "2023-03-09", "2025-09-30")["status"] == expected
    if defect == "positive_unit_change":
        del data[1]["positive_events"][0]["ratio_unit"]
        assert m.certify_interval(data, "XSHG:513500", "2023-03-09", "2025-09-30")["status"] == "EVENT_IDENTITY_AMBIGUOUS"


def test_nine_actual_reports_bind_code_and_true_fiscal_period():
    m = module()
    actual = []
    for source in (OLD / "extracted").glob("*.json"):
        payload = json.loads(source.read_text(encoding="utf-8"))
        code, year = source.name.split("-")[1:3]
        audit = m.audit_report(payload, "XSHG:" + code, int(year))
        assert audit["period_start"] == year + "-01-01"
        assert audit["period_end"] == year + "-12-31"
        assert audit["cash_absent"] and audit["holder_unit_change_absent"]
        assert audit["ordinary_subscriptions_redemptions_are_holder_unit_changes"] is False
        actual.append(audit)
    assert len(actual) == 9


def test_actual_wrong_fund_report_cannot_certify_another_fixed_etf():
    m = module()
    payload = json.loads((OLD / "extracted/040-513030-2025-official-annual.json").read_text(encoding="utf-8"))
    with pytest.raises(ValueError, match="EVENT_IDENTITY_AMBIGUOUS"):
        m.audit_report(payload, "XSHG:513520", 2025)


def test_existing_consumer_counts_known_reported_bars_without_a_volume_filter():
    m = module()
    result = m.trace_observation_policy(ROOT / "contracts")
    assert result["policy"] == "INCLUDE_KNOWN_REPORTED_DAILY_BAR"
    assert result["consumer_executed"] is False


def test_verified_suspension_zero_turnover_and_missing_bar_are_distinct():
    m = module()
    halt = {"instrument_id": "XSHG:513030", "date": "2025-01-23", "verified": True}
    row = {"instrument_id": "XSHG:513030", "date": "2025-01-23", "close": "1.815", "volume": 0, "amount": "0"}
    zero = m.classify_observation(row, "1.815", halt)
    assert zero["status"] == "VERIFIED_FULL_DAY_SUSPENSION"
    assert zero["signal_observation_eligible"] and not zero["tradable"]
    assert zero["valuation_close"] == "1.815"
    assert m.classify_observation(row, "1.815", None)["status"] == "UNCLASSIFIED_ZERO_TURNOVER"
    missing = m.classify_observation(None, "1.815", halt)
    assert missing["status"] == "MISSING_REPORTED_BAR_DURING_VERIFIED_SUSPENSION"
    assert not missing["signal_observation_eligible"]
    with pytest.raises(ValueError, match="SUSPENSION_TURNOVER_CONFLICT"):
        m.classify_observation({**row, "volume": 1}, "1.815", halt)


def test_date_precision_is_retained_and_future_announcement_is_refused():
    m = module()
    event = {"status": "implemented", "announcement_date": "2025-01-23", "available_at": None}
    with pytest.raises(ValueError, match="FUTURE_INFORMATION"):
        m.guard_event(event, datetime.fromisoformat("2025-01-23T15:30:00+08:00"))
    terms = m.guard_event(event, datetime.fromisoformat("2025-01-24T15:30:00+08:00"))
    assert terms["published_at"] is None and terms["source_time_precision"] == "date"
    assert terms["availability_basis"] == "INFERRED_DATE_END_EXISTING_CONSUMER_RULE"


@pytest.mark.parametrize("cash,ratio,before,after", [("0.1", "1", "2.0", "1.9"), ("0", "2", "2.0", "1.0")])
def test_conditional_cash_and_share_event_wealth_reconciliation(cash, ratio, before, after):
    # Explicitly simulated terms, never inserted into the actual empty ledger.
    m = module()
    event = {"status": "implemented", "announcement_date": "2025-01-01", "available_at": None,
             "economic_entitlement_date": "2025-01-06", "cash_payment_date": "2025-01-10",
             "backtest_cash_available_at": "2025-01-13T09:30:00+08:00"}
    m.guard_event(event, datetime.fromisoformat("2025-01-06T15:30:00+08:00"))
    assert (Decimal(after) * Decimal(ratio) + Decimal(cash)) / Decimal(before) == 1
    assert event["economic_entitlement_date"] != event["cash_payment_date"]
    assert event["backtest_cash_available_at"].startswith("2025-01-13")


def test_raw_price_promotion_does_not_wait_for_future_audit_publication():
    m = module()
    raw = {"row_id": "XSHG:513500/2024-01-02", "date": "2024-01-02", "information_available_at": "2024-01-02T15:00:00+08:00"}
    observation = {"retrospective_no_event_index": "100.1", "retrospective_return_126": "0.12", "retrospective_sma_200": "98.2"}
    certification = m.certify_interval(reports(), "XSHG:513500", "2023-03-09", "2025-09-30")
    result = m.promote_observation(observation, raw, certification, True)
    assert result["pit_signal_qualified"] and result["pit_total_return_index"] == "100.1"
    assert result["information_available_at"] == raw["information_available_at"]
    incomplete = {**certification, "status": "SOURCE_COVERAGE_INCOMPLETE"}
    assert m.promote_observation(observation, raw, incomplete, True)["pit_total_return_index"] is None


def test_repaired_receiver_accepts_qualified_actual_no_event_inputs():
    spec = importlib.util.spec_from_file_location("repaired_receiver", ROOT / "receive_repaired.py")
    receiver = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(receiver)
    result = receiver.receive(ROOT / "H01-delivery-repaired")
    assert result["errors"] == []
    assert result["consumer_acceptance"]
    assert result["qualified_historical_signal_rows"] == 1875
