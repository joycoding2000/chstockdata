"""MCP server entrypoint — exposes chstockdata vendor functions as tools.

Install the extra and run::

    pip install "chstockdata[mcp]"
    chstockdata-mcp

Or register in any MCP client config (see examples/mcp-config.json)::

    {"mcpServers": {"chstockdata": {"command": "chstockdata-mcp"}}}

Notes:
  * The heavy import is guarded so the package import works without the
    ``mcp`` extra; only this entrypoint requires it.
  * Returns are flattened for LLM consumption: DataFrames render as text
    tables, dicts/lists pass through as structured content.
  * All built-in hardening stays active (Eastmoney throttle, server
    selection negative cache, realtime fallback chain).
"""

from __future__ import annotations

import argparse
import inspect
from functools import wraps
from typing import Any

_TOOL_FUNCTIONS: tuple[str, ...] = (
    # ticker / resolution
    "resolve_ticker",
    # quotes / OHLCV
    "get_realtime_snapshot", "get_stock_data", "get_ohlcv_frame_cached",
    "get_adjusted_bars", "get_stock_monitor", "get_hot_concept_examples",
    # fundamentals / financials
    "get_fundamentals", "get_balance_sheet", "get_cashflow",
    "get_income_statement", "get_free_financial_indicators",
    "get_earnings_forecast", "get_research_reports",
    # corporate events / governance
    "get_corporate_actions", "get_fund_corporate_actions", "get_announcement_index",
    "get_disclosure_schedule", "get_suspension_info", "get_delisting_info",
    "get_insider_transactions", "get_shareholder_pledge",
    "get_corporate_buyback",
    # money flow / microstructure
    "get_fund_flow", "get_dragon_tiger_board", "get_block_trades",
    "get_northbound_flow", "get_market_breadth", "get_margin_trading",
    "get_valuation_history", "get_industry_comparison", "get_concept_blocks",
    # reversed-ported upstream endpoints (v0.2.0)
    "get_daily_dragon_tiger", "get_board_fund_flow",
    "get_limit_up_pool", "get_limit_up_reasons",
    "get_chip_distribution",
    "list_etf_option_contracts", "get_etf_option_tquote",
    "get_etf_option_greeks", "get_etf_option_chain",
    "get_hot_rank", "get_em_hot_rank", "get_hot_concepts", "get_investor_qa",
    # news / policy / macro
    "get_news", "get_global_news", "get_policy_news", "get_hot_stocks",
    "get_macro_indicators",
    # calendar
    "local_is_trading_day", "load_trading_calendar",
)


def _flatten(result: Any) -> Any:
    """Coerce vendor returns into MCP-friendly content."""
    import pandas as pd

    if isinstance(result, pd.DataFrame):
        return result.to_string(index=False)
    if isinstance(result, pd.Series):
        return result.to_string()
    if isinstance(result, (str, int, float, bool)) or result is None:
        return result
    if isinstance(result, (dict, list, tuple)):
        return result
    return str(result)


def build_server():  # pragma: no cover - exercised via the mcp extra
    """Construct the FastMCP server with all vendor tools registered."""
    from mcp.server.fastmcp import FastMCP

    import chstockdata as cd

    mcp = FastMCP("chstockdata")

    def _make_wrapped(func):
        @wraps(func)
        def _wrapped(*args, **kwargs):
            return _flatten(func(*args, **kwargs))

        if not _wrapped.__doc__:
            _wrapped.__doc__ = f"{func.__name__} from chstockdata"
        annotations = dict(getattr(func, "__annotations__", {}))
        annotations["return"] = Any
        signature = inspect.signature(func)
        parameters = []
        for parameter in signature.parameters.values():
            annotation = parameter.annotation
            if isinstance(annotation, str) and "DataFrame" in annotation:
                # DataFrames are internal convenience inputs; MCP receives JSON.
                annotation = Any
                annotations[parameter.name] = Any
            parameters.append(parameter.replace(annotation=annotation))
        _wrapped.__annotations__ = annotations
        _wrapped.__signature__ = signature.replace(
            parameters=parameters,
            return_annotation=Any,
        )
        return _wrapped

    for name in _TOOL_FUNCTIONS:
        func = getattr(cd, name)
        mcp.tool()(_make_wrapped(func))

    return mcp


def main(argv: list[str] | None = None) -> int:  # pragma: no cover
    parser = argparse.ArgumentParser(
        prog="chstockdata-mcp",
        description="chstockdata MCP server (stdio transport by default)",
    )
    parser.add_argument(
        "--transport", default="stdio", choices=["stdio"],
        help="MCP transport (stdio is the standard for local agents)",
    )
    args = parser.parse_args(argv)

    mcp = build_server()
    mcp.run(transport=args.transport)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
