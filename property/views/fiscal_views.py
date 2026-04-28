"""Fiscal / accounting views: amortization panel, initialization, accounting dashboard."""

import datetime

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from property.forms import AmortizationAssetForm, AmortizationSetupForm  # noqa: F401
from property.models import AmortizationAsset, AmortizationSetup, Property
from property.services.tax_lmnp import (
    get_accounting_data,
    get_amortization_schedule,
    get_amortization_table,
)

# ─── Per-property amortization panel context helper ──────────────────────────


def get_amortization_context(property_obj: Property) -> dict:
    """Build the context dict for the amortization tab panel."""
    current_year = datetime.date.today().year

    amortization_table = get_amortization_table(property_obj.pk, current_year)

    assets_qs = AmortizationAsset.objects.filter(property=property_obj)

    try:
        amortization_setup = property_obj.amortization_setup  # ty: ignore[unresolved-attribute]
    except AmortizationSetup.DoesNotExist:
        amortization_setup = None

    schedule_data = get_amortization_schedule(property_obj.pk)

    return {
        "amortization_table": amortization_table,
        "amortization_setup": amortization_setup,
        "has_assets": assets_qs.exists(),
        "amortization_form": AmortizationAssetForm(),
        "amortization_total_base": schedule_data["total_depreciable_base"],
        "amortization_amortized": schedule_data["amortized_to_date"],
        "amortization_remaining": schedule_data["remaining"],
        "amortization_end_year": schedule_data["end_year"],
        "amortization_schedule_json": schedule_data["rows"],
        "amortization_asset_series_json": schedule_data["asset_series"],
    }


# ─── Amortization initialization ─────────────────────────────────────────────


def initialize_amortization(request: HttpRequest, pk: int) -> HttpResponse:
    """Initialize the standard LMNP amortization components in one click (POST only).

    Creates an AmortizationSetup using the property's current net value and
    land_percentage=15%, then calls initialize_components() to generate the
    five standard LMNP assets.
    """
    property_obj = get_object_or_404(Property, pk=pk)

    if request.method == "POST":
        try:
            setup = property_obj.amortization_setup  # ty: ignore[unresolved-attribute]
        except AmortizationSetup.DoesNotExist:
            net = property_obj.net_value
            setup = AmortizationSetup(
                property=property_obj,
                total_value=net,
                land_percentage=15,
            )
            setup.save()

        setup.initialize_components()
        messages.success(request, _("Default amortization components initialized."))

    return redirect(reverse("property:detail", kwargs={"pk": pk}) + "#amortization")


# ─── Amortization asset CRUD ─────────────────────────────────────────────────


def create_amortization_asset(request: HttpRequest, property_pk: int) -> HttpResponse:
    """Create a new amortization asset (immobilisation) for a property."""
    property_obj = get_object_or_404(Property, pk=property_pk)

    if request.method == "POST":
        form = AmortizationAssetForm(request.POST)
        if form.is_valid():
            asset = form.save(commit=False)
            asset.property = property_obj
            asset.is_initial_component = False
            asset.save()
            messages.success(request, _("Immobilisation created successfully."))
            return redirect(
                reverse("property:detail", kwargs={"pk": property_pk}) + "#amortization"
            )
    else:
        form = AmortizationAssetForm()

    return render(
        request,
        "property/edit_amortization.html",
        {"form": form, "property": property_obj, "is_create": True},
    )


def edit_amortization_asset(
    request: HttpRequest, property_pk: int, asset_pk: int
) -> HttpResponse:
    """Edit an existing amortization asset (immobilisation)."""
    property_obj = get_object_or_404(Property, pk=property_pk)
    asset = get_object_or_404(AmortizationAsset, pk=asset_pk, property=property_obj)

    if request.method == "POST":
        form = AmortizationAssetForm(request.POST, instance=asset)
        if form.is_valid():
            form.save()
            messages.success(request, _("Immobilisation updated successfully."))
            return redirect(
                reverse("property:detail", kwargs={"pk": property_pk}) + "#amortization"
            )
    else:
        form = AmortizationAssetForm(instance=asset)

    return render(
        request,
        "property/edit_amortization.html",
        {"form": form, "property": property_obj, "asset": asset, "is_create": False},
    )


def delete_amortization_asset(
    request: HttpRequest, property_pk: int, asset_pk: int
) -> HttpResponse:
    """Delete an amortization asset (POST only)."""
    property_obj = get_object_or_404(Property, pk=property_pk)
    asset = get_object_or_404(AmortizationAsset, pk=asset_pk, property=property_obj)

    if request.method == "POST":
        asset.delete()
        messages.success(request, _("Immobilisation deleted."))

    return redirect(
        reverse("property:detail", kwargs={"pk": property_pk}) + "#amortization"
    )


# ─── Global accounting dashboard ─────────────────────────────────────────────


def accounting_dashboard(request: HttpRequest) -> HttpResponse:
    """Global accounting dashboard aggregating all LMNP réel properties.

    Displays the full LMNP fiscal package: 2033-A/B/C, 2031, 2031-BIS, 2042-C PRO.
    Each line shows the aggregate total; hovering reveals a per-property breakdown.
    """
    current_year = datetime.date.today().year
    try:
        year = int(request.GET.get("year", current_year))
    except ValueError, TypeError:
        year = current_year

    lmnp_properties = list(
        Property.objects.filter(tax_regime=Property.TaxRegime.LMNP_REEL, is_active=True)
    )

    year_range = list(range(current_year - 5, current_year + 2))
    accounting = get_accounting_data(lmnp_properties, year)

    context = {
        "year": year,
        "year_range": year_range,
        "lmnp_properties": lmnp_properties,
        "accounting": accounting,
    }
    return render(request, "property/accounting_dashboard.html", context)
