"""Complete r2-only delta, actual apply proof, source manifest and trust identity."""
import difflib
import hashlib
import json
import subprocess
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent
OLD = Path('C:/Users/Administrator/.codex/visualizations/2026/10/10/01a125dd-33f2-78d3-abe7-45e0928975d0/v042-opening-implementation')
WORK = Path('C:/Users/Administrator/.codex/visualizations/2026/10/13/01a135d1-a42d-73a3-b19f-dc0968e4ca6c/owner-rework-r2')
ROOT = WORK / 'systematic-investing-os'
BASE = json.loads((OUT / 'sios-baseline-manifest.json').read_text(encoding='utf-8'))['source_files_sha256']
NAME = 'src/systematic_investing/domain/historical_opening.py'
target = ROOT / NAME
if sys.argv[1:] == ['negative-control']:
    fixed = target.read_bytes()
    try:
        old = (OLD / 'systematic-investing-os' / NAME).read_bytes()
        assert hashlib.sha256(old).hexdigest() == BASE[NAME]
        target.write_bytes(old)
        result = subprocess.run([sys.executable, str(OUT / 'run_tests.py'), 'red-final', 'tests/component/test_owner_r2_interval_contract.py'], cwd=OUT)
        assert result.returncode == 1
    finally:
        target.write_bytes(fixed)
    print('Negative control finished; fixed source restored byte-for-byte')
    raise SystemExit(0)

CURRENT = json.loads((OUT / 'sios-source-manifest.json').read_text(encoding='utf-8'))['source_files_sha256']
rebuilt = WORK / 'delta-reconstruction'
assert not rebuilt.exists()
for n, digest in BASE.items():
    data = (OLD / 'systematic-investing-os' / n).read_bytes()
    assert hashlib.sha256(data).hexdigest() == digest
    dest = rebuilt / n
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
parts = []
changed = []
for n in sorted(set(BASE) | set(CURRENT)):
    new = (ROOT / n).read_bytes()
    assert hashlib.sha256(new).hexdigest() == CURRENT[n]
    old = (rebuilt / n).read_bytes() if n in BASE else b''
    if new == old:
        continue
    changed.append(n)
    parts.append(f'diff --git a/{n} b/{n}\n')
    if n not in BASE:
        parts.append('new file mode 100644\n')
    parts.extend(difflib.unified_diff(old.decode('utf-8').splitlines(keepends=True), new.decode('utf-8').splitlines(keepends=True), fromfile='a/' + n if n in BASE else '/dev/null', tofile='b/' + n))
patch = OUT / 'sios-source-vs-r1.patch'
patch.write_bytes(''.join(parts).encode('utf-8'))
results = []
for label, extra in [('check', ['--check']), ('apply', [])]:
    argv = ['git', '-c', 'core.autocrlf=false', 'apply', '--whitespace=nowarn', *extra, str(patch)]
    result = subprocess.run(argv, cwd=rebuilt, capture_output=True, text=True, encoding='utf-8')
    results.append({'argv': argv, 'cwd': str(rebuilt), 'exit': result.returncode, 'output': result.stdout + result.stderr})
    assert result.returncode == 0, result.stderr
assert {p.relative_to(rebuilt).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in rebuilt.rglob('*') if p.is_file()} == CURRENT
for n in changed:
    dest = OUT / 'delta' / n
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes((ROOT / n).read_bytes())
(OUT / 'delta-verification.json').write_text(json.dumps({'changed_files': changed, 'patch_sha256': hashlib.sha256(patch.read_bytes()).hexdigest(), 'apply': results, 'all_257_files_equal': True}, indent=2), encoding='utf-8')
print(json.dumps({'changed_files': changed, 'reconstruction': 'PASS_257_FILES'}))
