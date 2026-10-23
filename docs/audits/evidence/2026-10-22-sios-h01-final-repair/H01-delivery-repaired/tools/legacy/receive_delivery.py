"""Independent stdlib-only receiver. Does not import the exporter or SIOS.

Exit 0 = consumer acceptance, 2 = authentic partial delivery with named gaps,
1 = structural/integrity defect. A passing integrity check is not Gate PASS.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import struct


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def receive(package):
    errors = []
    checks = []
    def check(condition, message):
        checks.append(message)
        if not condition:
            errors.append(message)
    manifest = read_json(package / "manifest.json")
    manifest_sha = hashlib.sha256((package / "manifest.json").read_bytes()).hexdigest()
    check((package / "manifest.sha256").read_text(encoding="utf-8").split()[0] == manifest_sha, "manifest digest")
    for name, item in manifest["files"].items():
        path = (package / name).resolve()
        check(path.is_relative_to(package.resolve()), "confined manifest path: " + name)
        check(path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"], "file digest: " + name)
    with (package / "raw_market_data.csv").open(encoding="utf-8", newline="") as stream:
        raw = list(csv.DictReader(stream))
    observations = [json.loads(line) for line in (package / "total_return_observations.jsonl").read_text(encoding="utf-8").splitlines()]
    calendar = read_json(package / "calendar.json")["sessions"]
    coverage = read_json(package / "coverage_and_unknowns.json")
    actions = read_json(package / "fund_actions.json")
    codes = ["513500", "513030", "513520"]
    check(manifest["securities"] == codes, "fixed three instruments")
    check(manifest["observation_window"] == ["2024-01-02", "2025-09-30"], "fixed observation window")
    check(len(calendar) == 625 and len(set(calendar)) == 625, "625 distinct required sessions")
    check(sum(d < "2024-01-02" for d in calendar) == 200, "200 independent prior warmup observations")
    check(len(raw) == 1875 and len(observations) == 1875, "real data rows for all three instruments")
    check(actions["events"] == [], "verified actual no-event data; no synthetic economic event")
    for event in actions["events"]:
        check(event.get("status") in {"implemented", "cancelled", "proposed"}, "unknown event rejection")
        announced = event.get("announcement_date")
        effective = event.get("ex_dividend_date") or event.get("effective_date")
        check(bool(announced and effective) and announced <= effective, "future announcement rejection")
    check(len(actions["issuer_report_evidence"]) == 9, "nine issuer reports")
    for report in actions["issuer_report_evidence"]:
        check(report["cash_status"] == report["split_status"] == "normal_empty", "issuer negative evidence")
        check(report["usage"] == "EX_POST_FACT_RECONCILIATION_ONLY_NOT_HISTORICAL_SIGNAL_INFORMATION", "later report is reconciliation only")
        check(bool(report["cash_evidence"]) and bool(report["split_evidence"]), "locatable cash and split evidence")
    check(all(item["historical_asof_event_index_coverage"] == "NOT_ATTESTED" for item in actions["per_instrument"]), "no invented historical event vintage")
    raw_by_id = {r["row_id"]: r for r in raw}
    check(len(raw_by_id) == len(raw), "unique raw identities")
    actual_zero = []
    for code in codes:
        raw_rows = [r for r in raw if r["instrument_id"] == "XSHG:" + code]
        tr_rows = [r for r in observations if r["instrument_id"] == "XSHG:" + code]
        check([r["date"] for r in raw_rows] == calendar, "raw calendar coverage " + code)
        check([r["date"] for r in tr_rows] == calendar, "TR calendar coverage " + code)
        body = (package / "raw_sources" / f"sh{code}.day").read_bytes()
        source_hash = hashlib.sha256(body).hexdigest()
        normalized = []
        for i, (row, tr) in enumerate(zip(raw_rows, tr_rows)):
            record = struct.unpack_from("<IIIIIfII", body, int(row["source_record_index"]) * 32)
            d, op, hi, lo, cl, amount, volume, reserved = record
            stamp = f"{d:08d}"
            check(row["date"] == stamp[:4] + "-" + stamp[4:6] + "-" + stamp[6:], "raw date identity")
            check([Decimal(row[k]) for k in ("open", "high", "low", "close")] == [Decimal(v) / 1000 for v in (op, hi, lo, cl)], "fund price divisor exactly 1000")
            check(int(row["volume"]) == volume and Decimal(row["amount"]) == Decimal.from_float(amount), "lossless amount and volume")
            check(row["source_sha256"] == source_hash, "source .day identity")
            check(row["information_available_at"] == row["date"] + "T15:00:00+08:00" and row["availability_basis"] == "EXCHANGE_RULE", "frozen consumer raw availability rule")
            if volume:
                check(Decimal(lo) / 1000 - Decimal(".001") <= Decimal.from_float(amount) / volume <= Decimal(hi) / 1000 + Decimal(".001"), "VWAP independent unit check")
            else:
                actual_zero.append(row["row_id"])
                check(row["trade_status"] == "NO_TRADE_RECORDED" and row["suspension_status"] == "UNKNOWN", "zero turnover retained without suspension inference")
            index = Decimal(100) * Decimal(row["close"]) / Decimal(raw_rows[0]["close"])
            normalized.append(index)
            check(abs(Decimal(tr["retrospective_no_event_index"]) - index) < Decimal("1e-24"), "independent no-event return reconciliation")
            check(tr["event_ids_applied"] == [] and tr["share_multiplier"] == "1" and tr["cash_adjustment"] == "0", "no double dividend or share adjustment")
            if i >= 125:
                expected = Decimal(row["close"]) / Decimal(raw_rows[i - 125]["close"]) - 1
                check(abs(Decimal(tr["retrospective_return_126"]) - expected) < Decimal("1e-24"), "126 known observations are 125 intervals")
                check(tr["return_126_base_date"] == raw_rows[i - 125]["date"], "126 base identity")
            else:
                check(tr["retrospective_return_126"] is None, "no insufficient-history return")
            if i >= 199:
                expected = sum(normalized[-200:]) / Decimal(200)
                check(abs(Decimal(tr["retrospective_sma_200"]) - expected) < Decimal("1e-24"), "independent SMA200 inputs")
            else:
                check(tr["retrospective_sma_200"] is None, "no insufficient-history SMA")
            check(not tr["pit_signal_qualified"] and all(tr[k] is None for k in ("pit_total_return_index", "pit_return_126", "pit_sma_200", "information_available_at")), "unknown historical event coverage fails closed")
            check(not tr["issuer_reports_used_as_signal_input"], "no future annual report information in signal")
    check(actual_zero == ["XSHG:513030/2025-01-23"], "actual zero-turnover date classified")
    check(all(tr["retrospective_return_126"] is not None and tr["retrospective_sma_200"] is not None for tr in observations if not tr["is_warmup"]), "all 425 observation dates have full retrospective warmup")
    check(len(coverage["unresolved_required_gaps"]) == 4, "four named gaps retained")
    check(manifest["qualified_pit_signal_rows"] == 0 and manifest["gate"] == "BLOCKED_WITH_NAMED_GAPS", "no false acceptance or PASS")
    ledger = read_json(package / "network_ledger.json")
    requests = ledger["requests"]
    check(len(requests) <= 80 and sum(e["downloaded_bytes"] for e in requests) <= 60_000_000, "authorized network budget")
    check(all(sum(other["url"] == e["url"] for other in requests) <= 2 for e in requests), "at most one retry per URL")
    return {"checked_at": datetime.now().astimezone().isoformat(), "manifest_sha256": manifest_sha,
            "integrity_and_recomputation": "PASS" if not errors else "FAIL", "checks_executed": len(checks),
            "errors": errors, "consumer_receipt": "BLOCKED_WITH_NAMED_GAPS", "consumer_acceptance": False,
            "qualified_historical_signal_rows": 0, "retrospective_observation_rows": len(observations),
            "required_gaps": coverage["unresolved_required_gaps"],
            "real_event_transition_test": "NOT_APPLICABLE: nine issuer reports authenticate no implemented cash or split event",
            "strategy_backtests_executed": 0, "consumer_repository_executed_or_modified": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("package", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    result = receive(args.package)
    if args.report:
        args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k:v for k,v in result.items() if k not in {"required_gaps"}}, ensure_ascii=False))
    raise SystemExit(1 if result["errors"] else 2 if not result["consumer_acceptance"] else 0)
