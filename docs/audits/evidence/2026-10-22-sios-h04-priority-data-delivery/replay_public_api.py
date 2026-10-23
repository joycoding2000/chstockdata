"""Replay captured responses through the existing public API, zero network."""
import json
from pathlib import Path
from urllib.parse import urlsplit
from chstockdata.corporate_actions import get_fund_corporate_actions

ROOT = Path(__file__).resolve().parent


class Cached:
    def __init__(self, path):
        self.text = path.read_text(encoding="utf-8")
    def raise_for_status(self):
        pass
    def json(self):
        return json.loads(self.text)


def request(url, **kwargs):
    if url.endswith("fhsp_513530.html"):
        path = "001-513530-fhsp.raw"
    elif url.endswith("fhsp_513990.html"):
        path = "002-513990-fhsp.raw"
    elif urlsplit(url).path.endswith("/FHGG") and kwargs.get("params",{}).get("fundcode") == "513530":
        assert kwargs["params"]["pageIndex"] == 1
        path = "005-513530-fhgg.raw"
    else:
        raise RuntimeError("uncaptured request refused; no live fallback")
    return Cached(ROOT / "sources" / path)


results = {code:get_fund_corporate_actions(code,start="2023-03-09",end="2025-12-31",as_of_date="2025-12-31",page_size=100,request_get=request) for code in ("513530","513990")}
payload = {"network_requests":0, "uses_existing_production_implementation":True, "does_not_modify_provider":True,
           "evidence_role":"Captured vendor replay, cross-check only; official reports/notices determine completeness and time qualification", "results":results}
(ROOT/"public_api_offline_replay.json").write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
assert results["513530"]["status"] == "success" and len(results["513530"]["items"]) == 7
assert results["513990"]["status"] == "normal_empty"
print(json.dumps({code:{"status":r["status"],"coverage":r["coverage"],"items":len(r["items"])} for code,r in results.items()},ensure_ascii=False))
