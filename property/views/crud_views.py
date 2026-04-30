"""CRUD views for ledger entries, tenants, leases, managers, and mandates."""

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
)
from property.models import (
    Lease,
    ManagementMandate,
    Property,
    PropertyLedgerEntry,
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
