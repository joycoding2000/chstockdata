"""Offline replay for the S07 decisive screen; no network code in this file."""
from __future__ import annotations

import csv
from datetime import date, datetime
import json
from pathlib import Path
import struct
from collections import Counter
from decimal import Decimal
import re

from screen import BASE, ROOT, TZ, digest, load, now, save


def read_calendar():
    entries = {x["id"]: x for x in load("requests.json")["requests"]}
    series = {}
    for symbol in ("sh000001", "sz399001"):
        entry = entries["calendar-" + symbol + "-retry"]
        assert entry["status"] == "RESPONSE_SAVED"
        raw = (BASE / entry["file"]).read_bytes()
        assert digest(raw) == entry["sha256"]
        rows = json.loads(raw)
        dates = [date.fromisoformat(x["day"][:10]).isoformat() for x in rows]
        assert dates == sorted(set(dates))
        assert all(float(x["close"]) > 0 for x in rows)
        series[symbol] = dates
    assert series["sh000001"] == series["sz399001"], "SH/SZ calendar disagreement"
    dates = series["sh000001"]
    observed = datetime.fromisoformat(entries["calendar-sh000001-retry"]["finished_at"])
    # This qualification only accepts a current-day completed close. A stale date is never promoted.
    current_close_confirmed = dates[-1] == observed.date().isoformat() and observed.hour >= 15
    if not current_close_confirmed:
        save("calendar.json", {"qualified": False, "reason": "Latest completed day requires further calendar evidence",
                              "observed_last": dates[-1], "observation": observed.isoformat()})
        raise ValueError("Cannot silently bind a stale product date")
    nav = dates[-252:]
    idx = len(dates) - 252
    value = {"qualified": True, "qualification_scope": "Observed market sessions from existing free Sina index route, corroborated SH/SZ; not exchange holiday document certification",
             "observed_at": observed.isoformat(), "e": nav[-1], "s": nav[0],
             "s_minus_1": dates[idx - 1], "s_minus_65": dates[idx - 65],
             "nav_dates": nav, "technical_warmup_dates": dates[idx - 65:idx],
             "first_amount20_dates": dates[idx - 20:idx], "signal_dates": dates[idx - 1:],
             "observed_market_days": len(dates), "sh_sz_symmetric_difference": [],
             "local_vipdoc_last": "2026-09-22", "local_lag_market_days": len([d for d in dates if d > "2026-09-22"]),
             "local_missing_dates": [d for d in dates if d > "2026-09-22"],
             "all_observed_dates": dates}
    save("calendar.json", value)
    print({k: value[k] for k in ("e", "s", "s_minus_1", "s_minus_65", "local_lag_market_days")})


def authorities():
    relative = ["AGENTS.md", "docs/MISHI_RADAR_V0_1_SPEC_R3_2_SCOPE_APPROVED_DATA_PENDING_2026-10-16.md",
                "docs/MISHI_RADAR_TO_CHSTOCKDATA_DR01_DR06_CONSUMER_REQUEST_2026-10-16.md",
                "docs/DR01-current-free-data-feasibility-2026-10-19.md", "docs/DR02-DR06-consolidated-gap-report.md",
                "docs/plans/2026-10-19-dual-consumer-supply-plan.md",
                "docs/audits/2026-10-22-mishi-s07-real-window-admission-preflight.md",
                "docs/audits/2026-10-22-mishi-s07-real-window-dependencies.json",
                "docs/audits/2026-10-19-w5h-historical-financial-pit-feasibility.md",
                "docs/audits/2026-10-20-w5h-r2-alternative-source-qualification.md",
                "docs/audits/2026-10-22-w5h-f2-final-evidence-qualification.md"]
    paths = [ROOT / x for x in relative]
    paths += [ROOT.parent / "mishi-radar/docs" / ("MISHI_RADAR_R3_2_" + x + ".md") for x in
              ("PRODUCT_OPERATING_SPEC_CANDIDATE_2026-10-19", "OWNER_DECISIONS_2026-10-19",
               "OWNER_DECISION_ADDENDUM_2026-10-21", "X01_LOCAL_CR_2026-10-21")]
    save("authority-identities.json", [{"path": str(p), "sha256": digest(raw := p.read_bytes()),
        "bytes": len(raw), "lines": len(raw.decode("utf-8").splitlines())} for p in paths])


