"""chstockdata — free China A-share market data toolkit.

No API keys, no mandatory third-party market-data SDK in the core path —
direct HTTP/TCP access to public quote vendors (Tencent, mootdx/TDX,
Eastmoney, Sina, THS, CLS, SSE/SZSE), extracted and battle-tested from
TradingAgents-astock. Optional extras (``mootdx``, ``baostock``) unlock
specific capabilities such as the K-line primary source.

Quick start::

    from chstockdata import configure, get_stock_data, resolve_ticker

    configure(cache_dir="./cache")            # optional
    resolve_ticker("贵州茅台")                  # -> "600519"
    df = get_stock_data("600519", 365)         # daily OHLCV

Eastmoney requests are throttled module-wide (``EM_MIN_INTERVAL``, default
1.0s) — keep it that way; do not fan out concurrent full-market scans.
"""

from __future__ import annotations

from .config import (
    configure,
    get_config,
    get_setting,
    reset_config,
    validate_vipdoc_history_config,
)
from .vendor_errors import (
    DeadlineExceeded,
    SourceContextDeadlineExceeded,
    VendorError,
    VendorNetworkError,
    VendorNoDataError,
    VendorNotConfiguredError,
    VendorRateLimitError,
)
from .utils import safe_ticker_component

# ── Core vendor functions (a_stock) ─────────────────────────────────────────
from .a_stock import (
    ensure_name_code_map_warmup,
    name_code_map_ready,
    resolve_ticker,
    reset_mootdx_client,
    get_realtime_snapshot,
    get_hot_concept_examples,
    get_ohlcv_frame_cached,
    get_stock_data,
    get_fundamentals,
    get_balance_sheet,
    get_cashflow,
    get_income_statement,
    get_free_financial_indicators,
    get_news,
    get_global_news,
    get_insider_transactions,
    get_research_reports,
    get_earnings_forecast,
    get_shareholder_pledge,
    get_corporate_buyback,
    get_margin_trading,
    get_valuation_history,
    get_macro_indicators,
    get_disclosure_schedule,
    get_suspension_info,
    get_delisting_info,
    get_hot_stocks,
    get_stock_monitor,
    get_market_breadth,
    get_corporate_actions,
    get_fund_corporate_actions,
    get_announcement_index,
    get_block_trades,
    get_northbound_flow,
    get_policy_news,
    get_concept_blocks,
    get_fund_flow,
    get_dragon_tiger_board,
    get_lockup_expiry,
    get_industry_comparison,
    get_daily_dragon_tiger,
)

# ── Reversed-ported upstream endpoints (v0.2.0) ─────────────────────────────
from .board_flow import get_board_fund_flow
from .chips import chip_distribution, get_chip_distribution
from .etf_options import (
    get_etf_option_chain,
    get_etf_option_greeks,
    get_etf_option_tquote,
    list_etf_option_contracts,
)
from .hot_rank import get_em_hot_rank, get_hot_concepts, get_hot_rank
from .investor_qa import get_investor_qa
from .limit_up import get_limit_up_pool, get_limit_up_reasons

# ── Adjusted bars / calendar / vipdoc history ───────────────────────────────
from .adjusted_bars import get_adjusted_bars
from .trading_calendar import (
    TRADING_CALENDAR_PROVIDERS,
    fetch_trading_calendar,
    load_trading_calendar,
    local_is_trading_day,
    probe_trading_calendar_provider,
)
from .vipdoc_history import (
    load_vipdoc_daily,
    vipdoc_history_dir,
    vipdoc_history_status,
)

# ── Policy news ─────────────────────────────────────────────────────────────
from .policy_news import get_policy_news_for_context

# ── Provenance (evidence envelopes; capability resolver is injectable) ─────
from .provenance import (
    ATTEMPT_FAILED_AUTH,
    ATTEMPT_FAILED_NETWORK,
    ATTEMPT_FAILED_RATE_LIMIT,
    ATTEMPT_FAILED_STRUCTURE,
    ATTEMPT_NORMAL_EMPTY,
    ATTEMPT_SKIPPED,
    ATTEMPT_SKIPPED_DUE_TO_RUN_CIRCUIT,
    ATTEMPT_SUCCESS,
    COMPLETENESS_FULL,
    COMPLETENESS_MINIMAL,
    COMPLETENESS_PARTIAL,
    EvidenceEnvelope,
    ProviderAttempt,
    make_attempt,
    make_envelope,
    set_capability_resolver,
    validate_envelope,
)

