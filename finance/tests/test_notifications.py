"""Tests for the notification types of the finance app."""

import datetime
from decimal import Decimal
from unittest.mock import patch

import pytest
from moneyed import Money

from base.services.dashboard import RegistryGroup, RegistryRow
from finance import notifications
from finance.models.investment_account import InvestmentAccount
from finance.models.saving_account import SavingAccount, SavingAccountType

TODAY = datetime.date(2026, 10, 28)


def _row(name, value, old_value):
    return RegistryRow(
        kind="saving",
        name=name,
        sub="",
        holder="",
        value=Decimal(value),
        old_value=Decimal(old_value),
        url=f"/finance/saving/{name}/",
    )


def test_account_drops():
    group = RegistryGroup(kind="saving", net_total=Decimal(0))
    group.rows = [
        _row("dropped", 90, 100),
        _row("stable", 99, 100),
        _row("negative", -50, -10),
        _row("new", 100, 0),
    ]
    with (
        patch.object(notifications, "registry", return_value=[group]),
        patch.object(notifications, "default_currency", return_value="EUR"),
    ):
        events = list(notifications._account_drops({"threshold": 5}, TODAY))
    assert [e.title for e in events] == ["dropped dropped 10.0 % in 30 days"]
    assert events[0].key == "/finance/saving/dropped/"


def _book(code, amount):
    return SavingAccount.objects.create(
        account_type=SavingAccountType.objects.get_or_create(
            code=code, defaults={"name": code}
        )[0],
        name=code,
        institution="Bank",
        opening_value=Money(amount, "EUR"),
        opening_date=TODAY - datetime.timedelta(days=100),
    )


@pytest.mark.django_db
def test_ceilings():
    SavingAccount.objects.update(is_active=False)
    InvestmentAccount.objects.update(is_active=False)
    full = _book("LDDS", 12000)
    near = _book("LA", 22000)
    _book("CPT", 50000)  # no ceiling
    events = {e.key: e for e in notifications._ceilings({"percent": 95}, TODAY)}
    assert set(events) == {f"SavingAccount:{full.pk}", f"SavingAccount:{near.pk}"}
    assert events[f"SavingAccount:{full.pk}"].title == (
        "LDDS at Bank reached its deposit ceiling"
    )
    assert events[f"SavingAccount:{near.pk}"].title == (
        "LA at Bank is at 96 % of its deposit ceiling"
    )
    assert events[f"SavingAccount:{near.pk}"].url == f"/finance/saving/{near.pk}/"
    assert len(list(notifications._ceilings({"percent": 100}, TODAY))) == 1
