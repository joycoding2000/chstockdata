"""Record the original blocker and an offline PIT boundary demonstration."""
import os
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone

from probe import OUT, ROOT, WHEEL, save, sha

PYTHON = r"C:\Users\Administrator\.codex\visualizations\2026\10\09\01a11feb-cbea-7790-a83e-57b1dd555e13\v042-unified\sios-candidate\Scripts\python.exe"
SIOS = ROOT / "build/v042-unified/sios"
if sys.argv[1] == "live":
    env = dict(os.environ, PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1", PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",
               PYTHONPATH=str(SIOS / "src"), SIOS_CHSTOCKDATA_LIVE_QUALIFICATION="1",
               CHSTOCKDATA_VIPDOC_HISTORY_DIR=str(ROOT / ".rh3a2-vipdoc"),
               CHSTOCKDATA_CACHE_DIR=str(ROOT / "build/history-recovery/live-cache"),
               TEMP=str(ROOT / "build/history-recovery/temp"), TMP=str(ROOT / "build/history-recovery/temp"))
    (ROOT / "build/history-recovery/temp").mkdir(parents=True, exist_ok=True)
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        env.pop(key, None)
    argv = [PYTHON, "-B", "-m", "pytest", "tests/qualification/test_chstockdata_etf_gate.py",
            "-k", "test_live_tradability_adjustment_and_freshness", "-q", "--tb=long", "-p", "no:cacheprovider",
            "--basetemp=" + str(ROOT / "build/history-recovery/live-tmp"), "--junitxml=" + str(OUT / "sios-blocker.xml")]
    result = subprocess.run(argv, cwd=SIOS, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
    (OUT / "sios-blocker.log").write_text(result.stdout + result.stderr, encoding="utf-8")
    (OUT / "sios-blocker.exit").write_text(str(result.returncode) + "\n", encoding="utf-8")
    save("sios-blocker-command.json", {"argv": argv, "cwd": str(SIOS), "exit": result.returncode,
         "wheel_sha256": sha(WHEEL.read_bytes()), "environment_overrides": {k: env[k] for k in ("PYTHONPATH", "PYTHONDONTWRITEBYTECODE", "SIOS_CHSTOCKDATA_LIVE_QUALIFICATION", "CHSTOCKDATA_VIPDOC_HISTORY_DIR", "CHSTOCKDATA_CACHE_DIR", "TEMP", "TMP")}})
    print("original mandatory blocker exit", result.returncode)
    print(result.stdout[-700:])
elif sys.argv[1] == "pit":
    sys.path.insert(0, str(SIOS / "src"))
    from systematic_investing.adapters.chstockdata.provider import ChStockDataProvider
    from systematic_investing.domain.market import Availability, AvailabilityBasis
    tz = timezone(timedelta(hours=8))
    cutoff = datetime(2026, 9, 11, 9, 30, tzinfo=tz)
    retrieved = datetime.now(tz)
    output = []
    cases = [("historical daily fact, actual observation now", {"observed_at": retrieved.isoformat()}),
             ("declared final daily fact time", {"information_available_at": "2026-09-11T15:05:00+08:00"})]
    for label, payload in cases:
        availability = ChStockDataProvider._tradability_availability(payload=payload, session_date=date(2026, 9, 11), retrieved_at=retrieved)
        output.append({"label": label, "payload": payload, "mapped": repr(availability), "known_at_0930": availability.information_known_at(cutoff), "diagnostic_only": True})
        assert availability.information_known_at(cutoff) is True
    honest_unknown = Availability(information_available_at=None, retrieved_at=retrieved, availability_basis=AvailabilityBasis.UNKNOWN)
    honest_close = Availability(information_available_at=datetime(2026, 9, 11, 15, 5, tzinfo=tz), retrieved_at=retrieved, availability_basis=AvailabilityBasis.EXCHANGE_RULE)
    assert honest_unknown.information_known_at(cutoff) is None
    assert honest_close.information_known_at(cutoff) is False
    save("pit-boundary.json", {"cutoff": str(cutoff), "cases": output, "honest_unknown_known_at_cutoff": None,
         "honest_close_known_at_cutoff": False, "note": "15:05 is a diagnostic rule only, not a certified TDX publication time", "verdict": "CONFIRMED_DEFECT if retrospective bars are routed into this suspension contract"})
    print("2 historical mapper cases incorrectly known at 09:30; UNKNOWN/close controls correctly exclude pre-open use")
