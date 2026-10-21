"""Bounded official CNINFO access, raw responses and no authentication/bypass."""
import hashlib
import html
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[3]
R5 = OUT.parent/'2026-10-20-w5h-r5'
R4 = OUT.parent/'2026-10-20-w5h-r4'


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def save(name, data):
    p = OUT/name
    p.parent.mkdir(exist_ok=True, parents=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def now():
    return datetime.now(timezone.utc).isoformat()


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def check_request_budget(ledger, name, rules):
    assert len(ledger) < rules['total_direct_requests'], 'Total request bound exhausted'
    pdfs = sum(r['file'].startswith('originals/') for r in ledger)
    if name.startswith('originals/'):
        assert pdfs < rules['new_pdfs'], 'New original PDF bound exhausted'
    else:
        assert len(ledger)-pdfs < rules['metadata_requests'], 'Metadata request bound exhausted'


def request(name, url, form=None, maximum=4000000):
    rules = read(OUT/'preregistration.json')['budget']
    if (OUT/'pagination_budget_amendment.json').exists():
        rules.update({k: v for k, v in read(OUT/'pagination_budget_amendment.json').items()
                      if k in ['metadata_requests', 'total_direct_requests']})
    ledger = read(OUT/'requests.json') if (OUT/'requests.json').exists() else []
    dest = OUT/name
    if dest.exists():
        return dest.read_bytes()
    check_request_budget(ledger, name, rules)
    host = urllib.parse.urlsplit(url).hostname
    assert host in {'www.cninfo.com.cn', 'static.cninfo.com.cn'} and url.startswith('https://')
    previous = next((r for r in reversed(ledger) if r['host'] == host), None)
    if previous:
        wait = max(0, rules['seconds_between_same_host'] -
                   (datetime.now(timezone.utc) - datetime.fromisoformat(previous['finished_at'])).total_seconds())
        time.sleep(wait)
    else:
        wait = 0
    payload = urllib.parse.urlencode(form).encode('utf-8') if form is not None else None
    req = urllib.request.Request(url, data=payload, headers={
        'User-Agent': 'Mozilla/5.0', 'Referer': 'https://www.cninfo.com.cn/',
        'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8'})
    row = {'file': name, 'url': url, 'host': host, 'method': 'POST' if payload else 'GET',
           'form': form, 'started_at': now(), 'throttle_sleep_seconds': wait}
    start = time.perf_counter()
    try:
        with urllib.request.build_opener(NoRedirect).open(req, timeout=rules['timeout_seconds']) as res:
            b = res.read(maximum+1)
            assert len(b) <= maximum, 'Response exceeds preregistered byte bound'
            row.update(status='SAVED', http_status=res.status, bytes=len(b),
                       sha256=hashlib.sha256(b).hexdigest(), content_type=res.headers.get('Content-Type'))
        dest.parent.mkdir(exist_ok=True, parents=True)
        dest.write_bytes(b)
    except Exception as exc:
        row.update(status='FAILED_REQUEST_NOT_EMPTY_SOURCE', error=type(exc).__name__+': '+str(exc))
        raise
    finally:
        row.update(finished_at=now(), http_wall_seconds=time.perf_counter()-start)
        ledger.append(row)
        save('requests.json', ledger)
    return b


def org(code):
    path = R5/f'{code}_issuer.json'
    if path.exists():
        return next(r['orgId'] for r in read(path) if r['code'] == code)
    records = [r for q in read(R4/'cninfo_index_summary.json').values() for r in q['records']]
    return next(r['orgId'] for r in records if r.get('secCode') == code)


def indexes():
    reg = read(OUT/'preregistration.json')
    all_rows, checks = {}, []
    for w in reg['windows']:
        code = w['code']
        pages, combined = [], []
        for n in range(1, reg['budget']['max_pages_per_issuer']+1):
            form = {'pageNum': str(n), 'pageSize': str(reg['budget']['page_size']),
                    'column': 'sse' if code.startswith('6') else 'szse', 'tabName': 'fulltext',
                    'plate': '', 'stock': code+','+org(code), 'searchkey': '', 'secid': '',
                    'category': '', 'trade': '', 'seDate': w['start']+'~'+w['end'],
                    'sortName': 'time', 'sortType': 'asc', 'isHLtitle': 'true'}
            obj = json.loads(request(f'index/{code}-page{n}.json',
                                    'https://www.cninfo.com.cn/new/hisAnnouncement/query', form))
            records = obj.get('announcements')
            assert isinstance(records, list), 'Invalid index structure is not an empty source'
            combined.extend(records)
            pages.append({'page': n, 'count': len(records), 'hasMore': obj.get('hasMore'),
                          'totalAnnouncement': obj.get('totalAnnouncement'),
                          'totalRecordNum': obj.get('totalRecordNum'), 'totalpages': obj.get('totalpages')})
            if not obj.get('hasMore'):
                break
        unique = {r['announcementId']: r for r in combined}
        expected = pages[0]['totalAnnouncement']
        checks.append({'code': code, 'start': w['start'], 'end': w['end'], 'pages': pages,
                       'unique_ids': len(unique), 'raw_records': len(combined),
                       'count_matches_reported_total': len(unique) == expected,
                       'exhausted_hasMore': not pages[-1]['hasMore'],
                       'category_filter': '', 'title_filter': ''})
        all_rows.update(unique)
        print(json.dumps({'code': code, 'records': len(unique), 'pages': len(pages), 'total': expected}), flush=True)
    rows = []
    for r in all_rows.values():
        title = html.unescape(re.sub('<[^>]*>', '', r['announcementTitle']))
        rows.append({'id': r['announcementId'], 'code': r['secCode'], 'title': title,
                     'date': r['adjunctUrl'].split('/')[1],
                     'url': 'https://static.cninfo.com.cn/'+r['adjunctUrl'],
                     'orgId': r['orgId']})
    save('index_inventory.json', {'checks': checks, 'rows': sorted(rows, key=lambda r: (r['code'], r['date'], r['id']))})


if __name__ == '__main__':
    indexes()
