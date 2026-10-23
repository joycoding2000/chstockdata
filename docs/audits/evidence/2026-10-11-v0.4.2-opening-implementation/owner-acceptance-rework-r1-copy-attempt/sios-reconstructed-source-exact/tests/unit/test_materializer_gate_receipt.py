"""Materializer gate-receipt persistence tests.

The owner materializer computes the M0 data quality gate before writing any
snapshot. That decision is evidence and must be persisted as an immutable
receipt bound to the snapshot id; a gate result that exists only in the
process cannot be audited later.
"""

import json
from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from systematic_investing.data.contracts import ProviderEvidence, ProviderSuccess
from systematic_investing.data.quality import (
    CheckResult,
    CheckSeverity,
    CheckStatus,
    GateAction,
    GateResult,
    GateStatus,
)
from systematic_investing.data.snapshots import SnapshotReader
from systematic_investing.domain.market import (
    AdjustmentMode,
    Availability,
    AvailabilityBasis,
    TradingSession,
)
from systematic_investing.domain.runs import RunPurpose
from systematic_investing.instrument_master.repository import (
    InstrumentMaster,
    default_m0_master,
)
from systematic_investing.research import materializer
from systematic_investing.research.artifacts import (
    ArtifactIntegrityError,
    digest_of_bytes,
    read_json,
)
from systematic_investing.research.materializer import (
    MaterializationError,
    gate_receipt_payload,
    write_gate_receipt,
)

EVALUATED_AT = datetime(2026, 9, 16, 18, 0, tzinfo=UTC)
INTENT_PATH = (
    Path(__file__).resolve().parents[2]
    / "research"
    / "candidates"
    / "m1-etf-absolute-trend-v1.json"
)


def _gate_result() -> GateResult:
    return GateResult(
        gate_name="DATA_QUALITY_GATE",
        gate_version="m0-quality-gate-1",
        purpose=RunPurpose.DECISION,
        status=GateStatus.PASS,
        action=GateAction.PROCEED,
        evaluated_at=EVALUATED_AT,
        checks=(
            CheckResult(
                check_id="SCHEMA_VERSION",
                status=CheckStatus.PASS,
                severity=CheckSeverity.BLOCKING,
                reason_code="APPROVED_PROFILE_GOVERNS",
            ),
        ),
        reason_codes=(),
        input_digests={
            "dataset": "sha256:" + "1" * 64,
            "policy": "sha256:" + "2" * 64,
        },
    )


def _plan() -> materializer.MaterializationPlan:
    intent = materializer.CandidateIntent.from_dict(
        json.loads(INTENT_PATH.read_text(encoding="utf-8"))
    )
    return materializer.validate_materialization_request(
        intent,
        mode="BASIC",
        asset_class="ETF",
        start=date(2015, 1, 5),
        end=date(2022, 12, 30),
    )


def test_basic_mode_refuses_end_past_intent_basic_end() -> None:
    intent = materializer.CandidateIntent.from_dict(
        json.loads(INTENT_PATH.read_text(encoding="utf-8"))
    )

    with pytest.raises(
        MaterializationError, match="BASIC_MODE_REFUSES_POST_BASIC_END"
    ) as captured:
        materializer.validate_materialization_request(
            intent,
            mode="BASIC",
            asset_class="ETF",
            start=date(2015, 1, 5),
            end=date(2023, 1, 3),
        )

    message = str(captured.value)
    assert "2022-12-30" in message
    assert "2023-01-03" in message


def test_basic_mode_refuses_start_after_warmup_start() -> None:
    intent = materializer.CandidateIntent.from_dict(
        json.loads(INTENT_PATH.read_text(encoding="utf-8"))
    )

    with pytest.raises(MaterializationError, match="START_AFTER_WARMUP_START"):
        materializer.validate_materialization_request(
            intent,
            mode="BASIC",
            asset_class="ETF",
            start=date(2015, 1, 6),
            end=date(2022, 12, 30),
        )


def test_basic_mode_refuses_unknown_mode_and_asset_class_mismatch() -> None:
    intent = materializer.CandidateIntent.from_dict(
        json.loads(INTENT_PATH.read_text(encoding="utf-8"))
    )

    with pytest.raises(MaterializationError, match="UNKNOWN_MODE"):
        materializer.validate_materialization_request(
            intent,
            mode="OOS",
            asset_class="ETF",
            start=date(2015, 1, 5),
            end=date(2022, 12, 30),
        )

    with pytest.raises(MaterializationError, match="ASSET_CLASS_MISMATCH"):
        materializer.validate_materialization_request(
            intent,
            mode="BASIC",
            asset_class="STOCK",
            start=date(2015, 1, 5),
            end=date(2022, 12, 30),
        )


