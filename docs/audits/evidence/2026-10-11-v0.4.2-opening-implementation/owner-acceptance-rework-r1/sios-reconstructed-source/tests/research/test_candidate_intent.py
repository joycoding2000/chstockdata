"""M1 lifecycle contract tests: CandidateIntent, ResearchRunManifest.

A CandidateIntent is frozen before implementation and must never contain
implementation, code-commit, or snapshot digests; a ResearchRunManifest binds
exactly those run-time identities and fails closed when any required digest is
missing. Mutation of any identity field produces a new run identity; the
output path never does.
"""

from copy import deepcopy

import pytest

from systematic_investing.research.contracts import (
    CandidateIntent,
    InvalidCandidateIntentError,
    InvalidResearchRunManifestError,
    ResearchRunManifest,
)


def _minimal_intent_payload() -> dict:
    return {
        "intent_schema_version": "research-candidate-intent-1",
        "intent_id": "test-etf-absolute-trend-v1",
        "lineage_id": "test-etf-absolute-trend",
        "asset_class": "ETF",
        "sleeve": "CORE",
        "strategy_id": "etf-absolute-trend",
        "decision_frequency": "MONTHLY_LAST_SESSION",
        "economic_rationale": "Trend following avoids sustained drawdowns.",
        "rule_pseudocode": "if close > SMA(N): weight 1.0 else 0.0",
        "parameter_variants": [
            {"variant_id": "sma-2", "parameters": {"sma_sessions": "2"}},
            {"variant_id": "sma-3", "parameters": {"sma_sessions": "3"}},
        ],
        "parameter_priority": ["sma-2", "sma-3"],
        "parameter_selection_rule": "PRIORITY_FIRST_BASIC_PASS",
        "universe_policy": {
            "policy_name": "ETF_FIXED_QUALIFIED_V1",
            "instrument_ids": ["XSHG:510300"],
        },
        "warm_up_start": "2015-01-05",
        "basic_start": "2016-01-04",
        "basic_end": "2022-12-30",
        "oos_start": "2023-01-03",
        "oos_end": "2025-12-31",
        "benchmark": {
            "kind": "SINGLE_ETF_BUY_AND_HOLD",
            "instrument_ids": ["XSHG:510300"],
            "rebalance": "INCEPTION",
        },
        "risk_off_choice": "CASH_0",
        "initial_capital": "100000",
        "cost_convention": {
            "commission_rate": "0.00025",
            "minimum_commission": "5",
            "slippage_rate": "0.0005",
        },
        "metric_convention": {
            "return_basis": "DAILY_CLOSE_TO_CLOSE",
            "annualization_sessions": "252",
        },
        "basic_promotion_rule": {
            "min_nav_observations": "1000",
            "min_excess_total_return_vs_benchmark": "-0.05",
            "max_drawdown_floor": "-0.40",
            "max_turnover": "12",
        },
        "oos_survivor_rule": {
            "min_excess_total_return_vs_benchmark": "-0.05",
            "max_drawdown_floor": "-0.40",
        },
        "known_limitations": ("No dividend-tax modeling is required for ETFs.",),
        "source": "M1 protocol section 7 owner-approved seed candidate",
        "created_at": "2026-09-16",
    }


def test_candidate_intent_accepts_full_precode_contract() -> None:
    payload = _minimal_intent_payload()
    intent = CandidateIntent.from_dict(payload)

    assert intent.lineage_id == "test-etf-absolute-trend"
    assert intent.strategy_id == "etf-absolute-trend"
    assert intent.asset_class.value == "ETF"
    assert intent.sleeve.value == "CORE"
    assert intent.parameter_priority == ("sma-2", "sma-3")
    assert intent.basic_start.isoformat() == "2016-01-04"
    assert intent.benchmark.kind.value == "SINGLE_ETF_BUY_AND_HOLD"
    assert intent.basic_promotion_rule["max_turnover"] == "12"
    assert intent.intent_digest.startswith("sha256:")


def test_candidate_intent_rejects_runtime_digest_fields() -> None:
    for forbidden in ("implementation_digest", "code_commit", "snapshot_digest"):
        payload = _minimal_intent_payload()
        payload[forbidden] = "sha256:" + "0" * 64
        with pytest.raises(InvalidCandidateIntentError):
            CandidateIntent.from_dict(payload)


def test_candidate_intent_rejects_incomplete_priority_list() -> None:
    payload = _minimal_intent_payload()
    payload["parameter_priority"] = ["sma-2"]
    with pytest.raises(InvalidCandidateIntentError):
        CandidateIntent.from_dict(payload)


