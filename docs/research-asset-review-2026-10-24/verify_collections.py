"""Compare only named high-value duplicate candidates and one saved worktree."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess

O = Path(__file__).resolve().parent
R = O.parents[1]
ROWS = json.loads((O / "main-files.json").read_text(encoding="utf-8"))["rows"]


def fingerprint(prefix):
    selected = sorted((p[len(prefix) + 1:], p, size) for p, size, *_ in ROWS if p.startswith(prefix + "/"))
    digest = hashlib.sha256()
    count = total = 0
    for rel, p, size in selected:
        h = hashlib.sha256()
        with (R / p).open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        digest.update(rel.encode("utf-8") + b"\0" + str(size).encode() + b"\0" + h.digest())
        count += 1
        total += size
    return {"path": prefix, "files": count, "bytes": total, "collection_sha256": digest.hexdigest()}


def main():
    comparisons = []
    retained = "build/v042-qualification/sios/var"
    baseline = fingerprint(retained)
    for target in ["build/v042-qualification/sios-baseline/var", "build/v042-unified/sios/var"]:
        candidate = fingerprint(target)
        comparisons.append({"retained": baseline, "candidate": candidate,
                            "exact_path_size_content_equal": baseline["collection_sha256"] == candidate["collection_sha256"]})
    stem = "docs/audits/evidence/2026-10-11-v0.4.2-opening-implementation/"
    for suffix in ["sios-frozen-source", "sios-reconstructed-source", "sios-reconstructed-source-exact"]:
        a = fingerprint(stem + "owner-acceptance-rework-r1/" + suffix)
        b = fingerprint(stem + "owner-acceptance-rework-r1-copy-attempt/" + suffix)
        comparisons.append({"retained": a, "candidate": b,
                            "exact_path_size_content_equal": a["collection_sha256"] == b["collection_sha256"]})
    worktree = Path("C:/Users/Administrator/.codex/worktrees/v042-opening-cr/chstockdata")
    ref = "codex/ssd-migration-rh3b5-worktree-2026-10-23"
    env = {**os.environ, "GIT_OPTIONAL_LOCKS": "0"}
    result = subprocess.run(["git", "ls-tree", "-rz", ref], cwd=R, env=env, capture_output=True, check=True)
    tree = {p.decode("utf-8"): meta.split()[2].decode("ascii") for meta, p in
            (line.split(b"\t", 1) for line in result.stdout.split(b"\0") if line)}
    checked, mismatches = [], []
    for base, dirs, names in os.walk(worktree):
        dirs[:] = [d for d in dirs if d != ".git"]
        for name in sorted(names):
            p = Path(base) / name
            if name == ".git":
                continue
            rel = p.relative_to(worktree).as_posix()
            data = p.read_bytes()
            oid = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
            checked.append(rel)
            if tree.get(rel) != oid:
                mismatches.append(rel)
    venvs = []
    for p, size, *_ in ROWS:
        if p.endswith("/pyvenv.cfg") and not p.startswith(".venv/"):
            root = (R / p).parent
            packages = sorted(x.name for x in (root / "Lib/site-packages").glob("*.dist-info"))
            venvs.append({"path": root.relative_to(R).as_posix(),
                          "pyvenv_cfg": (R / p).read_text(encoding="utf-8"),
                          "installed_dist_info_directories": packages,
                          "rebuild_limit": "Version inventory and environment origin, not a wheelhouse or a guarantee of exact historical resolver/byte reproduction."})
    out = {"comparisons": comparisons,
           "snapshot_worktree": {"path": str(worktree), "ref": ref, "files_checked": len(checked),
                                 "files_in_backup_tree": len(tree), "mismatches": mismatches,
                                 "missing_locally_but_in_backup": sorted(set(tree) - set(checked)),
                                 "method": "Every current file compared as raw Git blob; no checkout, staging, qualification run or source request."},
           "historical_environments": venvs}
    (O / "collection-verification.json").write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for item in comparisons:
        print(item["candidate"]["path"], item["candidate"]["files"], item["candidate"]["bytes"], item["exact_path_size_content_equal"])
    print("WORKTREE",len(checked),"MISMATCHES",len(mismatches),"MISSING",len(set(tree)-set(checked)))


if __name__ == "__main__":
    main()