def test_gate_receipt_binds_the_snapshot_and_the_gate_decision(tmp_path) -> None:
    result = _gate_result()

    payload = gate_receipt_payload(result, snapshot_id="b" * 64)

    assert payload["receipt_schema_version"] == "research-gate-receipt-1"
    assert payload["snapshot_id"] == "sha256:" + "b" * 64
    assert payload["gate_name"] == "DATA_QUALITY_GATE"
    assert payload["status"] == "PASS"
    assert payload["gate_digest"] == result.content_digest()
    assert payload["input_digests"] == {
        "dataset": "sha256:" + "1" * 64,
        "policy": "sha256:" + "2" * 64,
    }


def test_gate_receipt_is_written_once_and_never_overwritten(tmp_path) -> None:
    result = _gate_result()

    path = write_gate_receipt(tmp_path, result, snapshot_id="b" * 64)

    payload = read_json(path)
    assert payload["snapshot_id"] == "sha256:" + "b" * 64
    assert digest_of_bytes(path.read_bytes()).startswith("sha256:")

    with pytest.raises(ArtifactIntegrityError):
        write_gate_receipt(tmp_path, result, snapshot_id="c" * 64)


def test_instrument_master_preflight_names_every_failed_lookup() -> None:
    checks = materializer._instrument_master_coverage_checks(
        instrument_symbols=("XSHG:510300", "XSHG:518880"),
        session_dates=(date(2015, 1, 5), date(2015, 1, 6)),
        master=InstrumentMaster(),
    )

    assert [check.reason_code for check in checks] == [
        "UNKNOWN_INSTRUMENT_CLASSIFICATION",
        "UNKNOWN_INSTRUMENT_CLASSIFICATION",
    ]
    assert [check.affected_scope for check in checks] == [
        ("XSHG:510300", "2015-01-05"),
        ("XSHG:518880", "2015-01-05"),
    ]
    assert all(check.check_id == "INSTRUMENT_MASTER_AUTHORITY" for check in checks)
    assert all("classification/profile lookup" in (check.observed or "") for check in checks)


def test_materializer_gate_failure_preserves_typed_check_diagnostics() -> None:
    failed = GateResult(
        gate_name="DATA_QUALITY_GATE",
        gate_version="m0-quality-gate-1",
        purpose=RunPurpose.DECISION,
        status=GateStatus.FAIL,
        action=GateAction.BLOCK_NEW_TARGET,
        evaluated_at=EVALUATED_AT,
        checks=(
            CheckResult(
                check_id="INSTRUMENT_MASTER_AUTHORITY",
                status=CheckStatus.FAIL,
                severity=CheckSeverity.BLOCKING,
                reason_code="UNKNOWN_INSTRUMENT_CLASSIFICATION",
                affected_scope=("XSHG:510300", "2015-01-05"),
                observed="classification/profile lookup failed",
                expected="approved Instrument Master classification",
            ),
        ),
        reason_codes=("UNKNOWN_INSTRUMENT_CLASSIFICATION",),
        input_digests={
            "dataset": "sha256:" + "1" * 64,
            "policy": "sha256:" + "2" * 64,
        },
    )

    with pytest.raises(MaterializationError) as captured:
        materializer._raise_quality_gate_failure(failed)

    message = str(captured.value)
    assert "check=INSTRUMENT_MASTER_AUTHORITY" in message
    assert "reason=UNKNOWN_INSTRUMENT_CLASSIFICATION" in message
    assert "instrument_id=XSHG:510300" in message
    assert "session_date=2015-01-05" in message
    assert "lookup=classification/profile" in message


def test_static_preflight_passes_without_creating_output(tmp_path) -> None:
    output = tmp_path / "basic-etf-v1"

    receipt = materializer.preflight_materialization(
        _plan(), output, master=default_m0_master()
    )

    assert receipt["status"] == "PASS"
    assert receipt["preflight_only"] is True
    assert receipt["checked_instrument_count"] == 4
    assert receipt["checked_start"] == "2015-01-05"
    assert receipt["checked_end"] == "2022-12-30"
    assert not output.exists()


def test_static_preflight_rejects_instrument_scope_expansion(tmp_path) -> None:
    plan = _plan()
    expanded = replace(
        plan,
        instrument_symbols=(*plan.instrument_symbols, "XSHG:510050"),
    )

    with pytest.raises(MaterializationError, match="UNDECLARED_INSTRUMENT_SCOPE"):
        materializer.preflight_materialization(
            expanded, tmp_path / "basic-etf-v1", master=default_m0_master()
        )


def test_master_failure_happens_before_provider_construction(
    tmp_path, monkeypatch
) -> None:
    provider_calls = 0

    def forbidden_provider():
        nonlocal provider_calls
        provider_calls += 1
        raise AssertionError("provider must not be constructed before static preflight")

    monkeypatch.setattr(materializer, "default_m0_master", InstrumentMaster)
    monkeypatch.setattr(materializer, "_provider", forbidden_provider)
    output = tmp_path / "basic-etf-v1"

    with pytest.raises(MaterializationError) as captured:
        materializer.materialize_basic_snapshot(_plan(), output)

    message = str(captured.value)
    assert "QUALITY_GATE_FAILED" in message
    for instrument_id in (
        "XSHG:510300",
        "XSHE:159915",
        "XSHG:518880",
        "XSHG:511010",
    ):
        assert instrument_id in message
    assert "session_date=2015-01-05" in message
    assert provider_calls == 0
    assert not output.exists()


