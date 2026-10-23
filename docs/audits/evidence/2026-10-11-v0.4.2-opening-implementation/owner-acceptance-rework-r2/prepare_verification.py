"""Reuse frozen read-only snapshot and unchanged observational live harness."""
import hashlib
import json
import shutil
from pathlib import Path

OUT = Path(__file__).resolve().parent
OLD = Path('C:/Users/Administrator/.codex/visualizations/2026/10/10/01a125dd-33f2-78d3-abe7-45e0928975d0/v042-opening-implementation')
WORK = Path('C:/Users/Administrator/.codex/visualizations/2026/10/13/01a135d1-a42d-73a3-b19f-dc0968e4ca6c/owner-rework-r2')
ROOT = WORK / 'systematic-investing-os'
baseline = json.loads((OUT / 'sios-baseline-manifest.json').read_text(encoding='utf-8'))
paths = sorted(set(baseline['source_files_sha256']) | {'tests/component/test_owner_r2_interval_contract.py'})
files = {n: hashlib.sha256((ROOT / n).read_bytes()).hexdigest() for n in paths}
runtime = {n: v for n, v in files.items() if n.startswith('src/') and n.endswith('.py')}
identity = {'source_files_sha256': files, 'source_manifest_sha256': hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest(),
    'runtime_source_sha256': hashlib.sha256(json.dumps(runtime, sort_keys=True, separators=(',', ':')).encode()).hexdigest(), 'frozen_commit': baseline['frozen_commit'], 'identity_kind': '257 source/config/test/docs file manifest, not Git commit'}
(OUT / 'sios-source-manifest.json').write_text(json.dumps(identity, indent=2), encoding='utf-8')
source = OLD / 'systematic-investing-os/var/research/snapshots/basic-etf-v1'
dest = ROOT / 'var/research/snapshots/basic-etf-v1'
proof = {}
for p in sorted(source.rglob('*')):
    if p.is_file():
        n = p.relative_to(source)
        target = dest / n
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(p.read_bytes())
        proof[n.as_posix()] = hashlib.sha256(target.read_bytes()).hexdigest()
(OUT / 'frozen-smoke-snapshot.json').write_text(json.dumps(proof, indent=2), encoding='utf-8')
assert (dest / 'manifest.json').exists()
runner = (OLD / 'evidence/owner-acceptance-rework-r1/gate/run_live.py').read_text(encoding='utf-8')
runner = runner.replace(str(OLD).replace('\\', '/'), str(WORK).replace('\\', '/'))
runner = runner.replace('CH = W / "chstockdata-owner-rework"', 'CH = W / "wheel"')
runner = runner.replace('import run_gate\nrun_gate.installed_identity("sios-candidate")', '''import zipfile
wheel = W / "chstockdata-0.4.2-py3-none-any.whl"
assert sha(wheel.read_bytes()) == "1dd58350678fbb07d3b545165708d814f93fb94f965dc2da33bad2fab7ff779c"
assert Path(chstockdata.__file__).parent == CH / "chstockdata"
with zipfile.ZipFile(wheel) as archive:
    for name in archive.namelist():
        if name.startswith("chstockdata/") and not name.endswith("/"):
            assert (CH / name).read_bytes() == archive.read(name), name''')
runner = runner.replace('HERE.parent/"sios-source-manifest.json"', 'HERE/"sios-source-manifest.json"')
runner = runner.replace('HERE.parent/"sios-source-vs-frozen.patch"', 'HERE/"sios-source-vs-r1.patch"')
runner = runner.replace('W / "dist/owner-rework-r1/chstockdata-0.4.2-py3-none-any.whl"', 'W / "chstockdata-0.4.2-py3-none-any.whl"')
runner = runner.replace('CH / "src/chstockdata/opening_known_events.json"', 'CH / "chstockdata/opening_known_events.json"')
(OUT / 'run_live.py').write_text(runner, encoding='utf-8')
print(json.dumps({'sios_source_sha256': identity['source_manifest_sha256'], 'runtime_sha256': identity['runtime_source_sha256'], 'frozen_snapshot_files': len(proof)}))
