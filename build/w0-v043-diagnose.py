import importlib.util
import hashlib
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

spec = importlib.util.spec_from_file_location("control", Path(__file__).with_name("w0-v043-control.py"))
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)
results = []
for path in ("tdx_history_responses.jsonl", "tdx_opening_page_responses.jsonl", "tdx_opening_page_followup_responses.jsonl", "tdx_opening_page_final_responses.jsonl"):
    rel = "docs/audits/evidence/2026-10-10-v0.4.2-tdx-historical-execution/" + path
    blob = subprocess.check_output(["git", "show", c.BASE + ":" + rel], cwd=c.ROOT)
    raw = (c.ROOT / rel).read_bytes()
    results.append({"path": rel, "blob_sha256": hashlib.sha256(blob).hexdigest(), "checkout_sha256": c.digest(c.ROOT / rel),
        "blob_crlf": blob.count(b"\r\n"), "checkout_crlf": raw.count(b"\r\n"), "only_checkout_crlf_conversion": raw.replace(b"\r\n", b"\n") == blob})
tree = ET.parse(c.EVIDENCE / "deterministic-tests.xml")
failures = [{"case": x.get("classname") + "::" + x.get("name"), "message": x.find("failure").get("message")} for x in tree.iter("testcase") if x.find("failure") is not None]
summary = {"tests": len(list(tree.iter("testcase"))), "failed": len(failures), "skipped": [x.get("classname") + "::" + x.get("name") for x in tree.iter("testcase") if x.find("skipped") is not None]}
c.save(c.EVIDENCE / "initial-failure-analysis.json", {"jsonl_bytes": results, "summary": summary, "failures": failures})
print(json.dumps({"jsonl_bytes": results, "summary": summary}, indent=2))
