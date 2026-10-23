"""Offline, fixed-universe H01 research export. No production entry point.

The retrospective no-event reconciliation is never promoted to a PIT signal
by assigning an old timestamp to a currently captured issuer report.
"""
from __future__ import annotations

import argparse
import csv
from datetime import date, timedelta
from decimal import Decimal as D
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import struct

CODES = ("513500", "513030", "513520")
START, END = "2024-01-02", "2025-09-30"
WARMUP = 200
DAY = struct.Struct("<IIIIIfII")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def read_day(path, code):
    if path.name != f"sh{code}.day":
        raise ValueError("source identity does not match requested instrument")
    body = path.read_bytes()
    if len(body) % DAY.size:
        raise ValueError("invalid 32-byte alignment")
    rows, previous = [], None
    for index, record in enumerate(DAY.iter_unpack(body)):
        stamp, op, hi, lo, cl, amount, volume, reserved = record
        session = date.fromisoformat(f"{stamp:08d}"[:4] + "-" + f"{stamp:08d}"[4:6] + "-" + f"{stamp:08d}"[6:])
        if previous is not None and session <= previous:
            raise ValueError("source date order is not strictly increasing")
        if code in CODES and (not 0 < lo <= min(op, cl) <= max(op, cl) <= hi or not math.isfinite(amount) or amount < 0):
            raise ValueError("invalid raw OHLC or amount")
        denominator = D(1000) if code in CODES else D(100)
        rows.append({
            "date": session.isoformat(), "instrument_id": f"XSHG:{code}",
            **{name: str(D(value) / denominator) for name, value in zip(("open", "high", "low", "close"), (op, hi, lo, cl))},
            "volume": volume, "amount": str(D.from_float(amount)),
            "raw_ohlc_integers": [op, hi, lo, cl], "raw_amount_float32_hex": body[index * 32 + 20:index * 32 + 24].hex(),
            "raw_reserved": reserved, "source_record_index": index,
            "trade_status": "TRADED" if volume > 0 else "NO_TRADE_RECORDED",
            "suspension_status": "NOT_FULL_DAY_SUSPENDED" if volume > 0 else "UNKNOWN",
            "intraday_suspension_status": "UNKNOWN",
            "information_available_at": session.isoformat() + "T15:00:00+08:00",
            "availability_basis": "EXCHANGE_RULE",
            "historical_observed_vintage": "NOT_ATTESTED",
        })
        previous = session
    return rows


def window_inputs(values):
    values = list(map(D, values))
    return {
        "return_126": str(values[-1] / values[-126] - 1) if len(values) >= 126 else None,
        "sma_200": str(sum(values[-200:], D(0)) / D(200)) if len(values) >= 200 else None,
    }


def guard_no_event_input(events, cutoff_date):
    for event in events:
        if event.get("announcement_date", "") > cutoff_date:
            raise ValueError("FUTURE_INFORMATION")
        raise ValueError("REQUIRES_EVENT_QUALIFICATION: fixed export is qualified only for the verified no-event case")


def negative_evidence(report):
    blocks = [re.sub(r"\s+", "", text) for text in report["blocks"]]
    text = "".join(blocks)
    cash_patterns = (
        "3.3过去三年基金的利润分配情况无。", "本基金过去三年无利润分配事项",
        "本报告期内本基金未进行收益分配", "本基金本报告期未进行利润分配",
    )
    cash_hit = next((p for p in cash_patterns if any(p in block for block in blocks)), None)
    split_hit = "本报告期基金拆分变动份额-"
    if cash_hit is None or split_hit not in text:
        raise ValueError("issuer report does not establish the necessary negative event facts")
    def locator(phrase):
        hits = []
        for i, block in enumerate(blocks):
            pos = block.find(phrase)
            if pos >= 0:
                hits.append({"kind": report["locator_kind"], "one_based_index": i + 1,
                             "excerpt": block[max(0, pos - 25):pos + len(phrase) + 70]})
        return hits
    return {"cash_status": "normal_empty", "split_status": "normal_empty",
            "cash_evidence": locator(cash_hit), "split_evidence": locator(split_hit),
            "usage": "EX_POST_FACT_RECONCILIATION_ONLY_NOT_HISTORICAL_SIGNAL_INFORMATION"}


