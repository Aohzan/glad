"""Tests for base/api_views.py — dashboard JSON endpoints."""

import datetime

import pytest
from django.urls import reverse
from moneyed import Money

from finance.models.saving_account import SavingAccount, SavingAccountValue

# ── helpers ────────────────────────────────────────────────────────────────


def get_json(client, url):
    return client.get(url, HTTP_ACCEPT="application/json")


def _make_saving_account(saving_account_type, name="Test"):
    """Create a minimal active saving account."""
    return SavingAccount.objects.create(
        name=name,
        account_type=saving_account_type,
        opening_value=Money(0, "EUR"),
        is_active=True,
    )


# ── auth guards ────────────────────────────────────────────────────────────


@pytest.mark.django_db
@pytest.mark.parametrize(
    "url_name",
    [
        "api_net_worth",
        "api_patrimony_chart",
        "api_recent_operations",
        "api_alerts",
    ],
)
def test_api_requires_login(client, url_name):
    response = get_json(client, reverse(url_name))
    assert response.status_code == 302
    assert "/accounts/login/" in response.url


# ── NetWorthApiView ────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_net_worth_empty(admin_client):
    response = get_json(admin_client, reverse("api_net_worth"))
    assert response.status_code == 200
    data = response.json()
    assert data["total_net_worth"] == 0.0
    assert data["total_investments"] == 0.0
    assert data["total_savings"] == 0.0
    assert data["total_properties_net"] == 0.0
    assert isinstance(data["global_progression"], float)
    assert isinstance(data["net_worth_by_currency"], dict)


@pytest.mark.django_db
def test_net_worth_with_accounts(admin_client, saving_account_type):
    acc = _make_saving_account(saving_account_type)
    SavingAccountValue.objects.create(
        account=acc, value=Money(5000, "EUR"), value_date=datetime.date.today()
    )
    response = get_json(admin_client, reverse("api_net_worth"))
    data = response.json()
    assert data["total_savings"] == 5000.0
    assert data["total_net_worth"] == 5000.0
    assert data["currency"] == "EUR"
    assert "EUR" in data["net_worth_by_currency"]


@pytest.mark.django_db
def test_net_worth_30day_progression(admin_client, saving_account_type):
    acc = _make_saving_account(saving_account_type)
    SavingAccountValue.objects.create(
        account=acc,
        value=Money(1000, "EUR"),
        value_date=datetime.date.today() - datetime.timedelta(days=35),
    )
    SavingAccountValue.objects.create(
        account=acc, value=Money(1100, "EUR"), value_date=datetime.date.today()
    )
    response = get_json(admin_client, reverse("api_net_worth"))
    data = response.json()
    assert data["global_progression"] > 0


# ── PatrimonyChartApiView ──────────────────────────────────────────────────


@pytest.mark.django_db
def test_patrimony_chart_structure(admin_client):
    response = get_json(admin_client, reverse("api_patrimony_chart"))
    assert response.status_code == 200
    data = response.json()
    assert "months" in data
    assert "investments" in data
    assert "savings" in data
    assert "properties_net" in data
    assert "properties_loans" in data
    assert "scpi" in data
    assert len(data["months"]) == 25  # 24 historical + current month


@pytest.mark.django_db
def test_patrimony_chart_series_length(admin_client):
    response = get_json(admin_client, reverse("api_patrimony_chart"))
    data = response.json()
    length = len(data["months"])
    assert len(data["investments"]) == length
    assert len(data["savings"]) == length
    assert len(data["properties_net"]) == length
    assert len(data["properties_loans"]) == length
    assert len(data["scpi"]) == length


# ── RecentOperationsApiView ────────────────────────────────────────────────


@pytest.mark.django_db
def test_recent_operations_empty(admin_client):
    response = get_json(admin_client, reverse("api_recent_operations"))
    assert response.status_code == 200
    data = response.json()
    assert "operations" in data
    assert isinstance(data["operations"], list)


@pytest.mark.django_db
def test_recent_operations_structure(admin_client, saving_account_type):
    acc = _make_saving_account(saving_account_type)
    SavingAccountValue.objects.create(
        account=acc, value=Money(1000, "EUR"), value_date=datetime.date.today()
    )
    response = get_json(admin_client, reverse("api_recent_operations"))
    data = response.json()
    assert len(data["operations"]) >= 1
    op = data["operations"][0]
    for key in ("label", "amount", "currency", "date", "icon", "type_css"):
        assert key in op


@pytest.mark.django_db
def test_recent_operations_max_five(admin_client, saving_account_type):
    acc = SavingAccount.objects.create(
        name="Test",
        account_type=saving_account_type,
        opening_value=Money(0, "EUR"),
        is_active=True,
    )
    for i in range(10):
        SavingAccountValue.objects.create(
            account=acc,
            value=Money(1000 + i, "EUR"),
            value_date=datetime.date.today() - datetime.timedelta(days=i),
        )
    response = get_json(admin_client, reverse("api_recent_operations"))
    data = response.json()
    assert len(data["operations"]) <= 5


# ── AlertsApiView ──────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_alerts_empty(admin_client):
    response = get_json(admin_client, reverse("api_alerts"))
    assert response.status_code == 200
    data = response.json()
    assert "alerts" in data
    assert isinstance(data["alerts"], list)


@pytest.mark.django_db
def test_alerts_triggered_on_decline(admin_client, declining_saving_account):
    response = get_json(admin_client, reverse("api_alerts"))
    data = response.json()
    assert len(data["alerts"]) >= 1
    alert = data["alerts"][0]
    assert "account" in alert
    assert "message" in alert
    assert alert["type_css"] == "danger"


@pytest.mark.django_db
def test_alerts_not_triggered_on_small_decline(admin_client, saving_account_type):
    acc = _make_saving_account(saving_account_type, name="Slight dip")
    SavingAccountValue.objects.create(
        account=acc,
        value=Money(1000, "EUR"),
        value_date=datetime.date.today() - datetime.timedelta(days=35),
    )
    SavingAccountValue.objects.create(
        account=acc, value=Money(980, "EUR"), value_date=datetime.date.today()
    )
    response = get_json(admin_client, reverse("api_alerts"))
    data = response.json()
    assert len(data["alerts"]) == 0
