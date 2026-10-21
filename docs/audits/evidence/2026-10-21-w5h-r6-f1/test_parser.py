"""Local deterministic safety tests; real-PDF regression is scored separately."""
import unittest
from decimal import Decimal
import parser_f1 as p


class ParserSafety(unittest.TestCase):
    def test_parentheses_and_minus(self):
        self.assertEqual(p.amount('(1,234.50)'), Decimal('-1234.50'))
        self.assertEqual(p.amount('（1,234.50）'), Decimal('-1234.50'))
        self.assertEqual(p.amount('−1,234.50'), Decimal('-1234.50'))
        self.assertIsNone(p.amount('12.5%'))
        self.assertIsNone(p.amount('—'))

    def test_exact_field_identity(self):
        self.assertEqual(p.field_id('归属于上市公司股东的所有者权益（万元）'), 'EQ')
        self.assertIsNone(p.field_id('归属于上市公司股东的扣除非经常性损益的净利润'))
        self.assertIsNone(p.field_id('归属于上市公司股东的每股净资产'))

    def test_explicit_parent_scope_is_separate(self):
        self.assertEqual(p.explicit_scope([{'text': '母公司现金流量表', 'bottom': 20}], 30), 'parent')
        self.assertEqual(p.explicit_scope([{'text': '合并现金流量表', 'bottom': 20}], 30), 'consolidated')

    def test_no_cross_page_without_aligned_table(self):
        class Page:
            height = 800
        previous = {'page': 1, 'height': 800, 'bbox': [10, 500, 500, 780], 'edges': [10, 100, 500]}
        current = {'bbox': [10, 50, 500, 150], 'edges': [10, 100, 500]}
        self.assertIsNotNone(p.continuity(previous, current, 2, Page(), []))
        self.assertIsNone(p.continuity(previous, current, 3, Page(), []))
        self.assertIsNone(p.continuity(previous, {**current, 'edges': [10, 100, 300, 500]}, 2, Page(), []))
        self.assertIsNone(p.continuity(previous, current, 2, Page(),
            [{'text': '（二）非经常性损益', 'bottom': 30}]))

    def test_unit_must_not_look_forward(self):
        lines = [{'top': 20, 'bottom': 30, 'text': '单位：元'},
                 {'top': 300, 'bottom': 310, 'text': '单位：万元'}]
        self.assertEqual(p.preceding_unit(lines, 50, 0)['multiplier'], 1)
        self.assertIsNone(p.preceding_unit(lines, 10, 0))

    def test_conflicting_units_unknown(self):
        self.assertIsNone(p.unit_from('单位：元；单位：万元'))

    def test_explicit_units(self):
        self.assertEqual(p.unit_from('全年经营成果（人民币百万元）')['multiplier'], 1000000)
        self.assertIsNotNone(p.unit_from('单位：除特别注明外，为人民币百万元'))
        self.assertEqual(p.unit_from('单位：除特别注明外，为人民币百万元')['multiplier'], 1000000)
        self.assertEqual(p.unit_from('归母权益（万元）')['multiplier'], 10000)

    def test_equity_is_end_not_beginning(self):
        self.assertEqual(p.header_period('2024年3月31日', '2024-03-31', 'EQ'), '2024-03-31')
        self.assertEqual(p.header_period('上年度末', '2024-03-31', 'EQ'), '2023-12-31')
        self.assertEqual(p.header_period('上年同期', '2024-03-31', 'NP'), '2023-03-31')
        self.assertIsNone(p.header_period('第一季度 第二季度', '2023-12-31', 'NP'))
        self.assertEqual(p.header_period('2023年第一季度', '2024-03-31', 'NP'), '2023-03-31')

    def test_explicit_rounding_is_not_an_arbitrary_repair(self):
        a = {'value_CNY': '1234.56', 'quantum_CNY': '0.01', 'source_sha256': 'a'}
        b = {'value_CNY': '1235', 'quantum_CNY': '1', 'source_sha256': 'a'}
        self.assertEqual(p.unique_value([b, a])['value_CNY'], '1234.56')
        self.assertEqual(p.unique_value([a, {**b, 'value_CNY': '1236'}])['status'], 'UNKNOWN')

    def test_disagreeing_same_identity_is_not_certified(self):
        base = {'value_CNY': '1', 'unit': '元', 'source_sha256': 'a'}
        self.assertEqual(p.unique_value([base, {**base, 'value_CNY': '2'}])['status'], 'UNKNOWN')


if __name__ == '__main__':
    unittest.main()
