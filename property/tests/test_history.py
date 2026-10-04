"""Tests for the bulk property valuations of property.services.history."""

import datetime
from decimal import Decimal

import pytest
from moneyed import Money

from property.models import Property, PropertyLoan, PropertyValue
from property.services.history import PropertyValues

D = datetime.date
MOMENTS = [
    D(2020, 6, 1),
    D(2021, 3, 1),
    D(2021, 3, 2),
    datetime.datetime(2021, 3, 1, 23, 59),
    D(2024, 1, 1),
]


@pytest.fixture
def valued_property():
    """Property revalued twice, with a loan running over the dates of MOMENTS."""
    prop = Property.objects.create(
        name="History flat",
        property_type=Property.APARTMENT,
        buying_value=Money(200000, "EUR"),
        buying_date=D(2020, 1, 1),
    )
    PropertyValue.objects.create(
        property=prop, value=Money(210000, "EUR"), valuation_date=D(2021, 3, 1)
    )
    PropertyValue.objects.create(
        property=prop, value=Money(230000, "EUR"), valuation_date=D(2023, 6, 1)
    )
    PropertyLoan.objects.create(
        property=prop,
        name="History loan",
        start_date=D(2020, 1, 1),
        end_date=D(2040, 1, 1),
        original_amount=Money(150000, "EUR"),
        monthly_payment=Money(Decimal("723.82"), "EUR"),
        interest_rate=Decimal("1.5"),
    )
    return Property.objects.prefetch_related("loans__amortization_entries").get(
        pk=prop.pk
    )


@pytest.mark.django_db
def test_values_match_get_value(valued_property):
    """Each value is the one get_value() returns at the same date or datetime."""
    values = PropertyValues([valued_property])

    assert [values.at(valued_property, m) for m in MOMENTS] == [
        valued_property.get_value(max_date=m).amount for m in MOMENTS
    ]
    assert [values.at(valued_property, m) for m in MOMENTS] == [
        Decimal(200000),
        Decimal(210000),
        Decimal(210000),
        Decimal(210000),
        Decimal(230000),
    ]


@pytest.mark.django_db
def test_net_values_match_net_value_at_date(valued_property):
    """The net value deducts the capital still owed on the loan."""
    values = PropertyValues([valued_property])
    days = [m for m in MOMENTS if not isinstance(m, datetime.datetime)]

    assert [values.net_at(valued_property, d) for d in days] == [
        valued_property.net_value_at_date(d).amount for d in days
    ]
    assert values.net_at(valued_property, D(2024, 1, 1)) < Decimal(230000)


@pytest.mark.django_db
def test_property_without_valuation_is_worth_its_buying_value(valued_property):
    valued_property.property_values.all().delete()

    assert PropertyValues([valued_property]).at(
        valued_property, D(2024, 1, 1)
    ) == Decimal(200000)


@pytest.mark.django_db
def test_valuations_are_read_once(valued_property, django_assert_num_queries):
    """With the loans prefetched, any number of dates runs no more queries."""
    with django_assert_num_queries(1):
        values = PropertyValues([valued_property])
    with django_assert_num_queries(0):
        for moment in MOMENTS:
            values.at(valued_property, moment)
            values.net_at(valued_property, D(2022, 1, 1))
