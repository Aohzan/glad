"""Tests for checking (reconciling) occurrences of recurring ledger entries."""

import datetime
from decimal import Decimal

import pytest
from django.contrib.messages import get_messages
from django.urls import reverse
from moneyed import Money

from property.models import Property, PropertyLedgerEntry, PropertyLedgerEntryException
from property.services.checks import (
    PendingOccurrence,
    check_all_up_to,
    check_occurrence,
    delete_occurrence,
    parse_occurrence_key,
    pending_checks_summary,
    pending_occurrences,
    uncheck_occurrence,
)
from property.views import check_views

TODAY = datetime.date.today()
EUR_1000 = Money(Decimal("1000.00"), "EUR")

# ─── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def property_obj():
    # Keep global summaries deterministic whatever else is in the database.
    Property.objects.update(is_active=False)
    return Property.objects.create(
        name="Check Test Property",
        property_type=Property.APARTMENT,
        buying_value=Money(200000, "EUR"),
        buying_date=datetime.date(2020, 1, 1),
    )


def _monthly_entry(property_obj, start, **kwargs):
    defaults = {
        "property": property_obj,
        "flow_type": PropertyLedgerEntry.FlowType.INCOME,
        "management_category": PropertyLedgerEntry.ManagementCategory.RENT_COLLECTED,
        "amount": EUR_1000,
        "entry_date": start,
        "recurrence_type": PropertyLedgerEntry.RecurrenceType.MONTHLY,
        "description": "Monthly rent",
    }
    defaults.update(kwargs)
    return PropertyLedgerEntry.objects.create(**defaults)


@pytest.fixture
def rent(property_obj):
    """Monthly rent 2024-01-01 → 2024-06-01 (6 past occurrences)."""
    return _monthly_entry(
        property_obj,
        datetime.date(2024, 1, 1),
        recurrence_end_date=datetime.date(2024, 6, 1),
        third_party="John",
    )


def _url(name, entry, occ_date):
    return reverse(
        f"property:{name}",
        kwargs={
            "property_pk": entry.property.pk,
            "entry_pk": entry.pk,
            "occurrence_date": occ_date.isoformat(),
        },
    )


# ─── Model: display_label and generate_occurrences ────────────────────────────


@pytest.mark.django_db
class TestModel:
    def test_display_label(self, rent, property_obj):
        from property.models import Lease

        assert rent.display_label == "John - Monthly rent"
        lease = Lease.objects.create(
            property=property_obj,
            first_name="Jane",
            last_name="Doe",
            start_date=datetime.date(2024, 1, 1),
            rent_amount=EUR_1000,
        )
        rent.lease = lease
        rent.description = ""
        rent.third_party = ""
        assert rent.display_label == "Jane Doe"

    def test_occurrences_expose_check_fields(self, rent):
        occ = rent.generate_occurrences()[0]
        assert occ["occurrence_date"] == datetime.date(2024, 1, 1)
        assert occ["is_checked"] is False
        assert occ["actual_date"] is None
        assert "has_exception" not in occ

    def test_single_entry_has_no_check_fields(self, property_obj):
        entry = _monthly_entry(
            property_obj,
            datetime.date(2024, 1, 1),
            recurrence_type=PropertyLedgerEntry.RecurrenceType.NONE,
        )
        assert "occurrence_date" not in entry.generate_occurrences()[0]

    def test_actual_date_becomes_effective_date(self, rent):
        PropertyLedgerEntryException.objects.create(
            parent_entry=rent,
            occurrence_date=datetime.date(2024, 3, 1),
            is_checked=True,
            actual_date=datetime.date(2024, 3, 5),
        )
        march = next(
            o
            for o in rent.generate_occurrences()
            if o["occurrence_date"] == datetime.date(2024, 3, 1)
        )
        assert march["date"] == datetime.date(2024, 3, 5)
        assert march["actual_date"] == datetime.date(2024, 3, 5)
        assert march["is_checked"] is True

    def test_end_date_uses_effective_date(self, rent):
        # Scheduled 2024-03-01 but paid on 2024-02-28: it belongs to February.
        PropertyLedgerEntryException.objects.create(
            parent_entry=rent,
            occurrence_date=datetime.date(2024, 3, 1),
            is_checked=True,
            actual_date=datetime.date(2024, 2, 28),
        )
        # Scheduled 2024-02-01 but paid on 2024-03-02: it leaves February.
        PropertyLedgerEntryException.objects.create(
            parent_entry=rent,
            occurrence_date=datetime.date(2024, 2, 1),
            is_checked=True,
            actual_date=datetime.date(2024, 3, 2),
        )
        dates = [
            o["date"] for o in rent.generate_occurrences(datetime.date(2024, 2, 29))
        ]
        assert dates == [datetime.date(2024, 1, 1), datetime.date(2024, 2, 28)]


