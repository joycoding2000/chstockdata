"""H04 bounded free-source evidence capture; not a production provider."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlsplit

ROOT = Path(__file__).resolve().parent


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def capture(label, url, *, params=None, headers=None):
    import requests

    if not label.replace("-", "").replace("_", "").isalnum():
        raise ValueError("invalid evidence label")
    ledger_path = ROOT / "network_ledger.json"
    ledger = json.loads(ledger_path.read_text(encoding="utf-8")) if ledger_path.exists() else {
        "authorization": "Owner H04 work package; executed 2026-10-23 Asia/Shanghai",
        "max_http_requests": 80, "max_total_bytes": 60000000,
        "max_single_response_bytes": 15000000, "max_retries_per_request": 1,
        "requests": [], "tooling_probe": {"command": "firecrawl --status", "result": "account fetch failed; no source data", "reserved_request_slots": 1, "reserved_bytes": 1000000, "actual_bytes": None},
        "byte_definition": "HTTP response body bytes, identity encoding; headers excluded; opaque tooling probe conservatively reserves 1 MB",
    }
    if ledger.get("closed"):
        raise RuntimeError("H04 source investigation is closed; no further requests")
    # Completed captures are immutable and reused on rerun.
    for old in ledger["requests"]:
        if old["label"] == label and old["url"] == url and old["status"] == "success":
            return old
    (ROOT / "sources").mkdir(exist_ok=True)
    session = requests.Session()
    session.headers.update({"User-Agent": "chstockdata-H04-offline-evidence/1.0", "Accept-Encoding": "identity", "Referer": "https://fundf10.eastmoney.com/"})
    for _ in range(4):
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password:
            raise ValueError("public URL required")
        used = sum(x["downloaded_bytes"] for x in ledger["requests"])
        if len(ledger["requests"]) + 6 >= 80 or used >= 57000000:
            raise RuntimeError("network budget exhausted")
        if sum(x["url"] == url for x in ledger["requests"]) >= 2:
            raise RuntimeError("one retry maximum")
        entry = {"id": len(ledger["requests"]) + 1, "label": label, "url": url,
                 "requested_at": datetime.now(timezone.utc).isoformat(), "downloaded_bytes": 0, "status": "started"}
        ledger["requests"].append(entry)
        save(ledger_path, ledger)
        body, redirect = bytearray(), None
        try:
            with session.get(url, params=params, headers=headers, timeout=(7, 25), stream=True, allow_redirects=False) as response:
                entry.update(http_status=response.status_code, content_type=response.headers.get("Content-Type"), encoding=response.encoding)
                limit = min(15000000, 57000000 - used)
                if int(response.headers.get("Content-Length", "0")) > limit:
                    raise ValueError("declared response exceeds byte limit; not downloaded")
                while len(body) < limit:
                    chunk = response.raw.read(min(65536, limit - len(body)), decode_content=False)
                    if not chunk:
                        break
                    body.extend(chunk)
                if len(body) == limit:
                    entry["status"] = "byte_limit_reached_unqualified"
                else:
                    entry["status"] = "success" if 200 <= response.status_code < 300 else "http_error"
                if response.status_code in {301, 302, 303, 307, 308}:
                    redirect = urljoin(url, response.headers["Location"])
                    entry["status"] = "redirect"
        except Exception as error:
            entry["status"] = "request_error" if entry["status"] == "started" else entry["status"]
            entry["error_type"] = type(error).__name__
        finally:
            path = ROOT / "sources" / f"{entry['id']:03d}-{label}.raw"
            path.write_bytes(body)
            entry.update(downloaded_bytes=len(body), file=path.relative_to(ROOT).as_posix(), sha256=hashlib.sha256(body).hexdigest(), completed_at=datetime.now(timezone.utc).isoformat())
            save(ledger_path, ledger)
        print(json.dumps(entry, ensure_ascii=False), flush=True)
        if redirect is None:
            return entry
        url = redirect
    raise RuntimeError("redirect bound reached")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("label")
    parser.add_argument("url")
    args = parser.parse_args()
    capture(args.label, args.url)
