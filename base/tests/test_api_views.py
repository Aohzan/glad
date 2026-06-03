"""Tests for base/api_views.py — dashboard JSON endpoints."""

import datetime
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.urls import reverse
from moneyed import Money

from finance.models.investment_account import (
    InvestmentAccount,
    InvestmentAccountCash,
    InvestmentAccountHolding,
    InvestmentAccountHoldingHistory,
)
from finance.models.saving_account import SavingAccount, SavingAccountValue
from property.models import Property
from property.models.scpi import SCPI, SCPIInvestment


def get_json(client, url):
    return client.get(url, HTTP_ACCEPT="application/json")


def _make_saving_account(saving_account_type, name="Test"):
    return SavingAccount.objects.create(
        name=name,
        account_type=saving_account_type,
        opening_value=Money(0, "EUR"),
        is_active=True,
    )


def _make_investment_account(investment_account_type, name="Test Inv", currency="EUR"):
    return InvestmentAccount.objects.create(
        account_type=investment_account_type,
        name=name,
        is_active=True,
        opening_cash_value=Money(0, currency),
        opening_date=datetime.date.today() - datetime.timedelta(days=60),
    )


def _make_property(name="Test Property", buying_value=Money(200000, "EUR")):
    return Property.objects.create(
        name=name,
        property_type=Property.APARTMENT,
        buying_value=buying_value,
        buying_date=datetime.date.today() - datetime.timedelta(days=365),
        is_active=True,
    )


def _make_scpi_investment(name="Test SCPI", shares=10, price=Money(100, "EUR")):
    scpi = SCPI.objects.create(name=name)
    return SCPIInvestment.objects.create(
        scpi=scpi,
        subscription_date=datetime.date.today() - datetime.timedelta(days=180),
        shares_count=Decimal(str(shares)),
        unit_purchase_price=price,
    )


def _make_property_with_value_and_patch():
    from property.models import PropertyValue

    prop = _make_property()
    PropertyValue.objects.create(
        property=prop,
        value=Money(200000, "EUR"),
        valuation_date=datetime.date.today(),
    )
    original = Property.net_value_at_date

    def _raising_net_value_at_date(self, as_of_date=None):
        if as_of_date is not None:
            raise Exception("mock error")
        return original(self, as_of_date=as_of_date)

    return patch.object(Property, "net_value_at_date", _raising_net_value_at_date)


def _make_multi_currency_data(saving_account_type, investment_account_type):
    usd_inv = InvestmentAccount.objects.create(
        account_type=investment_account_type,
        name="USD Inv",
        is_active=True,
        opening_cash_value=Money(0, "USD"),
        opening_date=datetime.date.today() - datetime.timedelta(days=60),
    )
    InvestmentAccountCash.objects.create(
        account=usd_inv, value=Money(3000, "USD"), value_date=datetime.date.today()
    )
    eur_saving = _make_saving_account(saving_account_type, name="EUR Saving")
    SavingAccountValue.objects.create(
        account=eur_saving, value=Money(2000, "EUR"), value_date=datetime.date.today()
    )


# ── auth guards ────────────────────────────────────────────────────────────


@pytest.mark.django_db
@pytest.mark.parametrize(
    "url_name",
    [
        "api_net_worth",
        "api_patrimony_chart",
        "api_recent_operations",
        "api_alerts",
    ],
)
def test_api_requires_login(client, url_name):
    response = get_json(client, reverse(url_name))
    assert response.status_code == 302
    assert "/accounts/login/" in response.url


# ── NetWorthApiView ────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_net_worth_empty(admin_client):
    response = get_json(admin_client, reverse("api_net_worth"))
    assert response.status_code == 200
    data = response.json()
    assert data["total_net_worth"] == 0.0
    assert data["total_investments"] == 0.0
    assert data["total_savings"] == 0.0
    assert data["total_properties_net"] == 0.0
    assert isinstance(data["global_progression"], float)
    assert isinstance(data["net_worth_by_currency"], dict)


@pytest.mark.django_db
def test_net_worth_with_accounts(admin_client, saving_account_type):
    acc = _make_saving_account(saving_account_type)
    SavingAccountValue.objects.create(
        account=acc, value=Money(5000, "EUR"), value_date=datetime.date.today()
    )
    response = get_json(admin_client, reverse("api_net_worth"))
    data = response.json()
    assert data["total_savings"] == 5000.0
    assert data["total_net_worth"] == 5000.0
    assert data["currency"] == "EUR"
    assert "EUR" in data["net_worth_by_currency"]


