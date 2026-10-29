"""Tests for the daily security price refresh and the security drop alerts."""

import datetime
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.urls import reverse
from moneyed import Money

from finance import jobs, notifications
from finance.forms import InvestmentAccountHoldingForm
from finance.models.investment_account import (
    InvestmentAccountHolding,
    InvestmentAccountHoldingHistory,
    QuoteSnapshot,
)
from finance.services.market_data import HistoricalPricePoint, MarketDataError

TODAY = datetime.date.today()
ISIN = "FR0010315770"
OTHER_ISIN = "IE00B4L5Y983"


def _points(*prices, last=TODAY):
    """Daily closes ending on *last*, oldest first."""
    count = len(prices)
    return [
        HistoricalPricePoint(
            date=last - datetime.timedelta(days=count - 1 - index),
            price=Decimal(str(price)),
        )
        for index, price in enumerate(prices)
    ]


@pytest.fixture
def holding(active_investment_account, user):
    return InvestmentAccountHolding.objects.create(
        account=active_investment_account,
        name="World ETF",
        code="WRLD",
        isin=ISIN,
        initial_quantity=Decimal(10),
        initial_value=Money(1000, "EUR"),
        initial_valuation_date=TODAY - datetime.timedelta(days=100),
        auto_update_price=True,
    )


@pytest.fixture(autouse=True)
def no_pause():
    with patch.object(jobs.time, "sleep"):
        yield


def _fetch(prices_by_symbol):
    def fake(symbol, days=45):
        value = prices_by_symbol[symbol]
        if isinstance(value, Exception):
            raise value
        return value

    return fake


@pytest.mark.django_db
def test_refresh_stores_closes_and_updates_auto_holdings(holding):
    manual = InvestmentAccountHolding.objects.create(
        account=holding.account,
        name="Manual",
        isin=OTHER_ISIN,
        initial_quantity=Decimal(5),
    )
    prices = {
        ISIN: (_points(100, 101, 102.5), "EUR"),
        OTHER_ISIN: (_points(50, 51), "EUR"),
    }
    with patch.object(jobs, "fetch_daily_closes", side_effect=_fetch(prices)):
        summary = jobs.refresh_security_prices()
    assert summary == "2/2 securities, 1 holding(s) updated"
    assert QuoteSnapshot.objects.filter(isin=ISIN).count() == 3
    assert QuoteSnapshot.objects.filter(isin=OTHER_ISIN).count() == 2
    row = InvestmentAccountHoldingHistory.objects.get(holding=holding)
    assert row.value == Money(Decimal("1025.00"), "EUR")
    assert row.quantity == Decimal(10)
    assert row.valuation_date == datetime.datetime.combine(TODAY, datetime.time.min)
    assert not InvestmentAccountHoldingHistory.objects.filter(holding=manual).exists()


@pytest.mark.django_db
def test_refresh_is_idempotent_and_keeps_manual_values(holding):
    InvestmentAccountHoldingHistory.objects.create(
        holding=holding,
        value=Money(999, "EUR"),
        quantity=Decimal(10),
        valuation_date=datetime.datetime.combine(TODAY, datetime.time(18)),
    )
    prices = {ISIN: (_points(100, 105), "EUR")}
    with patch.object(jobs, "fetch_daily_closes", side_effect=_fetch(prices)):
        assert jobs.refresh_security_prices() == "1/1 securities, 0 holding(s) updated"
        jobs.refresh_security_prices()
    assert InvestmentAccountHoldingHistory.objects.filter(holding=holding).count() == 1
    assert QuoteSnapshot.objects.filter(isin=ISIN).count() == 2


@pytest.mark.django_db
def test_refresh_skips_a_holding_without_quantity(holding):
    holding.initial_quantity = None
    holding.save()
    prices = {ISIN: (_points(100), "EUR")}
    with patch.object(jobs, "fetch_daily_closes", side_effect=_fetch(prices)):
        jobs.refresh_security_prices()
    assert not InvestmentAccountHoldingHistory.objects.exists()


@pytest.mark.django_db
def test_refresh_converts_another_currency(holding):
    prices = {
        ISIN: (_points(100, 110), "USD"),
        "USDEUR=X": (_points(Decimal("0.9"), Decimal("0.8")), "EUR"),
    }
    with patch.object(jobs, "fetch_daily_closes", side_effect=_fetch(prices)):
        summary = jobs.refresh_security_prices()
    assert summary == (
        "1/1 securities, 1 holding(s) updated (1 converted from another currency)"
    )
    row = InvestmentAccountHoldingHistory.objects.get(holding=holding)
    assert row.value == Money(Decimal("880.00"), "EUR")  # 110 USD × 0.8 × 10


@pytest.mark.django_db
def test_refresh_without_exchange_rate(holding):
    prices = {
        ISIN: (_points(100), "USD"),
        "USDEUR=X": MarketDataError("no rate"),
    }
    with patch.object(jobs, "fetch_daily_closes", side_effect=_fetch(prices)):
        summary = jobs.refresh_security_prices()
    assert summary == "1/1 securities, 0 holding(s) updated, 1 without exchange rate"
    assert not InvestmentAccountHoldingHistory.objects.exists()


def test_exchange_rate_of_an_earlier_day():
    rates = jobs.ExchangeRates()
    points = _points(Decimal("0.9"), last=TODAY - datetime.timedelta(days=3))
    with patch.object(jobs, "fetch_daily_closes", return_value=(points, "EUR")) as get:
        assert rates.rate("USD", "EUR", TODAY) == Decimal("0.9")
        assert rates.rate("USD", "EUR", TODAY - datetime.timedelta(days=10)) is None
    get.assert_called_once_with("USDEUR=X")


