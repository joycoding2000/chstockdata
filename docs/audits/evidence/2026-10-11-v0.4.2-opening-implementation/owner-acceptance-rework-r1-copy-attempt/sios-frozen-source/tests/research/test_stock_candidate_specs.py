"""Canonical Stock candidate specs: frozen intents and their strategy modules.

The two Stock CandidateIntent JSON files are frozen before any canonical
Stock strategy module is written and their digests are recorded here. The
tests pin the real annual PIT policy (>=250 listed sessions, trailing
60-session median amount, non-ST/non-unknown, top-50 with stable
InstrumentId tie-breaks, minimum 20), the SATELLITE sleeve, the
same-schedule annual benchmark, the predeclared parameter priority, and the
``DIVIDEND_TAX_NOT_MODELED`` limitation. Strategy behavior is proven with
hand-audited offline facts: month-end cadence, top-N equal weight, explicit
exit targets, breakout detection, and typed no-decisions.
"""

import json
from datetime import UTC, date, datetime, time
from decimal import Decimal
from pathlib import Path

import pytest

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
from systematic_investing.research.contracts import (
    CandidateIntent,
    InvalidCandidateIntentError,
)
from systematic_investing.research.strategies import month_end_sessions
from systematic_investing.research.universe import (
    AnnualUniversePolicy,
    UniverseView,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
CANDIDATE_DIR = REPO_ROOT / "research" / "candidates"

RELATIVE_STRENGTH_INTENT_ID = "m1-stock-relative-strength-v1"
BREAKOUT_INTENT_ID = "m1-stock-breakout-v1"

# Recorded frozen digests (M1 implementation plan Task 4 Step 3): the digests
# were computed from the committed JSON files before either canonical Stock
# strategy module was written and must never change for this candidate
# version.
RECORDED_INTENT_DIGESTS: dict[str, str] = {
    RELATIVE_STRENGTH_INTENT_ID: (
        "sha256:83124b79eb01d694df9abdc1546e21e5364304da112789ec19be95a19236cd79"
    ),
    BREAKOUT_INTENT_ID: (
        "sha256:421ad6094be27b6b50dbe8a731796465e56e4c3f5ac578744286e5521b2d835f"
    ),
}


def _intent_path(intent_id: str) -> Path:
    return CANDIDATE_DIR / f"{intent_id}.json"


def _load_intent(intent_id: str) -> CandidateIntent:
    payload = json.loads(_intent_path(intent_id).read_text(encoding="utf-8"))
    return CandidateIntent.from_dict(payload)


def _assert_annual_pit_contract(intent: CandidateIntent, intent_id: str) -> None:
    """The real-Stock policy contract shared by both M1 Stock candidates."""
    assert intent.intent_id == intent_id
    assert intent.asset_class.value == "STOCK"
    assert intent.sleeve is SleeveId.SATELLITE
    assert intent.decision_frequency == "MONTHLY_LAST_SESSION"
    assert intent.parameter_selection_rule == "PRIORITY_FIRST_BASIC_PASS"
    # Annual PIT formation: the standard M1 policy thresholds, bound by name.
    assert intent.universe_policy.policy_name == "STOCK_ANNUAL_PIT_TOP50_V1"
    assert intent.universe_policy.instrument_ids == ()
    policy = AnnualUniversePolicy.standard()
    assert policy.minimum_listing_sessions == 250
    assert policy.trailing_amount_sessions == 60
    assert policy.minimum_cohort_size == 20
    assert policy.maximum_cohort_size == 50
    # Same-schedule benchmark: equal weight over the same annual cohorts.
    assert intent.benchmark.kind.value == "STOCK_ANNUAL_SCHEDULE_EQUAL_WEIGHT"
    assert intent.benchmark.instrument_ids == ()
    assert intent.benchmark.rebalance == "ANNUAL"
    assert intent.warm_up_start.isoformat() == "2017-01-03"
    assert intent.basic_start.isoformat() == "2019-01-02"
    assert intent.basic_end.isoformat() == "2022-12-30"
    assert intent.oos_start.isoformat() == "2023-01-03"
    assert intent.oos_end.isoformat() == "2025-12-31"
    assert intent.risk_off_choice == "CASH_0"
    assert set(intent.basic_promotion_rule) >= {
        "min_nav_observations",
        "min_excess_total_return_vs_benchmark",
        "max_drawdown_floor",
        "max_turnover",
    }
    assert intent.oos_survivor_rule
    # OQ-24: dividend tax stays unmodeled in M1 and must be declared.
    assert any(
        "DIVIDEND_TAX_NOT_MODELED" in limitation
        for limitation in intent.known_limitations
    )


def test_relative_strength_intent_matches_frozen_contract() -> None:
    intent = _load_intent(RELATIVE_STRENGTH_INTENT_ID)

    _assert_annual_pit_contract(intent, RELATIVE_STRENGTH_INTENT_ID)
    assert intent.lineage_id == "m1-stock-relative-strength"
    assert intent.strategy_id == "stock-relative-strength"
    assert tuple(intent.parameters_grid) == (
        "rs-126-top5",
        "rs-126-top10",
        "rs-252-top10",
    )
    assert intent.parameter_priority == (
        "rs-126-top5",
        "rs-126-top10",
        "rs-252-top10",
    )
    assert intent.variant_parameters["rs-126-top5"] == {
        "return_sessions": "126",
        "top_n": "5",
    }
    assert intent.intent_digest == RECORDED_INTENT_DIGESTS[RELATIVE_STRENGTH_INTENT_ID]


def test_breakout_intent_matches_frozen_contract() -> None:
    intent = _load_intent(BREAKOUT_INTENT_ID)

    _assert_annual_pit_contract(intent, BREAKOUT_INTENT_ID)
    assert intent.lineage_id == "m1-stock-breakout"
    assert intent.strategy_id == "stock-breakout"
    assert tuple(intent.parameters_grid) == (
        "bo-60-top5",
        "bo-60-top10",
        "bo-120-top10",
    )
    assert intent.parameter_priority == (
        "bo-60-top5",
        "bo-60-top10",
        "bo-120-top10",
    )
    assert intent.variant_parameters["bo-60-top5"] == {
        "breakout_sessions": "60",
        "liquidity_sessions": "60",
        "top_n": "5",
    }
    assert intent.intent_digest == RECORDED_INTENT_DIGESTS[BREAKOUT_INTENT_ID]


def test_stock_intent_requires_dividend_tax_limitation() -> None:
    from test_candidate_intent import _minimal_intent_payload

    payload = _minimal_intent_payload()
    payload["asset_class"] = "STOCK"
    payload["sleeve"] = "SATELLITE"
    payload["universe_policy"] = {
        "policy_name": "STOCK_ANNUAL_PIT_TOP50_V1",
        "instrument_ids": [],
    }
    payload["benchmark"] = {
        "kind": "STOCK_ANNUAL_SCHEDULE_EQUAL_WEIGHT",
        "instrument_ids": [],
        "rebalance": "ANNUAL",
    }

    with pytest.raises(InvalidCandidateIntentError):
        CandidateIntent.from_dict(payload)


# --- offline strategy facts --------------------------------------------------


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
    *,
    amounts: tuple[Decimal, ...] | None = None,
    highs: tuple[Decimal, ...] | None = None,
) -> tuple[DailyBar, ...]:
    bars: list[DailyBar] = []
    previous_close = None
    for index, (close, session_date) in enumerate(zip(closes, sessions, strict=False)):
        available_at = datetime.combine(session_date, time(15, 5), tzinfo=UTC)
        amount = amounts[index] if amounts is not None else Decimal("4000000")
        high = highs[index] if highs is not None else close
        bars.append(
            DailyBar(
                schema_version="v1",
                instrument_id=instrument_id,
                session_date=session_date,
                open=close,
                high=max(high, close),
                low=close,
                close=close,
                pre_close=previous_close,
                volume=Decimal("1000000"),
                amount=amount,
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
                provider_evidence_id="stock-spec-test-bars",
            )
        )
        previous_close = close
    return tuple(bars)


