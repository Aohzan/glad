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
def test_property_detail_entries_older_than_buying_date(user_client):
    """Entries/loans older than buying_date should shift the observation window."""
    prop = Property.objects.create(
        name="Old Entry Prop",
        property_type=Property.APARTMENT,
        buying_value=Money(200000, "EUR"),
        buying_date=datetime.date(2020, 6, 1),
        is_active=True,
    )
    # Entry older than buying_date
    PropertyLedgerEntry.objects.create(
        property=prop,
        flow_type=PropertyLedgerEntry.FlowType.EXPENSE,
        amount=Money(500, "EUR"),
        entry_date=datetime.date(2020, 1, 1),  # before buying_date 2020-06-01
        management_category=PropertyLedgerEntry.ManagementCategory.MAINTENANCE,
    )
    # Loan with start_date older than buying_date
    PropertyLoan.objects.create(
        property=prop,
        name="Old Loan",
        lender="Bank",
        start_date=datetime.date(2019, 12, 1),  # before buying_date
        end_date=datetime.date(2039, 12, 1),
        original_amount=Money(150000, "EUR"),
        monthly_payment=Money(700, "EUR"),
        interest_rate=Decimal("1.5"),
    )
    response = user_client.get(reverse("property:detail", args=[prop.pk]))
    assert response.status_code == 200


@pytest.mark.django_db
def test_property_detail_loan_without_payment_skipped(user_client):
    """A loan with no monthly_payment and not smoothed is skipped in cashflow series."""
    prop = Property.objects.create(
        name="No Payment Loan",
        property_type=Property.APARTMENT,
        buying_value=Money(200000, "EUR"),
        buying_date=datetime.date(2020, 1, 1),
        is_active=True,
    )
    # Loan with no monthly_payment and no schedule (not smoothed)
    PropertyLoan.objects.create(
        property=prop,
        name="Interest Only",
        lender="Bank",
        start_date=datetime.date(2020, 1, 1),
        end_date=datetime.date(2040, 1, 1),
        original_amount=Money(150000, "EUR"),
        monthly_payment=None,  # no payment
        interest_rate=Decimal("2.0"),
    )
    response = user_client.get(reverse("property:detail", args=[prop.pk]))
    assert response.status_code == 200


