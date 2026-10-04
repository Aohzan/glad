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
from finance.services.history import InvestmentValues, SavingValues

DATES = [
    datetime.date(2024, 1, 31),
    datetime.date(2024, 2, 29),
    datetime.date(2024, 3, 31),
    datetime.date(2024, 4, 30),
    datetime.date(2024, 5, 31),
]
#: Dates and datetimes around the values saved on March 31st and April 1st.
MOMENTS = [
    *DATES,
    datetime.datetime(2024, 3, 31),
    datetime.datetime(2024, 3, 31, 12, 0),
    datetime.datetime(2024, 3, 31, 23, 30),
    datetime.datetime(2024, 4, 1),
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
        # Counted from 10:00 by a datetime, the day after by a date.
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
    """Each value is the one get_value() returns at the same date or datetime."""
    values = SavingValues([saving_with_values])

    assert [values.at(saving_with_values, m) for m in MOMENTS] == [
        saving_with_values.get_value(max_date=m).amount for m in MOMENTS
    ]
    assert [values.at(saving_with_values, d) for d in DATES] == [
        Decimal(1000),
        Decimal(1100),
        Decimal(1200),  # a date reads up to the end of the day
        Decimal(1250),
        Decimal(1250),
    ]
    assert values.at(saving_with_values, MOMENTS[-3]) == Decimal(1100)


@pytest.mark.django_db
def test_saving_values_without_history_use_opening_value(saving_account_type):
    """An account never revalued keeps its opening value."""
    account = SavingAccount.objects.create(
        account_type=saving_account_type, opening_value=Money(42, "EUR")
    )

    assert SavingValues([account]).at(account, DATES[0]) == Decimal(42)


@pytest.mark.django_db
def test_investment_values_match_get_value(investment_with_history):
    """Cash plus active holdings, as get_value() computes them."""
    values = InvestmentValues([investment_with_history])

    assert [values.at(investment_with_history, m) for m in MOMENTS] == [
        investment_with_history.get_value(max_date=m).amount for m in MOMENTS
    ]
    assert [values.at(investment_with_history, d) for d in DATES] == [
        Decimal(600),  # opening cash 500 + initial value 100
        Decimal(450),  # cash 300 + valuation 150
        Decimal(490),  # + holding bought on March 1st, valuation of the 31st ignored
        Decimal(220),  # cash 0 + 180 + 40
        Decimal(220),
    ]
    assert values.at(investment_with_history, MOMENTS[-3]) == Decimal(520)


@pytest.mark.django_db
def test_investment_values_without_holdings_are_cash(investment_account_type):
    """An account without holdings is worth its cash."""
    account = InvestmentAccount.objects.create(
        account_type=investment_account_type, opening_cash_value=Money(70, "EUR")
    )

    assert InvestmentValues([account]).at(account, DATES[0]) == Decimal(70)


@pytest.mark.django_db
def test_histories_are_read_once(
    saving_with_values, investment_with_history, django_assert_num_queries
):
    """Reading the values at any number of dates runs no more queries."""
    with django_assert_num_queries(1):
        saving_values = SavingValues([saving_with_values])
    with django_assert_num_queries(3):
        investment_values = InvestmentValues([investment_with_history])
    with django_assert_num_queries(0):
        for moment in MOMENTS:
            saving_values.at(saving_with_values, moment)
            investment_values.at(investment_with_history, moment)
