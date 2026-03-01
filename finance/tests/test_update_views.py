"""Tests for finance/views/update_views.py."""

import datetime
from decimal import Decimal

import pytest
from django.urls import reverse
from moneyed import Money

from finance.models.investment_account import (
    InvestmentAccount,
    InvestmentAccountCash,
    InvestmentAccountHolding,
    InvestmentAccountHoldingHistory,
    InvestmentAccountType,
)
from finance.models.saving_account import (
    SavingAccount,
    SavingAccountType,
    SavingAccountValue,
)


@pytest.fixture
def saving_account_type():
    return SavingAccountType.objects.create(name="Livret A", code="LA")


@pytest.fixture
def saving_account(saving_account_type):
    return SavingAccount.objects.create(
        account_type=saving_account_type,
        name="Test Livret",
        owner="Test Owner",
        institution="Test Bank",
        is_active=True,
        opening_value=Money(Decimal("1000.00"), "EUR"),
        opening_date=datetime.date.today() - datetime.timedelta(days=60),
        interest_rate=Decimal("3.0"),
    )


@pytest.fixture
def investment_account_type():
    return InvestmentAccountType.objects.create(name="PEA", code="PEA")


@pytest.fixture
def investment_account(investment_account_type):
    return InvestmentAccount.objects.create(
        account_type=investment_account_type,
        name="Test PEA",
        owner="Test Owner",
        institution="Test Broker",
        is_active=True,
        opening_cash_value=Money(Decimal("5000.00"), "EUR"),
        opening_date=datetime.date.today() - datetime.timedelta(days=60),
    )


@pytest.fixture
def investment_holding(investment_account):
    return InvestmentAccountHolding.objects.create(
        account=investment_account,
        name="Test ETF",
        code="ETF",
        is_active=True,
        initial_quantity=Decimal("10"),
        initial_value=Money(Decimal("100.00"), "EUR"),
    )


@pytest.mark.django_db
class TestUpdateAccountsGet:
    def test_get_update_page_empty(self, user_client):
        url = reverse("finance:update")
        response = user_client.get(url)
        assert response.status_code == 200
        assert "form" in response.context
        assert "saving_accounts_formset" in response.context

    def test_get_update_page_with_saving_account(self, user_client, saving_account):
        url = reverse("finance:update")
        response = user_client.get(url)
        assert response.status_code == 200
        assert "saving_accounts_formset" in response.context

    def test_get_update_page_with_investment_account(
        self, user_client, investment_account
    ):
        url = reverse("finance:update")
        response = user_client.get(url)
        assert response.status_code == 200
        assert "investment_accounts_formsets" in response.context

    def test_get_update_page_with_holding(
        self, user_client, investment_account, investment_holding
    ):
        url = reverse("finance:update")
        response = user_client.get(url)
        assert response.status_code == 200


