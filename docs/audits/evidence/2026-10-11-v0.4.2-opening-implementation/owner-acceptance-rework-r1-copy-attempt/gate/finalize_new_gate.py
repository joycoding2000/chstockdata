"""One final factual aggregation of the approved minimum Owner rework Gate."""
import importlib.util
import json
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

import run_gate as g


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def junit(path):
    cases = list(ET.parse(path).getroot().iter('testcase'))
    failures = {c.attrib['classname'] + '::' + c.attrib['name']: c.find('failure').attrib
                for c in cases if c.find('failure') is not None}
    errors = [c.attrib for c in cases if c.find('error') is not None]
    skips = [c.attrib for c in cases if c.find('skipped') is not None]
    return {'path':str(path), 'sha256':g.sha(path.read_bytes()), 'tests':len(cases),
            'passed':len(cases)-len(failures)-len(errors)-len(skips),
            'failures':failures, 'errors':errors, 'skipped':skips,
            'case_names':[c.attrib['classname']+'::'+c.attrib['name'] for c in cases]}


def dependency_paths():
    from importlib import metadata
    import chstockdata
    rows=[]
    for name in ('chstockdata','requests','pandas','mootdx','tdxpy','pypdf','mcp','baostock'):
        spec=importlib.util.find_spec(name)
        try: version=metadata.version(name)
        except metadata.PackageNotFoundError: version=None
        rows.append({'name':name,'version':version,'module_spec_origin':spec.origin if spec else None,
                     'actual_import_path':getattr(sys.modules.get(name),'__file__',None)})
    g.save(sys.argv[2]+'-dependency-paths.json',{'executable':sys.executable,'chstockdata_import':chstockdata.__file__,'wheel_sha256':g.sha(g.WHEEL.read_bytes()),'dependencies':rows})


if len(sys.argv)>1 and sys.argv[1]=='dependency-paths':
    if sys.argv[2]=='sios-candidate':
        import mootdx, tdxpy, pypdf
    if sys.argv[2]=='mcp':
        import mcp
    if sys.argv[2]=='baostock':
        import baostock
    dependency_paths()
    raise SystemExit(0)

wheel=g.sha(g.WHEEL.read_bytes())
source=read(g.OUT/'candidate-source.json')
approved=read(g.OUT.parent/'rework-source-manifest.json')
current=g.source_identity()
assert current['working_tree_files']==source['working_tree_files']==approved['source_files']
assert current['working_tree_manifest_sha256']==approved['canonical_files_sha256']
old_wheel=g.WORK/'dist/r21-qualified/chstockdata-0.4.2-py3-none-any.whl'
assert g.sha(old_wheel.read_bytes())=='3fd4f0b7334e310851495b8b13d4c7c55d21cde719acf9e00ff880ccb822f42e'
g.save('source-after.json',current)

