"""Target portfolio: contributions and the theoretical aggregate.

A ``TargetContribution`` binds one strategy's proposed weight for one
instrument to an explicit sleeve; sleeves are never inferred from strategy
names or instrument types. The ``TheoreticalTargetPortfolio`` aggregate
exposes per-instrument weights, explicit sleeve aggregates, and cash that
makes the theoretical weights sum to one. Zero is an addressed exit target;
absence means the instrument was not addressed at all.
"""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256

from systematic_investing.domain.identifiers import InstrumentId, SleeveId, require_session_date
from systematic_investing.domain.money import Money


class PortfolioError(Exception):
    """Base class for target-portfolio contract errors."""


class InvalidTargetError(PortfolioError):
    """Raised when a target contribution or aggregate violates its contract."""


# Declared, versioned M0 tolerance for theoretical-weight arithmetic; exact
# Decimal equality is still required wherever arithmetic is exact.
WEIGHT_SUM_TOLERANCE: Decimal = Decimal("0.000001")

class SizingPriceBasis(StrEnum):
    """Price basis used to size target amounts/quantities. M0 fixes the
    finalized T close; realized fills use the separate execution model."""

    T_CLOSE = "T_CLOSE"


def _require_text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise InvalidTargetError(f"{field_name} must be a non-empty string")
    return value