def _context(
    facts: dict[str, tuple[Decimal, ...]],
    sessions: tuple[date, ...],
    *,
    held: tuple[tuple[str, int], ...] = (),
    amounts: dict[str, tuple[Decimal, ...]] | None = None,
    highs: dict[str, tuple[Decimal, ...]] | None = None,
) -> DecisionContext:
    bars: list[DailyBar] = []
    for symbol, closes in facts.items():
        instrument_id = InstrumentId.parse(symbol)
        bars.extend(
            _bars_for(
                instrument_id,
                closes[: len(sessions)],
                sessions,
                amounts=amounts.get(symbol) if amounts else None,
                highs=highs.get(symbol) if highs else None,
            )
        )
    final_session = sessions[-1]
    cutoff = datetime.combine(final_session, time(15, 30), tzinfo=UTC)
    tradability: list[TradabilityStatus] = []
    for session_date in sessions:
        for symbol in facts:
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
                    provenance="stock-spec-test",
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
        cash=Money(Decimal("1000000")),
        valuation_equity=Money(Decimal("1000000")),
        positions=positions,
        bars=tuple(bars),
        tradability=tuple(tradability),
        corporate_actions=(),
    )


def _universe(symbols: tuple[str, ...]) -> UniverseView:
    return UniverseView(tuple(InstrumentId.parse(symbol) for symbol in symbols))


