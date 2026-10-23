"""Narrow candidate guard and explicit legacy-gap provenance."""

import json
from datetime import UTC, date, datetime
from types import SimpleNamespace
import pytest
from systematic_investing.adapters.chstockdata.provider import (
    ChStockDataProvider,
    LibraryChStockDataClient,
    ChStockDataConfigurationError,
    HistoricalSuspensionUnavailableError,
)
from systematic_investing.data.contracts import ProviderFailure
from systematic_investing.data.ports import TradabilityRequest, HistoricalOpeningRequest
from systematic_investing.domain.identifiers import InstrumentId
from systematic_investing.domain.market import AvailabilityBasis

I = InstrumentId.parse("XSHG:510300")
DAY = date(2026, 9, 11)
NOW = datetime(2026, 10, 12, tzinfo=UTC)


def test_real_new_library_pin_is_opt_in():
    import chstockdata

    assert chstockdata.__version__ == "0.4.2"
    with pytest.raises(ChStockDataConfigurationError):
        LibraryChStockDataClient(library=chstockdata)
    assert (
        LibraryChStockDataClient(
            library=chstockdata, historical_opening_candidate=True
        ).provider_version()
        == "0.4.2"
    )


def test_actual_legacy_failure_constructs_only_unknown_constraint(monkeypatch):
    import chstockdata
    from chstockdata import a_stock, suspension
    from chstockdata.fetch_result import FetchAttempt

    snapshot = {
        "rows": [],
        "reported_count": 0,
        "snapshot_pages": 1,
        "retrieved_at": NOW.isoformat(),
        "status": "success",
        "reason": None,
        "attempts": [
            FetchAttempt(
                "eastmoney",
                "eastmoney:suspension",
                "normal_empty",
                NOW.isoformat(),
                0,
                record_count=0,
            )
        ],
    }
    monkeypatch.setattr(suspension, "_load_suspension_snapshot", lambda _: snapshot)
    monkeypatch.setattr(a_stock, "_load_suspension_snapshot", lambda _: snapshot)
    monkeypatch.setattr(a_stock, "_today", lambda: date(2026, 10, 12))
    provider = ChStockDataProvider(
        client=LibraryChStockDataClient(library=chstockdata, historical_opening_candidate=True),
        clock=lambda: NOW,
    )
    request = TradabilityRequest((I,), DAY)
    failure = provider.fetch_tradability(request)
    assert isinstance(failure, ProviderFailure)
    assert isinstance(failure.cause, HistoricalSuspensionUnavailableError)
    constraints = provider.historical_suspension_gap(request, failure)
    assert constraints[0].status.value == "UNKNOWN"
    assert constraints[0].availability.availability_basis is AvailabilityBasis.UNKNOWN
    assert failure.evidence.evidence_id in constraints[0].provenance
    with pytest.raises(ChStockDataConfigurationError):
        provider.historical_suspension_gap(TradabilityRequest((I,), date(2026, 9, 10)), failure)


@pytest.mark.parametrize(
    "reason", ["snapshot_truncated", "TimeoutError", "future_suspension_unavailable"]
)
def test_generic_failure_cannot_become_gap(reason):
    library = SimpleNamespace(
        __version__="0.3.0",
        get_suspension_info=lambda *a: json.dumps({"status": "failed_structure", "reason": reason}),
    )
    provider = ChStockDataProvider(
        client=LibraryChStockDataClient(library=library), clock=lambda: NOW
    )
    request = TradabilityRequest((I,), DAY)
    failure = provider.fetch_tradability(request)
    assert isinstance(failure, ProviderFailure)
    with pytest.raises(ChStockDataConfigurationError):
        provider.historical_suspension_gap(request, failure)


def test_old_client_missing_optional_method_is_typed_unsupported():
    provider = ChStockDataProvider(
        client=SimpleNamespace(provider_version=lambda: "0.3.0"), clock=lambda: NOW
    )
    result = provider.fetch_historical_opening_evidence(HistoricalOpeningRequest((I,), DAY))
    assert isinstance(result, ProviderFailure)
    assert result.error_code.value == "UNSUPPORTED_CAPABILITY"
