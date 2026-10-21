"""Known failures first; all amount expectations remain outside the parser."""
import json
import unittest
from decimal import Decimal
from pathlib import Path
import parser_f2 as p

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[3]


class F2KnownGaps(unittest.TestCase):
    def test_moutai_two_equity_values_have_direct_proof(self):
        documents = json.loads((OUT/'dataset_legacy.json').read_text(encoding='utf-8'))['documents']
        src = next(d for d in documents if d['id'] == '1219875828')
        result = p.extract_document(ROOT, src)
        for period, expected in [('2024-03-31', '239731785910.55'), ('2023-12-31', '215668571607.43')]:
            with self.subTest(period=period):
                values = [f for f in result['facts'] if f['field'] == 'EQ' and f['period'] == period
                          and f['scope'] == 'consolidated']
                got = p.unique_value(values)
                self.assertNotEqual(got['status'], 'UNKNOWN')
                self.assertEqual(Decimal(got['value_CNY']), Decimal(expected))
                self.assertTrue(got['unit_evidence'])

    def test_nine_month_flow_header_is_not_beginning_equity(self):
        self.assertEqual(p.header_period('年初至报告期末', '2023-09-30', 'NP'), '2023-09-30')
        self.assertEqual(p.header_period('年初', '2023-09-30', 'EQ'), '2022-12-31')

    def test_prior_ytd_header_is_prior_period(self):
        self.assertEqual(p.header_period('上年初至上年报告期末', '2019-03-31', 'NP'), '2018-03-31')

    def test_new_documents_unit_blocks_and_dash_do_not_hide_fields(self):
        results = {r['id']: r for r in json.loads((OUT/'new_parsed.json').read_text(encoding='utf-8'))['results']}
        checks = [('1218204096','OCF','2023-09-30','267360450.96'),
                  ('1221084198','EQ','2024-06-30','241678563970.12'),
                  ('1217713835','EQ','2023-06-30','249326669106.12')]
        for id_, field, period, expected in checks:
            with self.subTest(id=id_, field=field):
                got = p.unique_value([f for f in results[id_]['facts'] if f['field']==field
                    and f['period']==period and f['column']=='current' and f['duration']!='SINGLE_QUARTER'])
                self.assertNotEqual(got['status'], 'UNKNOWN')
                self.assertEqual(Decimal(got['value_CNY']), Decimal(expected))


if __name__ == '__main__':
    unittest.main()
