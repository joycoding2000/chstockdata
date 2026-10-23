from datetime import UTC, date, datetime
from decimal import Decimal

from systematic_investing.backtest.engine import BacktestResult, SessionResult
from systematic_investing.backtest.execution import ActivationResult
from systematic_investing.data.snapshots import (
    ADJUSTMENT_POLICY_RAW_WITH_PIT_FACTORS,
    DataSnapshotManifest,
    SnapshotAvailabilityPolicy,
)
from systematic_investing.domain.identifiers import InstrumentId
from systematic_investing.domain.ledger import (
    AcquisitionLot,
    CashLedgerCategory,
    CashLedgerEntry,
    NavPoint,
    PortfolioSnapshot,
    Position,
    ValuationStatus,
)
from systematic_investing.domain.market import AvailabilityBasis
from systematic_investing.domain.money import Money

ETF = InstrumentId.parse("XSHG:510300")
SESSION = date(2026, 9, 17)
NOW = datetime(2026, 9, 17, 16, 0, tzinfo=UTC)


def _manifest(*, quality_report_id: str, quality_status: str) -> DataSnapshotManifest:
    return DataSnapshotManifest(
        created_at=NOW,
        knowledge_cutoff=NOW,
        provider_name="provider",
        provider_version="1.0",
        adapter_version="1.0",
        schemas={"daily_bar": "v1"},
        scope_instrument_ids=(ETF,),
        scope_start=SESSION,
        scope_end=SESSION,
        adjustment_policy=ADJUSTMENT_POLICY_RAW_WITH_PIT_FACTORS,
        availability_policy=SnapshotAvailabilityPolicy(
            allowed_bases=frozenset({AvailabilityBasis.OBSERVED}),
            unknown_handling="reject",
        ),
        retrieved_at=NOW,
        artifacts=(),
        quality_report_id=quality_report_id,
        quality_status=quality_status,
    )


def _position(*, sellable_from: date) -> Position:
    return Position(
        instrument_id=ETF,
        lots=(
            AcquisitionLot(
                quantity=100,
                acquired_session=SESSION,
                sellable_from=sellable_from,
                acquisition_price=Decimal("4.00"),
            ),
        ),
    )


def _snapshot(position: Position) -> PortfolioSnapshot:
    return PortfolioSnapshot(
        session_date=SESSION,
        generated_at=NOW,
        cash=Money(Decimal("99600")),
        positions=(position,),
        market_value=Money(Decimal("400")),
        total_equity=Money(Decimal("100000")),
        valuation_status=ValuationStatus.COMPLETE,
    )


def _result(*, ledger_source: str) -> BacktestResult:
    cash = Money(Decimal("100000"))
    snapshot = PortfolioSnapshot(
        session_date=SESSION,
        generated_at=NOW,
        cash=cash,
        positions=(),
        market_value=Money(Decimal("0")),
        total_equity=cash,
        valuation_status=ValuationStatus.COMPLETE,
    )
    nav = NavPoint(
        session_date=SESSION,
        cash=cash,
        market_value=Money(Decimal("0")),
        total_equity=cash,
        nav=Decimal("1"),
        valuation_status=ValuationStatus.COMPLETE,
    )
    entry = CashLedgerEntry(
        entry_id="cash:external:deposit",
        category=CashLedgerCategory.DEPOSIT,
        amount=Money(Decimal("100000")),
        session_date=SESSION,
        recorded_at=NOW,
        source_id=ledger_source,
    )
    activation = ActivationResult(
        orders=(),
        fills=(),
        rejections=(),
        cash_entries=(entry,),
        holdings_entries=(),
        positions=(),
        cash=cash,
    )
    session = SessionResult(
        session_date=SESSION,
        corporate_action_effects=(),
        invalidated_orders=(),
        activation=activation,
        snapshot=snapshot,
        nav=nav,
        target=None,
        plans=(),
        decision_digest=None,
        decision_blocked_reason=None,
    )
    return BacktestResult(sessions=(session,), cash=cash, positions=())


def test_snapshot_identity_binds_quality_receipt_and_status() -> None:
    passed = _manifest(quality_report_id="quality:1", quality_status="PASS")
    failed = _manifest(quality_report_id="quality:2", quality_status="FAIL")

    assert passed.snapshot_id != failed.snapshot_id


def test_portfolio_snapshot_digest_binds_acquisition_lot_schedule() -> None:
    next_session = _snapshot(_position(sellable_from=date(2026, 9, 18)))
    later_session = _snapshot(_position(sellable_from=date(2026, 9, 21)))

    assert next_session.positions[0].total_quantity == later_session.positions[0].total_quantity
    assert next_session.positions[0].sellable_quantity(SESSION) == 0
    assert later_session.positions[0].sellable_quantity(SESSION) == 0
    assert next_session.content_digest() != later_session.content_digest()


def test_backtest_digest_binds_ledger_source_identity() -> None:
    owner_deposit = _result(ledger_source="owner:deposit")
    synthetic_deposit = _result(ledger_source="synthetic:deposit")

    assert owner_deposit.content_digest() != synthetic_deposit.content_digest()
