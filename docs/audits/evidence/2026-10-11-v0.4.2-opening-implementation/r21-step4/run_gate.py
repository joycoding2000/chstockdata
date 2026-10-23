"""One immutable candidate, isolated consumers, recorded commands; no publication."""
import difflib
import hashlib
import importlib.util
import json
import os
import shutil
import struct
import subprocess
import sys
import tarfile
import xml.etree.ElementTree as ET
import zipfile
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

OUT = Path(__file__).resolve().parent
WORK = OUT.parents[1]
ROOT = WORK / "chstockdata"
SIOS = WORK / "systematic-investing-os"
TA = WORK / "TradingAgents-AStock-Private"
DIST = WORK / "dist/r21-qualified"
PROFILES = WORK / "profiles/r21-qualified"
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


def sha(data):
    return hashlib.sha256(data).hexdigest()


def save(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def command(name, argv, cwd=ROOT, env=None, allowed=(0,)):
    started = datetime.now().astimezone().isoformat()
    result = subprocess.run([str(a) for a in argv], cwd=cwd, env=env or ENV, capture_output=True, text=True, encoding="utf-8", errors="replace")
    (OUT / (name + ".log")).write_text(result.stdout + result.stderr, encoding="utf-8")
    (OUT / (name + ".exit")).write_text(str(result.returncode) + "\n", encoding="utf-8")
    journal = "commands.json"
    records = []
    records.append({"name": name, "argv": [str(a) for a in argv], "cwd": str(cwd), "exit": result.returncode,
                    "candidate_wheel_sha256": sha(WHEEL.read_bytes()) if WHEEL.exists() else None, "log": name + ".log", "exit_file": name + ".exit", "command_started_at": started, "command_finished_at": datetime.now().astimezone().isoformat(),
                    "environment_overrides": {key: (env or ENV).get(key) for key in ("PYTHONPATH", "PYTHONUTF8", "PYTEST_DISABLE_PLUGIN_AUTOLOAD", "SIOS_CHSTOCKDATA_LIVE_QUALIFICATION", "CHSTOCKDATA_VIPDOC_HISTORY_DIR", "CHSTOCKDATA_CACHE_DIR", "TEMP", "TMP")}})
    save(name + ".command.json", records[0])
    print(name, "exit", result.returncode, flush=True)
    if result.returncode not in allowed:
        raise RuntimeError(name + " failed; see saved log")
    return result


def git(repo, *args):
    return subprocess.check_output(["git", "-c", f"safe.directory={repo.as_posix()}", "-C", str(repo), *args], env=dict(ENV, GIT_OPTIONAL_LOCKS="0"))


def manifest(directory, exclude=()):
    return {p.relative_to(directory).as_posix(): sha(p.read_bytes()) for p in sorted(directory.rglob("*"))
            if p.is_file() and not any(part in exclude for part in p.relative_to(directory).parts)}


def source_identity():
    files = manifest(ROOT,exclude=("__pycache__","build","chstockdata.egg-info",".pytest_cache"))
    baseline=json.loads((WORK/"baseline.json").read_text(encoding="utf-8"))
    return {"identity_kind":"source_tree_sha256", "not_a_git_commit":True,
        "base_commit":baseline["chstockdata_head"], "original_working_tree_status":baseline["chstockdata_status_before"],
        "working_tree_files":files,"working_tree_manifest_sha256":sha(json.dumps(files,sort_keys=True).encode()),
        "package_files":manifest(ROOT/"src/chstockdata",exclude=("__pycache__",))}


def export(repo, commit, target):
    entries = [line.split("\t", 1) for line in git(repo, "ls-tree", "-r", "-z", commit).decode().split("\0") if line]
    raw = subprocess.check_output(["git", "-c", f"safe.directory={repo.as_posix()}", "-C", str(repo), "cat-file", "--batch"],
                                  input=("\n".join(info.split()[2] for info, _ in entries) + "\n").encode(), env=ENV)
    offset = 0
    files = {}
    for info, name in entries:
        end = raw.index(b"\n", offset)
        blob, kind, length = raw[offset:end].split()
        length = int(length)
        data = raw[end + 1:end + 1 + length]
        assert kind == b"blob" and blob.decode() == info.split()[2]
        assert hashlib.sha1(b"blob " + str(length).encode() + b"\0" + data).hexdigest() == blob.decode()
        path = target / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            assert path.read_bytes() == data, path
        else:
            path.write_bytes(data)
        files[name] = sha(data)
        offset = end + 1 + length + 1
    assert offset == len(raw)
    return {"commit": commit, "tree": git(repo, "rev-parse", commit + "^{tree}").decode().strip(), "files": files}


def build():
    identity = source_identity()
    save("candidate-source.json", identity)
    command("environment", [GATE, OUT/"dependencies.py"])
    command("build", [GATE, "-m", "build", "--outdir", DIST])
    with zipfile.ZipFile(WHEEL) as archive:
        package = {name.removeprefix("chstockdata/"): sha(archive.read(name)) for name in archive.namelist() if name.startswith("chstockdata/") and not name.endswith("/")}
        assert package == identity["package_files"]
    with tarfile.open(SDIST) as archive:
        members = {m.name: archive.extractfile(m).read() for m in archive.getmembers() if m.isfile()}
        prefix = "chstockdata-0.4.2/src/chstockdata/"
        assert {name.removeprefix(prefix): sha(data) for name, data in members.items() if name.startswith(prefix)} == package
        assert members["chstockdata-0.4.2/tests/test_vipdoc_price_scale.py"] == (ROOT / "tests/test_vipdoc_price_scale.py").read_bytes()
    save("artifacts.json", {"source_identity": identity, "wheel": {"path": str(WHEEL), "sha256": sha(WHEEL.read_bytes()), "bytes": WHEEL.stat().st_size},
                           "sdist": {"path": str(SDIST), "sha256": sha(SDIST.read_bytes()), "bytes": SDIST.stat().st_size}, "package_members_match": len(package),
                           "source_semantics_included": all(package[name] == sha((ROOT / "src/chstockdata" / name).read_bytes()) for name in ("suspension.py", "tradability.py", "a_stock.py"))})
    command("twine", [GATE, "-m", "twine", "check", WHEEL, SDIST])


def install(profile, artifact=WHEEL, extras="", ta=False):
    base = Path("C:/Users/Administrator/AppData/Local/Programs/Python/Python314/python.exe") if ta else Path("C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe")
    target = PROFILES / profile
    if (target/"Scripts/python.exe").exists() and (OUT/(profile+"-install.exit")).exists() and (OUT/(profile+"-install.exit")).read_text(encoding="utf-8").strip()=="0":
        return target/"Scripts/python.exe"
    command(profile + "-create", [base, "-m", "venv", target], cwd=WORK)
    python = target / "Scripts/python.exe"
    command(profile + "-install", [python, "-m", "pip", "install", *( ["--no-deps"] if ta else []), str(artifact) + extras, *( [] if ta else ["pytest==9.1.1"])], cwd=WORK)
    if ta:
        (target / "Lib/site-packages/consumer_dependencies.pth").write_text("D:/Dev/Projects/TradingAgents-AStock-Private/.venv/Lib/site-packages\n", encoding="utf-8")
    return python


def installed_identity(profile):
    import importlib.metadata as metadata
    import chstockdata
    site = PROFILES / profile / "Lib/site-packages"
    assert Path(chstockdata.__file__).resolve().is_relative_to(site.resolve())
    assert metadata.version("chstockdata") == chstockdata.__version__ == "0.4.2"
    with zipfile.ZipFile(WHEEL) as archive:
        names = [name for name in archive.namelist() if name.startswith("chstockdata/") and not name.endswith("/")]
        for name in names:
            assert archive.read(name) == (site / name).read_bytes(), name
    info = {"python": sys.version, "executable": sys.executable, "library_import": chstockdata.__file__, "version": chstockdata.__version__,
            "wheel_sha256": sha(WHEEL.read_bytes()), "all_installed_package_members_match": len(names), "venv": (PROFILES / profile / "pyvenv.cfg").read_text(encoding="utf-8")}
    save(profile + "-identity.json", info)
    return info


def prepare():
    ta=export(Path('D:/Dev/Projects/TradingAgents-AStock-Private'),'14673992b9cd1d8a74e514027843be3298e029c7',TA)
    overlays={
      'tests/test_phase2_step3_projection.py':'48f8d22bd9fd572942392727a6baeb88e4e63733667e5bff7441bf5d971fb8a5',
      'tests/test_phase2_step3_validation.py':'cfb393eb9f06e40cde31fb4b097a16549f3bfbb0ce665977ca89cc37258c71fd',
      'tradingagents/agents/utils/phase2_projection.py':'d29965e9d6a899b27448b0f7750981fd9aba9d3665cbcaa1588b3a2be3bd527e'}
    for name,digest in overlays.items():
        data=(Path('D:/Dev/Projects/chstockdata/build/v042-qualification/ta')/name).read_bytes()
        assert sha(data)==digest,name
        path=TA/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
    frozen=Path('D:/Dev/Projects/chstockdata/build/v042-qualification/sios-baseline/var')
    before=manifest(frozen)
    save('frozen-var-before.json',before)
    assert not (SIOS/'var').exists(),'fresh var required'
    shutil.copytree(frozen,SIOS/'var')
    assert manifest(SIOS/'var')==before
    save('consumer-identities.json',{'sios':{'frozen_commit':'84fd54fae0740bc06b1d250afa4578be29556956','actual_files':manifest(SIOS,exclude=('var','__pycache__','.pytest_cache'))},
      'ta':ta,'ta_overlays':overlays,'frozen_var_files':len(before),'frozen_var_manifest_sha256':sha(json.dumps(before,sort_keys=True).encode()),
      'snapshot_gitless':True,'test_only_code_identity_injection':['research.runner.resolve_code_commit','research.oos.resolve_code_commit']})
    print('exact TA export and isolated frozen var prepared',flush=True)

def probe():
    info=installed_identity('sios-candidate')
    sys.path.insert(0,str(SIOS/'src'))
    import chstockdata
    from systematic_investing.adapters.chstockdata import provider as adapter
    from systematic_investing.data.ports import DailyBarRequest
    from systematic_investing.data.contracts import ProviderSuccess
    from systematic_investing.domain.identifiers import InstrumentId
    from systematic_investing.domain.market import AdjustmentMode,DailyBar
    assert Path(adapter.__file__).resolve().is_relative_to(SIOS.resolve())
    try: adapter.LibraryChStockDataClient()
    except adapter.ChStockDataConfigurationError: guard='PASS'
    else: raise AssertionError('default pin admitted candidate')
    client=adapter.LibraryChStockDataClient(historical_opening_candidate=True)
    chstockdata.configure(vipdoc_history_enabled=True,vipdoc_history_dir=str(DATA),data_cache_dir=str(WORK/'cache/exact-probe'))
    provider=adapter.ChStockDataProvider(client=client,clock=lambda:datetime.now(adapter.MARKET_TIMEZONE))
    golden=json.loads((ROOT/'tests/fixtures/vipdoc/price_scale_20221230.json').read_text(encoding='utf-8'))['fixtures'][1:]
    facts=[]
    for item in golden:
        code,market=item['code'],item['market']
        packed=(DATA/market/'lday'/f'{market}{code}.day').read_bytes()
        assert sha(packed)==item['source_file_sha256']
        rows=list(struct.Struct('<IIIIIfII').iter_unpack(packed)); index=next(i for i,row in enumerate(rows) if row[0]==20221230)
        native,previous=rows[index],rows[index-1]
        instrument=InstrumentId.parse(f"{'XSHG' if market=='sh' else 'XSHE'}:{code}")
        result=provider.fetch_daily_bars(DailyBarRequest(instrument_ids=(instrument,),start_date=date(2022,12,30),end_date=date(2022,12,30)))
        assert isinstance(result,ProviderSuccess),result
        assert len(result.records)==1 and isinstance(result.records[0],DailyBar)
        bar=result.records[0]
        actual=[bar.open,bar.high,bar.low,bar.close,bar.pre_close]
        expected=[Decimal(str(v)) for v in [*item['expected_ohlc'],item['expected_pre_close']]]
        raw_expected=[Decimal(v)/Decimal(1000) for v in [*native[1:5],previous[4]]]
        checks={'exact_ohlc_and_pre_close':actual==expected==raw_expected,
          'units':bar.volume==Decimal(native[6]) and bar.volume_unit=='SHARE' and bar.amount==Decimal(str(native[5])) and bar.amount_unit==bar.currency=='CNY',
          'adjustment':bar.adjustment_mode is AdjustmentMode.RAW and bar.adjustment_factor is None,
          'provenance':result.evidence.provider_name=='chstockdata' and result.evidence.provider_version=='0.4.2'}
        facts.append({'code':code,'session':'2022-12-30','raw':native,'previous_raw':previous,'actual_decimal':actual,'expected_decimal':expected,'raw_expected_decimal':raw_expected,'source_file_sha256':sha(packed),'zero_tolerance':True,'checks':checks,'status':'PASS' if all(checks.values()) else 'FAIL'})
    save('etf-exact-probe.json',{'identity':info,'adapter_import':adapter.__file__,'adapter_sha256':sha(Path(adapter.__file__).read_bytes()),'default_pin_reject':guard,'explicit_candidate':True,'facts':facts,'price_parity':sum(f['status']=='PASS' for f in facts)})
    assert len(facts)==4 and all(f['status']=='PASS' for f in facts)
    print('4/4 exact ETF OHLC/pre_close contracts PASS',flush=True)

def pytest_run(name,python,cwd,selection,env=ENV,sios=False):
    args=[python,OUT/'run_sios_tests.py',name,*selection] if sios else [python,'-m','pytest',*selection,'-q','--tb=long','-rA','-p','no:cacheprovider','--basetemp='+str(OUT/(name+'-tmp')),'--junitxml='+str(OUT/(name+'.xml'))]
    return command(name,args,cwd=cwd,env=env,allowed=(0,1))

def packages():
    for profile,artifact,extras in (('core',WHEEL,''),('sdist',SDIST,''),('mcp',WHEEL,'[mcp]'),('baostock',WHEEL,'[baostock]')):
        python=install(profile,artifact,extras)
        command(profile+'-pip-check',[python,'-m','pip','check'],cwd=WORK)
        command(profile+'-deps',[python,OUT/'dependencies.py'],cwd=WORK)
        command(profile+'-version',[python,ROOT/'scripts/check_release_version.py','--tag','v0.4.2','--project-root',ROOT],cwd=WORK)
        command(profile+'-identity',[python,OUT/'run_gate.py','identity',profile],cwd=WORK)
        snippet="import chstockdata, importlib.metadata as m; assert all(n in chstockdata.__all__ and hasattr(chstockdata,n) for n in ('fetch_realtime_quotes','fetch_daily_bars','fetch_trading_calendar','fetch_suspension_info','fetch_delisting_status','fetch_tradability','fetch_historical_opening_evidence','FetchAttempt','FetchMetadata','FetchResult')); assert {'chstockdata-mcp','chstockdata-refresh-vipdoc'} <= {e.name for e in m.entry_points(group='console_scripts')}"
        if profile=='mcp':snippet+='; from chstockdata.mcp_server import build_server; assert build_server() is not None'
        if profile=='baostock':snippet+='; import baostock'
        command(profile+'-exports',[python,'-c',snippet],cwd=WORK)
        if profile in ('core','sdist'):
            for script in ('chstockdata-mcp','chstockdata-refresh-vipdoc'):
                command(profile+'-'+script,[python.parent/(script+'.exe'),'--help'],cwd=WORK)

def install_sios():
    python=install('sios-candidate',extras='[mootdx,opening-pdf]')
    command('sios-certified-deps',[python,'-m','pip','install','mootdx==0.11.7','tdxpy==0.2.7','pypdf==6.10.0'],cwd=WORK)
    command('sios-pip-check',[python,'-m','pip','check'],cwd=WORK)
    command('sios-deps',[python,OUT/'dependencies.py'],cwd=WORK)
    command('etf-exact-probe',[python,OUT/'run_gate.py','probe'],cwd=WORK)

def tests():
    python=PROFILES/'sios-candidate/Scripts/python.exe'
    command('package-suite-identity',[python,OUT/'run_gate.py','identity','sios-candidate'],cwd=ROOT)
    pytest_run('package-tests',python,ROOT,['tests/','--no-header'])
    static_record=OUT/'static-final.command.json'
    if not static_record.exists() or json.loads(static_record.read_text(encoding='utf-8')).get('candidate_wheel_sha256')!=sha(WHEEL.read_bytes()):
        command('static-final',[GATE,OUT/'run_static.py'],cwd=ROOT)
    command('compile',[python,'-m','compileall','-q','src','tests'],cwd=ROOT)
    command('original-diff-check',['git','-c','safe.directory=D:/Dev/Projects/chstockdata','-C','D:/Dev/Projects/chstockdata','diff','--check'],cwd=WORK)
    command('version-project',[python,ROOT/'scripts/check_release_version.py','--tag','v0.4.2','--project-root',ROOT,'--project-only'],cwd=ROOT)

def consumers():
    python=PROFILES/'sios-candidate/Scripts/python.exe'
    env=dict(ENV,PYTHONPATH=str(SIOS/'src'))
    pytest_run('sios-provider-contract',python,SIOS,['tests/contract/test_chstockdata_provider.py','tests/contract/test_provider_port.py'],env,sios=True)
    pytest_run('sios-etf-golden-smoke',python,SIOS,['tests/qualification','tests/golden','tests/parity'],env,sios=True)
    pytest_run('sios-offline',python,SIOS,['tests/'],env,sios=True)
    save('sios-var-after.json',manifest(SIOS/'var'))
    original=Path('D:/Dev/Projects/chstockdata/build/v042-qualification/sios-baseline/var')
    after=manifest(original); save('frozen-var-after.json',after)
    assert after==json.loads((OUT/'frozen-var-before.json').read_text(encoding='utf-8'))

def live():
    python=PROFILES/'sios-candidate/Scripts/python.exe'
    env=dict(ENV,PYTHONPATH=str(SIOS/'src'),SIOS_CHSTOCKDATA_LIVE_QUALIFICATION='1',CHSTOCKDATA_VIPDOC_HISTORY_DIR=str(DATA),CHSTOCKDATA_CACHE_DIR=str(WORK/'cache/r21-live'))
    command('sios-required-live',[python,OUT/'run_live.py'],cwd=SIOS,env=env,allowed=(0,1))

def ta_tests():
    python=install('ta-candidate',ta=True)
    env=dict(ENV,PYTHONPATH=str(TA))
    command('ta-pip-check',[python,'-m','pip','check'],cwd=TA,env=env,allowed=(0,1))
    command('ta-deps',[python,OUT/'dependencies.py'],cwd=TA,env=env)
    command('ta-identity',[python,OUT/'run_gate.py','identity','ta-candidate'],cwd=TA,env=env)
    selection=['tests/test_'+name+'.py' for name in ('upstream_adapters','trading_calendar','f1_public_integration','free_adjusted_bars','point_in_time_fundamentals','performance_optimization','p1_listing_status_data_plane','phase2_step3_projection','phase2_step3_validation')]
    expression='not stale_local_falls_back_online_and_labels_source and not stale_local_without_online_keeps_local_flagged and not missing_local_online_fallback_and_total_failure and not empty_or_missing_tree_returns_none'
    pytest_run('ta-candidate',python,TA,[*selection,'-k',expression],env)
    command('ta-legacy',[python,'-B','D:/Dev/Projects/chstockdata/dist/consumer-v0.4.2/evidence/legacy_probe.py','0.4.2',DATA],cwd=TA,env=env)
    command('ta-source-binding',[python,'-c',"import tradingagents,chstockdata; from pathlib import Path; from tradingagents.dataflows import a_stock; assert Path(tradingagents.__file__).resolve().is_relative_to(Path(r'"+str(TA)+"').resolve()); print(tradingagents.__file__); print(a_stock.__file__); print(chstockdata.__file__)"],cwd=TA,env=env)

if __name__=='__main__':
    mode=sys.argv[1]
    if mode=='identity':print(json.dumps(installed_identity(sys.argv[2]),indent=2))
    elif mode=='prepare':prepare()
    elif mode=='build':build()
    elif mode=='packages':packages()
    elif mode=='install-sios':install_sios()
    elif mode=='probe':probe()
    elif mode=='tests':tests()
    elif mode=='consumers':consumers()
    elif mode=='live':live()
    elif mode=='ta':ta_tests()
    else:raise ValueError(mode)
