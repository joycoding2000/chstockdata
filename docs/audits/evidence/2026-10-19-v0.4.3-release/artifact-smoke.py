"""Offline checks executed with isolated, installed release artifacts."""
import argparse
import hashlib
import importlib.metadata as metadata
import json
from pathlib import Path
from unittest.mock import patch

import chstockdata as cs
from chstockdata import daily_fund_flow as ff

p = argparse.ArgumentParser()
p.add_argument("--source-root", type=Path, required=True)
p.add_argument("--original-root", type=Path, required=True)
p.add_argument("--fixture-root", type=Path, required=True)
args = p.parse_args()
location = Path(cs.__file__).resolve()
assert not location.is_relative_to(args.source_root.resolve())
assert not location.is_relative_to(args.original_root.resolve())
assert cs.__version__ == metadata.version("chstockdata") == "0.4.3"
for name in ("get_sina_daily_fund_flow", "FundFlowCalendar", "FundFlowBudget", "DailyFundFlowResult",
             "get_fund_flow", "get_stock_data", "get_realtime_snapshot", "fetch_realtime_quotes",
             "fetch_daily_bars", "fetch_trading_calendar", "fetch_suspension_info", "fetch_delisting_status",
             "fetch_tradability", "FetchAttempt", "FetchMetadata", "FetchResult", "fetch_historical_opening_evidence"):
    assert name in cs.__all__, name
    assert callable(getattr(cs, name)), name
scripts = {e.name for e in metadata.distribution("chstockdata").entry_points if e.group == "console_scripts"}
assert {"chstockdata-mcp", "chstockdata-refresh-vipdoc"} <= scripts
f = args.fixture_root
manifest = json.loads((f / "manifest.json").read_text(encoding="utf-8"))
cal = json.loads((f / "calendar.json").read_text(encoding="utf-8"))
calendar = cs.FundFlowCalendar(trading_days=tuple(cal["days"]), source=cal["source"],
    version=manifest["calendar_sha256"], covered_start=cal["start"], covered_end=cal["end"],
    completed_through=cal["end"], qualified=True)
assert hashlib.sha256((f / "calendar.json").read_bytes()).hexdigest() == manifest["calendar_sha256"]


def fetch(symbol, *, fail=False, **kwargs):
    pages = {r["params"]["page"]: (f / Path(r["raw_file"]).name).read_bytes()
             for r in manifest["requests"] if r["params"]["daima"] == symbol}
    calls = []

    def get(url, **kw):
        assert url == ff.SINA_DAILY_FUND_FLOW_ENDPOINT
        assert kw["allow_redirects"] is False
        calls.append(kw["params"]["page"])
        if fail:
            raise ff.requests.Timeout("offline synthetic timeout")
        return type("Response", (), {"status_code": 200, "content": pages.get(kw["params"]["page"], b"[]")})()

    with patch.object(ff.requests, "get", get):
        result = cs.get_sina_daily_fund_flow(symbol[:2].upper(), symbol[2:], calendar=calendar,
            budget=cs.FundFlowBudget(max_pages=16, max_requests=20, max_seconds=30, retries=0), **kwargs)
    assert isinstance(result, cs.DailyFundFlowResult)
    json.dumps(result.to_dict(), allow_nan=False)
    return result, calls


recent, calls = fetch("sh600000", target_date="2026-10-16")
assert recent.status == "COMPLETE" and recent.coverage["denominator"] == 5
rows = {r["business_date"]: r for r in recent.records}
assert rows["2026-10-16"]["amount"] == "66064341.6800"
assert rows["2026-10-15"]["amount"] == "-8176030.7500"
annual, calls = fetch("sz300750", start_date="2025-10-16", end_date="2026-10-16")
assert annual.status == "COMPLETE" and len(annual.records) == 243
assert len(calls) == 14 and annual.pagination["pages_fetched"] == 13
assert annual.pagination["consistency"] == "OBSERVED_STABLE"
zero, _ = fetch("sh688432", start_date="2026-09-11", end_date="2026-09-11")
assert zero.records[0]["status"] == "RAW_ZERO" and zero.records[0]["zero_semantics"] == "UNKNOWN"
assert zero.coverage["numeric_complete_count"] == 1 and zero.coverage["semantic_usable_count"] == 0
failed, _ = fetch("sh600000", fail=True, target_date="2026-10-16")
assert failed.status == "PARTIAL" and failed.coverage["numeric_complete_count"] == 0
print(json.dumps({"result": "PASS", "version": cs.__version__, "installed_path": str(location),
    "offline_cases": ["public_exports", "entry_points", "lossless_signed_five_days", "annual_pagination_anchor",
                      "zero_semantics_unknown", "request_failure_not_empty_success"],
    "annual_rows": len(annual.records), "annual_http_attempts": len(calls), "live_source_requests": 0}, ensure_ascii=False))
