"""Build and qualify separate release installation profiles; no publishing."""
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

EVIDENCE = Path(__file__).resolve().parent
ROOT = EVIDENCE.parents[3]
WORK = ROOT / "build" / "v042-qualification"
DIST = ROOT / "dist" / "v042-closeout"
DIST.mkdir(parents=True, exist_ok=True)
ENV = os.environ.copy()
ENV.pop("PYTHONPATH", None)
ENV["PYTHONUTF8"] = "1"
PROFILES = Path("C:/Users/Administrator/.codex/visualizations/2026/10/09/01a11f8a-fc1b-7e30-9e9d-db11e8b44c0d/v042-qualification")
results = json.loads((EVIDENCE / "package-commands.json").read_text(encoding="utf-8")) if (EVIDENCE / "package-commands.json").exists() else []

def command(name, argv, cwd=WORK):
    result = subprocess.run([str(a) for a in argv], cwd=cwd, env=ENV, capture_output=True, text=True, encoding="utf-8", errors="replace")
    (EVIDENCE / (name + ".log")).write_text(result.stdout + result.stderr, encoding="utf-8")
    (EVIDENCE / (name + ".exit")).write_text(str(result.returncode) + "\n", encoding="utf-8")
    results.append({"name": name, "argv": [str(a) for a in argv], "cwd": str(cwd), "exit": result.returncode})
    print(name, "exit", result.returncode, flush=True)
    (EVIDENCE / "package-commands.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    if result.returncode:
        raise RuntimeError(name + " failed: see saved log")

if not list(DIST.glob("*.whl")):
    command("environment", [sys.executable, "-m", "pip", "freeze"])
    command("build", [sys.executable, "-m", "build", "--outdir", DIST], cwd=ROOT)
wheel = next(DIST.glob("*.whl"))
sdist = next(DIST.glob("*.tar.gz"))
command("twine", [sys.executable, "-m", "twine", "check", wheel, sdist])
artifacts = [{"file": p.name, "bytes": p.stat().st_size, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in (wheel, sdist)]
(EVIDENCE / "artifacts.json").write_text(json.dumps(artifacts, indent=2), encoding="utf-8")
for profile in ("core", "sdist", "mootdx", "baostock", "mcp"):
    target = PROFILES / profile
    command(profile + "-create", [sys._base_executable, "-m", "venv", target])
    python = target / "Scripts" / "python.exe"
    artifact = sdist if profile == "sdist" else wheel
    spec = str(artifact) + ("[" + profile + "]" if profile in {"mootdx", "baostock", "mcp"} else "")
    command(profile + "-install", [python, "-m", "pip", "install", spec])
    command(profile + "-pip-check", [python, "-m", "pip", "check"])
    command(profile + "-version", [python, ROOT / "scripts" / "check_release_version.py", "--tag", "v0.4.2", "--project-root", ROOT])
    snippet = "import chstockdata, importlib.metadata as m; from pathlib import Path; assert chstockdata.__version__ == m.version('chstockdata') == '0.4.2'; assert 'site-packages' in str(Path(chstockdata.__file__).resolve()); print(chstockdata.__file__); print(m.version('chstockdata')); assert all(callable(getattr(chstockdata, n)) for n in ('fetch_realtime_quotes','fetch_daily_bars','fetch_trading_calendar','fetch_suspension_info','fetch_delisting_status','fetch_tradability'))"
    if profile == "mootdx":
        snippet += "; import mootdx"
    if profile == "baostock":
        snippet += "; import baostock"
    if profile == "mcp":
        snippet += "; from chstockdata.mcp_server import build_server; assert build_server() is not None"
    command(profile + "-imports", [python, "-c", snippet])
    if profile == "core":
        for script in ("chstockdata-mcp", "chstockdata-refresh-vipdoc"):
            command(script + "-help", [target / "Scripts" / (script + ".exe"), "--help"])
print(json.dumps(artifacts), flush=True)
