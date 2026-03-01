"""Tests for CRUD views: delete views for lease, mandate, and cashflow service."""

import datetime
from decimal import Decimal

import pytest
from django.contrib.messages import get_messages
from django.urls import reverse
from moneyed import Money

from property.models import (
    Lease,
    ManagementMandate,
    Property,
    PropertyLedgerEntry,
    PropertyLoan,
    PropertyValue,
)
from property.services.cashflow import build_balance_sheet

# ─── Shared helpers ───────────────────────────────────────────────────────────


def _make_property():
    return Property.objects.create(
        name="Test Property",
        property_type=Property.APARTMENT,
        buying_value=Money(200000, "EUR"),
        buying_date=datetime.date(2020, 1, 1),
        is_active=True,
    )


def _make_lease(prop):
    return Lease.objects.create(
        property=prop,
        lease_type=Lease.LeaseType.EMPTY,
        start_date=datetime.date(2021, 1, 1),
        status=Lease.Status.ACTIVE,
        rent_amount=Money(800, "EUR"),
        first_name="Alice",
        last_name="Dupont",
    )


def _make_mandate(prop):
    return ManagementMandate.objects.create(
        property=prop,
        manager_name="Agence Immo",
        start_date=datetime.date(2021, 1, 1),
        fee_type=ManagementMandate.FeeType.PERCENTAGE,
        fee_percentage=Decimal("7.00"),
    )


# ─── delete_lease ─────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_delete_lease_requires_post(user_client):
    prop = _make_property()
    lease = _make_lease(prop)
    url = reverse(
        "property:delete_lease", kwargs={"property_pk": prop.pk, "lease_pk": lease.pk}
    )
    response = user_client.get(url)
    assert response.status_code == 302
    assert Lease.objects.filter(pk=lease.pk).exists()
    msgs = list(get_messages(response.wsgi_request))
    assert any("Invalid request method" in str(m) for m in msgs)


@pytest.mark.django_db
def test_delete_lease_post_deletes_and_redirects(user_client):
    prop = _make_property()
    lease = _make_lease(prop)
    url = reverse(
        "property:delete_lease", kwargs={"property_pk": prop.pk, "lease_pk": lease.pk}
    )
    response = user_client.post(url)
    assert response.status_code == 302
    assert not Lease.objects.filter(pk=lease.pk).exists()
    msgs = list(get_messages(response.wsgi_request))
    assert any("deleted" in str(m).lower() for m in msgs)


@pytest.mark.django_db
def test_delete_lease_nonexistent_returns_404(user_client):
    prop = _make_property()
    url = reverse(
        "property:delete_lease", kwargs={"property_pk": prop.pk, "lease_pk": 99999}
    )
    response = user_client.post(url)
    assert response.status_code == 404


# ─── delete_mandate ───────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_delete_mandate_requires_post(user_client):
    prop = _make_property()
    mandate = _make_mandate(prop)
    url = reverse(
        "property:delete_mandate",
        kwargs={"property_pk": prop.pk, "mandate_pk": mandate.pk},
    )
    response = user_client.get(url)
    assert response.status_code == 302
    assert ManagementMandate.objects.filter(pk=mandate.pk).exists()
    msgs = list(get_messages(response.wsgi_request))
    assert any("Invalid request method" in str(m) for m in msgs)


@pytest.mark.django_db
def test_delete_mandate_post_deletes_and_redirects(user_client):
    prop = _make_property()
    mandate = _make_mandate(prop)
    url = reverse(
        "property:delete_mandate",
        kwargs={"property_pk": prop.pk, "mandate_pk": mandate.pk},
    )
    response = user_client.post(url)
    assert response.status_code == 302
    assert not ManagementMandate.objects.filter(pk=mandate.pk).exists()
    msgs = list(get_messages(response.wsgi_request))
    assert any("deleted" in str(m).lower() for m in msgs)


