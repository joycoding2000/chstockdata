"""Canonical ETF candidate specs: frozen intents and their strategy modules.

The CandidateIntent JSON files are frozen before implementation and their
digests are recorded here. These tests validate both files against the typed
lifecycle contract and prove each canonical strategy's decision behavior with
hand-audited offline facts: month-end cadence, insufficient history, trend
gate, top-1 rotation, and explicit exit targets.
"""

import json
from datetime import UTC, date, datetime, time
from decimal import Decimal
from pathlib import Path

from systematic_investing.backtest.engine import DecisionContext
from systematic_investing.domain.identifiers import InstrumentId, SleeveId
from systematic_investing.domain.ledger import AcquisitionLot, Position
from systematic_investing.domain.market import (
    AdjustmentMode,
    Availability,
    AvailabilityBasis,
    DailyBar,
    TradabilityStatus,
    TradabilityStatusKind,
)
from systematic_investing.domain.money import Money
from systematic_investing.research.contracts import CandidateIntent
from systematic_investing.research.strategies import month_end_sessions
from systematic_investing.research.universe import UniverseView

REPO_ROOT = Path(__file__).resolve().parents[2]
CANDIDATE_DIR = REPO_ROOT / "research" / "candidates"

ABSOLUTE_INTENT_ID = "m1-etf-absolute-trend-v1"
MOMENTUM_INTENT_ID = "m1-etf-relative-momentum-v1"

# Recorded frozen digests (M1 implementation plan Task 3 Step 3): the digests
# were computed from the committed JSON files before any strategy module was
# written and must never change for this candidate version.
RECORDED_INTENT_DIGESTS: dict[str, str] = {
    ABSOLUTE_INTENT_ID: "sha256:3a67de20e1cfcb649f00cc996c1ce7a1cd653bc06cfb30f4b3550acf9c7076d4",
    MOMENTUM_INTENT_ID: "sha256:df12a555efd370bff526a4556488dd4db5e07847d9ac765773be97195ae932a7",
}


def _intent_path(intent_id: str) -> Path:
    return CANDIDATE_DIR / f"{intent_id}.json"


def test_absolute_trend_intent_matches_frozen_contract() -> None:
    payload = json.loads(_intent_path(ABSOLUTE_INTENT_ID).read_text(encoding="utf-8"))
    intent = CandidateIntent.from_dict(payload)

    assert intent.intent_id == ABSOLUTE_INTENT_ID
    assert intent.lineage_id == "m1-etf-absolute-trend"
    assert intent.asset_class.value == "ETF"
    assert intent.sleeve.value == "CORE"
    assert intent.strategy_id == "etf-absolute-trend"
    assert intent.decision_frequency == "MONTHLY_LAST_SESSION"
    assert tuple(intent.parameters_grid) == ("sma-150", "sma-200", "sma-250")
    assert intent.parameter_priority == ("sma-150", "sma-200", "sma-250")
    assert intent.parameter_selection_rule == "PRIORITY_FIRST_BASIC_PASS"
    assert intent.universe_policy.policy_name == "ETF_FIXED_QUALIFIED_V1"
    assert tuple(str(item) for item in intent.universe_policy.instrument_ids) == (
        "XSHG:510300",
    )
    assert intent.warm_up_start.isoformat() == "2015-01-05"
    assert intent.basic_start.isoformat() == "2016-01-04"
    assert intent.basic_end.isoformat() == "2022-12-30"
    assert intent.oos_start.isoformat() == "2023-01-03"
    assert intent.oos_end.isoformat() == "2025-12-31"
    assert intent.benchmark.kind.value == "SINGLE_ETF_BUY_AND_HOLD"
    assert intent.benchmark.instrument_ids == intent.universe_policy.instrument_ids
    assert intent.benchmark.rebalance == "INCEPTION"
    assert intent.risk_off_choice == "CASH_0"
    assert set(intent.basic_promotion_rule) >= {
        "min_nav_observations",
        "min_excess_total_return_vs_benchmark",
        "max_drawdown_floor",
        "max_turnover",
    }
    assert intent.oos_survivor_rule
    assert intent.known_limitations
    assert intent.intent_digest == RECORDED_INTENT_DIGESTS[ABSOLUTE_INTENT_ID]


