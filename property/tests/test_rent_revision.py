"""Tests for the yearly IRL rent revision."""

import datetime
from decimal import Decimal

import pytest
from django.contrib.messages import get_messages
from django.urls import reverse
from moneyed import Money

from base.models import EconomicIndex, EconomicIndexValue
from property.models import Lease, Property, PropertyLedgerEntry
from property.services.rent_revision import (
    RentRevision,
    apply_rent_revision,
    get_rent_revision,
    irl_for_revision,
    next_revision_date,
)

EUR = "EUR"


@pytest.fixture(autouse=True)
def _no_stored_index(request):
    """Start from an empty index table, whatever the session fixtures loaded."""
    if "db" in request.fixturenames or request.node.get_closest_marker("django_db"):
        EconomicIndexValue.objects.all().delete()


def _irl(year, quarter, value, published_on=None):
    return EconomicIndexValue.objects.create(
        index=EconomicIndex.IRL,
        period=datetime.date(year, (quarter - 1) * 3 + 1, 1),
        value=Decimal(value),
        published_on=published_on,
    )


def _revision(lease, today=None) -> RentRevision:
    revision = get_rent_revision(lease, today=today)
    assert revision is not None
    return revision


def _irl_value(quarter, revision_date) -> Decimal | None:
    value = irl_for_revision(quarter, revision_date)
    return None if value is None else value.value


@pytest.fixture
def property_obj():
    return Property.objects.create(
        name="Rented flat",
        property_type=Property.APARTMENT,
        buying_value=Money(200000, EUR),
        buying_date=datetime.date(2020, 1, 1),
    )


@pytest.fixture
def lease(property_obj):
    return Lease.objects.create(
        property=property_obj,
        last_name="Doe",
        lease_type=Lease.LeaseType.EMPTY,
        status=Lease.Status.ACTIVE,
        start_date=datetime.date(2024, 3, 1),
        rent_amount=Money(Decimal("1000.00"), EUR),
        charges_amount=Money(Decimal("50.00"), EUR),
        irl_reference_quarter=2,
        irl_reference_value=Decimal("140.00"),
    )


@pytest.fixture
def irl_history(db):
    _irl(2023, 2, "140.00", datetime.date(2023, 7, 13))
    _irl(2024, 2, "145.00", datetime.date(2024, 7, 12))
    _irl(2024, 3, "145.50")
    _irl(2025, 2, "146.45", datetime.date(2025, 7, 15))


class TestNextRevisionDate:
    def _lease(self, start, last=None):
        return Lease(start_date=start, last_rent_revision_date=last)

    def test_first_anniversary(self):
        lease = self._lease(datetime.date(2024, 3, 1))
        assert next_revision_date(lease, datetime.date(2025, 2, 1)) == (
            datetime.date(2025, 3, 1)
        )

    def test_revision_older_than_a_year_is_lost(self):
        lease = self._lease(datetime.date(2024, 3, 1))
        assert next_revision_date(lease, datetime.date(2026, 10, 1)) == (
            datetime.date(2026, 3, 1)
        )

    def test_after_last_revision(self):
        lease = self._lease(datetime.date(2024, 3, 1), datetime.date(2026, 3, 1))
        assert next_revision_date(lease, datetime.date(2026, 10, 1)) == (
            datetime.date(2027, 3, 1)
        )

    def test_leap_day_start(self):
        lease = self._lease(datetime.date(2024, 2, 29))
        assert next_revision_date(lease, datetime.date(2024, 6, 1)) == (
            datetime.date(2025, 2, 28)
        )


@pytest.mark.django_db
class TestIrlForRevision:
    def test_latest_published(self, irl_history):
        assert _irl_value(2, datetime.date(2025, 7, 1)) == Decimal("145.00")
        assert _irl_value(2, datetime.date(2025, 8, 1)) == Decimal("146.45")

    def test_publication_delay_without_date(self, irl_history):
        assert irl_for_revision(3, datetime.date(2024, 10, 1)) is None
        assert _irl_value(3, datetime.date(2024, 10, 20)) == Decimal("145.50")

    def test_none(self, db):
        assert irl_for_revision(1, datetime.date(2025, 1, 1)) is None


