"""Agent-reviewed field truth and bounded, date-only as-of diagnostics."""
import json
import re
import subprocess
import sys
import time
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from access import OUT, ROOT, R5, read, save, sha, now

RULE='R4_CANDIDATE_DATE_ONLY_NEXT_REAL_SESSION_CLOSE_NOT_OWNER_FROZEN'
AVAIL={'2023-04-25':'2023-04-26','2023-07-26':'2023-07-27','2023-04-29':'2023-05-04','2023-08-31':'2023-09-01','2023-10-31':'2023-11-01','2024-03-29':'2024-04-01','2024-03-16':'2024-03-18','2024-04-23':'2024-04-24','2024-09-30':'2024-10-08','2024-04-30':'2024-05-06'}

def row(file,page,label,count=1):
    pages=read(file+'.pages.json')
    text=pages[page-1]['text']
    m=re.search(r'\s*'.join(re.escape(c) for c in label),text)
    assert m,(file,page,label)
    tail=text[m.end():m.end()+400]
    numbers=re.findall(r'\(?\s*[-−－]?\s*\d{1,3}(?:,\d{3})+(?:\.\d{2})?\s*\)?',tail)[:count]
    assert len(numbers)==count
    vals=[]
    for v in numbers:
        v=re.sub(r'\s+','',v).replace(',','').replace('−','-').replace('－','-')
        if v.startswith('('):
            v='-'+v[1:-1]
        vals.append(str(Decimal(v)))
    return {'physical_page':page,'label':label,'values_CNY':vals,'excerpt':text[max(0,m.start()-80):m.end()+400]}

