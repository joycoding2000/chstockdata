"""Adversarial assertions for field-level evidence; synthetic values are TEST_ONLY."""
import copy
import unittest
import qualification_rules as rules


class QualificationTests(unittest.TestCase):
    def setUp(self):
        self.cell = {"field": "OCF", "period": "2022-12-31", "scope": "consolidated",
                     "unit": "元", "multiplier": 1, "value_CNY": "120.00",
                     "header_verified": True, "label_verified": True,
                     "column_verified": True, "source_bound": True}
        self.ref = dict(self.cell)

    def test_valid_cell(self):
        self.assertTrue(rules.equivalent_cell(self.cell, self.ref))

    def test_wrong_column(self):
        self.cell["column_verified"] = False
        self.assertFalse(rules.equivalent_cell(self.cell, self.ref))

    def test_wrong_multiplier(self):
        self.cell["multiplier"] = 10000
        self.assertFalse(rules.equivalent_cell(self.cell, self.ref))

    def test_wrong_subject(self):
        self.cell["scope"] = "parent"
        self.assertFalse(rules.equivalent_cell(self.cell, self.ref))

    def test_wrong_period(self):
        self.cell["period"] = "2021-12-31"
        self.assertFalse(rules.equivalent_cell(self.cell, self.ref))

    def test_wrong_sign(self):
        self.cell["value_CNY"] = "-120.00"
        self.assertFalse(rules.equivalent_cell(self.cell, self.ref))

    def test_audit_number_alone_is_not_duplicate(self):
        self.assertFalse(rules.page_equivalent({"audit_id": "TEST_ONLY"}, {"audit_id": "TEST_ONLY"}))

    def test_object_match_with_page_overlay_is_not_page_duplicate(self):
        self.assertFalse(rules.page_equivalent({"pixel_sha256": "a", "size": [10,10]},
                                               {"pixel_sha256": "b", "size": [10,10]}))

    def test_same_page_pixels(self):
        self.assertTrue(rules.page_equivalent({"pixel_sha256": "a", "size": [10,10]},
                                              {"pixel_sha256": "a", "size": [10,10]}))

    def test_single_ocf_match_does_not_prove_scope(self):
        self.assertFalse(rules.fingerprint_qualified([{"label": "OCF", "period": "2022", "matches": True}], True, True))

    def test_fingerprint_requires_non_ocf_rows_and_multiple_periods(self):
        rows = [{"label": "cash_in", "period": y, "matches": True} for y in ["2021","2022"]]
        self.assertFalse(rules.fingerprint_qualified(rows, True, True))
        rows += [{"label": f"TEST_ROW_{i}", "period": y, "matches": True}
                 for y in ["2021","2022"] for i in range(4)]
        self.assertTrue(rules.fingerprint_qualified(rows, True, True))
        self.assertFalse(rules.fingerprint_qualified(rows, False, True))
        self.assertFalse(rules.fingerprint_qualified(rows, True, False))

    def test_fy2021_conflict_blocks_only_dependency(self):
        conflict={"code":"TEST_ONLY","field":"OCF","period":"2021-12-31","available_on":"2023-05-05"}
        q={"code":"TEST_ONLY","field":"OCF","period":"2022-12-31","T":"2023-05-08"}
        self.assertFalse(rules.conflict_affects_query(conflict,q))
        q["required_dependencies"]=[{"field":"OCF","period":"2021-12-31"}]
        self.assertTrue(rules.conflict_affects_query(conflict,q))
        q["T"]="2023-05-04"
        self.assertFalse(rules.conflict_affects_query(conflict,q))


if __name__ == "__main__":
    unittest.main(verbosity=2)
