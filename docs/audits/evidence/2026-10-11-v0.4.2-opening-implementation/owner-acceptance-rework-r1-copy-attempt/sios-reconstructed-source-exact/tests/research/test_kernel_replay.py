"""Synthetic compatibility tests for frozen kernel replay profiles."""

from decimal import Decimal

import pytest

from systematic_investing.backtest.execution import ExecutionModel
from systematic_investing.research.kernel_replay import (
    UnsupportedKernelReplayError,
    current_kernel_replay_profile,
    legacy_kernel_replay_profile,
    resolve_kernel_replay_profile,
)
from systematic_investing.research.oos import OosWiring
from systematic_investing.research.runner import BasicWiring, kernel_identity_digest


@pytest.fixture
def model() -> ExecutionModel:
    return ExecutionModel(
        slippage_rate_buy=Decimal("0.0005"),
        slippage_rate_sell=Decimal("0.0005"),
    )


def test_legacy_profile_reproduces_the_frozen_basic_digest(
    model: ExecutionModel,
) -> None:
    assert legacy_kernel_replay_profile.identity_digest(model) == (
        "sha256:30b502997484a2ec42b3cda41152efd871ad1b722fb9151cfcc7c88f327cf60e"
    )


def test_current_profile_preserves_the_current_digest(model: ExecutionModel) -> None:
    assert current_kernel_replay_profile.identity_digest(model) == (
        "sha256:e4038c1ba724231d32183053a4a4d276f0ce710bf4d2b8747f222901f1f9b309"
    )


def test_unknown_digest_has_no_replay_profile(model: ExecutionModel) -> None:
    with pytest.raises(UnsupportedKernelReplayError):
        resolve_kernel_replay_profile("sha256:" + "0" * 64, model)


def test_research_wiring_defaults_to_the_current_replay_profile() -> None:
    assert BasicWiring.__dataclass_fields__["kernel_profile"].default is (
        current_kernel_replay_profile
    )
    assert OosWiring.__dataclass_fields__["kernel_profile"].default is (
        current_kernel_replay_profile
    )


def test_runner_identity_wrapper_accepts_a_legacy_profile(
    model: ExecutionModel,
) -> None:
    assert kernel_identity_digest(model, profile=legacy_kernel_replay_profile) == (
        "sha256:30b502997484a2ec42b3cda41152efd871ad1b722fb9151cfcc7c88f327cf60e"
    )