def _rising(start: str, step: str, count: int) -> tuple[Decimal, ...]:
    base = Decimal(start)
    increment = Decimal(step)
    return tuple(base + increment * index for index in range(count))


# --- stock relative strength -------------------------------------------------


def test_relative_strength_targets_top_n_equal_weight() -> None:
    from systematic_investing.research.strategies.stock_relative_strength import (
        build_strategy,
    )

    sessions = _weekdays(date(2024, 1, 2), date(2024, 1, 31))
    facts = {
        "XSHG:600001": _rising("2.00", "0.10", len(sessions)),  # strongest
        "XSHG:600002": _rising("2.00", "0.00", len(sessions)),  # flat
        "XSHG:600003": _rising("3.00", "-0.10", len(sessions)),  # falling
        "XSHG:600004": _rising("2.00", "0.02", len(sessions)),  # second
    }
    strategy = build_strategy(
        {"return_sessions": "3", "top_n": "2"}, month_end_sessions(sessions)
    )

    evaluation = strategy.evaluate(
        _context(facts, sessions),
        _universe(tuple(facts)),
    )

    assert evaluation.status.value == "TARGETS"
    weights = {
        str(item.instrument_id): item.target_weight
        for item in evaluation.contributions
    }
    assert weights == {
        "XSHG:600001": Decimal("0.5"),
        "XSHG:600004": Decimal("0.5"),
    }
    for contribution in evaluation.contributions:
        assert contribution.sleeve is SleeveId.SATELLITE
        assert contribution.strategy_id == "stock-relative-strength"


def test_relative_strength_exits_held_non_picks() -> None:
    from systematic_investing.research.strategies.stock_relative_strength import (
        build_strategy,
    )

    sessions = _weekdays(date(2024, 1, 2), date(2024, 1, 31))
    facts = {
        "XSHG:600001": _rising("2.00", "0.10", len(sessions)),
        "XSHG:600002": _rising("2.00", "0.00", len(sessions)),
    }
    strategy = build_strategy(
        {"return_sessions": "3", "top_n": "1"}, month_end_sessions(sessions)
    )

    evaluation = strategy.evaluate(
        _context(facts, sessions, held=(("XSHG:600002", 500),)),
        _universe(tuple(facts)),
    )

    weights = {
        str(item.instrument_id): item.target_weight
        for item in evaluation.contributions
    }
    assert weights == {
        "XSHG:600001": Decimal("1"),
        "XSHG:600002": Decimal("0"),
    }


def test_relative_strength_rank_ties_break_by_instrument_id() -> None:
    from systematic_investing.research.strategies.stock_relative_strength import (
        build_strategy,
    )

    sessions = _weekdays(date(2024, 1, 2), date(2024, 1, 31))
    closes = _rising("2.00", "0.01", len(sessions))
    facts = {"XSHG:600002": closes, "XSHG:600001": closes}
    strategy = build_strategy(
        {"return_sessions": "3", "top_n": "1"}, month_end_sessions(sessions)
    )

    evaluation = strategy.evaluate(
        _context(facts, sessions),
        _universe(tuple(facts)),
    )

    assert str(evaluation.contributions[0].instrument_id) == "XSHG:600001"


