"""Types of notification the users can subscribe to.

Each app declares its types in a ``notifications`` module (loaded when the
notifications app is ready) with ``register``. A type either has a ``check``,
run once a day for the household, or is sent by the code when something
happens (``notifications.services.notify``).
"""

import datetime
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

from django.core.exceptions import ValidationError
from django.utils.functional import Promise
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _

#: Groups of the settings page, in display order.
GROUPS: dict[str, str | Promise] = {
    "finance": _("Finance"),
    "tax": _("Tax"),
    "property": _("Properties"),
    "rental": _("Rental management"),
    "app": _("Application"),
}

_MONTH_DAY = re.compile(r"^(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$")


@dataclass(frozen=True)
class Param:
    """A setting of a notification type (threshold, number of days, date…)."""

    key: str
    label: str | Promise
    default: Any
    #: ``int``, ``choice`` or ``monthday`` (``MM-DD``, a date every year).
    kind: str = "int"
    min_value: int | None = None
    max_value: int | None = None
    choices: tuple[tuple[Any, str | Promise], ...] = ()
    help_text: str | Promise = ""

    def clean(self, raw: Any) -> Any:
        """Convert a submitted value; raise ``ValidationError`` when invalid."""
        if self.kind == "int":
            try:
                value = int(raw)
            except TypeError, ValueError:
                raise ValidationError(gettext("Enter a whole number.")) from None
            if self.min_value is not None and value < self.min_value:
                raise ValidationError(
                    gettext("Enter a number of at least %(min)d.")
                    % {"min": self.min_value}
                )
            if self.max_value is not None and value > self.max_value:
                raise ValidationError(
                    gettext("Enter a number of at most %(max)d.")
                    % {"max": self.max_value}
                )
            return value
        if self.kind == "monthday":
            value = str(raw).strip()
            if not _MONTH_DAY.match(value):
                raise ValidationError(gettext("Enter a date as MM-DD."))
            try:  # a leap year accepts 02-29
                datetime.date(2024, int(value[:2]), int(value[3:]))
            except ValueError:
                raise ValidationError(gettext("Enter a date as MM-DD.")) from None
            return value
        allowed = {str(choice): choice for choice, _label in self.choices}
        if str(raw) not in allowed:
            raise ValidationError(gettext("Select a valid choice."))
        return allowed[str(raw)]


@dataclass(frozen=True)
class Event:
    """Something worth notifying, found by a check or reported by the code.

    ``key`` identifies the event within its type: an event already notified
    to a user is not notified again.
    """

    key: str
    title: str
    body: str = ""
    url: str = ""
    level: str = "info"


Check = Callable[[dict[str, Any], datetime.date], Iterable[Event]]


@dataclass(frozen=True)
class NotificationType:
    """A kind of notification a user can enable and tune."""

    key: str
    group: str
    label: str | Promise
    description: str | Promise
    check: Check | None = None
    params: tuple[Param, ...] = field(default_factory=tuple)
    default_enabled: bool = True
    #: Notify the same event again after this many days (None: only once).
    renotify_days: int | None = None

    def default_params(self) -> dict[str, Any]:
        return {param.key: param.default for param in self.params}

    def resolve_params(self, stored: dict[str, Any] | None) -> dict[str, Any]:
        """Stored values completed with the defaults, invalid ones dropped."""
        params = self.default_params()
        for param in self.params:
            if stored and param.key in stored:
                try:
                    params[param.key] = param.clean(stored[param.key])
                except ValidationError:
                    pass
        return params

    def base_key(self, event: Event) -> str:
        """Identity of *event* for a user, whatever the day."""
        return f"{self.key}:{event.key}"[:240]

    def dedup_key(self, event: Event, today: datetime.date) -> str:
        """Identity of a notification of *event*: dated when it renotifies."""
        if self.renotify_days:
            return f"{self.base_key(event)}@{today.isoformat()}"
        return self.base_key(event)


_TYPES: dict[str, NotificationType] = {}


def register(notification_type: NotificationType) -> NotificationType:
    """Declare a notification type (idempotent)."""
    if notification_type.group not in GROUPS:
        raise ValueError(f"Unknown group {notification_type.group}")
    _TYPES[notification_type.key] = notification_type
    return notification_type


def get_type(key: str) -> NotificationType:
    return _TYPES[key]


def types() -> list[NotificationType]:
    """Every type, by group then in declaration order."""
    order = list(GROUPS)
    return sorted(_TYPES.values(), key=lambda t: order.index(t.group))


def grouped_types() -> list[tuple[str | Promise, list[NotificationType]]]:
    """The types under the label of their group, empty groups left out."""
    result = []
    for group, label in GROUPS.items():
        members = [t for t in types() if t.group == group]
        if members:
            result.append((label, members))
    return result
