"""Read-only repository identity capture. Writes only this task's evidence."""
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent
PRODUCER = Path("D:/Dev/Projects/chstockdata")
CONSUMER = Path("D:/Dev/Projects/systematic-investing-os")


def git(root, *args):
    return subprocess.check_output(["git", "-c", f"safe.directory={root.as_posix()}", "-C", str(root), *args])


def snapshot():
    contracts = ROOT / "contracts"
    contracts.mkdir(exist_ok=True)
    objects = {}
    for label, root in (("producer", PRODUCER), ("consumer", CONSUMER)):
        objects[label] = {"head": git(root, "rev-parse", "HEAD").decode().strip(),
                          "status": git(root, "status", "--porcelain").decode("utf-8"),
                          "tracked_diff_sha256": hashlib.sha256(git(root, "diff", "HEAD")).hexdigest()}
    archive = "d75867d3f4c297452d6ff4777aac631bb66edc8c"
    paths = {
        "h01-consumer-contract.md": git(CONSUMER, "show", archive + ":docs/m1-r2/R2-H01-H04-parallel-exploratory-admission-2026-10-19.md"),
        "consumer-provider.py": (CONSUMER / "src/systematic_investing/adapters/chstockdata/provider.py").read_bytes(),
        "consumer-relative-momentum.py": (CONSUMER / "src/systematic_investing/research/strategies/etf_relative_momentum.py").read_bytes(),
        "consumer-SOURCES.yaml": (CONSUMER / "third_party/SOURCES.yaml").read_bytes(),
    }
    for name, body in paths.items():
        (contracts / name).write_bytes(body)
    objects["contract_archive_commit"] = archive
    objects["consumer_contract_missing_in_current_worktree"] = True
    objects["contract_hashes"] = {name: hashlib.sha256(body).hexdigest() for name,body in paths.items()}
    objects["boundaries"] = {"consumer_read_only": True, "strategy_backtest": False, "commit": False,
                              "push": False, "production_change": False, "public_api_change": False}
    (ROOT / "context.json").write_text(json.dumps(objects, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({name: {k:v for k,v in objects[name].items() if k != "status"} for name in ("producer", "consumer")}, indent=2))


if __name__ == "__main__":
    snapshot()
