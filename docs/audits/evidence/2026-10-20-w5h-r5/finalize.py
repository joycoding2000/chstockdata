"""Offline cost ledger and delivery checks for this one screen only."""
import json
import re
import statistics
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from pypdf import PdfReader
from measure import OUT, ROOT, REG, read, save, sha, snapshot, now

REPORT=ROOT/'docs/audits/2026-10-20-w5h-r5-historical-disclosure-scale-cost-screen.md'

def summary():
    reqs=read('requests.json')['requests']
    pdfs=read('pdf_measurements.json')
    for r in reqs:
        if r['file'].endswith('.pdf') and 'identity' in r['file']:
            r['pdf_pages']=len(PdfReader(OUT/r['file']).pages)
    spans=read('review_spans.json')
    for r in spans['spans']:
        r['observable_wall_seconds']=(datetime.fromisoformat(r['end_utc'])-datetime.fromisoformat(r['start_utc'])).total_seconds()
    save('review_spans.json',spans)
    mean_bytes=statistics.mean(m['bytes'] for m in pdfs)
    mean_pages=statistics.mean(m['pages'] for m in pdfs)
    mean_parse=statistics.mean(m['machine_parse_wall_seconds'] for m in pdfs)
    scale=[]
    for periods in [6,8,10]:
        files=5000*periods
        scale.append({'N_assumption_NOT_current_or_historical_pool_count':5000,'F_scenario_not_frozen_requirement':periods,'original_files_excluding_corrections':files,'GB_decimal_using_balanced_sample_mean':files*mean_bytes/1e9,'pages_using_balanced_sample_mean':files*mean_pages,'single_process_parse_hours_using_local_measurement':files*mean_parse/3600,'serial_three_second_guard_hours_pdf_and_4_index_identity_calls_per_issuer':3*(files+4*5000-2)/3600,'all_PDF_human_1_min_per_doc_hours_ASSUMPTION':files/60,'all_PDF_human_5_min_per_doc_hours_ASSUMPTION':files*5/60})
    totalwall=(datetime.fromisoformat(reqs[-1]['finished_at'])-datetime.fromisoformat(reqs[0]['started_at'])).total_seconds()
    data={'direct_requests':len(reqs),'direct_budget':REG['budget']['direct_requests'],'direct_failed':sum(r['status']!='RESPONSE_SAVED' for r in reqs),'automatic_retries':0,'manual_network_retries':0,'saved_network_bytes':sum(r['bytes'] for r in reqs),'HTTP_wall_seconds':sum(r['http_wall_seconds'] for r in reqs),'throttle_sleep_seconds':sum(r['throttle_sleep_seconds'] for r in reqs),'request_span_wall_seconds':totalwall,'orchestration_gap_seconds_NOT_human_labor':totalwall-sum(r['http_wall_seconds']+r['throttle_sleep_seconds'] for r in reqs),'target_PDF_count':10,'target_PDF_bytes':sum(m['bytes'] for m in pdfs),'target_PDF_pages':sum(m['pages'] for m in pdfs),'target_download_HTTP_wall_seconds':sum(r['http_wall_seconds'] for r in reqs if any(r['file']==m['file'] for m in pdfs)),'additional_identity_PDF':next(r for r in reqs if 'identity.pdf' in r['file']),'machine_parse_wall_seconds':sum(m['machine_parse_wall_seconds'] for m in pdfs),'machine_field_extraction_wall_seconds':read('financial_facts.json')['machine_field_extraction_wall_seconds'],'machine_JSON_comparison_wall_seconds':read('structured_comparison.json')['machine_json_and_compare_wall_seconds'],'structured_files':6,'structured_bytes':sum(r['bytes'] for r in reqs if '_ths_' in r['file']),'structured_HTTP_wall_seconds':sum(r['http_wall_seconds'] for r in reqs if '_ths_' in r['file']),'matched_two_issuer_PDF_bytes':sum(m['bytes'] for m in pdfs if m['code'] in ['600519','000961']),'matched_two_issuer_PDF_parse_seconds':sum(m['machine_parse_wall_seconds'] for m in pdfs if m['code'] in ['600519','000961']),'assisted_review_spans':spans['spans'],'paid_human_effort_person_hours':'UNKNOWN_NOT_MEASURED','human_numeric_transcriptions':0,'page_label_column_plans_manually_chosen':10,'production_parser_setup_or_engineering_cost':'NOT_MEASURED_NOT_IMPLEMENTED','scaling_scenarios':scale,'hybrid_exception_sensitivity_for_40000_docs_10_minutes_per_exception_NOT_observed':[{'exception_fraction_assumed':p,'human_hours_scenario':40000*p*10/60} for p in [.01,.05,.20]],'scaling_limit':'No population success rate; balanced annual/Q1 workload is not actual 8-period mix, hence only order-of-magnitude. Current/historical N, actual exceptions, legal capacity, engineering, independent QA and daily PE not measured.'}
    save('cost_summary.json',data)
    print(json.dumps({k:data[k] for k in ['direct_requests','saved_network_bytes','target_PDF_bytes','target_PDF_pages','machine_parse_wall_seconds','scaling_scenarios']},ensure_ascii=False))

