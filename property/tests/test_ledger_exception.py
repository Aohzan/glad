"""Tests for PropertyLedgerEntryException model, generate_occurrences, and occurrence views."""

import datetime
from decimal import Decimal

import pytest
from django.contrib.messages import get_messages
from django.urls import reverse
from moneyed import Money

from property.models import Property, PropertyLedgerEntry, PropertyLedgerEntryException

# ─── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def property_obj():
    return Property.objects.create(
        name="Exception Test Property",
        property_type=Property.APARTMENT,
        buying_value=Money(200000, "EUR"),
        buying_date=datetime.date(2020, 1, 1),
    )


@pytest.fixture
def recurring_entry(property_obj):
    """Monthly recurring entry starting 2024-01-01, ending 2024-06-01 (6 occurrences)."""
    return PropertyLedgerEntry.objects.create(
        property=property_obj,
        flow_type=PropertyLedgerEntry.FlowType.INCOME,
        management_category=PropertyLedgerEntry.ManagementCategory.RENT_COLLECTED,
        amount=Money(Decimal("1000.00"), "EUR"),
        entry_date=datetime.date(2024, 1, 1),
        recurrence_type=PropertyLedgerEntry.RecurrenceType.MONTHLY,
        recurrence_end_date=datetime.date(2024, 6, 1),
        description="Monthly rent",
    )


@pytest.fixture
def single_entry(property_obj):
    """Non-recurring single entry."""
    return PropertyLedgerEntry.objects.create(
        property=property_obj,
        flow_type=PropertyLedgerEntry.FlowType.EXPENSE,
        management_category=PropertyLedgerEntry.ManagementCategory.INSURANCE,
        amount=Money(Decimal("500.00"), "EUR"),
        entry_date=datetime.date(2024, 3, 15),
    )


# ─── PropertyLedgerEntryException model ──────────────────────────────────────


@pytest.mark.django_db
class TestPropertyLedgerEntryExceptionModel:
    def test_str_deleted(self, recurring_entry):
        exc = PropertyLedgerEntryException.objects.create(
            parent_entry=recurring_entry,
            occurrence_date=datetime.date(2024, 3, 1),
            is_deleted=True,
        )
        assert "Deleted" in str(exc)
        assert "2024-03-01" in str(exc)

    def test_str_override(self, recurring_entry):
        exc = PropertyLedgerEntryException.objects.create(
            parent_entry=recurring_entry,
            occurrence_date=datetime.date(2024, 3, 1),
            amount_override=Money(Decimal("1200.00"), "EUR"),
        )
        assert "Override" in str(exc)

    def test_unique_together(self, recurring_entry):
        PropertyLedgerEntryException.objects.create(
            parent_entry=recurring_entry,
            occurrence_date=datetime.date(2024, 3, 1),
            is_deleted=True,
        )
        from django.db import IntegrityError

        with pytest.raises(IntegrityError):
            PropertyLedgerEntryException.objects.create(
                parent_entry=recurring_entry,
                occurrence_date=datetime.date(2024, 3, 1),
                is_deleted=False,
            )

    def test_cascade_delete(self, recurring_entry):
        exc = PropertyLedgerEntryException.objects.create(
            parent_entry=recurring_entry,
            occurrence_date=datetime.date(2024, 3, 1),
            is_deleted=True,
        )
        recurring_entry.delete()
        assert not PropertyLedgerEntryException.objects.filter(pk=exc.pk).exists()


# ─── generate_occurrences() with exceptions ───────────────────────────────────


