"""Independent byte identities, JUnit counts and raw live evidence verification."""
import hashlib
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

OUT = Path(__file__).resolve().parent
OLD = Path('C:/Users/Administrator/.codex/visualizations/2026/10/10/01a125dd-33f2-78d3-abe7-45e0928975d0/v042-opening-implementation')
WORK = Path('C:/Users/Administrator/.codex/visualizations/2026/10/13/01a135d1-a42d-73a3-b19f-dc0968e4ca6c/owner-rework-r2')
sha = lambda data: hashlib.sha256(data).hexdigest()
read = lambda path: json.loads(path.read_text(encoding='utf-8'))
manifest = read(OUT / 'sios-source-manifest.json')
assert sha(json.dumps(manifest['source_files_sha256'], sort_keys=True).encode()) == manifest['source_manifest_sha256']
for name, digest in manifest['source_files_sha256'].items():
    assert sha((WORK / 'systematic-investing-os' / name).read_bytes()) == digest, name
baseline = read(OUT / 'sios-baseline-manifest.json')
for name, digest in baseline['source_files_sha256'].items():
    assert sha((OLD / 'systematic-investing-os' / name).read_bytes()) == digest, name
ch = read(OLD / 'evidence/owner-acceptance-rework-r1/rework-source-manifest.json')['source_files']
for name, digest in ch.items():
    assert sha((OLD / 'chstockdata-owner-rework' / name).read_bytes()) == digest, name
wheel = WORK / 'chstockdata-0.4.2-py3-none-any.whl'
assert sha(wheel.read_bytes()) == '1dd58350678fbb07d3b545165708d814f93fb94f965dc2da33bad2fab7ff779c'
receipt = read(OUT.parent / 'owner-acceptance-rework-r1-delivery-receipt.json')
assert sha((OUT.parent / 'owner-acceptance-rework-r1-evidence.zip').read_bytes()) == receipt['zip_sha256']
assert read(OUT / 'delta-verification.json')['all_257_files_equal']


def junit(path):
    root = ET.parse(path)
    cases = list(root.iter('testcase'))
    return {'tests': len(cases), 'pass': sum(all(c.find(n) is None for n in ('failure', 'error', 'skipped')) for c in cases),
        **{n: sum(c.find(n) is not None for c in cases) for n in ('failure', 'error', 'skipped')}}


checks = {n: junit(OUT / (n + '.xml')) for n in ('red', 'red-final', 'green-26', 'sios-offline-final', 'sios-provider', 'sios-golden-etf')}
assert checks['red'] == {'tests': 16, 'pass': 13, 'failure': 3, 'error': 0, 'skipped': 0}
assert checks['red-final'] == {'tests': 26, 'pass': 19, 'failure': 7, 'error': 0, 'skipped': 0}
for n, count, skips in [('green-26', 26, 0), ('sios-offline-final', 999, 5), ('sios-provider', 73, 0), ('sios-golden-etf', 165, 5)]:
    assert checks[n] == {'tests': count + skips, 'pass': count, 'failure': 0, 'error': 0, 'skipped': skips}, n
    assert (OUT / (n + '.exit')).read_text(encoding='utf-8') == '0'
offline = ET.parse(OUT / 'sios-offline-final.xml')
regressions = [c for c in offline.iter('testcase') if any(word in c.attrib.get('classname', '') for word in ('historical_opening', 'snapshot', 'kernel_replay', 'point_in_time', 'pit'))]
assert all(all(c.find(n) is None for n in ('failure', 'error', 'skipped')) for c in regressions)
result = {'sios_source_sha256': manifest['source_manifest_sha256'], 'sios_runtime_sha256': manifest['runtime_source_sha256'],
    'chstockdata_wheel_unchanged': True, 'chstockdata_source_files_unchanged': len(ch), 'old_sios_files_unchanged': len(baseline['source_files_sha256']),
    'r1_delivery_zip_unchanged': True, 'junit': checks, 'snapshot_pit_replay_related_passed': len(regressions)}
if '--offline' not in sys.argv:
    checks['mandatory-live'] = junit(OUT / 'live/live.xml')
    assert checks['mandatory-live'] == {'tests': 5, 'pass': 5, 'failure': 0, 'error': 0, 'skipped': 0}
    live = read(OUT / 'live/live-result.json')
    assert live['exit_code'] == 0 and live['source_unchanged'] is True
    assert read(OUT / 'live/source-before.json') == read(OUT / 'live/source-after.json')
    assert read(OUT / 'live/qualification-source-before.json') == read(OUT / 'live/qualification-source-after.json')
    imports = read(OUT / 'live/actual-imports.json')
    assert imports['sios_full_source_sha256'] == manifest['source_manifest_sha256']
    assert imports['sios_runtime_source_sha256'] == manifest['runtime_source_sha256']
    assert imports['wheel_sha256'] == sha(wheel.read_bytes())
    capabilities = [entry for path in (OUT / 'live/capabilities').glob('*.json') for entry in read(path)['outcomes']]
    assert len(capabilities) == 54 and all(entry['status'] == 'PASS' for entry in capabilities)
    calls = read(OUT / 'live/calls.json')
    raw = []
    for call in calls:
        if 'raw_path' in call:
            data = (OUT / 'live' / call['raw_path']).read_bytes()
            assert sha(data) == call['raw_sha256'] and len(data) == call['raw_bytes']
            raw.append(call['raw_path'])
    result.update(live_raw_verified=len(raw), live_calls=len(calls), live_source_unchanged=True, live_capabilities_passed=len(capabilities))
    result['verdict'] = 'PASS_CANDIDATE_OWNER_PENDING'
    (OUT / 'independent-verification.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
else:
    (OUT / 'independent-offline-verification.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps(result, indent=2))
