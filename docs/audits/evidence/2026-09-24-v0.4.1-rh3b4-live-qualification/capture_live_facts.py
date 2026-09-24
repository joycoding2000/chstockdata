from __future__ import annotations

import json
import sys
from datetime import date, datetime
from enum import Enum
from pathlib import Path


def serializable(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "__dataclass_fields__"):
        return {
            name: serializable(getattr(value, name))
            for name in value.__dataclass_fields__
        }
    if isinstance(value, dict):
        return {str(key): serializable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, set)):
        return [serializable(item) for item in value]
    if hasattr(value, "__dict__"):
        return {key: serializable(item) for key, item in vars(value).items()}
    return repr(value)


def result_data(result):
    return serializable(result)


def main() -> int:
    root = Path(__file__).resolve().parent / "sios"
    sys.path.insert(0, str(root / "src"))
    sys.path.insert(0, str(root / "tests" / "qualification"))

    from live_qualification import live_provider, matrix_requests
    from test_chstockdata_etf_gate import MATRIX

    print(f"MATRIX_EVALUATION_SESSION={MATRIX['evaluation_session']}")
    print(f"MATRIX_WINDOW={json.dumps(MATRIX['window'], sort_keys=True)}")
    provider = live_provider()
    evidence = provider.capability_evidence()
    print("PROVIDER_EVIDENCE=" + json.dumps(serializable(evidence), sort_keys=True))

    for request in matrix_requests(MATRIX):
        instrument_id = str(request.instrument_id)
        print(f"INSTRUMENT_BEGIN={instrument_id}")
        try:
            tradability = provider.fetch_tradability(request.tradability_request)
            print(
                "TRADABILITY="
                + json.dumps(result_data(tradability), sort_keys=True, ensure_ascii=False)
            )
            if not tradability.is_success or not tradability.records:
                print(f"SUPPLEMENTAL_PROBE_STOP=tradability:{instrument_id}")
                return 3

            actions = provider.fetch_corporate_actions(request.corporate_action_request)
            print(
                "CORPORATE_ACTIONS="
                + json.dumps(result_data(actions), sort_keys=True, ensure_ascii=False)
            )
            if not actions.is_success:
                print(f"SUPPLEMENTAL_PROBE_STOP=corporate_actions:{instrument_id}")
                return 4

            bars = provider.fetch_daily_bars(request.bar_request)
            print(
                "DAILY_BARS="
                + json.dumps(result_data(bars), sort_keys=True, ensure_ascii=False)
            )
            if not bars.is_success or not bars.records:
                print(f"SUPPLEMENTAL_PROBE_STOP=daily_bars:{instrument_id}")
                return 5

            calendar = provider.fetch_calendar(request.calendar_request)
            print(
                "CALENDAR="
                + json.dumps(result_data(calendar), sort_keys=True, ensure_ascii=False)
            )
            if not calendar.is_success:
                print(f"SUPPLEMENTAL_PROBE_STOP=calendar:{instrument_id}")
                return 6
        except Exception as error:
            print(f"SUPPLEMENTAL_EXCEPTION_TYPE={type(error).__name__}")
            print(f"SUPPLEMENTAL_PROBE_STOP={instrument_id}")
            return 7
        print(f"INSTRUMENT_END={instrument_id}")

    print("SUPPLEMENTAL_PROBE_RESULT=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
