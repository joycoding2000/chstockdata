"""Unit tests: exact Decimal money and explicit rounding discipline."""

from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal

import pytest

from systematic_investing.domain.money import CurrencyMismatchError, InvalidMoneyAmountError, Money


class TestMoneyConstruction:
    def test_decimal_amount_and_default_cny_currency(self) -> None:
        money = Money(Decimal("100000"))

        assert money.amount == Decimal("100000")
        assert money.currency == "CNY"

    def test_explicit_currency_is_retained(self) -> None:
        assert Money(Decimal("1"), currency="USD").currency == "USD"

    def test_binary_float_is_rejected(self) -> None:
        with pytest.raises(InvalidMoneyAmountError):
            Money(0.1)  # type: ignore[arg-type]

    def test_integer_is_rejected_even_when_exact(self) -> None:
        with pytest.raises(InvalidMoneyAmountError):
            Money(100000)  # type: ignore[arg-type]

    def test_non_finite_decimal_is_rejected(self) -> None:
        with pytest.raises(InvalidMoneyAmountError):
            Money(Decimal("NaN"))

    def test_infinity_is_rejected(self) -> None:
        with pytest.raises(InvalidMoneyAmountError):
            Money(Decimal("Infinity"))

    def test_empty_currency_is_rejected(self) -> None:
        with pytest.raises(InvalidMoneyAmountError):
            Money(Decimal("1"), currency="")

    def test_money_is_immutable(self) -> None:
        money = Money(Decimal("1.00"))

        with pytest.raises(Exception, match="cannot assign"):
            money.amount = Decimal("2.00")  # type: ignore[misc]


class TestMoneyArithmetic:
    def test_decimal_arithmetic_is_exact_without_implicit_rounding(self) -> None:
        # A float would produce 0.30000000000000004; Decimal keeps 0.3 exact.
        total = Money(Decimal("0.1")) + Money(Decimal("0.2"))

        assert total.amount == Decimal("0.3")

    def test_subtraction_is_exact(self) -> None:
        assert (Money(Decimal("10.00")) - Money(Decimal("0.01"))).amount == Decimal("9.99")

    def test_adding_mismatched_currencies_is_typed_error(self) -> None:
        with pytest.raises(CurrencyMismatchError):
            Money(Decimal("1"), currency="CNY") + Money(Decimal("1"), currency="USD")

    def test_subtracting_mismatched_currencies_is_typed_error(self) -> None:
        with pytest.raises(CurrencyMismatchError):
            Money(Decimal("1"), currency="CNY") - Money(Decimal("1"), currency="USD")

    def test_scaling_by_integer_quantity_is_exact(self) -> None:
        assert (Money(Decimal("12.34")) * 100).amount == Decimal("1234.00")

    def test_scaling_by_decimal_rate_is_exact(self) -> None:
        assert (Money(Decimal("10000")) * Decimal("0.0005")).amount == Decimal("5.0000")

    def test_scaling_by_float_is_rejected(self) -> None:
        with pytest.raises(InvalidMoneyAmountError):
            Money(Decimal("10")) * 0.5  # type: ignore[operator]

    def test_negation_keeps_currency(self) -> None:
        assert (-Money(Decimal("7"), currency="CNY")).amount == Decimal("-7")

    def test_ordering_requires_same_currency(self) -> None:
        assert Money(Decimal("1")) < Money(Decimal("2"))

        with pytest.raises(CurrencyMismatchError):
            _ = Money(Decimal("2"), currency="CNY") < Money(Decimal("1"), currency="USD")


class TestExplicitRounding:
    def test_rounding_never_happens_implicitly(self) -> None:
        scaled = Money(Decimal("10000")) * Decimal("0.0005")

        assert str(scaled.amount) == "5.0000"

    def test_half_up_quantization_to_cents(self) -> None:
        money = Money(Decimal("1.005"))

        rounded = money.quantized(Decimal("0.01"), rounding=ROUND_HALF_UP)

        assert rounded.amount == Decimal("1.01")
        assert rounded.currency == "CNY"

    def test_round_down_quantization_to_cents(self) -> None:
        rounded = Money(Decimal("1.005")).quantized(Decimal("0.01"), rounding=ROUND_DOWN)

        assert rounded.amount == Decimal("1.00")

    def test_quantization_does_not_mutate_original(self) -> None:
        money = Money(Decimal("1.005"))

        money.quantized(Decimal("0.01"), rounding=ROUND_HALF_UP)

        assert money.amount == Decimal("1.005")
