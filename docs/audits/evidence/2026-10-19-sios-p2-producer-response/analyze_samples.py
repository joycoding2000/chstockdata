"""Offline sample export/check, deliberately not a production exporter."""
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path

from probe_history import BASE, CONTRACTS, DATES, digest, dump

LIVE = BASE / "live"
FIELD_MAP = {
    "open": ("OPENPRICE", "o"), "high": ("HIGHESTPRICE", "h"),
    "low": ("LOWESTPRICE", "l"), "close": ("CLOSEPRICE", "c"),
    "settlement": ("SETTLEMENTPRICE", "s"), "volume": ("VOLUME", "v"),
    "open_interest": ("OPENINTEREST", "p"),
}
META_FIELDS = ("listed_date", "last_trade_date", "contract_multiplier", "tick_size", "historical_rule_version", "natural_person_exit_rule")


def number(value):
    try:
        return Decimal(str(value)) if str(value).strip() else None
    except InvalidOperation:
        return None


def flags(row):
    result = []
    for key in FIELD_MAP:
        value = number(row[key])
        if value is None:
            result.append("MISSING_OR_INVALID_" + key.upper())
        elif value < 0 or (value == 0 and key not in ("volume", "open_interest")):
            result.append("NONPOSITIVE_" + key.upper())
    return result


