"""Freeze artifact identity, exposure classification, and OOS gate tests.

The freeze is the two-phase identity boundary: it binds the candidate
intent, the selected implementation/parameters, the requested OOS scope,
and the universe/benchmark/cost/kernel identities — and deliberately has no
OOS snapshot digest, because that digest cannot exist before the owner
materializes the controlled OOS snapshot. A verifier accepts only a
self-digest-consistent freeze whose bindings match the frozen intent, so
any mutation or scope drift fails closed. Exposure itself is classified:
without a verified freeze, OOS-window access can only ever be labeled
``HISTORICAL_VALIDATION``.
"""

from datetime import date
from decimal import Decimal

import pytest
from test_candidate_intent import _minimal_intent_payload

from systematic_investing.research.contracts import (
    CandidateIntent,
    ResearchRunManifest,
    canonical_payload_digest,
)
from systematic_investing.research.kernel_replay import legacy_kernel_replay_profile
from systematic_investing.research.oos import (
    EXPOSURE_CONTROLLED_OOS,
    EXPOSURE_HISTORICAL_VALIDATION,
    OOS_VERDICT_REJECTED_OOS,
    OOS_VERDICT_SURVIVOR,
    REASON_FREEZE_DIGEST_MISMATCH,
    REASON_FREEZE_FORBIDDEN_FIELD,
    REASON_FREEZE_ID_MISMATCH,
    REASON_FREEZE_IMPLEMENTATION_MISMATCH,
    REASON_FREEZE_INTENT_MISMATCH,
    REASON_FREEZE_KERNEL_MISMATCH,
    REASON_FREEZE_SCOPE_MISMATCH,
    REASON_OOS_SCOPE_OVERLAPS_BASIC,
    REASON_OOS_SURVIVOR_RULE_INVALID,
    OosError,
    build_freeze_payload,
    build_oos_run_manifest,
    classify_exposure,
    enforce_freeze_strategy_identity,
    evaluate_oos_gate,
    oos_kernel_identity_digest,
    resolve_freeze_kernel_replay_profile,
    validate_oos_scope,
    verify_freeze_against_intent,
    verify_freeze_payload,
)
from systematic_investing.research.runner import build_canonical_strategy

_FAKE_IMPLEMENTATION_DIGEST = "sha256:" + "a" * 64
_FAKE_KERNEL_DIGEST = "sha256:" + "b" * 64
_FAKE_BASIC_SNAPSHOT_DIGEST = "sha256:" + "c" * 64
_FAKE_SELECTION_DIGEST = "sha256:" + "d" * 64
_FAKE_PARAMETERS_DIGEST = "sha256:" + "e" * 64
_FAKE_UNIVERSE_SCHEDULE_DIGEST = "sha256:" + "f" * 64


def _intent_payload() -> dict:
    payload = _minimal_intent_payload()
    payload["oos_start"] = "2023-01-03"
    payload["oos_end"] = "2023-03-31"
    return payload


def _intent() -> CandidateIntent:
    return CandidateIntent.from_dict(_intent_payload())


def _freeze_payload(intent: CandidateIntent) -> dict:
    return build_freeze_payload(
        intent,
        intent_payload=_intent_payload(),
        selected_variant_id="sma-2",
        strategy_version="v1",
        implementation_digest=_FAKE_IMPLEMENTATION_DIGEST,
        parameters_digest=_FAKE_PARAMETERS_DIGEST,
        kernel_identity_digest=_FAKE_KERNEL_DIGEST,
        basic_selection_digest=_FAKE_SELECTION_DIGEST,
        basic_snapshot_digest=_FAKE_BASIC_SNAPSHOT_DIGEST,
    )


# --- exposure classification -------------------------------------------------


def test_pre_freeze_oos_access_is_historical_validation() -> None:
    """OOS-window exposure without a verified freeze can never claim
    controlled OOS; the classification is one-way."""
    assert classify_exposure(freeze_verified=False) == EXPOSURE_HISTORICAL_VALIDATION


def test_verified_freeze_classifies_controlled_oos() -> None:
    assert classify_exposure(freeze_verified=True) == EXPOSURE_CONTROLLED_OOS


