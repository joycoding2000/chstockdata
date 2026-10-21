import hashlib
import json
import urllib.parse
import urllib.request
from pathlib import Path
from parse_samples import OUT

rows = []
def fetch(url, path):
    row = {'url': url, 'file': path.relative_to(OUT).as_posix()}
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            b = r.read(1_000_001)
        assert len(b) <= 1_000_000
        path.parent.mkdir(exist_ok=True, parents=True)
        path.write_bytes(b)
        row.update(status='SAVED', bytes=len(b), sha256=hashlib.sha256(b).hexdigest())
        return b
    except Exception as e:
        row.update(status='FAILED', error=type(e).__name__)
    finally:
        rows.append(row)

meta = json.loads((OUT / 'upstream_summary.json').read_text(encoding='utf-8'))
repo = 'wkingnet/stock-analysis'
root = OUT / 'upstream/wkingnet__stock-analysis'
tree = json.loads((root / 'tree.json').read_text(encoding='utf-8'))
path = next(x['path'] for x in tree['tree'] if x['path'].startswith('util_docs/') and x['path'].endswith('.txt'))
fetch(f'https://raw.githubusercontent.com/{repo}/{meta[repo]["sha"]}/' + urllib.parse.quote(path), root / path)
repo = 'rainx/pytdx'
sha = meta[repo]['source_master_sha']
root = OUT / 'upstream/rainx__pytdx'
b = fetch(f'https://api.github.com/repos/{repo}/git/trees/{sha}?recursive=1', root / 'master-tree.json')
if b:
    names = [x['path'] for x in json.loads(b)['tree'] if x['type'] == 'blob' and '/' not in x['path'] and ('license' in x['path'].lower() or 'copying' in x['path'].lower())]
    for name in names:
        fetch(f'https://raw.githubusercontent.com/{repo}/{sha}/{name}', root / name)
    print('pytdx license files', names)
(OUT / 'github_requests_final.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')
