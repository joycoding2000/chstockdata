"""Read-only reuse of an existing local pure gbbq parser; no package initialization."""
import ast
import hashlib
import json
import struct
import sys
import types
from dataclasses import asdict
from pathlib import Path
from parse_samples import OUT

source = Path('D:/Dev/Projects/easy_tdx/src/easy_tdx/offline/gbbq.py')
source_bytes = source.read_bytes()
tree = ast.parse(source_bytes.decode('utf-8'))
# The only relative import supplies a missing-file exception. Use the builtin
# equivalent, so no client, config, transport or update module is initialized.
tree.body = [n for n in tree.body if not isinstance(n, ast.ImportFrom) or not n.level]
module = types.ModuleType('w5hr3_existing_gbbq_parser')
module.TdxFileNotFoundError = FileNotFoundError
sys.modules[module.__name__] = module
exec(compile(tree, str(source), 'exec'), module.__dict__)
results = []
for root in ('C:/new_hxzq_hc', 'C:/zd_zxzq_gm'):
    p = Path(root) / 'T0002/hq_cache/gbbq'
    b = p.read_bytes()
    count = struct.unpack_from('<I', b)[0]
    row = {'path': str(p), 'bytes': len(b), 'sha256': hashlib.sha256(b).hexdigest(), 'declared_records': count, '29_byte_layout_matches': len(b) == 4 + count * 29}
    assert row['29_byte_layout_matches']
    parsed = module.read_gbbq(p)
    row['decoded_records'] = len(parsed)
    selected = {}
    for code in ('600518', '600519'):
        records = [x for x in parsed if x.code == code]
        selected[code] = {'count': len(records), 'first_date': min(x.datetime for x in records) if records else None, 'last_date': max(x.datetime for x in records) if records else None, 'records': [{k:v for k,v in asdict(x).items() if k != '_raw'} for x in records]}
    row['fixed_securities'] = selected
    results.append(row)
    print(p, count, {k:v['count'] for k,v in selected.items()}, flush=True)
(OUT / 'corporate_action_sample.json').write_text(json.dumps({'parser_source': str(source), 'parser_sha256': hashlib.sha256(source_bytes).hexdigest(), 'execution': 'pure parser via AST, relative exception import replaced; no package init', 'files': results}, ensure_ascii=False, indent=2), encoding='utf-8')