@pytest.mark.django_db
def test_refresh_reports_partial_failures(holding):
    InvestmentAccountHolding.objects.create(
        account=holding.account, name="Broken", isin=OTHER_ISIN
    )
    prices = {ISIN: (_points(100), "EUR"), OTHER_ISIN: MarketDataError("down")}
    with patch.object(jobs, "fetch_daily_closes", side_effect=_fetch(prices)):
        summary = jobs.refresh_security_prices()
    assert summary == f"1/2 securities, 1 holding(s) updated; failed: {OTHER_ISIN}"


@pytest.mark.django_db
def test_refresh_raises_when_everything_fails(holding):
    prices = {ISIN: MarketDataError("down")}
    with (
        patch.object(jobs, "fetch_daily_closes", side_effect=_fetch(prices)),
        pytest.raises(MarketDataError, match="No price could be fetched"),
    ):
        jobs.refresh_security_prices()


@pytest.mark.django_db
def test_refresh_handles_empty_closes(holding):
    with patch.object(jobs, "fetch_daily_closes", return_value=([], "EUR")):
        assert jobs.refresh_security_prices() == "1/1 securities, 0 holding(s) updated"


@pytest.mark.django_db
def test_refresh_prunes_old_closes(holding):
    QuoteSnapshot.objects.create(
        isin=ISIN, date=TODAY - datetime.timedelta(days=500), close=1, currency="EUR"
    )
    with patch.object(jobs, "fetch_daily_closes", return_value=([], "EUR")):
        jobs.refresh_security_prices()
    assert not QuoteSnapshot.objects.exists()


@pytest.mark.django_db
def test_refresh_respects_the_live_data_setting(holding, user):
    user.profile.live_data_enabled = False
    user.profile.save()
    with patch.object(jobs, "fetch_daily_closes") as fetch:
        assert jobs.refresh_security_prices() == "Live market data is disabled"
    fetch.assert_not_called()


def test_refresh_job_is_registered():
    from base.scheduler import get_job

    assert get_job("refresh_security_prices").at == datetime.time(7, 0)


# ── Security drop alert ─────────────────────────────────────────────────────


def _closes(isin, *prices, last=TODAY, step=1):
    for index, price in enumerate(reversed(prices)):
        QuoteSnapshot.objects.create(
            isin=isin,
            date=last - datetime.timedelta(days=index * step),
            close=Decimal(str(price)),
            currency="EUR",
        )


@pytest.mark.django_db
def test_security_drop_over_one_day(holding):
    _closes(ISIN, 100, 94)
    (event,) = notifications._security_drops({"threshold": 5, "window": 1}, TODAY)
    assert event.title == "World ETF (WRLD) dropped 6.0 % in 1 day"
    assert event.body == f"Close of {TODAY.isoformat()}: 94.00 EUR"
    assert event.key == f"{ISIN}:{TODAY.isoformat()}:1"
    assert event.url == reverse(
        "finance:holding_detail",
        kwargs={"account_pk": holding.account_id, "holding_pk": holding.pk},
    )
    assert (
        list(notifications._security_drops({"threshold": 7, "window": 1}, TODAY)) == []
    )


@pytest.mark.django_db
def test_security_drop_over_a_week(holding):
    _closes(ISIN, 100, 99, 98, 97, 96, 95, 93, 90)
    (event,) = notifications._security_drops({"threshold": 5, "window": 7}, TODAY)
    assert "dropped 10.0 % in 7 days" in event.title
    assert (
        list(notifications._security_drops({"threshold": 5, "window": 30}, TODAY)) == []
    )


@pytest.mark.django_db
def test_security_drop_needs_a_recent_close(holding):
    _closes(ISIN, 100, 50, last=TODAY - datetime.timedelta(days=10))
    assert (
        list(notifications._security_drops({"threshold": 5, "window": 1}, TODAY)) == []
    )


@pytest.mark.django_db
def test_security_drop_needs_two_closes(holding):
    _closes(ISIN, 100)
    assert (
        list(notifications._security_drops({"threshold": 5, "window": 1}, TODAY)) == []
    )


@pytest.mark.django_db
def test_security_drop_ignores_inactive_holdings(holding):
    holding.is_active = False
    holding.save()
    _closes(ISIN, 100, 50)
    assert (
        list(notifications._security_drops({"threshold": 5, "window": 1}, TODAY)) == []
    )


# ── Holding form ────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_auto_update_needs_an_isin(active_investment_account):
    data = {
        "name": "No ISIN",
        "isin": "",
        "fees": "0",
        "is_active": "on",
        "auto_update_price": "on",
        "initial_value_0": "0",
        "initial_value_1": "EUR",
        "initial_valuation_date": TODAY.isoformat(),
    }
    form = InvestmentAccountHoldingForm(data=data)
    assert not form.is_valid()
    assert "auto_update_price" in form.errors
    form = InvestmentAccountHoldingForm(data={**data, "isin": ISIN})
    assert form.is_valid(), form.errors


@pytest.mark.django_db
def test_bulk_update_shows_the_auto_badge(admin_client, holding):
    response = admin_client.get(reverse("finance:update"))
    assert "The price is updated automatically every day." in response.content.decode()
