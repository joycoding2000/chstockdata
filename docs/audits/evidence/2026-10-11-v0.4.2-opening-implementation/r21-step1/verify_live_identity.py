"""Independently verify saved reader observations, without network access."""

from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
live = HERE / "live"
manifest = json.loads((live / "manifest.json").read_text(encoding="utf-8"))
requests = json.loads((live / "requests.json").read_text(encoding="utf-8"))
assert len(requests) == manifest["request_count"] == 74
assert len(manifest["results"]) == 12 and manifest["exit_code"] == 0
for record in requests:
    raw = (live / record["raw_file"]).read_bytes()
    assert len(raw) == record["bytes"]
    assert sha256(raw).hexdigest() == record["sha256"]
    assert datetime.fromisoformat(record["retrieved_at"]).utcoffset() is not None
    assert record["error_type"] is None

for entry in manifest["results"]:
    payload = json.loads((live / entry["result_file"]).read_text(encoding="utf-8"))
    data = payload["data"]
    digest = data.pop("evidence_hash")
    encoded = json.dumps(data, sort_keys=True, ensure_ascii=False,
                         separators=(",", ":"), allow_nan=False).encode("utf-8")
    assert sha256(encoded).hexdigest() == digest
    assert entry["actual"] == entry["expected"] == data["opening_status"]
    assert entry["pass"] is True
    assert data["instrument"] == entry["instrument"]
    assert data["session_date"] == entry["session_date"]
    assert data["official_query"]["pagination_complete"] is True
    assert data["official_query"]["all_returned_rows_considered"] is True
    assert data["information_available_at"] is None
    assert data["information_basis"] == "UNKNOWN"

result = {"actual_live_points": 12, "raw_requests_sha_verified": 74,
          "actual_live_payload_digests_verified": 12,
          "official_current_queries_complete": 12,
          "network_requests_in_this_verification": 0}
(HERE / "independent-live-identity.json").write_text(
    json.dumps(result, indent=2) + "\n", encoding="utf-8")
print(json.dumps(result))