def local_inventory():
    root = ROOT / ".rh3a2-vipdoc"
    result, summaries = [], {}
    for market in ("sh", "sz", "bj"):
        files = sorted((root / market / "lday").glob("*.day"))
        for p in files:
            size = p.stat().st_size
            if size == 0 or size % 32:
                result.append({"file": str(p.relative_to(ROOT)), "status": "INVALID_LENGTH", "bytes": size})
                continue
            with p.open("rb") as f:
                first = struct.unpack("<I", f.read(4))[0]
                f.seek(-32, 2)
                last = struct.unpack("<I", f.read(4))[0]
            result.append({"file": str(p.relative_to(ROOT)), "market": market,
                           "code": p.stem[2:], "records": size // 32,
                           "first_bar": str(first), "last_bar": str(last),
                           "identity_status": "BAR_FILE_NOT_SECURITY_LIFECYCLE"})
        summaries[market] = len(files)
    save("vipdoc-inventory.json", {"counts": summaries, "records": result,
         "warning": "Bar file dates/names are neither listing/delisting evidence nor historical ordinary-A universe denominators"})
    print("VIPDOC", summaries)


def raw_json(name):
    raw = (BASE / (name + ".raw")).read_bytes()
    try:
        return json.loads(raw)
    except UnicodeDecodeError:
        return json.loads(raw.decode("gb18030"))


def normal_date(value):
    if value is None or str(value) in ("-", "", "nan", "NaT", "None"):
        return None
    text = str(value)[:10]
    if len(text) == 8 and text.isdigit():
        text = f"{text[:4]}-{text[4:6]}-{text[6:]}"
    return date.fromisoformat(text).isoformat()


