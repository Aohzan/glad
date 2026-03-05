"""Test base views."""

import datetime

import pytest
from django.urls import reverse
from django.utils.translation import gettext as _
from moneyed import Money

from finance.models.investment_account import (
    InvestmentAccount,
    InvestmentAccountCash,
    InvestmentAccountHolding,
    InvestmentAccountHoldingHistory,
)
from finance.models.saving_account import SavingAccount, SavingAccountValue
from property.models import Property
from tests.conftest import ADMIN_USER


@pytest.mark.django_db
def test_index_view_unauthenticated(client):
    """Test that unauthenticated users are redirected to login page."""
    path = reverse("index")
    response = client.get(path)
    assert response.url == "/accounts/login/?next=/"
    assert response.status_code == 302


@pytest.mark.django_db
def test_index_view_authenticated(admin_client):
    """Test that authenticated users who can access the index page."""
    path = reverse("index")
    response = admin_client.get(path)
    assert response.status_code == 200
    # Check for translated welcome message
    assert _("Welcome") in response.content.decode()
    assert ADMIN_USER in response.content.decode()


@pytest.mark.django_db
def test_index_view_with_multiple_currencies(admin_client, saving_account_type):
    """Test dashboard aggregates accounts by currency correctly."""
    # Create accounts with different currencies
    SavingAccount.objects.create(
        name="EUR Account",
        account_type=saving_account_type,
        opening_value=Money(1000, "EUR"),
        is_active=True,
    )
    SavingAccountValue.objects.create(
        account=SavingAccount.objects.get(name="EUR Account"),
        value=Money(1000, "EUR"),
        value_date=datetime.date.today(),
    )

    SavingAccount.objects.create(
        name="USD Account",
        account_type=saving_account_type,
        opening_value=Money(2000, "USD"),
        is_active=True,
    )
    SavingAccountValue.objects.create(
        account=SavingAccount.objects.get(name="USD Account"),
        value=Money(2000, "USD"),
        value_date=datetime.date.today(),
    )

    response = admin_client.get(reverse("index"))
    assert response.status_code == 200

    context = response.context
    # Should have both currencies in the aggregated totals
    assert "EUR" in context["total_saving_accounts_by_currency"]
    assert "USD" in context["total_saving_accounts_by_currency"]
    assert context["total_saving_accounts_by_currency"]["EUR"] == Money(1000, "EUR")
    assert context["total_saving_accounts_by_currency"]["USD"] == Money(2000, "USD")


@pytest.mark.django_db
def test_index_view_historical_progression(
    admin_client, saving_account_type, investment_account_type, user
):
    """Test that historical progression calculation works correctly."""
    # Create accounts with historical data
    saving_account = SavingAccount.objects.create(
        name="Test Saving",
        account_type=saving_account_type,
        opening_value=Money(0, "EUR"),
        is_active=True,
    )
    # Add value from 35 days ago (before 30-day window)
    SavingAccountValue.objects.create(
        account=saving_account,
        value=Money(1000, "EUR"),
        value_date=datetime.date.today() - datetime.timedelta(days=35),
    )
    # Add current value
    SavingAccountValue.objects.create(
        account=saving_account,
        value=Money(1500, "EUR"),
        value_date=datetime.date.today(),
    )

    investment_account = InvestmentAccount.objects.create(
        name="Test Investment",
        account_type=investment_account_type,
        opening_cash_value=Money(0, "EUR"),
        is_active=True,
        owner=str(user),
    )
    # Add cash from 35 days ago
    InvestmentAccountCash.objects.create(
        account=investment_account,
        value=Money(2000, "EUR"),
        value_date=datetime.date.today() - datetime.timedelta(days=35),
    )
    # Add current cash
    InvestmentAccountCash.objects.create(
        account=investment_account,
        value=Money(3000, "EUR"),
        value_date=datetime.date.today(),
    )

    response = admin_client.get(reverse("index"))
    assert response.status_code == 200

    context = response.context
    # Should calculate global progression (from 3000 to 4500 = 50% increase)
    assert "global_progression" in context
    assert context["global_progression"] > 0


