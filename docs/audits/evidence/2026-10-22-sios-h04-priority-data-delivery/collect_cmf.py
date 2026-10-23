"""Anonymous public protocol request, then bounded official report downloads."""
import json
import subprocess
from acquire import capture, ROOT, save

request = json.loads(subprocess.check_output(["node", str(ROOT / "cmf_public_request.cjs")]))
item = capture("513990-official-periodic-public-protocol", "https://www.cmfchina.com/ws-business-server/fund/productAnn", **request)
body = json.loads((ROOT / item["file"]).read_text(encoding="utf-8"))
save(ROOT / "cmf-query-semantics.json", {"productCode": "513990", "type": 1, "pageNum": 1, "pageSize": 50, "protocol": "anonymous public website serialization from captured official JS; no login/cookies; transient signature not logged"})
if body.get("code") != 0:
    raise ValueError("official directory request failed")
selected = []
for record in body["data"]["list"]:
    for year in (2023, 2024, 2025):
        title = record["title"]
        if f"{year}年年度报告" in title or (year >= 2024 and f"{year}年中期报告" in title):
            kind = "annual" if "年度" in title else "semi"
            selected.append({"label": f"513990-{year}-official-{kind}", "source_listing": item["file"], "metadata": record})
assert len(selected) == 5
save(ROOT / "cmf-selected.json", selected)
for record in selected:
    capture(record["label"], record["metadata"]["attachmentUrl"])
