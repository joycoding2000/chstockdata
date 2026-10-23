"""Bounded, read-only probe of TDX historical minute and transaction commands."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from mootdx.quotes import Quotes


OUT_DIR = Path(__file__).resolve().parent
JSONL_PATH = OUT_DIR / "tdx_history_responses.jsonl"
MANIFEST_PATH = OUT_DIR / "tdx_history_manifest.json"
SERVER = ("110.41.147.114", 7709)
DELAY_SECONDS = 0.25
TRANSACTION_PAGE_SIZE = 800

# Fixed sample set; this is not a discovery or market-wide scan.
SAMPLES = [
    ("510300", "20260911", 1, "target_etf"),
    ("159915", "20260911", 0, "target_etf"),
    ("518880", "20260911", 1, "target_etf"),
    ("511010", "20260911", 1, "target_etf"),
    ("513100", "20260911", 1, "suspension_control"),
    ("159509", "20260911", 0, "suspension_control"),
    ("688432", "20260831", 1, "suspension_control"),
    ("688432", "20260914", 1, "suspension_control"),
    ("000002", "20151218", 0, "intraday_halt_control"),
    ("000002", "20160104", 0, "suspension_control"),
    ("510300", "20221230", 1, "long_history"),
    ("510300", "20161230", 1, "long_history"),
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write_record(record: dict) -> None:
    with JSONL_PATH.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
        handle.write("\n")
        handle.flush()


def main() -> None:
    JSONL_PATH.write_text("", encoding="utf-8")
    queries = []
    for code, date, market, sample_type in SAMPLES:
        queries.append(("historical_minute_0xfb4", code, date, market, sample_type))
        queries.append(("historical_transaction_0xfb5", code, date, market, sample_type))

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
        for index, (kind, code, date, market, sample_type) in enumerate(queries, start=1):
            started_at = utc_now()
            started = time.monotonic()
            try:
                if kind == "historical_minute_0xfb4":
                    rows = client.client.get_history_minute_time_data(
                        market=market, code=code, date=int(date)
                    )
                else:
                    rows = client.client.get_history_transaction_data(
                        market, code, 0, TRANSACTION_PAGE_SIZE, int(date)
                    )
                record = {
                    "sequence": index,
                    "requested_at_utc": started_at,
                    "command": kind,
                    "security": code,
                    "market_id": market,
                    "date": date,
                    "sample_type": sample_type,
                    "server": {"host": SERVER[0], "port": SERVER[1]},
                    "parameters": (
                        {"start": 0, "count": TRANSACTION_PAGE_SIZE}
                        if "transaction" in kind
                        else {}
                    ),
                    "status": "response",
                    "elapsed_seconds": round(time.monotonic() - started, 3),
                    "rows": rows,
                    "row_count": None if rows is None else len(rows),
                }
            except Exception as exc:  # preserve request failure distinctly from empty data
                error_count += 1
                record = {
                    "sequence": index,
                    "requested_at_utc": started_at,
                    "command": kind,
                    "security": code,
                    "market_id": market,
                    "date": date,
                    "sample_type": sample_type,
                    "server": {"host": SERVER[0], "port": SERVER[1]},
                    "parameters": (
                        {"start": 0, "count": TRANSACTION_PAGE_SIZE}
                        if "transaction" in kind
                        else {}
                    ),
                    "status": "request_error",
                    "elapsed_seconds": round(time.monotonic() - started, 3),
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                }
            write_record(record)
            print(
                f"{index}/{len(queries)} {kind} {code} {date}: "
                f"{record['status']} rows={record.get('row_count')} "
                f"elapsed={record['elapsed_seconds']}s",
                flush=True,
            )
            if record["status"] == "request_error":
                break
            if index != len(queries):
                time.sleep(DELAY_SECONDS)
    finally:
        if client is not None:
            client.close()

    digest = hashlib.sha256(JSONL_PATH.read_bytes()).hexdigest()
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
        "maximum_query_count": len(queries),
        "transaction_page_size": TRANSACTION_PAGE_SIZE,
        "completed_query_count": sum(1 for _ in JSONL_PATH.open(encoding="utf-8")),
        "error_count": error_count,
        "response_file": JSONL_PATH.name,
        "response_file_sha256": digest,
        "response_file_bytes": JSONL_PATH.stat().st_size,
        "data_note": (
            "rows contains complete parser-returned records. The 0xfb4 parser does not "
            "expose minute timestamps; 0xfb5 exposes HH:MM only. No raw TCP payload is captured."
        ),
    }
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"manifest={MANIFEST_PATH}", flush=True)


if __name__ == "__main__":
    main()