def truth():
    audit=[]
    for id in ['1216561621','1217386817']:
        values={f:row(id+'.pdf',6,label) for f,label in {'NP':'归属于上市公司股东的净利润','OCF':'经营活动产生的现金流量净额','EQ':'归属于上市公司股东的股东权益'}.items()}
        audit.append({'id':id,'code':'000961','period':'2022-12-31','unit':'CNY','source_sha256':sha(OUT/(id+'.pdf')),'fields':values})
    v2=read('exploratory_v2.json')
    facts=json.loads((R5/'financial_facts.json').read_text(encoding='utf-8'))['facts']
    expected={}
    for r in audit:
        expected[r['id']]={f:v['values_CNY'][0] for f,v in r['fields'].items()}
    key={'NP':'NP_parent','OCF':'OCF_consolidated','EQ':'EQ_parent'}
    for r in v2['results']:
        if r['is_periodic_report'] and r['id'] not in expected:
            expected[r['id']]={f:next(x['CNY_value'] for x in facts if x['official_id']==r['id'] and x['field']==k and x['column']=='current') for f,k in key.items()}
    validations=[]
    for r in v2['results']:
        if r['is_periodic_report']:
            for f in key:
                actual=r['extraction']['fields'][f]['current_CNY']
                validations.append({'source_id':r['id'],'field':f,'extracted':actual,'independent_expected':expected[r['id']][f],'match':Decimal(actual)==Decimal(expected[r['id']][f])})
    assert len(validations)==24
    if not (OUT/'v2_validation_failure.json').exists():
        save('v2_validation_failure.json',{'at_utc':now(),'validation':'FAILED_AUTOMATED_QUALIFICATION','matches':sum(v['match'] for v in validations),'denominator':24,'mismatches':[v for v in validations if not v['match']],'root_cause':'Exploratory two-page concatenation applied a following table RMB-wan header to a preceding RMB-yuan table. First V1 and V2 result files preserved. No V3 tuning, manual number patch or source mutation.','consequence':'Do not admit unvalidated V2 outputs. Replay uses separately verified source facts, not failed extraction.'})
    events=[
      {'source_ids':['1216561621','1217386817'],'kind':'DOCUMENT_UPDATE_NO_TARGET_VALUE_CHANGE','numeric_changed_fields':[],'tested_unchanged_fields':['NP','OCF','EQ'],'evidence':'Both physical p6 equal; 1217386818 p1 limits update to section 六/十二 penalties and rectification, says other content unchanged. Not a new FY2022 monetary fact.'},
      {'source_ids':['1217386818'],'kind':'NON_TARGET_SUPPLEMENT','numeric_changed_fields':[],'other_new_fact':'Adds historical regulatory warning/discipline narrative concerning 2021 forecast accuracy; not new NP/OCF/EQ amounts. No other issuer or cited old notices fetched.'},
      {'source_ids':['1221331382'],'kind':'IRRELEVANT_TO_TESTED_FINANCIAL_FACTS_CORRECTION','numeric_changed_fields':[],'evidence':'Both pages amend director biography/qualification/discipline statements in 2020/2023 governance documents. Mentions other-issuer 2017/2018 reports as background; not a Vanke statement restatement.'},
      {'source_ids':['1219747877'],'kind':'CONFIRMED_COMPARATIVE_MONETARY_CHANGE','code':'000961','financial_period':'2022-12-31','numeric_changed_fields':['NP','EQ'],'unchanged':['OCF'],'financial_fact_first_confirmed_in_this_set':'2024-04-23','earliest_real_world_revision_disclosure':'UNKNOWN_UNREVIEWED_2023_INTERVENING_REPORTS'},
      {'source_ids':['1219487237'],'kind':'CONFIRMED_COMPARATIVE_MONETARY_CHANGE','code':'000002','financial_period':'2022-12-31','numeric_changed_fields':['NP','EQ'],'unchanged':['OCF'],'financial_fact_first_confirmed_in_this_set':'2024-03-29','independent_original_FY2022':'NOT_OBTAINED_DO_NOT_BACKDATE_UNADJUSTED_COMPARATIVE'},
      {'source_ids':['1219313047','1219619642'],'kind':'EPS_ADJUSTMENT_NO_TESTED_MONETARY_CHANGE','code':'300750','numeric_changed_fields':[],'tested_unchanged_fields':['NP','OCF','EQ'],'evidence':'FY2023 p7 comparative monetary columns equal; EPS recalculated for April2023 capital-reserve conversion. Q12024 NP/OCF comparative before/after equal; EQ continuation on p2. No conclusion on untested EPS/PE eligibility.'},
    ]
    first=read('first_run_v1.json')
    monetary_ids=['1219747877','1219487237']
    scored={'metadata_rows':len(first['metadata']),'metadata_candidates':sum(bool(r['candidate_reasons']) for r in first['metadata']),'title_only_rows':sum(r['title_only_B0'] for r in first['metadata']),'four_material_ids_have_metadata_candidates':{id:next(bool(m['candidate_reasons']) for m in first['metadata'] if m['id']==id) for id in ['1216561621','1217386817','1217386818','1221331382']},'actual_monetary_change_source_events':2,'title_only_hits_for_these_two':sum(next(m['title_only_B0'] for m in first['metadata'] if m['id']==id) for id in monetary_ids),'body_candidate_hits_for_these_two':sum(next(b['body_candidate_B1'] for b in first['bodies'] if b['id']==id) for id in monetary_ids),'v1_current_periodic_fields_extracted':sum(bool(b['extraction']['fields'].get(f,{}).get('current_CNY')) for b in first['bodies'] if b['id'] in expected for f in key),'current_periodic_field_denominator':24,'v1_unknown_current_fields':4,'v2_current_validated':sum(v['match'] for v in validations),'v2_current_wrong':sum(not v['match'] for v in validations),'v2_comparative_denominator':9,'v2_comparative_amount_changes':4,'EPS_target_monetary_false_change_count':sum(c['changed'] for c in v2['comparative_column_candidates'] if c['code']=='300750'),'all_notices_automatically_semantically_resolved':False,'unknown_revision_recall':'NOT_ESTABLISHED','not_population_recall_or_precision':True}
    save('field_truth_and_scores.json',{'at_utc':now(),'truth_method':'Agent semantic review and physical-page label checks; no independent human reviewer. Truth is separate from frozen detector. R5 values are already documented manual-page/column audited facts, not unseen validation.','original_and_update_truth':audit,'expected_current_facts':expected,'V2_current_validations':validations,'comparative_truth':v2['comparative_column_candidates'],'events':events,'scores':scored})
    print(json.dumps(scored,ensure_ascii=False))

