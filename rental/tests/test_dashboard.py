"""Tests for the figures of the rental dashboard."""

import datetime
from decimal import Decimal

import pytest
from moneyed import Money

from property.models import Lease, ManagementMandate, Property
from rental.services.dashboard import lease_rows, monthly_rent_roll, occupancy_rate

TODAY = datetime.date(2026, 10, 1)


def _lease(prop, start, end=None, **kwargs):
    return Lease.objects.create(
        property=prop,
        start_date=start,
        end_date=end,
        status=kwargs.pop("status", Lease.Status.ACTIVE),
        rent_amount=Money(Decimal(600), "EUR"),
        charges_amount=Money(Decimal(30), "EUR"),
        **kwargs,
    )


@pytest.mark.django_db
def test_lease_rows_check_only_the_self_managed_leases(lease, prop):
    other = Property.objects.create(
        name="Agence",
        property_type=Property.APARTMENT,
        buying_value=Money(1, "EUR"),
        buying_date=datetime.date(2019, 1, 1),
    )
    managed = _lease(other, datetime.date(2020, 1, 1))
    mandate = ManagementMandate.objects.create(
        property=other, manager_name="Foncia", start_date=datetime.date(2020, 1, 1)
    )
    _lease(prop, datetime.date(2010, 1, 1), status=Lease.Status.ENDED)
    rows = {row.lease.pk: row for row in lease_rows(datetime.date.today())}
    assert set(rows) == {lease.pk, managed.pk}
    assert rows[managed.pk].mandate == mandate
    assert rows[managed.pk].checks == []
    assert rows[lease.pk].mandate is None
    assert rows[lease.pk].issues


@pytest.mark.django_db
def test_monthly_rent_roll(prop):
    monthly = _lease(prop, TODAY)
    quarterly = _lease(prop, TODAY, periodicity=Lease.Periodicity.QUARTERLY)
    upcoming = _lease(prop, TODAY, status=Lease.Status.UPCOMING)
    assert monthly_rent_roll([monthly, quarterly, upcoming]) == Decimal("840.00")


@pytest.mark.django_db
def test_occupancy_rate(prop):
    assert occupancy_rate(TODAY) is None
    # Let for the whole year, then vacant for the last 73 days.
    _lease(prop, datetime.date(2024, 1, 1), TODAY - datetime.timedelta(days=73))
    assert occupancy_rate(TODAY) == Decimal("80.0")


@pytest.mark.django_db
def test_occupancy_starts_with_the_first_lease(prop):
    _lease(prop, TODAY - datetime.timedelta(days=99))
    _lease(prop, TODAY - datetime.timedelta(days=50))  # overlapping: counted once
    assert occupancy_rate(TODAY) == Decimal("100.0")


@pytest.mark.django_db
def test_occupancy_leaves_out_the_properties_under_mandate(prop):
    _lease(prop, datetime.date(2024, 1, 1), TODAY - datetime.timedelta(days=73))
    ManagementMandate.objects.create(
        property=prop, manager_name="Foncia", start_date=datetime.date(2024, 1, 1)
    )
    assert occupancy_rate(TODAY) is None


@pytest.mark.django_db
def test_occupancy_ignores_leases_ended_before_the_window(prop):
    _lease(prop, datetime.date(2020, 1, 1), datetime.date(2021, 1, 1))
    _lease(prop, TODAY - datetime.timedelta(days=99))
    assert occupancy_rate(TODAY) == Decimal("27.4")
