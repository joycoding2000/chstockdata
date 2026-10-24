"""Read-only asset metadata and Git reachability inventory; no source requests."""
from __future__ import annotations

import collections
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent


def git(*args: str, cwd: Path = ROOT, binary: bool = False):
    result = subprocess.run(["git", "-c", "core.quotepath=false", "-c",
                             "safe.directory=" + cwd.resolve().as_posix(), *args], cwd=cwd,
                            capture_output=True, env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"})
    if result.returncode:
        raise RuntimeError(f"Git failed at {cwd}: {result.stderr.decode('utf-8', errors='replace')}")
    return result.stdout if binary else result.stdout.decode("utf-8").strip()


def dump(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def scan(root: Path):
    if "--resume" in sys.argv and root.resolve() == ROOT and (OUT / "main-files.json").exists():
        rows = json.loads((OUT / "main-files.json").read_text(encoding="utf-8"))["rows"]
        return summarize_rows(root, rows), rows
    groups = {}
    identities = set()
    errors, links, largest = [], [], []
    files = []
    for base, dirs, names in os.walk(root, followlinks=False, onerror=lambda e: errors.append(str(e))):
        dirs[:] = sorted(d for d in dirs if d != ".git" and (Path(base) / d).resolve() != OUT)
        for d in dirs[:]:
            p = Path(base) / d
            if p.is_symlink() or p.is_junction():
                links.append(str(p.relative_to(root)))
                dirs.remove(d)
        for name in sorted(names):
            p = Path(base) / name
            if name == ".git":
                continue
            try:
                s = p.stat(follow_symlinks=False)
                if p.is_symlink():
                    links.append(str(p.relative_to(root)))
                    continue
                rel = p.relative_to(root).as_posix()
                parts = rel.split("/")
                # Evidence batch, build/dist subtask, environment, or ordinary top-level tree.
                depth = 4 if rel.startswith("docs/audits/evidence/") else 2
                key = "/".join(parts[:depth]) if len(parts) > depth else rel
                g = groups.setdefault(key, {"files": 0, "bytes": 0, "identity_unique_bytes": 0,
                                           "multilink_files": 0, "extensions": {}, "latest_mtime_ns": 0})
                identity = (s.st_dev, s.st_ino)
                unique = identity not in identities
                identities.add(identity)
                g["files"] += 1
                g["bytes"] += s.st_size
                g["identity_unique_bytes"] += s.st_size if unique else 0
                g["multilink_files"] += int(s.st_nlink > 1)
                g["latest_mtime_ns"] = max(g["latest_mtime_ns"], s.st_mtime_ns)
                ext = p.suffix.lower() or "[none]"
                g["extensions"][ext] = g["extensions"].get(ext, 0) + 1
                files.append((rel, s.st_size, s.st_mtime_ns, s.st_dev, s.st_ino, s.st_nlink))
                largest.append((s.st_size, rel))
            except OSError as e:
                errors.append(str(e))
    return {"root": str(root), "groups": groups, "files": len(files),
            "logical_bytes": sum(x[1] for x in files),
            "identity_unique_bytes": sum(g["identity_unique_bytes"] for g in groups.values()),
            "links_skipped": links, "errors": errors, "largest": sorted(largest, reverse=True)[:12]}, files


def summarize_rows(root, rows):
    groups, seen = {}, set()
    for rel, size, mtime, dev, ino, nlink in rows:
        parts = rel.split("/")
        depth = 4 if rel.startswith("docs/audits/evidence/") else 2
        key = "/".join(parts[:depth]) if len(parts) > depth else rel
        g = groups.setdefault(key, {"files": 0, "bytes": 0, "identity_unique_bytes": 0,
                                   "multilink_files": 0, "extensions": {}, "latest_mtime_ns": 0})
        g["files"] += 1
        g["bytes"] += size
        g["identity_unique_bytes"] += size if (dev, ino) not in seen else 0
        seen.add((dev, ino))
        g["multilink_files"] += int(nlink > 1)
        g["latest_mtime_ns"] = max(g["latest_mtime_ns"], mtime)
        ext = Path(rel).suffix.lower() or "[none]"
        g["extensions"][ext] = g["extensions"].get(ext, 0) + 1
    return {"root": str(root), "groups": groups, "files": len(rows),
            "logical_bytes": sum(x[1] for x in rows),
            "identity_unique_bytes": sum(g["identity_unique_bytes"] for g in groups.values()),
            "links_skipped": [], "errors": [],
            "metadata_reused_from": "main-files.json; captured during the initial successful main walk",
            "largest": sorted(((x[1], x[0]) for x in rows), reverse=True)[:12]}


def main():
    start = datetime.now(timezone.utc).isoformat()
    baseline = git("rev-parse", "HEAD")
    refs = []
    for row in git("for-each-ref", "--format=%(refname)|%(objectname)|%(upstream:short)",
                   "refs/heads", "refs/remotes", "refs/tags").splitlines():
        ref, sha, upstream = row.split("|")
        commit = git("rev-parse", ref + "^{commit}")
        refs.append({"ref": ref, "object": sha, "commit": commit, "upstream": upstream})
    backup_names = [x["ref"] for x in refs if x["ref"].startswith("refs/heads/codex/ssd-migration-")]
    reachability = {}
    for r in refs:
        commit = r["commit"]
        if commit in reachability:
            r.update(reachability[commit])
            r["retaining_refs"] = [x for x in r["retaining_refs"] if x != r["ref"]]
            continue
        r["commits_not_in_main"] = int(git("rev-list", "--count", commit, "^" + baseline))
        r["commits_not_in_backups_or_main"] = int(git("rev-list", "--count", commit,
                                                      "^" + baseline, *["^" + b for b in backup_names]))
        containing = git("for-each-ref", "--format=%(refname)", "--contains=" + commit,
                         "refs/heads", "refs/remotes", "refs/tags").splitlines()
        r["retaining_refs"] = [x for x in containing if x != r["ref"]]
        reachability[commit] = {k: r[k] for k in ["commits_not_in_main", "commits_not_in_backups_or_main"]}
        reachability[commit]["retaining_refs"] = containing
    dump("git-refs.json", {"baseline": baseline, "refs": refs,
                           "stash": git("stash", "list"), "object_storage": git("count-objects", "-v")})
    blocks = git("worktree", "list", "--porcelain").split("\n\n")
    worktrees = []
    all_files = []
    for block in blocks:
        lines = block.splitlines()
        path = Path(lines[0][9:].strip('"'))
        print("Scanning " + str(path), flush=True)
        summary, files = scan(path)
        summary["head"] = git("rev-parse", "HEAD", cwd=path)
        summary["branch"] = next((l[7:] for l in lines if l.startswith("branch ")), "DETACHED")
        status = git("status", "--porcelain=v1", "-uall", cwd=path, binary=True)
        untracked = git("ls-files", "--others", "--exclude-standard", "-z", cwd=path, binary=True)
        ignored = git("ls-files", "--others", "--ignored", "--exclude-standard", "-z", cwd=path, binary=True)
        tracked = git("ls-files", "-z", cwd=path, binary=True)
        sets = {k: set(v.decode("utf-8").split("\0")) - {""} for k, v in
                [("tracked", tracked), ("untracked", untracked), ("ignored", ignored)]}
        summary["status_counts"] = dict(collections.Counter(l[:2].decode("utf-8") for l in status.splitlines()))
        summary["git_path_counts"] = {k: len(v) for k, v in sets.items()}
        for g in summary["groups"].values():
            g["git_states"] = {}
        for rel, size, *_ in files:
            parts = rel.split("/")
            depth = 4 if rel.startswith("docs/audits/evidence/") else 2
            key = "/".join(parts[:depth]) if len(parts) > depth else rel
            state = next((k for k, v in sets.items() if rel in v), "other")
            stats = summary["groups"][key]["git_states"].setdefault(state, {"files": 0, "bytes": 0})
            stats["files"] += 1
            stats["bytes"] += size
        if path.resolve() == ROOT:
            dump("baseline-status.json", {"head": baseline, "tracked_diff": git("diff", "--name-status"),
                                         "staged_diff": git("diff", "--cached", "--name-status"),
                                         "untracked": sorted(p for p in sets["untracked"] if not p.startswith(OUT.relative_to(ROOT).as_posix() + "/"))})
            dump("main-files.json", {"schema": ["relative_path", "bytes", "mtime_ns", "device", "file_id", "nlink"], "rows": files})
        worktrees.append(summary)
        all_files.extend((str(path / rel), size, dev, ino, nlink) for rel, size, _, dev, ino, nlink in files)
    unique = {}
    for p, size, dev, ino, nlink in all_files:
        unique.setdefault((dev, ino), size)
    dump("inventory.json", {"captured_at_utc": start, "baseline": baseline,
                            "scope": "chstockdata registered worktrees; .git and this report excluded",
                            "worktrees": worktrees, "aggregate_files": len(all_files),
                            "aggregate_logical_bytes": sum(x[1] for x in all_files),
                            "cross_worktree_identity_unique_bytes": sum(unique.values()),
                            "method": "One metadata walk per worktree; no recursive symlink/junction traversal; no raw data hashing. Byte lengths are not allocated clusters or guaranteed reclaimed space."})
    print(json.dumps({"worktrees": len(worktrees), "files": len(all_files),
                      "bytes": sum(x[1] for x in all_files), "main_groups": len(worktrees[0]["groups"]),
                      "errors": [w["errors"] for w in worktrees]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
