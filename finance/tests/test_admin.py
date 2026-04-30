"""Tests for finance admin classes and custom bulk-update actions."""

import datetime
from decimal import Decimal

import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory
from django.urls import reverse
from moneyed import Money

from finance.admin import (
    InvestmentAccountHoldingHistoryAdmin,
    SavingAccountValueAdmin,
)
from finance.models.investment_account import (
    InvestmentAccountHolding,
    InvestmentAccountHoldingHistory,
)
from finance.models.saving_account import SavingAccountValue

# ---------------------------------------------------------------------------
# Admin changelist smoke tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_investment_account_admin_changelist(admin_client):
    """Admin changelist for InvestmentAccount returns 200."""
    url = reverse("admin:finance_investmentaccount_changelist")
    response = admin_client.get(url)
    assert response.status_code == 200


@pytest.mark.django_db
def test_saving_account_admin_changelist(admin_client):
    """Admin changelist for SavingAccount returns 200."""
    url = reverse("admin:finance_savingaccount_changelist")
    response = admin_client.get(url)
    assert response.status_code == 200


@pytest.mark.django_db
def test_saving_account_deposit_admin_changelist(admin_client):
    """Admin changelist for SavingAccountDeposit returns 200."""
    url = reverse("admin:finance_savingaccountdeposit_changelist")
    response = admin_client.get(url)
    assert response.status_code == 200


@pytest.mark.django_db
def test_investment_account_deposit_admin_changelist(admin_client):
    """Admin changelist for InvestmentAccountDeposit returns 200."""
    url = reverse("admin:finance_investmentaccountdeposit_changelist")
    response = admin_client.get(url)
    assert response.status_code == 200


@pytest.mark.django_db
def test_investment_holding_history_admin_changelist(admin_client):
    """Admin changelist for InvestmentAccountHoldingHistory returns 200."""
    url = reverse("admin:finance_investmentaccountholdinghistory_changelist")
    response = admin_client.get(url)
    assert response.status_code == 200


@pytest.mark.django_db
def test_saving_account_value_admin_changelist(admin_client):
    """Admin changelist for SavingAccountValue returns 200."""
    url = reverse("admin:finance_savingaccountvalue_changelist")
    response = admin_client.get(url)
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# bulk_update_valuation_date action — intermediate form (no "apply")
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_bulk_update_valuation_date_shows_intermediate_form(
    admin_client, active_investment_account
):
    """Selecting bulk_update_valuation_date without 'apply' renders the intermediate page."""
    holding = InvestmentAccountHolding.objects.create(
        account=active_investment_account,
        name="Test Holding",
        is_active=True,
        initial_value=Money(Decimal("100"), "EUR"),
    )
    history = InvestmentAccountHoldingHistory.objects.create(
        holding=holding,
        value=Money(Decimal("200"), "EUR"),
        quantity=Decimal("2"),
        valuation_date=datetime.datetime(2025, 1, 15, 10, 0, 0),
    )

    url = reverse("admin:finance_investmentaccountholdinghistory_changelist")
    response = admin_client.post(
        url,
        {
            "action": "bulk_update_valuation_date",
            "_selected_action": [str(history.pk)],
        },
    )
    # Should render the intermediate template (200), not redirect (302)
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# bulk_update_valuation_date action — apply step
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_bulk_update_valuation_date_apply_updates_records(
    admin_client, active_investment_account
):
    """Selecting bulk_update_valuation_date with 'apply' updates the valuation date."""
    holding = InvestmentAccountHolding.objects.create(
        account=active_investment_account,
        name="Holding for Update",
        is_active=True,
        initial_value=Money(Decimal("100"), "EUR"),
    )
    history = InvestmentAccountHoldingHistory.objects.create(
        holding=holding,
        value=Money(Decimal("300"), "EUR"),
        quantity=Decimal("3"),
        valuation_date=datetime.datetime(2025, 2, 1, 10, 0, 0),
    )

    new_date = "2025-06-01"
    url = reverse("admin:finance_investmentaccountholdinghistory_changelist")
    response = admin_client.post(
        url,
        {
            "action": "bulk_update_valuation_date",
            "_selected_action": [str(history.pk)],
            "apply": "1",
            "new_valuation_date": new_date,
        },
    )
    # Should redirect after apply
    assert response.status_code in (200, 302)
    history.refresh_from_db()
    assert str(history.valuation_date.date()) == new_date or str(
        history.valuation_date
    ).startswith(new_date)


