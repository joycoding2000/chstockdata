"""Bounded metadata grouping and existing Git-object/sample comparisons."""
import collections
import hashlib
import json
import os
from pathlib import Path
import subprocess
import zipfile
import zlib

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
ENV = {**os.environ, "GIT_OPTIONAL_LOCKS": "0"}


def git(*args, binary=False):
    r = subprocess.run(["git", *args], cwd=ROOT, env=ENV, capture_output=True, check=True)
    return r.stdout if binary else r.stdout.decode("utf-8").strip()


def dump(name, data):
    (OUT / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def tree(ref):
    out = {}
    for row in git("ls-tree", "-rlz", ref, binary=True).split(b"\0"):
        if row:
            meta, path = row.split(b"\t", 1)
            mode, kind, oid, size = meta.split()
            out[path.decode("utf-8")] = {"blob": oid.decode(), "bytes": int(size)}
    return out


def main():
    inv = json.loads((OUT / "inventory.json").read_text(encoding="utf-8"))
    rows = json.loads((OUT / "main-files.json").read_text(encoding="utf-8"))["rows"]
    files = {x[0]: x for x in rows}
    baseline = json.loads((OUT / "baseline-status.json").read_text(encoding="utf-8"))
    backup_ref = "refs/heads/codex/ssd-migration-main-2026-10-23"
    backup = tree(backup_ref)
    untracked = [p for p in baseline["untracked"] if p in files]
    missing = [p for p in untracked if p not in backup]
    size_mismatch = [p for p in untracked if p in backup and files[p][1] != backup[p]["bytes"]]
    by_batch = collections.defaultdict(list)
    for p in untracked:
        key = "/".join(p.split("/")[:4]) if p.startswith("docs/audits/evidence/") else "docs/reports"
        by_batch[key].append(p)
    samples = set()
    for key, paths in by_batch.items():
        preferred = [p for p in paths if Path(p).suffix in {".md", ".json", ".csv"}]
        samples.add(min(preferred or paths, key=lambda p: (files[p][1], p)))
    samples.update(p for _, p in sorted(((files[p][1], p) for p in untracked), reverse=True)[:5])
    samples.update(p for p in untracked if p.endswith(".md") and p.startswith("docs/audits/") and "/evidence/" not in p)
    checked = []
    for p in sorted(samples):
        oid = git("hash-object", "--no-filters", "--", p)
        checked.append({"path": p, "bytes": files[p][1], "local_git_blob": oid,
                        "backup_git_blob": backup.get(p, {}).get("blob"),
                        "exact_match": oid == backup.get(p, {}).get("blob")})
    dump("backup-coverage.json", {
        "backup_ref": backup_ref, "backup_commit": git("rev-parse", backup_ref),
        "untracked_files_excluding_this_review": len(untracked),
        "untracked_bytes": sum(files[p][1] for p in untracked),
        "path_covered": len(untracked) - len(missing), "missing_paths": missing,
        "size_mismatches": size_mismatch, "sampled_exact_blobs": checked,
        "limitation": "Path and size coverage over all original untracked files; only listed samples have current byte equality checked. No blanket byte-identity claim.",
        "batches": [{"path": key, "files": len(ps), "bytes": sum(files[p][1] for p in ps)}
                    for key, ps in sorted(by_batch.items())]})
    groups = collections.defaultdict(lambda: [0, 0])
    for p, size, *_ in rows:
        if p.startswith("docs/audits/evidence/2026-10-11-v0.4.2-opening-implementation/"):
            key = "/".join(p.split("/")[:6])
            groups[key][0] += 1
            groups[key][1] += size
    dump("opening-subgroups.json", dict(sorted(groups.items())))
    print("UNTRACKED", len(untracked), sum(files[p][1] for p in untracked), "MISSING", len(missing),
          "SIZE_MISMATCH", len(size_mismatch), "SAMPLES", len(checked), "BAD", sum(not x["exact_match"] for x in checked))
    for k, v in sorted(groups.items()):
        if v[1] > 1000000:
            print("OPENING", k, *v)
    for w in inv["worktrees"][1:]:
        print("WORKTREE", w["root"], w["status_counts"], w["files"], w["logical_bytes"])
        if w["status_counts"]:
            continue
        for k, v in w["groups"].items():
            if v["git_states"].get("ignored"):
                print("IGNORED", k, v["files"], v["bytes"])


if __name__ == "__main__":
    main()
