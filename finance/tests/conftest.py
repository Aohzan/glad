"""
Conftest file for finance app tests.
This file imports fixtures from the central conftest.py
and defines fixtures specific to the finance app.
"""

import datetime
from decimal import Decimal

import pytest

from finance.models.investment_account import (
    InvestmentAccount,
    InvestmentAccountCash,
    InvestmentAccountType,
)
from finance.models.saving_account import (
    SavingAccount,
    SavingAccountType,
    SavingAccountValue,
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
    "saving_account_value",
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
        opening_value=Money(Decimal("1000.00"), "EUR"),
        opening_date=datetime.datetime.today() - datetime.timedelta(days=60),
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
        opening_value=Money(Decimal("500.00"), "EUR"),
        opening_date=datetime.datetime.today() - datetime.timedelta(days=60),
        interest_rate=Decimal("1.5"),
    )


@pytest.fixture
def saving_account_value(active_saving_account):
    """Create a saving account value for testing."""
    from djmoney.money import Money

    value = SavingAccountValue.objects.create(
        account=active_saving_account,
        value=Money(Decimal("1100.00"), "EUR"),
        value_date=datetime.datetime.today() - datetime.timedelta(days=15),
    )
    return value


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
        opening_cash_value=Money(Decimal("2000.00"), "EUR"),
        opening_date=datetime.datetime.today() - datetime.timedelta(days=60),
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
        opening_cash_value=Money(Decimal("1000.00"), "EUR"),
        opening_date=datetime.datetime.today() - datetime.timedelta(days=60),
    )


@pytest.fixture
def investment_account_cash(active_investment_account):
    """Create an investment account cash value for testing."""
    from djmoney.money import Money

    cash = InvestmentAccountCash.objects.create(
        account=active_investment_account,
        value=Money(Decimal("2200.00"), "EUR"),
        value_date=datetime.datetime.today() - datetime.timedelta(days=15),
    )
    return cash