@pytest.mark.django_db
class TestGetRentRevision:
    def test_ready_uses_previous_year_index(self, lease, irl_history):
        revision = _revision(lease, today=datetime.date(2025, 3, 10))
        assert revision.due_date == datetime.date(2025, 3, 1)
        assert revision.is_due is True
        assert revision.status == "ready"
        # IRL Q2 2024 / Q2 2023 = 145 / 140
        assert revision.reference_value == Decimal("140.00")
        assert revision.new_rent == Money(Decimal("1035.71"), EUR)
        assert revision.increase == Money(Decimal("35.71"), EUR)

    def test_falls_back_to_lease_reference(self, lease, db):
        _irl(2024, 2, "147.00", datetime.date(2024, 7, 12))
        revision = _revision(lease, today=datetime.date(2025, 2, 1))
        assert revision.is_due is False
        assert revision.previous_index is None
        assert revision.new_rent == Money(Decimal("1050.00"), EUR)

    def test_lower_index_keeps_rent(self, lease, db):
        _irl(2023, 2, "150.00", datetime.date(2023, 7, 13))
        _irl(2024, 2, "145.00", datetime.date(2024, 7, 12))
        revision = _revision(lease, today=datetime.date(2025, 3, 1))
        assert revision.new_rent == lease.rent_amount

    def test_missing_index(self, lease, db):
        revision = _revision(lease, today=datetime.date(2025, 3, 1))
        assert revision.status == "missing_index"
        assert revision.new_rent is None
        assert revision.increase is None

    def test_missing_reference(self, lease, irl_history):
        lease.irl_reference_quarter = None
        assert _revision(lease).status == "missing_reference"
        lease.irl_reference_quarter = 1
        lease.irl_reference_value = None
        _irl(2024, 1, "144.00", datetime.date(2024, 4, 15))
        revision = _revision(lease, today=datetime.date(2025, 3, 1))
        assert revision.status == "missing_reference"

    def test_frozen_rent(self, lease, irl_history):
        lease.property.dpe_rating = "F"
        revision = _revision(lease, today=datetime.date(2025, 3, 1))
        assert revision.status == "frozen"
        assert revision.new_rent is None

    @pytest.mark.parametrize(
        "change",
        [
            {"lease_type": Lease.LeaseType.COMMERCIAL},
            {"status": Lease.Status.ENDED},
            {"end_date": datetime.date(2025, 1, 1)},
        ],
    )
    def test_not_applicable(self, lease, change):
        for field, value in change.items():
            setattr(lease, field, value)
        assert get_rent_revision(lease, today=datetime.date(2025, 3, 1)) is None


def _rent_entry(lease, amount, start, **kwargs):
    return PropertyLedgerEntry.objects.create(
        property=lease.property,
        lease=lease,
        flow_type=PropertyLedgerEntry.FlowType.INCOME,
        management_category=PropertyLedgerEntry.ManagementCategory.RENT_COLLECTED,
        amount=Money(Decimal(amount), EUR),
        entry_date=start,
        recurrence_type=PropertyLedgerEntry.RecurrenceType.MONTHLY,
        **kwargs,
    )


