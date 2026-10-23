"""Target completeness validation.

A complete M0 target explicitly addresses every held instrument. Omitting a
current holding cannot silently mean HOLD or SELL; M0 has no carry-forward
policy and fails closed with the exact instruments that were missed.
"""

from systematic_investing.domain.identifiers import InstrumentId
from systematic_investing.domain.portfolio import PortfolioError, TheoreticalTargetPortfolio


class TargetNotCompleteError(PortfolioError):
    """Raised when a target does not explicitly address every held instrument."""

    def __init__(self, missing: tuple[InstrumentId, ...]) -> None:
        self.missing = missing
        listed = ", ".join(str(item) for item in missing)
        super().__init__(
            f"target does not address held instruments: {listed}; "
            "absence never implies HOLD or SELL"
        )


def validate_target_completeness(
    target: TheoreticalTargetPortfolio,
    held_instrument_ids: frozenset[InstrumentId],
) -> None:
    """Fail closed unless every held instrument is addressed by the target."""
    addressed = target.addressed_instruments
    missing = tuple(sorted(item for item in held_instrument_ids if item not in addressed))
    if missing:
        raise TargetNotCompleteError(missing)
