"""One installed mootdx GP endpoint, one fixed report; no retries or config setup."""
import ast
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from tdxpy.hq import TdxHq_API

OUT = Path(__file__).resolve().parent
SITE = Path('C:/Users/Administrator/AppData/Local/Programs/Python/Python314/Lib/site-packages')
tree = ast.parse((SITE / 'mootdx/consts.py').read_text(encoding='utf-8'))
hosts = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'GP_HOSTS' for t in n.targets))
_, host, port = hosts[0]
ledger = {'started_at_utc': datetime.now(timezone.utc).isoformat(), 'endpoint_source': 'installed mootdx 0.11.7 consts.GP_HOSTS[0]', 'host': host, 'port': port, 'max_connections': 1, 'auto_retry': False, 'heartbeat': False, 'client_setup': False, 'max_total_seconds': 45, 'max_protocol_calls': 128, 'max_bytes': 6_000_000, 'calls': []}
api = TdxHq_API(auto_retry=False, heartbeat=False, raise_exception=True)
api.need_setup = False
started = time.monotonic()

def get_file(name, expected=None, limit=6_000_000):
    body = bytearray()
    while len(ledger['calls']) < 128 and time.monotonic() - started < 45:
        t = datetime.now(timezone.utc).isoformat()
        result = api.get_report_file(name, len(body))
        if not isinstance(result, dict) or 'chunksize' not in result:
            raise ValueError('invalid_protocol_response')
        chunk = result.get('chunkdata', b'')
        size = result['chunksize']
        ledger['calls'].append({'file': name, 'offset': len(body), 'chunk_size': size, 'at_utc': t})
        if size != len(chunk) or size < 0:
            raise ValueError('chunk_size_mismatch')
        if size == 0:
            return bytes(body)
        body.extend(chunk)
        if len(body) > limit:
            raise ValueError('body_limit')
        if expected is not None and len(body) >= expected:
            return bytes(body)
        time.sleep(0.05)
    raise ValueError('global_budget_exhausted')

try:
    if not api.connect(host, port, time_out=3):
        raise ConnectionError('connect_returned_false')
    ledger['connection'] = 'CONNECTED'
    catalog = get_file('tdxfin/gpcw.txt', limit=100_000)
    (OUT / 'gp_catalog.txt').write_bytes(catalog)
    ledger['catalog_sha256'] = hashlib.sha256(catalog).hexdigest()
    lines = [line.split(',') for line in catalog.decode('utf-8').strip().splitlines()]
    row = next(x for x in lines if x[0].strip() == 'gpcw20171231.zip')
    expected = int(row[2])
    if not 0 < expected <= 6_000_000:
        raise ValueError('catalog_size_out_of_budget')
    ledger['target_catalog'] = {'filename': row[0], 'md5': row[1], 'bytes': expected}
    body = get_file('tdxfin/gpcw20171231.zip', expected=expected)
    (OUT / 'gpcw20171231.response').write_bytes(body)
    ledger['target'] = {'bytes': len(body), 'sha256': hashlib.sha256(body).hexdigest(), 'md5': hashlib.md5(body).hexdigest(), 'magic_hex': body[:8].hex(), 'length_matches': len(body) == expected, 'md5_matches': hashlib.md5(body).hexdigest() == row[1].strip().lower(), 'zip_magic': body.startswith(b'PK\x03\x04')}
    ledger['status'] = 'BYTES_RECEIVED_REQUIRES_PARSE'
except Exception as e:
    ledger['status'] = 'FAILED_STOPPED_NO_RETRY'
    ledger['error_type'] = type(e).__name__
    ledger['error'] = str(e)[:220]
finally:
    try:
        api.disconnect()
    except Exception as cleanup_error:
        ledger['cleanup_error_type'] = type(cleanup_error).__name__
    ledger['elapsed_seconds'] = time.monotonic() - started
    (OUT / 'gp_probe.json').write_text(json.dumps(ledger, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k:v for k,v in ledger.items() if k != 'calls'}, ensure_ascii=False))
