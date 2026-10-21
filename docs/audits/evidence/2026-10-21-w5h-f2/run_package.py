"""One fixed offline regression package. No network, installs, git or production I/O."""
import hashlib
import importlib.util
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parent


def main():
    missing = [n for n in ('pdfplumber','pypdf') if importlib.util.find_spec(n) is None]
    if missing:
        raise SystemExit('Use the existing research Python environment with '+', '.join(missing)+'. No dependencies installed by this script.')
    scripts = ['run_parse.py','parse_new.py','run_auxiliary.py','classify_index.py',
               'validate_values.py','validate_new.py','version_legacy.py','check_quality.py',
               'check_new_quality.py','version_f2.py','validate_replay_f2.py','qualify_events.py']
    reuse = '--reuse-parses' in sys.argv
    if reuse:
        old = json.loads((OUT/'parsed.json').read_text(encoding='utf-8'))
        new = json.loads((OUT/'new_parsed.json').read_text(encoding='utf-8'))
        code = hashlib.sha256((OUT/'parser_f2.py').read_bytes()).hexdigest()
        extra = hashlib.sha256((OUT/'offline_extras.py').read_bytes()).hexdigest()
        assert old['parser_sha256_at_start']==old['parser_sha256_at_end']==code
        assert new['code_sha256_start']==new['code_sha256_end']==code
        assert new['extra_code_sha256_start']==new['extra_code_sha256_end']==extra
        scripts = scripts[2:]
    code_start = {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in OUT.glob('*.py')}
    logs = []
    for args in [[n] for n in scripts]+[['-m','unittest','test_parser','test_versions','test_f2','test_pipeline','test_catalog']]:
        start = time.perf_counter()
        r = subprocess.run([sys.executable,'-X','utf8','-B',*args],cwd=OUT,capture_output=True,
                           text=True,encoding='utf-8',check=False)
        logs.append({'args':args,'elapsed_seconds':time.perf_counter()-start,
                     'exit_code':r.returncode,'stdout':r.stdout,'stderr':r.stderr})
        print(json.dumps({'stage':args,'exit':r.returncode,'seconds':logs[-1]['elapsed_seconds']}),flush=True)
        (OUT/'package_run.json').write_text(json.dumps({'finished_at_utc':datetime.now(timezone.utc).isoformat(),
            'code_sha256_start':code_start,'stages':logs,'complete':False},ensure_ascii=False,indent=2),encoding='utf-8')
        if r.returncode:
            raise SystemExit(r.returncode)
    end = {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in OUT.glob('*.py')}
    assert code_start==end, 'Code changed during package run'
    (OUT/'package_run.json').write_text(json.dumps({'finished_at_utc':datetime.now(timezone.utc).isoformat(),
        'code_sha256_start':code_start,'code_sha256_end':end,'stages':logs,
        'complete':True,'no_network':True,'reused_unchanged_pdf_parses':reuse},ensure_ascii=False,indent=2),encoding='utf-8')


if __name__ == '__main__':
    main()
