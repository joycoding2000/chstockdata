"""Limited offline Owner regression evidence; no build, publication or live gate."""
import hashlib
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

OUT = Path(__file__).resolve().parent
WORK = OUT.parents[1]
ROOT = WORK / 'chstockdata-owner-rework'
PYTHON = Path('C:/Users/Administrator/.codex/visualizations/2026/10/09/01a11feb-cbea-7790-a83e-57b1dd555e13/v042-unified/sios-candidate/Scripts/python.exe')
EXTRA = 'C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/Lib/site-packages'
ENV = dict(os.environ, PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1', PYTEST_DISABLE_PLUGIN_AUTOLOAD='1')
ENV.pop('PYTHONPATH', None)
ENV['TEMP'] = ENV['TMP'] = str(OUT / 'temp')
ENV['CHSTOCKDATA_CACHE_DIR'] = str(OUT / 'cache')
ENV['RUFF_CACHE_DIR'] = str(OUT / 'cache/ruff')
for folder in ('temp', 'cache'):
    (OUT / folder).mkdir(exist_ok=True)


def command(name, argv, cwd=ROOT):
    result = subprocess.run([str(a) for a in argv], cwd=cwd, env=ENV, capture_output=True,
                            text=True, encoding='utf-8', errors='replace')
    log = OUT / (name + '.log')
    log.write_text(result.stdout + result.stderr, encoding='utf-8')
    (OUT / (name + '.exit')).write_text(str(result.returncode) + '\n', encoding='utf-8')
    record = {'name': name, 'argv': [str(a) for a in argv], 'cwd': str(cwd),
              'exit': result.returncode, 'log': log.name,
              'log_sha256': hashlib.sha256(log.read_bytes()).hexdigest(), 'offline_injected': True}
    junit = OUT / (name + '.xml')
    if junit.exists():
        record.update(junit=junit.name, junit_sha256=hashlib.sha256(junit.read_bytes()).hexdigest())
    (OUT / (name + '.command.json')).write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(record), flush=True)
    return result.returncode


def pytest_run(name, selection):
    code = ('import sys; sys.path.insert(0,' + repr(str(ROOT / 'src')) + '); '
            'sys.path.append(' + repr(EXTRA) + '); import pytest; '
            'raise SystemExit(pytest.main(' + repr(selection + ['-q', '-p', 'no:cacheprovider',
                '--basetemp=' + str(OUT / ('temp/' + name)), '--junitxml=' + str(OUT / (name + '.xml'))]) + '))')
    return command(name, [PYTHON, '-c', code])


phase = sys.argv[1]
if phase == 'old-wheel':
    wheel = WORK / 'dist/r21-qualified/chstockdata-0.4.2-py3-none-any.whl'
    assert hashlib.sha256(wheel.read_bytes()).hexdigest() == '3fd4f0b7334e310851495b8b13d4c7c55d21cde719acf9e00ff880ccb822f42e'
    unpacked = OUT / 'old-wheel-unpacked'
    with zipfile.ZipFile(wheel) as archive:
        archive.extractall(unpacked)
    code = f'''import sys, importlib.util, json
sys.path.insert(0, {str(unpacked)!r})
spec=importlib.util.spec_from_file_location('owner_regression', {str(ROOT / 'tests/test_historical_opening_evidence.py')!r})
module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
rows=[]
for day in ('2015-12-18','2016-07-04','2016-07-05','2022-12-30'):
    data=module.owner_interval_fetch(day).data
    rows.append({{k:data[k] for k in ('session_date','opening_status','source_conflict','official_block_at_target','reason')}})
print(json.dumps({{'qualification':'offline injected reproduction against extracted unchanged old wheel','wheel_sha256':'3fd4f0b7334e310851495b8b13d4c7c55d21cde719acf9e00ff880ccb822f42e','results':rows}},indent=2))
assert [r['opening_status'] for r in rows]==['OPEN_ACTIVITY_CONFIRMED','UNKNOWN','UNKNOWN','UNKNOWN']
assert all(r['source_conflict'] and r['official_block_at_target'] for r in rows[1:])
'''
    raise SystemExit(command('old-wheel-owner-repro', [PYTHON, '-c', code]))
if phase in {'red', 'green'}:
    raise SystemExit(pytest_run('owner-' + phase, ['tests/test_historical_opening_evidence.py', '-k', 'owner_']))
if phase == 'focused':
    raise SystemExit(pytest_run('focused-green', ['tests/test_historical_opening_evidence.py',
        'tests/test_suspension_structured.py', 'tests/test_suspension_source_semantics.py',
        'tests/test_vipdoc_price_scale.py']))
if phase == 'static':
    raise SystemExit(command('rh1-static', [
        'D:/Dev/Projects/chstockdata/build/v042-qualification/gate/Scripts/python.exe',
        OUT / 'run_static_rework.py']))
if phase == 'export':
    raise SystemExit(command('export-evidence-final', [PYTHON, OUT / 'export_evidence.py']))
raise ValueError('unknown limited evidence phase')
