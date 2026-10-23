import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tomllib

spec = importlib.util.spec_from_file_location("control", Path(__file__).with_name("w0-v043-control.py"))
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)
attributes = c.ROOT / ".gitattributes"
raw_attributes = attributes.read_text(encoding="utf-8")
for path in ("/docs/audits/evidence/2026-10-19-v0.4.3-release/** -text", "/docs/audits/evidence/2026-10-19-v0.4.3-post-release/** -text"):
    if path not in raw_attributes:
        raw_attributes += path + "\n"
attributes.write_text(raw_attributes, encoding="utf-8")
allowed = {".gitattributes", "README.md", "pyproject.toml", "src/chstockdata/__init__.py",
           "tests/test_delisting_structured.py", "tests/test_fund_corporate_actions.py",
           "docs/releases/v0.4.3.md", "docs/audits/2026-10-19-v0.4.3-preflight.md"}
prefix = "docs/audits/evidence/2026-10-19-v0.4.3-release/"
changed = c.git("diff", "--name-only", c.BASE).splitlines()
untracked = c.git("ls-files", "--others", "--exclude-standard").splitlines()
assert all(p in allowed or p.startswith(prefix) for p in changed + untracked), changed + untracked


def blob(path, rev=c.BASE):
    return subprocess.check_output(["git", "show", rev + ":" + path], cwd=c.ROOT)


def canonical(raw):
    return raw.replace(b"\r\n", b"\n")


protected = c.git("ls-tree", "-r", "--name-only", c.BASE, "--", "src", "tests", "scripts", ".github", "MANIFEST.in", "docs/dr04-p-daily-fund-flow.md").splitlines()
identity = {}
for p in protected:
    before, after = canonical(blob(p)), canonical((c.ROOT / p).read_bytes())
    if p == "src/chstockdata/__init__.py":
        assert after.replace(b'__version__ = "0.4.3"', b'__version__ = "0.4.2"') == before
    elif p in {"tests/test_delisting_structured.py", "tests/test_fund_corporate_actions.py"}:
        assert after.replace(b'__version__ == "0.4.3"', b'__version__ == "0.4.2"').replace(
            b"test_structured_payload_is_minimal_and_version_is_043", b"test_structured_payload_is_minimal_and_version_stays_042").replace(
            b"test_release_version_is_043", b"test_release_version_is_042") == before
    else:
        assert after == before, p
    if "daily_fund_flow" in p or p in ("src/chstockdata/fetch_result.py", "src/chstockdata/vipdoc_history.py", "src/chstockdata/a_stock.py", "docs/dr04-p-daily-fund-flow.md"):
        identity[p] = {"accepted_git_blob_sha256": hashlib.sha256(blob(p)).hexdigest(),
            "candidate_canonical_sha256": hashlib.sha256(after).hexdigest(), "working_file_sha256": c.digest(c.ROOT / p)}
before = tomllib.loads(blob("pyproject.toml").decode("utf-8"))
after = tomllib.loads((c.ROOT / "pyproject.toml").read_text(encoding="utf-8"))
assert after["project"]["version"] == "0.4.3"
after["project"]["version"] = before["project"]["version"]
assert before == after
accepted = json.loads((c.ROOT / "docs/audits/evidence/2026-10-18-dr04-p-owner-acceptance/final-check.json").read_text(encoding="utf-8"))
contract = c.ORIGINAL / "docs/dr04-minimum-consumer-contract-owner-review.md"
assert c.digest(contract) == accepted["contract_sha256"]
for p in ("src/chstockdata/daily_fund_flow.py", "tests/test_daily_fund_flow.py"):
    expected = accepted["code_and_evidence_sha256"][p]
    assert expected in (identity[p]["candidate_canonical_sha256"], identity[p]["working_file_sha256"]), p

commands = {p.stem.removesuffix(".command"): json.loads(p.read_text(encoding="utf-8")) for p in c.EVIDENCE.glob("*.command.json") if not p.name.startswith("initial-")}
required = ["deterministic-tests", "rh1-static", "compile", "version-project", "build", "twine", "mcp-server-build"]
for profile in ("wheel", "sdist", "mcp"):
    required += [f"{profile}-{part}" for part in ("install", "pip-check", "versions", "api-smoke", "mcp-help", "refresh-help")]
assert all(commands[name]["exit_code"] == 0 for name in required)
summary = json.loads((c.EVIDENCE / "test-summary.json").read_text(encoding="utf-8"))
assert summary["failures"] == summary["errors"] == 0
c.save(c.EVIDENCE / "scope-and-identity.json", {"verdict": "PASS", "base_sha": c.BASE,
    "authorized_files": sorted(allowed), "evidence_prefix": prefix, "changed_tracked_files": changed,
    "protected_file_count": len(protected), "identities": identity, "external_contract_sha256": c.digest(contract),
    "dependency_constraints_unchanged": True, "business_and_price_assertions_unchanged": True,
    "accepted_dr04_p_tests_unchanged": True})
diff = subprocess.check_output(["git", "diff", "--no-ext-diff", "v0.4.2", "--", "src", "tests", ".gitattributes", "MANIFEST.in", "pyproject.toml", ".github"], cwd=c.ROOT)
(c.EVIDENCE / "v042-to-candidate-code.diff").write_bytes(diff)
c.save(c.EVIDENCE / "preflight-verdict.json", {"APPROVED_SCOPE_MATCH": "PASS", "VERSION_CONSISTENCY": "PASS",
    "DETERMINISTIC_TESTS": "PASS", "RELEASE_PREFLIGHT": "PASS", "ARTIFACT_VALIDATION": "PASS", "ISOLATED_INSTALL": "PASS",
    "OWNER_RELEASE_AUTHORIZATION": "YES_CONDITIONAL", "required_commands": required, "test_summary": summary,
    "live_source_requests": 0, "pypi_publish": "NOT_STARTED", "tag": "NOT_CREATED"})
