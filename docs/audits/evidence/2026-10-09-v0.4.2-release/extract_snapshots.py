import zipfile
from pathlib import Path
root = Path(__file__).resolve().parents[4] / "build" / "v042-qualification"
for name in ("sios", "ta"):
    with zipfile.ZipFile(root / (name + ".zip")) as archive:
        archive.extractall(root / name)