@pytest.mark.django_db
def test_delete_mandate_nonexistent_returns_404(user_client):
    prop = _make_property()
    url = reverse(
        "property:delete_mandate",
        kwargs={"property_pk": prop.pk, "mandate_pk": 99999},
    )
    response = user_client.post(url)
    assert response.status_code == 404


# ─── edit_lease ───────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_edit_lease_get_renders_form(user_client):
    prop = _make_property()
    lease = _make_lease(prop)
    url = reverse(
        "property:edit_lease", kwargs={"property_pk": prop.pk, "lease_pk": lease.pk}
    )
    response = user_client.get(url)
    assert response.status_code == 200
    assert "form" in response.context


@pytest.mark.django_db
def test_new_lease_get_renders_empty_form(user_client):
    prop = _make_property()
    url = reverse("property:new_lease", kwargs={"property_pk": prop.pk})
    response = user_client.get(url)
    assert response.status_code == 200
    assert response.context["lease"] is None


@pytest.mark.django_db
def test_edit_lease_post_invalid_shows_error(user_client):
    prop = _make_property()
    url = reverse("property:new_lease", kwargs={"property_pk": prop.pk})
    response = user_client.post(url, {})
    assert response.status_code == 200
    msgs = list(get_messages(response.wsgi_request))
    assert any("correct" in str(m).lower() for m in msgs)


# ─── edit_mandate ─────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_edit_mandate_get_renders_form(user_client):
    prop = _make_property()
    mandate = _make_mandate(prop)
    url = reverse(
        "property:edit_mandate",
        kwargs={"property_pk": prop.pk, "mandate_pk": mandate.pk},
    )
    response = user_client.get(url)
    assert response.status_code == 200
    assert "form" in response.context


@pytest.mark.django_db
def test_new_mandate_get_renders_empty_form(user_client):
    prop = _make_property()
    url = reverse("property:new_mandate", kwargs={"property_pk": prop.pk})
    response = user_client.get(url)
    assert response.status_code == 200
    assert response.context["mandate"] is None


@pytest.mark.django_db
def test_edit_mandate_post_invalid_shows_error(user_client):
    prop = _make_property()
    url = reverse("property:new_mandate", kwargs={"property_pk": prop.pk})
    response = user_client.post(url, {})
    assert response.status_code == 200
    msgs = list(get_messages(response.wsgi_request))
    assert any("correct" in str(m).lower() for m in msgs)


# ─── _get_property_or_redirect helper ────────────────────────────────────────


@pytest.mark.django_db
def test_edit_ledger_entry_unknown_property_redirects(user_client):
    """_get_property_or_redirect returns redirect when property not found."""
    url = reverse("property:edit_entry", kwargs={"property_pk": 99999, "entry_pk": 1})
    response = user_client.get(url)
    assert response.status_code == 302
    msgs = list(get_messages(response.wsgi_request))
    assert any("not found" in str(m).lower() for m in msgs)


@pytest.mark.django_db
def test_delete_ledger_entry_unknown_property_redirects(user_client):
    """delete_ledger_entry redirects when property not found."""
    url = reverse("property:delete_entry", kwargs={"property_pk": 99999, "entry_pk": 1})
    response = user_client.post(url)
    assert response.status_code == 302


@pytest.mark.django_db
def test_delete_valuation_unknown_property_redirects(user_client):
    """delete_property_valuation redirects when property not found."""
    url = reverse(
        "property:delete_valuation",
        kwargs={"property_pk": 99999, "valuation_pk": 1},
    )
    response = user_client.post(url)
    assert response.status_code == 302


@pytest.mark.django_db
def test_delete_valuation_unknown_valuation_shows_error(user_client):
    prop = _make_property()
    url = reverse(
        "property:delete_valuation",
        kwargs={"property_pk": prop.pk, "valuation_pk": 99999},
    )
    response = user_client.post(url)
    assert response.status_code == 302
    msgs = list(get_messages(response.wsgi_request))
    assert any("not found" in str(m).lower() for m in msgs)


