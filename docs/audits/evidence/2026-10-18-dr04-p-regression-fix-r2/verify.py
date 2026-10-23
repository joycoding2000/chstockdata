"""DR04-P scoped verification; trace assertion execution without changing it."""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import uuid

EVIDENCE = Path(__file__).resolve().parent
ROOT = EVIDENCE.parents[3]
TARGET = ROOT / 'tests/test_rh1_git_line_endings.py'
NAME = 'test_crlf_preserves_added_line_discrimination'


def save(name, data):
    (EVIDENCE / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def prepare():
    assert not (EVIDENCE / 'before.json').exists()
    names = ['README.md', 'src/chstockdata/__init__.py', 'src/chstockdata/a_stock.py',
             'src/chstockdata/daily_fund_flow.py', 'src/chstockdata/fetch_result.py',
             'tests/test_daily_fund_flow.py', 'scripts/check_rh1_static.py', 'pyproject.toml',
             'docs/dr04-p-daily-fund-flow.md']
    files = [ROOT / name for name in names]
    files += [ROOT / '.git/config', Path.home() / '.gitconfig', Path(r'C:\Program Files\Git\etc\gitconfig')]
    save('before.json', {
        'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'protected_hashes': {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
        'temp_root': str(ROOT / '.pytest_cache' / ('dr04-p-git-fix-' + uuid.uuid4().hex[:12])),
    })
    (EVIDENCE / 'before.diff').write_bytes(subprocess.check_output(['git', 'diff'], cwd=ROOT))
    (EVIDENCE / 'before-test.py.txt').write_bytes(TARGET.read_bytes())


def focused():
    import pytest
    before = json.loads((EVIDENCE / 'before.json').read_text(encoding='utf-8'))
    current_tree = ast.parse(TARGET.read_text(encoding='utf-8'))
    original_tree = ast.parse((EVIDENCE / 'before-test.py.txt').read_text(encoding='utf-8'))
    def assertions(tree):
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == NAME)
        return [n for n in ast.walk(function) if isinstance(n, ast.Assert)]
    current, original = assertions(current_tree), assertions(original_tree)
    assert len(current) == len(original) == 3
    assert [ast.dump(n) for n in current] == [ast.dump(n) for n in original], 'original assertions changed'
    lines = {n.lineno for n in current}
    seen = {'False': set(), 'True': set()}
    def trace(frame, event, arg):
        if frame.f_code.co_name == NAME and Path(frame.f_code.co_filename).resolve() == TARGET:
            if event == 'line' and frame.f_lineno in lines:
                seen[str(frame.f_locals['modify_existing'])].add(frame.f_lineno)
            return trace
        return None
    temp = Path(before['temp_root']) / 'focused'
    assert not temp.exists()
    args = [f'tests/test_rh1_git_line_endings.py::{NAME}[False]',
            f'tests/test_rh1_git_line_endings.py::{NAME}[True]', '-vv', '--tb=short',
            f'--basetemp={temp}', f'--junitxml={EVIDENCE / "focused.xml"}']
    sys.path.insert(0, str(ROOT / 'src'))
    sys.settrace(trace)
    try:
        status = int(pytest.main(args))
    finally:
        sys.settrace(None)
    complete = all(value == lines for value in seen.values())
    save('assertion-execution.json', {'pytest_args': args, 'pytest_exit_code': status,
         'original_assertions_ast_unchanged': True, 'assertion_lines': sorted(lines),
         'executed_lines': {k: sorted(v) for k, v in seen.items()},
         'all_three_assertions_reached_per_case': complete})
    return status if status else (0 if complete else 1)


def regression():
    before = json.loads((EVIDENCE / 'before.json').read_text(encoding='utf-8'))
    focus = json.loads((EVIDENCE / 'assertion-execution.json').read_text(encoding='utf-8'))
    assert focus['pytest_exit_code'] == 0 and focus['all_three_assertions_reached_per_case']
    tests = ['test_daily_fund_flow.py', 'test_astock_tdx_fallback.py', 'test_astock_interface_fix.py',
             'test_astock_silent_failure_sentinel.py', 'test_fetch_result_core.py',
             'test_trading_calendar_structured.py', 'test_config_and_warmup_regression.py',
             'test_release_version.py', 'test_rh1_git_line_endings.py']
    temp = Path(before['temp_root']) / 'regression'
    assert not temp.exists()
    command = [sys.executable, '-m', 'pytest', *(f'tests/{name}' for name in tests),
               '-q', '--tb=short', f'--basetemp={temp}', f'--junitxml={EVIDENCE / "regression.xml"}']
    result = subprocess.run(command, cwd=ROOT, capture_output=True)
    (EVIDENCE / 'regression.stdout.txt').write_bytes(result.stdout)
    (EVIDENCE / 'regression.stderr.txt').write_bytes(result.stderr)
    save('regression-command.json', {'command': command, 'cwd': str(ROOT), 'exit_code': result.returncode})
    print(result.stdout.decode('utf-8', errors='replace'))
    return result.returncode


if __name__ == '__main__':
    if sys.argv[1] == 'prepare':
        prepare()
    elif sys.argv[1] == 'focused':
        raise SystemExit(focused())
    elif sys.argv[1] == 'regression':
        raise SystemExit(regression())
