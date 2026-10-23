"""Path-only adaptation of the approved prior candidate Gate; no product edits."""
from pathlib import Path

WORK = Path('C:/Users/Administrator/.codex/visualizations/2026/10/10/01a125dd-33f2-78d3-abe7-45e0928975d0/v042-opening-implementation')
OUT = Path(__file__).resolve().parent
OLD = WORK / 'evidence/r21-step4'

for name in ('run_gate.py', 'run_static.py', 'dependencies.py', 'verify_artifacts.py', 'run_sios_tests.py', 'run_live.py', 'run_replay.py'):
    text = (OLD / name).read_text(encoding='utf-8')
    text = text.replace('WORK = OUT.parents[1]', 'WORK = Path(' + repr(WORK.as_posix()) + ')')
    text = text.replace('workspace=here.parents[1]', 'workspace=Path(' + repr(WORK.as_posix()) + ')')
    text = text.replace('W = HERE.parents[1]', 'W = Path(' + repr(WORK.as_posix()) + ')')
    text = text.replace("here=Path(__file__).resolve().parent;root=here.parents[1]/'chstockdata'", "here=Path(__file__).resolve().parent;root=Path(" + repr(WORK.as_posix()) + ")/'chstockdata-owner-rework'")
    text = text.replace('WORK / "chstockdata"', 'WORK / "chstockdata-owner-rework"')
    text = text.replace('W / "chstockdata"', 'W / "chstockdata-owner-rework"')
    text = text.replace('r21-qualified', 'owner-rework-r1').replace('r21-step4', 'owner-rework-r1-gate')
    text = text.replace('cache/r21-', 'cache/owner-rework-r1-')
    text = text.replace("cache/exact-probe", "cache/owner-rework-r1-exact-probe")
    text = text.replace('HERE / "final-live"', 'HERE / "live"')
    text = text.replace("live=here.parent/'r21-step1/live'", "live=run_gate.WORK/'evidence/r21-step1/live'")
    if name == 'run_gate.py':
        text = text.replace('".pytest_cache"))', '".pytest_cache",".ruff_cache"))')
        text = text.replace('ENV["PYTHONPYCACHEPREFIX"]', 'ENV["RUFF_CACHE_DIR"] = str(WORK / "cache/owner-rework-r1-ruff")\nENV["PYTHONPYCACHEPREFIX"]', 1)
        start = text.index('def prepare():')
        end = text.index('\ndef probe():', start)
        text = text[:start] + '''def prepare():
    approved = json.loads((OUT.parent/'rework-source-manifest.json').read_text(encoding='utf-8'))
    current = source_identity()
    assert current['working_tree_files'] == approved['source_files'], 'CH source differs from approved 765-file rework'
    assert current['working_tree_manifest_sha256'] == approved['canonical_files_sha256']
    save('candidate-source.json', current)
    sios = json.loads((OUT.parent/'sios-source-manifest.json').read_text(encoding='utf-8'))
    actual = manifest(SIOS, exclude=('var','__pycache__','.pytest_cache','.ruff_cache'))
    assert actual == sios['source_files_sha256'], 'SIOS full source changed'
    ta = json.loads((WORK/'evidence/r21-step4/consumer-identities.json').read_text(encoding='utf-8'))
    ta_actual = manifest(TA, exclude=('__pycache__','.pytest_cache','.ruff_cache'))
    assert ta_actual == ta['final_ta_source_manifest'], 'TA frozen source changed'
    frozen = Path('D:/Dev/Projects/chstockdata/build/v042-qualification/sios-baseline/var')
    before = manifest(frozen)
    assert manifest(SIOS/'var') == before, 'existing SIOS var differs from frozen'
    save('frozen-var-before.json', before)
    save('sios-var-before.json', manifest(SIOS/'var'))
    save('consumer-identities.json', {'sios': sios, 'sios_patch_sha256':sha((OUT.parent/'sios-source-vs-frozen.patch').read_bytes()), 'final_sios_source_manifest':actual, 'final_ta_source_manifest':ta_actual, 'ta_frozen_commit':'14673992b9cd1d8a74e514027843be3298e029c7', 'frozen_var_files':len(before), 'snapshot_gitless':True})
    print('Approved CH source, full 256-file SIOS, frozen TA and var verified', flush=True)

''' + text[end:]
        text = text.replace("    command('ta-pip-check',[python,'-m','pip','check'],cwd=TA,env=env,allowed=(0,1))\n", '')
        text = text.replace('"candidate_wheel_sha256": sha(WHEEL.read_bytes()) if WHEEL.exists() else None,', '"candidate_wheel_sha256": sha(WHEEL.read_bytes()) if WHEEL.exists() else None, "candidate_source_sha256": source_identity()["working_tree_manifest_sha256"], "sios_full_source_sha256": json.loads((OUT.parent/"sios-source-manifest.json").read_text(encoding="utf-8"))["source_manifest_sha256"], "sios_runtime_source_sha256": json.loads((OUT.parent/"sios-source-manifest.json").read_text(encoding="utf-8"))["runtime_source_sha256"], "sios_patch_sha256": sha((OUT.parent/"sios-source-vs-frozen.patch").read_bytes()),')
    if name == 'run_sios_tests.py':
        text = text.replace('result={"argv":', 'result={"sios_full_source_sha256":json.loads((here.parent/"sios-source-manifest.json").read_text(encoding="utf-8"))["source_manifest_sha256"],"sios_patch_sha256":run_gate.sha((here.parent/"sios-source-vs-frozen.patch").read_bytes()),"wheel_sha256":run_gate.sha(run_gate.WHEEL.read_bytes()),"argv":')
    if name == 'run_live.py':
        text = text.replace('"frozen_sios_commit":', '"sios_full_source_sha256": json.loads((HERE.parent/"sios-source-manifest.json").read_text(encoding="utf-8"))["source_manifest_sha256"],\n    "sios_runtime_source_sha256": json.loads((HERE.parent/"sios-source-manifest.json").read_text(encoding="utf-8"))["runtime_source_sha256"],\n    "sios_patch_sha256": sha((HERE.parent/"sios-source-vs-frozen.patch").read_bytes()),\n    "frozen_sios_commit":')
    (OUT / name).write_text(text, encoding='utf-8')
print('Prepared new isolated Gate runners')
