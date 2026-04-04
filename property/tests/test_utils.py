"""Tests for property utility classes."""

import datetime
from decimal import Decimal
from typing import cast

import pytest
from moneyed import Money

from property.models import Property
from property.utils import (
    PropertyProgression,
    PropertyRentability,
    add_months_safe,
    add_years_safe,
    build_loan_monthly_maps,
    generate_recurring_occurrences,
    iter_month_starts,
    month_start,
)


def test_property_progression_positive_case():
    progression = PropertyProgression(
        current_value=Money(120000, "EUR"),
        old_value=Money(100000, "EUR"),
    )
    assert progression.progression == 20
    assert progression.css_class == "text-success"
    assert str(progression) == "20% (20000.0)"


def test_property_progression_negative_case():
    progression = PropertyProgression(
        current_value=Money(90000, "EUR"),
        old_value=Money(100000, "EUR"),
    )
    assert progression.progression == -10
    assert progression.css_class == "text-danger"


def test_property_progression_zero_old_value_case():
    progression = PropertyProgression(
        current_value=Money(0, "EUR"),
        old_value=Money(0, "EUR"),
    )
    assert progression.progression == 0
    assert progression.css_class == "text-muted"


def test_property_rentability_not_implemented():
    with pytest.raises(NotImplementedError):
        PropertyRentability(property=cast(Property, object()))


def test_property_rentability_str_representation_without_init():
    rentability = PropertyRentability.__new__(PropertyRentability)
    rentability.rentability_percent = Decimal(5)
    assert str(rentability) == "5%"


def test_add_months_safe_clamps_end_of_month():
    result = add_months_safe(datetime.date(2025, 1, 31), 1)
    assert result == datetime.date(2025, 2, 28)


def test_add_years_safe_handles_leap_day():
    result = add_years_safe(datetime.date(2024, 2, 29), 1)
    assert result == datetime.date(2025, 2, 28)


def test_month_start_and_iter_month_starts():
    start = month_start(datetime.date(2025, 1, 18))
    end = month_start(datetime.date(2025, 3, 3))
    values = iter_month_starts(start, end)
    assert values == [
        datetime.date(2025, 1, 1),
        datetime.date(2025, 2, 1),
        datetime.date(2025, 3, 1),
    ]


def test_generate_recurring_occurrences_none_and_monthly_and_invalid_type():
    one_time = generate_recurring_occurrences(
        start_date=datetime.date(2025, 1, 1),
        amount=Money(100, "EUR"),
        recurrence_type="none",
        recurrence_none="none",
        recurrence_monthly="monthly",
        recurrence_yearly="yearly",
    )
    assert len(one_time) == 1
    assert one_time[0]["is_recurring"] is False

    monthly = generate_recurring_occurrences(
        start_date=datetime.date(2025, 1, 31),
        amount=Money(100, "EUR"),
        recurrence_type="monthly",
        recurrence_none="none",
        recurrence_monthly="monthly",
        recurrence_yearly="yearly",
        end_date=datetime.date(2025, 3, 31),
    )
    assert [item["date"] for item in monthly] == [
        datetime.date(2025, 1, 31),
        datetime.date(2025, 2, 28),
        datetime.date(2025, 3, 28),
    ]

    invalid_type = generate_recurring_occurrences(
        start_date=datetime.date(2025, 1, 1),
        amount=Money(100, "EUR"),
        recurrence_type="weekly",
        recurrence_none="none",
        recurrence_monthly="monthly",
        recurrence_yearly="yearly",
        end_date=datetime.date(2025, 12, 31),
    )
    assert len(invalid_type) == 1
    assert invalid_type[0]["is_recurring"] is False


def test_generate_recurring_occurrences_yearly_path():
    yearly = generate_recurring_occurrences(
        start_date=datetime.date(2024, 2, 29),
        amount=Money(100, "EUR"),
        recurrence_type="yearly",
        recurrence_none="none",
        recurrence_monthly="monthly",
        recurrence_yearly="yearly",
        end_date=datetime.date(2026, 3, 1),
    )
    assert [item["date"] for item in yearly] == [
        datetime.date(2024, 2, 29),
        datetime.date(2025, 2, 28),
        datetime.date(2026, 2, 28),
    ]


def test_build_loan_monthly_maps_handles_interest_and_negative_principal():
    interest_map, principal_map, insurance_map = build_loan_monthly_maps(
        start_date=datetime.date(2025, 1, 1),
        end_date=datetime.date(2025, 3, 1),
        original_amount=Decimal("1000"),
        monthly_payment=Decimal("10"),
        interest_rate=Decimal("24"),
        insurance_amount=Decimal("2"),
    )
    # monthly_rate=2%, so first month interest=20 and principal is clamped to 0
    assert interest_map[(2025, 1)] == Decimal("20")
    assert principal_map[(2025, 1)] == Decimal("0")
    assert insurance_map[(2025, 1)] == Decimal("2")


def test_build_loan_monthly_maps_handles_zero_duration():
    interest_map, principal_map, insurance_map = build_loan_monthly_maps(
        start_date=datetime.date(2025, 5, 1),
        end_date=datetime.date(2025, 4, 1),
        original_amount=Decimal("1000"),
        monthly_payment=Decimal("100"),
        interest_rate=None,
        insurance_amount=Decimal("0"),
    )
    assert interest_map == {}
    assert principal_map == {}
    assert insurance_map == {}
