"""Fixed eight-request W5-H evidence probe. No retries, crawling or writes elsewhere."""
import datetime
import hashlib
import json
from pathlib import Path
import time

import requests

BASE = Path(__file__).resolve().parent
SINA = "https://quotes.sina.cn/cn/api/openapi.php/CompanyFinanceService.getFinanceReport2022"
EM = "https://datacenter-web.eastmoney.com/api/data/v1/get"
JOBS = [(f"sina_600518_{source}", SINA, {
    "paperCode": "sh600518", "source": source, "type": "0", "page": "1", "num": "60",
}, ".json") for source in ("lrb", "fzb", "llb")]
for code, year in (("600518", 2025), ("600519", 2025), ("600518", 2020)):
    JOBS.append((f"eastmoney_{code}_{year}", EM, {
        "reportName": "RPT_VALUEANALYSIS_DET", "columns": "ALL",
        "filter": f'(SECURITY_CODE="{code}")(TRADE_DATE>=\'{year}-01-01\')(TRADE_DATE<=\'{year}-12-31\')',
        "pageSize": "500", "pageNumber": "1", "sortColumns": "TRADE_DATE",
        "sortTypes": "-1", "source": "WEB", "client": "WEB",
    }, ".json"))
for label, bulletin in (("original_2017", "4346342"), ("correction_2019", "5335860")):
    JOBS.append((label, "https://vip.stock.finance.sina.com.cn/corp/view/vCB_AllBulletinDetail.php",
                 {"id": bulletin, "stockid": "600518"}, ".html"))

if __name__ == "__main__":
    ledger = BASE / "requests.json"
    assert not ledger.exists(), "One run only: no automatic retry or sample substitution"
    result = {"budget": 8, "no_retries": True, "timeout_seconds": 15,
              "max_body_bytes": 2_000_000, "requests": []}
    session = requests.Session()
    session.headers["User-Agent"] = "Mozilla/5.0"
    for label, url, params, suffix in JOBS:
        entry = {"id": label, "url": url, "params": params, "requested_at":
            datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat()}
        result["requests"].append(entry)
        ledger.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        start = time.monotonic()
        stop = False
        try:
            response = session.get(url, params=params, timeout=15, allow_redirects=False, stream=True)
            entry["http_status"] = response.status_code
            entry["content_type"] = response.headers.get("Content-Type")
            data = bytearray()
            for chunk in response.iter_content(65536):
                data.extend(chunk)
                if len(data) > 2_000_000:
                    raise ValueError("body_budget_exceeded")
            response.close()
            raw = bytes(data)
            path = BASE / (label + suffix)
            path.write_bytes(raw)
            entry.update(file=path.name, bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
            entry["status"] = "response_saved" if response.status_code == 200 else "http_failure"
            if response.status_code in (403, 429):
                stop = True
                entry["stop_reason"] = "source_access_or_rate_limit"
        except Exception as exc:
            entry.update(status="request_failed", error_type=type(exc).__name__)
        entry["elapsed_seconds"] = round(time.monotonic() - start, 3)
        ledger.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(label, entry["status"], entry.get("http_status"), entry.get("bytes"), flush=True)
        if stop:
            break
