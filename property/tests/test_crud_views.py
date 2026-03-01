"""Tests for property/views/crud_views.py."""

import datetime
from decimal import Decimal

import pytest
from django.contrib.messages import get_messages
from django.urls import reverse
from moneyed import Money

from property.models import (
    Lease,
    ManagementMandate,
    Property,
    PropertyLedgerEntry,
    PropertyValue,
)


@pytest.fixture
def property_obj():
    return Property.objects.create(
        name="CRUD Test Property",
        property_type=Property.APARTMENT,
        buying_value=Money(200000, "EUR"),
        buying_date=datetime.date(2020, 1, 1),
    )


@pytest.fixture
def ledger_entry(property_obj):
    return PropertyLedgerEntry.objects.create(
        property=property_obj,
        flow_type=PropertyLedgerEntry.FlowType.INCOME,
        management_category=PropertyLedgerEntry.ManagementCategory.RENT_COLLECTED,
        amount=Money(Decimal("1200.00"), "EUR"),
        entry_date=datetime.date(2023, 3, 1),
        description="March rent",
    )


@pytest.fixture
def lease(property_obj):
    return Lease.objects.create(
        property=property_obj,
        first_name="Jean",
        last_name="Dupont",
        lease_type=Lease.LeaseType.FURNISHED,
        status=Lease.Status.ACTIVE,
        start_date=datetime.date(2022, 1, 1),
        rent_amount=Money(Decimal("800.00"), "EUR"),
    )


@pytest.fixture
def valuation(property_obj):
    return PropertyValue.objects.create(
        property=property_obj,
        value=Money(220000, "EUR"),
        valuation_date=datetime.date(2023, 1, 1),
    )


@pytest.fixture
def mandate(property_obj):
    return ManagementMandate.objects.create(
        property=property_obj,
        manager_name="Test Manager",
        start_date=datetime.date(2022, 1, 1),
        fee_percentage=Decimal("8.0"),
    )


# ─── Ledger Entry CRUD ────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestEditLedgerEntry:
    def test_get_edit_entry(self, user_client, property_obj, ledger_entry):
        url = reverse(
            "property:edit_entry",
            kwargs={
                "property_pk": property_obj.pk,
                "entry_pk": ledger_entry.pk,
            },
        )
        response = user_client.get(url)
        assert response.status_code == 200
        assert "form" in response.context

    def test_post_edit_entry_valid(self, user_client, property_obj, ledger_entry):
        url = reverse(
            "property:edit_entry",
            kwargs={
                "property_pk": property_obj.pk,
                "entry_pk": ledger_entry.pk,
            },
        )
        data = {
            "flow_type": PropertyLedgerEntry.FlowType.INCOME,
            "management_category": PropertyLedgerEntry.ManagementCategory.RENT_COLLECTED,
            "amount_0": "1300.00",
            "amount_1": "EUR",
            "entry_date": "2023-03-01",
            "description": "Updated rent",
            "recurrence_type": PropertyLedgerEntry.RecurrenceType.NONE,
        }
        response = user_client.post(url, data)
        assert response.status_code == 302
        ledger_entry.refresh_from_db()
        assert ledger_entry.amount.amount == Decimal("1300.00")

    def test_post_edit_entry_invalid(self, user_client, property_obj, ledger_entry):
        url = reverse(
            "property:edit_entry",
            kwargs={
                "property_pk": property_obj.pk,
                "entry_pk": ledger_entry.pk,
            },
        )
        data = {
            "flow_type": PropertyLedgerEntry.FlowType.INCOME,
            "management_category": PropertyLedgerEntry.ManagementCategory.RENT_COLLECTED,
            "amount": "-100.00",  # Invalid: negative
            "amount_currency": "EUR",
            "entry_date": "2023-03-01",
            "recurrence_type": PropertyLedgerEntry.RecurrenceType.NONE,
        }
        response = user_client.post(url, data)
        assert response.status_code == 200

    def test_edit_entry_nonexistent_property_redirects(self, user_client, ledger_entry):
        url = reverse(
            "property:edit_entry",
            kwargs={
                "property_pk": 99999,
                "entry_pk": ledger_entry.pk,
            },
        )
        response = user_client.get(url)
        assert response.status_code == 302

    def test_edit_entry_nonexistent_entry_redirects(self, user_client, property_obj):
        url = reverse(
            "property:edit_entry",
            kwargs={
                "property_pk": property_obj.pk,
                "entry_pk": 99999,
            },
        )
        response = user_client.get(url)
        assert response.status_code == 302


