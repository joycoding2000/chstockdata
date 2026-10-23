"""Deterministic, offline H04 input delivery. Never imports or runs SIOS."""
from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, getcontext
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct

SCRIPT_ROOT = Path(__file__).resolve().parent
ROOT = SCRIPT_ROOT.parent if SCRIPT_ROOT.name == "tools" else SCRIPT_ROOT
getcontext().prec = 36
D = Decimal
CST = timezone(timedelta(hours=8))
CODES = ("513530", "513990")


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compact(text):
    return re.sub(r"\s+", "", text)


def locator(blocks, phrase):
    for i, block in enumerate(blocks):
        text = compact(block)
        start = text.find(phrase)
        if start >= 0:
            return {"kind": "pdf_page", "one_based_page": i + 1, "excerpt": text[max(0, start - 30):start + len(phrase) + 180]}
    raise ValueError(f"missing source disclosure: {phrase}")


def parse_dividend(path):
    report = read(path)
    text = compact("".join(report["blocks"]))
    if "基金主代码513530" not in text:
        raise ValueError("wrong dividend identity")
    def day(label):
        match = re.search(label + r"(\d{4})年(\d{1,2})月(\d{1,2})日", text)
        if not match:
            raise ValueError(f"missing dividend date: {label}")
        return date(*map(int, match.groups())).isoformat()
    amount = re.search(r"本次分红方案[（(]单位[：:]元/10份基金份额[）)](\d+\.\d+)", text)
    if not amount:
        raise ValueError("missing explicit per-ten unit")
    published = day("公告送出日期：")
    ex = day("除息日")
    record = day("权益登记日")
    payment = day("现金红利发放日")
    pickup = re.search(r"投资者可在(\d{4})年(\d{1,2})月(\d{1,2})日领取现金红利", text)
    if not pickup or date(*map(int, pickup.groups())).isoformat() != payment:
        raise ValueError("cash availability not confirmed by issuer pickup clause")
    if not published <= record < ex <= payment:
        raise ValueError("invalid cash event lifecycle")
    return {"event_id": f"SH:513530:CASH:{ex}", "instrument_id": "SH:513530", "status": "implemented",
            "announcement_date": published, "announcement_available_at": published + "T23:59:59+08:00",
            "announcement_time_precision": "DATE; conservative date-end inference, not observed timestamp",
            "equity_record_date": record, "ex_dividend_date": ex, "payment_date": payment,
            "cash_per_10_shares_cny": amount.group(1), "cash_per_share_cny": str(D(amount.group(1)) / 10),
            "share_ratio": "1", "cash_available_not_before": payment + "T23:59:59+08:00",
            "cash_availability_basis": "ISSUER_PICKUP_DATE_FOR_REGISTERED_DESIGNATED_HOLDER; date-end conservative availability, next eligible session only",
            "broker_actual_credit_observed_at": None, "unregistered_holder_cash_available_at": None,
            "source_file": "sources/" + report["source_file"], "extracted_file": "extracted/" + path.name,
            "evidence": {key: locator(report["blocks"], phrase) for key, phrase in (("identity", "基金主代码513530"), ("unit", "本次分红方案"), ("effective", "除息日"), ("cash", "投资者可在"))}}


def economic_factor(day, previous_close, close, events):
    cash = D(0)
    for event in events:
        if event["ex_dividend_date"] != day:
            continue
        known = event.get("announcement_available_at")
        cutoff = day + "T15:00:00+08:00"
        if not known or datetime.fromisoformat(known) > datetime.fromisoformat(cutoff):
            raise ValueError("FUTURE_OR_UNKNOWN_ANNOUNCEMENT")
        cash += D(event["cash_per_share_cny"])
    if previous_close <= 0 or close <= 0:
        raise ValueError("invalid market price")
    return (close + cash) / previous_close


def unit_book(day, events):
    # At T-close, date-only payment availability inferred at 23:59:59 has not
    # happened yet. Transfer on the first subsequent reported session.
    claims = sum((D(e["cash_per_share_cny"]) for e in events if e["ex_dividend_date"] <= day <= e["payment_date"]), D(0))
    paid = sum((D(e["cash_per_share_cny"]) for e in events if e["payment_date"] < day), D(0))
    return claims, paid


