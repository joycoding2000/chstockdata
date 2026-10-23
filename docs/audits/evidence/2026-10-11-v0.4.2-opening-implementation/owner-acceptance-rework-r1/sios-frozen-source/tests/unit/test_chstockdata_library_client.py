"""Library client bridge: the pinned vendor's calendar/suspension/corporate
function surface, mapped to the adapter's raw payloads.

``LibraryChStockDataClient`` must expose every capability the adapter
declares (``SOURCES.yaml``). These tests run fully offline through the
injectable ``library`` seam: a stub vendor module replaces the pinned
package, so no network, no vendor install, and no recorded market data are
needed.
"""

import json
from datetime import date
from types import SimpleNamespace

import pytest

from systematic_investing.adapters.chstockdata.provider import (
    ChStockDataConfigurationError,
    ChStockDataProvider,
    ChStockDataSchemaDriftError,
    ChStockDataUnavailableError,
    LibraryChStockDataClient,
)
from systematic_investing.data.ports import (
    CalendarRequest,
    CorporateActionRequest,
    TradabilityRequest,
)
from systematic_investing.domain.identifiers import InstrumentId

INSTRUMENT = InstrumentId.parse("XSHG:510300")
SZ_INSTRUMENT = InstrumentId.parse("XSHE:159915")


def stub_library(
    *,
    trading_calendar=None,
    suspension_payload: str | None = None,
    corporate_actions_payload: str | None = None,
) -> SimpleNamespace:
    functions = {
        "__version__": "0.3.0",
        "load_vipdoc_daily": lambda *args, **kwargs: None,
    }
    if trading_calendar is not None:
        functions["load_trading_calendar"] = lambda **kwargs: trading_calendar
    if suspension_payload is not None:
        functions["get_suspension_info"] = lambda *args, **kwargs: suspension_payload
    if corporate_actions_payload is not None:
        functions["get_corporate_actions"] = lambda *args, **kwargs: (
            corporate_actions_payload
        )
    return SimpleNamespace(**functions)


def stub_library_with_routing(
    *,
    stock_payload: str | None = None,
    fund_payload: str | None = None,
) -> tuple[SimpleNamespace, dict[str, list]]:
    """A stub library exposing both dividend capabilities, recording calls."""
    functions: dict = {
        "__version__": "0.3.0",
        "load_vipdoc_daily": lambda *args, **kwargs: None,
    }
    calls: dict[str, list] = {"stock": [], "fund": []}

    def stock_actions(*args, **kwargs):
        calls["stock"].append((args, kwargs))
        return stock_payload if stock_payload is not None else _empty_stock_actions()

    def fund_actions(*args, **kwargs):
        calls["fund"].append((args, kwargs))
        return fund_payload if fund_payload is not None else _empty_stock_actions()

    functions["get_corporate_actions"] = stock_actions
    functions["get_fund_corporate_actions"] = fund_actions
    return SimpleNamespace(**functions), calls


def _empty_stock_actions() -> str:
    body = json.dumps(
        {
            "status": "normal_empty",
            "coverage": "complete",
            "source": "Eastmoney datacenter RPT_SHAREBONUS_DET",
            "items": [],
        }
    )
    return f"# Corporate actions\n{body}"


def client_with(library) -> LibraryChStockDataClient:
    return LibraryChStockDataClient(library=library)


def calendar_payload_text() -> str:
    fixture = json.dumps(
        {
            "open_days": ["2026-09-10", "2026-09-11", "2026-09-14"],
            "covered_start": "2026-09-01",
            "covered_end": "2026-09-30",
            "source": "vipdoc local index days",
            "stale": False,
            "limitations": [],
        }
    )
    return f"# Trading calendar\n{fixture}"


def test_bridge_declares_the_full_documented_capability_surface() -> None:
    library = stub_library()
    client = client_with(library)

    methods = (
        "provider_version",
        "daily_bars",
        "calendar",
        "suspension",
        "corporate_actions",
        "rule_candidates",
    )
    for method in methods:
        assert callable(getattr(client, method)), method


