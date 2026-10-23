"""Task-local W0 release evidence helper; never shipped as package code."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from datetime import datetime, timezone

ROOT = Path(r"C:\Users\Administrator\.codex\worktrees\w0-v043-release\chstockdata")
ORIGINAL = Path(r"D:\Dev\Projects\chstockdata")
TEMP = ORIGINAL / "build/w0-v043"
EVIDENCE = ROOT / "docs/audits/evidence/2026-10-19-v0.4.3-release"
BASE = "9543d03310b25be9963227a2a226366de04276ec"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, obj):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def git(*args, cwd=ROOT):
    return subprocess.check_output(["git", *args], cwd=cwd).decode("utf-8").strip()


def run(name, command, cwd=ROOT, *, extra_env=None):
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update(PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    env.pop("PYTHONPATH", None)
    if extra_env:
        env.update(extra_env)
    started = datetime.now(timezone.utc).isoformat()
    then = time.monotonic()
    with (EVIDENCE / f"{name}.stdout.txt").open("wb") as out, (EVIDENCE / f"{name}.stderr.txt").open("wb") as err:
        p = subprocess.run(list(map(str, command)), cwd=cwd, env=env, stdout=out, stderr=err)
    info = {"command": list(map(str, command)), "cwd": str(cwd), "started_at_utc": started,
            "seconds": round(time.monotonic() - then, 3), "exit_code": p.returncode,
            "environment_overrides": extra_env or {},
            "logs": {k: digest(EVIDENCE / f"{name}.{k}.txt") for k in ("stdout", "stderr")}}
    save(EVIDENCE / f"{name}.command.json", info)
    print(json.dumps({"step": name, "exit_code": p.returncode, "seconds": info["seconds"]}), flush=True)
    if p.returncode:
        print((EVIDENCE / f"{name}.stdout.txt").read_text(encoding="utf-8", errors="replace")[-10000:])
        print((EVIDENCE / f"{name}.stderr.txt").read_text(encoding="utf-8", errors="replace")[-5000:])
        raise SystemExit(p.returncode)
    return info


def prepare():
    assert git("rev-parse", "HEAD") == BASE
    assert not git("status", "--porcelain")
    TEMP.mkdir(parents=True, exist_ok=True)
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    original_status = git("status", "--porcelain", "--untracked-files=normal", cwd=ORIGINAL)
    files = [line[3:] for line in original_status.splitlines() if line.startswith("?? ") and not line.endswith("/")]
    save(EVIDENCE / "original-worktree.json", {"head": git("rev-parse", "HEAD", cwd=ORIGINAL),
         "tracked_diff": git("diff", "HEAD", cwd=ORIGINAL),
         "status_normal": original_status,
         "untracked_files": {p: digest(ORIGINAL / p) for p in files if p}})
    git("switch", "-c", "codex/w0-v043-release")
    for name in ("pyproject.toml", "src/chstockdata/__init__.py"):
        p = ROOT / name
        data = p.read_bytes()
        before, after = b'"0.4.2"', b'"0.4.3"'
        assert data.count(before) == 1
        p.write_bytes(data.replace(before, after))
    p = ROOT / "README.md"
    s = p.read_text(encoding="utf-8")
    old = """The unreleased DR04-P addition provides the public API
`get_sina_daily_fund_flow` for lossless Sina daily `r0_net` observations.
See the [consumer contract and usage](docs/dr04-p-daily-fund-flow.md).
DR04-P has [Owner Acceptance](docs/audits/2026-10-18-dr04-p-owner-acceptance.md)
and is not part of the published v0.4.2 package."""
    new = """Version 0.4.3 adds the Owner-accepted DR04-P public API
