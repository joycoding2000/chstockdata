"""Canonical identifiers and session-date primitives.

Canonical instrument identity is ``(exchange, local_symbol)`` rendered as
``XSHG:510300``. A six-digit symbol alone is never accepted at a domain
boundary. Exchange session dates are exchange-local calendar dates, never
timestamps: converting an instant to a session date requires a timezone
choice, so the domain refuses to accept a ``datetime`` where a session
date is required instead of picking one implicitly.
"""

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import ClassVar


class InvalidInstrumentIdError(ValueError):
    """Raised when an instrument identity is not exchange-qualified canonical form."""


class InvalidSessionDateError(ValueError):
    """Raised when a value that must be an exchange-local session date is not one."""


class Exchange(StrEnum):
    """Exchanges in M0 scope."""

    XSHG = "XSHG"
    XSHE = "XSHE"


@dataclass(frozen=True, order=True)
class InstrumentId:
    """Exchange-qualified canonical instrument identity, ordered as (exchange, symbol).

    The total ordering is the canonical tie-breaker used by deterministic
    allocation policies; it never depends on insertion or map order.
    """

    exchange: Exchange
    symbol: str

    _SYMBOL_PATTERN: ClassVar[str] = r"[0-9]{6}"

    def __post_init__(self) -> None:
        if not isinstance(self.exchange, Exchange):
            raise InvalidInstrumentIdError(
                f"exchange must be an Exchange member, got {self.exchange!r}"
            )
        if not isinstance(self.symbol, str) or len(self.symbol) != 6:
            raise InvalidInstrumentIdError(
                f"symbol must be exactly six digits, got {self.symbol!r}"
            )
        if not self.symbol.isascii() or not self.symbol.isdigit():
            raise InvalidInstrumentIdError(
                f"symbol must be exactly six digits, got {self.symbol!r}"
            )

    def __str__(self) -> str:
        return f"{self.exchange.value}:{self.symbol}"

    @classmethod
    def parse(cls, text: str) -> "InstrumentId":
        """Parse the canonical ``XSHG:510300`` form; anything else is rejected."""
        if not isinstance(text, str):
            raise InvalidInstrumentIdError(f"canonical id must be a string, got {text!r}")
        exchange_text, separator, symbol_text = text.partition(":")
        if not separator or ":" in symbol_text:
            raise InvalidInstrumentIdError(
                f"expected canonical '<EXCHANGE>:<6-digit symbol>' form, got {text!r}"
            )
        try:
            exchange = Exchange(exchange_text)
        except ValueError as error:
            raise InvalidInstrumentIdError(
                f"unknown exchange code in {text!r}"
            ) from error
        try:
            return cls(exchange=exchange, symbol=symbol_text)
        except InvalidInstrumentIdError as error:
            raise InvalidInstrumentIdError(
                f"invalid symbol in {text!r}: {error}"
            ) from error


class SleeveId(StrEnum):
    """Strong sleeve identity. Sleeves are always passed explicitly and are
    never inferred from strategy names or instrument types."""

    CORE = "CORE"
    SATELLITE = "SATELLITE"


def require_session_date(value: date) -> date:
    """Return ``value`` only if it is a calendar date, not a datetime.

    Session dates drive effective-date selection, so accepting a ``datetime``
    here would silently embed a timezone choice. The domain refuses instead.
    """
    if isinstance(value, datetime) or not isinstance(value, date):
        raise InvalidSessionDateError(
            f"session dates are calendar dates, not datetimes; got {value!r}"
        )
    return value
