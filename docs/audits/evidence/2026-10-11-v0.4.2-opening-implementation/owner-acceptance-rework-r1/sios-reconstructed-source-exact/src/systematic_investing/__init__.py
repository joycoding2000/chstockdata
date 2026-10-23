"""Systematic Investing OS: provider-neutral M0 foundation package.

The package root owns the system-wide default account facts that domain,
backtest, and metrics layers must agree on. Currency amounts are exact
``Decimal`` values; binary floats never decide capital, cash, or fees.
"""

from decimal import Decimal
from typing import Final

BASE_CURRENCY: Final[str] = "CNY"
DEFAULT_INITIAL_CAPITAL: Final[Decimal] = Decimal("100000")

__all__ = ["BASE_CURRENCY", "DEFAULT_INITIAL_CAPITAL"]