def save_csv(path, rows, fields=None):
    with path.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields or list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    with path.open(encoding="utf-8", newline="") as handle:
        assert len(list(csv.DictReader(handle))) == len(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-label", default="analysis")
    args = parser.parse_args()
    out = BASE / args.output_label
    out.mkdir(exist_ok=True)
    if any(out.iterdir()):
        raise FileExistsError("Refusing to overwrite analysis artifacts")
    requests = json.loads((LIVE / "requests.json").read_text(encoding="utf-8"))
    by_name = {r["name"]: r for r in requests}
    for record in requests:
        if "raw_file" in record:
            assert digest((LIVE / record["raw_file"]).read_bytes()) == record["sha256"]
    exports, official, shfe_summary, sina_summary, anomalies, anchors, comparisons = [], {}, [], [], [], [], []

    def normalize(source, contract, day, values, published="UNKNOWN"):
        match = re.fullmatch(r"(RB|BU|CS|PP|C)(\d{2})(\d{2})", contract)
        assert match is not None
        product, year, month = match.groups()
        assert 1 <= int(month) <= 12
        record = by_name[source + "_" + (day.replace("-", "") if source == "shfe" else contract)]
        row = {
            "source": source, "exchange": "SHFE" if product in ("RB", "BU") else "DCE",
            "product": product, "contract_id": contract, "trade_date": day,
            "delivery_month": "20" + year + "-" + month,
            **values, "price_unit": "CNY_PER_TONNE_DOCUMENTED_CURRENT" if source == "shfe" else "UNKNOWN",
            "volume_unit": "LOTS_SINGLE_SIDED_DOCUMENTED_CURRENT" if source == "shfe" else "UNKNOWN",
            "open_interest_unit": "LOTS_SINGLE_SIDED_DOCUMENTED_CURRENT" if source == "shfe" else "UNKNOWN",
            "unit_history_status": "UNVERIFIED", "published_at_source": published,
            "published_at_semantics": "SOURCE_UPDATE_TIME_NOT_FIRST_PUBLICATION" if published != "UNKNOWN" else "UNKNOWN",
            "retrieved_at": record["completed_at"], "first_available_at": "UNKNOWN",
            "revision_status": "UNKNOWN", "pit_status": "PIT_INFERRED/UNVERIFIED",
            "source_sha256": record["sha256"],
            **{field: "UNKNOWN" for field in META_FIELDS},
            "quality_flags": "",
        }
        row["quality_flags"] = "|".join(flags(row)) or "NO_FIELD_VALUE_FLAGS_IN_SAMPLE"
        return row

    for day in ("20200102", *DATES):
        data = json.loads((LIVE / ("shfe_" + day + ".raw")).read_bytes())
        assert str(data["report_date"]) == day and int(data["o_code"]) == 0
        months = {product: [] for product in ("RB", "BU")}
        for item in data["o_curinstrument"]:
            product = item.get("PRODUCTGROUPID", "").strip().upper()
            if not product:
                product = item.get("PRODUCTID", "").strip().split("_", 1)[0].upper()
            month = str(item.get("DELIVERYMONTH", "")).strip()
            if product not in months or not re.fullmatch(r"\d{4}", month):
                continue
            contract = product + month
            months[product].append(contract)
            date = day[:4] + "-" + day[4:6] + "-" + day[6:]
            row = normalize("shfe", contract, date, {field: item[keys[0]] for field, keys in FIELD_MAP.items()}, data["update_date"])
            official[(contract, date)] = row
            exports.append(row)
        assert all(months.values()), "Expected target products absent; do not classify parser loss as normal empty"
        shfe_summary.append({"date": day, "raw_rows": len(data["o_curinstrument"]), "update_date": data["update_date"], "months": months, "counts": {k: len(v) for k, v in months.items()}, "product_identity_field": "PRODUCTGROUPID" if "PRODUCTGROUPID" in data["o_curinstrument"][0] else "PRODUCTID_PREFIX"})

    for day, contracts in CONTRACTS.items():
        date = day[:4] + "-" + day[4:6] + "-" + day[6:]
        for contract in contracts:
            text = (LIVE / ("sina_" + contract + ".raw")).read_text(encoding="utf-8")
            marker = "var _V21052021_4_12=("
            assert text.count(marker) == 1 and text.rstrip().endswith(");")
            body = text.split(marker, 1)[1].rstrip()[:-2]
            data = json.loads(body)
            assert isinstance(data, list) and data
            window = [r for r in data if "2020-01-01" <= r["d"] <= "2025-12-31"]
            selected = [r for r in data if r["d"] == date]
            assert len(selected) == 1
            row = normalize("sina", contract, date, {field: selected[0][keys[1]] for field, keys in FIELD_MAP.items()})
            exports.append(row)
            anchors.append({k: row[k] for k in ("trade_date", "contract_id", *FIELD_MAP, "quality_flags")})
            bad = [r for r in window if number(r.get("s")) is None or number(r.get("s")) <= 0]
            sina_summary.append({"contract": contract, "raw_rows": len(data), "raw_start": data[0]["d"], "raw_end": data[-1]["d"], "in_scope_rows": len(window), "nonpositive_or_missing_settlement_in_scope": len(bad), "nonpositive_by_year": dict(Counter(r["d"][:4] for r in bad)), "duplicate_dates": sum(n - 1 for n in Counter(r["d"] for r in data).values() if n > 1)})
            anomalies.extend({"contract_id": contract, "trade_date": r["d"], "settlement_raw": r["s"], "close_raw": r["c"], "flag": "NONPOSITIVE_OR_MISSING_SETTLEMENT_NO_REPAIR"} for r in bad)
            if (contract, date) in official:
                for field in FIELD_MAP:
                    lhs, rhs = official[(contract, date)][field], row[field]
                    comparisons.append({"contract_id": contract, "trade_date": date, "field": field, "shfe_raw": lhs, "sina_raw": rhs, "equal_numeric": number(lhs) == number(rhs)})

    keys = [(r["source"], r["exchange"], r["contract_id"], r["trade_date"]) for r in exports]
    assert len(keys) == len(set(keys))
    save_csv(out / "daily_sample.csv", exports)
    save_csv(out / "sina_settlement_anomalies.csv", anomalies)
    save_csv(out / "shfe_sina_crosscheck.csv", comparisons)
    save_csv(out / "anchor_rows.csv", anchors)
    summary = {
        "not_a_consumer_ready_bundle": True,
        "request_count_live": len(requests), "http_success": sum(r["outcome"] == "HTTP_SUCCESS_UNVALIDATED" for r in requests),
        "dce_official_outcomes": [r for r in requests if r["name"].startswith("dce_")],
        "shfe": shfe_summary, "sina": sina_summary, "anchors": anchors,
        "export_rows": len(exports), "source_aware_unique_rows": len(set(keys)),
        "shfe_sina_comparison_fields": len(comparisons), "shfe_sina_equal_fields": sum(r["equal_numeric"] for r in comparisons),
        "mismatches": [r for r in comparisons if not r["equal_numeric"]],
        "sina_anomaly_rows_in_scope": len(anomalies),
        "full_2020_2025_coverage": "NOT_TESTED", "dce_all_month_universe": "UNVERIFIED", "metadata_history": "UNVERIFIED",
        "checks": {"raw_sha256": "PASS", "sample_trade_dates": "PASS", "source_aware_uniqueness": "PASS", "csv_roundtrip_row_count": "PASS"},
    }
    dump(out / "sample_summary.json", summary)
    print(json.dumps({k: summary[k] for k in ("export_rows", "shfe_sina_comparison_fields", "shfe_sina_equal_fields", "sina_anomaly_rows_in_scope", "checks")}, ensure_ascii=True))


if __name__ == "__main__":
    main()