# --- freeze identity ---------------------------------------------------------


def test_freeze_binds_intent_implementation_parameters_scope_and_specs() -> None:
    intent = _intent()
    payload = _freeze_payload(intent)

    assert payload["freeze_schema_version"] == "research-oos-freeze-1"
    assert payload["lineage_id"] == intent.lineage_id
    assert payload["intent_digest"] == intent.intent_digest
    assert payload["selected_variant_id"] == "sma-2"
    assert payload["implementation_digest"] == _FAKE_IMPLEMENTATION_DIGEST
    assert payload["parameters_digest"] == _FAKE_PARAMETERS_DIGEST
    assert payload["requested_oos_start"] == "2023-01-03"
    assert payload["requested_oos_end"] == "2023-03-31"
    assert payload["universe_policy_digest"] == intent.universe_policy.digest()
    assert payload["benchmark_digest"] == intent.benchmark.digest()
    assert payload["split_digest"].startswith("sha256:")
    assert payload["kernel_identity_digest"] == _FAKE_KERNEL_DIGEST
    assert payload["basic_selection_digest"] == _FAKE_SELECTION_DIGEST
    assert payload["freeze_id"].startswith("freeze-")
    assert payload["freeze_digest"].startswith("sha256:")


def test_freeze_carries_no_oos_snapshot_digest() -> None:
    """The OOS snapshot digest cannot exist before materialization; a freeze
    payload that claims one is rejected by the verifier."""
    payload = _freeze_payload(_intent())
    assert "oos_snapshot_digest" not in payload
    assert "snapshot_digest" not in payload

    forged = dict(payload)
    forged["oos_snapshot_digest"] = "sha256:" + "0" * 64
    with pytest.raises(OosError) as error:
        verify_freeze_payload(forged)
    assert REASON_FREEZE_FORBIDDEN_FIELD in str(error.value)


def test_verifier_accepts_well_formed_freeze() -> None:
    payload = verify_freeze_payload(_freeze_payload(_intent()))
    assert payload["selected_variant_id"] == "sma-2"


def test_verifier_rejects_mutated_freeze() -> None:
    payload = _freeze_payload(_intent())
    mutated = dict(payload)
    mutated["requested_oos_end"] = "2023-12-31"
    with pytest.raises(OosError) as error:
        verify_freeze_payload(mutated)
    assert REASON_FREEZE_DIGEST_MISMATCH in str(error.value)


def test_verifier_rejects_wrong_freeze_id() -> None:
    """A re-signed freeze whose freeze_id disagrees with the content-derived
    id is rejected."""
    payload = _freeze_payload(_intent())
    mutated = dict(payload)
    mutated["freeze_id"] = "freeze-" + "0" * 16
    del mutated["freeze_digest"]
    mutated["freeze_digest"] = canonical_payload_digest(mutated)
    with pytest.raises(OosError) as error:
        verify_freeze_payload(mutated)
    assert REASON_FREEZE_ID_MISMATCH in str(error.value)


def test_verifier_rejects_intent_digest_mismatch() -> None:
    """A fully re-signed freeze cannot disguise an intent swap: the embedded
    intent payload no longer hashes to the recorded intent digest."""
    payload = _freeze_payload(_intent())
    mutated = dict(payload)
    mutated["intent_digest"] = "sha256:" + "1" * 64
    body = {key: value for key, value in mutated.items() if key != "freeze_digest"}
    body["freeze_id"] = (
        "freeze-"
        + canonical_payload_digest(
            {key: value for key, value in body.items() if key != "freeze_id"}
        ).removeprefix("sha256:")[:16]
    )
    resigned = dict(body)
    resigned["freeze_digest"] = canonical_payload_digest(resigned)
    with pytest.raises(OosError) as error:
        verify_freeze_payload(resigned)
    assert REASON_FREEZE_INTENT_MISMATCH in str(error.value)


