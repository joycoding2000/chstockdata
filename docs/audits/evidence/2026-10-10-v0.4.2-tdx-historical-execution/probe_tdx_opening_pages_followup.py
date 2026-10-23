"""Second finite page sample targeting opening records absent from the latest page."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from mootdx.quotes import Quotes


OUT_DIR = Path(__file__).resolve().parent
JSONL_PATH = OUT_DIR / "tdx_opening_page_followup_responses.jsonl"
MANIFEST_PATH = OUT_DIR / "tdx_opening_page_followup_manifest.json"
SERVER = ("110.41.147.114", 7709)
PAGE_SIZE = 800
REQUESTS = [
    ("510300", "20260911", 1, 3200),
    ("159915", "20260911", 0, 4000),
    ("518880", "20260911", 1, 4000),
    ("513100", "20260911", 1, 2400),
    ("000002", "20151218", 0, 1600),
    ("510300", "20221230", 1, 3200),
    ("510300", "20161230", 1, 1600),
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def main() -> None:
    JSONL_PATH.write_text("", encoding="utf-8")
    client = None
    error_count = 0
    try:
        client = Quotes.factory(
            market="std",
            server=SERVER,
            bestip=False,
            timeout=4,
            heartbeat=False,
            auto_retry=False,
            raise_exception=True,
        )
        for index, (code, date, market, start) in enumerate(REQUESTS, start=1):
            requested_at = utc_now()
            started = time.monotonic()
            try:
                rows = client.client.get_history_transaction_data(
                    market, code, start, PAGE_SIZE, int(date)
                )
                record = {
                    "sequence": index,
                    "requested_at_utc": requested_at,
                    "command": "historical_transaction_0xfb5",
                    "security": code,
                    "market_id": market,
                    "date": date,
                    "server": {"host": SERVER[0], "port": SERVER[1]},
                    "parameters": {"start": start, "count": PAGE_SIZE},
                    "status": "response",
                    "elapsed_seconds": round(time.monotonic() - started, 3),
                    "rows": rows,
                    "row_count": None if rows is None else len(rows),
                }
            except Exception as exc:
                error_count += 1
                record = {
                    "sequence": index,
                    "requested_at_utc": requested_at,
                    "command": "historical_transaction_0xfb5",
                    "security": code,
                    "market_id": market,
                    "date": date,
                    "server": {"host": SERVER[0], "port": SERVER[1]},
                    "parameters": {"start": start, "count": PAGE_SIZE},
                    "status": "request_error",
                    "elapsed_seconds": round(time.monotonic() - started, 3),
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                }
            with JSONL_PATH.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
                handle.write("\n")
                handle.flush()
            print(
                f"{index}/{len(REQUESTS)} {code} {date} start={start}: "
                f"{record['status']} rows={record.get('row_count')} "
                f"elapsed={record['elapsed_seconds']}s",
                flush=True,
            )
            if record["status"] == "request_error":
                break
            if index != len(REQUESTS):
                time.sleep(0.25)
    finally:
        if client is not None:
            client.close()

    manifest = {
        "created_at_utc": utc_now(),
        "source": "mootdx / tdxpy existing repository environment",
        "mootdx_version": importlib.metadata.version("mootdx"),
        "tdxpy_version": importlib.metadata.version("tdxpy"),
        "server": {"host": SERVER[0], "port": SERVER[1]},
        "server_discovery": "disabled; explicit single host",
        "timeout_seconds": 4,
        "automatic_retry": False,
        "heartbeat": False,
        "maximum_query_count": len(REQUESTS),
        "page_size": PAGE_SIZE,
        "completed_query_count": sum(1 for _ in JSONL_PATH.open(encoding="utf-8")),
        "error_count": error_count,
        "response_file": JSONL_PATH.name,
        "response_file_sha256": hashlib.sha256(JSONL_PATH.read_bytes()).hexdigest(),
        "response_file_bytes": JSONL_PATH.stat().st_size,
        "data_note": "Complete parser-returned 0xfb5 rows; time resolution is HH:MM.",
    }
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"manifest={MANIFEST_PATH}", flush=True)


if __name__ == "__main__":
    main()