def _require_aware_datetime(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise InvalidTargetError(
            f"{field_name} must be a timezone-aware datetime, got {value!r}"
        )
    return value


@dataclass(frozen=True)
class TargetContribution:
    """One strategy's theoretical weight proposal for one instrument."""

    instrument_id: InstrumentId
    sleeve: SleeveId
    strategy_id: str
    strategy_version: str
    target_weight: Decimal
    evidence_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence_ids", tuple(self.evidence_ids))
        if not isinstance(self.instrument_id, InstrumentId):
            raise InvalidTargetError("instrument_id must be an InstrumentId")
        if not isinstance(self.sleeve, SleeveId):
            raise InvalidTargetError(f"sleeve must be a SleeveId, got {self.sleeve!r}")
        _require_text(self.strategy_id, "strategy_id")
        _require_text(self.strategy_version, "strategy_version")
        if not isinstance(self.target_weight, Decimal) or not self.target_weight.is_finite():
            raise InvalidTargetError(
                f"target_weight must be a finite Decimal, got {self.target_weight!r}"
            )
        if self.target_weight < 0:
            raise InvalidTargetError(
                "target_weight must be non-negative; M0 targets are long-only"
            )
        if not all(isinstance(item, str) and item for item in self.evidence_ids):
            raise InvalidTargetError("evidence_ids must be non-empty strings")


@dataclass(frozen=True)
class TheoreticalTargetPortfolio:
    """Immutable theoretical target for one future trade date.

    Corrections never rewrite this record: ``supersede`` creates a new
    revision with reason and audit identity. The content digest is a
    deterministic function of the declared content, so identical inputs and
    any input ordering produce identical identity."""

    target_id: str
    revision: int
    decision_for_trade_date: date
    generated_at: datetime
    information_cutoff: datetime
    valuation_equity: Money
    contributions: tuple[TargetContribution, ...]
    supersedes_revision: int | None = None
    supersession_reason: str | None = None
    superseded_by: str | None = None

    def __post_init__(self) -> None:
        _require_text(self.target_id, "target_id")
        if (
            not isinstance(self.revision, int)
            or isinstance(self.revision, bool)
            or self.revision < 1
        ):
            raise InvalidTargetError("revision must be a positive integer")
        require_session_date(self.decision_for_trade_date)
        _require_aware_datetime(self.generated_at, "generated_at")
        _require_aware_datetime(self.information_cutoff, "information_cutoff")
        if self.information_cutoff > self.generated_at:
            raise InvalidTargetError("information_cutoff must not be after generated_at")
        if not isinstance(self.valuation_equity, Money):
            raise InvalidTargetError("valuation_equity must be Money")
        if not isinstance(self.contributions, tuple) or not all(
            isinstance(item, TargetContribution) for item in self.contributions
        ):
            raise InvalidTargetError("contributions must be a tuple of TargetContribution")
        if self.supersedes_revision is not None or self.supersession_reason is not None:
            _require_text(self.supersession_reason or "", "supersession_reason")
        if self.superseded_by is not None:
            _require_text(self.superseded_by, "superseded_by")
        self._check_sleeve_consistency()
        total = self._instrument_weight_total()
        if total > Decimal("1") + WEIGHT_SUM_TOLERANCE:
            raise InvalidTargetError(
                f"total theoretical exposure above 100% is rejected: instruments sum "
                f"to {total}"
            )

    def _check_sleeve_consistency(self) -> None:
        sleeve_of: dict[InstrumentId, SleeveId] = {}
        for item in self.contributions:
            seen = sleeve_of.setdefault(item.instrument_id, item.sleeve)
            if seen is not item.sleeve:
                raise InvalidTargetError(
                    f"{item.instrument_id} is contributed under both {seen.value} and "
                    f"{item.sleeve.value}; an instrument belongs to exactly one sleeve"
                )

    def _instrument_weight_total(self) -> Decimal:
        return sum(self.weights_by_instrument.values(), Decimal("0"))

    @property
    def weights_by_instrument(self) -> dict[InstrumentId, Decimal]:
        """Aggregated theoretical weight per addressed instrument, built in
        canonical InstrumentId order so iteration is deterministic."""
        weights: dict[InstrumentId, Decimal] = {}
        for item in self.contributions:
            weights[item.instrument_id] = (
                weights.get(item.instrument_id, Decimal("0")) + item.target_weight
            )
        return dict(sorted(weights.items()))

    @property
    def sleeve_weights(self) -> dict[SleeveId, Decimal]:
        """Aggregate exposure per sleeve, from the explicit sleeve fields only."""
        weights: dict[SleeveId, Decimal] = {}
        for item in self.contributions:
            weights[item.sleeve] = weights.get(item.sleeve, Decimal("0")) + item.target_weight
        return dict(sorted(weights.items()))

    @property
    def addressed_instruments(self) -> frozenset[InstrumentId]:
        """Instruments the target explicitly addresses, including explicit
        zero targets; absence never means hold or sell."""
        return frozenset(item.instrument_id for item in self.contributions)

    @property
    def cash_weight(self) -> Decimal:
        return Decimal("1") - self._instrument_weight_total()

    def sleeve_of(self, instrument_id: InstrumentId) -> SleeveId:
        for item in self.contributions:
            if item.instrument_id == instrument_id:
                return item.sleeve
        raise InvalidTargetError(f"{instrument_id} is not addressed by this target")

    def supersede(
        self,
        contributions: tuple[TargetContribution, ...],
        reason_code: str,
        actor: str,
    ) -> "TheoreticalTargetPortfolio":
        """Create the superseding revision; the locked original is untouched."""
        _require_text(reason_code, "reason_code")
        _require_text(actor, "actor")
        return TheoreticalTargetPortfolio(
            target_id=self.target_id,
            revision=self.revision + 1,
            decision_for_trade_date=self.decision_for_trade_date,
            generated_at=self.generated_at,
            information_cutoff=self.information_cutoff,
            valuation_equity=self.valuation_equity,
            contributions=contributions,
            supersedes_revision=self.revision,
            supersession_reason=reason_code,
            superseded_by=actor,
        )

    @property
    def content_digest(self) -> str:
        """Deterministic digest over canonical content, independent of the
        input ordering of contributions."""
        canonical_items = sorted(
            self.contributions,
            key=lambda item: (
                str(item.instrument_id),
                item.sleeve.value,
                item.strategy_id,
                item.strategy_version,
                str(item.target_weight),
                item.evidence_ids,
            ),
        )
        lines = [
            f"target_id={self.target_id}",
            f"revision={self.revision}",
            f"decision_for_trade_date={self.decision_for_trade_date.isoformat()}",
            f"generated_at={self.generated_at.isoformat()}",
            f"information_cutoff={self.information_cutoff.isoformat()}",
            (
                f"valuation_equity={self.valuation_equity.amount},"
                f"{self.valuation_equity.currency}"
            ),
            f"supersedes_revision={self.supersedes_revision}",
            f"supersession_reason={self.supersession_reason}",
            f"superseded_by={self.superseded_by}",
        ]
        for item in canonical_items:
            lines.append(
                f"contribution={item.instrument_id},{item.sleeve.value},{item.strategy_id},"
                f"{item.strategy_version},{item.target_weight},{','.join(item.evidence_ids)}"
            )
        return sha256("\n".join(lines).encode("utf-8")).hexdigest()
