"""Only the authorized public reader points; no discovery or request retries."""
import hashlib
import importlib.metadata
import json
import os
import sys
from datetime import datetime,timezone
from pathlib import Path

here=Path(__file__).resolve().parent
root=here.parents[1]/'chstockdata'
sys.path.insert(0,str(root/'src'))
sys.path.append('C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/Lib/site-packages')
import requests
import pypdf
from mootdx.quotes import Quotes
from chstockdata.opening_evidence import (fetch_historical_opening_evidence,TdxOpeningReader,OfficialOpeningReader)
samples=[('510300','2026-09-11','OPEN_ACTIVITY_CONFIRMED'),('159915','2026-09-11','OPEN_ACTIVITY_CONFIRMED'),
 ('518880','2026-09-11','OPEN_ACTIVITY_CONFIRMED'),('511010','2026-09-11','OPEN_ACTIVITY_CONFIRMED'),
 ('513100','2026-09-11','BLOCKED_CONFIRMED'),('159509','2026-09-11','BLOCKED_CONFIRMED'),
 ('688432','2026-08-31','BLOCKED_CONFIRMED'),('688432','2026-09-14','OPEN_ACTIVITY_CONFIRMED'),
 ('000002','2015-12-18','OPEN_ACTIVITY_CONFIRMED'),('000002','2016-01-04','BLOCKED_CONFIRMED'),
 ('510300','2016-12-30','OPEN_ACTIVITY_CONFIRMED'),('510300','2022-12-30','OPEN_ACTIVITY_CONFIRMED')]
out=here/'live';out.mkdir(exist_ok=True)
calls=[];results=[]
def save_call(kind,request,value,error=None):
 index=len(calls)+1
 content=value if isinstance(value,bytes) else json.dumps(value,ensure_ascii=False,separators=(',',':')).encode('utf-8')
 suffix='bin' if isinstance(value,bytes) else 'json'
 path=out/f'{index:03d}-{kind}.{suffix}'
 path.write_bytes(content)
 entry={'kind':kind,'request':request,'retrieved_at':datetime.now(timezone.utc).isoformat(),
   'raw_file':path.name,'sha256':hashlib.sha256(content).hexdigest(),'bytes':len(content),'error_type':error}
 calls.append(entry)
 (out/'requests.json').write_text(json.dumps(calls,ensure_ascii=False,indent=2),encoding='utf-8')
class RecordedClient:
 def __init__(self,actual): self.actual=actual;self.client=self
 def get_history_minute_time_data(self,market,code,date):
  request={'command':'0x0fb4','market':market,'code':code,'date':date}
  try: rows=self.actual.client.get_history_minute_time_data(market=market,code=code,date=date)
  except Exception as exc:
   save_call('tdx',request,None,type(exc).__name__);raise
  save_call('tdx',request,rows);return rows
 def get_history_transaction_data(self,market,code,start,count,date):
  request={'command':'0x0fb5','market':market,'code':code,'date':date,'start':start,'count':count}
  try: rows=self.actual.client.get_history_transaction_data(market,code,start,count,date)
  except Exception as exc:
   save_call('tdx',request,None,type(exc).__name__);raise
  save_call('tdx',request,rows);return rows
 def close(self): self.actual.close()
def factory(**kwargs):return RecordedClient(Quotes.factory(**kwargs))
class RecordedSession:
 def __init__(self):self.session=requests.Session();self.session.trust_env=False
 def get(self,url,**kwargs):return self.call('get',url,kwargs)
 def post(self,url,**kwargs):return self.call('post',url,kwargs)
 def call(self,method,url,kwargs):
  request={'method':method.upper(),'url':url,**kwargs}
  try: response=getattr(self.session,method)(url,**kwargs)
  except Exception as exc:
   save_call('official',request,None,type(exc).__name__);raise
  request.update(http_status=response.status_code,content_type=response.headers.get('Content-Type'))
  save_call('official',request,response.content)
  return response
manifest={'argv':sys.argv,'cwd':str(root),'env':{'PYTHONPATH':os.environ.get('PYTHONPATH'),
 'PYTHONDONTWRITEBYTECODE':os.environ.get('PYTHONDONTWRITEBYTECODE')},
 'source_sha256':{str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest()
  for p in (root/'src/chstockdata/opening_evidence.py',root/'src/chstockdata/opening_known_events.json')},
 'versions':{k:importlib.metadata.version(k) for k in ('pytest','requests','pandas','mootdx','tdxpy')},
 'pypdf_version':pypdf.__version__,'pypdf_path':pypdf.__file__,'policy':'R2.1',
 'maximum_public_reader_points':12,'maximum_tdx_pages_per_point':9,
 'maximum_official_query_pages_per_point':4,'automatic_retries':False,
 'server_discovery':False,'server':['110.41.147.114',7709],
 'recording_note':'TDX raw is complete parser-returned rows, not raw TCP bytes; official raw is original HTTP body.'}
for code,day,expected in samples:
 start=datetime.now(timezone.utc).isoformat();first=len(calls)
 try:
  r=fetch_historical_opening_evidence(code,day,tdx_reader=TdxOpeningReader(client_factory=factory),
    official_reader=OfficialOpeningReader(session=RecordedSession()))
  payload={'data':r.data,'metadata':r.metadata.to_dict()}
  entry={'instrument':code,'session_date':day,'expected':expected,'actual':r.data['opening_status'],
   'reason':r.data['reason'],'pass':r.data['opening_status']==expected,'request_start':first+1,'request_end':len(calls),
   'started_at':start,'result_file':f'{code}-{day}.json'}
 except Exception as exc:
  payload={'unhandled_error_type':type(exc).__name__}
  entry={'instrument':code,'session_date':day,'expected':expected,'actual':'ERROR','pass':False,'error_type':type(exc).__name__}
 (out/f'{code}-{day}.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
 results.append(entry)
 manifest.update(results=results,request_count=len(calls))
 (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps(entry,ensure_ascii=False),flush=True)
manifest['exit_code']=0 if all(r['pass'] for r in results) else 1
(out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
raise SystemExit(manifest['exit_code'])
