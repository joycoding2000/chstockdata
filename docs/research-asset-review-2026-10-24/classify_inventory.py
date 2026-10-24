"""Assign mutually exclusive retention groups to the captured asset inventory."""
import collections
import csv
import json
from pathlib import Path

O = Path(__file__).resolve().parent
R = O.parents[1]


def dump(name, data):
    (O / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    inv = json.loads((O / "inventory.json").read_text(encoding="utf-8"))
    rows = json.loads((O / "main-files.json").read_text(encoding="utf-8"))["rows"]
    verification = json.loads((O / "collection-verification.json").read_text(encoding="utf-8"))
    duplicate_targets = {x["candidate"]["path"]: x["retained"]["path"] for x in verification["comparisons"]
                         if x["exact_path_size_content_equal"]}
    envs = {x["path"] for x in verification["historical_environments"]}
    keep_batches = {
        "2026-10-20-w5h-r3", "2026-10-20-w5h-r4", "2026-10-21-w5h-f2",
        "2026-10-21-w5h-f2-source-closure", "2026-10-22-w5h-f2-final-evidence-qualification",
        "2026-10-22-s07-free-supply-decisive-screen", "2026-10-22-sios-h01-final-repair",
        "2026-10-22-sios-h01-priority-delivery", "2026-10-22-sios-h04-priority-data-delivery",
        "2026-10-23-dr03-owner-semantics-closeout", "2026-10-23-dr03-s0a-capco", "2026-10-23-dr03-s1-capco"}
    ordinary_cache_files = {".pytest_cache/.gitignore", ".pytest_cache/CACHEDIR.TAG", ".pytest_cache/README.md"}
    groups = {}
    targets = {}
    totals = collections.defaultdict(lambda: {"files": 0, "bytes": 0})

    def add(root, group, category, size, count=1):
        key = (root, group, category)
        g = groups.setdefault(key, {"root": root, "group": group, "category": category, "files": 0, "bytes": 0})
        g["files"] += count
        g["bytes"] += size
        totals[category]["files"] += count
        totals[category]["bytes"] += size

    def target(path, size, category, retained=None, selected_file=False):
        physical = R / (".pytest_cache" if path.startswith(".pytest_cache/") else "") if selected_file else R / path
        t = targets.setdefault(path, {"path": str(physical), "relative_path": path,
                                      "kind": "SELECTED_FILES" if selected_file else "DIRECTORY",
                                      "category": category, "files": 0, "bytes": 0,
                                      "retained_copy": retained, "conditions": "Owner approval; recheck liveness, exact scope, no nested repository/unlisted files and restore identity before removal."})
        t["files"] += 1
        t["bytes"] += size
        return t

    main_root = str(R)
    for p, size, *_ in rows:
        candidate_prefix = next((x for x in [*duplicate_targets, *sorted(envs)] if p.startswith(x + "/")), None)
        if candidate_prefix:
            cat, group = "DELETE_CANDIDATE", candidate_prefix
            target(group, size, cat, duplicate_targets.get(group))
        elif p.startswith(".ruff_cache/") or p.startswith(".pytest_cache/v/") or p in ordinary_cache_files:
            cat = "DELETE_CANDIDATE"
            group = ".ruff_cache" if p.startswith(".ruff_cache/") else ".pytest_cache/standard-generated-only"
            t = target(group, size, cat, selected_file=group.endswith("only"))
            if t["kind"] == "SELECTED_FILES":
                t.setdefault("selected_paths", []).append(p)
        elif (p.startswith(("src/", "tests/", "scripts/", "build/__pycache__/"))
              and "/__pycache__/" in p and p.endswith(".pyc")
              and (R / Path(p).parent.parent / (Path(p).name.split(".cpython-")[0].split(".pypy")[0] + ".py")).exists()):
            cat, group = "DELETE_CANDIDATE", "current-source-bytecode-only"
            target(group, size, cat, selected_file=True).setdefault("selected_paths", []).append(p)
        elif p.startswith(".rh3a2-vipdoc/"):
            cat, group = "KEEP", ".rh3a2-vipdoc"
        elif p.startswith(".venv/"):
            cat, group = "KEEP", ".venv (current runtime)"
        elif p.startswith(".codegraph/"):
            cat, group = "KEEP", ".codegraph (current index)"
        elif p.startswith(".pytest_cache/"):
            cat, group = "REVIEW", ".pytest_cache/nonstandard-historical-content"
        elif p.startswith("build/v042-qualification/sios/var/"):
            cat, group = "ARCHIVE", "build/v042-qualification/sios/var"
        elif p.startswith("build/w0-v043/") or (p.startswith("build/") and p.endswith(".py")) or p in {"build/v042-qualification/sios.zip", "build/v042-qualification/ta.zip"}:
            cat, group = "ARCHIVE", "/".join(p.split("/")[:3])
        elif p.startswith(("build/", "dist/")):
            cat, group = "REVIEW", "/".join(p.split("/")[:3])
        elif p.startswith("docs/audits/evidence/"):
            group = "/".join(p.split("/")[:4])
            cat = "KEEP" if p.split("/")[3] in keep_batches else "ARCHIVE"
        else:
            cat, group = "KEEP", "/".join(p.split("/")[:2])
        add(main_root, group, cat, size)
    wt_targets, wt_review = [], []
    for w in inv["worktrees"][1:]:
        if "dr03-capco-archive" in w["root"]:
            category = "KEEP"
        elif "w0-v043-release" in w["root"]:
            category = "REVIEW"
            wt_review.append({"path": w["root"], "head": w["head"], "category": "REVIEW",
                              "files": w["files"], "bytes": w["logical_bytes"],
                              "reason": "Local wheel/sdist match recorded local artifacts but differ from published PyPI artifacts; no equal independent retained byte copy established."})
        else:
            category = "DELETE_CANDIDATE"
            wt_targets.append({"path": w["root"], "head": w["head"], "branch": w["branch"],
                               "files": w["files"], "bytes": w["logical_bytes"],
                               "retained_ref": "codex/ssd-migration-rh3b5-worktree-2026-10-23" if "v042-opening-cr" in w["root"] else
                                               ("codex/v042-release-audit" if "v042-controlled-release" in w["root"] else "main"),
                               "conditions": "Owner approves closure/removal; refresh status incl. ignored files and process use; preserve named Git refs; no force removal of new differences."})
        add(w["root"], "whole worktree", category, w["logical_bytes"], w["files"])
    assert sum(x["files"] for x in totals.values()) == inv["aggregate_files"]
    assert sum(x["bytes"] for x in totals.values()) == inv["aggregate_logical_bytes"]
    primary_totals = collections.defaultdict(lambda: {"files": 0, "bytes": 0})
    for row in groups.values():
        if row["root"] == main_root:
            primary_totals[row["category"]]["files"] += row["files"]
            primary_totals[row["category"]]["bytes"] += row["bytes"]
    branch_names = ["codex/cached-ohlcv-compatibility-hardening", "codex/phase41-routing-observation",
                    "codex/rh3-b4-live-qualification-evidence", "codex/rh3-b5-candidate-freeze-preflight",
                    "codex/trading-calendar-structured", "codex/v042-controlled-release",
                    "docs/v0.4.2-post-release-closeout",
                    "docs/v0.4.0-retrospective-design-audit"]
    refs = json.loads((O / "git-refs.json").read_text(encoding="utf-8"))["refs"]
    branches = []
    for name in branch_names:
        matches = [r for r in refs if r["ref"] in {"refs/heads/" + name, "refs/remotes/origin/" + name}]
        assert matches and all(r["commits_not_in_main"] == 0 for r in matches)
        branches.append({"name": name, "local_ref": next((r["ref"] for r in matches if r["ref"].startswith("refs/heads/")), None),
                         "remote_ref": "refs/heads/" + name if any(r["ref"].startswith("refs/remotes/") for r in matches) else None,
                         "heads": [{"ref": r["ref"], "sha": r["commit"]} for r in matches],
                         "retained_ref": "codex/ssd-migration-main-2026-10-23",
                         "conditions": "Keep protected refs; close dependent worktree first where applicable; update restore crosswalk; Owner approval; no merge to main."})
    result = {"scope": inv["scope"], "totals": totals, "main_worktree_totals": primary_totals,
              "aggregate_files": inv["aggregate_files"], "aggregate_logical_bytes": inv["aggregate_logical_bytes"],
              "identity_unique_bytes": inv["cross_worktree_identity_unique_bytes"],
              "primary_cleanup_targets": sorted(targets.values(), key=lambda x:x["relative_path"]),
              "worktree_cleanup_candidates": wt_targets, "branch_cleanup_candidates": branches,
              "worktree_review": wt_review,
              "branch_review": [{"name": "codex/w0-v043-release", "local_ref": "refs/heads/codex/w0-v043-release",
                                  "sha": "69957a58bcfd258f011c9c80250b58704fe0d784",
                                  "reason": "Commit is reachable from retained main, but checked-out worktree contains local artifact bytes still under REVIEW; resolve that collection before branch removal."}],
              "local_reclaimable_logical_bytes_estimate": totals["DELETE_CANDIDATE"]["bytes"],
              "actual_reclaimed_bytes": 0, "cleanup_authorized": False,
              "physical_space_limit": "Logical file bytes; file IDs deduplicated separately. No volume cluster, compression or open-handle guarantee; no Git object reclamation included."}
    dump("classification.json", result)
    with (O / "retention-groups.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["root", "group", "category", "files", "bytes"])
        writer.writeheader()
        writer.writerows(sorted(groups.values(), key=lambda x:(x["root"], x["group"], x["category"])))
    print(json.dumps({"totals":totals,"primary":primary_totals,"target_groups":len(targets),
                      "branch_names":len(branches),"worktrees":len(wt_targets),
                      "identity_unique_bytes":inv["cross_worktree_identity_unique_bytes"]},ensure_ascii=False))


if __name__ == "__main__":
    main()
