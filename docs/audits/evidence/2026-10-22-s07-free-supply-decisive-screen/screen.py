"""Bounded research evidence only; never imported by the production package.

Network operations are explicit, serial, pre-registered, and never run on import.
Replaying analysis reads saved bytes and does not issue network requests.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[3]
TZ = timezone(timedelta(hours=8))
LIMITS = {"requests": 120, "total_bytes": 100_000_000,
          "single_bytes": 20_000_000, "retries_per_request": 1}


def now():
    return datetime.now(TZ).isoformat(timespec="microseconds")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def save(name, obj):
    (BASE / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load(name):
    return json.loads((BASE / name).read_text(encoding="utf-8"))


def git(*args):
    return subprocess.check_output(["git", "-C", str(ROOT), *args])


def initialize():
    assert not (BASE / "registration.json").exists(), "Do not overwrite registration"
    save("registration.json", {
        "task": "S07_FREE_SUPPLY_DECISIVE_SCREEN", "registered_at": now(),
        "owner_network_budget": "Explicitly authorized in this chat: 授权上述预算",
        "limits": LIMITS, "automatic_retries": 0, "redirects": False,
        "free_only": True, "production_changes": False,
        "deep_financial_extraction_new_securities": 0,
        "controls": ["SH:600519", "SZ:000002"],
        "old_regression_only": {"security": "SH:600518", "date": "2020-01-09"},
        "calendar_rule": "Latest completed SH/SZ session at observation time, 252 NAV sessions; 65 warmup; no stale-cache substitution",
        "pe_date_selection_before_valuation": [
            "s-1 and s; e-1 and e",
            "2025Q3 actual disclosure: prior market close and first permissible close after date-only disclosure",
            "2025FY actual disclosure: same rule; if unverified, use preregistered calendar-near quarter/year-end controls, label NOT_DISCLOSURE_VERIFIED"],
        "pe_checks": ["specified business day", "parent TTM denominator", "historical shares/cap",
                      "input available by T", "revision policy and vintage", "S07 compatibility"],
        "boundary_selection": {
            "listing": "earliest verified listing in actual s..e; tie by exchange:ticker",
            "exit": "earliest verified delisting in actual s..e; tie by exchange:ticker",
            "industry": "earliest verifiable effective migration in actual s..e; tie by exchange:ticker; UNKNOWN if no complete event source"},
        "source_routes": ["existing Sina index calendar", "existing Eastmoney daily valuations and disclosure schedule",
                          "existing Baidu TTM", "official SSE/SZSE current and terminated security lists",
                          "official/free industry classification evidence; existing local identity and VIPDOC"],
        "route_stop": "403/401/429 or explicit access restriction stops that source path; no bypass. Missing vintage stops PIT qualification, not other independent routes.",
        "no_full_market_financial_download_or_reconstruction": True})
    save("before.json", {"captured_at": now(), "head": git("rev-parse", "HEAD").decode().strip(),
         "status": git("status", "--porcelain=v1", "--untracked-files=normal").decode("utf-8"),
         "tracked_diff_sha256": digest(git("diff", "HEAD", "--binary")),
         "index_diff_sha256": digest(git("diff", "--cached", "--binary"))})
    save("requests.json", {"limits": LIMITS, "requests": [], "blocked_hosts": [], "bytes_read": 0})


class Probe:
    def __init__(self):
        import requests  # Optional network dependency, only used on the explicit probe path.
        self.session = requests.Session()
        self.session.trust_env = False  # Same direct-source mode as prior repository qualifications.
        self.session.headers.update({"User-Agent": "Mozilla/5.0", "Accept-Encoding": "identity"})
        self.ledger = load("requests.json")

    def get(self, label, url, params=None, headers=None, max_bytes=5_000_000, retry_of=None, method="GET"):
        """One attempt; persist budget reservation before sending any bytes."""
        plan_path = BASE / ("plan-" + label + ".json")
        assert not plan_path.exists(), "Each identity is registered once; explicit retry identities required"
        host = urlsplit(url).hostname
        if host in self.ledger["blocked_hosts"]:
            skips = load("skipped-routes.json") if (BASE / "skipped-routes.json").exists() else []
            skips.append({"id": label, "host": host, "reason": "STOPPED_ACCESS_RESTRICTION", "at": now()})
            save("skipped-routes.json", skips)
            print(label, "SKIPPED_STOPPED_SOURCE", flush=True)
            return None
        assert len(self.ledger["requests"]) < LIMITS["requests"], "Request budget exhausted"
        assert 0 < max_bytes <= LIMITS["single_bytes"]
        assert self.ledger["bytes_read"] + max_bytes <= LIMITS["total_bytes"], "Insufficient byte reservation"
        if retry_of:
            original = next(x for x in self.ledger["requests"] if x["id"] == retry_of)
            assert original["status"] in ("REQUEST_FAILED", "HTTP_FAILURE")
            assert original["url"] == url and original["params"] == params
            assert not any(x["retry_of"] == retry_of for x in self.ledger["requests"])
        request = {"id": label, "url": url, "params": params, "max_bytes": max_bytes,
                   "registered_at": now(), "method": method, "retry_of": retry_of}
        save(plan_path.name, request)
        entry = dict(request, status="RESERVED", bytes=0)
        self.ledger["requests"].append(entry)
        save("requests.json", self.ledger)
        prior = [x for x in self.ledger["requests"][:-1] if urlsplit(x["url"]).hostname == host]
        if prior:
            wait = 2 - (datetime.now(TZ) - datetime.fromisoformat(prior[-1]["finished_at"])).total_seconds()
            if wait > 0:
                time.sleep(wait)
        entry["started_at"] = now()
        path = BASE / (label + ".raw")
        try:
            with self.session.request(method, url, params=params, headers=headers, timeout=(10, 20),
                                      stream=True, allow_redirects=False) as response:
                entry.update(http_status=response.status_code,
                             content_type=response.headers.get("Content-Type"),
                             declared_length=response.headers.get("Content-Length"),
                             server_date=response.headers.get("Date"))
                # Uncompressed transfer bytes are counted as read, including failed/partial responses.
                with path.open("wb") as output:
                    while entry["bytes"] < max_bytes:
                        chunk = response.raw.read(min(65536, max_bytes - entry["bytes"]), decode_content=False)
                        if not chunk:
                            break
                        output.write(chunk)
                        entry["bytes"] += len(chunk)
                        self.ledger["bytes_read"] += len(chunk)
                        save("requests.json", self.ledger)
                entry["status"] = "RESPONSE_SAVED" if response.status_code == 200 else "HTTP_FAILURE"
                if entry["bytes"] == max_bytes:
                    entry["status"] = "BODY_LIMIT_REACHED_UNQUALIFIED"
                if response.status_code in (401, 403, 429):
                    self.ledger["blocked_hosts"].append(host)
                    entry["stop_reason"] = "ACCESS_RESTRICTION"
                if response.status_code == 200 and path.stat().st_size < 10000:
                    try:
                        business = json.loads(path.read_bytes())
                        if isinstance(business, dict) and business.get("resultcode") in (401, 403, 429):
                            entry.update(status="BUSINESS_ACCESS_RESTRICTION", stop_reason="ACCESS_RESTRICTION",
                                         business_code=business["resultcode"])
                            self.ledger["blocked_hosts"].append(host)
                    except (ValueError, UnicodeError):
                        pass
                if response.is_redirect:
                    entry["location"] = response.headers.get("Location")
        except Exception as exc:
            entry.update(status="REQUEST_FAILED", error_type=type(exc).__name__)
            # Preserve diagnostics without printing URLs, proxy credentials, or request internals.
            chain, pending = [], [exc]
            for _ in range(8):
                if not pending:
                    break
                cause = pending.pop()
                chain.append({"type": type(cause).__name__, "errno": getattr(cause, "errno", None),
                              "winerror": getattr(cause, "winerror", None)})
                pending.extend(x for x in getattr(cause, "args", ()) if isinstance(x, BaseException))
                for key in ("reason", "__cause__"):
                    value = getattr(cause, key, None)
                    if isinstance(value, BaseException):
                        pending.append(value)
            entry["exception_chain"] = chain
        if path.exists():
            entry.update(file=path.name, sha256=digest(path.read_bytes()))
        entry["finished_at"] = now()
        save("requests.json", self.ledger)
        print(label, entry["status"], entry.get("http_status"), entry["bytes"], flush=True)
        return entry


def calendar_probes(retry=False):
    p = Probe()
    for market in ("sh000001", "sz399001"):
        label = "calendar-" + market
        p.get(label + ("-retry" if retry else ""),
              "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData",
              {"symbol": market, "scale": "240", "ma": "no", "datalen": 1023},
              retry_of=label if retry else None)
    p.get("sse-calendar-page" + ("-retry" if retry else ""),
          "https://www.sse.com.cn/services/tradingservice/tradingcalendar/",
          retry_of="sse-calendar-page" if retry else None)


def discovery_probes():
    p = Probe()
    for code in ("600519", "000002"):
        p.get("schedule-" + code, "https://datacenter-web.eastmoney.com/api/data/v1/get",
              {"reportName": "RPT_PUBLIC_BS_APPOIN", "columns": "ALL",
               "filter": f'(SECURITY_CODE="{code}")', "pageSize": 40, "pageNumber": 1,
               "sortColumns": "REPORT_DATE", "sortTypes": "-1", "source": "WEB", "client": "WEB"})
    p.get("em-valuation-method-page", "https://data.eastmoney.com/gzfx/detail/600519.html")
    for stock_type in ("1", "8"):
        p.get("sse-current-" + stock_type, "https://query.sse.com.cn/sseQuery/commonQuery.do",
              {"STOCK_TYPE": stock_type, "REG_PROVINCE": "", "CSRC_CODE": "", "STOCK_CODE": "",
               "sqlId": "COMMON_SSE_CP_GPJCTPZ_GPLB_GP_L", "COMPANY_STATUS": "2,4,5,7,8", "type": "inParams",
               "isPagination": "true", "pageHelp.cacheSize": 1, "pageHelp.beginPage": 1,
               "pageHelp.pageSize": 10000, "pageHelp.pageNo": 1, "pageHelp.endPage": 1},
              headers={"Referer": "https://www.sse.com.cn/assortment/stock/list/share/"}, max_bytes=10_000_000)
    p.get("sse-delisted", "https://query.sse.com.cn/commonQuery.do",
          {"sqlId": "COMMON_SSE_CP_GPJCTPZ_GPLB_GP_L", "isPagination": "true", "STOCK_CODE": "",
           "CSRC_CODE": "", "REG_PROVINCE": "", "STOCK_TYPE": "1,8", "COMPANY_STATUS": "3", "type": "inParams",
           "pageHelp.cacheSize": 1, "pageHelp.beginPage": 1, "pageHelp.pageSize": 500,
           "pageHelp.pageNo": 1, "pageHelp.endPage": 1}, headers={"Referer": "https://www.sse.com.cn/"})
    for label, catalog, tab in (("szse-current", "1110", "tab1"), ("szse-delisted", "1793_ssgs", "tab2")):
        p.get(label, "https://www.szse.cn/api/report/ShowReport",
              {"SHOWTYPE": "xlsx", "CATALOGID": catalog, "TABKEY": tab, "random": "0.6935816432433362"},
              headers={"Referer": "https://www.szse.cn/market/product/stock/list/index.html"})
    for doc in ("valuationDaily", "stockIndustry", "stockBasic", "allStock"):
        p.get("baostock-doc-" + doc, "https://www.baostock.com/helpdocs/api/markdown/" + doc + ".md")
    # Public documentation only. Do not generate encrypted request keys or acquire new credentials.
    p.get("cninfo-industry-doc", "https://webapi.cninfo.com.cn/api/stock/p_stock2110",
          {"scode": "", "sdate": load("calendar.json")["s"], "edate": load("calendar.json")["e"]})


def pe_probes():
    c = load("calendar.json")
    plan = {"registered_at": now(), "calendar_sha256": digest((BASE / "calendar.json").read_bytes()),
            "cases": [], "financial_pdfs": 0, "new_deep_financial_securities": 0}
    for code in ("600519", "000002"):
        dates = {c["s_minus_1"]: "first signal", c["s"]: "window start",
                 c["nav_dates"][-2]: "window end vicinity", c["e"]: "window end"}
        rows = json.loads((BASE / ("schedule-" + code + ".raw")).read_bytes())["result"]["data"]
        disclosures = []
        for period in ("2025-09-30", "2025-12-31"):
            row = next(x for x in rows if x["REPORT_DATE"][:10] == period)
            published = row["ACTUAL_PUBLISH_DATE"][:10]
            before = max(d for d in c["all_observed_dates"] if d <= published)
            after = min(d for d in c["all_observed_dates"] if d > published)
            dates[before] = period + " disclosure date-only boundary; not yet permissible close"
            dates[after] = period + " first permissible close after date-only disclosure"
            disclosures.append({"report_period": period, "reported_actual_publish_date": published,
                                "date_precision": "DATE_ONLY_AGGREGATOR_NOT_ORIGINAL_NOTICE",
                                "before": before, "after": after})
        plan["cases"].append({"security": ("SH:" if code == "600519" else "SZ:") + code,
                              "dates": dict(sorted(dates.items())), "disclosures": disclosures,
                              "expected_checks": load("registration.json")["pe_checks"]})
    assert not (BASE / "pe-controls.json").exists()
    save("pe-controls.json", plan)  # Exact securities and dates fixed before viewing PE results.
    p = Probe()
    # Retroactively recognize the explicit business restriction from discovery; never retry that host.
    for x in p.ledger["requests"]:
        if x["id"] == "cninfo-industry-doc" and x.get("file"):
            j = json.loads((BASE / x["file"]).read_bytes())
            if j.get("resultcode") == 401:
                x.update(status="BUSINESS_ACCESS_RESTRICTION", stop_reason="ACCESS_RESTRICTION", business_code=401)
                p.ledger["blocked_hosts"] = sorted(set(p.ledger["blocked_hosts"] + ["webapi.cninfo.com.cn"]))
    save("requests.json", p.ledger)
    for case in plan["cases"]:
        code = case["security"][3:]
        p.get("pe-em-" + code, "https://datacenter-web.eastmoney.com/api/data/v1/get",
              {"reportName": "RPT_VALUEANALYSIS_DET", "columns": "ALL",
               "filter": f'(SECURITY_CODE="{code}")(TRADE_DATE>=\'{c["s_minus_1"]}\')(TRADE_DATE<=\'{c["e"]}\')',
               "pageSize": 1000, "pageNumber": 1, "sortColumns": "TRADE_DATE", "sortTypes": "1",
               "source": "WEB", "client": "WEB"})
        p.get("pe-baidu-" + code, "https://finance.pae.baidu.com/vapi/v1/openapi",
              {"openapi": "1", "dspName": "iphone", "tn": "tangram", "client": "app",
               "query": "市盈率(TTM)", "code": code, "word": "", "resource_id": "51171", "market": "ab",
               "tag": "市盈率(TTM)", "chart_select": "近一年", "industry_select": "", "skip_industry": "1",
               "finClientType": "pc"})
    p.get("em-valuation-method-js", "https://data.eastmoney.com/newstatic/js/gzfx/detail.js")


def route_corrections():
    p = Probe()
    # The first API returned a successful empty result. Prior preserved evidence identifies
    # the actual existing canonical route, rather than a new provider or an auth workaround.
    for code in ("600519", "000002"):
        original = next(x for x in p.ledger["requests"] if x["id"] == "pe-baidu-" + code)
        p.get("pe-baidu-canonical-" + code, "https://finance.baidu.com/opendata", original["params"])
    # Preserved 2026-10-20 documentation ledger shows this read-only endpoint requires POST.
    for doc in ("valuationDaily", "stockIndustry", "stockBasic", "allStock"):
        p.get("baostock-doc-" + doc + "-post", "https://www.baostock.com/helpdocs/api/markdown/" + doc + ".md",
              method="POST", retry_of="baostock-doc-" + doc)


def control_financial():
    # SZ:000002 is already one of the prior six financial controls (F2 1216869640),
    # so this adds zero securities for deep financial extraction. One current NP table
    # only, no PDF/OCF/equity extraction and no reconstruction/provider implementation.
    prior = json.loads((ROOT / "docs/audits/evidence/2026-10-20-w5h-r2/requests.json").read_text(encoding="utf-8"))
    original = next(x for x in prior["requests"] if x["id"] == "ths_600518_benefit")
    params = dict(original["params"], code="000002", market="33")
    Probe().get("ths-000002-benefit", original["url"], params)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["init", "calendar", "calendar-retry", "discovery", "pe", "corrections", "control-financial"])
    args = parser.parse_args()
    if args.action == "init":
        initialize()
    elif args.action == "calendar":
        calendar_probes()
    elif args.action == "calendar-retry":
        calendar_probes(retry=True)
    elif args.action == "discovery":
        discovery_probes()
    elif args.action == "pe":
        pe_probes()
    elif args.action == "corrections":
        route_corrections()
    elif args.action == "control-financial":
        control_financial()