@pytest.mark.django_db
def test_net_worth_30day_progression(admin_client, saving_account_type):
    acc = _make_saving_account(saving_account_type)
    SavingAccountValue.objects.create(
        account=acc,
        value=Money(1000, "EUR"),
        value_date=datetime.date.today() - datetime.timedelta(days=35),
    )
    SavingAccountValue.objects.create(
        account=acc, value=Money(1100, "EUR"), value_date=datetime.date.today()
    )
    response = get_json(admin_client, reverse("api_net_worth"))
    data = response.json()
    assert data["global_progression"] > 0


@pytest.mark.django_db
def test_net_worth_with_all_account_types(
    admin_client,
    saving_account_type,
    investment_account_type,
):
    saving = _make_saving_account(saving_account_type)
    SavingAccountValue.objects.create(
        account=saving, value=Money(5000, "EUR"), value_date=datetime.date.today()
    )

    inv = _make_investment_account(investment_account_type)
    InvestmentAccountCash.objects.create(
        account=inv, value=Money(3000, "EUR"), value_date=datetime.date.today()
    )

    prop = _make_property()
    from property.models import PropertyValue

    PropertyValue.objects.create(
        property=prop,
        value=Money(200000, "EUR"),
        valuation_date=datetime.date.today(),
    )

    _make_scpi_investment()

    response = get_json(admin_client, reverse("api_net_worth"))
    data = response.json()
    assert data["total_savings"] == 5000.0
    assert data["total_investments"] == 3000.0
    assert data["total_properties_net"] > 0
    assert data["total_net_worth"] > 0
    assert data["has_investments"] is True
    assert data["has_savings"] is True
    assert data["has_properties"] is True
    assert data["has_scpi"] is True
    assert "EUR" in data["net_worth_by_currency"]


@pytest.mark.django_db
def test_net_worth_with_investment_30day_progression(
    admin_client, investment_account_type
):
    inv = _make_investment_account(investment_account_type)
    InvestmentAccountCash.objects.create(
        account=inv,
        value=Money(1000, "EUR"),
        value_date=datetime.date.today() - datetime.timedelta(days=35),
    )
    InvestmentAccountCash.objects.create(
        account=inv,
        value=Money(1100, "EUR"),
        value_date=datetime.date.today(),
    )
    response = get_json(admin_client, reverse("api_net_worth"))
    data = response.json()
    assert data["total_investments"] == 1100.0
    assert data["global_progression"] > 0


@pytest.mark.django_db
def test_net_worth_with_property_30day_progression(
    admin_client,
):
    prop = _make_property()
    from property.models import PropertyValue

    PropertyValue.objects.create(
        property=prop,
        value=Money(180000, "EUR"),
        valuation_date=datetime.date.today() - datetime.timedelta(days=35),
    )
    PropertyValue.objects.create(
        property=prop,
        value=Money(200000, "EUR"),
        valuation_date=datetime.date.today(),
    )
    response = get_json(admin_client, reverse("api_net_worth"))
    data = response.json()
    assert data["total_properties_net"] > 0


@pytest.mark.django_db
def test_net_worth_progression_with_closed_accounts(
    admin_client, saving_account_type, investment_account_type
):
    saving = SavingAccount.objects.create(
        name="Closed Saving",
        account_type=saving_account_type,
        opening_value=Money(0, "EUR"),
        is_active=False,
        closing_date=datetime.date.today() - datetime.timedelta(days=5),
    )
    SavingAccountValue.objects.create(
        account=saving,
        value=Money(500, "EUR"),
        value_date=datetime.date.today() - datetime.timedelta(days=35),
    )
    SavingAccountValue.objects.create(
        account=saving,
        value=Money(500, "EUR"),
        value_date=datetime.date.today() - datetime.timedelta(days=10),
    )

    inv = InvestmentAccount.objects.create(
        account_type=investment_account_type,
        name="Closed Investment",
        is_active=False,
        opening_cash_value=Money(0, "EUR"),
        opening_date=datetime.date.today() - datetime.timedelta(days=60),
        closing_date=datetime.date.today() - datetime.timedelta(days=5),
    )
    InvestmentAccountCash.objects.create(
        account=inv,
        value=Money(500, "EUR"),
        value_date=datetime.date.today() - datetime.timedelta(days=35),
    )
    InvestmentAccountCash.objects.create(
        account=inv,
        value=Money(500, "EUR"),
        value_date=datetime.date.today() - datetime.timedelta(days=10),
    )

    response = get_json(admin_client, reverse("api_net_worth"))
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data["global_progression"], float)


