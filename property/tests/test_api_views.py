"""Tests for property/views/api_views.py and new Property model helpers."""

import datetime
from decimal import Decimal

import pytest
from django.urls import reverse
from moneyed import Money

from property.models import Property, PropertyLoan, PropertyValue
from property.models.lease import Lease
from property.models.ledger import PropertyLedgerEntry

# ── fixtures ───────────────────────────────────────────────────────────────


@pytest.fixture
def prop():
    return Property.objects.create(
        name="Test Flat",
        address="1 Rue de la Paix, Paris",
        property_type=Property.APARTMENT,
        buying_value=Money(200000, "EUR"),
        notary_fees=Money(15000, "EUR"),
        buying_date=datetime.date(2020, 1, 1),
        floor_area=Decimal("65.0"),
        number_of_rooms=3,
        is_active=True,
    )


@pytest.fixture
def loan(prop):
    return PropertyLoan.objects.create(
        property=prop,
        name="Main loan",
        lender="BNP",
        start_date=datetime.date(2020, 1, 1),
        end_date=datetime.date(2045, 1, 1),
        original_amount=Money(160000, "EUR"),
        monthly_payment=Money(700, "EUR"),
        interest_rate=Decimal("1.5"),
        insurance_rate=Decimal("0.2"),
    )


@pytest.fixture
def valuation(prop):
    return PropertyValue.objects.create(
        property=prop,
        value=Money(230000, "EUR"),
        valuation_date=datetime.date(2024, 1, 1),
    )


@pytest.fixture
def active_lease(prop):
    return Lease.objects.create(
        property=prop,
        first_name="Jean",
        last_name="Dupont",
        start_date=datetime.date(2023, 1, 1),
        end_date=None,
        rent_amount=Money(850, "EUR"),
        charges_amount=Money(50, "EUR"),
    )


# ── Model helpers: appreciation_percent ────────────────────────────────────


@pytest.mark.django_db
def test_appreciation_percent_positive(prop, valuation):
    # gross_value = 230000, buying_value_gross = 215000 → +6.97%
    pct = prop.appreciation_percent
    assert pct > 0
    assert round(pct, 1) == pytest.approx((230000 - 215000) / 215000 * 100, rel=1e-2)


@pytest.mark.django_db
def test_appreciation_percent_negative(prop):
    # No revaluation → gross_value == buying_value (200000), buying_value_gross == 215000
    pct = prop.appreciation_percent
    assert pct < 0


@pytest.mark.django_db
def test_appreciation_percent_zero_cost():
    prop = Property.objects.create(
        name="Free Land",
        property_type=Property.LAND,
        buying_value=Money(0, "EUR"),
        buying_date=datetime.date(2020, 1, 1),
        is_active=True,
    )
    assert prop.appreciation_percent == 0.0


# ── Model helpers: loan_progress_percent ───────────────────────────────────


@pytest.mark.django_db
def test_loan_progress_no_loan(prop):
    assert prop.loan_progress_percent == 100.0


@pytest.mark.django_db
def test_loan_progress_with_loan(prop, loan):
    pct = prop.loan_progress_percent
    assert 0.0 <= pct <= 100.0
    # Some capital was repaid over ~4 years
    assert pct > 0


@pytest.mark.django_db
def test_loan_progress_new_loan():
    p = Property.objects.create(
        name="New Buy",
        property_type=Property.APARTMENT,
        buying_value=Money(300000, "EUR"),
        buying_date=datetime.date.today(),
        is_active=True,
    )
    PropertyLoan.objects.create(
        property=p,
        start_date=datetime.date.today(),
        end_date=datetime.date.today().replace(year=datetime.date.today().year + 20),
        original_amount=Money(250000, "EUR"),
        monthly_payment=Money(1100, "EUR"),
        interest_rate=Decimal("1.5"),
    )
    pct = p.loan_progress_percent
    assert 0.0 <= pct <= 100.0


# ── Model helpers: active_lease ────────────────────────────────────────────


@pytest.mark.django_db
def test_active_lease_present(prop, active_lease):
    assert prop.active_lease is not None
    assert prop.active_lease.pk == active_lease.pk


@pytest.mark.django_db
def test_active_lease_none_when_ended(prop):
    Lease.objects.create(
        property=prop,
        first_name="Old",
        last_name="Tenant",
        start_date=datetime.date(2020, 1, 1),
        end_date=datetime.date(2022, 12, 31),
        rent_amount=Money(700, "EUR"),
        charges_amount=Money(0, "EUR"),
    )
    assert prop.active_lease is None


@pytest.mark.django_db
def test_active_lease_none_when_no_leases(prop):
    assert prop.active_lease is None


@pytest.mark.django_db
def test_active_lease_upcoming_not_returned(prop):
    Lease.objects.create(
        property=prop,
        first_name="Future",
        last_name="Tenant",
        start_date=datetime.date.today() + datetime.timedelta(days=30),
        end_date=None,
        rent_amount=Money(800, "EUR"),
        charges_amount=Money(0, "EUR"),
    )
    assert prop.active_lease is None


# ── PropertyDashboardCardApiView ────────────────────────────────────────────


def card_url(pk):
    return reverse("property:api_dashboard_card", kwargs={"pk": pk})


@pytest.mark.django_db
def test_card_api_requires_login(client, prop):
    response = client.get(card_url(prop.pk))
    assert response.status_code == 302
    assert "/accounts/login/" in response.url


