import importlib.util
import hashlib
import json
from pathlib import Path
import subprocess
import sys

spec = importlib.util.spec_from_file_location("control", Path(__file__).with_name("w0-v043-control.py"))
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)
pre = c.EVIDENCE
c.EVIDENCE = c.TEMP / "post-release-evidence"
statefile = c.TEMP / "publish-state.json"


def remote(name, ref):
    c.run(name, ["git", "ls-remote", "origin", ref])
    text = (c.EVIDENCE / f"{name}.stdout.txt").read_text(encoding="utf-8").strip()
    return text.split()[0] if text else None


step = sys.argv[1]
if step == "commit-push-tag":
    verdict = json.loads((pre / "preflight-verdict.json").read_text(encoding="utf-8"))
    assert all(verdict[k] == "PASS" for k in ("APPROVED_SCOPE_MATCH", "VERSION_CONSISTENCY", "DETERMINISTIC_TESTS", "RELEASE_PREFLIGHT", "ARTIFACT_VALIDATION", "ISOLATED_INSTALL"))
    hashes = json.loads((pre / "evidence-sha256.json").read_text(encoding="utf-8"))
    assert all(c.digest(pre / p) == sha for p, sha in hashes.items())
    scope = json.loads((pre / "scope-and-identity.json").read_text(encoding="utf-8"))
    allowed = set(scope["authorized_files"])
    prefix = scope["evidence_prefix"]
    actual = c.git("diff", "--name-only", c.BASE).splitlines() + c.git("ls-files", "--others", "--exclude-standard").splitlines()
    assert all(p in allowed or p.startswith(prefix) for p in actual)
    assert c.git("rev-parse", "HEAD") == c.BASE
    assert c.git("rev-parse", "HEAD", cwd=c.ORIGINAL) == c.BASE
    assert not c.git("diff", "HEAD", cwd=c.ORIGINAL)
    assert remote("main-before-commit", "refs/heads/main") == c.BASE
    assert remote("tag-before-commit", "refs/tags/v0.4.3") is None
    assert not c.git("tag", "--list", "v0.4.3")
    c.run("stage-release", ["git", "add", "--", *sorted(allowed), prefix])
    staged = c.git("diff", "--cached", "--name-only").splitlines()
    assert all(p in allowed or p.startswith(prefix) for p in staged)
    for p, sha in hashes.items():
        indexed = subprocess.check_output(["git", "show", ":" + prefix + p], cwd=c.ROOT)
        assert hashlib.sha256(indexed).hexdigest() == sha, p
    c.run("staged-whitespace-platform", ["git", "-c", "core.whitespace=cr-at-eol", "diff", "--cached", "--check", "--", *sorted(allowed)])
    c.save(c.EVIDENCE / "staged-files.json", {p: c.git("rev-parse", ":" + p) for p in staged})
    c.run("release-commit", ["git", "commit", "-m", "release: publish v0.4.3 Owner-accepted DR04-P"])
    sha = c.git("rev-parse", "HEAD")
    c.save(statefile, {"release_sha": sha})
    assert not c.git("status", "--porcelain")
    assert remote("main-before-push", "refs/heads/main") == c.BASE
    c.run("main-fast-forward", ["git", "merge", "--ff-only", sha], cwd=c.ORIGINAL)
    assert c.git("rev-parse", "HEAD", cwd=c.ORIGINAL) == sha
    c.run("push-main", ["git", "push", "origin", "main:main"], cwd=c.ORIGINAL)
    assert remote("main-after-push", "refs/heads/main") == sha
    assert remote("tag-before-create", "refs/tags/v0.4.3") is None
    assert not c.git("diff", "HEAD")
    c.run("annotated-tag", ["git", "tag", "-a", "v0.4.3", sha, "-m", "chstockdata v0.4.3: Owner-accepted DR04-P daily fund flow"])
    obj = c.git("rev-parse", "v0.4.3")
    assert c.git("cat-file", "-t", obj) == "tag"
    assert c.git("rev-parse", "v0.4.3^{commit}") == sha
    c.save(statefile, {"release_sha": sha, "tag_object_sha": obj, "tag_target_sha": sha})
    c.run("push-tag", ["git", "push", "origin", "refs/tags/v0.4.3:refs/tags/v0.4.3"])
    assert remote("tag-after-push", "refs/tags/v0.4.3") == obj
    assert remote("tag-target-after-push", "refs/tags/v0.4.3^{}") == sha
    print(json.dumps(json.loads(statefile.read_text(encoding="utf-8")), indent=2))
