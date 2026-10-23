"""Actual accepted scan cells subjected to wrong-column/unit/subject mutations."""
import copy
import unittest
from common import HERE, read
from qualification_rules import equivalent_cell


class ActualEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.accepted=[r for r in read(HERE/'scan_field_qualification.json')['rows']if r['qualification_status']=='VERIFIED_EXISTING_VERSION']
        assert len(cls.accepted)==3

    def test_actual_accepted_cells(self):
        for r in self.accepted:
            with self.subTest(document=r['document_id']):
                self.assertTrue(all(equivalent_cell(r['source_cell'],ref)for ref in r['independent_references']))

    def test_wrong_actual_column_rejected(self):
        for r in self.accepted:
            with self.subTest(document=r['document_id']):
                cell=copy.deepcopy(r['source_cell']);cell['column_index']=1
                self.assertFalse(any(equivalent_cell(cell,ref)for ref in r['independent_references']))

    def test_wrong_actual_multiplier_rejected(self):
        for r in self.accepted:
            cell={**r['source_cell'],'multiplier':10000}
            self.assertFalse(any(equivalent_cell(cell,ref)for ref in r['independent_references']))

    def test_wrong_actual_subject_rejected(self):
        for r in self.accepted:
            cell={**r['source_cell'],'scope':'parent'}
            self.assertFalse(any(equivalent_cell(cell,ref)for ref in r['independent_references']))

    def test_matching_money_without_header_is_rejected(self):
        for r in self.accepted:
            cell={**r['source_cell'],'header_verified':False}
            self.assertFalse(any(equivalent_cell(cell,ref)for ref in r['independent_references']))

    def test_critical_unknowns_have_no_accepted_value(self):
        rows=read(HERE/'scan_field_qualification.json')['rows']
        unknown=[r for r in rows if r['qualification_status'].startswith('UNRESOLVED_')]
        self.assertEqual(len(unknown),24)
        self.assertTrue(all(r['value_CNY']is None for r in unknown))

    def test_explicit_h1_opening_is_not_prior_year_end(self):
        rows=read(HERE/'scan_field_qualification.json')['rows']
        opening=next(r for r in rows if r['document_id']=='1217949874' and r['evidence_page']==208 and r['column_index']==1)
        self.assertEqual(opening['affected_period'],'2023-01-01')
        self.assertEqual(opening['duration'],'INSTANT_START')


if __name__=='__main__':unittest.main(verbosity=2)
