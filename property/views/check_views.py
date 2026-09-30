"""Views for checking (reconciling) occurrences of recurring ledger entries."""

import datetime
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

from django.contrib import messages
from django.db import transaction
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from moneyed import Money

from property.models import Property
from property.services.checks import (
    PendingOccurrence,
    check_all_up_to,
    check_occurrence,
    delete_occurrence,
    pending_occurrences,
    uncheck_occurrence,
)
from property.views.crud_views import _get_entry_and_occurrence

# Keeps the bulk form well below Django's DATA_UPLOAD_MAX_NUMBER_FIELDS (1000).
MAX_ROWS = 100

ACTION_SAVE = "save"
ACTION_CHECK_ALL = "check_all"


def _parse_date(value: str | None) -> datetime.date | None:
    try:
        return datetime.date.fromisoformat(value or "")
    except ValueError:
        return None


def _parse_amount(value: str | None) -> Decimal | None:
    try:
        amount = Decimal((value or "").strip().replace(",", ".").replace(" ", ""))
    except InvalidOperation:
        return None
    return amount if amount.is_finite() else None


def _validate_actual_values(
    raw_date: str | None, raw_amount: str | None, currency: str
) -> tuple[datetime.date | None, Money | None, str | None]:
    """Validate the actual date/amount inputs; return (date, amount, error)."""
    actual_date = _parse_date(raw_date)
    if actual_date is None:
        return None, None, str(_("Invalid actual date."))
    if actual_date > datetime.date.today():
        return None, None, str(_("The actual date cannot be in the future."))
    amount = _parse_amount(raw_amount)
    if amount is None or amount <= 0:
        return None, None, str(_("The actual amount must be positive."))
    return actual_date, Money(amount.quantize(Decimal("0.01")), currency), None


@dataclass
class _CheckRow:
    """A pending occurrence as displayed in the bulk checking table."""

    pending: PendingOccurrence
    actual_date: str
    actual_amount: str
    is_checked: bool = False
    is_deleted: bool = False
    error: str | None = None


def _selected_property(value: str | None) -> Property | None:
    if not value or not value.isdigit():
        return None
    return Property.objects.filter(pk=int(value), is_active=True).first()


def _checks_url(property_obj: Property | None) -> str:
    url = reverse("property:checks")
    if property_obj is not None:
        url += "?" + urlencode({"property": property_obj.pk})
    return url


def _build_rows(
    pending: list[PendingOccurrence], data: dict | None = None
) -> list[_CheckRow]:
    """Build table rows, pre-filled with planned values or with posted values."""
    rows = []
    for p in pending:
        row = _CheckRow(
            pending=p,
            actual_date=p.planned_date.isoformat(),
            actual_amount=f"{p.planned_amount.amount:.2f}",
        )
        if data is not None:
            row.actual_date = data.get(f"date_{p.key}", row.actual_date)
            row.actual_amount = data.get(f"amount_{p.key}", row.actual_amount)
            row.is_checked = bool(data.get(f"check_{p.key}"))
            row.is_deleted = bool(data.get(f"delete_{p.key}"))
        rows.append(row)
    return rows


def _save_rows(request: HttpRequest, rows: list[_CheckRow]) -> bool:
    """Validate and apply the checked/deleted rows; return True when saved."""
    to_check: list[tuple[_CheckRow, datetime.date, Money]] = []
    to_delete: list[_CheckRow] = []
    has_errors = False
    for row in rows:
        if row.is_checked and row.is_deleted:
            row.error = str(_("An entry cannot be both checked and deleted."))
        elif row.is_checked:
            actual_date, actual_amount, row.error = _validate_actual_values(
                row.actual_date,
                row.actual_amount,
                str(row.pending.planned_amount.currency),
            )
            if row.error is None:
                assert actual_date is not None
                assert actual_amount is not None
                to_check.append((row, actual_date, actual_amount))
        elif row.is_deleted:
            to_delete.append(row)
        has_errors = has_errors or row.error is not None

    if has_errors:
        messages.error(request, _("Please correct the errors below."))
        return False
    if not to_check and not to_delete:
        messages.info(request, _("No entry was selected."))
        return True

    with transaction.atomic():
        for row, actual_date, actual_amount in to_check:
            check_occurrence(
                row.pending.entry, row.pending.planned_date, actual_date, actual_amount
            )
        for row in to_delete:
            delete_occurrence(row.pending.entry, row.pending.planned_date)
    messages.success(
        request,
        _("{checked} entry(ies) checked, {deleted} occurrence(s) deleted.").format(
            checked=len(to_check), deleted=len(to_delete)
        ),
    )
    return True


