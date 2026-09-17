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


def days360(start: datetime.date, end: datetime.date) -> int:
    """Return the number of days between two dates on a 30/360 basis.

    This mirrors the spreadsheet ``DAYS360(start, end)`` function with its default
    US (NASD) method, the convention used by French accountants for the first-year
    prorata temporis of linear amortization: every month counts 30 days and a full
    year counts 360 days.

    Rules (US/NASD method):
      - a start date on the last day of February is moved to the 30th;
      - a start day of 31 is moved to the 30th;
      - an end day of 31 is moved to the 30th when the (adjusted) start day is 30.
    """
    start_day, end_day = start.day, end.day
    if start.month == 2 and start_day == calendar.monthrange(start.year, 2)[1]:
        if end.month == 2 and end_day == calendar.monthrange(end.year, 2)[1]:
            end_day = 30
        start_day = 30
    if start_day == 31:
        start_day = 30
    if end_day == 31 and start_day == 30:
        end_day = 30
    return (
        (end.year - start.year) * 360
        + (end.month - start.month) * 30
        + (end_day - start_day)
    )
