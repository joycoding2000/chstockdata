from pathlib import Path
import hashlib
import json
out = Path(__file__).resolve().parent
dest = Path('D:/Dev/Projects/chstockdata/docs/audits/evidence/2026-10-11-v0.4.2-opening-implementation/owner-acceptance-rework-r1')
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
expected = {}
for line in (out/'SHA256SUMS').read_text(encoding='utf-8').splitlines():
    digest, name = line.split('  ', 1)
    expected[name] = digest
expected['SHA256SUMS'] = sha(out/'SHA256SUMS')
actual = {p.relative_to(dest).as_posix(): sha(p) for p in dest.rglob('*') if p.is_file()}
result = dict(expected_files=len(expected), actual_files=len(actual),
              extra=sorted(actual.keys()-expected.keys()), missing=sorted(expected.keys()-actual.keys()),
              different=[name for name in expected.keys() & actual.keys() if expected[name] != actual[name]])
(out/'delivery-copy-initial-check.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
print(json.dumps({key: value[:20] if isinstance(value, list) else value for key, value in result.items()}))
