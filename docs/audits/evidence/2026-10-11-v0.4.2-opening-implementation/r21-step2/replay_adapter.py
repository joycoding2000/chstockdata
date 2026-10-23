"""Replay 74 actual Step1 responses through real CH 0.4.2 and SIOS bridge."""
import hashlib,json,sys,functools
from pathlib import Path
from datetime import UTC,datetime,date
from types import SimpleNamespace
from dataclasses import asdict
here=Path(__file__).resolve().parent;workspace=here.parents[1]
root=workspace/"systematic-investing-os";ch=workspace/"chstockdata"
sys.path[:0]=[str(root/"src"),str(ch/"src")]
sys.path.append("C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/Lib/site-packages")
import chstockdata
from chstockdata.opening_evidence import fetch_historical_opening_evidence,TdxOpeningReader,OfficialOpeningReader
from systematic_investing.adapters.chstockdata.provider import LibraryChStockDataClient,ChStockDataProvider
from systematic_investing.data.ports import HistoricalOpeningRequest
from systematic_investing.domain.identifiers import InstrumentId
live=workspace/"evidence/r21-step1/live"
inputs=json.loads((live/"manifest.json").read_text(encoding="utf-8"))
calls=json.loads((live/"requests.json").read_text(encoding="utf-8"))
def raw(call):
    content=(live/call["raw_file"]).read_bytes()
    assert hashlib.sha256(content).hexdigest()==call["sha256"]
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

source_before={str(p.relative_to(workspace)):hashlib.sha256(p.read_bytes()).hexdigest() for directory in (root/"src",ch/"src") for p in sorted(directory.rglob("*.py"))}
results=[];started=datetime.now(UTC).isoformat()
for sample in inputs["results"]:
    selected=calls[sample["request_start"]-1:sample["request_end"]]
    tdx=Tdx(c for c in selected if c["kind"]=="tdx");http=Http(c for c in selected if c["kind"]=="official")
    # Real library function with recorded transport injection; no network.
    boundary=SimpleNamespace(__version__=chstockdata.__version__,fetch_historical_opening_evidence=functools.partial(fetch_historical_opening_evidence,tdx_reader=TdxOpeningReader(client_factory=lambda **kw:tdx),official_reader=OfficialOpeningReader(session=http)))
    client=LibraryChStockDataClient(library=boundary,historical_opening_candidate=True)
    provider=ChStockDataProvider(client=client,clock=lambda:datetime.now(UTC))
    symbol=sample["instrument"];instrument=InstrumentId.parse(("XSHG:" if symbol.startswith(("5","6")) else "XSHE:")+symbol)
    response=provider.fetch_historical_opening_evidence(HistoricalOpeningRequest((instrument,),date.fromisoformat(sample["session_date"])))
    assert response.is_success, response
    fact=response.records[0]
    assert not tdx.entries and not http.entries
    assert fact.opening_status==sample["expected"]
    results.append({"instrument":str(instrument),"session_date":sample["session_date"],"status":fact.opening_status,"source_evidence_hash":fact.evidence_hash,"canonical_payload_sha256":hashlib.sha256(fact.payload_json.encode("utf-8")).hexdigest(),"provider_evidence":asdict(response.evidence),"pass":True})
source_after={str(p.relative_to(workspace)):hashlib.sha256(p.read_bytes()).hexdigest() for directory in (root/"src",ch/"src") for p in sorted(directory.rglob("*.py"))}
assert source_before==source_after
result={"argv":sys.argv,"cwd":str(Path.cwd()),"started_at":started,"finished_at":datetime.now(UTC).isoformat(),"purpose":"offline replay of 74 actual NEW Step1 public reader transport responses through real library/client/provider/domain; no new live claim","library_version":chstockdata.__version__,"library_import_path":chstockdata.__file__,"source_function":fetch_historical_opening_evidence.__module__+"."+fetch_historical_opening_evidence.__name__,"source_files_sha256":source_before,"source_stable_during_run":True,"results":results,"exit_code":0}
(here/"replay-adapter-final.json").write_text(json.dumps(result,ensure_ascii=False,indent=2,default=lambda value:value.isoformat()),encoding="utf-8")
print(json.dumps({"count":len(results),"all_pass":True,"library_version":chstockdata.__version__},indent=2))
