"""Local diagnostic from actual failed-run snapshots; never new live evidence."""
import json
import sys
import traceback
from datetime import datetime
from pathlib import Path

OUT = Path(__file__).resolve().parent
SOURCE = OUT / "failed-live-run-1"
sys.path.insert(0, str(OUT.parents[1] / "systematic-investing-os/tests/qualification"))
from live_qualification import execution_proof, json_value
from systematic_investing.data.snapshots import SnapshotReader
from systematic_investing.domain.historical_opening import ExecutionEligibilityMode
from systematic_investing.data.contracts import ProviderSuccess, ProviderEvidence
from dataclasses import replace

report = json.loads((SOURCE / "capabilities/test_live_tradability_adjustment_and_freshness.json").read_text(encoding="utf-8"))
results = []
for symbol in ("510300", "159915", "518880", "511010", "513100", "159509"):
    snapshot, replay = SnapshotReader().load(SOURCE / "capabilities/snapshots" / symbol,
        execution_eligibility_mode=ExecutionEligibilityMode.HISTORICAL_OPENING_R21)
    source_order = replace(replay,
        daily_bars=tuple(sorted(replay.daily_bars, key=lambda bar: bar.session_date)),
        sessions=tuple(sorted(replay.sessions, key=lambda day: day.session_date)))
    record = next(item for item in report["outcomes"] if item["instrument_id"].endswith(symbol)
        and item["capability"] in {"RAW_AVAILABILITY", "CONTROL_RAW_BARS"})
    evidence = record["result"]["evidence"].copy()
    evidence["retrieved_at"] = datetime.fromisoformat(evidence["retrieved_at"])
    evidence["warnings"] = tuple(evidence["warnings"])
    evidence = ProviderEvidence(**evidence)
    item = {"symbol": symbol, "scope": "LOCAL_REPLAY_OF_ACTUAL_LIVE_INPUTS_ONLY",
            "original_tuple_equals_replay": source_order == replay,
            "content_digests_equal": source_order.content_digest() == replay.content_digest(),
            "source_bar_dates": [str(bar.session_date) for bar in source_order.daily_bars],
            "replay_bar_dates": [str(bar.session_date) for bar in replay.daily_bars]}
    try:
        item["proof"] = execution_proof(source_order.daily_bars[0].instrument_id,
            source_order.historical_opening_evidence[0].session_date,
            ProviderSuccess(source_order.daily_bars, evidence), ProviderSuccess(source_order.sessions, evidence),
            ProviderSuccess(source_order.corporate_actions, evidence), (None, source_order.tradability),
            ProviderSuccess(source_order.historical_opening_evidence, evidence),
            directory=OUT / sys.argv[1] / "snapshots", blocked=symbol in {"513100", "159509"})
        item["result"] = "PASS"
    except Exception as error:
        item.update(result="FAIL", exception_type=type(error).__name__, traceback=traceback.format_exc())
    results.append(item)
target = OUT / sys.argv[1] / "report.json"
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(json.dumps(json_value(results), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps([{key: row[key] for key in ("symbol", "result", "content_digests_equal")} for row in results]))
