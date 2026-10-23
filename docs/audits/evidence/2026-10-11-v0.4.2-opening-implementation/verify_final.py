"""Verify the protected baselines and bounded evidence, without running new requests."""

from pathlib import Path
import hashlib
import json
import subprocess
import xml.etree.ElementTree as ET
import zipfile

WORK = Path(__file__).resolve().parent
ROOT = Path("D:/Dev/Projects/chstockdata")
SIOS = Path("D:/Dev/Projects/systematic-investing-os")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(repo, *args):
    return subprocess.check_output(
        ["git", "-c", f"safe.directory={repo.as_posix()}", "-C", str(repo), *args],
        stderr=subprocess.PIPE,
    ).decode().strip()


baseline = json.loads((WORK / "baseline.json").read_text(encoding="utf-8"))
cr = "docs/releases/v0.4.2/change-requests/CR-historical-opening-execution.md"
original_differences = [p for p, h in baseline["chstockdata_before"].items() if sha(ROOT / p) != h]
isolated_differences = [p for p, h in baseline["chstockdata_before"].items() if sha(WORK / "chstockdata" / p) != h]
sios_original_differences = [p for p, h in baseline["sios_before"].items() if sha(SIOS / p) != h]
sios_isolated_differences = [
    p for p, h in baseline["sios_frozen_files"].items()
    if sha(WORK / "systematic-investing-os" / p) != h
]
assert original_differences == isolated_differences == [cr]
assert not sios_original_differences and not sios_isolated_differences
with zipfile.ZipFile(WORK / "chstockdata-before.zip") as archive:
    assert (ROOT / cr).read_bytes().startswith(archive.read(cr))
assert git(ROOT, "rev-parse", "HEAD") == baseline["chstockdata_head"]
assert git(SIOS, "rev-parse", "HEAD") == baseline["sios_current_head"]
assert git(SIOS, "status", "--porcelain") == baseline["sios_status_before"] == ""
wheel_sha = sha(ROOT / "dist/v042-unified/chstockdata-0.4.2-py3-none-any.whl")
assert wheel_sha == baseline["old_wheel_sha256"]

live = WORK / "evidence/step1/live"
manifest = json.loads((live / "manifest.json").read_text(encoding="utf-8"))
for item in manifest["files"]:
    assert sha(live / item["file"]) == item["sha256"]
    assert (live / item["file"]).stat().st_size == item["bytes"]
requests = json.loads((live / "requests.json").read_text(encoding="utf-8"))
assert len(requests) == 5 and all(r["http_status"] == 200 for r in requests)
body = (live / "sse_688432_interval.parsed.json")
interval = json.loads(body.read_text(encoding="utf-8"))["result"][0]
assert (interval["productCode"], interval["startStopDate"], interval["endStopDate"]) == (
    "688432", "20260831", "20260911"
)
assert not (live / "sse_688432_resume_pdf.bin").read_bytes().startswith(b"%PDF-")
for name, count in (("szse_159915_announcements", 4), ("szse_159509_announcements_control", 2)):
    data = json.loads((live / (name + ".parsed.json")).read_text(encoding="utf-8"))
    assert data["announceCount"] == len(data["data"]) == count

# Preserve the known issuer resume fact; the new constructed URL cannot negate it.
mirror = ROOT / "docs/audits/evidence/2026-10-09-v0.4.2-history-recovery/issuer-resume-mirror.pdf"
disclosures = json.loads((mirror.parent / "disclosure-pages.json").read_text(encoding="utf-8"))
assert mirror.read_bytes().startswith(b"%PDF-")

junit = ET.parse(WORK / "evidence/step1/legacy-safety.xml").getroot()
suites = list(junit.iter("testsuite"))
test_counts = {
    key: sum(int(s.attrib.get(key, 0)) for s in suites)
    for key in ("tests", "failures", "errors", "skipped")
}
assert test_counts == {"tests": 19, "failures": 0, "errors": 0, "skipped": 0}
assert (WORK / "evidence/step1/legacy-safety.exit").read_text(encoding="utf-8").strip() == "0"
result = {
    "original_chstockdata_files_checked": len(baseline["chstockdata_before"]),
    "original_chstockdata_differences": original_differences,
    "isolated_chstockdata_differences": isolated_differences,
    "original_sios_files_checked": len(baseline["sios_before"]),
    "frozen_sios_files_checked": len(baseline["sios_frozen_files"]),
    "original_sios_differences": sios_original_differences,
    "isolated_sios_differences": sios_isolated_differences,
    "old_wheel_sha256": wheel_sha,
    "cr_original_body_preserved": True,
    "source_response_hashes_verified": len(manifest["files"]),
    "source_probe_responses": 5,
    "known_issuer_resume_pdf_sha256": sha(mirror),
    "legacy_safety": test_counts,
    "product_implementation": "NOT_EXECUTED",
    "new_candidate": "NOT_BUILT",
}
(WORK / "final-verification.json").write_text(
    json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
)
print(json.dumps(result, ensure_ascii=False))