def test_freeze_bindings_must_match_the_intent() -> None:
    intent = _intent()
    payload = _freeze_payload(intent)
    verify_freeze_against_intent(payload, intent)

    scope_drift = dict(payload)
    scope_drift["requested_oos_end"] = "2023-06-30"
    with pytest.raises(OosError) as error:
        verify_freeze_against_intent(scope_drift, intent)
    assert REASON_FREEZE_SCOPE_MISMATCH in str(error.value)


# --- freeze-bound strategy identity enforcement -------------------------------


def _current_freeze_payload() -> dict:
    """A freeze whose bound implementation/version/parameters/kernel match the
    code actually running in this test process."""
    intent = _intent()
    strategy = build_canonical_strategy(intent, {"sma_sessions": "2"}, ())
    identity = strategy.identity
    return build_freeze_payload(
        intent,
        intent_payload=_intent_payload(),
        selected_variant_id="sma-2",
        strategy_version=identity.strategy_version,
        implementation_digest=identity.implementation_digest,
        parameters_digest=identity.parameters_digest,
        kernel_identity_digest=oos_kernel_identity_digest(intent),
        basic_selection_digest=_FAKE_SELECTION_DIGEST,
        basic_snapshot_digest=_FAKE_BASIC_SNAPSHOT_DIGEST,
    )


def _resign_freeze(payload: dict) -> dict:
    """Recompute freeze_id/freeze_digest over a mutated body, exactly as
    build_freeze_payload derives them; the verifier accepts the result by
    design, so only the oos-run identity cross-check can catch it."""
    body = {key: value for key, value in payload.items() if key != "freeze_digest"}
    body["freeze_id"] = (
        "freeze-"
        + canonical_payload_digest(
            {key: value for key, value in body.items() if key != "freeze_id"}
        ).removeprefix("sha256:")[:16]
    )
    resigned = dict(body)
    resigned["freeze_digest"] = canonical_payload_digest(resigned)
    return resigned


def test_freeze_identity_enforcement_accepts_the_running_code() -> None:
    payload = _current_freeze_payload()
    verify_freeze_payload(payload)
    assert enforce_freeze_strategy_identity(payload, _intent()) == "sma-2"


def test_supported_legacy_freeze_resolves_to_the_historical_profile() -> None:
    payload = _resign_freeze(
        {
            **_current_freeze_payload(),
            "kernel_identity_digest": oos_kernel_identity_digest(
                _intent(), profile=legacy_kernel_replay_profile
            ),
        }
    )

    assert (
        resolve_freeze_kernel_replay_profile(payload, _intent())
        is legacy_kernel_replay_profile
    )


def test_freeze_identity_enforcement_refuses_implementation_drift() -> None:
    """A self-consistent, re-signed freeze binding a different implementation
    digest is refused: code edited after the freeze can never run over OOS."""
    payload = _resign_freeze(
        {**_current_freeze_payload(),
         "implementation_digest": "sha256:" + "7" * 64}
    )
    verify_freeze_payload(payload)
    with pytest.raises(OosError) as error:
        enforce_freeze_strategy_identity(payload, _intent())
    assert REASON_FREEZE_IMPLEMENTATION_MISMATCH in str(error.value)


def test_freeze_identity_enforcement_refuses_kernel_drift() -> None:
    payload = _resign_freeze(
        {**_current_freeze_payload(),
         "kernel_identity_digest": "sha256:" + "8" * 64}
    )
    verify_freeze_payload(payload)
    with pytest.raises(OosError) as error:
        enforce_freeze_strategy_identity(payload, _intent())
    assert REASON_FREEZE_KERNEL_MISMATCH in str(error.value)


def test_freeze_identity_enforcement_refuses_unknown_variant() -> None:
    payload = _current_freeze_payload()
    payload["selected_variant_id"] = "sma-999"
    with pytest.raises(OosError) as error:
        enforce_freeze_strategy_identity(payload, _intent())
    assert "OOS_FREEZE_BINDING_MISMATCH" in str(error.value)


# --- scope validation --------------------------------------------------------


def test_oos_scope_overlapping_basic_window_fails_closed() -> None:
    intent = _intent()
    with pytest.raises(OosError) as error:
        validate_oos_scope(intent, start=intent.basic_end, end=intent.oos_end)
    assert REASON_OOS_SCOPE_OVERLAPS_BASIC in str(error.value)

    with pytest.raises(OosError) as error:
        validate_oos_scope(intent, start=date(2022, 6, 1), end=date(2022, 8, 31))
    assert REASON_OOS_SCOPE_OVERLAPS_BASIC in str(error.value)


