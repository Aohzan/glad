"""Figures of the rental dashboard."""

import datetime
from dataclasses import dataclass
from decimal import Decimal

from django.db.models import Q

from property.models import Lease, ManagementMandate
from rental.services.compliance import Check, documents_by_lease, issues, lease_checks
from rental.services.payments import Period, lease_periods, period_of_month

#: Statuses of the leases followed by the rental management.
CURRENT_STATUSES = (
    Lease.Status.UPCOMING,
    Lease.Status.ACTIVE,
    Lease.Status.NOTICE_PERIOD,
)
#: Number of rent payments in a month for each periodicity.
_PER_MONTH = {
    Lease.Periodicity.MONTHLY: Decimal(1),
    Lease.Periodicity.QUARTERLY: Decimal(1) / 3,
}
OCCUPANCY_DAYS = 365


@dataclass
class LeaseRow:
    lease: Lease
    checks: list[Check]
    mandate: object | None
    periods: list[Period]
    today: datetime.date

    @property
    def current_period(self) -> Period | None:
        return period_of_month(self.periods, self.today)

    @property
    def issues(self) -> list[Check]:
        return issues(self.checks)


def current_leases():
    """Leases that are upcoming, running or under notice, on active properties."""
    return (
        Lease.objects.filter(property__is_active=True, status__in=CURRENT_STATUSES)
        .select_related("property")
        .prefetch_related(
            "parties", "property__mandates", "property__ownerships__user__profile"
        )
        .order_by("property__name", "start_date")
    )


def lease_rows(today: datetime.date) -> list[LeaseRow]:
    """Current leases with their checklist; leases under mandate are not checked."""
    leases = list(current_leases())
    self_managed = [lease for lease in leases if lease.mandate_on(today) is None]
    documents = documents_by_lease(self_managed)
    return [
        LeaseRow(
            lease=lease,
            checks=(
                lease_checks(lease, documents[lease.pk], today)
                if lease.pk in documents
                else []
            ),
            mandate=lease.mandate_on(today),
            periods=lease_periods(lease, today) if lease.pk in documents else [],
            today=today,
        )
        for lease in leases
    ]


def monthly_rent_roll(leases) -> Decimal:
    """Rent and charges due in a month by the running leases."""
    return sum(
        (
            lease.total_rent().amount * _PER_MONTH[lease.periodicity]
            for lease in leases
            if lease.status != Lease.Status.UPCOMING
        ),
        Decimal(0),
    ).quantize(Decimal("0.01"))


def _covered_days(periods: list[tuple[datetime.date, datetime.date]]) -> int:
    """Number of distinct days covered by the inclusive *periods*."""
    days: set[int] = set()
    for start, end in periods:
        days.update(range(start.toordinal(), end.toordinal() + 1))
    return len(days)


def occupancy_rate(today: datetime.date) -> Decimal | None:
    """Share of the last 365 days the self-managed properties were let, in %.

    A property counts from the start of its first lease (or the window start),
    so that the time before it was first let is not counted as vacancy.
    Properties under a management mandate today are left out.
    """
    window_start = today - datetime.timedelta(days=OCCUPANCY_DAYS - 1)
    managed = ManagementMandate.objects.filter(start_date__lte=today).filter(
        Q(end_date__isnull=True) | Q(end_date__gte=today)
    )
    leases = (
        Lease.objects.filter(property__is_active=True, start_date__lte=today)
        .exclude(property__in=managed.values("property"))
        .values_list("property_id", "start_date", "end_date")
    )
    first_start: dict[int, datetime.date] = {}
    periods: dict[int, list[tuple[datetime.date, datetime.date]]] = {}
    for property_id, start, end in leases:
        first_start[property_id] = min(start, first_start.get(property_id, start))
        if end is None or end >= window_start:
            periods.setdefault(property_id, []).append(
                (max(start, window_start), min(end or today, today))
            )
    if not periods:
        return None
    occupied = sum(_covered_days(spans) for spans in periods.values())
    available = sum(
        (today - max(window_start, first_start[property_id])).days + 1
        for property_id in periods
    )
    return (Decimal(occupied) * 100 / available).quantize(Decimal("0.1"))
