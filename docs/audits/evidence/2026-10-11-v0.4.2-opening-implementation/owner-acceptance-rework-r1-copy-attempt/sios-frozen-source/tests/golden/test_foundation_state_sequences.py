"""Cross-session accounting invariants over the adversarial golden scenarios.

The ordinary golden assertions compare each session with a hand-calculated
oracle.  These tests add a second, sequence-oriented layer: every append-only
ledger must reconstruct the terminal account, fees must be posted exactly
once, and repeating a multi-session path must preserve its digest.
"""

from collections import Counter, defaultdict
from decimal import Decimal

import pytest
from golden_harness import load_scenario, normalized_digest, run_scenario

from systematic_investing.domain.execution import OrderStatus
from systematic_investing.domain.ledger import CashLedgerCategory

STATE_SEQUENCE_RUNS = (
    ("G02", "default"),  # lot rounding and residual cash
    ("G03", "default"),  # minimum commission
    ("G04", "default"),  # sell fees and cash reconstruction
    ("G09", "default"),  # buy, T+1 transition, then sell
    ("G14", "default"),  # simultaneous buys under global cash pressure
    ("G16", "default"),  # gap-open cash pressure
    ("G19", "default"),  # sleeve cap plus limited cash
    ("G20", "stale_mark"),  # suspension with a defensible stale mark
    ("G21", "split_pending_exit"),  # action while an exit is pending
)


def _initial_quantities(run: dict[str, object]) -> Counter[str]:
    quantities: Counter[str] = Counter()
    for raw in run.get("initial_positions", ()):  # type: ignore[union-attr]
        quantities[str(raw["instrument_id"])] += int(raw["quantity"])
    return quantities


@pytest.mark.parametrize(("scenario_id", "run_name"), STATE_SEQUENCE_RUNS)
def test_state_sequence_ledgers_reconstruct_terminal_account(
    scenario_id: str, run_name: str
) -> None:
    outcome = run_scenario(load_scenario(scenario_id), run_name=run_name)
    result = outcome.result

    initial_cash = Decimal(str(outcome.run.get("initial_cash", "100000")))
    assert initial_cash + sum(
        (entry.amount.amount for entry in result.cash_entries), Decimal("0")
    ) == result.cash.amount

    reconstructed = _initial_quantities(outcome.run)
    for entry in result.holdings_entries:
        reconstructed[str(entry.instrument_id)] += entry.quantity_delta
    terminal = Counter(
        {
            str(position.instrument_id): position.total_quantity
            for position in result.positions
            if position.total_quantity
        }
    )
    assert +reconstructed == terminal

    for session in result.sessions:
        assert session.snapshot.cash.amount >= 0
        for position in session.snapshot.positions:
            assert position.sellable_quantity(session.session_date) >= 0
            assert position.sellable_quantity(session.session_date) <= position.total_quantity


@pytest.mark.parametrize(("scenario_id", "run_name"), STATE_SEQUENCE_RUNS)
def test_state_sequence_order_outcomes_and_fee_postings_are_one_to_one(
    scenario_id: str, run_name: str
) -> None:
    result = run_scenario(load_scenario(scenario_id), run_name=run_name).result
    fills_by_order = defaultdict(list)
    rejections_by_order = defaultdict(list)
    entries_by_order = defaultdict(list)
    for fill in result.fills:
        fills_by_order[fill.order_id].append(fill)
    for rejection in result.rejections:
        rejections_by_order[rejection.order_id].append(rejection)
    for entry in result.cash_entries:
        entries_by_order[entry.source_id].append(entry)

    for order in result.orders:
        fills = fills_by_order[order.order_id]
        rejections = rejections_by_order[order.order_id]
        assert not (fills and rejections)
        if order.status is OrderStatus.FILLED:
            assert len(fills) == 1
            assert fills[0].quantity == order.submitted_quantity
        elif order.status is OrderStatus.REJECTED:
            assert len(rejections) == 1
            assert not fills
        elif order.status is OrderStatus.INVALIDATED:
            assert not fills and not rejections

    for fill in result.fills:
        postings = entries_by_order[fill.order_id]
        by_category = defaultdict(list)
        for entry in postings:
            by_category[entry.category].append(entry.amount.amount)

        assert len(by_category[CashLedgerCategory.BROKER_COMMISSION]) <= 1
        expected_commission = -(
            fill.fees.commission.amount
            + fill.fees.minimum_commission_adjustment.amount
        )
        assert sum(
            by_category[CashLedgerCategory.BROKER_COMMISSION], Decimal("0")
        ) == expected_commission
        assert sum(by_category[CashLedgerCategory.STAMP_TAX], Decimal("0")) == (
            -fill.fees.stamp_tax.amount
        )
        assert sum(by_category[CashLedgerCategory.TRANSFER_FEE], Decimal("0")) == (
            -fill.fees.transfer_fee.amount
        )


@pytest.mark.parametrize(("scenario_id", "run_name"), STATE_SEQUENCE_RUNS)
def test_state_sequence_replay_is_digest_stable(scenario_id: str, run_name: str) -> None:
    scenario = load_scenario(scenario_id)
    first = run_scenario(scenario, run_name=run_name)
    second = run_scenario(scenario, run_name=run_name)

    assert first.result.content_digest() == second.result.content_digest()
    assert normalized_digest(first) == normalized_digest(second)


def test_pending_exit_is_invalidated_instead_of_rescaled_after_split() -> None:
    outcome = run_scenario(load_scenario("G21"), run_name="split_pending_exit")
    invalidated = tuple(
        order
        for order in outcome.result.orders
        if order.status is OrderStatus.INVALIDATED
    )

    assert len(invalidated) == 1
    assert invalidated[0].reason_codes == ("CORPORATE_ACTION_REPLAN_REQUIRED",)
    assert all(fill.order_id != invalidated[0].order_id for fill in outcome.result.fills)


def test_stale_mark_never_fabricates_an_execution_price() -> None:
    outcome = run_scenario(load_scenario("G20"), run_name="stale_mark")
    marked_sessions = {
        (session.session_date, str(mark.instrument_id))
        for session in outcome.result.sessions
        for mark in session.snapshot.stale_marks
    }

    assert marked_sessions
    assert all(
        (fill.session_date, str(fill.instrument_id)) not in marked_sessions
        for fill in outcome.result.fills
    )
