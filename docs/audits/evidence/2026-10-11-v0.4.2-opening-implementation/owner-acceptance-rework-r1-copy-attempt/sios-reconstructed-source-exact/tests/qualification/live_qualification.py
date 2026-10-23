"""Live qualification helpers (opt-in release-environment runs only).

These helpers are used by opt-in live tests and deterministic orchestration
regressions. Live runs explicitly admit the 0.4.2 candidate with a local vipdoc tree; the package
needs no API keys, and no credentials or secret values are read, logged, or
recorded here.
"""

from __future__ import annotations

from dataclasses import fields, dataclass, is_dataclass, replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from hashlib import sha256
import json
import os
import traceback
from pathlib import Path
from typing import Any

from systematic_investing.adapters.chstockdata.provider import (
    ChStockDataProvider,
    LibraryChStockDataClient,
)
from systematic_investing.data.ports import (
    CalendarRequest,
    CorporateActionRequest,
    DailyBarRequest,
    TradabilityRequest,
)
from systematic_investing.domain.identifiers import InstrumentId

MARKET_TIMEZONE = timezone(timedelta(hours=8))


def live_provider() -> ChStockDataProvider:
    """Real explicit 0.4.2 qualification candidate and wall-clock retrieval."""
    client = LibraryChStockDataClient(historical_opening_candidate=True)
    return ChStockDataProvider(client=client, clock=lambda: datetime.now(MARKET_TIMEZONE))