def verify():
    before=read('before.json')
    after=snapshot()
    save('after.json',after)
    regid=read('preregistration_identity.json')
    assert sha(OUT/'preregistration.json')==regid['sha256']
    reqs=read('requests.json')['requests']
    assert datetime.fromisoformat(REG['registered_at_utc'])<datetime.fromisoformat(reqs[0]['started_at'])
    assert len(reqs)==37 and len(reqs)<=REG['budget']['direct_requests']
    assert len([r for r in reqs if r['file'].endswith('.pdf')])==11
    for r in reqs:
        assert r['status']=='RESPONSE_SAVED'
        assert sha(OUT/r['file'])==r['sha256'] and (OUT/r['file']).stat().st_size==r['bytes']
    intervals=[]
    last={}
    for r in reqs:
        if r['host'] in last:
            gap=(datetime.fromisoformat(r['started_at'])-datetime.fromisoformat(last[r['host']]['finished_at'])).total_seconds()
            assert gap>=2.99,gap
            intervals.append(gap)
        last[r['host']]=r
    facts=read('financial_facts.json')
    assert facts['current_facts_extracted']==30 and len(facts['facts'])==75
    assert read('structured_comparison.json')['current_value_matches']==12
    assert read('case_costs_and_denominators.json')['inventory_found']==38
    assert len(read('pdf_measurements.json'))==10
    # Re-read six physically rendered source pages instead of testing regex against itself.
    page_checks=[]
    for r in read('render_log.json'):
        actual=PdfReader(OUT/r['file']).pages[r['page']-1].extract_text() or ''
        expected=read(r['file']+'.pages.json')[r['page']-1]['text']
        assert actual==expected
        page_checks.append({'file':r['file'],'physical_page':r['page'],'fresh_text_matches':True})
    protected=[]
    for name,b in before['repos'].items():
        a=after['repos'][name]
        assert a['head']==b['head'] and a['tracked']==b['tracked']
        missing=set(b['untracked'])-set(a['untracked'])
        assert not missing
        new=sorted(set(a['untracked'])-set(b['untracked']))
        if name=='chstockdata':
            assert all(p.startswith('docs/audits/evidence/2026-10-20-w5h-r5/') or p==REPORT.relative_to(ROOT).as_posix() for p in new),new
        protected.append({'repository':name,'head':a['head'],'tracked_content_count':len(b['tracked']),'tracked_unchanged':True,'preexisting_untracked_names_preserved':True,'new_untracked_paths':new if name!='chstockdata' else 'ONLY_R5_ALLOWLIST'})
    for p,h in before['inputs'].items():
        assert sha(Path(p))==h
    for r in read('reused_control_checks.json')['files']:
        assert sha(Path(r['file']))==r['expected_sha256']
    text=REPORT.read_text(encoding='utf-8')
    for key in ['CURRENT_DECISION','FIXED_SAMPLE_COVERAGE','ORIGINAL_VERSION_RETRIEVABILITY','REVISION_CHAIN_EVIDENCE','FINANCIAL_FIELDS_COVERAGE','MACHINE_EXTRACTION_EVIDENCE','MANUAL_HANDLING_COST','FULL_UNIVERSE_SCALING_RISK','RECOMMENDED_SUPPLY_PATH','NEXT_MINIMUM_ACTION','MISHI_S07_HISTORICAL_GATE = NOT_PASSED','PRODUCT_SCOPE_CHANGED = NO','IMPLEMENTATION_AUTHORIZED = NO','GIT_COMMIT = NO','GIT_PUSH = NO','OWNER_REVIEW_REQUIRED = YES']:
        assert key in text,key
    save('final_verification.json',{'at_utc':now(),'delivery_check':'PASS','verdict':'FEASIBLE_FOR_NEXT_SOURCE_QUALIFICATION','source_qualification_not_passed':True,'direct_request_count':len(reqs),'source_min_same_host_gap_seconds':min(intervals),'preregistration_unchanged_and_precedes_results':True,'protected':protected,'fresh_PDF_page_checks':page_checks,'old_control_sha_rechecked':4,'formula_freeze_or_backtest':False,'offline_measurement_repairs':['issuer prefix / 年年度 vs 年度 / 一季度 title aliases','empty special OCF alias rejected; actual act_cash_flow_net from saved R2 parser adopted','Path import restored for render; no numeric transcription repairs or network retries'],'S07':'NOT_PASSED'})
    files=[{'path':p.name,'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(OUT.iterdir()) if p.is_file() and p.name!='manifest.json']
    save('manifest.json',{'at_utc':now(),'report':{'path':str(REPORT),'bytes':REPORT.stat().st_size,'sha256':sha(REPORT)},'files':files})
    print(json.dumps({'delivery_check':'PASS','files':len(files),'requests':len(reqs),'tracked_protected':sum(len(r['tracked']) for r in before['repos'].values()),'S07':'NOT_PASSED'}))

if __name__=='__main__':
    {'summary':summary,'verify':verify}[sys.argv[1]]()
