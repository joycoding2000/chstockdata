"""Fail-closed replay tests, synthetic adversarial inputs explicitly labelled."""
import unittest
from version_f1 import select


class ReplaySafety(unittest.TestCase):
    def fixture(self):
        return {'id': 'TEST_ONLY_ORIGINAL', 'code': 'TEST_ONLY_ISSUER', 'period': '2022-12-31',
                'field': 'NP', 'value_CNY': '10', 'source_sha256': 'TEST_SHA',
                'source_report_period': '2022-12-31', 'announcement_date': '2023-04-20',
                'available_on': '2023-04-21', 'physical_page': 1, 'raw_text': '10',
                'unit': '元', 'multiplier': 1, 'version_identity': 'TEST_ORIGINAL'}

    def query(self, ledger, rows=None, T='2023-04-21'):
        return select(ledger, rows or [], ['2023-04-21', '2023-05-04'],
                      'TEST_ONLY_ISSUER', '2022-12-31', 'NP', T)

    def test_missing_original_and_future_version_unknown(self):
        self.assertEqual(self.query([])['status'], 'UNKNOWN')
        self.assertEqual(self.query([self.fixture()], T='2023-04-20')['status'], 'UNKNOWN')

    def test_other_issuer_or_period_not_mixed(self):
        self.assertEqual(self.query([{**self.fixture(), 'code': 'OTHER'}])['status'], 'UNKNOWN')
        self.assertEqual(self.query([{**self.fixture(), 'period': '2023-12-31'}])['status'], 'UNKNOWN')

    def test_true_same_time_source_conflict_unknown(self):
        a = self.fixture()
        result = self.query([a, {**a, 'id': 'TEST_ONLY_CONFLICT', 'value_CNY': '11', 'source_sha256': 'OTHER'}])
        self.assertEqual(result['reason'], 'SOURCE_VERSION_CONFLICT')
        self.assertIsNone(result['value_CNY'])

    def test_missing_intermediate_report_unknown(self):
        gap = {'id': 'TEST_ONLY_MISSING_Q1', 'code': 'TEST_ONLY_ISSUER', 'period': '2023-03-31',
               'date': '2023-04-28', 'body_obtained': False}
        result = self.query([self.fixture()], [gap], T='2023-05-04')
        self.assertEqual(result['reason'], 'KNOWN_MISSING_INTERVENING_REPORT')

    def test_later_value_never_overwrites_earlier_T(self):
        a = self.fixture()
        b = {**a, 'id': 'TEST_ONLY_REVISED', 'value_CNY': '-5', 'announcement_date': '2023-04-28',
             'available_on': '2023-05-04', 'version_identity': 'TEST_REVISED'}
        self.assertEqual(self.query([a, b])['value_CNY'], '10')
        self.assertEqual(self.query([a, b], T='2023-05-04')['value_CNY'], '-5')


if __name__ == '__main__':
    unittest.main()
