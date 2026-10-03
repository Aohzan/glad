"""Tests for the bulk account valuations of finance.services.history."""

import datetime
from decimal import Decimal

import pytest
from moneyed import Money

from finance.models.investment_account import (
    InvestmentAccount,
    InvestmentAccountCash,
    InvestmentAccountHolding,
    InvestmentAccountHoldingHistory,
)
from finance.models.saving_account import SavingAccount, SavingAccountValue
from finance.services.history import investment_values_at, saving_values_at

DATES = [
    datetime.date(2024, 1, 31),
    datetime.date(2024, 2, 29),
    datetime.date(2024, 3, 31),
    datetime.date(2024, 4, 30),
    datetime.date(2024, 5, 31),
]


@pytest.fixture
def saving_with_values(saving_account_type):
    """Saving account revalued during the period, including at the end of a day."""
    account = SavingAccount.objects.create(
        account_type=saving_account_type,
        opening_value=Money(1000, "EUR"),
        opening_date=datetime.date(2024, 1, 1),
    )
    for value_date, value in [
        (datetime.datetime(2024, 2, 10, 9, 0), 1100),
        (datetime.datetime(2024, 3, 31, 23, 0), 1200),
        (datetime.datetime(2024, 4, 1, 0, 0), 1250),
    ]:
        SavingAccountValue.objects.create(
            account=account, value=Money(value, "EUR"), value_date=value_date
        )
    return account


@pytest.fixture
def investment_with_history(investment_account_type):
    """Investment account with cash records and several kinds of holdings."""
    account = InvestmentAccount.objects.create(
        account_type=investment_account_type,
        opening_cash_value=Money(500, "EUR"),
        opening_date=datetime.date(2024, 1, 1),
    )
    InvestmentAccountCash.objects.create(
        account=account, value=Money(300, "EUR"), value_date=datetime.date(2024, 2, 1)
    )
    # A cash value of zero must not fall back to the opening cash.
    InvestmentAccountCash.objects.create(
        account=account, value=Money(0, "EUR"), value_date=datetime.date(2024, 4, 30)
    )
    valued = InvestmentAccountHolding.objects.create(
        account=account,
        name="Valued",
        initial_value=Money(100, "EUR"),
        initial_valuation_date=datetime.date(2024, 1, 15),
    )
    for valuation_date, value in [
        (datetime.datetime(2024, 2, 15, 12, 0), 150),
        # Same day as a date of the series: ignored until the next one.
        (datetime.datetime(2024, 3, 31, 10, 0), 180),
    ]:
        InvestmentAccountHoldingHistory.objects.create(
            holding=valued, value=Money(value, "EUR"), valuation_date=valuation_date
        )
    InvestmentAccountHolding.objects.create(
        account=account,
        name="Bought later",
        initial_value=Money(40, "EUR"),
        initial_valuation_date=datetime.date(2024, 3, 1),
    )
    closed = InvestmentAccountHolding.objects.create(
        account=account,
        name="Closed",
        is_active=False,
        initial_value=Money(1000, "EUR"),
        initial_valuation_date=datetime.date(2024, 1, 1),
    )
    InvestmentAccountHoldingHistory.objects.create(
        holding=closed,
        value=Money(2000, "EUR"),
        valuation_date=datetime.datetime(2024, 2, 1),
    )
    return account


@pytest.mark.django_db
def test_saving_values_match_get_value(saving_with_values):
    """Each value is the one get_value() returns at the same date."""
    values = saving_values_at([saving_with_values], DATES)

    assert values[saving_with_values.pk] == [
        saving_with_values.get_value(max_date=d).amount for d in DATES
    ]
    assert values[saving_with_values.pk] == [
        Decimal(1000),
        Decimal(1100),
        Decimal(1200),
        Decimal(1250),
        Decimal(1250),
    ]


@pytest.mark.django_db
def test_saving_values_without_history_use_opening_value(saving_account_type):
    """An account never revalued keeps its opening value."""
    account = SavingAccount.objects.create(
        account_type=saving_account_type, opening_value=Money(42, "EUR")
    )

    assert saving_values_at([account], DATES[:2]) == {
        account.pk: [Decimal(42), Decimal(42)]
    }


@pytest.mark.django_db
def test_investment_values_match_get_value(investment_with_history):
    """Cash plus active holdings, as get_value() computes them."""
    values = investment_values_at([investment_with_history], DATES)

    assert values[investment_with_history.pk] == [
        investment_with_history.get_value(max_date=d).amount for d in DATES
    ]
    assert values[investment_with_history.pk] == [
        Decimal(600),  # opening cash 500 + initial value 100
        Decimal(450),  # cash 300 + valuation 150
        Decimal(490),  # + holding bought on March 1st, valuation of the 31st ignored
        Decimal(220),  # cash 0 + 180 + 40
        Decimal(220),
    ]


@pytest.mark.django_db
def test_investment_values_without_holdings_are_cash(investment_account_type):
    """An account without holdings is worth its cash."""
    account = InvestmentAccount.objects.create(
        account_type=investment_account_type, opening_cash_value=Money(70, "EUR")
    )

    assert investment_values_at([account], DATES[:1]) == {account.pk: [Decimal(70)]}


@pytest.mark.django_db
def test_values_use_a_fixed_number_of_queries(
    saving_with_values, investment_with_history, django_assert_num_queries
):
    """The number of queries does not depend on the number of dates."""
    with django_assert_num_queries(1):
        saving_values_at([saving_with_values], DATES)
    with django_assert_num_queries(3):
        investment_values_at([investment_with_history], DATES)