def test_relative_momentum_intent_matches_frozen_contract() -> None:
    payload = json.loads(_intent_path(MOMENTUM_INTENT_ID).read_text(encoding="utf-8"))
    intent = CandidateIntent.from_dict(payload)

    assert intent.intent_id == MOMENTUM_INTENT_ID
    assert intent.lineage_id == "m1-etf-relative-momentum"
    assert intent.asset_class.value == "ETF"
    assert intent.sleeve.value == "CORE"
    assert intent.strategy_id == "etf-relative-momentum"
    assert intent.decision_frequency == "MONTHLY_LAST_SESSION"
    assert tuple(intent.parameters_grid) == (
        "momentum-126",
        "momentum-252",
        "momentum-126-gate",
    )
    assert intent.parameter_priority == (
        "momentum-126",
        "momentum-252",
        "momentum-126-gate",
    )
    universe = tuple(str(item) for item in intent.universe_policy.instrument_ids)
    assert universe == (
        "XSHE:159915",
        "XSHG:510300",
        "XSHG:511010",
        "XSHG:518880",
    )
    assert intent.benchmark.kind.value == "ETF_UNIVERSE_EQUAL_WEIGHT"
    assert intent.benchmark.instrument_ids == intent.universe_policy.instrument_ids
    assert intent.oos_survivor_rule
    assert intent.intent_digest == RECORDED_INTENT_DIGESTS[MOMENTUM_INTENT_ID]


def _weekdays(start: date, end: date) -> tuple[date, ...]:
    sessions: list[date] = []
    day = start
    while day <= end:
        if day.weekday() < 5:
            sessions.append(day)
        day = date.fromordinal(day.toordinal() + 1)
    return tuple(sessions)


def _bars_for(
    instrument_id: InstrumentId,
    closes: tuple[Decimal, ...],
    sessions: tuple[date, ...],
) -> tuple[DailyBar, ...]:
    bars: list[DailyBar] = []
    previous_close = None
    for close, session_date in zip(closes, sessions, strict=False):
        available_at = datetime.combine(session_date, time(15, 5), tzinfo=UTC)
        bars.append(
            DailyBar(
                schema_version="v1",
                instrument_id=instrument_id,
                session_date=session_date,
                open=close,
                high=close,
                low=close,
                close=close,
                pre_close=previous_close,
                volume=Decimal("1000000"),
                amount=Decimal("4000000"),
                currency="CNY",
                volume_unit="shares",
                amount_unit="CNY",
                adjustment_mode=AdjustmentMode.RAW,
                adjustment_factor=None,
                availability=Availability(
                    information_available_at=available_at,
                    retrieved_at=available_at,
                    availability_basis=AvailabilityBasis.OBSERVED,
                ),
                provider_evidence_id="spec-test-bars",
            )
        )
        previous_close = close
    return tuple(bars)


def _context(
    closes_by_symbol: dict[str, tuple[Decimal, ...]],
    sessions: tuple[date, ...],
    *,
    held: tuple[tuple[str, int], ...] = (),
) -> DecisionContext:
    """Build a T-known decision context for ``sessions``' last session.

    Bars are sliced exactly to ``sessions``; a held position is expressed
    through real dated acquisition lots.
    """
    bars: list[DailyBar] = []
    tradability: list[TradabilityStatus] = []
    for symbol, closes in closes_by_symbol.items():
        instrument_id = InstrumentId.parse(symbol)
        bars.extend(_bars_for(instrument_id, closes[: len(sessions)], sessions))
    final_session = sessions[-1]
    cutoff = datetime.combine(final_session, time(15, 30), tzinfo=UTC)
    for session_date in sessions:
        for symbol in closes_by_symbol:
            tradability.append(
                TradabilityStatus(
                    instrument_id=InstrumentId.parse(symbol),
                    session_date=session_date,
                    status=TradabilityStatusKind.TRADABLE,
                    reason=None,
                    availability=Availability(
                        information_available_at=datetime.combine(
                            session_date, time(9, 0), tzinfo=UTC
                        ),
                        retrieved_at=datetime.combine(
                            session_date, time(9, 0), tzinfo=UTC
                        ),
                        availability_basis=AvailabilityBasis.OBSERVED,
                    ),
                    provenance="spec-test",
                )
            )
    positions = tuple(
        Position(
            instrument_id=InstrumentId.parse(symbol),
            lots=(
                AcquisitionLot(
                    quantity=quantity,
                    acquired_session=sessions[0],
                    sellable_from=sessions[0],
                    acquisition_price=Decimal("2.00"),
                ),
            ),
        )
        for symbol, quantity in held
    )
    return DecisionContext(
        session_date=final_session,
        decision_for_trade_date=final_session,
        information_cutoff=cutoff,
        cash=Money(Decimal("100000")),
        valuation_equity=Money(Decimal("100000")),
        positions=positions,
        bars=tuple(bars),
        tradability=tuple(tradability),
        corporate_actions=(),
    )


def _universe(symbols: tuple[str, ...]) -> UniverseView:
    return UniverseView(tuple(InstrumentId.parse(symbol) for symbol in symbols))


# --- absolute trend strategy -------------------------------------------------


