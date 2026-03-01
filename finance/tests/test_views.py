"""Tests for finance views."""

import datetime
from decimal import Decimal

import pytest
from django.urls import reverse
from moneyed import Money

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
        saving_account_context["progression"].net_progression
        == expected_saving_progression.net_progression
    )

    # For float values (difference), we should compare with a small tolerance
    assert (
        abs(
            saving_account_context["progression"].net_difference.amount
            - expected_saving_progression.net_difference.amount
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
        investment_account_context["progression"].net_progression
        == expected_investment_progression.net_progression
    )
    assert (
        abs(
            investment_account_context["progression"].net_difference.amount
            - expected_investment_progression.net_difference.amount
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
    assert hasattr(saving_progression, "gross_progression")
    assert hasattr(saving_progression, "gross_difference")
    assert hasattr(saving_progression, "net_progression")
    assert hasattr(saving_progression, "net_difference")
    assert hasattr(saving_progression, "css_class")

    # Check that progression values are of the correct type
    assert isinstance(saving_progression.net_progression, Decimal)
    assert isinstance(saving_progression.net_difference.amount, (float, int, Decimal))
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
    assert hasattr(investment_progression, "gross_progression")
    assert hasattr(investment_progression, "gross_difference")
    assert hasattr(investment_progression, "net_progression")
    assert hasattr(investment_progression, "net_difference")
    assert hasattr(investment_progression, "css_class")

    # Check that progression values are of the correct type
    assert isinstance(investment_progression.net_progression, Decimal)
    assert isinstance(
        investment_progression.net_difference.amount, (float, int, Decimal)
    )
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


@pytest.mark.django_db
def test_update_view_unauthenticated(client):
    """Test that unauthenticated users are redirected to login page."""
    path = reverse("finance:update")
    response = client.get(path)
    assert response.status_code == 302
    assert "/accounts/login/" in response.url


@pytest.mark.django_db
def test_update_view_authenticated_get(
    user_client,
    active_saving_account,
    active_investment_account,
):
    """Test that the update view returns the expected context."""
    path = reverse("finance:update")
    response = user_client.get(path)

    assert response.status_code == 200

    # Check that the context contains the expected keys
    assert "form" in response.context
    assert "saving_accounts_formset" in response.context
    assert "investment_accounts_formsets" in response.context

    # Check that the saving formset contains the active saving account
    saving_formset = response.context["saving_accounts_formset"]
    assert len(saving_formset.forms) == 1
    assert saving_formset.forms[0].initial["account_id"] == active_saving_account.id
    assert saving_formset.forms[0].initial["account_name"] == str(active_saving_account)
    assert (
        saving_formset.forms[0].initial["current_value"]
        == active_saving_account.current_value.amount
    )
    assert saving_formset.forms[0].initial.get("update_account") is not True
    assert (
        saving_formset.forms[0].initial["new_value"]
        == active_saving_account.current_value.amount
    )

    # Check that the investment formset grouped contains the active investment account
    investment_accounts_formsets = response.context["investment_accounts_formsets"]
    assert str(active_investment_account) in investment_accounts_formsets

    # Check the investment account cash form
    investment_cash_formset = investment_accounts_formsets[
        str(active_investment_account)
    ]["cash"]
    assert len(investment_cash_formset.forms) == 1
    assert (
        investment_cash_formset.forms[0].initial["account_id"]
        == active_investment_account.id
    )
    assert investment_cash_formset.forms[0].initial["account_name"] == str(
        active_investment_account
    )
    assert investment_cash_formset.forms[0].initial.get("update_account") is not True

    # Check the investment account holdings form if there are any holdings
    if "holdings" in investment_accounts_formsets[str(active_investment_account)]:
        investment_holdings_formset = investment_accounts_formsets[
            str(active_investment_account)
        ]["holdings"]
        if len(investment_holdings_formset.forms) > 0:
            assert (
                investment_holdings_formset.forms[0].initial.get("update_account")
                is not True
            )


@pytest.mark.django_db
def test_update_view_update_all_accounts(
    user_client,
    active_saving_account,
    active_investment_account,
):
    """Test updating all accounts with new values and quantity."""

    # Create a holding for the investment account
    from finance.models.investment_account import (
        InvestmentAccountCash,
        InvestmentAccountHolding,
        InvestmentAccountHoldingHistory,
    )
    from finance.models.saving_account import SavingAccountValue

    holding = InvestmentAccountHolding.objects.create(
        account=active_investment_account,
        name="Test Holding",
        is_active=True,
        initial_quantity=Decimal("10"),
        initial_value=Money(Decimal("100.00"), "EUR"),
    )

    # Record initial counts
    initial_saving_value_count = SavingAccountValue.objects.count()
    initial_cash_value_count = InvestmentAccountCash.objects.count()
    initial_holding_history_count = InvestmentAccountHoldingHistory.objects.count()

    # Get the form first
    path = reverse("finance:update")
    user_client.get(path)  # Just to get the form structure

    # Create a dictionary from the form data
    form_data = {}

    # Add the date field
    form_data["new_values_date"] = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M")

    # Add the saving formset management form data
    form_data["saving_accounts-TOTAL_FORMS"] = "1"
    form_data["saving_accounts-INITIAL_FORMS"] = "1"
    form_data["saving_accounts-MIN_NUM_FORMS"] = "0"
    form_data["saving_accounts-MAX_NUM_FORMS"] = "1000"

    # Add saving account form data
    form_data["saving_accounts-0-account_id"] = str(active_saving_account.id)
    form_data["saving_accounts-0-account_name"] = str(active_saving_account)
    form_data["saving_accounts-0-current_value"] = str(
        active_saving_account.current_value.amount
    )
    form_data["saving_accounts-0-new_value"] = "1500.00"
    form_data["saving_accounts-0-update_account"] = "on"

    # Add the investment account cash formset data
    investment_account_id = active_investment_account.id
    form_data[f"investment_{investment_account_id}_cash-TOTAL_FORMS"] = "1"
    form_data[f"investment_{investment_account_id}_cash-INITIAL_FORMS"] = "1"
    form_data[f"investment_{investment_account_id}_cash-MIN_NUM_FORMS"] = "0"
    form_data[f"investment_{investment_account_id}_cash-MAX_NUM_FORMS"] = "1000"

    form_data[f"investment_{investment_account_id}_cash-0-account_id"] = str(
        active_investment_account.id
    )
    form_data[f"investment_{investment_account_id}_cash-0-account_name"] = str(
        active_investment_account
    )
    form_data[f"investment_{investment_account_id}_cash-0-current_value"] = str(
        active_investment_account.current_cash_value.amount
    )
    form_data[f"investment_{investment_account_id}_cash-0-new_value"] = "2500.00"
    form_data[f"investment_{investment_account_id}_cash-0-update_account"] = "on"

    # Add the investment account holdings formset data
    form_data[f"investment_{investment_account_id}_holdings-TOTAL_FORMS"] = "1"
    form_data[f"investment_{investment_account_id}_holdings-INITIAL_FORMS"] = "1"
    form_data[f"investment_{investment_account_id}_holdings-MIN_NUM_FORMS"] = "0"
    form_data[f"investment_{investment_account_id}_holdings-MAX_NUM_FORMS"] = "1000"

    form_data[f"investment_{investment_account_id}_holdings-0-holding_id"] = str(
        holding.id
    )
    form_data[f"investment_{investment_account_id}_holdings-0-holding_name"] = (
        holding.short_name
    )
    form_data[f"investment_{investment_account_id}_holdings-0-current_value"] = str(
        holding.value.amount
    )
    form_data[f"investment_{investment_account_id}_holdings-0-new_value"] = "150.00"
    form_data[f"investment_{investment_account_id}_holdings-0-current_quantity"] = str(
        holding.quantity or ""
    )
    form_data[f"investment_{investment_account_id}_holdings-0-new_quantity"] = "15"
    form_data[f"investment_{investment_account_id}_holdings-0-update_account"] = "on"

    # Submit the form
    response = user_client.post(path, form_data)

    # Print response content for debugging
    if response.status_code != 302:
        print("Response content:", response.content.decode("utf-8"))
        print(
            "Form errors:",
            response.context["form"].errors
            if "form" in response.context
            else "No form in context",
        )
        print(
            "Saving formset errors:",
            response.context["saving_accounts_formset"].errors
            if "saving_accounts_formset" in response.context
            else "No saving_accounts_formset in context",
        )

        # Check investment formset errors more thoroughly
        if "investment_accounts_formsets" in response.context:
            investment_formsets = response.context["investment_accounts_formsets"]
            print("Investment formsets structure:", type(investment_formsets))
            for account_key, formset_types in investment_formsets.items():
                print(f"Account {account_key}:")
                if "cash" in formset_types:
                    print(f"  Cash formset errors: {formset_types['cash'].errors}")
                    print(
                        f"  Cash formset non_form_errors: {formset_types['cash'].non_form_errors()}"
                    )
                if "holdings" in formset_types:
                    print(
                        f"  Holdings formset errors: {formset_types['holdings'].errors}"
                    )
                    print(
                        f"  Holdings formset non_form_errors: {formset_types['holdings'].non_form_errors()}"
                    )
        else:
            print("No investment_accounts_formsets in context")

        # Print the form data we're submitting
        print("Form data:", form_data)

    # Check that the response redirects to the index page
    assert response.status_code == 302
    assert response.url == reverse("finance:index")

    # Check that new values were created
    # Check saving account value
    assert SavingAccountValue.objects.count() > initial_saving_value_count
    new_saving_value = (
        SavingAccountValue.objects.filter(account=active_saving_account)
        .order_by("-value_date")
        .first()
    )

    assert new_saving_value is not None
    assert new_saving_value.value == Money(1500.00, "EUR")

    # Check investment account cash value
    assert InvestmentAccountCash.objects.count() > initial_cash_value_count
    new_cash_value = (
        InvestmentAccountCash.objects.filter(account=active_investment_account)
        .order_by("-value_date")
        .first()
    )

    assert new_cash_value is not None
    assert new_cash_value.value == Money(2500.00, "EUR")

    # Check investment account holding history
    assert (
        InvestmentAccountHoldingHistory.objects.count() > initial_holding_history_count
    )
    new_holding_history = (
        InvestmentAccountHoldingHistory.objects.filter(holding=holding)
        .order_by("-valuation_date")
        .first()
    )

    assert new_holding_history is not None
    assert new_holding_history.value == Money(150.00, "EUR")
    assert new_holding_history.quantity == 15


@pytest.mark.django_db
def test_update_view_update_one_account(
    user_client,
    active_saving_account,
    active_investment_account,
):
    """Test updating only one account."""

    # Create a holding for the investment account
    from finance.models.investment_account import InvestmentAccountHolding

    holding = InvestmentAccountHolding.objects.create(
        account=active_investment_account,
        name="Test Holding",
        is_active=True,
    )

    # Get the update view first to get the formset management form data
    path = reverse("finance:update")
    # get_response = user_client.get(path)

    # Prepare the POST data - only update the saving account
    account_id = active_investment_account.id
    post_data = {
        "new_values_date": datetime.datetime.now().strftime("%Y-%m-%dT%H:%M"),
        # Saving account formset
        "saving_accounts-TOTAL_FORMS": "1",
        "saving_accounts-INITIAL_FORMS": "1",
        "saving_accounts-MIN_NUM_FORMS": "0",
        "saving_accounts-MAX_NUM_FORMS": "1000",
        "saving_accounts-0-account_id": active_saving_account.id,
        "saving_accounts-0-account_name": str(active_saving_account),
        "saving_accounts-0-current_value": active_saving_account.current_value.amount,
        "saving_accounts-0-update_account": "on",
        "saving_accounts-0-new_value": "1500.00",
        # Investment account cash formset
        f"investment_{account_id}_cash-TOTAL_FORMS": "1",
        f"investment_{account_id}_cash-INITIAL_FORMS": "1",
        f"investment_{account_id}_cash-MIN_NUM_FORMS": "0",
        f"investment_{account_id}_cash-MAX_NUM_FORMS": "1000",
        f"investment_{account_id}_cash-0-account_id": active_investment_account.id,
        f"investment_{account_id}_cash-0-account_name": str(active_investment_account),
        f"investment_{account_id}_cash-0-current_value": active_investment_account.current_cash_value.amount,
        f"investment_{account_id}_cash-0-update_account": "",  # Not checked
        f"investment_{account_id}_cash-0-new_value": "2500.00",
        # Investment account holdings formset
        f"investment_{account_id}_holdings-TOTAL_FORMS": "1",
        f"investment_{account_id}_holdings-INITIAL_FORMS": "1",
        f"investment_{account_id}_holdings-MIN_NUM_FORMS": "0",
        f"investment_{account_id}_holdings-MAX_NUM_FORMS": "1000",
        f"investment_{account_id}_holdings-0-holding_id": holding.id,
        f"investment_{account_id}_holdings-0-holding_name": "Test Holding",
        f"investment_{account_id}_holdings-0-current_value": "100.00",
        f"investment_{account_id}_holdings-0-update_account": "",  # Not checked
        f"investment_{account_id}_holdings-0-new_value": "150.00",
        f"investment_{account_id}_holdings-0-current_quantity": "10",
        f"investment_{account_id}_holdings-0-new_quantity": "15",
    }

    # Submit the form
    response = user_client.post(path, post_data)

    # Check that the response redirects to the index page
    assert response.status_code == 302
    assert response.url == reverse("finance:index")

    # Check that new values were created only for the saving account
    from finance.models.investment_account import (
        InvestmentAccountCash,
        InvestmentAccountHoldingHistory,
    )
    from finance.models.saving_account import SavingAccountValue

    # Check saving account value - should be updated
    new_saving_value = (
        SavingAccountValue.objects.filter(account=active_saving_account)
        .order_by("-value_date")
        .first()
    )

    assert new_saving_value is not None
    assert new_saving_value.value == Money(1500.00, "EUR")

    # Check investment account cash value - should not be updated
    initial_cash_count = InvestmentAccountCash.objects.filter(
        account=active_investment_account
    ).count()

    # If there's a fixture with cash value, count should be 1, otherwise 0
    assert initial_cash_count in [0, 1]

    # Check investment account holding history - should not be updated
    holding_history_count = InvestmentAccountHoldingHistory.objects.filter(
        holding=holding
    ).count()

    assert holding_history_count == 0


@pytest.mark.django_db
def test_update_view_duplicate_values_branch(
    user_client,
    active_saving_account,
    active_investment_account,
    monkeypatch,
):
    from finance.models.investment_account import (
        InvestmentAccountCash,
        InvestmentAccountHolding,
        InvestmentAccountHoldingHistory,
    )
    from finance.models.saving_account import SavingAccount, SavingAccountValue

    monkeypatch.setattr(SavingAccount, "__str__", lambda self: "SavingAccount")
    monkeypatch.setattr(InvestmentAccount, "__str__", lambda self: "InvestmentAccount")
    monkeypatch.setattr(
        InvestmentAccountHolding,
        "__str__",
        lambda self: "InvestmentAccountHolding",
    )

    fixed_date = datetime.datetime(2025, 1, 1, 10, 30)
    holding = InvestmentAccountHolding.objects.create(
        account=active_investment_account,
        name="Duplicate Holding",
        is_active=True,
        initial_quantity=Decimal("10"),
        initial_value=Money(Decimal("100.00"), "EUR"),
    )

    SavingAccountValue.objects.create(
        account=active_saving_account,
        value=Money(Decimal("1500.00"), "EUR"),
        value_date=fixed_date,
    )
    InvestmentAccountCash.objects.create(
        account=active_investment_account,
        value=Money(Decimal("2500.00"), "EUR"),
        value_date=fixed_date,
    )
    InvestmentAccountHoldingHistory.objects.create(
        holding=holding,
        value=Money(Decimal("150.00"), "EUR"),
        quantity=Decimal("15"),
        valuation_date=fixed_date,
    )

    account_id = active_investment_account.id
    post_data = {
        "new_values_date": fixed_date.strftime("%Y-%m-%dT%H:%M"),
        "saving_accounts-TOTAL_FORMS": "1",
        "saving_accounts-INITIAL_FORMS": "1",
        "saving_accounts-MIN_NUM_FORMS": "0",
        "saving_accounts-MAX_NUM_FORMS": "1000",
        "saving_accounts-0-account_id": active_saving_account.id,
        "saving_accounts-0-account_name": str(active_saving_account),
        "saving_accounts-0-current_value": active_saving_account.current_value.amount,
        "saving_accounts-0-update_account": "on",
        "saving_accounts-0-new_value": "1500.00",
        f"investment_{account_id}_cash-TOTAL_FORMS": "1",
        f"investment_{account_id}_cash-INITIAL_FORMS": "1",
        f"investment_{account_id}_cash-MIN_NUM_FORMS": "0",
        f"investment_{account_id}_cash-MAX_NUM_FORMS": "1000",
        f"investment_{account_id}_cash-0-account_id": active_investment_account.id,
        f"investment_{account_id}_cash-0-account_name": str(active_investment_account),
        f"investment_{account_id}_cash-0-current_value": active_investment_account.current_cash_value.amount,
        f"investment_{account_id}_cash-0-update_account": "on",
        f"investment_{account_id}_cash-0-new_value": "2500.00",
        f"investment_{account_id}_holdings-TOTAL_FORMS": "1",
        f"investment_{account_id}_holdings-INITIAL_FORMS": "1",
        f"investment_{account_id}_holdings-MIN_NUM_FORMS": "0",
        f"investment_{account_id}_holdings-MAX_NUM_FORMS": "1000",
        f"investment_{account_id}_holdings-0-holding_id": holding.id,
        f"investment_{account_id}_holdings-0-holding_name": holding.short_name,
        f"investment_{account_id}_holdings-0-current_value": "150.00",
        f"investment_{account_id}_holdings-0-update_account": "on",
        f"investment_{account_id}_holdings-0-new_value": "150.00",
        f"investment_{account_id}_holdings-0-current_quantity": "15",
        f"investment_{account_id}_holdings-0-new_quantity": "15",
    }

    response = user_client.post(reverse("finance:update"), post_data)
    assert response.status_code == 302
    # Duplicate values should be silently ignored with a warning message, not raise an error
    messages_list = list(response.wsgi_request._messages)
    assert any(
        "Duplicate" in str(m) or "already exists" in str(m) for m in messages_list
    )


@pytest.mark.django_db
def test_update_view_invalid_checked_form_branch(
    user_client,
    active_saving_account,
    active_investment_account,
):
    from finance.models.investment_account import InvestmentAccountHolding

    holding = InvestmentAccountHolding.objects.create(
        account=active_investment_account,
        name="Invalid Holding",
        is_active=True,
    )
    account_id = active_investment_account.id

    post_data = {
        "new_values_date": datetime.datetime.now().strftime("%Y-%m-%dT%H:%M"),
        "saving_accounts-TOTAL_FORMS": "1",
        "saving_accounts-INITIAL_FORMS": "1",
        "saving_accounts-MIN_NUM_FORMS": "0",
        "saving_accounts-MAX_NUM_FORMS": "1000",
        "saving_accounts-0-account_id": active_saving_account.id,
        "saving_accounts-0-account_name": str(active_saving_account),
        "saving_accounts-0-current_value": active_saving_account.current_value.amount,
        "saving_accounts-0-update_account": "on",
        "saving_accounts-0-new_value": "",
        f"investment_{account_id}_cash-TOTAL_FORMS": "1",
        f"investment_{account_id}_cash-INITIAL_FORMS": "1",
        f"investment_{account_id}_cash-MIN_NUM_FORMS": "0",
        f"investment_{account_id}_cash-MAX_NUM_FORMS": "1000",
        f"investment_{account_id}_cash-0-account_id": active_investment_account.id,
        f"investment_{account_id}_cash-0-account_name": str(active_investment_account),
        f"investment_{account_id}_cash-0-current_value": active_investment_account.current_cash_value.amount,
        f"investment_{account_id}_cash-0-update_account": "",
        f"investment_{account_id}_cash-0-new_value": "2500.00",
        f"investment_{account_id}_holdings-TOTAL_FORMS": "1",
        f"investment_{account_id}_holdings-INITIAL_FORMS": "1",
        f"investment_{account_id}_holdings-MIN_NUM_FORMS": "0",
        f"investment_{account_id}_holdings-MAX_NUM_FORMS": "1000",
        f"investment_{account_id}_holdings-0-holding_id": holding.id,
        f"investment_{account_id}_holdings-0-holding_name": holding.short_name,
        f"investment_{account_id}_holdings-0-current_value": "100.00",
        f"investment_{account_id}_holdings-0-update_account": "",
        f"investment_{account_id}_holdings-0-new_value": "150.00",
        f"investment_{account_id}_holdings-0-current_quantity": "10",
        f"investment_{account_id}_holdings-0-new_quantity": "15",
    }

    response = user_client.post(reverse("finance:update"), post_data)
    assert response.status_code == 200
    assert "saving_accounts_formset" in response.context