@pytest.mark.django_db
class TestGenerateOccurrencesWithExceptions:
    def test_no_exceptions_returns_all(self, recurring_entry):
        occurrences = recurring_entry.generate_occurrences()
        assert len(occurrences) == 6

    def test_deleted_exception_removes_occurrence(self, recurring_entry):
        PropertyLedgerEntryException.objects.create(
            parent_entry=recurring_entry,
            occurrence_date=datetime.date(2024, 3, 1),
            is_deleted=True,
        )
        occurrences = recurring_entry.generate_occurrences()
        dates = [o["date"] for o in occurrences]
        assert datetime.date(2024, 3, 1) not in dates
        assert len(occurrences) == 5

    def test_amount_override_applied(self, recurring_entry):
        PropertyLedgerEntryException.objects.create(
            parent_entry=recurring_entry,
            occurrence_date=datetime.date(2024, 3, 1),
            amount_override=Money(Decimal("1500.00"), "EUR"),
        )
        occurrences = recurring_entry.generate_occurrences()
        march = next(o for o in occurrences if o["date"] == datetime.date(2024, 3, 1))
        assert march["amount"] == Money(Decimal("1500.00"), "EUR")
        assert march["has_exception"] is True

    def test_description_override_applied(self, recurring_entry):
        PropertyLedgerEntryException.objects.create(
            parent_entry=recurring_entry,
            occurrence_date=datetime.date(2024, 3, 1),
            description_override="Special March",
        )
        occurrences = recurring_entry.generate_occurrences()
        march = next(o for o in occurrences if o["date"] == datetime.date(2024, 3, 1))
        assert march["description_override"] == "Special March"

    def test_none_exception_does_not_skip(self, recurring_entry):
        """Occurrences without exceptions are returned unchanged."""
        PropertyLedgerEntryException.objects.create(
            parent_entry=recurring_entry,
            occurrence_date=datetime.date(2024, 3, 1),
            is_deleted=True,
        )
        occurrences = recurring_entry.generate_occurrences()
        # Jan, Feb, Apr, May, Jun should still be present
        dates = [o["date"] for o in occurrences]
        assert datetime.date(2024, 1, 1) in dates
        assert datetime.date(2024, 6, 1) in dates

    def test_notes_override_applied(self, recurring_entry):
        PropertyLedgerEntryException.objects.create(
            parent_entry=recurring_entry,
            occurrence_date=datetime.date(2024, 3, 1),
            notes_override="Special note",
        )
        occurrences = recurring_entry.generate_occurrences()
        march = next(o for o in occurrences if o["date"] == datetime.date(2024, 3, 1))
        assert march["notes_override"] == "Special note"

    def test_no_exceptions_in_db_returns_all_unchanged(self, recurring_entry):
        """When no exceptions exist, all occurrences are returned unchanged."""
        occurrences = recurring_entry.generate_occurrences()
        assert len(occurrences) == 6
        assert all("has_exception" not in o for o in occurrences)


# ─── Edit occurrence view ─────────────────────────────────────────────────────


