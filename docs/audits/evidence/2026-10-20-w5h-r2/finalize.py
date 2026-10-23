"""Verify bounded R2 artifacts and protect all pre-existing Git-visible files."""
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re

from audit_tools import BASE, ROOT, REPORT, save, snapshot


def main():
    before = json.loads((BASE / "before.json").read_text(encoding="utf-8"))
    after = snapshot()
    checks = {}
    for name, old in before["repositories"].items():
        new = after["repositories"][name]
        checks[name] = {
            "head_before": old["head"], "head_after": new["head"],
            "head_unchanged": old["head"] == new["head"],
            "tracked_diff_unchanged": old["diff_sha256"] == new["diff_sha256"],
            "index_unchanged": old["index_sha256"] == new["index_sha256"],
            "original_files": len(old["files"]),
            "changed_or_removed": [p for p, h in old["files"].items() if new["files"].get(p) != h],
            "new_files_outside_evidence": sorted(set(new["files"]) - set(old["files"])),
            "status_before": old["status"], "status_after": new["status"],
        }
    save("verification.json", checks)
    for name, row in checks.items():
        assert row["head_unchanged"] and row["tracked_diff_unchanged"] and row["index_unchanged"], name
        assert not row["changed_or_removed"], (name, row["changed_or_removed"])
        expected = [REPORT] if name == "chstockdata" else []
        assert row["new_files_outside_evidence"] == expected, (name, row["new_files_outside_evidence"])

    report = ROOT / REPORT
    text = report.read_text(encoding="utf-8")
    assert not report.read_bytes().startswith(b"\xef\xbb\xbf")
    assert text.count("```") % 2 == 0
    links = []
    for target in re.findall(r"\]\(([^)]+)\)", text):
        if target.startswith(("https://", "http://")):
            continue
        path = (report.parent / target.split("#")[0]).resolve()
        assert path.exists() or path.name == "manifest.json", path
        links.append(target)
    expected_columns = None
    for line in text.splitlines():
        if not line.startswith("|"):
            expected_columns = None
            continue
        columns = len(line.split("|"))
        if expected_columns is None:
            expected_columns = columns
        assert columns == expected_columns, line

    analysis = json.loads((BASE / "analysis.json").read_text(encoding="utf-8"))
    assert analysis["requests_recorded"] == 22
    assert analysis["minimum_same_source_after_finish_seconds"] >= 3
    assert analysis["baostock_new_logins"] == 0
    assert analysis["prior_artifacts_reverified"] == 30
    assert all(analysis["authority_current_consumer_copy_equal"].values())

    artifacts = []
    excluded = {"manifest.json", "final_validation.json", "finalize.stdout.txt", "finalize.stderr.txt"}
    for path in sorted([report] + [p for p in BASE.iterdir() if p.is_file() and p.name not in excluded]):
        raw = path.read_bytes()
        artifacts.append({"path": path.relative_to(ROOT).as_posix(), "bytes": len(raw),
                          "sha256": hashlib.sha256(raw).hexdigest()})
    save("manifest.json", {"generated_at": after["captured_at"],
        "exclusions": ["manifest.json self", "final_validation.json validates this manifest",
                       "finalize stdout/stderr are written after hashing", "__pycache__"],
        "artifacts": artifacts})
    for row in artifacts:
        assert hashlib.sha256((ROOT / row["path"]).read_bytes()).hexdigest() == row["sha256"]

    result = {
        "document_and_evidence_verdict": "PASS",
        "source_qualification_verdict": "ACCESS_OR_EVIDENCE_INSUFFICIENT",
        "mishi_s07_historical_gate": "NOT_PASSED",
        "protected_original_files": {k: v["original_files"] for k, v in checks.items()},
        "changed_or_removed_existing_files": 0,
        "all_repository_heads_diffs_and_indexes_unchanged": True,
        "direct_http_requests": 22, "minimum_after_finish_interval_seconds":
            analysis["minimum_same_source_after_finish_seconds"],
        "old_artifacts_reverified": 30, "old_daily_valuation_rows_reused": 729,
        "local_markdown_links_checked": len(links), "manifest_artifacts_verified": len(artifacts),
        "runtime_or_consumer_changes": 0, "commit_push_release": "NOT_PERFORMED",
        "next_phase_authorized": False,
    }
    save("final_validation.json", result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
