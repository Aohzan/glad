"""Tests for finance/views/api_views.py — AccountsSummaryApiView."""

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
)
from finance.models.saving_account import SavingAccount, SavingAccountValue
from finance.services.market_data import LiveQuote, MarketDataError


def get_json(client, url):
    return client.get(url, HTTP_ACCEPT="application/json")


@pytest.mark.django_db
def test_accounts_summary_requires_login(client):
    response = get_json(client, reverse("finance:api_accounts_summary"))
    assert response.status_code == 302
    assert "/accounts/login/" in response.url


@pytest.mark.django_db
def test_accounts_summary_empty(admin_client):
    response = get_json(admin_client, reverse("finance:api_accounts_summary"))
    assert response.status_code == 200
    data = response.json()
    assert "breakdown_labels" in data
    assert "breakdown_values" in data
    assert "accounts" in data
    assert "alerts" in data
    assert isinstance(data["accounts"], list)
    assert isinstance(data["alerts"], list)


@pytest.mark.django_db
def test_accounts_summary_breakdown_labels(admin_client):
    response = get_json(admin_client, reverse("finance:api_accounts_summary"))
    data = response.json()
    assert "Investments" in data["breakdown_labels"]
    assert "Savings" in data["breakdown_labels"]
    assert len(data["breakdown_labels"]) == len(data["breakdown_values"])


@pytest.mark.django_db
def test_accounts_summary_includes_saving_account(admin_client, saving_account_type):
    acc = SavingAccount.objects.create(
        name="Livret A",
        account_type=saving_account_type,
        opening_value=Money(0, "EUR"),
        is_active=True,
    )
    SavingAccountValue.objects.create(
        account=acc, value=Money(3000, "EUR"), value_date=datetime.date.today()
    )
    response = get_json(admin_client, reverse("finance:api_accounts_summary"))
    data = response.json()
    names = [a["name"] for a in data["accounts"]]
    assert any("Livret A" in name for name in names)


@pytest.mark.django_db
def test_accounts_summary_account_structure(admin_client, saving_account_type):
    acc = SavingAccount.objects.create(
        name="Test",
        account_type=saving_account_type,
        opening_value=Money(0, "EUR"),
        is_active=True,
    )
    SavingAccountValue.objects.create(
        account=acc, value=Money(1000, "EUR"), value_date=datetime.date.today()
    )
    response = get_json(admin_client, reverse("finance:api_accounts_summary"))
    data = response.json()
    assert len(data["accounts"]) >= 1
    account = data["accounts"][0]
    for key in (
        "name",
        "value",
        "progression",
        "progression_percent",
        "progression_css",
        "icon",
        "type",
        "owner",
    ):
        assert key in account, f"Missing key: {key}"
    assert account["progression_css"] in ("success", "danger", "secondary")
    assert account["type"] in ("savings", "investment")


@pytest.mark.django_db
def test_accounts_summary_inactive_excluded(admin_client, saving_account_type):
    SavingAccount.objects.create(
        name="Inactive",
        account_type=saving_account_type,
        opening_value=Money(0, "EUR"),
        is_active=False,
        closing_date=datetime.date.today() - datetime.timedelta(days=1),
    )
    response = get_json(admin_client, reverse("finance:api_accounts_summary"))
    data = response.json()
    names = [a["name"] for a in data["accounts"]]
    assert "Inactive" not in names


@pytest.mark.django_db
def test_accounts_summary_alert_on_decline(admin_client, declining_saving_account):
    response = get_json(admin_client, reverse("finance:api_accounts_summary"))
    data = response.json()
    assert any("Declining" in a["account"] for a in data["alerts"])


@pytest.mark.django_db
def test_accounts_summary_investment_type(admin_client, investment_account_type, user):
    inv = InvestmentAccount.objects.create(
        name="PEA",
        account_type=investment_account_type,
        opening_cash_value=Money(0, "EUR"),
        is_active=True,
        owner=str(user),
    )
    InvestmentAccountCash.objects.create(
        account=inv, value=Money(5000, "EUR"), value_date=datetime.date.today()
    )
    response = get_json(admin_client, reverse("finance:api_accounts_summary"))
    data = response.json()
    investment_accounts = [a for a in data["accounts"] if a["type"] == "investment"]
    assert any("PEA" in a["name"] for a in investment_accounts)


# ─── HoldingLiveInfoApiView ─────────────────────────────────────────────────


@pytest.fixture
def investment_account_for_live_info(investment_account_type):
    return InvestmentAccount.objects.create(
        name="PEA",
        account_type=investment_account_type,
        opening_cash_value=Money(0, "EUR"),
        is_active=True,
    )


