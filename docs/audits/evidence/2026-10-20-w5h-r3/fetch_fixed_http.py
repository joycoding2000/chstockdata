"""One normal GET of the reviewed vendor file URL, no redirects/retries/scripts."""
import hashlib
import json
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parent
URL = 'http://down.tdx.com.cn:8001/tdxfin/gpcw20171231.zip'
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

row = {'url': URL, 'method': 'GET', 'max_requests': 1, 'timeout_seconds': 15, 'max_bytes': 6_000_000, 'redirects': False, 'automatic_retries': 0, 'at_utc': datetime.now(timezone.utc).isoformat(), 'url_provenance': 'reviewed stock-analysis readTDX_cw.py lines 32,45; filename in prior official gpcw.txt'}
try:
    opener = urllib.request.build_opener(NoRedirect)
    with opener.open(URL, timeout=15) as response:
        body = response.read(6_000_001)
        row.update(http_status=response.status, content_type=response.headers.get('Content-Type'))
    if len(body) > 6_000_000:
        raise ValueError('body_limit')
    (OUT / 'http_gpcw20171231.response').write_bytes(body)
    row.update(bytes=len(body), sha256=hashlib.sha256(body).hexdigest(), md5=hashlib.md5(body).hexdigest(), magic_hex=body[:8].hex(), zip_magic=body.startswith(b'PK\x03\x04'), status='RESPONSE_REQUIRES_QUALIFICATION')
except urllib.error.HTTPError as e:
    row.update(http_status=e.code, status='HTTP_FAILED_STOPPED', error_type=type(e).__name__)
except Exception as e:
    row.update(status='FAILED_STOPPED', error_type=type(e).__name__, detail=str(e)[:180])
(OUT / 'http_probe.json').write_text(json.dumps(row, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(row, ensure_ascii=False))
