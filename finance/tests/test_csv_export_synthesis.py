"""Tests for CSV synthesis export."""

import csv
import datetime
import io
from decimal import Decimal

import pytest
from django.urls import reverse
from moneyed import Money

from finance.models.investment_account import (
    InvestmentAccountCash,
    InvestmentAccountHolding,
    InvestmentAccountHoldingHistory,
)
from finance.models.saving_account import (
    SavingAccount,
    SavingAccountValue,
)


@pytest.mark.django_db
def test_csv_export_synthesis_empty(user_client):
    response = user_client.get(reverse("finance:csv_export_synthesis"))
    assert response.status_code == 200
    assert response["Content-Type"] == "text/csv"
    assert "synthesis_export.csv" in response["Content-Disposition"]
    content = response.content.decode("utf-8")
    reader = csv.reader(io.StringIO(content))
    rows = list(reader)
    assert len(rows) == 1
    assert rows[0][0] == "Type"


@pytest.mark.django_db
def test_csv_export_synthesis_saving_accounts(
    user_client, saving_account_type, active_saving_account
):
    SavingAccountValue.objects.create(
        account=active_saving_account,
        value=Money(1500, "EUR"),
        value_date=datetime.datetime.now(),
    )

    response = user_client.get(reverse("finance:csv_export_synthesis"))
    assert response.status_code == 200
    content = response.content.decode("utf-8")
    reader = csv.reader(io.StringIO(content))
    rows = list(reader)
    assert len(rows) == 2
    assert rows[1][0] == str(saving_account_type)
    assert rows[1][1] == "Test Owner"
    assert rows[1][2] == "Test Bank"
    assert "1500" in rows[1][3]


@pytest.mark.django_db
def test_csv_export_synthesis_investment_accounts(
    user_client, investment_account_type, active_investment_account
):
    InvestmentAccountCash.objects.create(
        account=active_investment_account,
        value=Money(3000, "EUR"),
        value_date=datetime.date.today(),
    )

    response = user_client.get(reverse("finance:csv_export_synthesis"))
    assert response.status_code == 200
    content = response.content.decode("utf-8")
    reader = csv.reader(io.StringIO(content))
    rows = list(reader)
    assert len(rows) == 2
    assert rows[1][0] == str(investment_account_type)
    assert rows[1][1] == "Test Owner"
    assert rows[1][2] == "Test Broker"


@pytest.mark.django_db
def test_csv_export_synthesis_saving_before_investment(
    user_client,
    saving_account_type,
    active_saving_account,
    investment_account_type,
    active_investment_account,
):
    SavingAccountValue.objects.create(
        account=active_saving_account,
        value=Money(1500, "EUR"),
        value_date=datetime.datetime.now(),
    )
    InvestmentAccountCash.objects.create(
        account=active_investment_account,
        value=Money(3000, "EUR"),
        value_date=datetime.date.today(),
    )

    response = user_client.get(reverse("finance:csv_export_synthesis"))
    content = response.content.decode("utf-8")
    reader = csv.reader(io.StringIO(content))
    rows = list(reader)
    assert len(rows) == 3
    assert rows[1][0] == str(saving_account_type)
    assert rows[2][0] == str(investment_account_type)


@pytest.mark.django_db
def test_csv_export_synthesis_excludes_inactive(
    user_client,
    saving_account_type,
    active_saving_account,
    inactive_saving_account,
):
    SavingAccountValue.objects.create(
        account=active_saving_account,
        value=Money(1500, "EUR"),
        value_date=datetime.datetime.now(),
    )
    SavingAccountValue.objects.create(
        account=inactive_saving_account,
        value=Money(800, "EUR"),
        value_date=datetime.datetime.now(),
    )

    response = user_client.get(reverse("finance:csv_export_synthesis"))
    content = response.content.decode("utf-8")
    reader = csv.reader(io.StringIO(content))
    rows = list(reader)
    assert len(rows) == 2


@pytest.mark.django_db
def test_csv_export_synthesis_header_contains_date(user_client):
    today = datetime.date.today().strftime("%d/%m/%Y")
    response = user_client.get(reverse("finance:csv_export_synthesis"))
    content = response.content.decode("utf-8")
    assert today in content


@pytest.mark.django_db
def test_csv_export_synthesis_empty_owner_institution(user_client, saving_account_type):
    SavingAccount.objects.create(
        account_type=saving_account_type,
        name="No Owner Account",
        owner="",
        institution="",
        is_active=True,
        opening_value=Money(Decimal("500.00"), "EUR"),
        opening_date=datetime.datetime.today() - datetime.timedelta(days=60),
        interest_rate=Decimal("1.0"),
    )

    response = user_client.get(reverse("finance:csv_export_synthesis"))
    content = response.content.decode("utf-8")
    reader = csv.reader(io.StringIO(content))
    rows = list(reader)
    assert len(rows) == 2
    assert rows[1][1] == ""
    assert rows[1][2] == ""


@pytest.mark.django_db
def test_csv_export_synthesis_investment_with_holdings(
    user_client, investment_account_type, active_investment_account
):
    holding = InvestmentAccountHolding.objects.create(
        account=active_investment_account,
        name="Test ETF",
        code="ETF",
        is_active=True,
        initial_value=Money(100, "EUR"),
        initial_quantity=1,
    )
    InvestmentAccountCash.objects.create(
        account=active_investment_account,
        value=Money(500, "EUR"),
        value_date=datetime.date.today(),
    )
    InvestmentAccountHoldingHistory.objects.create(
        holding=holding,
        value=Money(200, "EUR"),
        quantity=1,
        valuation_date=datetime.datetime.now(),
    )

    response = user_client.get(reverse("finance:csv_export_synthesis"))
    content = response.content.decode("utf-8")
    reader = csv.reader(io.StringIO(content))
    rows = list(reader)
    assert len(rows) == 2
    expected_value = active_investment_account.get_value()
    assert str(expected_value.amount) in rows[1][3]