def test_relative_strength_insufficient_history_is_typed_no_decision() -> None:
    from systematic_investing.research.strategies.stock_relative_strength import (
        build_strategy,
    )

    sessions = _weekdays(date(2024, 1, 2), date(2024, 1, 31))
    facts = {
        "XSHG:600001": (Decimal("2.00"), Decimal("2.01")),
        "XSHG:600002": (Decimal("2.00"), Decimal("2.01")),
    }
    strategy = build_strategy(
        {"return_sessions": "3", "top_n": "1"}, month_end_sessions(sessions)
    )

    evaluation = strategy.evaluate(
        _context(facts, sessions),
        _universe(tuple(facts)),
    )

    assert evaluation.status.value == "NO_DECISION"
    assert evaluation.reason_codes == ("INSUFFICIENT_HISTORY",)
    assert evaluation.contributions == ()


def test_relative_strength_no_decision_outside_month_end() -> None:
    from systematic_investing.research.strategies.stock_relative_strength import (
        build_strategy,
    )

    sessions = _weekdays(date(2024, 1, 2), date(2024, 2, 28))
    facts = {"XSHG:600001": _rising("2.00", "0.01", len(sessions))}
    strategy = build_strategy(
        {"return_sessions": "3", "top_n": "1"}, month_end_sessions(sessions)
    )

    evaluation = strategy.evaluate(
        _context(facts, sessions[:-1]),
        _universe(tuple(facts)),
    )

    assert evaluation.status.value == "NO_DECISION"
    assert evaluation.reason_codes == ("NOT_DECISION_SESSION",)


def test_relative_strength_identity_declares_satellite_and_history() -> None:
    from systematic_investing.research.strategies.stock_relative_strength import (
        build_strategy,
    )

    sessions = _weekdays(date(2024, 1, 2), date(2024, 1, 31))
    strategy = build_strategy(
        {"return_sessions": "126", "top_n": "5"}, month_end_sessions(sessions)
    )
    identity = strategy.identity

    assert identity.strategy_id == "stock-relative-strength"
    assert identity.strategy_version == "v1"
    assert identity.sleeve is SleeveId.SATELLITE
    assert identity.required_history_sessions == 126
    assert identity.decision_frequency == "MONTHLY_LAST_SESSION"
    assert identity.implementation_digest.startswith("sha256:")


# --- stock breakout ----------------------------------------------------------


def test_breakout_targets_new_highs_by_liquidity_rank() -> None:
    from systematic_investing.research.strategies.stock_breakout import (
        build_strategy,
    )

    sessions = _weekdays(date(2024, 1, 2), date(2024, 1, 31))
    # A and C sit flat for the whole month and jump on the last session, so
    # both close strictly above their prior 3-session channel highs; B never
    # breaks out. A carries the higher trailing median amount, so top-1
    # picks A.
    facts = {
        "XSHG:600001": (
            *tuple(Decimal("9.00") for _ in range(len(sessions) - 1)),
            Decimal("10.00"),
        ),
        "XSHG:600002": _rising("5.00", "0.01", len(sessions)),
        "XSHG:600003": (
            *tuple(Decimal("3.00") for _ in range(len(sessions) - 1)),
            Decimal("4.00"),
        ),
    }
    highs = {
        "XSHG:600001": tuple(Decimal("9.00") for _ in sessions),
        "XSHG:600003": tuple(Decimal("3.00") for _ in sessions),
    }
    amounts = {
        "XSHG:600001": tuple(Decimal("9000000") for _ in sessions),
        "XSHG:600003": tuple(Decimal("4000000") for _ in sessions),
    }
    strategy = build_strategy(
        {
            "breakout_sessions": "3",
            "liquidity_sessions": "3",
            "top_n": "1",
        },
        month_end_sessions(sessions),
    )

    evaluation = strategy.evaluate(
        _context(facts, sessions, amounts=amounts, highs=highs),
        _universe(tuple(facts)),
    )

    assert evaluation.status.value == "TARGETS"
    weights = {
        str(item.instrument_id): item.target_weight
        for item in evaluation.contributions
    }
    assert weights == {"XSHG:600001": Decimal("1")}