text = f"""# W0 / v0.4.3 release preflight

Date: 2026-10-19 (Asia/Shanghai). Gate: **PASS**. The Owner's one-time complete
release authorization permits continued commit/push/tag/Trusted Publishing,
GitHub Release and clean PyPI installation after these gates. This does not
authorize DR04-M, other DR development or consumer changes.

## Baseline and accepted scope

- Original checkout and live SSH remote main: `{c.BASE}`.
- Published v0.4.2 target: `17af23fe8183f740150dc01dd877473afe3911b7`;
  tag object: `fd79e4a22f2e6aff2d7fc831721c09761063ba87`.
- GitHub repository is public. Live preflight observed PyPI latest 0.4.2;
  v0.4.3 PyPI version, remote tag and GitHub Release were absent.
- The isolated candidate uses `codex/w0-v043-release`. Only the explicit
  [whitelist and identity record](evidence/2026-10-19-v0.4.3-release/scope-and-identity.json)
  may be staged. Dependency constraints, existing package scripts, production
  workflow, FetchResult, legacy text API and price-scale contract are unchanged.
- Owner-accepted DR04-P module SHA-256:
  `8b4b4e9e9debd5354d72fe8967d5906138413bd52a2a5faa30afc006a173f5e7`;
  test: `ce20e2c8bc09fa6164e2070ad5dc3c131c415a5dc2cf1d27efe489a9b5e73b63`.
  The frozen external contract hash remains
  `1c7c37b1514032ef08d9714fe8cfa4f722c0f730af1e58608dbc6b45eaffeba1`.

## Initial failure and authorized bounded repair

The initial full run exited 1: 801 passed, 50 failed, 1 skipped, 15 deselected.
Two exact release-version assertions still expected 0.4.2. The other 48 failed
at a frozen JSONL hash assertion: Git Windows checkout had converted LF to CRLF.
All four original Git blobs match the original frozen expected SHA-256 values.
Only the two version assertions/names were updated to 0.4.3; `.gitattributes`
marks these four exact files `-text`, and their original blob bytes were restored
in this isolated checkout. The four Git blob contents and all business/hash
assertions are unchanged. No DR04-P implementation/test/fixture change was made.
The two W0 evidence directories also use `-text` to preserve recorded log hashes
across Git checkout; this changes no runtime or package content.
The initial failure, raw-byte comparison and repair are retained as evidence.

## Fresh release Gate

- Full deterministic suite: **{summary['tests'] - summary['skipped']} passed,
  {summary['failures']} failed, {summary['errors']} errors, {summary['skipped']} skipped,
  15 network cases deselected**. The MCP optional-dependency test skipped in the
  dev+mootdx environment; the required separate MCP artifact environment built
  the real server successfully. Local Python: 3.14.5; the unchanged official
  publish workflow independently runs Python 3.12 before publishing.
- RH1: Ruff 0.16.10, structured paths PASS; 287 visible legacy findings,
  no findings on added lines. Compilation and v0.4.3 project version PASS.
- `python -m build` wheel/sdist and `python -m twine check` PASS.
  The sdist contains every accepted DR04-P fixture with matching bytes;
  the wheel contains the unchanged DR04-P module.
- Independent wheel, sdist and wheel[mcp] installations, `pip check`, metadata/
  runtime version consistency and existing CLI help all PASS, using fresh
  environments outside both source checkouts. MCP server construction PASS.
- Each installed profile passed public DR04-P/legacy exports, signed decimal
  five-day observations, 243-row annual pagination plus first-page anchor,
  raw-zero UNKNOWN semantics and synthetic request-failure handling.
  Real market-source requests: **0**.

Exact command arrays, working directories, environment overrides, exits,
stdout/stderr hashes and JUnit results are under
[`evidence/2026-10-19-v0.4.3-release/`](evidence/2026-10-19-v0.4.3-release/).
See `preflight-verdict.json`, `test-summary.json`, `local-artifacts.json`,
`scope-and-identity.json` and `evidence-sha256.json`. Local artifact hashes are
local build identities; formal Actions/PyPI artifacts will be checked separately.

## Handoff

Phase/step: W0 release preflight completed; formal publication is authorized
conditionally by the Owner's current request. Current HEAD is the accepted base
until the release commit is created; its tree contains only the listed release
metadata/packaging/docs/evidence changes. Original untracked research materials
remain preserved; their original normal status and file hashes are recorded.
No in-scope release blocker remains. Next action: final whitelist check,
release commit, unchanged-remote verification, normal push and annotated
`v0.4.3` tag on that verified commit. Post-release results belong in a separate
audit commit, without moving the tag. Other product phases are not authorized.

Mishi full-market/S08/PIT qualification remains NOT_PASSED; DR04-M remains
NOT_AUTHORIZED. SIOS H01/P2/H04 input gates and all consumer pins are unchanged.
"""
(c.ROOT / "docs/audits/2026-10-19-v0.4.3-preflight.md").write_text(text, encoding="utf-8")
c.save(c.EVIDENCE / "evidence-sha256.json", {p.relative_to(c.EVIDENCE).as_posix(): c.digest(p) for p in sorted(c.EVIDENCE.rglob("*")) if p.is_file() and p.name != "evidence-sha256.json"})
print(json.dumps({"verdict": "PASS", "protected_files": len(protected), "test_summary": summary, "required_commands": len(required)}, indent=2))