def market_rows(path, code):
    body = path.read_bytes()
    if len(body) % 32:
        raise ValueError("truncated vipdoc source")
    rows, previous = [], None
    for i, values in enumerate(struct.iter_unpack("<5If2I", body)):
        day, op, hi, lo, cl, amount, volume, reserved = values
        dt = datetime.strptime(str(day), "%Y%m%d").date().isoformat()
        if previous and previous >= dt:
            raise ValueError("non-increasing or duplicate dates")
        previous = dt
        if not lo <= min(op, cl) <= max(op, cl) <= hi:
            raise ValueError("OHLC constraints")
        amount_bits = struct.unpack_from("<I", body, i * 32 + 20)[0]
        rows.append({"instrument_id": f"SH:{code}", "date": dt,
                     **{k: f"{D(v)/1000:.3f}" for k,v in zip(("open", "high", "low", "close"), (op, hi, lo, cl))},
                     "volume_shares": volume, "amount_cny": str(D.from_float(amount)),
                     "open_int": op, "high_int": hi, "low_int": lo, "close_int": cl,
                     "amount_float32_bits": amount_bits, "reserved_uint32": reserved,
                     "source_file": "raw_sources/" + path.name, "source_row_1based": i + 1, "source_byte_offset": i * 32,
                     "source_sha256": sha(path), "price_unit": "CNY_PER_FUND_SHARE", "volume_unit": "SHARE", "amount_unit": "CNY",
                     "information_available_at": dt + "T15:00:00+08:00", "availability_basis": "EXCHANGE_RULE_INFERRED_NOT_OBSERVED_VINTAGE"})
    return rows


def audit_annual(path, code, year):
    report = read(path)
    blocks = report["blocks"]
    text = compact("".join(blocks))
    if f"基金主代码{code}" not in text:
        raise ValueError("report fund identity mismatch")
    period = re.search(r"本报告期自(\d{4})年(\d{1,2})月(\d{1,2})日起?至(?:(\d{4})年)?(\d{1,2})月(\d{1,2})日", text)
    if period is None:
        raise ValueError("report period unknown")
    y,m,d,ey,em,ed = period.groups()
    start, end = date(int(y),int(m),int(d)), date(int(ey or y),int(em),int(ed))
    if [start.isoformat(),end.isoformat()] != [f"{year}-01-01",f"{year}-12-31"]:
        raise ValueError("non-complete fiscal year")
    negative = next((x for x in ("本基金过去三年未进行利润分配", "本基金未实施过利润分配", "本基金本报告期未进行利润分配", "本基金本报告期内未进行利润分配", "本报告期内，本基金未进行利润分配") if x in text), None)
    positive = code == "513530" and year == 2025 and "2025年0.9000" in text
    if not negative and not positive:
        raise ValueError("cash completeness cannot be inferred from missing text")
    split = re.search(r"本报告期(?:期间)?基金拆分变动份额(?:（份额减少以[\"“]-[\"”]填列）)?-", text)
    if not split:
        raise ValueError("no explicit no-split disclosure")
    return {"instrument_id": f"SH:{code}", "period_start": start.isoformat(), "period_end": end.isoformat(),
            "source_file": "sources/" + report["source_file"], "extracted_file": "extracted/" + path.name,
            "cash_status": "SEVEN_IMPLEMENTED_CASH_EVENTS" if positive else "CONFIRMED_NO_CASH_EVENT_IN_REPORT_SCOPE",
            "cash_per_10_shares_annual": "0.9000" if positive else "0", "holder_unit_changes": "CONFIRMED_NONE_IN_REPORT_SCOPE",
            "cash_evidence": locator(blocks, "2025年0.9000" if positive else negative),
            "share_evidence": locator(blocks, split.group()), "evidence_role": "EX_POST_COMPLETENESS_AUDIT_NOT_HISTORICAL_SIGNAL"}


def clean_pages(blocks):
    return "\n".join(line for block in blocks for line in block.splitlines()
                     if not re.search(r"^(?:华泰柏瑞.*(?:报告|招募)|招商上证.*(?:报告|招募)|第\s*\d+\s*页\s*共)", line.strip()))


