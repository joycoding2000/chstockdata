import importlib.util
import json
from pathlib import Path
import shutil
import subprocess

spec = importlib.util.spec_from_file_location("control", Path(__file__).with_name("w0-v043-control.py"))
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)
for p in list(c.EVIDENCE.glob("deterministic-tests.*")):
    shutil.copy2(p, p.with_name("initial-" + p.name))
for rel, old_name, new_name in (
    ("tests/test_delisting_structured.py", "test_structured_payload_is_minimal_and_version_stays_042", "test_structured_payload_is_minimal_and_version_is_043"),
    ("tests/test_fund_corporate_actions.py", "test_release_version_is_042", "test_release_version_is_043"),
):
    p = c.ROOT / rel
    raw = p.read_bytes()
    assert raw.count(b'assert chstockdata.__version__ == "0.4.2"') == 1
    raw = raw.replace(b'assert chstockdata.__version__ == "0.4.2"', b'assert chstockdata.__version__ == "0.4.3"')
    raw = raw.replace(old_name.encode(), new_name.encode())
    p.write_bytes(raw)
analysis = json.loads((c.EVIDENCE / "initial-failure-analysis.json").read_text(encoding="utf-8"))
paths = [r["path"] for r in analysis["jsonl_bytes"]]
assert not (c.ROOT / ".gitattributes").exists()
(c.ROOT / ".gitattributes").write_text("# Preserve frozen raw evidence bytes used by the release gate and sdist.\n" + "".join(p + " -text\n" for p in paths), encoding="utf-8")
for p in paths:
    original_blob = subprocess.check_output(["git", "show", c.BASE + ":" + p], cwd=c.ROOT)
    (c.ROOT / p).write_bytes(original_blob)
assert not c.git("diff", "--name-only", "--", *paths)
notes = c.ROOT / "docs/releases/v0.4.3.md"
s = notes.read_text(encoding="utf-8")
s = s.replace("are unchanged from Owner acceptance. This release changes only version\nmetadata and delivery documentation/evidence.", "are unchanged from Owner acceptance. Release preparation updates version\nmetadata, its two exact legacy test assertions, delivery documentation/evidence\nand a bounded Git packaging setting: four frozen JSONL evidence files are\nmarked `-text` so Windows checkout preserves their existing SHA-256 bytes.")
notes.write_text(s, encoding="utf-8")
c.save(c.EVIDENCE / "authorized-packaging-fix.json", {"classification": "CONFIRMED_DEFECT", "authorization": "BOUNDED_PACKAGING_FIX_AUTHORIZED",
    "initial_result": "50 failed, 801 passed, 1 skipped, 15 deselected", "old_version_assertions": 2,
    "checkout_hash_failures": 48, "raw_files_restored_from_unchanged_git_blobs": paths,
    "business_assertions_relaxed": False, "dr04_p_implementation_tests_fixtures_contract_changed": False})
print(c.git("diff", "--stat"))
