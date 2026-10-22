import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from fetch_named import OUT,ROOT,read,save
import pdfplumber
from extract_facts import base
sources={d['id']:d for d in read(OUT/'documents.json')}
plan={'1216741268':[46,53,103], '1216741273':[21,88], '1217078312':[24,30], '1217078316':[50,126], '1217949872':[28,36,107], '1217949876':[57,138]}
result=[]
for sid,ns in plan.items():
 with pdfplumber.open(ROOT/sources[sid]['path']) as pdf:
  for n in ns:
   p=pdf.pages[n-1]
   result.append({'id':sid,'p':n,'text':p.extract_text(),'tables':[{'bbox':t.bbox,'rows':t.extract()} for t in p.find_tables()]})
save('summary_table_diagnostic.json',result)
for r in result:
 print(json.dumps(r,ensure_ascii=False))