consumer=read(g.OUT/'consumer-identities.json')
sios=read(g.OUT.parent/'sios-source-manifest.json')
sios_actual=g.manifest(g.SIOS,exclude=('var','__pycache__','.pytest_cache','.ruff_cache'))
ta_actual=g.manifest(g.TA,exclude=('__pycache__','.pytest_cache','.ruff_cache'))
assert sios_actual==sios['source_files_sha256']==consumer['final_sios_source_manifest']
assert ta_actual==consumer['final_ta_source_manifest']
assert g.sha((g.OUT.parent/'sios-source-vs-frozen.patch').read_bytes())=='cbf403397631eed42fe542364587c3f75eb6150b88017c7390da2828644d4873'
assert sios['source_manifest_sha256']=='573c8540e094e2c2c1d82788541a65d42424c707fa307a06c73d330483c75eb5'
assert sios['runtime_source_sha256']=='73376752616edc41b1560e0cea40a7cdb6190d2795c83dab34d19fdcffd4186f'
runtime=g.manifest(g.SIOS/'src',exclude=('__pycache__',))
runtime={('src/'+n):h for n,h in runtime.items() if n.endswith('.py')}
assert g.sha(json.dumps(runtime,sort_keys=True,separators=(',',':')).encode())==sios['runtime_source_sha256']
assert read(g.OUT/'sios-var-before.json')==read(g.OUT/'sios-var-after.json')
assert read(g.OUT/'frozen-var-before.json')==read(g.OUT/'frozen-var-after.json')
assert g.manifest(g.SIOS/'var')==read(g.OUT/'sios-var-before.json')
g.save('freeze-var-proof.json',{'status':'PASS','source_frozen_var_files':len(read(g.OUT/'frozen-var-before.json')),'candidate_var_files':len(read(g.OUT/'sios-var-before.json')),'before_after_identical':True,'original_frozen_var_before_after_identical':True})
consumer.update({'final_sios_source_manifest':sios_actual,'final_ta_source_manifest':ta_actual,'source_stable':True,'frozen_var_unchanged':True,'candidate_source_sha256':current['working_tree_manifest_sha256'],'wheel_sha256':wheel})
g.save('consumer-identities.json',consumer)

profiles={name:read(g.OUT/(name+'-identity.json')) for name in ('core','sdist','mcp','baostock','sios-candidate','ta-candidate')}
assert all(p['version']=='0.4.2' and p['wheel_sha256']==wheel and '/profiles/owner-rework-r1/' in p['library_import'].replace('\\','/') for p in profiles.values())
for name in profiles:
    g.command(name+'-dependency-paths',[g.PROFILES/name/'Scripts/python.exe',g.OUT/'finalize_new_gate.py','dependency-paths',name],cwd=g.WORK)
paths={name:read(g.OUT/(name+'-dependency-paths.json')) for name in profiles}
certified={r['name']:r for r in paths['sios-candidate']['dependencies']}
assert all(certified[n]['version']==v and '/profiles/owner-rework-r1/sios-candidate/' in certified[n]['actual_import_path'].replace('\\','/') for n,v in (('mootdx','0.11.7'),('tdxpy','0.2.7'),('pypdf','6.10.0')))
g.save('profile-import-dependencies.json',{'wheel_sha256':wheel,'candidate_source_sha256':current['working_tree_manifest_sha256'],'profile_identities':profiles,'profile_dependency_paths':paths,'dependency_logs':{name:str(g.OUT/(name+'-deps.log')) for name in ('core','sdist','mcp','baostock','sios','ta')},'ta_dependencies':'new Python314 no-deps wheel + approved readonly original site-packages .pth','ta_pip_check':'NOT_RUN_NONMANDATORY; frozen metadata mismatch retained','certified_mootdx_tdxpy_pypdf':'PASS'})

results={name:junit(g.OUT/(name+'.xml')) for name in ('package-tests','sios-provider-contract','sios-etf-golden-smoke','sios-offline','ta-candidate')}
results['live']=junit(g.OUT/'live/live.xml')
assert all(not results[n]['failures'] and not results[n]['errors'] for n in ('package-tests','sios-provider-contract','sios-etf-golden-smoke','sios-offline','live'))
assert results['live']['tests']==results['live']['passed']==5 and not results['live']['skipped']
owner_cases=[n for n in results['package-tests']['case_names'] if 'owner_' in n]
assert len(owner_cases)==22
g.save('interval-rework-result.json',{'status':'PASS','owner_regression_cases':owner_cases,'same_new_installed_wheel':wheel,'whole_package_junit':results['package-tests']['path'],'local_red_green_evidence':'../owner-red.xml and ../owner-green.xml; retained original13FAIL9PASS then22PASS, not rerun'})

