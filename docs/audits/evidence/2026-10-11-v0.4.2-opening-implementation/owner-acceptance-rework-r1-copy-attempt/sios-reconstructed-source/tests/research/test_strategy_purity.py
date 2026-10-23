"""Architecture guard: canonical strategies are pure decision logic."""

import ast
from pathlib import Path


def test_canonical_strategy_modules_do_not_access_external_state() -> None:
    root = Path(__file__).parents[2] / "src" / "systematic_investing" / "research" / "strategies"
    forbidden_imports = {"pathlib", "os", "socket", "requests", "httpx", "urllib"}
    forbidden_names = {"Path", "open", "read_bytes", "now", "today", "time"}
    for path in sorted(root.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert not any(
                    alias.name.split(".")[0] in forbidden_imports for alias in node.names
                ), path
            if isinstance(node, ast.ImportFrom):
                assert (node.module or "").split(".")[0] not in forbidden_imports, path
            if isinstance(node, ast.Name):
                assert node.id not in forbidden_names, f"{path}:{node.lineno}:{node.id}"
