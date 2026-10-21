"""Four-document R6 acquisition and evidence protection only."""
import hashlib
import importlib.util
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[3]
R5=OUT.parent/'2026-10-20-w5h-r5'
RULES=json.loads((OUT/'discovery_rules_v1.json').read_text(encoding='utf-8'))

def now():
    return datetime.now(timezone.utc).isoformat()

def read(name):
    return json.loads((OUT/name).read_text(encoding='utf-8'))

def save(name,value):
    assert Path(name).name==name
    (OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def snapshot():
    spec=importlib.util.spec_from_file_location('r5_readonly_snapshot',R5/'measure.py')
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.snapshot()

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        return None

def initialize():
    assert not (OUT/'before.json').exists()
    before=snapshot()
    checks=[]
    manifest=json.loads((R5/'manifest.json').read_text(encoding='utf-8'))
    for r in manifest['files']+[manifest['report']]:
        p=Path(r['path']) if Path(r['path']).is_absolute() else R5/r['path']
        checks.append({'path':str(p),'expected_sha256':r['sha256'],'actual_sha256':sha(p),'matches':sha(p)==r['sha256'] and p.stat().st_size==r['bytes']})
    assert all(c['matches'] for c in checks)
    before['inputs'][str(ROOT/'docs/audits/2026-10-20-w5h-r5-historical-disclosure-scale-cost-screen.md')]=sha(Path(manifest['report']['path']))
    save('before.json',before)
    save('R5_manifest_checks.json',{'all_match':True,'files':checks})
    context=[]
    for path,h in before['inputs'].items():
        text=Path(path).read_text(encoding='utf-8')
        lines=text.splitlines()
        selected=[{'line':i+1,'text':l} for i,l in enumerate(lines) if any(k in l for k in ['S07','DR05','ROE','PE','CURRENT_DECISION','NOT_FROZEN','NOT_PASSED','Gate','预热','旧版','修订'])]
        context.append({'path':path,'sha256':h,'characters_read':len(text),'head':text[:800],'relevant_lines':selected})
    save('context_recovery.json',context)
    print(json.dumps({'heads':{k:v['head'] for k,v in before['repos'].items()},'tracked':sum(len(v['tracked']) for v in before['repos'].values()),'prior_R5_hashes':len(checks)}),flush=True)

def fetch():
    assert (OUT/'before.json').exists()
    ledger=read('requests.json') if (OUT/'requests.json').exists() else {'budget':RULES['budget'],'requests':[]}
    assert not ledger['requests'],'No repeated fetch stage'
    for d in RULES['scope']['new_documents']:
        row={**d,'file':d['id']+'.pdf','started_at':None}
        if ledger['requests']:
            gap=(datetime.now(timezone.utc)-datetime.fromisoformat(ledger['requests'][-1]['finished_at'])).total_seconds()
            delay=max(0,3-gap)
        else:
            delay=0
        time.sleep(delay)
        row['throttle_sleep_seconds']=delay
        row['started_at']=now()
        start=time.perf_counter()
        try:
            req=urllib.request.Request(d['url'],headers={'User-Agent':'Mozilla/5.0','Referer':'https://www.cninfo.com.cn/'})
            with urllib.request.build_opener(NoRedirect).open(req,timeout=20) as r:
                row.update(http_status=r.status,content_type=r.headers.get('Content-Type'))
                b=r.read(RULES['budget']['single_body_bytes']+1)
            assert len(b)<=RULES['budget']['single_body_bytes']
            assert len(b)+sum(r.get('bytes',0) for r in ledger['requests'])<=RULES['budget']['total_network_bytes']
            assert b.startswith(b'%PDF')
            assert not (OUT/row['file']).exists()
            (OUT/row['file']).write_bytes(b)
            row.update(status='PDF_SAVED',bytes=len(b),sha256=sha(OUT/row['file']))
        except urllib.error.HTTPError as e:
            row.update(status='HTTP_FAILED',http_status=e.code,error=type(e).__name__)
        except Exception as e:
            row.update(status='FAILED',error=type(e).__name__,detail=str(e)[:150])
        row.update(finished_at=now(),http_wall_seconds=time.perf_counter()-start)
        ledger['requests'].append(row)
        save('requests.json',ledger)
        print(json.dumps(row),flush=True)
        if row['status']!='PDF_SAVED':
            break

def parse():
    from pypdf import PdfReader
    inventory=[]
    for r in read('requests.json')['requests']:
        if r['status']!='PDF_SAVED':
            continue
        start=time.perf_counter()
        pdf=PdfReader(OUT/r['file'])
        pages=[{'page':i+1,'text':p.extract_text() or ''} for i,p in enumerate(pdf.pages)]
        seconds=time.perf_counter()-start
        save(r['file']+'.pages.json',pages)
        inventory.append({**r,'pages':len(pages),'characters':sum(len(p['text']) for p in pages),'empty_text_pages':sum(not p['text'].strip() for p in pages),'machine_parse_seconds':seconds})
        print(json.dumps({k:inventory[-1][k] for k in ['file','pages','bytes','machine_parse_seconds']}),flush=True)
    save('new_document_inventory.json',inventory)

if __name__=='__main__':
    {'init':initialize,'fetch':fetch,'parse':parse}[sys.argv[1]]()
