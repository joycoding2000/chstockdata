"""R6 delivery verification; does not qualify a production data source."""
import json
import re
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from pypdf import PdfReader
from access import OUT, ROOT, read, save, sha, snapshot, now

REPORT=ROOT/'docs/audits/2026-10-21-w5h-r6-version-exception-qualification.md'

before=read('before.json')
after=snapshot()
save('after.json',after)
protected=[]
for name,b in before['repos'].items():
    a=after['repos'][name]
    assert b['head']==a['head'] and b['tracked']==a['tracked'],name
    old_tracked_status=[s for s in b['status'].splitlines() if not s.startswith('??')]
    new_tracked_status=[s for s in a['status'].splitlines() if not s.startswith('??')]
    assert old_tracked_status==new_tracked_status,name
    assert set(b['untracked']).issubset(a['untracked']),name
    additions=sorted(set(a['untracked'])-set(b['untracked']))
    if name=='chstockdata':
        assert all(p==REPORT.relative_to(ROOT).as_posix() or p.startswith('docs/audits/evidence/2026-10-21-w5h-r6/') for p in additions),additions
    protected.append({'repository':name,'head':a['head'],'branch':a['branch'],'tracked_content_count':len(a['tracked']),'tracked_content_and_status_unchanged':True,'original_untracked_names_preserved':True,'new_untracked':additions if name!='chstockdata' else 'ONLY_R6_ALLOWLIST'})
for p,h in before['inputs'].items():
    assert sha(Path(p))==h,p
for r in read('R5_manifest_checks.json')['files']:
    assert sha(Path(r['path']))==r['expected_sha256'],r['path']

rules=read('discovery_rules_v1.json')
assert sha(OUT/'discovery_rules_v1.json')==read('discovery_rules_v1_identity.json')['sha256']
assert sha(OUT/'experiment_v1.py')==read('experiment_v1_code_identity.json')['sha256']
assert sha(OUT/'first_run_v1.json')==read('first_run_v1_identity.json')['sha256']
reqs=read('requests.json')['requests']
assert len(reqs)==4
assert datetime.fromisoformat(rules['registered_at_utc'])<datetime.fromisoformat(reqs[0]['started_at'])
assert datetime.fromisoformat(read('experiment_v1_code_identity.json')['sealed_at_utc'])<datetime.fromisoformat(read('first_run_v1.json')['executed_at_utc'])
assert len({r['url'] for r in reqs})==4
gaps=[]
for i,r in enumerate(reqs):
    assert r['status']=='PDF_SAVED' and sha(OUT/r['file'])==r['sha256'] and (OUT/r['file']).stat().st_size==r['bytes']
    if i:
        gap=(datetime.fromisoformat(r['started_at'])-datetime.fromisoformat(reqs[i-1]['finished_at'])).total_seconds()
        assert gap>=2.99
        gaps.append(gap)
assert sum(r['bytes'] for r in reqs)==16_275_600
assert sum(d['pages'] for d in read('new_document_inventory.json'))==545

first=read('first_run_v1.json')
gold=read('field_truth_and_scores.json')
v2=read('exploratory_v2.json')
assert len(first['metadata'])==44 and len(first['bodies'])==10
assert gold['scores']['v2_current_validated']==21 and gold['scores']['v2_current_wrong']==3
assert read('v2_validation_failure.json')['validation']=='FAILED_AUTOMATED_QUALIFICATION'
v1_checks=[]
for b in first['bodies']:
    expected=gold['expected_current_facts'].get(b['id'])
    if expected:
        for f,val in expected.items():
            actual=b['extraction']['fields'].get(f,{}).get('current_CNY')
            v1_checks.append({'id':b['id'],'field':f,'actual':actual,'expected':val,'status':'UNKNOWN' if actual is None else 'MATCH' if Decimal(actual)==Decimal(val) else 'MISMATCH'})
assert len(v1_checks)==24 and sum(r['status']=='MATCH' for r in v1_checks)==20 and sum(r['status']=='UNKNOWN' for r in v1_checks)==4
facts=json.loads((OUT.parent/'2026-10-20-w5h-r5/financial_facts.json').read_text(encoding='utf-8'))['facts']
for c in v2['comparative_column_candidates']:
    field={'NP':'NP_parent','OCF':'OCF_consolidated','EQ':'EQ_parent'}[c['field']]
    for key,col in [('before','unadjusted'),('after','adjusted')]:
        expected=next(f['CNY_value'] for f in facts if f['official_id']==c['source_id'] and f['field']==field and f['column']==col)
        assert Decimal(expected)==Decimal(c[key])