@pytest.mark.django_db
class TestApplyRentRevision:
    def test_updates_lease_and_splits_rent_series(self, lease, irl_history):
        with_charges = _rent_entry(lease, "1050.00", datetime.date(2024, 3, 5))
        rent_only = _rent_entry(lease, "1000.00", datetime.date(2024, 3, 5))
        other = _rent_entry(lease, "980.00", datetime.date(2024, 3, 5))
        ended = _rent_entry(
            lease,
            "1000.00",
            datetime.date(2024, 3, 5),
            recurrence_end_date=datetime.date(2024, 12, 31),
        )
        revision = _revision(lease, today=datetime.date(2025, 3, 1))
        assert apply_rent_revision(revision) == 2

        lease.refresh_from_db()
        assert lease.rent_amount == Money(Decimal("1035.71"), EUR)
        assert lease.irl_reference_value == Decimal("145.00")
        assert lease.last_rent_revision_date == datetime.date(2025, 3, 1)

        with_charges.refresh_from_db()
        assert with_charges.recurrence_end_date == datetime.date(2025, 3, 4)
        new_series = PropertyLedgerEntry.objects.get(
            lease=lease, amount=Money(Decimal("1085.71"), EUR)
        )
        assert new_series.entry_date == datetime.date(2025, 3, 5)
        assert new_series.recurrence_end_date is None
        rent_only.refresh_from_db()
        assert rent_only.recurrence_end_date == datetime.date(2025, 3, 4)
        other.refresh_from_db()
        assert other.recurrence_end_date is None
        ended.refresh_from_db()
        assert ended.recurrence_end_date == datetime.date(2024, 12, 31)

    def test_late_claim_applies_from_today(self, lease, irl_history):
        entry = _rent_entry(lease, "1000.00", datetime.date(2024, 3, 5))
        revision = _revision(lease, today=datetime.date(2025, 3, 10))
        assert revision.default_effective_date == datetime.date(2025, 3, 10)
        apply_rent_revision(revision)
        entry.refresh_from_db()
        assert entry.recurrence_end_date == datetime.date(2025, 4, 4)

    def test_effective_date_never_before_anniversary(self, lease, irl_history):
        entry = _rent_entry(lease, "1000.00", datetime.date(2024, 3, 5))
        revision = _revision(lease, today=datetime.date(2025, 3, 10))
        apply_rent_revision(revision, datetime.date(2024, 1, 1))
        entry.refresh_from_db()
        assert entry.recurrence_end_date == datetime.date(2025, 3, 4)

    def test_later_effective_date(self, lease, irl_history):
        entry = _rent_entry(lease, "1000.00", datetime.date(2024, 3, 5))
        revision = _revision(lease, today=datetime.date(2025, 5, 10))
        apply_rent_revision(revision, datetime.date(2025, 5, 1))
        entry.refresh_from_db()
        assert entry.recurrence_end_date == datetime.date(2025, 5, 4)

    def test_not_computable(self, lease, db):
        revision = _revision(lease, today=datetime.date(2025, 3, 10))
        with pytest.raises(ValueError, match="cannot be computed"):
            apply_rent_revision(revision)


@pytest.fixture
def irl_series(db):
    """A Q2 IRL for every year around today, published each 15 July."""
    for year in range(2018, datetime.date.today().year + 2):
        _irl(year, 2, str(130 + year - 2018), datetime.date(year, 7, 15))


@pytest.mark.django_db
class TestRentRevisionViews:
    def _url(self, lease):
        return reverse(
            "property:apply_rent_revision",
            kwargs={"property_pk": lease.property.pk, "lease_pk": lease.pk},
        )

    def test_apply(self, user_client, lease, irl_series):
        lease.start_date = datetime.date.today() - datetime.timedelta(days=375)
        lease.save()
        response = user_client.post(self._url(lease), {"effective_date": "bad"})
        assert response.status_code == 302
        lease.refresh_from_db()
        assert lease.last_rent_revision_date is not None
        assert lease.rent_amount > Money(Decimal("1000.00"), EUR)
        assert any(
            "Rent revised" in str(m) for m in get_messages(response.wsgi_request)
        )

    def test_not_computable(self, user_client, lease):
        response = user_client.post(self._url(lease))
        assert response.status_code == 302
        assert any(
            "cannot be computed" in str(m) for m in get_messages(response.wsgi_request)
        )

    def test_not_due(self, user_client, lease, irl_series):
        lease.start_date = datetime.date.today() - datetime.timedelta(days=30)
        lease.save()
        response = user_client.post(self._url(lease))
        assert any("not due yet" in str(m) for m in get_messages(response.wsgi_request))

    def test_get_not_allowed(self, user_client, lease):
        assert user_client.get(self._url(lease)).status_code == 405

    def test_panel_shows_revision(self, user_client, lease, irl_series):
        lease.start_date = datetime.date.today() - datetime.timedelta(days=375)
        lease.save()
        response = user_client.get(
            reverse("property:panel_leases", args=[lease.property.pk])
        )
        content = response.content.decode()
        assert f'id="rent-revision-{lease.pk}"' in content
        assert "Apply revision" in content
