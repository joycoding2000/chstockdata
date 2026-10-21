import hashlib
import json
import struct
from pathlib import Path
from inspect_local import summarize, details
from parse_samples import OUT

root = Path('C:/Users/Administrator/.chstockdata/cache/vipdoc')
result = {'root': str(root), 'discovery_basis': 'actual config._DEFAULT_CACHE_DIR + vipdoc_history_dir fallback; targeted follow-up after bounded drive scan', 'directories': [summarize(root / m / t) for m in ('sh', 'sz', 'bj') for t in ('lday', 'minline')], 'cw': summarize(root / 'cw'), 'fixed_samples': []}
for market, code in [('sh', '600518'), ('sh', '600519'), ('sh', '000001'), ('sz', '000001')]:
    p = root / market / 'lday' / f'{market}{code}.day'
    b = p.read_bytes()
    result['fixed_samples'].append({**details(p), 'sha256': hashlib.sha256(b).hexdigest(), 'records': len(b)//32, 'first_date': struct.unpack_from('<I', b)[0], 'last_date': struct.unpack_from('<I', b, len(b)-32)[0]})
manifest_paths = [root / 'manifest.json', Path('.rh3a2-vipdoc/manifest.json')]
result['manifests'] = []
for p in manifest_paths:
    b = p.read_bytes()
    data = json.loads(b)
    result['manifests'].append({'path': str(p.resolve()), 'sha256': hashlib.sha256(b).hexdigest(), 'metadata': {k:v for k,v in data.items() if k not in ('max_bar_date', 'record_counts')}, 'record_counts': data.get('record_counts')})
(OUT / 'default_cache_inventory.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'root': str(root), 'counts': [(x['path'],x.get('file_count')) for x in result['directories']], 'fixed': [(x['path'],x['first_date'],x['last_date']) for x in result['fixed_samples']], 'cw': result['cw']}, ensure_ascii=True))
