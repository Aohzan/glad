"""
Conftest file for finance app tests.
This file imports fixtures from the central conftest.py
and defines fixtures specific to the finance app.
"""

import datetime
from decimal import Decimal

import pytest
from django.utils import timezone

from finance.models.investment_account import (
    InvestmentAccount,
    InvestmentAccountCash,
    InvestmentAccountType,
)
from finance.models.saving_account import (
    SavingAccount,
    SavingAccountBalance,
    SavingAccountType,
)
from tests.conftest import (
    ADMIN_PASSWORD,
    ADMIN_USER,
    TEST_PASSWORD,
    TEST_USER,
    admin_client,
    admin_user,
    client,
    user,
    user_client,
)

# Re-export all fixtures from the central conftest.py
__all__ = [
    "ADMIN_USER",
    "ADMIN_PASSWORD",
    "TEST_USER",
    "TEST_PASSWORD",
    "admin_user",
    "user",
    "client",
    "admin_client",
    "user_client",
    "saving_account_type",
    "active_saving_account",
    "inactive_saving_account",
    "saving_account_balance",
    "investment_account_type",
    "active_investment_account",
    "inactive_investment_account",
    "investment_account_cash",
]


@pytest.fixture
def saving_account_type():
    """Create a saving account type for testing."""
    return SavingAccountType.objects.create(name="Test Saving Type", code="TST")


@pytest.fixture
def active_saving_account(saving_account_type):
    """Create an active saving account for testing."""
    from djmoney.money import Money

    return SavingAccount.objects.create(
        account_type=saving_account_type,
        name="Test Active Saving Account",
        owner="Test Owner",
        institution="Test Bank",
        is_active=True,
        initial_balance=Money(Decimal("1000.00"), "EUR"),
        initial_balance_date=timezone.now().date() - datetime.timedelta(days=60),
        interest_rate=Decimal("2.5"),
    )


@pytest.fixture
def inactive_saving_account(saving_account_type):
    """Create an inactive saving account for testing."""
    from djmoney.money import Money

    return SavingAccount.objects.create(
        account_type=saving_account_type,
        name="Test Inactive Saving Account",
        owner="Test Owner",
        institution="Test Bank",
        is_active=False,
        initial_balance=Money(Decimal("500.00"), "EUR"),
        initial_balance_date=timezone.now().date() - datetime.timedelta(days=60),
        interest_rate=Decimal("1.5"),
    )


@pytest.fixture
def saving_account_balance(active_saving_account):
    """Create a saving account balance for testing."""
    from djmoney.money import Money

    balance = SavingAccountBalance.objects.create(
        account=active_saving_account,  # Correction ici
        balance=Money(Decimal("1100.00"), "EUR"),
        balance_date=timezone.now().date() - datetime.timedelta(days=15),
    )
    return balance


@pytest.fixture
def investment_account_type():
    """Create an investment account type for testing."""
    return InvestmentAccountType.objects.create(name="Test Investment Type", code="TIT")


@pytest.fixture
def active_investment_account(investment_account_type):
    """Create an active investment account for testing."""
    from djmoney.money import Money

    return InvestmentAccount.objects.create(
        account_type=investment_account_type,
        name="Test Active Investment Account",
        owner="Test Owner",
        institution="Test Broker",
        is_active=True,
        initial_cash_balance=Money(Decimal("2000.00"), "EUR"),
        initial_cash_balance_date=timezone.now().date() - datetime.timedelta(days=60),
    )


@pytest.fixture
def inactive_investment_account(investment_account_type):
    """Create an inactive investment account for testing."""
    from djmoney.money import Money

    return InvestmentAccount.objects.create(
        account_type=investment_account_type,
        name="Test Inactive Investment Account",
        owner="Test Owner",
        institution="Test Broker",
        is_active=False,
        initial_cash_balance=Money(Decimal("1000.00"), "EUR"),
        initial_cash_balance_date=timezone.now().date() - datetime.timedelta(days=60),
    )


@pytest.fixture
def investment_account_cash(active_investment_account):
    """Create an investment account cash balance for testing."""
    from djmoney.money import Money

    cash = InvestmentAccountCash.objects.create(
        account=active_investment_account,  # Correction ici
        balance=Money(Decimal("2200.00"), "EUR"),
        balance_date=timezone.now().date() - datetime.timedelta(days=15),
    )
    return cash
