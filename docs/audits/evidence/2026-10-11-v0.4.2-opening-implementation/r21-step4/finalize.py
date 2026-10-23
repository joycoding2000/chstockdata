"""Bind the completed actual matrix and limitations; never publish."""
import difflib,json,sys,xml.etree.ElementTree as ET
from datetime import datetime,timezone
from pathlib import Path
import run_gate as g

def read(path):return json.loads(path.read_text(encoding='utf-8'))
def junit(path):
    root=ET.parse(path).getroot();cases=list(root.iter('testcase'))
    failures={x.attrib['classname']+'::'+x.attrib['name']:x.find('failure').attrib for x in cases if x.find('failure') is not None}
    errors=[x.attrib for x in cases if x.find('error') is not None]
    skipped=[x.attrib for x in cases if x.find('skipped') is not None]
    return {'path':str(path),'sha256':g.sha(path.read_bytes()),'tests':len(cases),'passed':len(cases)-len(failures)-len(errors)-len(skipped),'failures':failures,'errors':errors,'skipped':skipped}

wheel=g.sha(g.WHEEL.read_bytes());source=read(g.OUT/'source-only-identity.json');envelope=read(g.OUT/'candidate-source.json')
current=g.source_identity()['working_tree_files']
assert all(current.get(n)==h for n,h in source['working_tree_files'].items())
assert all(envelope['working_tree_files'][n]==h for n,h in source['working_tree_files'].items())
assert g.sha((g.ROOT/'dist/v042-unified/chstockdata-0.4.2-py3-none-any.whl').read_bytes())=='b76b065a06cd1d91868880a7b57584f598b6fd4cb42931e9a33700bc99a88c7a'
old_verification={'agent_scope':'copied protected old wheel hash verified; original direct read sandbox denied','independent_root_evidence':str(g.WORK/'r21-protection.json'),'root_evidence_sha256':g.sha((g.WORK/'r21-protection.json').read_bytes())}
profiles={name:read(g.OUT/(name+'-identity.json')) for name in ('core','sdist','mcp','baostock','sios-candidate','ta-candidate')}
assert all(p['wheel_sha256']==wheel and p['version']=='0.4.2' and '/profiles/r21-qualified/' in p['library_import'].replace('\\','/') for p in profiles.values())
results={name:junit(g.OUT/(name+'.xml')) for name in ('package-tests','sios-provider-contract','sios-etf-golden-smoke','sios-offline','ta-candidate')}
results['live']=junit(g.OUT/'final-live/live.xml')
assert all(not results[n]['failures'] and not results[n]['errors'] for n in ('package-tests','sios-provider-contract','sios-etf-golden-smoke','sios-offline','live'))
assert results['live']['tests']==results['live']['passed']==5 and not results['live']['skipped']
baseline_path=Path('D:/Dev/Projects/chstockdata/dist/consumer-v0.4.2/evidence/ta-baseline-matrix.xml')
baseline=junit(baseline_path)
assert results['ta-candidate']['passed']==123 and results['ta-candidate']['failures']==baseline['failures'] and len(baseline['failures'])==7
g.save('ta-relative-compatibility.json',{'verdict':'PASS_RELATIVE_COMPATIBILITY','actual_test_exit':1,'candidate':results['ta-candidate'],'frozen_baseline':baseline,'same_failure_identities_and_messages':True,'new_failures':[],'out_of_scope_deselections':4,'legacy_probe_cases':5,'legacy_probe_exit':int((g.OUT/'ta-legacy.exit').read_text()),'dependency_pip_check_exit':1,'dependency_limitation':'inherited tradingagents-astock 0.6.0 metadata requires chstockdata[baostock]>=0.2.0,<0.3; frozen pin unchanged'})

