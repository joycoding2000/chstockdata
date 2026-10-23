"""Replay frozen consumers in isolated copies and record failure sets."""
import hashlib
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

EVIDENCE = Path(__file__).resolve().parent
ROOT = EVIDENCE.parents[3]
WORK = ROOT / "build" / "v042-qualification"
PROFILES = Path("C:/Users/Administrator/.codex/visualizations/2026/10/09/01a11f8a-fc1b-7e30-9e9d-db11e8b44c0d/v042-qualification")
BASELINE = ROOT / "docs/audits/evidence/2026-09-24-v0.4.1-rh3b3/consumer-artifacts/chstockdata-0.3.0-py3-none-any.whl"
CANDIDATE = ROOT / "dist/v042-closeout/chstockdata-0.4.2-py3-none-any.whl"
records = []
ENV = os.environ.copy()
ENV.pop("PYTHONPATH", None)
ENV["PYTHONUTF8"] = "1"

def command(name, argv, cwd=WORK, env=None, allowed=(0,)):
    r = subprocess.run([str(a) for a in argv], cwd=cwd, env=env or ENV, capture_output=True, text=True, encoding="utf-8", errors="replace")
    (EVIDENCE / (name + ".log")).write_text(r.stdout + r.stderr, encoding="utf-8")
    (EVIDENCE / (name + ".exit")).write_text(str(r.returncode) + "\n", encoding="utf-8")
    records.append({"name": name, "argv": [str(a) for a in argv], "cwd": str(cwd), "exit": r.returncode})
    (EVIDENCE / "consumer-commands.json").write_text(json.dumps(records, indent=2), encoding="utf-8")
    print(name, "exit", r.returncode, flush=True)
    if r.returncode not in allowed:
        raise RuntimeError(name + " failed: see log")
    return r

def failures(path):
    tree = ET.parse(path)
    cases = list(tree.iter("testcase"))
    return {"total": len(cases), "failed": sorted(c.attrib.get("classname", "") + "::" + c.attrib["name"] for c in cases if c.find("failure") is not None or c.find("error") is not None), "skipped": sum(c.find("skipped") is not None for c in cases)}

for package in (BASELINE, CANDIDATE):
    assert package.exists()
summary = {"baseline_version": "0.3.0", "candidate_version": "0.4.2", "baseline_sha256": hashlib.sha256(BASELINE.read_bytes()).hexdigest(), "candidate_sha256": hashlib.sha256(CANDIDATE.read_bytes()).hexdigest()}

# SIOS admission is adjusted only in the candidate scratch snapshot.
for variant, artifact, source in (("baseline", BASELINE, "sios-baseline"), ("candidate", CANDIDATE, "sios")):
    target = PROFILES / ("sios-" + variant)
    command("sios-" + variant + "-create", [sys._base_executable, "-m", "venv", target])
    python = target / "Scripts/python.exe"
    command("sios-" + variant + "-install", [python, "-m", "pip", "install", str(artifact) + "[mootdx]", "pytest==9.1.1"])
    command("sios-" + variant + "-identity", [python, "-c", "import chstockdata, importlib.metadata as m; print(chstockdata.__file__); print(m.version('chstockdata')); assert chstockdata.__version__ == m.version('chstockdata') == '" + ("0.3.0" if variant == "baseline" else "0.4.2") + "'"])
    offline_xml = EVIDENCE / ("sios-" + variant + "-offline.xml")
    command("sios-" + variant + "-offline", [python, "-m", "pytest", "tests/", "-q", "--no-header", "--junitxml=" + str(offline_xml)], cwd=WORK / source, allowed=(0, 1))
    summary["sios-" + variant + "-offline"] = failures(offline_xml)
    live_env = ENV.copy()
    live_env["SIOS_CHSTOCKDATA_LIVE_QUALIFICATION"] = "1"
    live_env["CHSTOCKDATA_VIPDOC_HISTORY_DIR"] = str(ROOT / "docs/audits/evidence/2026-09-24-v0.4.1-rh3b3/vipdoc-input")
    # This single affected mandatory case reaches suspension before bars/actions;
    # its historical coverage result cannot be fixed by refreshing local bars.
    live_xml = EVIDENCE / ("sios-" + variant + "-live.xml")
    command("sios-" + variant + "-live", [python, "-m", "pytest", "tests/qualification/test_chstockdata_etf_gate.py::TestLiveEtfQualification::test_live_tradability_adjustment_and_freshness", "-q", "--tb=long", "--junitxml=" + str(live_xml)], cwd=WORK / source, env=live_env, allowed=(0, 1))
    summary["sios-" + variant + "-live"] = failures(live_xml)
    (EVIDENCE / "consumer-results.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

# Preserve the original nine-file TA selection and three SHA-qualified overlays.
ta_py = Path("C:/Users/Administrator/AppData/Local/Programs/Python/Python314/python.exe")
selection = ["tests/test_upstream_adapters.py", "tests/test_trading_calendar.py", "tests/test_f1_public_integration.py", "tests/test_free_adjusted_bars.py", "tests/test_point_in_time_fundamentals.py", "tests/test_performance_optimization.py", "tests/test_p1_listing_status_data_plane.py", "tests/test_phase2_step3_projection.py", "tests/test_phase2_step3_validation.py"]
expression = "not stale_local_falls_back_online_and_labels_source and not stale_local_without_online_keeps_local_flagged and not missing_local_online_fallback_and_total_failure and not empty_or_missing_tree_returns_none"
for variant, artifact in (("baseline", BASELINE), ("candidate", CANDIDATE)):
    target = PROFILES / ("ta-" + variant)
    command("ta-" + variant + "-create", [ta_py, "-m", "venv", target])
    python = target / "Scripts/python.exe"
    command("ta-" + variant + "-install", [python, "-m", "pip", "install", "--no-deps", artifact])
    (target / "Lib/site-packages/consumer_dependencies.pth").write_text("D:/Dev/Projects/TradingAgents-AStock-Private/.venv/Lib/site-packages\n", encoding="utf-8")
    command("ta-" + variant + "-identity", [python, "-c", "import chstockdata, importlib.metadata as m; print(chstockdata.__file__); print(m.version('chstockdata')); assert chstockdata.__version__ == m.version('chstockdata') == '" + ("0.3.0" if variant == "baseline" else "0.4.2") + "'"])
    result_xml = EVIDENCE / ("ta-" + variant + ".xml")
    command("ta-" + variant, [python, "-m", "pytest", "-q", "--tb=long", "-p", "no:cacheprovider", *selection, "-k", expression, "--junitxml=" + str(result_xml)], cwd=WORK / "ta", allowed=(0, 1))
    summary["ta-" + variant] = failures(result_xml)
    (EVIDENCE / "consumer-results.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
print(json.dumps(summary), flush=True)