@pytest.mark.django_db
def test_net_worth_progression_exception_fallback(admin_client, saving_account_type):
    acc = _make_saving_account(saving_account_type)
    SavingAccountValue.objects.create(
        account=acc,
        value=Money(1000, "EUR"),
        value_date=datetime.date.today(),
    )
    response = get_json(admin_client, reverse("api_net_worth"))
    data = response.json()
    assert isinstance(data["global_progression"], float)


# ── _resolve_default_currency ──────────────────────────────────────────────


@pytest.mark.django_db
def test_net_worth_currency_from_investments(admin_client, investment_account_type):
    inv = InvestmentAccount.objects.create(
        account_type=investment_account_type,
        name="USD Investment",
        is_active=True,
        opening_cash_value=Money(0, "USD"),
        opening_date=datetime.date.today() - datetime.timedelta(days=60),
    )
    InvestmentAccountCash.objects.create(
        account=inv, value=Money(5000, "USD"), value_date=datetime.date.today()
    )
    response = get_json(admin_client, reverse("api_net_worth"))
    data = response.json()
    assert data["currency"] == "USD"
    assert "USD" in data["net_worth_by_currency"]


@pytest.mark.django_db
def test_net_worth_currency_from_properties(admin_client):
    prop = Property.objects.create(
        name="USD Property",
        property_type=Property.APARTMENT,
        buying_value=Money(300000, "USD"),
        buying_date=datetime.date.today() - datetime.timedelta(days=365),
        is_active=True,
    )
    from property.models import PropertyValue

    PropertyValue.objects.create(
        property=prop,
        value=Money(300000, "USD"),
        valuation_date=datetime.date.today(),
    )
    response = get_json(admin_client, reverse("api_net_worth"))
    data = response.json()
    assert data["currency"] == "USD"


# ── PatrimonyChartApiView ──────────────────────────────────────────────────


@pytest.mark.django_db
def test_patrimony_chart_structure(admin_client):
    response = get_json(admin_client, reverse("api_patrimony_chart"))
    assert response.status_code == 200
    data = response.json()
    assert "months" in data
    assert "investments" in data
    assert "savings" in data
    assert "properties_net" in data
    assert "properties_loans" in data
    assert "scpi" in data
    assert len(data["months"]) == 25


@pytest.mark.django_db
def test_patrimony_chart_series_length(admin_client):
    response = get_json(admin_client, reverse("api_patrimony_chart"))
    data = response.json()
    length = len(data["months"])
    assert len(data["investments"]) == length
    assert len(data["savings"]) == length
    assert len(data["properties_net"]) == length
    assert len(data["properties_loans"]) == length
    assert len(data["scpi"]) == length


@pytest.mark.django_db
def test_patrimony_chart_with_saving_accounts(admin_client, saving_account_type):
    acc = _make_saving_account(saving_account_type)
    SavingAccountValue.objects.create(
        account=acc, value=Money(5000, "EUR"), value_date=datetime.date.today()
    )
    SavingAccountValue.objects.create(
        account=acc,
        value=Money(4000, "EUR"),
        value_date=datetime.date.today() - datetime.timedelta(days=60),
    )
    response = get_json(admin_client, reverse("api_patrimony_chart"))
    data = response.json()
    assert any(v > 0 for v in data["savings"])


@pytest.mark.django_db
def test_patrimony_chart_with_closed_saving_accounts(admin_client, saving_account_type):
    acc = SavingAccount.objects.create(
        name="Closed Saving",
        account_type=saving_account_type,
        opening_value=Money(0, "EUR"),
        is_active=False,
        closing_date=datetime.date.today() - datetime.timedelta(days=5),
    )
    SavingAccountValue.objects.create(
        account=acc,
        value=Money(3000, "EUR"),
        value_date=datetime.date.today() - datetime.timedelta(days=10),
    )
    response = get_json(admin_client, reverse("api_patrimony_chart"))
    assert response.status_code == 200
    data = response.json()
    assert len(data["savings"]) == len(data["months"])


