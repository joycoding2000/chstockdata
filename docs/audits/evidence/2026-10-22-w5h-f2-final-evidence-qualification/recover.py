"""Preserve pre-existing files and bind the authoritative offline inputs."""
import subprocess
from datetime import datetime, timezone
from common import ROOT, HERE, OLD, SCANS, REPLIES, read, save, sha


def main():
    assert not (HERE / "before.json").exists(), "Never replace the initial snapshot"
    paths = set()
    for folder in ("docs", "src", "tests", "scripts", "examples"):
        paths.update(p for p in (ROOT / folder).rglob("*") if p.is_file() and
                     not p.is_relative_to(HERE) and "__pycache__" not in p.parts)
    paths.update(p for p in ROOT.iterdir() if p.is_file())
    files = {p.relative_to(ROOT).as_posix(): sha(p) for p in sorted(paths)}
    git = lambda *args: subprocess.check_output(["git", *args], cwd=ROOT).decode("utf-8")
    save("before.json", {"utc": datetime.now(timezone.utc).isoformat(),
         "head": git("rev-parse", "HEAD").strip(), "status": git("status", "--porcelain=v1", "-uall"),
         "files": files})
    docs = read(OLD / "documents.json")
    save("input_documents.json", [d for d in docs if d["id"] in SCANS + REPLIES])
    save("bounded_contract.json", {
        "current_decision": "FIX_ONLY", "network_requests_allowed": 0,
        "scans": SCANS, "replies": REPLIES, "only_new_outputs": HERE.relative_to(ROOT).as_posix(),
        "report": "docs/audits/2026-10-22-w5h-f2-final-evidence-qualification.md",
        "ordered_work": ["embedded image identity and table structure", "constrained field recovery",
                         "reply scope and six FY2021 conflicts", "field/period qualification and PIT replay",
                         "all frozen regression denominators", "integrity and Owner Review"],
        "stop_rule": "Stop on demonstrated material evidence gaps after bounded structural/targeted recovery; no new production architecture",
        "product_gate": "MISHI_S07_HISTORICAL_GATE=NOT_PASSED",
        "commit": False, "push": False, "production": False})
    print({"preserved_files": len(files), "head": git("rev-parse", "HEAD").strip(), "documents": 11})


if __name__ == "__main__":
    main()
