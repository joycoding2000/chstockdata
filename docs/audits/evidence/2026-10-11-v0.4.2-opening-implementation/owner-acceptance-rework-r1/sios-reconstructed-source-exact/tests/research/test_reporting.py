"""M1 Task 8: yearly/subperiod reporting without a regime router."""

from datetime import date
from decimal import Decimal

from systematic_investing.domain.ledger import NavPoint, ValuationStatus
from systematic_investing.domain.money import Money
from systematic_investing.research import reporting


def _nav(day: date, value: str) -> NavPoint:
    amount = Money(Decimal(value))
    return NavPoint(
        session_date=day,
        cash=amount,
        market_value=Money(Decimal("0")),
        total_equity=amount,
        nav=Decimal(value),
        valuation_status=ValuationStatus.COMPLETE,
    )


def test_yearly_and_half_year_metrics_are_deterministic_and_not_regime_based() -> None:
    points = (
        _nav(date(2022, 1, 3), "100"),
        _nav(date(2022, 2, 1), "110"),
        _nav(date(2022, 3, 1), "120"),
        _nav(date(2023, 1, 3), "120"),
        _nav(date(2023, 2, 1), "108"),
        _nav(date(2023, 3, 1), "132"),
    )

    first = reporting.build_yearly_subperiod_report(points)
    second = reporting.build_yearly_subperiod_report(tuple(reversed(points)))

    assert first == second
    assert first["report_schema_version"] == "research-period-report-1"
    assert [item["period"] for item in first["yearly"]] == ["2022", "2023"]
    assert first["yearly"][0]["metrics"]["observation_count"] == 3
    assert first["yearly"][0]["metrics"]["total_return"] == "0.2"
    assert {item["period"] for item in first["subperiods"]} == {
        "2022-H1",
        "2022-H2",
        "2023-H1",
        "2023-H2",
    }
    assert any(
        item["period"] == "2022-H2" and item["status"] == "INSUFFICIENT_HISTORY"
        for item in first["subperiods"]
    )
    assert "regime" not in first
    assert all("regime" not in item for item in first["yearly"])
    assert all("regime" not in item for item in first["subperiods"])
