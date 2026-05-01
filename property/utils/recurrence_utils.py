"""Recurrence helpers for generating dated occurrences of monetary entries."""

import datetime

from moneyed import Money

from property.utils.date_utils import add_months_safe, add_years_safe


def generate_recurring_occurrences(
    *,
    start_date: datetime.date,
    amount: Money,
    recurrence_type: str,
    recurrence_none: str,
    recurrence_monthly: str,
    recurrence_quarterly: str | None = None,
    recurrence_biannual: str | None = None,
    recurrence_yearly: str,
    recurrence_end_date: datetime.date | None = None,
    end_date: datetime.date | None = None,
) -> list[dict]:
    """Generate occurrences for a one-time or recurring monetary item."""
    if recurrence_type == recurrence_none:
        return [
            {
                "date": start_date,
                "amount": amount,
                "is_recurring": False,
            }
        ]

    occurrences = []
    current = start_date
    candidates = [d for d in [end_date, recurrence_end_date] if d is not None]
    max_date = min(candidates) if candidates else datetime.date.today()

    # Only process recurring types if valid
    valid_types = {recurrence_monthly, recurrence_yearly}
    if recurrence_quarterly:
        valid_types.add(recurrence_quarterly)
    if recurrence_biannual:
        valid_types.add(recurrence_biannual)
    is_valid_recurrence = recurrence_type in valid_types

    while current <= max_date:
        occurrences.append(
            {
                "date": current,
                "amount": amount,
                "is_recurring": is_valid_recurrence,
            }
        )

        if recurrence_type == recurrence_monthly:
            current = add_months_safe(current, 1)
            continue
        if recurrence_quarterly and recurrence_type == recurrence_quarterly:
            current = add_months_safe(current, 3)
            continue
        if recurrence_biannual and recurrence_type == recurrence_biannual:
            current = add_months_safe(current, 6)
            continue
        if recurrence_type == recurrence_yearly:
            current = add_years_safe(current, 1)
            continue
        break

    return (
        occurrences
        if occurrences
        else [
            {
                "date": start_date,
                "amount": amount,
                "is_recurring": False,
            }
        ]
    )
