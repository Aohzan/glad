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


def _parse_csv(response):
    content = response.content.decode("utf-8")
    reader = csv.reader(io.StringIO(content))
    return list(reader)


def _find_row_by_owner(rows, owner):
    for row in rows[1:]:
        if row[1] == owner:
            return row
    return None


@pytest.mark.django_db
def test_csv_export_synthesis_basic(user_client):
    response = user_client.get(reverse("finance:csv_export_synthesis"))
    assert response.status_code == 200
    assert response["Content-Type"] == "text/csv"
    assert "synthesis_export.csv" in response["Content-Disposition"]
    rows = _parse_csv(response)
    assert len(rows) >= 1
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
    rows = _parse_csv(response)
    row = _find_row_by_owner(rows, "Test Owner")
    assert row is not None
    assert row[0] == str(saving_account_type)
    assert row[2] == "Test Bank"
    assert "1500" in row[3]


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
    rows = _parse_csv(response)
    row = _find_row_by_owner(rows, "Test Owner")
    assert row is not None
    assert row[0] == str(investment_account_type)
    assert row[2] == "Test Broker"


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
    rows = _parse_csv(response)
    data_rows = rows[1:]
    saving_rows = [r for r in data_rows if r[0] == str(saving_account_type)]
    investment_rows = [r for r in data_rows if r[0] == str(investment_account_type)]
    assert len(saving_rows) >= 1
    assert len(investment_rows) >= 1
    first_saving_idx = data_rows.index(saving_rows[0])
    first_investment_idx = data_rows.index(investment_rows[0])
    assert first_saving_idx < first_investment_idx


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
    rows = _parse_csv(response)
    owners = [row[1] for row in rows[1:]]
    assert active_saving_account.owner in owners
    active_row = _find_row_by_owner(rows, active_saving_account.owner)
    assert active_row is not None
    assert active_row[2] == "Test Bank"
    inactive_row = None
    for row in rows[1:]:
        if row[1] == inactive_saving_account.owner and row[2] == "Test Bank":
            if row not in [active_row]:
                inactive_row = row
    assert inactive_row is None


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
        name="NoOwnerAccount",
        owner="",
        institution="",
        is_active=True,
        opening_value=Money(Decimal("500.00"), "EUR"),
        opening_date=datetime.datetime.today() - datetime.timedelta(days=60),
        interest_rate=Decimal("1.0"),
    )

    response = user_client.get(reverse("finance:csv_export_synthesis"))
    rows = _parse_csv(response)
    account_rows = [
        r
        for r in rows[1:]
        if r[0] == str(saving_account_type) and r[1] == "" and r[2] == ""
    ]
    assert len(account_rows) >= 1


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
    rows = _parse_csv(response)
    row = _find_row_by_owner(rows, "Test Owner")
    assert row is not None
    expected_value = active_investment_account.get_value()
    assert str(expected_value.amount) in row[3]
