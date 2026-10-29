"""Rent schedule of a lease and the payment status of each period.

The rent and charges are recurring ledger entries linked to the lease: an
occurrence is paid once it is checked (``property.services.checks``), for the
amount actually received. A one-off rent or charges entry linked to the lease
(a catch-up payment, a prorated first rent) counts as paid in its month.
"""

import datetime
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from django.db import transaction
from django.utils.translation import gettext as _

from property.models import Lease, PropertyLedgerEntry
from property.models.ledger import ManagementCategory

RENT = ManagementCategory.RENT_COLLECTED.value
CHARGES = ManagementCategory.CHARGES_COLLECTED.value

#: Months covered by one payment of each lease periodicity.
PERIOD_MONTHS = {Lease.Periodicity.MONTHLY: 1, Lease.Periodicity.QUARTERLY: 3}
_RECURRENCE = {
    Lease.Periodicity.MONTHLY: PropertyLedgerEntry.RecurrenceType.MONTHLY,
    Lease.Periodicity.QUARTERLY: PropertyLedgerEntry.RecurrenceType.QUARTERLY,
}
#: The periods due within this many days are shown as upcoming.
AHEAD_DAYS = 40

PAID = "paid"
PARTIAL = "partial"
UNPAID = "unpaid"
UPCOMING = "upcoming"


def _month(day: datetime.date) -> datetime.date:
    return day.replace(day=1)


@dataclass
class Period:
    """What was due and paid for one rent period of a lease."""

    start: datetime.date
    months: int
    today: datetime.date
    due_date: datetime.date | None = None
    rent: Decimal = Decimal(0)
    charges: Decimal = Decimal(0)
    paid: Decimal = Decimal(0)
    paid_date: datetime.date | None = None
    #: (entry, scheduled date) of the occurrences still to check.
    unchecked: list[tuple[PropertyLedgerEntry, datetime.date]] = field(
        default_factory=list
    )

    @property
    def end(self) -> datetime.date:
        return self.start + relativedelta(months=self.months, days=-1)

    @property
    def key(self) -> str:
        return f"{self.start:%Y-%m}"

    @property
    def expected(self) -> Decimal:
        return self.rent + self.charges

    @property
    def balance(self) -> Decimal:
        """Amount still owed (negative when overpaid)."""
        return self.expected - self.paid

    @property
    def status(self) -> str:
        if self.paid >= self.expected:
            return PAID
        if self.due_date is None or self.due_date > self.today:
            return UPCOMING
        return PARTIAL if self.paid else UNPAID

    @property
    def days_late(self) -> int:
        if self.status not in (PARTIAL, UNPAID) or self.due_date is None:
            return 0
        return (self.today - self.due_date).days


def rent_entries(lease: Lease):
    """Rent and charges entries of *lease*."""
    return PropertyLedgerEntry.objects.filter(
        lease=lease,
        flow_type=PropertyLedgerEntry.FlowType.INCOME,
        management_category__in=(RENT, CHARGES),
    )


def has_schedule(lease: Lease) -> bool:
    return (
        rent_entries(lease)
        .exclude(recurrence_type=PropertyLedgerEntry.RecurrenceType.NONE)
        .exists()
    )


def first_due_date(lease: Lease) -> datetime.date:
    """First payment day on or after the start of *lease*."""
    due = lease.start_date.replace(day=lease.payment_day)
    if due < lease.start_date:
        due += relativedelta(months=1)
    return due


def create_rent_schedule(lease: Lease) -> list[PropertyLedgerEntry]:
    """Recurring rent and charges entries of *lease*, from its first due date."""
    common = {
        "property": lease.property,
        "lease": lease,
        "flow_type": PropertyLedgerEntry.FlowType.INCOME,
        "entry_date": first_due_date(lease),
        "recurrence_type": _RECURRENCE[lease.periodicity],
        "recurrence_end_date": lease.end_date,
        "third_party": lease.name,
    }
    amounts = [(RENT, lease.rent_amount, _("Rent"))]
    if lease.charges_amount.amount > 0:
        amounts.append((CHARGES, lease.charges_amount, _("Charges")))
    with transaction.atomic():
        return [
            PropertyLedgerEntry.objects.create(
                management_category=category,
                amount=amount,
                description=description,
                **common,
            )
            for category, amount, description in amounts
        ]


def lease_periods(lease: Lease, today: datetime.date | None = None) -> list[Period]:
    """Every period of *lease* up to the next due date, newest first."""
    today = today or datetime.date.today()
    months = PERIOD_MONTHS.get(lease.periodicity, 1)
    periods: dict[datetime.date, Period] = {}

    def period_of(day: datetime.date) -> Period:
        start = _month(day)
        if start not in periods:
            periods[start] = Period(start=start, months=months, today=today)
        return periods[start]

    horizon = today + datetime.timedelta(days=AHEAD_DAYS)
    entries = rent_entries(lease).prefetch_related("exceptions")
    for entry in entries:
        for occurrence in entry.generate_occurrences(end_date=horizon):
            if not occurrence["is_recurring"]:
                # A one-off payment, for the period it refers to.
                day = entry.reference_period or entry.entry_date
                period = period_of(day)
                period.paid += occurrence["amount"].amount
                period.paid_date = max(
                    filter(None, (period.paid_date, entry.entry_date))
                )
                continue
            scheduled = occurrence["occurrence_date"]
            period = period_of(scheduled)
            period.due_date = min(filter(None, (period.due_date, scheduled)))
            planned = (
                entry.amount if occurrence["is_checked"] else occurrence["amount"]
            ).amount
            if entry.management_category == CHARGES:
                period.charges += planned
            else:
                period.rent += planned
            if occurrence["is_checked"]:
                period.paid += occurrence["amount"].amount
                period.paid_date = max(
                    filter(None, (period.paid_date, occurrence["date"]))
                )
            else:
                period.unchecked.append((entry, scheduled))
    return sorted(periods.values(), key=lambda p: p.start, reverse=True)


def arrears(periods: list[Period]) -> Decimal:
    """Amount still owed on the periods already due."""
    return sum(
        (p.balance for p in periods if p.status in (PARTIAL, UNPAID)), Decimal(0)
    )


def period_of_month(periods: list[Period], month: datetime.date) -> Period | None:
    """The period starting in the month of *month*, if any."""
    start = _month(month)
    return next((p for p in periods if p.start == start), None)


def summarize(by_lease: dict[int, list[Period]], today: datetime.date) -> dict:
    """Rent due and received this month, and the arrears, for the dashboard."""
    totals: dict[str, Decimal] = defaultdict(Decimal)
    for periods in by_lease.values():
        current = period_of_month(periods, today)
        if current is not None:
            totals["expected"] += current.expected
            totals["received"] += current.paid
        totals["arrears"] += arrears(periods)
    return {key: totals[key] for key in ("expected", "received", "arrears")}
