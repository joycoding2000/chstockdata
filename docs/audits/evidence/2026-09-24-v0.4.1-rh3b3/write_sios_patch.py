from pathlib import Path
import subprocess
import sys
repo, out = sys.argv[1:]
paths = ["src/systematic_investing/adapters/chstockdata/provider.py", "tests/qualification/test_chstockdata_etf_gate.py"]
result = subprocess.run(["git", "-C", repo, "diff", "--binary", "--unified=3", "--", *paths], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
Path(out).write_bytes(result.stdout)
print(result.stderr.decode("utf-8", errors="replace"), end="")
print(f"PATCH={out} BYTES={len(result.stdout)}")