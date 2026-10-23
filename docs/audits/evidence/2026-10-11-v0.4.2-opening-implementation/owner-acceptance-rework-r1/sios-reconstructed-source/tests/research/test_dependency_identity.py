"""Dependency identity is deterministic and declaration-bound."""

from pathlib import Path

from systematic_investing.research.runner import DEPENDENCY_DIGEST, dependency_digest_of


def test_identical_declared_inputs_have_identical_dependency_identity() -> None:
    declarations = (("pyproject.toml", b"dependencies=[]"), ("lock.txt", b"tool==1"))
    assert dependency_digest_of(declarations) == dependency_digest_of(declarations)


def test_material_declared_input_or_provider_change_changes_identity() -> None:
    declarations = (("pyproject.toml", b"dependencies=[]"),)
    base = dependency_digest_of(declarations)
    assert dependency_digest_of((("pyproject.toml", b"dependencies=[x]"),)) != base
    assert dependency_digest_of(
        declarations, qualified_providers=("chstockdata==0.3.1",)
    ) != base


def test_runner_identity_binds_checked_in_dependency_declarations() -> None:
    root = Path(__file__).parents[2]
    declarations = tuple(
        (relative_path, (root / relative_path).read_bytes())
        for relative_path in ("pyproject.toml", "third_party/SOURCES.yaml")
    )
    assert dependency_digest_of(declarations) == DEPENDENCY_DIGEST
