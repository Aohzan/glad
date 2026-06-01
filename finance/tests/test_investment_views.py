"""Tests for investment account CRUD views."""

import datetime
from decimal import Decimal

import pytest
from django.contrib.messages import get_messages
from django.urls import reverse
from djmoney.money import Money

from finance.models.investment_account import (
    InvestmentAccount,
    InvestmentAccountDeposit,
    InvestmentAccountHolding,
    InvestmentAccountHoldingHistory,
    InvestmentAccountType,
)


@pytest.fixture
def investment_type():
    """Create an investment account type."""
    return InvestmentAccountType.objects.create(name="PEA", code="PEA")


@pytest.fixture
def investment_account(investment_type):
    """Create an investment account."""
    return InvestmentAccount.objects.create(
        account_type=investment_type,
        name="My PEA",
        owner="Test Owner",
        institution="Test Broker",
        is_active=True,
        opening_cash_value=Money(Decimal("5000.00"), "EUR"),
        opening_date=datetime.date.today() - datetime.timedelta(days=90),
    )


@pytest.fixture
def holding(investment_account):
    """Create an investment holding."""
    return InvestmentAccountHolding.objects.create(
        account=investment_account,
        name="World ETF",
        code="CW8",
        isin="LU1681043599",
        fees=Decimal("0.38"),
        is_active=True,
        initial_quantity=Decimal("10.0000"),
        initial_value=Money(Decimal("300.00"), "EUR"),
        initial_valuation_date=datetime.date.today() - datetime.timedelta(days=60),
    )


@pytest.fixture
def holding_history(holding):
    """Create a holding history entry."""
    return InvestmentAccountHoldingHistory.objects.create(
        holding=holding,
        value=Money(Decimal("350.00"), "EUR"),
        valuation_date=datetime.datetime.now() - datetime.timedelta(days=5),
        quantity=Decimal("12.0000"),
    )


@pytest.fixture
def investment_deposit(investment_account):
    """Create an investment deposit."""
    return InvestmentAccountDeposit.objects.create(
        account=investment_account,
        amount=Money(Decimal("1000.00"), "EUR"),
        deposit_date=datetime.date.today() - datetime.timedelta(days=10),
        source="Transfer",
        update_account_cash=False,
    )


# ─── Detail view ──────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestInvestmentDetail:
    """Tests for the investment account detail view."""

    def test_detail_authenticated(
        self, user_client, investment_account, holding, investment_deposit
    ):
        """Detail page renders with account, holdings, and deposits."""
        url = reverse("finance:investment_detail", kwargs={"pk": investment_account.pk})
        response = user_client.get(url)
        assert response.status_code == 200
        assert response.context["account"] == investment_account
        assert holding in response.context["holdings"]
        assert investment_deposit in response.context["deposits"]

    def test_detail_unauthenticated(self, client, investment_account):
        """Unauthenticated users are redirected."""
        url = reverse("finance:investment_detail", kwargs={"pk": investment_account.pk})
        response = client.get(url)
        assert response.status_code == 302

    def test_detail_nonexistent(self, user_client):
        """Nonexistent account returns 404."""
        url = reverse("finance:investment_detail", kwargs={"pk": 99999})
        response = user_client.get(url)
        assert response.status_code == 404


# ─── Create investment account ────────────────────────────────────────────────


@pytest.mark.django_db
class TestCreateInvestment:
    """Tests for creating an investment account."""

    def test_get_create_form(self, user_client, investment_type):
        """GET returns the create form."""
        url = reverse("finance:new_investment")
        response = user_client.get(url)
        assert response.status_code == 200
        assert "form" in response.context

    def test_post_create_valid(self, user_client, investment_type):
        """POST with valid data creates an account and redirects."""
        url = reverse("finance:new_investment")
        data = {
            "account_type": investment_type.pk,
            "name": "New Investment",
            "owner": "Owner",
            "institution": "Broker",
            "opening_date": "2025-01-01",
            "opening_cash_value_0": "2000.00",
            "opening_cash_value_1": "EUR",
            "is_active": True,
        }
        response = user_client.post(url, data)
        assert response.status_code == 302
        assert InvestmentAccount.objects.filter(name="New Investment").exists()
        messages = list(get_messages(response.wsgi_request))
        assert any("created" in str(m).lower() for m in messages)

    def test_post_create_invalid(self, user_client):
        """POST with invalid data re-renders the form."""
        url = reverse("finance:new_investment")
        response = user_client.post(url, {})
        assert response.status_code == 200
        assert response.context["form"].errors


# ─── Edit investment account ──────────────────────────────────────────────────


