"""Independent offline receiver. Does not import the producer or SIOS."""
from __future__ import annotations

import argparse
from collections import defaultdict
import csv
from datetime import date, datetime
from decimal import Decimal, localcontext
from fractions import Fraction
import hashlib
import io
import json
from pathlib import Path
import re
import struct

D = Decimal


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def qualify(root, *, verify_pdf=True):
    errors = []
    def check(condition, label):
        if not condition and len(errors) < 100:
            errors.append(label)
    def flat(text):
        return re.sub(r"\s+", "", text)
    def close(actual, expected):
        with localcontext() as ctx:
            ctx.prec = 50
            exact = D(expected.numerator) / D(expected.denominator)
            return abs(D(actual) - exact) < D("1e-27")
    mf = read(root / "manifest.json")
    check(hashlib.sha256((root/"manifest.json").read_bytes()).hexdigest() == (root/"manifest.sha256").read_text(encoding="utf-8").split()[0], "manifest identity")
    for relative, identity in mf["files"].items():
        path = root / relative
        check(not Path(relative).is_absolute() and ".." not in Path(relative).parts, "unsafe manifest path")
        if not path.is_file():
            check(False, "missing " + relative); continue
        body = path.read_bytes()
        check(len(body) == identity["bytes"] and hashlib.sha256(body).hexdigest() == identity["sha256"], "file identity " + relative)
    check(mf["gates"]["H04_ATTRIBUTION_DATA_GATE"] == "PARTIAL_WITH_NAMED_GAPS", "attribution cannot be promoted")
    check(not mf["research_resumption_authorized"] and not mf["research_window_newly_frozen"], "scope changed")
    # These two market identities were independently recorded in the original
    # 2026-10-19 consumer contract, not generated from this exporter.
    pinned = {"513530":"ff4710cb1b78ab88afd13b67b883bc26b8255ce7d72c81b2ddaf21d37378f759", "513990":"c428e3efdd644f91266ebb192afeb39cb2d20246cc2b5ce26a8ad714f21db6b1"}
    binary = {}
    for code, expected_sha in pinned.items():
        body = (root / f"raw_sources/sh{code}.day").read_bytes()
        check(hashlib.sha256(body).hexdigest() == expected_sha, "original market changed " + code)
        check(len(body)%32 == 0, "raw alignment " + code)
        binary["SH:"+code] = list(struct.iter_unpack("<5If2I", body))
    cal_body = (root/"raw_sources/sh000001.day").read_bytes()
    sessions = [datetime.strptime(str(struct.unpack_from("<I",cal_body,i)[0]),"%Y%m%d").date().isoformat() for i in range(0,len(cal_body),32)]
    expected = [d for d in sessions if "2024-01-01" <= d <= "2025-12-31"]
    warmup = [d for d in sessions if d < "2024-01-01"][-200:]
    calendar = warmup + expected
    check(read(root/"calendar.json")["sessions"] == calendar and len(expected)==485, "independent session coverage")
    actions = read(root/"fund_actions.json")
    events = actions["events"]
    check(len(events)==7, "seven real dividends")
    check(sum((D(e["cash_per_share_cny"]) for e in events),D(0))==D("0.09"), "annual dividend reconciliation")
    used_pdfs = set()
    for event in events:
        check(event["instrument_id"] == "SH:513530" and event["status"] == "implemented", "positive event identity/status")
        doc = read(root / event["extracted_file"])
        text = flat("".join(doc["blocks"]))
        check("基金主代码513530" in text, "positive source fund identity")
        amount = re.search(r"本次分红方案.{0,25}?元/10份基金份额[）)](\d+\.\d+)", text)
        check(amount is not None and D(amount[1])/10 == D(event["cash_per_share_cny"]), "independent per-ten normalization")
        for field,label in (("announcement_date","公告送出日期："),("equity_record_date","权益登记日"),("ex_dividend_date","除息日"),("payment_date","现金红利发放日")):
            match = re.search(label+r"(\d{4})年(\d{1,2})月(\d{1,2})日",text)
            check(bool(match) and date(*map(int,match.groups())).isoformat()==event[field], "source lifecycle " + field)
        check(event["announcement_available_at"] == event["announcement_date"]+"T23:59:59+08:00", "conservative publication precision")
        check(event["cash_available_not_before"] == event["payment_date"]+"T23:59:59+08:00", "conservative cash timing")
        check(event["announcement_date"] < event["ex_dividend_date"] <= event["payment_date"], "effective lifecycle order")
        check(event["broker_actual_credit_observed_at"] is None, "unobserved broker credit cannot be invented")
        check(event["source_url"].startswith("https://www.huatai-pb.com/"), "official positive source")
        check(event["ex_dividend_date"] <= "2025-12-31", "future event contaminated input")
        for item in event["evidence"].values():
            check(item["excerpt"] in flat(doc["blocks"][item["one_based_page"]-1]), "event excerpt locator")
        used_pdfs.add(event["extracted_file"])
    check(len(actions["annual_audits"]) == 6, "six independently scoped annual audits")
    for audit in actions["annual_audits"]:
        code = audit["instrument_id"].split(":")[1]
        doc = read(root/audit["extracted_file"])
        text = flat("".join(doc["blocks"]))
        check("基金主代码"+code in text, "annual identity " + code)
        check(audit["period_start"].endswith("01-01") and audit["period_end"].endswith("12-31"), "complete fiscal audit")
        for key in ("cash_evidence", "share_evidence"):
            loc = audit[key]
            check(loc["excerpt"] in flat(doc["blocks"][loc["one_based_page"]-1]), "annual source locator")
        if code == "513990":
            check(any(x in text for x in ("本基金过去三年未进行利润分配", "本基金本报告期未进行利润分配", "本基金本报告期内未进行利润分配")), "no-event official disclosure " + code)
        check(audit["evidence_role"] == "EX_POST_COMPLETENESS_AUDIT_NOT_HISTORICAL_SIGNAL", "annual future information used as signal")
        used_pdfs.add(audit["extracted_file"])
    raw = list(csv.DictReader((root/"raw_market_data.csv").open(encoding="utf-8",newline="")))
    observations = [json.loads(line) for line in (root/"total_return_observations.jsonl").read_text(encoding="utf-8").splitlines()]
    check(len(raw)==len(observations)==1370, "1370 raw and total-return rows")
    check([(r["instrument_id"],r["date"]) for r in raw] == [(r["instrument_id"],r["date"]) for r in observations], "observation identity order")
    grouped = defaultdict(list)
    for row in raw:
        grouped[row["instrument_id"]].append(row)
        origin = binary[row["instrument_id"]][int(row["source_row_1based"])-1]
        check(row["date"].replace("-","") == str(origin[0]), "raw source date")
        check(int(row["source_byte_offset"]) == (int(row["source_row_1based"])-1)*32, "raw byte locator")
        for key,index in (("open",1),("high",2),("low",3),("close",4)):
            check(D(row[key])==D(origin[index])/1000 and int(row[key+"_int"])==origin[index], "price integer/scale " + key)
        check(int(row["volume_shares"])==origin[6] and D(row["amount_cny"])==D.from_float(origin[5]), "exact source volume/float32 amount")
        check(struct.unpack("<f",struct.pack("<I",int(row["amount_float32_bits"])))[0]==origin[5], "float32 bits")
        check(D(row["low"]) <= min(D(row["open"]),D(row["close"])) <= max(D(row["open"]),D(row["close"])) <= D(row["high"]), "OHLC ordering")
        check(origin[6]>0 and D(row["low"])-D("0.001") <= D(row["amount_cny"])/origin[6] <= D(row["high"])+D("0.001"), "independent share/CNY VWAP unit check")
        check(row["information_available_at"] == row["date"]+"T15:00:00+08:00", "raw inferred close timing")
    for instrument, rows in grouped.items():
        check([r["date"] for r in rows] == calendar, "no date shortening " + instrument)
        obs = [o for o in observations if o["instrument_id"] == instrument]
        index = Fraction(100)
        for i,(row,o) in enumerate(zip(rows,obs)):
            day = row["date"]
            value = Fraction(D(row["close"]))
            prev_bar = binary[instrument][int(row["source_row_1based"])-2]
            prev_value = Fraction(prev_bar[4],1000)
            applicable = [e for e in events if e["instrument_id"]==instrument]
            todays = [e for e in applicable if e["ex_dividend_date"]==day]
            dividend = sum((Fraction(D(e["cash_per_share_cny"])) for e in todays),Fraction(0))
            for event in todays:
                check(datetime.fromisoformat(event["announcement_available_at"]) <= datetime.fromisoformat(o["information_available_at"]), "event was not knowable at close")
            factor = (value+dividend)/prev_value
            if i:
                index *= factor
            check(close(o["gross_economic_return_factor"],factor), "economic return factor " + day)
            check(close(o["gross_ex_distribution_linked_index"],index), "independent rational linked index " + day)
            claims = sum((Fraction(D(e["cash_per_share_cny"])) for e in applicable if e["ex_dividend_date"]<=day<=e["payment_date"]),Fraction(0))
            paid = sum((Fraction(D(e["cash_per_share_cny"])) for e in applicable if e["payment_date"]<day),Fraction(0))
            check(close(o["fixed_one_share_receivable_cny"],claims) and close(o["fixed_one_share_distributed_cash_cny"],paid), "cash not posted before conservative availability " + day)
            check(close(o["fixed_one_share_wealth_cny"],value+claims+paid), "wealth conservation " + day)
            check(o["future_events_applied"] == [] and not o["latest_adjustment_factor_used"], "future factor backfill")
    attr = root/"H04-attribution-delivery"
    snapshots = read(attr/"fund_holdings_snapshots.json")
    holdings = read(attr/"historical_holdings.json")
    industries = read(attr/"industry_weights.json")
    check(len(snapshots)==8 and len(industries)==88, "eight fund / 88 sector snapshots")
    for snap in snapshots:
        key = (snap["instrument_id"],snap["observation_date"])
        h = [x for x in holdings if (x["instrument_id"],x["observation_date"])==key]
        sectors = [x for x in industries if (x["instrument_id"],x["observation_date"])==key]
        check(len({x["security_id"] for x in h})==len(h)==snap["canonical_hk_securities"], "HK route double counting")
        check(sum((D(x["market_value_cny"]) for x in h),D(0)) == sum((D(x["market_value_cny"]) for x in sectors),D(0)) == D(snap["equity_market_value_cny"]), "holdings/industry exact CNY reconciliation")
        check(snap["observation_date"] < snap["publication_date"] and not snap["historically_known_on_observation_date"], "future disclosure backfill")
        check(not snap["true_index_weights_qualified"] and snap["scope"]=="ACTUAL_FUND_HOLDINGS_NOT_INDEX_CONSTITUENTS", "fund holdings promoted to index")
        doc = read(root/snap["extracted_file"])
        text = flat("".join(doc["blocks"]))
        check("基金主代码"+snap["instrument_id"].split(":")[1] in text, "snapshot source identity")
        # Independently verify each reported sector value/weight against source
        # cells, including explicitly empty sectors rather than unknowns.
        for sector in sectors:
            label = sector["source_industry"]
            value = D(sector["market_value_cny"])
            pattern = re.escape(label) + (r"--" if value == 0 else re.escape(f"{value:,.2f}") + re.escape(sector["nav_weight_percent"]))
            check(re.search(pattern,text) is not None, "independent source sector cell " + str(key) + label)
        used_pdfs.add(snap["extracted_file"])
    gaps = read(attr/"coverage_and_unknowns.json")
    check(gaps["true_historical_index_weight_snapshots"]==0 and gaps["missing_factor_contributions"] is None and len(gaps["named_gaps"])==6, "required attribution unknowns hidden")
    methods = read(attr/"index_method_versions.json")
    check(set(methods["indices"])=={"930914","H50069"}, "actual comparator index identity")
    check(methods["indices"]["930914"]["universe"] != methods["indices"]["H50069"]["universe"], "different parent universes hidden")
    used_pdfs.update(x["extracted_file"] for x in methods["sources"])
    pdf_count = 0
    if verify_pdf:
        try:
            from pypdf import PdfReader
        except ImportError:
            check(False, "optional pypdf absent: full original-PDF validation unavailable")
        else:
            for relative in sorted(used_pdfs):
                doc = read(root/relative)
                source = root/"sources"/doc["source_file"]
                body = source.read_bytes()
                check(body.startswith(b"%PDF-"), "real PDF magic " + str(source.name))
                pages = [p.extract_text() for p in PdfReader(io.BytesIO(body)).pages]
                check(pages==doc["blocks"], "original PDF independent re-extraction " + source.name)
                pdf_count += 1
    ledger = read(root/"network_ledger.json")
    direct_bytes = sum(x["downloaded_bytes"] for x in ledger["requests"])
    check(len(ledger["requests"])+6 <= 80 and direct_bytes+3000000 <= 60000000, "conservative network reservation")
    check(all(x["downloaded_bytes"]<=15000000 for x in ledger["requests"]), "single response budget")
    # Query variants are distinct reads; direct URL attempt count bounded.
    counts = defaultdict(int)
    for item in ledger["requests"]:
        counts[item["url"]] += 1
        source = root/item["file"]
        check(source.stat().st_size==item["downloaded_bytes"] and hashlib.sha256(source.read_bytes()).hexdigest()==item["sha256"], "network original preserved")
    check(all(n<=2 for n in counts.values()), "retry budget")
    return {"schema_version":"H04-INDEPENDENT-RECEIPT-1", "integrity_and_economic_accounting_pass":not errors, "errors":errors,
            "qualified_raw_and_economic_rows":len(observations) if not errors else 0, "cash_events":len(events), "official_annual_audits":len(actions["annual_audits"]),
            "independently_reextracted_original_pdfs":pdf_count, "fund_snapshot_count":len(snapshots), "sector_observation_count":len(industries), "holding_security_snapshot_rows":len(holdings),
            "TR_gate":"PASS_FOR_CONSUMER_REVIEW" if not errors else "BLOCKED_WITH_EVIDENCE", "attribution_gate":"PARTIAL_WITH_NAMED_GAPS",
            "consumer_identity":"CHSTOCKDATA_SEPARATE_PROCESS_OFFLINE_RECEIVER; not independent SIOS acceptance", "SIOS_consumer_acceptance":"PENDING", "H04_research_resumption_authorized":False,
            "network_direct_http_requests":len(ledger["requests"]), "network_direct_body_bytes":direct_bytes, "full_stack_transport_exact_bytes":None}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("package",type=Path)
    parser.add_argument("--report",type=Path,required=True)
    args = parser.parse_args()
    report = qualify(args.package)
    args.report.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(report,ensure_ascii=False,indent=2))
    raise SystemExit(0 if report["integrity_and_economic_accounting_pass"] else 2)
