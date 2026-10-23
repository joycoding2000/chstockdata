"""Unit tests: the Data Quality Gate over canonical datasets.

Every expected outcome is reasoned from the declared dataset policy and the
approved Instrument Master authority; expected values are hand-derived, never
generated from the implementation. Fixed dates/timestamps only, no network.
"""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from systematic_investing.data.quality import (
    CanonicalDataset,
    CheckSeverity,
    CheckStatus,
    DataQualityGate,
    DatasetPolicy,
    GateAction,
    GateStatus,
    InvalidGateRequestError,
    ReductionEvidence,
)
from systematic_investing.domain.identifiers import Exchange, InstrumentId
from systematic_investing.domain.market import (
    AdjustmentMode,
    Availability,
    AvailabilityBasis,
    CorporateAction,
    CorporateActionKind,
    DailyBar,
    TradingSession,
)
from systematic_investing.domain.money import Money
from systematic_investing.domain.runs import RunPurpose
from systematic_investing.instrument_master.models import (
    LotRule,
    OddLotSellPolicy,
    RuleCandidate,
    RuleKind,
    RuleSource,
)
from systematic_investing.instrument_master.repository import default_m0_master

XSHG_510300 = InstrumentId(exchange=Exchange.XSHG, symbol="510300")
XSHE_000001 = InstrumentId(exchange=Exchange.XSHE, symbol="000001")

RETRIEVED_AT = datetime(2026, 9, 14, 16, 0, tzinfo=UTC)
DECISION_CUTOFF = datetime(2026, 9, 14, 15, 0, tzinfo=UTC)
EVALUATED_AT = datetime(2026, 9, 14, 15, 5, tzinfo=UTC)
INTENDED_SESSION = date(2026, 9, 14)

SESSION_DAYS = (
    (date(2026, 9, 11), True, None),
    (date(2026, 9, 12), False, "weekend"),
    (date(2026, 9, 13), False, "weekend"),
    (date(2026, 9, 14), True, None),
)


def sessions() -> tuple[TradingSession, ...]:
    records = []
    for calendar_id in ("XSHG", "XSHE"):
        for session_date, is_open, note in SESSION_DAYS:
            records.append(
                TradingSession(
                    calendar_id=calendar_id,
                    session_date=session_date,
                    is_open=is_open,
                    note=note,
                    snapshot_version="CAL-TEST-1",
                )
            )
    return tuple(records)


def daily_bar(
    instrument_id: InstrumentId,
    session_date: date,
    close: str,
    *,
    pre_close: str | None = "synthetic-prior-close",
    information_at: datetime | None = DECISION_CUTOFF,
    basis: AvailabilityBasis = AvailabilityBasis.OBSERVED,
    retrieved_at: datetime = RETRIEVED_AT,
    schema_version: str = "v1",
) -> DailyBar:
    """Build a one-price bar; ``pre_close="synthetic-prior-close"`` resolves to
    the prior dataset close when one exists, else the bar's own close."""
    close_value = Decimal(close)
    if pre_close == "synthetic-prior-close":
        is_first_session = session_date == date(2026, 9, 11)
        pre_close_value = (
            close_value * Decimal("0.99") if is_first_session else close_value
        )
    elif pre_close is None:
        pre_close_value = None
    else:
        pre_close_value = Decimal(pre_close)
    return DailyBar(
        schema_version=schema_version,
        instrument_id=instrument_id,
        session_date=session_date,
        open=close_value,
        high=close_value,
        low=close_value,
        close=close_value,
        pre_close=pre_close_value,
        volume=Decimal("1000"),
        amount=close_value * Decimal("1000"),
        currency="CNY",
        volume_unit="share",
        amount_unit="CNY",
        adjustment_mode=AdjustmentMode.RAW,
        adjustment_factor=None,
        availability=Availability(
            information_available_at=information_at,
            retrieved_at=retrieved_at,
            availability_basis=basis,
        ),
        provider_evidence_id="ev-quality-test",
    )


