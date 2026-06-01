"""Tests for finance/views/api_views.py — AccountsSummaryApiView."""

import datetime

import pytest
from django.urls import reverse
from moneyed import Money

from finance.models.investment_account import InvestmentAccount, InvestmentAccountCash
from finance.models.saving_account import SavingAccount, SavingAccountValue


def get_json(client, url):
    return client.get(url, HTTP_ACCEPT="application/json")


@pytest.mark.django_db
def test_accounts_summary_requires_login(client):
    response = get_json(client, reverse("finance:api_accounts_summary"))
    assert response.status_code == 302
    assert "/accounts/login/" in response.url


@pytest.mark.django_db
def test_accounts_summary_empty(admin_client):
    response = get_json(admin_client, reverse("finance:api_accounts_summary"))
    assert response.status_code == 200
    data = response.json()
    assert "breakdown_labels" in data
    assert "breakdown_values" in data
    assert "accounts" in data
    assert "alerts" in data
    assert isinstance(data["accounts"], list)
    assert isinstance(data["alerts"], list)


@pytest.mark.django_db
def test_accounts_summary_breakdown_labels(admin_client):
    response = get_json(admin_client, reverse("finance:api_accounts_summary"))
    data = response.json()
    assert "Investments" in data["breakdown_labels"]
    assert "Savings" in data["breakdown_labels"]
    assert len(data["breakdown_labels"]) == len(data["breakdown_values"])


@pytest.mark.django_db
def test_accounts_summary_includes_saving_account(admin_client, saving_account_type):
    acc = SavingAccount.objects.create(
        name="Livret A",
        account_type=saving_account_type,
        opening_value=Money(0, "EUR"),
        is_active=True,
    )
    SavingAccountValue.objects.create(
        account=acc, value=Money(3000, "EUR"), value_date=datetime.date.today()
    )
    response = get_json(admin_client, reverse("finance:api_accounts_summary"))
    data = response.json()
    names = [a["name"] for a in data["accounts"]]
    assert any("Livret A" in name for name in names)


@pytest.mark.django_db
def test_accounts_summary_account_structure(admin_client, saving_account_type):
    acc = SavingAccount.objects.create(
        name="Test",
        account_type=saving_account_type,
        opening_value=Money(0, "EUR"),
        is_active=True,
    )
    SavingAccountValue.objects.create(
        account=acc, value=Money(1000, "EUR"), value_date=datetime.date.today()
    )
    response = get_json(admin_client, reverse("finance:api_accounts_summary"))
    data = response.json()
    assert len(data["accounts"]) >= 1
    account = data["accounts"][0]
    for key in (
        "name",
        "value",
        "progression",
        "progression_percent",
        "progression_css",
        "icon",
        "type",
        "owner",
    ):
        assert key in account, f"Missing key: {key}"
    assert account["progression_css"] in ("success", "danger", "secondary")
    assert account["type"] in ("savings", "investment")


@pytest.mark.django_db
def test_accounts_summary_inactive_excluded(admin_client, saving_account_type):
    SavingAccount.objects.create(
        name="Inactive",
        account_type=saving_account_type,
        opening_value=Money(0, "EUR"),
        is_active=False,
        closing_date=datetime.date.today() - datetime.timedelta(days=1),
    )
    response = get_json(admin_client, reverse("finance:api_accounts_summary"))
    data = response.json()
    names = [a["name"] for a in data["accounts"]]
    assert "Inactive" not in names


@pytest.mark.django_db
def test_accounts_summary_alert_on_decline(admin_client, declining_saving_account):
    response = get_json(admin_client, reverse("finance:api_accounts_summary"))
    data = response.json()
    assert any("Declining" in a["account"] for a in data["alerts"])


@pytest.mark.django_db
def test_accounts_summary_investment_type(admin_client, investment_account_type, user):
    inv = InvestmentAccount.objects.create(
        name="PEA",
        account_type=investment_account_type,
        opening_cash_value=Money(0, "EUR"),
        is_active=True,
        owner=str(user),
    )
    InvestmentAccountCash.objects.create(
        account=inv, value=Money(5000, "EUR"), value_date=datetime.date.today()
    )
    response = get_json(admin_client, reverse("finance:api_accounts_summary"))
    data = response.json()
    investment_accounts = [a for a in data["accounts"] if a["type"] == "investment"]
    assert any("PEA" in a["name"] for a in investment_accounts)
