"""Offline W5-H-R2 analysis of fixed original responses and prior evidence."""
from collections import Counter
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
import ast
import hashlib
import importlib.util
import json
from pathlib import Path

from lxml import html

from audit_tools import BASE, ROOT, save

OLD = ROOT / "docs/audits/evidence/2026-10-19-w5h"


def read(name):
    return json.loads((BASE / name).read_bytes())


def ths(table):
    result = read(f"ths_600518_{table}.raw")
    assert result["status_code"] == 0
    return result["data"]


def baidu(name):
    result = read(name + ".raw")
    assert result["ResultCode"] == 0
    return result["Result"][0]["DisplayData"]["resultData"]["tplData"]


def yuan(value):
    return Decimal(str(value))


def main():
    ledger = read("requests.json")
    assert len(ledger["requests"]) <= ledger["max_http_requests"]
    previous = {}
    minimum_gaps = []
    for entry in ledger["requests"]:
        if "file" in entry:
            data = (BASE / entry["file"]).read_bytes()
            assert len(data) == entry["bytes"]
            assert hashlib.sha256(data).hexdigest() == entry["sha256"]
        source = entry["source"]
        if source in previous:
            gap = (datetime.fromisoformat(entry["requested_at"]) -
                   datetime.fromisoformat(previous[source]["finished_at"])).total_seconds()
            assert gap >= 3.0, (source, gap)
            minimum_gaps.append(gap)
        previous[source] = entry

    old_manifest = json.loads((OLD / "manifest.json").read_text(encoding="utf-8"))
    for item in old_manifest["artifacts"]:
        assert hashlib.sha256((ROOT / item["path"]).read_bytes()).hexdigest() == item["sha256"]

    financial = {}
    for table in ("benefit", "cash", "debt"):
        envelope = ths(table)
        rows = envelope["data"]
        target = [row for row in rows if row["date"] == "2017-12-31"]
        assert len(target) == 1
        financial[table] = {
            "rows": len(rows), "provider_total": envelope["total"],
            "first_report_date": min(r["date"] for r in rows),
            "last_report_date": max(r["date"] for r in rows),
            "target_period_count": len(target),
            "report_metadata_keys": sorted(k for k in target[0] if k != "index_list"),
            "target_metrics": {},
        }
        names = {"benefit": ["operating_income", "parent_holder_net_profit"],
                 "cash": ["act_cash_flow_net"],
                 "debt": ["parent_holder_equity_total", "equity"]}[table]
        for name in names:
            financial[table]["target_metrics"][name] = target[0]["index_list"][name]
        financial[table]["prior_equity_period_2016_present"] = any(
            r["date"] == "2016-12-31" for r in rows) if table == "debt" else None

    # These reference values are from the prior real issuer disclosures, not reconstruction.
    references = {
        "revenue": {"original": "26476970977.57", "revised": "17578618640.06"},
        "parent_profit": {"original": "4100926148.57", "revised": "2149836281.41"},
        "ocf": {"original": "1842794237.84", "revised": "-4840052606.46"},
        "parent_equity": {"original": "32032959807.76", "revised": "28413344515.00"},
    }
    got = {
        "revenue": financial["benefit"]["target_metrics"]["operating_income"]["value"],
        "parent_profit": financial["benefit"]["target_metrics"]["parent_holder_net_profit"]["value"],
        "ocf": financial["cash"]["target_metrics"]["act_cash_flow_net"]["value"],
        "parent_equity": financial["debt"]["target_metrics"]["parent_holder_equity_total"]["value"],
    }
    for name, value in got.items():
        assert yuan(value) == yuan(references[name]["revised"])
        assert yuan(value) != yuan(references[name]["original"])

    series = {}
    maps = {}
    names = ["baidu_canonical_600518_ttm", "baidu_600518_ttm_1y",
             "baidu_600519_ttm_1y", "baidu_600518_static_all", "baidu_600518_marketcap_all"]
    for name in names:
        tpl = baidu(name)
        chart = tpl["result"]["chartInfo"][0]
        points = chart["body"]
        dates = [date.fromisoformat(row[0]) for row in points]
        maps[name] = dict(points)
        gaps = Counter((right - left).days for left, right in zip(dates, dates[1:]))
        series[name] = {
            "points": len(points), "first": points[0], "last": points[-1],
            "calendar_gap_days": dict(gaps),
            "weekend_points": sum(d.weekday() >= 5 for d in dates),
            "negative_values": sum(str(row[1]).startswith("-") for row in points),
            "missing_values": sum(row[1] in ("", "--", None) for row in points),
            "metadata": {key: value for key, value in chart.items() if key != "body"},
            "source_marker": tpl["data_source"],
            "source_marker_meaning": "UNKNOWN; not proof of ultimate vendor independence",
        }

    crosscheck = {}
    quant = Decimal("0.01")
    for code in ("600518", "600519"):
        rows = json.loads((OLD / f"eastmoney_{code}_2025.json").read_bytes(), parse_float=Decimal)["result"]["data"]
        observed = maps[f"baidu_{code}_ttm_1y"]
        selected = [r for r in rows if r["TRADE_DATE"][:10] in observed]
        matched = [r for r in selected if yuan(r["PE_TTM"]).quantize(quant, rounding=ROUND_HALF_UP) ==
                   yuan(observed[r["TRADE_DATE"][:10]])]
        crosscheck[code] = {
            "intersecting_trading_days": len(selected), "equal_after_source_precision_rounding": len(matched),
            "first_intersection": min(r["TRADE_DATE"][:10] for r in selected),
            "last_intersection": max(r["TRADE_DATE"][:10] for r in selected),
            "end_2025_baidu": observed.get("2025-12-31"),
            "lineage_conclusion": "Value agreement alone does not prove independent upstream or historical vintage.",
        }

    # Extra original report is necessary to test the fixed 2020 TTM denominator.
    q3_text = html.fromstring((BASE / "sina_600518_2019q3_original.raw").read_bytes()).text_content()
    assert "公告日期:2019-10-30" in q3_text
    assert "33,173,948.69" in q3_text and "689,158,719.06" in q3_text
    annual_old = json.loads((OLD / "web_evidence.json").read_text(encoding="utf-8"))[
        "observations"][0]["2018_net_profit_attributable_to_parent_as_published_2019"]
    known_ttm = yuan(annual_old) + yuan("33173948.69") - yuan("689158719.06")
    assert known_ttm == Decimal("479203728.07")
    original_2020 = json.loads((OLD / "eastmoney_600518_2020.json").read_bytes(), parse_float=Decimal)["result"]["data"]
    fixed_day = next(r for r in original_2020 if r["TRADE_DATE"].startswith("2020-01-09"))
    original_annual = yuan(annual_old)
    ttm_value = yuan(maps["baidu_canonical_600518_ttm"]["2020-01-09"])
    static_value = yuan(maps["baidu_600518_static_all"]["2020-01-09"])
    cap = yuan(maps["baidu_600518_marketcap_all"]["2020-01-09"]) * Decimal(100_000_000)
    expected_static = cap / original_annual
    expected_ttm = cap / known_ttm
    assert expected_static.quantize(quant, rounding=ROUND_HALF_UP) == static_value
    assert expected_ttm > 0 and ttm_value < 0
    diagnostics = {
        "fixed_trade_date": "2020-01-09",
        "why_extra_original": "2019 Q3 original and its 2018 comparison are required TTM base periods for the already fixed 2020 case, not a replacement stock/year.",
        "2018_annual_original_parent_profit_yuan": str(original_annual),
        "2019_q3_parent_ytd_as_published_20191030_yuan": "33173948.69",
        "2018_q3_comparative_as_published_20191030_yuan": "689158719.06",
        "announcement_date_of_q3_original": "2019-10-30",
        "known_ttm_profit_yuan": str(known_ttm), "baidu_market_cap_yuan": str(cap),
        "old_eastmoney_market_cap_yuan": str(fixed_day["TOTAL_MARKET_CAP"]),
        "baidu_static_pe": str(static_value), "static_pe_from_original_annual": str(expected_static),
        "baidu_ttm_pe": str(ttm_value), "ttm_pe_from_then_disclosed_values": str(expected_ttm),
        "old_eastmoney_ttm_pe": str(fixed_day["PE_TTM"]), "old_eastmoney_static_pe": str(fixed_day["PE_LAR"]),
        "verdict": "Static sample is consistent with the then-disclosed annual profit; TTM sample contradicts the then-disclosed positive TTM numerator. Complete intervening disclosure chain and first-known history remain unqualified.",
    }

    code = {}
    for module, relative, functions in [
        ("akshare", "stock_fundamental/stock_finance_ths.py", ["stock_financial_benefit_new_ths", "stock_financial_cash_new_ths", "stock_financial_debt_new_ths"]),
        ("akshare", "stock_feature/stock_zh_valuation_baidu.py", ["stock_zh_valuation_baidu"]),
        ("mootdx", "financial/financial.py", []),
        ("baostock", "common/contants.py", []),
    ]:
        path = Path(importlib.util.find_spec(module).origin).parent / relative
        content = path.read_bytes()
        tree = ast.parse(content.decode("utf-8-sig"))
        code[str(path)] = {"sha256": hashlib.sha256(content).hexdigest(),
            "functions": [{"name": n.name, "line": n.lineno, "end_line": n.end_lineno,
                "signature": ast.unparse(n.args)} for n in ast.walk(tree)
                if isinstance(n, ast.FunctionDef) and n.name in functions]}

    authority_names = ["MISHI_RADAR_V0_1_SPEC_R3_2_SCOPE_APPROVED_DATA_PENDING_2026-10-16.md",
        "MISHI_RADAR_TO_CHSTOCKDATA_DR01_DR06_CONSUMER_REQUEST_2026-10-16.md"]
    authority_equal = {}
    for name in authority_names:
        producer = ROOT / "docs" / name
        consumer = ROOT.parent / "mishi-radar/docs" / name
        authority_equal[name] = producer.read_bytes() == consumer.read_bytes()

    result = {
        "requests_recorded": len(ledger["requests"]),
        "http_status_counts": dict(Counter(str(x.get("http_status")) for x in ledger["requests"])),
        "minimum_same_source_after_finish_seconds": min(minimum_gaps),
        "source_body_bytes": sum(x.get("bytes", 0) for x in ledger["requests"]),
        "prior_artifacts_reverified": len(old_manifest["artifacts"]),
        "prior_valuation_rows_reused_without_network": 729,
        "baostock_new_logins": 0, "financial": financial, "reference_versions": references,
        "baidu_series": series, "crosscheck_2025": crosscheck,
        "pe_denominator_check": diagnostics, "external_library_code": code,
        "authority_current_consumer_copy_equal": authority_equal,
        "production_runtime_changes": 0,
    }
    save("analysis.json", result)
    print(json.dumps({k: v for k, v in result.items() if k not in
        {"baidu_series", "financial", "external_library_code", "reference_versions"}}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
