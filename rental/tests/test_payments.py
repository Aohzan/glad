"""Tests for the rent schedule and the payment status of the periods."""

import datetime
from decimal import Decimal

import pytest
from moneyed import Money

from property.models import Lease, PropertyLedgerEntry, PropertyLedgerEntryException
from property.services.checks import (
    check_all_up_to,
    check_occurrence,
    pending_occurrences,
)
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
    schedule_start,
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


def test_schedule_start():
    """The schedule starts in the start month, even before the lease starts."""
    lease = Lease(start_date=datetime.date(2026, 7, 15), payment_day=5)
    assert schedule_start(lease) == datetime.date(2026, 7, 5)
    lease.payment_day = 20
    assert schedule_start(lease) == datetime.date(2026, 7, 20)


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
    assert set(Lease.PERIOD_MONTHS) == set(Lease.Periodicity.values)


@pytest.mark.django_db
def test_rent_paid_before_the_due_date(lease):
    today = datetime.date.today()
    due = today + datetime.timedelta(days=1)
    while due.day > 28:
        due += datetime.timedelta(days=1)
    lease.start_date = datetime.date(due.year - 1, due.month, 1)
    lease.payment_day = due.day
    lease.save()
    rent, charges = create_rent_schedule(lease)
    check_occurrence(rent, due, today)
    check_occurrence(charges, due, today)
    period = period_of_month(lease_periods(lease, today), due)
    assert period is not None
    assert (period.status, period.paid_date) == (PAID, today)


@pytest.mark.django_db
def test_first_month_is_prorated(lease):
    """A lease starting on 2 November expects 29/30 of the November rent."""
    lease.start_date = datetime.date(2026, 11, 2)
    lease.payment_day = 5
    lease.save()
    rent, charges = create_rent_schedule(lease)
    today = datetime.date(2026, 12, 20)

    november = period_of_month(lease_periods(lease, today), datetime.date(2026, 11, 1))
    assert november is not None
    assert (november.rent, november.charges) == (Decimal("773.33"), Decimal("48.33"))
    assert november.expected == Decimal("821.66")

    # Receiving the prorated amounts pays the month in full.
    check_occurrence(
        rent, datetime.date(2026, 11, 5), actual_amount=Money(Decimal("773.33"), "EUR")
    )
    check_occurrence(
        charges,
        datetime.date(2026, 11, 5),
        actual_amount=Money(Decimal("48.33"), "EUR"),
    )
    periods = lease_periods(lease, today)
    november = period_of_month(periods, datetime.date(2026, 11, 1))
    assert november is not None
    assert november.status == PAID
    assert november.balance == 0
    # December is a full month.
    december = period_of_month(periods, datetime.date(2026, 12, 1))
    assert december is not None
    assert december.expected == Decimal(850)


@pytest.mark.django_db
def test_last_month_is_prorated(lease):
    """A lease ending on 15 April expects half of the April rent."""
    lease.start_date = datetime.date(2026, 1, 1)
    lease.end_date = datetime.date(2026, 4, 15)
    lease.payment_day = 1
    lease.save()
    create_rent_schedule(lease)

    april = period_of_month(
        lease_periods(lease, datetime.date(2026, 5, 1)), datetime.date(2026, 4, 1)
    )
    assert april is not None
    assert (april.rent, april.charges) == (Decimal(400), Decimal(25))


@pytest.fixture
def mid_month_lease(lease):
    """A lease starting on 15 July, after its payment day."""
    lease.start_date = datetime.date(2026, 7, 15)
    lease.payment_day = 5
    lease.save()
    return lease, *create_rent_schedule(lease)


@pytest.mark.django_db
def test_first_rent_due_on_moving_in(mid_month_lease):
    """A lease starting after its payment day expects a prorated first rent."""
    lease, rent, _charges = mid_month_lease
    assert rent.entry_date == datetime.date(2026, 7, 5)

    july = period_of_month(
        lease_periods(lease, datetime.date(2026, 7, 10)), datetime.date(2026, 7, 1)
    )
    assert july is not None
    # 17 of the 31 days of July, due on moving in.
    assert (july.rent, july.charges) == (Decimal("438.71"), Decimal("27.42"))
    assert july.due_date == datetime.date(2026, 7, 15)
    assert july.status == UPCOMING