@pytest.mark.django_db
def test_patrimony_chart_with_investment_accounts(
    admin_client, investment_account_type
):
    inv = _make_investment_account(investment_account_type)
    InvestmentAccountCash.objects.create(
        account=inv, value=Money(8000, "EUR"), value_date=datetime.date.today()
    )
    InvestmentAccountCash.objects.create(
        account=inv,
        value=Money(6000, "EUR"),
        value_date=datetime.date.today() - datetime.timedelta(days=60),
    )
    response = get_json(admin_client, reverse("api_patrimony_chart"))
    data = response.json()
    assert any(v > 0 for v in data["investments"])


@pytest.mark.django_db
def test_patrimony_chart_with_closed_investment_accounts(
    admin_client, investment_account_type
):
    inv = InvestmentAccount.objects.create(
        account_type=investment_account_type,
        name="Closed Inv",
        is_active=False,
        opening_cash_value=Money(0, "EUR"),
        opening_date=datetime.date.today() - datetime.timedelta(days=60),
        closing_date=datetime.date.today() - datetime.timedelta(days=5),
    )
    InvestmentAccountCash.objects.create(
        account=inv,
        value=Money(5000, "EUR"),
        value_date=datetime.date.today() - datetime.timedelta(days=10),
    )
    response = get_json(admin_client, reverse("api_patrimony_chart"))
    assert response.status_code == 200
    data = response.json()
    assert len(data["investments"]) == len(data["months"])


@pytest.mark.django_db
def test_patrimony_chart_with_properties(admin_client):
    prop = _make_property()
    from property.models import PropertyValue

    PropertyValue.objects.create(
        property=prop,
        value=Money(200000, "EUR"),
        valuation_date=datetime.date.today(),
    )
    response = get_json(admin_client, reverse("api_patrimony_chart"))
    data = response.json()
    assert any(v > 0 for v in data["properties_net"])


@pytest.mark.django_db
def test_patrimony_chart_with_scpi(admin_client):
    _make_scpi_investment()
    response = get_json(admin_client, reverse("api_patrimony_chart"))
    data = response.json()
    assert any(v > 0 for v in data["scpi"])


@pytest.mark.django_db
def test_patrimony_chart_custom_range(admin_client):
    response = get_json(admin_client, reverse("api_patrimony_chart") + "?range=1")
    data = response.json()
    assert len(data["months"]) == 13


# ── RecentOperationsApiView ────────────────────────────────────────────────


@pytest.mark.django_db
def test_recent_operations_empty(admin_client):
    response = get_json(admin_client, reverse("api_recent_operations"))
    assert response.status_code == 200
    data = response.json()
    assert "operations" in data
    assert isinstance(data["operations"], list)


@pytest.mark.django_db
def test_recent_operations_structure(admin_client, saving_account_type):
    acc = _make_saving_account(saving_account_type)
    SavingAccountValue.objects.create(
        account=acc, value=Money(1000, "EUR"), value_date=datetime.date.today()
    )
    response = get_json(admin_client, reverse("api_recent_operations"))
    data = response.json()
    assert len(data["operations"]) >= 1
    op = data["operations"][0]
    for key in ("label", "amount", "currency", "date", "icon", "type_css"):
        assert key in op


@pytest.mark.django_db
def test_recent_operations_max_five(admin_client, saving_account_type):
    acc = SavingAccount.objects.create(
        name="Test",
        account_type=saving_account_type,
        opening_value=Money(0, "EUR"),
        is_active=True,
    )
    for i in range(10):
        SavingAccountValue.objects.create(
            account=acc,
            value=Money(1000 + i, "EUR"),
            value_date=datetime.date.today() - datetime.timedelta(days=i),
        )
    response = get_json(admin_client, reverse("api_recent_operations"))
    data = response.json()
    assert len(data["operations"]) <= 5


@pytest.mark.django_db
def test_recent_operations_with_investment_cash(admin_client, investment_account_type):
    inv = _make_investment_account(investment_account_type)
    InvestmentAccountCash.objects.create(
        account=inv, value=Money(2500, "EUR"), value_date=datetime.date.today()
    )
    response = get_json(admin_client, reverse("api_recent_operations"))
    data = response.json()
    cash_ops = [op for op in data["operations"] if op["icon"] == "bi-cash-coin"]
    assert len(cash_ops) >= 1
    assert cash_ops[0]["type_css"] == "primary"


