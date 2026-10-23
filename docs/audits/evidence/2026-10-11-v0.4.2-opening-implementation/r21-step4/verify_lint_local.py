"""Independent affected-source verification after the finite lint correction."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

out = Path(__file__).resolve().parent
work = out.parents[1]
source = work / 'chstockdata'
python = 'C:/Users/Administrator/.codex/visualizations/2026/10/09/01a11feb-cbea-7790-a83e-57b1dd555e13/v042-unified/sios-candidate/Scripts/python.exe'
optional = 'C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/Lib/site-packages'
names = ('src/chstockdata/opening_evidence.py', 'src/chstockdata/opening_known_events.json',
         'src/chstockdata/__init__.py', 'tests/test_historical_opening_evidence.py')
identity = lambda: {name: hashlib.sha256((source / name).read_bytes()).hexdigest() for name in names}
before = identity()
args = ['tests/test_historical_opening_evidence.py', 'tests/test_suspension_structured.py',
        'tests/test_suspension_source_semantics.py', 'tests/test_vipdoc_price_scale.py',
        '-q', '-p', 'no:cacheprovider', '--basetemp', str(out / 'independent-lint-local-temp'),
        '--junitxml', str(out / 'independent-lint-local.xml')]
snippet = f'import sys; sys.path.append({optional!r}); import pytest; raise SystemExit(pytest.main({args!r}))'
argv = [python, '-B', '-c', snippet]
env = dict(os.environ, PYTHONPATH=str(source / 'src'), PYTHONUTF8='1',
           PYTHONDONTWRITEBYTECODE='1', PYTEST_DISABLE_PLUGIN_AUTOLOAD='1')
result = subprocess.run(argv, cwd=source, env=env, capture_output=True, text=True, encoding='utf-8', errors='replace')
(out / 'independent-lint-local.log').write_text(result.stdout + result.stderr, encoding='utf-8')
(out / 'independent-lint-local.exit').write_text(str(result.returncode) + '\n', encoding='utf-8')
after = identity()
record = {'executor': 'root', 'argv': argv, 'cwd': str(source),
          'environment_overrides': {key: env[key] for key in ('PYTHONPATH', 'PYTHONUTF8', 'PYTHONDONTWRITEBYTECODE', 'PYTEST_DISABLE_PLUGIN_AUTOLOAD')},
          'source_before': before, 'source_after': after, 'exit_code': result.returncode,
          'claim': 'affected source local verification; same-wheel unified Gate recorded separately'}
(out / 'independent-lint-local.command.json').write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
print(result.stdout, end='')
assert result.returncode == 0 and before == after
suites = ET.parse(out / 'independent-lint-local.xml').getroot()
cases = list(suites.iter('testcase'))
assert len(cases) == 128 and not any(case.find('failure') is not None or case.find('error') is not None or case.find('skipped') is not None for case in cases)
