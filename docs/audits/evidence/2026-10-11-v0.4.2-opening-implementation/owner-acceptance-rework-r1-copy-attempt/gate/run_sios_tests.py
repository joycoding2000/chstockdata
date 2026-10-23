"""Explicit test-only source identity for frozen .git-less export."""
import hashlib,json,os,sys,time
from datetime import UTC,datetime
from pathlib import Path
here=Path(__file__).resolve().parent
workspace=Path('C:/Users/Administrator/.codex/visualizations/2026/10/10/01a125dd-33f2-78d3-abe7-45e0928975d0/v042-opening-implementation')
root=workspace/"systematic-investing-os"
os.chdir(root)
sys.path[:0]=[str(root/"src")]
os.environ.update(PYTHONDONTWRITEBYTECODE="1",PYTHONUTF8="1",PYTEST_DISABLE_PLUGIN_AUTOLOAD="1")
files={p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((root/"src").rglob("*.py"))}
tree=hashlib.sha256(json.dumps(files,sort_keys=True,separators=(",",":")).encode("utf-8")).hexdigest()
import systematic_investing.research.runner as runner
import systematic_investing.research.oos as oos
identity="source_tree_sha256:"+tree
# Only test process; production resolve_code_commit stays unchanged.
runner.resolve_code_commit=lambda:identity
oos.resolve_code_commit=lambda:identity
import chstockdata
import run_gate
run_gate.installed_identity("sios-candidate")
import pytest
name=sys.argv[1]
args=sys.argv[2:]+["-q","-p","no:cacheprovider","--basetemp",str(here/(name+"-tmp")),"--junitxml",str(here/(name+".xml"))]
started=datetime.now(UTC).isoformat()
code=pytest.main(args)
files_after={p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((root/"src").rglob("*.py"))}
source_stable=files_after==files
if not source_stable: code=1
result={"sios_full_source_sha256":json.loads((here.parent/"sios-source-manifest.json").read_text(encoding="utf-8"))["source_manifest_sha256"],"sios_patch_sha256":run_gate.sha((here.parent/"sios-source-vs-frozen.patch").read_bytes()),"wheel_sha256":run_gate.sha(run_gate.WHEEL.read_bytes()),"argv":sys.argv,"pytest_argv":args,"cwd":str(root),"env":{"PYTHONPATH":sys.path[:2],"PYTHONDONTWRITEBYTECODE":"1","PYTHONUTF8":"1","PYTEST_DISABLE_PLUGIN_AUTOLOAD":"1"},"test_only_identity_injection_points":["research.runner.resolve_code_commit","research.oos.resolve_code_commit"],"identity_label":"source_tree_sha256","source_tree_sha256":tree,"source_files_sha256":files,"source_files_sha256_after":files_after,"source_stable_during_run":source_stable,"started_at":started,"finished_at":datetime.now(UTC).isoformat(),"exit_code":int(code)}
(here/(name+".json")).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
(here/(name+".exit")).write_text(str(int(code)),encoding="utf-8")
raise SystemExit(code)