@pytest.mark.django_db
def test_recent_operations_with_holding_history(admin_client, investment_account_type):
    inv = _make_investment_account(investment_account_type)
    holding = InvestmentAccountHolding.objects.create(
        account=inv,
        name="Test Holding",
        is_active=True,
        initial_value=Money(100, "EUR"),
    )
    InvestmentAccountHoldingHistory.objects.create(
        holding=holding,
        value=Money(300, "EUR"),
        quantity=Decimal("3"),
        valuation_date=datetime.datetime.now(),
    )
    response = get_json(admin_client, reverse("api_recent_operations"))
    data = response.json()
    holding_ops = [op for op in data["operations"] if op["icon"] == "bi-graph-up"]
    assert len(holding_ops) >= 1
    assert holding_ops[0]["type_css"] == "info"


@pytest.mark.django_db
def test_recent_operations_sorted_by_date(
    admin_client, saving_account_type, investment_account_type
):
    acc = _make_saving_account(saving_account_type)
    SavingAccountValue.objects.create(
        account=acc,
        value=Money(1000, "EUR"),
        value_date=datetime.date.today() - datetime.timedelta(days=5),
    )
    inv = _make_investment_account(investment_account_type)
    InvestmentAccountCash.objects.create(
        account=inv,
        value=Money(2000, "EUR"),
        value_date=datetime.date.today(),
    )
    response = get_json(admin_client, reverse("api_recent_operations"))
    data = response.json()
    if len(data["operations"]) >= 2:
        dates = [op["date"] for op in data["operations"]]
        assert dates == sorted(dates, reverse=True)


# ── AlertsApiView ──────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_alerts_empty(admin_client):
    response = get_json(admin_client, reverse("api_alerts"))
    assert response.status_code == 200
    data = response.json()
    assert "alerts" in data
    assert isinstance(data["alerts"], list)


@pytest.mark.django_db
def test_alerts_triggered_on_decline(admin_client, declining_saving_account):
    response = get_json(admin_client, reverse("api_alerts"))
    data = response.json()
    assert len(data["alerts"]) >= 1
    alert = data["alerts"][0]
    assert "account" in alert
    assert "message" in alert
    assert alert["type_css"] == "danger"


@pytest.mark.django_db
def test_alerts_not_triggered_on_small_decline(admin_client, saving_account_type):
    acc = _make_saving_account(saving_account_type, name="Slight dip")
    SavingAccountValue.objects.create(
        account=acc,
        value=Money(1000, "EUR"),
        value_date=datetime.date.today() - datetime.timedelta(days=35),
    )
    SavingAccountValue.objects.create(
        account=acc, value=Money(980, "EUR"), value_date=datetime.date.today()
    )
    response = get_json(admin_client, reverse("api_alerts"))
    data = response.json()
    assert len(data["alerts"]) == 0


@pytest.mark.django_db
def test_alerts_triggered_on_investment_decline(admin_client, investment_account_type):
    inv = _make_investment_account(investment_account_type, name="Declining Inv")
    InvestmentAccountCash.objects.create(
        account=inv,
        value=Money(5000, "EUR"),
        value_date=datetime.date.today() - datetime.timedelta(days=35),
    )
    InvestmentAccountCash.objects.create(
        account=inv,
        value=Money(2000, "EUR"),
        value_date=datetime.date.today(),
    )
    holding = InvestmentAccountHolding.objects.create(
        account=inv,
        name="Declining Holding",
        is_active=True,
        initial_value=Money(100, "EUR"),
    )
    InvestmentAccountHoldingHistory.objects.create(
        holding=holding,
        value=Money(5000, "EUR"),
        quantity=Decimal("50"),
        valuation_date=datetime.datetime.now() - datetime.timedelta(days=35),
    )
    InvestmentAccountHoldingHistory.objects.create(
        holding=holding,
        value=Money(2000, "EUR"),
        quantity=Decimal("50"),
        valuation_date=datetime.datetime.now(),
    )
    response = get_json(admin_client, reverse("api_alerts"))
    data = response.json()
    inv_alerts = [a for a in data["alerts"] if "Declining" in a["account"]]
    assert len(inv_alerts) >= 1


# ── Exception fallback branches ────────────────────────────────────────────


def _typeerror_on_datetime_only(original_fn):
    """Return a mock function that raises TypeError on datetime args but calls through on date/None."""

    def _mock(self, max_date=None):
        if isinstance(max_date, datetime.datetime):
            raise TypeError("mock type error")
        return original_fn(self, max_date=max_date)

    return _mock