def test_oos_scope_outside_the_declared_window_fails_closed() -> None:
    intent = _intent()
    with pytest.raises(OosError):
        validate_oos_scope(intent, start=intent.oos_start, end=date(2023, 12, 31))
    with pytest.raises(OosError):
        validate_oos_scope(intent, start=date(2023, 1, 2), end=intent.oos_end)


def test_exact_declared_oos_scope_is_accepted() -> None:
    intent = _intent()
    validate_oos_scope(intent, start=intent.oos_start, end=intent.oos_end)


# --- OOS survivor gate -------------------------------------------------------


def _metrics(total_return: str, max_drawdown: str) -> dict[str, object]:
    return {
        "total_return": Decimal(total_return),
        "max_drawdown": Decimal(max_drawdown),
        "observation_count": 60,
    }


def test_oos_gate_survivor_requires_every_rule_criterion() -> None:
    intent = _intent()
    verdicts, status = evaluate_oos_gate(
        intent.oos_survivor_rule,
        _metrics("0.12", "-0.15"),
        benchmark_total_return=Decimal("0.05"),
    )
    assert status == OOS_VERDICT_SURVIVOR
    assert all(verdict["verdict"] == "PASS" for verdict in verdicts)


def test_oos_gate_rejects_below_floor_drawdown() -> None:
    rule = _intent().oos_survivor_rule
    _verdicts, status = evaluate_oos_gate(
        rule, _metrics("0.12", "-0.50"), benchmark_total_return=Decimal("0.05")
    )
    assert status == OOS_VERDICT_REJECTED_OOS


def test_oos_gate_rejects_excess_below_threshold() -> None:
    rule = _intent().oos_survivor_rule
    _verdicts, status = evaluate_oos_gate(
        rule, _metrics("-0.01", "-0.15"), benchmark_total_return=Decimal("0.05")
    )
    assert status == OOS_VERDICT_REJECTED_OOS


def test_oos_gate_refuses_unrecognized_criterion() -> None:
    """Evaluation must fail closed instead of silently ignoring an
    unrecognized survivor-rule criterion."""
    with pytest.raises(OosError) as error:
        evaluate_oos_gate(
            {"unknown_criterion": "1"},
            _metrics("0.12", "-0.15"),
            benchmark_total_return=Decimal("0.05"),
        )
    assert REASON_OOS_SURVIVOR_RULE_INVALID in str(error.value)


# --- OOS run manifest binding ------------------------------------------------


def test_oos_run_manifest_binds_actual_digests_with_oos_scope() -> None:
    """The OOS run manifest is built only after materialization and binds the
    ACTUAL snapshot and universe schedule digests, never the freeze's
    expectations."""
    intent = _intent()
    manifest = build_oos_run_manifest(
        intent,
        selected_variant_id="sma-2",
        strategy_version="v1",
        strategy_identity_digest="sha256:" + "9" * 64,
        implementation_digest=_FAKE_IMPLEMENTATION_DIGEST,
        parameters_digest=_FAKE_PARAMETERS_DIGEST,
        actual_snapshot_digest=_FAKE_BASIC_SNAPSHOT_DIGEST,
        actual_universe_schedule_digest=_FAKE_UNIVERSE_SCHEDULE_DIGEST,
        kernel_identity_digest=_FAKE_KERNEL_DIGEST,
        code_commit="deadbeef",
    )

    assert isinstance(manifest, ResearchRunManifest)
    assert manifest.output_scope == "OOS"
    assert manifest.snapshot_digest == _FAKE_BASIC_SNAPSHOT_DIGEST
    assert manifest.universe_schedule_digest == _FAKE_UNIVERSE_SCHEDULE_DIGEST
    assert manifest.intent_digest == intent.intent_digest
    assert manifest.split_digest.startswith("sha256:")
    assert manifest.identity_digest.startswith("sha256:")
