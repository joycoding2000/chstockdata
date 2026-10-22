"""Exact frozen official URLs only; independently enforced bounded acquisition."""
import hashlib
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[3]
F2 = OUT.parent/'2026-10-21-w5h-f2'


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def save(name, obj):
    path = OUT/name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf-8')


def now():
    return datetime.now(timezone.utc).isoformat()


def allowance(plan, ledger, source):
    b = plan['budget']
    assert source in plan['sources'], 'Only frozen ID/issuer/date/URL objects allowed'
    assert source['url'].startswith('https://static.cninfo.com.cn/finalpage/')
    assert len(ledger) < b['additional_requests_max']
    assert b['previous_requests']+len(ledger) < b['cumulative_requests_max']
    success = {r['id'] for r in ledger if r['status']=='SAVED'}
    assert len(success) < b['additional_identities_max']
    assert b['previous_pdf_successes']+len(success) < b['cumulative_pdf_successes_max']
    received = sum(r.get('received_bytes',0) for r in ledger)
    remaining = b['cumulative_new_pdf_bytes_max']-b['previous_pdf_bytes']-received
    assert remaining > 0, 'Cumulative byte budget exhausted'
    return min(b['single_pdf_max_bytes'],remaining)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        return None


def fetch(source, plan):
    ledger = read(OUT/'requests.json') if (OUT/'requests.json').exists() else []
    path = OUT/'originals'/f"{source['id']}.pdf"
    prior = next((r for r in ledger if r['id']==source['id'] and r['status']=='SAVED'),None)
    if prior:
        assert path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest()==prior['sha256']
        return prior
    limit = allowance(plan,ledger,source)
    wait = max(0,plan['budget']['same_host_gap_seconds']-
        (datetime.now(timezone.utc)-datetime.fromisoformat(ledger[-1]['finished_at'])).total_seconds()) if ledger else 0
    time.sleep(wait)
    row = {**source,'started_at':now(),'throttle_sleep_seconds':wait,'received_bytes':0}
    start = time.perf_counter()
    try:
        req = urllib.request.Request(source['url'],headers={'User-Agent':'Mozilla/5.0',
            'Referer':'https://www.cninfo.com.cn/'})
        with urllib.request.build_opener(NoRedirect).open(req,timeout=25) as response:
            row['http_status'] = response.status
            row['content_type'] = response.headers.get('Content-Type')
            length = int(response.headers.get('Content-Length','0'))
            row['declared_length'] = length or None
            if length > limit:
                row.update(status='BUDGET_BLOCKED',reason='DECLARED_LENGTH_EXCEEDS_SINGLE_OR_REMAINING_CAP',limit=limit)
            else:
                data = response.read(limit)
                row['received_bytes'] = len(data)
                if len(data)==limit and not length:
                    row.update(status='BUDGET_BLOCKED',reason='EOF_NOT_PROVEN_WITHIN_BYTE_LIMIT')
                elif length and len(data)!=length:
                    row.update(status='FAILED',reason='TRUNCATED_CONTENT_LENGTH')
                elif not data.startswith(b'%PDF-'):
                    row.update(status='ACCESS_OR_CONTENT_BLOCKED',reason='NOT_PDF_NO_BYPASS')
                else:
                    path.parent.mkdir(parents=True,exist_ok=True)
                    path.write_bytes(data)
                    row.update(status='SAVED',bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),
                               path=path.relative_to(ROOT).as_posix())
    except urllib.error.HTTPError as exc:
        row.update(status='ACCESS_BLOCKED' if exc.code in (401,403,429) else 'FAILED',
                   http_status=exc.code,reason=f'HTTP_{exc.code}')
    except Exception as exc:
        row.update(status='FAILED',reason=type(exc).__name__+': '+str(exc))
    row.update(finished_at=now(),http_seconds=time.perf_counter()-start)
    ledger.append(row)
    save('requests.json',ledger)
    return row


def main():
    plan = read(OUT/'preregistration.json')
    tiers = set(sys.argv[1:] or ['A','B','C'])
    for source in plan['sources']:
        if source['tier'] not in tiers:
            continue
        result = fetch(source,plan)
        if result['status']=='FAILED':
            ledger = read(OUT/'requests.json')
            retries = len(ledger)-len({r['id'] for r in ledger})
            if retries < plan['budget']['additional_retries_max']:
                result = fetch(source,plan)
        print(json.dumps({k:result.get(k) for k in ['id','tier','status','bytes','declared_length','reason']}),flush=True)
        if result['status'] in ('ACCESS_BLOCKED','ACCESS_OR_CONTENT_BLOCKED','FAILED'):
            break
    ledger = read(OUT/'requests.json')
    save('documents.json',[r for r in ledger if r['status']=='SAVED'])


if __name__ == '__main__':
    main()
