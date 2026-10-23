"""Verify saved prerequisite evidence bytes; no network or product changes."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
root = HERE.parent.parent
records = json.loads((HERE / "live/requests.json").read_text(encoding="utf-8"))
errors = []
for record in records:
    raw = (HERE / "live" / record["raw_file"]).read_bytes()
    if hashlib.sha256(raw).hexdigest() != record["raw_sha256"]:
        errors.append(record["id"] + ": raw hash mismatch")
    if len(raw) != record["raw_bytes"]:
        errors.append(record["id"] + ": byte length mismatch")
    if "parsed_file" in record:
        raw_parsed = json.loads(raw.decode("utf-8"))
        saved_parsed = json.loads((HERE / "live" / record["parsed_file"]).read_text(encoding="utf-8"))
        if raw_parsed != saved_parsed:
            errors.append(record["id"] + ": parsed mismatch")
source = root / "chstockdata"
baseline = json.loads((root / "baseline.json").read_text(encoding="utf-8"))
source_differences = []
for name, expected in baseline["chstockdata_before"].items():
    path = source / name
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        source_differences.append(name)
report = {
    "raw_records_checked": len(records),
    "raw_and_parsed_errors": errors,
    "isolated_source_baseline_entries_checked": len(baseline["chstockdata_before"]),
    "isolated_source_differences": source_differences,
    "note": "byte equality only; does not certify source coverage or candidate Gate",
}
(HERE / "evidence-integrity.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(report, ensure_ascii=False))
raise SystemExit(1 if errors or source_differences else 0)
