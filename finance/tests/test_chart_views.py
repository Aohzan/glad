"""Tests for finance chart data views."""

import datetime
from decimal import Decimal

import pytest
from django.urls import reverse
from djmoney.money import Money

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
    # invested series: union of history dates + event dates
    # history: day -10 (initial), day -5 (history); event: day -10 (holding), day -3 (deposit)
    # union = day -10, day -5, day -3 → 3 points
    assert len(payload["invested"]) == 3
    invested_values = [item["value"] for item in payload["invested"]]
    # day -10: holding 100; day -5: still 100 (deposit at day -3); day -3: 100+250=350
    assert invested_values[0] == pytest.approx(100.0, abs=1.0)
    assert invested_values[1] == pytest.approx(100.0, abs=1.0)
    assert invested_values[2] == pytest.approx(350.0, abs=1.0)


@pytest.mark.django_db
def test_chart_data_investment_account_negative_deposit(
    user_client, active_investment_account
):
    """A negative deposit (withdrawal) reduces the cumulative invested amount."""
    holding = InvestmentAccountHolding.objects.create(
        account=active_investment_account,
        name="ETF World",
        code="WLD",
        initial_quantity=Decimal("10"),
        initial_value=Money(Decimal("1000.00"), "EUR"),
        initial_valuation_date=datetime.date.today() - datetime.timedelta(days=10),
        is_active=True,
    )
    InvestmentAccountHoldingHistory.objects.create(
        holding=holding,
        value=Money(Decimal("1100.00"), "EUR"),
        quantity=Decimal("10"),
        valuation_date=datetime.datetime.now() - datetime.timedelta(days=5),
    )
    # Withdrawal recorded as negative deposit
    InvestmentAccountDeposit.objects.create(
        account=active_investment_account,
        amount=Money(Decimal("-400.00"), "EUR"),
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
    invested_values = [item["value"] for item in payload["invested"]]
    # history: day -10 (initial), day -5 (history); event: day -10 (holding), day -3 (withdrawal)
    # union = day -10, day -5, day -3 → 3 points
    assert len(invested_values) == 3
    # First point: only holding (1000); after withdrawal: 1000 - 400 = 600
    assert invested_values[0] == pytest.approx(1000.0, abs=1.0)
    assert invested_values[1] == pytest.approx(1000.0, abs=1.0)
    assert invested_values[2] == pytest.approx(600.0, abs=1.0)


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
    # invested series: union of history dates + event dates (>= values count)
    assert len(payload["invested"]) >= len(payload["values"])


@pytest.mark.django_db
def test_chart_data_saving_account_negative_deposit(user_client, active_saving_account):
    """A negative deposit (withdrawal) reduces the cumulative invested amount."""
    SavingAccountValue.objects.create(
        account=active_saving_account,
        value=Money(Decimal("900.00"), "EUR"),
        value_date=datetime.datetime.now() - datetime.timedelta(days=5),
    )
    SavingAccountDeposit.objects.create(
        account=active_saving_account,
        amount=Money(Decimal("-200.00"), "EUR"),
        deposit_date=datetime.datetime.now() - datetime.timedelta(days=3),
    )

    response = user_client.get(
        reverse("finance:chart_data", args=["saving_account", active_saving_account.id])
    )
    payload = response.json()
    assert response.status_code == 200
    assert payload["success"] is True
    invested_values = [item["value"] for item in payload["invested"]]
    # Last point should reflect withdrawal reducing cumulative invested
    opening_value = float(active_saving_account.opening_value.amount)
    assert invested_values[-1] == pytest.approx(opening_value - 200.0, abs=1.0)


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
