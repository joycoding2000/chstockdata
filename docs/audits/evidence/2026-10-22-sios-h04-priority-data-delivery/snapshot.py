"""Read-only contract recovery and preservation; only writes H04 evidence."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[3]
SIOS = Path("D:/Dev/Projects/systematic-investing-os")


def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args])


def main():
    out = ROOT / "contracts"
    out.mkdir(exist_ok=True)
    context = {"repositories": {}, "contracts": {}, "source_boundary": ["2024-01-01", "2025-12-31"],
               "h04_research_window": "NOT_NEWLY_FROZEN; original H04 exposed common 2024-2025; H01 2025-09-30 cutoff does not apply",
               "historical_failure": {"date": "2026-10-19T16:35:00+08:00", "funds": ["513530", "513990"], "status": "failed", "failure_kind": "request_error", "vendor_raw_response_preserved_by_original_task": False, "not_evidence_of_no_distributions": True}}
    for label, repo in (("producer", REPO), ("consumer", SIOS)):
        context["repositories"][label] = {"head": git(repo, "rev-parse", "HEAD").decode().strip(), "status": git(repo, "status", "--porcelain").decode("utf-8"), "diff_sha256": hashlib.sha256(git(repo, "diff", "HEAD")).hexdigest()}
    for commit, name in (("d75867d3f4c297452d6ff4777aac631bb66edc8c", "R2-H01-H04-parallel-exploratory-admission-2026-10-19.md"), ("6d47fd2e98c5ba3efcdd7ff0a6e9add8eabff9b9", "R2-parallel-economic-falsification-handoff-2026-10-20.md")):
        body = git(SIOS, "show", f"{commit}:docs/m1-r2/{name}")
        (out / name).write_bytes(body)
        context["contracts"][name] = {"git_commit": commit, "sha256": hashlib.sha256(body).hexdigest()}
    for name, source in (("producer-AGENTS.md", REPO / "AGENTS.md"), ("consumer-AGENTS.md", SIOS / "AGENTS.md"), ("owner-request.txt", Path("C:/Users/Administrator/.codex/attachments/2c4d2a72-c710-4367-9e24-3b03203bde74/Pasted text.txt"))):
        shutil.copyfile(source, out / name)
    raw = ROOT / "raw_sources"
    raw.mkdir(exist_ok=True)
    context["local_sources"] = {}
    for code in ("513530", "513990", "000001"):
        path = REPO / ".rh3a2-vipdoc/sh/lday" / f"sh{code}.day"
        shutil.copyfile(path, raw / path.name)
        context["local_sources"][path.name] = {"source": path.relative_to(REPO).as_posix(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "bytes": path.stat().st_size}
    (ROOT / "context.json").write_text(json.dumps(context, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    old = REPO / "docs/audits/evidence/2026-10-22-sios-h01-priority-delivery/extract_reports.py"
    shutil.copyfile(old, ROOT / "extract_reports.py")
    print(json.dumps({"heads": {k:v["head"] for k,v in context["repositories"].items()}, "local_sources": context["local_sources"]}, indent=2))


if __name__ == "__main__":
    main()
