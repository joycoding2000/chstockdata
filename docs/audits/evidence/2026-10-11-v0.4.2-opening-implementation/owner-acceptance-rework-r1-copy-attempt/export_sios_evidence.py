"""Export the actual tested SIOS source and prove patch reconstruction exactly."""
from datetime import datetime, timezone
import difflib
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

out = Path(__file__).resolve().parent
work = out.parents[1]
source = work / 'systematic-investing-os'
repository = Path('D:/Dev/Projects/systematic-investing-os')
frozen_commit = '84fd54fae0740bc06b1d250afa4578be29556956'
sha = lambda data: hashlib.sha256(data).hexdigest()
read = lambda path: json.loads(path.read_text(encoding='utf-8'))
save = lambda name, value: (out / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
started = datetime.now(timezone.utc).isoformat()
prior_identity = read(work / 'evidence/r21-step4/consumer-identities.json')
expected = prior_identity['final_sios_source_manifest']
assert prior_identity['sios']['frozen_commit'] == frozen_commit
candidate = {name: (source / name).read_bytes() for name in sorted(expected)}
assert {name: sha(data) for name, data in candidate.items()} == expected

def git(*args, input=None):
    return subprocess.check_output(['git', '-c', 'safe.directory=' + repository.as_posix(),
                                    '-C', str(repository), *args], input=input, stderr=subprocess.PIPE)

entries = [entry.split('\t', 1) for entry in git('ls-tree', '-r', '-z', frozen_commit).decode('utf-8').split('\0') if entry]
requests = ('\n'.join(info.split()[2] for info, _ in entries) + '\n').encode('ascii')
batch = git('cat-file', '--batch', input=requests)
offset = 0
baseline = {}
modes = {}
for info, name in entries:
    end = batch.index(b'\n', offset)
    oid, kind, length = batch[offset:end].split()
    length = int(length)
    data = batch[end + 1:end + 1 + length]
    assert kind == b'blob' and oid.decode() == info.split()[2]
    assert hashlib.sha1(b'blob ' + str(length).encode('ascii') + b'\0' + data).hexdigest() == oid.decode()
    assert info.split()[0] in {'100644', '100755'}, name
    baseline[name] = data
    modes[name] = info.split()[0]
    offset = end + 1 + length + 1
assert offset == len(batch)

changed = [name for name in sorted(set(baseline) | set(candidate)) if baseline.get(name) != candidate.get(name)]
parts = []
for name in changed:
    assert not any(char.isspace() for char in name), 'unexpected path requiring patch quoting'
    old = baseline.get(name)
    new = candidate.get(name)
    parts.append(f'diff --git a/{name} b/{name}\n')
    if old is None:
        parts.append('new file mode 100644\n')
    elif new is None:
        parts.append(f'deleted file mode {modes[name]}\n')
    old_lines = old.decode('utf-8').splitlines(keepends=True) if old is not None else []
    new_lines = new.decode('utf-8').splitlines(keepends=True) if new is not None else []
    for line in difflib.unified_diff(old_lines, new_lines,
                                     fromfile='a/' + name if old is not None else '/dev/null',
                                     tofile='b/' + name if new is not None else '/dev/null'):
        parts.append(line if line.endswith('\n') else line + '\n\\ No newline at end of file\n')
patch = out / 'sios-source-vs-frozen.patch'
patch.write_bytes(''.join(parts).encode('utf-8'))
frozen = out / 'sios-frozen-source'
rebuilt = out / 'sios-reconstructed-source-exact'
assert not rebuilt.exists()
for name, data in baseline.items():
    target = frozen / name
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        assert target.read_bytes() == data
    else:
        target.write_bytes(data)
shutil.copytree(frozen, rebuilt)

apply_results = []
for label, extra in (('check', ['--check']), ('apply', [])):
    argv = ['git', '-c', 'safe.directory=' + rebuilt.as_posix(), '-c', 'core.autocrlf=false',
            '-c', 'core.safecrlf=false', 'apply',
            '--whitespace=nowarn', *extra, str(patch)]
    result = subprocess.run(argv, cwd=rebuilt, capture_output=True, text=True, encoding='utf-8', errors='replace')
    (out / ('sios-patch-exact-' + label + '.log')).write_text(result.stdout + result.stderr, encoding='utf-8')
    (out / ('sios-patch-exact-' + label + '.exit')).write_text(str(result.returncode) + '\n', encoding='utf-8')
    record = {'argv': argv, 'cwd': str(rebuilt), 'exit_code': result.returncode, 'patch_sha256': sha(patch.read_bytes())}
    save('sios-patch-exact-' + label + '.command.json', record)
    apply_results.append(record)
    assert result.returncode == 0, 'patch ' + label + ' failed'
reconstructed = {path.relative_to(rebuilt).as_posix(): sha(path.read_bytes())
                 for path in sorted(rebuilt.rglob('*')) if path.is_file()}
assert reconstructed == expected, 'reconstructed source is not the tested candidate'
source_sha = sha(json.dumps(expected, sort_keys=True).encode('utf-8'))
runtime = read(work / 'evidence/r21-step4/sios-offline.json')
runtime_files = runtime['source_files_sha256']
for name, digest in runtime_files.items():
    path = source / name
    if not path.exists():
        path = source / 'src/systematic_investing' / name
    assert sha(path.read_bytes()) == digest, name
assert runtime_files == runtime['source_files_sha256_after']
assert runtime['source_stable_during_run'] and runtime['exit_code'] == 0
qualification = read(work / 'evidence/r21-step4/qualification-source-before.json')
assert all(sha((source / name).read_bytes()) == digest for name, digest in qualification.items())

snapshot = out / 'sios-tested-source.zip'
with zipfile.ZipFile(snapshot, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
    for name, data in candidate.items():
        archive.writestr('systematic-investing-os/' + name, data)
with zipfile.ZipFile(snapshot) as archive:
    assert archive.testzip() is None
    assert all(sha(archive.read('systematic-investing-os/' + name)) == digest for name, digest in expected.items())
manifest = {'identity_kind': 'all tested SIOS source/config/test/docs files; SHA256 manifest, not Git commit',
            'source_directory': str(source), 'frozen_commit': frozen_commit,
            'frozen_tree': git('rev-parse', frozen_commit + '^{tree}').decode('ascii').strip(),
            'source_files_sha256': expected, 'source_manifest_sha256': source_sha,
            'files': len(expected), 'runtime_source_sha256': runtime['source_tree_sha256'],
            'runtime_files': len(runtime_files),
            'non_source_inputs': 'Generated caches and var/ runtime inputs excluded; frozen 6007-file var identity remains separately bound by Step4 evidence'}
save('sios-source-manifest.json', manifest)
save('sios-source-diff-verification.json', {
    'sios_source_diff_complete': True, 'source_was_not_modified': all(sha((source / name).read_bytes()) == digest for name, digest in expected.items()),
    'frozen_files': len(baseline), 'candidate_files': len(expected), 'changed_files': changed,
    'added_files': sorted(set(candidate) - set(baseline)), 'deleted_files': sorted(set(baseline) - set(candidate)),
    'patch': patch.name, 'patch_sha256': sha(patch.read_bytes()),
    'full_source_snapshot': snapshot.name, 'snapshot_sha256': sha(snapshot.read_bytes()),
    'source_manifest_sha256': source_sha, 'runtime_source_sha256': runtime['source_tree_sha256'],
    'previous_actual_step4_manifest_exactly_matches': True,
    'previous_actual_step4_runtime_before_after_exactly_matches': True,
    'qualification_source_matches': True, 'git_apply_check_and_apply_exit_zero': True,
    'reconstructed_manifest_exactly_equals_all_tested_source': True,
    'reconstruction_directory': str(rebuilt), 'current_github_or_repository_head_not_used_as_candidate': True,
    'started_at': started, 'finished_at': datetime.now(timezone.utc).isoformat(), 'exit_code': 0})
save('sios-export.command.json', {'argv': [sys.executable, str(Path(__file__))], 'cwd': str(Path.cwd()),
                                'script_sha256': sha(Path(__file__).read_bytes()), 'exit_code': 0})
print(json.dumps({'source_files': len(expected), 'changed_files': len(changed), 'added_files': len(set(candidate) - set(baseline)),
                  'patch_sha256': sha(patch.read_bytes()), 'sios_source_sha256': source_sha, 'reconstruction': 'BYTE_EXACT_PASS'}))
