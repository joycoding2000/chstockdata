"""Bind final results to the one candidate; never manufacture PASS evidence."""
import hashlib
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import run_gate as gate

OUT = gate.OUT
ROOT = gate.ROOT


def result(name, directory=OUT):
    xml = directory / (name + ".xml")
    cases = list(ET.parse(xml).iter("testcase"))
    failed = sorted(c.attrib.get("classname", "") + "::" + c.attrib["name"] for c in cases if c.find("failure") is not None or c.find("error") is not None)
    skipped = sum(c.find("skipped") is not None for c in cases)
    return {"passed": len(cases) - len(failed) - skipped, "failed": failed, "skipped": skipped,
            "xml_sha256": gate.sha(xml.read_bytes()), "exit": int((directory / (name + ".exit")).read_text(encoding="utf-8-sig").strip())}


def git_tree(files):
    # Compute the Git-compatible tree identity from captured bytes. This creates
    # no commit/object and does not stage the user's outstanding work.
    root = {}
    for name in files:
        parts = name.split("/")
        node = root
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        data = (ROOT / name).read_bytes()
        node[parts[-1]] = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).digest()

    def tree(node):
        chunks = []
        for name, value in sorted(node.items(), key=lambda item: (item[0] + ("/" if isinstance(item[1], dict) else "")).encode()):
            directory = isinstance(value, dict)
            mode = b"40000" if directory else b"100644"
            chunks.append(mode + b" " + name.encode() + b"\0" + (tree(value) if directory else value))
        data = b"".join(chunks)
        return hashlib.sha1(b"tree " + str(len(data)).encode() + b"\0" + data).digest()
    return tree(root).hex()


artifacts = json.loads((OUT / "artifacts.json").read_text(encoding="utf-8"))
source = artifacts["source_identity"]
assert gate.sha(gate.WHEEL.read_bytes()) == artifacts["wheel"]["sha256"]
assert gate.sha(gate.SDIST.read_bytes()) == artifacts["sdist"]["sha256"]
assert all(gate.sha((ROOT / name).read_bytes()) == digest for name, digest in source["working_tree_files"].items())
assert gate.source_identity()["package_files"] == source["package_files"]
tree = git_tree(source["working_tree_files"])
protected_var = json.loads((OUT / "frozen-var.json").read_text(encoding="utf-8"))
assert gate.manifest(gate.WORK / "sios/var") == protected_var
consumers = json.loads((OUT / "consumer-identities.json").read_text(encoding="utf-8"))
for consumer, directory in (("sios", gate.WORK / "sios-pristine"), ("ta", gate.WORK / "ta")):
    for name, digest in consumers[consumer]["files"].items():
        if consumer == "ta" and any(overlay["path"] == name for overlay in consumers["ta_overlays"]):
            continue
        assert gate.sha((directory / name).read_bytes()) == digest, name
for overlay in consumers["ta_overlays"]:
    assert gate.sha((gate.WORK / "ta" / overlay["path"]).read_bytes()) == overlay["sha256"]
patch_files = {"src/systematic_investing/adapters/chstockdata/provider.py", "tests/qualification/test_chstockdata_etf_gate.py"}
actual_changes = [name for name, digest in consumers["sios"]["files"].items() if gate.sha((gate.WORK / "sios" / name).read_bytes()) != digest]
assert set(actual_changes) == patch_files
assert gate.sha((OUT / "candidate-only-version-exception.patch").read_bytes()) == consumers["version_exception_sha256"]
gate.save("final-integrity.json", {"candidate_base_commit": source["base_commit"], "candidate_working_tree_content_tree_sha1": tree,
    "tree_definition": "Git-compatible tree of captured tracked and non-ignored untracked source files; excludes this accumulating audit directory; no commit/object written",
    "candidate_files_unchanged_since_build": True, "wheel_sha256": artifacts["wheel"]["sha256"], "sdist_sha256": artifacts["sdist"]["sha256"],
    "source_semantics_included": artifacts["source_semantics_included"], "frozen_var_unchanged": True, "consumer_source_unchanged_except_admission": actual_changes,
    "sios_pristine_adapter_sha256": consumers["sios"]["files"]["src/systematic_investing/adapters/chstockdata/provider.py"],
    "sios_candidate_adapter_sha256": gate.sha((gate.WORK / "sios/src/systematic_investing/adapters/chstockdata/provider.py").read_bytes()),
    "exception_patch_sha256": consumers["version_exception_sha256"]})

