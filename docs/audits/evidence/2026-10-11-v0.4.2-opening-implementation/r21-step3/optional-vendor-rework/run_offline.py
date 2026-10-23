"""Simulate optional vendor absence or legacy pin without network or env changes."""
import hashlib
import json
import os
from pathlib import Path
import sys
import types
from datetime import datetime, timezone

OUT = Path(__file__).resolve().parent
W = OUT.parents[2]
SIOS = W / "systematic-investing-os"
stage, vendor = sys.argv[1:3]
if vendor == "missing":
    sys.modules["chstockdata"] = None
elif vendor == "legacy":
    library = types.ModuleType("chstockdata")
    library.__version__ = "0.3.0"
    sys.modules["chstockdata"] = library
elif vendor != "candidate":
    raise ValueError("unknown simulated optional vendor state")

import pytest
node = "tests/qualification/test_live_r21_contract.py::test_actual_candidate_client_is_explicit_and_pin_remains_legacy"
tests = [node] if vendor != "candidate" else ["tests/qualification/test_live_r21_contract.py", "tests/qualification/test_chstockdata_etf_gate.py"]
name = stage + "-" + vendor
argv = [*tests, "-q", "-p", "no:cacheprovider", "--basetemp", str(OUT / (name + "-temp")),
        "--junitxml", str(OUT / (name + ".xml"))]
test = SIOS / "tests/qualification/test_live_r21_contract.py"
record = {"argv": [sys.executable, str(Path(__file__)), stage, vendor], "pytest_argv": argv,
    "cwd": str(Path.cwd()), "vendor_environment": vendor,
    "simulation": "sys.modules missing marker or minimal legacy module; no installed package modification",
    "test_sha256": hashlib.sha256(test.read_bytes()).hexdigest(),
    "environment_overrides": {name: os.environ.get(name) for name in
        ("PYTHONPATH", "PYTHONUTF8", "PYTHONDONTWRITEBYTECODE", "PYTEST_DISABLE_PLUGIN_AUTOLOAD", "SIOS_CHSTOCKDATA_LIVE_QUALIFICATION")},
    "started_at": datetime.now(timezone.utc).isoformat()}
exit_code = pytest.main(argv)
record.update(exit_code=exit_code, finished_at=datetime.now(timezone.utc).isoformat())
(OUT / (name + ".json")).write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
(OUT / (name + ".exit")).write_text(str(exit_code) + "\n", encoding="utf-8")
raise SystemExit(exit_code)
