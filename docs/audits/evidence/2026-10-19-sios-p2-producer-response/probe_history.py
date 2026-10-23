"""Bounded, non-production P2 input probe. No credentials or market-data repairs."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[4]
BASE = Path(__file__).resolve().parent
DATES = ("20210104", "20230630", "20251231")
CONTRACTS = {
    "20210104": ("RB2105", "BU2106", "C2105", "CS2105", "PP2105"),
    "20230630": ("RB2310", "BU2309", "C2309", "CS2309", "PP2309"),
    "20251231": ("RB2601", "BU2601", "C2605", "CS2605", "PP2605"),
}


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def dump(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True, encoding="utf-8", stderr=subprocess.DEVNULL).strip()


class PublicOnlyAuth(requests.auth.AuthBase):
    def __call__(self, request):
        return request


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True)
    parser.add_argument("--connectivity-only", action="store_true")
    args = parser.parse_args()
    out = BASE / args.label
    out.mkdir(exist_ok=False)
    keys = ("TUSHARE_TOKEN", "TS_TOKEN", "RQDATAC_USERNAME", "RQDATAC_PASSWORD", "RQDATA_USERNAME", "RQDATA_PASSWORD", "RQDATAC_CONF")
    baseline = {
        "captured_at": now(), "head": git("rev-parse", "HEAD"),
        "status": git("status", "--porcelain=v1", "--untracked-files=all").splitlines(),
        "tracked_diff": git("diff", "--stat"),
        "credential_presence_only": {key: bool(os.getenv(key)) for key in keys},
        "standard_tushare_token_file_exists": (Path.home() / "tk.csv").exists(),
        "versions": {},
        "scope": {"products": ["RB", "BU", "C", "CS", "PP"], "window": ["2020-01-01", "2025-12-31"], "sample_dates": DATES},
    }
    for package in ("requests", "pandas", "akshare", "tushare", "rqdatac", "pyarrow"):
        try:
            baseline["versions"][package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            baseline["versions"][package] = None
    dump(out / "baseline.json", baseline)
    records = []

    def request(name, url, payload=None):
        record = {"name": name, "url": url, "method": "POST" if payload else "GET", "payload": payload, "requested_at": now()}
        try:
            with requests.Session() as session:
                session.auth = PublicOnlyAuth()
                session.headers.update({"User-Agent": "Mozilla/5.0", "Referer": "https://finance.sina.com.cn/" if "sina.com" in url else "https://www.shfe.com.cn/"})
                response = session.post(url, json=payload, timeout=(8, 15)) if payload else session.get(url, timeout=(8, 15))
                body = response.content
                record.update(status_code=response.status_code, content_type=response.headers.get("Content-Type"), bytes=len(body), sha256=digest(body))
                if len(body) <= 3_000_000:
                    filename = name + ".raw"
                    (out / filename).write_bytes(body)
                    record["raw_file"] = filename
                record["outcome"] = "HTTP_SUCCESS_UNVALIDATED" if response.ok else "HTTP_FAILURE"
                return body if response.ok else None
        except requests.RequestException as exc:
            # Never persist exception text: it may contain private proxy details.
            record.update(outcome="REQUEST_FAILURE", exception_type=type(exc).__name__)
            return None
        finally:
            record["completed_at"] = now()
            records.append(record)
            dump(out / "requests.json", records)
            print(json.dumps({k: record[k] for k in ("name", "outcome", "status_code", "exception_type", "bytes") if k in record}), flush=True)

    shfe_dates = ("20210104",) if args.connectivity_only else ("20200102", *DATES)
    for day in shfe_dates:
        request("shfe_" + day, f"https://www.shfe.com.cn/data/tradedata/future/dailydata/kx{day}.dat")
    if not args.connectivity_only:
        for day in DATES:
            request("dce_" + day, "https://www.dce.com.cn/dcereport/publicweb/dailystat/dayQuotes", {
                "contractId": "", "lang": "zh", "optionSeries": "", "statisticsType": "0", "tradeDate": day, "tradeType": "1", "varietyId": "all",
            })
        for day, contracts in CONTRACTS.items():
            for contract in contracts:
                request("sina_" + contract, "https://stock2.finance.sina.com.cn/futures/api/jsonp.php/var%20_V21052021_4_12=/InnerFuturesNewService.getDailyKLine?symbol=" + contract + "&type=2021_04_12")
    dump(out / "capture_result.json", {"completed_at": now(), "request_count": len(records), "http_success_unvalidated": sum(r["outcome"] == "HTTP_SUCCESS_UNVALIDATED" for r in records), "not_a_full_history_export": True})


if __name__ == "__main__":
    main()
