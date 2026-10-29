"""Tests for the notification types of the base app."""

import datetime
from decimal import Decimal
from importlib.metadata import PackageNotFoundError
from unittest.mock import MagicMock, patch

import httpx
import pytest
from moneyed import Money

from base import notifications
from base.services.dashboard import Hero
from finance.models.investment_account import (
    InvestmentAccount,
    InvestmentAccountCash,
    InvestmentAccountType,
)
from finance.models.other_asset import OtherAsset
from finance.models.saving_account import (
    SavingAccount,
    SavingAccountType,
    SavingAccountValue,
)
from property.models import Property, PropertyValue

TODAY = datetime.date.today()


@pytest.fixture
def old_assets():
    """A saving account valued 60 days ago and a property valued 400 days ago."""
    SavingAccount.objects.update(is_active=False)
    InvestmentAccount.objects.update(is_active=False)
    OtherAsset.objects.update(is_active=False)
    Property.objects.update(is_active=False)
    account = SavingAccount.objects.create(
        account_type=SavingAccountType.objects.get_or_create(
            code="LA", defaults={"name": "Livret A"}
        )[0],
        name="Old book",
        institution="Bank",
        opening_value=Money(100, "EUR"),
        opening_date=TODAY - datetime.timedelta(days=900),
    )
    SavingAccountValue.objects.create(
        account=account,
        value=Money(110, "EUR"),
        value_date=datetime.datetime.now() - datetime.timedelta(days=60),
    )
    prop = Property.objects.create(
        name="Old flat",
        property_type=Property.APARTMENT,
        buying_value=Money(100000, "EUR"),
        buying_date=datetime.date(2020, 1, 1),
    )
    PropertyValue.objects.create(
        property=prop,
        value=Money(120000, "EUR"),
        valuation_date=TODAY - datetime.timedelta(days=400),
    )
    cto = InvestmentAccountType.objects.get_or_create(
        code="CTO", defaults={"name": "CTO"}
    )[0]
    investment = InvestmentAccount.objects.create(
        account_type=cto,
        name="Fresh CTO",
        institution="Broker",
        opening_date=TODAY - datetime.timedelta(days=900),
    )
    InvestmentAccountCash.objects.create(
        account=investment,
        value=Money(10, "EUR"),
        value_date=TODAY - datetime.timedelta(days=2),
    )
    InvestmentAccount.objects.create(
        account_type=cto,
        name="Empty CTO",
        institution="Broker",
        opening_date=TODAY,
    )
    return account, prop


@pytest.mark.django_db
def test_stale_assets(old_assets):
    stale = notifications.stale_assets(TODAY, days=30, long_days=365)
    account, prop = old_assets
    assert [name for name, _ in stale] == [str(account), str(prop)]
    (event,) = notifications._stale_data({"days": 30, "long_days": 365}, TODAY)
    assert event.key == "stale"
    assert event.url == "/finance/update"
    assert event.title == "2 assets to update"
    assert list(notifications._stale_data({"days": 90, "long_days": 500}, TODAY)) == []


@pytest.mark.django_db
def test_no_stale_asset_before_the_data():
    earlier = TODAY - datetime.timedelta(days=4000)
    assert notifications.stale_assets(earlier, days=30, long_days=365) == []
    assert (
        list(notifications._stale_data({"days": 30, "long_days": 365}, earlier)) == []
    )


def test_as_date():
    moment = datetime.datetime(2026, 5, 1, 12, 30)
    assert notifications._as_date(moment) == datetime.date(2026, 5, 1)
    assert notifications._as_date(None) is None


INCOME_TAX = {"opening": "04-10", "deadline": "05-28", "days_before": 14}


@pytest.mark.parametrize(
    ("day", "keys"),
    [
        (datetime.date(2026, 4, 1), []),
        (datetime.date(2026, 4, 10), ["open:2026"]),
        (datetime.date(2026, 5, 20), ["open:2026", "deadline:2026"]),
        (datetime.date(2026, 5, 29), []),
    ],
)
def test_income_tax_return(day, keys):
    events = list(notifications._income_tax_return(INCOME_TAX, day))
    assert [e.key for e in events] == keys


def _release(tag: str) -> MagicMock:
    response = MagicMock()
    response.json.return_value = {
        "tag_name": tag,
        "html_url": f"https://github.com/Aohzan/glad/releases/tag/{tag}",
    }
    return response


def test_new_release_is_notified():
    with (
        patch.object(notifications.httpx, "get", return_value=_release("v99.0.0")),
        patch.object(notifications, "installed_version", return_value="1.7.0"),
    ):
        (event,) = notifications._app_release({}, TODAY)
    assert event.key == "v99.0.0"
    assert event.title == "Glad 99.0.0 is available"
    assert event.body == "Installed version: 1.7.0"
    assert event.url.endswith("/v99.0.0")


@pytest.mark.parametrize("tag", ["v1.7.0", "1.6.9", ""])
def test_current_or_older_release_is_not_notified(tag):
    with (
        patch.object(notifications.httpx, "get", return_value=_release(tag)),
        patch.object(notifications, "installed_version", return_value="1.7.0"),
    ):
        assert list(notifications._app_release({}, TODAY)) == []


def test_release_check_survives_a_network_error():
    with patch.object(
        notifications.httpx, "get", side_effect=httpx.ConnectError("offline")
    ):
        assert list(notifications._app_release({}, TODAY)) == []


def test_version_tuple():
    assert notifications._version_tuple("v1.10.0") > notifications._version_tuple(
        "1.9.3"
    )
    assert notifications._version_tuple("2.0.0-rc1") == (2, 0, 1)


def test_installed_version_without_metadata():
    with patch.object(notifications, "version", side_effect=PackageNotFoundError):
        assert notifications.installed_version() == "0"


def _hero(change_30d_pct, change_12m_pct):
    return Hero(
        net=Decimal(500000),
        gross=Decimal(600000),
        debt=Decimal(100000),
        change_30d=Decimal(1000),
        change_30d_pct=change_30d_pct,
        change_12m=Decimal(20000) if change_12m_pct is not None else None,
        change_12m_pct=change_12m_pct,
    )


@pytest.mark.django_db
def test_monthly_summary_at_the_start_of_the_month():
    with (
        patch.object(notifications, "registry", return_value=[]),
        patch.object(
            notifications,
            "hero_summary",
            return_value=_hero(Decimal("0.2"), Decimal("4.2")),
        ),
    ):
        (event,) = notifications._monthly_summary({}, datetime.date(2026, 11, 2))
    assert event.key == "2026-11"
    lines = event.body.split("\n")
    assert lines[0].startswith("Net worth:")
    assert "(+0.2 %)" in lines[1]
    assert "(+4.2 %)" in lines[2]


@pytest.mark.django_db
def test_monthly_summary_without_history():
    with (
        patch.object(notifications, "registry", return_value=[]),
        patch.object(notifications, "hero_summary", return_value=_hero(None, None)),
    ):
        (event,) = notifications._monthly_summary({}, datetime.date(2026, 11, 1))
    assert len(event.body.split("\n")) == 1


def test_no_monthly_summary_later_in_the_month():
    assert list(notifications._monthly_summary({}, datetime.date(2026, 11, 8))) == []