# ─── Service ──────────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestService:
    def test_parse_occurrence_key(self, rent):
        pending = PendingOccurrence(rent, datetime.date(2024, 3, 1), EUR_1000)
        assert pending.key == f"{rent.pk}_20240301"
        assert parse_occurrence_key(pending.key) == (rent.pk, datetime.date(2024, 3, 1))
        assert parse_occurrence_key("nounderscore") is None
        assert parse_occurrence_key("x_20240301") is None
        assert parse_occurrence_key("1_2024-03-01") is None

    def test_pending_occurrences(self, rent, property_obj):
        PropertyLedgerEntryException.objects.create(
            parent_entry=rent,
            occurrence_date=datetime.date(2024, 2, 1),
            is_checked=True,
        )
        PropertyLedgerEntryException.objects.create(
            parent_entry=rent,
            occurrence_date=datetime.date(2024, 3, 1),
            is_deleted=True,
        )
        # Single entries and inactive properties are ignored.
        _monthly_entry(
            property_obj,
            datetime.date(2024, 1, 1),
            recurrence_type=PropertyLedgerEntry.RecurrenceType.NONE,
        )
        pending = pending_occurrences(property_obj=property_obj)
        assert [p.planned_date.month for p in pending] == [1, 4, 5, 6]
        assert pending[0].planned_amount == EUR_1000
        assert len(pending_occurrences(up_to=datetime.date(2024, 4, 30))) == 2

        property_obj.is_active = False
        property_obj.save()
        assert pending_occurrences() == []

    def test_pending_excludes_future_start(self, property_obj):
        _monthly_entry(property_obj, TODAY + datetime.timedelta(days=10))
        assert pending_occurrences() == []

    def test_summary_levels(self, property_obj):
        assert pending_checks_summary() == {"count": 0, "oldest_days": 0, "level": None}

        entry = _monthly_entry(
            property_obj,
            TODAY - datetime.timedelta(days=3),
            recurrence_type=PropertyLedgerEntry.RecurrenceType.YEARLY,
        )
        assert pending_checks_summary()["level"] is None

        entry.entry_date = TODAY - datetime.timedelta(days=10)
        entry.save()
        summary = pending_checks_summary()
        assert summary == {"count": 1, "oldest_days": 10, "level": "warning"}

        entry.entry_date = TODAY - datetime.timedelta(days=45)
        entry.save()
        summary = pending_checks_summary()
        assert summary["level"] == "danger"
        assert summary["oldest_days"] == 45

    def test_check_occurrence_same_values(self, rent):
        occ_date = datetime.date(2024, 3, 1)
        exc = check_occurrence(rent, occ_date, occ_date, EUR_1000)
        assert exc.is_checked is True
        assert exc.actual_date is None
        assert exc.amount_override is None

    def test_check_occurrence_different_values(self, rent):
        occ_date = datetime.date(2024, 3, 1)
        PropertyLedgerEntryException.objects.create(
            parent_entry=rent, occurrence_date=occ_date, description_override="Keep"
        )
        exc = check_occurrence(
            rent, occ_date, datetime.date(2024, 3, 4), Money(Decimal("950.00"), "EUR")
        )
        assert exc.actual_date == datetime.date(2024, 3, 4)
        assert exc.amount_override == Money(Decimal("950.00"), "EUR")
        assert exc.description_override == "Keep"

    def test_check_occurrence_keeps_override_without_amount(self, rent):
        occ_date = datetime.date(2024, 3, 1)
        PropertyLedgerEntryException.objects.create(
            parent_entry=rent,
            occurrence_date=occ_date,
            amount_override=Money(Decimal("1100.00"), "EUR"),
            is_deleted=True,
        )
        exc = check_occurrence(rent, occ_date)
        assert exc.amount_override == Money(Decimal("1100.00"), "EUR")
        assert exc.is_deleted is False

    def test_uncheck_occurrence(self, rent):
        occ_date = datetime.date(2024, 3, 1)
        check_occurrence(
            rent, occ_date, datetime.date(2024, 3, 4), Money(Decimal("950.00"), "EUR")
        )
        uncheck_occurrence(rent, occ_date)
        exc = PropertyLedgerEntryException.objects.get(
            parent_entry=rent, occurrence_date=occ_date
        )
        assert exc.is_checked is False
        assert exc.actual_date is None
        assert exc.amount_override == Money(Decimal("950.00"), "EUR")

    def test_delete_occurrence(self, rent):
        occ_date = datetime.date(2024, 3, 1)
        check_occurrence(rent, occ_date, datetime.date(2024, 3, 4))
        delete_occurrence(rent, occ_date)
        exc = PropertyLedgerEntryException.objects.get(
            parent_entry=rent, occurrence_date=occ_date
        )
        assert exc.is_deleted is True
        assert exc.is_checked is False
        assert exc.actual_date is None

    def test_check_all_up_to(self, rent, property_obj):
        PropertyLedgerEntryException.objects.create(
            parent_entry=rent,
            occurrence_date=datetime.date(2024, 2, 1),
            amount_override=Money(Decimal("900.00"), "EUR"),
        )
        assert check_all_up_to(datetime.date(2024, 3, 15), property_obj) == 3
        exc = PropertyLedgerEntryException.objects.get(
            parent_entry=rent, occurrence_date=datetime.date(2024, 2, 1)
        )
        assert exc.is_checked is True
        assert exc.amount_override == Money(Decimal("900.00"), "EUR")
        assert len(pending_occurrences(property_obj)) == 3
        assert check_all_up_to(datetime.date(2024, 3, 15)) == 0


