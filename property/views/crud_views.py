"""CRUD views for ledger entries, tenants, leases, managers, and mandates."""

import datetime

from django.contrib import messages
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from base.views import get_object_or_redirect
from property.forms import (
    LeaseForm,
    ManagementMandateForm,
    PropertyLedgerEntryEditForm,
    PropertyLedgerEntryOccurrenceForm,
    PropertyLoanAnnualStatementForm,
)
from property.models import (
    Lease,
    ManagementMandate,
    Property,
    PropertyLedgerEntry,
    PropertyLedgerEntryException,
    PropertyLoan,
    PropertyLoanAnnualStatement,
    PropertyValue,
)

# ─── Helpers ─────────────────────────────────────────────────────────────────


def _get_property_or_redirect(
    request: HttpRequest,
    property_pk: int,
) -> tuple:
    return get_object_or_redirect(
        request,
        Property,
        property_pk,
        error_message=str(_("Property not found.")),
        redirect_url="property:index",
    )


def _get_related_or_redirect(
    request: HttpRequest,
    *,
    model,
    related_name: str,
    object_pk: int,
    property_obj: Property,
) -> tuple:
    return get_object_or_redirect(
        request,
        model,
        object_pk,
        error_message=str(_("%(name)s not found.") % {"name": related_name}),
        redirect_url="property:detail",
        redirect_kwargs={"pk": property_obj.pk},
        property=property_obj,
    )


# ─── Property valuation ───────────────────────────────────────────────────────


def delete_property_valuation(
    request: HttpRequest, property_pk: int, valuation_pk: int
) -> HttpResponse:
    if request.method != "POST":
        messages.error(request, _("Invalid request method."))
        return redirect("property:detail", pk=property_pk)

    property_obj, response = _get_property_or_redirect(request, property_pk)
    if response:
        return response
    assert property_obj is not None

    valuation = PropertyValue.objects.filter(
        pk=valuation_pk, property=property_obj
    ).first()
    if not valuation:
        messages.error(request, _("Valuation not found."))
        return redirect("property:detail", pk=property_pk)

    valuation.delete()
    messages.success(request, _("Property valuation deleted successfully."))
    return HttpResponseRedirect(
        reverse("property:detail", kwargs={"pk": property_pk}) + "#projection-panel"
    )


# ─── Ledger entry CRUD ────────────────────────────────────────────────────────


def edit_ledger_entry(
    request: HttpRequest, property_pk: int, entry_pk: int
) -> HttpResponse:
    """Edit a ledger entry (income or expense)."""
    property_obj, response = _get_property_or_redirect(request, property_pk)
    if response:
        return response
    assert property_obj is not None

    entry, response = _get_related_or_redirect(
        request,
        model=PropertyLedgerEntry,
        related_name=str(_("Entry")),
        object_pk=entry_pk,
        property_obj=property_obj,
    )
    if response:
        return response
    assert entry is not None

    if request.method == "POST":
        form = PropertyLedgerEntryEditForm(
            request.POST, instance=entry, property_obj=property_obj
        )
        if form.is_valid():
            form.save()
            messages.success(request, _("Entry updated successfully."))
            return HttpResponseRedirect(
                reverse("property:detail", kwargs={"pk": property_pk})
                + "#cashflow-panel"
            )
        messages.error(request, _("Please correct the errors below."))
    else:
        form = PropertyLedgerEntryEditForm(instance=entry, property_obj=property_obj)

    context = {
        "property": property_obj,
        "entry": entry,
        "form": form,
    }
    return render(request, "property/edit_entry.html", context)


def delete_ledger_entry(
    request: HttpRequest, property_pk: int, entry_pk: int
) -> HttpResponse:
    """Delete a ledger entry. Only accepts POST."""
    if request.method != "POST":
        messages.error(request, _("Invalid request method."))
        return redirect("property:detail", pk=property_pk)

    property_obj, response = _get_property_or_redirect(request, property_pk)
    if response:
        return response
    assert property_obj is not None

    entry, response = _get_related_or_redirect(
        request,
        model=PropertyLedgerEntry,
        related_name=str(_("Entry")),
        object_pk=entry_pk,
        property_obj=property_obj,
    )
    if response:
        return response
    assert entry is not None

    entry.delete()
    messages.success(request, _("Entry deleted successfully."))
    return HttpResponseRedirect(
        reverse("property:detail", kwargs={"pk": property_pk}) + "#cashflow-panel"
    )


