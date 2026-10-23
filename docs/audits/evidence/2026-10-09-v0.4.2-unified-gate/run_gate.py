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
ROOT = OUT.parents[3]
WORK = ROOT / "build/v042-unified"
DIST = ROOT / "dist/v042-unified"
PROFILES = Path(r"C:\Users\Administrator\.codex\visualizations\2026\10\09\01a11feb-cbea-7790-a83e-57b1dd555e13/v042-unified")
OLD = ROOT / "docs/audits/evidence/2026-10-09-v0.4.2-release"
GATE = ROOT / "build/v042-qualification/gate/Scripts/python.exe"
DATA = ROOT / ".rh3a2-vipdoc"
WHEEL = DIST / "chstockdata-0.4.2-py3-none-any.whl"
SDIST = DIST / "chstockdata-0.4.2.tar.gz"
ENV = dict(os.environ, PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1", PYTEST_DISABLE_PLUGIN_AUTOLOAD="1")
ENV.pop("PYTHONPATH", None)
ENV["TEMP"] = ENV["TMP"] = str(WORK / "temp")
for path in (WORK, DIST, PROFILES, WORK / "temp"):
    path.mkdir(parents=True, exist_ok=True)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def save(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def command(name, argv, cwd=ROOT, env=None, allowed=(0,)):
    result = subprocess.run([str(a) for a in argv], cwd=cwd, env=env or ENV, capture_output=True, text=True, encoding="utf-8", errors="replace")
    (OUT / (name + ".log")).write_text(result.stdout + result.stderr, encoding="utf-8")
    (OUT / (name + ".exit")).write_text(str(result.returncode) + "\n", encoding="utf-8")
    journal = "package-install-commands.json" if sys.argv[1] == "packages" else "commands.json"
    records = json.loads((OUT / journal).read_text(encoding="utf-8")) if (OUT / journal).exists() else []
    records.append({"name": name, "argv": [str(a) for a in argv], "cwd": str(cwd), "exit": result.returncode,
                    "candidate_wheel_sha256": sha(WHEEL.read_bytes()) if WHEEL.exists() else None,
                    "environment_overrides": {key: (env or ENV).get(key) for key in ("PYTHONPATH", "PYTHONUTF8", "PYTEST_DISABLE_PLUGIN_AUTOLOAD", "SIOS_CHSTOCKDATA_LIVE_QUALIFICATION", "CHSTOCKDATA_VIPDOC_HISTORY_DIR", "CHSTOCKDATA_CACHE_DIR", "TEMP", "TMP")}})
    save(journal, records)
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
    names = git(ROOT, "ls-files", "--cached", "--others", "--exclude-standard", "-z").decode().split("\0")
    files = {name: sha((ROOT / name).read_bytes()) for name in names if name and (ROOT / name).is_file() and not name.startswith(OUT.relative_to(ROOT).as_posix() + "/")}
    # The manifest binds the entire candidate working tree, including pre-existing
    # uncommitted semantics/tests/docs, without changing the real Git index.
    return {"base_commit": git(ROOT, "rev-parse", "HEAD").decode().strip(),
            "base_tree": git(ROOT, "rev-parse", "HEAD^{tree}").decode().strip(),
            "branch": git(ROOT, "branch", "--show-current").decode().strip(),
            "working_tree_status": git(ROOT, "status", "--porcelain=v1", "--untracked-files=all").decode(),
            "working_tree_files": files, "working_tree_manifest_sha256": sha(json.dumps(files, sort_keys=True).encode()),
            "package_files": manifest(ROOT / "src/chstockdata", exclude=("__pycache__",))}


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


def prepare():
    sios_repo = Path("D:/Dev/Projects/systematic-investing-os")
    ta_repo = Path("D:/Dev/Projects/TradingAgents-AStock-Private")
    sios = export(sios_repo, "84fd54fae0740bc06b1d250afa4578be29556956", WORK / "sios-pristine")
    ta = export(ta_repo, "14673992b9cd1d8a74e514027843be3298e029c7", WORK / "ta")
    frozen = ROOT / "build/v042-qualification/sios-baseline/var"
    frozen_manifest = manifest(frozen)
    save("frozen-var.json", frozen_manifest)
    shutil.copytree(WORK / "sios-pristine", WORK / "sios")
    shutil.copytree(frozen, WORK / "sios/var")
    assert manifest(WORK / "sios/var") == frozen_manifest
    changes = []
    for relative, replacements in {
        "src/systematic_investing/adapters/chstockdata/provider.py": [(b"if version != pinned:", b'if version != pinned and version != "0.4.2":')],
        "tests/qualification/test_chstockdata_etf_gate.py": [(b"assert evidence.provider_version == PINNED_CHSTOCKDATA_VERSION", b'assert evidence.provider_version == "0.4.2"'), (b"assert chstockdata.__version__ == PINNED_CHSTOCKDATA_VERSION", b'assert chstockdata.__version__ == "0.4.2"')],
    }.items():
        path = WORK / "sios" / relative
        before = path.read_bytes()
        after = before
        for original, replacement in replacements:
            assert after.count(original) == 1
            after = after.replace(original, replacement)
        path.write_bytes(after)
        changes.extend(difflib.unified_diff(before.decode().splitlines(True), after.decode().splitlines(True), "a/" + relative, "b/" + relative))
    patch = "".join(changes).encode()
    (OUT / "candidate-only-version-exception.patch").write_bytes(patch)
    identities = json.loads((ROOT / "dist/consumer-v0.4.2/evidence/fixed-identities.json").read_text(encoding="utf-8"))
    for overlay in identities["ta_overlays"]:
        data = (ROOT / "build/v042-qualification/ta" / overlay["path"]).read_bytes()
        assert sha(data) == overlay["sha256"], overlay
        path = WORK / "ta" / overlay["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    save("consumer-identities.json", {"sios": sios, "ta": ta, "ta_overlays": identities["ta_overlays"], "version_exception_sha256": sha(patch),
        "sios_production_pin": "0.3.0", "version_exception": "only extra admitted release is 0.4.2; frozen 0.3.0 stub contracts retained",
        "frozen_var_files": len(frozen_manifest), "frozen_var_manifest_sha256": sha(json.dumps(frozen_manifest, sort_keys=True).encode()),
        "production_before": {str(repo): {"head": git(repo, "rev-parse", "HEAD").decode().strip(), "status": git(repo, "status", "--porcelain=v1").decode()} for repo in (sios_repo, ta_repo)}})
    print("frozen consumer sources and inputs verified", flush=True)


def build():
    identity = source_identity()
    save("candidate-source.json", identity)
    command("environment", [GATE, "-m", "pip", "freeze"])
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


def probe():
    info = installed_identity("sios-candidate")
    sys.path.insert(0, str(WORK / "sios-pristine/src"))
    import chstockdata
    from systematic_investing.adapters.chstockdata import provider as adapter
    from systematic_investing.data.ports import DailyBarRequest
    from systematic_investing.data.contracts import ProviderSuccess
    from systematic_investing.domain.identifiers import InstrumentId
    from systematic_investing.domain.market import AdjustmentMode, DailyBar
    original_source = (WORK / "sios-pristine/src/systematic_investing/adapters/chstockdata/provider.py").read_bytes()
    assert Path(adapter.__file__).resolve() == (WORK / "sios-pristine/src/systematic_investing/adapters/chstockdata/provider.py").resolve()
    info.update(adapter_import=adapter.__file__, adapter_sha256=sha(original_source), client_name=adapter.LibraryChStockDataClient.__qualname__, production_pin=adapter.PINNED_CHSTOCKDATA_VERSION)
    try:
        adapter.LibraryChStockDataClient()
    except adapter.ChStockDataConfigurationError:
        original_guard = "PASS"
    else:
        raise AssertionError("original adapter did not reject candidate")
    defaults = dict(adapter.validate_library_version.__kwdefaults__)
    code_identity = adapter.validate_library_version.__code__
    facts = []
    try:
        adapter.validate_library_version.__kwdefaults__["pinned"] = "0.4.2"
        assert adapter.PINNED_CHSTOCKDATA_VERSION == "0.3.0"
        rejected = []
        for version in ("0.3.0", "0.4.0", "0.4.1", "0.4.3", "0.4.2rc1", "0.4.2+local", "9.9.9", "", None):
            try:
                adapter.validate_library_version(version)
            except adapter.ChStockDataConfigurationError:
                rejected.append(version)
            else:
                raise AssertionError(f"non-candidate admitted: {version!r}")
        assert adapter.validate_library_version("0.4.2") == "0.4.2"
        client = adapter.LibraryChStockDataClient()
        assert type(client) is adapter.LibraryChStockDataClient
        chstockdata.configure(vipdoc_history_enabled=True, vipdoc_history_dir=str(DATA), data_cache_dir=str(WORK / "probe-cache"))
        provider = adapter.ChStockDataProvider(client=client, clock=lambda: datetime.now(adapter.MARKET_TIMEZONE))
        golden = json.loads((ROOT / "tests/fixtures/vipdoc/price_scale_20221230.json").read_text(encoding="utf-8"))["fixtures"][1:]
        for item in golden:
            code, market = item["code"], item["market"]
            path = DATA / market / "lday" / f"{market}{code}.day"
            packed = path.read_bytes()
            assert sha(packed) == item["source_file_sha256"]
            rows = list(struct.Struct("<IIIIIfII").iter_unpack(packed))
            index = next(i for i, row in enumerate(rows) if row[0] == 20221230)
            native, previous = rows[index], rows[index - 1]
            instrument = InstrumentId.parse(f"{'XSHG' if market == 'sh' else 'XSHE'}:{code}")
            result = provider.fetch_daily_bars(DailyBarRequest(instrument_ids=(instrument,), start_date=date(2022, 12, 30), end_date=date(2022, 12, 30)))
            assert isinstance(result, ProviderSuccess), result
            assert len(result.records) == 1 and isinstance(result.records[0], DailyBar)
            bar = result.records[0]
            actual = [bar.open, bar.high, bar.low, bar.close, bar.pre_close]
            expected = [Decimal(str(value)) for value in [*item["expected_ohlc"], item["expected_pre_close"]]]
            raw_expected = [Decimal(value) / Decimal(1000) for value in [*native[1:5], previous[4]]]
            checks = {"exact_ohlc_and_pre_close": actual == expected == raw_expected,
                      "units": bar.volume == Decimal(native[6]) and bar.volume_unit == "SHARE" and bar.amount == Decimal(str(native[5])) and bar.amount_unit == bar.currency == "CNY",
                      "adjustment": bar.adjustment_mode is AdjustmentMode.RAW and bar.adjustment_factor is None,
                      "provenance": result.evidence.provider_name == "chstockdata" and result.evidence.provider_version == "0.4.2"}
            facts.append({"code": code, "session": "2022-12-30", "raw": native, "previous_raw": previous,
                          "actual_decimal": actual, "expected_decimal": expected, "raw_expected_decimal": raw_expected,
                          "source_file_sha256": sha(packed), "zero_tolerance": True, "checks": checks, "status": "PASS" if all(checks.values()) else "FAIL"})
    finally:
        adapter.validate_library_version.__kwdefaults__.clear()
        adapter.validate_library_version.__kwdefaults__.update(defaults)
    assert adapter.validate_library_version.__code__ is code_identity and adapter.validate_library_version.__kwdefaults__ == defaults
    save("etf-exact-probe.json", {"identity": info, "original_version_guard": original_guard, "candidate_only_exception": "PASS", "rejected_versions": rejected,
        "real_client": "PASS", "original_adapter_restored": True, "facts": facts, "price_parity": sum(fact["status"] == "PASS" for fact in facts)})
    assert len(facts) == 4 and all(fact["status"] == "PASS" for fact in facts)
    print("4/4 exact ETF OHLC/pre_close contracts PASS", flush=True)


def pytest_run(name, python, cwd, selection, env=ENV):
    command(name, [python, "-m", "pytest", *selection, "-q", "--tb=long", "-rA", "-p", "no:cacheprovider",
                   "--basetemp=" + str(WORK / (name + "-tmp")), "--junitxml=" + str(OUT / (name + ".xml"))], cwd=cwd, env=env, allowed=(0, 1))


def tests():
    env = dict(ENV, PYTHONPATH=str(ROOT / "src"))
    pytest_run("package-tests", GATE, ROOT, ["tests/", "--no-header"], env)
    command("static", [GATE, "scripts/check_rh1_static.py"], env=env)
    command("compile", [GATE, "-m", "compileall", "-q", "src", "tests"], env=env)
    command("diff-check", ["git", "diff", "--check"])
    command("version-project", [GATE, ROOT / "scripts/check_release_version.py", "--tag", "v0.4.2", "--project-root", ROOT, "--project-only"])


def packages():
    for profile, artifact, extras in (("core", WHEEL, ""), ("sdist", SDIST, ""), ("mcp", WHEEL, "[mcp]"), ("baostock", WHEEL, "[baostock]")):
        python = install(profile, artifact, extras)
        command(profile + "-pip-check", [python, "-m", "pip", "check"], cwd=WORK)
        command(profile + "-version", [python, ROOT / "scripts/check_release_version.py", "--tag", "v0.4.2", "--project-root", ROOT], cwd=WORK)
        command(profile + "-identity", [python, OUT / "run_gate.py", "identity", profile], cwd=WORK)
        snippet = "import chstockdata, importlib.metadata as m; assert all(n in chstockdata.__all__ and hasattr(chstockdata,n) for n in ('fetch_realtime_quotes','fetch_daily_bars','fetch_trading_calendar','fetch_suspension_info','fetch_delisting_status','fetch_tradability','FetchAttempt','FetchMetadata','FetchResult')); assert {'chstockdata-mcp','chstockdata-refresh-vipdoc'} <= {e.name for e in m.entry_points(group='console_scripts')}"
        if profile == "mcp":
            snippet += "; from chstockdata.mcp_server import build_server; assert build_server() is not None"
        if profile == "baostock":
            snippet += "; import baostock"
        command(profile + "-exports", [python, "-c", snippet], cwd=WORK)
        if profile in ("core", "sdist"):
            for script in ("chstockdata-mcp", "chstockdata-refresh-vipdoc"):
                command(profile + "-" + script, [python.parent / (script + ".exe"), "--help"], cwd=WORK)


def consumers():
    python = PROFILES / "sios-candidate/Scripts/python.exe"
    source = WORK / "sios"
    command("sios-suite-identity", [python, OUT / "run_gate.py", "identity", "sios-candidate"], cwd=source)
    pytest_run("sios-provider-contract", python, source, ["tests/contract/test_chstockdata_provider.py", "tests/contract/test_provider_port.py"])
    pytest_run("sios-etf-golden-smoke", python, source, ["tests/qualification", "tests/golden", "tests/parity"])
    pytest_run("sios-offline", python, source, ["tests/"])
    live_env = dict(ENV, SIOS_CHSTOCKDATA_LIVE_QUALIFICATION="1", CHSTOCKDATA_VIPDOC_HISTORY_DIR=str(DATA), CHSTOCKDATA_CACHE_DIR=str(WORK / "sios-live-cache"))
    pytest_run("sios-required-live", python, source, ["tests/qualification/test_chstockdata_etf_gate.py", "-k", "test_live"], live_env)
    python = install("ta-candidate", ta=True)
    command("ta-identity", [python, OUT / "run_gate.py", "identity", "ta-candidate"], cwd=WORK / "ta")
    selection = ["tests/test_upstream_adapters.py", "tests/test_trading_calendar.py", "tests/test_f1_public_integration.py", "tests/test_free_adjusted_bars.py", "tests/test_point_in_time_fundamentals.py", "tests/test_performance_optimization.py", "tests/test_p1_listing_status_data_plane.py", "tests/test_phase2_step3_projection.py", "tests/test_phase2_step3_validation.py"]
    expression = "not stale_local_falls_back_online_and_labels_source and not stale_local_without_online_keeps_local_flagged and not missing_local_online_fallback_and_total_failure and not empty_or_missing_tree_returns_none"
    pytest_run("ta-candidate", python, WORK / "ta", [*selection, "-k", expression])


if __name__ == "__main__":
    mode = sys.argv[1]
    if mode == "prepare":
        prepare()
    elif mode == "build":
        build()
    elif mode == "install-probe":
        python = install("sios-candidate", extras="[mootdx]")
        command("sios-pip-check", [python, "-m", "pip", "check"], cwd=WORK)
        command("etf-exact-probe", [python, OUT / "run_gate.py", "probe"], cwd=WORK)
    elif mode == "identity":
        print(json.dumps(installed_identity(sys.argv[2]), indent=2))
    elif mode == "probe":
        probe()
    elif mode == "tests":
        tests()
    elif mode == "packages":
        packages()
    elif mode == "consumers":
        consumers()
    elif mode == "ta-legacy":
        python = PROFILES / "ta-candidate/Scripts/python.exe"
        env = dict(ENV, PYTHONPATH=str(WORK / "ta"))
        command("ta-legacy", [python, "-B", ROOT / "dist/consumer-v0.4.2/evidence/legacy_probe.py", "0.4.2", DATA], cwd=WORK / "ta", env=env)
        command("ta-source-binding", [python, "-c", "import tradingagents,chstockdata; from pathlib import Path; from tradingagents.dataflows import a_stock; assert Path(tradingagents.__file__).resolve().is_relative_to(Path(r'" + str(WORK / "ta") + "').resolve()); print(tradingagents.__file__); print(a_stock.__file__); print(chstockdata.__file__)"], cwd=WORK / "ta", env=env)
    else:
        raise ValueError(mode)
