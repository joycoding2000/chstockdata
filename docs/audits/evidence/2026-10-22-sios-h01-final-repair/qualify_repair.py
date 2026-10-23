"""Fixed-scope H01 offline qualification repair; no strategy execution."""
from __future__ import annotations

import ast
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
import hashlib
import re


def audit_report(report, instrument, expected_year):
    blocks = [re.sub(r"\s+", "", block) for block in report["blocks"]]
    text = "".join(blocks)
    code = instrument.split(":")[1]
    if not re.search(r"基金主代码" + re.escape(code) + r"(?!\d)", text):
        raise ValueError("EVENT_IDENTITY_AMBIGUOUS: report fund code does not match")
    period = re.search(r"本报告期自(\d{4})年(\d{1,2})月(\d{1,2})日起?至(?:(\d{4})年)?(\d{1,2})月(\d{1,2})日止", text)
    if period is None:
        raise ValueError("SOURCE_COVERAGE_INCOMPLETE: no explicit report period")
    year, month, day, end_year, end_month, end_day = period.groups()
    start = date(int(year), int(month), int(day))
    end = date(int(end_year or year), int(end_month), int(end_day))
    if start.year != expected_year or end.year != expected_year:
        raise ValueError("SOURCE_COVERAGE_INCOMPLETE: unexpected fiscal period")
    cash_patterns = ("3.3过去三年基金的利润分配情况无。", "本基金过去三年无利润分配事项", "本报告期内本基金未进行收益分配", "本基金本报告期未进行利润分配")
    cash = next((p for p in cash_patterns if p in text), None)
    split = "本报告期基金拆分变动份额-"
    if cash is None or split not in text:
        raise ValueError("SOURCE_COVERAGE_INCOMPLETE: missing explicit negative event disclosure")
    def locate(phrase):
        for index in range(len(blocks)):
            # A Word heading and its conclusion may occupy adjacent blocks.
            span = "".join(blocks[index:index + 2])
            pos = span.find(phrase)
            if pos >= 0:
                return {"kind": report["locator_kind"], "one_based_index": index + 1,
                        "max_blocks": 2, "excerpt": span[max(0, pos - 20):pos + len(phrase) + 80]}
        raise ValueError("negative disclosure is not locatable")
    sensitivity = [{"one_based_index": i + 1, "context": match.group(0)} for i, block in enumerate(blocks)
                   for match in re.finditer(r".{0,25}(?:份额折算|份额合并|基金拆分).{0,80}", block)]
    return {"instrument_id": instrument, "period_start": start.isoformat(), "period_end": end.isoformat(),
            "cash_absent": True, "holder_unit_change_absent": True,
            "source_status": "AUTHENTICATED_OFFICIAL_REPORT", "cash_evidence": locate(cash),
            "holder_unit_evidence": locate(split), "share_change_contexts": sensitivity,
            "ordinary_subscriptions_redemptions_are_holder_unit_changes": False,
            "scope": "Implemented fund cash distributions and holder-unit-changing splits/conversions within the stated fiscal period; not a complete cancelled/proposed announcement index"}


def certify_interval(reports, instrument, start, end):
    result = {"instrument_id": instrument, "interval": [start, end], "evidence_role": "EX_POST_COMPLETENESS_AUDIT",
              "historical_input_events": [], "status": "SOURCE_COVERAGE_INCOMPLETE"}
    if any(r.get("instrument_id") != instrument for r in reports):
        return {**result, "status": "EVENT_IDENTITY_AMBIGUOUS"}
    if any(r.get("source_status") == "SOURCE_ACCESS_FAILED" for r in reports):
        return {**result, "status": "SOURCE_ACCESS_FAILED"}
    if not reports or any(r.get("source_status") != "AUTHENTICATED_OFFICIAL_REPORT" for r in reports):
        return result
    cursor, final = date.fromisoformat(start), date.fromisoformat(end)
    for record in sorted(reports, key=lambda r: r["period_start"]):
        low, high = date.fromisoformat(record["period_start"]), date.fromisoformat(record["period_end"])
        if low > cursor:
            return result
        if high >= cursor:
            cursor = high + timedelta(days=1)
    if cursor <= final:
        return result
    if any(not r.get("cash_absent") or not r.get("holder_unit_change_absent") for r in reports):
        events = [e for r in reports for e in r.get("positive_events", [])]
        complete = bool(events) and all(
            e.get("source_identifier") and e.get("status") == "implemented" and e.get("effective_date")
            and e.get("announcement_date") and e["announcement_date"] <= e["effective_date"]
            and ((e.get("share_ratio") and e.get("ratio_unit") == "NEW_SHARES_PER_OLD_SHARE")
                 or (e.get("cash_per_old_share") and e.get("cash_unit") == "CNY_PER_OLD_SHARE"))
            for e in events
        )
        return {**result, "status": "QUALIFIED_POSITIVE_EVENT" if complete else "EVENT_IDENTITY_AMBIGUOUS", "historical_input_events": events}
    return {**result, "status": "CONFIRMED_NO_EVENT_IN_SCOPE", "audit_report_count": len(reports),
            "publication_date_is_not_a_historical_signal_input": True}