@pytest.mark.django_db
class TestDeleteLedgerEntry:
    def test_delete_entry_post(self, user_client, property_obj, ledger_entry):
        entry_pk = ledger_entry.pk
        url = reverse(
            "property:delete_entry",
            kwargs={
                "property_pk": property_obj.pk,
                "entry_pk": entry_pk,
            },
        )
        response = user_client.post(url)
        assert response.status_code == 302
        assert not PropertyLedgerEntry.objects.filter(pk=entry_pk).exists()
        messages = list(get_messages(response.wsgi_request))
        assert any("deleted" in str(m).lower() for m in messages)

    def test_delete_entry_get_returns_error(
        self, user_client, property_obj, ledger_entry
    ):
        url = reverse(
            "property:delete_entry",
            kwargs={
                "property_pk": property_obj.pk,
                "entry_pk": ledger_entry.pk,
            },
        )
        response = user_client.get(url)
        assert response.status_code == 302
        assert PropertyLedgerEntry.objects.filter(pk=ledger_entry.pk).exists()

    def test_delete_entry_nonexistent_property_redirects(
        self, user_client, ledger_entry
    ):
        url = reverse(
            "property:delete_entry",
            kwargs={
                "property_pk": 99999,
                "entry_pk": ledger_entry.pk,
            },
        )
        response = user_client.post(url)
        assert response.status_code == 302

    def test_delete_entry_nonexistent_entry_redirects(self, user_client, property_obj):
        url = reverse(
            "property:delete_entry",
            kwargs={
                "property_pk": property_obj.pk,
                "entry_pk": 99999,
            },
        )
        response = user_client.post(url)
        assert response.status_code == 302


# ─── Property Valuation CRUD ──────────────────────────────────────────────────


@pytest.mark.django_db
class TestDeletePropertyValuation:
    def test_delete_valuation_post(self, user_client, property_obj, valuation):
        valuation_pk = valuation.pk
        url = reverse(
            "property:delete_valuation",
            kwargs={
                "property_pk": property_obj.pk,
                "valuation_pk": valuation_pk,
            },
        )
        response = user_client.post(url)
        assert response.status_code == 302
        assert not PropertyValue.objects.filter(pk=valuation_pk).exists()

    def test_delete_valuation_get_returns_redirect(
        self, user_client, property_obj, valuation
    ):
        url = reverse(
            "property:delete_valuation",
            kwargs={
                "property_pk": property_obj.pk,
                "valuation_pk": valuation.pk,
            },
        )
        response = user_client.get(url)
        assert response.status_code == 302
        assert PropertyValue.objects.filter(pk=valuation.pk).exists()

    def test_delete_valuation_nonexistent_property_redirects(
        self, user_client, valuation
    ):
        url = reverse(
            "property:delete_valuation",
            kwargs={
                "property_pk": 99999,
                "valuation_pk": valuation.pk,
            },
        )
        response = user_client.post(url)
        assert response.status_code == 302

    def test_delete_valuation_nonexistent_valuation_redirects(
        self, user_client, property_obj
    ):
        url = reverse(
            "property:delete_valuation",
            kwargs={
                "property_pk": property_obj.pk,
                "valuation_pk": 99999,
            },
        )
        response = user_client.post(url)
        assert response.status_code == 302