@pytest.mark.django_db
def test_index_view_patrimony_evolution(
    admin_client, saving_account_type, investment_account_type, user
):
    """Test patrimony evolution arrays are generated for 24 months."""
    # Create accounts to populate evolution
    saving_account = SavingAccount.objects.create(
        name="Test Saving",
        account_type=saving_account_type,
        opening_value=Money(0, "EUR"),
        is_active=True,
    )
    SavingAccountValue.objects.create(
        account=saving_account,
        value=Money(1000, "EUR"),
        value_date=datetime.date.today(),
    )

    response = admin_client.get(reverse("index"))
    assert response.status_code == 200

    context = response.context
    # Should have 25 months of data (24 historical + current)
    assert len(context["patrimony_months"]) == 25
    assert len(context["patrimony_evolution_investments"]) == 25
    assert len(context["patrimony_evolution_savings"]) == 25
    assert len(context["patrimony_evolution_properties_net"]) == 25
    assert len(context["patrimony_evolution_properties_gross"]) == 25


@pytest.mark.django_db
def test_index_view_alerts_generation(admin_client, saving_account_type):
    """Test alerts are generated for accounts with negative progression."""
    # Create account with declining value
    saving_account = SavingAccount.objects.create(
        name="Declining Account",
        account_type=saving_account_type,
        opening_value=Money(0, "EUR"),
        is_active=True,
    )
    # Add value from 35 days ago (before 30-day window) that was higher
    SavingAccountValue.objects.create(
        account=saving_account,
        value=Money(2000, "EUR"),
        value_date=datetime.date.today() - datetime.timedelta(days=35),
    )
    # Add current value that's much lower (to trigger alert)
    SavingAccountValue.objects.create(
        account=saving_account,
        value=Money(1000, "EUR"),
        value_date=datetime.date.today(),
    )

    response = admin_client.get(reverse("index"))
    assert response.status_code == 200

    context = response.context
    # Should have alerts for accounts with > 5% decrease
    assert "alerts" in context


@pytest.mark.django_db
def test_index_view_latest_operations(
    admin_client, saving_account_type, investment_account_type, user
):
    """Test latest operations are showing recent account updates."""
    # Create saving account with value
    saving_account = SavingAccount.objects.create(
        name="Test Saving",
        account_type=saving_account_type,
        opening_value=Money(0, "EUR"),
        is_active=True,
    )
    SavingAccountValue.objects.create(
        account=saving_account,
        value=Money(1000, "EUR"),
        value_date=datetime.date.today(),
    )

    # Create investment account with cash
    investment_account = InvestmentAccount.objects.create(
        name="Test Investment",
        account_type=investment_account_type,
        opening_cash_value=Money(0, "EUR"),
        is_active=True,
        owner=str(user),
    )
    InvestmentAccountCash.objects.create(
        account=investment_account,
        value=Money(2000, "EUR"),
        value_date=datetime.date.today(),
    )

    # Create holding with history
    holding = InvestmentAccountHolding.objects.create(
        account=investment_account,
        name="Test Stock",
        code="TST",
        initial_quantity=10,
    )
    InvestmentAccountHoldingHistory.objects.create(
        holding=holding,
        quantity=10,
        value=Money(100, "EUR"),
        valuation_date=datetime.date.today(),
    )

    response = admin_client.get(reverse("index"))
    assert response.status_code == 200

    context = response.context
    # Should have latest operations (max 10)
    assert "latest_operations" in context
    assert len(context["latest_operations"]) <= 10
    assert len(context["latest_operations"]) >= 3  # We created 3 operations


