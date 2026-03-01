"""Tests for finance account favorite toggle functionality."""

import datetime
from decimal import Decimal

import pytest
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory
from django.urls import reverse
from djmoney.money import Money

from finance.context_processors import nav_accounts
from finance.models.investment_account import InvestmentAccount, InvestmentAccountType
from finance.models.saving_account import SavingAccount, SavingAccountType

# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def saving_type(db):
    return SavingAccountType.objects.create(name="Livret A", code="LA")


@pytest.fixture
def investment_type(db):
    return InvestmentAccountType.objects.create(name="PEA", code="PEA")


def _make_saving(saving_type, name, is_active=True, is_favorite=False):
    return SavingAccount.objects.create(
        account_type=saving_type,
        name=name,
        is_active=is_active,
        is_favorite=is_favorite,
        opening_value=Money(Decimal("1000"), "EUR"),
        opening_date=datetime.date.today(),
    )


def _make_investment(investment_type, name, is_active=True, is_favorite=False):
    return InvestmentAccount.objects.create(
        account_type=investment_type,
        name=name,
        is_active=is_active,
        is_favorite=is_favorite,
        opening_cash_value=Money(Decimal("5000"), "EUR"),
        opening_date=datetime.date.today(),
    )


# ─── Context processor ───────────────────────────────────────────────────────


@pytest.mark.django_db
def test_nav_accounts_unauthenticated_returns_empty():
    """Anonymous user should receive empty nav_accounts."""
    factory = RequestFactory()
    request = factory.get("/")
    request.user = AnonymousUser()

    result = nav_accounts(request)

    assert result["nav_accounts"] == []
    assert result["nav_accounts_any"] is False


@pytest.mark.django_db
def test_nav_accounts_shows_only_favorites(user, saving_type, investment_type):
    """Only active + favorite accounts should appear in nav."""
    fav_saving = _make_saving(saving_type, "Fav Saving", is_favorite=True)
    _make_saving(saving_type, "Normal Saving", is_favorite=False)
    fav_inv = _make_investment(investment_type, "Fav Investment", is_favorite=True)
    _make_investment(investment_type, "Normal Investment", is_favorite=False)
    _make_saving(saving_type, "Inactive Fav", is_active=False, is_favorite=True)

    factory = RequestFactory()
    request = factory.get("/")
    request.user = user

    result = nav_accounts(request)

    saving_names = [a.name for a in result["nav_accounts_saving"]]
    investment_names = [a.name for a in result["nav_accounts_investment"]]
    assert fav_saving.name in saving_names
    assert "Normal Saving" not in saving_names
    assert fav_inv.name in investment_names
    assert "Normal Investment" not in investment_names
    assert "Inactive Fav" not in saving_names


@pytest.mark.django_db
def test_nav_accounts_any_true_when_accounts_exist(user, saving_type):
    """nav_accounts_any should be True when active accounts exist."""
    _make_saving(saving_type, "Some Account", is_favorite=False)

    factory = RequestFactory()
    request = factory.get("/")
    request.user = user

    result = nav_accounts(request)

    assert result["nav_accounts_any"] is True


# ─── Toggle saving favorite view ─────────────────────────────────────────────


@pytest.mark.django_db
def test_toggle_saving_favorite_adds(user_client, saving_type):
    """POST should set is_favorite=True on a non-favorite saving account."""
    account = _make_saving(saving_type, "Livret", is_favorite=False)

    url = reverse("finance:toggle_saving_favorite", kwargs={"pk": account.pk})
    response = user_client.post(url)

    account.refresh_from_db()
    assert account.is_favorite is True
    assert response.status_code == 302


@pytest.mark.django_db
def test_toggle_saving_favorite_removes(user_client, saving_type):
    """POST should set is_favorite=False on a favorite saving account."""
    account = _make_saving(saving_type, "Livret", is_favorite=True)

    url = reverse("finance:toggle_saving_favorite", kwargs={"pk": account.pk})
    response = user_client.post(url)

    account.refresh_from_db()
    assert account.is_favorite is False
    assert response.status_code == 302


@pytest.mark.django_db
def test_toggle_saving_favorite_get_not_allowed(user_client, saving_type):
    """GET to toggle_saving_favorite should return 405."""
    account = _make_saving(saving_type, "Livret")

    url = reverse("finance:toggle_saving_favorite", kwargs={"pk": account.pk})
    response = user_client.get(url)

    assert response.status_code == 405


@pytest.mark.django_db
def test_toggle_saving_favorite_404_on_missing(user_client):
    """POST with unknown pk should return 404."""
    url = reverse("finance:toggle_saving_favorite", kwargs={"pk": 99999})
    response = user_client.post(url)

    assert response.status_code == 404


# ─── Toggle investment favorite view ─────────────────────────────────────────


@pytest.mark.django_db
def test_toggle_investment_favorite_adds(user_client, investment_type):
    """POST should set is_favorite=True on a non-favorite investment account."""
    account = _make_investment(investment_type, "PEA", is_favorite=False)

    url = reverse("finance:toggle_investment_favorite", kwargs={"pk": account.pk})
    response = user_client.post(url)

    account.refresh_from_db()
    assert account.is_favorite is True
    assert response.status_code == 302


@pytest.mark.django_db
def test_toggle_investment_favorite_removes(user_client, investment_type):
    """POST should set is_favorite=False on a favorite investment account."""
    account = _make_investment(investment_type, "PEA", is_favorite=True)

    url = reverse("finance:toggle_investment_favorite", kwargs={"pk": account.pk})
    response = user_client.post(url)

    account.refresh_from_db()
    assert account.is_favorite is False
    assert response.status_code == 302


@pytest.mark.django_db
def test_toggle_investment_favorite_get_not_allowed(user_client, investment_type):
    """GET to toggle_investment_favorite should return 405."""
    account = _make_investment(investment_type, "PEA")

    url = reverse("finance:toggle_investment_favorite", kwargs={"pk": account.pk})
    response = user_client.get(url)

    assert response.status_code == 405


@pytest.mark.django_db
def test_toggle_investment_favorite_404_on_missing(user_client):
    """POST with unknown pk should return 404."""
    url = reverse("finance:toggle_investment_favorite", kwargs={"pk": 99999})
    response = user_client.post(url)

    assert response.status_code == 404
