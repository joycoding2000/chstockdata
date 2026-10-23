"""Root verification of final artifact, source, installed bytes and actual evidence."""
import hashlib
import json
from pathlib import Path
import tarfile
import xml.etree.ElementTree as ET
import zipfile

out = Path(__file__).resolve().parent
work = out.parents[1]
read = lambda path: json.loads(path.read_text(encoding='utf-8'))
sha = lambda data: hashlib.sha256(data).hexdigest()
summary = read(out / 'summary.json')
artifacts = read(out / 'artifacts.json')
wheel = Path(artifacts['wheel']['path'])
sdist = Path(artifacts['sdist']['path'])
wheel_sha = sha(wheel.read_bytes())
assert wheel_sha == artifacts['wheel']['sha256'] == summary['candidate_wheel_sha256']
assert sha(sdist.read_bytes()) == artifacts['sdist']['sha256'] == summary['candidate_sdist_sha256']
identity = artifacts['source_only_identity']
files = identity['working_tree_files']
manifest_sha = sha(json.dumps(files, sort_keys=True).encode('utf-8'))
assert manifest_sha == identity['working_tree_manifest_sha256'] == summary['candidate_source_sha256']
envelope = artifacts['source_identity']['working_tree_files']
assert all(envelope[name] == digest for name, digest in files.items())
assert all(sha((work / 'chstockdata' / name).read_bytes()) == digest for name, digest in files.items())

with zipfile.ZipFile(wheel) as archive:
    members = {name: archive.read(name) for name in archive.namelist()
               if name.startswith('chstockdata/') and not name.endswith('/')}
assert {name.removeprefix('chstockdata/'): sha(data) for name, data in members.items()} == identity['package_files']
profile_counts = {}
for profile in ('core', 'sdist', 'mcp', 'baostock', 'sios-candidate', 'ta-candidate'):
    site = work / 'profiles/r21-qualified' / profile / 'Lib/site-packages'
    assert all((site / name).read_bytes() == data for name, data in members.items()), profile
    metadata = (site / 'chstockdata-0.4.2.dist-info/METADATA').read_text(encoding='utf-8')
    assert '\nVersion: 0.4.2\n' in metadata
    profile_counts[profile] = len(members)
with tarfile.open(sdist) as archive:
    packaged = {member.name: archive.extractfile(member).read()
                for member in archive.getmembers() if member.isfile()}
prefix = 'chstockdata-0.4.2/'
fixture_names = [name for name in files if name.startswith('tests/fixtures/')]
assert all(sha(packaged[prefix + name]) == files[name] for name in fixture_names)
assert all(packaged[prefix + 'src/' + name] == data for name, data in members.items())

results = {}
for name, expected in summary['results'].items():
    path = Path(expected['path'])
    assert sha(path.read_bytes()) == expected['sha256'], name
    cases = list(ET.parse(path).getroot().iter('testcase'))
    failures = sum(case.find('failure') is not None for case in cases)
    errors = sum(case.find('error') is not None for case in cases)
    skips = sum(case.find('skipped') is not None for case in cases)
    actual = {'tests': len(cases), 'passed': len(cases) - failures - errors - skips,
              'failed': failures, 'errors': errors, 'skipped': skips}
    assert actual['passed'] == expected['passed']
    assert failures == len(expected['failures']) and errors == len(expected['errors']) and skips == len(expected['skipped'])
    results[name] = actual
assert results['live'] == {'tests': 5, 'passed': 5, 'failed': 0, 'errors': 0, 'skipped': 0}
commands = {item['name']: item for item in read(out / 'commands.json')}
for name in summary['required_zero_exit_commands']:
    item = commands[name]
    assert item['exit'] == 0 and item['candidate_wheel_sha256'] == wheel_sha, name
    assert item['candidate_source_only_sha256'] == manifest_sha, name
    assert Path(item['record_file']).exists(), name
    exit_path = out / item['exit_file']
    assert exit_path.read_text(encoding='utf-8').strip() == '0', name
    assert (out / item['log']).exists(), name
live = out / 'final-live'
calls = read(live / 'calls.json')
assert len(calls) == 111
assert all('raw_path' in call and sha((live / call['raw_path']).read_bytes()) == call['raw_sha256']
           and len((live / call['raw_path']).read_bytes()) == call['raw_bytes'] for call in calls)
assert read(live / 'source-before.json') == read(live / 'source-after.json')
assert read(live / 'live-result.json')['exit_code'] == 0
report = {'executor': 'root independent verification', 'source_only_sha256': manifest_sha,
          'wheel_sha256': wheel_sha, 'sdist_sha256': sha(sdist.read_bytes()),
          'source_only_files_equal_current_and_prebuild': len(files),
          'installed_members_verified_per_profile': profile_counts,
          'sdist_fixture_files_verified': len(fixture_names), 'results': results,
          'mandatory_zero_exit_commands_verified': len(summary['required_zero_exit_commands']),
          'actual_final_live_raw_files_verified': len(calls), 'exit_code': 0,
          'claim': 'identities and actual evidence independently checked; no new network or repeated full suites'}
(out / 'independent-final-verification.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
(out / 'independent-final-verification.exit').write_text('0\n', encoding='utf-8')
print(json.dumps(report))
