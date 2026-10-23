"""Execution contracts: run-owned account fee configuration, orders, fills,
and rejections.

Market/regulatory fee and tax truth lives in the effective-dated Instrument
Master; account/broker commission and minimums live in run-owned
``AccountFeeConfig``. The two authorities are composed by explicit
computations and are never merged, and nothing branches on instrument type
alone. M0 monetary quantization is explicit ROUND_HALF_UP to CNY cents.
"""

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from hashlib import sha256
from typing import Final

from systematic_investing.domain.identifiers import InstrumentId, require_session_date
from systematic_investing.domain.market import TradeSide
from systematic_investing.domain.money import Money
from systematic_investing.domain.portfolio import SizingPriceBasis

EXECUTION_CONVENTION_VERSION: Final[str] = "m0-execution-1"
FILL_PRICE_MODEL_NEXT_SESSION_OPEN: Final[str] = "NEXT_SESSION_OPEN"
ORDER_INVALIDATION_CORPORATE_ACTION: Final[str] = "CORPORATE_ACTION_REPLAN_REQUIRED"
MONETARY_EXPONENT: Final[Decimal] = Decimal("0.01")
MONETARY_ROUNDING: Final[str] = ROUND_HALF_UP


class ExecutionError(Exception):
    """Base class for execution contract errors."""


class InvalidOrderError(ExecutionError):
    """Raised when an order record or transition violates its contract."""


class InvalidFillError(ExecutionError):
    """Raised when a fill record violates its contract."""


class OrderStatus(StrEnum):
    """Order lifecycle states. M0 daily-bar orders are all-or-none once
    submitted."""

    PENDING_ACTIVATION = "PENDING_ACTIVATION"
    SUBMITTED = "SUBMITTED"
    FILLED = "FILLED"
    REJECTED = "REJECTED"
    INVALIDATED = "INVALIDATED"


class RejectionCode(StrEnum):
    """First-class market rejection categories."""

    INSUFFICIENT_CASH = "INSUFFICIENT_CASH"
    INSUFFICIENT_SELLABLE_QUANTITY = "INSUFFICIENT_SELLABLE_QUANTITY"
    SUSPENDED = "SUSPENDED"
    TRADABILITY_UNKNOWN = "TRADABILITY_UNKNOWN"
    NOT_LISTED = "NOT_LISTED"
    DELISTED = "DELISTED"
    BUY_BLOCKED_UPPER_LIMIT = "BUY_BLOCKED_UPPER_LIMIT"
    SELL_BLOCKED_LOWER_LIMIT = "SELL_BLOCKED_LOWER_LIMIT"
    MISSING_RULE = "MISSING_RULE"


