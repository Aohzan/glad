"""Income & expenses report service for properties."""

import datetime
from dataclasses import dataclass
from decimal import Decimal

from django.db.models import Q, Sum
from moneyed import Money

from property.utils import generate_recurring_occurrences


@dataclass
class _OccurrenceEntry:
    """Virtual occurrence of a recurring ledger entry, used inside the report."""

    entry_date: datetime.date
    property: object
    flow_type: str
    management_category: str
    amount: Money
    description: str


def get_income_expense_report(
    property_ids: list[int],
    start_date: datetime.date | None,
    end_date: datetime.date | None,
) -> dict:
    """
    Compute income and expense totals for a set of properties over a date range.

    Recurring entries (monthly/yearly) are expanded: all occurrences that fall
    within [start_date, end_date] are counted, even when the entry's start date
    is before start_date.

    Returns:
        {
            "total_income": Decimal,
            "total_expenses": Decimal,
            "net": Decimal,
            "by_category": [
                {
                    "category": str,        # ManagementCategory value
                    "label": str,           # Human-readable label
                    "flow_type": str,       # "income" or "expense"
                    "total": Decimal,
                },
                ...
            ],
            "entries": list,  # sorted by entry_date
        }
    """
    from property.models import PropertyLedgerEntry

    base_filter = {"property_id__in": property_ids, "amount_currency": "EUR"}

    # ── Non-recurring entries within the date range ────────────────────────
    non_recurring_qs = PropertyLedgerEntry.objects.filter(
        **base_filter,
        recurrence_type=PropertyLedgerEntry.RecurrenceType.NONE,
    )
    if start_date:
        non_recurring_qs = non_recurring_qs.filter(entry_date__gte=start_date)
    if end_date:
        non_recurring_qs = non_recurring_qs.filter(entry_date__lte=end_date)

    # ── Recurring entries that overlap the date range ──────────────────────
    # An entry overlaps when its start_date <= end_date AND its recurrence
    # end_date (if set) >= start_date.
    recurring_qs = PropertyLedgerEntry.objects.filter(**base_filter).exclude(
        recurrence_type=PropertyLedgerEntry.RecurrenceType.NONE
    )
    if end_date:
        recurring_qs = recurring_qs.filter(entry_date__lte=end_date)
    if start_date:
        recurring_qs = recurring_qs.filter(
            Q(recurrence_end_date__gte=start_date) | Q(recurrence_end_date__isnull=True)
        )

    # Expand recurring entries into individual occurrences within [start, end]
    expanded_occurrences: list[_OccurrenceEntry] = []
    for entry in recurring_qs.select_related("property"):
        occurrences = generate_recurring_occurrences(
            start_date=entry.entry_date,
            amount=entry.amount,
            recurrence_type=entry.recurrence_type,
            recurrence_none=PropertyLedgerEntry.NONE,
            recurrence_monthly=PropertyLedgerEntry.MONTHLY,
            recurrence_yearly=PropertyLedgerEntry.YEARLY,
            recurrence_end_date=entry.recurrence_end_date,
            end_date=end_date,
        )
        for occ in occurrences:
            occ_date: datetime.date = occ["date"]
            if start_date and occ_date < start_date:
                continue
            if end_date and occ_date > end_date:
                continue
            expanded_occurrences.append(
                _OccurrenceEntry(
                    entry_date=occ_date,
                    property=entry.property,
                    flow_type=entry.flow_type,
                    management_category=entry.management_category,
                    amount=occ["amount"],
                    description=entry.description,
                )
            )

    # ── Aggregate totals ───────────────────────────────────────────────────
    income_total: Decimal = non_recurring_qs.filter(
        flow_type=PropertyLedgerEntry.FlowType.INCOME
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0")
    expenses_total: Decimal = non_recurring_qs.filter(
        flow_type=PropertyLedgerEntry.FlowType.EXPENSE
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0")
    for occ in expanded_occurrences:
        if occ.flow_type == PropertyLedgerEntry.FlowType.INCOME:
            income_total += occ.amount.amount
        else:
            expenses_total += occ.amount.amount

    # ── Category breakdown ─────────────────────────────────────────────────
    category_label_map = {
        choice[0]: choice[1]
        for choice in PropertyLedgerEntry.ManagementCategory.choices
    }

    # Seed with DB-aggregated non-recurring data
    category_totals: dict[tuple[str, str], Decimal] = {}
    for row in (
        non_recurring_qs.values("management_category", "flow_type")
        .annotate(total=Sum("amount"))
        .order_by("flow_type", "management_category")
    ):
        key = (row["management_category"], row["flow_type"])
        category_totals[key] = (category_totals.get(key) or Decimal("0")) + (
            row["total"] or Decimal("0")
        )

    # Add recurring occurrences
    for occ in expanded_occurrences:
        key = (occ.management_category, occ.flow_type)
        category_totals[key] = (
            category_totals.get(key) or Decimal("0")
        ) + occ.amount.amount

    category_rows: list[dict] = [
        {
            "category": cat,
            "label": str(category_label_map.get(cat, cat)),
            "flow_type": flow_type,
            "total": total,
        }
        for (cat, flow_type), total in sorted(
            category_totals.items(), key=lambda x: (x[0][1], x[0][0])
        )
    ]

    # ── Combined entries list (sorted by date) ─────────────────────────────
    non_recurring_list = list(
        non_recurring_qs.select_related("property").order_by("entry_date")
    )
    all_entries = sorted(
        non_recurring_list + expanded_occurrences,
        key=lambda e: e.entry_date,
    )

    return {
        "total_income": income_total,
        "total_expenses": expenses_total,
        "net": income_total - expenses_total,
        "by_category": category_rows,
        "entries": all_entries,
    }
