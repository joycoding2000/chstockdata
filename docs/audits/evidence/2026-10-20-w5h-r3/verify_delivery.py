"""Offline final checks; never re-run source downloads, TQ or GP probes."""
import ast
import hashlib
import importlib.metadata
import io
import json
import re
import struct
import subprocess
import zipfile
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[3]
REPORT = ROOT / 'docs/audits/2026-10-20-w5h-r3-tdx-local-opensource-qualification.md'

def read(name):
    return json.loads((OUT / name).read_text(encoding='utf-8'))

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def git(p, *args):
    result = subprocess.run(['git', '-c', f'safe.directory={p.as_posix()}', '-C', str(p), *args], capture_output=True, encoding='utf-8', errors='replace')
    assert result.returncode == 0, (p, args, result.stderr)
    return result.stdout

def main():
    before = read('before.json')
    repo_checks = {}
    allowed_prefix = 'docs/audits/evidence/2026-10-20-w5h-r3/'
    report_path = REPORT.relative_to(ROOT).as_posix()
    for name, baseline in before['repos'].items():
        p = Path(baseline['path'])
        head = git(p, 'rev-parse', 'HEAD')
        status = git(p, 'status', '--porcelain=v1', '--untracked-files=all')
        changed = [n for n, h in baseline['tracked_sha256'].items() if not (p/n).is_file() or sha(p/n) != h]
        assert not changed, (name, changed)
        assert head == baseline['head']['stdout'], name
        added = sorted(set(status.splitlines()) - set(baseline['status']['stdout'].splitlines()))
        removed = sorted(set(baseline['status']['stdout'].splitlines()) - set(status.splitlines()))
        assert not removed, (name, removed)
        if name == 'chstockdata':
            assert all(x.startswith('?? ') and (x[3:].lstrip('"').startswith(allowed_prefix) or x[3:] == report_path) for x in added), added
        else:
            # Another chat may add consumer research while this read-only audit runs.
            # Preserve and explicitly report such changes; do not claim a static tree.
            assert all(x.startswith('?? ') for x in added), (name, added)
        assert not git(p, 'diff', '--check')
        repo_checks[name] = {'head': head.strip(), 'head_unchanged': True, 'tracked_files_hashed': len(baseline['tracked_sha256']), 'tracked_content_unchanged': True, 'status_lines': len(status.splitlines()), 'new_status_lines': len(added), 'old_status_lines_removed': 0, 'producer_new_paths_within_authorized_scope': True if name == 'chstockdata' else None, 'consumer_parallel_untracked_additions_preserved': added if name != 'chstockdata' else [], 'status': status}

    fixed = read('fixed_2017_qualification.json')
    local = read('local_financial_sample.json')
    original_inputs = []
    for record in read('local_inventory.json')[:3]:
        for sample in record['fixed_daily_samples']:
            p = Path(sample['path'])
            assert sha(p) == sample['sha256'] and p.stat().st_size == sample['bytes']
            original_inputs.append(str(p))
    for sample in read('default_cache_inventory.json')['fixed_samples']:
        p = Path(sample['path'])
        assert sha(p) == sample['sha256'] and p.stat().st_size == sample['bytes']
        original_inputs.append(str(p))
    for sample in read('corporate_action_sample.json')['files']:
        p = Path(sample['path'])
        assert sha(p) == sample['sha256']
        original_inputs.append(str(p))

    duplicate_checks = []
    for p, expected_date in [(OUT/'http_gpcw20171231.response', 20171231), (Path(local['origin_path']), 20260331)]:
        blob = p.read_bytes()
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            assert len(z.infolist()) == 1
            dat = z.read(z.infolist()[0])
        header = struct.unpack_from('<hIHIII', dat)
        assert header[1] == expected_date
        counts = {'600518': 0, '600519': 0}
        for i in range(header[2]):
            code, flag, offset = struct.unpack_from('<6scI', dat, 20+i*11)
            code = code.rstrip(b'\0').decode('ascii')
            if code in counts:
                counts[code] += 1
        assert counts == {'600518': 1, '600519': 1}
        duplicate_checks.append({'report_date': expected_date, 'fixed_security_record_counts': counts, 'zip_crc_verified_again': True})
    assert sha(Path(local['origin_path'])) == local['sha256']
    assert sha(Path(local['existing_dat_path'])) == local['dat_sha256']
    assert sha(OUT/'http_gpcw20171231.response') == fixed['zip_sha256']
    comparison = fixed['600518_comparison']
    assert all(comparison[k]['matches_revision_rounded_float32'] for k in ('FN74', 'FN96', 'FN271'))
    assert comparison['FN107']['matches_original_rounded_float32']
    assert not comparison['FN107']['matches_revision_rounded_float32']
    assert fixed['parse']['fixed_securities']['600518']['fn']['FN314'] == 180426
    assert all(fixed['installed_mootdx_crosscheck'].values())
    assert all(x['report_matches'] and x['all_selected_float32_values_match'] for x in local['installed_mootdx_parser_crosscheck'].values())
    supplement = read('supplement.json')
    assert len(supplement['2026q1_600518_saved_ths_crosscheck']) == 5
    assert all(x['matches_rounded_float32'] for x in supplement['2026q1_600518_saved_ths_crosscheck'])
    assert len(supplement['existing_public_daily_reader_verification']) == 4
    assert all(x['matches_raw_last_record'] for x in supplement['existing_public_daily_reader_verification'])
    assert not any(x['available_version_asof_proven'] for x in fixed['pit'])

    # Remove only bytecode created by these new audit helpers, never original caches.
    cache = OUT / '__pycache__'
    if cache.exists():
        assert cache.resolve().parent == OUT.resolve()
        for p in cache.iterdir():
            assert p.is_file() and p.suffix == '.pyc'
            p.unlink()
        cache.rmdir()
    json_count = 0
    for p in OUT.rglob('*.json'):
        json.loads(p.read_text(encoding='utf-8'))
        json_count += 1
    for p in OUT.glob('*.py'):
        ast.parse(p.read_text(encoding='utf-8'))
    report = REPORT.read_text(encoding='utf-8')
    targets = []
    for target in re.findall(r'\]\(([^)]+)\)', report):
        if target.startswith(('http://', 'https://')):
            continue
        path = REPORT.parent / target.split('#')[0]
        if path.name not in ('final_verification.json', 'manifest.json'):
            assert path.exists(), target
        targets.append(path)
    for key in ('CURRENT_DECISION', 'W5_H_R3_VERDICT', 'LOCAL_VIPDOC_FOUND', 'LOCAL_VIPDOC_PATHS', 'LOCAL_DAILY_DATA_STATUS', 'LOCAL_CW_FINANCIAL_STATUS', 'LOCAL_GPCW_FILES', 'LOCAL_CORPORATE_ACTION_DATA', 'TDX_CLIENT_CAPABILITY', 'TDX_TQ_LOCAL_ACCESS', 'TDX_FINANCIAL_RAW_SAMPLE', 'TDX_FREE_ACCESS_EVIDENCE', 'GITHUB_REFERENCE_PROJECTS', 'REUSABLE_EXISTING_CODE', 'NEW_DEPENDENCY_NEEDED', 'FINANCIAL_FIELD_VERIFICATION', 'FINANCIAL_ORIGINAL_VERSION', 'FINANCIAL_REVISION_VERSION', 'FINANCIAL_ASOF_QUALIFICATION', 'HISTORICAL_PE_QUALIFICATION', 'FULL_UNIVERSE_FEASIBILITY', 'S07_HISTORICAL_GATE', 'RECOMMENDED_SUPPLY_PATH', 'NEXT_MINIMUM_ACTION', 'SCOPE_DEVIATION', 'RUNTIME_CHANGED', 'GIT_COMMIT', 'GIT_PUSH', 'OWNER_REVIEW_REQUIRED'):
        assert re.search(r'^'+key+r' = ', report, re.MULTILINE), key
    result = {'at_utc': datetime.now(timezone.utc).isoformat(), 'status': 'PASS_AUDIT_DELIVERY_CHECKS_ONLY', 's07_gate': 'NOT_PASSED', 'repos': repo_checks, 'original_sample_inputs_unchanged': original_inputs, 'fixed_rows_and_zip_crc': duplicate_checks, '2017_mixed_revision_counterexample_confirmed': True, '2017_fn314_original_announcement_confirmed': True, '2026q1_saved_source_field_checks': 5, 'existing_public_daily_reader_cases': 4, 'json_files_validated_before_final_outputs': json_count, 'report_local_links': len(targets), 'network_requests_in_this_verifier': 0, 'runtime_test_suite_or_release_gate_run': False, 'installed_packages': {n: importlib.metadata.version(n) for n in ('mootdx','tdxpy')}}
    (OUT/'final_verification.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    manifest = {'report': {'path': str(REPORT), 'bytes': REPORT.stat().st_size, 'sha256': sha(REPORT)}, 'files': [{'path': p.relative_to(OUT).as_posix(), 'bytes': p.stat().st_size, 'sha256': sha(p)} for p in sorted(OUT.rglob('*')) if p.is_file() and p.name != 'manifest.json']}
    (OUT/'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    assert all(p.exists() for p in targets)
    assert all(sha(OUT / r['path']) == r['sha256'] for r in manifest['files'])
    print(json.dumps({'status': result['status'], 'heads_unchanged': True, 'tracked_files_unchanged': sum(x['tracked_files_hashed'] for x in repo_checks.values()), 'producer_new_files_only_in_authorized_scope': True, 'consumer_parallel_untracked_additions': {n: len(r['consumer_parallel_untracked_additions_preserved']) for n,r in repo_checks.items() if n != 'chstockdata'}, 'source_sample_checks': len(original_inputs)+2, 'daily_cases': 4, '2026_field_checks': 5, '2017_mixed_version_counterexample': True, 'manifest_files': len(manifest['files']), 's07_gate': 'NOT_PASSED'}, ensure_ascii=False))

if __name__ == '__main__':
    main()