def clean_dataset() -> CanonicalDataset:
    return CanonicalDataset(
        daily_bars=(
            daily_bar(XSHG_510300, date(2026, 9, 11), "4.00", pre_close="3.95"),
            daily_bar(XSHG_510300, date(2026, 9, 14), "4.10", pre_close="4.00"),
            daily_bar(XSHE_000001, date(2026, 9, 11), "12.00", pre_close="11.88"),
            daily_bar(XSHE_000001, date(2026, 9, 14), "12.20", pre_close="12.00"),
        ),
        sessions=sessions(),
        tradability=(),
        corporate_actions=(),
        rule_candidates=(),
    )


def dividend_action(instrument_id: InstrumentId, ex_date: date) -> CorporateAction:
    return CorporateAction(
        action_id="ACT-QUALITY-1",
        instrument_id=instrument_id,
        action_kind=CorporateActionKind.CASH_DIVIDEND,
        ex_date=ex_date,
        record_date=None,
        pay_date=None,
        cash_amount=Money(Decimal("0.05")),
        share_ratio=None,
        revision=1,
        availability=Availability(
            information_available_at=datetime(2026, 9, 13, 18, 0, tzinfo=UTC),
            retrieved_at=RETRIEVED_AT,
            availability_basis=AvailabilityBasis.OBSERVED,
        ),
        provenance="exchange-announcement",
    )


def run_gate(dataset, *, purpose=RunPurpose.DECISION, policy=None, **overrides):
    gate = DataQualityGate(master=default_m0_master(), policy=policy or DatasetPolicy())
    return gate.evaluate(
        dataset,
        purpose=purpose,
        intended_decision_session=INTENDED_SESSION,
        information_cutoff=DECISION_CUTOFF,
        evaluated_at=EVALUATED_AT,
        **overrides,
    )


def failing_reasons(result) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            check.reason_code
            for check in result.checks
            if check.status is CheckStatus.FAIL and check.severity is CheckSeverity.BLOCKING
        )
    )