@pytest.mark.django_db
def test_index_view_all_accounts_progression(
    admin_client, saving_account_type, investment_account_type, user
):
    """Test all accounts are listed with their progression."""
    # Create accounts
    saving_account = SavingAccount.objects.create(
        name="Test Saving",
        account_type=saving_account_type,
        opening_value=Money(0, "EUR"),
        is_active=True,
    )
    SavingAccountValue.objects.create(
        account=saving_account,
        value=Money(1000, "EUR"),
        value_date=datetime.date.today(),
    )

    investment_account = InvestmentAccount.objects.create(
        name="Test Investment",
        account_type=investment_account_type,
        opening_cash_value=Money(0, "EUR"),
        is_active=True,
        owner=str(user),
    )
    InvestmentAccountCash.objects.create(
        account=investment_account,
        value=Money(2000, "EUR"),
        value_date=datetime.date.today(),
    )

    response = admin_client.get(reverse("index"))
    assert response.status_code == 200

    context = response.context
    # Should list both accounts with progression
    assert "all_accounts" in context
    assert len(context["all_accounts"]) == 2
    # Each should have name, progression_percent, progression_css, icon
    for account in context["all_accounts"]:
        assert "name" in account
        assert "progression_percent" in account
        assert "progression_css" in account
        assert "icon" in account


@pytest.mark.django_db
def test_index_view_with_properties(admin_client, user):
    """Test dashboard includes property calculations."""
    # Create property
    Property.objects.create(
        name="Test Property",
        buying_date=datetime.date.today() - datetime.timedelta(days=365),
        buying_value=Money(200000, "EUR"),
        is_active=True,
    )

    response = admin_client.get(reverse("index"))
    assert response.status_code == 200

    context = response.context
    # Should include property values
    assert "total_properties" in context
    assert "total_properties_net" in context
    assert "total_properties_gross" in context
    assert "EUR" in context["total_properties_value_by_currency"]


@pytest.mark.django_db
def test_index_view_inactive_accounts_excluded(admin_client, saving_account_type):
    """Test that inactive accounts are excluded from current totals."""
    # Create inactive account
    inactive_account = SavingAccount.objects.create(
        name="Inactive Account",
        account_type=saving_account_type,
        opening_value=Money(0, "EUR"),
        is_active=False,
        closing_date=datetime.date.today() - datetime.timedelta(days=10),
    )
    SavingAccountValue.objects.create(
        account=inactive_account,
        value=Money(5000, "EUR"),
        value_date=datetime.date.today() - datetime.timedelta(days=100),
    )

    # Create active account
    active_account = SavingAccount.objects.create(
        name="Active Account",
        account_type=saving_account_type,
        opening_value=Money(0, "EUR"),
        is_active=True,
    )
    SavingAccountValue.objects.create(
        account=active_account,
        value=Money(1000, "EUR"),
        value_date=datetime.date.today(),
    )

    response = admin_client.get(reverse("index"))
    assert response.status_code == 200

    context = response.context
    # Only active account should count in current total
    assert context["total_saving_accounts_by_currency"]["EUR"] == Money(1000, "EUR")


@pytest.mark.django_db
def test_index_view_breakdown_data(
    admin_client, saving_account_type, investment_account_type, user
):
    """Test breakdown labels and values for pie chart."""
    # Create accounts
    saving_account = SavingAccount.objects.create(
        name="Test Saving",
        account_type=saving_account_type,
        opening_value=Money(0, "EUR"),
        is_active=True,
    )
    SavingAccountValue.objects.create(
        account=saving_account,
        value=Money(1000, "EUR"),
        value_date=datetime.date.today(),
    )

    investment_account = InvestmentAccount.objects.create(
        name="Test Investment",
        account_type=investment_account_type,
        opening_cash_value=Money(0, "EUR"),
        is_active=True,
        owner=str(user),
    )
    InvestmentAccountCash.objects.create(
        account=investment_account,
        value=Money(2000, "EUR"),
        value_date=datetime.date.today(),
    )

    response = admin_client.get(reverse("index"))
    assert response.status_code == 200

    context = response.context
    # Should have 4 categories in breakdown
    assert len(context["breakdown_labels"]) == 4
    assert len(context["breakdown_values"]) == 4
    assert "Investments" in context["breakdown_labels"]
    assert "Savings" in context["breakdown_labels"]
    assert "Properties Net" in context["breakdown_labels"]
    assert "Properties Loans" in context["breakdown_labels"]
