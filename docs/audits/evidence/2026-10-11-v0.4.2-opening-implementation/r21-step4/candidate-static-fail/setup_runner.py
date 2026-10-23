"""Prepare isolated Step4 runner from read-only prior command helpers."""
from pathlib import Path
W=Path(__file__).resolve().parents[2]
E=Path(__file__).resolve().parent
old=Path('D:/Dev/Projects/chstockdata/docs/audits/evidence/2026-10-09-v0.4.2-unified-gate/run_gate.py').read_text(encoding='utf-8')
prefix=old.split('def prepare():')[0]
start=prefix.index('OUT = ')
end=prefix.index('\n\ndef sha')
prefix=prefix[:start]+'''OUT = Path(__file__).resolve().parent
WORK = OUT.parents[1]
ROOT = WORK / "chstockdata"
SIOS = WORK / "systematic-investing-os"
TA = WORK / "TradingAgents-AStock-Private"
DIST = WORK / "dist/r21-final"
PROFILES = WORK / "profiles/r21-final"
GATE = Path("D:/Dev/Projects/chstockdata/build/v042-qualification/gate/Scripts/python.exe")
DATA = Path("D:/Dev/Projects/chstockdata/.rh3a2-vipdoc")
WHEEL = DIST / "chstockdata-0.4.2-py3-none-any.whl"
SDIST = DIST / "chstockdata-0.4.2.tar.gz"
ENV = dict(os.environ, PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1", PYTEST_DISABLE_PLUGIN_AUTOLOAD="1")
ENV.pop("PYTHONPATH",None)
ENV["TEMP"] = ENV["TMP"] = str(WORK / "temp/r21-step4")
ENV["PIP_CACHE_DIR"] = str(WORK / "cache/r21-pip")
ENV["PYTHONPYCACHEPREFIX"] = str(WORK / "cache/r21-pycache")
ENV["CHSTOCKDATA_CACHE_DIR"] = str(WORK / "cache/r21-data")
for path in (OUT,DIST,PROFILES,Path(ENV["TEMP"]),Path(ENV["PIP_CACHE_DIR"]),Path(ENV["PYTHONPYCACHEPREFIX"]),Path(ENV["CHSTOCKDATA_CACHE_DIR"])):
    path.mkdir(parents=True,exist_ok=True)
''' + prefix[end:]
prefix=prefix.replace('journal = "package-install-commands.json" if sys.argv[1] == "packages" else "commands.json"','journal = "commands.json"')
prefix=prefix.replace('"candidate_wheel_sha256": sha(WHEEL.read_bytes()) if WHEEL.exists() else None,','"candidate_wheel_sha256": sha(WHEEL.read_bytes()) if WHEEL.exists() else None, "log": name + ".log", "exit_file": name + ".exit", "command_started_at": started, "command_finished_at": datetime.now().astimezone().isoformat(),')
prefix=prefix.replace('    result = subprocess.run(', '    started = datetime.now().astimezone().isoformat()\n    result = subprocess.run(')
prefix=prefix.replace('    records = json.loads((OUT / journal).read_text(encoding="utf-8")) if (OUT / journal).exists() else []','    records = []')
prefix=prefix.replace('    save(journal, records)','    save(name + ".command.json", records[0])')
# Source identity uses a complete byte manifest; the snapshot is not a Git commit.
si_start=prefix.index('def source_identity():')
si_end=prefix.index('\n\ndef export',si_start)
prefix=prefix[:si_start]+'''def source_identity():
    files = manifest(ROOT,exclude=("__pycache__","build","chstockdata.egg-info",".pytest_cache"))
    baseline=json.loads((WORK/"baseline.json").read_text(encoding="utf-8"))
    return {"identity_kind":"source_tree_sha256", "not_a_git_commit":True,
        "base_commit":baseline["chstockdata_head"], "original_working_tree_status":baseline["chstockdata_status_before"],
        "working_tree_files":files,"working_tree_manifest_sha256":sha(json.dumps(files,sort_keys=True).encode()),
        "package_files":manifest(ROOT/"src/chstockdata",exclude=("__pycache__",))}
''' + prefix[si_end:]
kept=old[old.index('def build():'):old.index('def probe():')]
kept=kept.replace('command(profile + "-install", [python, "-m", "pip", "install",', 'command(profile + "-install", [python, "-m", "pip", "install",')
kept=kept.replace('[GATE, "-m", "pip", "freeze"]','[GATE, OUT/"dependencies.py"]')
kept=kept.replace('    command(profile + "-create",', '    if (target/"Scripts/python.exe").exists() and (OUT/(profile+"-install.exit")).exists() and (OUT/(profile+"-install.exit")).read_text(encoding="utf-8").strip()=="0":\n        return target/"Scripts/python.exe"\n    command(profile + "-create",')
(E/'run_gate.py').write_text(prefix+kept+(E/'runner_tail.py').read_text(encoding='utf-8'),encoding='utf-8')
# Preserve source-independent test identity injection, without source CH import.
test= (W/'evidence/r21-step2/run_tests.py').read_text(encoding='utf-8')
test=test.replace('str(root/"src"),str(workspace/"chstockdata/src")','str(root/"src")')
test=test.replace('str(here/"tmp")','str(here/(name+"-tmp"))')
test=test.replace('import pytest\nname=sys.argv[1]','import chstockdata\nimport run_gate\nrun_gate.installed_identity("sios-candidate")\nimport pytest\nname=sys.argv[1]')
(E/'run_sios_tests.py').write_text(test,encoding='utf-8')
live=(W/'evidence/r21-step3/run_live.py').read_text(encoding='utf-8')
live=live.replace('sys.path.append(str(RUNTIME))  # Optional pypdf only; installed candidate dependencies keep precedence.','')
live=live.replace('"chstockdata": CH / "src/chstockdata"','"chstockdata": Path(__import__("chstockdata").__file__).parent')
live=live.replace('"candidate_artifact": "source prebuild; wheel NOT_BUILT in Step3",','"candidate_artifact": str(W / "dist/r21-final/chstockdata-0.4.2-py3-none-any.whl"),\n    "wheel_sha256": sha((W / "dist/r21-final/chstockdata-0.4.2-py3-none-any.whl").read_bytes()),')
live=live.replace('import chstockdata\nimport requests','import chstockdata\nimport run_gate\nrun_gate.installed_identity("sios-candidate")\nimport requests')
(E/'run_live.py').write_text(live,encoding='utf-8')
print('isolated runner prepared')