def extract_portfolio(path, code):
    report = read(path)
    text = clean_pages(report["blocks"])
    # The live table is after the financial statements, excluding the contents page.
    candidates = list(re.finditer(r"(?:8|7)\.3(?:\.1)?\s*(?:期末|报告期末)(?:指数投资)?按(?:行业|公允价值)", text))
    sector_start = next((m.start() for m in candidates if m.start() > len(text) / 3 and "行业" in text[m.start():m.start()+70]), None)
    if sector_start is None:
        # Domestic-format funds use 8.2.3/7.2.3 for Hong Kong sectors.
        matches = list(re.finditer(r"(?:报告期末按行业分类的港股通投资股票投资组合|期末按行业分类的港股通投资股票投资组合)", text))
        sector_start = matches[-1].start() if matches else None
    if sector_start is None:
        raise ValueError("industry table not found")
    sector_chunk = text[sector_start:]
    heading = "期末指数投资按公允价值占基金资产净值比例大小排序的所有权益投资明细" if code == "513530" else "报告期末指数投资按公允价值占基金资产净值比例大小排序的所有股票投资明细"
    if heading not in compact(text):
        raise ValueError("complete equity holdings heading missing")
    # Heading line wrap is removed only for locating the source position.
    pattern = r"\s*".join(re.escape(c) for c in heading)
    hits = list(re.finditer(pattern, text))
    table = text[hits[-1].end():]
    ending = re.search(r"(?:8|7)\.[45]\s*报告期内", table)
    if ending:
        table = table[:ending.start()]
    positions = []
    if code == "513530":
        ids = list(re.finditer(r"(?<!\d)(\d{1,5})\s+(?:(HG|HK)\b|(沪港通|香港联))", table))
        for i, item in enumerate(ids):
            span = table[item.end():ids[i+1].start() if i+1 < len(ids) else len(table)]
            number = re.search(r"([\d,]+\.\d{2})\s+(\d+\.\d{2})", span)
            if not number:
                raise ValueError("unparsed HK holding value")
            positions.append({"security_id": "HK:" + item.group(1).zfill(5), "source_security_code": item.group(1),
                              "channel": item.group(2) or ("HG" if item.group(3) == "沪港通" else "HK"), "security_name": None, "shares": None,
                              "shares_qualification": "UNPARSED_WRAPPED_PDF_CELLS; not required for reported value/weight attribution",
                              "market_value_cny": number.group(1).replace(",", ""), "nav_weight_percent": number.group(2)})
    else:
        active = re.search(r"(?:8|7)\.3\.2\s*期末积极投资", table)
        for item in re.finditer(r"(?:^|\n)\s*(\d{1,3})\s+(\d{5})\s+(.+?)\s+([\d,]+)\s+([\d,]+\.\d{2})\s+(\d+\.\d{2})", table, re.S):
            positions.append({"security_id": "HK:" + item.group(2), "source_security_code": item.group(2), "channel": "HG",
                              "security_name": compact(item.group(3)), "shares": int(item.group(4).replace(",", "")),
                              "holding_role": "ACTIVE_NON_INDEX" if active and item.start() > active.start() else "INDEX_INVESTMENT",
                              "market_value_cny": item.group(5).replace(",", ""), "nav_weight_percent": item.group(6)})
    if not positions:
        raise ValueError("no parsed holdings")
    sectors = []
    names = {"能源":"ENERGY", "原材料":"MATERIALS", "材料":"MATERIALS", "工业":"INDUSTRIALS", "可选消费":"CONSUMER_DISCRETIONARY", "非必需消费品":"CONSUMER_DISCRETIONARY", "非日常生活消费品":"CONSUMER_DISCRETIONARY", "主要消费":"CONSUMER_STAPLES", "必需消费品":"CONSUMER_STAPLES", "日常消费品":"CONSUMER_STAPLES", "医药卫生":"HEALTH_CARE", "医疗保健":"HEALTH_CARE", "金融":"FINANCIALS", "信息技术":"INFORMATION_TECHNOLOGY", "科技":"INFORMATION_TECHNOLOGY", "通信服务":"COMMUNICATION_SERVICES", "通讯":"COMMUNICATION_SERVICES", "公用事业":"UTILITIES", "房地产":"REAL_ESTATE"}
    stop = re.search(r"(?:8|7)\.[34]\s*期末按公允价值", sector_chunk)
    sector_chunk = sector_chunk[:stop.start()] if stop else sector_chunk[:4500]
    for label, value, weight in re.findall(r"(?:^|\n)\s*([\u4e00-\u9fff]+)\s+([\d,]+\.\d{2}|-)\s+(\d+\.\d{2}|-)", sector_chunk):
        if label in names:
            sectors.append({"source_industry": label, "common_sector": names[label], "market_value_cny": value.replace(",", "") if value != "-" else "0", "nav_weight_percent": weight if weight != "-" else "0", "zero_basis": "EXPLICIT_DISCLOSED_DASH_NO_HOLDING" if value == "-" else None})
    if len(sectors) != 11 or len({x["common_sector"] for x in sectors}) != 11:
        raise ValueError(f"industry coverage {len(sectors)} not eleven: {path.name}")
    stock_total = sum((D(x["market_value_cny"]) for x in positions), D(0))
    industry_total = sum((D(x["market_value_cny"]) for x in sectors), D(0))
    if stock_total != industry_total:
        raise ValueError(f"holdings/industry value reconciliation: {path.name}: {stock_total} != {industry_total}")
    return positions, sectors


