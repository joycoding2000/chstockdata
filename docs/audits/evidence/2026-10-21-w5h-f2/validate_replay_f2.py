"""Expected values are confined to this independent check, never selection input."""
from decimal import Decimal
from collections import Counter
from acquire import OUT, read, save


def main():
    results = {q['query_id']:q for q in read(OUT/'replay_results_f2.json')}
    scored = []
    for c in read(OUT/'replay_expected_f2.json')['cases']:
        r = results[c['query_id']]
        ok = r['status']==c['status'] and (r['value_CNY'] is None and c['value_CNY'] is None or
            r['value_CNY'] is not None and c['value_CNY'] is not None and
            Decimal(r['value_CNY'])==Decimal(c['value_CNY']))
        scored.append({'query_id':c['query_id'],'result':'PASS' if ok else 'FAIL',
                       'expected':c,'actual':r})
    eps = [f for d in read(OUT/'auxiliary_evidence.json')['eps'] for f in d['facts']]
    aux_checks = []
    for c in read(OUT/'expected_eps.json')['expected']:
        got = [f for f in eps if all(f[k]==c[k] for k in ('id','period','column'))]
        ok = bool(got) and all(Decimal(f['value_per_share'])==Decimal(c['value']) and
                              f['unit']=='元/股' for f in got)
        aux_checks.append({'expected':c,'actual':got,'result':'PASS' if ok else 'FAIL'})
    counts = dict(Counter(r['result'] for r in scored))
    save('replay_validation_f2.json',{'denominator':len(scored),'counts':counts,
        'eps_control_checks':aux_checks,'cases':scored})
    print({'counts':counts,'eps':dict(Counter(r['result'] for r in aux_checks)),
           'failed':[(r['query_id'],r['actual'].get('reason'),r['actual'].get('value_CNY'))
                     for r in scored if r['result']=='FAIL']})
    assert not counts.get('FAIL') and all(r['result']=='PASS' for r in aux_checks)


if __name__ == '__main__':
    main()
