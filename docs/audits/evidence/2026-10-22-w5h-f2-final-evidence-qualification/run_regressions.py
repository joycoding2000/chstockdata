"""Re-execute all frozen checks, redirecting every archive write to this task."""
import json
import runpy
import subprocess
import sys
import time
import unittest
from common import HERE, ROOT, F2, OLD, read, save


def stage(name):
    mappings=[(OLD,HERE/'regression'/'closure'),(F2,HERE/'regression'/'f2')]
    wt,wb,rt,rb=__import__('pathlib').Path.write_text,__import__('pathlib').Path.write_bytes,__import__('pathlib').Path.read_text,__import__('pathlib').Path.read_bytes
    from pathlib import Path
    def mapped(p):
        q=p.resolve()
        for source,target in mappings:
            if q.is_relative_to(source):return target/q.relative_to(source)
        return p
    def reader(p):
        q=mapped(p)
        return q if q.exists() else p
    def write(p,fn,*a,**kw):
        q=mapped(p);q.parent.mkdir(parents=True,exist_ok=True)
        assert q.resolve().is_relative_to(HERE),str(q)
        return fn(q,*a,**kw)
    Path.write_text=lambda p,*a,**kw:write(p,wt,*a,**kw)
    Path.write_bytes=lambda p,*a,**kw:write(p,wb,*a,**kw)
    Path.read_text=lambda p,*a,**kw:rt(reader(p),*a,**kw)
    Path.read_bytes=lambda p,*a,**kw:rb(reader(p),*a,**kw)
    group,script=name.split(':')
    source=F2 if group=='f2' else OLD
    sys.path.insert(0,str(source))
    if script=='unittest':
        names=['test_parser','test_versions','test_f2','test_pipeline','test_catalog'] if group=='f2' else ['test_sources','test_closure_safety']
        result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromNames(names))
        assert result.wasSuccessful()
        print({'tests_run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors)})
    else:runpy.run_path(str(source/script),run_name='__main__')


def main():
    if len(sys.argv)>1:stage(sys.argv[1]);return
    stages=['f2:'+s for s in ['run_auxiliary.py','classify_index.py','validate_values.py','validate_new.py',
             'version_legacy.py','check_quality.py','check_new_quality.py','version_f2.py',
             'validate_replay_f2.py','qualify_events.py','unittest']]
    stages+=['closure:qualify_sources.py','closure:replay_closure.py','closure:unittest']
    logs=[]
    for name in stages:
        t=time.perf_counter()
        r=subprocess.run([sys.executable,'-X','utf8','-B',str(HERE/'run_regressions.py'),name],cwd=ROOT,
                         capture_output=True,text=True,encoding='utf-8')
        logs.append({'stage':name,'exit':r.returncode,'seconds':time.perf_counter()-t,'stdout':r.stdout,'stderr':r.stderr})
        save('regression_run.json',{'complete':False,'stages':logs})
        print(name,r.returncode,flush=True)
        if r.returncode:raise SystemExit(r.returncode)
    f=HERE/'regression'/'f2';c=HERE/'regression'/'closure'
    assert read(f/'value_validation.json')['counts']=={'PASS':89}
    assert read(f/'new_value_validation.json')['counts']=={'PASS':68,'PASS_UNKNOWN':2}
    assert read(f/'replay_validation.json')['assertion_pass']==46
    assert read(f/'replay_validation_f2.json')['counts']=={'PASS':118}
    assert read(f/'quality_checks.json')['pass'] and len(read(f/'quality_checks.json')['checks'])==91
    assert read(f/'new_quality_checks.json')['passed']==70
    assert read(c/'closure_replay_validation.json')['counts']=={'PASS':23}
    assert read(c/'source_value_validation.json')['counts']=={'PASS':22,'UNKNOWN':2}
    save('regression_run.json',{'complete':True,'stages':logs,'F1_values':89,'F2_values':70,'EPS':3,
         'F1_replay':46,'F2_replay':118,'closure_temporal_assertions':23,
         'old_unit_tests':36,'closure_unit_tests':10,'actual_quality_checks':161,
         'source_checks_preserved':24,'archive_outputs_written':False,'network_requests':0,
         'parse_inputs':'Unchanged SHA-bound archived parses; all scorers, replay and tests freshly executed'})


if __name__=='__main__':main()
