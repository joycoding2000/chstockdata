"""Exact money value objects.

Currency amounts are exact ``Decimal`` values; binary floats never decide
capital, cash, or fees. Arithmetic is exact and never rounds implicitly:
quantization happens only through an explicit rounding-mode argument.
"""

from dataclasses import dataclass
from decimal import Decimal
from functools import total_ordering

from systematic_investing import BASE_CURRENCY

ScaleFactor = int | Decimal


class MoneyError(Exception):
    """Base class for money value-object errors."""


class InvalidMoneyAmountError(MoneyError):
    """Raised when a money amount or currency is not an exact, finite value."""


class CurrencyMismatchError(MoneyError):
    """Raised when an operation mixes two different currencies."""


@total_ordering
@dataclass(frozen=True)
class Money:
    """An exact currency amount. Construction only accepts ``Decimal`` so a
    binary float can never enter accounting by accident. Arithmetic is exact;
    callers quantize explicitly when a monetary scale (for example CNY cents)
    is required."""

    amount: Decimal
    currency: str = BASE_CURRENCY

    def __post_init__(self) -> None:
        if not isinstance(self.amount, Decimal):
            raise InvalidMoneyAmountError(
                f"money amounts must be Decimal, got {type(self.amount).__name__}"
            )
        if not self.amount.is_finite():
            raise InvalidMoneyAmountError(f"money amounts must be finite, got {self.amount!r}")
        if not isinstance(self.currency, str) or not self.currency:
            raise InvalidMoneyAmountError(
                f"currency must be a non-empty string, got {self.currency!r}"
            )

    def _require_same_currency(self, other: "Money") -> None:
        if not isinstance(other, Money):
            raise InvalidMoneyAmountError(f"cannot combine Money with {type(other).__name__}")
        if self.currency != other.currency:
            raise CurrencyMismatchError(f"{self.currency} and {other.currency} cannot be combined")

    def __add__(self, other: "Money") -> "Money":
        self._require_same_currency(other)
        return Money(self.amount + other.amount, currency=self.currency)

    def __sub__(self, other: "Money") -> "Money":
        self._require_same_currency(other)
        return Money(self.amount - other.amount, currency=self.currency)

    def __neg__(self) -> "Money":
        return Money(-self.amount, currency=self.currency)

    def __abs__(self) -> "Money":
        return Money(abs(self.amount), currency=self.currency)

    def __mul__(self, factor: ScaleFactor) -> "Money":
        if isinstance(factor, Decimal):
            if not factor.is_finite():
                raise InvalidMoneyAmountError(f"scale factors must be finite, got {factor!r}")
        elif not isinstance(factor, int) or isinstance(factor, bool):
            raise InvalidMoneyAmountError(
                f"money scales only by int or Decimal, got {type(factor).__name__}"
            )
        return Money(self.amount * factor, currency=self.currency)

    def __lt__(self, other: "Money") -> bool:
        self._require_same_currency(other)
        return self.amount < other.amount

    def quantized(self, exponent: Decimal, *, rounding: str) -> "Money":
        """Return a new Money quantized to ``exponent`` using the explicit
        ``rounding`` mode (a ``decimal`` module rounding constant)."""
        if not isinstance(exponent, Decimal):
            raise InvalidMoneyAmountError(
                f"quantization exponent must be Decimal, got {type(exponent).__name__}"
            )
        return Money(
            self.amount.quantize(exponent, rounding=rounding),
            currency=self.currency,
        )