@pytest.fixture
def holding_with_isin(investment_account_for_live_info):
    return InvestmentAccountHolding.objects.create(
        account=investment_account_for_live_info,
        name="World ETF",
        code="CW8",
        isin="LU1681043599",
        is_active=True,
        initial_quantity=Decimal("10.0000"),
        initial_value=Money(Decimal("300.00"), "EUR"),
    )


@pytest.fixture
def holding_without_isin(investment_account_for_live_info):
    return InvestmentAccountHolding.objects.create(
        account=investment_account_for_live_info,
        name="No ISIN Holding",
        is_active=True,
        initial_quantity=Decimal("5.0000"),
        initial_value=Money(Decimal("100.00"), "EUR"),
    )


def _live_info_url(account, holding):
    return reverse(
        "finance:api_holding_live_info",
        kwargs={"account_pk": account.pk, "holding_pk": holding.pk},
    )


@pytest.mark.django_db
def test_holding_live_info_requires_login(
    client, investment_account_for_live_info, holding_with_isin
):
    response = get_json(
        client, _live_info_url(investment_account_for_live_info, holding_with_isin)
    )
    assert response.status_code == 302
    assert "/accounts/login/" in response.url


@pytest.mark.django_db
def test_holding_live_info_no_isin(
    admin_client, investment_account_for_live_info, holding_without_isin
):
    response = get_json(
        admin_client,
        _live_info_url(investment_account_for_live_info, holding_without_isin),
    )
    assert response.status_code == 400
    assert response.json()["error"] == "no_isin"


@pytest.mark.django_db
def test_holding_live_info_success(
    admin_client, investment_account_for_live_info, holding_with_isin
):
    quote = LiveQuote(
        name="World ETF",
        price=Decimal("123.45"),
        currency="EUR",
        previous_close=Decimal("120.0"),
        day_high=Decimal("125.0"),
        day_low=Decimal("119.0"),
        year_high=Decimal("130.0"),
        year_low=Decimal("100.0"),
        fifty_day_average=Decimal("122.0"),
        two_hundred_day_average=Decimal("115.0"),
        exchange="PAR",
        as_of=datetime.datetime.now(),
    )
    with patch("finance.views.api_views.get_live_quote", return_value=quote):
        response = get_json(
            admin_client,
            _live_info_url(investment_account_for_live_info, holding_with_isin),
        )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "World ETF"
    assert data["price"] == 123.45
    assert data["currency"] == "EUR"
    assert data["currency_mismatch"] is False
    assert data["quantity"] == 10.0
    assert data["total_value"] == pytest.approx(1234.5)