live_dir=g.OUT/'final-live'
live_result=read(live_dir/'live-result.json');calls=read(live_dir/'calls.json');actual_imports=read(live_dir/'actual-imports.json')
assert live_result['exit_code']==0 and live_result['source_unchanged'] and actual_imports['wheel_sha256']==wheel
assert read(live_dir/'source-before.json')==read(live_dir/'source-after.json')
assert read(live_dir/'qualification-source-before.json')==read(live_dir/'qualification-source-after.json')
for call in calls:
    if call.get('raw_path'):assert g.sha((live_dir/call['raw_path']).read_bytes())==call['raw_sha256']
caps={f.name:read(f) for f in sorted((live_dir/'capabilities').glob('*.json'))}
outcomes=[item for report in caps.values() for item in report['outcomes']]
assert len(outcomes)==54 and all(x['status']=='PASS' for x in outcomes)
executions=[x for x in outcomes if x['capability'] in ('SNAPSHOT_ENGINE_RAW_FILL_IDENTITY','CONTROL_ENGINE_NO_FILL_NO_RETRY')]
assert len(executions)==6
for item in executions:
    rules=dict(item['result']['run_manifest']['rule_versions'])
    assert rules['execution-mode']=='HISTORICAL_OPENING_R21' and rules['execution-policy']=='R2.1' and rules['execution-clock']=='Asia/Shanghai|09:15:00|09:30:00|15:30:00'
    assert item['result']['snapshot_manifest']['snapshot_schema_version']=='v3-historical-opening'
g.save('runtime-identity-bindings.json',{'candidate_source_only_sha256':source['working_tree_manifest_sha256'],'prebuild_envelope_sha256':envelope['working_tree_manifest_sha256'],'wheel_sha256':wheel,
  'actual_imports':actual_imports,'combined_installed_ch_plus_sios_source_sha256':read(live_dir/'source-before.json')['tree_sha256'],'live_run_code_commit_field_semantics':'source SHA256 supplied by public test harness, not a Git commit','full_actual_execution_payloads':executions,'source_stable':True,'qualification_contract_stable':True,'raw_calls':calls})

replay=read(g.OUT/'installed-wheel-replay/manifest.json')
assert len(replay['results'])==12 and replay['exit_code']==0 and all(r['pass'] for r in replay['results']) and replay['wheel_sha256']==wheel
exact=read(g.OUT/'etf-exact-probe.json');assert exact['price_parity']==4 and exact['default_pin_reject']=='PASS' and exact['identity']['wheel_sha256']==wheel
assert read(g.OUT/'frozen-var-before.json')==read(g.OUT/'frozen-var-after.json')
offline=read(g.OUT/'sios-offline.json');assert offline['source_stable_during_run'] and offline['exit_code']==0

commands=[]
for path in sorted(g.OUT.glob('*.command.json')):
    record=read(path)
    record.update(record_file=str(path),candidate_source_only_sha256=source['working_tree_manifest_sha256'],source_binding_basis='source-only subset equals every prebuild frozen byte; final source stability independently rechecked')
    commands.append(record)
g.save('commands.json',commands)
final_records={r['name']:r for r in commands if r.get('candidate_wheel_sha256')==wheel}
required=['build','twine','artifact-members','static-final','compile','version-project','original-diff-check','package-tests','sios-provider-contract','sios-etf-golden-smoke','sios-offline','sios-required-live','installed-wheel-74raw-replay','etf-exact-probe','ta-identity','ta-source-binding','ta-legacy']
for profile in ('core','sdist','mcp','baostock'):
    required.extend(profile+'-'+task for task in ('create','install','pip-check','version','identity','exports','deps'))
required.extend(['sios-candidate-create','sios-candidate-install','sios-certified-deps','sios-pip-check','sios-deps','ta-candidate-create','ta-candidate-install','ta-deps'])
assert all(name in final_records and final_records[name]['exit']==0 for name in required),[(n,final_records.get(n,{}).get('exit')) for n in required if n not in final_records or final_records[n]['exit']]
assert final_records['ta-candidate']['exit']==1 and final_records['ta-pip-check']['exit']==1
g.save('profile-import-dependencies.json',{'wheel_sha256':wheel,'profile_identities':profiles,'dependency_logs':{name:str(g.OUT/(name+'-deps.log')) for name in ('core','sdist','mcp','baostock','sios','ta')},'core_optional_dependencies_not_forced':True,'ta_dependency_mode':'new Python314 venv, no-deps wheel; read-only original .venv site-packages via .pth','ta_metadata_constraint_known_risk':True})

