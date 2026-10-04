"""Tests for the context returned by the finance index view."""

import datetime
import json
from unittest.mock import patch

import pytest
from django.urls import reverse
from moneyed import Money

from finance.models.investment_account import (
    InvestmentAccount,
    InvestmentAccountHolding,
    InvestmentAccountHoldingHistory,
)
from finance.models.saving_account import SavingAccount, SavingAccountValue
from finance.utils import AccountProgression

INDEX_URL = reverse("finance:index")


@pytest.mark.django_db
def test_index_view_unauthenticated(client):
    """Test that unauthenticated users are redirected to login page."""
    response = client.get(INDEX_URL)
    assert response.status_code == 302
    assert "/accounts/login/" in response.url


@pytest.mark.django_db
def test_index_view_context_keys(client, user):
    """Test that the index view returns the expected context keys."""
    client.force_login(user)

    context = client.get(INDEX_URL).context

    assert context["form"] is not None
    assert context["savings_accounts"] == []
    assert context["investment_accounts"] == []
    assert context["days"] == 30  # Default value
    assert context["has_chart_data"] is False


@pytest.mark.django_db
def test_index_view_custom_days(client, user):
    """Test that the index view uses the days parameter from the request."""
    client.force_login(user)

    context = client.get(INDEX_URL, {"days": "15"}).context

    assert context["days"] == 15


@pytest.mark.django_db
def test_index_view_active_accounts_only(
    client,
    user,
    active_saving_account,
    inactive_saving_account,
    active_investment_account,
    inactive_investment_account,
):
    """Closed accounts are listed only when asked for."""
    client.force_login(user)

    context = client.get(INDEX_URL).context
    assert [e["model"] for e in context["savings_accounts"]] == [active_saving_account]
    assert [e["model"] for e in context["investment_accounts"]] == [
        active_investment_account
    ]

    context = client.get(INDEX_URL, {"days": "30"}).context
    assert [e["model"] for e in context["savings_accounts"]] == [
        active_saving_account,
        inactive_saving_account,
    ]
    assert [e["model"] for e in context["investment_accounts"]] == [
        active_investment_account,
        inactive_investment_account,
    ]


@pytest.mark.django_db
def test_index_view_savings_accounts_structure(
    client, user, active_saving_account, saving_account_value
):
    """Test the structure of savings_accounts in the context."""
    client.force_login(user)

    context = client.get(INDEX_URL).context

    (entry,) = context["savings_accounts"]
    assert entry["model"] == active_saving_account
    assert isinstance(entry["progression"], AccountProgression)
    assert context["total_saving_value"] == Money(1100, "EUR")
    (series,) = json.loads(context["chart_series_json"])
    assert series["name"] == str(active_saving_account)
    assert series["data"][-1] == 1100.0
    assert len(series["data"]) == len(json.loads(context["chart_months_json"]))


@pytest.mark.django_db
def test_index_view_investment_accounts_structure(
    client, user, active_investment_account, investment_account_cash
):
    """Test the structure of investment_accounts in the context."""
    holding = InvestmentAccountHolding.objects.create(
        account=active_investment_account,
        name="Fund",
        initial_value=Money(100, "EUR"),
        initial_valuation_date=datetime.date.today() - datetime.timedelta(days=50),
    )
    InvestmentAccountHoldingHistory.objects.create(
        holding=holding,
        value=Money(300, "EUR"),
        valuation_date=datetime.datetime.now() - datetime.timedelta(days=5),
    )
    client.force_login(user)

    context = client.get(INDEX_URL).context

    (entry,) = context["investment_accounts"]
    assert entry["model"] == active_investment_account
    assert entry["value"] == Money(2500, "EUR")
    assert isinstance(entry["progression"], AccountProgression)
    cash, fund = entry["subentries"]
    assert cash["id"] == "cash"
    assert cash["value"] == Money(2200, "EUR")
    assert fund["id"] == holding.id
    assert fund["value"] == Money(300, "EUR")
    assert fund["weight"] == 12
    (series,) = json.loads(context["chart_series_json"])
    assert series["data"][-1] == 2500.0


@pytest.mark.django_db
def test_index_view_custom_days_progression(
    client, user, active_saving_account, active_investment_account
):
    """Test that the progression is calculated with the custom days value."""
    client.force_login(user)
    with (
        patch.object(
            SavingAccount,
            "get_progression",
            autospec=True,
            side_effect=SavingAccount.get_progression,
        ) as saving_progression,
        patch.object(
            InvestmentAccount,
            "get_progression",
            autospec=True,
            side_effect=InvestmentAccount.get_progression,
        ) as investment_progression,
    ):
        client.get(INDEX_URL, {"days": "15", "active_only": "on"})

    saving_progression.assert_called_once_with(active_saving_account, 15)
    investment_progression.assert_called_once_with(active_investment_account, 15)


@pytest.mark.django_db
def test_index_view_queries_do_not_grow_with_history(
    client, user, saving_account_type, django_assert_max_num_queries
):
    """The monthly chart is built without querying each account month by month."""
    for index in range(3):
        account = SavingAccount.objects.create(
            account_type=saving_account_type,
            name=f"Old {index}",
            opening_value=Money(100, "EUR"),
            opening_date=datetime.date.today() - datetime.timedelta(days=3650),
        )
        SavingAccountValue.objects.create(
            account=account,
            value=Money(200, "EUR"),
            value_date=datetime.datetime.now() - datetime.timedelta(days=1800),
        )
    client.force_login(user)

    with django_assert_max_num_queries(40):
        context = client.get(INDEX_URL).context

    assert len(json.loads(context["chart_months_json"])) > 100
