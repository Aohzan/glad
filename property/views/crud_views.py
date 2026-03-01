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
)
from property.models import (
    Lease,
    ManagementMandate,
    Property,
    PropertyLedgerEntry,
    PropertyLedgerEntryException,
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


def _get_entry_and_occurrence(
    request: HttpRequest,
    property_pk: int,
    entry_pk: int,
    occurrence_date: str,
) -> tuple:
    """Resolve property, entry and occurrence date; return (property_obj, entry, occ_date, error_response)."""
    property_obj, response = _get_property_or_redirect(request, property_pk)
    if response:
        return None, None, None, response
    assert property_obj is not None

    entry, response = _get_related_or_redirect(
        request,
        model=PropertyLedgerEntry,
        related_name=str(_("Entry")),
        object_pk=entry_pk,
        property_obj=property_obj,
    )
    if response:
        return None, None, None, response
    assert entry is not None

    occ_date = _parse_occurrence_date(occurrence_date)
    if occ_date is None or not _is_valid_occurrence(entry, occ_date):
        messages.error(request, _("Invalid occurrence date."))
        return None, None, None, redirect("property:detail", pk=property_pk)

    return property_obj, entry, occ_date, None


def edit_ledger_entry_occurrence(
    request: HttpRequest,
    property_pk: int,
    entry_pk: int,
    occurrence_date: str,
) -> HttpResponse:
    """Edit a single occurrence (or this-and-future) of a recurring ledger entry."""
    property_obj, entry, occ_date, error = _get_entry_and_occurrence(
        request, property_pk, entry_pk, occurrence_date
    )
    if error:
        return error
    assert property_obj is not None
    assert entry is not None
    assert occ_date is not None

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
    property_obj, entry, occ_date, error = _get_entry_and_occurrence(
        request, property_pk, entry_pk, occurrence_date
    )
    if error:
        return error
    assert property_obj is not None
    assert entry is not None
    assert occ_date is not None

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


# ─── Shared helpers for simple property-related CRUD ─────────────────────────


def _edit_property_related(
    request: HttpRequest,
    *,
    property_pk: int,
    model,
    object_pk: int | None,
    form_class,
    template: str,
    context_key: str,
    success_message: str,
    anchor: str,
) -> HttpResponse:
    """Shared create/edit logic for models that belong to a Property."""
    property_obj = get_object_or_404(Property, pk=property_pk)
    obj = (
        get_object_or_404(model, pk=object_pk, property=property_obj)
        if object_pk
        else None
    )

    if request.method == "POST":
        form = form_class(request.POST, instance=obj)
        if form.is_valid():
            created = form.save(commit=False)
            created.property = property_obj
            created.save()
            messages.success(request, success_message)
            return HttpResponseRedirect(
                reverse("property:detail", kwargs={"pk": property_pk}) + anchor
            )
        messages.error(request, _("Please correct the errors below."))
    else:
        form = form_class(instance=obj)

    return render(
        request,
        template,
        {"property": property_obj, context_key: obj, "form": form},
    )


def _delete_property_related(
    request: HttpRequest,
    *,
    property_pk: int,
    model,
    object_pk: int,
    success_message: str,
    anchor: str,
) -> HttpResponse:
    """Shared delete logic for models that belong to a Property."""
    if request.method != "POST":
        messages.error(request, _("Invalid request method."))
        return redirect("property:detail", pk=property_pk)

    property_obj = get_object_or_404(Property, pk=property_pk)
    obj = get_object_or_404(model, pk=object_pk, property=property_obj)
    obj.delete()
    messages.success(request, success_message)
    return HttpResponseRedirect(
        reverse("property:detail", kwargs={"pk": property_pk}) + anchor
    )


# ─── Lease CRUD ───────────────────────────────────────────────────────────────


def edit_lease(
    request: HttpRequest, property_pk: int, lease_pk: int | None = None
) -> HttpResponse:
    """Create or edit a lease for a property."""
    return _edit_property_related(
        request,
        property_pk=property_pk,
        model=Lease,
        object_pk=lease_pk,
        form_class=LeaseForm,
        template="property/edit_lease.html",
        context_key="lease",
        success_message=str(_("Lease saved.")),
        anchor="#leases-panel",
    )


def delete_lease(request: HttpRequest, property_pk: int, lease_pk: int) -> HttpResponse:
    """Delete a lease. Only accepts POST."""
    return _delete_property_related(
        request,
        property_pk=property_pk,
        model=Lease,
        object_pk=lease_pk,
        success_message=str(_("Lease deleted successfully.")),
        anchor="#leases-panel",
    )


# ─── ManagementMandate CRUD ───────────────────────────────────────────────────


def edit_mandate(
    request: HttpRequest, property_pk: int, mandate_pk: int | None = None
) -> HttpResponse:
    """Create or edit a management mandate for a property."""
    return _edit_property_related(
        request,
        property_pk=property_pk,
        model=ManagementMandate,
        object_pk=mandate_pk,
        form_class=ManagementMandateForm,
        template="property/edit_mandate.html",
        context_key="mandate",
        success_message=str(_("Mandate saved.")),
        anchor="#mandate-panel",
    )


def delete_mandate(
    request: HttpRequest, property_pk: int, mandate_pk: int
) -> HttpResponse:
    """Delete a management mandate. Only accepts POST."""
    return _delete_property_related(
        request,
        property_pk=property_pk,
        model=ManagementMandate,
        object_pk=mandate_pk,
        success_message=str(_("Mandate deleted successfully.")),
        anchor="#mandate-panel",
    )