lint_diff=[];lint_files={}
for name,relative in [('opening_evidence','src/chstockdata/opening_evidence.py'),('test_historical_opening_evidence','tests/test_historical_opening_evidence.py')]:
    before=(g.OUT/(name+'-pre-lint.py.txt')).read_text(encoding='utf-8');after=(g.ROOT/relative).read_text(encoding='utf-8')
    lint_diff.extend(difflib.unified_diff(before.splitlines(True),after.splitlines(True),'a/'+relative,'b/'+relative))
    lint_files[relative]={'before_sha256':g.sha(before.encode()),'after_sha256':g.sha((g.ROOT/relative).read_bytes())}
(g.OUT/'step4-lint-only.patch').write_text(''.join(lint_diff),encoding='utf-8')
g.save('step4-necessary-fixes.json',{'packaging_fix':'MANIFEST.in recursive-include tests/fixtures *; source/sdist exact 9 fixture members','lint':{'files':lint_files,'rules':['I001','UP035','FURB157','RUF007','SIM102','RUF022'],'preserved_contract_exceptions':['ValueError payload status via TRY004 exact noqa','vendor observation and cleanup catchall via BLE001/S110 exact noqa'],'source_local_recheck':'128 PASS','independent_root_recheck':'independent-lint-local.xml','diff':'step4-lint-only.patch'},'scope_expansion':False})