def _order_text(value, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise InvalidOrderError(f"{field_name} must be a non-empty string")
    return value


@dataclass(frozen=True)
class FeeBreakdown:
    """Itemized execution fees: broker commission plus its minimum-commission
    adjustment, sell-side stamp tax where applicable, and transfer/other
    market fees. ``total`` is the sum of the itemized parts."""

    commission: Money
    minimum_commission_adjustment: Money
    stamp_tax: Money
    transfer_fee: Money

    @property
    def total(self) -> Money:
        return (
            self.commission
            + self.minimum_commission_adjustment
            + self.stamp_tax
            + self.transfer_fee
        )


def compute_fees(
    market_rule,
    broker_profile: "BrokerFeeProfile",
    side: TradeSide,
    quantity: int,
    price: Decimal,
) -> FeeBreakdown:
    """Compose the two fee authorities for one candidate execution.

    Market truth (stamp tax sell-side rate, transfer fee rate) comes from
    the Instrument Master ``MarketFeeTaxRule``; broker commission rate and
    minimum come from the run-owned profile. Nothing branches on instrument
    type: only the passed rule values decide the outcome.
    """
    if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity <= 0:
        raise ExecutionError(f"fee quantity must be a positive integer, got {quantity!r}")
    if not isinstance(price, Decimal) or not price.is_finite() or price <= 0:
        raise ExecutionError(f"fee price must be a finite positive Decimal, got {price!r}")
    notional = Decimal(quantity) * price
    commission_base = (notional * broker_profile.commission_rate).quantize(
        MONETARY_EXPONENT, rounding=MONETARY_ROUNDING
    )
    adjustment = (
        max(Decimal("0"), broker_profile.minimum_commission - commission_base)
    ).quantize(MONETARY_EXPONENT, rounding=MONETARY_ROUNDING)
    if side is TradeSide.SELL:
        stamp_tax = (notional * market_rule.stamp_tax_sell_rate).quantize(
            MONETARY_EXPONENT, rounding=MONETARY_ROUNDING
        )
    else:
        stamp_tax = Decimal("0").quantize(MONETARY_EXPONENT)
    transfer_fee = (notional * market_rule.transfer_fee_rate).quantize(
        MONETARY_EXPONENT, rounding=MONETARY_ROUNDING
    )
    return FeeBreakdown(
        commission=_money(commission_base),
        minimum_commission_adjustment=_money(adjustment),
        stamp_tax=_money(stamp_tax),
        transfer_fee=_money(transfer_fee),
    )


@dataclass(frozen=True)
class Order:
    """Intent to change quantity: T-close-sized ``planned_quantity``, the
    activation-time ``submitted_quantity`` (complete lots only), and the
    declared fill model. Transitions are pure: a rejected or invalidated
    order keeps its planned evidence; the locked target is never mutated."""

    order_id: str
    instrument_id: InstrumentId
    side: TradeSide
    planned_quantity: int
    submitted_quantity: int | None
    execution_session: date
    sizing_reference_price_basis: SizingPriceBasis
    sizing_reference_price: Decimal
    fill_price_model: str
    target_id: str
    target_revision: int
    decision_for_trade_date: date
    status: OrderStatus
    reason_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "reason_codes", tuple(self.reason_codes))
        _order_text(self.order_id, "order_id")
        if not isinstance(self.instrument_id, InstrumentId):
            raise InvalidOrderError("instrument_id must be an InstrumentId")
        if not isinstance(self.side, TradeSide):
            raise InvalidOrderError(f"side must be a TradeSide, got {self.side!r}")
        if (
            not isinstance(self.planned_quantity, int)
            or isinstance(self.planned_quantity, bool)
            or self.planned_quantity <= 0
        ):
            raise InvalidOrderError(
                f"planned_quantity must be a positive integer, got {self.planned_quantity!r}"
            )
        submitted = self.submitted_quantity
        if submitted is not None and (
            not isinstance(submitted, int)
            or isinstance(submitted, bool)
            or not 0 < submitted <= self.planned_quantity
        ):
            raise InvalidOrderError(
                f"submitted_quantity must be a complete legal quantity within "
                f"the plan, got {submitted!r}"
            )
        require_session_date(self.execution_session)
        require_session_date(self.decision_for_trade_date)
        if not isinstance(self.sizing_reference_price_basis, SizingPriceBasis):
            raise InvalidOrderError(
                "sizing_reference_price_basis must be a SizingPriceBasis"
            )
        if (
            not isinstance(self.sizing_reference_price, Decimal)
            or not self.sizing_reference_price.is_finite()
            or self.sizing_reference_price <= 0
        ):
            raise InvalidOrderError("sizing_reference_price must be a positive Decimal")
        _order_text(self.fill_price_model, "fill_price_model")
        _order_text(self.target_id, "target_id")
        if (
            not isinstance(self.target_revision, int)
            or isinstance(self.target_revision, bool)
            or self.target_revision < 1
        ):
            raise InvalidOrderError("target_revision must be a positive integer")
        if not isinstance(self.status, OrderStatus):
            raise InvalidOrderError(f"status must be an OrderStatus, got {self.status!r}")
        if not all(isinstance(code, str) and code for code in self.reason_codes):
            raise InvalidOrderError("reason_codes must be non-empty strings")

    def submit(self, submitted_quantity: int, lot_multiple: int) -> "Order":
        """Activation-time submission: a legal complete-lot quantity within
        the plan. This never resizes the theoretical target."""
        if self.status is not OrderStatus.PENDING_ACTIVATION:
            raise InvalidOrderError(
                f"order {self.order_id} in status {self.status.value} cannot be submitted"
            )
        if (
            not isinstance(lot_multiple, int)
            or isinstance(lot_multiple, bool)
            or lot_multiple <= 0
        ):
            raise InvalidOrderError("lot_multiple must be a positive integer")
        if (
            not isinstance(submitted_quantity, int)
            or isinstance(submitted_quantity, bool)
            or submitted_quantity <= 0
            or submitted_quantity % lot_multiple != 0
            or submitted_quantity > self.planned_quantity
        ):
            raise InvalidOrderError(
                f"{submitted_quantity} is not a legal complete-lot submission "
                f"within the planned {self.planned_quantity}"
            )
        return Order(
            order_id=self.order_id,
            instrument_id=self.instrument_id,
            side=self.side,
            planned_quantity=self.planned_quantity,
            submitted_quantity=submitted_quantity,
            execution_session=self.execution_session,
            sizing_reference_price_basis=self.sizing_reference_price_basis,
            sizing_reference_price=self.sizing_reference_price,
            fill_price_model=self.fill_price_model,
            target_id=self.target_id,
            target_revision=self.target_revision,
            decision_for_trade_date=self.decision_for_trade_date,
            status=OrderStatus.FILLED,
            reason_codes=self.reason_codes,
        )

    def rejected(
        self, code: RejectionCode, message: str, observed: str
    ) -> tuple["Order", "Rejection"]:
        """Expected market rejections are values, not crashes."""
        if self.status is not OrderStatus.PENDING_ACTIVATION:
            raise InvalidOrderError(
                f"order {self.order_id} in status {self.status.value} cannot be rejected"
            )
        rejection = Rejection(
            rejection_id=f"reject:{self.order_id}",
            order_id=self.order_id,
            instrument_id=self.instrument_id,
            side=self.side,
            code=code,
            message=message,
            session_date=self.execution_session,
            observed=observed,
        )
        order = Order(
            order_id=self.order_id,
            instrument_id=self.instrument_id,
            side=self.side,
            planned_quantity=self.planned_quantity,
            submitted_quantity=None,
            execution_session=self.execution_session,
            sizing_reference_price_basis=self.sizing_reference_price_basis,
            sizing_reference_price=self.sizing_reference_price,
            fill_price_model=self.fill_price_model,
            target_id=self.target_id,
            target_revision=self.target_revision,
            decision_for_trade_date=self.decision_for_trade_date,
            status=OrderStatus.REJECTED,
            reason_codes=(code.value,),
        )
        return order, rejection

    def invalidated_corporate_action(self) -> "Order":
        """A quantity-changing action effective between decision and
        activation invalidates the pending execution; no rescaled substitute
        is synthesized and the locked target is preserved."""
        if self.status is not OrderStatus.PENDING_ACTIVATION:
            raise InvalidOrderError(
                f"order {self.order_id} in status {self.status.value} cannot be invalidated"
            )
        return Order(
            order_id=self.order_id,
            instrument_id=self.instrument_id,
            side=self.side,
            planned_quantity=self.planned_quantity,
            submitted_quantity=None,
            execution_session=self.execution_session,
            sizing_reference_price_basis=self.sizing_reference_price_basis,
            sizing_reference_price=self.sizing_reference_price,
            fill_price_model=self.fill_price_model,
            target_id=self.target_id,
            target_revision=self.target_revision,
            decision_for_trade_date=self.decision_for_trade_date,
            status=OrderStatus.INVALIDATED,
            reason_codes=(ORDER_INVALIDATION_CORPORATE_ACTION,),
        )


