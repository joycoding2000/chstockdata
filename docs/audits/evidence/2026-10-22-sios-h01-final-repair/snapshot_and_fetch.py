"""Read-only baseline capture and one named, budgeted official H01 request."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import runpy
import subprocess

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[3]
OLD = ROOT.parent / "2026-10-22-sios-h01-priority-delivery"
SIOS = Path("D:/Dev/Projects/systematic-investing-os")
URL = "https://www.sse.com.cn/disclosure/fund/announcement/c/new/2025-01-23/513030_20250123_HU9P.pdf"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(root, *args):
    return subprocess.check_output(["git", "-c", f"safe.directory={root.as_posix()}", "-C", str(root), *args])


def main():
    baseline_path = ROOT / "baseline.json"
    if not baseline_path.exists():
        protected = {str(p.relative_to(REPO)).replace("\\", "/"): digest(p) for p in OLD.rglob("*")
                     if p.is_file() and "__pycache__" not in p.parts}
        for path in (REPO / "tests/test_sios_h01_delivery.py", REPO / "docs/audits/2026-10-22-sios-h01-priority-delivery.md"):
            protected[path.relative_to(REPO).as_posix()] = digest(path)
        context = {"protected_original_files": protected, "network_authorization": "Owner explicitly accepted 12 requests / 15000000 bytes / max one retry in this chat"}
        for label, repo in (("producer", REPO), ("consumer", SIOS)):
            context[label] = {"head": git(repo, "rev-parse", "HEAD").decode().strip(),
                              "status": git(repo, "status", "--porcelain").decode("utf-8"),
                              "tracked_diff_sha256": hashlib.sha256(git(repo, "diff", "HEAD")).hexdigest()}
        contracts = ROOT / "contracts"
        contracts.mkdir(exist_ok=True)
        for name in ("AGENTS.md", "src/systematic_investing/backtest/engine.py", "src/systematic_investing/domain/market.py",
                     "src/systematic_investing/adapters/chstockdata/provider.py", "src/systematic_investing/research/strategies/etf_relative_momentum.py",
                     "docs/architecture/data-contracts.md"):
            body = (SIOS / name).read_bytes()
            target = contracts / ("consumer-" + Path(name).name)
            target.write_bytes(body)
        baseline_path.write_text(json.dumps(context, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # Original manifest/ledger contain no named SSE PDF. Existing body caches are
    # retained; capture uses a separate ROOT and independent Owner budget.
    namespace = runpy.run_path(str(OLD / "acquire.py"))
    capture = namespace["capture"]
    capture.__globals__.update({"ROOT": ROOT, "MAX_REQUESTS": 12, "MAX_BYTES": 15_000_000})
    ledger_path = ROOT / "network_ledger.json"
    entries = json.loads(ledger_path.read_text(encoding="utf-8"))["requests"] if ledger_path.exists() else []
    cached = next((e for e in entries if e["url"] == URL and e["status"] == "success" and (ROOT / e["file"]).read_bytes().startswith(b"%PDF-")), None)
    if cached:
        print("CACHE_REUSED", cached["sha256"])
    else:
        capture("513030-20250123-sse-official-halt", URL)
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    ledger["task"] = "SIOS_H01_DATA_DELIVERY_FINAL_REPAIR"
    ledger["prior_budget_inherited"] = False
    ledger_path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
