"""Final read-only archival checks and manifest; no network or Git mutations."""
import hashlib,json,subprocess,sys
from datetime import datetime,timezone
from pathlib import Path
from fetch_named import OUT,ROOT,F2,read,save

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def main():
    before=read(OUT/'before.json')
    changed=[p for p,h in before['tracked_sha256'].items() if not (ROOT/p).is_file() or sha(ROOT/p)!=h]
    assert not changed, changed
    for d in read(OUT/'authority_inputs.json'):
        assert sha(ROOT/d['path'])==d['sha256']
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    assert head==before['head']=='92d85ef7edc10a7663cce329589c5a0c8eb4bebd'
    status=subprocess.check_output(['git','status','--porcelain=v1','--untracked-files=normal'],cwd=ROOT,text=True).splitlines()
    assert set(before['status'])<=set(status)
    delta=set(status)-set(before['status'])
    allowed={'?? docs/audits/2026-10-21-w5h-f2-source-closure.md',
             '?? docs/audits/evidence/2026-10-21-w5h-f2-source-closure/'}
    assert delta==allowed,delta
    assert not subprocess.check_output(['git','diff','--name-only'],cwd=ROOT,text=True).strip()
    package=read(OUT/'closure_package_run.json')
    assert package['complete'] and package['code_sha256_start']==package['code_sha256_end']
    for name,h in package['code_sha256_end'].items():assert sha(OUT/name)==h
    assert read(OUT/'regression_run.json')['complete']
    docs={d['id']:d for d in read(OUT/'documents.json')}
    plan=read(OUT/'preregistration.json')
    index={r['id']:r for r in read(F2/'index_inventory.json')['rows']}
    for d in docs.values():
        assert sha(ROOT/d['path'])==d['sha256']
        assert all(d[k]==index[d['id']][k] for k in ['code','date','url'])
    facts=read(OUT/'parsed_source_facts.json')
    assert facts['code_sha256']==sha(OUT/'extract_facts.py')
    from extract_facts import base
    for f in facts['facts']:
        assert base.amount(f['raw_text'])*f['multiplier']==__import__('decimal').Decimal(f['value_CNY'])
        assert f['unit_evidence']['multiplier']==f['multiplier'] and f['unit_evidence']['physical_page']<=f['physical_page']
        assert f['source_sha256']==docs[f['id']]['sha256'] and f['physical_page']>0
        assert f['duration']!='DURATION_UNKNOWN' and not f['pit_qualified']
    ocr_checked=0
    for folder in ['ocr','ocr-en','crop-ocr']:
        for p in (OUT/folder).glob('*.json'):
            obj=read(p)
            assert obj['source_sha256']==docs[obj['id']]['sha256']
            ocr_checked+=1
    for name in ['ocr_plan.json','ocr_en_plan.json','crop_probe_plan.json']:
        for item in read(OUT/name):
            o=read(item['output'])
            assert sha(item['image'])==o['image_sha256']
    assert ocr_checked==328
    value=read(OUT/'source_value_validation.json')
    assert value['denominator']==24 and value['counts']=={'PASS':22,'UNKNOWN':2}
    replay=read(OUT/'closure_replay_validation.json')
    assert replay['counts']=={'PASS':23} and replay['all_output_denominator']==141
    qual=read(OUT/'source_qualification.json')
    assert qual['denominator']==23 and qual['resolved']==12
    assert qual['candidate_denominator']==176
    report=ROOT/'docs/audits/2026-10-21-w5h-f2-source-closure.md'
    assert 'SOURCE_CLOSED_WITH_NAMED_UNKNOWN' in report.read_text(encoding='utf-8')
    payload={'finished_at_utc':datetime.now(timezone.utc).isoformat(),'head':head,
        'working_tree_tracked_files':len(before['tracked_sha256']),'tracked_bytes_unchanged':not changed,
        'archived_f2_unchanged':True,'authority_inputs_unchanged':True,
        'original_untracked_status_entries_preserved':len(before['status']),'final_status':status,
        'only_added_status':sorted(delta),'raw_official_identity_and_sha_checks':len(docs),
        'all_candidate_provenance_checks':len(facts['facts']),'ocr_identity_and_image_sha_checks':ocr_checked,
        'core_package_sha_matches_tested_code':True,'new_value_checks':value['counts'],
        'new_replay_assertions':23,'old_regression_complete':True,
        'report':{'path':report.relative_to(ROOT).as_posix(),'sha256':sha(report)},
        'git_commit':'NO','git_push':'NO','production_change':'NO'}
    save('final_integrity.json',payload)
    entries=[{'path':p.relative_to(ROOT).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)}
             for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='manifest.json']
    save('manifest.json',{'files':entries,'count':len(entries),'bytes':sum(e['bytes'] for e in entries),
         'report':payload['report'],'excluded_self':'manifest.json cannot contain its own hash'})
    assert all(sha(ROOT/e['path'])==e['sha256'] for e in entries)
    print(json.dumps({'protected_tracked':len(before['tracked_sha256']),'evidence_files':len(entries),
        'evidence_bytes':sum(e['bytes'] for e in entries),'candidate_records':len(facts['facts']),
        'all_checks':'PASS','head':head,'status_entries':len(status)}))

if __name__=='__main__':main()