elif step == "resume-push-tag":
    state = json.loads(statefile.read_text(encoding="utf-8"))
    sha = state["release_sha"]
    assert c.git("rev-parse", "HEAD") == sha
    raw_paths = [r["path"] for r in json.loads((pre / "initial-failure-analysis.json").read_text(encoding="utf-8"))["jsonl_bytes"]]
    for p in raw_paths:
        assert (c.ROOT / p).read_bytes() == subprocess.check_output(["git", "show", sha + ":" + p], cwd=c.ROOT)
    c.run("refresh-unchanged-raw-index", ["git", "add", "--", *raw_paths])
    assert not c.git("diff", "--cached", "--name-only")
    assert not c.git("status", "--porcelain")
    assert c.git("rev-parse", "HEAD", cwd=c.ORIGINAL) == c.BASE
    assert not c.git("diff", "HEAD", cwd=c.ORIGINAL)
    assert remote("main-before-push", "refs/heads/main") == c.BASE
    assert remote("tag-before-create", "refs/tags/v0.4.3") is None
    c.run("main-fast-forward", ["git", "merge", "--ff-only", sha], cwd=c.ORIGINAL)
    assert c.git("rev-parse", "HEAD", cwd=c.ORIGINAL) == sha
    c.run("push-main", ["git", "push", "origin", "main:main"], cwd=c.ORIGINAL)
    assert remote("main-after-push", "refs/heads/main") == sha
    c.run("annotated-tag", ["git", "tag", "-a", "v0.4.3", sha, "-m", "chstockdata v0.4.3: Owner-accepted DR04-P daily fund flow"])
    obj = c.git("rev-parse", "v0.4.3")
    assert c.git("cat-file", "-t", obj) == "tag"
    assert c.git("rev-parse", "v0.4.3^{commit}") == sha
    c.save(statefile, {"release_sha": sha, "tag_object_sha": obj, "tag_target_sha": sha})
    c.run("push-tag", ["git", "push", "origin", "refs/tags/v0.4.3:refs/tags/v0.4.3"])
    assert remote("tag-after-push", "refs/tags/v0.4.3") == obj
    assert remote("tag-target-after-push", "refs/tags/v0.4.3^{}") == sha
    print(json.dumps(json.loads(statefile.read_text(encoding="utf-8")), indent=2))
elif step == "find-run":
    state = json.loads(statefile.read_text(encoding="utf-8"))
    c.run("actions-runs", ["gh", "run", "list", "--repo", "joycoding2000/chstockdata", "--workflow", "publish.yml", "--event", "push", "--branch", "v0.4.3", "--limit", "10", "--json", "databaseId,headSha,headBranch,status,conclusion,url"])
    runs = json.loads((c.EVIDENCE / "actions-runs.stdout.txt").read_text(encoding="utf-8"))
    runs = [r for r in runs if r["headSha"] == state["release_sha"] and r["headBranch"] == "v0.4.3"]
    assert len(runs) <= 1
    if runs:
        state["run_id"] = runs[0]["databaseId"]
        state["run_url"] = runs[0]["url"]
        c.save(statefile, state)
    print(json.dumps(runs, indent=2))
elif step == "run-status":
    state = json.loads(statefile.read_text(encoding="utf-8"))
    c.run("actions-status", ["gh", "run", "view", str(state["run_id"]), "--repo", "joycoding2000/chstockdata", "--json", "status,conclusion,jobs,headSha,headBranch,url,event,workflowName"])
    status = json.loads((c.EVIDENCE / "actions-status.stdout.txt").read_text(encoding="utf-8"))
    assert status["headSha"] == state["release_sha"] and status["headBranch"] == "v0.4.3"
    print(json.dumps({"status": status["status"], "conclusion": status["conclusion"], "url": status["url"],
        "jobs": [{"name": j["name"], "status": j["status"], "conclusion": j["conclusion"],
                  "current_or_failed_steps": [s["name"] for s in j["steps"] if s["status"] == "in_progress" or s["conclusion"] == "failure"]} for j in status["jobs"]]}, indent=2))
