"""Tests for the rent schedule and the payment status of the periods."""

import datetime
from decimal import Decimal

import pytest
from moneyed import Money

from property.models import Lease, PropertyLedgerEntry
from property.services.checks import check_occurrence
from rental.services import payments
from rental.services.payments import (
    PAID,
    PARTIAL,
    UNPAID,
    UPCOMING,
    arrears,
    create_rent_schedule,
    first_due_date,
    has_schedule,
    lease_periods,
    period_of_month,
    summarize,
)

TODAY = datetime.date(2026, 10, 20)


@pytest.fixture
def scheduled(lease):
    lease.start_date = datetime.date(2026, 7, 1)
    lease.payment_day = 5
    lease.save()
    rent, charges = create_rent_schedule(lease)
    return lease, rent, charges


def test_first_due_date():
    lease = Lease(start_date=datetime.date(2026, 7, 15), payment_day=5)
    assert first_due_date(lease) == datetime.date(2026, 8, 5)
    lease.payment_day = 20
    assert first_due_date(lease) == datetime.date(2026, 7, 20)


@pytest.mark.django_db
def test_create_rent_schedule(scheduled):
    lease, rent, charges = scheduled
    assert has_schedule(lease)
    assert (rent.management_category, rent.amount) == (
        "rent_collected",
        lease.rent_amount,
    )
    assert (charges.management_category, charges.amount.amount) == (
        "charges_collected",
        Decimal(50),
    )
    assert rent.entry_date == datetime.date(2026, 7, 5)
    assert rent.recurrence_type == PropertyLedgerEntry.RecurrenceType.MONTHLY
    assert rent.third_party == "Jean Dupont"
    assert rent.lease == lease


@pytest.mark.django_db
def test_quarterly_schedule_without_charges(lease):
    lease.periodicity = Lease.Periodicity.QUARTERLY
    lease.charges_amount = Money(0, "EUR")
    (rent,) = create_rent_schedule(lease)
    assert rent.recurrence_type == PropertyLedgerEntry.RecurrenceType.QUARTERLY
    lease.start_date = datetime.date(2026, 1, 1)
    rent.entry_date = datetime.date(2026, 1, 1)
    rent.save()
    periods = lease_periods(lease, TODAY)
    assert [p.key for p in periods] == ["2026-10", "2026-07", "2026-04", "2026-01"]
    assert periods[0].end == datetime.date(2026, 12, 31)


@pytest.mark.django_db
def test_periods(scheduled):
    lease, rent, charges = scheduled
    # July: paid in full; August: rent paid late and partly; September: nothing.
    check_occurrence(rent, datetime.date(2026, 7, 5))
    check_occurrence(charges, datetime.date(2026, 7, 5), datetime.date(2026, 7, 4))
    check_occurrence(
        rent,
        datetime.date(2026, 8, 5),
        datetime.date(2026, 8, 12),
        Money(Decimal(500), "EUR"),
    )
    periods = lease_periods(lease, TODAY)
    by_key = {p.key: p for p in periods}
    assert [p.key for p in periods] == [
        "2026-11",
        "2026-10",
        "2026-09",
        "2026-08",
        "2026-07",
    ]
    july, august, september = by_key["2026-07"], by_key["2026-08"], by_key["2026-09"]
    assert (july.status, july.paid, july.paid_date) == (
        PAID,
        Decimal(850),
        datetime.date(2026, 7, 5),
    )
    assert (august.status, august.expected, august.paid, august.balance) == (
        PARTIAL,
        Decimal(850),
        Decimal(500),
        Decimal(350),
    )
    assert august.paid_date == datetime.date(2026, 8, 12)
    assert (september.status, september.days_late) == (UNPAID, 45)
    assert len(september.unchecked) == 2
    assert by_key["2026-11"].status == UPCOMING
    assert by_key["2026-11"].days_late == 0
    assert arrears(periods) == Decimal(350 + 850 + 850)
    assert period_of_month(periods, TODAY) == by_key["2026-10"]
    assert period_of_month(periods, datetime.date(2025, 1, 1)) is None


@pytest.mark.django_db
def test_one_off_payment_counts_for_its_period(scheduled):
    lease, _rent, _charges = scheduled
    PropertyLedgerEntry.objects.create(
        property=lease.property,
        lease=lease,
        flow_type=PropertyLedgerEntry.FlowType.INCOME,
        management_category="rent_collected",
        amount=Money(Decimal(850), "EUR"),
        entry_date=datetime.date(2026, 10, 2),
        reference_period=datetime.date(2026, 9, 1),
    )
    september = period_of_month(lease_periods(lease, TODAY), datetime.date(2026, 9, 1))
    assert september is not None
    assert (september.status, september.paid_date) == (PAID, datetime.date(2026, 10, 2))


@pytest.mark.django_db
def test_other_entries_are_ignored(scheduled):
    lease, _rent, _charges = scheduled
    PropertyLedgerEntry.objects.create(
        property=lease.property,
        lease=lease,
        flow_type=PropertyLedgerEntry.FlowType.EXPENSE,
        management_category="maintenance",
        amount=Money(Decimal(100), "EUR"),
        entry_date=datetime.date(2026, 9, 2),
    )
    september = period_of_month(lease_periods(lease, TODAY), datetime.date(2026, 9, 1))
    assert september is not None
    assert september.paid == 0


@pytest.mark.django_db
def test_summarize(scheduled):
    lease, rent, _charges = scheduled
    check_occurrence(rent, datetime.date(2026, 10, 5))
    periods = lease_periods(lease, TODAY)
    assert summarize({lease.pk: periods, 0: []}, TODAY) == {
        "expected": Decimal(850),
        "received": Decimal(800),
        "arrears": Decimal(850 * 3 + 50),
    }


def test_period_months_cover_the_periodicities():
    assert set(payments.PERIOD_MONTHS) == set(Lease.Periodicity.values)
