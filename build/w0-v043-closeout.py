import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess

spec = importlib.util.spec_from_file_location("control", Path(__file__).with_name("w0-v043-control.py"))
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)
pre = c.EVIDENCE
c.EVIDENCE = c.TEMP / "post-release-evidence"
result = json.loads((c.EVIDENCE / "post-release-result.json").read_text(encoding="utf-8"))
assert result["W0_FINAL_VERDICT"] == "RELEASE_COMPLETE"
sha = result["release_sha"]
assert c.git("rev-parse", "HEAD") == sha
assert c.git("rev-parse", "v0.4.3^{commit}") == sha
assert c.git("rev-parse", "v0.4.3") == result["tag_object_sha"]
assert not c.git("diff", "HEAD")
assert not c.git("diff", "HEAD", cwd=c.ORIGINAL)
original = json.loads((pre / "original-worktree.json").read_text(encoding="utf-8"))
assert all((c.ORIGINAL / p).is_file() and c.digest(c.ORIGINAL / p) == h for p, h in original["untracked_files"].items())
now = c.git("status", "--porcelain", "--untracked-files=normal", cwd=c.ORIGINAL)
assert now == original["status_normal"]
c.save(c.EVIDENCE / "original-worktree-preserved.json", {"verdict": "PASS", "normal_status_matches_initial": True,
    "original_untracked_file_hashes_match": True, "status": now})
c.run("official-actions-log", ["gh", "run", "view", str(result["run_id"]), "--repo", "joycoding2000/chstockdata", "--log"])
full_log = (c.EVIDENCE / "official-actions-log.stdout.txt").read_text(encoding="utf-8")
test_lines = [line for line in full_log.splitlines() if " passed" in line and ("deselected" in line or "skipped" in line)]
assert test_lines
c.save(c.EVIDENCE / "official-test-summary.json", {"lines": test_lines})
c.run("final-main-before-audit", ["git", "ls-remote", "origin", "refs/heads/main"])
assert (c.EVIDENCE / "final-main-before-audit.stdout.txt").read_text(encoding="utf-8").split()[0] == sha
c.run("final-tag-identity", ["git", "ls-remote", "origin", "refs/tags/v0.4.3", "refs/tags/v0.4.3^{}"])
remote_lines = (c.EVIDENCE / "final-tag-identity.stdout.txt").read_text(encoding="utf-8")
assert result["tag_object_sha"] in remote_lines and sha in remote_lines
subprocess.run(["git", "diff", "--stat", "v0.4.2", "v0.4.3"], cwd=c.ROOT, check=True,
    stdout=(c.EVIDENCE / "v042-to-v043.stat.txt").open("wb"))
subprocess.run(["git", "diff", "--no-ext-diff", "v0.4.2", "v0.4.3", "--", "src", "tests", ".gitattributes", "pyproject.toml", "MANIFEST.in", ".github"], cwd=c.ROOT, check=True,
    stdout=(c.EVIDENCE / "v042-to-v043-code.diff").open("wb"))
dest = c.ROOT / "docs/audits/evidence/2026-10-19-v0.4.3-post-release"
dest.mkdir(parents=True, exist_ok=False)
for p in c.EVIDENCE.iterdir():
    if p.is_file():
        shutil.copy2(p, dest / p.name)
