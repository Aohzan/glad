"""Helpers shared by the notification checks of the apps."""

import datetime
import hashlib
from collections.abc import Iterator
from typing import Any

from django.utils.formats import date_format
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy, ngettext

from base.services.deadlines import deadlines_of
from notifications.registry import Check, Event, Param

#: A deadline missed by the daily check (scheduler down) is still notified
#: this many days afterwards.
LATE_DAYS = 7


def days_before_param(default: int) -> Param:
    return Param(
        key="days_before",
        label=gettext_lazy("Days before"),
        default=default,
        min_value=1,
        max_value=730,
        help_text=gettext_lazy("How long before the date to be notified."),
    )


def short_key(*parts: Any) -> str:
    """Stable short identifier of an event made of *parts*."""
    text = "|".join(str(part) for part in parts)
    return hashlib.sha1(text.encode()).hexdigest()[:20]


def when(date: datetime.date, today: datetime.date) -> str:
    """``on 12 March 2027 (in 30 days)``-like text for a date."""
    days = (date - today).days
    formatted = date_format(date, "DATE_FORMAT")
    if days > 0:
        relative = ngettext("in %(days)d day", "in %(days)d days", days) % {
            "days": days
        }
    elif days == 0:
        relative = _("today")
    else:
        relative = ngettext("%(days)d day ago", "%(days)d days ago", -days) % {
            "days": -days
        }
    return _("On %(date)s (%(relative)s)") % {"date": formatted, "relative": relative}


def deadline_check(*kinds: str, late_days: int = LATE_DAYS) -> Check:
    """A check notifying the dashboard deadlines of *kinds* ``days_before``.

    A deadline passed for less than *late_days* is still notified (once).
    """

    def check(params: dict[str, Any], today: datetime.date) -> Iterator[Event]:
        for deadline in deadlines_of(set(kinds), today):
            if not -late_days <= deadline.days_left <= params["days_before"]:
                continue
            yield Event(
                key=short_key(
                    deadline.kind, deadline.url, deadline.title, deadline.date
                ),
                title=f"{deadline.detail} — {deadline.title}",
                body=when(deadline.date, today),
                url=deadline.url,
                level="warning" if deadline.days_left <= 7 else "info",
            )

    return check


def month_day(value: str, year: int) -> datetime.date:
    """The date of a ``MM-DD`` setting in *year* (29 February → 28 when needed)."""
    month, day = (int(part) for part in value.split("-"))
    try:
        return datetime.date(year, month, day)
    except ValueError:
        return datetime.date(year, month, 28)