`get_sina_daily_fund_flow` and the public `FundFlowCalendar`, `FundFlowBudget`
and `DailyFundFlowResult` types for lossless Sina daily `r0_net` observations.
Install with `python -m pip install chstockdata==0.4.3`.
See the [consumer contract and usage](docs/dr04-p-daily-fund-flow.md) and
[v0.4.3 release notes](docs/releases/v0.4.3.md).
Consumers supply a qualified trading calendar and explicit request budget.
Numeric completeness does not establish zero-value semantics, source finality,
historical PIT, full-market coverage or strategy qualification; DR04-M remains
outside this release."""
    assert old in s
    s = s.replace(old, new).replace("The\ncurrent published version is `0.4.2`", "The\ncurrent release version is `0.4.3`")
    s = s.replace("/chstockdata/0.4.2/)", "/chstockdata/0.4.3/)").replace("/releases/tag/v0.4.2)).", "/releases/tag/v0.4.3)).")
    p.write_text(s, encoding="utf-8", newline="\n")
    (ROOT / "docs/releases/v0.4.3.md").write_text("""# chstockdata v0.4.3

v0.4.3 delivers the Owner-accepted DR04-P Sina daily fund-flow numerical API,
merged at `9543d03310b25be9963227a2a226366de04276ec`, on top of published
v0.4.2 (`17af23fe8183f740150dc01dd877473afe3911b7`).

```bash
python -m pip install chstockdata==0.4.3
```

## New public entries

```python
from chstockdata import (
    get_sina_daily_fund_flow,
    FundFlowCalendar,
    FundFlowBudget,
    DailyFundFlowResult,
)
```

`get_sina_daily_fund_flow` returns lossless daily Sina `r0_net` observations:
a target date with its preceding four completed market trading days, or an
explicit closed date range. Consumers provide a qualified, fully covering
`FundFlowCalendar`; `FundFlowBudget` bounds pages, HTTP attempts, retries,
elapsed time and request timeout. `DailyFundFlowResult` preserves decimal
amount strings in CNY yuan, daily statuses, coverage, pagination consistency,
partial failures, provenance and response hashes. Multi-page completion
includes a first-page anchor recheck. See the unchanged
[consumer contract and usage](../dr04-p-daily-fund-flow.md).

## Compatibility and boundaries

The DR04-P implementation, accepted fixtures, tests and numerical contract
are unchanged from Owner acceptance. This release changes only version
metadata and delivery documentation/evidence. The legacy `get_fund_flow`
text interface, `FetchResult`, existing public exports, dependency constraints,
price-scale Golden contract and v0.4.2 historical-opening boundaries remain
unchanged. Existing MCP and refresh CLI entry points remain available; the
MCP and mootdx extras continue to require separate environments.

`COMPLETE` establishes numerical completeness for the requested window, not
economic meaning of raw zeros, historical first-known time, source finality,
revision timing, source-frozen snapshots, security applicability or PIT.
These qualifications remain UNKNOWN where specified by the contract.
DR04-M, full-market qualification, Mishi S08 and historical PIT qualification
are not delivered. SIOS H01/P2/H04 input blockers remain unchanged. Neither
consumer repository, dependency pin nor strategy contract is modified.

## Release verification

The release follows the existing tag-triggered `publish.yml` workflow:
full deterministic tests, RH1 static checks, compilation, version consistency,
wheel/sdist build and Twine validation, independent wheel/sdist installation,
dependency checks, CLI/MCP compatibility and offline DR04-P artifact checks.
The [W0 preflight audit](../audits/2026-10-19-v0.4.3-preflight.md) records
commands, outcomes, identities and evidence hashes. Formal publication and
clean installation from PyPI are recorded separately after release; the
release tag is never moved to add post-release evidence.
""", encoding="utf-8")
    save(EVIDENCE / "preflight-baseline.json", {"base_sha": BASE, "v042_sha": "17af23fe8183f740150dc01dd877473afe3911b7",
         "remote_main_verified": BASE, "remote_v043_tag": "ABSENT", "pypi_latest": "0.4.2", "pypi_v043": "ABSENT",
         "github_release_v043": "404_ABSENT", "owner_release_authorization": "YES_CONDITIONAL",
         "external_contract_sha256": "1c7c37b1514032ef08d9714fe8cfa4f722c0f730af1e58608dbc6b45eaffeba1"})
    print(git("diff", "--stat"))


if __name__ == "__main__":
    if sys.argv[1] == "prepare":
        prepare()
    elif sys.argv[1] == "run":
        run(sys.argv[2], sys.argv[3:])
