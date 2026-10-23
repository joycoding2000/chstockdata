"""Check retained candidate evidence without rebuilding or changing a gate."""
import json
import xml.etree.ElementTree as ET

from probe import OLD, OUT, ROOT, save, sha

results = {}
for name in ("package-tests", "sios-provider-contract", "sios-etf-golden-smoke", "sios-offline", "sios-required-live", "ta-candidate"):
    xml = OLD / (name + ".xml")
    suites = list(ET.parse(xml).getroot().iter("testsuite"))
    counts = {key: sum(int(s.get(key, "0")) for s in suites) for key in ("tests", "failures", "errors", "skipped")}
    results[name] = {"xml_sha256": sha(xml.read_bytes()), "counts": counts, "exit": (OLD / (name + ".exit")).read_text(encoding="utf-8").strip(), "retained_evidence_not_rerun": True}

consumers = json.loads((OLD / "consumer-identities.json").read_text(encoding="utf-8"))
provider_path = "src/systematic_investing/adapters/chstockdata/provider.py"
test_path = "tests/qualification/test_chstockdata_etf_gate.py"
provider_bytes = (ROOT / "build/v042-unified/sios" / provider_path).read_bytes()
test_bytes = (ROOT / "build/v042-unified/sios" / test_path).read_bytes()
original_provider = provider_bytes.replace(b'if version != pinned and version != "0.4.2":', b'if version != pinned:')
original_test = test_bytes.replace(b'assert evidence.provider_version == "0.4.2"', b'assert evidence.provider_version == PINNED_CHSTOCKDATA_VERSION').replace(b'assert chstockdata.__version__ == "0.4.2"', b'assert chstockdata.__version__ == PINNED_CHSTOCKDATA_VERSION')
assert sha(original_provider) == consumers["sios"]["files"][provider_path]
assert sha(original_test) == consumers["sios"]["files"][test_path]
assert sha(provider_bytes) == json.loads((OLD / "final-integrity.json").read_text(encoding="utf-8"))["sios_candidate_adapter_sha256"]
results["sios-business-contract-unchanged"] = True
patches = {}
for line in (OLD / "candidate-only-version-exception.patch").read_text(encoding="utf-8").splitlines():
    if line.startswith("+++ b/"):
        patches[line[6:]] = "sios"
overlays = {r["path"]: r["sha256"] for r in consumers["ta_overlays"]}
for key in ("sios", "ta"):
    files = consumers[key]["files"]
    changes = []
    matched = 0
    for name, digest in files.items():
        actual = sha((ROOT / "build/v042-unified" / key / name).read_bytes())
        if actual == digest or (key == "ta" and actual == overlays.get(name)):
            matched += 1
        else:
            changes.append(name)
    results[key + "-frozen-files"] = {"files": len(files), "matched_original_or_authorized_overlay": matched, "changed": changes}
    if key == "sios":
        assert set(changes) == set(patches), (changes, patches)
    else:
        assert not changes, changes
probe = json.loads((OUT / "sios-history-and-pit.json").read_text(encoding="utf-8"))
assert len(probe["real_requests"]) == 8
assert all(not r["is_success"] and "historical_suspension_unavailable" in r["result"] for r in probe["real_requests"])
results["fresh-history-probe"] = {"requested": 8, "success": 0, "all_fail_closed": True, "wheel_sha256": probe["wheel_sha256"]}
save("verification-summary.json", results)
for key, value in results.items():
    print(key, value.get("counts", value.get("changed", value)) if isinstance(value, dict) else value)
