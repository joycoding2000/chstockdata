"""Source-aware rejection checks on actual parsed fixed artifacts."""
import copy
import unittest
from decimal import Decimal
from acquire import OUT, read
from version_f2 import valid_fact, build_ledger, select
from version_legacy import calendar


class PipelineGuards(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.documents = read(OUT/'dataset_legacy.json')['documents']+read(OUT/'new_documents.json')
        cls.docs = {d['id']:d for d in cls.documents}
        cls.ledger = read(OUT/'version_evidence_f2.json')['ledger']
        cls.rows = read(OUT/'discovery_classification.json')['rows']
        cls.notices = read(OUT/'auxiliary_evidence.json')['notices']
        cls.sessions = calendar()
        cls.windows = read(OUT/'preregistration.json')['windows']
        cls.good = next(f for f in cls.ledger if f['code']=='000002' and f['period']=='2024-06-30' and f['field']=='NP')

    def query(self,code,period,field,T,ledger=None,rows=None,notices=None):
        return select(self.ledger if ledger is None else ledger,self.rows if rows is None else rows,
                      self.notices if notices is None else notices,self.sessions,
                      {'code':code,'period':period,'field':field,'T':T,'mode':'strict_index'},self.windows)

    def test_wrong_issuer_rejected(self):
        f = {**self.good,'code':'600519'}
        self.assertFalse(valid_fact(f,self.docs))

    def test_future_report_period_rejected(self):
        self.assertFalse(valid_fact({**self.good,'period':'2025-06-30'},self.docs))

    def test_wrong_unit_scope_rejected(self):
        self.assertFalse(valid_fact({**self.good,'multiplier':10000},self.docs))

    def test_parent_not_consolidated(self):
        self.assertFalse(valid_fact({**self.good,'scope':'parent'},self.docs))

    def test_missing_source_or_location_rejected(self):
        for patch in [{'source_sha256':'bad'},{'physical_page':None},{'unit_evidence':None}]:
            with self.subTest(patch=patch):
                self.assertFalse(valid_fact({**self.good,**patch},self.docs))

    def test_current_structured_row_cannot_enter_ledger(self):
        row = {'code':'600518','period':'2017-12-31','field':'OCF','value_CNY':'-4840052606.46'}
        ledger,rejected = build_ledger([row],self.documents,self.sessions)
        self.assertEqual(ledger,[])
        self.assertEqual(len(rejected),1)

    def test_missing_original_future_comparative_not_backdated(self):
        only_future = [f for f in self.ledger if f['code']=='600518' and f['announcement_date']>'2019-01-01']
        self.assertEqual(self.query('600518','2017-12-31','OCF','2018-04-27',ledger=only_future)['status'],'UNKNOWN')

    def test_before_adjustment_column_not_its_own_original(self):
        f = {**self.good,'column':'unadjusted'}
        ledger,_ = build_ledger([f],self.documents,self.sessions)
        self.assertEqual(ledger,[])

    def test_missing_intermediate_original_blocks_old_carry(self):
        rows = copy.deepcopy(self.rows)
        for r in rows:
            if r['id']=='1216696970':
                r['body_obtained']=False
        ledger = [f for f in self.ledger if f['id']!='1216696970']
        got = self.query('000961','2022-12-31','NP','2023-05-04',ledger=ledger,rows=rows)
        self.assertEqual(got['status'],'UNKNOWN')
        self.assertIn('1216696970',got['gaps'])

    def test_unread_financial_filing_blocks_qualified_history(self):
        got = self.query('000961','2022-12-31','EQ','2023-05-05')
        self.assertEqual(got['status'],'UNKNOWN')
        self.assertIn('1216741269',got['gaps'])

    def test_source_conflict_not_hidden(self):
        chosen = next(f for f in self.ledger if f['id']==self.good['id'] and f['field']=='NP')
        other = {**chosen,'id':'test_conflicting_source','source_sha256':'different',
                 'value_CNY':str(Decimal(chosen['value_CNY'])+1)}
        got = self.query('000002','2024-06-30','NP','2024-09-02',ledger=[chosen,other])
        self.assertEqual(got['reason'],'SOURCE_VERSION_CONFLICT')

    def test_unrelated_governance_does_not_replace_negative_value(self):
        got = self.query('000002','2024-06-30','NP','2024-10-08')
        self.assertEqual(Decimal(got['value_CNY']),Decimal('-9852499598.84'))
        self.assertEqual(got['source_id'],'1221084198')

    def test_single_quarter_does_not_replace_ytd(self):
        facts = read(OUT/'certified_new_facts.json')['facts']
        ledger,_ = build_ledger(facts,self.documents,self.sessions)
        self.assertFalse(any(f['duration']=='SINGLE_QUARTER' for f in ledger))
        got = self.query('000002','2023-09-30','NP','2023-10-30',ledger=ledger)
        self.assertEqual(Decimal(got['value_CNY']),Decimal('13621477419.62'))

    def test_unsupported_interval_rejected(self):
        self.assertEqual(self.query('600519','2023-12-31','NP','2026-10-21')['reason'],
                         'INTERVAL_OUTSIDE_FIXED_INDEX_COVERAGE')


if __name__ == '__main__':
    unittest.main()
