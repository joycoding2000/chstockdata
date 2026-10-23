"""Golden scenario harness (test-only, never imported by the core package).

Scenarios are declarative JSON manifests frozen under
``tests/fixtures/golden/GNN``. This module builds the frozen canonical inputs,
persists them as an immutable snapshot for replay, drives the deterministic
daily-bar engine, and compares the observable evidence against the
hand-calculated expectations declared next to each manifest.

``PredeterminedTargetDriver`` is a test-only predetermined-target driver. It
is **not a strategy**: it replays the target contributions a scenario
declares, records the decision context it was shown, and executes declared
probes. It computes no signal and observes no market data of its own.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta, timezone
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from typing import Any

from systematic_investing.backtest.engine import (
    BacktestResult,
    DailyBarEngine,
    EngineClock,
    FutureDataAccessError,
    UnknownFactError,
)
from systematic_investing.backtest.execution import ExecutionModel
from systematic_investing.data.quality import CanonicalDataset
from systematic_investing.data.snapshots import SnapshotReader, SnapshotWriter
from systematic_investing.domain.execution import AccountFeeConfig, BrokerFeeProfile, compute_fees
from systematic_investing.domain.identifiers import InstrumentId, SleeveId
from systematic_investing.domain.instruments import FundSubtype, Instrument, InstrumentType
from systematic_investing.domain.ledger import (
    AcquisitionLot,
    NavPoint,
    Position,
    ValuationStatus,
)
from systematic_investing.domain.market import (
    AdjustmentFactor,
    AdjustmentMode,
    Availability,
    AvailabilityBasis,
    CorporateAction,
    CorporateActionKind,
    DailyBar,
    MarketCalendar,
    TradabilityStatus,
    TradabilityStatusKind,
    TradingSession,
)
from systematic_investing.domain.money import Money
from systematic_investing.domain.portfolio import TargetContribution
from systematic_investing.instrument_master.models import (
    EffectiveDatedRule,
    LotRule,
    MarketFeeTaxRule,
    OddLotSellPolicy,
    PriceLimitBasis,
    PriceLimitRule,
    RuleCandidate,
    RuleKind,
    RuleSource,
    SettlementRule,
)
from systematic_investing.instrument_master.repository import (
    InstrumentMaster,
    default_m0_master,
)
from systematic_investing.metrics.performance import (
    BenchmarkIdentity,
    MetricConventions,
    MetricsError,
    TerminalMode,
    compute_metrics,
)
from systematic_investing.portfolio.allocation import (
    CurrentHolding,
    CurrentPortfolio,
    ExecutableTargetPortfolio,
    FeeEstimate,
    build_executable_target,
)
from systematic_investing.risk.decisions import RiskTransformation, SleeveCapRule

SCENARIO_SCHEMA_VERSION = "golden-scenario-v1"
EXPECTED_SCHEMA_VERSION = "golden-expected-v1"
FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "golden"
MARKET_TZ = UTC
BAR_INFORMATION_LOCAL_TIME = time(15, 5)
TRADABILITY_INFORMATION_LOCAL_TIME = time(9, 0)
CORPORATE_ACTION_INFORMATION_LOCAL_TIME = time(8, 0)


class GoldenHarnessError(Exception):
    """Raised when a scenario manifest is malformed or an expectation fails."""


def discover_scenarios() -> tuple[str, ...]:
    """All scenario ids with a manifest under ``tests/fixtures/golden``."""
    if not FIXTURE_ROOT.exists():
        return ()
    return tuple(
        sorted(
            path.name
            for path in FIXTURE_ROOT.iterdir()
            if path.is_dir() and (path / "scenario.json").is_file()
        )
    )


@dataclass(frozen=True)
class GoldenScenario:
    """One loaded scenario: manifest, expected outputs, and manual notes."""

    scenario_id: str
    directory: Path
    payload: dict[str, Any]
    expected: dict[str, Any]

    def run(self, name: str) -> dict[str, Any]:
        for run in self.payload["runs"]:
            if run["name"] == name:
                return run
        raise GoldenHarnessError(f"{self.scenario_id} has no run named {name!r}")

    @property
    def run_names(self) -> tuple[str, ...]:
        return tuple(run["name"] for run in self.payload["runs"])

    @property
    def kind(self) -> str:
        """``engine`` scenarios drive the kernel; ``metrics`` scenarios use a
        hand-authored NAV path to pin metric semantics directly."""
        return self.payload.get("kind", "engine")


def load_scenario(scenario_id: str) -> GoldenScenario:
    directory = FIXTURE_ROOT / scenario_id
    payload = json.loads((directory / "scenario.json").read_text(encoding="utf-8"))
    expected = json.loads((directory / "expected.json").read_text(encoding="utf-8"))
    if payload.get("schema_version") != SCENARIO_SCHEMA_VERSION:
        raise GoldenHarnessError(
            f"{scenario_id} scenario schema {payload.get('schema_version')!r} is not "
            f"{SCENARIO_SCHEMA_VERSION!r}"
        )
    return GoldenScenario(
        scenario_id=scenario_id,
        directory=directory,
        payload=payload,
        expected=expected,
    )


def assert_scenario_files(scenario: GoldenScenario) -> None:
    """A scenario must carry its manual economic story beside the facts."""
    notes = scenario.directory / "README.md"
    if not notes.is_file():
        raise GoldenHarnessError(f"{scenario.scenario_id} is missing README.md")
    text = notes.read_text(encoding="utf-8")
    if "calculation" not in text.lower():
        raise GoldenHarnessError(
            f"{scenario.scenario_id} README must document the manual calculation"
        )


def _tz(offset: str) -> timezone:
    sign = 1 if offset.startswith("+") else -1
    hours, minutes = offset[1:].split(":")
    return timezone(sign * timedelta(hours=int(hours), minutes=int(minutes)))


def _time(value: str) -> time:
    return time.fromisoformat(value)


def _datetime(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _instrument(value: str) -> InstrumentId:
    return InstrumentId.parse(value)


def _decimal(value: str | int) -> Decimal:
    return Decimal(str(value))


def _optional_decimal(value: str | None) -> Decimal | None:
    return None if value is None else Decimal(str(value))


@dataclass(frozen=True)
class _Facts:
    """Frozen canonical inputs of one run."""

    calendar: MarketCalendar
    bars: tuple[DailyBar, ...]
    tradability: tuple[TradabilityStatus, ...]
    corporate_actions: tuple[CorporateAction, ...]
    rule_candidates: tuple[RuleCandidate, ...] = ()

    def dataset(self) -> CanonicalDataset:
        return CanonicalDataset(
            daily_bars=self.bars,
            sessions=self.calendar.sessions,
            tradability=self.tradability,
            corporate_actions=self.corporate_actions,
            rule_candidates=self.rule_candidates,
        )


def _calendar_of(scenario: GoldenScenario) -> MarketCalendar:
    calendar = scenario.payload["calendar"]
    sessions = tuple(
        TradingSession(
            calendar_id=calendar["calendar_id"],
            session_date=date.fromisoformat(day),
            is_open=True,
            note=None,
            snapshot_version=calendar["snapshot_version"],
        )
        for day in calendar["open_sessions"]
    )
    return MarketCalendar(
        calendar_id=calendar["calendar_id"],
        snapshot_version=calendar["snapshot_version"],
        sessions=sessions,
    )


def _bar_of(raw: dict[str, Any]) -> DailyBar:
    session_date = date.fromisoformat(raw["session_date"])
    open_price = _decimal(raw["open"])
    close_price = _decimal(raw["close"])
    basis = AvailabilityBasis(raw.get("availability_basis", "OBSERVED"))
    if raw.get("available_at"):
        available_at = _datetime(raw["available_at"])
    elif basis is AvailabilityBasis.UNKNOWN:
        available_at = None
    else:
        available_at = datetime.combine(
            session_date, BAR_INFORMATION_LOCAL_TIME, tzinfo=MARKET_TZ
        )
    if raw.get("retrieved_at"):
        retrieved_at = _datetime(raw["retrieved_at"])
    elif available_at is not None:
        retrieved_at = available_at + timedelta(minutes=1)
    else:
        raise GoldenHarnessError(
            f"bar {raw['instrument_id']} on {raw['session_date']} needs retrieved_at"
        )
    factor = raw.get("adjustment_factor")
    return DailyBar(
        schema_version="v1",
        instrument_id=_instrument(raw["instrument_id"]),
        session_date=session_date,
        open=open_price,
        high=_decimal(raw.get("high", str(max(open_price, close_price)))),
        low=_decimal(raw.get("low", str(min(open_price, close_price)))),
        close=close_price,
        pre_close=_optional_decimal(raw.get("pre_close")),
        volume=_decimal(raw.get("volume", "1000000")),
        amount=_decimal(raw.get("amount", "4000000")),
        currency=raw.get("currency", "CNY"),
        volume_unit=raw.get("volume_unit", "SHARE"),
        amount_unit=raw.get("amount_unit", "CNY"),
        adjustment_mode=AdjustmentMode.RAW,
        adjustment_factor=(
            AdjustmentFactor(
                factor=_decimal(factor["factor"]),
                convention=factor["convention"],
                version=factor["version"],
                as_of=date.fromisoformat(factor["as_of"]),
            )
            if factor is not None
            else None
        ),
        availability=Availability(
            information_available_at=available_at,
            retrieved_at=retrieved_at,
            availability_basis=basis,
        ),
        provider_evidence_id=raw.get("provider_evidence_id", "fixture:golden"),
    )


def _tradability_of(raw: dict[str, Any]) -> TradabilityStatus:
    session_date = date.fromisoformat(raw["session_date"])
    available_at = (
        _datetime(raw["available_at"])
        if raw.get("available_at")
        else datetime.combine(
            session_date, TRADABILITY_INFORMATION_LOCAL_TIME, tzinfo=MARKET_TZ
        )
    )
    return TradabilityStatus(
        instrument_id=_instrument(raw["instrument_id"]),
        session_date=session_date,
        status=TradabilityStatusKind(raw["status"]),
        reason=raw.get("reason"),
        availability=Availability(
            information_available_at=available_at,
            retrieved_at=available_at + timedelta(minutes=1),
            availability_basis=AvailabilityBasis(raw.get("availability_basis", "OBSERVED")),
        ),
        provenance=raw.get("provenance", "golden-fixture"),
    )


def _corporate_action_of(raw: dict[str, Any]) -> CorporateAction:
    ex_date = date.fromisoformat(raw["ex_date"])
    available_at = (
        _datetime(raw["available_at"])
        if raw.get("available_at")
        else datetime.combine(
            ex_date, CORPORATE_ACTION_INFORMATION_LOCAL_TIME, tzinfo=MARKET_TZ
        )
    )
    return CorporateAction(
        action_id=raw["action_id"],
        instrument_id=_instrument(raw["instrument_id"]),
        action_kind=CorporateActionKind(raw["action_kind"]),
        ex_date=ex_date,
        record_date=(
            date.fromisoformat(raw["record_date"]) if raw.get("record_date") else None
        ),
        pay_date=date.fromisoformat(raw["pay_date"]) if raw.get("pay_date") else None,
        cash_amount=(
            Money(_decimal(raw["cash_amount"])) if raw.get("cash_amount") else None
        ),
        share_ratio=(
            _decimal(raw["share_ratio"]) if raw.get("share_ratio") is not None else None
        ),
        revision=int(raw.get("revision", 1)),
        availability=Availability(
            information_available_at=available_at,
            retrieved_at=available_at,
            availability_basis=AvailabilityBasis(raw.get("availability_basis", "OBSERVED")),
        ),
        provenance=raw.get("provenance", "golden-fixture"),
    )


def _rule_profile_of(raw: dict[str, Any]) -> EffectiveDatedRule:
    kind = RuleKind(raw["kind"])
    common = {
        "profile_id": raw["profile_id"],
        "effective_from": date.fromisoformat(raw["effective_from"]),
        "effective_to": (
            date.fromisoformat(raw["effective_to"]) if raw.get("effective_to") else None
        ),
        "source": RuleSource(
            authority=raw["source"]["authority"],
            reference=raw["source"]["reference"],
            accessed_on=date.fromisoformat(raw["source"]["accessed_on"]),
        ),
    }
    values = raw.get("values", {})
    if kind is RuleKind.LOT:
        return LotRule(
            **common,
            board_lot=int(values.get("board_lot", 100)),
            buy_increment=int(values.get("buy_increment", 100)),
            odd_lot_sell_policy=OddLotSellPolicy(
                values.get("odd_lot_sell_policy", "ALLOWED")
            ),
        )
    if kind is RuleKind.SETTLEMENT:
        return SettlementRule(
            **common, sessions_until_sellable=int(values.get("sessions_until_sellable", 1))
        )
    if kind is RuleKind.PRICE_LIMIT:
        return PriceLimitRule(
            **common,
            basis=PriceLimitBasis(values.get("basis", "PREVIOUS_CLOSE")),
            limit_percent=_decimal(values.get("limit_percent", "0.10")),
            tick_size=_decimal(values.get("tick_size", "0.01")),
        )
    if kind is RuleKind.MARKET_FEE_TAX:
        return MarketFeeTaxRule(
            **common,
            stamp_tax_sell_rate=_decimal(values.get("stamp_tax_sell_rate", "0")),
            transfer_fee_rate=_decimal(values.get("transfer_fee_rate", "0")),
        )
    raise GoldenHarnessError(f"unsupported rule kind {kind!r}")


def _master_of(scenario: GoldenScenario) -> InstrumentMaster:
    master_section = scenario.payload.get("master", {"mode": "default"})
    if master_section.get("mode", "default") != "default":
        raise GoldenHarnessError(
            f"{scenario.scenario_id} master mode {master_section['mode']!r} is unsupported"
        )
    master = default_m0_master()
    for raw in master_section.get("extra_profiles", ()):
        master.add_rule_profile(_rule_profile_of(raw))
    for raw in master_section.get("extra_instruments", ()):
        master.register_instrument(
            Instrument(
                instrument_id=_instrument(raw["instrument_id"]),
                display_name=raw["display_name"],
                currency=raw.get("currency", "CNY"),
                instrument_type=InstrumentType(raw["instrument_type"]),
                fund_subtype=(
                    FundSubtype(raw["fund_subtype"]) if raw.get("fund_subtype") else None
                ),
                list_date=date.fromisoformat(raw["list_date"]),
                delist_date=None,
                trading_calendar_id=raw.get(
                    "trading_calendar_id",
                    raw["instrument_id"].split(":")[0],
                ),
                lot_rule_profile_id=raw["lot_rule_profile_id"],
                settlement_rule_profile_id=raw["settlement_rule_profile_id"],
                price_limit_rule_profile_id=raw["price_limit_rule_profile_id"],
                market_fee_tax_profile_id=raw["market_fee_tax_profile_id"],
                reference_data_version=raw.get("reference_data_version", "GOLDEN-OVERLAY-1"),
                valid_from=date.fromisoformat(raw["valid_from"]),
                valid_to=None,
            )
        )
    return master


def _account_fees_of(scenario: GoldenScenario) -> AccountFeeConfig:
    raw = scenario.payload["account_fees"]
    return AccountFeeConfig(
        config_id=raw["config_id"],
        config_version=raw["config_version"],
        broker_profiles=tuple(
            BrokerFeeProfile(
                profile_id=profile["profile_id"],
                version=profile["version"],
                commission_rate=_decimal(profile["commission_rate"]),
                minimum_commission=_decimal(profile["minimum_commission"]),
                agreement_reference=profile["agreement_reference"],
                effective_from=date.fromisoformat(profile["effective_from"]),
                effective_to=None,
            )
            for profile in raw["broker_profiles"]
        ),
    )


def _execution_model_of(scenario: GoldenScenario) -> ExecutionModel:
    raw = scenario.payload["execution_model"]
    return ExecutionModel(
        slippage_rate_buy=_decimal(raw["slippage_rate_buy"]),
        slippage_rate_sell=_decimal(raw["slippage_rate_sell"]),
    )


def _clock_of(scenario: GoldenScenario) -> EngineClock:
    raw = scenario.payload["clock"]
    tz = _tz(raw.get("timezone", "+00:00"))
    return EngineClock(
        timezone=tz,
        activation_local_time=_time(raw.get("activation_local_time", "09:15")),
        execution_local_time=_time(raw.get("execution_local_time", "09:30")),
        decision_local_time=_time(raw.get("decision_local_time", "15:30")),
    )


def _positions_of(run: dict[str, Any]) -> tuple[Position, ...]:
    positions = []
    for raw in run.get("initial_positions", ()):
        positions.append(
            Position(
                instrument_id=_instrument(raw["instrument_id"]),
                lots=(
                    AcquisitionLot(
                        quantity=int(raw["quantity"]),
                        acquired_session=date.fromisoformat(raw["acquired_session"]),
                        sellable_from=date.fromisoformat(raw["sellable_from"]),
                        acquisition_price=_decimal(raw["acquisition_price"]),
                    ),
                ),
            )
        )
    return tuple(positions)


def _targets_of(run: dict[str, Any]) -> dict[date, tuple[TargetContribution, ...]]:
    targets: dict[date, tuple[TargetContribution, ...]] = {}
    for session_text, contributions in run.get("targets", {}).items():
        targets[date.fromisoformat(session_text)] = tuple(
            TargetContribution(
                instrument_id=_instrument(item["instrument_id"]),
                sleeve=SleeveId(item.get("sleeve", "CORE")),
                strategy_id=item.get("strategy_id", "golden-predetermined-target"),
                strategy_version=item.get("strategy_version", "1"),
                target_weight=_decimal(item["target_weight"]),
            )
            for item in contributions
        )
    return targets


def _risk_of(run: dict[str, Any]) -> RiskTransformation | None:
    raw = run.get("risk")
    if raw is None:
        return None
    rules = tuple(
        SleeveCapRule(
            rule_id=cap["rule_id"],
            rule_version=cap["rule_version"],
            sleeve=SleeveId(cap["sleeve"]),
            max_weight=_decimal(cap["max_weight"]),
        )
        for cap in raw.get("sleeve_caps", ())
    )
    return RiskTransformation(rules, raw["composition_version"])


class PredeterminedTargetDriver:
    """Test-only predetermined-target driver; NOT a strategy.

    Replays the contributions a scenario declares for the decision session,
    records every decision context it is shown, and executes the declared
    probes (for example requesting a future bar slice, which must fail
    loudly). It computes no signal.
    """

    def __init__(
        self,
        targets: dict[date, tuple[TargetContribution, ...]],
        probes: tuple[dict[str, Any], ...] = (),
    ) -> None:
        self._targets = dict(targets)
        self._probes = probes
        self.contexts: list[Any] = []
        self.probe_results: list[dict[str, Any]] = []

    def contributions_for(self, context):
        self.contexts.append(context)
        self._execute_probes(context)
        return self._targets.get(context.session_date)

    def _execute_probes(self, context) -> None:
        for probe in self._probes:
            if context.session_date != date.fromisoformat(probe["at_session"]):
                continue
            expected_error = probe["expect"]
            try:
                context.require_bar(
                    _instrument(probe["instrument_id"]),
                    date.fromisoformat(probe["session_date"]),
                )
            except (FutureDataAccessError, UnknownFactError) as error:
                actual = type(error).__name__
                if actual != expected_error:
                    raise GoldenHarnessError(
                        f"probe expected {expected_error} but got {actual}: {error}"
                    ) from error
                self.probe_results.append(
                    {
                        "kind": probe["kind"],
                        "instrument_id": probe["instrument_id"],
                        "session_date": probe["session_date"],
                        "error": actual,
                    }
                )
            else:
                raise GoldenHarnessError(
                    f"probe {probe['kind']} for {probe['instrument_id']} did not fail"
                )


@dataclass(frozen=True)
class GoldenOutcome:
    """One scenario run: engine result plus its frozen inputs and driver."""

    scenario_id: str
    run_name: str
    run: dict[str, Any]
    calendar: MarketCalendar
    master: InstrumentMaster
    account_fees: AccountFeeConfig
    dataset: CanonicalDataset
    result: BacktestResult
    driver: PredeterminedTargetDriver
    conventions: MetricConventions


def _facts_of(scenario: GoldenScenario, run: dict[str, Any]) -> _Facts:
    return _Facts(
        calendar=_calendar_of(scenario),
        bars=tuple(_bar_of(raw) for raw in run["bars"]),
        tradability=tuple(_tradability_of(raw) for raw in run.get("tradability", ())),
        corporate_actions=tuple(
            _corporate_action_of(raw) for raw in run.get("corporate_actions", ())
        ),
        rule_candidates=tuple(
            _rule_candidate_of(raw) for raw in run.get("rule_candidates", ())
        ),
    )


def _rule_candidate_of(raw: dict[str, Any]) -> RuleCandidate:
    return RuleCandidate(
        instrument_id=_instrument(raw["instrument_id"]),
        session_date=date.fromisoformat(raw["session_date"]),
        rule_kind=RuleKind(raw["rule_kind"]),
        proposed_value=_rule_profile_of(raw["proposed_value"]),
        proposed_by=raw.get("proposed_by", "chstockdata:golden-fixture"),
    )


def run_scenario(
    scenario: GoldenScenario,
    *,
    run_name: str | None = None,
    dataset: CanonicalDataset | None = None,
    bar_overrides: dict[tuple[str, str], dict[str, str]] | None = None,
) -> GoldenOutcome:
    """Run one scenario run; ``dataset`` replays previously frozen facts."""
    run = (
        scenario.run(run_name)
        if run_name is not None
        else scenario.run(scenario.run_names[0])
    )
    facts = _facts_of(scenario, run)
    if bar_overrides:
        facts = _Facts(
            calendar=facts.calendar,
            bars=tuple(
                _bar_of(
                    {
                        **raw,
                        **bar_overrides.get((raw["instrument_id"], raw["session_date"]), {}),
                    }
                )
                for raw in run["bars"]
            ),
            tradability=facts.tradability,
            corporate_actions=facts.corporate_actions,
            rule_candidates=facts.rule_candidates,
        )
    active_dataset = dataset if dataset is not None else facts.dataset()
    driver = PredeterminedTargetDriver(_targets_of(run), tuple(run.get("probes", ())))
    engine = DailyBarEngine(
        calendar=facts.calendar,
        clock=_clock_of(scenario),
        master=_master_of(scenario),
        account_fees=_account_fees_of(scenario),
        execution_model=_execution_model_of(scenario),
        bars=tuple(active_dataset.daily_bars),
        tradability=tuple(active_dataset.tradability),
        corporate_actions=tuple(active_dataset.corporate_actions),
        target_source=driver,
        initial_cash=Money(_decimal(run.get("initial_cash", "100000"))),
        initial_positions=_positions_of(run),
        risk_transformation=_risk_of(run),
    )
    period = run["period"]
    result = engine.run(
        start_session=date.fromisoformat(period["start_session"]),
        end_session=date.fromisoformat(period["end_session"]),
    )
    return GoldenOutcome(
        scenario_id=scenario.scenario_id,
        run_name=run["name"],
        run=run,
        calendar=facts.calendar,
        master=_master_of(scenario),
        account_fees=_account_fees_of(scenario),
        dataset=active_dataset,
        result=result,
        driver=driver,
        conventions=MetricConventions(
            benchmark=BenchmarkIdentity(run.get("benchmark", "NONE")),
            terminal_mode=TerminalMode(run.get("terminal_mode", "MARK_TO_MARKET")),
        ),
    )


# --- immutable snapshot persistence and replay ------------------------------


def snapshot_directory(tmp_root: Path, scenario_id: str, run_name: str) -> Path:
    return tmp_root / f"{scenario_id}-{run_name}"


def persist_scenario(tmp_root: Path, outcome: GoldenOutcome) -> Any:
    """Persist the frozen canonical facts as an immutable snapshot."""
    directory = snapshot_directory(tmp_root, outcome.scenario_id, outcome.run_name)
    last_session = max(session.session_date for session in outcome.calendar.sessions)
    created_at = datetime.combine(last_session, time(16, 30), tzinfo=MARKET_TZ)
    knowledge_cutoff = datetime.combine(last_session, time(15, 30), tzinfo=MARKET_TZ)
    retrieved_at = datetime.combine(last_session, time(16, 0), tzinfo=MARKET_TZ)
    return SnapshotWriter(
        provider_name="golden-fixture",
        provider_version="recorded-1",
        adapter_version="0.1.0",
    ).persist(
        outcome.dataset,
        snapshot_dir=directory,
        created_at=created_at,
        knowledge_cutoff=knowledge_cutoff,
        retrieved_at=retrieved_at,
    )


def replay_scenario(tmp_root: Path, scenario_id: str, run_name: str) -> CanonicalDataset:
    """Replay a persisted snapshot, verifying every artifact checksum."""
    directory = snapshot_directory(tmp_root, scenario_id, run_name)
    _, dataset = SnapshotReader().load(directory)
    return dataset


# --- normalization and expectation comparison -------------------------------


def _normalize_order(order) -> dict[str, Any]:
    return {
        "order_id": order.order_id,
        "instrument_id": str(order.instrument_id),
        "side": order.side.value,
        "planned_quantity": order.planned_quantity,
        "submitted_quantity": order.submitted_quantity,
        "execution_session": order.execution_session.isoformat(),
        "sizing_reference_price_basis": order.sizing_reference_price_basis.value,
        "sizing_reference_price": str(order.sizing_reference_price),
        "fill_price_model": order.fill_price_model,
        "status": order.status.value,
        "reason_codes": list(order.reason_codes),
    }


def _normalize_fill(fill) -> dict[str, Any]:
    return {
        "instrument_id": str(fill.instrument_id),
        "side": fill.side.value,
        "quantity": fill.quantity,
        "fill_price": str(fill.fill_price),
        "reference_open": str(fill.reference_open),
        "session_date": fill.session_date.isoformat(),
        "commission": str(fill.fees.commission.amount),
        "minimum_commission_adjustment": str(
            fill.fees.minimum_commission_adjustment.amount
        ),
        "stamp_tax": str(fill.fees.stamp_tax.amount),
        "transfer_fee": str(fill.fees.transfer_fee.amount),
        "total_fees": str(fill.fees.total.amount),
    }


def _normalize_rejection(rejection) -> dict[str, Any]:
    return {
        "instrument_id": str(rejection.instrument_id),
        "side": rejection.side.value,
        "code": rejection.code.value,
        "observed": rejection.observed,
    }


def _normalize_plan(plan) -> dict[str, Any]:
    return {
        "instrument_id": str(plan.instrument_id),
        "sleeve": plan.sleeve.value,
        "side": plan.side.value,
        "order_quantity": plan.order_quantity,
        "target_weight": str(plan.target_weight),
        "current_weight": str(plan.current_weight),
        "sizing_reference_price": str(plan.sizing_reference_price),
        "target_id": plan.target_id,
        "target_revision": plan.target_revision,
        "decision_for_trade_date": plan.decision_for_trade_date.isoformat(),
    }


def _normalize_session(record) -> dict[str, Any]:
    snapshot = record.snapshot
    target = record.target
    return {
        "session_date": record.session_date.isoformat(),
        "orders": [
            _normalize_order(order)
            for order in sorted(
                record.activation.orders, key=lambda item: str(item.instrument_id)
            )
        ],
        "fills": [
            _normalize_fill(fill)
            for fill in sorted(
                record.activation.fills, key=lambda item: str(item.instrument_id)
            )
        ],
        "rejections": [
            _normalize_rejection(rejection)
            for rejection in sorted(
                record.activation.rejections, key=lambda item: str(item.instrument_id)
            )
        ],
        "invalidated_orders": [
            _normalize_order(order)
            for order in sorted(
                record.invalidated_orders, key=lambda item: str(item.instrument_id)
            )
        ],
        "cash_entries": [
            {
                "entry_id": entry.entry_id,
                "category": entry.category.value,
                "amount": str(entry.amount.amount),
                "session_date": entry.session_date.isoformat(),
                "source_id": entry.source_id,
            }
            for entry in sorted(
                (
                    *(
                        effect.cash_entry
                        for effect in record.corporate_action_effects
                        if effect.cash_entry is not None
                    ),
                    *record.activation.cash_entries,
                ),
                key=lambda item: item.entry_id,
            )
        ],
        "holdings_entries": [
            {
                "entry_id": entry.entry_id,
                "instrument_id": str(entry.instrument_id),
                "quantity_delta": entry.quantity_delta,
                "acquisition_session": (
                    entry.acquisition_session.isoformat()
                    if entry.acquisition_session is not None
                    else None
                ),
                "sellable_from": (
                    entry.sellable_from.isoformat()
                    if entry.sellable_from is not None
                    else None
                ),
                "source_id": entry.source_id,
            }
            for entry in sorted(
                (
                    *(
                        effect.holdings_entry
                        for effect in record.corporate_action_effects
                        if effect.holdings_entry is not None
                    ),
                    *record.activation.holdings_entries,
                ),
                key=lambda item: item.entry_id,
            )
        ],
        "corporate_action_effects": [
            {
                "action_id": effect.action_id,
                "instrument_id": str(effect.instrument_id),
                "action_kind": effect.action_kind.value,
                "cash_delta": str(effect.cash_delta.amount),
                "quantity_delta": effect.quantity_delta,
            }
            for effect in sorted(
                record.corporate_action_effects, key=lambda item: item.action_id
            )
        ],
        "plans": [
            _normalize_plan(plan)
            for plan in sorted(record.plans, key=lambda item: str(item.instrument_id))
        ],
        "target": (
            {
                "target_id": target.target_id,
                "revision": target.revision,
                "decision_for_trade_date": target.decision_for_trade_date.isoformat(),
                "valuation_equity": str(target.valuation_equity.amount),
                "cash_weight": str(target.cash_weight),
                "sleeve_weights": {
                    sleeve.value: str(weight)
                    for sleeve, weight in target.sleeve_weights.items()
                },
                "addressed_instruments": [
                    str(item) for item in sorted(target.addressed_instruments)
                ],
                "content_digest": target.content_digest,
            }
            if target is not None
            else None
        ),
        "decision_digest": record.decision_digest,
        "decision_blocked_reason": (
            record.decision_blocked_reason.value if record.decision_blocked_reason else None
        ),
        "cash": str(snapshot.cash.amount),
        "market_value": str(snapshot.market_value.amount),
        "total_equity": str(snapshot.total_equity.amount),
        "nav": str(record.nav.nav),
        "valuation_status": snapshot.valuation_status.value,
        "stale_marks": [
            {
                "instrument_id": str(mark.instrument_id),
                "marked_price": str(mark.marked_price),
                "last_valid_session": mark.last_valid_session.isoformat(),
                "age_sessions": mark.age_sessions,
            }
            for mark in snapshot.stale_marks
        ],
        "incomplete_reasons": sorted(reason.value for reason in snapshot.incomplete_reasons),
    }


def metrics_summary(outcome: GoldenOutcome) -> dict[str, Any]:
    """Metrics over the session NAV series, or a typed refusal status."""
    nav_points = tuple(record.nav for record in outcome.result.sessions)
    try:
        report = compute_metrics(
            nav_points,
            cash_entries=outcome.result.cash_entries,
            conventions=outcome.conventions,
        )
    except MetricsError as error:
        return {
            "status": type(error).__name__,
            "metric_conventions_digest": outcome.conventions.digest(),
        }
    return {
        "status": "COMPLETE",
        "observation_count": report.observation_count,
        "total_return": str(report.total_return),
        "max_drawdown": str(report.max_drawdown),
        "underwater_sessions": report.underwater.sessions,
        "underwater_calendar_days": report.underwater.calendar_days,
        "turnover": str(report.turnover),
        "cost_drag": str(report.cost_drag.drag),
        "metric_conventions_digest": outcome.conventions.digest(),
    }


def normalized_output(outcome: GoldenOutcome) -> dict[str, Any]:
    """Canonical normalized evidence used for digest comparison."""
    last_session = outcome.result.sessions[-1].session_date
    return {
        "scenario_id": outcome.scenario_id,
        "run_name": outcome.run_name,
        "terminal_mode": outcome.conventions.terminal_mode.value,
        "sessions": [_normalize_session(record) for record in outcome.result.sessions],
        "final_cash": str(outcome.result.cash.amount),
        "final_positions": [
            {
                "instrument_id": str(position.instrument_id),
                "total_quantity": position.total_quantity,
                "sellable_quantity": position.sellable_quantity(last_session),
                "average_cost": (
                    str(position.average_cost) if position.average_cost is not None else None
                ),
            }
            for position in outcome.result.positions
        ],
        "metrics": metrics_summary(outcome),
        "probe_results": list(outcome.driver.probe_results),
    }


def normalized_digest(outcome: GoldenOutcome) -> str:
    return sha256(
        json.dumps(normalized_output(outcome), sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()


# --- expectation comparison -------------------------------------------------


def _fail(scenario_id: str, run_name: str, message: str) -> None:
    raise AssertionError(f"{scenario_id}/{run_name}: {message}")


def _expect_decimal(actual: Decimal, expected: Any, context: str) -> None:
    if actual != _decimal(expected):
        raise AssertionError(f"{context}: expected {expected!r}, got {actual!r}")


_DECIMAL_FIELDS = {
    "sizing_reference_price",
    "target_weight",
    "current_weight",
    "fill_price",
    "reference_open",
    "commission",
    "minimum_commission_adjustment",
    "stamp_tax",
    "transfer_fee",
    "total_fees",
    "marked_price",
    "cash_delta",
}


def _compare_by_instrument(
    actual: list[dict[str, Any]],
    expected: list[dict[str, Any]],
    context: str,
) -> None:
    actual_by_id = {item["instrument_id"]: item for item in actual}
    expected_by_id = {item["instrument_id"]: item for item in expected}
    if set(actual_by_id) != set(expected_by_id):
        raise AssertionError(
            f"{context}: instrument mismatch expected {sorted(expected_by_id)}, "
            f"got {sorted(actual_by_id)}"
        )
    for instrument_id, expectation in expected_by_id.items():
        observed = actual_by_id[instrument_id]
        for key, value in expectation.items():
            if key not in observed:
                raise AssertionError(f"{context}[{instrument_id}]: unknown field {key!r}")
            actual_value = observed[key]
            if key in _DECIMAL_FIELDS:
                _expect_decimal(Decimal(actual_value), value, f"{context}[{instrument_id}].{key}")
                continue
            if actual_value != value:
                raise AssertionError(
                    f"{context}[{instrument_id}].{key}: expected {value!r}, "
                    f"got {actual_value!r}"
                )


def _compare_by_action(actual, expected, context: str) -> None:
    actual_by_id = {item["action_id"]: item for item in actual}
    expected_by_id = {item["action_id"]: item for item in expected}
    if set(actual_by_id) != set(expected_by_id):
        raise AssertionError(
            f"{context}: action mismatch expected {sorted(expected_by_id)}, "
            f"got {sorted(actual_by_id)}"
        )
    for action_id, expectation in expected_by_id.items():
        observed = actual_by_id[action_id]
        for key, value in expectation.items():
            actual_value = observed.get(key)
            if key in _DECIMAL_FIELDS:
                _expect_decimal(
                    Decimal(actual_value), value, f"{context}[{action_id}].{key}"
                )
                continue
            if actual_value != value:
                raise AssertionError(
                    f"{context}[{action_id}].{key}: expected {value!r}, got {actual_value!r}"
                )


def _compare_target(observed, expected, context: str) -> None:
    if expected is None:
        if observed is not None:
            raise AssertionError(f"{context}: expected no target, got one")
        return
    if observed is None:
        raise AssertionError(f"{context}: expected a target, got none")
    for key, value in expected.items():
        actual = observed.get(key)
        if key in {"valuation_equity", "cash_weight"}:
            _expect_decimal(Decimal(actual), value, f"{context}.{key}")
            continue
        if key == "sleeve_weights":
            observed_weights = {k: Decimal(v) for k, v in actual.items()}
            expected_weights = {k: _decimal(v) for k, v in value.items()}
            if observed_weights != expected_weights:
                raise AssertionError(
                    f"{context}.sleeve_weights: expected {expected_weights}, "
                    f"got {observed_weights}"
                )
            continue
        if key == "addressed_instruments":
            if list(value) != list(actual):
                raise AssertionError(
                    f"{context}.addressed_instruments: expected {value!r}, got {actual!r}"
                )
            continue
        if actual != value:
            raise AssertionError(f"{context}.{key}: expected {value!r}, got {actual!r}")


def assert_expected(outcome: GoldenOutcome, expected_run: dict[str, Any]) -> None:
    """Compare the observable run evidence against hand-calculated values."""
    scenario_id = outcome.scenario_id
    run_name = outcome.run_name
    sessions = {
        record.session_date.isoformat(): _normalize_session(record)
        for record in outcome.result.sessions
    }
    for expectation in expected_run.get("sessions", ()):
        session_key = expectation["session_date"]
        if session_key not in sessions:
            _fail(scenario_id, run_name, f"no session record for {session_key}")
        observed = sessions[session_key]
        context = f"session {session_key}"
        for key in ("cash", "market_value", "total_equity", "nav"):
            if key in expectation:
                _expect_decimal(
                    Decimal(observed[key]), expectation[key], f"{context}.{key}"
                )
        for key in ("valuation_status", "decision_blocked_reason"):
            if key in expectation and expectation[key] != observed[key]:
                _fail(
                    scenario_id,
                    run_name,
                    f"{context}.{key}: expected {expectation[key]!r}, got {observed[key]!r}",
                )
        if "incomplete_reasons" in expectation:
            expected_reasons = sorted(expectation["incomplete_reasons"])
            if expected_reasons != observed["incomplete_reasons"]:
                _fail(
                    scenario_id,
                    run_name,
                    f"{context}.incomplete_reasons: expected {expected_reasons}, "
                    f"got {observed['incomplete_reasons']}",
                )
        for key in (
            "orders",
            "invalidated_orders",
            "fills",
            "rejections",
            "plans",
            "stale_marks",
        ):
            if key in expectation:
                _compare_by_instrument(
                    observed[key], expectation[key], f"{context}.{key}"
                )
        if "corporate_action_effects" in expectation:
            _compare_by_action(
                observed["corporate_action_effects"],
                expectation["corporate_action_effects"],
                f"{context}.corporate_action_effects",
            )
        if "target" in expectation:
            _compare_target(
                observed["target"], expectation["target"], f"{context}.target"
            )

    final = expected_run.get("final", {})
    if final:
        last = _normalize_session(outcome.result.sessions[-1])
        if "cash" in final:
            _expect_decimal(
                Decimal(str(outcome.result.cash.amount)), final["cash"], "final.cash"
            )
        if "equity" in final:
            _expect_decimal(Decimal(last["total_equity"]), final["equity"], "final.equity")
        if "nav" in final:
            _expect_decimal(Decimal(last["nav"]), final["nav"], "final.nav")
        if "positions" in final:
            observed_positions = {
                item["instrument_id"]: item
                for item in normalized_output(outcome)["final_positions"]
            }
            expected_positions = {
                item["instrument_id"]: item for item in final["positions"]
            }
            if set(observed_positions) != set(expected_positions):
                _fail(
                    scenario_id,
                    run_name,
                    f"final.positions: expected {sorted(expected_positions)}, "
                    f"got {sorted(observed_positions)}",
                )
            for instrument_id, expectation in expected_positions.items():
                observed = observed_positions[instrument_id]
                for key, value in expectation.items():
                    if key == "instrument_id":
                        continue
                    if key == "average_cost" and value is not None:
                        _expect_decimal(
                            Decimal(str(observed.get(key))),
                            value,
                            f"final.positions[{instrument_id}].{key}",
                        )
                        continue
                    if observed.get(key) != value:
                        _fail(
                            scenario_id,
                            run_name,
                            f"final.positions[{instrument_id}].{key}: "
                            f"expected {value!r}, got {observed.get(key)!r}",
                        )


# --- metrics-path scenarios (hand-authored NAV series) ----------------------


@dataclass(frozen=True)
class MetricsPathOutcome:
    """A metrics-only scenario: a hand-authored NAV path and its statistics."""

    scenario_id: str
    run_name: str
    run: dict[str, Any]
    nav_points: tuple[NavPoint, ...]
    report: Any
    conventions: MetricConventions


def run_metrics_path(
    scenario: GoldenScenario, *, run_name: str | None = None
) -> MetricsPathOutcome:
    if scenario.kind != "metrics":
        raise GoldenHarnessError(
            f"{scenario.scenario_id} is not a metrics scenario (kind={scenario.kind!r})"
        )
    run = (
        scenario.run(run_name)
        if run_name is not None
        else scenario.run(scenario.run_names[0])
    )
    nav_points = tuple(
        NavPoint(
            session_date=date.fromisoformat(point["session_date"]),
            cash=Money(_decimal(point["equity"])),
            market_value=Money(Decimal("0")),
            total_equity=Money(_decimal(point["equity"])),
            nav=_decimal(point["equity"])
            / _decimal(scenario.payload.get("initial_capital", "100000")),
            valuation_status=ValuationStatus.COMPLETE,
        )
        for point in run["nav_path"]
    )
    conventions = MetricConventions(
        benchmark=BenchmarkIdentity(run.get("benchmark", "NONE")),
        terminal_mode=TerminalMode(run.get("terminal_mode", "MARK_TO_MARKET")),
    )
    report = compute_metrics(nav_points, conventions=conventions)
    return MetricsPathOutcome(
        scenario_id=scenario.scenario_id,
        run_name=run["name"],
        run=run,
        nav_points=nav_points,
        report=report,
        conventions=conventions,
    )


def normalized_metrics_path(outcome: MetricsPathOutcome) -> dict[str, Any]:
    report = outcome.report
    return {
        "scenario_id": outcome.scenario_id,
        "run_name": outcome.run_name,
        "observation_count": report.observation_count,
        "total_return": str(report.total_return),
        "drawdowns": [str(value) for value in report.drawdowns],
        "max_drawdown": str(report.max_drawdown),
        "underwater_sessions": report.underwater.sessions,
        "underwater_calendar_days": report.underwater.calendar_days,
        "turnover": str(report.turnover),
        "cost_drag": str(report.cost_drag.drag),
        "stale_observation_count": report.stale_observation_count,
        "metric_conventions_digest": outcome.conventions.digest(),
    }


def assert_metrics_path_expected(
    outcome: MetricsPathOutcome, expected: dict[str, Any]
) -> None:
    observed = normalized_metrics_path(outcome)
    for key, value in expected.items():
        if key == "drawdowns":
            expected_drawdowns = [_decimal(item) for item in value]
            observed_drawdowns = [Decimal(item) for item in observed["drawdowns"]]
            if expected_drawdowns != observed_drawdowns:
                raise AssertionError(
                    f"{outcome.scenario_id}/{outcome.run_name}: drawdowns expected "
                    f"{expected_drawdowns}, got {observed_drawdowns}"
                )
            continue
        if key == "nav_path":
            continue
        if key in {"total_return", "max_drawdown", "turnover", "cost_drag"}:
            _expect_decimal(
                Decimal(observed[key]),
                value,
                f"{outcome.scenario_id}/{outcome.run_name}.{key}",
            )
            continue
        if observed.get(key) != value:
            raise AssertionError(
                f"{outcome.scenario_id}/{outcome.run_name}.{key}: expected {value!r}, "
                f"got {observed.get(key)!r}"
            )


# --- T-close executable draft helper (residual-cash assertions) -------------


def draft_executable(outcome: GoldenOutcome) -> ExecutableTargetPortfolio:
    """Build the T-close executable draft for explicit residual-cash checks.

    Uses the same frozen inputs the engine used; the expected numbers are
    hand-calculated in the scenario README, never read back from this call.
    """
    session = date.fromisoformat(outcome.run["period"]["start_session"])
    session_result = outcome.result.session(session)
    assert session_result.target is not None
    risk = RiskTransformation((), "m0-identity-risk-1").transform(session_result.target)
    assert risk.approved is not None
    close_prices = {
        bar.instrument_id: bar.close
        for bar in outcome.dataset.daily_bars
        if bar.session_date == session
    }
    holdings = tuple(
        CurrentHolding(
            instrument_id=position.instrument_id, quantity=position.total_quantity
        )
        for position in session_result.snapshot.positions
    )
    lot_rules = {
        instrument_id: outcome.master.resolve_rules(instrument_id, session).lot
        for instrument_id in close_prices
    }
    broker = outcome.account_fees.resolve_broker_profile(session)

    class _Estimator:
        """Compose the two fee authorities exactly as the run configuration does."""

        def estimate(self, instrument_id, side, quantity, price) -> FeeEstimate:
            rules = outcome.master.resolve_rules(instrument_id, session)
            fees = compute_fees(rules.market_fee_tax, broker, side, quantity, price)
            return FeeEstimate(
                market_fees=fees.stamp_tax + fees.transfer_fee,
                broker_fees=fees.commission + fees.minimum_commission_adjustment,
            )

    return build_executable_target(
        risk.approved,
        CurrentPortfolio(cash=session_result.snapshot.cash, holdings=holdings),
        close_prices,
        lot_rules,
        _Estimator(),
    )
