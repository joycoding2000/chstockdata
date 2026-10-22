"""Reproduce bounded offline qualification; never fetch, commit or push."""
import hashlib,json,subprocess,sys,time
from pathlib import Path
HERE=Path(__file__).resolve().parent

def main():
    start={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in HERE.glob('*.py')}
    logs=[]
    stages=[['test_sources.py'],['qualify_sources.py'],['replay_closure.py'],['test_closure_safety.py']]
    if '--reuse-f2-regression' not in sys.argv:stages.append(['run_regression.py'])
    else:assert json.loads((HERE/'regression_run.json').read_text(encoding='utf-8'))['complete']
    for args in stages:
        t=time.perf_counter();r=subprocess.run([sys.executable,'-X','utf8','-B',*args],cwd=HERE,capture_output=True,text=True,encoding='utf-8')
        logs.append({'args':args,'exit':r.returncode,'machine_seconds':time.perf_counter()-t,'stdout':r.stdout,'stderr':r.stderr})
        (HERE/'closure_package_run.json').write_text(json.dumps({'complete':False,'stages':logs},ensure_ascii=False,indent=2),encoding='utf-8')
        print({'stage':args,'exit':r.returncode},flush=True)
        if r.returncode:raise SystemExit(r.returncode)
    end={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in HERE.glob('*.py')}
    assert start==end
    (HERE/'closure_package_run.json').write_text(json.dumps({'complete':True,'code_sha256_start':start,
       'code_sha256_end':end,'stages':logs,'network_requests':0,
       'old_regression_reused':'--reuse-f2-regression' in sys.argv},ensure_ascii=False,indent=2),encoding='utf-8')

if __name__=='__main__':main()