class TestCoreChecks:
    def test_clean_dataset_passes_for_a_new_target_decision(self) -> None:
        result = run_gate(clean_dataset())

        assert result.status is GateStatus.PASS
        assert result.action is GateAction.PROCEED
        assert failing_reasons(result) == ()

    def test_duplicate_instrument_session_bar_key_fails_closed(self) -> None:
        bars = list(clean_dataset().daily_bars)
        bars.append(
            daily_bar(XSHG_510300, date(2026, 9, 14), "4.10", pre_close="4.00")
        )
        dataset = CanonicalDataset(
            daily_bars=tuple(bars),
            sessions=sessions(),
            tradability=(),
            corporate_actions=(),
            rule_candidates=(),
        )

        result = run_gate(dataset)

        assert result.status is GateStatus.FAIL
        assert result.action is GateAction.BLOCK_NEW_TARGET
        assert failing_reasons(result) == ("DUPLICATE_BAR_KEY",)

    def test_missing_required_pre_close_field_fails_without_zero_conversion(self) -> None:
        dataset = clean_dataset()
        bars = list(dataset.daily_bars)
        bars[1] = daily_bar(XSHG_510300, date(2026, 9, 14), "4.10", pre_close=None)
        dataset = CanonicalDataset(
            daily_bars=tuple(bars),
            sessions=dataset.sessions,
            tradability=(),
            corporate_actions=(),
            rule_candidates=(),
        )

        result = run_gate(dataset)

        assert result.status is GateStatus.FAIL
        assert failing_reasons(result) == ("MISSING_REQUIRED_FIELD",)

    def test_bar_on_closed_calendar_session_fails(self) -> None:
        dataset = clean_dataset()
        bars = list(dataset.daily_bars)
        bars.append(
            daily_bar(XSHG_510300, date(2026, 9, 12), "4.02", pre_close="4.00")
        )
        dataset = CanonicalDataset(
            daily_bars=tuple(bars),
            sessions=dataset.sessions,
            tradability=(),
            corporate_actions=(),
            rule_candidates=(),
        )

        result = run_gate(dataset)

        assert result.status is GateStatus.FAIL
        assert failing_reasons(result) == ("BAR_ON_CLOSED_SESSION",)

    def test_unsupported_bar_schema_version_fails_closed(self) -> None:
        dataset = clean_dataset()
        bars = list(dataset.daily_bars)
        bars[0] = daily_bar(
            XSHG_510300, date(2026, 9, 11), "4.00", pre_close="3.95", schema_version="v9"
        )
        dataset = CanonicalDataset(
            daily_bars=tuple(bars),
            sessions=dataset.sessions,
            tradability=(),
            corporate_actions=(),
            rule_candidates=(),
        )

        result = run_gate(dataset)

        assert result.status is GateStatus.FAIL
        assert failing_reasons(result) == ("UNSUPPORTED_SCHEMA_VERSION",)

    def test_pre_close_mismatch_with_prior_close_without_action_fails(self) -> None:
        dataset = clean_dataset()
        bars = list(dataset.daily_bars)
        bars[1] = daily_bar(XSHG_510300, date(2026, 9, 14), "4.10", pre_close="4.05")
        dataset = CanonicalDataset(
            daily_bars=tuple(bars),
            sessions=dataset.sessions,
            tradability=(),
            corporate_actions=(),
            rule_candidates=(),
        )

        result = run_gate(dataset)

        assert result.status is GateStatus.FAIL
        assert failing_reasons(result) == ("PRE_CLOSE_MISMATCH_WITHOUT_ACTION",)

    def test_pre_close_mismatch_is_allowed_when_a_corporate_action_is_effective(
        self,
    ) -> None:
        dataset = clean_dataset()
        bars = list(dataset.daily_bars)
        bars[1] = daily_bar(XSHG_510300, date(2026, 9, 14), "4.10", pre_close="4.05")
        dataset = CanonicalDataset(
            daily_bars=tuple(bars),
            sessions=dataset.sessions,
            tradability=(),
            corporate_actions=(dividend_action(XSHG_510300, date(2026, 9, 14)),),
            rule_candidates=(),
        )

        result = run_gate(dataset)

        assert result.status is GateStatus.PASS
        assert failing_reasons(result) == ()

    def test_missing_calendar_snapshot_fails_closed(self) -> None:
        dataset = CanonicalDataset(
            daily_bars=clean_dataset().daily_bars,
            sessions=(),
            tradability=(),
            corporate_actions=(),
            rule_candidates=(),
        )

        result = run_gate(dataset)

        assert result.status is GateStatus.FAIL
        assert failing_reasons(result) == ("CALENDAR_NOT_PROVIDED",)

    def test_gate_purpose_must_be_a_declared_run_purpose(self) -> None:
        gate = DataQualityGate(master=default_m0_master(), policy=DatasetPolicy())

        with pytest.raises(InvalidGateRequestError) as error:
            gate.evaluate(
                clean_dataset(),
                purpose="DECISION",
                intended_decision_session=INTENDED_SESSION,
                information_cutoff=DECISION_CUTOFF,
                evaluated_at=EVALUATED_AT,
            )
        assert "purpose" in str(error.value)


