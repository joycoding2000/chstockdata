"""One-off bounded R5 measurement. Never imported by production code."""
import hashlib
import html
import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[3]
REG = json.loads((OUT/'preregistration.json').read_text(encoding='utf-8'))

def now():
    return datetime.now(timezone.utc).isoformat()

def save(name, data):
    assert Path(name).name == name
    (OUT/name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')

def read(name):
    return json.loads((OUT/name).read_text(encoding='utf-8'))

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

def request(name, url, form=None, limit=25_000_000):
    ledger = read('requests.json') if (OUT/'requests.json').exists() else {'requests': []}
    rows = ledger['requests']
    assert len(rows) < REG['budget']['direct_requests']
    total = sum(r.get('bytes',0) for r in rows)
    assert total < REG['budget']['total_network_bytes']
    host = urllib.parse.urlparse(url).netloc
    last = next((r for r in reversed(rows) if r['host']==host), None)
    delay = max(0,3-(datetime.now(timezone.utc)-datetime.fromisoformat(last['finished_at'])).total_seconds()) if last else 0
    time.sleep(delay)
    row = {'file':name,'url':url,'host':host,'method':'POST' if form else 'GET','form':form,'started_at':now(),'throttle_sleep_seconds':delay}
    start=time.perf_counter()
    body=None
    try:
        data=urllib.parse.urlencode(form).encode('utf-8') if form else None
        req=urllib.request.Request(url,data=data,headers={'User-Agent':'Mozilla/5.0','Referer':'https://www.cninfo.com.cn/' if 'cninfo' in host else 'https://basic.10jqka.com.cn/','Content-Type':'application/x-www-form-urlencoded'})
        with urllib.request.build_opener(NoRedirect).open(req,timeout=20) as r:
            row.update(http_status=r.status,content_type=r.headers.get('Content-Type'))
            body=r.read(limit+1)
        if len(body)>limit or len(body)+total>REG['budget']['total_network_bytes']:
            raise ValueError('response_body_budget_exceeded')
        (OUT/name).write_bytes(body)
        row.update(status='RESPONSE_SAVED',bytes=len(body),sha256=hashlib.sha256(body).hexdigest(),magic_hex=body[:8].hex())
    except urllib.error.HTTPError as e:
        row.update(status='HTTP_FAILED',http_status=e.code,error_type=type(e).__name__)
    except Exception as e:
        row.update(status='REQUEST_FAILED',error_type=type(e).__name__,detail=str(e)[:180])
        body=None
    row.update(finished_at=now(),http_wall_seconds=time.perf_counter()-start)
    rows.append(row)
    save('requests.json',ledger)
    if row['status']!='RESPONSE_SAVED':
        raise RuntimeError(json.dumps(row,ensure_ascii=False))
    return body

def git(root,*args):
    r=subprocess.run(['git','-c',f'safe.directory={root.as_posix()}','-C',str(root),*args],capture_output=True,encoding='utf-8',errors='replace')
    assert r.returncode==0,r.stderr
    return r.stdout

def snapshot():
    result={'at_utc':now(),'repos':{},'inputs':{}}
    for name in ['chstockdata','mishi-radar','systematic-investing-os']:
        root=ROOT.parent/name
        tracked=[p for p in git(root,'ls-files','-z').split('\0') if p]
        result['repos'][name]={'head':git(root,'rev-parse','HEAD').strip(),'branch':git(root,'branch','--show-current').strip(),'status':git(root,'status','--porcelain=v1','--untracked-files=all'),'tracked':{p:sha(root/p) if (root/p).is_file() else None for p in tracked},'untracked':[p for p in git(root,'ls-files','--others','--exclude-standard','-z').split('\0') if p]}
    inputs=['AGENTS.md','docs/plans/2026-10-19-dual-consumer-supply-plan.md','docs/audits/2026-10-19-w5h-historical-financial-pit-feasibility.md','docs/audits/2026-10-20-w5h-r2-alternative-source-qualification.md','docs/audits/2026-10-20-w5h-r3-tdx-local-opensource-qualification.md','docs/audits/2026-10-20-w5h-r4-tdx-revision-root-cause-and-archival-pit.md','docs/MISHI_RADAR_V0_1_SPEC_R3_2_SCOPE_APPROVED_DATA_PENDING_2026-10-16.md','docs/MISHI_RADAR_TO_CHSTOCKDATA_DR01_DR06_CONSUMER_REQUEST_2026-10-16.md']
    for p in inputs:
        result['inputs'][str(ROOT/p)]=sha(ROOT/p)
    spec=ROOT.parent/'mishi-radar/docs/MISHI_RADAR_R3_2_PRODUCT_OPERATING_SPEC_CANDIDATE_2026-10-19.md'
    result['inputs'][str(spec)]=sha(spec)
    return result

def discover():
    result=[]
    for s in REG['samples'][:5]:
        code=s['code']
        raw=json.loads(request(f'{code}_issuer.json','https://www.cninfo.com.cn/new/information/topSearch/query',{'keyWord':code,'maxNum':'10'},1_000_000))
        hits=[r for r in raw if r['code']==code]
        if len(hits)!=1:
            result.append({'code':code,'issuer_hits':hits,'status':'ISSUER_ID_UNRESOLVED'})
            save('discovery.json',result)
            raise RuntimeError('No unique issuer; retain failed sample and stop, no substitution')
        org=hits[0]['orgId']
        row={'code':code,'orgId':org,'queries':{},'targets':{}}
        for purpose,key,cat in [('periodic','','category_ndbg_szsh;category_yjdbg_szsh;category_bndbg_szsh;category_sjdbg_szsh;'),('correction','更正',''),('supplement','补充','')]:
            form={'pageNum':'1','pageSize':'100','column':s['market'],'tabName':'fulltext','plate':'','stock':code+','+org,'searchkey':key,'secid':'','category':cat,'trade':'','seDate':'2023-01-01~2024-12-31','sortName':'time','sortType':'asc','isHLtitle':'true'}
            response=json.loads(request(f'{code}_{purpose}_index.json','https://www.cninfo.com.cn/new/hisAnnouncement/query',form,4_000_000))
            anns=response.get('announcements') or []
            row['queries'][purpose]={'total':response.get('totalAnnouncement'),'returned':len(anns),'hasMore':response.get('hasMore')}
            if purpose=='periodic':
                for period,title in [('FY2023','2023年年度报告'),('Q12024','2024年第一季度报告')]:
                    matches=[r for r in anns if re.sub(r'\s+','',html.unescape(re.sub('<[^>]*>','',r['announcementTitle']))).split('：')[-1] in (title,title+'全文')]
                    row['targets'][period]={'candidates':matches,'selected':matches[0] if matches else None}
        result.append(row)
        save('discovery.json',result)
        print(json.dumps({'code':code,'index':row['queries'],'selected':{k:v['selected']['announcementId'] if v['selected'] else None for k,v in row['targets'].items()}},ensure_ascii=False),flush=True)

def download():
    docs=read('documents.json') if (OUT/'documents.json').exists() else []
    for s in read('discovery.json'):
        for period,target in s.get('targets',{}).items():
            name=s['code']+'_'+period+'.pdf'
            if any(d['file']==name for d in docs):
                continue
            r=target['selected']
            if not r:
                docs.append({'code':s['code'],'period':period,'file':name,'status':'INDEX_TARGET_NOT_FOUND'})
                save('documents.json',docs)
                continue
            url='https://static.cninfo.com.cn/'+r['adjunctUrl']
            b=request(name,url)
            assert b.startswith(b'%PDF'), 'Not a PDF; stop source path'
            docs.append({'code':s['code'],'period':period,'file':name,'url':url,'id':r['announcementId'],'catalog_time_epoch_ms':r['announcementTime'],'catalog_date':r['adjunctUrl'].split('/')[1],'title':r['announcementTitle'],'bytes':len(b),'sha256':sha(OUT/name),'status':'PDF_OBTAINED'})
            save('documents.json',docs)
            print(name,len(b),flush=True)
    name='000961_delisting_identity.pdf'
    if not (OUT/name).exists():
        request(name,REG['samples'][4]['basis_url'],limit=2_000_000)

def select_saved():
    rows=read('discovery.json')
    for row in rows:
        anns=read(row['code']+'_periodic_index.json').get('announcements') or []
        for period,title in [('FY2023','2023年年度报告'),('Q12024','2024年第一季度报告')]:
            matches=[]
            for r in anns:
                clean=re.sub(r'\s+','',html.unescape(re.sub('<[^>]*>','',r['announcementTitle'])))
                aliases=[title,title.replace('第一季度','一季度'),title.replace('年年度','年度')]
                if any(clean.endswith(t) or clean.endswith(t+'全文') for t in aliases):
                    matches.append(r)
            row['targets'][period]={'candidates':matches,'selected':matches[0] if matches else None}
    save('discovery.json',rows)
    save('matching_note.json',{'reason':'Initial exact-title matcher omitted issuer name prefixes. Corrected to Chinese full-title suffix, no value-based selection, no requests repeated. Original raw indexes untouched.','at_utc':now(),'targets':{r['code']:{k:v['selected']['announcementId'] if v['selected'] else None for k,v in r['targets'].items()} for r in rows}})
    print(json.dumps(read('matching_note.json'),ensure_ascii=False))

def structured():
    for code,market in [('600519',17),('000961',33)]:
        for table in ['benefit','cash','debt']:
            name=f'{code}_ths_{table}.json'
            if (OUT/name).exists():
                continue
            params={'code':code,'id':'client_stock_'+table,'market':market,'type':'stock','page':'1','size':'50','period':'0'}
            request(name,'https://basic.10jqka.com.cn/basicapi/finance/index/v1/app_data/?'+urllib.parse.urlencode(params),limit=4_000_000)
            print(name,flush=True)

def parse():
    from pypdf import PdfReader
    rows=read('pdf_measurements.json') if (OUT/'pdf_measurements.json').exists() else []
    for d in read('documents.json'):
        if d['status']!='PDF_OBTAINED' or any(r['file']==d['file'] for r in rows):
            continue
        start=time.perf_counter()
        pdf=PdfReader(OUT/d['file'])
        pages=[{'page':i+1,'text':p.extract_text() or ''} for i,p in enumerate(pdf.pages)]
        elapsed=time.perf_counter()-start
        save(d['file']+'.pages.json',pages)
        keywords=['归属于','经营活动产生的现金','追溯','重述','调整','单位','合并资产负债','合并利润','合并现金','所有者权益']
        selected=[p for p in pages if any(k in re.sub(r'\s+','',p['text']) for k in keywords)]
        save(d['file']+'.hits.json',selected)
        rows.append({'file':d['file'],'code':d['code'],'period':d['period'],'pages':len(pages),'bytes':d['bytes'],'characters':sum(len(p['text']) for p in pages),'empty_text_pages':sum(not p['text'].strip() for p in pages),'machine_parse_wall_seconds':elapsed,'parser':'pypdf existing bundled runtime','status':'TEXT_LAYER_OBTAINED'})
        save('pdf_measurements.json',rows)
        print(json.dumps(rows[-1]),flush=True)

if __name__=='__main__':
    stage=sys.argv[1]
    if stage=='init':
        assert not (OUT/'before.json').exists()
        save('before.json',snapshot())
        save('preregistration_identity.json',{'sha256':sha(OUT/'preregistration.json'),'at_utc':now()})
    elif stage=='discover':
        discover()
    elif stage=='download':
        download()
    elif stage=='select':
        select_saved()
    elif stage=='structured':
        structured()
    elif stage=='parse':
        parse()
    elif stage=='after':
        save('after.json',snapshot())
    else:
        raise ValueError(stage)
