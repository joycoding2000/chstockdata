"""Unfiltered finite windows, closed by counts over disjoint date partitions."""
import json
from datetime import date, timedelta
from pathlib import Path
from acquire import OUT, read, save, request, org


def query(code, a, b, direction='asc', root_cache=None):
    if root_cache and root_cache.exists():
        return read(root_cache)
    form = {'pageNum': '1', 'pageSize': '30', 'column': 'sse' if code.startswith('6') else 'szse',
            'tabName': 'fulltext', 'plate': '', 'stock': code+','+org(code), 'searchkey': '',
            'secid': '', 'category': '', 'trade': '', 'seDate': a+'~'+b,
            'sortName': 'time', 'sortType': direction, 'isHLtitle': 'true'}
    return json.loads(request(f'index/{code}-{a}-{b}-{direction}.json',
                             'https://www.cninfo.com.cn/new/hisAnnouncement/query', form))


def close(code, a, b, depth=0, root_cache=None):
    assert depth <= 12
    obj = query(code, a, b, root_cache=root_cache)
    rows = {r['announcementId']: r for r in obj.get('announcements') or []}
    total = obj['totalAnnouncement']
    proof = {'code': code, 'start': a, 'end': b, 'reported_total': total, 'initial_unique': len(rows)}
    if len(rows) == total:
        proof['closed'] = True
        return rows, proof
    if a == b:
        rows = {}
        raw_count = 0
        for page in range(1, (total+29)//30+1):
            form = {'stock': code+','+org(code), 'tabName': 'fulltext', 'pageSize': '30',
                    'pageNum': str(page), 'column': 'sse' if code.startswith('6') else 'szse',
                    'category': '', 'plate': 'sh' if code.startswith('6') else 'sz',
                    'seDate': a+'~'+b, 'searchkey': '', 'secid': '',
                    'sortName': '', 'sortType': '', 'isHLtitle': 'true'}
            obj = json.loads(request(f'index/{code}-{a}-native-page{page}.json',
                                    'https://www.cninfo.com.cn/new/hisAnnouncement/query', form))
            raw_count += len(obj['announcements'])
            rows.update({r['announcementId']: r for r in obj['announcements']})
        proof.update(method='OFFICIAL_FRONTEND_PLATE_AND_DEFAULT_ORDER_PAGINATION',
                     closed=len(rows) == total and raw_count == total, final_unique=len(rows), raw_count=raw_count)
        return rows, proof
    left, right = date.fromisoformat(a), date.fromisoformat(b)
    mid = left + (right-left)//2
    lrows, lp = close(code, a, mid.isoformat(), depth+1)
    rrows, rp = close(code, (mid+timedelta(days=1)).isoformat(), b, depth+1)
    rows = {**lrows, **rrows}
    proof.update(method='DISJOINT_DATE_PARTITIONS', children=[lp, rp], final_unique=len(rows),
                 closed=lp['closed'] and rp['closed'] and len(rows) == total and
                        lp['reported_total']+rp['reported_total'] == total)
    return rows, proof


def main():
    import html
    import re
    all_rows, proofs = {}, []
    for w in read(OUT/'preregistration.json')['windows']:
        cache = OUT/'index'/f"{w['code']}-page1.json"
        rows, proof = close(w['code'], w['start'], w['end'], root_cache=cache)
        proofs.append(proof)
        all_rows.update(rows)
        save('index_closure_partial.json', {'proofs': proofs, 'raw_rows': list(all_rows.values())})
        print(json.dumps({'code': w['code'], 'closed': proof['closed'],
                          'unique': len(rows), 'total': proof['reported_total']}), flush=True)
    normalized = [{'id': r['announcementId'], 'code': r['secCode'],
                   'title': html.unescape(re.sub('<[^>]*>', '', r['announcementTitle'])),
                   'date': r['adjunctUrl'].split('/')[1],
                   'url': 'https://static.cninfo.com.cn/'+r['adjunctUrl'],
                   'orgId': r['orgId']} for r in all_rows.values()]
    save('index_inventory.json', {'proofs': proofs, 'all_windows_closed': all(p['closed'] for p in proofs),
                                 'rows': sorted(normalized, key=lambda r: (r['code'], r['date'], r['id']))})


if __name__ == '__main__':
    main()
