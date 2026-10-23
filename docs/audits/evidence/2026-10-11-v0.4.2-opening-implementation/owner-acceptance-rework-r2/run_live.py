"""Bounded real Step3 qualification, observational wrappers only; no wheel claim."""
import dataclasses
import hashlib
import importlib.metadata
import json
import os
import faulthandler
from pathlib import Path
import sys
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit

HERE = Path(__file__).resolve().parent
OUT = HERE / "live"
OUT.mkdir(exist_ok=True)
W = Path('C:/Users/Administrator/.codex/visualizations/2026/10/13/01a135d1-a42d-73a3-b19f-dc0968e4ca6c/owner-rework-r2')
SIOS = W / "systematic-investing-os"
CH = W / "wheel"
RUNTIME = Path("C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/Lib/site-packages")

sys.path.insert(0, str(SIOS / "tests/qualification"))
from live_qualification import json_value


def sha(data):
    return hashlib.sha256(data).hexdigest()


def save(path, value):
    path.write_text(json.dumps(json_value(value), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def source_manifest():
    roots = {"chstockdata": Path(__import__("chstockdata").__file__).parent, "sios": SIOS / "src/systematic_investing"}
    files = {name + "/" + path.relative_to(root).as_posix(): sha(path.read_bytes())
             for name, root in roots.items() for path in sorted(root.rglob("*"))
             if path.is_file() and "__pycache__" not in path.parts}
    return {"files": files, "tree_sha256": sha(json.dumps(files, sort_keys=True).encode("utf-8"))}


before = source_manifest()
save(OUT / "source-before.json", before)
qualification_before = {name: sha((SIOS / name).read_bytes()) for name in (
    "tests/qualification/live_qualification.py", "tests/qualification/test_chstockdata_etf_gate.py",
    "tests/qualification/test_live_r21_contract.py", "docs/contracts/historical-opening-execution-r21.md")}
save(OUT / "qualification-source-before.json", qualification_before)
os.environ["SIOS_LIVE_SOURCE_ID"] = before["tree_sha256"]
os.environ["SIOS_LIVE_EVIDENCE_DIR"] = str(OUT / "capabilities")
(OUT / "raw").mkdir(exist_ok=True)

import chstockdata
import zipfile
wheel = W / "chstockdata-0.4.2-py3-none-any.whl"
assert sha(wheel.read_bytes()) == "1dd58350678fbb07d3b545165708d814f93fb94f965dc2da33bad2fab7ff779c"
assert Path(chstockdata.__file__).parent == CH / "chstockdata"
with zipfile.ZipFile(wheel) as archive:
    for name in archive.namelist():
        if name.startswith("chstockdata/") and not name.endswith("/"):
            assert (CH / name).read_bytes() == archive.read(name), name
import requests
from chstockdata import opening_evidence
from chstockdata import a_stock, source_context

save(OUT / "actual-imports.json", {
    "chstockdata_version": chstockdata.__version__, "chstockdata_file": chstockdata.__file__,
    "python": sys.executable, "sys_path": sys.path,
    "versions": {name: importlib.metadata.version(name) for name in
                 ("pytest", "requests", "pandas", "mootdx", "tdxpy", "pypdf")},
    "sios_full_source_sha256": json.loads((HERE/"sios-source-manifest.json").read_text(encoding="utf-8"))["source_manifest_sha256"],
    "sios_runtime_source_sha256": json.loads((HERE/"sios-source-manifest.json").read_text(encoding="utf-8"))["runtime_source_sha256"],
    "sios_patch_sha256": sha((HERE/"sios-source-vs-r1.patch").read_bytes()),
    "frozen_sios_commit": "84fd54fae0740bc06b1d250afa4578be29556956",
    "candidate_artifact": str(W / "chstockdata-0.4.2-py3-none-any.whl"),
    "wheel_sha256": sha((W / "chstockdata-0.4.2-py3-none-any.whl").read_bytes()),
    "known_events_sha256": sha((CH / "chstockdata/opening_known_events.json").read_bytes()),
    "wrappers_sha256": sha(Path(__file__).read_bytes()),
    "opening_reader_sha256": sha(Path(opening_evidence.__file__).read_bytes()),
})

calls = []


def record(kind, request, call):
    index = len(calls) + 1
    entry = {"index": index, "kind": kind, "request": json_value(request),
             "started_at": datetime.now(timezone.utc).isoformat()}
    calls.append(entry)
    try:
        value = call()
        entry["outcome"] = "returned"
        if isinstance(value, bytes):
            raw = value
            path = OUT / "raw" / f"{index:03d}-{kind}.bin"
            path.write_bytes(raw)
        else:
            if hasattr(value, "to_dict") and hasattr(value, "columns"):
                retained = {"columns": list(value.columns), "rows": value.to_dict(orient="records")}
            else:
                retained = json_value(value)
            raw = json.dumps(json_value(retained), ensure_ascii=False, sort_keys=True).encode("utf-8")
            path = OUT / "raw" / f"{index:03d}-{kind}.json"
            path.write_bytes(raw)
        entry.update(raw_path=path.relative_to(OUT).as_posix(), raw_sha256=sha(raw), raw_bytes=len(raw))
        return value
    except Exception as error:
        entry.update(outcome="exception", error_type=type(error).__name__)
        raise
    finally:
        entry["request"] = json_value(request)
        entry["finished_at"] = datetime.now(timezone.utc).isoformat()
        save(OUT / "calls.json", calls)


# Preserve every complete parser-returned minute/page value. The return is unchanged.
original_observe = opening_evidence._observe


def observe(attempts, provider, capability, call, observations, request):
    return original_observe(attempts, provider, capability,
        lambda: record("opening-parser", request, call), observations, request)


opening_evidence._observe = observe

# Retain actual HTTP bytes for official, legacy, and actions queries. Never log headers,
# cookies, proxy configuration, credentials, or full exception strings.
original_request = requests.Session.request


def http(session, method, url, **kwargs):
    split = urlsplit(url)
    public_url = urlunsplit((split.scheme, split.hostname or "", split.path, "", ""))
    def public_parameters(value):
        if isinstance(value, dict):
            return {key: public_parameters(item) for key, item in value.items()
                    if not any(secret in key.lower() for secret in
                               ("token", "password", "credential", "authorization", "cookie", "api_key", "proxy"))}
        if isinstance(value, list):
            return [public_parameters(item) for item in value]
        return value
    identity = {"method": method, "url": public_url,
                **{key: public_parameters(kwargs[key]) for key in ("params", "json", "data", "timeout") if key in kwargs}}
    response_holder = []
    def invoke():
        response = original_request(session, method, url, **kwargs)
        response_holder.append(response)
        identity["http_status"] = response.status_code
        return response.content
    record("http", identity, invoke)
    return response_holder[0]


requests.Session.request = http


def source_call(source_id, operation, function, *, attempt_no=1, fallback_from=None):
    return record("legacy-source", {"source_id": source_id, "operation": operation,
        "attempt_no": attempt_no, "fallback_from": fallback_from}, function)


source_context.install(call_source=source_call)

for name in ("load_vipdoc_daily", "load_trading_calendar", "get_suspension_info",
             "get_fund_corporate_actions", "fetch_historical_opening_evidence"):
    original = getattr(chstockdata, name)
    def wrapper(*args, _name=name, _original=original, **kwargs):
        return record(_name, {"args": args, "kwargs": kwargs}, lambda: _original(*args, **kwargs))
    setattr(chstockdata, name, wrapper)

import pytest
argv = ["tests/qualification/test_chstockdata_etf_gate.py::TestLiveEtfQualification",
        "-q", "-p", "no:cacheprovider", "--basetemp", str(OUT / "live-temp"),
        "--junitxml", str(OUT / "live.xml")]
save(OUT / "live-command.json", {"argv": [sys.executable, str(Path(__file__))],
    "pytest_argv": argv, "cwd": str(Path.cwd()), "source_identity": before["tree_sha256"],
    "environment_overrides": {name: os.environ.get(name) for name in
        ("PYTHONPATH", "PYTHONUTF8", "PYTHONDONTWRITEBYTECODE", "PYTEST_DISABLE_PLUGIN_AUTOLOAD",
         "SIOS_CHSTOCKDATA_LIVE_QUALIFICATION", "CHSTOCKDATA_VIPDOC_HISTORY_DIR", "CHSTOCKDATA_CACHE_DIR",
         "SIOS_LIVE_EVIDENCE_DIR", "SIOS_LIVE_SOURCE_ID")},
    "started_at": datetime.now(timezone.utc).isoformat(),
    "legacy_calendar_policy": "original public current-date staleness and original labelled online fallback retained",
    "bounded_new_source_policy": {"host": opening_evidence.SERVER, "timeout_seconds": 4,
                                  "tdx_pages": 9, "official_pages": 4, "retries": False, "discovery": False}})
faulthandler.dump_traceback_later(600, exit=True)  # Hard outer safety cap; preserve partial evidence on timeout.
exit_code = pytest.main(argv)
faulthandler.cancel_dump_traceback_later()
after = source_manifest()
save(OUT / "source-after.json", after)
qualification_after = {name: sha((SIOS / name).read_bytes()) for name in qualification_before}
save(OUT / "qualification-source-after.json", qualification_after)
save(OUT / "live-result.json", {"exit_code": exit_code, "source_unchanged": before == after,
     "finished_at": datetime.now(timezone.utc).isoformat(), "calls": len(calls)})
(OUT / "live.exit").write_text(str(exit_code) + "\n", encoding="utf-8")
assert before == after, "runtime source changed during qualification"
assert qualification_before == qualification_after, "qualification contract changed during run"
raise SystemExit(exit_code)
