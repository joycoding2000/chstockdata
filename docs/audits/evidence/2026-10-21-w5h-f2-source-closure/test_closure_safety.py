import copy,unittest
from datetime import datetime
from fetch_named import OUT,F2,read,allowance

class ClosureSafety(unittest.TestCase):
    def test_real_budget_and_gap(self):
        p=read(OUT/'preregistration.json');rs=read(OUT/'requests.json');b=p['budget']
        self.assertEqual(len(rs),23)
        self.assertEqual([r['id'] for r in rs],[r['id'] for r in p['sources']])
        self.assertTrue(all(r['status']=='SAVED' and r['http_status']==200 for r in rs))
        self.assertLessEqual(b['previous_requests']+len(rs),181)
        self.assertLessEqual(b['previous_pdf_bytes']+sum(r['received_bytes'] for r in rs),200000000)
        self.assertTrue(all(r['bytes']<=25000000 for r in rs))
        for a,c in zip(rs,rs[1:]):
            self.assertGreaterEqual((datetime.fromisoformat(c['started_at'])-datetime.fromisoformat(a['finished_at'])).total_seconds(),3)
    def test_pre_network_budget_boundaries(self):
        p=read(OUT/'preregistration.json');s=p['sources'][0]
        for n in [25,26]:
            with self.assertRaises(AssertionError):allowance(p,[{'id':str(i),'status':'FAILED'} for i in range(n)],s)
        with self.assertRaises(AssertionError):allowance(p,[],{**s,'id':'UNAUTHORIZED_TEST_ONLY_ID'})
        with self.assertRaises(AssertionError):allowance(p,[{'id':'test','status':'FAILED','received_bytes':147147482}],s)
    def test_mutually_exclusive_dispositions(self):
        q=read(OUT/'source_qualification.json')
        self.assertEqual(q['denominator'],23);self.assertEqual(q['resolved'],12)
        self.assertEqual(sum(q['counts'].values()),23)
        self.assertTrue(all(not r['whole_document_equivalence'] for r in q['reviews']))
    def test_same_date_unqualified_companion_blocks(self):
        from replay_closure import blockers
        # Synthetic identity/date guard only, not a claimed real financial event.
        rs=[{'id':'COMPANION_TEST_ONLY','date':'2023-05-04','code':'test','resolved':False,'blocked_fields':['OCF']}]
        q={'code':'test','field':'OCF','T':'2023-05-05'}
        self.assertEqual(len(blockers(rs,q,'2023-05-04','ANCHOR_TEST_ONLY',['2023-05-05'])),1)
        q['T']='2023-05-04';self.assertFalse(blockers(rs,q,'2023-05-04','ANCHOR_TEST_ONLY',['2023-05-05']))
    def test_original_audit_requote_does_not_revert_adjustment(self):
        l=read(OUT/'source_aware_ledger.json')
        self.assertEqual(l['ledger'],read(F2/'version_evidence_f2.json')['ledger'])
        self.assertEqual(len(l['ledger']),127)
        self.assertFalse(l['new_monetary_revision_events'])
        rs={r['query_id']:r for r in read(OUT/'closure_replay_results.json')}
        self.assertEqual(rs['V_after_bond_known']['value_CNY'],'243325374922.33')
        self.assertEqual(rs['V_after_bond_strict']['status'],'UNKNOWN')
    def test_unknown_scope_not_certified_and_ocr_not_money(self):
        v=read(OUT/'source_value_validation.json')
        self.assertEqual(v['denominator'],24);self.assertEqual(v['counts'],{'PASS':22,'UNKNOWN':2})
        fs=read(OUT/'source_qualification.json')['facts']
        self.assertTrue(all(r['status']!='VERIFIED_PRIOR_FACT_CORROBORATION' for r in fs if r['scope']!='consolidated'))
        self.assertTrue(all(f['method']!='OCR' for f in read(OUT/'parsed_source_facts.json')['facts']))
    def test_source_conflict_not_silently_repaired(self):
        q=read(OUT/'source_qualification.json')
        self.assertEqual(len(q['source_internal_inconsistencies']),6)
        self.assertTrue(all(r['not_auto_revision_event'] for r in q['source_internal_inconsistencies']))
    def test_parser_has_no_truth_or_issuer_patch_input(self):
        import ast
        tree=ast.parse((OUT/'extract_facts.py').read_text(encoding='utf-8'))
        strings=[n.value for n in ast.walk(tree) if isinstance(n,ast.Constant) and isinstance(n.value,str)]
        ids={r['id'] for r in read(OUT/'documents.json')}
        self.assertFalse(any(s in ids or (s.startswith('expected_') and s.endswith('.json')) for s in strings))

if __name__=='__main__':unittest.main(verbosity=2)
