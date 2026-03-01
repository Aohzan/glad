"""Tests for saving account CRUD views."""

import datetime
from decimal import Decimal

import pytest
from django.contrib.messages import get_messages
from django.urls import reverse
from djmoney.money import Money

from finance.models.saving_account import (
    SavingAccount,
    SavingAccountDeposit,
    SavingAccountType,
    SavingAccountValue,
)


@pytest.fixture
def saving_type():
    """Create a saving account type."""
    return SavingAccountType.objects.create(name="Livret A", code="LA")


@pytest.fixture
def saving_account(saving_type):
    """Create a saving account."""
    return SavingAccount.objects.create(
        account_type=saving_type,
        name="My Livret A",
        owner="Test Owner",
        institution="Test Bank",
        is_active=True,
        opening_value=Money(Decimal("1000.00"), "EUR"),
        opening_date=datetime.date.today() - datetime.timedelta(days=60),
        interest_rate=Decimal("3.00"),
    )


@pytest.fixture
def saving_value(saving_account):
    """Create a saving account value entry."""
    return SavingAccountValue.objects.create(
        account=saving_account,
        value=Money(Decimal("1200.00"), "EUR"),
        value_date=datetime.datetime.now() - datetime.timedelta(days=10),
    )


@pytest.fixture
def saving_deposit(saving_account):
    """Create a saving account deposit."""
    return SavingAccountDeposit.objects.create(
        account=saving_account,
        amount=Money(Decimal("200.00"), "EUR"),
        deposit_date=datetime.datetime.now() - datetime.timedelta(days=5),
        source="Salary",
        update_account_value=False,
    )


# ─── Detail view ──────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestSavingDetail:
    """Tests for the saving account detail view."""

    def test_detail_authenticated(
        self, user_client, saving_account, saving_value, saving_deposit
    ):
        """Detail page renders with account, values, and deposits."""
        url = reverse("finance:saving_detail", kwargs={"pk": saving_account.pk})
        response = user_client.get(url)
        assert response.status_code == 200
        assert response.context["account"] == saving_account
        assert saving_value in response.context["values"]
        assert saving_deposit in response.context["deposits"]

    def test_detail_unauthenticated(self, client, saving_account):
        """Unauthenticated users are redirected."""
        url = reverse("finance:saving_detail", kwargs={"pk": saving_account.pk})
        response = client.get(url)
        assert response.status_code == 302

    def test_detail_nonexistent(self, user_client):
        """Nonexistent account returns 404."""
        url = reverse("finance:saving_detail", kwargs={"pk": 99999})
        response = user_client.get(url)
        assert response.status_code == 404


# ─── Create saving account ───────────────────────────────────────────────────


@pytest.mark.django_db
class TestCreateSaving:
    """Tests for creating a saving account."""

    def test_get_create_form(self, user_client, saving_type):
        """GET returns the create form."""
        url = reverse("finance:new_saving")
        response = user_client.get(url)
        assert response.status_code == 200
        assert "form" in response.context
        assert response.context.get("account") is None

    def test_post_create_valid(self, user_client, saving_type):
        """POST with valid data creates an account and redirects."""
        url = reverse("finance:new_saving")
        data = {
            "account_type": saving_type.pk,
            "name": "New Account",
            "owner": "Owner",
            "institution": "Bank",
            "opening_date": "2025-01-01",
            "interest_rate": "2.50",
            "opening_value_0": "500.00",
            "opening_value_1": "EUR",
            "is_active": True,
        }
        response = user_client.post(url, data)
        assert response.status_code == 302
        assert SavingAccount.objects.filter(name="New Account").exists()
        messages = list(get_messages(response.wsgi_request))
        assert any("created" in str(m).lower() for m in messages)

    def test_post_create_invalid(self, user_client):
        """POST with invalid data re-renders the form."""
        url = reverse("finance:new_saving")
        response = user_client.post(url, {})
        assert response.status_code == 200
        assert response.context["form"].errors


# ─── Edit saving account ─────────────────────────────────────────────────────


@pytest.mark.django_db
class TestEditSaving:
    """Tests for editing a saving account."""

    def test_get_edit_form(self, user_client, saving_account):
        """GET returns the edit form with existing data."""
        url = reverse("finance:edit_saving", kwargs={"pk": saving_account.pk})
        response = user_client.get(url)
        assert response.status_code == 200
        assert response.context["account"] == saving_account

    def test_post_edit_valid(self, user_client, saving_account, saving_type):
        """POST with valid data updates the account."""
        url = reverse("finance:edit_saving", kwargs={"pk": saving_account.pk})
        data = {
            "account_type": saving_type.pk,
            "name": "Updated Name",
            "opening_date": "2025-01-01",
            "interest_rate": "3.50",
            "opening_value_0": "1000.00",
            "opening_value_1": "EUR",
            "is_active": True,
        }
        response = user_client.post(url, data)
        assert response.status_code == 302
        saving_account.refresh_from_db()
        assert saving_account.name == "Updated Name"

    def test_edit_nonexistent(self, user_client):
        """Editing a nonexistent account returns 404."""
        url = reverse("finance:edit_saving", kwargs={"pk": 99999})
        response = user_client.get(url)
        assert response.status_code == 404


# ─── Delete saving account ───────────────────────────────────────────────────


@pytest.mark.django_db
class TestDeleteSaving:
    """Tests for deleting a saving account."""

    def test_post_delete(self, user_client, saving_account):
        """POST deletes the account and redirects to index."""
        url = reverse("finance:delete_saving", kwargs={"pk": saving_account.pk})
        response = user_client.post(url)
        assert response.status_code == 302
        assert not SavingAccount.objects.filter(pk=saving_account.pk).exists()

    def test_get_delete_rejected(self, user_client, saving_account):
        """GET is rejected for delete."""
        url = reverse("finance:delete_saving", kwargs={"pk": saving_account.pk})
        response = user_client.get(url)
        assert response.status_code == 302
        assert SavingAccount.objects.filter(pk=saving_account.pk).exists()