@pytest.mark.django_db
class TestUpdateAccountsPost:
    def test_post_no_updates_shows_info(self, user_client, saving_account):
        url = reverse("finance:update")
        data = {
            "new_values_date": datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "saving_accounts-TOTAL_FORMS": "1",
            "saving_accounts-INITIAL_FORMS": "0",
            "saving_accounts-MIN_NUM_FORMS": "0",
            "saving_accounts-MAX_NUM_FORMS": "1000",
            "saving_accounts-0-account_id": str(saving_account.pk),
            "saving_accounts-0-account_name": str(saving_account),
            "saving_accounts-0-current_value": "1000.00",
            "saving_accounts-0-new_value": "1000.00",
            "saving_accounts-0-update_account": "",  # Not checked
        }
        response = user_client.post(url, data)
        assert response.status_code == 302

    def test_post_with_saving_account_update(self, user_client, saving_account):
        url = reverse("finance:update")
        new_date = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        data = {
            "new_values_date": new_date,
            "saving_accounts-TOTAL_FORMS": "1",
            "saving_accounts-INITIAL_FORMS": "0",
            "saving_accounts-MIN_NUM_FORMS": "0",
            "saving_accounts-MAX_NUM_FORMS": "1000",
            "saving_accounts-0-account_id": str(saving_account.pk),
            "saving_accounts-0-account_name": str(saving_account),
            "saving_accounts-0-current_value": "1000.00",
            "saving_accounts-0-new_value": "1100.00",
            "saving_accounts-0-update_account": "on",
        }
        response = user_client.post(url, data)
        assert response.status_code == 302
        assert SavingAccountValue.objects.filter(
            account=saving_account,
            value=Money(Decimal("1100.00"), "EUR"),
        ).exists()

    def test_post_duplicate_saving_account_value_shows_warning(
        self, user_client, saving_account
    ):
        """Posting the same value twice for the same date should show a warning."""
        fixed_date = datetime.datetime(2023, 6, 15, 12, 0, 0)
        # Create existing value
        SavingAccountValue.objects.create(
            account=saving_account,
            value=Money(Decimal("1100.00"), "EUR"),
            value_date=fixed_date,
        )
        url = reverse("finance:update")
        data = {
            "new_values_date": fixed_date.strftime("%Y-%m-%dT%H:%M:%S"),
            "saving_accounts-TOTAL_FORMS": "1",
            "saving_accounts-INITIAL_FORMS": "0",
            "saving_accounts-MIN_NUM_FORMS": "0",
            "saving_accounts-MAX_NUM_FORMS": "1000",
            "saving_accounts-0-account_id": str(saving_account.pk),
            "saving_accounts-0-account_name": str(saving_account),
            "saving_accounts-0-current_value": "1100.00",
            "saving_accounts-0-new_value": "1100.00",
            "saving_accounts-0-update_account": "on",
        }
        response = user_client.post(url, data)
        assert response.status_code == 302

    def test_post_with_investment_cash_update(self, user_client, investment_account):
        url = reverse("finance:update")
        new_date = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        data = {
            "new_values_date": new_date,
            "saving_accounts-TOTAL_FORMS": "0",
            "saving_accounts-INITIAL_FORMS": "0",
            "saving_accounts-MIN_NUM_FORMS": "0",
            "saving_accounts-MAX_NUM_FORMS": "1000",
            f"investment_{investment_account.pk}_cash-TOTAL_FORMS": "1",
            f"investment_{investment_account.pk}_cash-INITIAL_FORMS": "0",
            f"investment_{investment_account.pk}_cash-MIN_NUM_FORMS": "0",
            f"investment_{investment_account.pk}_cash-MAX_NUM_FORMS": "1000",
            f"investment_{investment_account.pk}_cash-0-account_id": str(
                investment_account.pk
            ),
            f"investment_{investment_account.pk}_cash-0-account_name": str(
                investment_account
            ),
            f"investment_{investment_account.pk}_cash-0-current_value": "500.00",
            f"investment_{investment_account.pk}_cash-0-new_value": "600.00",
            f"investment_{investment_account.pk}_cash-0-update_account": "on",
            f"investment_{investment_account.pk}_holdings-TOTAL_FORMS": "0",
            f"investment_{investment_account.pk}_holdings-INITIAL_FORMS": "0",
            f"investment_{investment_account.pk}_holdings-MIN_NUM_FORMS": "0",
            f"investment_{investment_account.pk}_holdings-MAX_NUM_FORMS": "1000",
        }
        response = user_client.post(url, data)
        assert response.status_code == 302
        assert InvestmentAccountCash.objects.filter(
            account=investment_account,
            value=Money(Decimal("600.00"), "EUR"),
        ).exists()

    def test_post_with_holding_update(
        self, user_client, investment_account, investment_holding
    ):
        url = reverse("finance:update")
        new_date = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        data = {
            "new_values_date": new_date,
            "saving_accounts-TOTAL_FORMS": "0",
            "saving_accounts-INITIAL_FORMS": "0",
            "saving_accounts-MIN_NUM_FORMS": "0",
            "saving_accounts-MAX_NUM_FORMS": "1000",
            f"investment_{investment_account.pk}_cash-TOTAL_FORMS": "0",
            f"investment_{investment_account.pk}_cash-INITIAL_FORMS": "0",
            f"investment_{investment_account.pk}_cash-MIN_NUM_FORMS": "0",
            f"investment_{investment_account.pk}_cash-MAX_NUM_FORMS": "1000",
            f"investment_{investment_account.pk}_holdings-TOTAL_FORMS": "1",
            f"investment_{investment_account.pk}_holdings-INITIAL_FORMS": "0",
            f"investment_{investment_account.pk}_holdings-MIN_NUM_FORMS": "0",
            f"investment_{investment_account.pk}_holdings-MAX_NUM_FORMS": "1000",
            f"investment_{investment_account.pk}_holdings-0-holding_id": str(
                investment_holding.pk
            ),
            f"investment_{investment_account.pk}_holdings-0-holding_name": investment_holding.short_name,
            f"investment_{investment_account.pk}_holdings-0-current_value": "1000.00",
            f"investment_{investment_account.pk}_holdings-0-new_value": "1100.00",
            f"investment_{investment_account.pk}_holdings-0-current_quantity": "10",
            f"investment_{investment_account.pk}_holdings-0-new_quantity": "10",
            f"investment_{investment_account.pk}_holdings-0-update_account": "on",
        }
        response = user_client.post(url, data)
        assert response.status_code == 302
        assert InvestmentAccountHoldingHistory.objects.filter(
            holding=investment_holding,
        ).exists()

    def test_post_no_date_uses_now(self, user_client, saving_account):
        url = reverse("finance:update")
        data = {
            # No new_values_date
            "saving_accounts-TOTAL_FORMS": "1",
            "saving_accounts-INITIAL_FORMS": "0",
            "saving_accounts-MIN_NUM_FORMS": "0",
            "saving_accounts-MAX_NUM_FORMS": "1000",
            "saving_accounts-0-account_id": str(saving_account.pk),
            "saving_accounts-0-account_name": str(saving_account),
            "saving_accounts-0-current_value": "1000.00",
            "saving_accounts-0-new_value": "1050.00",
            "saving_accounts-0-update_account": "on",
        }
        response = user_client.post(url, data)
        assert response.status_code == 302
