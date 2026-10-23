"""Reuse unchanged RH1 Git-less runner with only the isolated ROOT/output adapted."""
import hashlib
import json
import os
import runpy
import subprocess
import sys
import types
from pathlib import Path

OUT = Path(__file__).resolve().parent
WORK = OUT.parents[1]
gate = types.ModuleType('run_gate')
gate.ROOT = WORK / 'chstockdata-owner-rework'
gate.ENV = dict(os.environ, PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1', PYTEST_DISABLE_PLUGIN_AUTOLOAD='1')
gate.ENV.pop('PYTHONPATH', None)
gate.ENV['TEMP'] = gate.ENV['TMP'] = str(OUT / 'temp')
gate.ENV['CHSTOCKDATA_CACHE_DIR'] = str(OUT / 'cache')
gate.ENV['RUFF_CACHE_DIR'] = str(OUT / 'cache/ruff')
gate.sha = lambda data: hashlib.sha256(data).hexdigest()
gate.save = lambda name, data: (OUT / name).write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')
gate.git = lambda repo, *args: subprocess.check_output(
    ['git', '-c', 'safe.directory=' + repo.as_posix(), '-C', str(repo), *args], env=gate.ENV)
sys.modules['run_gate'] = gate
runpy.run_path(str(WORK / 'evidence/r21-step4/run_static.py'), run_name='__main__')
