"""The values of an account follow a change of its currency."""

import datetime
from decimal import Decimal

import pytest
from djmoney.money import Money

from finance.models.investment_account import (
    InvestmentAccountCash,
    InvestmentAccountDeposit,
    InvestmentAccountHolding,
    InvestmentAccountHoldingHistory,
)
from finance.models.other_asset import OtherAsset, OtherAssetValue
from finance.models.saving_account import SavingAccountDeposit, SavingAccountValue
from finance.signals import follow_currency

pytestmark = pytest.mark.django_db
DAY = datetime.date(2025, 3, 1)


def _currencies(*rows):
    return {str(money.currency) for money in rows}


def test_investment_account_values_follow_its_currency(active_investment_account):
    account = active_investment_account
    cash = InvestmentAccountCash.objects.create(
        account=account, value=Money(159, "USD"), value_date=DAY
    )
    deposit = InvestmentAccountDeposit.objects.create(
        account=account,
        amount=Money(500, "USD"),
        deposit_date=DAY,
        update_account_cash=False,
    )
    holding = InvestmentAccountHolding.objects.create(
        account=account, name="Apple", initial_value=Money(340, "USD")
    )
    history = InvestmentAccountHoldingHistory.objects.create(
        holding=holding,
        value=Money(350, "USD"),
        quantity=Decimal(2),
        valuation_date=datetime.datetime(2025, 3, 2),
    )

    # The account was in USD, like its values; it is corrected to EUR.
    account.save()
    for row in (cash, deposit, holding, history):
        row.refresh_from_db()

    assert _currencies(
        cash.value, deposit.amount, holding.initial_value, history.value
    ) == {"EUR"}
    # The amounts were entered in the account currency: they are not converted.
    assert cash.value.amount == Decimal(159)


def test_saving_account_values_follow_its_currency(active_saving_account):
    account = active_saving_account
    value = SavingAccountValue.objects.create(
        account=account, value=Money(1100, "EUR"), value_date=datetime.datetime.now()
    )
    deposit = SavingAccountDeposit.objects.create(
        account=account,
        amount=Money(100, "EUR"),
        deposit_date=DAY,
        update_account_value=False,
    )

    account.opening_value = Money(1000, "CHF")
    account.save()
    value.refresh_from_db()
    deposit.refresh_from_db()

    assert _currencies(value.value, deposit.amount) == {"CHF"}


def test_other_asset_values_follow_its_currency():
    asset = OtherAsset.objects.create(name="Watch", acquisition_value=Money(0, "EUR"))
    value = OtherAssetValue.objects.create(
        asset=asset, value=Money(900, "EUR"), value_date=DAY
    )

    asset.acquisition_value = Money(800, "USD")
    asset.save()
    value.refresh_from_db()

    assert str(value.value.currency) == "USD"


def test_a_fixture_load_keeps_the_currencies(active_saving_account):
    value = SavingAccountValue.objects.create(
        account=active_saving_account,
        value=Money(1100, "USD"),
        value_date=datetime.datetime.now(),
    )
    follow_currency(type(active_saving_account), active_saving_account, raw=True)
    value.refresh_from_db()
    assert str(value.value.currency) == "USD"
