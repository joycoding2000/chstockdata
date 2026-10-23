"""Root artifact/evidence check: no test rerun, network or source writes."""
import hashlib
import json
from pathlib import Path
import tarfile
import xml.etree.ElementTree as ET
import zipfile

OUT = Path(__file__).resolve().parent
WORK = OUT.parents[1]
GATE = OUT / 'gate'
read = lambda path: json.loads(path.read_text(encoding='utf-8'))
sha = lambda data: hashlib.sha256(data).hexdigest()
mapping_sha = lambda files: sha(json.dumps(files, sort_keys=True).encode('utf-8'))
summary = read(GATE / 'summary.json')
artifacts = read(GATE / 'artifacts.json')
wheel, sdist = (Path(artifacts[key]['path']) for key in ('wheel', 'sdist'))
wheel_sha = sha(wheel.read_bytes())
assert wheel_sha == artifacts['wheel']['sha256'] == summary['candidate_wheel_sha256']
assert sha(sdist.read_bytes()) == artifacts['sdist']['sha256'] == summary['candidate_sdist_sha256']
identity = artifacts['source_identity']
files = identity['working_tree_files']
source_sha = mapping_sha(files)
assert source_sha == identity['working_tree_manifest_sha256'] == summary['candidate_source_sha256']
assert files == read(OUT / 'rework-source-manifest.json')['source_files']
assert len(files) == 765
assert all(sha((WORK / 'chstockdata-owner-rework' / name).read_bytes()) == digest for name, digest in files.items())
with zipfile.ZipFile(wheel) as archive:
    members = {name: archive.read(name) for name in archive.namelist()
               if name.startswith('chstockdata/') and not name.endswith('/')}
assert {name.removeprefix('chstockdata/'): sha(data) for name, data in members.items()} == identity['package_files']
profile_counts = {}
for profile in ('core', 'sdist', 'mcp', 'baostock', 'sios-candidate', 'ta-candidate'):
    site = WORK / 'profiles/owner-rework-r1' / profile / 'Lib/site-packages'
    assert all((site / name).read_bytes() == data for name, data in members.items()), profile
    assert '\nVersion: 0.4.2\n' in (site / 'chstockdata-0.4.2.dist-info/METADATA').read_text(encoding='utf-8')
    profile_counts[profile] = len(members)
with tarfile.open(sdist) as archive:
    packaged = {member.name: archive.extractfile(member).read()
                for member in archive.getmembers() if member.isfile()}
prefix = 'chstockdata-0.4.2/'
fixtures = [name for name in files if name.startswith('tests/fixtures/')]
assert all(sha(packaged[prefix + name]) == files[name] for name in fixtures)
assert all(packaged[prefix + 'src/' + name] == data for name, data in members.items())
results = {}
for name, expected in summary['results'].items():
    path = Path(expected['path'])
    assert sha(path.read_bytes()) == expected['sha256'], name
    cases = list(ET.parse(path).getroot().iter('testcase'))
    failures = sum(case.find('failure') is not None for case in cases)
    errors = sum(case.find('error') is not None for case in cases)
    skips = sum(case.find('skipped') is not None for case in cases)
    actual = dict(tests=len(cases), passed=len(cases)-failures-errors-skips,
                  failed=failures, errors=errors, skipped=skips)
    assert actual['passed'] == expected['passed']
    assert failures == len(expected['failures']) and errors == len(expected['errors']) and skips == len(expected['skipped'])
    results[name] = actual
assert results['live'] == dict(tests=5, passed=5, failed=0, errors=0, skipped=0)
commands = read(GATE / 'commands.json')
assert sha((GATE / 'commands.json').read_bytes()) == summary['commands_sha256']
index = {item['name']: item for item in commands}
for item in commands:
    # Environment inventory ran before the wheel existed; it makes no package claim.
    assert item['candidate_wheel_sha256'] == wheel_sha or (
        item['name'] == 'environment' and not item['candidate_wheel_sha256'])
    assert item['candidate_source_sha256'] == source_sha
    assert item['sios_full_source_sha256'] == summary['sios_full_source_sha256']
    assert item['sios_runtime_source_sha256'] == summary['sios_runtime_source_sha256']
    assert item['sios_patch_sha256'] == summary['sios_patch_sha256']
    assert Path(item['record_file']).is_file()
    assert sha((GATE / item['log']).read_bytes()) == item['log_sha256']
    assert sha((GATE / item['exit_file']).read_bytes()) == item['exit_sha256']
    assert int((GATE / item['exit_file']).read_text(encoding='utf-8').strip()) == item['exit']
    for path, digest in item.get('argv_existing_files_sha256', {}).items():
        assert sha(Path(path).read_bytes()) == digest, (item['name'], path)
for name in summary['required_zero_exit_commands']:
    assert index[name]['exit'] == 0, name
live = GATE / 'live'
calls = read(live / 'calls.json')
assert len(calls) == 129 == summary['actual_required_live']['raw_calls']
assert all(sha((live / call['raw_path']).read_bytes()) == call['raw_sha256']
           and len((live / call['raw_path']).read_bytes()) == call['raw_bytes'] for call in calls)
assert read(live / 'source-before.json') == read(live / 'source-after.json')
assert read(live / 'live-result.json')['exit_code'] == 0
consumers = read(GATE / 'consumer-identities.json')
sios_files = consumers['final_sios_source_manifest']
assert len(sios_files) == 256 and mapping_sha(sios_files) == summary['sios_full_source_sha256']
assert sha((OUT / 'sios-source-vs-frozen.patch').read_bytes()) == summary['sios_patch_sha256']
with zipfile.ZipFile(OUT / 'sios-tested-source.zip') as archive:
    assert sorted(archive.namelist()) == sorted('systematic-investing-os/' + name for name in sios_files)
    for name, digest in sios_files.items():
        assert sha(archive.read('systematic-investing-os/' + name)) == digest
for name, digest in sios_files.items():
    assert sha((WORK / 'systematic-investing-os' / name).read_bytes()) == digest
    assert sha((OUT / 'sios-reconstructed-source-exact' / name).read_bytes()) == digest
for name, digest in consumers['final_ta_source_manifest'].items():
    assert sha((WORK / 'TradingAgents-AStock-Private' / name).read_bytes()) == digest
old = read(WORK / 'evidence/r21-step4/source-only-identity.json')
old_files = old['working_tree_files']
assert len(old_files) == 765
assert all(sha((WORK / 'chstockdata' / name).read_bytes()) == digest for name, digest in old_files.items())
assert sha((WORK / 'dist/r21-qualified/chstockdata-0.4.2-py3-none-any.whl').read_bytes()) == '3fd4f0b7334e310851495b8b13d4c7c55d21cde719acf9e00ff880ccb822f42e'
report = dict(executor='root independent read-only verification', exit_code=0,
              new_source_sha256=source_sha, new_wheel_sha256=wheel_sha,
              new_sdist_sha256=sha(sdist.read_bytes()), source_files_verified=len(files),
              installed_members_verified_per_profile=profile_counts,
              sdist_fixture_files_verified=len(fixtures), junit_results_verified=results,
              command_records_verified=len(commands),
              mandatory_zero_exit_commands_verified=len(summary['required_zero_exit_commands']),
              actual_new_live_raw_files_verified=len(calls),
              sios_actual_reconstructed_and_snapshot_files_verified=len(sios_files),
              old_source_files_and_old_wheel_unchanged=True,
              claim='New artifacts and actual saved evidence verified; no network or repeated full suites.')
(OUT / 'independent-new-gate-verification.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
print(json.dumps(report))
