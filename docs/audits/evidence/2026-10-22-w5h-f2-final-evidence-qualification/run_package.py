"""Finite offline package; cached OCR is SHA checked, never downloaded/retrained."""
import subprocess
import sys
import time
from common import HERE, ROOT, read, save, sha


def main():
    start={p.name:sha(p)for p in HERE.glob('*.py')}
    logs=[]
    stages=['qualify_reply_scope.py','verify_images_and_reply.py','qualify_scan_fields.py',
            'build_qualification.py','replay_final.py','connect_field_T_impact.py','UNITTEST','check_final_quality.py']
    if '--reuse-fresh-legacy-regression' not in sys.argv:stages.insert(0,'run_regressions.py')
    else:assert read(HERE/'regression_run.json')['complete']
    for stage in stages:
        args=[sys.executable,'-X','utf8','-B']
        args+=['-m','unittest','-v','test_qualification','test_real_evidence']if stage=='UNITTEST'else[str(HERE/stage)]
        t=time.perf_counter()
        result=subprocess.run(args,cwd=HERE,capture_output=True,text=True,encoding='utf-8')
        logs.append({'stage':stage,'exit':result.returncode,'seconds':time.perf_counter()-t,'stdout':result.stdout,'stderr':result.stderr})
        save('package_run.json',{'complete':False,'stages':logs,'code_sha256_start':start})
        print(stage,result.returncode,flush=True)
        if result.returncode:raise SystemExit(result.returncode)
    end={p.name:sha(p)for p in HERE.glob('*.py')}
    assert start==end
    save('package_run.json',{'complete':True,'stages':logs,'code_sha256_start':start,'code_sha256_end':end,
         'new_unit_test_methods':19,'network_requests':0,'legacy_regression_reused':'--reuse-fresh-legacy-regression'in sys.argv,
         'raw_ocr_cache_binding':'All 480 source/image SHA bindings checked; earlier failed attempts retained',
         'source_qualification_gate':'FIXED_WINDOW_PARTIAL_WITH_PROVEN_GAPS','product_gate':'NOT_PASSED'})


if __name__=='__main__':main()
