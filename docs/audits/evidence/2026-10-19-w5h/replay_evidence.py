"""Offline examination of real W5-H responses; not a collector or PIT implementation."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

from lxml import html

BASE = Path(__file__).resolve().parent


def load(name):
    return json.loads((BASE / name).read_bytes())


class Response:
    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload

    def raise_for_status(self):
        return None


def main():
    from chstockdata import a_stock
    from chstockdata.point_in_time import filter_financial_records

    result = {"network_calls": 0, "financial": {}, "valuation": {}, "public_api_replay": {}}
    for source, field in (("lrb", "营业收入"), ("llb", "经营活动产生的现金流量净额")):
        payload = load(f"sina_600518_{source}.json")
        data = payload["result"]["data"]
        raw = data["report_list"]["20171231"]
        value = next(x["item_value"] for x in raw["data"] if x["item_title"] == field)
        dates = {}
        record = {"end_date": "20171231", "publish_date": raw["publish_date"], field: value}
        for cutoff in ("2018-04-24", "2018-04-27", "2019-05-06"):
            visible, excluded = filter_financial_records([record], cutoff, source="sina", historical_review=True)
            dates[cutoff] = {"visible": visible, "excluded": excluded}
        result["financial"][source] = {
            "report_count": data["report_count"], "returned_periods": len(data["report_list"]),
            "first_period": min(data["report_list"]), "last_period": max(data["report_list"]),
            "same_period_keys": [k for k in data["report_list"] if "20171231" in k],
            "metadata": {k: v for k, v in raw.items() if k != "data"},
            "update_time_interpretation_if_unix_seconds": datetime.fromtimestamp(
                raw["update_time"], timezone(timedelta(hours=8))).isoformat(),
            "field": field, "value": value, "visibility_of_actual_current_row": dates,
        }
        with patch.object(a_stock, "_source_http_get", return_value=Response(payload)):
            func = a_stock.get_income_statement if source == "lrb" else a_stock.get_cashflow
            text = func("600518", curr_date="2019-05-06", historical_review=True)
            (BASE / f"public_{source}_replay.txt").write_text(text, encoding="utf-8")
        result["public_api_replay"][source] = {
            "input": "captured 60-period response, not the public API's default 20-period fetch",
            "output_type": type(text).__name__, "contains_target_period": "2017-12-31" in text,
            "contains_target_value": value in text,
        }

    original = html.fromstring((BASE / "original_2017.html").read_bytes())
    correction = html.fromstring((BASE / "correction_2019.html").read_bytes())
    result["disclosure"] = {
        "original_date_present": "公告日期:2018-04-26" in original.text_content(),
        "correction_date_present": "公告日期:2019-04-30" in correction.text_content(),
        "original_2017_profit_present": "4,100,926,148.57" in original.text_content(),
        "original_2017_ocf_present": "1,842,794,237.84" in original.text_content(),
        "correction_tables": [
            [[cell.text_content().strip() for cell in tr.xpath("./th|./td")]
             for tr in table.xpath("./tr|./tbody/tr")]
            for table in correction.xpath("//table[.//text()[contains(.,'更正前金额')]]")
            if len(table.xpath(".//table")) == 0
        ],
    }
    for name in ("eastmoney_600518_2025", "eastmoney_600519_2025", "eastmoney_600518_2020"):
        payload = load(name + ".json")
        rows = payload["result"]["data"]
        dates = [x["TRADE_DATE"][:10] for x in rows]
        code = name.split("_")[1]
        raw_decimal = json.loads((BASE / (name + ".json")).read_bytes(), parse_float=Decimal)
        decimal_rows = raw_decimal["result"]["data"]
        fields = ("TRADE_DATE", "SECURITY_CODE", "CLOSE_PRICE", "PE_TTM", "PE_LAR", "PB_MRQ", "TOTAL_MARKET_CAP")
        result["valuation"][name] = {
            "provider_count": payload["result"]["count"], "pages": payload["result"]["pages"],
            "rows": len(rows), "unique_dates": len(set(dates)), "first_date": min(dates), "last_date": max(dates),
            "security_ids": sorted(set(x["SECURITY_CODE"] for x in rows)),
            "pe_nonpositive": sum(x["PE_TTM"] is not None and x["PE_TTM"] <= 0 for x in rows),
            "pe_missing": sum(x["PE_TTM"] is None for x in rows),
            "raw_fields": sorted(rows[0]),
            "decimal_endpoint_rows": [{k: str(x[k]) for k in fields} for x in (decimal_rows[-1], decimal_rows[0])],
            "maximum_pe_ttm_decimal_places": max(-x["PE_TTM"].as_tuple().exponent for x in decimal_rows if isinstance(x["PE_TTM"], Decimal)),
        }
        with patch.object(a_stock, "_em_get", return_value=Response(payload)):
            output = a_stock.get_valuation_history(code)
        output_payload = json.loads(output[output.find("{"):])
        (BASE / (name + "_public_replay.json")).write_text(json.dumps(output_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        result["public_api_replay"][name] = {
            "status": output_payload["status"], "keys": sorted(output_payload),
            "has_daily_rows": "data" in output_payload or "rows" in output_payload or "series" in output_payload,
            "history": output_payload["history"],
            "latest_pe_ttm": output_payload["metrics"]["pe_ttm"],
            "latest_pe_reliability": output_payload["percentiles"]["pe_ttm"]["windows"]["all"]["reliability"],
        }
    historical_row = load("eastmoney_600518_2020.json")["result"]["data"][-1]
    income = load("sina_600518_lrb.json")["result"]["data"]["report_list"]["20191231"]
    profit = Decimal(next(x["item_value"] for x in income["data"] if x["item_field"] == "PARENETP"))
    implied = Decimal(str(historical_row["TOTAL_MARKET_CAP"])) / Decimal(str(historical_row["PE_LAR"]))
    result["valuation_denominator_check"] = {
        "trade_date": historical_row["TRADE_DATE"], "pe_static": historical_row["PE_LAR"],
        "market_cap_yuan": historical_row["TOTAL_MARKET_CAP"], "implied_profit_yuan": str(implied),
        "later_2019_profit_yuan": str(profit), "later_row_publish_date": income["publish_date"],
        "absolute_difference_yuan": str(abs(implied - profit)),
        "relative_difference": str(abs((implied - profit) / profit)),
        "interpretation": "Numerical match is an inference of retrospective denominator use; source supplies no vintage or formula history.",
    }
    (BASE / "analysis.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"financial": result["financial"], "valuation": result["valuation"],
                      "public_api_replay": result["public_api_replay"],
                      "valuation_denominator_check": result["valuation_denominator_check"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    with patch("socket.create_connection", side_effect=AssertionError("offline replay")), \
         patch("socket.socket.connect", side_effect=AssertionError("offline replay")):
        main()