@pytest.mark.django_db
class TestEditInvestment:
    """Tests for editing an investment account."""

    def test_get_edit_form(self, user_client, investment_account):
        """GET returns the edit form with existing data."""
        url = reverse("finance:edit_investment", kwargs={"pk": investment_account.pk})
        response = user_client.get(url)
        assert response.status_code == 200
        assert response.context["account"] == investment_account

    def test_post_edit_valid(self, user_client, investment_account, investment_type):
        """POST with valid data updates the account."""
        url = reverse("finance:edit_investment", kwargs={"pk": investment_account.pk})
        data = {
            "account_type": investment_type.pk,
            "name": "Updated PEA",
            "opening_date": "2025-01-01",
            "opening_cash_value_0": "5000.00",
            "opening_cash_value_1": "EUR",
            "is_active": True,
        }
        response = user_client.post(url, data)
        assert response.status_code == 302
        investment_account.refresh_from_db()
        assert investment_account.name == "Updated PEA"

    def test_edit_nonexistent(self, user_client):
        """Editing a nonexistent account returns 404."""
        url = reverse("finance:edit_investment", kwargs={"pk": 99999})
        response = user_client.get(url)
        assert response.status_code == 404


# ─── Delete investment account ────────────────────────────────────────────────


@pytest.mark.django_db
class TestDeleteInvestment:
    """Tests for deleting an investment account."""

    def test_post_delete(self, user_client, investment_account):
        """POST deletes the account and redirects to index."""
        url = reverse("finance:delete_investment", kwargs={"pk": investment_account.pk})
        response = user_client.post(url)
        assert response.status_code == 302
        assert not InvestmentAccount.objects.filter(pk=investment_account.pk).exists()

    def test_get_delete_rejected(self, user_client, investment_account):
        """GET is rejected for delete."""
        url = reverse("finance:delete_investment", kwargs={"pk": investment_account.pk})
        response = user_client.get(url)
        assert response.status_code == 302
        assert InvestmentAccount.objects.filter(pk=investment_account.pk).exists()


# ─── Holding CRUD ─────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestHoldingCRUD:
    """Tests for investment holding CRUD."""

    def test_get_create_holding(self, user_client, investment_account):
        """GET returns holding create form."""
        url = reverse(
            "finance:new_holding", kwargs={"account_pk": investment_account.pk}
        )
        response = user_client.get(url)
        assert response.status_code == 200
        assert response.context["account"] == investment_account

    def test_post_create_holding(self, user_client, investment_account):
        """POST creates a holding."""
        url = reverse(
            "finance:new_holding", kwargs={"account_pk": investment_account.pk}
        )
        data = {
            "name": "S&P 500 ETF",
            "code": "SP5",
            "fees": "0.15",
            "is_active": True,
            "initial_quantity": "5.0000",
            "initial_value_0": "400.00",
            "initial_value_1": "EUR",
            "initial_valuation_date": "2025-03-01",
        }
        response = user_client.post(url, data)
        assert response.status_code == 302
        assert InvestmentAccountHolding.objects.filter(
            account=investment_account, code="SP5"
        ).exists()

    def test_get_edit_holding(self, user_client, investment_account, holding):
        """GET returns holding edit form."""
        url = reverse(
            "finance:edit_holding",
            kwargs={"account_pk": investment_account.pk, "holding_pk": holding.pk},
        )
        response = user_client.get(url)
        assert response.status_code == 200
        assert response.context["holding"] == holding

    def test_post_edit_holding(self, user_client, investment_account, holding):
        """POST updates the holding."""
        url = reverse(
            "finance:edit_holding",
            kwargs={"account_pk": investment_account.pk, "holding_pk": holding.pk},
        )
        data = {
            "name": "Updated ETF",
            "code": "CW8",
            "fees": "0.38",
            "is_active": True,
            "initial_quantity": "10.0000",
            "initial_value_0": "300.00",
            "initial_value_1": "EUR",
            "initial_valuation_date": str(holding.initial_valuation_date),
        }
        response = user_client.post(url, data)
        assert response.status_code == 302
        holding.refresh_from_db()
        assert holding.name == "Updated ETF"

    def test_post_delete_holding(self, user_client, investment_account, holding):
        """POST deletes the holding."""
        url = reverse(
            "finance:delete_holding",
            kwargs={"account_pk": investment_account.pk, "holding_pk": holding.pk},
        )
        response = user_client.post(url)
        assert response.status_code == 302
        assert not InvestmentAccountHolding.objects.filter(pk=holding.pk).exists()

    def test_get_delete_holding_rejected(
        self, user_client, investment_account, holding
    ):
        """GET is rejected for delete."""
        url = reverse(
            "finance:delete_holding",
            kwargs={"account_pk": investment_account.pk, "holding_pk": holding.pk},
        )
        response = user_client.get(url)
        assert response.status_code == 302
        assert InvestmentAccountHolding.objects.filter(pk=holding.pk).exists()


# ─── Investment deposit CRUD ─────────────────────────────────────────────────