mapping={
 'A1':{'evidence':['final-live/capabilities/test_live_tradability_adjustment_and_freshness.json','runtime-identity-bindings.json'],'scope':'4 certified ETF 2026-09-11 opening activity; raw daily open remains fill price'},
 'A2':{'evidence':['runtime-identity-bindings.json','sios-offline.xml'],'scope':'2 official halt controls no-fill/no-retry; boundary contracts offline'},
 'A3':{'evidence':['installed-wheel-replay/manifest.json','package-tests.xml','sios-offline.xml'],'scope':'actual saved raw final-wheel replay 688432/000002 and permanent boundary contracts; no added live investigation'},
 'A4':{'evidence':['installed-wheel-replay/manifest.json'],'scope':'actual 74 saved raw responses / 12 bounded points final-wheel replay incl 2016/2022; no continuous all-history claim'},
 'A5':{'evidence':['package-tests.xml','artifact-members.json','final-live/actual-imports.json','final-live/raw/','etf-exact-probe.json'],'scope':'permanent parser normalization regression plus actual certified mootdx0.11.7/tdxpy0.2.7 live; fourETF Decimal exact OHLC/preclose'},
 'A6':{'evidence':['package-tests.xml','sios-offline.xml'],'scope':'typed empty/failure/partial/conflict/naive/unknown outcomes and no-fill permanent contracts'},
 'A7':{'evidence':['sios-offline.xml','sios-offline.json'],'scope':'historical opening component/research wiring keeps DecisionContext and T strategy PIT isolated'},
 'A8':{'evidence':['sios-offline.xml','runtime-identity-bindings.json'],'scope':'timezone/boundary/identity permanent tests and six actual Asia/Shanghai run manifests'},
 'A9':{'evidence':['sios-etf-golden-smoke.xml','sios-offline.xml','runtime-identity-bindings.json'],'scope':'original accounting/RAW/Tclose/slippage/fees/funding/lots/all-or-none/UNKNOWN contracts plus four real raw fill and two no-fill outputs'},
 'A10':{'evidence':['final-live/live.xml','final-live/capabilities/','final-live/calls.json','sios-required-live.command.json'],'scope':'all original 5 live nodes actually run zero skip/xfail/deselect;54 capabilities including all four independent actions/calendar/RAW/freshness/staleness'},
 'A11':{'evidence':['commands.json','artifacts.json','artifact-members.json','source-only-identity.json','profile-import-dependencies.json','consumer-identities.json','ta-relative-compatibility.json','runtime-identity-bindings.json'],'scope':'all final checks same wheel; TA relative compatibility preserves 7 identical baseline failures and known metadata constraint'}
}
for item in mapping.values():item['verdict']='PASS_CANDIDATE'
g.save('A1-A11-evidence-map.json',mapping)
consumer=read(g.OUT/'consumer-identities.json')
consumer.update({'final_sios_source_manifest':g.manifest(g.SIOS,exclude=('var','__pycache__','.pytest_cache','.ruff_cache')),'final_ta_source_manifest':g.manifest(g.TA,exclude=('__pycache__','.pytest_cache','.ruff_cache')),'final_profiles':profiles,'source_only_sha256':source['working_tree_manifest_sha256'],'wheel_sha256':wheel,'frozen_var_unchanged':True})
g.save('consumer-identities.json',consumer)
artifacts=read(g.OUT/'artifacts.json')
artifacts.update({'source_only_identity':source,'source_only_sha256':source['working_tree_manifest_sha256'],'original_prebuild_envelope_sha256':envelope['working_tree_manifest_sha256'],'source_only_is_exact_immutable_prebuild_subset':True,'non_source_cache_drift_is_explicit':source['generated_cache_drift'],'member_hashes':'artifact-members.json'})
g.save('artifacts.json',artifacts)
limitations=[{'classification':'UNRESOLVED_RISK','fact':'Only certified single-host bounded minute activity + current official query; strict exact-time order fill/full-day/PIT/all-history completeness not proven'},
 {'classification':'UNRESOLVED_RISK','fact':'Legacy complete historical PIT suspension remains UNKNOWN/fail-closed; QDII halt controls are source controls, not ETF product qualification'},
 {'classification':'UNRESOLVED_RISK','fact':'TA inherited dependency metadata constraint remains incompatible with 0.4.2; actual pipcheck1 and seven frozen baseline failures retained'},
 {'classification':'KNOWN_LIMITATION','fact':'Package one optional MCP skip in non-MCP test profile; separately actual MCP profile exports/build_server pass;15 network smoke deselected by original package marker contract'},
 {'classification':'KNOWN_LIMITATION','fact':'SIOS offline five default live optin skips; same original five mandatory live nodes independently actually executed and passed'},
 {'classification':'KNOWN_LIMITATION','fact':'Gitless snapshot research runner/oos public test-only source identity injection; production resolver unchanged; code_commit field represents source SHA256'}]
