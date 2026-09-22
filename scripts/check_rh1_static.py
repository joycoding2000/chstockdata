"""Run the repeatable v0.4.0 RH1 static-quality gate.

The repository deliberately keeps the legacy Ruff debt visible.  This gate
therefore combines two checks:

* the v0.4.0 structured modules and their focused tests must be Ruff-clean;
* a full Ruff scan must not report a finding on a source/test line added since
  the frozen v0.3.0 baseline.

The second check uses the Git diff rather than a permanent Ruff ignore list, so
RH2/RH3 can rerun it after committed or uncommitted changes without hiding
legacy findings from the normal full-tree report.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

BASELINE_SHA = "143eb5a61e11003a4b29461eeb78deec0ab8d8e5"
ROOT = Path(__file__).resolve().parents[1]

STRUCTURED_PATHS = (
    "src/chstockdata/capabilities.py",
    "src/chstockdata/fetch_result.py",
    "src/chstockdata/quote_chain.py",
    "src/chstockdata/daily_bars.py",
    "src/chstockdata/trading_calendar.py",
    "src/chstockdata/suspension.py",
    "src/chstockdata/delisting.py",
    "src/chstockdata/tradability.py",
    "tests/test_cached_ohlcv_structured.py",
    "tests/test_capability_isolation.py",
    "tests/test_daily_bars_contract.py",
    "tests/test_daily_bars_legacy_compat.py",
    "tests/test_daily_bars_routing.py",
    "tests/test_daily_bars_schema.py",
    "tests/test_delisting_structured.py",
    "tests/test_fetch_result_core.py",
    "tests/test_live_capability_probes.py",
    "tests/test_mootdx_capability_health.py",
    "tests/test_mootdx_capability_isolation.py",
    "tests/test_routing_observation.py",
    "tests/test_structured_semantics_phase11.py",
    "tests/test_suspension_structured.py",
    "tests/test_tradability.py",
    "tests/test_trading_calendar_structured.py",
)

_HUNK_RE = re.compile(r"^@@ .* \+(\d+)(?:,(\d+))? ")


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _ruff(paths: tuple[str, ...]) -> tuple[int, list[dict]]:
    result = _run(
        sys.executable,
        "-m",
        "ruff",
        "check",
        *paths,
        "--output-format",
        "json",
    )
    try:
        findings = json.loads(result.stdout or "[]")
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Ruff did not return JSON (exit={result.returncode}): {result.stdout[:500]}"
        ) from exc
    if not isinstance(findings, list):
        raise RuntimeError("Ruff JSON output was not a finding list")
    return result.returncode, findings


def _relative_path(filename: str) -> str:
    path = Path(filename)
    if not path.is_absolute():
        path = ROOT / path
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _added_line_ranges() -> dict[str, list[tuple[int, int]]]:
    result = _run(
        "git",
        "diff",
        "--no-ext-diff",
        "--unified=0",
        BASELINE_SHA,
        "--",
        "src",
        "tests",
    )
    if result.returncode != 0:
        raise RuntimeError(f"git diff failed: {result.stderr.strip()}")

    ranges: dict[str, list[tuple[int, int]]] = {}
    current_file: str | None = None
    for line in result.stdout.splitlines():
        if line.startswith("+++ b/"):
            current_file = line[6:].replace("\\", "/")
            continue
        if current_file is None:
            continue
        match = _HUNK_RE.match(line)
        if not match:
            continue
        start = int(match.group(1))
        count = int(match.group(2) or "1")
        if count:
            ranges.setdefault(current_file, []).append((start, start + count - 1))

    untracked = _run("git", "ls-files", "--others", "--exclude-standard", "--", "src", "tests")
    if untracked.returncode != 0:
        raise RuntimeError(f"git ls-files failed: {untracked.stderr.strip()}")
    for path in untracked.stdout.splitlines():
        if path:
            ranges[path.replace("\\", "/")] = [(1, 2**31 - 1)]
    return ranges


def _is_added_line(finding: dict, ranges: dict[str, list[tuple[int, int]]]) -> bool:
    path = _relative_path(str(finding.get("filename", "")))
    row = int(finding.get("location", {}).get("row", 0))
    return any(start <= row <= end for start, end in ranges.get(path, ()))


def main() -> int:
    baseline_check = _run("git", "cat-file", "-e", f"{BASELINE_SHA}^{{commit}}")
    if baseline_check.returncode != 0:
        print(f"Missing RH1 baseline commit: {BASELINE_SHA}", file=sys.stderr)
        return 2

    version = _run(sys.executable, "-m", "ruff", "--version")
    if version.returncode != 0:
        print(version.stderr.strip(), file=sys.stderr)
        return 2
    print(f"Ruff: {version.stdout.strip()}")

    structured_exit, structured_findings = _ruff(STRUCTURED_PATHS)
    if structured_findings:
        print(
            f"Structured gate: FAIL ({len(structured_findings)} findings)",
            file=sys.stderr,
        )
        print(json.dumps(structured_findings, ensure_ascii=False, indent=2))
    else:
        print(f"Structured gate: PASS ({len(STRUCTURED_PATHS)} paths)")

    full_exit, full_findings = _ruff(("src", "tests"))
    if full_exit not in (0, 1):
        print(f"Full Ruff invocation failed with exit={full_exit}", file=sys.stderr)
        return 2
    print(f"Full Ruff findings (visible legacy debt included): {len(full_findings)}")

    ranges = _added_line_ranges()
    new_findings = [finding for finding in full_findings if _is_added_line(finding, ranges)]
    if new_findings:
        print(
            f"Added-line gate: FAIL ({len(new_findings)} findings since {BASELINE_SHA[:7]})",
            file=sys.stderr,
        )
        for finding in new_findings:
            print(
                f"{_relative_path(finding['filename'])}:{finding['location']['row']} "
                f"{finding['code']} {finding['message']}",
                file=sys.stderr,
            )
    else:
        print(
            f"Added-line gate: PASS (no findings on lines added since {BASELINE_SHA[:7]})"
        )

    return 1 if structured_exit != 0 or structured_findings or new_findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