@pytest.mark.django_db
class TestEditLedgerEntryOccurrence:
    def _url(self, property_obj, entry, occ_date):
        return reverse(
            "property:edit_entry_occurrence",
            kwargs={
                "property_pk": property_obj.pk,
                "entry_pk": entry.pk,
                "occurrence_date": occ_date.isoformat(),
            },
        )

    def test_get_shows_form(self, user_client, property_obj, recurring_entry):
        url = self._url(property_obj, recurring_entry, datetime.date(2024, 3, 1))
        response = user_client.get(url)
        assert response.status_code == 200
        assert "form" in response.context
        assert response.context["occurrence_date"] == datetime.date(2024, 3, 1)

    def test_get_invalid_date_redirects(
        self, user_client, property_obj, recurring_entry
    ):
        url = reverse(
            "property:edit_entry_occurrence",
            kwargs={
                "property_pk": property_obj.pk,
                "entry_pk": recurring_entry.pk,
                "occurrence_date": "not-a-date",
            },
        )
        response = user_client.get(url)
        assert response.status_code == 302

    def test_get_non_occurrence_date_redirects(
        self, user_client, property_obj, recurring_entry
    ):
        # 2024-03-15 is not a valid occurrence (monthly on 1st)
        url = self._url(property_obj, recurring_entry, datetime.date(2024, 3, 15))
        response = user_client.get(url)
        assert response.status_code == 302

    def test_post_scope_this_creates_exception(
        self, user_client, property_obj, recurring_entry
    ):
        url = self._url(property_obj, recurring_entry, datetime.date(2024, 3, 1))
        data = {
            "scope": "this",
            "amount_override_0": "1500.00",
            "amount_override_1": "EUR",
            "description_override": "Special March",
            "notes_override": "",
        }
        response = user_client.post(url, data)
        assert response.status_code == 302
        exc = PropertyLedgerEntryException.objects.get(
            parent_entry=recurring_entry, occurrence_date=datetime.date(2024, 3, 1)
        )
        assert exc.amount_override == Money(Decimal("1500.00"), "EUR")
        assert exc.description_override == "Special March"
        assert not exc.is_deleted

    def test_post_scope_this_updates_existing_exception(
        self, user_client, property_obj, recurring_entry
    ):
        existing = PropertyLedgerEntryException.objects.create(
            parent_entry=recurring_entry,
            occurrence_date=datetime.date(2024, 3, 1),
            amount_override=Money(Decimal("900.00"), "EUR"),
        )
        url = self._url(property_obj, recurring_entry, datetime.date(2024, 3, 1))
        data = {
            "scope": "this",
            "amount_override_0": "1500.00",
            "amount_override_1": "EUR",
            "description_override": "",
            "notes_override": "",
        }
        user_client.post(url, data)
        existing.refresh_from_db()
        assert existing.amount_override == Money(Decimal("1500.00"), "EUR")

    def test_post_scope_future_splits_series(
        self, user_client, property_obj, recurring_entry
    ):
        url = self._url(property_obj, recurring_entry, datetime.date(2024, 4, 1))
        data = {
            "scope": "future",
            "amount_override_0": "1200.00",
            "amount_override_1": "EUR",
            "description_override": "Raised rent",
            "notes_override": "",
        }
        response = user_client.post(url, data)
        assert response.status_code == 302
        # Original series truncated
        recurring_entry.refresh_from_db()
        assert recurring_entry.recurrence_end_date == datetime.date(2024, 3, 31)
        # New series created
        new_entry = PropertyLedgerEntry.objects.exclude(pk=recurring_entry.pk).get(
            property=property_obj, entry_date=datetime.date(2024, 4, 1)
        )
        assert new_entry.amount == Money(Decimal("1200.00"), "EUR")
        assert new_entry.description == "Raised rent"

    def test_post_scope_all_redirects_to_edit_entry(
        self, user_client, property_obj, recurring_entry
    ):
        url = self._url(property_obj, recurring_entry, datetime.date(2024, 3, 1))
        data = {"scope": "all"}
        response = user_client.post(url, data)
        assert response.status_code == 302
        assert "edit" in response["Location"]

    def test_post_invalid_scope_redirects(
        self, user_client, property_obj, recurring_entry
    ):
        url = self._url(property_obj, recurring_entry, datetime.date(2024, 3, 1))
        data = {"scope": "invalid"}
        response = user_client.post(url, data)
        assert response.status_code == 302
        msgs = list(get_messages(response.wsgi_request))
        assert any("Invalid scope" in str(m) for m in msgs)

    def test_post_scope_this_invalid_amount_shows_form(
        self, user_client, property_obj, recurring_entry
    ):
        """Invalid form data (bad amount) should re-render the form with errors."""
        url = self._url(property_obj, recurring_entry, datetime.date(2024, 3, 1))
        data = {
            "scope": "this",
            "amount_override_0": "not-a-number",
            "amount_override_1": "EUR",
            "description_override": "",
            "notes_override": "",
        }
        response = user_client.post(url, data)
        assert response.status_code == 200
        assert "form" in response.context


# ─── Delete occurrence view ───────────────────────────────────────────────────


