import unittest
from decimal import Decimal
from fetch_named import OUT, read


class FixedSourceFields(unittest.TestCase):
    def test_source_fields(self):
        from extract_facts import extract_all
        results = extract_all()
        for c in read(OUT/'expected_source_fields.json')['cases']+read(OUT/'expected_summary_columns.json')['cases']+read(OUT/'expected_dated_narrative.json')['cases']+read(OUT/'expected_annual_quote.json')['cases']+read(OUT/'expected_split_row.json')['cases']:
            with self.subTest(id=c['id'],field=c['field'],scope=c['scope']):
                got = [f for f in results if all(f[k]==c[k] for k in
                    ['id','field','period','scope','physical_page'])]
                if not got:
                    unknown=[f for f in results if all(f[k]==c[k] for k in ['id','field','period','physical_page'])]
                    self.assertTrue(unknown)
                    self.assertTrue(all(f['scope']=='unknown' for f in unknown))
                    continue
                self.assertTrue(got)
                self.assertTrue(all(Decimal(f['value_CNY'])==Decimal(c['value_CNY']) and
                                    f['multiplier']==c['multiplier'] for f in got))

    def test_growth_column_not_money(self):
        from extract_facts import extract_all
        rows=[f for f in extract_all() if f['code']=='600518' and f['field']=='NP' and f['method']=='GRID']
        self.assertFalse(any(f['raw_text'] in ('22.77','21.17') for f in rows))


if __name__=='__main__':
    unittest.main()