# ─── edit_ledger_entry POST path ─────────────────────────────────────────────


def _make_edit_entry_url(prop):
    entry = PropertyLedgerEntry.objects.create(
        property=prop,
        description="Rent",
        flow_type=PropertyLedgerEntry.FlowType.INCOME,
        management_category=PropertyLedgerEntry.ManagementCategory.RENT_COLLECTED,
        amount=Money(800, "EUR"),
        entry_date=datetime.date(2022, 3, 15),
    )
    url = reverse(
        "property:edit_entry", kwargs={"property_pk": prop.pk, "entry_pk": entry.pk}
    )
    return entry, url


@pytest.mark.django_db
def test_edit_ledger_entry_post_saves_and_redirects(user_client):
    prop = _make_property()
    entry, url = _make_edit_entry_url(prop)
    response = user_client.post(
        url,
        {
            "description": "Updated Rent",
            "flow_type": PropertyLedgerEntry.FlowType.INCOME,
            "management_category": PropertyLedgerEntry.ManagementCategory.RENT_COLLECTED,
            "amount_0": "900",
            "amount_1": "EUR",
            "entry_date": "2022-03-15",
            "recurrence_type": PropertyLedgerEntry.RecurrenceType.NONE,
        },
    )
    assert response.status_code == 302
    entry.refresh_from_db()
    assert entry.description == "Updated Rent"


@pytest.mark.django_db
def test_edit_ledger_entry_post_invalid_shows_error(user_client):
    prop = _make_property()
    _, url = _make_edit_entry_url(prop)
    response = user_client.post(url, {"description": ""})
    assert response.status_code == 200
    msgs = list(get_messages(response.wsgi_request))
    assert any("correct" in str(m).lower() for m in msgs)


@pytest.mark.django_db
def test_edit_ledger_entry_entry_not_found_redirects(user_client):
    prop = _make_property()
    url = reverse(
        "property:edit_entry", kwargs={"property_pk": prop.pk, "entry_pk": 99999}
    )
    response = user_client.get(url)
    assert response.status_code == 302
    msgs = list(get_messages(response.wsgi_request))
    assert any("not found" in str(m).lower() for m in msgs)


@pytest.mark.django_db
def test_delete_ledger_entry_entry_not_found_redirects(user_client):
    prop = _make_property()
    url = reverse(
        "property:delete_entry", kwargs={"property_pk": prop.pk, "entry_pk": 99999}
    )
    response = user_client.post(url)
    assert response.status_code == 302
    msgs = list(get_messages(response.wsgi_request))
    assert any("not found" in str(m).lower() for m in msgs)


# ─── edit_property POST path ──────────────────────────────────────────────────


@pytest.mark.django_db
def test_edit_property_post_invalid_shows_error(user_client):
    prop = _make_property()
    url = reverse("property:edit", kwargs={"pk": prop.pk})
    response = user_client.post(url, {"name": ""})
    assert response.status_code == 200
    msgs = list(get_messages(response.wsgi_request))
    assert any("correct" in str(m).lower() for m in msgs)


# ─── get_annual_cashflow service ──────────────────────────────────────────────


@pytest.mark.django_db
def test_get_annual_cashflow_with_entries():
    from property.services.cashflow import get_annual_cashflow

    prop = _make_property()
    PropertyLedgerEntry.objects.create(
        property=prop,
        description="Rent",
        flow_type=PropertyLedgerEntry.FlowType.INCOME,
        management_category=PropertyLedgerEntry.ManagementCategory.RENT_COLLECTED,
        amount=Money(800, "EUR"),
        entry_date=datetime.date(2022, 6, 1),
    )
    PropertyLedgerEntry.objects.create(
        property=prop,
        description="Repair",
        flow_type=PropertyLedgerEntry.FlowType.EXPENSE,
        management_category=PropertyLedgerEntry.ManagementCategory.MAINTENANCE,
        amount=Money(200, "EUR"),
        entry_date=datetime.date(2022, 6, 15),
    )
    result = get_annual_cashflow(prop.pk, 2022)
    assert result["income"] == Decimal("800")
    assert result["expenses"] == Decimal("200")
    assert result["net"] == Decimal("600")
    assert result["year"] == 2022