# ─── Occurrence edit / delete (single occurrence of a recurring entry) ────────

_OCCURRENCE_DATE_FORMAT = "%Y-%m-%d"

RECURRENCE_SCOPE_THIS = "this"
RECURRENCE_SCOPE_FUTURE = "future"
RECURRENCE_SCOPE_ALL = "all"
_VALID_SCOPES = {RECURRENCE_SCOPE_THIS, RECURRENCE_SCOPE_FUTURE, RECURRENCE_SCOPE_ALL}


def _parse_occurrence_date(occurrence_date_str: str) -> datetime.date | None:
    """Parse a YYYY-MM-DD string into a date, returning None on failure."""
    try:
        return datetime.datetime.strptime(
            occurrence_date_str, _OCCURRENCE_DATE_FORMAT
        ).date()
    except ValueError:
        return None


def _is_valid_occurrence(
    entry: PropertyLedgerEntry, occurrence_date: datetime.date
) -> bool:
    """Return True if occurrence_date is a real occurrence of the entry."""
    return any(occ["date"] == occurrence_date for occ in entry.generate_occurrences())


def edit_ledger_entry_occurrence(
    request: HttpRequest,
    property_pk: int,
    entry_pk: int,
    occurrence_date: str,
) -> HttpResponse:
    """Edit a single occurrence (or this-and-future) of a recurring ledger entry."""
    property_obj, response = _get_property_or_redirect(request, property_pk)
    if response:
        return response
    assert property_obj is not None

    entry, response = _get_related_or_redirect(
        request,
        model=PropertyLedgerEntry,
        related_name=str(_("Entry")),
        object_pk=entry_pk,
        property_obj=property_obj,
    )
    if response:
        return response
    assert entry is not None

    occ_date = _parse_occurrence_date(occurrence_date)
    if occ_date is None or not _is_valid_occurrence(entry, occ_date):
        messages.error(request, _("Invalid occurrence date."))
        return redirect("property:detail", pk=property_pk)

    # Load existing exception if any
    existing_exc = PropertyLedgerEntryException.objects.filter(
        parent_entry=entry, occurrence_date=occ_date
    ).first()

    if request.method == "POST":
        scope = request.POST.get("scope", RECURRENCE_SCOPE_THIS)
        if scope not in _VALID_SCOPES:
            messages.error(request, _("Invalid scope."))
            return redirect("property:detail", pk=property_pk)

        if scope == RECURRENCE_SCOPE_ALL:
            return redirect(
                reverse(
                    "property:edit_entry",
                    kwargs={"property_pk": property_pk, "entry_pk": entry_pk},
                )
            )

        form = PropertyLedgerEntryOccurrenceForm(request.POST, instance=existing_exc)
        if form.is_valid():
            if scope == RECURRENCE_SCOPE_THIS:
                exc = form.save(commit=False)
                exc.parent_entry = entry
                exc.occurrence_date = occ_date
                exc.is_deleted = False
                exc.save()
                messages.success(request, _("Occurrence updated successfully."))

            elif scope == RECURRENCE_SCOPE_FUTURE:
                one_day = datetime.timedelta(days=1)
                entry.recurrence_end_date = occ_date - one_day
                entry.save(update_fields=["recurrence_end_date"])

                cleaned = form.cleaned_data
                new_amount = cleaned.get("amount_override") or entry.amount
                new_description = (
                    cleaned.get("description_override")
                    if cleaned.get("description_override") is not None
                    else entry.description
                )
                new_notes = (
                    cleaned.get("notes_override")
                    if cleaned.get("notes_override") is not None
                    else entry.notes
                )

                PropertyLedgerEntry.objects.create(
                    property=property_obj,
                    lease=entry.lease,
                    flow_type=entry.flow_type,
                    amount=new_amount,
                    entry_date=occ_date,
                    reference_period=entry.reference_period,
                    management_category=entry.management_category,
                    description=new_description,
                    notes=new_notes,
                    recurrence_type=entry.recurrence_type,
                    recurrence_end_date=None,
                )
                messages.success(
                    request, _("Series updated from this occurrence onwards.")
                )

            return HttpResponseRedirect(
                reverse("property:detail", kwargs={"pk": property_pk})
                + "#cashflow-panel"
            )
        messages.error(request, _("Please correct the errors below."))
    else:
        form = PropertyLedgerEntryOccurrenceForm(instance=existing_exc)

    context = {
        "property": property_obj,
        "entry": entry,
        "occurrence_date": occ_date,
        "form": form,
        "scope_this": RECURRENCE_SCOPE_THIS,
        "scope_future": RECURRENCE_SCOPE_FUTURE,
        "scope_all": RECURRENCE_SCOPE_ALL,
    }
    return render(request, "property/edit_entry_occurrence.html", context)


