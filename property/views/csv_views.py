"""CSV import views for property ledger entries."""

import csv
import io
import logging

import dateparser
from django.contrib import messages
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext_lazy as _
from moneyed import Money

from property.forms import PropertyCSVImportForm
from property.models import Property, PropertyLedgerEntry

_LOGGER = logging.getLogger(__name__)

_REQUIRED_COLUMNS = {"date", "amount", "category", "description"}
_OPTIONAL_COLUMNS = {"notes", "reference_period"}

_SESSION_DATA_KEY = "property_csv_data"
_SESSION_HEADER_KEY = "property_csv_header"
_SESSION_PROPERTY_KEY = "property_csv_property_pk"


def _get_property_or_404(property_pk: int) -> Property:
    return get_object_or_404(Property, pk=property_pk)


def csv_import(request, property_pk: int):
    """Step 1: upload the CSV file. Preview is shown before confirmation."""
    property_obj = _get_property_or_404(property_pk)

    if request.method == "POST":
        form = PropertyCSVImportForm(request.POST, request.FILES)
        if form.is_valid():
            csv_file = request.FILES["csv_file"]
            try:
                raw = csv_file.read().decode("utf-8")
            except UnicodeDecodeError:
                messages.error(
                    request,
                    _("The file could not be decoded. Please use UTF-8 encoding."),
                )
                return render(
                    request,
                    "property/csv_import.html",
                    {"form": form, "property": property_obj},
                )

            reader = csv.reader(io.StringIO(raw))
            try:
                header = [col.strip() for col in next(reader)]
            except StopIteration:
                messages.error(request, _("The CSV file is empty."))
                return render(
                    request,
                    "property/csv_import.html",
                    {"form": form, "property": property_obj},
                )

            missing = _REQUIRED_COLUMNS - set(header)
            if missing:
                messages.error(
                    request,
                    _("CSV file is missing required columns: %(cols)s")
                    % {"cols": ", ".join(sorted(missing))},
                )
                return render(
                    request,
                    "property/csv_import.html",
                    {"form": form, "property": property_obj},
                )

            rows = list(reader)
            if not rows:
                messages.error(request, _("The CSV file contains no data rows."))
                return render(
                    request,
                    "property/csv_import.html",
                    {"form": form, "property": property_obj},
                )

            # Store in session for the confirmation step
            request.session[_SESSION_DATA_KEY] = rows
            request.session[_SESSION_HEADER_KEY] = header
            request.session[_SESSION_PROPERTY_KEY] = property_pk

            context = {
                "property": property_obj,
                "header": header,
                "preview_rows": rows[:5],
                "total_rows": len(rows),
                "valid_categories": [
                    (c.value, c.label) for c in PropertyLedgerEntry.ManagementCategory
                ],
            }
            return render(request, "property/csv_confirm.html", context)
    else:
        form = PropertyCSVImportForm()

    return render(
        request,
        "property/csv_import.html",
        {
            "form": form,
            "property": property_obj,
            "valid_categories": [
                (c.value, c.label) for c in PropertyLedgerEntry.ManagementCategory
            ],
        },
    )


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

    valid_categories = {c.value for c in PropertyLedgerEntry.ManagementCategory}
    income_categories = {c.value for c in PropertyLedgerEntry._INCOME_CATEGORIES}

    imported_count = 0
    error_rows = []

    def _col(row, name):
        idx = csv_header.index(name)
        return row[idx].strip() if idx < len(row) else ""

    with transaction.atomic():
        for row_index, row in enumerate(csv_data, start=2):  # row 1 is header
            try:
                raw_date = _col(row, "date")
                raw_amount = _col(row, "amount")
                raw_category = _col(row, "category")
                description = _col(row, "description")
                notes = _col(row, "notes") if "notes" in csv_header else ""
                raw_ref_period = (
                    _col(row, "reference_period")
                    if "reference_period" in csv_header
                    else ""
                )

                # Parse date
                parsed_date = dateparser.parse(raw_date)
                if not parsed_date:
                    error_rows.append(
                        (row_index, str(_("Invalid date: %(val)s") % {"val": raw_date}))
                    )
                    continue

                # Parse amount (supports both 1200.50 and European 1.200,50)
                clean_amount = "".join(
                    c for c in raw_amount if c.isdigit() or c in (".", ",", "-")
                )
                if "." in clean_amount and "," in clean_amount:
                    # Determine which is the decimal separator by position
                    if clean_amount.rfind(",") > clean_amount.rfind("."):
                        # European: 1.200,50 → thousands=dot, decimal=comma
                        clean_amount = clean_amount.replace(".", "").replace(",", ".")
                    else:
                        # US with comma thousands: 1,200.50 → remove commas
                        clean_amount = clean_amount.replace(",", "")
                elif "," in clean_amount:
                    clean_amount = clean_amount.replace(",", ".")
                try:
                    amount_val = float(clean_amount)
                except ValueError:
                    error_rows.append(
                        (
                            row_index,
                            str(_("Invalid amount: %(val)s") % {"val": raw_amount}),
                        )
                    )
                    continue

                if amount_val == 0:
                    error_rows.append((row_index, str(_("Amount must not be zero."))))
                    continue

                # Derive flow_type from sign
                flow_type = (
                    PropertyLedgerEntry.FlowType.INCOME
                    if amount_val > 0
                    else PropertyLedgerEntry.FlowType.EXPENSE
                )

                # Validate category
                if raw_category not in valid_categories:
                    error_rows.append(
                        (
                            row_index,
                            str(_("Unknown category: %(val)s") % {"val": raw_category}),
                        )
                    )
                    continue

                # Enforce category ↔ flow_type coherence
                if (
                    raw_category in income_categories
                    and flow_type != PropertyLedgerEntry.FlowType.INCOME
                ):
                    error_rows.append(
                        (
                            row_index,
                            str(
                                _("Category %(cat)s requires a positive amount.")
                                % {"cat": raw_category}
                            ),
                        )
                    )
                    continue
                if (
                    raw_category not in income_categories
                    and flow_type != PropertyLedgerEntry.FlowType.EXPENSE
                ):
                    error_rows.append(
                        (
                            row_index,
                            str(
                                _("Category %(cat)s requires a negative amount.")
                                % {"cat": raw_category}
                            ),
                        )
                    )
                    continue

                # Optional reference_period
                ref_period = None
                if raw_ref_period:
                    parsed_ref = dateparser.parse(raw_ref_period)
                    if parsed_ref:
                        ref_period = parsed_ref.date()

                PropertyLedgerEntry.objects.create(
                    property=property_obj,
                    flow_type=flow_type,
                    management_category=raw_category,
                    amount=Money(abs(amount_val), property_obj.currency),
                    entry_date=parsed_date.date(),
                    description=description,
                    notes=notes,
                    reference_period=ref_period,
                )
                imported_count += 1

            except Exception as exc:  # noqa: BLE001
                _LOGGER.exception("CSV import error on row %d: %s", row_index, exc)
                error_rows.append((row_index, str(exc)))

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