tests = {name: result(name) for name in ("package-tests", "sios-provider-contract", "sios-etf-golden-smoke", "sios-offline", "sios-required-live", "ta-candidate")}
baseline_sios = result("sios-baseline-offline", gate.OLD)
baseline_ta = result("ta-baseline", gate.OLD)
ta_compatible = tests["ta-candidate"]["failed"] == baseline_ta["failed"] and tests["ta-candidate"]["passed"] == baseline_ta["passed"]
assert ta_compatible
probe = json.loads((OUT / "etf-exact-probe.json").read_text(encoding="utf-8"))
assert probe["price_parity"] == 4
commands = json.loads((OUT / "commands.json").read_text(encoding="utf-8")) + json.loads((OUT / "package-install-commands.json").read_text(encoding="utf-8"))
mandatory_names = ["static", "compile", "diff-check", "version-project", "build", "twine", "sios-pip-check", "etf-exact-probe", "ta-legacy", "ta-source-binding"]
mandatory_names += [profile + "-" + suffix for profile in ("core", "sdist", "mcp", "baostock") for suffix in ("install", "pip-check", "version", "identity", "exports")]
mandatory_names += [profile + "-" + script for profile in ("core", "sdist") for script in ("chstockdata-mcp", "chstockdata-refresh-vipdoc")]
last = {item["name"]: item for item in commands}
assert all(last[name]["exit"] == 0 for name in mandatory_names)
assert tests["package-tests"]["exit"] == 0
baseline_artifact = ROOT / "docs/audits/evidence/2026-09-24-v0.4.1-rh3b3/consumer-artifacts/chstockdata-0.3.0-py3-none-any.whl"
assert gate.sha(baseline_artifact.read_bytes()) == "be759128fcbe818d7ff782e09ea0b69a5ded06fa7a3a6b9a3ebd3038d5a2e627"
gate.save("qualification-summary.json", {"candidate_base_commit": source["base_commit"], "candidate_dirty": True,
    "candidate_content_tree_sha1": tree, "candidate_manifest_sha256": source["working_tree_manifest_sha256"], "wheel_sha256": artifacts["wheel"]["sha256"], "sdist_sha256": artifacts["sdist"]["sha256"],
    "tests": tests, "etf_exact": probe["price_parity"], "baseline_reuse": {"sios": baseline_sios, "ta": baseline_ta, "baseline_wheel_sha256": gate.sha(baseline_artifact.read_bytes()),
        "basis": "same frozen commits and SHA-qualified TA overlays; SIOS var verified byte-for-byte; baseline wheel unchanged; candidate suites rerun in this task; original baseline logs/JUnit and command records retained",
        "limitations": "TA reuses existing consumer third-party dependency directory via .pth, as in the original baseline; PASS is relative compatibility, not a whole-project all-green claim"},
    "ta_relative_compatibility": ta_compatible, "source_semantics_included": artifacts["source_semantics_included"], "mandatory_package_checks": "PASS",
    "historical_tradability": "FAIL" if any("test_live_tradability_adjustment_and_freshness" in name for name in tests["sios-required-live"]["failed"]) else "INSUFFICIENT_EVIDENCE",
    "release_gate": "FAIL", "decision": "FIX_ONLY", "ready_for_owner_release_review": False})
gate.save("all-commands.json", commands)
print(json.dumps({"tests": tests, "tree": tree, "wheel": artifacts["wheel"]["sha256"], "ta_compatible": ta_compatible}, indent=2))