def test_daily_bars_pass_the_pure_six_digit_code_and_explicit_market() -> None:
    """The vendor's vipdoc reader rejects prefixed symbols.

    ``load_vipdoc_daily`` validates a pure six-digit code and resolves the
    exchange from the explicit ``market`` argument; a prefixed "sh510300"
    form is rejected and silently returns no data.
    """
    import pandas as pd  # noqa: F401  (stub frame only needs an interface)

    calls: list[tuple[object, ...]] = []

    def fake_load(*args, **kwargs):
        calls.append((args, kwargs))
        return None

    library = stub_library()
    library.load_vipdoc_daily = fake_load
    client = client_with(library)

    from systematic_investing.adapters.chstockdata.provider import (
        ChStockDataUnavailableError,
    )

    with pytest.raises(ChStockDataUnavailableError):
        client.daily_bars(
            instrument_id=INSTRUMENT,
            start_date=date(2026, 9, 10),
            end_date=date(2026, 9, 11),
        )

    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args[0] == "510300"
    assert args[1] == "2026-09-10"
    assert args[2] == "2026-09-11"
    assert kwargs.get("market") == "sh"

    with pytest.raises(ChStockDataUnavailableError):
        client.daily_bars(
            instrument_id=SZ_INSTRUMENT,
            start_date=date(2026, 9, 10),
            end_date=date(2026, 9, 11),
        )
    args, kwargs = calls[1]
    assert args[0] == "159915"
    assert kwargs.get("market") == "sz"


def test_calendar_maps_the_vendor_trading_calendar_payload() -> None:
    calendar = SimpleNamespace(
        trading_days=("2026-09-10", "2026-09-11", "2026-09-14"),
        source="vipdoc local index days",
        covered_range=("2026-09-01", "2026-09-30"),
        last_bar_date="2026-09-14",
        stale=False,
        as_of="2026-09-16",
        limitations=(),
    )
    client = client_with(stub_library(trading_calendar=calendar))

    response = client.calendar(
        calendar_id="XSHG", start_date=date(2026, 9, 10), end_date=date(2026, 9, 14)
    )

    assert response.capability == "trading_calendar"
    assert response.payload["open_days"] == ["2026-09-10", "2026-09-11", "2026-09-14"]
    assert response.payload["covered_start"] == "2026-09-01"
    assert response.payload["covered_end"] == "2026-09-30"
    assert response.payload["stale"] is False
    assert response.payload["limitations"] == []
    assert "load_trading_calendar" in response.upstream_source


def test_calendar_unavailable_fails_closed() -> None:
    functions = stub_library()
    functions.load_trading_calendar = lambda **kwargs: None
    client = client_with(functions)

    with pytest.raises(ChStockDataUnavailableError):
        client.calendar(
            calendar_id="XSHG", start_date=date(2026, 9, 10), end_date=date(2026, 9, 14)
        )


def test_suspension_success_maps_the_labeled_json_payload() -> None:
    body = json.dumps(
        {
            "status": "success",
            "source": "Eastmoney datacenter RPT_CUSTOM_SUSPEND_DATA_INTERFACE",
            "observed_at": "2026-09-11T18:05:00+08:00",
            "as_of_date": "2026-09-16",
            "snapshot_date": "2026-09-11",
            "snapshot_rows": 3,
            "suspended": True,
            "suspend_start_date": "2026-09-11",
            "suspend_start_time": None,
            "suspend_expire": None,
            "suspend_reason": "重大事项",
            "trade_market": "上海",
            "predict_resume_date": None,
        }
    )
    client = client_with(
        stub_library(suspension_payload=f"[缺数据] 停复牌\n{body}")
    )

    response = client.suspension(
        instrument_id=INSTRUMENT, session_date=date(2026, 9, 11)
    )

    assert response.capability == "tradability"
    assert response.payload["suspended"] is True
    assert response.payload["snapshot_date"] == "2026-09-11"
    assert response.payload["source"]


def test_suspension_normal_empty_maps_to_a_not_suspended_snapshot() -> None:
    body = json.dumps(
        {
            "status": "normal_empty",
            "source": "Eastmoney datacenter RPT_CUSTOM_SUSPEND_DATA_INTERFACE",
            "observed_at": "2026-09-11T18:05:00+08:00",
            "as_of_date": "2026-09-16",
            "snapshot_date": "2026-09-11",
            "snapshot_rows": 1,
            "suspended": False,
            "suspend_start_time": None,
            "suspend_expire": None,
            "suspend_reason": None,
            "trade_market": None,
            "predict_resume_date": None,
        }
    )
    client = client_with(
        stub_library(suspension_payload=f"[缺数据] 停复牌\n{body}")
    )

    response = client.suspension(
        instrument_id=SZ_INSTRUMENT, session_date=date(2026, 9, 11)
    )

    assert response.payload["suspended"] is False
    assert response.payload["snapshot_date"] == "2026-09-11"


