"""Offline R4 final verification. Network probes are never re-executed."""
import ast
import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from pypdf import PdfReader
from audit_common import OUT, ROOT, read, save, sha

REPORT=ROOT/'docs/audits/2026-10-20-w5h-r4-tdx-revision-root-cause-and-archival-pit.md'
PREFIX='docs/audits/evidence/2026-10-20-w5h-r4/'

def git(root,*args):
    r=subprocess.run(['git','-c',f'safe.directory={root.as_posix()}','-C',str(root),*args],capture_output=True,encoding='utf-8',errors='replace')
    assert r.returncode==0,(args,r.stderr)
    return r.stdout

def main():
    request_count=len(read('requests.json')['requests'])
    # Fresh replay uses real source files, not a cached PASS flag.
    r=subprocess.run([str(ROOT/'.venv/Scripts/python.exe'),'-B',str(OUT/'build_replay.py')],cwd=ROOT,capture_output=True,encoding='utf-8',errors='replace')
    (OUT/'replay.stdout.txt').write_text(r.stdout,encoding='utf-8')
    (OUT/'replay.stderr.txt').write_text(r.stderr,encoding='utf-8')
    assert r.returncode==0,r.stderr
    assert len(read('requests.json')['requests'])==request_count==16

    prior=read('prior_manifest_checks.json')['files']
    assert all(sha(Path(x['path']))==x['expected_sha256'] for x in prior)
    assert len(prior)==145
    pdf_checks=[]
    for name,selected in [('official_original_2017.pdf',[6,7,106,107,108]),('official_annual_2018.pdf',[6,7,115,116,117]),('official_regulatory_letter_20190501.pdf',[1,2])]:
        p=OUT/name;assert p.read_bytes().startswith(b'%PDF-')
        reader=PdfReader(p);extracted=read(name+'.pages.json')
        assert len(reader.pages)==len(extracted)
        for number in selected:
            assert (reader.pages[number-1].extract_text() or '')==extracted[number-1]['text'],(name,number)
        pdf_checks.append({'file':name,'sha256':sha(p),'pages':len(reader.pages),'selected_page_texts_reextracted_and_matched':selected})
    audit=PdfReader(OUT/'correction_audit_20190430.pdf')
    assert len(audit.pages)==11
    assert not any(p.extract_text() for p in audit.pages)
    ids=read('official_document_identities.json')
    assert all(sha(OUT/d['file'])==d['sha256'] for d in ids.values())

    states=read('three_date_information_sets.json')['states']
    required={'security_id','financial_period','field_name','value','unit','accounting_basis','disclosure_id','disclosure_date','version_identity','decision_date','availability_rule','provenance','quality_status'}
    assert len(states)==3 and all(len(x)==4 for x in states.values())
    for T,records in states.items():
        for row in records:
            assert required<=row.keys()
            assert row['decision_date']==T and row['security_id']=='SH:600518'
            assert 'NOT_OWNER_FROZEN' in row['availability_rule']
            if T=='2018-04-24':
                assert row['value']=='UNKNOWN' and row['disclosure_id']=='NONE_ALLOWED_AT_T'
            else:
                assert row['disclosure_date']<=T
                assert row['provenance']['origin_kind']=='OFFICIAL_PDF_DIRECT_VALUE'
                assert row['provenance']['file'] in ('official_original_2017.pdf','official_annual_2018.pdf')
                assert sha(OUT/row['provenance']['file'])==row['provenance']['source_sha256']
    assert {r['disclosure_id'] for r in states['2018-04-27']}=={'CNINFO:1204793690'}
    assert {r['disclosure_id'] for r in states['2019-05-06']}=={'CNINFO:1206168292'}
    assert next(r['value'] for r in states['2019-05-06'] if r['field_name']=='net_operating_cashflow')=='-4840052606.46'
    assert read('offline_assertions.json')['status']=='PASS_BOUNDED_SELECTED_FOUR_FIELDS'
    cash=read('cashflow_comparison.json')
    assert cash['independent_installed_parser_all_fn98_to_fn107_match']
    assert cash['diagnostics']['stored_totals_net']['within_float32_bound']
    assert not cash['diagnostics']['inflow_components_to_subtotal']['within_float32_bound']
    assert not cash['diagnostics']['outflow_components_to_subtotal']['within_float32_bound']
    assert cash['diagnostics']['ocf_from_tdx_components']['not_used_in_pit_replay']
    assert read('research_summary.json')['version_chain_check']['completeness']=='UNKNOWN'
    official_cf=read('sse_xbrl_2017_cashflow.json')['result'][0]
    assert Decimal(official_cf['S2030_0250'])==Decimal('1842794237.84')

    before=read('before.json')['repos'];repo_checks={}
    for name,baseline in before.items():
        root=Path(baseline['root'])
        head=git(root,'rev-parse','HEAD').strip()
        changed=[rel for rel,item in baseline['files'].items() if not (root/rel).is_file() or sha(root/rel)!=item['sha256']]
        current_untracked={x for x in git(root,'ls-files','--others','--exclude-standard','-z').split('\0') if x}
        old=set(baseline['untracked_paths'])
        added=sorted(current_untracked-old);removed=sorted(old-current_untracked)
        if name=='chstockdata':
            assert head==baseline['head'] and not changed and not removed
            assert all(p.startswith(PREFIX) or p==REPORT.relative_to(ROOT).as_posix() for p in added),added
        # Consumer parallel work is recorded without undoing it or misattributing it.
        repo_checks[name]={'head_before':baseline['head'],'head_after':head,'head_unchanged':head==baseline['head'],'tracked_files_checked':len(baseline['files']),'tracked_content_changes_observed':changed,'untracked_added':added,'untracked_removed':removed,'status':git(root,'status','--porcelain=v1','--untracked-files=all'),'task_performed_consumer_writes':False if name!='chstockdata' else None}
        assert not git(root,'diff','--check')

    report=REPORT.read_text(encoding='utf-8')
    keys=('CURRENT_DECISION W5_H_R4_VERDICT TDX_FILE_IDENTITY TDX_FN_FIELD_MAPPING TDX_OCF_COMPONENT_RECONCILIATION TDX_MIXED_VERSION_CONFIRMED TDX_MIXED_VERSION_ROOT_CAUSE TDX_REPAIRABILITY TDX_ASOF_SOURCE_CAPABILITY ORIGINAL_DISCLOSURE_ARCHIVE REVISED_DISCLOSURE_ARCHIVE OFFICIAL_XBRL_AVAILABILITY DISCLOSURE_VERSION_IDENTITY DISCLOSURE_TIME_EVIDENCE VERSION_CHAIN_COMPLETENESS T0_2018_04_24 T1_2018_04_27 T2_2019_05_06 FIXED_CASE_ASOF_RECONSTRUCTION FUTURE_DATA_LEAKAGE_TEST REQUIRED_FINANCIAL_FIELD_COVERAGE FINANCIAL_WARMUP_COVERAGE RECOMMENDED_HISTORICAL_SUPPLY_PATH NEXT_MINIMUM_ACTION MISHI_S07_HISTORICAL_GATE MISHI_PRODUCT_SCOPE_CHANGED NEXT_PHASE_IMPLEMENTATION_ALLOWED RUNTIME_CHANGED GIT_COMMIT GIT_PUSH OWNER_REVIEW_REQUIRED').split()
    assert all(re.search(r'^'+k+r' = ',report,re.MULTILINE) for k in keys)
    assert 'W5_H_R4_VERDICT = PARTIAL_RECONSTRUCTION_WITH_NAMED_GAPS' in report
    assert 'MISHI_S07_HISTORICAL_GATE = NOT_PASSED' in report
    links=[]
    for target in re.findall(r'\]\(([^)]+)\)',report):
        if target.startswith(('http://','https://')):continue
        p=REPORT.parent/target.split('#')[0]
        if p.name not in ('final_verification.json','manifest.json'):assert p.exists(),target
        links.append(p)
    for p in OUT.glob('*.py'):ast.parse(p.read_text(encoding='utf-8'))
    json_count=0
    for p in OUT.rglob('*.json'):
        json.loads(p.read_text(encoding='utf-8'));json_count+=1
    result={'at_utc':datetime.now(timezone.utc).isoformat(),'verdict':'PASS_R4_DELIVERY_CHECKS_ONLY','r4_reconstruction_verdict':'PARTIAL_RECONSTRUCTION_WITH_NAMED_GAPS','fixed_case_replay':'PASS_BOUNDED_FOUR_FIELDS_CONDITIONAL_DATE_RULE','s07_historical_gate':'NOT_PASSED','fresh_replay_exit_code':r.returncode,'prior_manifest_records_reverified':145,'pdf_checks':pdf_checks,'scanned_correction_report_image_only_confirmed':True,'record_schema_required_fields':len(required),'replay_states':3,'populated_or_unknown_records':12,'zero_network_in_verifier':True,'network_attempts_unchanged':16,'json_files_validated':json_count,'local_report_links_checked':len(links),'repos':repo_checks}
    save('final_verification.json',result)
    manifest={'report':{'path':str(REPORT),'bytes':REPORT.stat().st_size,'sha256':sha(REPORT)},'files':[{'path':p.relative_to(OUT).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='manifest.json']}
    save('manifest.json',manifest)
    assert all(p.exists() for p in links)
    assert all(sha(OUT/x['path'])==x['sha256'] for x in manifest['files'])
    print(json.dumps({'delivery_checks':'PASS','r4_verdict':result['r4_reconstruction_verdict'],'fixed_case':'PASS_BOUNDED','prior_hashes':145,'tracked_files_checked':sum(x['tracked_files_checked'] for x in repo_checks.values()),'all_heads_unchanged':all(x['head_unchanged'] for x in repo_checks.values()),'all_tracked_unchanged':not any(x['tracked_content_changes_observed'] for x in repo_checks.values()),'consumer_parallel_untracked_additions':{n:len(x['untracked_added']) for n,x in repo_checks.items() if n!='chstockdata'},'evidence_files':len(manifest['files']),'s07_gate':'NOT_PASSED'},ensure_ascii=True))

if __name__=='__main__':main()
