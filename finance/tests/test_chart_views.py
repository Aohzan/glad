"""Tests for finance chart data views."""

import datetime
from decimal import Decimal

import pytest
from django.urls import reverse
from djmoney.money import Money

from finance.models.investment_account import (
    InvestmentAccountCash,
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
        initial_quantity=Decimal(10),
        initial_value=Money(Decimal("100.00"), "EUR"),
        initial_valuation_date=datetime.date.today() - datetime.timedelta(days=10),
        is_active=True,
    )
    InvestmentAccountHoldingHistory.objects.create(
        holding=holding,
        value=Money(Decimal("110.00"), "EUR"),
        quantity=Decimal(11),
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
    assert len(payload["values"]) >= 2
    assert len(payload["deposits"]) == 1
    deposit = payload["deposits"][0]
    assert "date" in deposit
    assert "value" in deposit
    assert deposit["value"] == pytest.approx(250.0, abs=0.01)

    # holdings_series includes the holding plus a Cash series
    series_names = [s["name"] for s in payload["holdings_series"]]
    assert "ETF World (WLD)" in series_names
    assert any("Cash" in n or "cash" in n.lower() for n in series_names)

    # All series should have the same number of data points (aligned dates)
    point_counts = [len(s["data"]) for s in payload["holdings_series"]]
    assert len(set(point_counts)) == 1  # all equal

    # Total at each date = sum of all series at that date
    for v in payload["values"]:
        date_str = v["date"]
        series_sum = sum(
            p["value"]
            for s in payload["holdings_series"]
            for p in s["data"]
            if p["date"] == date_str
        )
        assert v["value"] == pytest.approx(series_sum, abs=0.01)

    # The chart starts at the opening date with the opening cash
    assert payload["values"][0]["value"] == pytest.approx(2000.0, abs=0.01)

    # invested series: opening day -60, holding day -10, history day -5,
    # deposit day -3 → 4 points
    assert len(payload["invested"]) == 4
    invested_values = [item["value"] for item in payload["invested"]]
    # Opening cash 2000, the holding is bought with that cash (not new capital),
    # then the deposit of 250
    assert invested_values == pytest.approx([2000.0, 2000.0, 2000.0, 2250.0])


@pytest.mark.django_db
def test_chart_data_investment_account_negative_deposit(
    user_client, active_investment_account
):
    """A negative deposit (withdrawal) reduces the cumulative invested amount."""
    holding = InvestmentAccountHolding.objects.create(
        account=active_investment_account,
        name="ETF World",
        code="WLD",
        initial_quantity=Decimal(10),
        initial_value=Money(Decimal("1000.00"), "EUR"),
        initial_valuation_date=datetime.date.today() - datetime.timedelta(days=10),
        is_active=True,
    )
    InvestmentAccountHoldingHistory.objects.create(
        holding=holding,
        value=Money(Decimal("1100.00"), "EUR"),
        quantity=Decimal(10),
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
    # opening day -60, holding day -10, history day -5, withdrawal day -3
    # Opening cash 2000; after withdrawal: 2000 - 400 = 1600
    assert invested_values == pytest.approx([2000.0, 2000.0, 2000.0, 1600.0])


@pytest.mark.django_db
def test_chart_data_investment_account_multiple_deposits(
    user_client, active_investment_account
):
    """Multiple deposits produce multiple entries in the deposits response."""
    InvestmentAccountHolding.objects.create(
        account=active_investment_account,
        name="ETF World",
        code="WLD",
        initial_value=Money(Decimal("100.00"), "EUR"),
        initial_valuation_date=datetime.date.today() - datetime.timedelta(days=30),
        is_active=True,
    )
    InvestmentAccountDeposit.objects.create(
        account=active_investment_account,
        amount=Money(Decimal("500.00"), "EUR"),
        deposit_date=datetime.date.today() - datetime.timedelta(days=20),
    )
    InvestmentAccountDeposit.objects.create(
        account=active_investment_account,
        amount=Money(Decimal("1000.00"), "EUR"),
        deposit_date=datetime.date.today() - datetime.timedelta(days=10),
    )
    InvestmentAccountDeposit.objects.create(
        account=active_investment_account,
        amount=Money(Decimal("-200.00"), "EUR"),
        deposit_date=datetime.date.today() - datetime.timedelta(days=5),
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
    deposits = payload["deposits"]
    assert len(deposits) == 3
    # Each deposit has date and value fields
    for d in deposits:
        assert "date" in d
        assert "value" in d
    # Values should match the deposit amounts
    deposit_values = [d["value"] for d in deposits]
    assert 500.0 in deposit_values
    assert 1000.0 in deposit_values
    assert -200.0 in deposit_values


@pytest.mark.django_db
def test_chart_data_investment_account_aligned_holdings(
    user_client, active_investment_account
):
    """Multiple holdings with different dates are forward-filled and aligned."""
    # Holding A: starts day-20, valued 100, updated to 150 on day-10
    holding_a = InvestmentAccountHolding.objects.create(
        account=active_investment_account,
        name="Fund A",
        code="FA",
        initial_value=Money(Decimal("100.00"), "EUR"),
        initial_valuation_date=datetime.date.today() - datetime.timedelta(days=20),
        is_active=True,
    )
    InvestmentAccountHoldingHistory.objects.create(
        holding=holding_a,
        value=Money(Decimal("150.00"), "EUR"),
        quantity=Decimal(10),
        valuation_date=datetime.datetime.now() - datetime.timedelta(days=10),
    )

    # Holding B: starts day-15, valued 200, updated to 250 on day-5
    holding_b = InvestmentAccountHolding.objects.create(
        account=active_investment_account,
        name="Fund B",
        code="FB",
        initial_value=Money(Decimal("200.00"), "EUR"),
        initial_valuation_date=datetime.date.today() - datetime.timedelta(days=15),
        is_active=True,
    )
    InvestmentAccountHoldingHistory.objects.create(
        holding=holding_b,
        value=Money(Decimal("250.00"), "EUR"),
        quantity=Decimal(5),
        valuation_date=datetime.datetime.now() - datetime.timedelta(days=5),
    )

    # Cash entry on day-12
    InvestmentAccountCash.objects.create(
        account=active_investment_account,
        value=Money(Decimal("1800.00"), "EUR"),
        value_date=datetime.date.today() - datetime.timedelta(days=12),
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

    # All dates: day-60 (opening), day-20 (A initial), day-15 (B initial),
    # day-12 (cash), day-10 (A history), day-5 (B history) → 6 dates
    all_dates = [v["date"] for v in payload["values"]]
    assert len(all_dates) == 6

    # Every series has a point at every date, zero before the holding purchase
    series_values = {
        s["name"]: [p["value"] for p in s["data"]] for s in payload["holdings_series"]
    }
    for s in payload["holdings_series"]:
        assert [p["date"] for p in s["data"]] == all_dates
    assert series_values["Fund A (FA)"] == pytest.approx(
        [0.0, 100.0, 100.0, 100.0, 150.0, 150.0]
    )
    assert series_values["Fund B (FB)"] == pytest.approx(
        [0.0, 0.0, 200.0, 200.0, 200.0, 250.0]
    )

    # Total at day-10 = Fund A (150) + Fund B (200, forward-filled) + Cash (1800)
    assert payload["values"][4]["value"] == pytest.approx(150.0 + 200.0 + 1800.0)


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
        initial_quantity=Decimal(2),
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