def test_absolute_trend_no_decision_outside_month_end() -> None:
    from systematic_investing.research.strategies.etf_absolute_trend import build_strategy

    sessions = _weekdays(date(2024, 1, 2), date(2024, 2, 28))
    closes = tuple(
        Decimal("2.00") + Decimal(index) * Decimal("0.02")
        for index in range(len(sessions))
    )
    schedule = month_end_sessions(sessions)
    strategy = build_strategy({"sma_sessions": "3"}, schedule)

    evaluation = strategy.evaluate(
        _context({"XSHG:510300": closes}, sessions[:-1]),
        _universe(("XSHG:510300",)),
    )
    assert evaluation.status.value == "NO_DECISION"
    assert evaluation.reason_codes == ("NOT_DECISION_SESSION",)
    assert evaluation.contributions == ()


def test_absolute_trend_uptrend_targets_full_weight() -> None:
    from systematic_investing.research.strategies.etf_absolute_trend import build_strategy

    sessions = _weekdays(date(2024, 1, 2), date(2024, 1, 31))
    closes = tuple(
        Decimal("2.00") + Decimal(index) * Decimal("0.02")
        for index in range(len(sessions))
    )
    strategy = build_strategy({"sma_sessions": "3"}, month_end_sessions(sessions))

    evaluation = strategy.evaluate(
        _context({"XSHG:510300": closes}, sessions),
        _universe(("XSHG:510300",)),
    )

    assert evaluation.status.value == "TARGETS"
    assert evaluation.reason_codes == ()
    contribution = evaluation.contributions[0]
    assert str(contribution.instrument_id) == "XSHG:510300"
    assert contribution.sleeve is SleeveId.CORE
    assert contribution.target_weight == Decimal("1")


def test_absolute_trend_downtrend_is_explicit_cash_target() -> None:
    from systematic_investing.research.strategies.etf_absolute_trend import build_strategy

    sessions = _weekdays(date(2024, 2, 1), date(2024, 2, 29))
    closes = tuple(
        Decimal("3.00") - Decimal(index) * Decimal("0.02")
        for index in range(len(sessions))
    )
    strategy = build_strategy({"sma_sessions": "3"}, month_end_sessions(sessions))

    evaluation = strategy.evaluate(
        _context({"XSHG:510300": closes}, sessions),
        _universe(("XSHG:510300",)),
    )

    assert evaluation.status.value == "TARGETS"
    assert evaluation.contributions[0].target_weight == Decimal("0")


def test_absolute_trend_insufficient_history_is_typed_no_decision() -> None:
    from systematic_investing.research.strategies.etf_absolute_trend import build_strategy

    sessions = _weekdays(date(2024, 1, 2), date(2024, 1, 31))
    closes = (Decimal("2.00"), Decimal("2.02"))
    strategy = build_strategy({"sma_sessions": "3"}, month_end_sessions(sessions))

    evaluation = strategy.evaluate(
        _context({"XSHG:510300": closes}, sessions),
        _universe(("XSHG:510300",)),
    )

    assert evaluation.status.value == "NO_DECISION"
    assert evaluation.reason_codes == ("INSUFFICIENT_HISTORY",)


def test_absolute_trend_identity_and_determinism() -> None:
    from systematic_investing.research.strategies.etf_absolute_trend import build_strategy

    sessions = _weekdays(date(2024, 1, 2), date(2024, 1, 31))
    closes = tuple(
        Decimal("2.00") + Decimal(index) * Decimal("0.02")
        for index in range(len(sessions))
    )
    strategy = build_strategy({"sma_sessions": "3"}, month_end_sessions(sessions))
    identity = strategy.identity

    assert identity.strategy_id == "etf-absolute-trend"
    assert identity.strategy_version == "v1"
    assert identity.decision_frequency == "MONTHLY_LAST_SESSION"
    assert identity.required_history_sessions == 3
    assert identity.implementation_digest.startswith("sha256:")

    context = _context({"XSHG:510300": closes}, sessions)
    reordered = _context({"XSHG:510300": closes}, sessions)
    reordered_bars = DecisionContext(
        session_date=reordered.session_date,
        decision_for_trade_date=reordered.decision_for_trade_date,
        information_cutoff=reordered.information_cutoff,
        cash=reordered.cash,
        valuation_equity=reordered.valuation_equity,
        positions=reordered.positions,
        bars=tuple(reversed(reordered.bars)),
        tradability=reordered.tradability,
        corporate_actions=(),
    )

    assert strategy.evaluate(context, _universe(("XSHG:510300",))) == strategy.evaluate(
        reordered_bars, _universe(("XSHG:510300",))
    )


# --- relative momentum -------------------------------------------------------


