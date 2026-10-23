"""Data correctness checks, no strategy or return experiment."""
import unittest
from decimal import Decimal as D


class EconomicEventTests(unittest.TestCase):
    def test_real_per_ten_amount_and_date_precision(self):
        from build_delivery import parse_dividend, ROOT
        path = next((ROOT / "extracted").glob("*2025-06-11-official-dividend.json"))
        event = parse_dividend(path)
        self.assertEqual(event["cash_per_share_cny"], "0.0200")
        self.assertEqual(event["ex_dividend_date"], "2025-06-16")
        self.assertEqual(event["cash_available_not_before"], "2025-06-19T23:59:59+08:00")
        self.assertEqual(event["announcement_available_at"], "2025-06-11T23:59:59+08:00")

    def test_ex_date_claim_is_not_spendable_cash(self):
        from build_delivery import unit_book
        event = {"ex_dividend_date": "2025-06-16", "payment_date": "2025-06-19", "cash_per_share_cny": "0.02"}
        claims, paid = unit_book("2025-06-16", [event])
        self.assertEqual((claims, paid), (D("0.02"), D("0")))
        self.assertEqual(D("0.98") + claims + paid, D("1.00"))
        # Availability is inferred at payment-date end, after that day's close.
        self.assertEqual(unit_book("2025-06-19", [event]), (D("0.02"), D("0")))
        self.assertEqual(unit_book("2025-06-20", [event]), (D("0"), D("0.02")))

    def test_future_dividend_does_not_change_earlier_return(self):
        from build_delivery import economic_factor
        event = {"ex_dividend_date": "2025-06-16", "cash_per_share_cny": "0.02", "announcement_available_at": "2025-06-11T23:59:59+08:00"}
        self.assertEqual(economic_factor("2025-06-10", D("1"), D("1"), [event]), D("1"))
        self.assertEqual(economic_factor("2025-06-16", D("1"), D("0.98"), [event]), D("1"))

    def test_late_or_unknown_announcement_fails_closed(self):
        from build_delivery import economic_factor
        for known in (None, "2025-06-17T23:59:59+08:00"):
            with self.assertRaises(ValueError):
                economic_factor("2025-06-16", D("1"), D("0.98"), [{"ex_dividend_date": "2025-06-16", "cash_per_share_cny": "0.02", "announcement_available_at": known}])

    def test_hk_and_hg_routes_aggregate_same_security(self):
        from build_delivery import aggregate_holdings
        rows = [{"security_id": "HK:01919", "channel": "HG", "market_value_cny": "60", "nav_weight_percent": "3.0", "shares": 6}, {"security_id": "HK:01919", "channel": "HK", "market_value_cny": "40", "nav_weight_percent": "2.0", "shares": 4}]
        combined = aggregate_holdings(rows)
        self.assertEqual(len(combined), 1)
        self.assertEqual(combined[0]["market_value_cny"], "100")
        self.assertEqual(combined[0]["shares"], 10)

    def test_real_wrapped_hg_hk_cells_reconcile_full_equity(self):
        from build_delivery import extract_portfolio, aggregate_holdings, ROOT
        path = next((ROOT / "extracted").glob("*513530-2025-official-annual.json"))
        positions, sectors = extract_portfolio(path, "513530")
        self.assertEqual(len(positions), 60)
        self.assertEqual(len(aggregate_holdings(positions)), 30)
        self.assertEqual(sum(D(x["market_value_cny"]) for x in positions), D("3640068792.70"))

    def test_real_active_residual_is_not_dropped_from_fund_proxy(self):
        from build_delivery import extract_portfolio, ROOT
        path = next((ROOT / "extracted").glob("*513990-2024-official-semi.json"))
        positions, _ = extract_portfolio(path, "513990")
        active = [x for x in positions if x["holding_role"] == "ACTIVE_NON_INDEX"]
        self.assertEqual([(x["security_id"],x["market_value_cny"]) for x in active], [("HK:09930", "506.54")])


if __name__ == "__main__":
    unittest.main()
