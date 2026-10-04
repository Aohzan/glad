"""Tests for value entries typed as an amount added to the previous value."""

import datetime
from decimal import Decimal

import pytest
from django.urls import reverse
from djmoney.money import Money

from finance.forms import SavingAccountValueForm
from finance.models.investment_account import (
    InvestmentAccount,
    InvestmentAccountCash,
    InvestmentAccountType,
)
from finance.models.other_asset import OtherAsset, OtherAssetValue
from finance.models.saving_account import (
    SavingAccount,
    SavingAccountType,
    SavingAccountValue,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def saving_account():
    """A saving account opened with 1000 € and valued 1100 € on 2025-03-01."""
    account = SavingAccount.objects.create(
        account_type=SavingAccountType.objects.create(name="Livret A", code="LA"),
        opening_value=Money(Decimal(1000), "EUR"),
        opening_date=datetime.date(2025, 1, 1),
    )
    SavingAccountValue.objects.create(
        account=account,
        value=Money(Decimal(1100), "EUR"),
        value_date=datetime.datetime(2025, 3, 1, 12, 0),
    )
    return account


def _new_saving_value(client, account, **data):
    url = reverse("finance:new_saving_value", kwargs={"account_pk": account.pk})
    return client.post(url, {"value_1": "EUR", **data})


class TestSavingValue:
    def test_amount_is_added_to_the_previous_value(self, user_client, saving_account):
        response = _new_saving_value(
            user_client,
            saving_account,
            value_0="",
            amount_to_add="50",
            value_date="2025-04-01T12:00",
        )
        assert response.status_code == 302
        latest = saving_account.values.order_by("-value_date").first()
        assert latest.value == Money(Decimal(1150), "EUR")

    def test_negative_amount_is_subtracted(self, user_client, saving_account):
        _new_saving_value(
            user_client,
            saving_account,
            amount_to_add="-100",
            value_date="2025-04-01T12:00",
        )
        latest = saving_account.values.order_by("-value_date").first()
        assert latest.value == Money(Decimal(1000), "EUR")

    def test_previous_value_is_the_one_at_the_entry_date(
        self, user_client, saving_account
    ):
        """Before any recorded value, the opening value is the base."""
        _new_saving_value(
            user_client,
            saving_account,
            amount_to_add="20",
            value_date="2025-02-01T12:00",
        )
        entry = saving_account.values.get(value_date=datetime.datetime(2025, 2, 1, 12))
        assert entry.value == Money(Decimal(1020), "EUR")

    def test_value_and_amount_together_are_rejected(self, user_client, saving_account):
        response = _new_saving_value(
            user_client,
            saving_account,
            value_0="1200",
            amount_to_add="50",
            value_date="2025-04-01T12:00",
        )
        assert response.status_code == 200
        assert "amount_to_add" in response.context["form"].errors
        assert saving_account.values.count() == 1

    def test_value_or_amount_is_required(self, user_client, saving_account):
        response = _new_saving_value(
            user_client, saving_account, value_date="2025-04-01T12:00"
        )
        assert response.status_code == 200
        assert "value" in response.context["form"].errors

    def test_missing_date_reports_the_date_only(self, user_client, saving_account):
        response = _new_saving_value(user_client, saving_account, amount_to_add="50")
        errors = response.context["form"].errors
        assert "value_date" in errors
        assert "value" not in errors

    def test_create_page_shows_the_amount_field(self, user_client, saving_account):
        url = reverse(
            "finance:new_saving_value", kwargs={"account_pk": saving_account.pk}
        )
        assert 'name="amount_to_add"' in user_client.get(url).content.decode()

    def test_edit_form_has_no_amount_field(self, user_client, saving_account):
        value = saving_account.values.get()
        url = reverse(
            "finance:edit_saving_value",
            kwargs={"account_pk": saving_account.pk, "value_pk": value.pk},
        )
        response = user_client.get(url)
        assert "amount_to_add" not in response.context["form"].fields
        assert response.context["form"].fields["value"].required

    def test_form_without_parent_has_no_amount_field(self):
        assert "amount_to_add" not in SavingAccountValueForm().fields


def test_investment_cash_amount_is_added_to_the_cash(user_client):
    account = InvestmentAccount.objects.create(
        account_type=InvestmentAccountType.objects.create(name="PEA", code="PEA"),
        opening_cash_value=Money(Decimal(5000), "EUR"),
        opening_date=datetime.date(2025, 1, 1),
    )
    InvestmentAccountCash.objects.create(
        account=account,
        value=Money(Decimal(300), "EUR"),
        value_date=datetime.date(2025, 3, 1),
    )
    url = reverse("finance:new_investment_cash", kwargs={"account_pk": account.pk})
    response = user_client.post(
        url, {"value_1": "EUR", "amount_to_add": "200", "value_date": "2025-04-01"}
    )
    assert response.status_code == 302
    entry = account.cash_values.get(value_date=datetime.date(2025, 4, 1))
    assert entry.value == Money(Decimal(500), "EUR")


def test_other_asset_amount_is_added_to_the_value(user_client):
    asset = OtherAsset.objects.create(
        name="Gold coins",
        category=OtherAsset.Category.PRECIOUS_METALS,
        acquisition_date=datetime.date(2020, 1, 1),
        acquisition_value=Money(Decimal(1000), "EUR"),
    )
    OtherAssetValue.objects.create(
        asset=asset, value=Money(1100, "EUR"), value_date=datetime.date(2021, 1, 1)
    )
    url = reverse("finance:new_other_asset_value", args=[asset.pk])
    response = user_client.post(
        url, {"value_1": "EUR", "amount_to_add": "-150", "value_date": "2022-01-01"}
    )
    assert response.status_code == 302
    entry = asset.values.get(value_date=datetime.date(2022, 1, 1))
    assert entry.value == Money(Decimal(950), "EUR")
