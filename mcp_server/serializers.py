"""Conversion of the values of the services into compact JSON for the model."""

import dataclasses
import datetime
import enum
from collections.abc import Iterable, Mapping
from decimal import Decimal
from typing import Any

from django.db import models
from django.utils.functional import Promise
from moneyed import Money


def decimal(value: Decimal) -> str:
    """At most 4 decimals, without trailing zeros: ``"1234.5"``."""
    return format(round(value, 4).normalize(), "f")


def money(value: Money | None) -> dict[str, str] | None:
    if value is None:
        return None
    return {"amount": decimal(value.amount), "currency": str(value.currency)}


def ref(obj: models.Model | None) -> dict[str, Any] | None:
    """A model instance as its id and label."""
    return None if obj is None else {"id": obj.pk, "label": str(obj)}


def to_json(value: Any) -> Any:
    """Recursively convert *value* to JSON-compatible data.

    Dataclasses keep their fields (not their properties), model instances
    become a ``ref``.
    """
    match value:
        case None | bool() | int() | float() | str():
            return value
        case Decimal():
            return decimal(value)
        case Money():
            return money(value)
        case datetime.date():
            return value.isoformat()
        case enum.Enum():
            return to_json(value.value)
        case Promise():
            return str(value)
        case models.Model():
            return ref(value)
        case Mapping():
            return {str(key): to_json(item) for key, item in value.items()}
        case _ if dataclasses.is_dataclass(value) and not isinstance(value, type):
            return {
                f.name: to_json(getattr(value, f.name))
                for f in dataclasses.fields(value)
            }
        case Iterable():
            return [to_json(item) for item in value]
    return str(value)
