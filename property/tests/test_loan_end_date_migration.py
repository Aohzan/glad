"""Tests for the migration moving the loan end dates to the last installment."""

import datetime
import importlib
from decimal import Decimal

import pytest
from django.apps import apps
from moneyed import Money

from property.models import Property, PropertyLoan

migration = importlib.import_module(
    "property.migrations.0015_loan_end_date_last_installment"
)


def _loan(prop, start, end, first_payment_date=None) -> PropertyLoan:
    return PropertyLoan.objects.create(
        property=prop,
        start_date=start,
        end_date=end,
        first_payment_date=first_payment_date,
        original_amount=Money(100000, "EUR"),
        interest_rate=Decimal("3.5"),
    )


@pytest.mark.django_db
def test_end_date_moves_to_the_last_installment():
    prop = Property.objects.create(
        name="Flat",
        property_type=Property.APARTMENT,
        buying_value=Money(150000, "EUR"),
        buying_date=datetime.date(2020, 1, 1),
    )
    # 240 months saved by the old form as start + 240 months.
    late = _loan(
        prop,
        datetime.date(2020, 1, 25),
        datetime.date(2040, 1, 25),
        first_payment_date=datetime.date(2020, 3, 5),
    )
    regular = _loan(
        prop,
        datetime.date(2020, 1, 15),
        datetime.date(2040, 1, 15),
        first_payment_date=datetime.date(2020, 2, 15),
    )
    without = _loan(prop, datetime.date(2020, 1, 15), datetime.date(2040, 1, 15))

    migration.end_on_last_installment(apps, None)

    for loan in (late, regular, without):
        loan.refresh_from_db()
        assert loan.get_duration_months() == 240
    assert late.end_date == datetime.date(2040, 2, 5)
    assert regular.end_date == datetime.date(2040, 1, 15)
    assert without.end_date == datetime.date(2040, 1, 15)

    migration.end_after_duration(apps, None)

    late.refresh_from_db()
    assert late.end_date == datetime.date(2040, 1, 25)


def test_add_months_clamps_to_the_month_end():
    assert migration._add_months(datetime.date(2020, 1, 31), 1) == datetime.date(
        2020, 2, 29
    )
    assert migration._add_months(datetime.date(2020, 11, 30), 14) == datetime.date(
        2022, 1, 30
    )
