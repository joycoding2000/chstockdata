"""Reconstruct the unchanged r1 consumer and wheel in a writable isolation root."""
import hashlib
import json
import shutil
import zipfile
from pathlib import Path

OLD = Path('C:/Users/Administrator/.codex/visualizations/2026/10/10/01a125dd-33f2-78d3-abe7-45e0928975d0/v042-opening-implementation')
OUT = Path(__file__).resolve().parent
WORK = Path('C:/Users/Administrator/.codex/visualizations/2026/10/13/01a135d1-a42d-73a3-b19f-dc0968e4ca6c/owner-rework-r2')
SIOS = WORK / 'systematic-investing-os'
WHEEL = OLD / 'dist/owner-rework-r1/chstockdata-0.4.2-py3-none-any.whl'
EXPECTED = '1dd58350678fbb07d3b545165708d814f93fb94f965dc2da33bad2fab7ff779c'
manifest = json.loads((OLD / 'evidence/owner-acceptance-rework-r1/sios-source-manifest.json').read_text(encoding='utf-8'))
assert hashlib.sha256(WHEEL.read_bytes()).hexdigest() == EXPECTED
for name, digest in manifest['source_files_sha256'].items():
    content = (OLD / 'systematic-investing-os' / name).read_bytes()
    assert hashlib.sha256(content).hexdigest() == digest, name
    target = SIOS / name
    target.parent.mkdir(parents=True, exist_ok=True)
    assert not target.exists(), name
    target.write_bytes(content)
with zipfile.ZipFile(WHEEL) as archive:
    archive.extractall(WORK / 'wheel')
shutil.copyfile(WHEEL, WORK / WHEEL.name)
shutil.copyfile(OLD / 'evidence/owner-acceptance-rework-r1/sios-source-manifest.json', OUT / 'sios-baseline-manifest.json')
(OUT / 'baseline.json').write_text(json.dumps({'sios': str(SIOS), 'work': str(WORK), 'wheel_sha256': EXPECTED, 'sios_files_verified': len(manifest['source_files_sha256']), 'old_sios_manifest_sha256': manifest['source_manifest_sha256']}, indent=2), encoding='utf-8')
print('Verified and copied', len(manifest['source_files_sha256']), 'SIOS files and unchanged r1 wheel')