c.save(dest / "evidence-sha256.json", {p.name: c.digest(p) for p in sorted(dest.iterdir()) if p.is_file()})
wheel = next(i for i in result["pypi_files"] if i["packagetype"] == "bdist_wheel")
sdist = next(i for i in result["pypi_files"] if i["packagetype"] == "sdist")
smoke = json.loads((c.EVIDENCE / "clean-pypi-api-smoke.stdout.txt").read_text(encoding="utf-8"))
audit = c.ROOT / "docs/audits/2026-10-19-v0.4.3-release-closeout.md"
audit.write_text(f"""# W0 / v0.4.3 formal release closeout

Date: 2026-10-19 (Asia/Shanghai). **W0_FINAL_VERDICT = RELEASE_COMPLETE**.
Authority: the Owner's current one-time conditional complete-release request.
All required conditions were satisfied before the tag push. DR04-M, other DR
implementation and consumer changes remain unauthorized.

## Immutable release identities

| Item | Verified identity |
| --- | --- |
| Owner-accepted DR04-P main baseline | `9543d03310b25be9963227a2a226366de04276ec` |
| Previous v0.4.2 target | `17af23fe8183f740150dc01dd877473afe3911b7` |
| Release commit / v0.4.3 target | `{sha}` |
| Annotated tag object | `{result['tag_object_sha']}` |
| Version | `0.4.3`, project / installed metadata / runtime agree |
| Actions run | [{result['run_id']}]({result['run_url']}) |
| GitHub Release | [v0.4.3]({result['github_release_url']}) |
| PyPI | [chstockdata 0.4.3](https://pypi.org/project/chstockdata/0.4.3/) |

The release tag was created once and was never moved or rewritten. main was
normally fast-forwarded/pushed to the exact gated release commit. This closeout
is an independent documentation-only follow-up commit; its SHA is available
in Git history and the final handoff. main may advance to that audit commit
without changing any released package code or the tag target.

## Scope and Gate evidence

The [preflight audit](2026-10-19-v0.4.3-preflight.md) and its committed evidence
record 851 passing deterministic tests, zero failures/errors, one optional MCP
test skip and 15 deselected network cases, RH1/compile/version/build/Twine,
independent wheel/sdist/MCP environments and offline public API behavior.
The separate MCP artifact environment successfully constructed the server.
The local dev Python was 3.14.5; official Actions independently used Python 3.12.

The official tag-triggered Actions run completed **successfully**, including
the deterministic Gate, version/tag check, build, artifact validation and
Trusted Publishing jobs. Official test output:

```
{chr(10).join(test_lines)}
```

The downloaded official `dist` workflow artifact exactly matches the two
published PyPI file SHA-256 values. Every published wheel source file matches
the release-tag source (accounting for checkout line endings); every DR04-P
fixture in the published sdist matches its tag bytes.

Changes since the accepted baseline are release metadata/docs/evidence, the
two exact old-version test assertions, and byte-preserving Git attributes for
four frozen JSONL fixtures and this release's audit evidence. The initial
50-failure Gate and minimal metadata/checkout-byte repair are preserved in
the preflight evidence; no business assertion was weakened. The subsequent
auxiliary staged whitespace check used `core.whitespace=cr-at-eol` to handle
the already-present CRLF source lines, and an unchanged-content Git index
refresh cleared stale status flags. Neither changed source/data bytes or
bypassed a required Gate.

Accepted DR04-P implementation/test/fixture/contract identities, FetchResult,
legacy text API, dependencies, price-scale Golden contract, existing CLI/MCP
entries and v0.4.2 historical-opening qualification boundaries are unchanged.
The full previous-tag diff and code/test diff are retained as
`v042-to-v043.stat.txt` and `v042-to-v043-code.diff`.

## Public PyPI artifacts and clean consumer delivery

| File | SHA-256 |
| --- | --- |
| `{wheel['filename']}` | `{wheel['sha256']}` |
| `{sdist['filename']}` | `{sdist['sha256']}` |

Both files were actually fetched from the public PyPI file URLs, with byte
lengths and SHA-256 checked against the version-specific PyPI JSON response.
After confirming upload, the GitHub Release was created from the approved
release notes and its live tag/body/draft/prerelease state was verified.

A new environment installed `chstockdata==0.4.3` from `https://pypi.org/simple`
with pip cache disabled. The pip installation report proves its wheel URL/hash
equals the published artifact; this was not a local wheel or editable install.
Metadata/runtime version checks, `pip check`, existing CLI help and all offline
DR04-P/legacy export and behavior checks passed. Installed package location:
`{smoke['installed_path']}` (outside both source checkouts).
Live market-source requests across all release smoke checks: **0**.

```bash
python -m pip install chstockdata==0.4.3
```

Public additions: `get_sina_daily_fund_flow`, `FundFlowCalendar`,
`FundFlowBudget`, `DailyFundFlowResult`. Supply a qualified covering calendar
and explicit budget; consume lossless CNY-yuan decimal strings, daily statuses,
coverage and response provenance. Raw-zero semantics, source finality,
first-known/revision timing, security applicability and historical PIT remain
UNKNOWN where the accepted contract specifies. COMPLETE is numerical-window
completeness only. See [consumer usage](../dr04-p-daily-fund-flow.md).

## Final handoff and remaining boundaries

- Current phase/step: W0 formal publication and consumer package verification
  complete; this record closes the independent post-release documentation step.
- Original research/untracked normal status and individual file hashes match
  the pre-release snapshot. The release worktree is retained for audit; only
  this audit file and its evidence directory enter the follow-up commit.
- Release Gate verdict: PASS; unresolved in-scope release blockers: NONE.
- Scope changes: only the explicitly authorized metadata/packaging repair.
  No DR04-P redesign, DR04-M, other DR or consumer-repository modification.
- Mishi full-market/S08 and historical PIT qualification: **NOT_PASSED**.
  DR01 status, industry/financial/PIT gaps and DR04-M budget/qualification
  remain consumer blockers; release availability does not resolve them.
- SIOS H01 total-return/as-of, P2 complete historical inputs and H04 return/
  attribution input blockers remain **UNCHANGED**. Consumer pins and strategy
  contracts are unchanged.
- Recommended next action: consumers may install the formal package and use
  the accepted P interface; any consumer qualification or other product phase
  requires its own authorization. No next phase is authorized by this release.

Post-release commands, exits, pip report, actual official/PyPI identities,
workflow job/step results, offline results and evidence hashes are preserved
under [post-release evidence](evidence/2026-10-19-v0.4.3-post-release/).
""", encoding="utf-8")
allowed = {audit.relative_to(c.ROOT).as_posix()}
prefix = dest.relative_to(c.ROOT).as_posix() + "/"
paths = c.git("ls-files", "--others", "--exclude-standard").splitlines()
assert all(p in allowed or p.startswith(prefix) for p in paths)
c.run("stage-post-release-audit", ["git", "add", "--", audit, dest])
staged = c.git("diff", "--cached", "--name-only").splitlines()
assert all(p in allowed or p.startswith(prefix) for p in staged)
for p in dest.iterdir():
    expected = c.digest(p)
    actual = subprocess.check_output(["git", "show", ":" + p.relative_to(c.ROOT).as_posix()], cwd=c.ROOT)
    assert hashlib.sha256(actual).hexdigest() == expected