@dataclass(frozen=True)
class Fill:
    """An append-only execution fact with itemized fees and slippage
    attribution."""

    fill_id: str
    order_id: str
    instrument_id: InstrumentId
    side: TradeSide
    quantity: int
    fill_price: Decimal
    reference_open: Decimal
    session_date: date
    fees: FeeBreakdown
    source: str = "SIMULATED"

    def __post_init__(self) -> None:
        _order_text(self.fill_id, "fill_id")
        _order_text(self.order_id, "order_id")
        if not isinstance(self.instrument_id, InstrumentId):
            raise InvalidFillError("instrument_id must be an InstrumentId")
        if not isinstance(self.side, TradeSide):
            raise InvalidFillError(f"side must be a TradeSide, got {self.side!r}")
        if (
            not isinstance(self.quantity, int)
            or isinstance(self.quantity, bool)
            or self.quantity <= 0
        ):
            raise InvalidFillError(f"quantity must be a positive integer, got {self.quantity!r}")
        for field_name in ("fill_price", "reference_open"):
            value = getattr(self, field_name)
            if not isinstance(value, Decimal) or not value.is_finite() or value <= 0:
                raise InvalidFillError(f"{field_name} must be a finite positive Decimal")
        if not isinstance(self.fees, FeeBreakdown):
            raise InvalidFillError("fees must be a FeeBreakdown")
        require_session_date(self.session_date)


@dataclass(frozen=True)
class Rejection:
    """A first-class execution outcome with the evaluated facts."""

    rejection_id: str
    order_id: str
    instrument_id: InstrumentId
    side: TradeSide
    code: RejectionCode
    message: str
    session_date: date
    observed: str

    def __post_init__(self) -> None:
        _order_text(self.rejection_id, "rejection_id")
        _order_text(self.order_id, "order_id")
        if not isinstance(self.instrument_id, InstrumentId):
            raise InvalidOrderError("instrument_id must be an InstrumentId")
        if not isinstance(self.side, TradeSide):
            raise InvalidOrderError(f"side must be a TradeSide, got {self.side!r}")
        if not isinstance(self.code, RejectionCode):
            raise InvalidOrderError(f"code must be a RejectionCode, got {self.code!r}")
        _order_text(self.message, "message")
        require_session_date(self.session_date)
        _order_text(self.observed, "observed")


