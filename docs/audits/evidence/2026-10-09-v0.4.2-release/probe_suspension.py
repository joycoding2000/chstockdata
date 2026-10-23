"""Bounded source-semantic probe through the existing throttled transport."""
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from chstockdata import a_stock, suspension

out = Path(__file__).resolve().parent
original = a_stock._em_get
requests = []

def capture(url, *, params=None, **kwargs):
    stamp = datetime.now(timezone.utc).isoformat()
    entry = {"url": url, "params": params, "queried_at": stamp}
    requests.append(entry)
    try:
        response = original(url, params=params, **kwargs)
        entry["http_status"] = response.status_code
        payload = response.json()
        filename = f"raw-{params['filter'].split(chr(39))[1]}-page-{params['pageNumber']}.json"
        raw = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        (out / filename).write_bytes(raw)
        entry["raw_file"] = filename
        entry["sha256"] = hashlib.sha256(raw).hexdigest()
        return response
    except Exception as exc:
        entry["error_type"] = type(exc).__name__
        raise

a_stock._em_get = capture
summary = []
for day in (sys.argv[1:] or ("2015-01-05", "2020-02-03", "2022-12-30", "2026-09-11", "2026-10-09")):
    snapshot = suspension._fetch_suspension_snapshot_uncached(day)
    rows = snapshot["rows"]
    future = [row for row in rows if str(row.get("SUSPEND_START_DATE") or "")[:10] > day]
    normalized = json.dumps(rows, ensure_ascii=False, sort_keys=True).encode("utf-8")
    summary.append({"date": day, "status": snapshot["status"], "reason": snapshot["reason"],
                    "rows": len(rows), "reported_count": snapshot["reported_count"],
                    "pages": snapshot["snapshot_pages"], "rows_sha256": hashlib.sha256(normalized).hexdigest(),
                    "future_start_rows": len(future), "future_start_codes": [r.get("SECURITY_CODE") for r in future]})
    print(json.dumps({k: v for k, v in summary[-1].items() if k != "future_start_codes"}, ensure_ascii=False), flush=True)
(out / ("source-probe-" + sys.argv[1] + ".json" if len(sys.argv) > 1 else "source-probe.json")).write_text(json.dumps({"requests": requests, "summary": summary}, ensure_ascii=False, indent=2), encoding="utf-8")
