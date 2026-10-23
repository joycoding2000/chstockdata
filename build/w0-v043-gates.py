"""Run exactly the existing release checks plus required DR04-P artifact smoke."""
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tarfile
import tempfile
import xml.etree.ElementTree as ET
import zipfile

spec = importlib.util.spec_from_file_location("control", Path(__file__).with_name("w0-v043-control.py"))
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)
dev = c.TEMP / "dev/Scripts/python.exe"
outside = Path(tempfile.mkdtemp(prefix="chstockdata-w0-v043-"))
c.save(c.TEMP / "runtime-paths.json", {"outside": str(outside)})
shutil.copy2(Path(__file__).with_name("w0-v043-artifact-smoke.py"), c.EVIDENCE / "artifact-smoke.py")

c.run("deterministic-tests", [dev, "-m", "pytest", "tests/", "-q", "--no-header", "--basetemp=" + str(outside / "pytest"),
    "--junitxml=" + str(c.EVIDENCE / "deterministic-tests.xml")], extra_env={"PYTHONPATH": str(c.ROOT / "src")})
xml = ET.parse(c.EVIDENCE / "deterministic-tests.xml").getroot()
suites = list(xml.iter("testsuite"))
summary = {k: sum(int(s.get(k, "0")) for s in suites) for k in ("tests", "failures", "errors", "skipped")}
c.save(c.EVIDENCE / "test-summary.json", summary)
print(json.dumps(summary), flush=True)
c.run("rh1-static", [dev, "scripts/check_rh1_static.py"])
c.run("compile", [dev, "-m", "compileall", "-q", "src", "tests"])
c.run("version-project", [dev, "scripts/check_release_version.py", "--tag", "v0.4.3", "--project-root", c.ROOT, "--project-only"])
c.run("build", [dev, "-m", "build"])
dist = sorted((c.ROOT / "dist").iterdir())
assert len(dist) == 2
wheel = next(x for x in dist if x.suffix == ".whl")
sdist = next(x for x in dist if x.name.endswith(".tar.gz"))
c.run("twine", [dev, "-m", "twine", "check", *dist])
with zipfile.ZipFile(wheel) as z:
    assert z.read("chstockdata/daily_fund_flow.py").replace(b"\r\n", b"\n") == (c.ROOT / "src/chstockdata/daily_fund_flow.py").read_bytes().replace(b"\r\n", b"\n")
with tarfile.open(sdist) as t:
    for path in (c.ROOT / "tests/fixtures/daily_fund_flow").iterdir():
        if path.is_file():
            name = "chstockdata-0.4.3/tests/fixtures/daily_fund_flow/" + path.name
            assert t.extractfile(name).read() == path.read_bytes(), name
c.save(c.EVIDENCE / "local-artifacts.json", {p.name: {"sha256": c.digest(p), "bytes": p.stat().st_size} for p in dist})

for profile, artifact in (("wheel", wheel), ("sdist", sdist), ("mcp", wheel)):
    env = outside / profile
    python = env / "Scripts/python.exe"
    c.run(f"{profile}-venv", [dev, "-m", "venv", env])
    target = str(artifact) + ("[mcp]" if profile == "mcp" else "")
    c.run(f"{profile}-install", [python, "-m", "pip", "install", "--index-url", "https://pypi.org/simple", target], cwd=outside)
    c.run(f"{profile}-pip-check", [python, "-m", "pip", "check"], cwd=outside)
    c.run(f"{profile}-versions", [python, "-I", c.ROOT / "scripts/check_release_version.py", "--tag", "v0.4.3", "--project-root", c.ROOT], cwd=outside)
    c.run(f"{profile}-api-smoke", [python, "-I", c.EVIDENCE / "artifact-smoke.py", "--source-root", c.ROOT,
        "--original-root", c.ORIGINAL, "--fixture-root", c.ROOT / "tests/fixtures/daily_fund_flow"], cwd=outside)
    c.run(f"{profile}-mcp-help", [env / "Scripts/chstockdata-mcp.exe", "--help"], cwd=outside)
    c.run(f"{profile}-refresh-help", [env / "Scripts/chstockdata-refresh-vipdoc.exe", "--help"], cwd=outside)
    if profile == "mcp":
        c.run("mcp-server-build", [python, "-I", "-c", "from chstockdata.mcp_server import build_server; assert build_server() is not None; print('MCP server build: PASS')"], cwd=outside)
print("ALL LOCAL RELEASE CHECKS PASSED", flush=True)
