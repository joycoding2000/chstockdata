"""Explicit replay profiles for versioned research kernel identities."""

from dataclasses import dataclass
from hashlib import sha256

from systematic_investing.backtest.accounting import AccountingSemantics
from systematic_investing.backtest.engine import IDENTITY_RISK_COMPOSITION_VERSION
from systematic_investing.backtest.execution import ExecutionModel
from systematic_investing.domain.execution import EXECUTION_CONVENTION_VERSION

KERNEL_ENGINE_IDENTITY = "systematic_investing.backtest.engine.DailyBarEngine"
KERNEL_IDENTITY_WIRE_VERSION = "research_kernel_identity_v1"


class KernelReplayError(Exception):
    """Base class for replay-profile resolution failures."""


class UnsupportedKernelReplayError(KernelReplayError):
    """Raised when a frozen identity has no executable replay profile."""


@dataclass(frozen=True)
class KernelReplayProfile:
    """One executable kernel contract and its canonical identity algorithm."""

    profile_id: str
    identity_scheme: str
    accounting_semantics: AccountingSemantics
    engine: str
    risk_composition: str
    execution_semantics: str
    include_accounting_semantics_in_identity: bool

    def validate_executable(self, execution_model: ExecutionModel) -> None:
        if not isinstance(execution_model, ExecutionModel):
            raise UnsupportedKernelReplayError(
                f"{self.profile_id} requires an ExecutionModel"
            )
        if execution_model.version != self.execution_semantics:
            raise UnsupportedKernelReplayError(
                f"{self.profile_id} requires execution semantics "
                f"{self.execution_semantics!r}, got {execution_model.version!r}"
            )
        if not isinstance(self.accounting_semantics, AccountingSemantics):
            raise UnsupportedKernelReplayError(
                f"{self.profile_id} has unsupported accounting semantics "
                f"{self.accounting_semantics!r}"
            )

    def identity_digest(self, execution_model: ExecutionModel) -> str:
        """Derive the profile's exact historical/current identity digest."""
        self.validate_executable(execution_model)
        lines = [
            KERNEL_IDENTITY_WIRE_VERSION,
            f"engine={self.engine}",
            f"risk_composition={self.risk_composition}",
        ]
        if self.include_accounting_semantics_in_identity:
            lines.append(f"accounting_semantics={self.accounting_semantics.value}")
        lines.append(f"execution_model={execution_model.version}")
        return "sha256:" + sha256("\n".join(lines).encode("utf-8")).hexdigest()


current_kernel_replay_profile = KernelReplayProfile(
    profile_id="CURRENT",
    identity_scheme="research-kernel-current-v1",
    accounting_semantics=AccountingSemantics.CURRENT_M0_ACCOUNTING_2,
    engine=KERNEL_ENGINE_IDENTITY,
    risk_composition=IDENTITY_RISK_COMPOSITION_VERSION,
    execution_semantics=EXECUTION_CONVENTION_VERSION,
    include_accounting_semantics_in_identity=True,
)

legacy_kernel_replay_profile = KernelReplayProfile(
    profile_id="LEGACY_M0_ACCOUNTING_1",
    identity_scheme="research-kernel-legacy-v1",
    accounting_semantics=AccountingSemantics.LEGACY_M0_ACCOUNTING_1,
    engine=KERNEL_ENGINE_IDENTITY,
    risk_composition=IDENTITY_RISK_COMPOSITION_VERSION,
    execution_semantics=EXECUTION_CONVENTION_VERSION,
    include_accounting_semantics_in_identity=False,
)

SUPPORTED_KERNEL_REPLAY_PROFILES: tuple[KernelReplayProfile, ...] = (
    current_kernel_replay_profile,
    legacy_kernel_replay_profile,
)


def resolve_kernel_replay_profile(
    frozen_digest: str,
    execution_model: ExecutionModel,
) -> KernelReplayProfile:
    """Resolve a frozen digest by reproducing supported identity algorithms."""
    for profile in SUPPORTED_KERNEL_REPLAY_PROFILES:
        if profile.identity_digest(execution_model) == frozen_digest:
            return profile
    raise UnsupportedKernelReplayError(
        f"no supported executable kernel replay profile matches {frozen_digest!r}"
    )
