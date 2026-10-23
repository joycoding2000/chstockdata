"""One bounded, read-only prerequisite check; never a candidate Gate.

Stores actual bytes and parsed JSON without interpreting absence as normal.
No source/product code is changed and no request is retried automatically.
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

OUT = Path(__file__).resolve().parent / sys.argv[1]
OUT.mkdir(parents=True, exist_ok=False)
PAGE = {
    "isPagination": "true", "pageHelp.pageSize": 25,
    "pageHelp.pageNo": 1, "pageHelp.beginPage": 1,
    "pageHelp.cacheSize": 1, "pageHelp.endPage": 1,
}
REQUESTS = [
    {
        "id": "sse_688432_interval", "method": "GET",
        "url": "https://query.sse.com.cn/commonSoaQuery.do",
        "params": dict(PAGE, sqlId="GW_PL_JYTS_TFPXX", productCode="688432",
                       keyWords="", startStopDate="20260911", endStopDate="20260911"),
        "headers": {"Referer": "https://www.sse.com.cn/disclosure/dealinstruc/suspension/stock/"},
        "actual_query_range": ["2026-09-11", "2026-09-11"],
        "necessary_semantics": "must include intervals starting before queried session",
    },
    {
        "id": "sse_688432_resume_session", "method": "GET",
        "url": "https://query.sse.com.cn/commonSoaQuery.do",
        "params": dict(PAGE, sqlId="GW_PL_JYTS_TFPXX", productCode="688432",
                       keyWords="", startStopDate="20260914", endStopDate="20260914"),
        "headers": {"Referer": "https://www.sse.com.cn/disclosure/dealinstruc/suspension/stock/"},
        "actual_query_range": ["2026-09-14", "2026-09-14"],
        "necessary_semantics": "empty row is not itself explicit resume at 09:30",
    },
    {
        "id": "sse_688432_resume_pdf", "method": "GET",
        "url": "https://static.sse.com.cn/disclosure/listedinfo/announcement/c/new/2026-09-12/688432_20260912_QF57.pdf",
        "necessary_semantics": "actual official PDF body must prove explicit 2026-09-14 resume; HTML cannot",
    },
    {
        "id": "szse_159915_announcements", "method": "POST",
        "url": "https://www.szse.cn/api/disc/announcement/annList",
        "json": {"stock": ["159915"], "channelCode": ["fundinfoNotice_disc"],
                 "seDate": ["2026-08-01", "2026-09-14"], "pageSize": 50, "pageNum": 1},
        "actual_query_range": ["2026-08-01", "2026-09-14"],
        "necessary_semantics": "publication-date window is not certified persistent secondary-market interval coverage for 2026-09-11",
    },
    {
        "id": "szse_159509_announcements_control", "method": "POST",
        "url": "https://www.szse.cn/api/disc/announcement/annList",
        "json": {"stock": ["159509"], "channelCode": ["fundinfoNotice_disc"],
                 "seDate": ["2026-09-10", "2026-09-11"], "pageSize": 50, "pageNum": 1},
        "actual_query_range": ["2026-09-10", "2026-09-11"],
        "necessary_semantics": "positive announcement does not certify persistent interval query semantics",
    },
]


def now():
    return datetime.now(timezone.utc).isoformat()


def main():
    records = []
    session = requests.Session()
    session.trust_env = False
    session.headers.update({"User-Agent": "Mozilla/5.0"})
    for spec in REQUESTS:
        started = time.monotonic()
        record = dict(spec, requested_at=now(), timeout_seconds=[4, 8],
                      automatic_retry=False, tls_verify=True,
                      redirects=False, coverage_qualification="NOT_CERTIFIED")
        try:
            response = session.request(
                spec["method"], spec["url"],
                params=spec.get("params"), json=spec.get("json"),
                headers=spec.get("headers"), timeout=(4, 8),
                allow_redirects=False, verify=True,
            )
            raw = response.content
            raw_name = spec["id"] + ".bin"
            (OUT / raw_name).write_bytes(raw)
            record.update(status="response", http_status=response.status_code,
                          content_type=response.headers.get("Content-Type"),
                          raw_file=raw_name, raw_bytes=len(raw),
                          raw_sha256=hashlib.sha256(raw).hexdigest(),
                          pdf_magic=raw.startswith(b"%PDF-"))
            try:
                payload = response.json()
                parsed_name = spec["id"] + ".parsed.json"
                (OUT / parsed_name).write_text(
                    json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                record["parsed_file"] = parsed_name
                if isinstance(payload, dict):
                    record["top_level_keys"] = sorted(payload)
                    record["page_metadata"] = payload.get("pageHelp")
                    record["announceCount"] = payload.get("announceCount")
                    rows = payload.get("data", payload.get("result"))
                    record["parsed_row_count"] = len(rows) if isinstance(rows, list) else None
                    record["parsed_rows"] = rows
            except (ValueError, TypeError) as exc:
                record["json_parse_error"] = type(exc).__name__
        except requests.RequestException as exc:
            record.update(status="request_error", error_type=type(exc).__name__)
        record.update(retrieved_at=now(), elapsed_seconds=round(time.monotonic() - started, 3))
        records.append(record)
        print(spec["id"], record["status"], "http=" + str(record.get("http_status")),
              "rows=" + str(record.get("parsed_row_count")), flush=True)
        (OUT / "requests.json").write_text(
            json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        # A sandbox/transport failure is not evidence of source absence. Stop
        # immediately so a deliberate escalation can perform the single batch.
        if record["status"] == "request_error":
            session.close()
            return 2
    session.close()
    manifest = {
        "purpose": "bounded prerequisite verification only; no candidate reader/live Gate",
        "request_count": len(records), "maximum_request_count": len(REQUESTS),
        "coverage_qualification": "NOT_CERTIFIED",
        "information_available_at": None, "information_basis": "UNKNOWN",
        "files": [dict(file=p.name, bytes=p.stat().st_size,
                       sha256=hashlib.sha256(p.read_bytes()).hexdigest())
                  for p in sorted(OUT.iterdir()) if p.is_file()],
    }
    (OUT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
