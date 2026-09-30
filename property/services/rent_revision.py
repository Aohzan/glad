"""Yearly rent revision of residential leases with the IRL (loi du 6 juillet 1989).

The rent (charges excluded) can be revised once a year, on the lease anniversary,
by at most the yearly change of the rent reference index (IRL) of the quarter
named in the lease: ``new rent = rent × IRL(quarter, year) / IRL(quarter, year - 1)``.
The landlord has one year to claim a revision, after which that year is lost;
the revision is not retroactive, and the rent of F and G rated housing is frozen.
"""

import datetime
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from dateutil.relativedelta import relativedelta
from django.db import transaction
from moneyed import Money

from base.models import EconomicIndex, EconomicIndexValue
from property.models import Lease, PropertyLedgerEntry
from property.models.ledger import ManagementCategory
from property.services.energy import rent_increase_allowed

CENT = Decimal("0.01")
#: The IRL of a quarter is published about 15 days after its end.
_PUBLICATION_DELAY = relativedelta(months=3, days=15)
_REVISABLE_STATUSES = (Lease.Status.ACTIVE, Lease.Status.NOTICE_PERIOD)
_REVISABLE_TYPES = (Lease.LeaseType.EMPTY, Lease.LeaseType.FURNISHED)


def next_revision_date(lease: Lease, today: datetime.date) -> datetime.date:
    """First lease anniversary after the last revision that can still be claimed.

    Anniversaries more than a year before *today* are skipped: their revision
    is lost.
    """
    since = lease.last_rent_revision_date or lease.start_date
    one_year_ago = today - relativedelta(years=1)
    years = max(1, since.year - lease.start_date.year)
    candidate = lease.start_date + relativedelta(years=years)
    while candidate <= since or candidate < one_year_ago:
        years += 1
        candidate = lease.start_date + relativedelta(years=years)
    return candidate


def irl_for_revision(
    quarter: int, revision_date: datetime.date
) -> EconomicIndexValue | None:
    """Latest IRL of *quarter* published on or before *revision_date*."""
    candidates = EconomicIndexValue.objects.filter(
        index=EconomicIndex.IRL, period__lte=revision_date
    ).order_by("-period")
    for value in candidates:
        if value.quarter != quarter:
            continue
        published_on = value.published_on or value.period + _PUBLICATION_DELAY
        if published_on <= revision_date:
            return value
    return None


@dataclass(frozen=True)
class RentRevision:
    """The next revision of a lease rent."""

    lease: Lease
    due_date: datetime.date
    today: datetime.date
    new_index: EconomicIndexValue | None
    #: IRL of the same quarter one year before ``new_index``, when stored.
    previous_index: EconomicIndexValue | None
    frozen: bool

    @property
    def is_due(self) -> bool:
        """True once the anniversary is reached."""
        return self.due_date <= self.today

    @property
    def default_effective_date(self) -> datetime.date:
        """The anniversary, or today for a late claim (it is not retroactive)."""
        return max(self.due_date, self.today)

    @property
    def reference_value(self) -> Decimal | None:
        """IRL the change is measured from.

        The IRL of the same quarter one year earlier when known (so that a
        lost revision is not caught up), else the lease reference value.
        """
        if self.previous_index is not None:
            return self.previous_index.value
        return self.lease.irl_reference_value

    @property
    def status(self) -> str:
        """``frozen``, ``missing_reference``, ``missing_index`` or ``ready``."""
        if self.frozen:
            return "frozen"
        if not self.lease.irl_reference_quarter:
            return "missing_reference"
        if self.new_index is None:
            return "missing_index"
        if not self.reference_value:
            return "missing_reference"
        return "ready"

    @property
    def new_rent(self) -> Money | None:
        """Revised rent (charges excluded), None when it cannot be computed."""
        if self.status != "ready":
            return None
        assert self.new_index is not None
        assert self.reference_value is not None
        rent = self.lease.rent_amount
        amount = rent.amount * self.new_index.value / self.reference_value
        # The rent can only follow the index up: a lower index keeps the rent.
        amount = max(rent.amount, amount).quantize(CENT, rounding=ROUND_HALF_UP)
        return Money(amount, rent.currency)

    @property
    def increase(self) -> Money | None:
        """Increase of the rent, None when it cannot be computed."""
        new_rent = self.new_rent
        return None if new_rent is None else new_rent - self.lease.rent_amount