# ─── Lease CRUD ───────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestEditLease:
    def test_get_new_lease(self, user_client, property_obj):
        url = reverse("property:new_lease", kwargs={"property_pk": property_obj.pk})
        response = user_client.get(url)
        assert response.status_code == 200
        assert "form" in response.context

    def test_get_edit_existing_lease(self, user_client, property_obj, lease):
        url = reverse(
            "property:edit_lease",
            kwargs={
                "property_pk": property_obj.pk,
                "lease_pk": lease.pk,
            },
        )
        response = user_client.get(url)
        assert response.status_code == 200
        assert "form" in response.context

    def test_post_create_lease_valid(self, user_client, property_obj):
        url = reverse("property:new_lease", kwargs={"property_pk": property_obj.pk})
        data = {
            "first_name": "Marie",
            "last_name": "Curie",
            "lease_type": Lease.LeaseType.FURNISHED,
            "status": Lease.Status.ACTIVE,
            "start_date": "2023-01-01",
            "rent_amount_0": "900.00",
            "rent_amount_1": "EUR",
            "charges_amount_0": "50.00",
            "charges_amount_1": "EUR",
            "deposit_amount_0": "1800.00",
            "deposit_amount_1": "EUR",
            "periodicity": Lease.Periodicity.MONTHLY,
        }
        response = user_client.post(url, data)
        assert response.status_code == 302
        assert Lease.objects.filter(last_name="Curie", property=property_obj).exists()

    def test_post_edit_lease_invalid(self, user_client, property_obj, lease):
        url = reverse(
            "property:edit_lease",
            kwargs={
                "property_pk": property_obj.pk,
                "lease_pk": lease.pk,
            },
        )
        data = {
            "last_name": "",  # Required
            "lease_type": Lease.LeaseType.FURNISHED,
            "status": Lease.Status.ACTIVE,
            "start_date": "2023-01-01",
            "rent_amount": "900.00",
            "rent_amount_currency": "EUR",
        }
        response = user_client.post(url, data)
        assert response.status_code == 200


@pytest.mark.django_db
class TestDeleteLease:
    def test_delete_lease_post(self, user_client, property_obj, lease):
        lease_pk = lease.pk
        url = reverse(
            "property:delete_lease",
            kwargs={
                "property_pk": property_obj.pk,
                "lease_pk": lease_pk,
            },
        )
        response = user_client.post(url)
        assert response.status_code == 302
        assert not Lease.objects.filter(pk=lease_pk).exists()

    def test_delete_lease_get_returns_redirect(self, user_client, property_obj, lease):
        url = reverse(
            "property:delete_lease",
            kwargs={
                "property_pk": property_obj.pk,
                "lease_pk": lease.pk,
            },
        )
        response = user_client.get(url)
        assert response.status_code == 302
        assert Lease.objects.filter(pk=lease.pk).exists()


# ─── Mandate CRUD ─────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestEditMandate:
    def test_get_new_mandate(self, user_client, property_obj):
        url = reverse("property:new_mandate", kwargs={"property_pk": property_obj.pk})
        response = user_client.get(url)
        assert response.status_code == 200
        assert "form" in response.context

    def test_get_edit_existing_mandate(self, user_client, property_obj, mandate):
        url = reverse(
            "property:edit_mandate",
            kwargs={
                "property_pk": property_obj.pk,
                "mandate_pk": mandate.pk,
            },
        )
        response = user_client.get(url)
        assert response.status_code == 200

    def test_post_create_mandate_valid(self, user_client, property_obj):
        url = reverse("property:new_mandate", kwargs={"property_pk": property_obj.pk})
        data = {
            "manager_name": "New Manager",
            "start_date": "2023-01-01",
            "fee_type": ManagementMandate.FeeType.PERCENTAGE,
            "fee_percentage": "7.5",
        }
        response = user_client.post(url, data)
        assert response.status_code == 302
        assert ManagementMandate.objects.filter(
            manager_name="New Manager", property=property_obj
        ).exists()

    def test_post_edit_mandate_invalid(self, user_client, property_obj, mandate):
        url = reverse(
            "property:edit_mandate",
            kwargs={
                "property_pk": property_obj.pk,
                "mandate_pk": mandate.pk,
            },
        )
        data = {
            "manager_name": "",  # Required
            "start_date": "2023-01-01",
            "fee_percentage": "7.5",
        }
        response = user_client.post(url, data)
        assert response.status_code == 200


@pytest.mark.django_db
class TestDeleteMandate:
    def test_delete_mandate_post(self, user_client, property_obj, mandate):
        mandate_pk = mandate.pk
        url = reverse(
            "property:delete_mandate",
            kwargs={
                "property_pk": property_obj.pk,
                "mandate_pk": mandate_pk,
            },
        )
        response = user_client.post(url)
        assert response.status_code == 302
        assert not ManagementMandate.objects.filter(pk=mandate_pk).exists()

    def test_delete_mandate_get_returns_redirect(
        self, user_client, property_obj, mandate
    ):
        url = reverse(
            "property:delete_mandate",
            kwargs={
                "property_pk": property_obj.pk,
                "mandate_pk": mandate.pk,
            },
        )
        response = user_client.get(url)
        assert response.status_code == 302
        assert ManagementMandate.objects.filter(pk=mandate.pk).exists()