def aggregate_holdings(rows):
    combined = {}
    for row in rows:
        key = row["security_id"]
        if key not in combined:
            combined[key] = {"security_id": key, "shares": 0, "market_value_cny": D(0), "nav_weight_percent": D(0), "source_channels": [], "source_roles": []}
        dest = combined[key]
        if row["shares"] is None or dest["shares"] is None:
            dest["shares"] = None
        else:
            dest["shares"] += row["shares"]
        dest["market_value_cny"] += D(row["market_value_cny"])
        dest["nav_weight_percent"] += D(row["nav_weight_percent"])
        dest["source_channels"].append(row["channel"])
        dest["source_roles"].append(row.get("holding_role", "INDEX_INVESTMENT"))
    return [{**row, "market_value_cny": str(row["market_value_cny"]), "nav_weight_percent": str(row["nav_weight_percent"])} for row in combined.values()]


def manifest(root, name, gates):
    paths = [p for p in root.rglob("*") if p.is_file() and not (p.parent == root and p.name in {"manifest.json", "manifest.sha256"}) and "__pycache__" not in p.parts]
    save(root / "manifest.json", {"schema_version": "H04-OFFLINE-1", "name": name, "source_investigation_boundary": ["2024-01-01", "2025-12-31"],
        "research_window_newly_frozen": False, "research_resumption_authorized": False, "gates": gates,
        "files": {p.relative_to(root).as_posix(): {"sha256": sha(p), "bytes": p.stat().st_size} for p in sorted(paths)}})
    (root / "manifest.sha256").write_text(sha(root / "manifest.json") + "  manifest.json\n", encoding="utf-8")


