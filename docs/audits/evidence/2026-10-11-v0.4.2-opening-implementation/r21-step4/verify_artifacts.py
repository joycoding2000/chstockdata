import json,tarfile,zipfile,difflib,hashlib
from pathlib import Path
import run_gate as gate
identity=json.loads((gate.OUT/'candidate-source.json').read_text(encoding='utf-8'))
current=gate.source_identity()['working_tree_files']
assert all(current.get(n)==d for n,d in identity['working_tree_files'].items() if not n.startswith('.ruff_cache/')),'frozen source changed'
with zipfile.ZipFile(gate.WHEEL) as z:
    wheel={n:gate.sha(z.read(n)) for n in z.namelist() if not n.endswith('/')}
    assert {n.removeprefix('chstockdata/'):d for n,d in wheel.items() if n.startswith('chstockdata/')}==identity['package_files']
with tarfile.open(gate.SDIST) as t:
    sdist={m.name:gate.sha(t.extractfile(m).read()) for m in t.getmembers() if m.isfile()}
    fixtures={p.relative_to(gate.ROOT).as_posix():gate.sha(p.read_bytes()) for p in sorted((gate.ROOT/'tests/fixtures').rglob('*')) if p.is_file() and '__pycache__' not in p.parts}
    for n,d in fixtures.items():assert sdist['chstockdata-0.4.2/'+n]==d,n
    for n,d in identity['working_tree_files'].items():
        key='chstockdata-0.4.2/'+n
        if key in sdist:assert sdist[key]==d,n
    for n in ('opening_known_events.json','py.typed'):
        assert sdist['chstockdata-0.4.2/src/chstockdata/'+n]==wheel['chstockdata/'+n]==identity['package_files'][n]
gate.save('artifact-members.json',{'wheel_sha256':gate.sha(gate.WHEEL.read_bytes()),'sdist_sha256':gate.sha(gate.SDIST.read_bytes()),'wheel_members':wheel,'sdist_members':sdist,'fixtures':fixtures,'fixtures_all_match':len(fixtures),'source_stable':True})
baseline=json.loads((gate.WORK/'baseline.json').read_text(encoding='utf-8'))['chstockdata_before']
actual=identity['working_tree_files']
delta={n:{'baseline_sha256':baseline.get(n),'candidate_sha256':actual.get(n)} for n in sorted(set(baseline)|set(actual)) if baseline.get(n)!=actual.get(n)}
gate.save('source-vs-baseline.json',{'identity':'full_source_tree_sha256','base_commit':identity['base_commit'],'candidate_source_sha256':identity['working_tree_manifest_sha256'],'changes':delta,'packaging_fix':{'file':'MANIFEST.in','content':'recursive-include tests/fixtures *','root_cause':'default setuptools sdist includes test modules but omits their fixture data','preliminary_artifacts_retained':'dist/r21-unified','runtime_package_unchanged':True}})
with zipfile.ZipFile(gate.WORK/'chstockdata-before.zip') as archive:
    names=set(archive.namelist()); patch=[]
    for n in delta:
        p=gate.ROOT/n
        if not p.exists() or p.suffix not in ('.py','.toml','.md','.json','.in') and n!='MANIFEST.in':continue
        old=archive.read(n).decode('utf-8') if n in names else ''
        try:new=p.read_text(encoding='utf-8')
        except UnicodeDecodeError:continue
        patch.extend(difflib.unified_diff(old.splitlines(True),new.splitlines(True),'a/'+n,'b/'+n))
(gate.OUT/'source-vs-baseline.patch').write_text(''.join(patch),encoding='utf-8')
print(json.dumps({'wheel_members':len(wheel),'sdist_members':len(sdist),'fixture_members':len(fixtures),'source_sha256':identity['working_tree_manifest_sha256'],'wheel_sha256':gate.sha(gate.WHEEL.read_bytes()),'status':'PASS'},indent=2))
