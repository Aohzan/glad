"""Tests for finance/views/live_price_views.py."""

import datetime
import json
from decimal import Decimal

import pytest
from django.urls import reverse
from moneyed import Money

from finance.models.investment_account import (
    InvestmentAccount,
    InvestmentAccountHolding,
    InvestmentAccountHoldingHistory,
    InvestmentAccountType,
)


@pytest.fixture
def account_type():
    return InvestmentAccountType.objects.create(name="PEA", code="PEA")


@pytest.fixture
def account(account_type):
    return InvestmentAccount.objects.create(
        account_type=account_type,
        name="Main",
        is_active=True,
        opening_cash_value=Money(0, "EUR"),
    )


@pytest.fixture
def holding(account):
    return InvestmentAccountHolding.objects.create(
        account=account, name="World", isin="IE00B4L5Y983"
    )


def toggle(client, holding, body):
    return client.post(
        reverse(
            "finance:toggle_holding_auto_update", args=[holding.account_id, holding.pk]
        ),
        data=body if isinstance(body, str) else json.dumps(body),
        content_type="application/json",
    )


@pytest.mark.django_db
class TestLivePrices:
    def test_lists_the_active_holdings_with_an_isin(
        self, user_client, account, account_type, holding
    ):
        closed = InvestmentAccount.objects.create(
            account_type=account_type,
            name="Old",
            is_active=False,
            opening_cash_value=Money(0, "EUR"),
        )
        manual = InvestmentAccountHolding.objects.create(
            account=account, name="Europe", isin="FR0010315770", auto_update_price=True
        )
        InvestmentAccountHolding.objects.create(account=account, name="No ISIN")
        InvestmentAccountHolding.objects.create(
            account=account, name="Sold", isin="FR0011550185", is_active=False
        )
        InvestmentAccountHolding.objects.create(
            account=closed, name="Closed account", isin="LU1681043599"
        )
        InvestmentAccountHoldingHistory.objects.create(
            holding=holding,
            value=Money(Decimal(100), "EUR"),
            quantity=Decimal(1),
            valuation_date=datetime.datetime(2026, 10, 30),
        )

        response = user_client.get(reverse("finance:live_prices"))

        assert response.status_code == 200
        holdings = {h.pk: h for h in response.context["holdings"]}
        assert set(holdings) == {holding.pk, manual.pk}
        assert holdings[holding.pk].last_valuation.date() == datetime.date(2026, 10, 30)
        assert holdings[manual.pk].last_valuation is None
        content = response.content.decode()
        assert "IE00B4L5Y983" in content
        assert (
            reverse("finance:toggle_holding_auto_update", args=[account.pk, manual.pk])
            in content
        )
        assert "Live market data is disabled" not in content

    def test_empty(self, user_client):
        response = user_client.get(reverse("finance:live_prices"))
        assert "No active holding with an ISIN." in response.content.decode()

    def test_warns_when_live_data_is_disabled(self, user_client, user):
        user.profile.live_data_enabled = False
        user.profile.save()
        response = user_client.get(reverse("finance:live_prices"))
        assert "Live market data is disabled" in response.content.decode()


@pytest.mark.django_db
class TestToggleHoldingAutoUpdate:
    def test_enables_and_disables(self, user_client, holding):
        response = toggle(user_client, holding, {"enabled": True})
        assert response.status_code == 200
        assert response.json() == {"auto_update_price": True}
        holding.refresh_from_db()
        assert holding.auto_update_price is True

        response = toggle(user_client, holding, {"enabled": False})
        assert response.json() == {"auto_update_price": False}
        holding.refresh_from_db()
        assert holding.auto_update_price is False

    @pytest.mark.parametrize("body", ["not json", "[]", {"enabled": "yes"}, {}])
    def test_rejects_an_invalid_body(self, user_client, holding, body):
        response = toggle(user_client, holding, body)
        assert response.status_code == 400
        assert response.json() == {"error": "invalid_request"}
        holding.refresh_from_db()
        assert holding.auto_update_price is False

    def test_refuses_a_holding_without_isin(self, user_client, account):
        holding = InvestmentAccountHolding.objects.create(account=account, name="Fund")
        response = toggle(user_client, holding, {"enabled": True})
        assert response.status_code == 400
        assert response.json() == {"error": "no_isin"}
        holding.refresh_from_db()
        assert holding.auto_update_price is False

    def test_holding_of_another_account(self, user_client, holding, account_type):
        other = InvestmentAccount.objects.create(
            account_type=account_type, name="Other", opening_cash_value=Money(0, "EUR")
        )
        response = user_client.post(
            reverse("finance:toggle_holding_auto_update", args=[other.pk, holding.pk]),
            data=json.dumps({"enabled": True}),
            content_type="application/json",
        )
        assert response.status_code == 404

    def test_get_not_allowed(self, user_client, holding):
        url = reverse(
            "finance:toggle_holding_auto_update", args=[holding.account_id, holding.pk]
        )
        assert user_client.get(url).status_code == 405

    def test_requires_login(self, client, holding):
        response = toggle(client, holding, {"enabled": True})
        assert response.status_code == 302
        holding.refresh_from_db()
        assert holding.auto_update_price is False
