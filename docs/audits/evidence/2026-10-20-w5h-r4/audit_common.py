"""Bounded read-only R4 evidence helpers; no production integration."""
import hashlib
import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[3]
MAX_DIRECT_REQUESTS = 16
MAX_WEB_BATCHES = 8
MAX_BODY = 20_000_000
MAX_TOTAL_BYTES = 60_000_000

def save(name, data):
    (OUT/name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')

def read(name):
    return json.loads((OUT/name).read_text(encoding='utf-8'))

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

def request(name, url, *, data=None, headers=None, max_bytes=MAX_BODY):
    ledger_path = OUT/'requests.json'
    ledger = read('requests.json') if ledger_path.exists() else {'max_direct_requests': MAX_DIRECT_REQUESTS, 'max_web_batches': MAX_WEB_BATCHES, 'timeout_seconds': 15, 'max_body_bytes': MAX_BODY, 'max_total_saved_bytes': MAX_TOTAL_BYTES, 'same_host_after_finish_seconds': 3, 'automatic_retries': 0, 'redirects': False, 'requests': []}
    rows = ledger['requests']
    assert len(rows) < MAX_DIRECT_REQUESTS
    assert sum(x.get('bytes',0) for x in rows) < MAX_TOTAL_BYTES
    host = urllib.request.urlparse(url).netloc if hasattr(urllib.request, 'urlparse') else __import__('urllib.parse', fromlist=['urlparse']).urlparse(url).netloc
    last = next((x for x in reversed(rows) if x['host']==host), None)
    if last:
        wait = 3 - (datetime.now(timezone.utc)-datetime.fromisoformat(last['finished_at'])).total_seconds()
        if wait > 0:
            time.sleep(wait)
    row = {'id': name, 'url': url, 'host': host, 'method': 'POST' if data is not None else 'GET', 'request_body_utf8': data.decode('utf-8') if data is not None else None, 'at_utc': datetime.now(timezone.utc).isoformat(), 'max_bytes': max_bytes}
    b = None
    try:
        req = urllib.request.Request(url, data=data, headers={'User-Agent':'Mozilla/5.0 chstockdata-fixed-disclosure-audit', **(headers or {})})
        with urllib.request.build_opener(NoRedirect).open(req, timeout=15) as r:
            row.update(http_status=r.status, content_type=r.headers.get('Content-Type'), content_length=r.headers.get('Content-Length'), last_modified=r.headers.get('Last-Modified'))
            b = r.read(max_bytes+1)
        if len(b) > max_bytes or sum(x.get('bytes',0) for x in rows)+len(b) > MAX_TOTAL_BYTES:
            raise ValueError('body_budget_exceeded')
        path = OUT/name
        assert path.parent == OUT
        path.write_bytes(b)
        row.update(bytes=len(b), sha256=hashlib.sha256(b).hexdigest(), magic_hex=b[:8].hex(), status='RESPONSE_SAVED')
    except urllib.error.HTTPError as e:
        row.update(http_status=e.code, status='HTTP_FAILED', error_type=type(e).__name__)
    except Exception as e:
        row.update(status='REQUEST_FAILED', error_type=type(e).__name__, detail=str(e)[:180])
        b = None
    finally:
        row['finished_at'] = datetime.now(timezone.utc).isoformat()
        rows.append(row)
        save('requests.json', ledger)
    return b
