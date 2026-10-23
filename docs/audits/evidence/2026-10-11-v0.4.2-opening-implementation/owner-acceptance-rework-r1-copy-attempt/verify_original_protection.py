"""Preservation check for originals and prior Owner evidence; writes only here."""
from pathlib import Path
import hashlib
import json
import subprocess
import zipfile

OUT = Path(__file__).resolve().parent
WORK = OUT.parents[1]
ROOT = Path('D:/Dev/Projects/chstockdata')
SIOS = Path('D:/Dev/Projects/systematic-investing-os')
TA = Path('D:/Dev/Projects/TradingAgents-AStock-Private')
read = lambda path: json.loads(path.read_text(encoding='utf-8'))
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
def git(repo, *args):
    return subprocess.check_output(['git', '-c', f'safe.directory={repo.as_posix()}', '-C', str(repo), *args], stderr=subprocess.PIPE).decode('utf-8').strip()
def differences(repo, files):
    return [name for name, digest in files.items() if not (repo/name).is_file() or sha(repo/name) != digest]
base = read(WORK/'baseline.json')
cr = 'docs/releases/v0.4.2/change-requests/CR-historical-opening-execution.md'
assert differences(ROOT, base['chstockdata_before']) == [cr]
assert git(ROOT, 'rev-parse', 'HEAD') == base['chstockdata_head']
sios_changes = differences(SIOS, base['sios_before'])
assert sios_changes == ['docs/m1-r2/R2-product-assumption-and-universe-decision.md'], sios_changes
assert git(SIOS, 'rev-parse', 'HEAD') == base['sios_current_head']
sios_status = git(SIOS, 'status', '--porcelain', '--untracked-files=all')
with zipfile.ZipFile(WORK/'chstockdata-before.zip') as archive:
    assert (ROOT/cr).read_bytes().startswith(archive.read(cr))
original_wheel = ROOT/'dist/v042-unified/chstockdata-0.4.2-py3-none-any.whl'
assert sha(original_wheel) == base['old_wheel_sha256']
ta = read(WORK/'ta-step4-protection-before.json')
assert not differences(TA, ta['files'])
assert git(TA, 'rev-parse', 'HEAD') == ta['head']
assert git(TA, 'status', '--porcelain', '--untracked-files=all') == ta['status'].strip()
old = read(WORK/'evidence/r21-step4/source-only-identity.json')
assert not differences(WORK/'chstockdata', old['working_tree_files'])
old_zip = ROOT/'docs/audits/evidence/2026-10-11-v0.4.2-opening-implementation/r21-step4-evidence.zip'
assert sha(old_zip) == 'a94de2c4ce72a4e98ffad9b0fa2dfdb93833623832078dcb5d2373b23d7e8b8d'
assert sha(WORK/'dist/r21-qualified/chstockdata-0.4.2-py3-none-any.whl') == '3fd4f0b7334e310851495b8b13d4c7c55d21cde719acf9e00ff880ccb822f42e'
report = dict(exit_code=0, original_chstockdata_head=base['chstockdata_head'],
              original_chstockdata_files_checked=len(base['chstockdata_before']),
              original_chstockdata_baseline_differences=[cr], original_cr_prefix_preserved=True,
              original_sios_head=base['sios_current_head'], original_sios_files_checked=len(base['sios_before']),
              original_sios_baseline_differences=sios_changes,
              original_sios_current_status=sios_status,
              original_sios_baseline_status=base['sios_status_before'],
              original_sios_product_source_unchanged=True,
              original_sios_changed_doc_sha256={name: sha(SIOS/name) for name in sios_changes},
              original_sios_preservation_note='Two concurrent document changes versus early baseline are retained; this REWORK issued no original SIOS writes. Isolated tested source is independently unchanged.',
              original_ta_head=ta['head'], original_ta_files_checked=len(ta['files']),
              original_ta_source_and_working_tree_status_unchanged=True,
              old_isolated_source_files_unchanged=len(old['working_tree_files']),
              original_wheel_sha256=sha(original_wheel),
              previous_candidate_wheel_sha256='3fd4f0b7334e310851495b8b13d4c7c55d21cde719acf9e00ff880ccb822f42e',
              previous_step4_zip_sha256=sha(old_zip),
              claim='Existing user source changes, old candidate and old acceptance ZIP preserved; concurrent original SIOS documents explicitly recorded.')
(OUT/'original-protection-final.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
print(json.dumps(report))