def delete_ledger_entry_occurrence(
    request: HttpRequest,
    property_pk: int,
    entry_pk: int,
    occurrence_date: str,
) -> HttpResponse:
    """Show scope-selection page (GET) or delete a single occurrence (POST)."""
    property_obj, response = _get_property_or_redirect(request, property_pk)
    if response:
        return response
    assert property_obj is not None

    entry, response = _get_related_or_redirect(
        request,
        model=PropertyLedgerEntry,
        related_name=str(_("Entry")),
        object_pk=entry_pk,
        property_obj=property_obj,
    )
    if response:
        return response
    assert entry is not None

    occ_date = _parse_occurrence_date(occurrence_date)
    if occ_date is None or not _is_valid_occurrence(entry, occ_date):
        messages.error(request, _("Invalid occurrence date."))
        return redirect("property:detail", pk=property_pk)

    if request.method == "GET":
        context = {
            "property": property_obj,
            "entry": entry,
            "occurrence_date": occ_date,
            "scope_this": RECURRENCE_SCOPE_THIS,
            "scope_future": RECURRENCE_SCOPE_FUTURE,
            "scope_all": RECURRENCE_SCOPE_ALL,
        }
        return render(request, "property/delete_entry_occurrence.html", context)

    if request.method != "POST":
        messages.error(request, _("Invalid request method."))
        return redirect("property:detail", pk=property_pk)

    scope = request.POST.get("scope", RECURRENCE_SCOPE_THIS)
    if scope not in _VALID_SCOPES:
        messages.error(request, _("Invalid scope."))
        return redirect("property:detail", pk=property_pk)

    if scope == RECURRENCE_SCOPE_ALL:
        entry.delete()
        messages.success(request, _("Entry deleted successfully."))

    elif scope == RECURRENCE_SCOPE_THIS:
        PropertyLedgerEntryException.objects.update_or_create(
            parent_entry=entry,
            occurrence_date=occ_date,
            defaults={
                "is_deleted": True,
                "amount_override": None,
                "description_override": None,
                "notes_override": None,
            },
        )
        messages.success(request, _("Occurrence deleted successfully."))

    elif scope == RECURRENCE_SCOPE_FUTURE:
        one_day = datetime.timedelta(days=1)
        entry.recurrence_end_date = occ_date - one_day
        entry.save(update_fields=["recurrence_end_date"])
        PropertyLedgerEntryException.objects.filter(
            parent_entry=entry, occurrence_date__gte=occ_date
        ).delete()
        messages.success(request, _("Series truncated from this occurrence onwards."))

    return HttpResponseRedirect(
        reverse("property:detail", kwargs={"pk": property_pk}) + "#cashflow-panel"
    )


# ─── Lease CRUD ───────────────────────────────────────────────────────────────


def edit_lease(
    request: HttpRequest, property_pk: int, lease_pk: int | None = None
) -> HttpResponse:
    """Create or edit a lease for a property."""
    property_obj = get_object_or_404(Property, pk=property_pk)
    lease = (
        get_object_or_404(Lease, pk=lease_pk, property=property_obj)
        if lease_pk
        else None
    )

    if request.method == "POST":
        form = LeaseForm(request.POST, instance=lease)
        if form.is_valid():
            created = form.save(commit=False)
            created.property = property_obj
            created.save()
            messages.success(request, _("Lease saved."))
            return HttpResponseRedirect(
                reverse("property:detail", kwargs={"pk": property_pk}) + "#leases-panel"
            )
        messages.error(request, _("Please correct the errors below."))
    else:
        form = LeaseForm(instance=lease)

    return render(
        request,
        "property/edit_lease.html",
        {"property": property_obj, "lease": lease, "form": form},
    )


