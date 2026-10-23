"""Assemble Step3 evidence already executed; no tests, network, or build."""
import collections
import difflib
import hashlib
import json
import subprocess
from pathlib import Path
import xml.etree.ElementTree as ET

OUT = Path(__file__).resolve().parent
W = OUT.parents[1]
SIOS = W / "systematic-investing-os"


def read(name):
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def save(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def junit(name):
    root = ET.parse(OUT / name).getroot()
    cases = list(root.iter("testcase"))
    return {"tests": len(cases), "passed": sum(not any(case.find(key) is not None for key in
        ("failure", "error", "skipped")) for case in cases),
        "failures": len(list(root.iter("failure"))), "errors": len(list(root.iter("error"))),
        "skipped": len(list(root.iter("skipped"))), "names": [case.attrib["name"] for case in cases]}


reports = [json.loads(path.read_text(encoding="utf-8")) for path in sorted((OUT / "capabilities").glob("*.json"))]
outcomes = [{"test": report["test"], **item} for report in reports for item in report["outcomes"]]
by_instrument = {}
for item in outcomes:
    by_instrument.setdefault(item["instrument_id"], []).append(item)
save("all-capabilities.json", {"outcomes_count": len(outcomes), "by_instrument": by_instrument,
    "passed": sum(item["status"] == "PASS" for item in outcomes),
    "failed": sum(item["status"] != "PASS" for item in outcomes),
    "version_and_default_pin_checks": {"evidence": "live.xml + actual-imports.json",
        "actual_version": "0.4.2", "default_pin": "0.3.0", "default_rejects_candidate": True,
        "explicit_candidate_admission": True}})

calls = read("calls.json")
bad_sha = []
for call in calls:
    if "raw_path" in call:
        actual = hashlib.sha256((OUT / call["raw_path"]).read_bytes()).hexdigest()
        if actual != call["raw_sha256"]:
            bad_sha.append(call["index"])
opening = []
calendars = []
for call in calls:
    if call["kind"] == "fetch_historical_opening_evidence":
        payload = json.loads((OUT / call["raw_path"]).read_text(encoding="utf-8"))["data"]
        opening.append({"instrument": payload["instrument"], "session_date": payload["session_date"],
            "status": payload["opening_status"], "current_official_query_status": payload["official_query"]["status"],
            "pagination_complete": payload["official_query"]["pagination_complete"],
            "official_observations": payload["official_query"]["observations"],
            "known_events": [{"raw_sha256": event["raw_sha256"], "offline_cache": event["offline_cache"]}
                             for event in payload["official_events"]],
            "tdx_observations": payload["tdx_activity"]["observations"],
            "tdx_server": payload["tdx_activity"]["server"],
            "evidence_hash": payload["evidence_hash"], "call_index": call["index"]})
    if call["kind"] == "load_trading_calendar":
        data = json.loads((OUT / call["raw_path"]).read_text(encoding="utf-8"))
        calendars.append({"call_index": call["index"], "source": data["source"],
            "stale": data["stale"], "covered_range": data["covered_range"], "as_of": data["as_of"]})
save("all-calls-coverage.json", {"calls_count": len(calls),
    "kinds": dict(collections.Counter(call["kind"] for call in calls)),
    "raw_sha_mismatch": bad_sha, "opening_requests": opening,
    "calendar_requests": calendars,
    "scope": {"approved_targets": ["510300", "159915", "518880", "511010"],
              "source_controls_only": ["513100", "159509"],
              "controls_actions_qualification": "NOT_IN_SCOPE"},
    "policy_boundary": "single fixed host/no discovery applies to new opening reader; original public calendar staleness and fallback retained"})

changes = ["tests/qualification/live_qualification.py", "tests/qualification/test_chstockdata_etf_gate.py",
           "tests/qualification/test_live_r21_contract.py", "docs/contracts/historical-opening-execution-r21.md"]
diffs = []
for name in changes:
    current = (SIOS / name).read_text(encoding="utf-8")
    if name.startswith("docs/"):
        old = current.split("## Owner-approved R5 mandatory live contract", 1)[0]
        base_label = "step2/" + name
    else:
        result = subprocess.run(["git", "-c", "safe.directory=D:/Dev/Projects/systematic-investing-os",
            "-C", "D:/Dev/Projects/systematic-investing-os", "show",
            "84fd54fae0740bc06b1d250afa4578be29556956:" + name], capture_output=True)
        old = result.stdout.decode("utf-8") if result.returncode == 0 else ""
        base_label = "frozen/" + name
    diffs.extend(difflib.unified_diff(old.splitlines(True), current.splitlines(True),
        fromfile=base_label, tofile="step3/" + name))
(OUT / "step3-changes.diff").write_text("".join(diffs), encoding="utf-8")

before, after = read("source-before.json"), read("source-after.json")
test_before, test_after = read("qualification-source-before.json"), read("qualification-source-after.json")
step2 = json.loads((OUT.parent / "r21-step2/final.json").read_text(encoding="utf-8"))
step2_runtime_matches = all(before["files"].get("sios/" + name.removeprefix("src/systematic_investing/")) == digest
                            for name, digest in step2["source_files_sha256"].items())
summary = {"status": "DONE", "current_phase": "v0.4.2 FIX_ONLY", "step": 3,
    "gate": "PASS_STEP3_LOCAL_PENDING_FRESH_REVIEWS", "runtime_modified_in_step3": False,
    "frozen_sios_commit": "84fd54fae0740bc06b1d250afa4578be29556956", "working_tree": "isolated no-.git source export; no commit/push/merge/tag",
    "changed_files": changes, "runtime_source_unchanged": before == after,
    "qualification_source_unchanged_during_final_run": test_before == test_after,
    "source_tree_sha256": before["tree_sha256"], "source_files": len(before["files"]),
    "sios_step2_runtime_identity": {"source_tree_sha256": step2["source_tree_sha256"],
        "files": len(step2["source_files_sha256"]), "all_file_hashes_match": step2_runtime_matches},
    "qualification_run_manifest_code_identity_basis": "source tree SHA256 test identity in code_commit field; NOT a Git commit; frozen baseline commit recorded separately",
    "opening_reader_sha256": before["files"]["chstockdata/opening_evidence.py"],
    "red": junit("red.xml"), "helper_bond_red": junit("engine-red.xml"),
    "offline_final": junit("final-green.xml"), "mandatory_live_final": junit("live.xml"),
    "mandatory_live_final_exit": int((OUT / "live.exit").read_text(encoding="utf-8")),
    "capabilities_outcomes": len(outcomes), "all_capabilities_pass": all(item["status"] == "PASS" for item in outcomes),
    "opening_sources": {row["instrument"]: row["status"] for row in opening},
    "all_retained_raw_sha_verified": not bad_sha,
    "actual_imports": read("actual-imports.json"),
    "prior_runs": {"invalid-observation-run": "tool serialization TypeError, interrupted, NOT_QUALIFICATION_EVIDENCE",
        "failed-live-run-1": "real 4 passed/1 failed; helper tuple-equality assertion; retained unchanged",
        "local-repro-red": "six actual failed-run snapshots reproduce helper assertion; all canonical digests equal",
        "local-repro-green": "six actual failed-run snapshots pass corrected helper; OFFLINE_DIAGNOSTIC_ONLY",
        "root_independent_16": "SUPERSEDED by final helper source; root must independently verify 17-case version"},
    "limitations": ["prebuild source run, NOT a new wheel qualification", "legacy complete historical PIT/full-day suspension remains UNKNOWN/fail-closed",
        "activity proxy is [09:30,09:31), not preopen knowledge or guaranteed arbitrary-order fill", "no QDII product qualification"],
    "unresolved_blockers": [], "scope_expansion": False, "step4": "NOT_EXECUTED",
    "recommended_next_action": "fresh Step3 spec then quality review; no Step4 work performed here",
    "release_authorized": False, "publish_authorized": False, "next_phase_authorized": False}
assert summary["mandatory_live_final"]["tests"] == 5
assert summary["mandatory_live_final"]["passed"] == 5
assert summary["all_capabilities_pass"] and before == after and test_before == test_after
assert step2_runtime_matches
save("summary.json", summary)

python = summary["actual_imports"]["python"]
base_env = {"PYTHONPATH": (SIOS / "src").as_posix() + ";" + (W / "chstockdata/src").as_posix(),
            "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1", "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"}
journal = []
for name, tests in (("red", ["tests/qualification/test_live_r21_contract.py"]),
                    ("green", ["tests/qualification/test_live_r21_contract.py", "tests/qualification/test_chstockdata_etf_gate.py"]),
                    ("green-controls", ["tests/qualification/test_live_r21_contract.py", "tests/qualification/test_chstockdata_etf_gate.py"]),
                    ("engine-red", ["tests/qualification/test_live_r21_contract.py"]),
                    ("final-green", ["tests/qualification/test_live_r21_contract.py", "tests/qualification/test_chstockdata_etf_gate.py"])):
    journal.append({"name": name, "argv": [python, "-m", "pytest", *tests, "-q", "-p", "no:cacheprovider",
        "--basetemp", (OUT / (name + "-temp")).as_posix(), "--junitxml", (OUT / (name + ".xml")).as_posix()],
        "cwd": str(SIOS), "environment_overrides": base_env,
        "exit_code": int((OUT / (name + ".exit")).read_text(encoding="utf-8")),
        "log": name + ".log", "journal_basis": "exact executed argv recovered from tool calls; not a new execution"})
journal.append({"name": "mandatory-live-final", **read("live-command.json"), "exit_code": summary["mandatory_live_final_exit"], "log": "live.log"})
save("execution-journal.json", journal)
rework = OUT / "optional-vendor-rework"
if (rework / "green-candidate.xml").exists():
    current = {name: hashlib.sha256((SIOS / name).read_bytes()).hexdigest() for name in test_before}
    changed_since_live = [name for name in test_before if current[name] != test_before[name]]
    assert changed_since_live == ["tests/qualification/test_live_r21_contract.py"]
    assert current["tests/qualification/live_qualification.py"] == test_before["tests/qualification/live_qualification.py"]
    assert current["tests/qualification/test_chstockdata_etf_gate.py"] == test_before["tests/qualification/test_chstockdata_etf_gate.py"]
    save("qualification-current.json", current)
    summary["review_history"] = [{"verdict": "REWORK", "priority": "P1",
        "issue": "offline regression imported optional real vendor and required actual 0.4.2; missing vendor or valid old 0.3.0 failed",
        "fix_scope": "one offline regression only; injected vendor objects using existing library parameter"}]
    summary["optional_vendor_rework"] = {
        "status": "FIXED_PENDING_FRESH_SPEC_QUALITY_REVIEW", "network_rerun": False,
        "red_missing": junit("optional-vendor-rework/red-missing.xml"),
        "red_legacy": junit("optional-vendor-rework/red-legacy.xml"),
        "green_missing": junit("optional-vendor-rework/green-missing.xml"),
        "green_legacy": junit("optional-vendor-rework/green-legacy.xml"),
        "offline_final": junit("optional-vendor-rework/green-candidate.xml"),
        "only_file_changed_since_actual_live": changed_since_live,
        "live_helper_and_five_test_module_hashes_match_actual_5_pass_run": True,
        "current_source_hashes": current, "prior_summary_preserved": "optional-vendor-rework/before-summary.json"}
    summary["offline_final"] = summary["optional_vendor_rework"]["offline_final"]
    for name in ("red-missing", "red-legacy", "green-missing", "green-legacy", "green-candidate"):
        journal.append({"name": "optional-vendor-" + name,
            **json.loads((rework / (name + ".json")).read_text(encoding="utf-8")),
            "log": "optional-vendor-rework/" + name + ".log"})
    save("execution-journal.json", journal)
    save("summary.json", summary)
print(json.dumps({key: summary[key] for key in ("gate", "capabilities_outcomes", "opening_sources", "runtime_source_unchanged")}, ensure_ascii=False))
