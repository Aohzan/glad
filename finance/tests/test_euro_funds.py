"""Tests for the euro fund / units of account split and the credited rates."""

from decimal import Decimal

import pytest
from django.contrib.messages import get_messages
from django.urls import reverse
from moneyed import Money

from base.choices import AssetClass
from finance.models.investment_account import (
    EuroFundRate,
    InvestmentAccount,
    InvestmentAccountHolding,
    InvestmentAccountType,
)


@pytest.fixture
def contract(db):
    av_type = InvestmentAccountType.objects.get_or_create(code="AV", name="AV")[0]
    return InvestmentAccount.objects.create(
        account_type=av_type, name="Contract", opening_cash_value=Money(100, "EUR")
    )


def _holding(account, name, value, asset_class="", **kwargs):
    return InvestmentAccountHolding.objects.create(
        account=account,
        name=name,
        asset_class=asset_class,
        initial_value=Money(Decimal(value), "EUR"),
        **kwargs,
    )


@pytest.fixture
def euro_fund(contract):
    return _holding(contract, "Fonds euros", 6000, AssetClass.EURO_FUND)


@pytest.mark.django_db
class TestSplit:
    def test_split(self, contract, euro_fund):
        _holding(contract, "World", 3900, AssetClass.EQUITIES)
        _holding(contract, "Closed", 999, AssetClass.EQUITIES, is_active=False)
        split = contract.euro_fund_split()
        assert split is not None
        assert split.euro_funds == Money(6000, "EUR")
        assert split.units == Money(3900, "EUR")
        assert split.cash == Money(100, "EUR")
        assert split.total == Money(10000, "EUR")
        assert split.euro_funds_percent == 60.0
        assert split.units_percent == 39.0
        assert euro_fund.is_euro_fund is True

    def test_no_euro_fund(self, contract):
        _holding(contract, "World", 3900, AssetClass.EQUITIES)
        assert contract.euro_fund_split() is None

    def test_empty_contract_percent(self, contract, euro_fund):
        euro_fund.initial_value = Money(0, "EUR")
        euro_fund.save()
        contract.opening_cash_value = Money(0, "EUR")
        contract.save()
        assert contract.euro_fund_split().euro_funds_percent == 0.0

    def test_account_detail_shows_split(self, user_client, contract, euro_fund):
        response = user_client.get(
            reverse("finance:investment_detail", args=[contract.pk])
        )
        assert 'id="euro-fund-split"' in response.content.decode()


@pytest.mark.django_db
class TestRates:
    def _url(self, holding, name="finance:add_euro_fund_rate", **extra):
        return reverse(
            name,
            kwargs={
                "account_pk": holding.account.pk,
                "holding_pk": holding.pk,
                **extra,
            },
        )

    def test_add_replace_delete(self, user_client, euro_fund):
        response = user_client.post(
            self._url(euro_fund), {"year": 2024, "rate": "2.50", "notes": "Bonus"}
        )
        assert response.status_code == 302
        assert response.url.endswith("#rates-panel")
        user_client.post(self._url(euro_fund), {"year": 2024, "rate": "2.60"})
        rate = EuroFundRate.objects.get(holding=euro_fund)
        assert rate.rate == Decimal("2.60")
        assert "2024" in str(rate)

        response = user_client.post(
            self._url(euro_fund, "finance:delete_euro_fund_rate", rate_pk=rate.pk)
        )
        assert response.status_code == 302
        assert not EuroFundRate.objects.exists()

    def test_invalid(self, user_client, euro_fund):
        response = user_client.post(self._url(euro_fund), {"year": "", "rate": "x"})
        assert any(
            "correct the errors" in str(m) for m in get_messages(response.wsgi_request)
        )
        assert not EuroFundRate.objects.exists()

    def test_holding_detail_shows_rates(self, user_client, euro_fund):
        EuroFundRate.objects.create(holding=euro_fund, year=2023, rate=Decimal(2))
        EuroFundRate.objects.create(holding=euro_fund, year=2024, rate=Decimal(3))
        response = user_client.get(
            reverse(
                "finance:holding_detail",
                kwargs={"account_pk": euro_fund.account.pk, "holding_pk": euro_fund.pk},
            )
        )
        assert response.context["average_rate"] == Decimal("2.5")
        assert 'id="rates-panel"' in response.content.decode()

    def test_rates_hidden_for_other_holdings(self, user_client, contract):
        holding = _holding(contract, "World", 100, AssetClass.EQUITIES)
        response = user_client.get(
            reverse(
                "finance:holding_detail",
                kwargs={"account_pk": contract.pk, "holding_pk": holding.pk},
            )
        )
        assert response.context["average_rate"] is None
        assert 'id="rates-panel"' not in response.content.decode()

    def test_get_not_allowed(self, user_client, euro_fund):
        assert user_client.get(self._url(euro_fund)).status_code == 405