c.run("post-release-audit-commit", ["git", "commit", "-m", "docs: close W0 v0.4.3 formal release audit"])
final = c.git("rev-parse", "HEAD")
assert not c.git("diff", sha, "--", "src", "tests", "pyproject.toml", ".github", "MANIFEST.in", ".gitattributes")
assert not c.git("status", "--porcelain")
c.run("audit-main-fast-forward", ["git", "merge", "--ff-only", final], cwd=c.ORIGINAL)
c.run("push-audit-main", ["git", "push", "origin", "main:main"], cwd=c.ORIGINAL)
c.run("remote-main-final", ["git", "ls-remote", "origin", "refs/heads/main"])
assert (c.EVIDENCE / "remote-main-final.stdout.txt").read_text(encoding="utf-8").split()[0] == final
assert c.git("rev-parse", "HEAD", cwd=c.ORIGINAL) == final
assert c.git("status", "--porcelain", "--untracked-files=normal", cwd=c.ORIGINAL) == original["status_normal"]
assert not c.git("status", "--porcelain")
result.update(FINAL_MAIN_SHA=final, REMOTE_MAIN_SHA=final, WORKTREE_STATUS="release worktree clean; original untracked research preserved", UNRESOLVED_BLOCKERS="NONE_WITHIN_W0; consumer data gates unchanged")
c.save(c.TEMP / "final-handoff.json", result)
print(json.dumps(result, ensure_ascii=False, indent=2))
