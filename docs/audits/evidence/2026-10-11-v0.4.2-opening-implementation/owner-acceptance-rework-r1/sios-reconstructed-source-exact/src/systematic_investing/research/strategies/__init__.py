"""Canonical Research strategies (the only ones wired into Basic/OOS runs).

Each strategy implements the typed :class:`StrategyContract`: it observes
only the T-known ``DecisionContext`` and the current ``UniverseView`` and
returns explicit target contributions or a typed no-decision with reason
codes. Strategies never execute, size, fee, settle, fetch data, or touch a
clock. A new rule, parameter, or universe semantic means a new
``strategy_version``; the implementation digest covers the module's own
bytes, addressed by its canonical path under ``src``.
"""

from collections.abc import Sequence
from datetime import date

from systematic_investing.research.strategies.etf_absolute_trend import (
    AbsoluteTrendStrategy,
)
from systematic_investing.research.strategies.etf_absolute_trend import (
    build_strategy as build_etf_absolute_trend,
)
from systematic_investing.research.strategies.etf_relative_momentum import (
    RelativeMomentumStrategy,
)
from systematic_investing.research.strategies.etf_relative_momentum import (
    build_strategy as build_etf_relative_momentum,
)
from systematic_investing.research.strategies.stock_breakout import (
    StockBreakoutStrategy,
)
from systematic_investing.research.strategies.stock_breakout import (
    build_strategy as build_stock_breakout,
)
from systematic_investing.research.strategies.stock_relative_strength import (
    StockRelativeStrengthStrategy,
)
from systematic_investing.research.strategies.stock_relative_strength import (
    build_strategy as build_stock_relative_strength,
)

DECISION_FREQUENCY_MONTHLY_LAST_SESSION: str = "MONTHLY_LAST_SESSION"

# The canonical strategy registry. Canonical Basic/OOS runs resolve the
# implementation only from these modules; test-only smoke strategies must
# never enter this registry.
CANONICAL_STRATEGY_IDS: tuple[str, ...] = (
    "etf-absolute-trend",
    "etf-relative-momentum",
    "stock-relative-strength",
    "stock-breakout",
)


def month_end_sessions(session_dates: Sequence[date]) -> tuple[date, ...]:
    """The last open session of each calendar month, in order.

    Derived only from the frozen calendar snapshot; which session is a
    month's last open session is calendar knowledge available at that
    session's close, never a look into future prices.
    """
    latest_by_month: dict[tuple[int, int], date] = {}
    for session_date in session_dates:
        key = (session_date.year, session_date.month)
        current = latest_by_month.get(key)
        if current is None or session_date > current:
            latest_by_month[key] = session_date
    return tuple(sorted(latest_by_month.values()))


__all__ = (
    "CANONICAL_STRATEGY_IDS",
    "AbsoluteTrendStrategy",
    "RelativeMomentumStrategy",
    "StockBreakoutStrategy",
    "StockRelativeStrengthStrategy",
    "build_etf_absolute_trend",
    "build_etf_relative_momentum",
    "build_stock_breakout",
    "build_stock_relative_strength",
    "month_end_sessions",
)
