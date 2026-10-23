"""Independent frozen-source oracle for legacy v2 bytes and dataset digest."""
import hashlib,json,sys,types,zipfile,difflib
from pathlib import Path
here=Path(__file__).resolve().parent;workspace=here.parents[1];root=workspace/"systematic-investing-os"
sys.path[:0]=[str(root/"src"),str(root/"tests/integration")]
import test_snapshot_replay as helper
from systematic_investing.data.quality import CanonicalDataset
from systematic_investing.data.snapshots import SnapshotReader,SnapshotWriter,manifest_to_dict
source_before={p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((root/"src").rglob("*.py"))}
def frozen(name,source):
    module=types.ModuleType(name);sys.modules[name]=module;exec(compile(source,name,"exec"),module.__dict__);return module
with zipfile.ZipFile(workspace/"sios-frozen.zip") as archive:
    old_quality=frozen("step2_frozen_quality",archive.read("src/systematic_investing/data/quality.py").decode("utf-8"))
    old_snapshots=frozen("step2_frozen_snapshots",archive.read("src/systematic_investing/data/snapshots.py").decode("utf-8"))
    changes={}
    diff=[]
    for path in sorted((root/"src").rglob("*.py")):
        name=path.relative_to(root).as_posix();current=path.read_text(encoding="utf-8")
        original_bytes=archive.read(name) if name in archive.namelist() else b""
        original=original_bytes.decode("utf-8").replace("\r\n","\n")
        if current!=original:
            changes[name]={"frozen_sha256":hashlib.sha256(original_bytes).hexdigest() if original_bytes else None,"current_sha256":hashlib.sha256(path.read_bytes()).hexdigest()}
            diff.extend(difflib.unified_diff(original.splitlines(keepends=True),current.splitlines(keepends=True),fromfile="frozen/"+name,tofile="current/"+name))
(here/"source-vs-frozen.diff").write_text("".join(diff),encoding="utf-8")
base=helper.dataset()
old=old_quality.CanonicalDataset(daily_bars=base.daily_bars,sessions=base.sessions,tradability=base.tradability,corporate_actions=base.corporate_actions,rule_candidates=base.rule_candidates)
assert old.content_digest()==base.content_digest()
# New run-specific directories, no old evidence overwrite.
import tempfile
with tempfile.TemporaryDirectory(dir=here,prefix="frozen-v2-") as temp:
    directory=Path(temp)
    args=dict(created_at=helper.CREATED_AT,knowledge_cutoff=helper.KNOWLEDGE_CUTOFF,retrieved_at=helper.RETRIEVED_AT)
    old_manifest=old_snapshots.SnapshotWriter("chstockdata","commit-review-1","0.1.0").persist(old,snapshot_dir=directory/"frozen",**args)
    new_manifest=helper.writer().persist(base,snapshot_dir=directory/"current",**args)
    assert old_manifest.snapshot_id==new_manifest.snapshot_id
    hashes={}
    for file in sorted((directory/"frozen").rglob("*")):
        if file.is_file():
            name=file.relative_to(directory/"frozen").as_posix()
            assert file.read_bytes()==(directory/"current"/name).read_bytes(),name
            hashes[name]=hashlib.sha256(file.read_bytes()).hexdigest()
    loaded,dataset=SnapshotReader().load(directory/"frozen")
    assert dataset.content_digest()==base.content_digest() and loaded.snapshot_id==old_manifest.snapshot_id
    legacy_loaded,legacy_dataset=old_snapshots.SnapshotReader().load(directory/"current")
    assert legacy_dataset.content_digest()==base.content_digest()
source_after={p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((root/"src").rglob("*.py"))}
assert source_before==source_after
result={"argv":sys.argv,"cwd":str(Path.cwd()),"frozen_commit":"84fd54fae0740bc06b1d250afa4578be29556956","frozen_archive_sha256":hashlib.sha256((workspace/"sios-frozen.zip").read_bytes()).hexdigest(),"legacy_dataset_digest":base.content_digest(),"legacy_snapshot_id":new_manifest.snapshot_id,"all_v2_bytes_equal":True,"legacy_to_new_reader":True,"new_v2_to_legacy_reader":True,"v2_file_sha256":hashes,"changed_source_files":changes,"source_stable_during_run":True,"exit_code":0}
(here/"frozen-compat.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
print(json.dumps({"legacy_snapshot_id":new_manifest.snapshot_id,"all_v2_bytes_equal":True,"changed_runtime_files":len(changes)},indent=2))
