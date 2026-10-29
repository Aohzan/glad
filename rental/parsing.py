"""Reading the dates, amounts and amount lines of the rental forms."""

import datetime
from decimal import Decimal, InvalidOperation

from django.http import HttpRequest

CENT = Decimal("0.01")


def parse_date(value: str | None) -> datetime.date | None:
    try:
        return datetime.date.fromisoformat(value or "")
    except ValueError:
        return None


def parse_amount(value: str | None) -> Decimal | None:
    """An amount typed with a comma or a dot, None when invalid."""
    try:
        amount = Decimal((value or "").replace(",", ".").replace(" ", ""))
    except InvalidOperation:
        return None
    return amount.quantize(CENT) if amount.is_finite() else None


def parse_lines(request: HttpRequest, prefix: str) -> list[dict] | None:
    """The ``<prefix>_label`` / ``<prefix>_amount`` rows of a form.

    Empty rows are skipped; None when a row lacks a label or a valid amount.
    """
    rows = []
    labels = request.POST.getlist(f"{prefix}_label")
    amounts = request.POST.getlist(f"{prefix}_amount")
    for label, raw in zip(labels, amounts, strict=False):
        if not label.strip() and not raw.strip():
            continue
        amount = parse_amount(raw)
        if amount is None or not label.strip():
            return None
        rows.append({"label": label.strip()[:200], "amount": str(amount)})
    return rows
