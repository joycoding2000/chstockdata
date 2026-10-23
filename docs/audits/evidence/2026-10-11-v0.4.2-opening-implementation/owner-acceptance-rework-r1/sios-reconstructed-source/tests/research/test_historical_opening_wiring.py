"""Explicit R2.1 runner/OOS mode binds real engine inputs and run identity."""

import json
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path
import pytest
from test_research_reproducibility import (
    _dataset,
    _basic_sessions,
    _basic_intent,
    _receipt,
    _run_variant,
)
from test_oos_exposure_gate import _intent as oos_intent, _oos_dataset
from systematic_investing.domain.historical_opening import (
    HistoricalOpeningEvidence,
    ExecutionEligibilityMode,
    OPENING_POLICY,
    OPENING_CLOCK_ID,
    opening_evidence_digest,
)
from systematic_investing.instrument_master.repository import default_m0_master
from systematic_investing.research import runner, oos
from systematic_investing.research.universe import UniverseView
from systematic_investing.data.snapshots import SnapshotWriter, SnapshotReader
from systematic_investing.research.intake import validate_basic_snapshot

MODE = ExecutionEligibilityMode.HISTORICAL_OPENING_R21


def fact():
    p = (
        Path(__file__).resolve().parents[1]
        / "fixtures/chstockdata/historical_opening/510300-2026-09-11.json"
    )
    return HistoricalOpeningEvidence.from_payload(json.loads(p.read_text(encoding="utf-8"))["data"])


def test_basic_explicit_clock_engine_path_and_manifest_identity(monkeypatch):
    dataset = replace(_dataset(_basic_sessions()), historical_opening_evidence=(fact(),))
    receipt = replace(
        _receipt(dataset),
        dataset_digest=dataset.content_digest(),
        execution_policy=OPENING_POLICY,
        execution_clock=OPENING_CLOCK_ID,
        execution_evidence_digest=opening_evidence_digest(dataset.historical_opening_evidence),
    )
    monkeypatch.setattr(
        runner, "resolve_code_commit", lambda: "84fd54fae0740bc06b1d250afa4578be29556956"
    )
    legacy = runner.build_basic_wiring(
        dataset, _basic_intent(), receipt, master=default_m0_master()
    )
    new = runner.build_basic_wiring(
        dataset,
        _basic_intent(),
        receipt,
        master=default_m0_master(),
        execution_eligibility_mode=MODE,
    )
    assert legacy.clock.execution_at(date(2026, 9, 11)).hour == 9
    assert new.clock.execution_at(date(2026, 9, 11)) == datetime(2026, 9, 11, 1, 30, tzinfo=UTC)
    captured = []
    real = runner.DailyBarEngine

    def observe(**kw):
        captured.append(kw)
        return real(**kw)

    monkeypatch.setattr(runner, "DailyBarEngine", observe)
    a = _run_variant(legacy, _basic_intent())
    b = _run_variant(new, _basic_intent())
    assert captured[-1]["execution_eligibility_mode"] is MODE
    assert captured[-1]["historical_opening_evidence"] == dataset.historical_opening_evidence
    assert (
        a.manifest_payload["kernel_identity_digest"] != b.manifest_payload["kernel_identity_digest"]
    )
    assert a.manifest_payload != b.manifest_payload


def test_basic_new_mode_refuses_legacy_receipt(monkeypatch):
    dataset = replace(_dataset(_basic_sessions()), historical_opening_evidence=(fact(),))
    with pytest.raises(runner.RunWiringError):
        runner.build_basic_wiring(
            dataset,
            _basic_intent(),
            _receipt(dataset),
            master=default_m0_master(),
            execution_eligibility_mode=MODE,
        )


def test_oos_explicit_clock_actual_engine_path_and_identity(tmp_path, monkeypatch):
    intent = oos_intent()
    dataset = replace(_oos_dataset(), historical_opening_evidence=(fact(),))
    now = datetime(2026, 10, 12, tzinfo=UTC)
    directory = tmp_path / "oos"
    manifest = SnapshotWriter("recorded", "0.4.2", "r21").persist(
        dataset,
        snapshot_dir=directory,
        created_at=now,
        knowledge_cutoff=now,
        retrieved_at=now,
        execution_eligibility_mode=MODE,
    )
    receipt = oos.validate_oos_snapshot(manifest, dataset, intent)
    monkeypatch.setattr(
        oos, "resolve_code_commit", lambda: "84fd54fae0740bc06b1d250afa4578be29556956"
    )
    wiring = oos.build_oos_wiring(
        dataset, intent, receipt, master=default_m0_master(), execution_eligibility_mode=MODE
    )
    captured = []
    real = oos.DailyBarEngine

    def observe(**kw):
        captured.append(kw)
        return real(**kw)

    monkeypatch.setattr(oos, "DailyBarEngine", observe)
    oos.oos_benchmark_total_return(wiring)
    assert captured[-1]["clock"].execution_at(date(2026, 9, 11)) == datetime(
        2026, 9, 11, 1, 30, tzinfo=UTC
    )
    assert captured[-1]["execution_eligibility_mode"] is MODE
    assert captured[-1]["historical_opening_evidence"] == dataset.historical_opening_evidence
    assert runner.kernel_identity_digest(
        wiring.execution_model, execution_eligibility_mode=MODE
    ) != runner.kernel_identity_digest(wiring.execution_model)


