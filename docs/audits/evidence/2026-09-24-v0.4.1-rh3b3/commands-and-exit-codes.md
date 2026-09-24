# Commands and exit codes

The raw stdout/stderr and separate exit-code files are in `logs/`. Paths below are relative to this evidence directory. Python versions are from the actual interpreter used for each run.

## Clean Python 3.12 package qualification

Environment: Python 3.12.14, venv `C:\Users\Administrator\AppData\Local\Temp\chstockdata-rh3b3-execution-20260924\clean-python312`; `include-system-site-packages = false`, user site disabled. Dependency specification copied from `publish.yml`.

| Command/action | Result | Evidence |
| --- | --- | --- |
| `python -m pip install ".[dev,mootdx]" build twine` | exit 0 | `logs/python312-workflow-dependencies.log`, `logs/python312-workflow-dependencies.exit` |
| `python -m pytest tests/ -q --no-header` | exit 0; 656 passed, 1 skipped, 15 deselected | `logs/deterministic-pytest.command.txt`, `logs/deterministic-pytest.log`, `logs/deterministic-pytest.exit` |
| `python scripts/check_rh1_static.py` | exit 0; structured gate 24 paths PASS, added-line gate PASS, 287 full Ruff findings | `logs/rh1-static-gate.log`, `logs/rh1-static-gate.exit` |
| `python -m compileall -q src tests` | exit 0 | `logs/compileall.log`, `logs/compileall.exit` |
| `python -m build --outdir docs/audits/evidence/2026-09-24-v0.4.1-rh3b3/build-python312/` | exit 0; fresh wheel and sdist created | `logs/python312-build.log`, `logs/python312-build.exit`, `python312-build-files.txt`, `python312-build-sha256.txt` |
| `python -m twine check dist/recovery-v0.4.1/chstockdata-0.4.1-py3-none-any.whl dist/recovery-v0.4.1/chstockdata-0.4.1.tar.gz` | exit 0; both PASSED | `logs/twine-check.log`, `logs/twine-check.exit` |
| `python -m pip install <selected v0.4.1 wheel>` in a new core venv | exit 0 | `logs/wheel-core-install.log`, `logs/wheel-core-install.exit` |
| `python -m pip install <selected v0.4.1 sdist>` in a separate new core venv | exit 0 | `logs/sdist-core-install.log`, `logs/sdist-core-install.exit` |
| `python -m pip check` in each core install | exit 0 for wheel and sdist | `logs/wheel-core-pip-check.log` / `.exit`; `logs/sdist-core-pip-check.log` / `.exit` |
| `python scripts/check_release_version.py --tag v0.4.1 --project-only` | exit 0 | `logs/release-version-project-only.log`, `logs/release-version-project-only.exit` |
| `python scripts/check_release_version.py --tag v0.4.1` in each installed-artifact venv | exit 0 for wheel and sdist | `logs/wheel-core-release-version.log` / `.exit`; `logs/sdist-core-release-version.log` / `.exit` |
| `chstockdata-mcp --help`; `chstockdata-refresh-vipdoc --help` in the wheel venv | exit 0 for each | `logs/wheel-core-chstockdata-mcp-help.log` / `.exit`; `logs/wheel-core-refresh-vipdoc-help.log` / `.exit` |
| Install selected candidate wheel with each of `[mootdx]`, `[baostock]`, `[mcp]` in separate new venvs, import the extra, then `python -m pip check` | all install/import/check steps exit 0 | `logs/wheel-{mootdx,baostock,mcp}-py312-{install,import,pip-check}.log` and matching `.exit` files |

Version inventory: build 1.6.1, Twine 7.0.0, pytest 9.1.1, Ruff 0.16.8; isolated PEP 517 build output identifies setuptools 84.0.0 in the build environment. See `logs/python312-tool-versions.txt` and `logs/python312-build.log`.

## TradingAgents RH3-A frozen snapshot

Python 3.14.5. The exact command, nine file paths, `-k` selection, deselected cases, snapshot identity, and wheel hashes are in `tradingagents-matrix.txt`. Baseline and candidate each exit 1 with 123 passed, 7 failed, 4 deselected. Raw long tracebacks are `logs/tradingagents-baseline-123-matrix.log` and `logs/tradingagents-candidate-123-matrix.log`; each `.exitcode` records exit 1.

## systematic-investing-os RH3-A frozen snapshot

Python 3.12.14. Offline command: `python -m pytest -q --tb=long --junitxml=<evidence log path>` over the frozen repository's full pytest collection. Baseline and candidate each exit 0 with 929 passed, 5 skipped. Logs and JUnit XML: `logs/systematic-investing-os-baseline-full-rerun.log`, `logs/systematic-investing-os-baseline-full-rerun.junit.xml`, `logs/systematic-investing-os-candidate-full.log`, `logs/systematic-investing-os-candidate-full.junit.xml`.

Live command: `python -m pytest -q -vv --tb=long -o log_cli=true --log-cli-level=DEBUG tests/qualification/test_chstockdata_etf_gate.py -k test_live`; environment variable `SIOS_CHSTOCKDATA_LIVE_QUALIFICATION=1`; direct connection with proxy variables unset and `NO_PROXY=*`. Baseline and candidate each exit 1 with 4 passed, 1 failed, 12 deselected. See `logs/systematic-investing-os-{baseline,candidate}-live-direct.log` and `.log.exitcode`.

