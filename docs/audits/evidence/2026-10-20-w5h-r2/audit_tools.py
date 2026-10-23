"""Bounded, one-off W5-H-R2 evidence helpers. No production provider changes."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import time

BASE = Path(__file__).resolve().parent
ROOT = Path("D:/Dev/Projects/chstockdata")
EVIDENCE_PREFIX = BASE.relative_to(ROOT).as_posix() + "/"
REPORT = "docs/audits/2026-10-20-w5h-r2-alternative-source-qualification.md"


def stamp():
    return datetime.now(timezone(timedelta(hours=8))).isoformat()


def save(name, value):
    (BASE / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def git(root, *args):
    return subprocess.check_output(["git", "-c", f"safe.directory={root.as_posix()}",
        "-C", str(root), *args], stderr=subprocess.DEVNULL)


def snapshot():
    result = {"captured_at": stamp(), "repositories": {}}
    for name in ("chstockdata", "mishi-radar", "systematic-investing-os"):
        root = ROOT.parent / name
        paths = sorted(set(filter(None, git(root, "ls-files", "-z", "-c", "-o",
            "--exclude-standard").decode("utf-8").split("\0"))))
        hashes = {}
        for path in paths:
            if name == "chstockdata" and path.startswith(EVIDENCE_PREFIX):
                continue
            local = root / path
            if local.is_file():
                hashes[path] = hashlib.sha256(local.read_bytes()).hexdigest()
        result["repositories"][name] = {
            "head": git(root, "rev-parse", "HEAD").decode().strip(),
            "status": git(root, "status", "--porcelain=v1", "--untracked-files=normal").decode("utf-8"),
            "diff_sha256": hashlib.sha256(git(root, "diff", "HEAD", "--binary")).hexdigest(),
            "index_sha256": hashlib.sha256(git(root, "diff", "--cached", "--binary")).hexdigest(),
            "files": hashes,
        }
    return result


def initialize():
    assert not (BASE / "before.json").exists()
    before = snapshot()
    save("before.json", before)
    print({k: {"head": v["head"], "files": len(v["files"])} for k, v in before["repositories"].items()})


class Probe:
    """Serial source requests routed through the existing optional source hook."""
    def __init__(self):
        import requests
        self.session = requests.Session()
        self.session.trust_env = False
        self.session.headers["User-Agent"] = "Mozilla/5.0"
        self.ledger_path = BASE / "requests.json"
        self.ledger = json.loads(self.ledger_path.read_text(encoding="utf-8")) if self.ledger_path.exists() else {
            "started_at": stamp(), "max_http_requests": 28, "minimum_after_finish_seconds": 3,
            "timeout_seconds": 15, "automatic_retries": 0, "redirects": False,
            "requests": [], "blocked_sources": [],
        }
        from chstockdata import source_context
        self.source_context = source_context
        self.ledger["host_source_hook_installed"] = source_context.get_source_execution_context() is not None

    def get(self, label, source, url, params=None, max_bytes=4_000_000, headers=None, method="GET"):
        assert len(self.ledger["requests"]) < 28
        assert not any(x["id"] == label for x in self.ledger["requests"]), "No retry of recorded request"
        if source in self.ledger["blocked_sources"]:
            print(label, "SKIPPED_SOURCE_STOP", flush=True)
            return None
        prior = [x for x in self.ledger["requests"] if x["source"] == source]
        if prior:
            last = datetime.fromisoformat(prior[-1]["finished_at"])
            wait = 3 - (datetime.now(last.tzinfo) - last).total_seconds()
            if wait > 0:
                time.sleep(wait)
        entry = {"id": label, "source": source, "url": url, "params": params, "method": method,
                 "max_bytes": max_bytes, "requested_at": stamp()}
        self.ledger["requests"].append(entry)
        self.flush()
        content = None
        try:
            def request():
                return self.session.request(method, url, params=params, timeout=(10, 15),
                    allow_redirects=False, stream=True, headers=headers)
            response = self.source_context.call_source(source, "w5h_r2_readonly", request, attempt_no=1)
            entry.update(http_status=response.status_code,
                content_type=response.headers.get("Content-Type"),
                content_length=response.headers.get("Content-Length"),
                location=response.headers.get("Location"))
            with response:
                body = bytearray()
                for chunk in response.iter_content(65536):
                    body.extend(chunk)
                    if len(body) > max_bytes:
                        raise ValueError("response_body_budget_exceeded")
                content = bytes(body)
            path = BASE / (label + ".raw")
            path.write_bytes(content)
            entry.update(file=path.name, bytes=len(content), sha256=hashlib.sha256(content).hexdigest(),
                status="response_saved" if response.status_code == 200 else "http_failure")
            if response.status_code in (401, 403, 429):
                self.ledger["blocked_sources"].append(source)
                entry["stop_reason"] = "access_or_rate_limit"
        except Exception as exc:
            entry.update(status="request_failed", error_type=type(exc).__name__)
            if isinstance(exc, ValueError):
                entry["failure_detail"] = "response_body_budget_exceeded"
            self.ledger["blocked_sources"].append(source)
        entry["finished_at"] = stamp()
        self.flush()
        print(label, entry["status"], entry.get("http_status"), entry.get("bytes"), flush=True)
        return content if entry["status"] == "response_saved" else None

    def flush(self):
        save("requests.json", self.ledger)


if __name__ == "__main__":
    initialize()
