import shutil
import zipfile
from pathlib import Path
base = Path(__file__).resolve().parents[4] / "build" / "v042-qualification"
with zipfile.ZipFile(base / "sios.zip") as archive:
    archive.extractall(base / "sios-baseline")
source = Path("C:/Users/Administrator/AppData/Local/Temp/chstockdata-rh3b3-execution-20260924/consumer-sios-rh3a-baseline/var")
for name in ("sios", "sios-baseline"):
    shutil.copytree(source, base / name / "var", dirs_exist_ok=True)
print("Frozen SIOS var copied only into build scratch")

# Restore the two independently SHA-qualified frozen LF report files.
for relative in ("tests/parity/reports/m0-parity-offline-v1.json", "tests/qualification/reports/m0-etf-qualification-offline-v1.json"):
    raw = (source.parent / relative).read_bytes()
    for name in ("sios", "sios-baseline"):
        (base / name / relative).write_bytes(raw)
