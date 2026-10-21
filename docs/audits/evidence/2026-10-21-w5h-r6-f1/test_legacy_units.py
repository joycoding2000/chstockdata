"""Red regression against the preserved V2 two-page concatenation."""
import json
import sys
import unittest
from pathlib import Path
from decimal import Decimal

OUT = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(OUT.parent / '2026-10-21-w5h-r6'))
import experiment_v1 as legacy


class LegacyUnitRegression(unittest.TestCase):
    def test_vanke_three_units(self):
        pages = json.loads((OUT.parent / '2026-10-20-w5h-r5' /
                            '000002_Q12024.pdf.pages.json').read_text(encoding='utf-8'))
        start = next(i for i, p in enumerate(pages)
                     if '主要会计数据和财务指标' in legacy.clean(p['text']))
        legacy.LABELS['EQ'].append('归属于上市公司股东的股东权益')
        got = legacy.extract_summary([{'page': pages[start]['page'],
            'text': '\n'.join(p['text'] for p in pages[start:start+2])}], '2024-03-31')
        expected = json.loads((OUT / 'expected.json').read_text(encoding='utf-8'))['cases']
        for case in expected:
            if case['id'] == '1219913619' and case['column'] == 'current':
                with self.subTest(field=case['field']):
                    self.assertEqual(Decimal(got['fields'][case['field']]['current_CNY']),
                                     Decimal(case['expected_CNY']))


if __name__ == '__main__':
    unittest.main()