@pytest.mark.django_db
class TestInvestmentDepositCRUD:
    """Tests for investment account deposit CRUD."""

    def test_get_create_deposit(self, user_client, investment_account):
        """GET returns deposit create form."""
        url = reverse(
            "finance:new_investment_deposit",
            kwargs={"account_pk": investment_account.pk},
        )
        response = user_client.get(url)
        assert response.status_code == 200

    def test_post_create_deposit(self, user_client, investment_account):
        """POST creates a deposit."""
        url = reverse(
            "finance:new_investment_deposit",
            kwargs={"account_pk": investment_account.pk},
        )
        data = {
            "amount_0": "500.00",
            "amount_1": "EUR",
            "deposit_date": "2025-06-01",
            "source": "Bonus",
            "update_account_cash": True,
        }
        response = user_client.post(url, data)
        assert response.status_code == 302
        assert InvestmentAccountDeposit.objects.filter(
            account=investment_account, source="Bonus"
        ).exists()

    def test_post_edit_deposit(
        self, user_client, investment_account, investment_deposit
    ):
        """POST updates the deposit."""
        url = reverse(
            "finance:edit_investment_deposit",
            kwargs={
                "account_pk": investment_account.pk,
                "deposit_pk": investment_deposit.pk,
            },
        )
        data = {
            "amount_0": "1500.00",
            "amount_1": "EUR",
            "deposit_date": "2025-06-15",
            "source": "Updated",
        }
        response = user_client.post(url, data)
        assert response.status_code == 302
        investment_deposit.refresh_from_db()
        assert investment_deposit.source == "Updated"

    def test_post_delete_deposit(
        self, user_client, investment_account, investment_deposit
    ):
        """POST deletes the deposit."""
        url = reverse(
            "finance:delete_investment_deposit",
            kwargs={
                "account_pk": investment_account.pk,
                "deposit_pk": investment_deposit.pk,
            },
        )
        response = user_client.post(url)
        assert response.status_code == 302
        assert not InvestmentAccountDeposit.objects.filter(
            pk=investment_deposit.pk
        ).exists()


# ─── Holding history CRUD ────────────────────────────────────────────────────


@pytest.mark.django_db
class TestHoldingHistoryCRUD:
    """Tests for investment holding history CRUD."""

    def test_get_create_history(self, user_client, investment_account, holding):
        """GET returns history create form."""
        url = reverse(
            "finance:new_holding_history",
            kwargs={"account_pk": investment_account.pk, "holding_pk": holding.pk},
        )
        response = user_client.get(url)
        assert response.status_code == 200
        assert response.context["holding"] == holding
        assert response.context["account"] == investment_account

    def test_post_create_history(self, user_client, investment_account, holding):
        """POST creates a history entry."""
        url = reverse(
            "finance:new_holding_history",
            kwargs={"account_pk": investment_account.pk, "holding_pk": holding.pk},
        )
        data = {
            "value_0": "400.00",
            "value_1": "EUR",
            "valuation_date": "2025-06-01T12:00",
            "quantity": "15.0000",
        }
        response = user_client.post(url, data)
        assert response.status_code == 302
        assert InvestmentAccountHoldingHistory.objects.filter(holding=holding).exists()

    def test_get_edit_history(
        self, user_client, investment_account, holding, holding_history
    ):
        """GET returns history edit form."""
        url = reverse(
            "finance:edit_holding_history",
            kwargs={
                "account_pk": investment_account.pk,
                "holding_pk": holding.pk,
                "history_pk": holding_history.pk,
            },
        )
        response = user_client.get(url)
        assert response.status_code == 200
        assert response.context["history"] == holding_history

    def test_post_edit_history(
        self, user_client, investment_account, holding, holding_history
    ):
        """POST updates the history entry."""
        url = reverse(
            "finance:edit_holding_history",
            kwargs={
                "account_pk": investment_account.pk,
                "holding_pk": holding.pk,
                "history_pk": holding_history.pk,
            },
        )
        data = {
            "value_0": "500.00",
            "value_1": "EUR",
            "valuation_date": "2025-06-15T14:00",
            "quantity": "20.0000",
        }
        response = user_client.post(url, data)
        assert response.status_code == 302
        holding_history.refresh_from_db()
        assert holding_history.value.amount == Decimal("500.00")

    def test_post_delete_history(
        self, user_client, investment_account, holding, holding_history
    ):
        """POST deletes the history entry."""
        url = reverse(
            "finance:delete_holding_history",
            kwargs={
                "account_pk": investment_account.pk,
                "holding_pk": holding.pk,
                "history_pk": holding_history.pk,
            },
        )
        response = user_client.post(url)
        assert response.status_code == 302
        assert not InvestmentAccountHoldingHistory.objects.filter(
            pk=holding_history.pk
        ).exists()

    def test_get_delete_history_rejected(
        self, user_client, investment_account, holding, holding_history
    ):
        """GET is rejected for delete."""
        url = reverse(
            "finance:delete_holding_history",
            kwargs={
                "account_pk": investment_account.pk,
                "holding_pk": holding.pk,
                "history_pk": holding_history.pk,
            },
        )
        response = user_client.get(url)
        assert response.status_code == 302
        assert InvestmentAccountHoldingHistory.objects.filter(
            pk=holding_history.pk
        ).exists()

    def test_create_history_nonexistent_holding(self, user_client, investment_account):
        """Creating history for nonexistent holding returns 404."""
        url = reverse(
            "finance:new_holding_history",
            kwargs={"account_pk": investment_account.pk, "holding_pk": 99999},
        )
        response = user_client.get(url)
        assert response.status_code == 404
