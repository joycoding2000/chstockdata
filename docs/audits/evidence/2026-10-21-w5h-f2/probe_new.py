"""Independent PDF text review input, separate from the amount parser."""
import json
import re
from pathlib import Path
from pypdf import PdfReader
from acquire import OUT, ROOT, read, save


def main():
    results = []
    for d in read(OUT/'new_documents.json'):
        reader = PdfReader(ROOT/d['path'])
        cache = OUT/'text'/f"{d['id']}.pages.json"
        pages = read(cache) if cache.exists() else [
            {'page': i+1, 'text': p.extract_text() or ''} for i, p in enumerate(reader.pages[:30])]
        if not cache.exists():
            save(f"text/{d['id']}.pages.json", pages)
        selected = []
        for p in pages:
            t = re.sub(r'\s+', '', p['text'])
            if ('主要会计数据' in t or '全年经营成果' in t) and re.search(r'\d,\d{3}', t):
                selected.append(p)
                if p['page'] < len(pages):
                    selected.append(pages[p['page']])
                break
        results.append({'id': d['id'], 'code': d['code'], 'period': d['period'],
                        'page_count': len(reader.pages), 'selected': selected})
    save('new_independent_review.json', results)
    print(json.dumps([{'id': r['id'], 'pages': r['page_count'],
                       'summary': [p['page'] for p in r['selected']]} for r in results]))


if __name__ == '__main__':
    main()
