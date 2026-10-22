"""Replay unchanged F2 checks with every generated file redirected to this evidence."""
import hashlib,json,runpy,subprocess,sys,time,unittest
from pathlib import Path
HERE=Path(__file__).resolve().parent
F2=HERE.parent/'2026-10-21-w5h-f2'
DEST=HERE/'regression'

def stage(name):
    DEST.mkdir(exist_ok=True)
    wt,wb,rt,rb=Path.write_text,Path.write_bytes,Path.read_text,Path.read_bytes
    def mapped(p):
        p=p.resolve()
        return DEST/p.relative_to(F2) if p.is_relative_to(F2) else p
    def readpath(p):
        other=mapped(p)
        return other if other!=p.resolve() and other.exists() else p
    def write_text(p,*a,**kw):
        q=mapped(p);q.parent.mkdir(parents=True,exist_ok=True);return wt(q,*a,**kw)
    def write_bytes(p,*a,**kw):
        q=mapped(p);q.parent.mkdir(parents=True,exist_ok=True);return wb(q,*a,**kw)
    Path.write_text=write_text;Path.write_bytes=write_bytes
    Path.read_text=lambda p,*a,**kw:rt(readpath(p),*a,**kw)
    Path.read_bytes=lambda p,*a,**kw:rb(readpath(p),*a,**kw)
    sys.path.insert(0,str(F2))
    if name=='unittest':
        suite=unittest.defaultTestLoader.loadTestsFromNames(['test_parser','test_versions','test_f2','test_pipeline','test_catalog'])
        result=unittest.TextTestRunner(verbosity=2).run(suite)
        if not result.wasSuccessful(): raise SystemExit(1)
    else:
        runpy.run_path(str(F2/name),run_name='__main__')


def main():
    if len(sys.argv)>1:
        stage(sys.argv[1]);return
    scripts=['run_auxiliary.py','classify_index.py','validate_values.py','validate_new.py',
             'version_legacy.py','check_quality.py','check_new_quality.py','version_f2.py',
             'validate_replay_f2.py','qualify_events.py','unittest']
    logs=[]
    for s in scripts:
        t=time.perf_counter()
        r=subprocess.run([sys.executable,'-X','utf8','-B',str(__file__),s],capture_output=True,text=True,encoding='utf-8')
        logs.append({'stage':s,'machine_seconds':time.perf_counter()-t,'exit':r.returncode,'stdout':r.stdout,'stderr':r.stderr})
        (HERE/'regression_run.json').write_text(json.dumps({'complete':False,'stages':logs},ensure_ascii=False,indent=2),encoding='utf-8')
        print({'stage':s,'exit':r.returncode},flush=True)
        if r.returncode: raise SystemExit(r.returncode)
    load=lambda n:json.loads((DEST/n).read_text(encoding='utf-8'))
    assert load('value_validation.json')['counts']=={'PASS':89}
    assert load('new_value_validation.json')['counts']=={'PASS':68,'PASS_UNKNOWN':2}
    assert load('replay_validation.json')['assertion_pass']==46
    assert load('replay_validation_f2.json')['counts']=={'PASS':118}
    assert load('quality_checks.json')['pass'] and len(load('quality_checks.json')['checks'])==91
    assert load('new_quality_checks.json')['passed']==70
    (HERE/'regression_run.json').write_text(json.dumps({'complete':True,'stages':logs,
       'inputs':'Unchanged SHA-bound archived parses; original 36 tests re-executed; output redirected',
       'old_money':89,'new_money':70,'eps':3,'old_replay':46,'f2_replay':118,'quality':161},ensure_ascii=False,indent=2),encoding='utf-8')

if __name__=='__main__':main()
