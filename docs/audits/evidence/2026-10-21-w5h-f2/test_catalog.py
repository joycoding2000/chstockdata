"""Keep a supplemental announcement distinct from a complete periodic PDF."""
import unittest
from acquire import OUT, read
from classify_index import classify
from acquire import check_request_budget


class CatalogIdentity(unittest.TestCase):
    def test_supplement_is_not_full_report(self):
        rows = {r['id']:r for r in read(OUT/'index_inventory.json')['rows']}
        supplement = classify(rows['1217386818'],{'1217386818'})
        updated = classify(rows['1217386817'],{'1217386817'})
        self.assertEqual(supplement['category'],'FINANCIAL_VERSION_CANDIDATE')
        self.assertEqual(updated['category'],'FULL_PERIODIC')

    def test_full_denominator_and_positive_periodic_bodies(self):
        dc = read(OUT/'discovery_classification.json')
        self.assertEqual(dc['denominator'],868)
        periodic = [r for r in dc['rows'] if r['category']=='FULL_PERIODIC']
        self.assertEqual(len(periodic),25)
        self.assertTrue(all(r['body_obtained'] for r in periodic))

    def test_request_sub_budgets_block_before_network(self):
        rules = {'total_direct_requests':160,'metadata_requests':130,'new_pdfs':20}
        with self.assertRaisesRegex(AssertionError,'Metadata'):
            check_request_budget([{'file':'index/test.json'}]*130,'index/new.json',rules)
        with self.assertRaisesRegex(AssertionError,'PDF'):
            check_request_budget([{'file':'originals/test.pdf'}]*20,'originals/new.pdf',rules)
        with self.assertRaisesRegex(AssertionError,'Total'):
            check_request_budget([{'file':'index/test.json'}]*160,'index/new.json',rules)


if __name__ == '__main__':
    unittest.main()