def universe():
    import pandas as pd  # Used only to parse the two saved official XLSX exports.
    c = load("calendar.json")
    records, sources, exclusions = [], [], []
    for label in ("sse-current-1", "sse-current-8", "sse-delisted"):
        j = raw_json(label)
        rows = j["result"]
        assert rows == j["pageHelp"]["data"]
        assert len(rows) == j["pageHelp"]["total"], "SSE source export incomplete"
        sources.append({"source": label, "rows": len(rows), "declared_total": j["pageHelp"]["total"],
                        "page_count": j["pageHelp"]["pageCount"], "query_date": j.get("queryDate"),
                        "coverage": "COMPLETE_CURRENT_QUERY_RESULT_NOT_HISTORICAL_SNAPSHOT"})
        for row in rows:
            code = row["A_STOCK_CODE"]
            if not code or code == "-":
                exclusions.append({"source": label, "company_code": row["COMPANY_CODE"], "reason": "NO_A_CODE"})
                continue
            if code.startswith("689"):
                exclusions.append({"source": label, "security": "SH:" + code,
                                   "reason": "CDR_CODE_FAMILY_EXCLUDED_PENDING_INSTRUMENT_ORIGINAL"})
                continue
            records.append({"security": "SH:" + code, "name": row["COMPANY_ABBR"],
                            "source": label, "listing": normal_date(row["LIST_DATE"]),
                            "delisting": normal_date(row["DELIST_DATE"]),
                            "board_current": row["LIST_BOARD"], "stock_type_current": row["STOCK_TYPE"],
                            "industry_current": row.get("CSRC_CODE"), "industry_label_current": row.get("CSRC_CODE_DESC"),
                            "historical_known_at": None, "historical_type_and_board": "UNVERIFIED"})
    for label in ("szse-current", "szse-delisted"):
        df = pd.read_excel(BASE / (label + ".raw"), engine="openpyxl", dtype=str)
        sources.append({"source": label, "rows": len(df), "declared_total": None,
                        "coverage": "FULL_XLSX_EXPORT_NO_INDEPENDENT_HISTORICAL_TOTAL"})
        ended = label == "szse-delisted"
        for row in df.to_dict("records"):
            code = str(row["证券代码" if ended else "A股代码"]).zfill(6)
            if not (len(code) == 6 and code.isdigit() and code.startswith(("000", "001", "002", "003", "300", "301"))):
                exclusions.append({"source": label, "security": "SZ:" + code, "reason": "OUTSIDE_ORDINARY_A_CODE_FAMILIES"})
                continue
            industry = None if ended or pd.isna(row.get("所属行业")) else row["所属行业"]
            records.append({"security": "SZ:" + code, "name": row["证券简称" if ended else "A股简称"],
                            "source": label, "listing": normal_date(row["上市日期" if ended else "A股上市日期"]),
                            "delisting": normal_date(row["终止上市日期"]) if ended else None,
                            "board_current": None if ended else row["板块"],
                            "stock_type_current": "A_FROM_EXPORT" if not ended else "A_CODE_FAMILY_ONLY",
                            "industry_current": industry, "historical_known_at": None,
                            "historical_type_and_board": "UNVERIFIED"})
    counts = Counter(x["security"] for x in records)
    duplicates = {key: value for key, value in counts.items() if value > 1}
    # Preserve duplicate lifecycle rows; never silently collapse a re-listing into an invented interval.
    for row in records:
        row["ambiguous_duplicate"] = row["security"] in duplicates
    relevant = [r for r in records if r["listing"] and r["listing"] <= c["e"]
                and (r["delisting"] is None or r["delisting"] > c["s_minus_1"])]
    new = sorted([r for r in relevant if c["s"] <= r["listing"] <= c["e"]], key=lambda r: (r["listing"], r["security"]))
    exits = sorted([r for r in relevant if r["delisting"] and c["s"] <= r["delisting"] <= c["e"]],
                   key=lambda r: (r["delisting"], r["security"]))
    boundaries = {"selection_rule": load("registration.json")["boundary_selection"],
                  "listing": new[0] if new else None, "exit": exits[0] if exits else None,
                  "industry_migration": {"status": "UNKNOWN_NO_QUALIFIED_HISTORICAL_EVENT_COLLECTION",
                                         "not_applicable_claimed": False},
                  "listing_event_rows": len(new), "exit_event_rows": len(exits)}
    save("boundary-controls.json", boundaries)
    coverage = []
    for day in c["signal_dates"]:
        # Delisting-date endpoint is deliberately provisional; this is an observable candidate
        # denominator, not an accepted product lifecycle rule or a certified U(D).
        live = [r for r in records if r["listing"] and r["listing"] <= day
                and (r["delisting"] is None or day < r["delisting"])]
        current = [r for r in live if r["delisting"] is None]
        coverage.append({"date": day, "role": "FIRST_SIGNAL" if day == c["s_minus_1"] else "NAV",
            "observed_candidate_distinct_ids": len({r["security"] for r in live}),
            "observed_current_list_rows": len(current), "observed_terminated_list_rows": len(live) - len(current),
            "candidate_duplicate_rows": sum(r["ambiguous_duplicate"] for r in live),
            "current_industry_present_rows": sum(bool(r["industry_current"]) for r in live),
            "current_industry_missing_rows": sum(not bool(r["industry_current"]) for r in live),
            "certified_U_size": "UNKNOWN", "certified_complete_U_day": 0,
            "historical_industry_qualified_rows": 0,
            "historical_industry_unknown_candidate_ids": len({r["security"] for r in live}),
            "gap": "TYPE_BOARD_HISTORY;LIFECYCLE_NOTICE_KNOWN_AT;RELISTING_COMPLETENESS;INDUSTRY_INTERVALS_VERSION_KNOWN_AT;STATUS_HISTORY"})
    with (BASE / "daily-coverage.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(coverage[0]))
        writer.writeheader()
        writer.writerows(coverage)
    # These compact source-derived identities make missing/ambiguous states inspectable without
    # copying old evidence or emitting a huge security-by-day cartesian product.
    save("universe.json", {"sources": sources, "source_rows": len(records), "duplicates": duplicates,
         "excluded_rows": exclusions, "records": records,
         "window_relevant_distinct_ids": len({r["security"] for r in relevant}),
         "window_relevant_terminated_ids": sorted({r["security"] for r in relevant if r["delisting"]}),
         "nav_days": 252, "first_signal_extra_days": 1, "complete_U_days_qualified": 0,
         "historical_industry_days_qualified": 0, "candidate_first_day": coverage[1], "candidate_last_day": coverage[-1],
         "gaps": ["Current + terminated exports give lifecycle candidates; relisting/intermediate status/board/type history and contemporaneous notices not closed",
                  "Source delisting-date meaning and market-day inclusion require original effective notice, not bar-file inference",
                  "No historical industry membership intervals, taxonomy version or migration completeness accepted",
                  "ST/risk-warning/delisting-consolidation/suspension known-at intervals unqualified; UNKNOWN never excluded"]})
    print(json.dumps({"source_counts": sources, "relevant_ids": len({r["security"] for r in relevant}),
                      "duplicates": duplicates, "boundaries": boundaries,
                      "first": coverage[1], "last": coverage[-1]}, ensure_ascii=True))


def pe():
    c, controls = load("calendar.json"), load("pe-controls.json")
    result = {"controls": [], "verdict": "INSUFFICIENT_EVIDENCE_WITH_NAMED_BLOCKER",
              "blocker": "No historical denominator/EPS/share-capital version and as-of availability contract for the tested source values",
              "reconstruction": "INPUTS_PARTIALLY_OBSERVED_NOT_FEASIBILITY_QUALIFIED"}
    financial_paths = {"600519": ROOT / "docs/audits/evidence/2026-10-20-w5h-r5/600519_ths_benefit.json",
                       "000002": BASE / "ths-000002-benefit.raw"}
    result["financial_inputs"] = [{"security": code, "path": str(path.relative_to(ROOT)),
        "sha256": digest(path.read_bytes()), "status": "CURRENT_VERSION_ONLY_NO_ORIGINAL_NOTICE_BINDING",
        "use": "Arithmetic diagnostic only; never treated as historical PIT financial evidence"}
        for code, path in financial_paths.items()]
    for case in controls["cases"]:
        code = case["security"][3:]
        financial = json.loads(financial_paths[code].read_text(encoding="utf-8"))
        np_by_period = {r["date"]: Decimal(r["index_list"]["parent_holder_net_profit"]["value"])
                        for r in financial["data"]["data"]}
        payload = raw_json("pe-em-" + code)
        assert payload["success"] is True
        rows = payload["result"]["data"]
        assert len(rows) == payload["result"]["count"] and payload["result"]["pages"] == 1
        byday = {row["TRADE_DATE"][:10]: row for row in rows}
        assert len(byday) == len(rows)
        assert set(byday) == set(c["signal_dates"]), "Business-date coverage gap"
        assert all(r["SECURITY_CODE"] == code for r in rows)
        baidu = raw_json("pe-baidu-canonical-" + code)
        chart = baidu["Result"][0]["DisplayData"]["resultData"]["tplData"]["result"]["chartInfo"][0]
        pairs = chart["body"]
        bd = {p[0][:10]: Decimal(str(p[1])) for p in pairs}
        dates = sorted(bd)
        fixed = []
        strict_before_diagnostics = []
        schedule = raw_json("schedule-" + code)["result"]["data"]
        for day, reason in case["dates"].items():
            row = byday[day]
            cap, pe_ttm, price, shares = (Decimal(str(row[k])) for k in ("TOTAL_MARKET_CAP", "PE_TTM", "CLOSE_PRICE", "TOTAL_SHARES"))
            fixed.append({"security": case["security"], "date": day, "reason": reason,
                "PE_TTM": str(pe_ttm), "total_market_cap_yuan": str(cap), "close": str(price), "total_shares": str(shares),
                "implied_profit_cap_div_pe": str(cap / pe_ttm) if pe_ttm else None,
                "cap_minus_price_times_shares": str(cap - price * shares),
                "baidu_pe": str(bd[day]) if day in bd else None,
                "denominator_period": "UNKNOWN", "denominator_scope": "EPS_TTM_DESCRIBED_PARENT_TTM_NOT_PROVEN",
                "historical_input_vintage": "UNKNOWN", "historical_available_at": "UNKNOWN", "PIT_qualified": False})
            if code in financial_paths:
                known = [r for r in schedule if r.get("ACTUAL_PUBLISH_DATE") and r["ACTUAL_PUBLISH_DATE"][:10] < day
                         and r["REPORT_DATE"][:10] in np_by_period]
                q = max(r["REPORT_DATE"][:10] for r in known)
                year = int(q[:4])
                bases = [q] if q.endswith("12-31") else [q, f"{year-1}-12-31", f"{year-1}" + q[4:]]
                expected = np_by_period[q] if len(bases) == 1 else np_by_period[bases[0]] + np_by_period[bases[1]] - np_by_period[bases[2]]
                fixed[-1]["current_financial_diagnostic_not_asof_proof"] = {
                    "q_from_date_only_schedule": q, "base_periods": bases,
                    "base_values_current_records_yuan": [str(np_by_period[p]) for p in bases],
                    "NP_TTM_current_records_yuan": str(expected), "cap_div_current_NP_TTM": str(cap / expected),
                    "source_implied_profit_minus_current_NP_TTM": str(cap / pe_ttm - expected),
                    "current_record_comparison_is_PIT_evidence": False}
        # Keep all original pre-registered controls unchanged. The original exact-date mapping
        # used the announcement-date close (before the accepted first-usable close). Add the
        # strict pre-announcement date requested by the initial selection rule as a transparent
        # deterministic mapping repair; it cannot add PIT passes or replace failed cases.
        for disclosure in case["disclosures"]:
            d = disclosure["reported_actual_publish_date"]
            before = max(x for x in c["all_observed_dates"] if x < d)
            strict_before_diagnostics.append({"announcement_date": d, "strict_prior_market_close": before,
                "PE_TTM": str(byday[before]["PE_TTM"]), "PIT_qualified": False,
                "status": "DETERMINISTIC_DATE_MAPPING_REPAIR_AFTER_FETCH_NOT_NEW_PREREGISTERED_SUCCESS"})
        overlap = sorted(set(byday) & set(bd))
        old_path = ROOT / "docs/audits/evidence/2026-10-19-w5h/eastmoney_600519_2025.json"
        repeated = None
        if code == "600519":
            old = json.loads(old_path.read_text(encoding="utf-8"))["result"]["data"]
            oldmap = {r["TRADE_DATE"][:10]: r for r in old}
            common = sorted(set(oldmap) & set(byday))
            repeated = {"old_file": str(old_path.relative_to(ROOT)), "old_sha256": digest(old_path.read_bytes()),
                        "overlap_days": len(common), "changed_PE_TTM_days": [d for d in common if Decimal(str(oldmap[d]["PE_TTM"])) != Decimal(str(byday[d]["PE_TTM"]))],
                        "interpretation": "Same current response values at two retrievals do not prove historical publication vintage"}
        result["controls"].append({"security": case["security"], "em_rows": len(rows), "EM_date_coverage": "253/253",
            "opaque_payload_version": payload.get("version"), "version_is_financial_vintage": False,
            "row_fields": sorted(rows[0]), "negative_pe_rows": sum(r["PE_TTM"] < 0 for r in rows),
            "missing_pe_rows": sum(r["PE_TTM"] is None for r in rows),
            "market_cap_price_shares_consistent_rows": sum(abs(Decimal(str(r["TOTAL_MARKET_CAP"])) - Decimal(str(r["CLOSE_PRICE"])) * Decimal(str(r["TOTAL_SHARES"]))) <= Decimal("0.02") for r in rows),
            "baidu_points": len(pairs), "baidu_first": dates[0], "baidu_last": dates[-1],
            "baidu_weekend_points": sum(date.fromisoformat(d).weekday() >= 5 for d in bd),
            "baidu_required_missing_days": sorted(set(c["signal_dates"]) - set(bd)),
            "baidu_overlap": len(overlap),
            "baidu_equal_to_em_2dp": sum(bd[d] == Decimal(str(byday[d]["PE_TTM"])).quantize(Decimal("0.01")) for d in overlap),
            "baidu_metadata": {k:v for k,v in chart.items() if k != "body"},
            "fixed_cases": fixed, "strict_pre_announcement_diagnostics": strict_before_diagnostics,
            "repeat_retrieval_check": repeated,
            "historical_industry_labels_in_em_rows": sorted({r["BOARD_NAME"] for r in rows}),
            "historical_industry_label_is_full_membership_evidence": False})
    prior = ROOT / "docs/audits/evidence/2026-10-20-w5h-r2"
    old = json.loads((prior / "analysis.json").read_text(encoding="utf-8"))["pe_denominator_check"]
    ttm = Decimal(old["2018_annual_original_parent_profit_yuan"]) + Decimal(old["2019_q3_parent_ytd_as_published_20191030_yuan"]) - Decimal(old["2018_q3_comparative_as_published_20191030_yuan"])
    assert str(ttm) == old["known_ttm_profit_yuan"]
    result["old_regression_control"] = dict(old, recalculated_ttm=str(ttm),
        recalculated_pe=str(Decimal(old["baidu_market_cap_yuan"]) / ttm),
        scope="Archived 2020 regression only; full intervening revision chain not newly certified; not a current-window case",
        reused_files=[{"path": str((prior / name).relative_to(ROOT)), "sha256": digest((prior / name).read_bytes())}
                      for name in ("analysis.json", "sina_600518_2019q3_original.raw", "sina_600518_2019q3_original.txt", "baidu_canonical_600518_ttm.raw", "baidu_600518_marketcap_all.raw")])
    old_web = ROOT / "docs/audits/evidence/2026-10-19-w5h/web_evidence.json"
    result["old_regression_control"]["annual_2018_evidence_limitation"] = {
        "path": str(old_web.relative_to(ROOT)), "sha256": digest(old_web.read_bytes()),
        "kind": "Prior structured web observation, not a stored original response; retained limitation"}
    save("pe-analysis.json", result)
    print(json.dumps({"verdict": result["verdict"], "controls": [{k:v for k,v in x.items() if k not in ("row_fields", "baidu_metadata", "fixed_cases")} for x in result["controls"]]}, ensure_ascii=True))


if __name__ == "__main__":
    import sys
    action = sys.argv[1]
    {"calendar": read_calendar, "authorities": authorities, "local": local_inventory,
     "universe": universe, "pe": pe}[action]()