def test_preflight_only_cli_never_constructs_provider(
    tmp_path, monkeypatch, capsys
) -> None:
    def forbidden_provider():
        raise AssertionError("--preflight-only must not construct a provider")

    monkeypatch.setattr(materializer, "_provider", forbidden_provider)
    output = tmp_path / "basic-etf-v1"

    exit_code = materializer.main(
        [
            "--mode",
            "BASIC",
            "--asset",
            "ETF",
            "--start",
            "2015-01-05",
            "--end",
            "2022-12-30",
            "--request",
            str(INTENT_PATH),
            "--output",
            str(output),
            "--preflight-only",
        ]
    )

    assert exit_code == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["status"] == "PASS"
    assert receipt["preflight_only"] is True
    assert not output.exists()


class _SpyWriter(materializer.SnapshotWriter):
    """Real writer that records the persist kwargs for wiring assertions."""

    last_persist_kwargs: dict

    def persist(self, dataset, **kwargs):
        type(self).last_persist_kwargs = kwargs
        return super().persist(dataset, **kwargs)


class _StubProvider:
    PROVIDER_NAME = "chstockdata"
    ADAPTER_VERSION = "0.1.0"

    def __init__(self) -> None:
        self.calls: list[str] = []

    def capability_evidence(self):
        return ProviderEvidence(
            evidence_id="stub-evidence",
            provider_name=self.PROVIDER_NAME,
            provider_version="0.3.0",
            adapter_name="stub",
            adapter_version=self.ADAPTER_VERSION,
            capability="all",
            request_digest="0" * 64,
            retrieved_at=datetime(2026, 9, 18, 12, 0, tzinfo=UTC),
            upstream_source=None,
            record_count=0,
            payload_checksum="0" * 64,
        )

    def _success(self, records):
        self.calls.append("call")
        return ProviderSuccess(
            records=records,
            evidence=self.capability_evidence(),
        )

    def fetch_calendar(self, request):
        sessions = tuple(
            TradingSession(
                calendar_id=request.calendar_id,
                session_date=session_date,
                is_open=True,
                note=None,
                snapshot_version="STUB-CAL-1",
            )
            for session_date in (date(2022, 12, 29), date(2022, 12, 30))
        )
        return self._success(sessions)

    def fetch_daily_bars(self, request):
        instrument_id = request.instrument_ids[0]
        bar = materializer.DailyBar(
            schema_version="v1",
            instrument_id=instrument_id,
            session_date=date(2022, 12, 30),
            open=Decimal("4.00"),
            high=Decimal("4.00"),
            low=Decimal("4.00"),
            close=Decimal("4.00"),
            pre_close=Decimal("3.98"),
            volume=Decimal("1000"),
            amount=Decimal("4000"),
            currency="CNY",
            volume_unit="share",
            amount_unit="CNY",
            adjustment_mode=AdjustmentMode.RAW,
            adjustment_factor=None,
            availability=Availability(
                information_available_at=datetime(
                    2022, 12, 30, 15, 5, tzinfo=UTC
                ),
                retrieved_at=datetime(2022, 12, 30, 15, 6, tzinfo=UTC),
                availability_basis=AvailabilityBasis.OBSERVED,
            ),
            provider_evidence_id="stub-bar",
        )
        return self._success((bar,))

    def fetch_tradability(self, request):
        return self._success(())

    def fetch_corporate_actions(self, request):
        return self._success(())


def test_materialization_binds_the_gate_decision_into_the_snapshot_manifest(
    tmp_path, monkeypatch
) -> None:
    gate_result = _gate_result()

    class _StubGate:
        def __init__(self, *, master, policy) -> None:
            pass

        def evaluate(self, *args, **kwargs):
            return gate_result

    monkeypatch.setattr(materializer, "_provider", lambda: _StubProvider())
    monkeypatch.setattr(materializer, "DataQualityGate", _StubGate)
    monkeypatch.setattr(materializer, "SnapshotWriter", _SpyWriter)
    output = tmp_path / "basic-etf-v1"

    receipt = materializer.materialize_basic_snapshot(_plan(), output)

    kwargs = _SpyWriter.last_persist_kwargs
    assert kwargs["quality_report_id"] == gate_result.content_digest()
    assert kwargs["quality_status"] == "PASS"
    assert receipt["quality_status"] == "PASS"

    manifest, _ = SnapshotReader().load(output)
    assert manifest.quality_status == "PASS"
    assert manifest.quality_report_id == gate_result.content_digest()
    assert manifest.snapshot_id == receipt["snapshot_id"]
