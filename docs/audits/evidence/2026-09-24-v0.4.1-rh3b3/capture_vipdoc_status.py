from __future__ import annotations
import json
import os
import sys
from pathlib import Path
import chstockdata

root = Path(os.environ["CHSTOCKDATA_VIPDOC_HISTORY_DIR"])
status = chstockdata.vipdoc_history_status()
print(f"PYTHON={sys.version.split()[0]}")
print(f"DISTRIBUTION_RUNTIME={chstockdata.__version__}")
print(f"IMPORT_PATH={chstockdata.__file__}")
print("STATUS=" + json.dumps({key: status.get(key) for key in ("available", "enabled", "stale", "age_days", "latest_bar_date", "max_staleness_days", "record_counts", "dir")}, sort_keys=True))
manifest = status.get("manifest") or {}
print("SOURCE=" + json.dumps({key: manifest.get(key) for key in ("downloaded_at", "source_last_modified", "source_url", "zip_sha256")}, sort_keys=True))
max_dates = manifest.get("max_bar_date") or {}
for market, code in (("sh", "000001"), ("sh", "510300"), ("sh", "511010"), ("sh", "518880"), ("sz", "159915")):
    frame = chstockdata.load_vipdoc_daily(code, root=root, market=market)
    if frame is None:
        print(f"DAY={market}/{code} rows=0 frame=None")
        continue
    date_cols = [col for col in frame.columns if str(col).lower() in {"date", "trade_date", "session_date"}]
    dates = frame[date_cols[0]] if date_cols else None
    print(f"DAY={market}/{code} rows={len(frame)} columns={list(map(str, frame.columns))} date_min={dates.min() if dates is not None else 'UNAVAILABLE'} date_max={dates.max() if dates is not None else 'UNAVAILABLE'} manifest_max={max_dates.get(code)}")