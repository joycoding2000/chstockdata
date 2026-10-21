import io
import json
import struct
import zipfile
from decimal import Decimal
from pathlib import Path
from bs4 import BeautifulSoup
from audit_common import OUT, ROOT, save, sha

prior = OUT.parent
zip_path = prior/'2026-10-20-w5h-r3/http_gpcw20171231.response'
with zipfile.ZipFile(io.BytesIO(zip_path.read_bytes())) as z:
    assert z.namelist() == ['gpcw20171231.dat']
    dat = z.read(z.namelist()[0])
header = struct.unpack_from('<hIHIII',dat)
matches = []
for i in range(header[2]):
    code, flag, offset = struct.unpack_from('<6scI',dat,20+i*11)
    if code == b'600518':
        matches.append((i,offset,struct.unpack_from(f'<{header[4]//4}f',dat,offset)))
assert len(matches)==1
index, offset, rec = matches[0]
fields = {f'FN{k}':rec[k-1] for k in list(range(98,108))+[74,96,107,230,232,234,238,271,281,314]}
definition_paths = [* (prior/'2026-10-20-w5h-r3/upstream/zxtzlyt__tdx_quant/docs').rglob('get_financial_data.md'), * (prior/'2026-10-20-w5h-r3/upstream/wkingnet__stock-analysis/util_docs').glob('*.txt')]
definitions = []
for p in definition_paths:
    lines=p.read_text(encoding='utf-8').splitlines()
    definitions.append({'path':str(p),'sha256':sha(p),'selected_lines':[{'line':i+1,'text':s} for i,s in enumerate(lines) if any(k in s for k in ('FN101','FN106','FN107','101.--','106.--','107.--','单季','累计','没有标注单位'))]})

source_excerpts = {}
for name in ('original_2017.html','correction_2019.html'):
    p=prior/'2026-10-19-w5h'/name
    soup=BeautifulSoup(p.read_bytes(),'html.parser',from_encoding='gb18030')
    text=' '.join(soup.stripped_strings)
    (OUT/(name+'.extracted.txt')).write_text(text,encoding='utf-8')
    terms=('经营活动现金流入小计','经营活动现金流出小计','经营活动产生的现金流量净额','销售商品、提供劳务收到的现金','母公司现金流量表','合并现金流量表')
    hits=[]
    for term in terms:
        start=0
        while True:
            at=text.find(term,start)
            if at<0:break
            hits.append({'term':term,'text_offset':at,'excerpt':text[max(0,at-140):at+500]})
            start=at+len(term)
    rows=[]
    for ti,table in enumerate(soup.find_all('table')):
        for ri,tr in enumerate(table.find_all('tr')):
            cells=[' '.join(c.stripped_strings) for c in tr.find_all(['th','td'],recursive=False)]
            if any(any(term in c for term in terms) for c in cells):
                rows.append({'table':ti,'row':ri,'cells':cells})
    source_excerpts[name]={'sha256':sha(p),'characters':len(text),'table_count':len(soup.find_all('table')),'hits':hits,'table_rows':rows}

def ulp32(v):
    bits=struct.unpack('<I',struct.pack('<f',abs(v)))[0]
    return struct.unpack('<f',struct.pack('<I',bits+1))[0]-abs(v)

inflow,outflow,net=(fields[k] for k in ('FN101','FN106','FN107'))
residual=Decimal(str(inflow))-Decimal(str(outflow))-Decimal(str(net))
tol=sum(Decimal(str(ulp32(x)))/2 for x in (inflow,outflow,net))
result={'zip_path':str(zip_path),'zip_sha256':sha(zip_path),'dat_sha256':__import__('hashlib').sha256(dat).hexdigest(),'header':header,'fixed_record_index':index,'fixed_record_offset':offset,'fields':fields,'definitions':definitions,'ocf_identity':{'inflow_minus_outflow':inflow-outflow,'stored_net':net,'residual_yuan':str(residual),'float32_half_ulp_error_bound_yuan':str(tol),'within_quantization_bound':abs(residual)<=tol},'saved_original_excerpts':source_excerpts}
save('tdx_reconciliation.json',result)
print(json.dumps({'fields':fields,'reconciliation':result['ocf_identity'],'saved_original_hits':{k:[(h['term'],h['excerpt'][:220]) for h in v['hits']] for k,v in source_excerpts.items()}},ensure_ascii=True))
