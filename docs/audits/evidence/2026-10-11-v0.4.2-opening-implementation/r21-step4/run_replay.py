"""Final-source replay of the NEW reader live bytes, never another live run."""
import hashlib
import json
import sys
from pathlib import Path
here=Path(__file__).resolve().parent;root=here.parents[1]/'chstockdata'
import chstockdata
import run_gate
run_gate.installed_identity('sios-candidate')

from chstockdata.opening_evidence import fetch_historical_opening_evidence,TdxOpeningReader,OfficialOpeningReader
live=here.parent/'r21-step1/live';out=here/(sys.argv[1] if len(sys.argv)>1 else 'final-replay');out.mkdir(exist_ok=True)
inputs=json.loads((live/'manifest.json').read_text(encoding='utf-8'))
calls=json.loads((live/'requests.json').read_text(encoding='utf-8'))
def raw(call):
 content=(live/call['raw_file']).read_bytes()
 assert hashlib.sha256(content).hexdigest()==call['sha256']
 return content
class Tdx:
 def __init__(self,entries):self.entries=list(entries);self.client=self
 def get_history_minute_time_data(self,market,code,date):
  c=self.entries.pop(0);assert c['request']=={'command':'0x0fb4','market':market,'code':code,'date':date}
  return json.loads(raw(c))
 def get_history_transaction_data(self,market,code,start,count,date):
  c=self.entries.pop(0);assert c['request']=={'command':'0x0fb5','market':market,'code':code,'date':date,'start':start,'count':count}
  return json.loads(raw(c))
 def close(self):pass
class Response:
 def __init__(self,c):self.content=raw(c);self.status_code=c['request']['http_status']
 def raise_for_status(self):assert self.status_code==200
class Http:
 def __init__(self,entries):self.entries=list(entries)
 def get(self,url,**kwargs):return self.call('GET',url,kwargs)
 def post(self,url,**kwargs):return self.call('POST',url,kwargs)
 def call(self,method,url,kwargs):
  c=self.entries.pop(0);r=c['request'];assert r['method']==method and r['url']==url
  for k in ('params','json','data'):assert r.get(k)==kwargs.get(k)
  return Response(c)
results=[]
for sample in inputs['results']:
 selected=calls[sample['request_start']-1:sample['request_end']]
 tdx=Tdx(c for c in selected if c['kind']=='tdx');http=Http(c for c in selected if c['kind']=='official')
 r=fetch_historical_opening_evidence(sample['instrument'],sample['session_date'],
     tdx_reader=TdxOpeningReader(client_factory=lambda **kw:tdx),official_reader=OfficialOpeningReader(session=http))
 assert not tdx.entries and not http.entries
 entry={'instrument':sample['instrument'],'session_date':sample['session_date'],
        'actual_live_status':sample['actual'],'final_replay_status':r.data['opening_status'],
        'pass':r.data['opening_status']==sample['expected']}
 results.append(entry)
 (out/sample['result_file']).write_text(json.dumps({'data':r.data,'metadata':r.metadata.to_dict()},ensure_ascii=False,indent=2),encoding='utf-8')
summary={'wheel_sha256':run_gate.sha(run_gate.WHEEL.read_bytes()),'installed_import':chstockdata.__file__,'purpose':'final installed-wheel replay of 74 actual NEW public reader responses; no network',
 'argv':sys.argv,'cwd':str(root),
 'actual_live_source_sha256':inputs['source_sha256'],
 'final_source_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest()
                       for p in (Path(chstockdata.__file__).parent/'opening_evidence.py',Path(chstockdata.__file__).parent/'opening_known_events.json')},
 'original_new_live_manifest_sha256':hashlib.sha256((live/'manifest.json').read_bytes()).hexdigest(),
 'results':results,'exit_code':0 if all(x['pass'] for x in results) else 1}
(out/'manifest.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
print(json.dumps(summary,indent=2))
raise SystemExit(summary['exit_code'])
