"""Bounded public-source capture for the Owner-authorized H01 work package.

No automatic retry, cookies, paid service, or access-control bypass. Redirects
are separate ledger entries and count against the same request/byte budget.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import requests

ROOT = Path(__file__).resolve().parent
MAX_REQUESTS = 80
MAX_BYTES = 60_000_000


def save_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def capture(label, url):
    if not label.replace("-", "").replace("_", "").isalnum():
        raise ValueError("unsafe label")
    ledger_path = ROOT / "network_ledger.json"
    ledger = json.loads(ledger_path.read_text(encoding="utf-8")) if ledger_path.exists() else {
        "authorization": "Owner explicit approval in this chat, 2026-10-22 Asia/Shanghai",
        "max_http_requests": MAX_REQUESTS, "max_downloaded_bytes": MAX_BYTES,
        "max_retries_per_request": 1, "requests": [],
        "downloaded_bytes_definition": "HTTP response entity bytes, Accept-Encoding identity; headers excluded",
    }
    sources = ROOT / "sources"
    sources.mkdir(exist_ok=True)
    session = requests.Session()
    session.headers.update({"User-Agent": "chstockdata-H01-research/1.0", "Accept-Encoding": "identity",
                            "Referer": "https://fundf10.eastmoney.com/"})
    for hop in range(6):
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password:
            raise ValueError("public HTTP URL required")
        used = sum(item.get("downloaded_bytes", 0) for item in ledger["requests"])
        if len(ledger["requests"]) >= MAX_REQUESTS or used >= MAX_BYTES:
            raise RuntimeError("Owner network budget exhausted")
        if sum(item["url"] == url for item in ledger["requests"]) >= 2:
            raise RuntimeError("maximum one retry for the same request")
        entry = {"id": len(ledger["requests"]) + 1, "label": label, "url": url,
                 "requested_at": datetime.now(timezone.utc).isoformat(),
                 "downloaded_bytes": 0, "status": "started"}
        ledger["requests"].append(entry)
        save_json(ledger_path, ledger)
        body = bytearray()
        redirect = None
        try:
            with session.get(url, timeout=(5, 20), stream=True, allow_redirects=False) as response:
                entry["http_status"] = response.status_code
                entry["content_type"] = response.headers.get("Content-Type")
                entry["encoding"] = response.encoding
                for chunk in response.raw.stream(65536, decode_content=False):
                    remaining = MAX_BYTES - used - len(body)
                    if len(chunk) > remaining:
                        body.extend(chunk[:remaining])
                        entry["status"] = "byte_budget_exhausted"
                        raise RuntimeError("download byte budget exhausted")
                    body.extend(chunk)
                entry["status"] = "success" if 200 <= response.status_code < 300 else "http_error"
                if response.status_code in {301, 302, 303, 307, 308}:
                    redirect = urljoin(url, response.headers["Location"])
                    entry["status"] = "redirect"
        except Exception as error:
            entry["status"] = "request_error" if entry["status"] == "started" else entry["status"]
            entry["error_type"] = type(error).__name__
        finally:
            entry["downloaded_bytes"] = len(body)
            path = sources / f"{entry['id']:03d}-{label}.raw"
            path.write_bytes(body)
            entry["file"] = path.relative_to(ROOT).as_posix()
            entry["sha256"] = hashlib.sha256(body).hexdigest()
            entry["completed_at"] = datetime.now(timezone.utc).isoformat()
            save_json(ledger_path, ledger)
        print(json.dumps(entry, ensure_ascii=False))
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