@pytest.mark.django_db
def test_checks_propose_the_prorated_rent(mid_month_lease):
    """The entries to check propose the prorated amount of a partial month."""
    lease, rent, charges = mid_month_lease
    PropertyLedgerEntryException.objects.create(
        parent_entry=charges,
        occurrence_date=datetime.date(2026, 7, 5),
        amount_override=Money(Decimal(30), "EUR"),
    )

    pending = pending_occurrences(
        property_obj=lease.property, up_to=datetime.date(2026, 8, 31)
    )
    amounts = {(p.entry.pk, p.planned_date): p.planned_amount.amount for p in pending}
    assert amounts == {
        (rent.pk, datetime.date(2026, 7, 5)): Decimal("438.71"),
        # An amount set on the occurrence is kept.
        (charges.pk, datetime.date(2026, 7, 5)): Decimal(30),
        (rent.pk, datetime.date(2026, 8, 5)): Decimal(800),
        (charges.pk, datetime.date(2026, 8, 5)): Decimal(50),
    }


@pytest.mark.django_db
def test_check_all_records_the_prorated_rent(mid_month_lease):
    lease, rent, _charges = mid_month_lease
    assert rent.planned_amount(datetime.date(2026, 7, 5)).amount == Decimal("438.71")
    assert rent.planned_amount(datetime.date(2026, 8, 5)) == rent.amount

    check_all_up_to(datetime.date(2026, 7, 31), property_obj=lease.property)
    july = period_of_month(
        lease_periods(lease, datetime.date(2026, 8, 1)), datetime.date(2026, 7, 1)
    )
    assert july is not None
    assert (july.status, july.paid, july.balance) == (
        PAID,
        Decimal("466.13"),
        Decimal(0),
    )


@pytest.mark.django_db
def test_full_rent_received_for_a_partial_month(mid_month_lease):
    """A full rent checked on a partial month is kept as received."""
    lease, rent, _charges = mid_month_lease
    check_occurrence(
        rent, datetime.date(2026, 7, 5), actual_amount=Money(Decimal(800), "EUR")
    )
    # The full amount needs no override: a checked occurrence keeps it.
    assert rent.exceptions.get().amount_override is None
    july = period_of_month(
        lease_periods(lease, datetime.date(2026, 8, 1)), datetime.date(2026, 7, 1)
    )
    assert july is not None
    assert (july.paid, july.expected) == (Decimal(800), Decimal("466.13"))


@pytest.mark.django_db
def test_check_without_amount_records_the_prorated_rent(mid_month_lease):
    _lease, rent, _charges = mid_month_lease
    check_occurrence(rent, datetime.date(2026, 7, 5))
    assert rent.exceptions.get().amount_override == Money(Decimal("438.71"), "EUR")
    # The next one, a full month, needs no override.
    check_occurrence(rent, datetime.date(2026, 8, 5))
    assert rent.exceptions.get(occurrence_date="2026-08-05").amount_override is None


@pytest.mark.django_db
def test_first_rent_to_check_is_due_on_moving_in(mid_month_lease):
    lease, rent, _charges = mid_month_lease
    pending = pending_occurrences(
        property_obj=lease.property, up_to=datetime.date(2026, 8, 31)
    )
    due = {p.planned_date: p.due_date for p in pending if p.entry == rent}
    assert due == {
        datetime.date(2026, 7, 5): datetime.date(2026, 7, 15),
        datetime.date(2026, 8, 5): datetime.date(2026, 8, 5),
    }


@pytest.mark.django_db
def test_no_rent_after_the_lease_ends(lease):
    """A notice ends the lease, not its schedule: nothing is due after it."""
    lease.start_date = datetime.date(2026, 1, 1)
    lease.payment_day = 1
    lease.save()
    rent, _charges = create_rent_schedule(lease)
    lease.end_date = datetime.date(2026, 4, 15)
    lease.save()
    rent.refresh_from_db()
    occurrences = rent.generate_occurrences(end_date=datetime.date(2026, 7, 31))
    assert [o["date"].month for o in occurrences] == [1, 2, 3, 4]
    assert occurrences[-1]["amount"] == Money(Decimal(400), "EUR")


@pytest.mark.django_db
def test_last_month_before_the_payment_day(lease):
    """A lease ending on 10 April, paid on the 15th, expects 10/30 of April."""
    lease.start_date = datetime.date(2026, 1, 1)
    lease.end_date = datetime.date(2026, 4, 10)
    lease.payment_day = 15
    lease.save()
    rent, _charges = create_rent_schedule(lease)
    assert rent.recurrence_end_date == datetime.date(2026, 4, 15)

    april = period_of_month(
        lease_periods(lease, datetime.date(2026, 5, 1)), datetime.date(2026, 4, 1)
    )
    assert april is not None
    assert (april.rent, april.charges) == (Decimal("266.67"), Decimal("16.67"))
    # Due on leaving, not after the lease ended.
    assert april.due_date == datetime.date(2026, 4, 10)
