"""Tests for the context returned by the finance index view."""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from django.http import HttpRequest, QueryDict
from django.urls import reverse
from moneyed import Money

from finance.utils import AccountProgression
from finance.views import IndexView


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
@patch("finance.views.render")
def test_index_view_context_keys(
    mock_render, mock_investment_filter, mock_saving_filter, user
):
    """Test that the index view returns the expected context keys."""
    # Setup mocks
    mock_saving_filter.return_value = []
    mock_investment_filter.return_value = []
    mock_render.return_value = MagicMock()

    # Create request
    request = HttpRequest()
    request.user = user
    request.method = "GET"
    request.GET = QueryDict("")

    # Call view directly
    view = IndexView()
    view.get(request)

    # Verify context keys
    context = mock_render.call_args[0][2]
    assert "days" in context
    assert "savings_accounts" in context
    assert "investment_accounts" in context
    assert context["days"] == 30  # Default value


@pytest.mark.django_db
@patch("finance.views.SavingAccount.objects.filter")
@patch("finance.views.InvestmentAccount.objects.filter")
@patch("finance.views.render")
def test_index_view_custom_days(
    mock_render, mock_investment_filter, mock_saving_filter, user
):
    """Test that the index view uses the days parameter from the request."""
    # Setup mocks
    mock_saving_filter.return_value = []
    mock_investment_filter.return_value = []
    mock_render.return_value = MagicMock()

    # Create request with custom days
    request = HttpRequest()
    request.user = user
    request.method = "GET"
    query_dict = QueryDict("", mutable=True)
    query_dict["days"] = "15"
    request.GET = query_dict

    # Call view directly
    view = IndexView()
    view.get(request)

    # Verify days value
    context = mock_render.call_args[0][2]
    assert context["days"] == 15


@pytest.mark.django_db
@patch("finance.views.SavingAccount.objects.filter")
@patch("finance.views.InvestmentAccount.objects.filter")
@patch("finance.views.render")
def test_index_view_active_accounts_only(
    mock_render, mock_investment_filter, mock_saving_filter, user
):
    """Test that the index view only includes active accounts in the context."""
    # Setup mocks
    mock_saving_filter.return_value = []
    mock_investment_filter.return_value = []
    mock_render.return_value = MagicMock()

    # Create request
    request = HttpRequest()
    request.user = user
    request.method = "GET"
    request.GET = QueryDict("")

    # Call view directly
    view = IndexView()
    view.get(request)

    # Verify filter calls
    mock_saving_filter.assert_called_once_with(is_active=True)
    mock_investment_filter.assert_called_once_with(is_active=True)


@pytest.mark.django_db
@patch("finance.views.SavingAccount.objects.filter")
@patch("finance.views.InvestmentAccount.objects.filter")
@patch("finance.views.render")
def test_index_view_savings_accounts_structure(
    mock_render, mock_investment_filter, mock_saving_filter, user
):
    """Test the structure of savings_accounts in the context."""
    # Create mock saving account
    mock_saving = MagicMock()
    mock_saving.name = "Test Saving Account"
    mock_saving.current_balance = Money(Decimal("1000.00"), "EUR")

    # Create mock progression
    mock_progression = MagicMock(spec=AccountProgression)
    mock_progression.progression = Money(Decimal("10.00"), "EUR")
    mock_progression.difference = Money(Decimal("100.0"), "EUR")
    mock_progression.css_class = "positive"

    # Setup mock saving account to return mock progression
    mock_saving.get_progression.return_value = mock_progression

    # Setup mock filter to return list with mock saving account
    mock_saving_filter.return_value = [mock_saving]
    mock_investment_filter.return_value = []
    mock_render.return_value = MagicMock()

    # Create request
    request = HttpRequest()
    request.user = user
    request.method = "GET"
    request.GET = QueryDict("")

    # Call view directly
    view = IndexView()
    view.get(request)

    # Verify savings_accounts structure
    context = mock_render.call_args[0][2]
    savings_accounts = context["savings_accounts"]
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
@patch("finance.views.render")
def test_index_view_investment_accounts_structure(
    mock_render, mock_investment_filter, mock_saving_filter, user
):
    """Test the structure of investment_accounts in the context."""
    # Create mock investment account
    mock_investment = MagicMock()
    mock_investment.name = "Test Investment Account"
    mock_investment.current_value = Money(Decimal("2000.00"), "EUR")

    # Create mock progression
    mock_progression = MagicMock(spec=AccountProgression)
    mock_progression.progression = Money(Decimal("5.00"), "EUR")
    mock_progression.difference = Money(Decimal("100.0"), "EUR")
    mock_progression.css_class = "positive"

    # Setup mock investment account to return mock progression
    mock_investment.get_progression.return_value = mock_progression

    # Setup mock filter to return list with mock investment account
    mock_saving_filter.return_value = []
    mock_investment_filter.return_value = [mock_investment]
    mock_render.return_value = MagicMock()

    # Create request
    request = HttpRequest()
    request.user = user
    request.method = "GET"
    request.GET = QueryDict("")

    # Call view directly
    view = IndexView()
    view.get(request)

    # Verify investment_accounts structure
    context = mock_render.call_args[0][2]
    investment_accounts = context["investment_accounts"]
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
@patch("finance.views.render")
def test_index_view_custom_days_progression(
    mock_render, mock_investment_filter, mock_saving_filter, user
):
    """Test that the progression is calculated with the custom days value."""
    # Create mock accounts
    mock_saving = MagicMock()
    mock_saving.current_balance = Money(Decimal("1000.00"), "EUR")
    mock_saving.get_progression.return_value = MagicMock(
        spec=AccountProgression,
        progression=Money(Decimal("10.00"), "EUR"),
        difference=Money(Decimal("100.0"), "EUR"),
        css_class="positive",
    )

    mock_investment = MagicMock()
    mock_investment.current_value = Money(Decimal("2000.00"), "EUR")
    mock_investment.get_progression.return_value = MagicMock(
        spec=AccountProgression,
        progression=Money(Decimal("5.00"), "EUR"),
        difference=Money(Decimal("100.0"), "EUR"),
        css_class="positive",
    )

    # Setup mock filters
    mock_saving_filter.return_value = [mock_saving]
    mock_investment_filter.return_value = [mock_investment]
    mock_render.return_value = MagicMock()

    # Create request with custom days
    custom_days = 15
    request = HttpRequest()
    request.user = user
    request.method = "GET"
    query_dict = QueryDict("", mutable=True)
    query_dict["days"] = str(custom_days)
    request.GET = query_dict

    # Call view directly
    view = IndexView()
    view.get(request)

    # Verify get_progression was called with the custom days value
    mock_saving.get_progression.assert_called_once_with(custom_days)
    mock_investment.get_progression.assert_called_once_with(custom_days)
