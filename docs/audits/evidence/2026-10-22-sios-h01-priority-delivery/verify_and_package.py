"""Run bounded offline checks, preserve results, and archive the actual export."""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[3]
PACKAGE = ROOT / "H01-delivery"


def save(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run(name, args):
    result = subprocess.run(args, cwd=REPO, capture_output=True, encoding="utf-8", errors="replace")
    (ROOT / (name + ".stdout.txt")).write_text(result.stdout, encoding="utf-8")
    (ROOT / (name + ".stderr.txt")).write_text(result.stderr, encoding="utf-8")
    return result


def git(root, *args):
    return subprocess.check_output(["git", "-c", f"safe.directory={root.as_posix()}", "-C", str(root), *args])


def main():
    for path in [*ROOT.glob("*.py"), REPO / "tests/test_sios_h01_delivery.py"]:
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    focused = run("focused", [sys.executable, "-X", "utf8", "-m", "pytest",
        "tests/test_sios_h01_delivery.py", "tests/test_fund_corporate_actions.py",
        "tests/test_vipdoc_price_scale.py", "tests/test_vipdoc_history.py",
        "--basetemp=.h01-task-tmp/final-focused", "--junitxml=" + str(ROOT / "focused.xml"), "-q", "--tb=short"])
    if focused.returncode:
        raise RuntimeError("focused tests failed; preserved diagnostics")
    from chstockdata.corporate_actions import get_fund_corporate_actions
    ledger = json.loads((PACKAGE / "network_ledger.json").read_text(encoding="utf-8"))
    replays = []
    for code in ("513500", "513030", "513520"):
        entry = next(e for e in ledger["requests"] if e["label"] == code + "-fhsp" and e["status"] == "success")
        class Response:
            text = (PACKAGE / entry["file"]).read_text(encoding="utf-8")
            def raise_for_status(self):
                return None
        calls = []
        def request(url, **kwargs):
            calls.append(url)
            if url != "https://fundf10.eastmoney.com/fhsp_" + code + ".html":
                raise AssertionError("offline replay attempted an uncaptured source")
            return Response()
        result = get_fund_corporate_actions(code, "2023-03-09", "2025-09-30", request_get=request)
        assert result["status"] == "normal_empty" and result["coverage"] == "complete" and result["items"] == []
        replays.append({"instrument": code, "calls": calls, "captured_source_sha256": entry["sha256"], "result": result,
                        "qualification": "CURRENT_F10_NORMAL_EMPTY_ONLY_NOT_HISTORICAL_PIT_COVERAGE"})
    save(PACKAGE / "public_api_offline_replay.json", replays)
    build = run("build-final", [sys.executable, "-X", "utf8", str(PACKAGE / "tools/build_delivery.py"), "--package", str(PACKAGE)])
    assert build.returncode == 0, build.stdout + build.stderr
    receiver = run("receipt", [sys.executable, "-X", "utf8", str(PACKAGE / "tools/receive_delivery.py"), str(PACKAGE),
                                "--report", str(PACKAGE / "validation_report.json")])
    report = json.loads((PACKAGE / "validation_report.json").read_text(encoding="utf-8"))
    assert receiver.returncode == 2, (receiver.returncode, receiver.stdout, receiver.stderr)
    assert report["integrity_and_recomputation"] == "PASS" and report["errors"] == []
    # Rebuild once using only package inputs; no source repo reader or network.
    before = (PACKAGE / "manifest.json").read_bytes()
    repeat = run("offline-reproduction", [sys.executable, "-X", "utf8", str(PACKAGE / "tools/build_delivery.py"), "--package", str(PACKAGE)])
    assert repeat.returncode == 0 and (PACKAGE / "manifest.json").read_bytes() == before
    context = json.loads((PACKAGE / "context.json").read_text(encoding="utf-8"))
    protected = {}
    for label, repo in (("producer", REPO), ("consumer", Path("D:/Dev/Projects/systematic-investing-os"))):
        head = git(repo, "rev-parse", "HEAD").decode().strip()
        diff = hashlib.sha256(git(repo, "diff", "HEAD")).hexdigest()
        assert head == context[label]["head"] and diff == context[label]["tracked_diff_sha256"]
        status = git(repo, "status", "--porcelain").decode("utf-8")
        if label == "consumer":
            assert status == context[label]["status"], "SIOS status changed"
            assert hashlib.sha256((repo / "src/systematic_investing/adapters/chstockdata/provider.py").read_bytes()).hexdigest() == context["contract_hashes"]["consumer-provider.py"]
        protected[label] = {"head": head, "tracked_diff_sha256": diff, "status": status}
    archive = ROOT / "H01-delivery.zip"
    files = [p for p in sorted(PACKAGE.rglob("*")) if p.is_file() and "__pycache__" not in p.parts]
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as out:
        for path in files:
            item = zipfile.ZipInfo("H01-delivery/" + path.relative_to(PACKAGE).as_posix(), (1980, 1, 1, 0, 0, 0))
            item.compress_type = zipfile.ZIP_DEFLATED
            out.writestr(item, path.read_bytes())
    with zipfile.ZipFile(archive) as check:
        assert check.testzip() is None
        assert check.read("H01-delivery/manifest.json") == before
    coverage = json.loads((PACKAGE / "coverage_and_unknowns.json").read_text(encoding="utf-8"))
    provenance = json.loads((PACKAGE / "provenance.json").read_text(encoding="utf-8"))
    result = {"verdict": "H01_PARTIAL_DELIVERY_WITH_NAMED_GAPS", "gate": "BLOCKED_WITH_NAMED_GAPS",
              "focused_returncode": focused.returncode, "focused_summary": focused.stdout.strip().splitlines()[-1],
              "receiver_exit_code": receiver.returncode, "receipt_checks": report["checks_executed"],
              "offline_reproduction_manifest_identical": True, "public_api_replays": len(replays),
              "manifest_sha256": report["manifest_sha256"],
              "validation_report_sha256": hashlib.sha256((PACKAGE / "validation_report.json").read_bytes()).hexdigest(),
              "zip_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(), "zip_bytes": archive.stat().st_size,
              "package_files": len(files), "network": provenance["network"], "protected_repositories": protected,
              "required_gaps": coverage["unresolved_required_gaps"], "strategy_backtests_executed": 0,
              "production_files_modified": 0, "git_commit": False, "git_push": False}
    save(ROOT / "completion.json", result)
    print(json.dumps({k:v for k,v in result.items() if k not in {"required_gaps", "protected_repositories", "network"}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
