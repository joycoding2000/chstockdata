"""Machine checks of the actual PDFs and failed-current-row counterexample."""
import hashlib
import json
from decimal import Decimal
from pathlib import Path
from parser_f2 import amount

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[3]


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def main():
    scored = read(OUT / 'value_validation.json')['cases']
    docs = {d['id']: d for d in read(OUT / 'dataset_legacy.json')['documents']}
    checks = []
    for case in scored:
        a = case['actual']
        if case['result'] != 'PASS':
            checks.append({'case': case['case_id'], 'check': 'UNKNOWN_NOT_CERTIFIED',
                           'pass': not case['auto_certified_fixed_case'] and a['status'] == 'UNKNOWN'})
            continue
        checks.append({'case': case['case_id'], 'check': 'RAW_UNIT_COLUMN_PROVENANCE',
            'pass': (amount(a['raw_text']) == Decimal(a['source_amount']) and
                     Decimal(a['source_amount']) * a['multiplier'] == Decimal(a['value_CNY']) and
                     a['multiplier'] == a['unit_evidence']['multiplier'] and
                     a['unit_evidence'].get('physical_page') is not None and
                     a['source_sha256'] == docs[a['id']]['sha256'] and
                     a['physical_page'] > 0 and bool(a['cell_bbox']) and
                     a['scope'] == case['scope'] and not a['pit_qualified'])})
    original = {c['field']: c['actual'] for c in scored if c['id'] == '1216561621' and c['result'] == 'PASS'}
    structured = []
    r5 = OUT.parent / '2026-10-20-w5h-r5'
    for field, name, key in [('NP', 'benefit', 'parent_holder_net_profit'),
                             ('OCF', 'cash', 'act_cash_flow_net'),
                             ('EQ', 'debt', 'parent_holder_equity_total')]:
        path = r5 / ('000961_ths_' + name + '.json')
        row = next(r for r in read(path)['data']['data'] if r['date'] == '2022-12-31')
        current = row['index_list'][key]['value']
        structured.append({'field': field, 'period': row['date'], 'current_structured_value': current,
            'official_original_value': original[field]['value_CNY'],
            'numeric_equal': Decimal(current) == Decimal(original[field]['value_CNY']),
            'source_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'bound_official_announcement_id': None, 'eligible_for_historical_replay': False,
            'reason': 'UNBOUND_CURRENT_ROW_NO_HISTORICAL_VERSION_IDENTITY',
            'conflict_kind': 'DIFFERENT_VERSION_OR_UNBOUND_SOURCE_NOT_A_CONFIRMED_SAME_VINTAGE_CONFLICT'})
    v2 = [c for c in scored if c['id'] == '1219913619' and c['column'] == 'current']
    checks.append({'check': 'THREE_KNOWN_V2_ERRORS_PASS_WITH_MULTIPLIER_ONE',
                   'pass': len(v2) == 3 and all(c['result'] == 'PASS' and c['actual']['multiplier'] == 1 for c in v2)})
    checks.append({'check': 'NO_FALSE_AUTOMATIC_CERTIFICATION',
                   'pass': all(c['result'] == 'PASS' for c in scored if c['program_accepted_before_truth'])})
    payload = {'checks': checks, 'pass': all(c['pass'] for c in checks),
               'structured_current_rows_rejected': structured,
               'genuine_same_vintage_source_conflict_observed': False,
               'synthetic_conflict_branch': 'test_versions.py, explicit TEST_ONLY data',
               'manual_numeric_repair_table': False}
    (OUT / 'quality_checks.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'pass': payload['pass'], 'checks': len(checks),
                      'current_row_numeric_mismatches': sum(not s['numeric_equal'] for s in structured)}))


if __name__ == '__main__':
    main()