def delete_lease(request: HttpRequest, property_pk: int, lease_pk: int) -> HttpResponse:
    """Delete a lease. Only accepts POST."""
    if request.method != "POST":
        messages.error(request, _("Invalid request method."))
        return redirect("property:detail", pk=property_pk)

    property_obj = get_object_or_404(Property, pk=property_pk)
    lease = get_object_or_404(Lease, pk=lease_pk, property=property_obj)
    lease.delete()
    messages.success(request, _("Lease deleted successfully."))
    return HttpResponseRedirect(
        reverse("property:detail", kwargs={"pk": property_pk}) + "#leases-panel"
    )


# ─── ManagementMandate CRUD ───────────────────────────────────────────────────
def edit_mandate(
    request: HttpRequest, property_pk: int, mandate_pk: int | None = None
) -> HttpResponse:
    """Create or edit a management mandate for a property."""
    property_obj = get_object_or_404(Property, pk=property_pk)
    mandate = (
        get_object_or_404(ManagementMandate, pk=mandate_pk, property=property_obj)
        if mandate_pk
        else None
    )

    if request.method == "POST":
        form = ManagementMandateForm(request.POST, instance=mandate)
        if form.is_valid():
            created = form.save(commit=False)
            created.property = property_obj
            created.save()
            messages.success(request, _("Mandate saved."))
            return HttpResponseRedirect(
                reverse("property:detail", kwargs={"pk": property_pk})
                + "#mandate-panel"
            )
        messages.error(request, _("Please correct the errors below."))
    else:
        form = ManagementMandateForm(instance=mandate)

    return render(
        request,
        "property/edit_mandate.html",
        {"property": property_obj, "mandate": mandate, "form": form},
    )


def delete_mandate(
    request: HttpRequest, property_pk: int, mandate_pk: int
) -> HttpResponse:
    """Delete a management mandate. Only accepts POST."""
    if request.method != "POST":
        messages.error(request, _("Invalid request method."))
        return redirect("property:detail", pk=property_pk)

    property_obj = get_object_or_404(Property, pk=property_pk)
    mandate = get_object_or_404(ManagementMandate, pk=mandate_pk, property=property_obj)
    mandate.delete()
    messages.success(request, _("Mandate deleted successfully."))
    return HttpResponseRedirect(
        reverse("property:detail", kwargs={"pk": property_pk}) + "#mandate-panel"
    )


# ─── Loan annual statements CRUD ─────────────────────────────────────────────


def edit_loan_annual_statement(
    request: HttpRequest,
    property_pk: int,
    loan_pk: int,
    statement_pk: int | None = None,
) -> HttpResponse:
    """Create or edit a PropertyLoanAnnualStatement (bank-provided interest/insurance)."""
    property_obj = get_object_or_404(Property, pk=property_pk)
    loan = get_object_or_404(PropertyLoan, pk=loan_pk, property=property_obj)

    if statement_pk is not None:
        statement = get_object_or_404(
            PropertyLoanAnnualStatement, pk=statement_pk, loan=loan
        )
    else:
        statement = None

    if request.method == "POST":
        form = PropertyLoanAnnualStatementForm(
            request.POST, instance=statement, loan=loan
        )
        if form.is_valid():
            obj = form.save(commit=False)
            obj.loan = loan
            obj.save()
            messages.success(request, _("Annual statement saved."))
            return HttpResponseRedirect(
                reverse("property:detail", kwargs={"pk": property_pk}) + "#loans-panel"
            )
        messages.error(request, _("Please correct the errors below."))
    else:
        form = PropertyLoanAnnualStatementForm(instance=statement, loan=loan)

    return render(
        request,
        "property/edit_loan_annual_statement.html",
        {"property": property_obj, "loan": loan, "form": form, "statement": statement},
    )


def delete_loan_annual_statement(
    request: HttpRequest,
    property_pk: int,
    loan_pk: int,
    statement_pk: int,
) -> HttpResponse:
    """Delete a PropertyLoanAnnualStatement. Only accepts POST."""
    if request.method != "POST":
        messages.error(request, _("Invalid request method."))
        return redirect("property:detail", pk=property_pk)

    property_obj = get_object_or_404(Property, pk=property_pk)
    loan = get_object_or_404(PropertyLoan, pk=loan_pk, property=property_obj)
    statement = get_object_or_404(
        PropertyLoanAnnualStatement, pk=statement_pk, loan=loan
    )
    statement.delete()
    messages.success(request, _("Annual statement deleted."))
    return HttpResponseRedirect(
        reverse("property:detail", kwargs={"pk": property_pk}) + "#loans-panel"
    )