# ─── Bulk checking view ───────────────────────────────────────────────────────


@pytest.mark.django_db
class TestOccurrenceChecksView:
    url = reverse("property:checks")

    def test_requires_login(self, client):
        assert client.get(self.url).status_code == 302

    def test_get_lists_pending(self, admin_client, rent):
        response = admin_client.get(self.url)
        assert response.status_code == 200
        assert response.context["total_count"] == 6
        assert len(response.context["rows"]) == 6
        row = response.context["rows"][0]
        assert row.actual_date == "2024-01-01"
        assert row.actual_amount == "1000.00"
        content = response.content.decode()
        assert f"check_{rent.pk}_20240101" in content
        assert "John - Monthly rent" in content

    def test_get_empty(self, admin_client, property_obj):
        response = admin_client.get(self.url)
        assert response.status_code == 200
        assert response.context["rows"] == []

    def test_property_filter(self, admin_client, rent):
        other = Property.objects.create(
            name="Other",
            property_type=Property.APARTMENT,
            buying_value=Money(1, "EUR"),
            buying_date=datetime.date(2020, 1, 1),
        )
        _monthly_entry(
            other,
            datetime.date(2024, 1, 1),
            recurrence_end_date=datetime.date(2024, 1, 1),
        )
        assert admin_client.get(self.url).context["total_count"] == 7
        response = admin_client.get(self.url, {"property": other.pk})
        assert response.context["selected_property"] == other
        assert response.context["total_count"] == 1
        # Invalid filters fall back to all properties.
        assert (
            admin_client.get(self.url, {"property": "abc"}).context["selected_property"]
            is None
        )

    def test_rows_are_capped(self, admin_client, rent, monkeypatch):
        monkeypatch.setattr(check_views, "MAX_ROWS", 2)
        response = admin_client.get(self.url)
        assert len(response.context["rows"]) == 2
        assert response.context["hidden_count"] == 4

    def test_save_checks_and_deletes(self, admin_client, rent):
        key_jan = f"{rent.pk}_20240101"
        key_feb = f"{rent.pk}_20240201"
        key_mar = f"{rent.pk}_20240301"
        response = admin_client.post(
            self.url,
            {
                "action": "save",
                f"check_{key_jan}": "1",
                f"date_{key_jan}": "2024-01-03",
                f"amount_{key_jan}": "980,50",
                f"check_{key_feb}": "1",
                f"delete_{key_mar}": "1",
                # Posted keys that are not pending are ignored.
                "check_999999_20240101": "1",
            },
        )
        assert response.status_code == 302
        jan = PropertyLedgerEntryException.objects.get(
            parent_entry=rent, occurrence_date=datetime.date(2024, 1, 1)
        )
        assert jan.is_checked
        assert jan.actual_date == datetime.date(2024, 1, 3)
        assert jan.amount_override == Money(Decimal("980.50"), "EUR")
        feb = PropertyLedgerEntryException.objects.get(
            parent_entry=rent, occurrence_date=datetime.date(2024, 2, 1)
        )
        assert feb.is_checked
        assert feb.actual_date is None
        assert feb.amount_override is None
        assert PropertyLedgerEntryException.objects.get(
            parent_entry=rent, occurrence_date=datetime.date(2024, 3, 1)
        ).is_deleted
        msgs = [str(m) for m in get_messages(response.wsgi_request)]
        assert any("2" in m and "1" in m for m in msgs)

    def test_save_keeps_property_filter(self, admin_client, rent):
        response = admin_client.post(
            self.url,
            {
                "action": "save",
                "property": rent.property.pk,
                f"check_{rent.pk}_20240101": "1",
            },
        )
        assert response.url == f"{self.url}?property={rent.property.pk}"

    def test_save_nothing_selected(self, admin_client, rent):
        response = admin_client.post(self.url, {"action": "save"})
        assert response.status_code == 302
        assert not PropertyLedgerEntryException.objects.exists()

    @pytest.mark.parametrize(
        ("extra", "error"),
        [
            ({"delete": "1"}, "both"),
            ({"date": "not-a-date"}, "date"),
            ({"date": (TODAY + datetime.timedelta(days=1)).isoformat()}, "future"),
            ({"amount": "0"}, "positive"),
            ({"amount": "abc"}, "positive"),
            ({"amount": "NaN"}, "positive"),
        ],
    )
    def test_save_invalid_row(self, admin_client, rent, extra, error):
        key = f"{rent.pk}_20240101"
        data = {"action": "save", f"check_{key}": "1"}
        data.update({f"{name}_{key}": value for name, value in extra.items()})
        response = admin_client.post(self.url, data)
        assert response.status_code == 200
        row = response.context["rows"][0]
        assert error in row.error
        assert row.is_checked
        assert not PropertyLedgerEntryException.objects.exists()

    def test_check_all(self, admin_client, rent):
        response = admin_client.post(
            self.url,
            {
                "action": "check_all",
                "up_to": "2024-02-15",
                "property": rent.property.pk,
            },
        )
        assert response.status_code == 302
        assert PropertyLedgerEntryException.objects.filter(is_checked=True).count() == 2

    def test_check_all_clamps_future_date(self, admin_client, property_obj):
        _monthly_entry(property_obj, TODAY - datetime.timedelta(days=1))
        admin_client.post(
            self.url,
            {
                "action": "check_all",
                "up_to": (TODAY + datetime.timedelta(days=90)).isoformat(),
            },
        )
        assert PropertyLedgerEntryException.objects.filter(is_checked=True).count() == 1

    def test_check_all_invalid_date(self, admin_client, rent):
        response = admin_client.post(self.url, {"action": "check_all", "up_to": "x"})
        assert response.status_code == 302
        assert not PropertyLedgerEntryException.objects.exists()

    def test_invalid_action(self, admin_client, rent):
        response = admin_client.post(self.url, {"action": "nope"})
        assert response.status_code == 302


