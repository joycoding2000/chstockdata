"""Verify archived observations and file boundaries without further network access."""
from __future__ import annotations

import ast
import csv
import json
from collections import Counter
from decimal import Decimal
from pathlib import Path

from probe_history import BASE, CONTRACTS, ROOT, digest, dump, git, now

REPORT = ROOT / "docs/audits/2026-10-19-sios-p2-producer-response.md"


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def csv_rows(path):
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def main():
    summary = load(BASE / "analysis-r2/sample_summary.json")
    raw_files_checked = 0
    for label in ("sandbox", "live"):
        for record in load(BASE / label / "requests.json"):
            if "raw_file" in record:
                body = (BASE / label / record["raw_file"]).read_bytes()
                assert digest(body) == record["sha256"] and len(body) == record["bytes"]
                raw_files_checked += 1
    assert raw_files_checked == 20
    assert summary["request_count_live"] == 22 and summary["http_success"] == 19
    assert len(summary["dce_official_outcomes"]) == 3
    assert all(r["outcome"] == "REQUEST_FAILURE" for r in summary["dce_official_outcomes"])
    assert [r["counts"] for r in summary["shfe"]] == [
        {"RB": 12, "BU": 12}, {"RB": 12, "BU": 12},
        {"RB": 12, "BU": 16}, {"RB": 12, "BU": 16},
    ]
    assert sum(r["raw_rows"] for r in summary["sina"]) == 4090
    assert sum(r["in_scope_rows"] for r in summary["sina"]) == 3684
    rows = csv_rows(BASE / "analysis-r2/daily_sample.csv")
    assert len(rows) == 119
    assert len({(r["source"], r["exchange"], r["contract_id"], r["trade_date"]) for r in rows}) == 119
    original_fields_checked = 0
    mapping = {"open": ("OPENPRICE", "o"), "high": ("HIGHESTPRICE", "h"), "low": ("LOWESTPRICE", "l"), "close": ("CLOSEPRICE", "c"), "settlement": ("SETTLEMENTPRICE", "s"), "volume": ("VOLUME", "v"), "open_interest": ("OPENINTEREST", "p")}
    for row in rows:
        if row["source"] == "shfe":
            raw = load(BASE / "live" / ("shfe_" + row["trade_date"].replace("-", "") + ".raw"))
            candidates = [r for r in raw["o_curinstrument"] if str(r.get("PRODUCTID", "")).strip().split("_", 1)[0].upper() + str(r["DELIVERYMONTH"]).strip() == row["contract_id"]]
            assert len(candidates) == 1
            original = candidates[0]
            field_index = 0
        else:
            text = (BASE / "live" / ("sina_" + row["contract_id"] + ".raw")).read_text(encoding="utf-8")
            decoder = json.JSONDecoder()
            data, _ = decoder.raw_decode(text[text.index("=(") + 2:])
            candidates = [r for r in data if r["d"] == row["trade_date"]]
            assert len(candidates) == 1
            original = candidates[0]
            field_index = 1
        for field, keys in mapping.items():
            assert str(original[keys[field_index]]) == row[field]
            original_fields_checked += 1
        assert row["first_available_at"] == "UNKNOWN" and row["revision_status"] == "UNKNOWN"
        assert row["contract_multiplier"] == "UNKNOWN" and row["tick_size"] == "UNKNOWN"
    assert original_fields_checked == 833
    anchors = csv_rows(BASE / "analysis-r2/anchor_rows.csv")
    assert {(r["trade_date"].replace("-", ""), r["contract_id"]) for r in anchors} == {(d, c) for d, cs in CONTRACTS.items() for c in cs}
    comparisons = csv_rows(BASE / "analysis-r2/shfe_sina_crosscheck.csv")
    assert len(comparisons) == 42 and all(Decimal(r["shfe_raw"]) == Decimal(r["sina_raw"]) for r in comparisons)
    anomalies = csv_rows(BASE / "analysis-r2/sina_settlement_anomalies.csv")
    assert len(anomalies) == 125 and all(Decimal(r["settlement_raw"]) <= 0 for r in anomalies)
    assert Counter(r["contract_id"] for r in anomalies) == {"C2105": 41, "CS2105": 41, "PP2105": 41, "RB2310": 1, "BU2309": 1}
    assert sum(r["quality_flags"].startswith("MISSING_OR_INVALID_OPEN") for r in rows) == 3
    for path in BASE.glob("*.py"):
        ast.parse(path.read_text(encoding="utf-8"))
    assert not git("diff", "HEAD", "--name-only"), "Pre-existing tracked files changed"
    before = set(load(BASE / "sandbox/baseline.json")["status"])
    after = set(git("status", "--porcelain=v1", "--untracked-files=all").splitlines())
    assert not (before - after), "Pre-existing working-tree entry disappeared or changed status"
    new = sorted(after - before)
    in_scope = [line for line in new if line[3:] == "docs/audits/2026-10-19-sios-p2-producer-response.md" or line[3:].startswith("docs/audits/evidence/2026-10-19-sios-p2-producer-response/")]
    outside_scope = [line for line in new if line not in in_scope]
    source_paths = [ROOT / p for p in ("AGENTS.md", "pyproject.toml", "src/chstockdata/__init__.py", "src/chstockdata/daily_bars.py", "src/chstockdata/vipdoc_history.py", "docs/provider-capability-matrix.md", "docs/SIOS-P2-chstockdata-consumer-data-request.md")]
    source_paths.extend(Path("D:/Dev/Projects/systematic-investing-os/docs/m1-r2") / name for name in ("R2-p2-final-exploratory-feasibility-verdict-2026-10-18.md", "R2-p2-first-exploratory-economic-falsification-2026-10-19.md"))
    dump(BASE / "source_inventory.json", [{"path": str(p), "sha256": digest(p.read_bytes())} for p in source_paths])
    dump(BASE / "verification.json", {
        "verified_at": now(), "status": "PASS_LIMITED_EVIDENCE_CHECKS_ONLY",
        "head": git("rev-parse", "HEAD"), "branch": git("branch", "--show-current"),
        "raw_responses_verified": raw_files_checked, "original_field_values_verified": original_fields_checked,
        "csv_rows": len(rows), "cross_source_numeric_comparisons": len(comparisons), "anomalies_preserved": len(anomalies),
        "tracked_diff": git("diff", "HEAD", "--stat"), "new_status_entries_in_scope": in_scope,
        "other_new_untracked_entries_observed_not_written_by_this_probe": outside_scope,
        "full_consumer_data_gate": "INSUFFICIENT_EVIDENCE", "network_repeated_during_verification": False,
    })
    files = [REPORT, *sorted(p for p in BASE.rglob("*") if p.is_file() and "__pycache__" not in p.parts and p.name != "artifact_manifest.json")]
    dump(BASE / "artifact_manifest.json", {"generated_at": now(), "files": [{"path": p.relative_to(ROOT).as_posix(), "bytes": p.stat().st_size, "sha256": digest(p.read_bytes())} for p in files], "excluded": ["artifact_manifest.json (self)", "__pycache__"]})
    print(json.dumps({"status": "PASS_LIMITED_EVIDENCE_CHECKS_ONLY", "raw_responses": raw_files_checked, "original_fields": original_fields_checked, "sample_rows": len(rows), "numeric_comparisons": len(comparisons), "anomalies": len(anomalies), "manifest_files": len(files), "tracked_diff_empty": True}))


if __name__ == "__main__":
    main()
