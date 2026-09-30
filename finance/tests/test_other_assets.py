"""Tests for the other assets (vehicles, precious metals, crypto…)."""

import datetime
from decimal import Decimal

import pytest
from django.contrib.messages import get_messages
from django.urls import reverse
from moneyed import Money

from base.choices import Liquidity
from finance.models.other_asset import OtherAsset, OtherAssetValue
from finance.services.market_data import LiveQuote, MarketDataError
from finance.views import other_asset_views

TODAY = datetime.date.today()


@pytest.fixture(autouse=True)
def _no_other_assets(request):
    """Start without assets, whatever the session fixtures loaded."""
    if request.node.get_closest_marker("django_db"):
        OtherAsset.objects.all().delete()


def _asset(**kwargs) -> OtherAsset:
    defaults = {
        "name": "Gold coins",
        "category": OtherAsset.Category.PRECIOUS_METALS,
        "acquisition_date": datetime.date(2020, 1, 1),
        "acquisition_value": Money(Decimal(1000), "EUR"),
    }
    defaults.update(kwargs)
    return OtherAsset.objects.create(**defaults)


def _quote(price: str, currency: str = "EUR") -> LiveQuote:
    return LiveQuote(
        name=None,
        price=Decimal(price),
        currency=currency,
        previous_close=None,
        day_high=None,
        day_low=None,
        year_high=None,
        year_low=None,
        fifty_day_average=None,
        two_hundred_day_average=None,
        exchange=None,
        as_of=datetime.datetime.now(),
    )


def _messages(response) -> list[str]:
    return [str(m) for m in get_messages(response.wsgi_request)]


@pytest.mark.django_db
class TestOtherAssetModel:
    def test_value_history(self):
        asset = _asset()
        assert asset.get_value(datetime.date(2019, 12, 31)).amount == 0
        assert asset.get_value(datetime.date(2020, 6, 1)).amount == 1000
        OtherAssetValue.objects.create(
            asset=asset, value=Money(1500, "EUR"), value_date=datetime.date(2021, 1, 1)
        )
        assert asset.get_value(datetime.date(2020, 12, 31)).amount == 1000
        assert asset.current_value.amount == 1500
        assert asset.capital_gain.amount == 500
        assert str(asset) == "Gold coins"
        assert "Gold coins" in str(asset.values.first())

    def test_sold_asset_is_worth_nothing_after_sale(self):
        asset = _asset(sold_date=datetime.date(2022, 1, 1), is_active=False)
        assert asset.get_value(datetime.date(2021, 12, 31)).amount == 1000
        assert asset.get_value(datetime.date(2022, 1, 1)).amount == 0

    def test_liquidity_and_icon(self):
        crypto = _asset(category=OtherAsset.Category.CRYPTO)
        assert crypto.effective_liquidity == Liquidity.IMMEDIATE
        assert crypto.icon == "bi-currency-bitcoin"
        crypto.liquidity = Liquidity.LOCKED
        assert crypto.get_effective_liquidity_display() == "Locked until a term"
        assert crypto.has_market_price is False
        crypto.ticker = "BTC-EUR"
        crypto.quantity = Decimal("0.5")
        assert crypto.has_market_price is True


