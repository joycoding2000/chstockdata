"""Verify report arithmetic, retained Git objects and unchanged working state."""
import collections
import csv
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

O = Path(__file__).resolve().parent
R = O.parents[1]
ENV = {**os.environ, "GIT_OPTIONAL_LOCKS": "0"}


def git(*args, cwd=R):
    p = subprocess.run(["git", "-c", "core.quotepath=false", "-c", "safe.directory=" + cwd.as_posix(), *args],
                       cwd=cwd, env=ENV, capture_output=True, check=True)
    return p.stdout.decode("utf-8").rstrip()


def read(name):
    return json.loads((O / name).read_text(encoding="utf-8-sig"))


def write(name, data):
    (O / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def set_digest(paths):
    return hashlib.sha256("\0".join(sorted(paths)).encode("utf-8")).hexdigest()


def main():
    c, inv, coverage, refs = map(read, ["classification.json", "inventory.json", "backup-coverage.json", "git-refs.json"])
    prefix = O.relative_to(R).as_posix() + "/"
    if (O / "baseline-status.json").exists():
        b = read("baseline-status.json")
        write("baseline-summary.json", {"head": b["head"], "tracked_diff": b["tracked_diff"],
                                       "staged_diff": b["staged_diff"], "untracked_files": len(b["untracked"]),
                                       "untracked_pathset_sha256": set_digest(b["untracked"]),
                                       "untracked_paths_recoverable_via": coverage["backup_commit"],
                                       "census_main_files": inv["worktrees"][0]["files"],
                                       "census_main_bytes": inv["worktrees"][0]["logical_bytes"],
                                       "census_pathset_sha256": set_digest(x[0] for x in read("main-files.json")["rows"])})
    b = read("baseline-summary.json")
    checks = {}
    checks["category_files_sum"] = sum(x["files"] for x in c["totals"].values()) == inv["aggregate_files"]
    checks["category_bytes_sum"] = sum(x["bytes"] for x in c["totals"].values()) == inv["aggregate_logical_bytes"]
    with (O / "retention-groups.csv").open(encoding="utf-8", newline="") as f:
        groups = list(csv.DictReader(f))
    checks["csv_files_sum"] = sum(int(x["files"]) for x in groups) == inv["aggregate_files"]
    checks["csv_bytes_sum"] = sum(int(x["bytes"]) for x in groups) == inv["aggregate_logical_bytes"]
    checks["candidate_files_sum"] = (sum(x["files"] for x in c["primary_cleanup_targets"]) +
                                      sum(x["files"] for x in c["worktree_cleanup_candidates"])) == c["totals"]["DELETE_CANDIDATE"]["files"]
    checks["candidate_bytes_sum"] = (sum(x["bytes"] for x in c["primary_cleanup_targets"]) +
                                      sum(x["bytes"] for x in c["worktree_cleanup_candidates"])) == c["totals"]["DELETE_CANDIDATE"]["bytes"]
    checks["no_inventory_errors"] = not any(w["errors"] or w["links_skipped"] for w in inv["worktrees"])
    current_paths, traversal_errors = [], []
    for base, dirs, names in os.walk(R, followlinks=False, onerror=lambda e: traversal_errors.append(str(e))):
        dirs[:] = [d for d in dirs if d != ".git" and (Path(base) / d).resolve() != O
                   and not (Path(base) / d).is_symlink() and not (Path(base) / d).is_junction()]
        current_paths.extend((Path(base) / name).relative_to(R).as_posix() for name in names if name != ".git")
    checks["main_census_pathset_complete"] = not traversal_errors and set_digest(current_paths) == b["census_pathset_sha256"]
    checks["main_head_unchanged"] = git("rev-parse", "HEAD") == b["head"]
    checks["main_branch_unchanged"] = git("branch", "--show-current") == "main"
    checks["main_tracked_unchanged"] = git("diff", "--name-status") == b["tracked_diff"] == ""
    checks["main_index_unchanged"] = git("diff", "--cached", "--name-status") == b["staged_diff"] == ""
    untracked = [p for p in git("ls-files", "--others", "--exclude-standard").splitlines() if not p.startswith(prefix)]
    checks["original_untracked_pathset_unchanged"] = set_digest(untracked) == b["untracked_pathset_sha256"]
    checks["backup_path_size_coverage"] = not coverage["missing_paths"] and not coverage["size_mismatches"]
    checks["sample_blobs_preserved"] = all(git("hash-object", "--no-filters", "--", x["path"]) == x["backup_git_blob"]
                                            for x in coverage["sampled_exact_blobs"])
    collections_result = read("collection-verification.json")
    checks["duplicate_collections_verified"] = all(x["exact_path_size_content_equal"] for x in collections_result["comparisons"])
    wt = collections_result["snapshot_worktree"]
    checks["dirty_worktree_snapshot_preserved"] = wt["files_checked"] == 758 and not wt["mismatches"] and not wt["missing_locally_but_in_backup"]
    checks["existing_refs_unchanged"] = all(git("rev-parse", x["ref"]) == x["object"] for x in refs["refs"])
    remote = {}
    for line in (O / "remote-refs.txt").read_text(encoding="utf-8-sig").splitlines():
        oid, ref = line.split()
        remote[ref] = oid
    checks["remote_refs_captured"] = len([x for x in remote if x.startswith("refs/heads/")]) == 14
    checks["remote_backup_refs_match"] = all(remote.get(x["ref"].replace("refs/remotes/origin/", "refs/heads/")) == x["object"]
                                              for x in refs["refs"] if x["ref"].startswith("refs/remotes/origin/") and not x["ref"].endswith("/HEAD"))
    checks["candidate_commits_reachable"] = all(git("rev-list", "--count", h["sha"], "^" + b["head"]) == "0"
                                                for x in c["branch_cleanup_candidates"] for h in x["heads"])
    wt_results = []
    for w in inv["worktrees"][1:]:
        path = Path(w["root"])
        counts = dict(collections.Counter(line[:2] for line in git("status", "--porcelain=v1", "-uall", cwd=path).splitlines()))
        wt_results.append({"path": str(path), "head_unchanged": git("rev-parse", "HEAD", cwd=path) == w["head"],
                           "status_counts": counts, "expected_status_counts": w["status_counts"]})
    checks["worktree_heads_unchanged"] = all(x["head_unchanged"] for x in wt_results)
    checks["worktree_status_counts_unchanged"] = all(x["status_counts"] == x["expected_status_counts"] for x in wt_results)
    release_text = (R / "docs/audits/2026-10-19-v0.4.3-release-closeout.md").read_text(encoding="utf-8")
    release_artifacts = {}
    local_artifacts_record = (R / "docs/audits/evidence/2026-10-19-v0.4.3-release/local-artifacts.json").read_text(encoding="utf-8").lower()
    local_artifacts_traceable = []
    for name, expected in re.findall(r"`(chstockdata-0\.4\.3[^`]+)`\s*\|\s*`([0-9a-f]{64})`", release_text):
        artifact = Path("C:/Users/Administrator/.codex/worktrees/w0-v043-release/chstockdata/dist") / name
        current_sha = hashlib.sha256(artifact.read_bytes()).hexdigest()
        release_artifacts[name] = {"current_sha256": current_sha, "published_sha256": expected,
                                   "matches_published": current_sha == expected}
        local_artifacts_traceable.append(current_sha in local_artifacts_record)
    checks["w0_local_artifacts_identity_traceable"] = len(local_artifacts_traceable) == 2 and all(local_artifacts_traceable)
    checks["w0_artifacts_held_in_review"] = len(c["worktree_review"]) == 1 and c["worktree_review"][0]["category"] == "REVIEW"
    documents = [O / name for name in ["RESEARCH_ASSET_INDEX.md", "RESEARCH_DECISION_QUEUE.md", "ASSET_RETENTION_AND_CLEANUP_PLAN.md"]]
    git_links = set()
    local_links = []
    for path in documents:
        text = path.read_text(encoding="utf-8")
        git_links.update(re.findall(r"https://github\.com/joycoding2000/chstockdata/blob/([0-9a-f]{40})/([^\s)]+)", text))
        for link in re.findall(r"\]\(([^)]+)\)", text):
            if not link.startswith("https://"):
                local_links.append((path.parent / link).exists())
    batch = "".join(sha + ":" + path + "\n" for sha, path in sorted(git_links))
    p = subprocess.run(["git", "cat-file", "--batch-check"], cwd=R, env=ENV, input=batch.encode("utf-8"), capture_output=True, check=True)
    checks["git_evidence_links_resolve"] = b" missing" not in p.stdout and len(p.stdout.splitlines()) == len(git_links)
    checks["local_document_links_resolve"] = all(local_links)
    checks["no_cleanup_authorization"] = c["cleanup_authorized"] is False and c["actual_reclaimed_bytes"] == 0
    result = {"checked_at_utc": datetime.now(timezone.utc).isoformat(), "checks": checks,
              "all_pass": all(checks.values()), "git_evidence_links_checked": len(git_links),
              "worktree_states": wt_results, "recorded_release_artifacts": release_artifacts,
              "source_requests": 0, "qualification_tests_run": 0,
              "limits": ["Historical test outputs were sampled/indexed, not rerun or independently requalified.",
                         "Process evidence is a snapshot; refresh before cleanup.",
                         "All original untracked paths retained; only 53 current-byte samples rehashed, not all research originals."],
              "documents_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in documents}}
    write("review-verification.json", result)
    print(json.dumps({"all_pass": result["all_pass"], "checks": checks, "git_links": len(git_links)}))
    if not result["all_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
