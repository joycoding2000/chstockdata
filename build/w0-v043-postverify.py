import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
import urllib.request
import zipfile

spec = importlib.util.spec_from_file_location("control", Path(__file__).with_name("w0-v043-control.py"))
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)
pre = c.EVIDENCE
c.EVIDENCE = c.TEMP / "post-release-evidence"
state = json.loads((c.TEMP / "publish-state.json").read_text(encoding="utf-8"))
status = json.loads((c.EVIDENCE / "actions-status.stdout.txt").read_text(encoding="utf-8"))
assert status["status"] == "completed" and status["conclusion"] == "success"
assert status["headSha"] == state["release_sha"] and status["headBranch"] == "v0.4.3"
assert {j["name"] for j in status["jobs"] if j["conclusion"] == "success"} >= {"build", "publish"}
out = Path(tempfile.mkdtemp(prefix="chstockdata-v043-pypi-"))
c.save(c.TEMP / "pypi-runtime-paths.json", {"outside": str(out)})
assets = out / "assets"
assets.mkdir()
with urllib.request.urlopen("https://pypi.org/pypi/chstockdata/0.4.3/json", timeout=30) as response:
    payload = json.load(response)
assert payload["info"]["version"] == "0.4.3"
files = payload["urls"]
assert len(files) == 2 and {f["packagetype"] for f in files} == {"bdist_wheel", "sdist"}
identities = []
for item in files:
    assert item["url"].startswith("https://files.pythonhosted.org/")
    assert not item["yanked"]
    name = item["filename"]
    with urllib.request.urlopen(item["url"], timeout=60) as response:
        raw = response.read()
    assert hashlib.sha256(raw).hexdigest() == item["digests"]["sha256"]
    assert len(raw) == item["size"]
    (assets / name).write_bytes(raw)
    identities.append({"filename": name, "packagetype": item["packagetype"], "url": item["url"],
        "sha256": item["digests"]["sha256"], "bytes": item["size"], "uploaded_at": item["upload_time_iso_8601"]})
c.save(c.EVIDENCE / "pypi-assets.json", {"version": "0.4.3", "json_endpoint": "https://pypi.org/pypi/chstockdata/0.4.3/json", "files": identities})
official = out / "actions-artifacts"
c.run("download-official-actions-dist", ["gh", "run", "download", str(state["run_id"]), "--repo", "joycoding2000/chstockdata", "--name", "dist", "--dir", official])
for item in identities:
    assert c.digest(official / item["filename"]) == item["sha256"]
wheel = next(assets.glob("*.whl"))
sdist = next(assets.glob("*.tar.gz"))
with zipfile.ZipFile(wheel) as z:
    for rel in c.git("ls-tree", "-r", "--name-only", state["release_sha"], "--", "src/chstockdata").splitlines():
        actual = z.read(rel.removeprefix("src/"))
        expected = subprocess.check_output(["git", "show", state["release_sha"] + ":" + rel], cwd=c.ROOT)
        assert actual.replace(b"\r\n", b"\n") == expected.replace(b"\r\n", b"\n"), rel
with tarfile.open(sdist) as t:
    for rel in c.git("ls-tree", "-r", "--name-only", state["release_sha"], "--", "tests/fixtures/daily_fund_flow").splitlines():
        actual = t.extractfile("chstockdata-0.4.3/" + rel).read()
        expected = subprocess.check_output(["git", "show", state["release_sha"] + ":" + rel], cwd=c.ROOT)
        assert actual == expected, rel

lookup = subprocess.run(["gh", "api", "repos/joycoding2000/chstockdata/releases/tags/v0.4.3"], cwd=c.ROOT, capture_output=True, text=True, encoding="utf-8")
release = json.loads(lookup.stdout)
c.save(c.EVIDENCE / "github-release-before-create.json", {"exit_code": lookup.returncode, "response": release})
if lookup.returncode:
    assert str(release.get("status")) == "404"
    c.run("create-github-release", ["gh", "release", "create", "v0.4.3", "--repo", "joycoding2000/chstockdata", "--verify-tag", "--title", "chstockdata v0.4.3", "--notes-file", c.ROOT / "docs/releases/v0.4.3.md"])
c.run("verify-github-release", ["gh", "api", "repos/joycoding2000/chstockdata/releases/tags/v0.4.3"])
release = json.loads((c.EVIDENCE / "verify-github-release.stdout.txt").read_text(encoding="utf-8"))
assert release["tag_name"] == "v0.4.3" and not release["draft"] and not release["prerelease"]
assert release["body"].replace("\r\n", "\n").strip() == (c.ROOT / "docs/releases/v0.4.3.md").read_text(encoding="utf-8").strip()

python = out / "clean/Scripts/python.exe"
dev = c.TEMP / "dev/Scripts/python.exe"
c.run("clean-pypi-venv", [dev, "-m", "venv", out / "clean"], cwd=out)
c.run("clean-pypi-install", [python, "-m", "pip", "install", "--no-cache-dir", "--index-url", "https://pypi.org/simple", "--report", c.EVIDENCE / "pypi-install-report.json", "chstockdata==0.4.3"], cwd=out)
report = json.loads((c.EVIDENCE / "pypi-install-report.json").read_text(encoding="utf-8"))
installed = next(i for i in report["install"] if i["metadata"]["name"] == "chstockdata")
published_wheel = next(i for i in identities if i["packagetype"] == "bdist_wheel")
assert installed["download_info"]["url"] == published_wheel["url"]
assert installed["download_info"]["archive_info"]["hashes"]["sha256"] == published_wheel["sha256"]
c.run("clean-pypi-pip-check", [python, "-m", "pip", "check"], cwd=out)
c.run("clean-pypi-versions", [python, "-I", c.ROOT / "scripts/check_release_version.py", "--tag", "v0.4.3", "--project-root", c.ROOT], cwd=out)
c.run("clean-pypi-api-smoke", [python, "-I", pre / "artifact-smoke.py", "--source-root", c.ROOT, "--original-root", c.ORIGINAL,
    "--fixture-root", c.ROOT / "tests/fixtures/daily_fund_flow"], cwd=out)
for name in ("chstockdata-mcp", "chstockdata-refresh-vipdoc"):
    c.run("clean-pypi-" + name + "-help", [python.parent / (name + ".exe"), "--help"], cwd=out)
c.save(c.EVIDENCE / "post-release-result.json", {"W0_FINAL_VERDICT": "RELEASE_COMPLETE", **state,
    "GITHUB_ACTIONS_BUILD": "SUCCESS", "PYPI_UPLOAD": "SUCCESS", "PYPI_VERSION": "0.4.3", "pypi_files": identities,
    "github_release_url": release["html_url"], "CLEAN_PYPI_INSTALL": "PASS", "PUBLIC_API_SMOKE": "PASS",
    "official_actions_artifacts_match_pypi": True, "published_source_matches_release_tag": True, "live_market_source_requests": 0,
    "CONSUMER_HANDOFF": "python -m pip install chstockdata==0.4.3", "DR04_M_STATUS": "NOT_AUTHORIZED",
    "MISHI_QUALIFICATION": "NOT_PASSED", "SIOS_INPUT_GATES": "UNCHANGED"})
print((c.EVIDENCE / "post-release-result.json").read_text(encoding="utf-8"))
