import hashlib
import json
from pathlib import Path
from bs4 import BeautifulSoup
from qualify_fixed import ORIGINAL, REVISION, OUT

checks = {}
for name in ('original_2017.html', 'correction_2019.html'):
    p = OUT.parent / '2026-10-19-w5h' / name
    b = p.read_bytes()
    soup = BeautifulSoup(b, 'html.parser', from_encoding='gb18030')
    text = ' '.join(soup.stripped_strings)
    compact = text.replace(',', '').replace(' ', '')
    checks[name] = {'sha256': hashlib.sha256(b).hexdigest(), 'values_present': {**{f'original_{k}': v in compact for k, v in ORIGINAL.items()}, **{f'revision_{k}': v in compact for k, v in REVISION.items()}}}

comparison = {}
fn = json.loads((OUT / 'local_financial_sample.json').read_text(encoding='utf-8'))['parse']['fixed_securities']['600518']['fn']
mapping = {'benefit': {'FN74': 'operating_income', 'FN96': 'parent_net_profit'}, 'cash': {'FN107': 'net_operate_cash_flow'}, 'debt': {'FN271': 'parent_equity', 'FN238': 'share_capital'}}
for table, fields in mapping.items():
    p = OUT.parent / '2026-10-20-w5h-r2' / f'ths_600518_{table}.raw'
    obj = json.loads(p.read_bytes())
    row = next(r for r in obj['data']['data'] if r['date'] == '2026-03-31')
    # Preserve actual key candidates for explicit mapping review rather than guessing a missing key.
    candidates = {k:v for k,v in row['index_list'].items() if any(x in k for x in ('income', 'parent', 'operat', 'share_capital', 'equity'))}
    comparison[table] = {'source_sha256': hashlib.sha256(p.read_bytes()).hexdigest(), 'date': row['date'], 'candidates': candidates}

(OUT / 'disclosure_anchor_checks.json').write_text(json.dumps({'saved_disclosures': checks, '2026q1_saved_ths_candidates': comparison}, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(checks, ensure_ascii=False))
print(json.dumps({t:{k:v['value'] for k,v in r['candidates'].items()} for t,r in comparison.items()},ensure_ascii=False))
