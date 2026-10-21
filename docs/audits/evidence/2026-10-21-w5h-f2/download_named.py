"""Fetch only index-bound named originals; no security/amount predicates in parsing."""
import hashlib
import json
import time
from acquire import OUT, ROOT, read, save, request


def download(plan):
    prior = read(OUT/'new_documents.json') if (OUT/'new_documents.json').exists() else []
    rows = {r['id']: r for r in prior}
    for d in plan:
        if d['id'] in rows:
            continue
        assert len(rows) < read(OUT/'preregistration.json')['budget']['new_pdfs']
        b = request(f"originals/{d['id']}.pdf", d['url'], maximum=25000000)
        assert b.startswith(b'%PDF'), 'Not a PDF; never treat a request/error page as a report'
        assert sum(r['bytes'] for r in rows.values()) + len(b) <= 200000000
        path = OUT/'originals'/f"{d['id']}.pdf"
        rows[d['id']] = {**d, 'path': path.relative_to(ROOT).as_posix(), 'bytes': len(b),
                        'sha256': hashlib.sha256(b).hexdigest()}
        save('new_documents.json', list(rows.values()))
        print(json.dumps({'id': d['id'], 'code': d['code'], 'bytes': len(b)}), flush=True)


if __name__ == '__main__':
    download(read(OUT/'named_download_plan.json'))