@pytest.mark.django_db
def test_get_annual_cashflow_empty():
    from property.services.cashflow import get_annual_cashflow

    prop = _make_property()
    result = get_annual_cashflow(prop.pk, 2022)
    assert result["income"] == Decimal("0")
    assert result["expenses"] == Decimal("0")
    assert result["net"] == Decimal("0")


@pytest.mark.django_db
def test_build_balance_sheet_with_standard_loan():
    """build_balance_sheet correctly handles standard (non-smoothed) loans."""
    prop = _make_property()
    PropertyLoan.objects.create(
        property=prop,
        name="Standard Loan",
        lender="Bank",
        start_date=datetime.date(2020, 1, 1),
        end_date=datetime.date(2025, 12, 31),
        original_amount=Money(100000, "EUR"),
        monthly_payment=Money(600, "EUR"),
        interest_rate=Decimal("0.02"),
    )

    result = build_balance_sheet(
        prop,
        datetime.date(2020, 1, 1),
        datetime.date(2020, 12, 31),
    )
    assert result["total_loan_interest"] > Decimal("0")
    assert result["total_loan_principal"] > Decimal("0")
    assert result["months_count"] == 12


@pytest.mark.django_db
def test_build_balance_sheet_skips_loan_without_payment():
    """build_balance_sheet skips loans with no monthly_payment and not smoothed."""
    prop = _make_property()
    # Loan with no monthly_payment and no schedule (not smoothed)
    PropertyLoan.objects.create(
        property=prop,
        name="Incomplete Loan",
        lender="Bank",
        start_date=datetime.date(2020, 1, 1),
        end_date=datetime.date(2025, 12, 31),
        original_amount=Money(100000, "EUR"),
        interest_rate=Decimal("0.02"),
    )

    result = build_balance_sheet(
        prop,
        datetime.date(2020, 1, 1),
        datetime.date(2020, 12, 31),
    )
    # No payment data → no loan costs
    assert result["total_loan_interest"] == Decimal("0")
    assert result["total_loan_principal"] == Decimal("0")


@pytest.mark.django_db
def test_build_balance_sheet_with_ledger_entries():
    """build_balance_sheet aggregates income and expense entries."""
    prop = _make_property()
    PropertyLedgerEntry.objects.create(
        property=prop,
        description="Rent",
        flow_type=PropertyLedgerEntry.FlowType.INCOME,
        management_category=PropertyLedgerEntry.ManagementCategory.RENT_COLLECTED,
        amount=Money(800, "EUR"),
        entry_date=datetime.date(2022, 3, 15),
    )
    PropertyLedgerEntry.objects.create(
        property=prop,
        description="Repair",
        flow_type=PropertyLedgerEntry.FlowType.EXPENSE,
        management_category=PropertyLedgerEntry.ManagementCategory.MAINTENANCE,
        amount=Money(200, "EUR"),
        entry_date=datetime.date(2022, 3, 20),
    )

    result = build_balance_sheet(
        prop,
        datetime.date(2022, 1, 1),
        datetime.date(2022, 12, 31),
    )
    assert result["total_income"] == Decimal("800")
    assert result["total_expenses"] == Decimal("200")
    assert result["net_cashflow"] == Decimal("600")
    assert result["months_with_rent"] == 1
    assert result["occupancy_rate"] > Decimal("0")


