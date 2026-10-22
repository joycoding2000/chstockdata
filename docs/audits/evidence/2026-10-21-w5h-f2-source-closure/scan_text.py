"""Independent whole-document text evidence and page fingerprints, not numeric truth."""
import hashlib
import json
import re
import sys
import time
import unicodedata
from fetch_named import OUT, ROOT, F2, read, save


def canonical(text):
    return re.sub(r'\s+','',unicodedata.normalize('NFKC',text))


def scan(source):
    from pypdf import PdfReader
    path = ROOT/source['path']
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    assert sha==source['sha256']
    target = OUT/'text'/f"{source['id']}.json"
    if target.exists():
        prior = read(target)
        assert prior['source_sha256']==sha
        return prior
    start = time.perf_counter()
    reader = PdfReader(path)
    pages = []
    for n,page in enumerate(reader.pages,1):
        text = page.extract_text() or ''
        normalized = canonical(text)
        pages.append({'physical_page':n,'text':text,
            'text_sha256':hashlib.sha256(normalized.encode('utf-8')).hexdigest(),
            'target_signal':any(t in normalized for t in ['归属于母公司','归属于上市公司',
                '经营活动产生的现金流量净额','经营活动产生的现金流量净','前期差错','追溯调整'])})
    result = {'id':source['id'],'code':source['code'],'source_sha256':sha,
        'page_count':len(pages),'machine_seconds':time.perf_counter()-start,'pages':pages}
    save(f"text/{source['id']}.json",result)
    return result


def main():
    sources = read(OUT/'documents.json')
    if '--baselines' in sys.argv:
        # Only existing securities relevant to new source candidates; no new source access.
        sources = [d for d in read(F2/'dataset_legacy.json')['documents']+read(F2/'new_documents.json')
                   if d['code'] in ('000961','000002','600518') and d['kind']=='periodic']
    results = []
    for d in sources:
        r = scan(d)
        results.append({k:r[k] for k in ['id','code','source_sha256','page_count','machine_seconds']})
        print(json.dumps({**results[-1],'target_pages':[p['physical_page'] for p in r['pages'] if p['target_signal']]}),flush=True)
    save('baseline_text_inventory.json' if '--baselines' in sys.argv else 'text_inventory.json',results)


if __name__=='__main__':
    main()