class TestInformationTime:
    def test_fact_not_knowable_at_decision_cutoff_fails(self) -> None:
        dataset = clean_dataset()
        bars = list(dataset.daily_bars)
        bars[3] = daily_bar(
            XSHE_000001,
            date(2026, 9, 14),
            "12.20",
            pre_close="12.00",
            information_at=datetime(2026, 9, 14, 15, 30, tzinfo=UTC),
        )
        dataset = CanonicalDataset(
            daily_bars=tuple(bars),
            sessions=dataset.sessions,
            tradability=(),
            corporate_actions=(),
            rule_candidates=(),
        )

        result = run_gate(dataset)

        assert result.status is GateStatus.FAIL
        # The unknowable fact also drags the instrument's knowable history
        # back to the prior session, so freshness fails for the same scope.
        assert failing_reasons(result) == (
            "INFORMATION_NOT_AVAILABLE_AT_CUTOFF",
            "STALE_INFORMATION",
        )
        information_checks = [
            check for check in result.checks if check.check_id == "INFORMATION_TIME"
        ]
        assert information_checks[0].affected_scope == ("XSHE:000001", "2026-09-14")

    def test_same_retrieval_time_with_earlier_information_remains_knowable(self) -> None:
        # Both instruments' bars share retrieved_at; only the fact whose
        # information time is at/before the cutoff stays accessible.
        result = run_gate(clean_dataset())
        assert result.status is GateStatus.PASS


class TestUnknownAvailability:
    def test_unknown_availability_basis_is_rejected_for_a_decision(self) -> None:
        dataset = clean_dataset()
        bars = list(dataset.daily_bars)
        bars[3] = daily_bar(
            XSHE_000001,
            date(2026, 9, 14),
            "12.20",
            pre_close="12.00",
            information_at=None,
            basis=AvailabilityBasis.UNKNOWN,
        )
        dataset = CanonicalDataset(
            daily_bars=tuple(bars),
            sessions=dataset.sessions,
            tradability=(),
            corporate_actions=(),
            rule_candidates=(),
        )

        result = run_gate(dataset)

        assert result.status is GateStatus.FAIL
        # Same compound effect: the unknown basis is rejected and the
        # instrument's knowable history ages past the policy.
        assert failing_reasons(result) == (
            "UNKNOWN_INFORMATION_AVAILABILITY",
            "STALE_INFORMATION",
        )


class TestFreshness:
    def stale_dataset(self) -> CanonicalDataset:
        stale_bars = tuple(
            bar for bar in clean_dataset().daily_bars if bar.session_date == date(2026, 9, 11)
        )
        return CanonicalDataset(
            daily_bars=stale_bars,
            sessions=sessions(),
            tradability=(),
            corporate_actions=(),
            rule_candidates=(),
        )

    def test_information_older_than_policy_age_fails_with_injected_cutoff(self) -> None:
        result = run_gate(self.stale_dataset())

        assert result.status is GateStatus.FAIL
        assert failing_reasons(result) == ("STALE_INFORMATION",)

    def test_information_within_policy_age_passes(self) -> None:
        policy = DatasetPolicy(max_information_age_sessions=1)

        result = run_gate(self.stale_dataset(), policy=policy)

        assert result.status is GateStatus.PASS
        assert failing_reasons(result) == ()

    def test_information_from_a_session_after_the_intended_session_fails(self) -> None:
        late_sessions = (
            *sessions(),
            TradingSession(
                calendar_id="XSHG",
                session_date=date(2026, 9, 15),
                is_open=True,
                note=None,
                snapshot_version="CAL-TEST-1",
            ),
            TradingSession(
                calendar_id="XSHE",
                session_date=date(2026, 9, 15),
                is_open=True,
                note=None,
                snapshot_version="CAL-TEST-1",
            ),
        )
        future_bar = daily_bar(
            XSHG_510300,
            date(2026, 9, 15),
            "4.20",
            pre_close="4.10",
            retrieved_at=datetime(2026, 9, 15, 16, 0, tzinfo=UTC),
        )
        dataset = CanonicalDataset(
            daily_bars=(*clean_dataset().daily_bars, future_bar),
            sessions=late_sessions,
            tradability=(),
            corporate_actions=(),
            rule_candidates=(),
        )

        result = run_gate(dataset)

        assert result.status is GateStatus.FAIL
        assert failing_reasons(result) == ("SESSION_AFTER_INTENDED_DECISION",)


