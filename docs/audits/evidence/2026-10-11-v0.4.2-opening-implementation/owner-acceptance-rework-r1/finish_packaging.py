"""Resume delivery with exact file copying; retain initial alias-expanded copy."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import zipfile

OUT = Path(__file__).resolve().parent
ROOT = Path('D:/Dev/Projects/chstockdata')
DELIVERY_ROOT = ROOT/'docs/audits/evidence/2026-10-11-v0.4.2-opening-implementation'
DEST = DELIVERY_ROOT/'owner-acceptance-rework-r1'
FAILED = DELIVERY_ROOT/'owner-acceptance-rework-r1-copy-attempt'
ZIP = DELIVERY_ROOT/'owner-acceptance-rework-r1-evidence.zip'
AUDIT = ROOT/'docs/audits/2026-10-11-v0.4.2-opening-implementation.md'
sha = lambda data: hashlib.sha256(data).hexdigest()
read = lambda p: json.loads(p.read_text(encoding='utf-8'))
initial = read(OUT/'delivery-copy-initial-check.json')
assert initial['missing'] == initial['different'] == []
assert initial['expected_files'] == 3096 and initial['actual_files'] == 4372
assert all('current/' in name for name in initial['extra'])
assert (OUT/'owner-review-status.ini').is_file()
assert not ZIP.exists() and not FAILED.exists()
assert DEST.resolve().parent == DELIVERY_ROOT.resolve()
assert FAILED.resolve().parent == DELIVERY_ROOT.resolve()
assert DELIVERY_ROOT.resolve().is_relative_to(ROOT.resolve())
assert DEST.is_dir()
DEST.rename(FAILED)
note = '\n交付工具留证：首次 copytree 展开 pytest 临时目录 current 别名，多出1276份重复文件；原3096文件无缺失且全部 SHA一致，检查失败并保留首次副本 owner-acceptance-rework-r1-copy-attempt。最终按清单逐文件导出唯一文件集合，ZIP全部成员/CRC/SHA逐项校验；没有改变源码、测试结果或Gate结论。\n'
text = AUDIT.read_text(encoding='utf-8')
assert '### Owner REWORK r1 final candidate and evidence closeout — 2026-10-13' in text
assert '交付工具留证：首次 copytree' not in text
AUDIT.write_text(text+note, encoding='utf-8')
shutil.copyfile(AUDIT, OUT/'implementation-audit-final.md')
record = dict(exit=1, cause='shutil.copytree follows pytest current directory aliases',
              unique_original_files=3096, extra_duplicate_alias_files=1276,
              missing_files=0, mismatched_files=0, preserved_initial_copy=str(FAILED),
              remedy='Export exact unique inventory paths, without expanding directory aliases.',
              product_source_and_test_results_modified=False)
(OUT/'delivery-initial-attempt.json').write_text(json.dumps(record, indent=2)+'\n', encoding='utf-8')
inventory = {p.relative_to(OUT).as_posix(): sha(p.read_bytes()) for p in sorted(OUT.rglob('*'))
             if p.is_file() and p.relative_to(OUT).as_posix() != 'SHA256SUMS'}
(OUT/'SHA256SUMS').write_text(''.join(f'{digest}  {name}\n' for name, digest in inventory.items()), encoding='utf-8')
inventory['SHA256SUMS'] = sha((OUT/'SHA256SUMS').read_bytes())
DEST.mkdir()
for name, digest in inventory.items():
    source, target = OUT/name, DEST/name
    assert target.resolve().is_relative_to(DEST.resolve())
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    assert sha(target.read_bytes()) == digest
actual = {p.relative_to(DEST).as_posix(): sha(p.read_bytes()) for p in DEST.rglob('*') if p.is_file()}
assert actual == inventory
with zipfile.ZipFile(ZIP, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
    for name in sorted(inventory):
        archive.write(DEST/name, DEST.name+'/'+name)
with zipfile.ZipFile(ZIP) as archive:
    assert archive.testzip() is None
    assert sorted(archive.namelist()) == sorted(DEST.name+'/'+name for name in inventory)
    assert all(sha(archive.read(DEST.name+'/'+name)) == digest for name, digest in inventory.items())
zip_sha = sha(ZIP.read_bytes())
ZIP.with_name(ZIP.name+'.sha256').write_text(f'{zip_sha}  {ZIP.name}\n', encoding='utf-8')
head = subprocess.check_output(['git', '-c', f'safe.directory={ROOT.as_posix()}', '-C', str(ROOT), 'rev-parse', 'HEAD'], stderr=subprocess.PIPE).decode('utf-8').strip()
assert head == '42bd44ef4d695aa3e88cfab4ebc3417660d0437a'
handoff = read(OUT/'owner-rework-final-handoff.json')
receipt = dict(zip_path=str(ZIP), zip_sha256=zip_sha, zip_bytes=ZIP.stat().st_size,
               files=len(inventory), crc_and_every_member_sha_verified=True,
               copied_evidence_equal_origin=True, audit_path=str(AUDIT),
               source_sha256=handoff['candidate_source_sha256'], wheel_sha256=handoff['candidate_wheel_sha256'],
               source_snapshot_files=765, sios_snapshot_files=256,
               gate_verdict='PASS_CANDIDATE', flags=handoff['flags'], commit_sha=head,
               no_new_commit=True, scope_expansion='NO', owner_acceptance='PENDING',
               next_phase_authorized='NO', initial_copy_attempt_retained=str(FAILED),
               created_at_utc=datetime.now(timezone.utc).isoformat())
(DELIVERY_ROOT/'owner-acceptance-rework-r1-delivery-receipt.json').write_text(json.dumps(receipt, indent=2)+'\n', encoding='utf-8')
print(json.dumps(receipt))