def prepare(package, captures, vipdoc):
    package.mkdir(parents=True, exist_ok=True)
    for name in ("sources", "extracted"):
        shutil.copytree(captures / name, package / name, dirs_exist_ok=True)
    shutil.copy2(captures / "network_ledger.json", package / "network_ledger.json")
    shutil.copy2(captures / "context.json", package / "context.json")
    shutil.copytree(captures / "contracts", package / "contracts", dirs_exist_ok=True)
    source_dir = package / "raw_sources"
    source_dir.mkdir(exist_ok=True)
    for code in (*CODES, "000001"):
        shutil.copy2(vipdoc / "sh/lday" / f"sh{code}.day", source_dir / f"sh{code}.day")
    original = load_json(vipdoc / "manifest.json")
    write_json(package / "raw_source_manifest.json", {
        **{k: original[k] for k in ("downloaded_at", "source_url", "source_last_modified", "zip_sha256")},
        "original_manifest_sha256": digest((vipdoc / "manifest.json").read_bytes()),
        "selected_codes": list(CODES), "calendar_only_code": "000001",
        "calendar_reference_is_not_an_added_H01_security": True,
    })


def build(package):
    ledger = load_json(package / "network_ledger.json")
    context = load_json(package / "context.json")
    source_meta = load_json(package / "raw_source_manifest.json")
    all_calendar = read_day(package / "raw_sources/sh000001.day", "000001")
    calendar = [r["date"] for r in all_calendar]
    warmup = [d for d in calendar if d < START][-WARMUP:]
    observed = [d for d in calendar if START <= d <= END]
    if len(warmup) != WARMUP:
        raise ValueError("insufficient independent warmup")
    required = warmup + observed
    annuals, envelopes = [], []
    publications = {
        "513500": {"2023": "2024-03-29", "2024": "2025-03-31", "2025": "2026-03-31"},
        "513030": {"2023": "2024-03-27", "2024": "2025-03-31", "2025": "2026-03-31"},
        "513520": {"2023": "2024-03-28", "2024": "2025-03-31", "2025": "2026-03-31"},
    }
    for entry in ledger["requests"]:
        if not entry["label"].endswith("-official-annual"):
            continue
        code, year = entry["label"].split("-")[:2]
        parsed = load_json(package / "extracted" / (Path(entry["file"]).stem + ".json"))
        evidence = negative_evidence(parsed)
        annuals.append({"instrument_id": f"XSHG:{code}", "period_start": year + "-01-01", "period_end": year + "-12-31",
                        "published_date": publications[code][year], "published_at": None,
                        "captured_at": entry["completed_at"], "source_file": entry["file"],
                        "source_sha256": entry["sha256"], "source_url": entry["url"], **evidence})
    for code in CODES:
        if {e["period_start"][:4] for e in annuals if e["instrument_id"] == f"XSHG:{code}"} != {"2023", "2024", "2025"}:
            raise ValueError("annual evidence does not cover the entire fixed window")
        f10 = next(e for e in ledger["requests"] if e["label"] == code + "-fhsp" and e["status"] == "success")
        html = (package / f10["file"]).read_text(encoding="utf-8")
        if "暂无分红信息" not in html or "cfxq" not in html:
            raise ValueError("F10 no-event corroboration no longer applies")
        envelopes.append({"instrument_id": f"XSHG:{code}", "status": "normal_empty", "coverage": "complete_ex_post_implemented_event_facts",
                          "items": [], "f10_source_file": f10["file"], "f10_source_sha256": f10["sha256"],
                          "implemented_cash_events": 0, "split_events": 0,
                          "cancelled_or_proposed_index_coverage": "UNKNOWN_NOT_NEEDED_FOR_ZERO_IMPLEMENTED_ACTION_FACTS",
                          "historical_asof_event_index_coverage": "NOT_ATTESTED",
                          "economic_entitlement_at": None, "actual_cash_payment_at": None,
                          "backtest_cash_available_at": None, "cash_timing_applicability": "NOT_APPLICABLE_NO_IMPLEMENTED_CASH_EVENT"})
    guard_no_event_input([], END)
    write_json(package / "fund_actions.json", {"events": [], "per_instrument": envelopes, "issuer_report_evidence": annuals})
    rows, observations, coverage, gaps = [], [], {}, []
    for code in CODES:
        path = package / "raw_sources" / f"sh{code}.day"
        original = read_day(path, code)
        selected = [r for r in original if r["date"] in required]
        missing = sorted(set(required) - {r["date"] for r in selected})
        if missing:
            raise ValueError(f"missing raw dates for {code}: {missing}")
        values = []
        for row in selected:
            row.update({"row_id": f"XSHG:{code}/{row['date']}", "source_file": f"raw_sources/sh{code}.day",
                        "source_sha256": digest(path.read_bytes()), "source_retrieved_at": source_meta["downloaded_at"],
                        "price_unit": "CNY_PER_SHARE", "volume_unit": "SHARE", "amount_unit": "CNY",
                        "adjustment_mode": "RAW", "is_warmup": row["date"] < START})
            if row["volume"] > 0:
                vwap = D(row["amount"]) / D(row["volume"])
                if not D(row["low"]) - D("0.001") <= vwap <= D(row["high"]) + D("0.001"):
                    raise ValueError("amount/volume units fail OHLC reconciliation")
            elif D(row["amount"]) != 0:
                raise ValueError("zero volume with nonzero amount")
            index = D(100) * D(row["close"]) / D(selected[0]["close"])
            values.append(str(index))
            inputs = window_inputs(values)
            n = len(values)
            reasons = ["HISTORICAL_EVENT_ASOF_COVERAGE_NOT_ATTESTED"]
            if any(r["volume"] == 0 for r in selected[max(0, n - 200):n]):
                reasons.append("NO_TRADE_OBSERVATION_ELIGIBILITY_UNKNOWN")
            observations.append({"row_id": row["row_id"], "instrument_id": row["instrument_id"], "date": row["date"],
                "raw_row_id": row["row_id"], "is_warmup": row["is_warmup"],
                "retrospective_no_event_index": str(index), "retrospective_return_126": inputs["return_126"],
                "retrospective_sma_200": inputs["sma_200"], "return_126_base_date": selected[n - 126]["date"] if n >= 126 else None,
                "sma_200_start_date": selected[n - 200]["date"] if n >= 200 else None,
                "event_ids_applied": [], "cash_adjustment": "0", "share_multiplier": "1",
                "pit_total_return_index": None, "pit_return_126": None, "pit_sma_200": None,
                "pit_signal_qualified": False, "information_available_at": None,
                "unqualified_reason_codes": reasons,
                "raw_availability_basis": "EXCHANGE_RULE", "issuer_reports_used_as_signal_input": False})
            rows.append(row)
        gap = {"id": f"H01-{code}-EVENT-ASOF", "classification": "UNRESOLVED_RISK", "instrument_id": f"XSHG:{code}",
               "event_date": None, "kind": "HISTORICAL_EVENT_ASOF_COVERAGE_NOT_ATTESTED",
               "missing_fields": ["historical_asof_event_coverage", "historical_first_known_or_version_evidence"],
               "fact_scope": "No missing dividend amount or named implemented event is asserted; issuer reports establish zero implemented events ex post.",
               "affected_signal_dates": observed, "affected_input_start": warmup[0], "affected_input_end": END,
               "affected_inputs": ["126_OBSERVATION_TOTAL_RETURN", "SMA200_TOTAL_RETURN"],
               "why": "Current F10 snapshots and later annual reports authenticate historical facts, but do not themselves attest the event index available at each historical cutoff. Raw EXCHANGE_RULE is retained; it is not extended to retrospective report content."}
        gaps.append(gap)
        zero_days = [r["date"] for r in selected if r["volume"] == 0]
        coverage[code] = {"raw_rows": len(selected), "warmup_rows": WARMUP, "observation_rows": len(observed),
                          "missing_dates": missing, "zero_turnover_dates": zero_days, "raw_source_first": original[0]["date"],
                          "raw_source_last": original[-1]["date"], "raw_source_sha256": digest(path.read_bytes()),
                          "cash_event_facts": "normal_empty_verified_ex_post", "split_event_facts": "normal_empty_verified_ex_post",
                          "retrospective_inputs_complete": True, "qualified_pit_signal_rows": 0}
        for zero in zero_days:
            pos = required.index(zero)
            gaps.append({"id": f"H01-{code}-{zero}-NO-TRADE", "classification": "UNRESOLVED_RISK", "instrument_id": f"XSHG:{code}",
                "event_date": zero, "kind": "ZERO_TURNOVER_REASON_AND_SIGNAL_OBSERVATION_ELIGIBILITY",
                "missing_fields": ["official_full_day_suspension_reason", "consumer_no_trade_signal_observation_policy"],
                "affected_return_126_dates": [d for i,d in enumerate(required) if START <= d <= END and pos <= i <= pos + 125],
                "affected_sma_200_dates": [d for i,d in enumerate(required) if START <= d <= END and pos <= i <= pos + 199],
                "why": "An actual vendor bar is retained, with zero amount and volume; no fabricated traded close, missing-day fill, or suspension assertion."})
    with (package / "raw_market_data.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        for row in rows:
            writer.writerow({**row, "raw_ohlc_integers": json.dumps(row["raw_ohlc_integers"])})
    (package / "total_return_observations.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in observations), encoding="utf-8")
    first, last = date.fromisoformat(required[0]), date.fromisoformat(END)
    days = []
    for i in range((last - first).days + 1):
        day = (first + timedelta(days=i)).isoformat()
        days.append({"date": day, "is_exchange_session": day in required,
                     "classification": "SESSION_IN_LOCAL_INDEX" if day in required else "CLOSED_IN_LOCAL_INDEX_CALENDAR",
                     "classification_basis": "LOCAL_TDX_SH000001_SESSION_DATES", "official_calendar_vintage": "NOT_ATTESTED"})
    write_json(package / "calendar.json", {"sessions": required, "days": days, "source_sha256": digest((package / "raw_sources/sh000001.day").read_bytes())})
    write_json(package / "coverage_and_unknowns.json", {"securities": list(CODES), "observation_start": START, "observation_end": END,
        "warmup_start": warmup[0], "warmup_end": warmup[-1], "required_prior_observations": WARMUP,
        "return_rule": "126 observations, current / observation[-126] - 1 (125 intervals)",
        "sma_rule": "arithmetic mean of latest 200 observations, including current",
        "per_instrument": coverage, "unresolved_required_gaps": gaps,
        "acceptance": "BLOCKED_WITH_NAMED_GAPS", "production_adapter_integrated": False})
    semantic_failures = []
    for entry in ledger["requests"]:
        body = (package / entry["file"]).read_bytes()
        if body.startswith(b"<script>") and "annual" in entry["label"]:
            semantic_failures.append({"request_id": entry["id"], "kind": "ACCESS_CHALLENGE_NOT_PDF"})
        elif body.startswith(b"{"):
            payload = json.loads(body)
            if payload.get("ErrCode", 0) != 0:
                semantic_failures.append({"request_id": entry["id"], "kind": "UPSTREAM_ERROR", "upstream_code": payload["ErrCode"]})
            elif "data" in payload and (payload["data"] is None or isinstance(payload["data"], dict) and payload["data"].get("list") == []):
                semantic_failures.append({"request_id": entry["id"], "kind": "EMPTY_INDEX_NOT_COVERAGE_PROOF"})
    write_json(package / "provenance.json", {"raw": source_meta, "context": context,
        "network": {"attempted_requests": len(ledger["requests"]), "downloaded_bytes": sum(e["downloaded_bytes"] for e in ledger["requests"]),
                    "transport_successes": sum(e["status"] == "success" for e in ledger["requests"]),
                    "transport_failures": sum(e["status"] in {"request_error", "http_error"} for e in ledger["requests"]),
                    "redirects": sum(e["status"] == "redirect" for e in ledger["requests"]), "semantic_failures": semantic_failures},
        "pit": {"raw_basis": "FROZEN_CONSUMER_EXCHANGE_RULE_15_00_ASIA_SHANGHAI", "raw_observed_vintage": "NOT_ATTESTED",
                "event_fact_reconciliation": "VERIFIED_EX_POST_ONLY", "historical_event_asof_coverage": "NOT_ATTESTED"},
        "units": {"prices": "original uint32 / 1000 CNY/share", "volume": "original uint32 SHARE", "amount": "exact original float32 CNY"}})
    write_json(package / "schema.json", {"schema_version": "sios-h01-research-v1", "csv": {k: type(v).__name__ for k,v in rows[0].items()},
        "jsonl": {k: (type(v).__name__ if v is not None else "nullable") for k,v in observations[0].items()},
        "nullable_pit_fields": ["pit_total_return_index", "pit_return_126", "pit_sma_200", "information_available_at"],
        "event_status_enum": ["implemented", "cancelled", "proposed", "unknown"],
        "empty_events_mean": "Only authenticated zero implemented distributions/splits; not complete historical proposal/cancellation index",
        "retrospective_values_are_accepted_pit_signals": False, "decimal_fields": "lossless decimal strings; JSON null is never zero",
        "warmup": "200 observations strictly before 2024-01-02", "signal_use_requires": "pit_signal_qualified == true"})
    manifest = {"schema_version": "sios-h01-research-v1", "verdict": "H01_PARTIAL_DELIVERY_WITH_NAMED_GAPS",
                "gate": "BLOCKED_WITH_NAMED_GAPS", "securities": list(CODES), "observation_window": [START, END],
                "raw_rows": len(rows), "retrospective_observation_rows": len(observations), "qualified_pit_signal_rows": 0,
                "files": {}}
    for path in sorted(package.rglob("*")):
        if path.is_file() and path.name not in {"manifest.json", "manifest.sha256", "validation_report.json"} and "__pycache__" not in path.parts:
            manifest["files"][path.relative_to(package).as_posix()] = {"sha256": digest(path.read_bytes()), "bytes": path.stat().st_size}
    write_json(package / "manifest.json", manifest)
    (package / "manifest.sha256").write_text(digest((package / "manifest.json").read_bytes()) + "  manifest.json\n", encoding="utf-8")
    print(json.dumps({k:v for k,v in manifest.items() if k != "files"}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--capture-root", type=Path)
    parser.add_argument("--vipdoc-root", type=Path)
    args = parser.parse_args()
    if args.capture_root and args.vipdoc_root:
        prepare(args.package, args.capture_root, args.vipdoc_root)
    build(args.package)