baseline=junit(Path('D:/Dev/Projects/chstockdata/dist/consumer-v0.4.2/evidence/ta-baseline-matrix.xml'))
assert results['ta-candidate']['failures']==baseline['failures'] and len(baseline['failures'])==7
assert results['ta-candidate']['passed']==123 and not results['ta-candidate']['errors']
g.save('ta-relative-compatibility.json',{'verdict':'PASS_RELATIVE_COMPATIBILITY','actual_test_exit':1,'candidate':results['ta-candidate'],'frozen_baseline':baseline,'same_failure_identities_and_messages':True,'new_failures':[],'out_of_scope_deselections':4,'legacy_probe_cases':5,'legacy_probe_exit':int((g.OUT/'ta-legacy.exit').read_text(encoding='utf-8')),'pip_check':'NOT_RUN_NONMANDATORY','dependency_limitation':'inherited tradingagents-astock0.6 metadata requires chstockdata[baostock]>=0.2.0,<0.3; frozen pin unchanged'})

live=g.OUT/'live'
live_result=read(live/'live-result.json')
calls=read(live/'calls.json')
imports=read(live/'actual-imports.json')
assert live_result['exit_code']==0 and live_result['source_unchanged'] and imports['wheel_sha256']==wheel
assert imports['sios_full_source_sha256']==sios['source_manifest_sha256']
assert read(live/'source-before.json')==read(live/'source-after.json')
assert read(live/'qualification-source-before.json')==read(live/'qualification-source-after.json')
for c in calls:
    if c.get('raw_path'):
        assert g.sha((live/c['raw_path']).read_bytes())==c['raw_sha256']
reports={p.name:read(p) for p in sorted((live/'capabilities').glob('*.json'))}
outcomes=[r for report in reports.values() for r in report['outcomes']]
assert len(outcomes)==54 and all(r['status']=='PASS' for r in outcomes)
execution=[r for r in outcomes if r['capability'] in ('SNAPSHOT_ENGINE_RAW_FILL_IDENTITY','CONTROL_ENGINE_NO_FILL_NO_RETRY')]
assert len(execution)==6
for row in execution:
    rules=dict(row['result']['run_manifest']['rule_versions'])
    assert rules['execution-mode']=='HISTORICAL_OPENING_R21' and rules['execution-policy']=='R2.1'
    assert rules['execution-clock']=='Asia/Shanghai|09:15:00|09:30:00|15:30:00'
    assert row['result']['snapshot_manifest']['snapshot_schema_version']=='v3-historical-opening'
g.save('live-full-facts.json',{'status':'PASS','wheel_sha256':wheel,'candidate_source_sha256':current['working_tree_manifest_sha256'],'sios_full_source_sha256':sios['source_manifest_sha256'],'sios_runtime_source_sha256':sios['runtime_source_sha256'],'sios_patch_sha256':consumer['sios_patch_sha256'],'actual_imports':imports,'mandatory_junit':results['live'],'source_unchanged':True,'qualification_unchanged':True,'outcomes':outcomes,'full_execution_payloads':execution,'actual_raw_calls':calls,'capture_semantics':'actual HTTP response bodies and TDX parser-returned rows, never TCP wire-byte claim','calendar_policy':'real current-date freshness and labelled default fallback retained; see raw calls and capability facts'})
g.save('runtime-identity-bindings.json',{'candidate_source_sha256':current['working_tree_manifest_sha256'],'wheel_sha256':wheel,'sios_full_source_sha256':sios['source_manifest_sha256'],'sios_runtime_source_sha256':sios['runtime_source_sha256'],'sios_patch_sha256':consumer['sios_patch_sha256'],'combined_installed_ch_plus_sios_source_sha256':read(live/'source-before.json')['tree_sha256'],'live_run_code_commit_semantics':'public test supplied actual source_tree_sha256, not frozen Git commit','execution_facts':'live-full-facts.json','source_stable':True})