def test_relative_momentum_selects_top1_by_return() -> None:
    from systematic_investing.research.strategies.etf_relative_momentum import build_strategy

    sessions = _weekdays(date(2024, 1, 2), date(2024, 1, 31))
    closes_a = tuple(Decimal("2.00") + Decimal(i) * Decimal("0.05") for i in range(len(sessions)))
    closes_b = tuple(Decimal("2.00") + Decimal(i) * Decimal("0.01") for i in range(len(sessions)))
    strategy = build_strategy({"return_sessions": "3"}, month_end_sessions(sessions))

    evaluation = strategy.evaluate(
        _context({"XSHG:510300": closes_a, "XSHG:518880": closes_b}, sessions),
        _universe(("XSHG:510300", "XSHG:518880")),
    )

    assert evaluation.status.value == "TARGETS"
    assert len(evaluation.contributions) == 1
    contribution = evaluation.contributions[0]
    assert str(contribution.instrument_id) == "XSHG:510300"
    assert contribution.target_weight == Decimal("1")
    assert contribution.sleeve is SleeveId.CORE
    assert contribution.strategy_id == "etf-relative-momentum"


def test_relative_momentum_rank_ties_break_by_instrument_id() -> None:
    from systematic_investing.research.strategies.etf_relative_momentum import build_strategy

    sessions = _weekdays(date(2024, 1, 2), date(2024, 1, 31))
    closes = tuple(Decimal("2.00") + Decimal(i) * Decimal("0.01") for i in range(len(sessions)))
    strategy = build_strategy({"return_sessions": "3"}, month_end_sessions(sessions))

    evaluation = strategy.evaluate(
        _context({"XSHG:510300": closes, "XSHG:518880": closes}, sessions),
        _universe(("XSHG:510300", "XSHG:518880")),
    )

    assert str(evaluation.contributions[0].instrument_id) == "XSHG:510300"


def test_relative_momentum_trend_gate_falls_back_to_cash() -> None:
    from systematic_investing.research.strategies.etf_relative_momentum import build_strategy

    sessions = _weekdays(date(2024, 2, 1), date(2024, 2, 29))
    closes_a = tuple(Decimal("3.00") - Decimal(i) * Decimal("0.03") for i in range(len(sessions)))
    closes_b = tuple(Decimal("3.00") - Decimal(i) * Decimal("0.01") for i in range(len(sessions)))
    strategy = build_strategy(
        {"return_sessions": "3", "trend_gate_sma_sessions": "3"},
        month_end_sessions(sessions),
    )

    evaluation = strategy.evaluate(
        _context({"XSHG:510300": closes_a, "XSHG:518880": closes_b}, sessions),
        _universe(("XSHG:510300", "XSHG:518880")),
    )

    assert evaluation.status.value == "TARGETS"
    contribution = evaluation.contributions[0]
    assert str(contribution.instrument_id) == "XSHG:518880"
    assert contribution.target_weight == Decimal("0")


def test_relative_momentum_insufficient_history_is_typed_no_decision() -> None:
    from systematic_investing.research.strategies.etf_relative_momentum import build_strategy

    sessions = _weekdays(date(2024, 1, 2), date(2024, 1, 31))
    closes = (Decimal("2.00"), Decimal("2.01"))
    strategy = build_strategy({"return_sessions": "3"}, month_end_sessions(sessions))

    evaluation = strategy.evaluate(
        _context({"XSHG:510300": closes, "XSHG:518880": closes}, sessions),
        _universe(("XSHG:510300", "XSHG:518880")),
    )

    assert evaluation.status.value == "NO_DECISION"
    assert evaluation.reason_codes == ("INSUFFICIENT_HISTORY",)


def test_relative_momentum_exits_held_instruments_outside_top1() -> None:
    from systematic_investing.research.strategies.etf_relative_momentum import build_strategy

    sessions = _weekdays(date(2024, 1, 2), date(2024, 2, 29))
    closes_strong = tuple(
        Decimal("2.00") + Decimal(i) * Decimal("0.05") for i in range(len(sessions))
    )
    closes_weak = tuple(
        Decimal("2.00") + Decimal(i) * Decimal("0.01") for i in range(len(sessions))
    )
    held = (("XSHG:510300", 500), ("XSHG:518880", 300))
    strategy = build_strategy({"return_sessions": "3"}, month_end_sessions(sessions))

    evaluation = strategy.evaluate(
        _context(
            {"XSHG:510300": closes_strong, "XSHG:518880": closes_weak},
            sessions,
            held=held,
        ),
        _universe(("XSHG:510300", "XSHG:518880")),
    )

    contributions = {str(item.instrument_id): item for item in evaluation.contributions}
    assert contributions["XSHG:510300"].target_weight == Decimal("1")
    assert contributions["XSHG:518880"].target_weight == Decimal("0")
    assert len(evaluation.contributions) == 2