@pytest.mark.django_db
def test_holding_live_info_currency_mismatch(
    admin_client, investment_account_for_live_info, holding_with_isin
):
    quote = LiveQuote(
        name="US Stock",
        price=Decimal("50.0"),
        currency="USD",
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
    with patch("finance.views.api_views.get_live_quote", return_value=quote):
        response = get_json(
            admin_client,
            _live_info_url(investment_account_for_live_info, holding_with_isin),
        )
    assert response.status_code == 200
    assert response.json()["currency_mismatch"] is True


@pytest.mark.django_db
def test_holding_live_info_market_data_error(
    admin_client, investment_account_for_live_info, holding_with_isin
):
    with patch(
        "finance.views.api_views.get_live_quote",
        side_effect=MarketDataError("boom"),
    ):
        response = get_json(
            admin_client,
            _live_info_url(investment_account_for_live_info, holding_with_isin),
        )
    assert response.status_code == 502
    assert response.json()["error"] == "boom"


@pytest.mark.django_db
def test_holding_live_info_disabled_by_user_setting(
    admin_client, admin_user, investment_account_for_live_info, holding_with_isin
):
    admin_user.profile.live_data_enabled = False
    admin_user.profile.save()

    response = get_json(
        admin_client,
        _live_info_url(investment_account_for_live_info, holding_with_isin),
    )
    assert response.status_code == 403
    assert response.json()["error"] == "live_data_disabled"


# ─── HoldingAutofillApiView ──────────────────────────────────────────────────


@pytest.mark.django_db
def test_holding_autofill_requires_login(client):
    response = get_json(
        client, reverse("finance:api_holding_autofill") + "?isin=LU1681043599"
    )
    assert response.status_code == 302
    assert "/accounts/login/" in response.url


@pytest.mark.django_db
def test_holding_autofill_invalid_isin(admin_client):
    response = get_json(
        admin_client, reverse("finance:api_holding_autofill") + "?isin=short"
    )
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_isin"


@pytest.mark.django_db
def test_holding_autofill_success(admin_client):
    from finance.services.market_data import HoldingAutofillInfo

    autofill = HoldingAutofillInfo(
        code="CW8",
        name="Amundi MSCI World",
        issuer="Amundi",
        fees=Decimal("0.38"),
        initial_value=Decimal("450.5"),
        currency="EUR",
    )
    with patch("finance.views.api_views.fetch_holding_autofill", return_value=autofill):
        response = get_json(
            admin_client,
            reverse("finance:api_holding_autofill") + "?isin=LU1681043599",
        )
    assert response.status_code == 200
    data = response.json()
    assert data["code"] == "CW8"
    assert data["fees"] == 0.38
    assert data["initial_value"] == 450.5


@pytest.mark.django_db
def test_holding_autofill_market_data_error(admin_client):
    with patch(
        "finance.views.api_views.fetch_holding_autofill",
        side_effect=MarketDataError("boom"),
    ):
        response = get_json(
            admin_client,
            reverse("finance:api_holding_autofill") + "?isin=LU1681043599",
        )
    assert response.status_code == 502
    assert response.json()["error"] == "boom"


@pytest.mark.django_db
def test_holding_autofill_disabled_by_user_setting(admin_client, admin_user):
    admin_user.profile.live_data_enabled = False
    admin_user.profile.save()

    response = get_json(
        admin_client,
        reverse("finance:api_holding_autofill") + "?isin=LU1681043599",
    )
    assert response.status_code == 403
    assert response.json()["error"] == "live_data_disabled"


# ─── InvestmentLiveChangeApiView ─────────────────────────────────────────────


def _live_change_quote(price, previous_close, currency="EUR"):
    return LiveQuote(
        name="World ETF",
        price=Decimal(str(price)),
        currency=currency,
        previous_close=Decimal(str(previous_close)) if previous_close else None,
        day_high=None,
        day_low=None,
        year_high=None,
        year_low=None,
        fifty_day_average=None,
        two_hundred_day_average=None,
        exchange=None,
        as_of=datetime.datetime.now(),
    )


@pytest.mark.django_db
def test_investments_live_change_requires_login(client):
    response = get_json(client, reverse("finance:api_investments_live_change"))
    assert response.status_code == 302
    assert "/accounts/login/" in response.url


@pytest.mark.django_db
def test_investments_live_change_disabled_by_user_setting(admin_client, admin_user):
    admin_user.profile.live_data_enabled = False
    admin_user.profile.save()

    response = get_json(admin_client, reverse("finance:api_investments_live_change"))
    assert response.status_code == 200
    assert response.json() == {"enabled": False}


@pytest.mark.django_db
def test_investments_live_change_no_accounts(admin_client):
    response = get_json(admin_client, reverse("finance:api_investments_live_change"))
    data = response.json()
    assert data == {"enabled": True, "accounts": {}, "alerts": []}


@pytest.mark.django_db
def test_investments_live_change_drop_generates_alert(
    admin_client, investment_account_for_live_info, holding_with_isin
):
    quote = _live_change_quote(price=100, previous_close=110)
    with patch("finance.views.api_views.get_live_quote", return_value=quote):
        response = get_json(
            admin_client, reverse("finance:api_investments_live_change")
        )
    data = response.json()
    assert data["enabled"] is True
    account_data = data["accounts"][str(investment_account_for_live_info.pk)]
    assert account_data["live_change_percent"] == pytest.approx(-9.09, abs=0.01)
    assert len(data["alerts"]) == 1
    assert data["alerts"][0]["account"] == str(investment_account_for_live_info)


@pytest.mark.django_db
def test_investments_live_change_positive_no_alert(
    admin_client, investment_account_for_live_info, holding_with_isin
):
    quote = _live_change_quote(price=110, previous_close=100)
    with patch("finance.views.api_views.get_live_quote", return_value=quote):
        response = get_json(
            admin_client, reverse("finance:api_investments_live_change")
        )
    data = response.json()
    account_data = data["accounts"][str(investment_account_for_live_info.pk)]
    assert account_data["live_change_percent"] == pytest.approx(10.0)
    assert data["alerts"] == []


@pytest.mark.django_db
def test_investments_live_change_skips_currency_mismatch(
    admin_client, investment_account_for_live_info, holding_with_isin
):
    quote = _live_change_quote(price=100, previous_close=90, currency="USD")
    with patch("finance.views.api_views.get_live_quote", return_value=quote):
        response = get_json(
            admin_client, reverse("finance:api_investments_live_change")
        )
    data = response.json()
    assert data["accounts"] == {}


@pytest.mark.django_db
def test_investments_live_change_skips_market_data_error(
    admin_client, investment_account_for_live_info, holding_with_isin
):
    with patch(
        "finance.views.api_views.get_live_quote", side_effect=MarketDataError("boom")
    ):
        response = get_json(
            admin_client, reverse("finance:api_investments_live_change")
        )
    data = response.json()
    assert data["accounts"] == {}


@pytest.mark.django_db
def test_investments_live_change_ignores_holding_without_isin(
    admin_client, investment_account_for_live_info, holding_without_isin
):
    response = get_json(admin_client, reverse("finance:api_investments_live_change"))
    data = response.json()
    assert data["accounts"] == {}
