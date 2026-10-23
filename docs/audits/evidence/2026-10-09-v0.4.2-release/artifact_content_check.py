import hashlib
import json
import tarfile
import zipfile
from pathlib import Path
out = Path(__file__).resolve().parent
root = out.parents[3]
dist = root / "dist/v042-closeout"
checks = []
with tarfile.open(next(dist.glob("*.tar.gz"))) as archive:
    for member in archive.getmembers():
        if not member.isfile():
            continue
        relative = Path(*Path(member.name).parts[1:])
        target = root / relative
        if target.is_file() and member.name.split("/")[1] not in {"PKG-INFO", "chstockdata.egg-info"}:
            raw = archive.extractfile(member).read()
            # Git checkout uses CRLF for some text members; artifacts copy those bytes.
            checks.append({"file": relative.as_posix(), "matches_worktree": raw == target.read_bytes(), "sha256": hashlib.sha256(raw).hexdigest()})
with zipfile.ZipFile(next(dist.glob("*.whl"))) as archive:
    for name in archive.namelist():
        if name.startswith("chstockdata/"):
            raw = archive.read(name)
            target = root / "src" / name
            checks.append({"file": name, "matches_worktree": target.is_file() and raw == target.read_bytes(), "sha256": hashlib.sha256(raw).hexdigest()})
(out / "artifact-content.json").write_text(json.dumps(checks, indent=2), encoding="utf-8")
print("members checked", len(checks), "mismatches", sum(not c["matches_worktree"] for c in checks))
assert all(c["matches_worktree"] for c in checks)