def _exception_on_datetime_only(original_fn):
    """Return a mock function that raises Exception on datetime args but calls through on date/None."""

    def _mock(self, max_date=None):
        if isinstance(max_date, datetime.datetime):
            raise Exception("mock error")
        return original_fn(self, max_date=max_date)

    return _mock


@pytest.mark.django_db
def test_net_worth_saving_typeerror_fallback(admin_client, saving_account_type):
    acc = _make_saving_account(saving_account_type)
    SavingAccountValue.objects.create(
        account=acc, value=Money(1000, "EUR"), value_date=datetime.date.today()
    )
    original = SavingAccount.get_value
    with patch.object(
        SavingAccount, "get_value", _typeerror_on_datetime_only(original)
    ):
        response = get_json(admin_client, reverse("api_net_worth"))
    assert response.status_code == 200
    data = response.json()
    assert data["total_savings"] == 1000.0


@pytest.mark.django_db
def test_net_worth_saving_exception_fallback(admin_client, saving_account_type):
    acc = _make_saving_account(saving_account_type)
    SavingAccountValue.objects.create(
        account=acc, value=Money(1000, "EUR"), value_date=datetime.date.today()
    )
    original = SavingAccount.get_value
    with patch.object(
        SavingAccount, "get_value", _exception_on_datetime_only(original)
    ):
        response = get_json(admin_client, reverse("api_net_worth"))
    assert response.status_code == 200


@pytest.mark.django_db
def test_net_worth_investment_typeerror_fallback(admin_client, investment_account_type):
    inv = _make_investment_account(investment_account_type)
    InvestmentAccountCash.objects.create(
        account=inv, value=Money(2000, "EUR"), value_date=datetime.date.today()
    )
    original = InvestmentAccount.get_value
    with patch.object(
        InvestmentAccount, "get_value", _typeerror_on_datetime_only(original)
    ):
        response = get_json(admin_client, reverse("api_net_worth"))
    assert response.status_code == 200


@pytest.mark.django_db
def test_net_worth_investment_exception_fallback(admin_client, investment_account_type):
    inv = _make_investment_account(investment_account_type)
    InvestmentAccountCash.objects.create(
        account=inv, value=Money(2000, "EUR"), value_date=datetime.date.today()
    )
    original = InvestmentAccount.get_value
    with patch.object(
        InvestmentAccount, "get_value", _exception_on_datetime_only(original)
    ):
        response = get_json(admin_client, reverse("api_net_worth"))
    assert response.status_code == 200


@pytest.mark.django_db
def test_net_worth_property_exception_fallback(admin_client):
    with _make_property_with_value_and_patch():
        response = get_json(admin_client, reverse("api_net_worth"))
    assert response.status_code == 200


@pytest.mark.django_db
def test_net_worth_outer_exception_fallback(admin_client, saving_account_type):
    acc = _make_saving_account(saving_account_type)
    SavingAccountValue.objects.create(
        account=acc, value=Money(1000, "EUR"), value_date=datetime.date.today()
    )
    with patch.object(SavingAccount, "get_progression", side_effect=Exception("boom")):
        response = get_json(admin_client, reverse("api_net_worth"))
    assert response.status_code == 200
    data = response.json()
    assert data["global_progression"] == 0.0


@pytest.mark.django_db
def test_patrimony_chart_saving_typeerror_fallback(admin_client, saving_account_type):
    acc = _make_saving_account(saving_account_type)
    SavingAccountValue.objects.create(
        account=acc, value=Money(5000, "EUR"), value_date=datetime.date.today()
    )
    original = SavingAccount.get_value
    with patch.object(
        SavingAccount, "get_value", _typeerror_on_datetime_only(original)
    ):
        response = get_json(admin_client, reverse("api_patrimony_chart"))
    assert response.status_code == 200
    data = response.json()
    assert len(data["savings"]) == len(data["months"])


@pytest.mark.django_db
def test_patrimony_chart_saving_exception_fallback(admin_client, saving_account_type):
    acc = _make_saving_account(saving_account_type)
    SavingAccountValue.objects.create(
        account=acc, value=Money(5000, "EUR"), value_date=datetime.date.today()
    )
    original = SavingAccount.get_value
    with patch.object(
        SavingAccount, "get_value", _exception_on_datetime_only(original)
    ):
        response = get_json(admin_client, reverse("api_patrimony_chart"))
    assert response.status_code == 200
    data = response.json()
    assert len(data["savings"]) == len(data["months"])