# ─── Value CRUD ───────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestSavingValueCRUD:
    """Tests for saving account value CRUD."""

    def test_get_create_value(self, user_client, saving_account):
        """GET returns value create form."""
        url = reverse(
            "finance:new_saving_value", kwargs={"account_pk": saving_account.pk}
        )
        response = user_client.get(url)
        assert response.status_code == 200
        assert response.context["account"] == saving_account

    def test_post_create_value(self, user_client, saving_account):
        """POST creates a value entry."""
        url = reverse(
            "finance:new_saving_value", kwargs={"account_pk": saving_account.pk}
        )
        data = {
            "value_0": "1500.00",
            "value_1": "EUR",
            "value_date": "2025-06-01T12:00",
        }
        response = user_client.post(url, data)
        assert response.status_code == 302
        assert SavingAccountValue.objects.filter(account=saving_account).exists()

    def test_get_edit_value(self, user_client, saving_account, saving_value):
        """GET returns value edit form with existing data."""
        url = reverse(
            "finance:edit_saving_value",
            kwargs={"account_pk": saving_account.pk, "value_pk": saving_value.pk},
        )
        response = user_client.get(url)
        assert response.status_code == 200
        assert response.context["value"] == saving_value

    def test_post_edit_value(self, user_client, saving_account, saving_value):
        """POST updates the value entry."""
        url = reverse(
            "finance:edit_saving_value",
            kwargs={"account_pk": saving_account.pk, "value_pk": saving_value.pk},
        )
        data = {
            "value_0": "1800.00",
            "value_1": "EUR",
            "value_date": "2025-06-15T14:00",
        }
        response = user_client.post(url, data)
        assert response.status_code == 302
        saving_value.refresh_from_db()
        assert saving_value.value.amount == Decimal("1800.00")

    def test_post_delete_value(self, user_client, saving_account, saving_value):
        """POST deletes the value entry."""
        url = reverse(
            "finance:delete_saving_value",
            kwargs={"account_pk": saving_account.pk, "value_pk": saving_value.pk},
        )
        response = user_client.post(url)
        assert response.status_code == 302
        assert not SavingAccountValue.objects.filter(pk=saving_value.pk).exists()

    def test_get_delete_value_rejected(self, user_client, saving_account, saving_value):
        """GET is rejected for delete."""
        url = reverse(
            "finance:delete_saving_value",
            kwargs={"account_pk": saving_account.pk, "value_pk": saving_value.pk},
        )
        response = user_client.get(url)
        assert response.status_code == 302
        assert SavingAccountValue.objects.filter(pk=saving_value.pk).exists()


# ─── Deposit CRUD ─────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestSavingDepositCRUD:
    """Tests for saving account deposit CRUD."""

    def test_get_create_deposit(self, user_client, saving_account):
        """GET returns deposit create form."""
        url = reverse(
            "finance:new_saving_deposit", kwargs={"account_pk": saving_account.pk}
        )
        response = user_client.get(url)
        assert response.status_code == 200

    def test_post_create_deposit(self, user_client, saving_account):
        """POST creates a deposit."""
        url = reverse(
            "finance:new_saving_deposit", kwargs={"account_pk": saving_account.pk}
        )
        data = {
            "amount_0": "300.00",
            "amount_1": "EUR",
            "deposit_date": "2025-06-01T12:00",
            "source": "Bonus",
            "update_account_value": True,
        }
        response = user_client.post(url, data)
        assert response.status_code == 302
        assert SavingAccountDeposit.objects.filter(
            account=saving_account, source="Bonus"
        ).exists()

    def test_get_edit_deposit(self, user_client, saving_account, saving_deposit):
        """GET returns deposit edit form."""
        url = reverse(
            "finance:edit_saving_deposit",
            kwargs={"account_pk": saving_account.pk, "deposit_pk": saving_deposit.pk},
        )
        response = user_client.get(url)
        assert response.status_code == 200
        assert response.context["deposit"] == saving_deposit

    def test_post_edit_deposit(self, user_client, saving_account, saving_deposit):
        """POST updates the deposit."""
        url = reverse(
            "finance:edit_saving_deposit",
            kwargs={"account_pk": saving_account.pk, "deposit_pk": saving_deposit.pk},
        )
        data = {
            "amount_0": "400.00",
            "amount_1": "EUR",
            "deposit_date": "2025-06-10T10:00",
            "source": "Updated",
        }
        response = user_client.post(url, data)
        assert response.status_code == 302
        saving_deposit.refresh_from_db()
        assert saving_deposit.source == "Updated"

    def test_post_delete_deposit(self, user_client, saving_account, saving_deposit):
        """POST deletes the deposit."""
        url = reverse(
            "finance:delete_saving_deposit",
            kwargs={"account_pk": saving_account.pk, "deposit_pk": saving_deposit.pk},
        )
        response = user_client.post(url)
        assert response.status_code == 302
        assert not SavingAccountDeposit.objects.filter(pk=saving_deposit.pk).exists()

    def test_get_delete_deposit_rejected(
        self, user_client, saving_account, saving_deposit
    ):
        """GET is rejected for delete."""
        url = reverse(
            "finance:delete_saving_deposit",
            kwargs={"account_pk": saving_account.pk, "deposit_pk": saving_deposit.pk},
        )
        response = user_client.get(url)
        assert response.status_code == 302
        assert SavingAccountDeposit.objects.filter(pk=saving_deposit.pk).exists()
