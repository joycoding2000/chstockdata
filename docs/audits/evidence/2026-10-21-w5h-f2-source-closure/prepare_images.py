"""Only the fixed financial-statement bundles' genuinely non-text pages."""
from fetch_named import OUT, ROOT, read, save


def main():
    import pdfplumber
    plan = []
    for d in read(OUT/'documents.json'):
        text = read(OUT/'text'/f"{d['id']}.json")
        with pdfplumber.open(ROOT/d['path']) as pdf:
            for p in text['pages']:
                if len(''.join(p['text'].split()))>=20:
                    continue
                n = p['physical_page']
                target = OUT/'images'/f"{d['id']}-p{n}.png"
                target.parent.mkdir(parents=True,exist_ok=True)
                if not target.exists():
                    pdf.pages[n-1].to_image(resolution=180).save(target)
                (OUT/'ocr').mkdir(exist_ok=True)
                plan.append({'id':d['id'],'physical_page':n,'source_sha256':d['sha256'],
                             'image':str(target),'output':str(OUT/'ocr'/f"{d['id']}-p{n}.json")})
    save('ocr_plan.json',plan)
    print({'genuine_nontext_pages':len(plan)})


if __name__=='__main__':
    main()