replay=read('version_ledger_and_replay.json')
assert replay['test_count']==14 and len(replay['ledger'])==15
assert len(replay['known_unreviewed_intervening_reports'])==3
assert replay['full_history_gate']=='NOT_PASSED'
assert sum(r['differs'] for r in replay['current_structured_backfill_rejection'])==2
for t in replay['tests']:
    for r in t['selected']:
        assert all(k in r for k in ['security_id','financial_period','field_name','field_value','unit','disclosure_id','disclosure_date','version_identity','source_sha256','decision_date','availability_rule','quality_status'])
        if r['field_value'] is not None:
            assert r['disclosure_date']<r['decision_date']
page_checks=[]
for r in read('render_log.json'):
    file=r['id']+'.pdf'
    expected=read(file+'.pages.json')[r['physical_page']-1]['text']
    actual=PdfReader(OUT/file).pages[r['physical_page']-1].extract_text() or ''
    assert expected==actual
    page_checks.append({'file':file,'physical_page':r['physical_page'],'fresh_text_matches':True})
assert len(page_checks)==5

cost=read('cost_ledger.json')
assert cost['HUMAN_REVIEW_TIME']=='NOT_MEASURED'
assert cost['real_replay_cases']==11 and cost['real_replay_slots']==33 and cost['real_replay_unknown']==15
text=REPORT.read_text(encoding='utf-8')
required=['CURRENT_DECISION','W5_H_R6_VERDICT','KNOWN_REVISION_FILES','FINANCIAL_VALUE_CHANGE_EVENTS','IRRELEVANT_CORRECTION_EVENTS','REVISION_DETECTION_FIXED_CASE','UNKNOWN_REVISION_RECALL = NOT_ESTABLISHED','STRUCTURED_VALUE_ASOF','FIXED_CASE_VERSION_SELECTION','AUTOMATED_WORK_EVIDENCE','AGENT_ASSISTED_WORK_EVIDENCE','REAL_HUMAN_REVIEW_COST','MANUAL_EXCEPTION_DEPENDENCY','FULL_UNIVERSE_DELIVERY_COST_CONFIDENCE','RECOMMENDED_SUPPLY_ROUTE','OWNER_SUPPLY_DECISION_REQUIRED','NEXT_MINIMUM_ACTION','MISHI_S07_HISTORICAL_GATE = NOT_PASSED','PRODUCT_SCOPE_CHANGED = NO','PRODUCTION_IMPLEMENTATION_AUTHORIZED = NO','GIT_COMMIT = NO','GIT_PUSH = NO','OWNER_REVIEW_REQUIRED = YES']
assert all(k in text for k in required)
for link in re.findall(r'\]\(([^)]+)\)',text):
    if not link.startswith('https://'):
        target=(REPORT.parent/link).resolve()
        if target not in [(OUT/'final_verification.json').resolve(),(OUT/'manifest.json').resolve()]:
            assert target.exists(),link
assert not re.findall(r"['\"]\d{10}['\"]",(OUT/'experiment_v1.py').read_text(encoding='utf-8')),'IDs must not be detector predicates'
save('final_verification.json',{'at_utc':now(),'delivery_verification':'PASS','qualification_verdict':'MANUAL_VERIFICATION_DOMINANT','automated_qualification':'NOT_PASSED_EXPECTED_FAILURES_PRESERVED','protected_repositories':protected,'protected_prior_R5_files':86,'frozen_rule_code_first_result_hashes':'PASS','direct_requests':4,'min_same_host_gap_seconds':min(gaps),'first_pass_current_fact_checks':v1_checks,'V2_validation':{'correct':21,'wrong':3,'denominator':24},'fresh_source_page_checks':page_checks,'asof_diagnostic_tests':14,'asof_complete_chain':'NOT_PASSED','HUMAN_REVIEW_TIME':'NOT_MEASURED','MISHI_S07_HISTORICAL_GATE':'NOT_PASSED','commit_push_release':False})
files=[{'path':p.name,'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(OUT.iterdir()) if p.is_file() and p.name!='manifest.json']
save('manifest.json',{'at_utc':now(),'report':{'path':str(REPORT),'bytes':REPORT.stat().st_size,'sha256':sha(REPORT)},'files':files})
assert (OUT/'final_verification.json').exists() and (OUT/'manifest.json').exists()
print(json.dumps({'delivery_verification':'PASS','verdict':'MANUAL_VERIFICATION_DOMINANT','evidence_files_excluding_manifest':len(files),'tracked_files_protected':sum(len(r['tracked']) for r in before['repos'].values()),'current_structured_backfill_rejected':True,'S07':'NOT_PASSED'}))
