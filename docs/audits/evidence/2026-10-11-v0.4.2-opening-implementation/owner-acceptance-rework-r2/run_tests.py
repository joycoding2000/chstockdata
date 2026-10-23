"""Exact r1 wheel boundary and explicit source identity for a gitless consumer."""
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent
WORK = Path('C:/Users/Administrator/.codex/visualizations/2026/10/13/01a135d1-a42d-73a3-b19f-dc0968e4ca6c/owner-rework-r2')
ROOT = WORK / 'systematic-investing-os'
PYTHON = Path('C:/Users/Administrator/.codex/visualizations/2026/10/10/01a125dd-33f2-78d3-abe7-45e0928975d0/v042-opening-implementation/profiles/owner-rework-r1/sios-candidate/Scripts/python.exe')
name = sys.argv[1]
args = sys.argv[2:]
env = dict(os.environ, PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1', PYTEST_DISABLE_PLUGIN_AUTOLOAD='1')
env['PYTHONPATH'] = os.pathsep.join((str(ROOT / 'src'), str(WORK / 'wheel')))
env['TEMP'] = env['TMP'] = str(WORK / 'temp')
env['CHSTOCKDATA_CACHE_DIR'] = str(WORK / 'cache')
for d in ('temp', 'cache'):
    (WORK / d).mkdir(exist_ok=True)
code = '''import sys, hashlib, json, zipfile
from pathlib import Path
root=Path(sys.argv[1]); work=root.parent
import chstockdata
package=Path(chstockdata.__file__).parent
assert package==work/'wheel/chstockdata'
wheel=work/'chstockdata-0.4.2-py3-none-any.whl'
assert hashlib.sha256(wheel.read_bytes()).hexdigest()=='1dd58350678fbb07d3b545165708d814f93fb94f965dc2da33bad2fab7ff779c'
with zipfile.ZipFile(wheel) as z:
    for n in z.namelist():
        if n.startswith('chstockdata/') and not n.endswith('/'):
            assert (work/'wheel'/n).read_bytes()==z.read(n), n
files={p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((root/'src').rglob('*.py'))}
tree=hashlib.sha256(json.dumps(files,sort_keys=True,separators=(',',':')).encode()).hexdigest()
import systematic_investing.research.runner as runner
import systematic_investing.research.oos as oos
runner.resolve_code_commit=lambda:'source_tree_sha256:'+tree
oos.resolve_code_commit=lambda:'source_tree_sha256:'+tree
print(json.dumps({'wheel_sha256':hashlib.sha256(wheel.read_bytes()).hexdigest(),'chstockdata_file':str(package),'sios_runtime_sha256':tree,'test_only_identity_injection':['research.runner','research.oos']}))
import pytest
raise SystemExit(pytest.main(sys.argv[2:]))
'''
argv = [str(PYTHON), '-c', code, str(ROOT), *args, '-q', '-p', 'no:cacheprovider', '--basetemp', str(WORK / 'temp' / name), '--junitxml', str(OUT / (name + '.xml'))]
result = subprocess.run(argv, cwd=ROOT, env=env, capture_output=True, text=True, encoding='utf-8', errors='replace')
(OUT / (name + '.log')).write_text(result.stdout + result.stderr, encoding='utf-8')
(OUT / (name + '.exit')).write_text(str(result.returncode), encoding='utf-8')
(OUT / (name + '.command.json')).write_text(json.dumps({'argv': argv, 'cwd': str(ROOT), 'exit': result.returncode, 'log_sha256': hashlib.sha256((OUT / (name + '.log')).read_bytes()).hexdigest()}, indent=2), encoding='utf-8')
print((result.stdout + result.stderr)[-12000:])
raise SystemExit(result.returncode)
