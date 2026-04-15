"""Tests for property views."""

import datetime
from decimal import Decimal

import pytest
from django.contrib.messages import get_messages
from django.urls import reverse
from moneyed import Money

from property.models import (
    Property,
    PropertyLedgerEntry,
    PropertyLoan,
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
def test_property_detail_post_quick_create_ledger_entry(user_client):
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
            "form_type": "ledger_entry",
            "flow_type": PropertyLedgerEntry.FlowType.EXPENSE,
            "amount_0": "250",
            "amount_1": "EUR",
            "entry_date": datetime.date.today().isoformat(),
            "tax_category": PropertyLedgerEntry.TaxCategory.TAXES,
            "management_category": PropertyLedgerEntry.ManagementCategory.PROPERTY_TAX,
            "description": "Taxe foncière",
            "recurrence_type": "none",
        },
    )
    assert expense_response.status_code == 302
    assert PropertyLedgerEntry.objects.filter(property=property_obj).count() == 1

    revenue_response = user_client.post(
        reverse("property:detail", args=[property_obj.pk]),
        {
            "form_type": "ledger_entry",
            "flow_type": PropertyLedgerEntry.FlowType.INCOME,
            "amount_0": "1200",
            "amount_1": "EUR",
            "entry_date": datetime.date.today().isoformat(),
            "tax_category": PropertyLedgerEntry.TaxCategory.RENT,
            "management_category": PropertyLedgerEntry.ManagementCategory.RENT_COLLECTED,
            "description": "Loyer mensuel",
            "recurrence_type": "monthly",
        },
    )
    assert revenue_response.status_code == 302
    assert PropertyLedgerEntry.objects.filter(property=property_obj).count() == 2


@pytest.mark.django_db
def test_edit_entry_unknown_id_uses_generic_not_found_message(user_client):
    property_obj = Property.objects.create(
        name="Studio",
        property_type=Property.APARTMENT,
        buying_value=Money(150000, "EUR"),
        buying_date=datetime.date.today() - datetime.timedelta(days=180),
        is_active=True,
    )

    response = user_client.get(
        reverse(
            "property:edit_entry",
            args=[property_obj.pk, 999999],
        )
    )

    assert response.status_code == 302
    msgs = [str(m) for m in get_messages(response.wsgi_request)]
    assert "Entry not found." in msgs


@pytest.mark.django_db
def test_delete_property_valuation_requires_post(user_client):
    property_obj = Property.objects.create(
        name="Test Property",
        property_type=Property.HOUSE,
        buying_value=Money(300000, "EUR"),
        buying_date=datetime.date.today() - datetime.timedelta(days=100),
        is_active=True,
    )
    valuation = PropertyValue.objects.create(
        property=property_obj,
        value=Money(350000, "EUR"),
        valuation_date=datetime.date.today(),
    )

    get_response = user_client.get(
        reverse("property:delete_valuation", args=[property_obj.pk, valuation.pk])
    )
    assert get_response.status_code == 302
    assert PropertyValue.objects.filter(pk=valuation.pk).exists()

    post_response = user_client.post(
        reverse("property:delete_valuation", args=[property_obj.pk, valuation.pk])
    )
    assert post_response.status_code == 302
    assert not PropertyValue.objects.filter(pk=valuation.pk).exists()


@pytest.mark.django_db
def test_property_quick_create_normalizes_currency(user_client):
    property_obj = Property.objects.create(
        name="Multi-Currency Property",
        property_type=Property.APARTMENT,
        buying_value=Money(150000, "EUR"),
        buying_date=datetime.date.today() - datetime.timedelta(days=100),
        is_active=True,
    )

    response = user_client.post(
        reverse("property:detail", args=[property_obj.pk]),
        {
            "form_type": "ledger_entry",
            "flow_type": PropertyLedgerEntry.FlowType.EXPENSE,
            "amount_0": "500",
            "amount_1": "EUR",
            "entry_date": datetime.date.today().isoformat(),
            "tax_category": PropertyLedgerEntry.TaxCategory.MAINTENANCE_REPAIRS,
            "management_category": PropertyLedgerEntry.ManagementCategory.MAINTENANCE,
            "description": "Maintenance cost",
            "recurrence_type": "none",
        },
    )
    assert response.status_code == 302
    entry = PropertyLedgerEntry.objects.filter(property=property_obj).first()
    assert entry is not None
    assert str(entry.amount.currency) == "EUR"