replay=read(g.OUT/'installed-wheel-replay/manifest.json')
assert replay['wheel_sha256']==wheel and replay['exit_code']==0 and len(replay['results'])==12 and all(r['pass'] for r in replay['results'])
exact=read(g.OUT/'etf-exact-probe.json')
assert exact['price_parity']==4 and exact['default_pin_reject']=='PASS' and exact['identity']['wheel_sha256']==wheel
assert read(g.OUT/'candidate-rework-diff-check.json')['status']=='PASS'
assert read(g.OUT/'artifact-members.json')['fixtures_all_match']==9

commands=[]
for p in sorted(g.OUT.glob('*.command.json')):
    record=read(p)
    record['record_file']=str(p)
    log=g.OUT/record['log']
    record['log_sha256']=g.sha(log.read_bytes())
    record['exit_sha256']=g.sha((g.OUT/record['exit_file']).read_bytes())
    jp=g.OUT/(record['name']+'.xml')
    if jp.exists(): record.update(junit=str(jp),junit_sha256=g.sha(jp.read_bytes()))
    commands.append(record)
g.save('commands.json',commands)
by_name={r['name']:r for r in commands}
required=['environment','build','twine','artifact-members','static-final','compile','version-project','original-diff-check','package-suite-identity','package-tests','sios-provider-contract','sios-etf-golden-smoke','sios-offline','sios-required-live','installed-wheel-74raw-replay','etf-exact-probe','ta-identity','ta-source-binding','ta-legacy']
for profile in ('core','sdist','mcp','baostock'):
    required.extend(profile+'-'+task for task in ('create','install','pip-check','version','identity','exports','deps','dependency-paths'))
for profile in ('core','sdist'):
    required.extend(profile+'-'+name for name in ('chstockdata-mcp','chstockdata-refresh-vipdoc'))
required.extend(['sios-candidate-create','sios-candidate-install','sios-certified-deps','sios-pip-check','sios-deps','sios-candidate-dependency-paths','ta-candidate-create','ta-candidate-install','ta-deps','ta-candidate-dependency-paths'])
assert all(n in by_name and by_name[n]['exit']==0 for n in required),[(n,by_name.get(n,{}).get('exit')) for n in required if n not in by_name or by_name[n]['exit']]
assert all(by_name[n]['candidate_source_sha256']==current['working_tree_manifest_sha256'] for n in required)
assert all(by_name[n]['candidate_wheel_sha256']==wheel for n in required if n!='environment')
assert all(by_name[n]['sios_full_source_sha256']==sios['source_manifest_sha256'] and by_name[n]['sios_patch_sha256']==consumer['sios_patch_sha256'] for n in required)
assert by_name['ta-candidate']['exit']==1

mapping=read(g.WORK/'evidence/r21-step4/A1-A11-evidence-map.json')
for item in mapping.values():
    item['evidence']=[s.replace('final-live/','live/').replace('source-only-identity.json','candidate-source.json') for s in item['evidence']]
    item['candidate_wheel_sha256']=wheel
    item['candidate_source_sha256']=current['working_tree_manifest_sha256']
    item['verdict']='PASS_CANDIDATE'
mapping['A3']['evidence'].append('interval-rework-result.json')
mapping['A11']['evidence'].extend(['candidate-rework-diff-check.json','freeze-var-proof.json','live-full-facts.json'])
g.save('A1-A11-evidence-map.json',mapping)

