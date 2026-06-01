"""Date helper utilities for property calculations."""

import calendar
import datetime


def add_months_safe(base_date: datetime.date, months: int = 1) -> datetime.date:
    """Add months to a date while clamping to the month last day when needed."""
    total_month = (base_date.year * 12 + (base_date.month - 1)) + months
    year = total_month // 12
    month = (total_month % 12) + 1
    day = min(base_date.day, calendar.monthrange(year, month)[1])
    return datetime.date(year, month, day)


def add_years_safe(base_date: datetime.date, years: int = 1) -> datetime.date:
    """Add years to a date while keeping leap years safe."""
    try:
        return base_date.replace(year=base_date.year + years)
    except ValueError:
        return base_date.replace(month=2, day=28, year=base_date.year + years)


def month_start(value: datetime.date) -> datetime.date:
    """Return the first day of the month for a date."""
    return value.replace(day=1)


def month_end(value: datetime.date) -> datetime.date:
    """Return the last day of the month for a date."""
    last_day = calendar.monthrange(value.year, value.month)[1]
    return value.replace(day=last_day)


def iter_month_starts(
    start_month: datetime.date,
    end_month: datetime.date,
) -> list[datetime.date]:
    """Return first-of-month dates from start to end (inclusive)."""
    current = month_start(start_month)
    limit = month_start(end_month)
    months: list[datetime.date] = []
    while current <= limit:
        months.append(current)
        current = add_months_safe(current, 1)
    return months