@pytest.mark.django_db
def test_property_detail_transactions_json_context(user_client):
    """Test that the detail view provides transactions_json for DataTables."""
    property_obj = Property.objects.create(
        name="JSON Test Property",
        property_type=Property.APARTMENT,
        buying_value=Money(200000, "EUR"),
        buying_date=datetime.date.today() - datetime.timedelta(days=400),
        is_active=True,
    )
    PropertyLedgerEntry.objects.create(
        property=property_obj,
        flow_type=PropertyLedgerEntry.FlowType.INCOME,
        amount=Money(1000, "EUR"),
        entry_date=datetime.date.today() - datetime.timedelta(days=30),
        tax_category=PropertyLedgerEntry.TaxCategory.RENT,
        management_category=PropertyLedgerEntry.ManagementCategory.RENT_COLLECTED,
        description="Loyer",
        recurrence_type="none",
    )
    PropertyLedgerEntry.objects.create(
        property=property_obj,
        flow_type=PropertyLedgerEntry.FlowType.EXPENSE,
        amount=Money(150, "EUR"),
        entry_date=datetime.date.today() - datetime.timedelta(days=10),
        tax_category=PropertyLedgerEntry.TaxCategory.INSURANCE,
        management_category=PropertyLedgerEntry.ManagementCategory.INSURANCE,
        description="Assurance",
        recurrence_type="none",
    )

    response = user_client.get(reverse("property:detail", args=[property_obj.pk]))

    assert response.status_code == 200
    tx_json = response.context["transactions_json"]
    assert isinstance(tx_json, list)
    assert len(tx_json) == 2

    # Each row must have the expected keys for DataTables
    for row in tx_json:
        assert "date" in row
        assert "kind" in row
        assert "category" in row
        assert "amount" in row
        assert "description" in row
        assert "is_recurring" in row
        assert "parent_id" in row

    # Sorted most-recent first
    assert tx_json[0]["date"] >= tx_json[1]["date"]

    # Amounts are floats (not Money objects)
    assert isinstance(tx_json[0]["amount"], float)

    # Dates are ISO strings
    import re

    assert re.match(r"\d{4}-\d{2}-\d{2}", tx_json[0]["date"])


@pytest.mark.django_db
def test_recurring_ledger_entry_generates_occurrences(user_client):
    """Test that recurring ledger entries generate occurrences correctly."""
    property_obj = Property.objects.create(
        name="Rental Property",
        property_type=Property.APARTMENT,
        buying_value=Money(200000, "EUR"),
        buying_date=datetime.date.today() - datetime.timedelta(days=200),
        is_active=True,
    )

    entry = PropertyLedgerEntry.objects.create(
        property=property_obj,
        flow_type=PropertyLedgerEntry.FlowType.INCOME,
        amount=Money(1000, "EUR"),
        entry_date=datetime.date.today(),
        tax_category=PropertyLedgerEntry.TaxCategory.RENT,
        management_category=PropertyLedgerEntry.ManagementCategory.RENT_COLLECTED,
        recurrence_type="monthly",
        recurrence_end_date=datetime.date.today() + datetime.timedelta(days=90),
    )

    occurrences = entry.generate_occurrences(
        end_date=datetime.date.today() + datetime.timedelta(days=90)
    )

    assert len(occurrences) >= 3
    assert all(occ["is_recurring"] for occ in occurrences)
    assert all(occ["amount"] == Money(1000, "EUR") for occ in occurrences)


@pytest.mark.django_db
def test_delete_ledger_entry_requires_post(user_client):
    """Test that ledger entry deletion requires POST."""
    property_obj = Property.objects.create(
        name="Test Property",
        property_type=Property.HOUSE,
        buying_value=Money(250000, "EUR"),
        buying_date=datetime.date.today() - datetime.timedelta(days=100),
        is_active=True,
    )
    entry = PropertyLedgerEntry.objects.create(
        property=property_obj,
        flow_type=PropertyLedgerEntry.FlowType.EXPENSE,
        amount=Money(1200, "EUR"),
        entry_date=datetime.date.today(),
        tax_category=PropertyLedgerEntry.TaxCategory.TAXES,
        management_category=PropertyLedgerEntry.ManagementCategory.PROPERTY_TAX,
        recurrence_type="none",
    )

    get_response = user_client.get(
        reverse("property:delete_entry", args=[property_obj.pk, entry.pk])
    )
    assert get_response.status_code == 302
    assert PropertyLedgerEntry.objects.filter(pk=entry.pk).exists()

    post_response = user_client.post(
        reverse("property:delete_entry", args=[property_obj.pk, entry.pk])
    )
    assert post_response.status_code == 302
    assert not PropertyLedgerEntry.objects.filter(pk=entry.pk).exists()
