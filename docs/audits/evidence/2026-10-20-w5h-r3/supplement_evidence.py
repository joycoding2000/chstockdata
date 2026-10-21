import ast
import hashlib
import importlib.util
import json
import struct
import sys
import types
from pathlib import Path
from inspect_local import summarize
from parse_samples import OUT

root = Path('D:/Dev/Projects/chstockdata-frozen-v042/.rh3a2-vipdoc')
mirror = {'root': str(root), 'directories': [summarize(root / market / 'lday', '*.day') for market in ('sh', 'sz', 'bj')], 'fixed_samples': []}
for code in ('600518', '600519'):
    p = root / 'sh/lday' / f'sh{code}.day'
    b = p.read_bytes()
    mirror['fixed_samples'].append({'path': str(p), 'sha256': hashlib.sha256(b).hexdigest(), 'bytes': len(b), 'first_date': struct.unpack_from('<I', b)[0], 'last_date': struct.unpack_from('<I', b, len(b)-32)[0]})

package = types.ModuleType('chstockdata')
package.__path__ = [str(Path('src/chstockdata').resolve())]
sys.modules['chstockdata'] = package
spec = importlib.util.spec_from_file_location('chstockdata.vipdoc_history', 'src/chstockdata/vipdoc_history.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
daily = []
for base in (Path('C:/zd_zxzq_gm/vipdoc'), Path('.rh3a2-vipdoc').resolve()):
    for code in ('600518', '600519'):
        frame = module.load_vipdoc_daily(code, root=str(base), market='sh')
        p = base / 'sh/lday' / f'sh{code}.day'
        b = p.read_bytes()
        last = struct.unpack_from('<IIIIIfII', b, len(b)-32)
        assert frame.iloc[-1]['Close'] == last[4] / 100
        assert frame.iloc[-1]['Amount'] == last[5]
        assert frame.iloc[-1]['Volume'] == last[6]
        daily.append({'root': str(base), 'code': code, 'rows': len(frame), 'first_date': str(frame.iloc[0]['Date']), 'last_date': str(frame.iloc[-1]['Date']), 'last_close': float(frame.iloc[-1]['Close']), 'last_amount_yuan_float32': float(frame.iloc[-1]['Amount']), 'last_volume_shares': int(frame.iloc[-1]['Volume']), 'matches_raw_last_record': True})

q = json.loads((OUT / 'local_financial_sample.json').read_text(encoding='utf-8'))
fn = q['parse']['fixed_securities']['600518']['fn']
mapping = {'benefit': {'FN74': 'operating_income', 'FN96': 'parent_holder_net_profit'}, 'cash': {'FN107': 'act_cash_flow_net'}, 'debt': {'FN271': 'parent_holder_equity_total', 'FN238': 'equity'}}
current = []
for table, fields in mapping.items():
    p = OUT.parent / '2026-10-20-w5h-r2' / f'ths_600518_{table}.raw'
    obj = json.loads(p.read_bytes())
    record = next(r for r in obj['data']['data'] if r['date'] == '2026-03-31')
    for field, key in fields.items():
        value = record['index_list'][key]['value']
        rounded = struct.unpack('<f', struct.pack('<f', float(value)))[0]
        assert rounded == fn[field]
        current.append({'field': field, 'ths_field': key, 'ths_raw_decimal': value, 'gpcw_float32': fn[field], 'matches_rounded_float32': True, 'source_sha256': hashlib.sha256(p.read_bytes()).hexdigest()})

fields_path = next((OUT / 'upstream/wkingnet__stock-analysis/util_docs').glob('*.txt'))
field_text = fields_path.read_text(encoding='utf-8')
field_lines = [s for s in field_text.splitlines() if s.split('.--')[0] in ('74', '96', '107', '238', '271', '281', '314')]
saved_observation = OUT.parent / '2026-10-19-w5h/web_evidence.json'
disclosures = json.loads(saved_observation.read_text(encoding='utf-8'))['observations'][0]
result = {'mirror_daily': mirror, 'existing_public_daily_reader_verification': daily, '2026q1_600518_saved_ths_crosscheck': current, 'stock_analysis_field_doc_encoding': 'utf-8', 'stock_analysis_field_lines': field_lines, 'prior_corrected_disclosure_observation': disclosures, 'prior_observation_sha256': hashlib.sha256(saved_observation.read_bytes()).hexdigest(), 'default_vipdoc_root_exists': Path('C:/Users/Administrator/.chstockdata/cache/vipdoc').exists()}
(OUT / 'supplement.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'daily_reader_cases': len(daily), 'financial_crosschecks': len(current), 'all_passed': True, 'mirror_files': [x['file_count'] for x in mirror['directories']]}, ensure_ascii=False))
