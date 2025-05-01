"""Tests for finance views."""

from moneyed import Money
import pytest
from django.urls import reverse
from decimal import Decimal

from finance.models.investment_account import InvestmentAccount
from finance.models.saving_account import SavingAccount
from finance.utils import AccountProgression


@pytest.mark.django_db
def test_index_view_unauthenticated(client):
    """Test that unauthenticated users are redirected to login page."""
    path = reverse("finance:index")
    response = client.get(path)
    assert response.status_code == 302
    assert "/accounts/login/" in response.url


@pytest.mark.django_db
def test_index_view_authenticated_default_context(
    user_client,
    active_saving_account,
    active_investment_account,
):
    """Test that the index view returns the expected context with default days value."""
    path = reverse("finance:index")
    response = user_client.get(path)

    assert response.status_code == 200

    # Check that the context contains the expected keys
    assert "days" in response.context
    assert "savings_accounts" in response.context
    assert "investment_accounts" in response.context

    # Check that days has the default value of 30
    assert response.context["days"] == 30

    # Check that only active accounts are included
    assert len(response.context["savings_accounts"]) == 1
    assert len(response.context["investment_accounts"]) == 1

    # Check that the saving account in the context is the active one
    saving_account_context = response.context["savings_accounts"][0]
    assert saving_account_context["model"].id == active_saving_account.id
    assert saving_account_context["model"].name == active_saving_account.name

    # Check that the investment account in the context is the active one
    investment_account_context = response.context["investment_accounts"][0]
    assert investment_account_context["model"].id == active_investment_account.id
    assert investment_account_context["model"].name == active_investment_account.name

    # Check that each account has a progression object
    assert "progression" in saving_account_context
    assert isinstance(saving_account_context["progression"], AccountProgression)

    assert "progression" in investment_account_context
    assert isinstance(investment_account_context["progression"], AccountProgression)


@pytest.mark.django_db
def test_index_view_with_custom_days(
    user_client,
    active_saving_account,
    active_investment_account,
):
    """Test that the index view uses the days parameter from the request."""
    custom_days = 15
    path = f"{reverse('finance:index')}?days={custom_days}"
    response = user_client.get(path)

    assert response.status_code == 200

    # Check that days has the custom value
    assert response.context["days"] == custom_days

    # Check that the progression is calculated with the custom days value
    saving_account_context = response.context["savings_accounts"][0]
    investment_account_context = response.context["investment_accounts"][0]

    # Get the expected progression values
    expected_saving_progression = active_saving_account.get_progression(custom_days)
    expected_investment_progression = active_investment_account.get_progression(
        custom_days
    )

    # Compare progression values - use assertAlmostEqual for floating point comparisons
    # For Decimal values (progression), we can use exact comparison
    assert (
        saving_account_context["progression"].progression
        == expected_saving_progression.progression
    )

    # For float values (difference), we should compare with a small tolerance
    assert (
        abs(
            saving_account_context["progression"].difference.amount
            - expected_saving_progression.difference.amount
        )
        < 0.001
    )

    # Check CSS class is consistent
    assert (
        saving_account_context["progression"].css_class
        == expected_saving_progression.css_class
    )

    # Same checks for investment account
    assert (
        investment_account_context["progression"].progression
        == expected_investment_progression.progression
    )
    assert (
        abs(
            investment_account_context["progression"].difference.amount
            - expected_investment_progression.difference.amount
        )
        < 0.001
    )
    assert (
        investment_account_context["progression"].css_class
        == expected_investment_progression.css_class
    )


@pytest.mark.django_db
def test_index_view_context_structure(
    user_client,
    active_saving_account,
    active_investment_account,
):
    """Test the structure of the context returned by the index view."""
    path = reverse("finance:index")
    response = user_client.get(path)

    assert response.status_code == 200

    # Check savings_accounts structure
    savings_accounts = response.context["savings_accounts"]
    assert len(savings_accounts) == 1

    saving_account_item = savings_accounts[0]
    assert "model" in saving_account_item
    assert "progression" in saving_account_item

    assert isinstance(saving_account_item["model"], SavingAccount)
    assert isinstance(saving_account_item["progression"], AccountProgression)

    # Check progression attributes
    saving_progression = saving_account_item["progression"]
    assert hasattr(saving_progression, "progression")
    assert hasattr(saving_progression, "difference")
    assert hasattr(saving_progression, "css_class")

    # Check that progression values are of the correct type
    assert isinstance(saving_progression.progression, Money)
    assert isinstance(saving_progression.difference.amount, (float, int, Decimal))
    assert isinstance(saving_progression.css_class, str)

    # Check investment_accounts structure
    investment_accounts = response.context["investment_accounts"]
    assert len(investment_accounts) == 1

    investment_account_item = investment_accounts[0]
    assert "model" in investment_account_item
    assert "progression" in investment_account_item

    assert isinstance(investment_account_item["model"], InvestmentAccount)
    assert isinstance(investment_account_item["progression"], AccountProgression)

    # Check progression attributes
    investment_progression = investment_account_item["progression"]
    assert hasattr(investment_progression, "progression")
    assert hasattr(investment_progression, "difference")
    assert hasattr(investment_progression, "css_class")

    # Check that progression values are of the correct type
    assert isinstance(investment_progression.progression, Money)
    assert isinstance(investment_progression.difference.amount, (float, int, Decimal))
    assert isinstance(investment_progression.css_class, str)


@pytest.mark.django_db
def test_index_view_filters_inactive_accounts(
    user_client,
    active_saving_account,
    inactive_saving_account,
    active_investment_account,
    inactive_investment_account,
):
    """Test that the index view only includes active accounts in the context."""
    path = reverse("finance:index")
    response = user_client.get(path)

    assert response.status_code == 200

    # Check that only active accounts are included
    savings_accounts = response.context["savings_accounts"]
    investment_accounts = response.context["investment_accounts"]

    assert len(savings_accounts) == 1
    assert savings_accounts[0]["model"].id == active_saving_account.id
    assert savings_accounts[0]["model"].is_active is True

    assert len(investment_accounts) == 1
    assert investment_accounts[0]["model"].id == active_investment_account.id
    assert investment_accounts[0]["model"].is_active is True

    # Check that inactive accounts are not included
    saving_account_ids = [item["model"].id for item in savings_accounts]
    investment_account_ids = [item["model"].id for item in investment_accounts]

    assert inactive_saving_account.id not in saving_account_ids
    assert inactive_investment_account.id not in investment_account_ids