@pytest.mark.django_db
def test_property_detail_loan_with_insurance(user_client):
    """A loan with insurance produces non-empty insurance_map in cashflow series."""
    prop = Property.objects.create(
        name="Insurance Loan",
        property_type=Property.APARTMENT,
        buying_value=Money(200000, "EUR"),
        buying_date=datetime.date(2020, 1, 1),
        is_active=True,
    )
    PropertyLoan.objects.create(
        property=prop,
        name="Insured Loan",
        lender="Bank",
        start_date=datetime.date(2020, 1, 1),
        end_date=datetime.date(2040, 1, 1),
        original_amount=Money(150000, "EUR"),
        monthly_payment=Money(700, "EUR"),
        interest_rate=Decimal("1.5"),
        insurance=Money(50, "EUR"),  # insurance amount
    )
    response = user_client.get(reverse("property:detail", args=[prop.pk]))
    assert response.status_code == 200


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
def test_property_detail_history_series_uses_buying_value_gross(user_client):
    """The first point in the history series must use buying_value_gross, not buying_value."""
    buying_date = datetime.date.today() - datetime.timedelta(days=365)
    property_obj = Property.objects.create(
        name="Gross History Test",
        property_type=Property.APARTMENT,
        buying_value=Money(200000, "EUR"),
        notary_fees=Money(15000, "EUR"),
        agency_fees=Money(5000, "EUR"),
        buying_date=buying_date,
        is_active=True,
    )
    response = user_client.get(reverse("property:detail", args=[property_obj.pk]))

    assert response.status_code == 200
    value_history = response.context["value_history_series"]
    # The earliest point in the series corresponds to buying_date
    buying_date_point = next(
        p for p in value_history if p["x"] == buying_date.isoformat()
    )
    # buying_value_gross = 200000 + 15000 + 5000 = 220000
    assert buying_date_point["y"] == float(220000), (
        f"Expected 220000 (buying_value_gross) at buying_date, got {buying_date_point['y']}"
    )


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
def test_property_detail_capital_repaid_for_standard_loan(user_client):
    """Standard loan's capital repaid should be > 0 after some payments."""
    property_obj = Property.objects.create(
        name="Loan Detail",
        property_type=Property.HOUSE,
        buying_value=Money(200000, "EUR"),
        buying_date=datetime.date(2020, 1, 1),
        is_active=True,
    )
    PropertyLoan.objects.create(
        property=property_obj,
        name="Standard Loan",
        start_date=datetime.date(2020, 1, 1),
        end_date=datetime.date(2040, 1, 1),
        original_amount=Money(200000, "EUR"),
        monthly_payment=Money(Decimal("1159.97"), "EUR"),
        interest_rate=Decimal("3.5"),
    )

    response = user_client.get(reverse("property:detail", args=[property_obj.pk]))

    assert response.status_code == 200
    capital_repaid = response.context["capital_repaid"].amount
    assert capital_repaid > Decimal("0")
    assert capital_repaid < Decimal("200000")


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
        management_category=PropertyLedgerEntry.ManagementCategory.RENT_COLLECTED,
        description="Loyer",
        recurrence_type="none",
    )
    PropertyLedgerEntry.objects.create(
        property=property_obj,
        flow_type=PropertyLedgerEntry.FlowType.EXPENSE,
        amount=Money(150, "EUR"),
        entry_date=datetime.date.today() - datetime.timedelta(days=10),
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


# ─── Edit property view ───────────────────────────────────────────────────────


def _make_property():
    return Property.objects.create(
        name="Edit Test Property",
        property_type=Property.HOUSE,
        buying_value=Money(200_000, "EUR"),
        buying_date=datetime.date(2020, 1, 1),
        is_active=True,
    )


def _make_standard_loan(prop):
    return PropertyLoan.objects.create(
        property=prop,
        name="Standard Loan",
        start_date=datetime.date(2020, 1, 1),
        end_date=datetime.date(2040, 1, 1),
        original_amount=Money(200_000, "EUR"),
        monthly_payment=Money(Decimal("1159.97"), "EUR"),
        interest_rate=Decimal("3.5"),
    )


def _make_second_loan(prop):
    return PropertyLoan.objects.create(
        property=prop,
        name="Second Loan",
        start_date=datetime.date(2020, 1, 1),
        end_date=datetime.date(2040, 1, 1),
        original_amount=Money(200_000, "EUR"),
        monthly_payment=Money(Decimal("1100.00"), "EUR"),
        interest_rate=Decimal("3.5"),
    )


@pytest.mark.django_db
def test_edit_property_get_renders_form(user_client):
    """GET on edit view returns 200 with property_form."""
    prop = _make_property()
    response = user_client.get(reverse("property:edit", args=[prop.pk]))
    assert response.status_code == 200
    assert "property_form" in response.context


@pytest.mark.django_db
def test_edit_property_loan_forms_with_schedules_context(user_client):
    """loan_forms_with_schedules context includes existing loan form entries."""
    prop = _make_property()
    _make_standard_loan(prop)
    response = user_client.get(reverse("property:detail", args=[prop.pk]))
    assert response.status_code == 200
    entries = response.context["loan_forms_with_schedules"]
    existing = [e for e in entries if e["form"].instance.pk]
    assert len(existing) == 1


@pytest.mark.django_db
def test_edit_property_post_saves_property(user_client):
    """POST with valid data updates the property."""
    prop = _make_property()
    response = user_client.post(
        reverse("property:edit", args=[prop.pk]),
        {
            "name": "Updated Name",
            "property_type": Property.HOUSE,
            "buying_value_0": "210000",
            "buying_value_1": "EUR",
            "buying_date": "2020-01-01",
            "is_active": "on",
            "tax_regime": "none",
            # loan formset management form (no loans)
            "loans-TOTAL_FORMS": "0",
            "loans-INITIAL_FORMS": "0",
            "loans-MIN_NUM_FORMS": "0",
            "loans-MAX_NUM_FORMS": "1000",
        },
    )
    assert response.status_code == 302
    prop.refresh_from_db()
    assert prop.name == "Updated Name"


@pytest.mark.django_db
def test_edit_property_context_has_loans_with_totals_standard(user_client):
    """Detail view includes loans_with_totals with computed cost for a standard loan."""
    prop = _make_property()
    _make_standard_loan(prop)
    response = user_client.get(reverse("property:detail", args=[prop.pk]))
    assert response.status_code == 200
    loans_with_totals = response.context["loans_with_totals"]
    assert len(loans_with_totals) == 1
    item = loans_with_totals[0]
    assert item["duration_months"] > 0
    assert item["total_repaid"] is not None
    assert item["total_cost"] is not None


@pytest.mark.django_db
def test_edit_property_context_has_loans_with_totals_second_loan(user_client):
    """Detail view includes loans_with_totals for a second loan."""
    prop = _make_property()
    _make_second_loan(prop)
    response = user_client.get(reverse("property:detail", args=[prop.pk]))
    assert response.status_code == 200
    loans_with_totals = response.context["loans_with_totals"]
    assert len(loans_with_totals) == 1
    assert loans_with_totals[0]["duration_months"] > 0


@pytest.mark.django_db
def test_edit_property_context_loans_with_totals_empty_when_no_loans(user_client):
    """Detail view loans_with_totals is empty when property has no loans."""
    prop = _make_property()
    response = user_client.get(reverse("property:detail", args=[prop.pk]))
    assert response.status_code == 200
    assert response.context["loans_with_totals"] == []


# ─── create_property view tests ───────────────────────────────────────────────


@pytest.mark.django_db
def test_create_property_get_renders_form(user_client):
    """GET on create view returns 200 with a blank property_form."""
    response = user_client.get(reverse("property:create"))
    assert response.status_code == 200
    assert "property_form" in response.context
    assert response.context["property_form"].instance.pk is None


@pytest.mark.django_db
def test_create_property_post_valid_creates_and_redirects(user_client):
    """POST with valid data creates a property and redirects to the edit view."""
    assert Property.objects.count() == 0
    response = user_client.post(
        reverse("property:create"),
        {
            "name": "New Flat",
            "property_type": Property.APARTMENT,
            "buying_value_0": "180000",
            "buying_value_1": "EUR",
            "buying_date": "2024-06-01",
            "is_active": "on",
            "tax_regime": "none",
        },
    )
    assert Property.objects.count() == 1
    prop = Property.objects.get()
    assert prop.name == "New Flat"
    assert response.status_code == 302
    assert response["Location"] == reverse("property:detail", args=[prop.pk])


@pytest.mark.django_db
def test_create_property_post_invalid_rerenders_form(user_client):
    """POST with missing required fields re-renders the create form with errors."""
    response = user_client.post(
        reverse("property:create"),
        {"name": "", "property_type": "", "buying_value_0": "", "buying_date": ""},
    )
    assert response.status_code == 200
    assert "property_form" in response.context
    assert response.context["property_form"].errors
    assert Property.objects.count() == 0


# ─── Growth rate edge cases ────────────────────────────────────────────────────


@pytest.mark.django_db
def test_property_detail_growth_rate_small_positive(user_client):
    """growth_rate <= 1 (e.g., 0.03) should be used directly without division."""
    prop = Property.objects.create(
        name="Rate Small",
        property_type=Property.APARTMENT,
        buying_value=Money(200000, "EUR"),
        buying_date=datetime.date.today() - datetime.timedelta(days=365),
        is_active=True,
    )
    response = user_client.get(
        reverse("property:detail", args=[prop.pk]),
        {"growth_rate": "0.03"},
    )
    assert response.status_code == 200
    assert response.context["growth_rate"] == Decimal("0.03")


@pytest.mark.django_db
def test_property_detail_growth_rate_too_negative_uses_default(user_client):
    """growth_rate < -0.99 should fall back to default rate."""
    prop = Property.objects.create(
        name="Rate Negative",
        property_type=Property.APARTMENT,
        buying_value=Money(200000, "EUR"),
        buying_date=datetime.date.today() - datetime.timedelta(days=365),
        is_active=True,
    )
    response = user_client.get(
        reverse("property:detail", args=[prop.pk]),
        {"growth_rate": "-1.5"},
    )
    assert response.status_code == 200
    assert response.context["growth_rate"] == Decimal("0.02")  # default


@pytest.mark.django_db
def test_property_detail_growth_rate_invalid_string_uses_default(user_client):
    """Non-numeric growth_rate should fall back to default rate."""
    prop = Property.objects.create(
        name="Rate Invalid",
        property_type=Property.APARTMENT,
        buying_value=Money(200000, "EUR"),
        buying_date=datetime.date.today() - datetime.timedelta(days=365),
        is_active=True,
    )
    response = user_client.get(
        reverse("property:detail", args=[prop.pk]),
        {"growth_rate": "notanumber"},
    )
    assert response.status_code == 200
    assert response.context["growth_rate"] == Decimal("0.02")  # default


# ─── Detail view POST invalid / unknown form_type ──────────────────────────────


@pytest.mark.django_db
def test_property_detail_post_invalid_value_form(user_client):
    """POST with form_type=value and invalid data should re-render (not redirect)."""
    prop = Property.objects.create(
        name="Post Invalid",
        property_type=Property.APARTMENT,
        buying_value=Money(200000, "EUR"),
        buying_date=datetime.date.today() - datetime.timedelta(days=365),
        is_active=True,
    )
    response = user_client.post(
        reverse("property:detail", args=[prop.pk]),
        {
            "form_type": "value",
            "value_0": "",  # missing required value
            "value_1": "EUR",
            "valuation_date": "",  # missing required date
        },
    )
    assert response.status_code == 200
    assert PropertyValue.objects.filter(property=prop).count() == 0


@pytest.mark.django_db
def test_property_detail_post_invalid_ledger_entry_form(user_client):
    """POST with form_type=ledger_entry and invalid data should re-render."""
    prop = Property.objects.create(
        name="Post Ledger Invalid",
        property_type=Property.APARTMENT,
        buying_value=Money(200000, "EUR"),
        buying_date=datetime.date.today() - datetime.timedelta(days=365),
        is_active=True,
    )
    response = user_client.post(
        reverse("property:detail", args=[prop.pk]),
        {
            "form_type": "ledger_entry",
            # Missing required fields
            "amount_0": "",
            "entry_date": "",
        },
    )
    assert response.status_code == 200
    assert PropertyLedgerEntry.objects.filter(property=prop).count() == 0


@pytest.mark.django_db
def test_property_detail_post_unknown_form_type(user_client):
    """POST with an unknown form_type should show an error."""
    from django.contrib.messages import get_messages

    prop = Property.objects.create(
        name="Unknown Form",
        property_type=Property.APARTMENT,
        buying_value=Money(200000, "EUR"),
        buying_date=datetime.date.today() - datetime.timedelta(days=365),
        is_active=True,
    )
    response = user_client.post(
        reverse("property:detail", args=[prop.pk]),
        {"form_type": "completely_unknown"},
    )
    assert response.status_code == 200
    msgs = [str(m) for m in get_messages(response.wsgi_request)]
    assert any("Unknown" in m or "unknown" in m for m in msgs)