@pytest.mark.django_db
def test_card_api_404_for_inactive(admin_client):
    p = Property.objects.create(
        name="Inactive",
        property_type=Property.HOUSE,
        buying_value=Money(100000, "EUR"),
        buying_date=datetime.date(2020, 1, 1),
        is_active=False,
    )
    response = admin_client.get(card_url(p.pk))
    assert response.status_code == 404


@pytest.mark.django_db
def test_card_api_basic_structure(admin_client, prop):
    response = admin_client.get(card_url(prop.pk))
    assert response.status_code == 200
    data = response.json()
    for key in (
        "pk",
        "name",
        "address",
        "property_type",
        "property_type_display",
        "icon",
        "currency",
        "gross_value",
        "net_value",
        "buying_value_gross",
        "appreciation_percent",
        "floor_area",
        "number_of_rooms",
        "loan_progress_percent",
        "total_remaining_loans",
        "loan_end_date",
        "cashflow_last_month",
        "active_lease",
    ):
        assert key in data, f"Missing key: {key}"


@pytest.mark.django_db
def test_card_api_values(admin_client, prop, valuation):
    response = admin_client.get(card_url(prop.pk))
    data = response.json()
    assert data["name"] == "Test Flat"
    assert data["address"] == "1 Rue de la Paix, Paris"
    assert data["gross_value"] == 230000.0
    assert data["buying_value_gross"] == 215000.0
    assert data["floor_area"] == 65.0
    assert data["number_of_rooms"] == 3
    assert data["currency"] == "EUR"


@pytest.mark.django_db
def test_card_api_loan_end_date(admin_client, prop, loan):
    response = admin_client.get(card_url(prop.pk))
    data = response.json()
    assert data["loan_end_date"] == "2045-01-01"
    assert data["total_remaining_loans"] > 0


@pytest.mark.django_db
def test_card_api_no_loan(admin_client, prop):
    response = admin_client.get(card_url(prop.pk))
    data = response.json()
    assert data["loan_end_date"] is None
    assert data["total_remaining_loans"] == 0.0
    assert data["loan_progress_percent"] == 100.0


@pytest.mark.django_db
def test_card_api_active_lease(admin_client, prop, active_lease):
    response = admin_client.get(card_url(prop.pk))
    data = response.json()
    assert data["active_lease"] is not None
    lease = data["active_lease"]
    assert lease["rent_amount"] == 850.0
    assert lease["charges_amount"] == 50.0
    assert lease["total_rent"] == 900.0
    assert "Jean" in lease["tenant_name"]


@pytest.mark.django_db
def test_card_api_no_lease(admin_client, prop):
    response = admin_client.get(card_url(prop.pk))
    data = response.json()
    assert data["active_lease"] is None


@pytest.mark.django_db
def test_card_api_cashflow_structure(admin_client, prop):
    response = admin_client.get(card_url(prop.pk))
    data = response.json()
    cf = data["cashflow_last_month"]
    for key in ("income", "expenses", "net", "occupancy_rate"):
        assert key in cf


@pytest.mark.django_db
def test_card_api_cashflow_with_entries(admin_client, prop):
    today = datetime.date.today()
    last_month = (today.replace(day=1) - datetime.timedelta(days=1)).replace(day=15)
    PropertyLedgerEntry.objects.create(
        property=prop,
        flow_type=PropertyLedgerEntry.FlowType.INCOME,
        management_category=PropertyLedgerEntry.ManagementCategory.RENT_COLLECTED,
        amount=Money(850, "EUR"),
        entry_date=last_month,
    )
    PropertyLedgerEntry.objects.create(
        property=prop,
        flow_type=PropertyLedgerEntry.FlowType.EXPENSE,
        management_category=PropertyLedgerEntry.ManagementCategory.INSURANCE,
        amount=Money(100, "EUR"),
        entry_date=last_month,
    )
    response = admin_client.get(card_url(prop.pk))
    data = response.json()
    cf = data["cashflow_last_month"]
    assert cf["income"] == 850.0
    assert cf["expenses"] == 100.0
    assert cf["net"] == pytest.approx(750.0, rel=1e-2)


# ── SCPIDashboardCardApiView ────────────────────────────────────────────────


def scpi_card_url(pk):
    return reverse("property:api_scpi_dashboard_card", kwargs={"pk": pk})


@pytest.fixture
def scpi_fund():
    from property.models.scpi import SCPI

    return SCPI.objects.create(name="Corum Eurion", management_company="Corum AM")


@pytest.mark.django_db
def test_scpi_card_api_requires_login(client, scpi_fund):
    response = client.get(scpi_card_url(scpi_fund.pk))
    assert response.status_code == 302
    assert "/accounts/login/" in response.url


@pytest.mark.django_db
def test_scpi_card_api_404_unknown(admin_client):
    response = admin_client.get(scpi_card_url(99999))
    assert response.status_code == 404


@pytest.mark.django_db
def test_scpi_card_api_basic_structure(admin_client, scpi_fund):
    response = admin_client.get(scpi_card_url(scpi_fund.pk))
    assert response.status_code == 200
    data = response.json()
    for key in (
        "pk",
        "name",
        "management_company",
        "total_resale",
        "total_invested",
        "total_dividends",
        "gain_pct",
        "net_rentability",
        "currency",
    ):
        assert key in data, f"Missing key: {key}"


@pytest.mark.django_db
def test_scpi_card_api_values(admin_client, scpi_fund):
    response = admin_client.get(scpi_card_url(scpi_fund.pk))
    data = response.json()
    assert data["name"] == "Corum Eurion"
    assert data["management_company"] == "Corum AM"
    assert data["total_resale"] is None
    assert data["total_invested"] is None
    assert data["gain_pct"] is None
    assert data["net_rentability"] == 0.0