# ── Capability health + structured results (v0.4.0, additive) ───────────────
from .capabilities import (
    CapabilityHealth,
    ProviderCapability,
    capability_health_snapshot,
    fetch_status_to_health_status,
    get_capability_health,
    record_capability_health,
    reset_capability_health,
)
from .fetch_result import (
    FETCH_FAILED_NETWORK,
    FETCH_FAILED_RATE_LIMIT,
    FETCH_FAILED_STRUCTURE,
    FETCH_NORMAL_EMPTY,
    FETCH_NOT_CONFIGURED,
    FETCH_SKIPPED,
    FETCH_SUCCESS,
    FetchAttempt,
    FetchMetadata,
    FetchResult,
)
from .quote_chain import fetch_realtime_quotes, probe_quote_provider
from .daily_bars import (
    DAILY_BAR_PROVIDERS,
    fetch_daily_bars,
    probe_daily_bars_provider,
)
from .suspension import fetch_suspension_info
from .delisting import fetch_delisting_status
from .tradability import fetch_tradability

__version__ = "0.4.0"

__all__ = [
    # config
    "configure", "get_config", "get_setting", "reset_config",
    "validate_vipdoc_history_config",
    # errors
    "DeadlineExceeded", "SourceContextDeadlineExceeded", "VendorError",
    "VendorNetworkError", "VendorNoDataError", "VendorNotConfiguredError",
    "VendorRateLimitError",
    # ticker safety / name resolution
    "safe_ticker_component", "resolve_ticker", "name_code_map_ready",
    "ensure_name_code_map_warmup", "reset_mootdx_client",
    # quotes / OHLCV
    "get_realtime_snapshot", "get_ohlcv_frame_cached", "get_stock_data",
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
    "get_daily_dragon_tiger", "get_board_fund_flow",
    # limit-up / chip distribution
    "get_limit_up_pool", "get_limit_up_reasons",
    "chip_distribution", "get_chip_distribution",
    # ETF options (Sina)
    "list_etf_option_contracts", "get_etf_option_tquote",
    "get_etf_option_greeks", "get_etf_option_chain",
    # market sentiment / investor relations
    "get_hot_rank", "get_em_hot_rank", "get_hot_concepts", "get_investor_qa",
    # news / policy
    "get_news", "get_global_news", "get_policy_news", "get_policy_news_for_context",
    "get_hot_stocks", "get_macro_indicators",
    # calendar / vipdoc history
    "local_is_trading_day", "load_trading_calendar",
    "TRADING_CALENDAR_PROVIDERS", "fetch_trading_calendar",
    "probe_trading_calendar_provider",
    "load_vipdoc_daily", "vipdoc_history_dir", "vipdoc_history_status",
    # provenance
    "ATTEMPT_SUCCESS", "ATTEMPT_NORMAL_EMPTY", "ATTEMPT_FAILED_NETWORK",
    "ATTEMPT_FAILED_AUTH", "ATTEMPT_FAILED_RATE_LIMIT",
    "ATTEMPT_FAILED_STRUCTURE", "ATTEMPT_SKIPPED",
    "ATTEMPT_SKIPPED_DUE_TO_RUN_CIRCUIT",
    "COMPLETENESS_FULL", "COMPLETENESS_PARTIAL", "COMPLETENESS_MINIMAL",
    "EvidenceEnvelope", "ProviderAttempt", "make_attempt", "make_envelope",
    "set_capability_resolver", "validate_envelope",
    # capability health + structured results (v0.4.0, additive)
    "ProviderCapability", "CapabilityHealth", "capability_health_snapshot",
    "get_capability_health", "record_capability_health", "reset_capability_health",
    "fetch_status_to_health_status",
    "FETCH_SUCCESS", "FETCH_NORMAL_EMPTY", "FETCH_FAILED_NETWORK",
    "FETCH_FAILED_RATE_LIMIT", "FETCH_FAILED_STRUCTURE",
    "FETCH_NOT_CONFIGURED", "FETCH_SKIPPED",
    "FetchAttempt", "FetchMetadata", "FetchResult", "fetch_realtime_quotes",
    "probe_quote_provider",
    # daily bars structured routing (v0.4.0 Phase 2, additive)
    "DAILY_BAR_PROVIDERS", "fetch_daily_bars", "probe_daily_bars_provider",
    # suspension structured snapshot (v0.4.0 Phase 5, additive)
    "fetch_suspension_info",
    # delisting structured status (additive)
    "fetch_delisting_status",
    # derived tradability (calendar + suspension, additive)
    "fetch_tradability",
]
