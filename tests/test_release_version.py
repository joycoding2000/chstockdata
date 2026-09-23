from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts" / "check_release_version.py"


def _write_project(tmp_path: Path, version: str = "0.3.0") -> Path:
    (tmp_path / "pyproject.toml").write_text(
        f"[project]\nversion = \"{version}\"\n",
        encoding="utf-8",
    )
    return tmp_path


def _run(project_root: Path, tag: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--project-root",
            str(project_root),
            "--tag",
            tag,
            "--project-only",
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def test_matching_tag_and_project_version_pass(tmp_path: Path):
    result = _run(_write_project(tmp_path), "v0.3.0")

    assert result.returncode == 0
    assert "version consistency: PASS" in result.stdout


def test_mismatched_tag_and_project_version_fail(tmp_path: Path):
    result = _run(_write_project(tmp_path, version="0.3.0"), "v0.4.0")

    assert result.returncode != 0
    assert "does not match project version" in result.stderr


def test_malformed_tag_fails(tmp_path: Path):
    result = _run(_write_project(tmp_path), "0.3.0")

    assert result.returncode != 0
    assert "must match vMAJOR.MINOR.PATCH" in result.stderr