artifacts=read(g.OUT/'artifacts.json')
artifacts.update({'source_frozen_before_after_identical':True,'candidate_source_sha256':current['working_tree_manifest_sha256'],'member_hashes':'artifact-members.json','sios_full_source_sha256':sios['source_manifest_sha256'],'sios_runtime_source_sha256':sios['runtime_source_sha256'],'sios_patch_sha256':consumer['sios_patch_sha256'],'protected_old_wheel_sha256':g.sha(old_wheel.read_bytes())})
g.save('artifacts.json',artifacts)
limitations=[{'classification':'UNRESOLVED_RISK','fact':'Bounded single-host minute activity and current official query do not prove strict precise-time fill, full-day/PIT or all-history completeness.'},
 {'classification':'UNRESOLVED_RISK','fact':'Legacy full historical PIT suspension remains UNKNOWN/fail-closed; QDII halt controls are source controls, not product expansion.'},
 {'classification':'UNRESOLVED_RISK','fact':'TA seven baseline failures and inherited chstockdata<0.3 metadata remain visible; TA pipcheck not mandatory and not rerun.'},
 {'classification':'KNOWN_LIMITATION','fact':'Package one optional MCP skip independently covered by actual MCP profile;15 original network deselections. SIOS five default live-optin skips independently executed as5 mandatory livePASS.'},
 {'classification':'KNOWN_LIMITATION','fact':'Saved74raw/12points replay uses this new installed wheel offline; it is not this run live evidence.'},
 {'classification':'KNOWN_LIMITATION','fact':'Gitless SIOS test process injects actual source SHA in runner/oos only; production resolver unchanged.'}]
