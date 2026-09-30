"""Checking (reconciliation) of recurring ledger entry occurrences.

An occurrence of a recurring entry is "checked" once the user has verified that
the planned transfer actually happened. The state is stored on
``PropertyLedgerEntryException`` (one row per occurrence, keyed by the scheduled
date), alongside the optional actual date and amount.
"""

import datetime
from dataclasses import dataclass

from django.db import transaction
from moneyed import Money

from property.models import Property, PropertyLedgerEntry, PropertyLedgerEntryException

WARNING_AFTER_DAYS = 7
DANGER_AFTER_DAYS = 30

_KEY_DATE_FORMAT = "%Y%m%d"


@dataclass(frozen=True)
class PendingOccurrence:
    """An unchecked past occurrence of a recurring ledger entry."""

    entry: PropertyLedgerEntry
    planned_date: datetime.date
    planned_amount: Money

    @property
    def key(self) -> str:
        """Stable identifier used in form field names."""
        return f"{self.entry.pk}_{self.planned_date.strftime(_KEY_DATE_FORMAT)}"


def parse_occurrence_key(key: str) -> tuple[int, datetime.date] | None:
    """Parse a key built by ``PendingOccurrence.key``; return None when invalid."""
    entry_pk, sep, date_str = key.partition("_")
    if not sep or not entry_pk.isdigit():
        return None
    try:
        occ_date = datetime.datetime.strptime(date_str, _KEY_DATE_FORMAT).date()
    except ValueError:
        return None
    return int(entry_pk), occ_date


def _recurring_entries(property_obj: Property | None = None):
    """Recurring entries of active properties, ready for occurrence expansion."""
    qs = (
        PropertyLedgerEntry.objects.filter(property__is_active=True)
        .exclude(recurrence_type=PropertyLedgerEntry.RecurrenceType.NONE)
        .select_related("property", "lease")
        .prefetch_related("exceptions")
    )
    if property_obj is not None:
        qs = qs.filter(property=property_obj)
    return qs


def pending_occurrences(
    property_obj: Property | None = None,
    up_to: datetime.date | None = None,
) -> list[PendingOccurrence]:
    """Return unchecked occurrences scheduled up to ``up_to`` (default today), oldest first."""
    up_to = up_to or datetime.date.today()
    pending: list[PendingOccurrence] = []
    for entry in _recurring_entries(property_obj):
        for occ in entry.generate_occurrences():
            planned_date = occ.get("occurrence_date")
            if (
                planned_date is None
                or not occ["is_recurring"]
                or occ["is_checked"]
                or planned_date > up_to
            ):
                continue
            pending.append(
                PendingOccurrence(
                    entry=entry,
                    planned_date=planned_date,
                    planned_amount=occ["amount"],
                )
            )
    pending.sort(key=lambda p: (p.planned_date, p.entry.property.name, p.entry.pk))
    return pending


def pending_checks_summary() -> dict:
    """Summary for the dashboard alert: count, age of the oldest and alert level.

    ``level`` is "danger" when the oldest unchecked occurrence is more than
    DANGER_AFTER_DAYS old, "warning" when more than WARNING_AFTER_DAYS old,
    otherwise None (recent occurrences are not worth an alert yet).
    """
    today = datetime.date.today()
    pending = pending_occurrences(up_to=today)
    overdue = [p for p in pending if (today - p.planned_date).days > WARNING_AFTER_DAYS]
    if not overdue:
        return {"count": 0, "oldest_days": 0, "level": None}
    oldest_days = (today - overdue[0].planned_date).days
    level = "danger" if oldest_days > DANGER_AFTER_DAYS else "warning"
    return {"count": len(overdue), "oldest_days": oldest_days, "level": level}


def check_occurrence(
    entry: PropertyLedgerEntry,
    occurrence_date: datetime.date,
    actual_date: datetime.date | None = None,
    actual_amount: Money | None = None,
) -> PropertyLedgerEntryException:
    """Mark an occurrence as checked, recording its actual date and amount.

    The actual date is only stored when it differs from the scheduled date, and
    the amount override only when the amount differs from the entry amount.
    An existing amount override is kept when no amount is given.
    """
    exc, _created = PropertyLedgerEntryException.objects.get_or_create(
        parent_entry=entry, occurrence_date=occurrence_date
    )
    exc.is_checked = True
    exc.is_deleted = False
    exc.actual_date = (
        actual_date if actual_date and actual_date != occurrence_date else None
    )
    if actual_amount is not None:
        exc.amount_override = actual_amount if actual_amount != entry.amount else None
    exc.save()
    return exc


def uncheck_occurrence(
    entry: PropertyLedgerEntry, occurrence_date: datetime.date
) -> None:
    """Revert an occurrence to unchecked (the planned date applies again)."""
    PropertyLedgerEntryException.objects.filter(
        parent_entry=entry, occurrence_date=occurrence_date
    ).update(is_checked=False, actual_date=None)


def delete_occurrence(
    entry: PropertyLedgerEntry, occurrence_date: datetime.date
) -> None:
    """Hide a single occurrence of a recurring entry."""
    PropertyLedgerEntryException.objects.update_or_create(
        parent_entry=entry,
        occurrence_date=occurrence_date,
        defaults={
            "is_deleted": True,
            "is_checked": False,
            "actual_date": None,
            "amount_override": None,
            "description_override": None,
            "notes_override": None,
        },
    )


def check_all_up_to(up_to: datetime.date, property_obj: Property | None = None) -> int:
    """Mark every pending occurrence scheduled up to ``up_to`` as checked.

    Existing exceptions keep their overrides; returns the number of occurrences checked.
    """
    pending = pending_occurrences(property_obj=property_obj, up_to=up_to)
    if not pending:
        return 0
    with transaction.atomic():
        PropertyLedgerEntryException.objects.bulk_create(
            [
                PropertyLedgerEntryException(
                    parent_entry=p.entry,
                    occurrence_date=p.planned_date,
                    is_checked=True,
                )
                for p in pending
            ],
            update_conflicts=True,
            unique_fields=["parent_entry", "occurrence_date"],
            update_fields=["is_checked"],
        )
    return len(pending)