summary={'phase':'v0.4.2 R1-R5 + R2.1','step':'Step4 unified candidate','gate_verdict':'PASS_CANDIDATE','owner_acceptance':'PENDING','release_authorized':False,'publish_authorized':False,'next_phase_authorized':False,'scope_expansion':False,
 'base_commit':'42bd44ef4d695aa3e88cfab4ebc3417660d0437a','snapshot_git_status':'no .git; isolated source content identity, no new commit','candidate_source_kind':'source-only SHA256; not Git commit','candidate_source_sha256':source['working_tree_manifest_sha256'],'candidate_prebuild_envelope_sha256':envelope['working_tree_manifest_sha256'],'candidate_wheel_sha256':wheel,'candidate_sdist_sha256':g.sha(g.SDIST.read_bytes()),'candidate_paths':{'wheel':str(g.WHEEL),'sdist':str(g.SDIST)},
 'results':results,'required_zero_exit_commands':required,'actual_required_live':{'passed':5,'failed':0,'skipped':0,'xfail':0,'deselected':0,'capabilities_passed':54,'raw_calls':len(calls),'directory':str(live_dir)},'etf_exact_price_cases_passed':4,'legacy_probe_cases_passed':5,'ta_relative_compatibility':'PASS_123_PLUS_7_IDENTICAL_BASELINE_FAILURES','ta_pip_check':'EXIT1_KNOWN_FROZEN_METADATA_CONSTRAINT','saved_raw_replay':{'points':12,'raw_responses':74,'network':False,'same_final_wheel':True},'frozen_var_files':len(read(g.OUT/'frozen-var-before.json')),'frozen_var_unchanged':True,
 'unresolved_mandatory_blockers':[],'limitations':limitations,'retained_invalid_or_superseded_attempts':['preliminary/ + dist/r21-unified (missing fixtures)','candidate-static-fail/ + dist/r21-final (12 lint findings)','live-sandbox-attempt/ (network-layer denial actual4PASS1FAIL)','live-snapshot-reuse-attempt/ (actual111 requests success;6 snapshot immutable path refusals;4PASS1FAIL)','freeze-source-only-cache-drift-attempt.log (tool cache drift excluded and explicitly bound)','commands-initial-invalid.json (parallel journal race; replaced by per-command records)'],
 'recommended_next_action':'Independent root review/protection audit and Owner Acceptance; no publication or next-phase advancement','finished_at':datetime.now(timezone.utc).isoformat()}
summary['old_wheel_verification_scope']=old_verification
g.save('summary.json',summary)
handoff=f'''Step4 unified candidate: PASS_CANDIDATE; Owner Acceptance PENDING.
CH base commit 42bd44ef4d695aa3e88cfab4ebc3417660d0437a; isolated snapshot has no .git/no new commit.
Source-only SHA256 {source['working_tree_manifest_sha256']} (not Git commit); immutable prebuild envelope {envelope['working_tree_manifest_sha256']}.
Wheel SHA256 {wheel}; sdist SHA256 {summary['candidate_sdist_sha256']}.
Package {results['package-tests']['passed']} PASS,1 optional MCP skip,15 default network deselected; SIOS offline {results['sios-offline']['passed']} PASS,5 default optin skip; provider67; Golden/ETF/parity165+5skip.
Actual final-live 5PASS0skip,54 capabilities PASS,111 complete raw calls; actual installed final wheel import identity and six v3 snapshot/new-policy/Shanghai-clock/full-payload run identities saved.
TA123PASS/7 identical baseline failures (failure identities/messages exact); legacy5; TA pipcheck exit1 frozen metadata limitation retained. Four ETF Decimal exact price cases PASS.
Necessary changes this step: MANIFEST.in includes 9 fixture members; safe lint in reader/test, public exception/status behavior preserved. 128 local source tests + root independent128; full final wheel matrix rerun.
No new source or runtime bytes changed after final wheel build; source-only identity removes generated cache/archived artifacts from retained build envelope, with two cache-drift entries explicit.
All commands/exits/logs/JUnit: commands.json and referenced files. Runtime live: final-live/. A1-A11: A1-A11-evidence-map.json. Source changes: source-vs-baseline.patch, step4-lint-only.patch.
Frozen SIOS var {summary['frozen_var_files']} files before/after unchanged; old b76b065a... wheel unchanged. Original repositories untouched by this agent.
Mandatory blockers none. Scope expansion NO. Keep bounded coverage/old historical PIT limitation and TA dependency metadata mismatch visible.
Next: root independent fresh review and Owner Acceptance only. Release/publish/tag/upload/push/merge/nextPhase NO.
'''
(g.OUT/'handoff.txt').write_text(handoff,encoding='utf-8')
print(json.dumps({'status':'PASS_CANDIDATE','source_sha256':source['working_tree_manifest_sha256'],'wheel_sha256':wheel,'tests':{n:{'passed':v['passed'],'failures':len(v['failures']),'skipped':len(v['skipped'])} for n,v in results.items()},'live_capabilities':54,'live_raw_calls':len(calls)},indent=2))
