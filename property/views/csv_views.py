"""CSV import views for property ledger entries."""

import logging

from django.contrib import messages
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext_lazy as _
from moneyed import Money

from property.forms import PropertyCSVImportForm
from property.models import Property, PropertyLedgerEntry
from property.services.ledger_csv import (
    COLUMN_ALIASES,
    LedgerCSVError,
    ai_prompt,
    parse_entries,
    read_rows,
    resolve_categories,
)

_LOGGER = logging.getLogger(__name__)

_SESSION_DATA_KEY = "property_csv_data"
_SESSION_HEADER_KEY = "property_csv_header"
_SESSION_PROPERTY_KEY = "property_csv_property_pk"


def _get_property_or_404(property_pk: int) -> Property:
    return get_object_or_404(Property, pk=property_pk)


def _valid_categories() -> list[tuple[str, str]]:
    return [(c.value, c.label) for c in PropertyLedgerEntry.ManagementCategory]


def csv_import(request, property_pk: int):
    """Step 1: upload the CSV file. Preview is shown before confirmation."""
    property_obj = _get_property_or_404(property_pk)
    context = {
        "property": property_obj,
        "valid_categories": _valid_categories(),
        "aliases": {
            column: [alias for alias in aliases if alias != column]
            for column, aliases in COLUMN_ALIASES.items()
        },
    }

    if request.method == "POST":
        form = PropertyCSVImportForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                header, rows = read_rows(request.FILES["csv_file"].read())
            except LedgerCSVError as error:
                messages.error(request, str(error))
                return render(
                    request, "property/csv_import.html", {**context, "form": form}
                )
            rows = resolve_categories(header, rows)

            # Store in session for the confirmation step
            request.session[_SESSION_DATA_KEY] = rows
            request.session[_SESSION_HEADER_KEY] = header
            request.session[_SESSION_PROPERTY_KEY] = property_pk

            return render(
                request,
                "property/csv_confirm.html",
                {
                    **context,
                    "header": header,
                    "preview_rows": rows[:5],
                    "total_rows": sum(
                        1 for row in rows if any(cell.strip() for cell in row)
                    ),
                },
            )
    else:
        form = PropertyCSVImportForm()

    return render(request, "property/csv_import.html", {**context, "form": form})


def csv_import_confirm(request, property_pk: int):
    """Step 2: process and persist the previously uploaded CSV data."""
    if request.method != "POST":
        raise Http404

    property_obj = _get_property_or_404(property_pk)

    csv_data = request.session.get(_SESSION_DATA_KEY)
    csv_header = request.session.get(_SESSION_HEADER_KEY)
    session_pk = request.session.get(_SESSION_PROPERTY_KEY)

    if not csv_data or not csv_header or session_pk != property_pk:
        messages.error(request, _("CSV import session expired. Please try again."))
        return redirect("property:csv_import", property_pk=property_pk)

    entries, error_rows = parse_entries(csv_header, csv_data)
    imported_count = 0
    with transaction.atomic():
        for entry in entries:
            try:
                PropertyLedgerEntry.objects.create(
                    property=property_obj,
                    flow_type=entry.flow_type,
                    management_category=entry.category,
                    amount=Money(entry.amount, property_obj.currency),
                    entry_date=entry.entry_date,
                    description=entry.description,
                    notes=entry.notes,
                    reference_period=entry.reference_period,
                )
                imported_count += 1
            except Exception as exc:
                _LOGGER.exception("CSV import error on row %d", entry.row)
                error_rows.append((entry.row, str(exc)))
    error_rows.sort()

    # Clean up session
    for key in (_SESSION_DATA_KEY, _SESSION_HEADER_KEY, _SESSION_PROPERTY_KEY):
        request.session.pop(key, None)

    if imported_count:
        messages.success(
            request,
            _("%(count)d entr%(plural)s imported successfully.")
            % {"count": imported_count, "plural": "ies" if imported_count > 1 else "y"},
        )
    if error_rows:
        messages.warning(
            request,
            _("%(count)d row(s) could not be imported.") % {"count": len(error_rows)},
        )
        for row_num, reason in error_rows:
            messages.warning(
                request,
                _("Row %(num)d: %(reason)s") % {"num": row_num, "reason": reason},
            )

    return redirect("property:detail", pk=property_pk)


def csv_ai_prompt(request, property_pk: int):
    """Prompt asking an AI to turn an export of transactions into an importable file."""
    property_obj = _get_property_or_404(property_pk)
    return render(
        request,
        "property/csv_ai_prompt.html",
        {"property": property_obj, "prompt": ai_prompt(property_obj)},
    )
