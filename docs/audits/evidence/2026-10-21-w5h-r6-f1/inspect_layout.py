import json,sys,time
from pathlib import Path
import pdfplumber
ROOT=Path(__file__).resolve().parents[4]
OUT=Path(__file__).parent
selections=[('2026-10-20-w5h-r5','000002_Q12024.pdf',[1,2,3]),('2026-10-20-w5h-r5','000002_FY2023.pdf',[10,11]),('2026-10-20-w5h-r5','300750_Q12024.pdf',[1,2]),('2026-10-20-w5h-r5','601398_FY2023.pdf',[14,15]),('2026-10-20-w5h-r5','601398_Q12024.pdf',[1,2,12,13]),('2026-10-20-w5h-r4','official_annual_2018.pdf',[6]),('2026-10-20-w5h-r4','official_original_2017.pdf',[6,7])]
res=[]
for dr,name,ps in selections:
 with pdfplumber.open(OUT.parent/dr/name) as doc:
  for n in ps:
   pg=doc.pages[n-1]
   words=pg.extract_words(x_tolerance=2,y_tolerance=3)
   tables=pg.find_tables()
   res.append(dict(file=name,page=n,width=pg.width,height=pg.height,text=pg.extract_text(layout=False),tables=[dict(bbox=t.bbox,rows=t.extract()) for t in tables],words=words))
(OUT/'layout_probe.json').write_text(json.dumps(res,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps([dict(file=r['file'],page=r['page'],tables=len(r['tables']),chars=len(r['text'] or '')) for r in res]))