def trace_observation_policy(contracts):
    engine = (contracts / "consumer-engine.py").read_text(encoding="utf-8")
    strategy = (contracts / "consumer-etf_relative_momentum.py").read_text(encoding="utf-8")
    market = (contracts / "consumer-market.py").read_text(encoding="utf-8")
    def function(source, name):
        return next(n for n in ast.walk(ast.parse(source)) if isinstance(n, ast.FunctionDef) and n.name == name)
    bars = function(engine, "bars_for")
    known = function(engine, "_known_bars_through")
    forbidden = {"volume", "amount", "tradability", "suspended"}
    attrs = {n.attr for fn in (bars, known) for n in ast.walk(fn) if isinstance(n, ast.Attribute)}
    if attrs & forbidden or "recorded zero volume/amount is a genuine zero" not in market or "context.bars_for(instrument_id)" not in strategy:
        return {"policy": "UNRESOLVED_REQUIRES_OWNER", "consumer_executed": False}
    return {"policy": "INCLUDE_KNOWN_REPORTED_DAILY_BAR", "consumer_executed": False,
            "references": {"consumer-engine.py": [bars.lineno, known.lineno], "consumer-etf_relative_momentum.py": [117, 120, 140, 141], "consumer-market.py": [164, 211]},
            "contract_sha256": {name: hashlib.sha256((contracts / name).read_bytes()).hexdigest()
                                 for name in ("consumer-engine.py", "consumer-etf_relative_momentum.py", "consumer-market.py")},
            "scope": "Existing known DailyBar observations include a genuine reported zero-turnover bar. Tradability is a separate contract; no strategy or calendar rule is changed."}


def classify_observation(row, previous_close, halt):
    if row is None:
        return {"status": "MISSING_REPORTED_BAR_DURING_VERIFIED_SUSPENSION" if halt and halt.get("verified") else "DATA_MISSING",
                "signal_observation_eligible": False, "valuation_close": previous_close, "tradable": False}
    known_halt = bool(halt and halt.get("verified") and halt["instrument_id"] == row["instrument_id"] and halt["date"] == row["date"])
    quantity, amount = Decimal(str(row["volume"])), Decimal(str(row["amount"]))
    if known_halt:
        if quantity != 0 or amount != 0:
            raise ValueError("SUSPENSION_TURNOVER_CONFLICT")
        if Decimal(row["close"]) != Decimal(previous_close):
            raise ValueError("SUSPENDED_PRICE_REFERENCE_MISMATCH")
        return {"status": "VERIFIED_FULL_DAY_SUSPENSION", "signal_observation_eligible": True,
                "valuation_close": row["close"], "valuation_basis": "EXISTING_REPORTED_BAR_EQUALS_PRIOR_CLOSE", "tradable": False}
    if quantity == 0:
        return {"status": "UNCLASSIFIED_ZERO_TURNOVER", "signal_observation_eligible": False, "valuation_close": row["close"], "tradable": False}
    return {"status": "TRADED", "signal_observation_eligible": True, "valuation_close": row["close"], "tradable": None}


def guard_event(event, cutoff):
    if event.get("status") in {"cancelled", "proposed"}:
        return None
    if event.get("status") != "implemented" or not event.get("announcement_date"):
        raise ValueError("EVENT_IDENTITY_AMBIGUOUS")
    declared = event.get("available_at")
    available = datetime.fromisoformat(declared) if declared else datetime.combine(date.fromisoformat(event["announcement_date"]), time(23, 59, 59), timezone(timedelta(hours=8)))
    if available.tzinfo is None or cutoff.tzinfo is None:
        raise ValueError("EVENT_IDENTITY_AMBIGUOUS: timezone required")
    if available > cutoff:
        raise ValueError("FUTURE_INFORMATION")
    return {"published_at": declared, "source_time_precision": "datetime" if declared else "date",
            "derived_information_available_at": available.isoformat(),
            "availability_basis": "OBSERVED" if declared else "INFERRED_DATE_END_EXISTING_CONSUMER_RULE"}


def promote_observation(observation, raw, certification, eligible):
    qualified = certification["status"] == "CONFIRMED_NO_EVENT_IN_SCOPE" and eligible
    values = {"pit_total_return_index": observation["retrospective_no_event_index"],
              "pit_return_126": observation["retrospective_return_126"], "pit_sma_200": observation["retrospective_sma_200"]}
    return {**observation, **{key: value if qualified else None for key, value in values.items()},
            "pit_signal_qualified": qualified, "information_available_at": raw["information_available_at"] if qualified else None,
            "return_126_qualified": qualified and values["pit_return_126"] is not None,
            "sma_200_qualified": qualified and values["pit_sma_200"] is not None,
            "unqualified_reason_codes": [] if qualified else [certification["status"] if certification["status"] != "CONFIRMED_NO_EVENT_IN_SCOPE" else "OBSERVATION_POLICY_UNRESOLVED"],
            "issuer_reports_used_as_signal_input": False, "no_event_audit_used_for_data_quality_certification": True,
            "information_lineage": "HISTORICAL_RAW_PRICE; NO_IMPLEMENTED_HOLDER_ACTION_IN_CERTIFIED_SCOPE",
            "qualification_status": certification["status"]}
