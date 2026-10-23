import hashlib
import importlib.metadata
import json
import os
import subprocess
import sys
from pathlib import Path

here=Path(__file__).resolve().parent
root=here.parents[1]/'chstockdata'
bundled=Path('C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/Lib/site-packages')
sys.path.append(str(bundled))
import pypdf
phase=sys.argv[1]
tests=sys.argv[2:]
args=['-q','-p','no:cacheprovider',f'--junitxml={here/ (phase+".xml")}',*tests]
env=dict(os.environ,PYTHONPATH=str(root/'src'),PYTHONDONTWRITEBYTECODE='1')
code='import sys;sys.path.append('+repr(str(bundled))+');import pytest;raise SystemExit(pytest.main('+repr(args)+'))'
argv=[sys.executable,'-B','-c',code]
record={'argv':argv,'cwd':str(root),'env':{k:env[k] for k in ('PYTHONPATH','PYTHONDONTWRITEBYTECODE')},
 'dependency_versions':{k:importlib.metadata.version(k) for k in ('pytest','requests','pandas','mootdx','tdxpy')},
 'pypdf_version':pypdf.__version__,'pypdf_path':pypdf.__file__,
 'source_sha256':{p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in [root/'src/chstockdata/opening_evidence.py',root/'src/chstockdata/opening_known_events.json',root/'src/chstockdata/__init__.py',root/'tests/test_historical_opening_evidence.py']}}
with (here/(phase+'.log')).open('w',encoding='utf-8') as log:
 result=subprocess.run(argv,cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT)
record['exit_code']=result.returncode
(here/(phase+'.command.json')).write_text(json.dumps(record,indent=2),encoding='utf-8')
(here/(phase+'.exit')).write_text(str(result.returncode)+'\n',encoding='utf-8')
print((here/(phase+'.log')).read_text(encoding='utf-8'))
raise SystemExit(result.returncode)
