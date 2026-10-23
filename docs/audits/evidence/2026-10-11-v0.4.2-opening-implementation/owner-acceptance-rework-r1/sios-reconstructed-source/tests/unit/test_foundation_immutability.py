from datetime import UTC, date, datetime
from decimal import Decimal

from systematic_investing.backtest.engine import DecisionContext
from systematic_investing.data.contracts import ProviderEvidence, ProviderSuccess
from systematic_investing.data.quality import (
    CheckResult,
    CheckSeverity,
    CheckStatus,
    GateAction,
    GateResult,
    GateStatus,
)
from systematic_investing.data.snapshots import (
    ADJUSTMENT_POLICY_RAW_WITH_PIT_FACTORS,
    DataSnapshotManifest,
    SnapshotAvailabilityPolicy,
)
from systematic_investing.domain.execution import Order, OrderStatus
from systematic_investing.domain.identifiers import InstrumentId, SleeveId
from systematic_investing.domain.ledger import NavPoint, ValuationStatus
from systematic_investing.domain.market import (
    AdjustmentMode,
    Availability,
    AvailabilityBasis,
    DailyBar,
    TradeSide,
)
from systematic_investing.domain.money import Money
from systematic_investing.domain.portfolio import (
    SizingPriceBasis,
    TargetContribution,
    TheoreticalTargetPortfolio,
)
from systematic_investing.domain.runs import RunManifest, RunPurpose

ETF = InstrumentId.parse("XSHG:510300")
NOW = datetime(2026, 9, 17, 16, 0, tzinfo=UTC)
DECISION_DATE = date(2026, 9, 17)
TRADE_DATE = date(2026, 9, 18)


def _bar(session_date: date) -> DailyBar:
    return DailyBar(
        schema_version="v1",
        instrument_id=ETF,
        session_date=session_date,
        open=Decimal("4.00"),
        high=Decimal("4.10"),
        low=Decimal("3.90"),
        close=Decimal("4.05"),
        pre_close=Decimal("4.00"),
        volume=Decimal("1000"),
        amount=Decimal("4050"),
        currency="CNY",
        volume_unit="SHARE",
        amount_unit="CNY",
        adjustment_mode=AdjustmentMode.RAW,
        adjustment_factor=None,
        availability=Availability(
            information_available_at=NOW,
            retrieved_at=NOW,
            availability_basis=AvailabilityBasis.OBSERVED,
        ),
        provider_evidence_id="evidence:bar",
    )


def _target(evidence_ids: object) -> TheoreticalTargetPortfolio:
    contribution = TargetContribution(
        instrument_id=ETF,
        sleeve=SleeveId.CORE,
        strategy_id="fixture-not-strategy",
        strategy_version="v1",
        target_weight=Decimal("0.50"),
        evidence_ids=evidence_ids,  # type: ignore[arg-type]
    )
    return TheoreticalTargetPortfolio(
        target_id="target:immutable",
        revision=1,
        decision_for_trade_date=TRADE_DATE,
        generated_at=NOW,
        information_cutoff=NOW,
        valuation_equity=Money(Decimal("100000")),
        contributions=(contribution,),
    )


def test_decision_context_copies_caller_owned_market_sequences() -> None:
    known = _bar(DECISION_DATE)
    bars = [known]
    context = DecisionContext(
        session_date=DECISION_DATE,
        decision_for_trade_date=TRADE_DATE,
        information_cutoff=NOW,
        cash=Money(Decimal("100000")),
        valuation_equity=Money(Decimal("100000")),
        positions=[],  # type: ignore[arg-type]
        bars=bars,  # type: ignore[arg-type]
        tradability=[],  # type: ignore[arg-type]
        corporate_actions=[],  # type: ignore[arg-type]
    )

    bars.append(_bar(TRADE_DATE))

    assert context.bars == (known,)
    assert context.bars_for(ETF) == (known,)
    assert context.positions == ()
    assert context.tradability == ()
    assert context.corporate_actions == ()


def test_snapshot_manifest_copies_nested_identity_collections() -> None:
    schemas = {"daily_bar": "v1"}
    allowed_bases = {AvailabilityBasis.OBSERVED}
    manifest = DataSnapshotManifest(
        created_at=NOW,
        knowledge_cutoff=NOW,
        provider_name="provider",
        provider_version="1.0",
        adapter_version="1.0",
        schemas=schemas,
        scope_instrument_ids=(ETF,),
        scope_start=DECISION_DATE,
        scope_end=DECISION_DATE,
        adjustment_policy=ADJUSTMENT_POLICY_RAW_WITH_PIT_FACTORS,
        availability_policy=SnapshotAvailabilityPolicy(
            allowed_bases=allowed_bases,  # type: ignore[arg-type]
            unknown_handling="reject",
        ),
        retrieved_at=NOW,
        artifacts=(),
    )
    identity = manifest.snapshot_id

    schemas["corporate_action"] = "v2"
    allowed_bases.add(AvailabilityBasis.UNKNOWN)

    assert dict(manifest.schemas) == {"daily_bar": "v1"}
    assert manifest.availability_policy.allowed_bases == frozenset(
        {AvailabilityBasis.OBSERVED}
    )
    assert manifest.snapshot_id == identity


