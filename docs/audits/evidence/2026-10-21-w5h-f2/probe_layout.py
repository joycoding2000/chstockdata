import json
import pdfplumber
from acquire import OUT, ROOT, read, save
from parser_f2 import grid_rows, lines_of
rows=[]
for id_, page in [('1218204096',1),('1217713835',8),('1221084198',8)]:
 d=next(x for x in read(OUT/'new_documents.json') if x['id']==id_)
 with pdfplumber.open(ROOT/d['path']) as doc:
  p=doc.pages[page-1]
  rows.append({'id':id_, 'page':page, 'lines':lines_of(p), 'tables':[{'bbox':list(t.bbox), 'rows':grid_rows(t)} for t in p.find_tables()]})
save('new_layout_probe.json', rows)
print(json.dumps([{'id':x['id'],'tables':len(x['tables'])} for x in rows]))
