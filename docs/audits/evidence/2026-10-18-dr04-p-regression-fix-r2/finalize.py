"""Record final acceptance evidence and verify the authorized change boundary."""
from pathlib import Path
import collections
import hashlib
import json
import re
import subprocess
import xml.etree.ElementTree as ET

evidence = Path(__file__).resolve().parent
root = evidence.parents[3]
before = json.loads((evidence / 'before.json').read_text(encoding='utf-8'))
protected = {name: hashlib.sha256(Path(name).read_bytes()).hexdigest() == sha
             for name, sha in before['protected_hashes'].items()}
assert all(protected.values())
head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
assert head == before['head']
assert not subprocess.check_output(['git', 'diff', '--cached', '--name-only'], cwd=root)
prior_diff = subprocess.check_output(['git', 'diff', '--', 'README.md', 'src/chstockdata/__init__.py'], cwd=root)
assert prior_diff == (evidence / 'before.diff').read_bytes()
names = subprocess.check_output(['git', 'diff', '--name-only'], cwd=root, text=True).splitlines()
assert set(names) == {'README.md', 'src/chstockdata/__init__.py', 'tests/test_rh1_git_line_endings.py'}
check = subprocess.run(['git', '-c', 'core.whitespace=cr-at-eol', 'diff', '--check', '--',
                        'tests/test_rh1_git_line_endings.py'], cwd=root, capture_output=True)
assert check.returncode == 0, check.stderr
diff = subprocess.check_output(['git', 'diff', '--', 'tests/test_rh1_git_line_endings.py'], cwd=root)
(evidence / 'test-fix.diff').write_bytes(diff)
focused = json.loads((evidence / 'assertion-execution.json').read_text(encoding='utf-8'))
assert focused['pytest_exit_code'] == 0 and focused['all_three_assertions_reached_per_case']
cases = ET.parse(evidence / 'regression.xml').findall('.//testcase')
assert len(cases) == 134
assert all(c.find('failure') is None and c.find('error') is None and c.find('skipped') is None for c in cases)
groups = collections.Counter()
for case in cases:
    match = re.match(r'test_(P\d\d)', case.attrib['name'])
    if match:
        groups[match[1]] += 1
assert len(groups) == 12
summary = {
    'head': head, 'root_cause_fixed': True, 'focused_passed': 2,
    'original_assertions_ast_unchanged': True, 'assertions_reached_per_case': 3,
    'P01_P12': dict(sorted(groups.items())), 'contract_instances_passed': sum(groups.values()),
    'daily_fund_flow_module_passed': sum('test_daily_fund_flow' in c.attrib['classname'] for c in cases),
    'combined_regression_passed': len(cases), 'failed': 0, 'errors': 0, 'skipped': 0,
    'protected_product_gate_contract_and_config_hashes': protected,
    'prior_tracked_diff_unchanged': True, 'staging_empty': True,
    'test_patch_sha256': hashlib.sha256((root / 'tests/test_rh1_git_line_endings.py').read_bytes()).hexdigest(),
    'diff_check_exit_code': check.returncode, 'verdict': 'PASS_CANDIDATE',
    'owner_acceptance_ready': True, 'owner_acceptance': 'NOT_GRANTED',
}
(evidence / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({k: summary[k] for k in ('head', 'focused_passed', 'P01_P12',
    'daily_fund_flow_module_passed', 'combined_regression_passed', 'verdict')}, indent=2))
