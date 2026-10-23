"""Scoped RED/GREEN and original regression evidence for the identity fix."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys
import uuid

EVIDENCE = Path(__file__).resolve().parent
ROOT = EVIDENCE.parents[3]


def save(name, data):
    (EVIDENCE / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def prepare():
    assert not (EVIDENCE / 'before.json').exists()
    names = ['README.md', 'src/chstockdata/__init__.py', 'src/chstockdata/a_stock.py',
             'src/chstockdata/fetch_result.py', 'tests/test_rh1_git_line_endings.py',
             'scripts/check_rh1_static.py', 'pyproject.toml', 'docs/dr04-p-daily-fund-flow.md']
    paths = [ROOT / name for name in names]
    paths += [ROOT / '.git/config', Path.home() / '.gitconfig', Path(r'C:\Program Files\Git\etc\gitconfig'),
              Path(r'D:\Dev\Projects\mishi-radar\outputs\dr04-minimum-consumer-contract-2026-10-17\dr04-minimum-consumer-contract-owner-review.md')]
    work = ROOT / '.pytest_cache' / ('dr04-p-type-identity-' + uuid.uuid4().hex[:12])
    work.mkdir(parents=True, exist_ok=False)
    save('before.json', {'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
         'temp_root': str(work), 'protected_sha256': {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}})
    for name, output in [('src/chstockdata/daily_fund_flow.py', 'module-before.txt'),
                         ('tests/test_daily_fund_flow.py', 'tests-before.txt')]:
        (EVIDENCE / output).write_bytes((ROOT / name).read_bytes())
    (EVIDENCE / 'tracked-before.diff').write_bytes(subprocess.check_output(['git', 'diff'], cwd=ROOT))


def run(mode):
    before = json.loads((EVIDENCE / 'before.json').read_text(encoding='utf-8'))
    tests = ['test_daily_fund_flow.py']
    if mode == 'full':
        tests += ['test_astock_tdx_fallback.py', 'test_astock_interface_fix.py',
                  'test_astock_silent_failure_sentinel.py', 'test_fetch_result_core.py',
                  'test_trading_calendar_structured.py', 'test_config_and_warmup_regression.py',
                  'test_release_version.py', 'test_rh1_git_line_endings.py']
    temp = Path(before['temp_root']) / mode
    assert temp.parent.is_dir() and not temp.exists()
    command = [sys.executable, '-m', 'pytest', *(f'tests/{name}' for name in tests), '-q', '--tb=short',
               f'--basetemp={temp}', f'--junitxml={EVIDENCE / (mode + ".xml")}']
    if mode != 'full':
        command += ['-k', 'type_identity']
    result = subprocess.run(command, cwd=ROOT, capture_output=True)
    (EVIDENCE / (mode + '.stdout.txt')).write_bytes(result.stdout)
    (EVIDENCE / (mode + '.stderr.txt')).write_bytes(result.stderr)
    save(mode + '-command.json', {'command': command, 'cwd': str(ROOT), 'exit_code': result.returncode})
    print(result.stdout.decode('utf-8', errors='replace'))
    return result.returncode


if __name__ == '__main__':
    if sys.argv[1] == 'prepare':
        prepare()
    else:
        raise SystemExit(run(sys.argv[1]))
