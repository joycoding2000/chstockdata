"""Read-only diagnostic harness; run only the two authorized existing tests.

The child process records subprocess.run inputs/results without altering them.
No product/test/config file is changed. Fixture-created Git repositories are
created by the original tests, including their original local config writes.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

EVIDENCE = Path(__file__).resolve().parent
ROOT = EVIDENCE.parents[3]
SETUP = json.loads((EVIDENCE / 'setup.json').read_text(encoding='utf-8'))


def write_json(name, data):
    (EVIDENCE / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def observe(label):
    import pytest

    repo = Path(SETUP['baseline_dir']) if label == 'baseline' else ROOT
    temp = Path(SETUP['work_dir']) / f'{label}-pytest-temp'
    assert not temp.exists(), 'refusing to reuse pytest basetemp'
    os.chdir(repo)
    sys.path.insert(0, str(repo / 'src'))
    calls = []
    original_run = subprocess.run

    def recorded_run(*args, **kwargs):
        command = args[0] if args else kwargs.get('args')
        is_git = isinstance(command, (list, tuple)) and Path(str(command[0])).stem.lower() == 'git'
        try:
            result = original_run(*args, **kwargs)
        except subprocess.CalledProcessError as exc:
            if is_git:
                calls.append({'command': list(command), 'cwd': str(kwargs.get('cwd', Path.cwd())),
                              'exit_code': exc.returncode, 'stdout': decoded(exc.stdout),
                              'stderr': decoded(exc.stderr)})
            raise
        if is_git:
            calls.append({'command': list(command), 'cwd': str(kwargs.get('cwd', Path.cwd())),
                          'exit_code': result.returncode, 'stdout': decoded(result.stdout),
                          'stderr': decoded(result.stderr)})
        return result

    subprocess.run = recorded_run
    arguments = [
        'tests/test_rh1_git_line_endings.py::test_crlf_preserves_added_line_discrimination[False]',
        'tests/test_rh1_git_line_endings.py::test_crlf_preserves_added_line_discrimination[True]',
        '-vv', '--tb=short', '-p', 'no:cacheprovider', f'--basetemp={temp}',
        f'--junitxml={EVIDENCE / (label + ".xml")}',
    ]
    try:
        exit_code = int(pytest.main(arguments))
    finally:
        subprocess.run = original_run
        write_json(label + '-git-calls.json', calls)
    package = sys.modules.get('chstockdata')
    write_json(label + '-environment.json', {
        'python_executable': sys.executable, 'python_version': sys.version,
        'pytest_version': pytest.__version__, 'git_executable': shutil.which('git'),
        'cwd': str(repo), 'pytest_args': arguments, 'pytest_exit_code': exit_code,
        'loaded_package_file': getattr(package, '__file__', None),
        'git_environment': {name: os.environ.get(name) for name in (
            'GIT_DIR', 'GIT_WORK_TREE', 'GIT_COMMON_DIR', 'GIT_CEILING_DIRECTORIES',
            'GIT_CONFIG_COUNT', 'GIT_CONFIG_NOSYSTEM', 'GIT_CONFIG_GLOBAL', 'GIT_CONFIG_SYSTEM')},
        'git_config_parameters_present': 'GIT_CONFIG_PARAMETERS' in os.environ,
    })
    return exit_code


def decoded(value):
    return value.decode('utf-8', errors='replace') if isinstance(value, bytes) else value


def main():
    if len(sys.argv) == 3 and sys.argv[1] == '--observe':
        return observe(sys.argv[2])
    results = {}
    for label in ('candidate', 'baseline'):
        command = [sys.executable, str(Path(__file__).resolve()), '--observe', label]
        result = subprocess.run(command, capture_output=True)
        (EVIDENCE / (label + '.stdout.txt')).write_bytes(result.stdout)
        (EVIDENCE / (label + '.stderr.txt')).write_bytes(result.stderr)
        results[label] = {'command': command, 'exit_code': result.returncode}
    write_json('runs.json', results)
    print(json.dumps(results, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