class TestInstrumentMasterAuthority:
    def lot_candidate(self, instrument_id, board_lot: int) -> RuleCandidate:
        return RuleCandidate(
            instrument_id=instrument_id,
            session_date=INTENDED_SESSION,
            rule_kind=RuleKind.LOT,
            proposed_value=LotRule(
                profile_id="LOT:PROVIDER",
                effective_from=INTENDED_SESSION,
                effective_to=None,
                source=RuleSource(
                    authority="provider", reference="test", accessed_on=INTENDED_SESSION
                ),
                board_lot=board_lot,
                buy_increment=board_lot,
                odd_lot_sell_policy=OddLotSellPolicy.PROHIBITED,
            ),
            proposed_by="chstockdata",
        )

    def dataset_with_candidate(self, candidate: RuleCandidate) -> CanonicalDataset:
        return CanonicalDataset(
            daily_bars=clean_dataset().daily_bars,
            sessions=sessions(),
            tradability=(),
            corporate_actions=(),
            rule_candidates=(candidate,),
        )

    def test_conflicting_provider_rule_candidate_is_adjudicated_by_the_authority(
        self,
    ) -> None:
        candidate = self.lot_candidate(XSHG_510300, board_lot=200)
        result = run_gate(self.dataset_with_candidate(candidate))

        assert result.status is GateStatus.PASS
        passing = [
            check
            for check in result.checks
            if check.check_id == "INSTRUMENT_MASTER_AUTHORITY"
            and check.status is CheckStatus.PASS
        ]
        assert len(passing) == 1
        assert passing[0].reason_code == "APPROVED_PROFILE_GOVERNS"
        assert passing[0].affected_scope == ("XSHG:510300", "2026-09-14")

    def test_rule_candidate_without_an_approved_profile_fails_closed(self) -> None:
        candidate = self.lot_candidate(
            InstrumentId(exchange=Exchange.XSHG, symbol="600000"), board_lot=200
        )

        result = run_gate(self.dataset_with_candidate(candidate))

        assert result.status is GateStatus.FAIL
        assert failing_reasons(result) == ("RULE_CANDIDATE_FAIL_CLOSED",)

    def test_bar_for_an_unregistered_instrument_fails_closed(self) -> None:
        dataset = clean_dataset()
        bars = list(dataset.daily_bars)
        bars.append(
            daily_bar(
                InstrumentId(exchange=Exchange.XSHG, symbol="600000"),
                date(2026, 9, 14),
                "8.00",
                pre_close="7.90",
            )
        )
        dataset = CanonicalDataset(
            daily_bars=tuple(bars),
            sessions=dataset.sessions,
            tradability=(),
            corporate_actions=(),
            rule_candidates=(),
        )

        result = run_gate(dataset)

        assert result.status is GateStatus.FAIL
        assert failing_reasons(result) == ("UNKNOWN_INSTRUMENT_CLASSIFICATION",)

    def test_instrument_with_an_uncovered_rule_profile_fails_closed(self) -> None:
        from systematic_investing.domain.instruments import Instrument, InstrumentType
        from systematic_investing.instrument_master.repository import InstrumentMaster

        master = InstrumentMaster()
        master.register_instrument(
            Instrument(
                instrument_id=InstrumentId(exchange=Exchange.XSHG, symbol="600000"),
                display_name="Uncovered rules fixture",
                currency="CNY",
                instrument_type=InstrumentType.A_SHARE,
                fund_subtype=None,
                list_date=date(2020, 1, 1),
                delist_date=None,
                trading_calendar_id="XSHG",
                lot_rule_profile_id="LOT:TEST",
                settlement_rule_profile_id="SETTLE:TEST",
                price_limit_rule_profile_id="PLIMIT:TEST",
                market_fee_tax_profile_id="FEE:TEST",
                reference_data_version="TEST-1",
                valid_from=date(2020, 1, 1),
                valid_to=None,
            )
        )
        uncovered_bar = daily_bar(
            InstrumentId(exchange=Exchange.XSHG, symbol="600000"),
            date(2026, 9, 14),
            "8.00",
            pre_close="7.90",
        )
        dataset = CanonicalDataset(
            daily_bars=(uncovered_bar,),
            sessions=sessions(),
            tradability=(),
            corporate_actions=(),
            rule_candidates=(),
        )
        gate = DataQualityGate(master=master, policy=DatasetPolicy())

        result = gate.evaluate(
            dataset,
            purpose=RunPurpose.DECISION,
            intended_decision_session=INTENDED_SESSION,
            information_cutoff=DECISION_CUTOFF,
            evaluated_at=EVALUATED_AT,
        )

        assert result.status is GateStatus.FAIL
        assert failing_reasons(result) == ("UNKNOWN_RULE_PROFILE",)


