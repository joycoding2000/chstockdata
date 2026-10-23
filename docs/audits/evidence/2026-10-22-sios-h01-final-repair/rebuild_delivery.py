"""Reuse the original H01 export, repair qualification, and seal a new package."""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import zipfile

from qualify_repair import audit_report, certify_interval, classify_observation, promote_observation, trace_observation_policy

OLD_MANIFEST = "68ca0d4facc72b03f4828aae1b254fbd10beec4b456d7aa1ff80cea0e89f1dd0"
CODES = ("513500", "513030", "513520")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def initialize(old_zip, package, evidence):
    if package.exists():
        raise ValueError("new package directory already exists; original artifacts are never overwritten")
    package.mkdir(parents=True)
    with zipfile.ZipFile(old_zip) as archive:
        manifest_body = archive.read("H01-delivery/manifest.json")
        if hashlib.sha256(manifest_body).hexdigest() != OLD_MANIFEST:
            raise ValueError("original manifest identity mismatch")
        manifest = json.loads(manifest_body)
        for name, entry in manifest["files"].items():
            body = archive.read("H01-delivery/" + name)
            if hashlib.sha256(body).hexdigest() != entry["sha256"]:
                raise ValueError("original source integrity failure: " + name)
        for member in archive.infolist():
            relative = Path(member.filename).relative_to("H01-delivery")
            target = package / relative
            if not target.resolve().is_relative_to(package.resolve()):
                raise ValueError("unsafe archive path")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(member))
    parent = package / "parent_evidence"
    parent.mkdir()
    for name in ("manifest.json", "manifest.sha256", "raw_market_data.csv", "total_return_observations.jsonl", "fund_actions.json",
                 "coverage_and_unknowns.json", "provenance.json", "schema.json", "validation_report.json", "README.md"):
        (package / name).rename(parent / name)
    legacy = package / "tools/legacy"
    legacy.mkdir()
    for name in ("build_delivery.py", "receive_delivery.py", "extract_reports.py"):
        (package / "tools" / name).rename(legacy / name)
    for name in ("qualify_repair.py", "rebuild_delivery.py", "receive_repaired.py"):
        shutil.copy2(evidence / name, package / "tools" / name)
    shutil.copytree(evidence / "contracts", package / "contracts", dirs_exist_ok=True)
    shutil.copytree(evidence / "sources", package / "sources-repair")
    shutil.copy2(evidence / "network_ledger.json", package / "network_ledger.repair.json")
    shutil.copy2(evidence / "baseline.json", package / "repair_baseline.json")
    write(package / "parent_identity.json", {"manifest_sha256": OLD_MANIFEST, "zip_sha256": sha(old_zip), "original_zip_preserved": True})


