"""Tests for finance chart data views."""

import datetime
from decimal import Decimal

import pytest
from djmoney.money import Money
from django.urls import reverse

from finance.models.investment_account import (
    InvestmentAccountDeposit,
    InvestmentAccountHolding,
    InvestmentAccountHoldingHistory,
)
from finance.models.saving_account import SavingAccountDeposit, SavingAccountValue


@pytest.mark.django_db
def test_chart_data_invalid_type(user_client):
    response = user_client.get(reverse("finance:chart_data", args=["invalid", 1]))
    assert response.status_code == 400
    assert response.json()["success"] is False


@pytest.mark.django_db
def test_chart_data_exception_path(user_client, monkeypatch, active_investment_account):
    def _raise(request, account_id):
        raise RuntimeError("boom")

    monkeypatch.setattr(
        "finance.views.chart_views._get_investment_account_chart_data", _raise
    )
    response = user_client.get(
        reverse(
            "finance:chart_data",
            args=["investment_account", active_investment_account.id],
        )
    )
    assert response.status_code == 500
    assert response.json()["success"] is False


@pytest.mark.django_db
def test_chart_data_investment_account(user_client, active_investment_account):
    holding = InvestmentAccountHolding.objects.create(
        account=active_investment_account,
        name="ETF World",
        code="WLD",
        initial_quantity=Decimal("10"),
        initial_value=Money(Decimal("100.00"), "EUR"),
        initial_valuation_date=datetime.date.today() - datetime.timedelta(days=10),
        is_active=True,
    )
    InvestmentAccountHoldingHistory.objects.create(
        holding=holding,
        value=Money(Decimal("110.00"), "EUR"),
        quantity=Decimal("11"),
        valuation_date=datetime.datetime.now() - datetime.timedelta(days=5),
    )
    InvestmentAccountDeposit.objects.create(
        account=active_investment_account,
        amount=Money(Decimal("250.00"), "EUR"),
        deposit_date=datetime.date.today() - datetime.timedelta(days=3),
    )

    response = user_client.get(
        reverse(
            "finance:chart_data",
            args=["investment_account", active_investment_account.id],
        )
    )
    payload = response.json()
    assert response.status_code == 200
    assert payload["success"] is True
    assert payload["name"]
    assert len(payload["values"]) >= 1
    assert len(payload["deposits"]) == 1


@pytest.mark.django_db
def test_chart_data_saving_account(user_client, active_saving_account):
    SavingAccountValue.objects.create(
        account=active_saving_account,
        value=Money(Decimal("1200.00"), "EUR"),
        value_date=datetime.datetime.now() - datetime.timedelta(days=8),
    )
    SavingAccountDeposit.objects.create(
        account=active_saving_account,
        amount=Money(Decimal("200.00"), "EUR"),
        deposit_date=datetime.datetime.now() - datetime.timedelta(days=6),
    )

    response = user_client.get(
        reverse("finance:chart_data", args=["saving_account", active_saving_account.id])
    )
    payload = response.json()
    assert response.status_code == 200
    assert payload["success"] is True
    assert len(payload["values"]) >= 2
    assert len(payload["deposits"]) == 1


@pytest.mark.django_db
def test_chart_data_holding(user_client, active_investment_account):
    holding = InvestmentAccountHolding.objects.create(
        account=active_investment_account,
        name="Holding One",
        initial_quantity=Decimal("2"),
        initial_value=Money(Decimal("50.00"), "EUR"),
        initial_valuation_date=datetime.date.today() - datetime.timedelta(days=4),
        is_active=True,
    )
    InvestmentAccountHoldingHistory.objects.create(
        holding=holding,
        value=Money(Decimal("55.00"), "EUR"),
        quantity=Decimal("2.5"),
        valuation_date=datetime.datetime.now() - datetime.timedelta(days=2),
    )

    response = user_client.get(
        reverse("finance:chart_data", args=["holding", holding.id])
    )
    payload = response.json()
    assert response.status_code == 200
    assert payload["success"] is True
    assert len(payload["values"]) == 2
    assert len(payload["quantities"]) == 2
