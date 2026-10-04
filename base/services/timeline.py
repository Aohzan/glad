"""Dated values of many objects, loaded at once and read back as of any date."""

import datetime
from bisect import bisect_right
from collections import defaultdict
from collections.abc import Iterable
from decimal import Decimal


class DatedValues:
    """Values of several objects over time, read back as of any date.

    Built from ``(object id, date, value)`` rows sorted by object then date, so
    a whole history table is read with one query instead of one query per
    object and per date. Dates are compared as stored: read a ``DateField``
    history with dates and a ``DateTimeField`` one with datetimes.
    """

    def __init__(self, rows: Iterable[tuple[int, datetime.date, Decimal]]) -> None:
        self._dates: dict[int, list[datetime.date]] = defaultdict(list)
        self._values: dict[int, list[Decimal]] = defaultdict(list)
        for object_id, date, value in rows:
            self._dates[object_id].append(date)
            self._values[object_id].append(value)

    def at(self, object_id: int, date: datetime.date) -> Decimal | None:
        """Last value of *object_id* dated on or before *date*, None without any."""
        dates = self._dates.get(object_id)
        if not dates:
            return None
        index = bisect_right(dates, date)
        return self._values[object_id][index - 1] if index else None
