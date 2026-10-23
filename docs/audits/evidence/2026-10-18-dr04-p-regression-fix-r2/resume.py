"""Prepare missing evidence temp parent; preserve the previous attempt's logs."""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess

evidence = Path(__file__).resolve().parent
root = evidence.parents[3]
previous = evidence.with_name('2026-10-18-dr04-p-regression-fix')
before = json.loads((previous / 'before.json').read_text(encoding='utf-8'))
assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip() == before['head']
assert all(hashlib.sha256(Path(name).read_bytes()).hexdigest() == sha
           for name, sha in before['protected_hashes'].items())
temp_root = Path(before['temp_root']).resolve()
assert temp_root.is_relative_to((root / '.pytest_cache').resolve())
assert not (temp_root / 'focused').exists()
assert not (temp_root / 'regression').exists()
temp_root.mkdir(parents=True, exist_ok=True)
for name in ('verify.py', 'before.json', 'before.diff', 'before-test.py.txt'):
    destination = evidence / name
    assert not destination.exists()
    shutil.copyfile(previous / name, destination)
print('Prepared evidence temp parent; prior logs and all protected files preserved.')
