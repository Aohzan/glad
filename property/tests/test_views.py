"""Tests for property index view."""

import datetime
from decimal import Decimal

import pytest
from django.contrib.messages import get_messages
from django.urls import reverse
from moneyed import Money

from property.models import (
    Property,
    PropertyExpense,
    PropertyLoan,
    PropertyRevenue,
    PropertyValue,
)


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


@pytest.mark.django_db
def test_property_detail_view_projection_context(user_client):
    property_obj = Property.objects.create(
        name="City Loft",
        property_type=Property.APARTMENT,
        buying_value=Money(200000, "EUR"),
        buying_date=datetime.date.today() - datetime.timedelta(days=365),
        is_active=True,
        address="10 Rue de Rivoli, Paris",
    )
    PropertyLoan.objects.create(
        property=property_obj,
        name="Main Loan",
        lender="Bank",
        start_date=datetime.date.today() - datetime.timedelta(days=365),
        end_date=datetime.date.today() + datetime.timedelta(days=365 * 20),
        original_amount=Money(140000, "EUR"),
        monthly_payment=Money(820, "EUR"),
    )

    response = user_client.get(reverse("property:detail", args=[property_obj.pk]))

    assert response.status_code == 200
    assert response.context["property"] == property_obj
    assert len(response.context["projection_points"]) == 20
    assert response.context["projection_labels"] == [str(year) for year in range(1, 21)]


@pytest.mark.django_db
def test_property_detail_growth_rate_query_param(user_client):
    property_obj = Property.objects.create(
        name="Lake House",
        property_type=Property.HOUSE,
        buying_value=Money(300000, "EUR"),
        buying_date=datetime.date.today() - datetime.timedelta(days=600),
        is_active=True,
    )

    response = user_client.get(
        reverse("property:detail", args=[property_obj.pk]),
        {"growth_rate": "3.5"},
    )

    assert response.status_code == 200
    assert response.context["growth_rate"] == Decimal("0.035")
    assert response.context["growth_rate_percent"] == Decimal("3.500")


@pytest.mark.django_db
def test_property_detail_post_quick_create_value(user_client):
    property_obj = Property.objects.create(
        name="Family Home",
        property_type=Property.HOUSE,
        buying_value=Money(250000, "EUR"),
        buying_date=datetime.date.today() - datetime.timedelta(days=180),
        is_active=True,
    )

    response = user_client.post(
        reverse("property:detail", args=[property_obj.pk]),
        {
            "form_type": "value",
            "value_0": "275000",
            "value_1": "EUR",
            "valuation_date": datetime.date.today().isoformat(),
        },
    )

    assert response.status_code == 302
    assert PropertyValue.objects.filter(property=property_obj).count() == 1


@pytest.mark.django_db
def test_property_detail_post_quick_create_expense_and_revenue(user_client):
    property_obj = Property.objects.create(
        name="Rental Building",
        property_type=Property.APARTMENT,
        buying_value=Money(500000, "EUR"),
        buying_date=datetime.date.today() - datetime.timedelta(days=1200),
        is_active=True,
    )

    expense_response = user_client.post(
        reverse("property:detail", args=[property_obj.pk]),
        {
            "form_type": "expense",
            "expense_0": "250",
            "expense_1": "EUR",
            "expense_date": datetime.date.today().isoformat(),
            "expense_type": PropertyExpense.TAX,
            "description": "Monthly tax",
            "recurrence_type": PropertyExpense.NONE,
        },
    )
    revenue_response = user_client.post(
        reverse("property:detail", args=[property_obj.pk]),
        {
            "form_type": "revenue",
            "revenue_0": "1200",
            "revenue_1": "EUR",
            "revenue_date": datetime.date.today().isoformat(),
            "revenue_type": PropertyRevenue.RENT,
            "description": "Monthly rent",
            "recurrence_type": PropertyRevenue.NONE,
        },
    )

    assert expense_response.status_code == 302
    assert revenue_response.status_code == 302
    assert PropertyExpense.objects.filter(property=property_obj).count() == 1
    assert PropertyRevenue.objects.filter(property=property_obj).count() == 1


@pytest.mark.django_db
def test_edit_expense_unknown_id_uses_generic_not_found_message(user_client):
    property_obj = Property.objects.create(
        name="Studio",
        property_type=Property.APARTMENT,
        buying_value=Money(150000, "EUR"),
        buying_date=datetime.date.today() - datetime.timedelta(days=180),
        is_active=True,
    )

    response = user_client.get(
        reverse(
            "property:edit_expense",
            args=[property_obj.pk, 999999],
        )
    )

    assert response.status_code == 302
    messages = [str(message) for message in get_messages(response.wsgi_request)]
    assert "Expense not found." in messages


@pytest.mark.django_db
def test_edit_revenue_unknown_id_uses_generic_not_found_message(user_client):
    property_obj = Property.objects.create(
        name="Villa",
        property_type=Property.HOUSE,
        buying_value=Money(350000, "EUR"),
        buying_date=datetime.date.today() - datetime.timedelta(days=250),
        is_active=True,
    )

    response = user_client.get(
        reverse(
            "property:edit_revenue",
            args=[property_obj.pk, 999999],
        )
    )

    assert response.status_code == 302
    messages = [str(message) for message in get_messages(response.wsgi_request)]
    assert "Revenue not found." in messages
