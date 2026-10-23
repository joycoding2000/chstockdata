"""Static import-boundary checks for the trusted M0 kernel.

The scanner uses Python's AST rather than import execution, so optional vendor
packages and future Research dependencies need not be installed to enforce the
boundary.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

_TRUSTED_NAMESPACES = frozenset(
    {
        "domain",
        "instrument_master",
        "data",
        "portfolio",
        "risk",
        "backtest",
        "metrics",
        "boundaries",
        "production",
    }
)
_CORE_NAMESPACES = _TRUSTED_NAMESPACES - {"production"}
_LLM_ROOTS = frozenset({"openai", "anthropic", "langchain", "llama_index"})


@dataclass(frozen=True, order=True)
class ImportBoundaryViolation:
    """One deterministic, source-located dependency-boundary violation."""

    path: str
    line: int
    code: str
    module: str


def _imports(path: Path) -> tuple[tuple[str, int], ...]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend((alias.name, node.lineno) for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append((node.module, node.lineno))
    return tuple(imports)


def _is_module(module: str, root: str) -> bool:
    return module == root or module.startswith(f"{root}.")


def scan_import_boundaries(
    package_root: str | Path,
) -> tuple[ImportBoundaryViolation, ...]:
    """Return all forbidden imports below a ``systematic_investing`` package.

    Provider code remains behind ``adapters/chstockdata``. Trusted core and
    future Production namespaces cannot import provider adapters, Research, or
    LLM libraries. This also prevents provider candidates from becoming rule
    authority through a direct adapter dependency.
    """

    root = Path(package_root)
    violations: list[ImportBoundaryViolation] = []
    for path in sorted(root.rglob("*.py")):
        relative = path.relative_to(root)
        namespace = relative.parts[0] if len(relative.parts) > 1 else ""
        is_vendor_adapter = relative.parts[:2] == ("adapters", "chstockdata")
        for module, line in _imports(path):
            code: str | None = None
            if _is_module(module, "chstockdata") and not is_vendor_adapter:
                code = "VENDOR_IMPORT_OUTSIDE_ADAPTER"
            elif namespace in _CORE_NAMESPACES and _is_module(
                module, "systematic_investing.adapters"
            ):
                code = "PROVIDER_ADAPTER_IMPORT_IN_CORE"
            elif namespace in _TRUSTED_NAMESPACES and _is_module(
                module, "systematic_investing.research"
            ):
                code = "RESEARCH_IMPORT_IN_TRUSTED_NAMESPACE"
            elif namespace in _TRUSTED_NAMESPACES and any(
                _is_module(module, llm_root) for llm_root in _LLM_ROOTS
            ):
                code = "LLM_IMPORT_IN_TRUSTED_NAMESPACE"
            if code is not None:
                violations.append(
                    ImportBoundaryViolation(
                        path=relative.as_posix(),
                        line=line,
                        code=code,
                        module=module,
                    )
                )
    return tuple(sorted(violations))