def build(root, out):
    out.mkdir(parents=True, exist_ok=True)
    if root.resolve() != out.resolve():
        for name in ("sources", "raw_sources", "extracted", "contracts"):
            shutil.copytree(root / name, out / name, dirs_exist_ok=True)
        for name in ("context.json", "network_ledger.json", "huatai-selected.json", "cmf-selected.json", "cmf-query-semantics.json", "index-search-result.json"):
            shutil.copyfile(root / name, out / name)
        if (root / "public_api_offline_replay.json").exists():
            shutil.copyfile(root / "public_api_offline_replay.json", out / "public_api_offline_replay.json")
        tools = out / "tools"
        tools.mkdir(exist_ok=True)
        for name in ("build_delivery.py", "receive_delivery.py", "test_h04_offline.py", "extract_reports.py"):
            if (root / name).exists():
                shutil.copyfile(root / name, tools / name)
    ledger = read(root / "network_ledger.json")
    source_map = {x["file"]: x for x in ledger["requests"]}
    actions = sorted([parse_dividend(p) for p in (root / "extracted").glob("*official-dividend.json")], key=lambda x:x["ex_dividend_date"])
    if len(actions) != 7 or sum(D(x["cash_per_share_cny"]) for x in actions) != D("0.09"):
        raise ValueError("seven real notices must reconcile to annual 0.09 CNY/share")
    audits = [audit_annual(next((root / "extracted").glob(f"*{code}-{year}-official-annual.json")), code, year) for code in CODES for year in (2023, 2024, 2025)]
    for record in audits + actions:
        record["source_sha256"] = source_map[record["source_file"]]["sha256"]
        record["source_url"] = source_map[record["source_file"]]["url"]
    save(out / "fund_actions.json", {"scope": "2023 warmup audit and 2024-2025 implemented distributions and unit changes", "annual_audits": audits, "events": actions,
        "per_fund": {"SH:513530": "QUALIFIED_POSITIVE_EVENTS_2025_NO_EVENT_2023_2024", "SH:513990": "CONFIRMED_NO_EVENT_2023_2025"},
        "failed_2026_10_19_queries": read(root / "context.json")["historical_failure"], "annual_reports_are_signal_inputs": False})
    calendar_body = (root / "raw_sources/sh000001.day").read_bytes()
    if len(calendar_body) % 32:
        raise ValueError("truncated calendar source")
    calendar_all = [datetime.strptime(str(v[0]), "%Y%m%d").date().isoformat()
                    for v in struct.iter_unpack("<5If2I", calendar_body)]
    if calendar_all != sorted(set(calendar_all)):
        raise ValueError("calendar duplicate/date order")
    expected = [d for d in calendar_all if "2024-01-01" <= d <= "2025-12-31"]
    warmup = [d for d in calendar_all if d < "2024-01-01"][-200:]
    calendar = warmup + expected
    save(out / "calendar.json", {"sessions": calendar, "observation_sessions": expected, "warmup_sessions": warmup,
        "basis": "Independent cached SSE Composite session dates, prices not used", "static_H04_contract_required_signal_warmup": None,
        "warmup_role": "200 prior raw observations supplied for compatibility; does not import H01 SMA200/126 rules into static H04"})
    raw, observations, coverage = [], [], {}
    for code in CODES:
        all_rows = market_rows(root / f"raw_sources/sh{code}.day", code)
        by_date = {r["date"]:r for r in all_rows}
        if any(d not in by_date for d in calendar):
            raise ValueError("missing required session; no successful-date-only truncation")
        events = actions if code == "513530" else []
        tr_index, base = D(100), D(by_date[calendar[0]]["close"])
        for i, day in enumerate(calendar):
            row = by_date[day]
            prev = all_rows[row["source_row_1based"] - 2]
            factor = economic_factor(day, D(prev["close"]), D(row["close"]), events)
            if i:
                tr_index *= factor
            amount, volume = D(row["amount_cny"]), row["volume_shares"]
            if volume <= 0 or not D(row["low"]) - D("0.001") <= amount / volume <= D(row["high"]) + D("0.001"):
                raise ValueError("nontrade or VWAP unit mismatch")
            claims, paid = unit_book(day, events)
            entitled = sum((D(e["cash_per_share_cny"]) for e in events if e["ex_dividend_date"] <= day), D(0))
            if claims + paid != entitled:
                raise ValueError("wealth conservation failed")
            raw.append(row)
            observations.append({"instrument_id": row["instrument_id"], "date": day, "role": "WARMUP_REFERENCE" if day < "2024-01-01" else "EXPOSED_HISTORY_INPUT",
                "raw_close_cny": row["close"], "previous_raw_close_cny": prev["close"], "cash_entitlement_today_cny_per_share": str(sum((D(e["cash_per_share_cny"]) for e in events if e["ex_dividend_date"] == day), D(0))),
                "gross_economic_return_factor": str(factor), "gross_ex_distribution_linked_index": str(tr_index), "price_only_index": str(D(100)*D(row["close"])/base),
                "linked_index_interpretation": "CONVENTIONAL_GROSS_EX_DISTRIBUTION_REINVESTMENT_IDENTITY; not executable self-financing reinvestment before payment",
                "fixed_one_share_receivable_cny": str(claims), "fixed_one_share_distributed_cash_cny": str(paid), "fixed_one_share_wealth_cny": str(D(row["close"]) + claims + paid),
                "fixed_one_share_model": "1 continuously held share; gross cash retained after conservative pickup-date-end availability; no interest/tax/fees or reinvestment; diagnostic accounting only",
                "information_available_at": row["information_available_at"], "pit_economic_input_qualified": True,
                "future_events_applied": [], "latest_adjustment_factor_used": False, "broker_cash_credit_attested": False,
                "source_market_row_1based": row["source_row_1based"], "source_market_sha256": row["source_sha256"]})
        coverage[code] = {"full_raw_file_first": all_rows[0]["date"], "full_raw_file_last": all_rows[-1]["date"], "full_raw_rows": len(all_rows),
            "warmup_rows": len(warmup), "investigation_rows": len(expected), "qualified_economic_input_rows": len(calendar),
            "investigation_first": expected[0], "investigation_last": expected[-1], "missing_sessions": [], "zero_turnover_rows": [],
            "cash_events_in_investigation": len(events), "gate": "PASS_FOR_CONSUMER_REVIEW"}
    with (out / "raw_market_data.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(raw[0]))
        writer.writeheader(); writer.writerows(raw)
    (out / "total_return_observations.jsonl").write_text("".join(json.dumps(row,ensure_ascii=False) + "\n" for row in observations), encoding="utf-8")
    sample = []
    for event in actions:
        day = next(x for x in observations if x["instrument_id"] == event["instrument_id"] and x["date"] == event["ex_dividend_date"])
        payment = next(x for x in observations if x["instrument_id"] == event["instrument_id"] and x["date"] == event["payment_date"])
        sample.append({"event_id":event["event_id"], "ex_date":day["date"], "previous_raw_close_cny":day["previous_raw_close_cny"], "ex_date_raw_close_cny":day["raw_close_cny"],
            "cash_per_share_cny":event["cash_per_share_cny"], "price_only_factor":str(D(day["raw_close_cny"])/D(day["previous_raw_close_cny"])),
            "gross_economic_factor":day["gross_economic_return_factor"], "economic_increment_due_to_distribution":str(D(event["cash_per_share_cny"])/D(day["previous_raw_close_cny"])),
            "payment_date":payment["date"], "payment_date_new_return_entitlement_cny":payment["cash_entitlement_today_cny_per_share"],
            "payment_date_receivable_still_held_until_date_end_cny":payment["fixed_one_share_receivable_cny"],
            "payment_not_counted_twice":True, "cash_reinvestment_executed":False})
    save(out / "event_reconciliation.json", sample)
    save(out / "coverage_and_unknowns.json", {"per_fund": coverage, "not_a_new_frozen_strategy_window": True,
        "bounded_qualification": "PIT economic entitlement/return and cash date schedules under exchange-rule raw availability. Not attested historical downloaded vintages, broker credit, fees, execution or reinvestment strategy.",
        "remaining_tr_use_conditions": ["SIOS must independently accept schema and distinction between ex-distribution economic index and spendable cash", "Any executable reinvestment timing/cost/tax must be frozen by consumer before an authorized experiment", "Unknown exact broker credit/intraday publication timestamps remain null; conservative date-end schedules are explicit"]})
    save(out / "provenance.json", {"source_transport": ledger, "raw_identity": read(root / "context.json")["local_sources"],
        "issuer_complete_periods": audits, "historical_download_vintage": "NOT_ATTESTED", "time_zone": "Asia/Shanghai", "source_rules": "Do not use future events, future holdings, latest adjustment factors or currently selected dates to backfill historical decisions",
        "rejected_sources": {"sources/009-000159-method.raw": "WRONG_INDEX_IDENTITY_SH_NOT_HK", "sources/044-H11054-method.raw": "WRONG_INDEX_IDENTITY_EQUIPMENT", "sources/012-513530-dividend-pdf-test.raw": "HTTP_200_HTML_CHALLENGE_NOT_PDF", "sources/043-513990-official-periodic.raw": "APPLICATION_ERROR_111_MISSING_PUBLIC_PROTOCOL", "sources/022-513530-official-periodic.raw": "APPLICATION_ERROR_PAGE_SIZE", "sources/023-513530-official-notices.raw": "APPLICATION_ERROR_PAGE_SIZE"},
        "network_accounting": {"direct_http_requests": len(ledger["requests"]), "direct_body_bytes": sum(x["downloaded_bytes"] for x in ledger["requests"]), "web_search_tool_queries": 1, "web_search_result_file": "index-search-result.json", "tooling_probe_failed_calls": 1, "opaque_tool_transport_body_bytes": None, "conservative_reserved_requests": 6, "conservative_reserved_bytes": 3000000, "total_controlled_request_slots_used": len(ledger["requests"])+6, "total_byte_reservation_used": sum(x["downloaded_bytes"] for x in ledger["requests"])+3000000, "note": "Raw source bytes exact; search/status internal transport not exposed. No claim of exact full-stack traffic; 6 request slots and 3 MB withheld for both tool calls."}})
    attribute(out, root, source_map)
    (out / "README.md").write_text("# H04 离线消费者输入\n\n本包只供独立消费者审阅，不授权研究恢复。2024–2025 是来源调查边界，不是新冻结策略窗口。\n\n```text\npython tools/build_delivery.py --root . --output .\npython tools/receive_delivery.py . --report ../independent-validation.json\n```\n\n完整原件复核需要已有可选 pypdf；缺失时接收器明确阻断，不会静默降级为全验证通过。\n\n原始价格单位元/份，量股，额人民币元，保留 float32 精确值与源字节定位。\n\n每日经济回报因子为 (当日原始收盘价+当日除息现金)/前收盘价。链接指数是标准毛总回报恒等式，隐含除息再投资的数学口径；不是支付前可执行再投资。另给一份不再投资、现金留存的每份财富账：价格+应收+已分配现金。权益只在除息生效，保守日末可用后再将应收转现金、不再产生一次收益。可用现金按官方领取日结束后、下一合格交易时段保守处理；真实券商到账未知。\n\n基金持仓只作为具名历史产品暴露代理，绝不是指数真实成分或权重。行业归一映射保留原名和彭博来源；分类历史版本未认证。价值、质量、股票利率敏感性与连续历史母池/指数权重缺失，不能计零。禁止用后发报告回填历史已知。\n", encoding="utf-8")
    gates = {"H04_TOTAL_RETURN_DATA_GATE": "PASS_FOR_CONSUMER_REVIEW", "H04_ATTRIBUTION_DATA_GATE": "PARTIAL_WITH_NAMED_GAPS"}
    manifest(out / "H04-attribution-delivery", "H04 partial attribution inputs", {"H04_ATTRIBUTION_DATA_GATE": gates["H04_ATTRIBUTION_DATA_GATE"]})
    manifest(out, "H04-TR-delivery with separately gated attribution inputs", gates)
    print(json.dumps({"raw_rows":len(raw), "qualified_rows":len(observations), "events":len(actions), "gates":gates, "manifest_sha256":sha(out / "manifest.json")}, indent=2))


def attribute(out, root, source_map):
    attr = out / "H04-attribution-delivery"
    snapshots, all_holdings, industry, risks = [], [], [], []
    selections = read(root / "huatai-selected.json") + read(root / "cmf-selected.json")
    for code in CODES:
        for year in (2024, 2025):
            for kind in ("semi", "annual"):
                path = next((root / "extracted").glob(f"*{code}-{year}-official-{kind}.json"))
                report = read(path)
                positions, sectors = extract_portfolio(path, code)
                combined = aggregate_holdings(positions)
                meta = next(x for x in selections if x["label"] == f"{code}-{year}-official-{kind}")["metadata"]
                publication = (datetime.fromtimestamp(int(meta["activationDate"])/1000,CST).date().isoformat() if code == "513530" else meta["pubDate"])
                asof = f"{year}-06-30" if kind == "semi" else f"{year}-12-31"
                base = {"instrument_id": f"SH:{code}", "index_id": "930914" if code == "513530" else "H50069", "observation_date": asof,
                        "publication_date": publication, "available_at": publication + "T23:59:59+08:00", "actual_first_observed_at": source_map["sources/" + report["source_file"]]["completed_at"],
                        "source_file": "sources/" + report["source_file"], "source_sha256": source_map["sources/" + report["source_file"]]["sha256"], "extracted_file": "extracted/" + path.name,
                        "scope": "ACTUAL_FUND_HOLDINGS_NOT_INDEX_CONSTITUENTS", "historically_known_on_observation_date": False}
                equity_value = sum((D(x["market_value_cny"]) for x in combined),D(0))
                sector_weights = sorted((D(x["nav_weight_percent"]) for x in sectors),reverse=True)
                holdings_weights = sorted((D(x["nav_weight_percent"]) for x in combined),reverse=True)
                snapshots.append({**base, "source_channel_rows":len(positions), "canonical_hk_securities":len(combined), "equity_market_value_cny":str(equity_value),
                    "equity_nav_weight_percent_sum_rounded": str(sum(sector_weights,D(0))), "largest_holding_nav_weight_percent":str(holdings_weights[0]),
                    "top_10_holdings_nav_weight_percent":str(sum(holdings_weights[:10],D(0))), "top_3_industries_nav_weight_percent":str(sum(sector_weights[:3],D(0))),
                    "holdings_hhi_within_equity_exact_values":str(sum((D(x["market_value_cny"])/equity_value)**2 for x in combined)),
                    "industry_taxonomy": "BLOOMBERG_11_SECTOR_LABEL_CROSSWALK; historical taxonomy release not specified by issuer", "true_index_weights_qualified":False})
                all_holdings.extend({**base, **row} for row in combined)
                industry.extend({**base, **row} for row in sectors)
                for i, block in enumerate(report["blocks"]):
                    if i > 10 and any(x in compact(block) for x in ("利率风险的敏感性分析", "外汇风险的敏感性分析", "其他价格风险的敏感性分析")):
                        risks.append({**base, "one_based_page":i+1, "disclosure_text":block,
                            "interpretation": "Issuer accounting/sensitivity disclosure, not a stock-style interest-rate beta, not a causal attribution coefficient; no risk set to zero because bonds absent"})
    save(attr / "fund_holdings_snapshots.json", snapshots)
    save(attr / "historical_holdings.json", all_holdings)
    save(attr / "industry_weights.json", industry)
    save(attr / "other_risk_disclosures.json", risks)
    methods = []
    for label in ("008-930914-method", "060-H50069-official-method-v11", "061-H50069-official-legacy-method", "056-513990-2023-prospectus", "057-513990-2025-prospectus", "058-513530-2023-prospectus", "059-513530-2025-prospectus"):
        path = root / "extracted" / (label + ".json")
        if not path.exists():
            raise ValueError("method original extraction missing: " + label)
        report = read(path)
        methods.append({"source_file": "sources/" + report["source_file"], "source_sha256":source_map["sources/"+report["source_file"]]["sha256"], "extracted_file": "extracted/"+path.name,
                        "evidence_pages": [{"one_based_page":i+1,"text":t} for i,t in enumerate(report["blocks"][:3])], "exact_effective_start":None, "exact_effective_end":None})
    save(attr / "index_method_versions.json", {"indices": {"930914": {"currency":"HKD", "cny_variant":"930915", "universe":"CSI_HONG_KONG_300_INTERSECT_ELIGIBLE_HK_CONNECT", "standalone_method_label":"2024-11 V1.2", "history_status":"VERSION_EFFECTIVE_CHAIN_UNRESOLVED"}, "H50069": {"name":"上证港股通指数", "universe":"SSE_PUBLISHED_SOUTHBOUND_HK_CONNECT_SECURITIES", "standalone_method_label":"2020-12 V1.1", "history_status":"DATED_METHOD_AND_HISTORICAL_FUND_DESCRIPTIONS_PRESENT; full amendment/effective chain not attested"}},
        "sources":methods, "confirmed_source_discrepancy": "930914 2024-11 V1.2 adds past-three-year mean and latest-year payout ratio >0 and <1; 513530 prospectus dated 2025-04 still describes prior positive-dividend-only screen. Publication/content cutoff does not establish index-rule effective date.",
        "rejected_wrong_identities":["000159 is northbound Shanghai stocks, not H50069", "H11054 is equipment industry, not H50069"], "fund_holdings_are_not_true_index_weights":True})
    gaps = [
        {"id":"H04-INDEX-VERSION-EFFECTIVE-CHAIN", "impact":"Cannot assign 930914 payout/selection rule and all H50069 amendments to each historical decision date; confirmed 930914 source discrepancy", "free_source_result":"Dated official methods and historical prospectuses delivered; effective chain not established"},
        {"id":"H04-HISTORICAL-PARENT-UNIVERSE", "impact":"Cannot distinguish dividend screen from different investable universe or selection/survivorship effects", "free_source_result":"Definitions available, historical CSI HK300 and SSE Connect membership/event versions not delivered"},
        {"id":"H04-TRUE-INDEX-CONSTITUENTS-WEIGHTS", "impact":"Cannot reconstruct daily index, rebalance entry/exit and sector matched comparator; fund holdings are a disclosed proxy only", "free_source_result":"Eight actual fund snapshots delivered; zero true-index historical weight snapshots; direct generic weight link returned HTTP404"},
        {"id":"H04-INDUSTRY-CONTINUOUS-HISTORY", "impact":"Four paired snapshots cannot identify time-varying industry contribution across all 485 sessions", "free_source_result":"88 named sector observations in matching Bloomberg broad crosswalk, raw taxonomy labels retained; taxonomy release and between-snapshot changes unknown"},
        {"id":"H04-VALUE-QUALITY-RATE-EXPLANATORY-SERIES", "impact":"Value, quality and equity interest-rate sensitivity remain omitted-variable explanations; contribution unknown, not zero", "free_source_result":"Issuer market/FX/rate accounting sensitivities delivered; no qualified PIT valuation/quality factor or interest-rate attribution series"},
        {"id":"H04-HISTORICAL-INDEX-MARKET-CONTROL", "impact":"Fund TR is not an independently qualified historical market/sector index return control", "free_source_result":"No continuous index return/sector benchmark package qualified in this bounded task"}]
    save(attr / "coverage_and_unknowns.json", {"gate":"PARTIAL_WITH_NAMED_GAPS", "paired_snapshot_dates":["2024-06-30","2024-12-31","2025-06-30","2025-12-31"], "fund_snapshots":len(snapshots), "holdings_rows":len(all_holdings), "industry_rows":len(industry), "true_historical_index_weight_snapshots":0, "true_historical_parent_pool_snapshots":0,
        "optional_field_limits":["Huatai wrapped bilingual quantity/name cells not qualified in structured holdings; security identity and reported market value/weight are qualified and originals preserved. Quantity remains null, never zero or a fabricated integer.", "CMF 2024-06-30 includes HK:09930 active residual CNY506.54; not dropped or mislabeled as an index constituent."],
        "named_gaps":gaps, "missing_factor_contributions":None, "free_source_decision":"Free issuer files can fill these disclosed point-in-time product snapshots and real cash events. Tested paths have not filled continuous true index/universe and style series. Stop expanding; no evidence that all free sources are universally impossible. A larger platform is not authorized.",
        "minimum_alternative":"Owner may accept this partial product-exposure packet and preserve STOP; any descriptive two-product comparison must retain universe/style confounding and would require separate research authorization."})


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    build(args.root, args.output or args.root / "H04-TR-delivery")
