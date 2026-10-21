"""Separate scorer: no truth amounts are inputs to PDF extraction or replay."""
import hashlib
import json
from collections import Counter
from decimal import Decimal
from pathlib import Path
from parser_f2 import unique_value

OUT = Path(__file__).resolve().parent


def main():
    truth = []
    for name in ['expected_new_batch1.json', 'expected_new_batch2.json', 'expected_new_batch3.json']:
        truth += json.loads((OUT/name).read_text(encoding='utf-8'))['cases']
    parsed = json.loads((OUT/'new_parsed.json').read_text(encoding='utf-8'))
    docs = {d['id']: d for d in parsed['results']}
    scored = []
    for c in truth:
        candidates = [f for f in docs[c['id']]['facts'] if all(f[k] == c[k] for k in
            ['field', 'period', 'scope', 'duration']) and (f['column'] == c['column'] or
            c['column'] == 'comparative' and f['column'] in ('adjusted', 'unadjusted'))]
        got = unique_value(candidates)
        unknown = got['status'] == 'UNKNOWN'
        expected_unknown = c.get('expected_status') == 'UNKNOWN'
        result = ('PASS_UNKNOWN' if unknown else 'FAIL') if expected_unknown else (
            'UNKNOWN' if unknown else 'PASS' if Decimal(got['value_CNY']) == Decimal(c['expected_CNY'])
            and got['multiplier'] == c['expected_multiplier'] else 'FAIL')
        scored.append({**c, 'result': result, 'actual': got})
    counts = dict(Counter(c['result'] for c in scored))
    payload = {'denominator': len(scored), 'counts': counts, 'cases': scored,
               'parsed_sha256': hashlib.sha256((OUT/'new_parsed.json').read_bytes()).hexdigest()}
    (OUT/'new_value_validation.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'counts': counts, 'non_pass': [{k:c[k] for k in
        ['id','period','field','column','duration','expected_CNY','result']} |
        {'got': c['actual'].get('value_CNY'), 'reason':c['actual'].get('reason')}
        for c in scored if c['result'] not in ('PASS','PASS_UNKNOWN')]}, ensure_ascii=True))
    assert not counts.get('FAIL'), 'Wrong accepted value: whole new batch rejected'
    # The full batch is qualified before any facts are selected for demonstration.
    facts = {tuple(c['actual'][k] for k in ['id','field','period','column','scope','duration']):
             c['actual'] for c in scored if c['result'] == 'PASS'}
    (OUT/'certified_new_facts.json').write_text(json.dumps({
        'qualification': 'CHECKED_FIXED_CASE_IDENTITIES_ONLY', 'facts': list(facts.values()),
        'whole_batch_has_zero_incorrect_accepted_values': True,
        'parsed_sha256': payload['parsed_sha256'],
    }, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
