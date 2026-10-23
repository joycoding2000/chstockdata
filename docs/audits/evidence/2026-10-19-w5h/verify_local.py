"""One-off W5-H local identity check; no network or runtime changes."""
import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import sys

BASE = Path(__file__).resolve().parent
ROOTS = [Path("D:/Dev/Projects") / name for name in
         ("chstockdata", "mishi-radar", "systematic-investing-os")]


def git(root, *args):
    return subprocess.check_output(
        ["git", "-c", f"safe.directory={root.as_posix()}", "-C", str(root), *args],
        stderr=subprocess.DEVNULL,
    )


def capture():
    result = {"captured_at": datetime.datetime.now(datetime.timezone(
        datetime.timedelta(hours=8))).isoformat(), "repositories": {}}
    for root in ROOTS:
        names = sorted(set(filter(None, git(root, "ls-files", "-z", "-c", "-o",
            "--exclude-standard").decode("utf-8").split("\0"))))
        files = {}
        for name in names:
            path = root / name
            if path.is_file() and not (root.name == "chstockdata" and
                    name.startswith("docs/audits/evidence/2026-10-19-w5h/")):
                files[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        result["repositories"][root.name] = {
            "head": git(root, "rev-parse", "HEAD").decode().strip(),
            "status": git(root, "status", "--porcelain=v1",
                          "--untracked-files=normal").decode("utf-8"),
            "diff_sha256": hashlib.sha256(git(root, "diff", "HEAD", "--binary")).hexdigest(),
            "index_sha256": hashlib.sha256(git(root, "diff", "--cached", "--binary")).hexdigest(),
            "files": files,
        }
    return result


if __name__ == "__main__":
    current = capture()
    if sys.argv[1] == "before":
        target = BASE / "before.json"
        assert not target.exists()
        target.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
        print({k: {"head": v["head"], "files": len(v["files"])}
               for k, v in current["repositories"].items()})
    else:
        before = json.loads((BASE / "before.json").read_text(encoding="utf-8"))
        checks = {}
        for name, old in before["repositories"].items():
            new = current["repositories"][name]
            checks[name] = {
                "head_unchanged": old["head"] == new["head"],
                "tracked_diff_unchanged": old["diff_sha256"] == new["diff_sha256"],
                "index_unchanged": old["index_sha256"] == new["index_sha256"],
                "original_files": len(old["files"]),
                "changed_or_removed": [p for p, h in old["files"].items() if new["files"].get(p) != h],
                "new_files_outside_evidence": sorted(set(new["files"]) - set(old["files"])),
                "status": new["status"],
            }
        (BASE / "verification.json").write_text(json.dumps(checks, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(checks, ensure_ascii=False, indent=2))