def replay():
    gold=read('field_truth_and_scores.json')
    v1=read('first_run_v1.json')
    body={d['id']:d for d in v1['bodies']}
    ledger=[]
    def add(code,period,field,value,id,date,version):
        ledger.append({'security_id':'SZ:'+code,'financial_period':period,'field_name':field,'field_value':value,'unit':'CNY','disclosure_id':id,'disclosure_date':date,'version_identity':version,'source_sha256':body[id]['source_sha256'],'available_from_candidate':AVAIL[date],'availability_rule':RULE,'quality_status':'SOURCE_VALUE_CONFIRMED_FIXED_SET_NOT_FULL_CHAIN_CERTIFICATION'})
    for f,v in gold['expected_current_facts']['1216561621'].items():
        add('000961','2022-12-31',f,v,'1216561621','2023-04-25','FY2022_MONETARY_ORIGINAL')
    for c in gold['comparative_truth']:
        if c['source_id'] in ['1219747877','1219487237']:
            date='2024-04-23' if c['source_id']=='1219747877' else '2024-03-29'
            add(c['code'],'2022-12-31',c['field'],c['after'],c['source_id'],date,'FY2022_COMPARATIVE_ADJUSTED_IN_FY2023')
    for f,v in gold['expected_current_facts']['1219487237'].items():
        add('000002','2023-12-31',f,v,'1219487237','2024-03-29','FY2023_REPORTED_CURRENT')
    for c in gold['comparative_truth']:
        if c['source_id']=='1219313047':
            add(c['code'],'2022-12-31',c['field'],c['after'],c['source_id'],'2024-03-16','FY2022_EQUAL_MONETARY_COMPARATIVES_EPS_ONLY_DIAGNOSTIC')
    metadata=v1['metadata']
    unread=[m for m in metadata if m['code']=='000961' and m['id'] not in body and m['period'] and m['period'].startswith('2023') and 'periodic' in m['queried_kinds'] and not any(k in m['title'] for k in ['摘要','英文','H股'])]
    results=[]
    def select(name,code,period,T,strict=True,conflict=False):
        out=[]
        for field in ['NP','OCF','EQ']:
            eligible=[r for r in ledger if r['security_id']=='SZ:'+code and r['financial_period']==period and r['field_name']==field and r['available_from_candidate']<=T]
            selected=max(eligible,key=lambda r:r['available_from_candidate']) if eligible else None
            blockers=[]
            if selected and strict and code=='000961':
                blockers=[m['id'] for m in unread if AVAIL.get(m['date'],m['date'])<=T and m['date']>selected['disclosure_date']]
            if selected and not blockers and not conflict:
                row={**selected,'decision_date':T,'quality_status':'SELECTED_FIXED_EVIDENCE_SET_ONLY'}
            else:
                row={'security_id':'SZ:'+code,'financial_period':period,'field_name':field,'field_value':None,'unit':'CNY','disclosure_id':None,'disclosure_date':None,'version_identity':'UNKNOWN','source_sha256':None,'decision_date':T,'availability_rule':RULE,'quality_status':'UNKNOWN_SOURCE_CONFLICT_TEST' if conflict else 'UNKNOWN_UNREVIEWED_INTERVENING_REPORTS' if blockers else 'UNKNOWN_NO_ELIGIBLE_ORIGINAL','blocked_by_ids':blockers}
            out.append(row)
        result={'test':name,'decision_date':T,'mode':'STRICT_KNOWN_GAP_GUARD' if strict else 'KNOWN_LEDGER_ONLY_UPPER_BOUND_NOT_REAL_WORLD_PASS','synthetic_conflict_guard_test':conflict,'selected':out}
        results.append(result)
        return out
    a=select('before_original','000961','2022-12-31','2023-04-24')
    assert all(r['field_value'] is None for r in a)
    a=select('first_candidate_session_after_original','000961','2022-12-31','2023-04-26')
    assert all(r['disclosure_id']=='1216561621' for r in a)
    a=select('before_nonfinancial_update_known_ledger_only','000961','2022-12-31','2023-07-25',strict=False)
    assert all(r['disclosure_id']=='1216561621' for r in a)
    a=select('after_nonfinancial_update_known_ledger_only','000961','2022-12-31','2023-07-27',strict=False)
    assert all(r['disclosure_id']=='1216561621' for r in a)
    a=select('after_nonfinancial_update_strict_gap','000961','2022-12-31','2023-07-27')
    assert all(r['field_value'] is None for r in a)
    a=select('on_new_report_date_before_candidate_availability','000961','2022-12-31','2024-04-23')
    assert all(r['field_value'] is None for r in a)
    a=select('after_confirmed_adjusted_comparative','000961','2022-12-31','2024-04-24')
    assert all(r['disclosure_id']=='1219747877' for r in a)
    before=select('vanke_before_irrelevant_correction','000002','2023-12-31','2024-09-27')
    after=select('vanke_after_irrelevant_correction','000002','2023-12-31','2024-10-08')
    assert [r['field_value'] for r in before]==[r['field_value'] for r in after]
    assert all(r['disclosure_id']=='1219487237' for r in after)
    a=select('missing_vanke_original_never_backfill_from_comparative','000002','2022-12-31','2023-04-26')
    assert all(r['field_value'] is None for r in a)
    a=select('vanke_comparative_only_after_its_verified_disclosure','000002','2022-12-31','2024-04-01')
    assert all(r['disclosure_id']=='1219487237' for r in a)
    a=select('EPS_control_before_document','300750','2022-12-31','2024-03-15')
    assert all(r['field_value'] is None for r in a)
    a=select('EPS_control_after_document','300750','2022-12-31','2024-03-18')
    assert all(r['disclosure_id']=='1219313047' for r in a)
    a=select('unresolved_conflict_fail_closed_TEST_ONLY','000961','2022-12-31','2024-04-24',conflict=True)
    assert all(r['field_value'] is None for r in a)
    # Negative leakage test uses real stored values, never invented historical originals.
    ths={}
    for table,field,key in [('benefit','NP','parent_holder_net_profit'),('cash','OCF','act_cash_flow_net'),('debt','EQ','parent_holder_equity_total')]:
        raw=json.loads((R5/('000961_ths_'+table+'.json')).read_text(encoding='utf-8'))
        rec=next(r for r in raw['data']['data'] if r['date']=='2022-12-31')
        ths[field]=rec['index_list'][key]['value']
    original=gold['expected_current_facts']['1216561621']
    leakage=[{'field':f,'current_structured':v,'real_original':original[f],'differs':Decimal(v)!=Decimal(original[f]),'candidate_decision_date':'2023-04-26','structured_row_admitted_by_absence_of_alert':False} for f,v in ths.items()]
    assert sum(r['differs'] for r in leakage)==2
    for result in results:
        for r in result['selected']:
            assert all(k in r for k in ['security_id','financial_period','field_name','field_value','unit','disclosure_id','disclosure_date','version_identity','source_sha256','decision_date','availability_rule','quality_status'])
    save('version_ledger_and_replay.json',{'availability_rule':RULE,'ledger':ledger,'metadata_only_non_numeric_events':[{'id':'1217386817','date':'2023-07-26','replaces_financial_values':False},{'id':'1217386818','date':'2023-07-26','replaces_financial_values':False},{'id':'1221331382','date':'2024-09-30','replaces_financial_values':False}],'known_unreviewed_intervening_reports':unread,'first_actual_adjustment_date':'UNKNOWN_NOT_ASSUMED_TO_BE_FY2023_REPORT_DATE','tests':results,'test_count':len(results),'diagnostic_assertions':'PASS_BOUNDED_WITH_EXPLICIT_UNKNOWN_AND_SYNTHETIC_CONFLICT_GUARD','current_structured_backfill_rejection':leakage,'real_source_conflict_observed':False,'unknown_revision_recall':'NOT_ESTABLISHED','full_history_gate':'NOT_PASSED'})
    print(json.dumps({'tests':len(results),'ledger_facts':len(ledger),'unreviewed_intervening_reports':len(unread),'naive_current_row_future_leaks':sum(r['differs'] for r in leakage),'diagnostic':'PASS_BOUNDED_NOT_CHAIN_QUALIFICATION'}))

def render():
    binary=Path('C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/poppler/Library/bin/pdftoppm.exe')
    logs=[]
    for id,page in [('1216561621',6),('1217386817',6),('1217386818',1),('1221331382',1),('1221331382',2)]:
        start=time.perf_counter()
        r=subprocess.run([str(binary),'-f',str(page),'-l',str(page),'-scale-to','1800','-jpeg','-jpegopt','quality=85',str(OUT/(id+'.pdf')),str(OUT/(id+'_qa'))],capture_output=True,encoding='utf-8',errors='replace')
        logs.append({'id':id,'physical_page':page,'returncode':r.returncode,'seconds':time.perf_counter()-start,'stderr':r.stderr,'images':[p.name for p in OUT.glob(id+'_qa-*.jpg')]})
        assert r.returncode==0
    save('render_log.json',logs)
    print(json.dumps({'rendered_pages':len(logs),'all_returncode_zero':True}))

if __name__=='__main__':
    {'truth':truth,'replay':replay,'render':render}[sys.argv[1]]()