@pytest.mark.django_db
class TestDeleteLedgerEntryOccurrence:
    def _url(self, property_obj, entry, occ_date):
        return reverse(
            "property:delete_entry_occurrence",
            kwargs={
                "property_pk": property_obj.pk,
                "entry_pk": entry.pk,
                "occurrence_date": occ_date.isoformat(),
            },
        )

    def test_get_shows_confirmation_page(
        self, user_client, property_obj, recurring_entry
    ):
        url = self._url(property_obj, recurring_entry, datetime.date(2024, 3, 1))
        response = user_client.get(url)
        assert response.status_code == 200
        assert response.context["occurrence_date"] == datetime.date(2024, 3, 1)

    def test_post_scope_this_creates_deleted_exception(
        self, user_client, property_obj, recurring_entry
    ):
        url = self._url(property_obj, recurring_entry, datetime.date(2024, 3, 1))
        response = user_client.post(url, {"scope": "this"})
        assert response.status_code == 302
        exc = PropertyLedgerEntryException.objects.get(
            parent_entry=recurring_entry, occurrence_date=datetime.date(2024, 3, 1)
        )
        assert exc.is_deleted

    def test_post_scope_this_overwrites_override_exception(
        self, user_client, property_obj, recurring_entry
    ):
        """An existing override exception should be converted to a deletion."""
        PropertyLedgerEntryException.objects.create(
            parent_entry=recurring_entry,
            occurrence_date=datetime.date(2024, 3, 1),
            amount_override=Money(Decimal("999.00"), "EUR"),
        )
        user_client.post(
            self._url(property_obj, recurring_entry, datetime.date(2024, 3, 1)),
            {"scope": "this"},
        )
        exc = PropertyLedgerEntryException.objects.get(
            parent_entry=recurring_entry, occurrence_date=datetime.date(2024, 3, 1)
        )
        assert exc.is_deleted
        assert exc.amount_override is None

    def test_post_scope_future_truncates_series(
        self, user_client, property_obj, recurring_entry
    ):
        url = self._url(property_obj, recurring_entry, datetime.date(2024, 4, 1))
        response = user_client.post(url, {"scope": "future"})
        assert response.status_code == 302
        recurring_entry.refresh_from_db()
        assert recurring_entry.recurrence_end_date == datetime.date(2024, 3, 31)

    def test_post_scope_future_removes_later_exceptions(
        self, user_client, property_obj, recurring_entry
    ):
        """Exceptions on or after the cut date should be cleaned up."""
        exc = PropertyLedgerEntryException.objects.create(
            parent_entry=recurring_entry,
            occurrence_date=datetime.date(2024, 5, 1),
            amount_override=Money(Decimal("900.00"), "EUR"),
        )
        user_client.post(
            self._url(property_obj, recurring_entry, datetime.date(2024, 4, 1)),
            {"scope": "future"},
        )
        assert not PropertyLedgerEntryException.objects.filter(pk=exc.pk).exists()

    def test_post_scope_all_deletes_entry(
        self, user_client, property_obj, recurring_entry
    ):
        url = self._url(property_obj, recurring_entry, datetime.date(2024, 3, 1))
        response = user_client.post(url, {"scope": "all"})
        assert response.status_code == 302
        assert not PropertyLedgerEntry.objects.filter(pk=recurring_entry.pk).exists()

    def test_post_invalid_date_redirects(
        self, user_client, property_obj, recurring_entry
    ):
        url = reverse(
            "property:delete_entry_occurrence",
            kwargs={
                "property_pk": property_obj.pk,
                "entry_pk": recurring_entry.pk,
                "occurrence_date": "2024-99-99",
            },
        )
        response = user_client.post(url, {"scope": "this"})
        assert response.status_code == 302

    def test_post_invalid_scope_redirects(
        self, user_client, property_obj, recurring_entry
    ):
        url = self._url(property_obj, recurring_entry, datetime.date(2024, 3, 1))
        response = user_client.post(url, {"scope": "bad"})
        assert response.status_code == 302
        msgs = list(get_messages(response.wsgi_request))
        assert any("Invalid scope" in str(m) for m in msgs)
