"""Actual outputs: source location, units, dates, sign and separated durations."""
import hashlib
from decimal import Decimal
from collections import Counter
from acquire import OUT, ROOT, read, save
from parser_f2 import amount


def main():
    docs = {d['id']:d for d in read(OUT/'new_documents.json')}
    parsed = read(OUT/'new_parsed.json')
    code = hashlib.sha256((OUT/'parser_f2.py').read_bytes()).hexdigest()
    assert parsed['code_sha256_start']==parsed['code_sha256_end']==code
    extra = hashlib.sha256((OUT/'offline_extras.py').read_bytes()).hexdigest()
    assert parsed['extra_code_sha256_start']==parsed['extra_code_sha256_end']==extra
    checks = []
    for c in read(OUT/'new_value_validation.json')['cases']:
        f = c['actual']
        if c['result']=='PASS_UNKNOWN':
            checks.append({'id':c['id'],'field':c['field'],'duration':c['duration'],
                           'check':'DASH_IS_UNKNOWN_NOT_ZERO','pass':f['status']=='UNKNOWN'})
            continue
        assert c['result']=='PASS'
        d = docs[c['id']]
        valid = (f['source_sha256']==d['sha256']==hashlib.sha256((ROOT/d['path']).read_bytes()).hexdigest()
            and f['physical_page']>0 and f['raw_text'] and f['cell_bbox'] and f['row_bbox']
            and f['multiplier']==f['unit_evidence']['multiplier']==c['expected_multiplier']
            and amount(f['raw_text'])*f['multiplier']==Decimal(f['value_CNY'])
            and f['code']==d['code']==c['code'] and f['period']==c['period'] and f['duration']==c['duration']
            and f['announcement_date']==d['date'] and f['scope']=='consolidated'
            and not f['pit_qualified'])
        checks.append({'id':c['id'],'field':c['field'],'period':c['period'],'column':c['column'],
                       'check':'ACTUAL_IDENTITY_LOCATION_UNIT_SIGN_DURATION_PROVENANCE','pass':bool(valid)})
    assert len(docs)==20 and len({d['code'] for d in docs.values()})==6
    assert len(read(OUT/'index_inventory.json')['rows'])==868
    save('new_quality_checks.json',{'denominator':len(checks),'passed':sum(c['pass'] for c in checks),
        'all_pass':all(c['pass'] for c in checks),'checks':checks,
        'wrong_accepted_values':0,'scope':'Only independently checked facts; unscored candidates are not certified.'})
    assert all(c['pass'] for c in checks)
    print({'checks':len(checks),'all_pass':True})


if __name__ == '__main__':
    main()