def occurrence_checks(request: HttpRequest) -> HttpResponse:
    """List unchecked occurrences of recurring entries and check them in bulk."""
    source = request.POST if request.method == "POST" else request.GET
    property_obj = _selected_property(source.get("property"))
    pending = pending_occurrences(property_obj=property_obj)
    shown = pending[:MAX_ROWS]
    rows = _build_rows(shown)

    if request.method == "POST":
        action = request.POST.get("action")
        if action == ACTION_CHECK_ALL:
            up_to = _parse_date(request.POST.get("up_to"))
            if up_to is None:
                messages.error(request, _("Invalid date."))
            else:
                count = check_all_up_to(
                    min(up_to, datetime.date.today()), property_obj=property_obj
                )
                messages.success(
                    request,
                    _("{count} entry(ies) checked.").format(count=count),
                )
            return redirect(_checks_url(property_obj))
        if action == ACTION_SAVE:
            rows = _build_rows(shown, request.POST)
            if _save_rows(request, rows):
                return redirect(_checks_url(property_obj))
        else:
            messages.error(request, _("Invalid action."))
            return redirect(_checks_url(property_obj))

    context = {
        "rows": rows,
        "total_count": len(pending),
        "hidden_count": max(len(pending) - MAX_ROWS, 0),
        "properties": Property.objects.filter(is_active=True).order_by("name"),
        "selected_property": property_obj,
        "today": datetime.date.today(),
        "action_save": ACTION_SAVE,
        "action_check_all": ACTION_CHECK_ALL,
    }
    return render(request, "property/occurrence_checks.html", context)


def _cashflow_redirect(property_pk: int) -> HttpResponseRedirect:
    return HttpResponseRedirect(
        reverse("property:detail", kwargs={"pk": property_pk}) + "#cashflow-panel"
    )


def check_ledger_entry_occurrence(
    request: HttpRequest,
    property_pk: int,
    entry_pk: int,
    occurrence_date: str,
) -> HttpResponse:
    """Check a single occurrence from the cash flow table. Only accepts POST."""
    if request.method != "POST":
        messages.error(request, _("Invalid request method."))
        return redirect("property:detail", pk=property_pk)

    _property_obj, entry, occ_date, error = _get_entry_and_occurrence(
        request, property_pk, entry_pk, occurrence_date
    )
    if error:
        return error
    assert entry is not None
    assert occ_date is not None

    actual_date, actual_amount, error_message = _validate_actual_values(
        request.POST.get("actual_date"),
        request.POST.get("actual_amount"),
        str(entry.amount.currency),
    )
    if error_message:
        messages.error(request, error_message)
    else:
        check_occurrence(entry, occ_date, actual_date, actual_amount)
        messages.success(request, _("Entry checked."))
    return _cashflow_redirect(property_pk)


def uncheck_ledger_entry_occurrence(
    request: HttpRequest,
    property_pk: int,
    entry_pk: int,
    occurrence_date: str,
) -> HttpResponse:
    """Revert a checked occurrence to unchecked. Only accepts POST."""
    if request.method != "POST":
        messages.error(request, _("Invalid request method."))
        return redirect("property:detail", pk=property_pk)

    _property_obj, entry, occ_date, error = _get_entry_and_occurrence(
        request, property_pk, entry_pk, occurrence_date
    )
    if error:
        return error
    assert entry is not None
    assert occ_date is not None

    uncheck_occurrence(entry, occ_date)
    messages.success(request, _("Entry unchecked."))
    return _cashflow_redirect(property_pk)