# ─── Check / uncheck from the cash flow table ─────────────────────────────────


@pytest.mark.django_db
class TestCheckFromCashflow:
    occ_date = datetime.date(2024, 3, 1)

    def test_check(self, admin_client, rent):
        response = admin_client.post(
            _url("check_occurrence", rent, self.occ_date),
            {"actual_date": "2024-03-02", "actual_amount": "1000"},
        )
        assert response.status_code == 302
        assert response.url.endswith("#cashflow-panel")
        exc = PropertyLedgerEntryException.objects.get(parent_entry=rent)
        assert exc.is_checked
        assert exc.actual_date == datetime.date(2024, 3, 2)
        assert exc.amount_override is None

    def test_check_invalid_values(self, admin_client, rent):
        response = admin_client.post(
            _url("check_occurrence", rent, self.occ_date),
            {"actual_date": "2024-03-02", "actual_amount": "-5"},
        )
        assert response.status_code == 302
        assert not PropertyLedgerEntryException.objects.exists()

    def test_check_invalid_occurrence(self, admin_client, rent):
        response = admin_client.post(
            _url("check_occurrence", rent, datetime.date(2024, 3, 2)),
            {"actual_date": "2024-03-02", "actual_amount": "1000"},
        )
        assert response.status_code == 302
        assert not PropertyLedgerEntryException.objects.exists()

    def test_check_other_property_entry(self, admin_client, rent):
        other = Property.objects.create(
            name="Other",
            property_type=Property.APARTMENT,
            buying_value=Money(1, "EUR"),
            buying_date=datetime.date(2020, 1, 1),
        )
        url = reverse(
            "property:check_occurrence",
            kwargs={
                "property_pk": other.pk,
                "entry_pk": rent.pk,
                "occurrence_date": self.occ_date.isoformat(),
            },
        )
        admin_client.post(url, {"actual_date": "2024-03-02", "actual_amount": "1000"})
        assert not PropertyLedgerEntryException.objects.exists()

    @pytest.mark.parametrize("name", ["check_occurrence", "uncheck_occurrence"])
    def test_get_not_allowed(self, admin_client, rent, name):
        response = admin_client.get(_url(name, rent, self.occ_date))
        assert response.status_code == 302
        assert not PropertyLedgerEntryException.objects.exists()

    def test_uncheck(self, admin_client, rent):
        check_occurrence(rent, self.occ_date, datetime.date(2024, 3, 3))
        # The checked occurrence is still addressed by its scheduled date.
        response = admin_client.post(_url("uncheck_occurrence", rent, self.occ_date))
        assert response.status_code == 302
        exc = PropertyLedgerEntryException.objects.get(parent_entry=rent)
        assert not exc.is_checked
        assert exc.actual_date is None

    def test_uncheck_invalid_occurrence(self, admin_client, rent):
        response = admin_client.post(
            _url("uncheck_occurrence", rent, datetime.date(2030, 1, 1))
        )
        assert response.status_code == 302

    def test_cashflow_rows_expose_check_state(self, admin_client, rent):
        check_occurrence(
            rent, self.occ_date, datetime.date(2024, 3, 3), Money(Decimal(990), "EUR")
        )
        response = admin_client.get(
            reverse("property:panel_cashflow", args=[rent.property.pk])
        )
        rows = response.context["transactions_json"]
        march = next(r for r in rows if r["occurrence_date"] == "2024-03-01")
        assert march["date"] == "2024-03-03"
        assert march["is_checked"] is True
        assert march["is_moved"] is True
        assert march["amount"] == 990.0
        assert march["planned_amount"] == 1000.0
        april = next(r for r in rows if r["occurrence_date"] == "2024-04-01")
        assert april["is_checked"] is False
        assert "checkOccurrenceModal" in response.content.decode()

    def test_edit_occurrence_keeps_check_state(self, admin_client, rent):
        check_occurrence(rent, self.occ_date, datetime.date(2024, 3, 3))
        admin_client.post(
            _url("edit_entry_occurrence", rent, self.occ_date),
            {"scope": "this", "description_override": "Late"},
        )
        exc = PropertyLedgerEntryException.objects.get(parent_entry=rent)
        assert exc.description_override == "Late"
        assert exc.is_checked
        assert exc.actual_date == datetime.date(2024, 3, 3)


# ─── Home page alert ──────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestIndexAlert:
    def test_no_alert_without_properties(self, admin_client):
        Property.objects.update(is_active=False)
        response = admin_client.get(reverse("index"))
        assert response.context["property_checks"] is None

    def test_no_alert_when_recent(self, admin_client, property_obj):
        _monthly_entry(property_obj, TODAY - datetime.timedelta(days=2))
        response = admin_client.get(reverse("index"))
        assert response.context["property_checks"]["level"] is None
        assert "property-checks-alert" not in response.content.decode()

    @pytest.mark.parametrize(("days", "level"), [(10, "warning"), (40, "danger")])
    def test_alert_level(self, admin_client, property_obj, days, level):
        _monthly_entry(
            property_obj,
            TODAY - datetime.timedelta(days=days),
            recurrence_type=PropertyLedgerEntry.RecurrenceType.YEARLY,
        )
        response = admin_client.get(reverse("index"))
        content = response.content.decode()
        assert f"alert-{level}" in content
        assert "property-checks-alert" in content
        assert reverse("property:checks") in content
