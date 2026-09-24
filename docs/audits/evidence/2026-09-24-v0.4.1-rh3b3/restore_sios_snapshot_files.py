from __future__ import annotations
import hashlib
import subprocess
import sys
from pathlib import Path

commit = "84fd54fae0740bc06b1d250afa4578be29556956"
relative_paths = (
    "tests/parity/reports/m0-parity-offline-v1.json",
    "tests/qualification/reports/m0-etf-qualification-offline-v1.json",
)
for repo_text in sys.argv[1:]:
    repo = Path(repo_text)
    print(f"REPO={repo}")
    for relative in relative_paths:
        result = subprocess.run(
            ["git", "-C", str(repo), "show", f"{commit}:{relative}"],
            check=True,
            stdout=subprocess.PIPE,
        )
        target = repo / relative
        target.write_bytes(result.stdout)
        print(f"RESTORED={relative} BYTES={len(result.stdout)} SHA256={hashlib.sha256(result.stdout).hexdigest()}")
    status = subprocess.run(
        ["git", "-C", str(repo), "status", "--short", "--untracked-files=all"],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    print("GIT_STATUS_BEGIN")
    print(status.stdout, end="")
    print("GIT_STATUS_END")