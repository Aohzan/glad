"""Tests for the context returned by the finance index view."""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from django.urls import reverse

from finance.utils import AccountProgression


@pytest.mark.django_db
def test_index_view_unauthenticated(client):
    """Test that unauthenticated users are redirected to login page."""
    path = reverse("finance:index")
    response = client.get(path)
    assert response.status_code == 302
    assert "/accounts/login/" in response.url


@pytest.mark.django_db
@patch("finance.views.SavingAccount.objects.filter")
@patch("finance.views.InvestmentAccount.objects.filter")
def test_index_view_context_keys(
    mock_investment_filter, mock_saving_filter, user_client
):
    """Test that the index view returns the expected context keys."""
    # Setup mocks
    mock_saving_filter.return_value = []
    mock_investment_filter.return_value = []

    # Execute view
    path = reverse("finance:index")
    response = user_client.get(path)

    # Verify context keys
    assert response.status_code == 200
    assert "days" in response.context
    assert "savings_accounts" in response.context
    assert "investment_accounts" in response.context
    assert response.context["days"] == 30  # Default value


@pytest.mark.django_db
@patch("finance.views.SavingAccount.objects.filter")
@patch("finance.views.InvestmentAccount.objects.filter")
def test_index_view_custom_days(
    mock_investment_filter, mock_saving_filter, user_client
):
    """Test that the index view uses the days parameter from the request."""
    # Setup mocks
    mock_saving_filter.return_value = []
    mock_investment_filter.return_value = []

    # Execute view with custom days
    custom_days = 15
    path = f"{reverse('finance:index')}?days={custom_days}"
    response = user_client.get(path)

    # Verify days value
    assert response.status_code == 200
    assert response.context["days"] == custom_days


@pytest.mark.django_db
@patch("finance.views.SavingAccount.objects.filter")
@patch("finance.views.InvestmentAccount.objects.filter")
def test_index_view_active_accounts_only(
    mock_investment_filter, mock_saving_filter, user_client
):
    """Test that the index view only includes active accounts in the context."""
    # Setup mocks
    mock_saving_filter.return_value = []
    mock_investment_filter.return_value = []

    # Execute view
    path = reverse("finance:index")
    response = user_client.get(path)

    # Verify filter calls
    assert response.status_code == 200
    mock_saving_filter.assert_called_once_with(is_active=True)
    mock_investment_filter.assert_called_once_with(is_active=True)


@pytest.mark.django_db
@patch("finance.views.SavingAccount.objects.filter")
@patch("finance.views.InvestmentAccount.objects.filter")
def test_index_view_savings_accounts_structure(
    mock_investment_filter, mock_saving_filter, user_client
):
    """Test the structure of savings_accounts in the context."""
    # Create mock saving account
    mock_saving = MagicMock()
    mock_saving.name = "Test Saving Account"
    mock_saving.current_balance = Decimal("1000.00")

    # Create mock progression
    mock_progression = MagicMock(spec=AccountProgression)
    mock_progression.progression = Decimal("10.00")
    mock_progression.difference = 100.0
    mock_progression.css_class = "positive"

    # Setup mock saving account to return mock progression
    mock_saving.get_progression.return_value = mock_progression

    # Setup mock filter to return list with mock saving account
    mock_saving_filter.return_value = [mock_saving]
    mock_investment_filter.return_value = []

    # Execute view
    path = reverse("finance:index")
    response = user_client.get(path)

    # Verify savings_accounts structure
    assert response.status_code == 200
    savings_accounts = response.context["savings_accounts"]
    assert len(savings_accounts) == 1

    saving_account_item = savings_accounts[0]
    assert "model" in saving_account_item
    assert "progression" in saving_account_item

    assert saving_account_item["model"] == mock_saving
    assert saving_account_item["progression"] == mock_progression

    # Verify get_progression was called with the correct days value
    mock_saving.get_progression.assert_called_once_with(30)


@pytest.mark.django_db
@patch("finance.views.SavingAccount.objects.filter")
@patch("finance.views.InvestmentAccount.objects.filter")
def test_index_view_investment_accounts_structure(
    mock_investment_filter, mock_saving_filter, user_client
):
    """Test the structure of investment_accounts in the context."""
    # Create mock investment account
    mock_investment = MagicMock()
    mock_investment.name = "Test Investment Account"
    mock_investment.current_value = Decimal("2000.00")

    # Create mock progression
    mock_progression = MagicMock(spec=AccountProgression)
    mock_progression.progression = Decimal("5.00")
    mock_progression.difference = 100.0
    mock_progression.css_class = "positive"

    # Setup mock investment account to return mock progression
    mock_investment.get_progression.return_value = mock_progression

    # Setup mock filter to return list with mock investment account
    mock_saving_filter.return_value = []
    mock_investment_filter.return_value = [mock_investment]

    # Execute view
    path = reverse("finance:index")
    response = user_client.get(path)

    # Verify investment_accounts structure
    assert response.status_code == 200
    investment_accounts = response.context["investment_accounts"]
    assert len(investment_accounts) == 1

    investment_account_item = investment_accounts[0]
    assert "model" in investment_account_item
    assert "progression" in investment_account_item

    assert investment_account_item["model"] == mock_investment
    assert investment_account_item["progression"] == mock_progression

    # Verify get_progression was called with the correct days value
    mock_investment.get_progression.assert_called_once_with(30)


@pytest.mark.django_db
@patch("finance.views.SavingAccount.objects.filter")
@patch("finance.views.InvestmentAccount.objects.filter")
def test_index_view_custom_days_progression(
    mock_investment_filter, mock_saving_filter, user_client
):
    """Test that the progression is calculated with the custom days value."""
    # Create mock accounts
    mock_saving = MagicMock()
    mock_investment = MagicMock()

    # Setup mock filters
    mock_saving_filter.return_value = [mock_saving]
    mock_investment_filter.return_value = [mock_investment]

    # Execute view with custom days
    custom_days = 15
    path = f"{reverse('finance:index')}?days={custom_days}"
    response = user_client.get(path)

    # Verify get_progression was called with the custom days value
    assert response.status_code == 200
    mock_saving.get_progression.assert_called_once_with(custom_days)
    mock_investment.get_progression.assert_called_once_with(custom_days)