flags={'CURRENT_DECISION':'FIX_ONLY','OWNER_REVIEW_FINDING':'CONFIRMED_INTERVAL_DEFECT','INTERVAL_REWORK':'PASS','SIOS_SOURCE_DIFF_COMPLETE':'YES','SCOPE_EXPANSION':'NO','PACKAGE':'PASS_796_PLUS_1_ORIGINAL_OPTIONAL_SKIP_15_ORIGINAL_NETWORK_DESELECT','SIOS_OFFLINE':'PASS_973_PLUS_5_DEFAULT_LIVE_OPTIN_SKIP','LIVE':'PASS_ACTUAL_5_ZERO_SKIP_54_CAPABILITIES','TA':'PASS_RELATIVE_123_PLUS_7_IDENTICAL_BASELINE_FAILURES','NEW_WHEEL_SHA256':wheel,'NEW_SOURCE_SHA256':current['working_tree_manifest_sha256'],'READY_FOR_OWNER_REVIEW':'YES','OWNER_ACCEPTANCE':'PENDING','RELEASE':'NO','PUBLISH':'NO','NEXT_PHASE':'NO'}
summary={'phase':'v0.4.2 R1-R5 + R2.1','step':'Owner minimum interval rework r1 unified new candidate Gate','gate_verdict':'PASS_CANDIDATE','flags':flags,'base_commit':current['base_commit'],'working_tree_status':'isolated snapshot has no.git; no new commit; source765files frozen; original repo audit delegated to root','owner_acceptance':'PENDING','release_authorized':False,'publish_authorized':False,'next_phase_authorized':False,'scope_expansion':False,'candidate_source_sha256':current['working_tree_manifest_sha256'],'candidate_wheel_sha256':wheel,'candidate_sdist_sha256':g.sha(g.SDIST.read_bytes()),'sios_full_source_sha256':sios['source_manifest_sha256'],'sios_runtime_source_sha256':sios['runtime_source_sha256'],'sios_patch_sha256':consumer['sios_patch_sha256'],'results':results,'required_zero_exit_commands':required,'diff_check_records':read(g.OUT/'candidate-rework-diff-check.json')['records'],'actual_required_live':{'passed':5,'failed':0,'skip':0,'xfail':0,'deselected':0,'capabilities_passed':54,'raw_calls':len(calls),'directory':str(live)},'owner_interval_regression_cases_passed':22,'etf_exact_price_cases_passed':4,'ta_relative_compatibility':'PASS_123_PLUS_7_IDENTICAL_BASELINE_FAILURES','legacy_probe_cases_passed':5,'ta_pip_check':'NOT_RUN_NONMANDATORY','saved_raw_replay':{'points':12,'raw_responses':74,'network':False,'new_installed_wheel':True},'frozen_var_files':len(read(g.OUT/'frozen-var-before.json')),'frozen_var_unchanged':True,'unresolved_mandatory_blockers':[],'limitations':limitations,'retained_attempts':['artifact-members-sandbox-attempt: default sandbox read denied; rerun authorized scope PASS','candidate-rework-patch-diff-check: platform newline applicability','candidate-rework-0-diff-check: global autocrlf warnings','candidate-three-files-1-diff-check: CRLF detected as whitespace; final CRLF-aware checks PASS'],'recommended_next_action':'root independent new evidence verification and Owner Acceptance only; no next phase authorized','finished_at':datetime.now(timezone.utc).isoformat()}
g.save('summary.json',summary)
handoff='''Current phase/step: v0.4.2 R1-R5+R2.1 Owner minimum interval rework r1 new unified candidate Gate.
Base commit {base}; isolated snapshots no.git/no new commit; exact CH765files frozen. Original working tree status/protection audit belongs to root final audit.
Gate PASS_CANDIDATE; Owner Acceptance PENDING; CURRENT_DECISION FIX_ONLY; confirmed interval defect rework PASS; SIOS complete source diff YES; scope expansion NO.
Source {source}; new wheel {wheel}; new sdist {sdist}.
SIOS full256 {siosfull}; runtime54 {siosruntime}; approved patch {patch}.
Whole package796PASS/1 original optionalMCPskip/15 originalnetworkdeselect including22Ownerregressions; RH1static/compile/version/diffcheck PASS; source/wheel/sdist/member9fixtures byte matches PASS.
Core/sdist/mcp/baostock freshprofiles pipcheck/version/exports PASS; core+sdist both actualCLIhelp PASS; MCPbuild_server PASS. SIOS installed certified mootdx0.11.7/tdxpy0.2.7/pypdf6.10.0; fourETF Decimal exact4/4; default0.3.0pin still rejects candidate, explicitoptin admits.
SIOS provider67PASS; golden/qualification/parity165PASS+5defaultskip; whole973PASS+5defaultskip. Actual mandatory live5PASS0skip/xfail/deselect,54capabilitiesPASS,{calls}this-run retained rawcalls with actualHTTPbodies/TDXparserrows, six v3snapshot/policy/ShanghaiClock/evidence/RunManifest fullfacts.
TA123PASS7identicalbaselineFAIL4approveddeselect; legacy5PASS; frozen metadata mismatch retained; nonmandatoryTApipcheck not rerun. New installed wheel offline replay12savedpoints/74savedrawPASS; explicitly not this-runlive.
Frozen6007varbeforeafterPASS; CH/SIOS/TAidentitybeforeafterPASS; oldwheel3fd4f0...unchanged. Prior sandbox/newline attempts retained and final scoped checks PASS. Product only3approved interval files changed; no new production/source modifications in thisGate.
Evidence: summary.json,commands.json,artifacts.json,candidate-source.json,consumer-identities.json,profile-import-dependencies.json,A1-A11-evidence-map.json,ta-relative-compatibility.json,live-full-facts.json,freeze-var-proof.json,installed-wheel-replay/manifest.json.
Mandatory blockers NONE; limitations boundedminute/currentofficial/historyPIT and knownTAfailures remain. Next action: root fresh physical evidence review then OwnerAcceptance only. Release/publish/merge/push/tag/PyPI/nextPhase NO. DONE.
'''.format(base=current['base_commit'],source=current['working_tree_manifest_sha256'],wheel=wheel,sdist=summary['candidate_sdist_sha256'],siosfull=sios['source_manifest_sha256'],siosruntime=sios['runtime_source_sha256'],patch=consumer['sios_patch_sha256'],calls=len(calls))
(g.OUT/'handoff.txt').write_text(handoff,encoding='utf-8')
print(json.dumps({'status':'PASS_CANDIDATE','flags':flags,'results':{n:{'passed':v['passed'],'failures':len(v['failures']),'skipped':len(v['skipped'])} for n,v in results.items()},'raw_calls':len(calls)},indent=2))