@pytest.mark.django_db
def test_build_balance_sheet_gross_yield():
    """build_balance_sheet computes gross_yield_annual when property has a value."""
    prop = _make_property()
    PropertyValue.objects.create(
        property=prop,
        value=Money(200000, "EUR"),
        valuation_date=datetime.date(2022, 1, 1),
    )
    PropertyLedgerEntry.objects.create(
        property=prop,
        description="Rent",
        flow_type=PropertyLedgerEntry.FlowType.INCOME,
        management_category=PropertyLedgerEntry.ManagementCategory.RENT_COLLECTED,
        amount=Money(800, "EUR"),
        entry_date=datetime.date(2022, 6, 1),
    )

    result = build_balance_sheet(
        prop,
        datetime.date(2022, 1, 1),
        datetime.date(2022, 12, 31),
    )
    assert result["gross_yield_annual"] is not None
    assert result["gross_yield_annual"] > Decimal("0")


# ─── detail_views: balance sheet range parsing ────────────────────────────────


@pytest.mark.django_db
def test_detail_view_balance_sheet_default_range(user_client):
    """No date params → default is current civil year (Jan 1 – Dec 31)."""
    prop = _make_property()
    url = reverse("property:panel_balance", kwargs={"pk": prop.pk})
    response = user_client.get(url)
    assert response.status_code == 200
    today = datetime.date.today()
    assert response.context["bs_date_from"] == datetime.date(today.year, 1, 1)
    assert response.context["bs_date_to"] == datetime.date(today.year, 12, 31)


@pytest.mark.django_db
def test_detail_view_balance_sheet_invalid_dates_use_defaults(user_client):
    """Invalid start_date/end_date params fall back to current-year defaults."""
    prop = _make_property()
    url = reverse("property:panel_balance", kwargs={"pk": prop.pk})
    response = user_client.get(url, {"start_date": "notadate", "end_date": "also-bad"})
    assert response.status_code == 200
    today = datetime.date.today()
    assert response.context["bs_date_from"] == datetime.date(today.year, 1, 1)
    assert response.context["bs_date_to"] == datetime.date(today.year, 12, 31)


@pytest.mark.django_db
def test_detail_view_balance_sheet_valid_date_range(user_client):
    """Valid start_date/end_date are normalised to month boundaries."""
    prop = _make_property()
    url = reverse("property:panel_balance", kwargs={"pk": prop.pk})
    # Supply mid-month dates; they must be clamped to month boundaries.
    response = user_client.get(
        url, {"start_date": "2023-04-15", "end_date": "2023-06-20"}
    )
    assert response.status_code == 200
    assert response.context["bs_date_from"] == datetime.date(2023, 4, 1)
    assert response.context["bs_date_to"] == datetime.date(2023, 6, 30)


@pytest.mark.django_db
def test_detail_view_balance_sheet_inverted_range_uses_defaults(user_client):
    """start_date > end_date falls back to current-year defaults."""
    prop = _make_property()
    url = reverse("property:panel_balance", kwargs={"pk": prop.pk})
    response = user_client.get(
        url, {"start_date": "2023-12-01", "end_date": "2023-01-31"}
    )
    assert response.status_code == 200
    today = datetime.date.today()
    assert response.context["bs_date_from"] == datetime.date(today.year, 1, 1)
    assert response.context["bs_date_to"] == datetime.date(today.year, 12, 31)


@pytest.mark.django_db
def test_detail_view_balance_sheet_full_year_range(user_client):
    """A full-year range (Jan 1 – Dec 31) is preserved correctly."""
    prop = _make_property()
    url = reverse("property:panel_balance", kwargs={"pk": prop.pk})
    response = user_client.get(
        url, {"start_date": "2023-01-01", "end_date": "2023-12-31"}
    )
    assert response.status_code == 200
    assert response.context["bs_date_from"] == datetime.date(2023, 1, 1)
    assert response.context["bs_date_to"] == datetime.date(2023, 12, 31)