def extract_again(package, filename):
    spec = importlib.util.spec_from_file_location("frozen_report_extractor", package / "tools/legacy/extract_reports.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    kind, blocks = module.report_text_blocks((package / filename).read_bytes())
    return {"locator_kind": kind, "blocks": blocks}


def rebuild(package, reaudit=False):
    parent = package / "parent_evidence"
    parent_manifest = read(parent / "manifest.json")
    if sha(parent / "manifest.json") != OLD_MANIFEST:
        raise ValueError("original manifest identity mismatch")
    old_actions = read(parent / "fund_actions.json")
    audits, certificates = [], {}
    for reference in old_actions["issuer_report_evidence"]:
        filename = reference["source_file"]
        if sha(package / filename) != reference["source_sha256"]:
            raise ValueError("SOURCE_ACCESS_FAILED: report identity changed")
        cached = read(package / "extracted" / (Path(filename).stem + ".json"))
        cached_path = "extracted/" + Path(filename).stem + ".json"
        if sha(package / cached_path) != parent_manifest["files"][cached_path]["sha256"]:
            raise ValueError("SOURCE_COVERAGE_INCOMPLETE: cached extraction changed")
        if reaudit:
            actual = extract_again(package, filename)
            if actual["blocks"] != cached["blocks"] or actual["locator_kind"] != cached["locator_kind"]:
                raise ValueError("re-extracted report differs from the immutable original evidence")
        audit = audit_report(cached, reference["instrument_id"], int(reference["period_start"][:4]))
        audits.append({**audit, "published_date": reference["published_date"], "published_at": None,
                       "source_file": filename, "source_sha256": reference["source_sha256"],
                       "source_url": reference["source_url"], "source_time_precision": "date",
                       "evidence_role": "EX_POST_COMPLETENESS_AUDIT"})
    for code in CODES:
        identifier = "XSHG:" + code
        certificates[identifier] = certify_interval([r for r in audits if r["instrument_id"] == identifier], identifier, "2023-03-09", "2025-09-30")
    policy = trace_observation_policy(package / "contracts")
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise SystemExit("Optional pypdf is needed for official-PDF revalidation; all source and parent evidence is preserved") from exc
    ledger = read(package / "network_ledger.repair.json")
    entry = next(e for e in ledger["requests"] if e["status"] == "success")
    halt_file = "sources-repair/" + Path(entry["file"]).name
    if sha(package / halt_file) != entry["sha256"]:
        raise ValueError("halt PDF identity mismatch")
    halt_text = "".join(p.extract_text() for p in PdfReader(package / halt_file).pages)
    compact = "".join(halt_text.split())
    if not all(s in compact for s in ("交易代码：513030", "2025年1月23日开市起停牌至收市", "二零二五年一月二十三日", "华安基金管理有限公司")):
        raise ValueError("official full-day halt identity or date not authenticated")
    halt = {"instrument_id": "XSHG:513030", "date": "2025-01-23", "verified": True,
            "status": "VERIFIED_FULL_DAY_SUSPENSION", "source_file": halt_file, "source_sha256": entry["sha256"],
            "source_url": entry["url"], "announcement_date": "2025-01-23", "published_at": None,
            "source_time_precision": "date", "effective_period": "EXCHANGE_OPEN_THROUGH_CLOSE",
            "conservative_rule_available_at": "2025-01-23T23:59:59+08:00",
            "availability_basis": "INFERRED_DATE_END_EXISTING_CONSUMER_RULE_NOT_OBSERVED_PUBLICATION_TIME",
            "ex_ante_tradability_known_at_open": "NOT_ATTESTED", "historical_tradability_fact_role": "EX_POST_COMPLETENESS_AUDIT",
            "signal_observation_policy": policy["policy"], "source_quote": "2025年1月23日开市起停牌至收市"}
    with (parent / "raw_market_data.csv").open(encoding="utf-8", newline="") as stream:
        raw = list(csv.DictReader(stream))
    originals = [json.loads(line) for line in (parent / "total_return_observations.jsonl").read_text(encoding="utf-8").splitlines()]
    raw_by_id, previous = {}, {}
    for row in raw:
        instrument = row["instrument_id"]
        result = classify_observation(row, previous.get(instrument), halt)
        row.update({"trade_status": result["status"], "signal_observation_eligible": result["signal_observation_eligible"],
                    "valuation_close": result["valuation_close"], "historical_execution_allowed": False if result["status"] == "VERIFIED_FULL_DAY_SUSPENSION" else "NOT_QUALIFIED_BY_THIS_PACKAGE"})
        if result["status"] == "VERIFIED_FULL_DAY_SUSPENSION":
            row["suspension_status"] = "FULL_DAY_SUSPENDED"
            row["intraday_suspension_status"] = "FULL_DAY_SUSPENDED"
            row["suspension_evidence_sha256"] = entry["sha256"]
        else:
            row["suspension_evidence_sha256"] = ""
        previous[instrument] = row["close"]
        raw_by_id[row["row_id"]] = row
    observations, qualified_history = [], {"XSHG:" + code: [] for code in CODES}
    for old in originals:
        row = raw_by_id[old["raw_row_id"]]
        eligible = row["signal_observation_eligible"] and (row["trade_status"] != "VERIFIED_FULL_DAY_SUSPENSION" or policy["policy"] == "INCLUDE_KNOWN_REPORTED_DAILY_BAR")
        result = promote_observation(old, row, certificates[row["instrument_id"]], eligible)
        history = qualified_history[row["instrument_id"]]
        history.append(result["pit_signal_qualified"])
        for field, flag, length in (("pit_return_126", "return_126_qualified", 126), ("pit_sma_200", "sma_200_qualified", 200)):
            if len(history) >= length and not all(history[-length:]):
                result[field], result[flag] = None, False
                if "UNQUALIFIED_OBSERVATION_IN_INPUT_WINDOW" not in result["unqualified_reason_codes"]:
                    result["unqualified_reason_codes"].append("UNQUALIFIED_OBSERVATION_IN_INPUT_WINDOW")
        result["observation_policy"] = policy["policy"]
        result["historical_trade_status"] = row["trade_status"]
        result["historical_execution_allowed"] = row["historical_execution_allowed"]
        observations.append(result)
    with (package / "raw_market_data.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(raw[0]))
        writer.writeheader()
        writer.writerows(raw)
    (package / "total_return_observations.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in observations), encoding="utf-8")
    updated_actions = {**old_actions, "interval_certifications": certificates, "ex_post_completeness_audit": audits,
                       "audit_role_is_not_historical_signal_input": True, "actual_event_count": 0}
    for record in updated_actions["per_instrument"]:
        record["qualification_status"] = certificates[record["instrument_id"]]["status"]
        record["status"] = "normal_empty" if record["qualification_status"] == "CONFIRMED_NO_EVENT_IN_SCOPE" else "blocked"
        record["coverage"] = "CERTIFIED_IMPLEMENTED_HOLDER_EVENTS_IN_TARGET_SCOPE" if record["status"] == "normal_empty" else record["qualification_status"]
    write(package / "fund_actions.json", updated_actions)
    write(package / "suspension_evidence.json", halt)
    write(package / "observation_policy.json", policy)
    old_coverage = read(parent / "coverage_and_unknowns.json")
    gaps = []
    for certificate in certificates.values():
        if certificate["status"] != "CONFIRMED_NO_EVENT_IN_SCOPE":
            gaps.append(certificate)
    if policy["policy"] != "INCLUDE_KNOWN_REPORTED_DAILY_BAR":
        gaps.append({"kind": "SUSPENSION_OBSERVATION_POLICY_REQUIRES_OWNER", "instrument_id": "XSHG:513030", "date": "2025-01-23"})
    for code in CODES:
        subset = [r for r in observations if r["instrument_id"] == "XSHG:" + code]
        old_coverage["per_instrument"][code].update({"qualified_pit_signal_rows": sum(r["pit_signal_qualified"] for r in subset),
            "qualified_warmup_rows": sum(r["pit_signal_qualified"] and r["is_warmup"] for r in subset),
            "complete_observation_period_signal_inputs": sum(r["return_126_qualified"] and r["sma_200_qualified"] and not r["is_warmup"] for r in subset),
            "event_qualification_status": certificates["XSHG:" + code]["status"]})
    complete = all(r["pit_signal_qualified"] for r in observations) and all(r["return_126_qualified"] and r["sma_200_qualified"] for r in observations if not r["is_warmup"]) and not gaps
    old_coverage.update({"unresolved_required_gaps": gaps, "acceptance": "PASS_FOR_RESEARCH_CONSUMER_ACCEPTANCE" if complete else "BLOCKED_WITH_PROVEN_GAPS",
                         "observation_policy": policy["policy"], "superseded_false_gaps": [g["id"] for g in old_coverage["unresolved_required_gaps"]]})
    write(package / "coverage_and_unknowns.json", old_coverage)
    provenance = read(parent / "provenance.json")
    provenance.update({"parent_manifest_sha256": OLD_MANIFEST,
        "repair_network": {"attempted_requests": len(ledger["requests"]), "downloaded_bytes": sum(e["downloaded_bytes"] for e in ledger["requests"]), "max_requests": 12, "max_bytes": 15_000_000},
        "pit": {"historical_signal_input": "Original RAW prices at existing EXCHANGE_RULE availability; actual event ledger is empty in audited scope",
                "ex_post_completeness_audit": "Nine official fiscal reports; publication dates are not signal inputs", "historical_information_leakage": "NOT_INTRODUCED_BY_LATER_NO_EVENT_AUDIT",
                "raw_observed_vintage": "NOT_ATTESTED_LIMITATION_RETAINED", "no_daily_official_negative_certificate_required": True}})
    write(package / "provenance.json", provenance)
    schema = read(parent / "schema.json")
    schema.update({"schema_version": "sios-h01-research-v2", "pit_signal_qualified_means": "The per-date total-return observation is qualified; separate flags cover 126/SMA200 readiness",
                   "qualification_status_enum": ["CONFIRMED_NO_EVENT_IN_SCOPE", "QUALIFIED_POSITIVE_EVENT", "SOURCE_COVERAGE_INCOMPLETE", "EVENT_IDENTITY_AMBIGUOUS", "SOURCE_ACCESS_FAILED"],
                   "no_event_audit_role": "EX_POST_COMPLETENESS_AUDIT", "historical_information_role": "HISTORICAL_SIGNAL_INPUT",
                   "trade_eligibility_is_separate_from_signal_and_valuation": True})
    write(package / "schema.json", schema)
    manifest = {"schema_version": "sios-h01-research-v2", "parent_manifest_sha256": OLD_MANIFEST,
                "verdict": "H01_DATA_PACKAGE_READY_FOR_CONSUMER_ACCEPTANCE" if complete else "H01_PARTIAL_WITH_PROVEN_GAPS",
                "gate": "PASS_FOR_RESEARCH_CONSUMER_ACCEPTANCE" if complete else "BLOCKED_WITH_PROVEN_GAPS",
                "securities": list(CODES), "observation_window": ["2024-01-02", "2025-09-30"], "raw_rows": len(raw),
                "qualified_pit_signal_rows": sum(r["pit_signal_qualified"] for r in observations),
                "qualified_observation_period_input_rows": sum(not r["is_warmup"] and r["return_126_qualified"] and r["sma_200_qualified"] for r in observations),
                "production_adapter_integrated": False, "strategy_experiment_authorized": False, "files": {}}
    for path in sorted(package.rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts and path.relative_to(package).as_posix() not in {"manifest.json", "manifest.sha256", "validation_report.json"}:
            manifest["files"][path.relative_to(package).as_posix()] = {"sha256": sha(path), "bytes": path.stat().st_size}
    write(package / "manifest.json", manifest)
    (package / "manifest.sha256").write_text(sha(package / "manifest.json") + "  manifest.json\n", encoding="utf-8")
    print(json.dumps({k:v for k,v in manifest.items() if k != "files"}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--old-zip", type=Path)
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--reaudit", action="store_true")
    args = parser.parse_args()
    if args.old_zip:
        initialize(args.old_zip, args.package, args.evidence)
    rebuild(args.package, reaudit=args.reaudit)
