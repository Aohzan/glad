"""Freeze the LMNP liasse of one year into JSON, and read it back."""

import dataclasses
import datetime
import re
from decimal import Decimal
from typing import Any

from django.db import models
from django.utils import timezone
from django.utils.functional import Promise
from moneyed import Money

from property.services.lmnp_rules import RULES_VERSION
from property.services.tax_lmnp import (
    get_accounting_data,
    get_amortization_table,
    get_lmnp_checklist,
)

# Frozen money amounts are strings with exactly two decimals ("1234.56").
_MONEY_RE = re.compile(r"^-?\d+\.\d{2}$")
_CENTS = Decimal("0.01")


def freeze(value: Any) -> Any:
    """Convert a computation result into JSON-serialisable data.

    Decimal and Money become strings with two decimals (exact), dates become
    ISO strings, lazy translations become plain strings, model instances become
    ``{"id", "name"}`` dicts and dict keys become strings.
    """
    if isinstance(value, Money):
        return freeze(value.amount)
    if isinstance(value, Decimal):
        return f"{value.quantize(_CENTS):f}"
    if isinstance(value, bool | int | float | str) or value is None:
        return value
    if isinstance(value, Promise):
        return str(value)
    if isinstance(value, datetime.datetime | datetime.date):
        return value.isoformat()
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return freeze(dataclasses.asdict(value))
    if isinstance(value, models.Model):
        return {"id": value.pk, "name": str(value)}
    if isinstance(value, dict):
        return {str(k): freeze(v) for k, v in value.items()}
    if isinstance(value, list | tuple | set | frozenset):
        return [freeze(v) for v in value]
    return str(value)


def thaw(value: Any) -> Any:
    """Turn frozen money strings back into Decimal so templates can compare them."""
    if isinstance(value, str):
        return Decimal(value) if _MONEY_RE.match(value) else value
    if isinstance(value, dict):
        return {k: thaw(v) for k, v in value.items()}
    if isinstance(value, list):
        return [thaw(v) for v in value]
    return value


def build_snapshot_payload(properties: list, year: int) -> dict:
    """Compute and freeze everything shown on the LMNP dashboard for ``year``."""
    return freeze(
        {
            "fiscal_year": year,
            "rules_version": RULES_VERSION,
            "generated_at": timezone.now(),
            "properties": [
                {
                    "id": p.pk,
                    "name": p.name,
                    "buying_date": p.buying_date,
                    "lmnp_start_date": p.lmnp_start_date,
                    "amortization_start_date": p.amortization_start_date,
                }
                for p in properties
            ],
            "accounting": get_accounting_data(properties, year),
            "checklist": get_lmnp_checklist(properties, year),
            "amortization": {
                p.pk: [
                    {k: v for k, v in row.items() if k != "source_transactions"}
                    for row in get_amortization_table(p.pk, year)
                ]
                for p in properties
            },
        }
    )


def create_snapshot(properties: list, year: int, notes: str = "", user=None):
    """Compute, freeze and store the liasse of ``year`` for ``properties``."""
    from property.models import LmnpDeclarationSnapshot

    snapshot = LmnpDeclarationSnapshot.objects.create(
        fiscal_year=year,
        rules_version=RULES_VERSION,
        property_names=[p.name for p in properties],
        data=build_snapshot_payload(properties, year),
        notes=notes,
        created_by=user if getattr(user, "pk", None) else None,
    )
    snapshot.properties.set(properties)
    return snapshot