def json_value(value):
    """Preserve canonical results and public request evidence without repr objects."""
    if isinstance(value, BaseException):
        return {"type": type(value).__name__, "message": str(value)}
    if is_dataclass(value):
        return {field.name: json_value(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, dict):
        return {str(key): json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [json_value(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, (date, datetime, Decimal, Path)):
        return str(value)
    return {"object_type": type(value).__name__}


class CapabilityOutcomes:
    """Attempt every independent capability, persist evidence, then fail together."""

    def __init__(self, name, *, directory=None):
        self.name = name
        self.directory = Path(directory or os.environ["SIOS_LIVE_EVIDENCE_DIR"])
        self.results = []

    def check(self, instrument, capability, call):
        started = datetime.now(MARKET_TIMEZONE).isoformat()
        try:
            value = call()
            item = {"status": "PASS", "result": json_value(value)}
        except Exception as error:
            value = None
            item = {"status": "FAIL", "error": json_value(error), "error_locations": [
                {"file": frame.filename, "line": frame.lineno, "function": frame.name}
                for frame in traceback.extract_tb(error.__traceback__)]}
        self.results.append({"instrument_id": str(instrument), "capability": capability,
                             "started_at": started,
                             "finished_at": datetime.now(MARKET_TIMEZONE).isoformat(), **item})
        return value

    def finish(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        report = {"test": self.name, "outcomes": self.results}
        (self.directory / f"{self.name}.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        failures = [f"{item['instrument_id']}:{item['capability']}:{item['error']}"
                    for item in self.results if item["status"] == "FAIL"]
        assert not failures, "\n".join(failures)


def require_success(result, *, nonempty=True):
    assert result is not None and result.is_success, str(result)
    if nonempty:
        assert result.records, "empty successful response"
    return result


def historical_gap(provider, request):
    from systematic_investing.adapters.chstockdata.provider import HistoricalSuspensionUnavailableError
    from systematic_investing.domain.market import AvailabilityBasis

    result = provider.fetch_tradability(request)
    assert not result.is_success, "legacy historical PIT must not be fabricated"
    assert type(result.cause) is HistoricalSuspensionUnavailableError
    gap = provider.historical_suspension_gap(request, result)
    assert len(gap) == 1 and gap[0].status.value == "UNKNOWN"
    assert gap[0].availability.information_available_at is None
    assert gap[0].availability.availability_basis is AvailabilityBasis.UNKNOWN
    return result, gap


def opening_fact(provider, instrument, session, *, blocked=False):
    from systematic_investing.data.ports import HistoricalOpeningRequest

    result = require_success(provider.fetch_historical_opening_evidence(
        HistoricalOpeningRequest((instrument,), session)))
    assert len(result.records) == 1
    fact = result.records[0]
    assert fact.instrument_id == instrument and fact.session_date == session
    data = fact.payload
    assert fact.target_execution_at == datetime.combine(session, datetime.min.time(),
        MARKET_TIMEZONE).replace(hour=9, minute=30)
    assert data["policy_version"] == "R2.1" and data["evidence_hash"]
    assert data["official_query"]["status"] in {"success", "normal_empty"}
    assert data["official_query"]["pagination_complete"]
    assert data["opening_status"] == ("BLOCKED_CONFIRMED" if blocked else "OPEN_ACTIVITY_CONFIRMED")
    assert data["official_block_at_target"] == blocked
    assert not data["source_conflict"]
    if not blocked:
        assert data["tdx_activity"]["qualified"]
    return result


def freshness_proof(bars_result, calendar_result, instrument, session):
    from systematic_investing.data.quality import CanonicalDataset, DataQualityGate, DatasetPolicy
    from systematic_investing.domain.runs import RunPurpose
    from systematic_investing.instrument_master.repository import default_m0_master

    bars = require_success(bars_result).records
    sessions = require_success(calendar_result).records
    assert any(bar.session_date == session for bar in bars)
    dataset = CanonicalDataset(bars, sessions, (), (), ())
    gate = DataQualityGate(default_m0_master(), DatasetPolicy())
    cutoff = datetime.combine(session, datetime.min.time(), MARKET_TIMEZONE).replace(hour=15, minute=30)

    def evaluate(data):
        return gate.evaluate(data, purpose=RunPurpose.DECISION,
                             intended_decision_session=session,
                             information_cutoff=cutoff,
                             evaluated_at=datetime.now(MARKET_TIMEZONE))

    good = evaluate(dataset)
    assert good.status.value == "PASS", str(good)
    stale = evaluate(replace(dataset, daily_bars=tuple(b for b in bars if b.session_date < session)))
    assert "STALE_INFORMATION" in stale.reason_codes
    missing = evaluate(replace(dataset, daily_bars=tuple(replace(b, pre_close=None) for b in bars)))
    assert "MISSING_REQUIRED_FIELD" in missing.reason_codes
    return {"fresh": good, "stale_control": stale, "missing_control": missing}


class QualificationTargets:
    """Declared test targets only; no strategy signal or evidence input."""

    def __init__(self, instrument, session):
        from systematic_investing.domain.identifiers import SleeveId
        from systematic_investing.domain.portfolio import TargetContribution
        self.session = session
        # Enough declared test allocation for the bond ETF's 100-share lot.
        self.target = TargetContribution(instrument, SleeveId.CORE, "live-qualification", "1", Decimal("0.50"))
        self.contexts = []

    def contributions_for(self, context):
        self.contexts.append(context)
        return (self.target,) if context.session_date == self.session else None


def execution_proof(instrument, session, bars_result, calendar_result, actions_result,
                    gap_result, opening_result, *, directory, blocked=False):
    """Real adapter records -> v3 replay -> real engine -> RAW-open fill proof."""
    from systematic_investing.backtest.engine import DailyBarEngine, EngineClock
    from systematic_investing.backtest.execution import ExecutionModel
    from systematic_investing.data.quality import CanonicalDataset
    from systematic_investing.data.snapshots import SnapshotWriter, SnapshotReader, manifest_to_dict
    from systematic_investing.domain.execution import AccountFeeConfig, BrokerFeeProfile
    from systematic_investing.domain.historical_opening import ExecutionEligibilityMode, OPENING_CLOCK_ID
    from systematic_investing.domain.market import MarketCalendar, TradeSide
    from systematic_investing.domain.runs import RunManifest
    from systematic_investing.domain.money import Money
    from systematic_investing.instrument_master.repository import default_m0_master

    bars = require_success(bars_result).records
    sessions = require_success(calendar_result).records
    # Halt controls isolate event eligibility; they do not qualify QDII actions.
    actions = () if blocked else require_success(actions_result, nonempty=False).records
    facts = require_success(opening_result).records
    assert gap_result is not None, "no certified legacy failure"
    _, gap = gap_result
    mode = ExecutionEligibilityMode.HISTORICAL_OPENING_R21
    dataset = CanonicalDataset(bars, sessions, gap, actions, (), facts)
    now = datetime.now(MARKET_TIMEZONE)
    snapshot = SnapshotWriter("chstockdata", "0.4.2", ChStockDataProvider.ADAPTER_VERSION).persist(
        dataset, snapshot_dir=Path(directory) / instrument.symbol,
        created_at=now, knowledge_cutoff=now, retrieved_at=now, execution_eligibility_mode=mode)
    loaded, replay = SnapshotReader().load(Path(directory) / instrument.symbol, execution_eligibility_mode=mode)
    assert loaded == snapshot
    assert replay.content_digest() == dataset.content_digest(), "snapshot canonical content changed"
    assert snapshot.snapshot_schema_version == "v3-historical-opening"
    assert snapshot.execution_policy == "R2.1" and snapshot.execution_clock == OPENING_CLOCK_ID
    calendar = MarketCalendar(instrument.exchange.value, sessions[0].snapshot_version, sessions)
    previous = max(s.session_date for s in sessions if s.is_open and s.session_date < session)
    target = QualificationTargets(instrument, previous)
    master = default_m0_master()
    if blocked:
        # A separate test-only master isolates event veto. Production QDII scope stays rejected.
        reference = master.resolve_instrument(InstrumentId.parse("XSHG:510300"), session)
        master.register_instrument(replace(reference, instrument_id=instrument, display_name="official-halt-control"))
    fees = AccountFeeConfig("LIVE-QUALIFICATION", "1", (
        BrokerFeeProfile("ACCT:MAIN", "1", Decimal("0.0003"), Decimal("5"),
                         "qualification-test-account", date(2022, 1, 4), None),))
    model = ExecutionModel(Decimal("0.001"), Decimal("0.001"))
    engine = DailyBarEngine(calendar=calendar, clock=EngineClock.shanghai(), master=master,
        account_fees=fees, execution_model=model, bars=replay.daily_bars,
        tradability=replay.tradability, corporate_actions=replay.corporate_actions,
        historical_opening_evidence=replay.historical_opening_evidence,
        execution_eligibility_mode=mode, target_source=target, initial_cash=Money(Decimal("100000")))
    result = engine.run(start_session=previous, end_session=session)
    plans = result.session(previous).plans
    assert plans and plans[0].order_quantity > 0, "empty plan cannot prove eligibility"
    assert all(not hasattr(context, "historical_opening_evidence") for context in target.contexts)
    if blocked:
        assert not result.fills
        assert len(result.session(session).activation.orders) == 1
        assert result.session(session).activation.orders[0].status.value == "REJECTED"
        assert len(result.session(session).activation.rejections) == 1
        assert result.session(session).activation.rejections[0].code.value == "SUSPENDED"
    else:
        assert len(result.fills) == 1
        fill = result.fills[0]
        raw = next(bar for bar in bars if bar.session_date == session)
        rules = master.resolve_rules(instrument, session)
        assert fill.fill_price == model.execution_price(raw.open, TradeSide.BUY, rules.price_limit.tick_size)
        assert fill.quantity == plans[0].order_quantity
    def digest(value):
        return "sha256:" + sha256(json.dumps(json_value(value), sort_keys=True).encode("utf-8")).hexdigest()
    identity = RunManifest("m0-run-manifest-1", "BACKTEST",
        os.environ.get("SIOS_LIVE_SOURCE_ID", "qualification-source"), digest({"chstockdata": "0.4.2"}),
        snapshot.snapshot_id, "sha256:" + fees.content_digest(), digest(sessions), model.version,
        (("execution-mode", mode.value), ("execution-policy", "R2.1"), ("execution-clock", OPENING_CLOCK_ID)),
        digest("m0-metric-conventions"), "NONE", 0)
    return {"run_manifest": identity, "run_identity": identity.identity_digest,
            "snapshot_manifest": manifest_to_dict(snapshot), "plans": plans,
            "fills": result.fills, "activation_orders": result.session(session).activation.orders,
            "rejections": result.session(session).activation.rejections,
            "execution_at": EngineClock.shanghai().execution_at(session),
            "raw_daily_open": str(next(b for b in bars if b.session_date == session).open),
            "result_digest": result.content_digest()}


@dataclass(frozen=True)
class MatrixRequest:
    """One matrix instrument with every live capability request prepared."""

    subtype: str
    instrument_id: InstrumentId
    bar_request: DailyBarRequest
    calendar_request: CalendarRequest
    tradability_request: TradabilityRequest
    corporate_action_request: CorporateActionRequest


def matrix_requests(
    matrix: dict[str, Any],
    *,
    window: dict[str, str] | None = None,
    evaluation_session: str | None = None,
) -> tuple[MatrixRequest, ...]:
    """Build live requests for every approved matrix instrument."""
    resolved_window = window or matrix["window"]
    start = date.fromisoformat(resolved_window["start"])
    end = date.fromisoformat(resolved_window["end"])
    session = date.fromisoformat(evaluation_session or matrix["evaluation_session"])
    requests: list[MatrixRequest] = []
    for entry in matrix["subtypes"]:
        for instrument in entry["instruments"]:
            instrument_id = InstrumentId.parse(instrument["instrument_id"])
            requests.append(
                MatrixRequest(
                    subtype=entry["subtype"],
                    instrument_id=instrument_id,
                    bar_request=DailyBarRequest(
                        instrument_ids=(instrument_id,), start_date=start, end_date=end
                    ),
                    calendar_request=CalendarRequest(
                        calendar_id=instrument_id.exchange.value,
                        start_date=start,
                        end_date=end,
                    ),
                    tradability_request=TradabilityRequest(
                        instrument_ids=(instrument_id,), session_date=session
                    ),
                    corporate_action_request=CorporateActionRequest(
                        instrument_ids=(instrument_id,),
                        start_date=start,
                        end_date=end,
                        instrument_kind="ETF",
                    ),
                )
            )
    return tuple(requests)
