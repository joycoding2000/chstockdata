"""Git-less snapshot harness; original static contract and candidate ROOT unchanged."""
import difflib,hashlib,importlib.util,json,subprocess,sys
from pathlib import Path
import run_gate as gate
spec=importlib.util.spec_from_file_location('candidate_rh1_static',gate.ROOT/'scripts/check_rh1_static.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
repo=Path('D:/Dev/Projects/chstockdata')
entries=[line.split('\t',1) for line in gate.git(repo,'ls-tree','-r','-z',module.BASELINE_SHA,'--','src','tests').decode().split('\0') if line]
raw=subprocess.check_output(['git','-c','safe.directory='+repo.as_posix(),'-C',str(repo),'cat-file','--batch'],input=('\n'.join(info.split()[2] for info,_ in entries)+'\n').encode(),env=gate.ENV)
offset=0;baseline={};baseline_hashes={}
for info,name in entries:
    end=raw.index(b'\n',offset);blob,kind,length=raw[offset:end].split();length=int(length)
    data=raw[end+1:end+1+length]
    assert kind==b'blob' and blob.decode()==info.split()[2]
    assert hashlib.sha1(b'blob '+str(length).encode()+b'\0'+data).hexdigest()==blob.decode()
    baseline[name]=data;baseline_hashes[name]={'git_blob':blob.decode(),'sha256':gate.sha(data)}
    offset=end+1+length+1
assert offset==len(raw)
ranges={};candidate_hashes={}
for folder in ('src','tests'):
    for p in sorted((gate.ROOT/folder).rglob('*.py')):
        name=p.relative_to(gate.ROOT).as_posix();data=p.read_bytes();candidate_hashes[name]=gate.sha(data)
        old=baseline.get(name)
        if old is None:ranges[name]=[(1,2**31-1)];continue
        matcher=difflib.SequenceMatcher(None,old.decode('utf-8').splitlines(),data.decode('utf-8').splitlines(),autojunk=False)
        added=[(j1+1,j2) for tag,i1,i2,j1,j2 in matcher.get_opcodes() if tag in ('insert','replace') and j2>j1]
        if added:ranges[name]=added
original_run=module._run
def run(*args):
    if args[:3]==('git','cat-file','-e'):
        return subprocess.run(['git','-c','safe.directory='+repo.as_posix(),'-C',str(repo),*args[1:]],env=gate.ENV,capture_output=True,text=True,encoding='utf-8')
    return original_run(*args)
module._run=run
module._added_line_ranges=lambda:ranges
assert module.ROOT==gate.ROOT
gate.save('static-gitless-injection.json',{'test_only_injection':['_run:git cat-file baseline existence','_added_line_ranges:exact baseline blobs to candidate source via SequenceMatcher'],
  'production_script_unchanged':True,'candidate_root':str(module.ROOT),'baseline_commit':module.BASELINE_SHA,'baseline_files':baseline_hashes,'candidate_files':candidate_hashes,'added_line_ranges':ranges,
  'runner_sha256':gate.sha(Path(__file__).read_bytes()),'script_sha256':gate.sha((gate.ROOT/'scripts/check_rh1_static.py').read_bytes())})
raise SystemExit(module.main())
