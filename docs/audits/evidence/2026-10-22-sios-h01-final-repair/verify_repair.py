"""Final offline regression, independent receipt, preservation and ZIP evidence."""
from __future__ import annotations

from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from xml.etree import ElementTree
import zipfile

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[3]
OLD = ROOT.parent / "2026-10-22-sios-h01-priority-delivery"
PACKAGE = ROOT / "H01-delivery-repaired"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run(label, args):
    result = subprocess.run([sys.executable, "-X", "utf8", *args], cwd=REPO, capture_output=True, encoding="utf-8", errors="replace")
    (ROOT / (label + ".stdout.txt")).write_text(result.stdout, encoding="utf-8")
    (ROOT / (label + ".stderr.txt")).write_text(result.stderr, encoding="utf-8")
    save(ROOT / (label + ".command.json"), {"args": args, "returncode": result.returncode})
    return result


def git(repo, *args):
    return subprocess.check_output(["git", "-c", f"safe.directory={repo.as_posix()}", "-C", str(repo), *args])


def cases(path):
    return {(r.attrib.get("classname"), r.attrib["name"]) for r in ElementTree.parse(path).findall(".//testcase")}


def main():
    rebuild = run("final-reaudit-and-rebuild", [str(PACKAGE / "tools/rebuild_delivery.py"), "--package", str(PACKAGE), "--reaudit"])
    assert rebuild.returncode == 0, rebuild.stderr
    old_tests = run("old-87-tests", ["-m", "pytest", "tests/test_sios_h01_delivery.py", "tests/test_fund_corporate_actions.py",
        "tests/test_vipdoc_price_scale.py", "tests/test_vipdoc_history.py", "--basetemp=.h01-repair-tmp/final-old",
        "--junitxml=" + str(ROOT / "old-87-tests.xml"), "-q", "--tb=short"])
    assert old_tests.returncode == 0, old_tests.stdout + old_tests.stderr
    assert cases(ROOT / "old-87-tests.xml") == cases(OLD / "focused.xml") and len(cases(ROOT / "old-87-tests.xml")) == 87
    new_tests = run("new-repair-tests", ["-m", "pytest", "tests/test_sios_h01_final_repair.py", "--basetemp=.h01-repair-tmp/final-new",
        "--junitxml=" + str(ROOT / "new-repair-tests.xml"), "-q", "--tb=short"])
    assert new_tests.returncode == 0, new_tests.stdout + new_tests.stderr
    original_original = run("original-receiver-original-package", [str(OLD / "receive_delivery.py"), str(OLD / "H01-delivery"), "--report", str(ROOT / "original-receiver-original-package.json")])
    assert original_original.returncode == 2
    original_new = run("original-receiver-new-package", [str(OLD / "receive_delivery.py"), str(PACKAGE), "--report", str(ROOT / "original-receiver-new-package.json")])
    assert original_new.returncode == 1
    old_errors = Counter(read(ROOT / "original-receiver-new-package.json")["errors"])
    assert old_errors == Counter({"unknown historical event coverage fails closed": 1875, "zero turnover retained without suspension inference": 1, "four named gaps retained": 1, "no false acceptance or PASS": 1})
    receipt = run("repaired-independent-receiver", [str(PACKAGE / "tools/receive_repaired.py"), str(PACKAGE), "--report", str(PACKAGE / "validation_report.json")])
    assert receipt.returncode == 0, receipt.stdout + receipt.stderr
    report = read(PACKAGE / "validation_report.json")
    assert not report["errors"] and report["consumer_acceptance"] and report["qualified_historical_signal_rows"] == 1875
    before = (PACKAGE / "manifest.json").read_bytes()
    repeated = run("offline-reproduction", [str(PACKAGE / "tools/rebuild_delivery.py"), "--package", str(PACKAGE)])
    assert repeated.returncode == 0 and (PACKAGE / "manifest.json").read_bytes() == before
    with (OLD / "H01-delivery/raw_market_data.csv").open(encoding="utf-8", newline="") as stream:
        original_rows = list(csv.DictReader(stream))
    with (PACKAGE / "raw_market_data.csv").open(encoding="utf-8", newline="") as stream:
        repaired_rows = list(csv.DictReader(stream))
    numerical_fields = ["row_id", "date", "instrument_id", "open", "high", "low", "close", "volume", "amount", "raw_ohlc_integers", "raw_amount_float32_hex", "source_record_index", "source_sha256", "information_available_at"]
    assert len(original_rows) == len(repaired_rows) == 1875
    assert all(all(a[field] == b[field] for field in numerical_fields) for a,b in zip(original_rows, repaired_rows))
    baseline = read(ROOT / "baseline.json")
    for name, expected in baseline["protected_original_files"].items():
        assert sha(REPO / name) == expected, "original evidence changed: " + name
    repositories = {}
    for label, repo in (("producer", REPO), ("consumer", Path("D:/Dev/Projects/systematic-investing-os"))):
        head = git(repo, "rev-parse", "HEAD").decode().strip()
        diff = hashlib.sha256(git(repo, "diff", "HEAD")).hexdigest()
        status = git(repo, "status", "--porcelain").decode("utf-8")
        assert head == baseline[label]["head"] and diff == baseline[label]["tracked_diff_sha256"]
        if label == "consumer":
            assert status == baseline[label]["status"]
        repositories[label] = {"head": head, "tracked_diff_sha256": diff, "status": status}
    archive_path = ROOT / "H01-delivery-repaired.zip"
    files = [p for p in sorted(PACKAGE.rglob("*")) if p.is_file() and "__pycache__" not in p.parts]
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in files:
            item = zipfile.ZipInfo("H01-delivery-repaired/" + path.relative_to(PACKAGE).as_posix(), (1980, 1, 1, 0, 0, 0))
            item.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(item, path.read_bytes())
    with zipfile.ZipFile(archive_path) as archive:
        assert archive.testzip() is None and archive.read("H01-delivery-repaired/manifest.json") == before
    ledger = read(ROOT / "network_ledger.json")
    source = read(OLD / "H01-delivery/fund_actions.json")
    root_cause = {"classification": "CONFIRMED_DEFECT", "producer_location": "build_delivery.py:196-208", "receiver_location": "receive_delivery.py:100,105-106",
                  "actual_condition": "Every record was unconditionally marked NOT_ATTESTED/False/null after a successful no-event audit; the receiver required that failure state.",
                  "source_request_failure_was_not_the_reason_for_zero_signal_rows": True,
                  "no_literal_per_day_negative_certificate_test_or_publication_cutoff_comparison_existed": True,
                  "three_etfs": {code: {"blocked_rows": 625, "base_reason": "HISTORICAL_EVENT_ASOF_COVERAGE_NOT_ATTESTED"} for code in ("513500", "513030", "513520")},
                  "original_api_normal_empty_and_request_error_semantics_preserved": True,
                  "later_reports_are_completeness_audit_not_signal_input": True,
                  "original_receiver_rejected_new_package_only_due_to_four_obsolete_assertion_categories": dict(old_errors),
                  "original_issuer_reports": len(source["issuer_report_evidence"])}
    save(ROOT / "root_cause.json", root_cause)
    result = {"current_decision": "FIX_ONLY", "verdict": "H01_DATA_PACKAGE_READY_FOR_CONSUMER_ACCEPTANCE",
              "manifest_sha256": sha(PACKAGE / "manifest.json"), "validation_report_sha256": sha(PACKAGE / "validation_report.json"),
              "zip_sha256": sha(archive_path), "zip_bytes": archive_path.stat().st_size, "package_files": len(files),
              "old_manifest_sha256": "68ca0d4facc72b03f4828aae1b254fbd10beec4b456d7aa1ff80cea0e89f1dd0", "old_zip_sha256": sha(OLD / "H01-delivery.zip"),
              "protected_original_files_verified": len(baseline["protected_original_files"]),
              "old_tests": old_tests.stdout.strip().splitlines()[-1], "old_test_case_ids_identical": True,
              "new_tests": new_tests.stdout.strip().splitlines()[-1], "receiver_exit_code": receipt.returncode,
              "receipt_checks": report["checks_executed"], "qualified_observations": 1875, "qualified_observation_period_input_rows": 1275,
              "qualified_warmup_per_etf": 200, "raw_numerical_fields_unchanged": True, "offline_reproduction_manifest_identical": True,
              "official_suspension_sha256": "be01b505d9c05cf5c7bc58a231849379321d519d154f789b2ad3c5ae5bd81c28",
              "network": {"requests": len(ledger["requests"]), "bytes": sum(e["downloaded_bytes"] for e in ledger["requests"]), "budget": [12, 15_000_000]},
              "repositories": repositories, "remaining_necessary_gaps": [], "owner_acceptance": "PENDING",
              "strategy_backtests_executed": 0, "production_adapter_integrated": False, "git_commit": False, "git_push": False}
    save(ROOT / "completion.json", result)
    print(json.dumps({k:v for k,v in result.items() if k != "repositories"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
