"""The scorer, and only the scorer, loads independent expected amounts."""
import json
import hashlib
from collections import Counter
from decimal import Decimal
from pathlib import Path
from parser_f1 import unique_value

OUT = Path(__file__).resolve().parent


def main():
    truth = json.loads((OUT / 'expected.json').read_text(encoding='utf-8'))['cases']
    parsed = json.loads((OUT / 'parsed.json').read_text(encoding='utf-8'))
    docs = {r['id']: r for r in parsed['results']}
    scored = []
    for case in truth:
        # R5's generic "comparative as printed" does not specify adjusted/unadjusted.
        # Accept only if every matching comparative column agrees; never choose by truth.
        candidates = [f for f in docs[case['id']]['facts'] if all(
            f[k] == case[k] for k in ['field', 'period', 'scope', 'mode']) and
            (f['column'] == case['column'] or case['column'] == 'comparative' and
             f['column'] in ('adjusted', 'unadjusted'))]
        got = unique_value(candidates)
        status = 'UNKNOWN' if got['status'] == 'UNKNOWN' else 'PASS' if (
            Decimal(got['value_CNY']) == Decimal(case['expected_CNY']) and
            got['multiplier'] == case['expected_multiplier']) else 'FAIL'
        scored.append({**case, 'result': status, 'actual': got,
                       'program_accepted_before_truth': got['status'] != 'UNKNOWN',
                       'auto_certified_fixed_case': status == 'PASS',
                       'historical_pit_qualified': False,
                       'reason': got.get('reason') if status == 'UNKNOWN' else
                                 'MATCH_INDEPENDENT_PDF_TRUTH' if status == 'PASS' else
                                 'VALUE_OR_UNIT_MISMATCH_NOT_CERTIFIED'})
    counts = dict(Counter(r['result'] for r in scored))
    (OUT / 'value_validation.json').write_text(json.dumps({
        'denominator': len(scored), 'counts': counts,
        'unknown_is_not_success': True, 'cases': scored,
    }, ensure_ascii=False, indent=2), encoding='utf-8')
    # Whole-batch qualification: never discard a wrong accepted value using truth
    # and then pass the remaining values to the version demonstrator.
    assert not counts.get('FAIL', 0), 'An accepted value was wrong; batch must not enter replay'
    certified = {tuple(r['actual'][k] for k in ['id', 'field', 'period', 'column', 'scope', 'mode']):
                 r['actual'] for r in scored if r['program_accepted_before_truth']}
    (OUT / 'certified_facts.json').write_text(json.dumps({
        'qualification': 'FIXED_CASE_VALUES_ONLY_NOT_PIT',
        'expected_values_excluded_from_runtime_ledger_input': True,
        'parsed_sha256': hashlib.sha256((OUT / 'parsed.json').read_bytes()).hexdigest(),
        'whole_batch_has_zero_incorrect_accepted_values': True,
        'facts': list(certified.values()),
    }, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'counts': counts, 'by_id': {k: dict(Counter(
        r['result'] for r in scored if r['id'] == k)) for k in docs}}, ensure_ascii=True))


if __name__ == '__main__':
    main()
