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


@pytest.fixture
def investment_holding_history(active_investment_account):
    """Create an InvestmentAccountHolding with one history entry for testing."""
    from djmoney.money import Money

    holding = InvestmentAccountHolding.objects.create(
        account=active_investment_account,
        name="Test Holding",
        is_active=True,
        initial_value=Money(Decimal("100"), "EUR"),
    )
    return InvestmentAccountHoldingHistory.objects.create(
        holding=holding,
        value=Money(Decimal("300"), "EUR"),
        quantity=Decimal("3"),
        valuation_date=datetime.datetime(2025, 2, 1, 10, 0, 0),
    )


@pytest.fixture
def declining_saving_account(saving_account_type):
    """Create a saving account whose value has declined over the past 35 days."""
    from djmoney.money import Money

    acc = SavingAccount.objects.create(
        name="Declining",
        account_type=saving_account_type,
        opening_value=Money(0, "EUR"),
        is_active=True,
    )
    SavingAccountValue.objects.create(
        account=acc,
        value=Money(2000, "EUR"),
        value_date=datetime.date.today() - datetime.timedelta(days=35),
    )
    SavingAccountValue.objects.create(
        account=acc,
        value=Money(1000, "EUR"),
        value_date=datetime.date.today(),
    )
    return acc
