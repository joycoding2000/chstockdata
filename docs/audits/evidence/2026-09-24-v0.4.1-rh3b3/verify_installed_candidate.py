from __future__ import annotations

import importlib.metadata as metadata
import site
import sys
from pathlib import Path

source_root = Path(sys.argv[1]).resolve()
module = __import__("chstockdata")
distribution = metadata.distribution("chstockdata")
module_path = Path(module.__file__).resolve()
site_paths = tuple(Path(path).resolve() for path in site.getsitepackages())
assert distribution.version == "0.4.1", distribution.version
assert module.__version__ == "0.4.1", module.__version__
assert any(module_path.is_relative_to(path) for path in site_paths), module_path
assert not module_path.is_relative_to(source_root), module_path

required = {
    "fetch_realtime_quotes",
    "fetch_daily_bars",
    "fetch_trading_calendar",
    "fetch_suspension_info",
    "fetch_delisting_status",
    "fetch_tradability",
    "FetchAttempt",
    "FetchMetadata",
    "FetchResult",
}
assert required <= set(module.__all__), required - set(module.__all__)
assert all(hasattr(module, name) for name in required)

entry_points = {
    item.name for item in metadata.entry_points(group="console_scripts")
}
expected_scripts = {"chstockdata-mcp", "chstockdata-refresh-vipdoc"}
assert expected_scripts <= entry_points, expected_scripts - entry_points

print(f"distribution_version={distribution.version}")
print(f"runtime_version={module.__version__}")
print(f"import_path={module_path}")
print(f"public_exports={len(module.__all__)}")
print("required_api=" + ",".join(sorted(required)))
print("console_entry_points=" + ",".join(sorted(entry_points & expected_scripts)))