def test_suspension_network_failure_maps_to_unavailable() -> None:
    body = json.dumps(
        {
            "status": "failed_network",
            "reason": "RequestException",
        }
    )
    client = client_with(
        stub_library(suspension_payload=f"[数据缺失] 停复牌\n{body}")
    )

    with pytest.raises(ChStockDataUnavailableError):
        client.suspension(instrument_id=INSTRUMENT, session_date=date(2026, 9, 11))


def test_suspension_snapshot_truncation_maps_to_schema_drift() -> None:
    body = json.dumps(
        {
            "status": "failed_structure",
            "reason": "snapshot_truncated",
            "snapshot_date": "2026-09-11",
            "snapshot_rows": 50,
            "reported_count": 200,
        }
    )
    client = client_with(
        stub_library(suspension_payload=f"[数据缺失] 停复牌\n{body}")
    )

    with pytest.raises(ChStockDataSchemaDriftError):
        client.suspension(instrument_id=INSTRUMENT, session_date=date(2026, 9, 11))


def test_suspension_invalid_input_maps_to_configuration() -> None:
    body = json.dumps({"status": "invalid_input", "reason": "ValueError"})
    client = client_with(
        stub_library(suspension_payload=f"Invalid ticker for suspension\n{body}")
    )

    with pytest.raises(ChStockDataConfigurationError):
        client.suspension(instrument_id=INSTRUMENT, session_date=date(2026, 9, 11))


def test_suspension_malformed_vendor_text_fails_as_schema_drift() -> None:
    client = client_with(stub_library(suspension_payload="not json at all"))

    with pytest.raises(ChStockDataSchemaDriftError):
        client.suspension(instrument_id=INSTRUMENT, session_date=date(2026, 9, 11))


def test_corporate_actions_success_maps_the_labeled_json_payload() -> None:
    body = json.dumps(
        {
            "status": "success",
            "coverage": "complete",
            "source": "Eastmoney datacenter RPT_SHAREBONUS_DET",
            "fetched_at": "2026-09-16T18:00:00+08:00",
            "failure_kind": None,
            "error_summary": None,
            "items": [
                {
                    "source_identifier": "eastmoney:cash-2026-600519",
                    "source_identifier_kind": "provider_identifier",
                    "source": "Eastmoney datacenter RPT_SHAREBONUS_DET",
                    "announcement_date": "2026-09-03",
                    "ex_dividend_date": "2026-09-10",
                    "equity_record_date": "2026-09-09",
                    "payment_date": "2026-09-11",
                    "cash_dividend": {
                        "value": 0.3,
                        "unit": "per_10_shares",
                        "source_field": "CASH_DIVIDEND_RATIO",
                        "tax_basis": "unknown",
                    },
                    "stock_dividend": None,
                    "capital_reserve_transfer": None,
                    "rights_issue": None,
                }
            ],
        }
    )
    client = client_with(
        stub_library(corporate_actions_payload=f"# Corporate actions\n{body}")
    )

    response = client.corporate_actions(
        instrument_id=INSTRUMENT,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 9, 11),
        instrument_kind="STOCK",
    )

    assert response.capability == "corporate_actions"
    assert response.payload["coverage"] == "complete"
    assert response.payload["items"][0]["ex_dividend_date"] == "2026-09-10"


def test_corporate_actions_failure_maps_to_unavailable() -> None:
    body = json.dumps(
        {
            "status": "failed",
            "coverage": "unavailable",
            "source": "Eastmoney datacenter RPT_SHAREBONUS_DET",
            "items": [],
            "failure_kind": "request_error",
            "error_summary": "request failed",
        }
    )
    client = client_with(
        stub_library(corporate_actions_payload=f"[数据缺失] 分红派息\n{body}")
    )

    with pytest.raises(ChStockDataUnavailableError):
        client.corporate_actions(
            instrument_id=INSTRUMENT,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 9, 11),
            instrument_kind="STOCK",
        )


