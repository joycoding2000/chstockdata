"""One necessary already-certified official PDF fixture, no discovery/retry."""
import hashlib
import json
from datetime import datetime,timezone
from pathlib import Path
import requests
root=Path(__file__).resolve().parents[2]/'chstockdata'
url='https://disc.static.szse.cn/disc/disk03/finalpage/2026-09-11/441bfc71-d5d9-4f67-aed6-05eeeec9aaf3.PDF'
s=requests.Session();s.trust_env=False
m={'purpose':'necessary raw fixture acquisition, not public reader live Gate','url':url,'retrieved_at':datetime.now(timezone.utc).isoformat()}
try:
 r=s.get(url,timeout=(4,8),allow_redirects=False)
 m.update(http_status=r.status_code,sha256=hashlib.sha256(r.content).hexdigest(),bytes=len(r.content),pdf_magic=r.content.startswith(b'%PDF-'))
 (root/'tests/fixtures/opening/159509-20260911.pdf').write_bytes(r.content)
except Exception as exc:
 m.update(error_type=type(exc).__name__)
Path(__file__).with_name('pdf-fixture-acquisition.json').write_text(json.dumps(m,indent=2),encoding='utf-8')
print(json.dumps(m))