def test_candidate_intent_rejects_unqualified_etf_universe() -> None:
    payload = _minimal_intent_payload()
    payload["universe_policy"]["instrument_ids"] = ["XSHG:513100"]
    with pytest.raises(InvalidCandidateIntentError):
        CandidateIntent.from_dict(payload)


def test_candidate_intent_rejects_missing_benchmark_and_gates() -> None:
    payload = _minimal_intent_payload()
    del payload["benchmark"]
    with pytest.raises(InvalidCandidateIntentError):
        CandidateIntent.from_dict(payload)

    payload = _minimal_intent_payload()
    del payload["basic_promotion_rule"]
    with pytest.raises(InvalidCandidateIntentError):
        CandidateIntent.from_dict(payload)


def _run_manifest_payload() -> dict:
    intent = CandidateIntent.from_dict(_minimal_intent_payload())
    return {
        "manifest_schema_version": "research-run-manifest-1",
        "lineage_id": intent.lineage_id,
        "intent_digest": intent.intent_digest,
        "strategy_id": intent.strategy_id,
        "strategy_version": "v1",
        "strategy_identity_digest": "sha256:" + "1" * 64,
        "implementation_digest": "sha256:" + "2" * 64,
        "parameters_digest": "sha256:" + "3" * 64,
        "code_commit": "a" * 40,
        "dependency_digest": "stdlib-only-0",
        "split_digest": "sha256:" + "4" * 64,
        "snapshot_digest": "sha256:" + "5" * 64,
        "universe_schedule_digest": "sha256:" + "6" * 64,
        "benchmark_spec_digest": "sha256:" + "7" * 64,
        "cost_spec_digest": "sha256:" + "8" * 64,
        "metric_convention_digest": "sha256:" + "9" * 64,
        "kernel_identity_digest": "sha256:" + "a" * 64,
        "output_scope": "BASIC",
        "random_seed": 0,
    }


def test_research_run_manifest_requires_runtime_digests() -> None:
    payload = _run_manifest_payload()
    manifest = ResearchRunManifest.from_dict(payload)
    assert manifest.identity_digest.startswith("sha256:")

    required = (
        "intent_digest",
        "implementation_digest",
        "parameters_digest",
        "snapshot_digest",
        "universe_schedule_digest",
        "benchmark_spec_digest",
        "cost_spec_digest",
        "metric_convention_digest",
        "kernel_identity_digest",
        "split_digest",
        "code_commit",
        "dependency_digest",
    )
    for missing in required:
        broken = deepcopy(payload)
        del broken[missing]
        with pytest.raises(InvalidResearchRunManifestError):
            ResearchRunManifest.from_dict(broken)


def test_research_run_manifest_identity_mutation_matrix() -> None:
    payload = _run_manifest_payload()
    baseline = ResearchRunManifest.from_dict(payload).identity_digest

    mutations: dict[str, object] = {
        "lineage_id": "other-lineage",
        "intent_digest": "sha256:" + "b" * 64,
        "strategy_id": "other-strategy",
        "strategy_version": "v2",
        "strategy_identity_digest": "sha256:" + "c" * 64,
        "implementation_digest": "sha256:" + "d" * 64,
        "parameters_digest": "sha256:" + "e" * 64,
        "code_commit": "b" * 40,
        "dependency_digest": "stdlib-only-1",
        "split_digest": "sha256:" + "f" * 64,
        "snapshot_digest": "sha256:" + "0" * 64,
        "universe_schedule_digest": "sha256:" + "1" * 64,
        "benchmark_spec_digest": "sha256:" + "2" * 64,
        "cost_spec_digest": "sha256:" + "3" * 64,
        "metric_convention_digest": "sha256:" + "4" * 64,
        "kernel_identity_digest": "sha256:" + "5" * 64,
        "output_scope": "OOS",
        "random_seed": 7,
    }
    for field, value in mutations.items():
        broken = deepcopy(payload)
        broken[field] = value
        mutated = ResearchRunManifest.from_dict(broken)
        assert mutated.identity_digest != baseline, field


def test_research_run_manifest_identity_ignores_output_path() -> None:
    payload = _run_manifest_payload()
    payload["output_path"] = "var/research/experiments/other"
    manifest = ResearchRunManifest.from_dict(payload)
    baseline = ResearchRunManifest.from_dict(_run_manifest_payload())
    assert manifest.identity_digest == baseline.identity_digest


def test_research_run_manifest_rejects_bad_digest_shape() -> None:
    payload = _run_manifest_payload()
    payload["snapshot_digest"] = "not-a-digest"
    with pytest.raises(InvalidResearchRunManifestError):
        ResearchRunManifest.from_dict(payload)
