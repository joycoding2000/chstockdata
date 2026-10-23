"""Root verification using the same declared, read-only dependency runtime."""
import contextlib
import json
from pathlib import Path
import runpy
import sys

here = Path(__file__).resolve().parent
final = json.loads((here / "final.json").read_text(encoding="utf-8"))
sys.argv = [str(here / "run_tests.py"), "independent-final", *final["argv"][2:]]
with (here / "independent-final.log").open("w", encoding="utf-8") as log:
    with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
        runpy.run_path(str(here / "run_tests.py"), run_name="__main__")