def test_gate_result_copies_nested_collections_and_keeps_digest_stable() -> None:
    affected_scope = ["XSHG:510300"]
    evidence_ids = ["evidence:quality"]
    input_digests = {"dataset": "sha256:dataset"}
    check = CheckResult(
        check_id="PIT",
        status=CheckStatus.PASS,
        severity=CheckSeverity.BLOCKING,
        reason_code="PIT_OK",
        affected_scope=affected_scope,  # type: ignore[arg-type]
        evidence_ids=evidence_ids,  # type: ignore[arg-type]
    )
    result = GateResult(
        gate_name="M0_DATA_QUALITY",
        gate_version="v1",
        purpose=RunPurpose.DECISION,
        status=GateStatus.PASS,
        action=GateAction.PROCEED,
        evaluated_at=NOW,
        checks=(check,),
        reason_codes=("PIT_OK",),
        input_digests=input_digests,
    )
    digest = result.content_digest()

    affected_scope.append("XSHG:511010")
    evidence_ids.append("evidence:late")
    input_digests["policy"] = "sha256:changed"

    assert result.checks[0].affected_scope == ("XSHG:510300",)
    assert result.checks[0].evidence_ids == ("evidence:quality",)
    assert dict(result.input_digests) == {"dataset": "sha256:dataset"}
    assert result.content_digest() == digest


def test_run_manifest_copies_rule_versions_and_keeps_identity_stable() -> None:
    rule_versions = [["instrument-master", "v1"]]
    manifest = RunManifest(
        manifest_schema_version="m0-run-manifest-1",
        run_type="BACKTEST",
        code_commit="a" * 40,
        dependency_lock_digest="sha256:dependencies",
        data_snapshot_digest="sha256:snapshot",
        fee_config_digest="sha256:fees",
        calendar_digest="sha256:calendar",
        execution_model_version="NEXT_SESSION_OPEN-v1",
        rule_versions=rule_versions,  # type: ignore[arg-type]
        metric_convention_digest="sha256:metrics",
        benchmark_identity="NONE",
        random_seed=0,
    )
    digest = manifest.identity_digest

    rule_versions[0][1] = "v2"
    rule_versions.append(["risk", "v1"])

    assert manifest.rule_versions == (("instrument-master", "v1"),)
    assert manifest.identity_digest == digest


def test_target_contribution_copies_evidence_and_keeps_digest_stable() -> None:
    evidence_ids = ["evidence:target"]
    target = _target(evidence_ids)
    digest = target.content_digest

    evidence_ids.append("evidence:future")

    assert target.contributions[0].evidence_ids == ("evidence:target",)
    assert target.content_digest == digest


def test_order_copies_reason_codes() -> None:
    reason_codes = ["PLANNED"]
    order = Order(
        order_id="order:immutable",
        instrument_id=ETF,
        side=TradeSide.BUY,
        planned_quantity=100,
        submitted_quantity=None,
        execution_session=TRADE_DATE,
        sizing_reference_price_basis=SizingPriceBasis.T_CLOSE,
        sizing_reference_price=Decimal("4.05"),
        fill_price_model="NEXT_SESSION_OPEN",
        target_id="target:immutable",
        target_revision=1,
        decision_for_trade_date=TRADE_DATE,
        status=OrderStatus.PENDING_ACTIVATION,
        reason_codes=reason_codes,  # type: ignore[arg-type]
    )

    reason_codes.append("MUTATED")

    assert order.reason_codes == ("PLANNED",)


def test_provider_success_copies_records() -> None:
    records = [_bar(DECISION_DATE)]
    evidence = ProviderEvidence(
        evidence_id="evidence:provider",
        provider_name="provider",
        provider_version="1.0",
        adapter_name="adapter",
        adapter_version="1.0",
        capability="daily_bars",
        request_digest="sha256:request",
        retrieved_at=NOW,
        upstream_source=None,
        record_count=1,
        payload_checksum="sha256:payload",
    )
    result = ProviderSuccess(records=records, evidence=evidence)  # type: ignore[arg-type]

    records.clear()

    assert result.records == (_bar(DECISION_DATE),)


def test_nav_point_copies_stale_and_incomplete_collections() -> None:
    stale_marks: list[object] = []
    incomplete_reasons: list[object] = []
    point = NavPoint(
        session_date=DECISION_DATE,
        cash=Money(Decimal("100000")),
        market_value=Money(Decimal("0")),
        total_equity=Money(Decimal("100000")),
        nav=Decimal("1"),
        valuation_status=ValuationStatus.COMPLETE,
        stale_marks=stale_marks,  # type: ignore[arg-type]
        incomplete_reasons=incomplete_reasons,  # type: ignore[arg-type]
    )

    stale_marks.append("MUTATED")
    incomplete_reasons.append("MUTATED")

    assert point.stale_marks == ()
    assert point.incomplete_reasons == ()
