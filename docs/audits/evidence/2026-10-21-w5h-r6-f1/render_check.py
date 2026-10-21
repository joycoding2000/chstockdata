"""Physical-page QA only; archived PDFs remain unchanged."""
import json
from pathlib import Path
import pdfplumber

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[3]


def main():
    docs = {d['id']: d for d in json.loads((OUT/'dataset.json').read_text(encoding='utf-8'))['documents']}
    selected = [('1219913619', 2), ('1219913619', 3), ('1219619642', 1),
                ('1219619642', 2), ('1219922891', 13), ('1206168292', 6), ('1219875828', 2)]
    records = []
    (OUT/'renders').mkdir(exist_ok=True)
    for id_, n in selected:
        with pdfplumber.open(ROOT/docs[id_]['path']) as pdf:
            img = pdf.pages[n-1].to_image(resolution=110)
            dest = OUT/'renders'/f'{id_}-p{n}.png'
            img.save(dest)
            records.append({'id': id_, 'physical_page': n, 'source_sha256': docs[id_]['sha256'],
                            'render': str(dest.relative_to(OUT))})
    (OUT/'render_log.json').write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'rendered': len(records)}))


if __name__ == '__main__':
    main()
