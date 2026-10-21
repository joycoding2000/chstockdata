import json
from pathlib import Path
from pypdf import PdfReader

OUT=Path(__file__).resolve().parent
results={}
terms=('经营活动现金流入小计','经营活动现金流出小计','经营活动产生的现金流量净额','前期会计差错','归属于上市公司股东的净资产','28,413','2,149','4,840','29,709')
for p in OUT.glob('*.pdf'):
    reader=PdfReader(p)
    pages=[]
    for i,page in enumerate(reader.pages):
        text=page.extract_text() or ''
        pages.append({'page':i+1,'text':text})
    (OUT/(p.name+'.pages.json')).write_text(json.dumps(pages,ensure_ascii=False,indent=2),encoding='utf-8')
    (OUT/(p.name+'.txt')).write_text('\n\n'.join(f'--- PDF PAGE {r["page"]} ---\n{r["text"]}' for r in pages),encoding='utf-8')
    results[p.name]={'pages':len(pages),'total_text_characters':sum(len(x['text']) for x in pages),'metadata':{str(k):str(v) for k,v in (reader.metadata or {}).items()},'selected_pages':[{'page':x['page'],'characters':len(x['text']),'matched_terms':[t for t in terms if t in x['text'].replace(' ','')]} for x in pages if any(t in x['text'].replace(' ','') for t in terms)]}
(OUT/'pdf_extraction_inventory.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(results,ensure_ascii=True))