@pytest.mark.django_db
def test_patrimony_chart_investment_typeerror_fallback(
    admin_client, investment_account_type
):
    inv = _make_investment_account(investment_account_type)
    InvestmentAccountCash.objects.create(
        account=inv, value=Money(8000, "EUR"), value_date=datetime.date.today()
    )
    original = InvestmentAccount.get_value
    with patch.object(
        InvestmentAccount, "get_value", _typeerror_on_datetime_only(original)
    ):
        response = get_json(admin_client, reverse("api_patrimony_chart"))
    assert response.status_code == 200
    data = response.json()
    assert len(data["investments"]) == len(data["months"])


@pytest.mark.django_db
def test_patrimony_chart_investment_exception_fallback(
    admin_client, investment_account_type
):
    inv = _make_investment_account(investment_account_type)
    InvestmentAccountCash.objects.create(
        account=inv, value=Money(8000, "EUR"), value_date=datetime.date.today()
    )
    original = InvestmentAccount.get_value
    with patch.object(
        InvestmentAccount, "get_value", _exception_on_datetime_only(original)
    ):
        response = get_json(admin_client, reverse("api_patrimony_chart"))
    assert response.status_code == 200
    data = response.json()
    assert len(data["investments"]) == len(data["months"])


@pytest.mark.django_db
def test_patrimony_chart_property_exception_fallback(admin_client):
    with _make_property_with_value_and_patch():
        response = get_json(admin_client, reverse("api_patrimony_chart"))
    assert response.status_code == 200
    data = response.json()
    assert len(data["properties_net"]) == len(data["months"])


@pytest.mark.django_db
def test_patrimony_chart_scpi_exception_fallback(admin_client):
    _make_scpi_investment()
    original = SCPIInvestment.get_estimated_value

    def _raising_estimated_value(self, as_of_date=None):
        if as_of_date is not None and as_of_date != datetime.date.today():
            raise Exception("mock error")
        return original(self, as_of_date=as_of_date)

    with patch.object(SCPIInvestment, "get_estimated_value", _raising_estimated_value):
        response = get_json(admin_client, reverse("api_patrimony_chart"))
    assert response.status_code == 200
    data = response.json()
    assert len(data["scpi"]) == len(data["months"])


@pytest.mark.django_db
def test_net_worth_multi_currency_skips_non_dc(
    admin_client, saving_account_type, investment_account_type
):
    _make_multi_currency_data(saving_account_type, investment_account_type)
    response = get_json(admin_client, reverse("api_net_worth"))
    data = response.json()
    assert data["currency"] == "USD"
    assert "EUR" in data["net_worth_by_currency"]
    assert "USD" in data["net_worth_by_currency"]


@pytest.mark.django_db
def test_net_worth_property_bought_after_30_days(admin_client):
    prop = Property.objects.create(
        name="New Property",
        property_type=Property.APARTMENT,
        buying_value=Money(200000, "EUR"),
        buying_date=datetime.date.today() - datetime.timedelta(days=10),
        is_active=True,
    )
    from property.models import PropertyValue

    PropertyValue.objects.create(
        property=prop,
        value=Money(200000, "EUR"),
        valuation_date=datetime.date.today(),
    )
    response = get_json(admin_client, reverse("api_net_worth"))
    data = response.json()
    assert data["total_properties_net"] > 0
    assert data["global_progression"] == 0.0


@pytest.mark.django_db
def test_patrimony_chart_multi_currency_skips_non_dc(
    admin_client, saving_account_type, investment_account_type
):
    _make_multi_currency_data(saving_account_type, investment_account_type)
    response = get_json(admin_client, reverse("api_patrimony_chart"))
    data = response.json()
    assert data["savings"][0] == 0.0


@pytest.mark.django_db
def test_alerts_investment_no_decline(admin_client, investment_account_type):
    inv = _make_investment_account(investment_account_type, name="Stable Inv")
    InvestmentAccountCash.objects.create(
        account=inv,
        value=Money(2000, "EUR"),
        value_date=datetime.date.today() - datetime.timedelta(days=35),
    )
    InvestmentAccountCash.objects.create(
        account=inv,
        value=Money(2100, "EUR"),
        value_date=datetime.date.today(),
    )
    response = get_json(admin_client, reverse("api_alerts"))
    data = response.json()
    inv_alerts = [a for a in data["alerts"] if "Stable" in a["account"]]
    assert len(inv_alerts) == 0