class InvalidRejectionError(ExecutionError):
    """Raised when a rejection record violates its contract."""


class InvalidAccountFeeConfigError(ExecutionError):
    """Raised when an account/broker fee configuration is inconsistent."""


class UnknownBrokerProfileError(ExecutionError):
    """Raised when no broker fee profile covers the requested date."""


class ConflictingBrokerProfileError(ExecutionError):
    """Raised when broker fee profile versions overlap."""


def _require_text(value, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise InvalidAccountFeeConfigError(f"{field_name} must be a non-empty string")
    return value


_END_OF_TIME: Final[date] = date(9999, 12, 31)


def _digest(lines) -> str:
    return sha256("\n".join(lines).encode("utf-8")).hexdigest()


def _intervals_overlap(from_a, to_a, from_b, to_b) -> bool:
    end_a = to_a if to_a is not None else _END_OF_TIME
    end_b = to_b if to_b is not None else _END_OF_TIME
    return from_a <= end_b and from_b <= end_a


def _require_non_negative_decimal(value, field_name: str) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite() or value < 0:
        raise InvalidAccountFeeConfigError(
            f"{field_name} must be a finite non-negative Decimal"
        )
    return value


def _money(value: Decimal) -> Money:
    return Money(value)


@dataclass(frozen=True)
class BrokerFeeProfile:
    """Account-owned broker commission truth: rate, minimum, agreement
    provenance, and effective dates. Never an Instrument Master record."""

    profile_id: str
    version: str
    commission_rate: Decimal
    minimum_commission: Decimal
    agreement_reference: str
    effective_from: date
    effective_to: date | None

    def __post_init__(self) -> None:
        _require_text(self.profile_id, "profile_id")
        _require_text(self.version, "version")
        _require_text(self.agreement_reference, "agreement_reference")
        _require_non_negative_decimal(self.commission_rate, "commission_rate")
        _require_non_negative_decimal(self.minimum_commission, "minimum_commission")
        require_session_date(self.effective_from)
        if self.effective_to is not None:
            require_session_date(self.effective_to)
            if self.effective_to < self.effective_from:
                raise InvalidAccountFeeConfigError(
                    "effective_to must not precede effective_from"
                )

    def covers(self, session_date: date) -> bool:
        if session_date < self.effective_from:
            return False
        return self.effective_to is None or session_date <= self.effective_to


@dataclass(frozen=True)
class AccountFeeConfig:
    """Run-owned account fee configuration. Referenced by execution and
    accounting services and the run manifest; never by instrument identity
    or the Instrument Master."""

    config_id: str
    config_version: str
    broker_profiles: tuple[BrokerFeeProfile, ...]

    def __post_init__(self) -> None:
        _require_text(self.config_id, "config_id")
        _require_text(self.config_version, "config_version")
        if not isinstance(self.broker_profiles, tuple) or not all(
            isinstance(profile, BrokerFeeProfile) for profile in self.broker_profiles
        ):
            raise InvalidAccountFeeConfigError(
                "broker_profiles must be a tuple of BrokerFeeProfile"
            )
        seen_versions: set[tuple[str, str]] = set()
        for profile in self.broker_profiles:
            key = (profile.profile_id, profile.version)
            if key in seen_versions:
                raise InvalidAccountFeeConfigError(
                    f"duplicate broker profile version {key}"
                )
            seen_versions.add(key)
        for index, first in enumerate(self.broker_profiles):
            for second in self.broker_profiles[index + 1 :]:
                if _intervals_overlap(
                    first.effective_from,
                    first.effective_to,
                    second.effective_from,
                    second.effective_to,
                ):
                    raise ConflictingBrokerProfileError(
                        f"broker profiles {first.profile_id}/{first.version} and "
                        f"{second.profile_id}/{second.version} overlap"
                    )

    def resolve_broker_profile(self, session_date: date) -> BrokerFeeProfile:
        require_session_date(session_date)
        candidates = [profile for profile in self.broker_profiles if profile.covers(session_date)]
        if not candidates:
            raise UnknownBrokerProfileError(
                f"no broker fee profile covers {session_date}"
            )
        return candidates[0]

    def content_digest(self) -> str:
        lines = [
            f"config_id={self.config_id}",
            f"config_version={self.config_version}",
        ]
        for profile in sorted(
            self.broker_profiles,
            key=lambda profile: (profile.profile_id, profile.version),
        ):
            lines.append(
                f"broker={profile.profile_id},{profile.version},{profile.commission_rate},"
                f"{profile.minimum_commission},{profile.agreement_reference},"
                f"{profile.effective_from.isoformat()},{profile.effective_to}"
            )
        return _digest(lines)
