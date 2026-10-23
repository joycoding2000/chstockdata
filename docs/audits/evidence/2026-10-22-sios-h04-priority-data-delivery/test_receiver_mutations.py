"""In-memory financial fault injection bypasses hash checks to test requalification."""
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from receive_delivery import qualify

ROOT = Path(__file__).resolve().parent / "H04-TR-delivery"


class ReceiverMutationTests(unittest.TestCase):
    def reject(self, relative, change, expected_error):
        original = Path.read_text
        target = ROOT / relative
        def altered(path, *args, **kwargs):
            text = original(path, *args, **kwargs)
            return change(text) if path.resolve() == target.resolve() else text
        # Original bytes remain intact so manifest hashes cannot be the reason
        # for rejection. Only the decoded financial view is corrupted.
        with patch.object(Path,"read_text",altered):
            report = qualify(ROOT,verify_pdf=False)
        self.assertFalse(report["integrity_and_economic_accounting_pass"])
        self.assertTrue(any(expected_error in e for e in report["errors"]), report["errors"])

    def test_dividend_unit_tenfold_error(self):
        def change(text):
            data=json.loads(text); data["events"][0]["cash_per_share_cny"]="0.2"
            return json.dumps(data)
        self.reject("fund_actions.json",change,"independent per-ten")

    def test_cash_credited_early(self):
        def change(text):
            rows=[json.loads(x) for x in text.splitlines()]
            row=next(x for x in rows if x["instrument_id"]=="SH:513530" and x["date"]=="2025-06-19")
            row["fixed_one_share_receivable_cny"]="0"; row["fixed_one_share_distributed_cash_cny"]="0.02"
            return "\n".join(json.dumps(x) for x in rows)
        self.reject("total_return_observations.jsonl",change,"cash not posted")

    def test_latest_factor_backfill_flag(self):
        def change(text):
            rows=[json.loads(x) for x in text.splitlines()]; rows[0]["latest_adjustment_factor_used"]=True
            return "\n".join(json.dumps(x) for x in rows)
        self.reject("total_return_observations.jsonl",change,"future factor")

    def test_optimistic_attribution_gate(self):
        def change(text):
            data=json.loads(text); data["gates"]["H04_ATTRIBUTION_DATA_GATE"]="PASS_FOR_CONSUMER_REVIEW"
            return json.dumps(data)
        self.reject("manifest.json",change,"attribution cannot be promoted")

    def test_future_holdings_disclosure_backfilled(self):
        def change(text):
            data=json.loads(text); data[0]["publication_date"]=data[0]["observation_date"]
            return json.dumps(data)
        self.reject("H04-attribution-delivery/fund_holdings_snapshots.json",change,"future disclosure")


if __name__ == "__main__":
    unittest.main()