# ---------------------------------------------------------------------------
# bulk_update_value_date action — intermediate form (no "apply")
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_bulk_update_value_date_shows_intermediate_form(
    admin_client, active_saving_account
):
    """Selecting bulk_update_value_date without 'apply' renders the intermediate page."""
    value = SavingAccountValue.objects.create(
        account=active_saving_account,
        value=Money(Decimal("1500"), "EUR"),
        value_date=datetime.datetime(2025, 3, 10, 10, 0, 0),
    )

    url = reverse("admin:finance_savingaccountvalue_changelist")
    response = admin_client.post(
        url,
        {
            "action": "bulk_update_value_date",
            "_selected_action": [str(value.pk)],
        },
    )
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# bulk_update_value_date action — apply step
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_bulk_update_value_date_apply_updates_records(
    admin_client, active_saving_account
):
    """Selecting bulk_update_value_date with 'apply' updates the value date."""
    value = SavingAccountValue.objects.create(
        account=active_saving_account,
        value=Money(Decimal("2000"), "EUR"),
        value_date=datetime.datetime(2025, 4, 1, 10, 0, 0),
    )

    new_date = "2025-07-01"
    url = reverse("admin:finance_savingaccountvalue_changelist")
    response = admin_client.post(
        url,
        {
            "action": "bulk_update_value_date",
            "_selected_action": [str(value.pk)],
            "apply": "1",
            "new_value_date": new_date,
        },
    )
    assert response.status_code in (200, 302)
    value.refresh_from_db()
    assert str(value.value_date.date()) == new_date or str(value.value_date).startswith(
        new_date
    )


# ---------------------------------------------------------------------------
# Direct unit tests for admin action methods via RequestFactory
# ---------------------------------------------------------------------------


@pytest.fixture
def _make_admin_request(admin_user):
    """Helper: build a POST request with message storage attached."""

    def _build(data=None):
        factory = RequestFactory()
        request = factory.post("/admin/", data or {})
        request.user = admin_user
        setattr(request, "session", {})
        messages = FallbackStorage(request)
        setattr(request, "_messages", messages)
        return request

    return _build


@pytest.mark.django_db
def test_bulk_update_valuation_date_direct_apply(
    _make_admin_request, active_investment_account
):
    """Direct call to admin action applies the new date when 'apply' is in POST."""
    holding = InvestmentAccountHolding.objects.create(
        account=active_investment_account,
        name="Direct Holding",
        is_active=True,
        initial_value=Money(Decimal("100"), "EUR"),
    )
    history = InvestmentAccountHoldingHistory.objects.create(
        holding=holding,
        value=Money(Decimal("400"), "EUR"),
        quantity=Decimal("4"),
        valuation_date=datetime.datetime(2025, 1, 1, 12, 0, 0),
    )

    request = _make_admin_request({"apply": "1", "new_valuation_date": "2025-09-15"})
    ma = InvestmentAccountHoldingHistoryAdmin(
        InvestmentAccountHoldingHistory, AdminSite()
    )
    queryset = InvestmentAccountHoldingHistory.objects.filter(pk=history.pk)
    result = ma.bulk_update_valuation_date(request, queryset)

    assert result is None  # action returns None after apply
    history.refresh_from_db()
    assert str(history.valuation_date.date()) == "2025-09-15"


@pytest.mark.django_db
def test_bulk_update_value_date_direct_apply(
    _make_admin_request, active_saving_account
):
    """Direct call to admin action applies the new date when 'apply' is in POST."""
    value = SavingAccountValue.objects.create(
        account=active_saving_account,
        value=Money(Decimal("1000"), "EUR"),
        value_date=datetime.datetime(2025, 1, 1, 12, 0, 0),
    )

    request = _make_admin_request({"apply": "1", "new_value_date": "2025-10-20"})
    ma = SavingAccountValueAdmin(SavingAccountValue, AdminSite())
    queryset = SavingAccountValue.objects.filter(pk=value.pk)
    result = ma.bulk_update_value_date(request, queryset)

    assert result is None
    value.refresh_from_db()
    assert str(value.value_date.date()) == "2025-10-20"


@pytest.mark.django_db
def test_bulk_update_valuation_date_direct_no_apply(
    _make_admin_request, active_investment_account
):
    """Direct call without 'apply' renders the intermediate template."""
    holding = InvestmentAccountHolding.objects.create(
        account=active_investment_account,
        name="No Apply Holding",
        is_active=True,
        initial_value=Money(Decimal("100"), "EUR"),
    )
    history = InvestmentAccountHoldingHistory.objects.create(
        holding=holding,
        value=Money(Decimal("100"), "EUR"),
        quantity=Decimal("1"),
        valuation_date=datetime.datetime(2025, 1, 1, 12, 0, 0),
    )

    request = _make_admin_request({})
    ma = InvestmentAccountHoldingHistoryAdmin(
        InvestmentAccountHoldingHistory, AdminSite()
    )
    queryset = InvestmentAccountHoldingHistory.objects.filter(pk=history.pk)
    result = ma.bulk_update_valuation_date(request, queryset)

    # Should return a TemplateResponse (not None)
    assert result is not None


@pytest.mark.django_db
def test_bulk_update_value_date_direct_no_apply(
    _make_admin_request, active_saving_account
):
    """Direct call without 'apply' renders the intermediate template."""
    value = SavingAccountValue.objects.create(
        account=active_saving_account,
        value=Money(Decimal("500"), "EUR"),
        value_date=datetime.datetime(2025, 2, 1, 12, 0, 0),
    )

    request = _make_admin_request({})
    ma = SavingAccountValueAdmin(SavingAccountValue, AdminSite())
    queryset = SavingAccountValue.objects.filter(pk=value.pk)
    result = ma.bulk_update_value_date(request, queryset)

    assert result is not None