class TestPurposeSpecificActions:
    def stale_dataset(self) -> CanonicalDataset:
        stale_bars = tuple(
            bar for bar in clean_dataset().daily_bars if bar.session_date == date(2026, 9, 11)
        )
        return CanonicalDataset(
            daily_bars=stale_bars,
            sessions=sessions(),
            tradability=(),
            corporate_actions=(),
            rule_candidates=(),
        )

    def complete_evidence(self) -> ReductionEvidence:
        return ReductionEvidence(
            identity_evidence_id="ev-identity",
            holding_evidence_id="ev-holding",
            sellability_evidence_id="ev-sellable",
            tradability_evidence_id="ev-tradable",
            price_cost_evidence_id="ev-price-cost",
        )

    def test_pre_open_critical_failure_blocks_risk_increase_but_allows_reduction(
        self,
    ) -> None:
        result = run_gate(
            self.stale_dataset(),
            purpose=RunPurpose.PRE_OPEN,
            reduction_intended=True,
            reduction_evidence=self.complete_evidence(),
        )

        assert result.status is GateStatus.FAIL
        assert result.action is GateAction.BLOCK_RISK_INCREASE

    def test_reduction_without_complete_evidence_emits_no_order_and_escalates(
        self,
    ) -> None:
        evidence = ReductionEvidence(
            identity_evidence_id="ev-identity",
            holding_evidence_id="ev-holding",
            sellability_evidence_id="ev-sellable",
            tradability_evidence_id="ev-tradable",
            price_cost_evidence_id=None,
        )

        result = run_gate(
            clean_dataset(),
            purpose=RunPurpose.PRE_OPEN,
            reduction_intended=True,
            reduction_evidence=evidence,
        )

        assert result.status is GateStatus.FAIL
        assert result.action is GateAction.NO_ORDER_MANUAL_REVIEW
        assert "INSUFFICIENT_REDUCTION_EVIDENCE" in result.reason_codes
        assert "URGENT_MANUAL_REVIEW_REQUIRED" in result.reason_codes

    def test_reduction_with_complete_evidence_proceeds(self) -> None:
        result = run_gate(
            clean_dataset(),
            purpose=RunPurpose.PRE_OPEN,
            reduction_intended=True,
            reduction_evidence=self.complete_evidence(),
        )

        assert result.status is GateStatus.PASS
        assert result.action is GateAction.PROCEED


class TestGateIdentity:
    def test_gate_result_digest_is_deterministic_and_input_sensitive(self) -> None:
        first = run_gate(clean_dataset())
        second = run_gate(clean_dataset())
        assert first.content_digest() == second.content_digest()

        bars = list(clean_dataset().daily_bars)
        bars[1] = daily_bar(XSHG_510300, date(2026, 9, 14), "4.11", pre_close="4.00")
        other = run_gate(
            CanonicalDataset(
                daily_bars=tuple(bars),
                sessions=sessions(),
                tradability=(),
                corporate_actions=(),
                rule_candidates=(),
            )
        )
        assert other.content_digest() != first.content_digest()