def get_rent_revision(
    lease: Lease, today: datetime.date | None = None
) -> RentRevision | None:
    """Next IRL revision of a residential lease, None when not applicable."""
    if lease.status not in _REVISABLE_STATUSES or lease.lease_type not in (
        _REVISABLE_TYPES
    ):
        return None
    today = today or datetime.date.today()
    due_date = next_revision_date(lease, today)
    if lease.end_date and lease.end_date < due_date:
        return None
    quarter = lease.irl_reference_quarter
    new_index = irl_for_revision(quarter, due_date) if quarter else None
    previous_index = None
    if new_index is not None:
        previous_index = EconomicIndexValue.objects.filter(
            index=EconomicIndex.IRL,
            period=new_index.period - relativedelta(years=1),
        ).first()
    return RentRevision(
        lease=lease,
        due_date=due_date,
        today=today,
        new_index=new_index,
        previous_index=previous_index,
        frozen=not rent_increase_allowed(lease.property.dpe_rating),
    )


def _first_occurrence_from(
    entry: PropertyLedgerEntry, start: datetime.date
) -> datetime.date | None:
    for occurrence in entry.generate_occurrences(
        end_date=start + datetime.timedelta(days=400)
    ):
        occurrence_date = occurrence.get("occurrence_date") or occurrence["date"]
        if occurrence_date >= start:
            return occurrence_date
    return None


def _update_rent_series(
    lease: Lease, old_rent: Money, new_rent: Money, effective_date: datetime.date
) -> int:
    """Split the recurring rent entries of *lease* so that they use *new_rent*.

    Only series whose amount is the old rent, or the old rent plus charges, are
    updated; the others are left for the user to adjust.
    """
    charges = lease.charges_amount
    new_amounts = {
        old_rent.amount: new_rent,
        (old_rent + charges).amount: new_rent + charges,
    }
    entries = PropertyLedgerEntry.objects.filter(
        lease=lease,
        management_category=ManagementCategory.RENT_COLLECTED.value,
        entry_date__lte=effective_date,
    ).exclude(recurrence_type=PropertyLedgerEntry.NONE)
    updated = 0
    for entry in entries:
        new_amount = new_amounts.get(entry.amount.amount)
        if new_amount is None or (
            entry.recurrence_end_date and entry.recurrence_end_date < effective_date
        ):
            continue
        split_date = _first_occurrence_from(entry, effective_date)
        if split_date is None:
            continue
        previous_end = entry.recurrence_end_date
        entry.recurrence_end_date = split_date - datetime.timedelta(days=1)
        entry.save(update_fields=["recurrence_end_date"])
        entry.pk = None
        entry.id = None
        entry._state.adding = True
        entry.amount = new_amount
        entry.entry_date = split_date
        entry.recurrence_end_date = previous_end
        entry.save()
        updated += 1
    return updated


def apply_rent_revision(
    revision: RentRevision, effective_date: datetime.date | None = None
) -> int:
    """Apply *revision* to the lease and its rent series; return the series updated.

    *effective_date* defaults to the anniversary, or to today when the
    revision is claimed late: it then only applies from the claim. It can
    never be earlier than the anniversary.
    """
    new_rent = revision.new_rent
    if new_rent is None:
        raise ValueError("The rent revision cannot be computed.")
    assert revision.new_index is not None
    effective_date = max(
        effective_date or revision.default_effective_date, revision.due_date
    )
    lease = revision.lease
    old_rent = lease.rent_amount
    with transaction.atomic():
        updated = _update_rent_series(lease, old_rent, new_rent, effective_date)
        lease.rent_amount = new_rent
        lease.irl_reference_value = revision.new_index.value
        lease.last_rent_revision_date = revision.due_date
        lease.save(
            update_fields=[
                "rent_amount",
                "irl_reference_value",
                "last_rent_revision_date",
                "updated_at",
            ]
        )
    return updated
