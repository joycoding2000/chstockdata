from __future__ import annotations
import hashlib
import sys
from pathlib import Path

for root_text in sys.argv[1:]:
    root = Path(root_text)
    files = sorted(path for path in root.rglob("*") if path.is_file())
    digest = hashlib.sha256()
    total = 0
    for path in files:
        relative = path.relative_to(root).as_posix().encode("utf-8")
        size = path.stat().st_size
        total += size
        file_digest = hashlib.sha256(path.read_bytes()).digest()
        digest.update(relative + b"\0" + str(size).encode("ascii") + b"\0" + file_digest)
    print(f"ROOT={root}")
    print(f"FILE_COUNT={len(files)}")
    print(f"TOTAL_BYTES={total}")
    print(f"TREE_SHA256={digest.hexdigest()}")