def test_breakout_prior_high_window_excludes_the_decision_session() -> None:
    from systematic_investing.research.strategies.stock_breakout import (
        build_strategy,
    )

    sessions = _weekdays(date(2024, 1, 2), date(2024, 1, 31))
    # A close equal to the prior channel high touches it but does not break
    # it: only a close strictly above all PRIOR session highs may break out.
    closes = tuple(Decimal("5.00") for _ in sessions)
    facts = {"XSHG:600001": closes}
    highs = {"XSHG:600001": closes}
    strategy = build_strategy(
        {
            "breakout_sessions": "3",
            "liquidity_sessions": "3",
            "top_n": "1",
        },
        month_end_sessions(sessions),
    )

    evaluation = strategy.evaluate(
        _context(facts, sessions, highs=highs),
        _universe(tuple(facts)),
    )

    # No breakout and no holdings: a typed no-decision, never a silent one.
    assert evaluation.status.value == "NO_DECISION"
    assert evaluation.reason_codes == ("NO_ELIGIBLE_BREAKOUT",)


def test_breakout_without_picks_exits_held_positions() -> None:
    from systematic_investing.research.strategies.stock_breakout import (
        build_strategy,
    )

    sessions = _weekdays(date(2024, 1, 2), date(2024, 1, 31))
    closes = _rising("5.00", "-0.05", len(sessions))
    facts = {"XSHG:600001": closes}
    strategy = build_strategy(
        {
            "breakout_sessions": "3",
            "liquidity_sessions": "3",
            "top_n": "2",
        },
        month_end_sessions(sessions),
    )

    evaluation = strategy.evaluate(
        _context(facts, sessions, held=(("XSHG:600001", 300),)),
        _universe(tuple(facts)),
    )

    assert evaluation.status.value == "TARGETS"
    weights = {
        str(item.instrument_id): item.target_weight
        for item in evaluation.contributions
    }
    assert weights == {"XSHG:600001": Decimal("0")}


def test_breakout_insufficient_history_is_typed_no_decision() -> None:
    from systematic_investing.research.strategies.stock_breakout import (
        build_strategy,
    )

    sessions = _weekdays(date(2024, 1, 2), date(2024, 1, 31))
    facts = {
        "XSHG:600001": (Decimal("2.00"), Decimal("2.01")),
        "XSHG:600002": (Decimal("2.00"), Decimal("2.01")),
    }
    strategy = build_strategy(
        {
            "breakout_sessions": "3",
            "liquidity_sessions": "3",
            "top_n": "1",
        },
        month_end_sessions(sessions),
    )

    evaluation = strategy.evaluate(
        _context(facts, sessions),
        _universe(tuple(facts)),
    )

    assert evaluation.status.value == "NO_DECISION"
    assert evaluation.reason_codes == ("INSUFFICIENT_HISTORY",)


def test_breakout_no_decision_outside_month_end() -> None:
    from systematic_investing.research.strategies.stock_breakout import (
        build_strategy,
    )

    sessions = _weekdays(date(2024, 1, 2), date(2024, 2, 28))
    facts = {"XSHG:600001": _rising("5.00", "0.05", len(sessions))}
    strategy = build_strategy(
        {
            "breakout_sessions": "3",
            "liquidity_sessions": "3",
            "top_n": "1",
        },
        month_end_sessions(sessions),
    )

    evaluation = strategy.evaluate(
        _context(facts, sessions[:-1]),
        _universe(tuple(facts)),
    )

    assert evaluation.status.value == "NO_DECISION"
    assert evaluation.reason_codes == ("NOT_DECISION_SESSION",)


def test_breakout_identity_declares_satellite_and_history() -> None:
    from systematic_investing.research.strategies.stock_breakout import (
        build_strategy,
    )

    sessions = _weekdays(date(2024, 1, 2), date(2024, 1, 31))
    strategy = build_strategy(
        {
            "breakout_sessions": "120",
            "liquidity_sessions": "60",
            "top_n": "10",
        },
        month_end_sessions(sessions),
    )
    identity = strategy.identity

    assert identity.strategy_id == "stock-breakout"
    assert identity.strategy_version == "v1"
    assert identity.sleeve is SleeveId.SATELLITE
    assert identity.required_history_sessions == 121
    assert identity.decision_frequency == "MONTHLY_LAST_SESSION"
    assert identity.implementation_digest.startswith("sha256:")


def test_canonical_registry_names_both_stock_strategies() -> None:
    from systematic_investing.research.strategies import CANONICAL_STRATEGY_IDS

    assert "stock-relative-strength" in CANONICAL_STRATEGY_IDS
    assert "stock-breakout" in CANONICAL_STRATEGY_IDS