def test_missing_vendor_capability_fails_closed_as_configuration() -> None:
    client = client_with(stub_library())

    with pytest.raises(ChStockDataConfigurationError):
        client.calendar(
            calendar_id="XSHG", start_date=date(2026, 9, 10), end_date=date(2026, 9, 14)
        )
    with pytest.raises(ChStockDataConfigurationError):
        client.suspension(instrument_id=INSTRUMENT, session_date=date(2026, 9, 11))
    with pytest.raises(ChStockDataConfigurationError):
        client.corporate_actions(
            instrument_id=INSTRUMENT,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 9, 11),
            instrument_kind="STOCK",
        )
    with pytest.raises(ChStockDataConfigurationError):
        client.corporate_actions(
            instrument_id=INSTRUMENT,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 9, 11),
            instrument_kind="BOND",
        )


def test_corporate_actions_route_by_declared_instrument_kind() -> None:
    """ETF requests hit the fund F10 surface; stock requests stay on the
    A-share dividend report; the routing is a declared kind, never a symbol
    inference."""
    library, calls = stub_library_with_routing()
    client = client_with(library)

    client.corporate_actions(
        instrument_id=SZ_INSTRUMENT,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 9, 11),
        instrument_kind="ETF",
    )
    client.corporate_actions(
        instrument_id=INSTRUMENT,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 9, 11),
        instrument_kind="STOCK",
    )

    assert calls["fund"] == [(("159915", "2026-01-01", "2026-09-11"), {})]
    assert calls["stock"] == [(("510300", "2026-01-01", "2026-09-11"), {})]


def test_provider_end_to_end_maps_bridge_outputs_to_canonical_records() -> None:
    from datetime import datetime, timedelta, timezone

    from systematic_investing.data.contracts import ProviderSuccess
    from systematic_investing.domain.market import (
        AvailabilityBasis,
        TradingSession,
    )

    calendar = SimpleNamespace(
        trading_days=("2026-09-10", "2026-09-11"),
        source="vipdoc local index days",
        covered_range=("2026-09-01", "2026-09-30"),
        last_bar_date="2026-09-11",
        stale=False,
        as_of="2026-09-16",
        limitations=(),
    )
    suspension_body = json.dumps(
        {
            "status": "success",
            "source": "Eastmoney datacenter RPT_CUSTOM_SUSPEND_DATA_INTERFACE",
            "observed_at": "2026-09-11T18:05:00+08:00",
            "as_of_date": "2026-09-16",
            "snapshot_date": "2026-09-11",
            "suspended": False,
            "suspend_start_time": None,
            "suspend_expire": None,
            "suspend_reason": None,
            "trade_market": None,
            "predict_resume_date": None,
        }
    )
    actions_body = json.dumps(
        {
            "status": "normal_empty",
            "coverage": "complete",
            "source": "Eastmoney datacenter RPT_SHAREBONUS_DET",
            "items": [],
        }
    )
    client = client_with(
        stub_library(
            trading_calendar=calendar,
            suspension_payload=f"# 停复牌\n{suspension_body}",
            corporate_actions_payload=f"# 分红派息\n{actions_body}",
        )
    )
    retrieved_at = datetime(2026, 9, 16, 18, 0, tzinfo=timezone(timedelta(hours=8)))
    provider = ChStockDataProvider(client=client, clock=lambda: retrieved_at)

    sessions = provider.fetch_calendar(
        CalendarRequest(
            calendar_id="XSHG", start_date=date(2026, 9, 10), end_date=date(2026, 9, 11)
        )
    )
    assert isinstance(sessions, ProviderSuccess)
    assert {session.session_date for session in sessions.records} == {
        date(2026, 9, 10),
        date(2026, 9, 11),
    }
    for session in sessions.records:
        assert isinstance(session, TradingSession)

    tradability = provider.fetch_tradability(
        TradabilityRequest(
            instrument_ids=(SZ_INSTRUMENT,), session_date=date(2026, 9, 11)
        )
    )
    assert isinstance(tradability, ProviderSuccess)
    assert tradability.records[0].status.value == "TRADABLE"
    assert tradability.records[0].availability.availability_basis is not (
        AvailabilityBasis.UNKNOWN
    )

    actions = provider.fetch_corporate_actions(
        CorporateActionRequest(
            instrument_ids=(INSTRUMENT,),
            start_date=date(2026, 1, 1),
            end_date=date(2026, 9, 11),
        )
    )
    assert isinstance(actions, ProviderSuccess)
    assert actions.records == ()
