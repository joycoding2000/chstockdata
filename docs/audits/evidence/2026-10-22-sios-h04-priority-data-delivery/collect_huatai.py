"""Collect only the two-year H04 reports, warmup audit and seven notices."""
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
from acquire import capture, ROOT, save

periodic = json.loads((ROOT / "sources/026-513530-official-periodic-p1.raw").read_text(encoding="utf-8"))
notices = json.loads((ROOT / "sources/027-513530-official-notices-p1.raw").read_text(encoding="utf-8"))
selected = []
for item in periodic["contents"]:
    title = item["title"]
    if "中证港股通高股息投资交易型" not in title:
        continue
    for year in (2023, 2024, 2025):
        if f"{year}年年度报告" in title or (year >= 2024 and f"{year}年中期报告" in title):
            kind = "annual" if "年度" in title else "semi"
            selected.append({"label": f"513530-{year}-official-{kind}", "source_listing": "sources/026-513530-official-periodic-p1.raw", "metadata": item})
for item in notices["contents"]:
    day = datetime.fromtimestamp(int(item["activationDate"]) / 1000, timezone(timedelta(hours=8))).date().isoformat()
    if day.startswith("2025-") and "分红公告" in item["title"]:
        selected.append({"label": f"513530-{day}-official-dividend", "source_listing": "sources/027-513530-official-notices-p1.raw", "metadata": item})
assert len(selected) == 12, "bounded list must be 5 reports and 7 dividend notices"
save(ROOT / "huatai-selected.json", selected)
for item in selected:
    capture(item["label"], "https://www.huatai-pb.com" + item["metadata"]["url"])