@pytest.mark.django_db
class TestOtherAssetViews:
    def test_list(self, user_client):
        _asset()
        _asset(name="Old car", category=OtherAsset.Category.VEHICLE, is_active=False)
        response = user_client.get(reverse("finance:other_asset_list"))
        assert response.status_code == 200
        assert response.context["totals"] == {"EUR": Money(1000, "EUR")}
        assert "Old car" in response.content.decode()

    def test_empty_list(self, user_client):
        response = user_client.get(reverse("finance:other_asset_list"))
        assert "Track vehicles" in response.content.decode()

    def test_detail(self, user_client):
        asset = _asset(ticker="GC=F", quantity=Decimal(2), notes="In a safe")
        response = user_client.get(
            reverse("finance:other_asset_detail", args=[asset.pk])
        )
        content = response.content.decode()
        assert response.status_code == 200
        assert "Update from market price" in content
        assert "In a safe" in content

    def test_create_edit_delete(self, user_client):
        response = user_client.post(
            reverse("finance:new_other_asset"),
            {
                "name": "Car",
                "category": "vehicle",
                "acquisition_date": "2023-05-01",
                "acquisition_value_0": "20000",
                "acquisition_value_1": "EUR",
                "is_active": "on",
            },
        )
        asset = OtherAsset.objects.get(name="Car")
        assert response.status_code == 302
        assert response.url == reverse("finance:other_asset_detail", args=[asset.pk])

        response = user_client.post(
            reverse("finance:edit_other_asset", args=[asset.pk]),
            {"name": "", "category": "vehicle"},
        )
        assert response.status_code == 200
        assert "Please correct the errors below." in _messages(response)
        assert (
            user_client.get(
                reverse("finance:edit_other_asset", args=[asset.pk])
            ).status_code
            == 200
        )
        assert user_client.get(reverse("finance:new_other_asset")).status_code == 200

        response = user_client.post(
            reverse("finance:delete_other_asset", args=[asset.pk])
        )
        assert response.status_code == 302
        assert not OtherAsset.objects.filter(pk=asset.pk).exists()

    def test_value_crud(self, user_client):
        asset = _asset()
        url = reverse("finance:new_other_asset_value", args=[asset.pk])
        assert user_client.get(url).status_code == 200
        response = user_client.post(
            url, {"value_0": "1200", "value_1": "EUR", "value_date": "2024-01-01"}
        )
        assert response.status_code == 302
        value = asset.values.get()
        response = user_client.post(
            reverse("finance:delete_other_asset_value", args=[asset.pk, value.pk])
        )
        assert response.status_code == 302
        assert not asset.values.exists()

    def test_chart_data(self, user_client):
        asset = _asset()
        OtherAssetValue.objects.create(
            asset=asset, value=Money(1100, "EUR"), value_date=datetime.date(2021, 1, 1)
        )
        response = user_client.get(
            reverse(
                "finance:chart_data",
                kwargs={"data_type": "other_asset", "object_id": asset.pk},
            )
        )
        data = response.json()
        assert data["success"] is True
        assert data["values"] == [{"date": "2021-01-01", "value": 1100.0}]
        assert data["invested"][0]["value"] == 1000.0


@pytest.mark.django_db
class TestUpdatePrice:
    def _post(self, client, asset):
        return client.post(reverse("finance:update_other_asset_price", args=[asset.pk]))

    def test_records_quantity_times_price(self, user_client, monkeypatch):
        monkeypatch.setattr(
            other_asset_views, "get_live_quote", lambda *a, **k: _quote("60000.123")
        )
        asset = _asset(
            category=OtherAsset.Category.CRYPTO,
            ticker="BTC-EUR",
            quantity=Decimal("0.5"),
        )
        response = self._post(user_client, asset)
        assert response.status_code == 302
        assert asset.values.get(value_date=TODAY).value == Money(
            Decimal("30000.06"), "EUR"
        )
        # A second update the same day replaces the value.
        self._post(user_client, asset)
        assert asset.values.count() == 1

    def test_currency_mismatch(self, user_client, monkeypatch):
        monkeypatch.setattr(
            other_asset_views, "get_live_quote", lambda *a, **k: _quote("1", "USD")
        )
        asset = _asset(ticker="GC=F", quantity=Decimal(1))
        response = self._post(user_client, asset)
        assert any("differs" in m for m in _messages(response))
        assert not asset.values.exists()

    def test_market_error(self, user_client, monkeypatch):
        def _fail(*args, **kwargs):
            raise MarketDataError("no data")

        monkeypatch.setattr(other_asset_views, "get_live_quote", _fail)
        asset = _asset(ticker="XXX", quantity=Decimal(1))
        assert "no data" in _messages(self._post(user_client, asset))

    def test_without_ticker(self, user_client):
        response = self._post(user_client, _asset())
        assert any("not available" in m for m in _messages(response))

    def test_get_not_allowed(self, user_client):
        asset = _asset()
        response = user_client.get(
            reverse("finance:update_other_asset_price", args=[asset.pk])
        )
        assert response.status_code == 405


@pytest.mark.django_db
class TestNetWorth:
    def test_net_worth_and_chart_include_other_assets(self, user_client):
        _asset(acquisition_date=TODAY - datetime.timedelta(days=400))
        data = user_client.get(reverse("api_net_worth")).json()
        assert data["has_other"] is True
        assert data["total_other"] >= 1000
        chart = user_client.get(reverse("api_patrimony_chart") + "?range=1").json()
        assert chart["other"][-1] >= 1000
