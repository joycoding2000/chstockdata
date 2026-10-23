"""Package-contract tests: the bootstrap facts every later layer relies on."""

from decimal import Decimal


def test_default_initial_capital_is_exactly_cny_100000() -> None:
    import systematic_investing

    capital = systematic_investing.DEFAULT_INITIAL_CAPITAL
    assert isinstance(capital, Decimal)
    assert capital == Decimal("100000")
    # Exact representation: no scaled variant such as Decimal("100000.00").
    assert str(capital) == "100000"
    assert systematic_investing.BASE_CURRENCY == "CNY"
