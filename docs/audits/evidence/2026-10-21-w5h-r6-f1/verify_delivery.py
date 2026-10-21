"""Read-only verification of archived inputs and the bounded F1 deliverable."""
import ast
import hashlib
import json
import re
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[3]
REPORT = ROOT/'docs/audits/2026-10-21-w5h-r6-f1-parser-correction.md'


def read(name):
    return json.loads((OUT/name).read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(*args):
    return subprocess.run(['git', *args], cwd=ROOT, capture_output=True,
                          text=True, encoding='utf-8', check=True).stdout


def main():
    before = read('before.json')
    tracked_changes = [p for p, h in before['tracked_sha256'].items() if sha(ROOT/p) != h]
    frozen_changes = [p for p, h in read('freeze.json').items() if sha(OUT/p) != h]
    context_changes = [x['path'] for x in read('context_recovery.json') if sha(ROOT/x['path']) != x['sha256']]
    source_checks = [{'id': d['id'], 'matches': sha(ROOT/d['path']) == d['sha256']}
                     for d in read('dataset.json')['documents']]
    parsed = read('parsed.json')
    values = read('value_validation.json')
    replay = read('replay_validation.json')
    quality = read('quality_checks.json')
    statuses = git('status', '--porcelain=v1', '-z').split('\0')
    added_statuses = [s for s in statuses if s and s not in before['status']]
    prefix = '?? docs/audits/evidence/2026-10-21-w5h-r6-f1/'
    report_status = '?? docs/audits/2026-10-21-w5h-r6-f1-parser-correction.md'
    outside = [s for s in added_statuses if not s.startswith(prefix) and s != report_status]
    removed_original_statuses = [s for s in before['status'] if s not in statuses]
    script_ast = []
    for path in sorted(OUT.glob('*.py')):
        ast.parse(path.read_text(encoding='utf-8'), filename=path.name)
        script_ast.append(path.name)
    broken_links = []
    for target in re.findall(r'\]\(([^)]+)\)', REPORT.read_text(encoding='utf-8')):
        if '://' not in target and not (REPORT.parent/target).exists():
            broken_links.append(target)
    strict = [r for r in replay['results'] if r['actual']['mode'] == 'strict_saved_catalog']
    known = [r for r in replay['results'] if r['actual']['mode'] == 'known_ledger_only']
    checks = {
        'head_unchanged': git('rev-parse', 'HEAD').strip() == before['head'],
        'branch_main': git('branch', '--show-current').strip() == 'main',
        'all_archived_tracked_bytes_unchanged': not tracked_changes,
        'frozen_fixture_bytes_unchanged': not frozen_changes,
        'authority_context_bytes_unchanged': not context_changes,
        'source_PDFs_match': all(c['matches'] for c in source_checks),
        'parser_sha_stable_during_final_run': parsed['parser_sha256_at_start'] ==
            parsed['parser_sha256_at_end'] == sha(OUT/'parser_f1.py'),
        'whole_batch_values': values['denominator'] == 89 and
            values['counts'] == {'PASS': 87, 'UNKNOWN': 2} and
            all(c['result'] == 'PASS' for c in values['cases'] if c['program_accepted_before_truth']),
        'replay_values_sources_and_statuses': replay['field_output_denominator'] == 46 and
            replay['assertion_pass'] == 46,
        'strict_and_diagnostic_denominators': len(strict) == 39 and len(known) == 7,
        'actual_output_quality': quality['pass'] and len(quality['checks']) == 91,
        'no_staged_or_tracked_diff': not git('diff', '--name-only').strip() and
                                   not git('diff', '--cached', '--name-only').strip(),
        'only_authorized_additions': not outside and not removed_original_statuses,
        'report_links_exist': not broken_links,
    }
    result = {'verified_at_utc': datetime.now(timezone.utc).isoformat(),
              'status': 'PASS_DELIVERY_NOT_S07_GATE' if all(checks.values()) else 'FAIL',
              'head': git('rev-parse', 'HEAD').strip(), 'protected_tracked_files': len(before['tracked_sha256']),
              'checks': checks, 'tracked_changes': tracked_changes, 'frozen_changes': frozen_changes,
              'context_changes': context_changes, 'source_checks': source_checks,
              'outside_scope_statuses': outside, 'removed_original_statuses': removed_original_statuses,
              'broken_links': broken_links, 'syntax_checked_scripts': script_ast,
              'strict_output_counts': dict(Counter(r['actual']['status'] for r in strict)),
              'staged_files': git('diff', '--cached', '--name-only').splitlines(),
              'git_commit': 'NO', 'git_push': 'NO', 'S07_gate': 'NOT_PASSED'}
    (OUT/'final_verification.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=True))
    if not all(checks.values()):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
