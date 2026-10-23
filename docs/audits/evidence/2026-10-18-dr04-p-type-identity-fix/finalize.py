"""Verify this patch's scope and reconcile the original 134 cases with the 142."""
from pathlib import Path
import ast
import collections
import difflib
import hashlib
import json
import re
import subprocess
import xml.etree.ElementTree as ET

evidence = Path(__file__).resolve().parent
root = evidence.parents[3]
before = json.loads((evidence / 'before.json').read_text(encoding='utf-8'))
head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
assert head == before['head']
assert not subprocess.check_output(['git', 'diff', '--cached', '--name-only'], cwd=root)
assert subprocess.check_output(['git', 'diff'], cwd=root) == (evidence / 'tracked-before.diff').read_bytes()
protected = {name: hashlib.sha256(Path(name).read_bytes()).hexdigest() == sha
             for name, sha in before['protected_sha256'].items()}
assert all(protected.values())
original_module = (evidence / 'module-before.txt').read_text(encoding='utf-8')
current_module = (root / 'src/chstockdata/daily_fund_flow.py').read_text(encoding='utf-8')
original_tests = (evidence / 'tests-before.txt').read_text(encoding='utf-8')
current_tests = (root / 'tests/test_daily_fund_flow.py').read_text(encoding='utf-8')
assert current_tests.startswith(original_tests), 'existing tests were changed'
old_tree, new_tree = ast.parse(original_module), ast.parse(current_module)
def retained(tree):
    return [ast.dump(n) for n in tree.body if not isinstance(n, ast.FunctionDef)
            or n.name not in {'get_sina_daily_fund_flow', '_raw_identity'}]
assert retained(old_tree) == retained(new_tree)
old_get = next(n for n in old_tree.body if isinstance(n, ast.FunctionDef) and n.name == 'get_sina_daily_fund_flow')
new_get = next(n for n in new_tree.body if isinstance(n, ast.FunctionDef) and n.name == 'get_sina_daily_fund_flow')
assert ast.dump(old_get.args) == ast.dump(new_get.args)
def fetch(tree):
    return next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'fetch')
assert ast.dump(fetch(old_get)) == ast.dump(fetch(new_get)), 'HTTP/budget logic changed'
for old, new, name in [(original_module, current_module, 'module'), (original_tests, current_tests, 'tests')]:
    patch = ''.join(difflib.unified_diff(old.splitlines(keepends=True), new.splitlines(keepends=True),
                                       fromfile=f'before/{name}.py', tofile=f'after/{name}.py'))
    (evidence / (name + '.diff')).write_text(patch, encoding='utf-8')
cases = ET.parse(evidence / 'full.xml').findall('.//testcase')
assert len(cases) == 142
assert all(c.find('failure') is None and c.find('error') is None and c.find('skipped') is None for c in cases)
key = lambda c: (c.attrib['classname'], c.attrib['name'])
original = ET.parse(evidence.parent / '2026-10-18-dr04-p-regression-fix-r2/regression.xml').findall('.//testcase')
assert len(original) == 134 and {key(c) for c in original} <= {key(c) for c in cases}
focused = ET.parse(evidence / 'focused.xml').findall('.//testcase')
red = ET.parse(evidence / 'red.xml').findall('.//testcase')
assert len(focused) == 8 and all(c.find('failure') is None and c.find('error') is None for c in focused)
assert sum(c.find('failure') is not None for c in red) == 6
groups = collections.Counter()
for case in cases:
    match = re.match(r'test_(P\d\d)', case.attrib['name'])
    if match:
        groups[match[1]] += 1
assert len(groups) == 12 and sum(groups.values()) == 41
summary = {'head': head, 'red_failed': 6, 'red_positive_controls_passed': 2,
           'new_regressions_passed': 8, 'original_regressions_passed': 134,
           'combined_passed': 142, 'failures': 0, 'errors': 0, 'skipped': 0,
           'P01_P12': dict(sorted(groups.items())), 'original_module_cases_passed': 45,
           'protected_sha256_unchanged': protected, 'existing_tests_unchanged': True,
           'HTTP_and_budget_AST_unchanged': True, 'public_signature_and_raw_format_unchanged': True,
           'prior_tracked_diff_unchanged': True, 'staging_empty': True,
           'current_sha256': {name: hashlib.sha256((root / name).read_bytes()).hexdigest()
                              for name in ['src/chstockdata/daily_fund_flow.py', 'tests/test_daily_fund_flow.py']},
           'verdict': 'PASS_CANDIDATE', 'owner_acceptance': 'NOT_GRANTED'}
(evidence / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({k: summary[k] for k in ['head', 'new_regressions_passed', 'original_regressions_passed',
                                       'combined_passed', 'P01_P12', 'verdict']}, indent=2))