def test_new_freeze_mode_is_explicit_and_old_digest_cannot_be_reinterpreted():
    from test_oos_verifier import _current_freeze_payload, _intent

    frozen = _current_freeze_payload()
    intent = _intent()
    new_digest = oos.oos_kernel_identity_digest(intent, execution_eligibility_mode=MODE)
    assert new_digest != oos.oos_kernel_identity_digest(intent)
    with pytest.raises(oos.OosFreezeError):
        oos.resolve_freeze_kernel_replay_profile(frozen, intent, execution_eligibility_mode=MODE)
    changed = {**frozen, "kernel_identity_digest": new_digest}
    assert (
        oos.resolve_freeze_kernel_replay_profile(
            changed, intent, execution_eligibility_mode=MODE
        ).profile_id
        == "CURRENT"
    )
    with pytest.raises(oos.OosFreezeError):
        oos.resolve_freeze_kernel_replay_profile(changed, intent)


def test_public_cli_mode_is_explicit_and_legacy_default():
    from systematic_investing.research.cli import build_parser

    parser = build_parser()
    for args in (
        ("basic-backtest", "--intent", "x", "--snapshot", "x", "--root", "x"),
        ("oos-freeze", "--candidate-id", "x", "--root", "x"),
        ("oos-run", "--freeze-id", "x", "--snapshot", "x", "--root", "x"),
    ):
        assert parser.parse_args(args).execution_eligibility_mode == "LEGACY"
        assert (
            parser.parse_args(
                (*args, "--execution-eligibility-mode", MODE.value)
            ).execution_eligibility_mode
            == MODE.value
        )


def test_execution_fact_payload_changes_run_identity_through_real_snapshot(tmp_path, monkeypatch):
    import hashlib
    from datetime import timedelta
    from test_research_reproducibility import _run_variant

    monkeypatch.setattr(runner, "resolve_code_commit", lambda: "test-source-identity")
    base = _dataset(_basic_sessions())
    # Keep the strategy fixture's information at 15:05 Shanghai in the new mode.
    base = replace(
        base,
        daily_bars=tuple(
            replace(
                bar,
                availability=replace(
                    bar.availability,
                    information_available_at=bar.availability.information_available_at
                    - timedelta(hours=8),
                    retrieved_at=bar.availability.retrieved_at - timedelta(hours=8),
                ),
            )
            for bar in base.daily_bars
        ),
    )
    data = fact().payload
    outputs = []
    for index, retrieval in enumerate(("2026-10-12T00:00:00+00:00", "2026-10-12T01:00:00+00:00")):
        data["retrieved_at"] = retrieval
        data.pop("evidence_hash", None)
        data["evidence_hash"] = hashlib.sha256(
            json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
                "utf-8"
            )
        ).hexdigest()
        dataset = replace(
            base, historical_opening_evidence=(HistoricalOpeningEvidence.from_payload(data),)
        )
        now = datetime(2026, 10, 12, 2, tzinfo=UTC)
        manifest = SnapshotWriter("recorded", "0.4.2", "r21").persist(
            dataset,
            snapshot_dir=tmp_path / str(index),
            created_at=now,
            knowledge_cutoff=now,
            retrieved_at=now,
            execution_eligibility_mode=MODE,
        )
        receipt = validate_basic_snapshot(manifest, dataset, _basic_intent())
        wiring = runner.build_basic_wiring(
            dataset,
            _basic_intent(),
            receipt,
            master=default_m0_master(),
            execution_eligibility_mode=MODE,
        )
        outputs.append(_run_variant(wiring, _basic_intent()))
    assert (
        outputs[0].manifest_payload["kernel_identity_digest"]
        == outputs[1].manifest_payload["kernel_identity_digest"]
    )
    assert (
        outputs[0].manifest_payload["snapshot_digest"]
        != outputs[1].manifest_payload["snapshot_digest"]
    )
    from systematic_investing.research.contracts import ResearchRunManifest

    assert (
        ResearchRunManifest.from_dict(dict(outputs[0].manifest_payload)).identity_digest
        != ResearchRunManifest.from_dict(dict(outputs[1].manifest_payload)).identity_digest
    )


def test_public_oos_run_variant_reaches_new_engine(tmp_path, monkeypatch):
    from datetime import timedelta

    intent = oos_intent()
    base = _oos_dataset()
    data = replace(
        base,
        daily_bars=tuple(
            replace(
                bar,
                availability=replace(
                    bar.availability,
                    information_available_at=bar.availability.information_available_at
                    - timedelta(hours=8),
                    retrieved_at=bar.availability.retrieved_at - timedelta(hours=8),
                ),
            )
            for bar in base.daily_bars
        ),
        historical_opening_evidence=(fact(),),
    )
    now = datetime(2026, 10, 12, tzinfo=UTC)
    manifest = SnapshotWriter("recorded", "0.4.2", "r21").persist(
        data,
        snapshot_dir=tmp_path / "oos",
        created_at=now,
        knowledge_cutoff=now,
        retrieved_at=now,
        execution_eligibility_mode=MODE,
    )
    receipt = oos.validate_oos_snapshot(manifest, data, intent)
    monkeypatch.setattr(oos, "resolve_code_commit", lambda: "test-source-identity")
    wiring = oos.build_oos_wiring(
        data, intent, receipt, master=default_m0_master(), execution_eligibility_mode=MODE
    )
    captured = []
    real = oos.DailyBarEngine

    def observe(**kwargs):
        captured.append(kwargs)
        return real(**kwargs)

    monkeypatch.setattr(oos, "DailyBarEngine", observe)
    variant = intent.parameter_priority[0]
    from decimal import Decimal

    outcome = oos.run_oos_variant(
        wiring, intent, variant, intent.variant_parameters[variant], Decimal("0")
    )
    assert captured[0]["execution_eligibility_mode"] is MODE
    assert captured[0]["historical_opening_evidence"] == data.historical_opening_evidence
    assert outcome.manifest_payload["kernel_identity_digest"] == oos.oos_kernel_identity_digest(
        intent, execution_eligibility_mode=MODE
    )
