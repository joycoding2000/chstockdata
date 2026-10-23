"""Shared pytest configuration for the M0 offline quality harness.

Keep this module minimal: fixtures that carry business semantics belong to the
test module that defines the behavior under test, not here.

The golden scenario harness under ``tests/golden`` is shared by the golden
tests and the reproducibility integration tests, so its directory is added to
the import path here instead of duplicating the loader.
"""

import sys
from pathlib import Path

_GOLDEN_DIR = Path(__file__).resolve().parent / "golden"
if str(_GOLDEN_DIR) not in sys.path:
    sys.path.insert(0, str(_GOLDEN_DIR))
