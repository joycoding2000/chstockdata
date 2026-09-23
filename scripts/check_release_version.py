"""Validate the version contract used by the PyPI release workflow.

The release tag, source project metadata, installed distribution metadata, and
runtime ``__version__`` must all describe the same stable ``vMAJOR.MINOR.PATCH``
version.  This script intentionally uses only the Python standard library so
the workflow can run it before installing optional package dependencies.
"""

from __future__ import annotations

import argparse
import importlib
import importlib.metadata as metadata
import os
import re
import site
import sys
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - release workflow uses Python 3.12+
    tomllib = None  # type: ignore[assignment]


TAG_RE = re.compile(r"^v(?P<version>\d+\.\d+\.\d+)$")


class ReleaseVersionError(RuntimeError):
    """Raised when one part of the release version contract is invalid."""


def _parse_tag(tag: str) -> str:
    match = TAG_RE.fullmatch(tag)
    if match is None:
        raise ReleaseVersionError(
            f"release tag {tag!r} must match vMAJOR.MINOR.PATCH"
        )
    return match.group("version")


def _read_project_version(project_root: Path) -> str:
    pyproject = project_root / "pyproject.toml"
    if tomllib is None:
        raise ReleaseVersionError(
            "Python 3.11+ is required to parse pyproject.toml without extra dependencies"
        )
    try:
        with pyproject.open("rb") as stream:
            document: dict[str, Any] = tomllib.load(stream)
    except FileNotFoundError as exc:
        raise ReleaseVersionError(f"missing project metadata: {pyproject}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ReleaseVersionError(f"invalid TOML in {pyproject}: {exc}") from exc

    project = document.get("project")
    version = project.get("version") if isinstance(project, dict) else None
    if not isinstance(version, str) or not version:
        raise ReleaseVersionError(f"project.version is missing or invalid in {pyproject}")
    return version


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _site_package_paths() -> tuple[Path, ...]:
    paths = {Path(path).resolve() for path in site.getsitepackages()}
    return tuple(sorted(paths))


def _check_installed_version(
    expected_version: str,
    *,
    distribution_name: str,
    module_name: str,
    project_root: Path,
) -> None:
    try:
        distribution = metadata.distribution(distribution_name)
    except metadata.PackageNotFoundError as exc:
        raise ReleaseVersionError(
            f"installed distribution {distribution_name!r} was not found"
        ) from exc

    installed_version = distribution.version
    if installed_version != expected_version:
        raise ReleaseVersionError(
            "installed distribution metadata version "
            f"{installed_version!r} does not match expected version {expected_version!r}"
        )

    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        raise ReleaseVersionError(
            f"installed runtime module {module_name!r} could not be imported"
        ) from exc

    runtime_version = getattr(module, "__version__", None)
    if runtime_version != expected_version:
        raise ReleaseVersionError(
            f"runtime {module_name}.__version__ {runtime_version!r} does not match "
            f"expected version {expected_version!r}"
        )

    module_file = getattr(module, "__file__", None)
    if not module_file:
        raise ReleaseVersionError(f"runtime module {module_name!r} has no __file__")
    module_path = Path(module_file).resolve()
    distribution_path = Path(distribution.locate_file("")).resolve()
    site_paths = _site_package_paths()
    if not any(_is_relative_to(module_path, path) for path in site_paths):
        raise ReleaseVersionError(
            f"runtime module is not installed under an isolated site-packages path: "
            f"{module_path}"
        )
    if not any(_is_relative_to(distribution_path, path) for path in site_paths):
        raise ReleaseVersionError(
            f"distribution metadata is not installed under an isolated site-packages "
            f"path: {distribution_path}"
        )
    if _is_relative_to(module_path, project_root):
        raise ReleaseVersionError(
            f"runtime module resolved from the source checkout instead of the installed "
            f"artifact: {module_path}"
        )

    print(f"installed location: PASS {module_path}")
    print(
        "installed versions: PASS "
        f"metadata={installed_version} runtime={runtime_version}"
    )


def validate(
    *,
    tag: str,
    project_root: Path,
    distribution_name: str = "chstockdata",
    module_name: str = "chstockdata",
    check_installed: bool = True,
) -> str:
    """Validate the release version contract and return the expected version."""
    expected_version = _parse_tag(tag)
    project_version = _read_project_version(project_root)
    if project_version != expected_version:
        raise ReleaseVersionError(
            f"tag version {expected_version!r} does not match project version "
            f"{project_version!r}"
        )

    print(
        "version consistency: PASS "
        f"tag={tag} project={project_version}"
    )
    if check_installed:
        _check_installed_version(
            expected_version,
            distribution_name=distribution_name,
            module_name=module_name,
            project_root=project_root,
        )
    return expected_version


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tag",
        default=os.environ.get("GITHUB_REF_NAME"),
        help="release tag, defaulting to GITHUB_REF_NAME",
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path.cwd(),
        help="checkout containing pyproject.toml",
    )
    parser.add_argument("--distribution", default="chstockdata")
    parser.add_argument("--module", default="chstockdata")
    parser.add_argument(
        "--project-only",
        action="store_true",
        help="validate only the tag and source project version",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if not args.tag:
        print("release tag is required via --tag or GITHUB_REF_NAME", file=sys.stderr)
        return 2
    try:
        validate(
            tag=args.tag,
            project_root=args.project_root.resolve(),
            distribution_name=args.distribution,
            module_name=args.module,
            check_installed=not args.project_only,
        )
    except (ReleaseVersionError, OSError) as exc:
        print(f"release version check failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
