"""Tests for property index view."""

import datetime

import pytest
from django.urls import reverse
from moneyed import Money

from property.models import Property, PropertyLoan, PropertyValue


@pytest.mark.django_db
def test_property_index_empty_state(user_client):
    response = user_client.get(reverse("property:index"))
    assert response.status_code == 200
    assert response.context["properties"] == []
    assert response.context["properties_months"] == []
    assert response.context["properties_gross_evolution"] == []
    assert response.context["properties_net_evolution"] == []


@pytest.mark.django_db
def test_property_index_with_active_and_inactive_properties(user_client):
    active_property = Property.objects.create(
        name="Main Home",
        property_type=Property.HOUSE,
        buying_value=Money(300000, "EUR"),
        buying_date=datetime.date.today() - datetime.timedelta(days=420),
        is_active=True,
    )
    PropertyValue.objects.create(
        property=active_property,
        value=Money(330000, "EUR"),
        valuation_date=datetime.date.today() - datetime.timedelta(days=20),
    )
    PropertyLoan.objects.create(
        property=active_property,
        name="Home Loan",
        lender="Bank",
        start_date=datetime.date.today() - datetime.timedelta(days=420),
        end_date=datetime.date.today() + datetime.timedelta(days=3650),
        original_amount=Money(200000, "EUR"),
        monthly_payment=Money(900, "EUR"),
    )

    Property.objects.create(
        name="Old Flat",
        property_type=Property.APARTMENT,
        buying_value=Money(150000, "EUR"),
        buying_date=datetime.date.today() - datetime.timedelta(days=1200),
        is_active=False,
    )

    response = user_client.get(reverse("property:index"))

    assert response.status_code == 200
    assert len(response.context["properties"]) == 2
    assert response.context["inactive_properties_count"] == 1
    assert response.context["total_gross_value"].amount >= 300000
    assert response.context["total_net_value"].amount >= 0
    assert len(response.context["properties_months"]) >= 1
    assert len(response.context["properties_months"]) == len(
        response.context["properties_gross_evolution"]
    )
    assert len(response.context["properties_months"]) == len(
        response.context["properties_net_evolution"]
    )


@pytest.mark.django_db
def test_property_index_handles_property_calculation_exception(
    user_client, monkeypatch
):
    Property.objects.create(
        name="Broken Home",
        property_type=Property.HOUSE,
        buying_value=Money(100000, "EUR"),
        buying_date=datetime.date.today() - datetime.timedelta(days=60),
        is_active=True,
    )

    original_get_value = Property.get_value

    def _patched_get_value(self, max_date=None):
        if max_date is not None:
            raise RuntimeError("boom")
        return original_get_value(self, max_date=max_date)

    monkeypatch.setattr(Property, "get_value", _patched_get_value)

    response = user_client.get(reverse("property:index"))
    assert response.status_code == 200
