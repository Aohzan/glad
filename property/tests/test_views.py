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
    PropertyLoanSchedule,
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
def test_property_detail_capital_repaid_uses_schedule_for_smoothed_loans(user_client):
    """Smoothed loans must not be treated as fully repaid only from end_date."""
    property_obj = Property.objects.create(
        name="Schedule Detail",
        property_type=Property.HOUSE,
        buying_value=Money(200000, "EUR"),
        buying_date=datetime.date(2020, 1, 1),
        is_active=True,
    )
    loan = PropertyLoan.objects.create(
        property=property_obj,
        name="Smoothed Loan",
        start_date=datetime.date(2020, 1, 1),
        # Intentionally inconsistent with schedule duration (too short)
        end_date=datetime.date(2021, 1, 1),
        original_amount=Money(200000, "EUR"),
        interest_rate=Decimal("3.5"),
    )
    PropertyLoanSchedule.objects.create(
        loan=loan,
        order=1,
        count=60,
        amount=Money(Decimal("800.00"), "EUR"),
    )
    PropertyLoanSchedule.objects.create(
        loan=loan,
        order=2,
        count=180,
        amount=Money(Decimal("1200.00"), "EUR"),
    )

    response = user_client.get(reverse("property:detail", args=[property_obj.pk]))

    assert response.status_code == 200
    capital_repaid = response.context["capital_repaid"].amount
    assert capital_repaid > Decimal("0")
    assert capital_repaid < loan.original_amount.amount


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


def _make_smoothed_loan(prop):
    loan = PropertyLoan.objects.create(
        property=prop,
        name="Smoothed Loan",
        start_date=datetime.date(2020, 1, 1),
        end_date=datetime.date(2040, 1, 1),
        original_amount=Money(200_000, "EUR"),
        interest_rate=Decimal("3.5"),
    )
    PropertyLoanSchedule.objects.create(
        loan=loan, order=1, count=60, amount=Money(Decimal("800.00"), "EUR")
    )
    PropertyLoanSchedule.objects.create(
        loan=loan, order=2, count=180, amount=Money(Decimal("1200.00"), "EUR")
    )
    return loan


@pytest.mark.django_db
def test_edit_property_get_renders_form(user_client):
    """GET on edit view returns 200 with property_form and loan_formset."""
    prop = _make_property()
    response = user_client.get(reverse("property:edit", args=[prop.pk]))
    assert response.status_code == 200
    assert "property_form" in response.context
    assert "loan_formset" in response.context
    assert "loan_forms_with_schedules" in response.context


@pytest.mark.django_db
def test_edit_property_standard_loan_is_not_smoothed(user_client):
    """Standard loan must have is_smoothed=False in context."""
    prop = _make_property()
    _make_standard_loan(prop)
    response = user_client.get(reverse("property:edit", args=[prop.pk]))
    assert response.status_code == 200
    entries = response.context["loan_forms_with_schedules"]
    # First entry is the existing standard loan
    existing = [e for e in entries if e["form"].instance.pk]
    assert len(existing) == 1
    assert existing[0]["is_smoothed"] is False


@pytest.mark.django_db
def test_edit_property_smoothed_loan_is_smoothed(user_client):
    """Smoothed loan must have is_smoothed=True in context."""
    prop = _make_property()
    _make_smoothed_loan(prop)
    response = user_client.get(reverse("property:edit", args=[prop.pk]))
    assert response.status_code == 200
    entries = response.context["loan_forms_with_schedules"]
    existing = [e for e in entries if e["form"].instance.pk]
    assert len(existing) == 1
    assert existing[0]["is_smoothed"] is True


@pytest.mark.django_db
def test_edit_property_new_loan_entry_is_not_smoothed(user_client):
    """The extra (new) loan form entry must have is_smoothed=False."""
    prop = _make_property()
    response = user_client.get(reverse("property:edit", args=[prop.pk]))
    assert response.status_code == 200
    entries = response.context["loan_forms_with_schedules"]
    new_entries = [e for e in entries if not e["form"].instance.pk]
    assert len(new_entries) >= 1
    for entry in new_entries:
        assert entry["is_smoothed"] is False


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
def test_edit_property_delete_schedule_row(user_client):
    """Marking a schedule row for deletion removes it from the database."""
    prop = _make_property()
    loan = _make_smoothed_loan(prop)
    schedules = list(PropertyLoanSchedule.objects.filter(loan=loan).order_by("order"))
    assert len(schedules) == 2

    schedule_to_delete = schedules[0]
    schedule_to_keep = schedules[1]
    prefix = f"schedules_{loan.pk}"

    response = user_client.post(
        reverse("property:edit", args=[prop.pk]),
        {
            # Property form
            "name": prop.name,
            "property_type": prop.property_type,
            "buying_value_0": str(int(prop.buying_value.amount)),
            "buying_value_1": "EUR",
            "buying_date": prop.buying_date.isoformat(),
            "is_active": "on",
            # Loan formset management form
            "loans-TOTAL_FORMS": "1",
            "loans-INITIAL_FORMS": "1",
            "loans-MIN_NUM_FORMS": "0",
            "loans-MAX_NUM_FORMS": "1000",
            # Loan form
            "loans-0-id": str(loan.pk),
            "loans-0-name": loan.name,
            "loans-0-start_date": loan.start_date.isoformat(),
            "loans-0-duration_months": str(loan.get_duration_months()),
            "loans-0-original_amount_0": str(int(loan.original_amount.amount)),
            "loans-0-original_amount_1": "EUR",
            "loans-0-interest_rate": str(loan.interest_rate),
            # Schedule formset management form
            f"{prefix}-TOTAL_FORMS": "2",
            f"{prefix}-INITIAL_FORMS": "2",
            f"{prefix}-MIN_NUM_FORMS": "0",
            f"{prefix}-MAX_NUM_FORMS": "1000",
            # Schedule row 0 – mark for deletion
            f"{prefix}-0-id": str(schedule_to_delete.pk),
            f"{prefix}-0-order": str(schedule_to_delete.order),
            f"{prefix}-0-count": str(schedule_to_delete.count),
            f"{prefix}-0-amount_0": str(schedule_to_delete.amount.amount),
            f"{prefix}-0-amount_1": "EUR",
            f"{prefix}-0-DELETE": "on",
            # Schedule row 1 – keep
            f"{prefix}-1-id": str(schedule_to_keep.pk),
            f"{prefix}-1-order": str(schedule_to_keep.order),
            f"{prefix}-1-count": str(schedule_to_keep.count),
            f"{prefix}-1-amount_0": str(schedule_to_keep.amount.amount),
            f"{prefix}-1-amount_1": "EUR",
        },
    )
    assert response.status_code == 302
    assert not PropertyLoanSchedule.objects.filter(pk=schedule_to_delete.pk).exists()
    assert PropertyLoanSchedule.objects.filter(pk=schedule_to_keep.pk).exists()
