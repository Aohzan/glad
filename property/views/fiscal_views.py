"""Fiscal / accounting views: amortization panel, initialization, accounting dashboard."""

import csv
import datetime

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from property.forms import (
    AmortizationAssetForm,  # noqa: F401
    AmortizationInitForm,
    PropertyReportFilterForm,
)
from property.models import AmortizationAsset, AmortizationSetup, Property
from property.services.report import get_income_expense_report
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

    # Compute default acquisition fees for the init form
    from decimal import Decimal

    acquisition_fees_total = Decimal("0")
    acquisition_fees_breakdown: dict[str, Decimal] = {}
    for attr, label in (
        ("notary_fees", _("Notary fees")),
        ("agency_fees", _("Agency fees")),
        ("other_fees", _("Other fees")),
    ):
        fee = getattr(property_obj, attr, None)
        if fee is not None:
            amount = fee.amount if hasattr(fee, "amount") else Decimal(str(fee))
            if amount:
                acquisition_fees_breakdown[str(label)] = amount
                acquisition_fees_total += amount

    amortization_init_form = AmortizationInitForm(
        initial={"extra_amount": acquisition_fees_total}
    )

    return {
        "amortization_table": amortization_table,
        "amortization_setup": amortization_setup,
        "has_assets": assets_qs.exists(),
        "amortization_form": AmortizationAssetForm(property_obj=property_obj),
        "amortization_total_base": schedule_data["total_depreciable_base"],
        "amortization_amortized": schedule_data["amortized_to_date"],
        "amortization_remaining": schedule_data["remaining"],
        "amortization_end_year": schedule_data["end_year"],
        "amortization_current_year": current_year,
        "amortization_schedule": schedule_data["rows"],
        "amortization_schedule_json": schedule_data["rows"],
        "amortization_asset_series_json": schedule_data["asset_series"],
        "amortization_init_form": amortization_init_form,
        "acquisition_fees_breakdown": acquisition_fees_breakdown,
        "acquisition_fees_total": acquisition_fees_total,
    }


# ─── Amortization initialization ─────────────────────────────────────────────


def initialize_amortization(request: HttpRequest, pk: int) -> HttpResponse:
    """Initialize the standard LMNP amortization components in one click (POST only).

    Creates an AmortizationSetup using the property's buying_value optionally
    increased by acquisition fees (notary, agency, other), then calls
    initialize_components() to generate the five standard LMNP assets.
    """
    from decimal import Decimal

    from moneyed import Money

    property_obj = get_object_or_404(Property, pk=pk)

    if request.method == "POST":
        form = AmortizationInitForm(request.POST)
        if form.is_valid():
            extra_amount = form.cleaned_data["extra_amount"]
            land_percentage = form.cleaned_data["land_percentage"]

            currency = str(property_obj.currency)
            base_amount = (
                property_obj.buying_value.amount
                if hasattr(property_obj.buying_value, "amount")
                else Decimal(str(property_obj.buying_value))
            )
            total_value = Money(base_amount + extra_amount, currency)

            try:
                setup = property_obj.amortization_setup  # ty: ignore[unresolved-attribute]
                setup.total_value = total_value
                setup.land_percentage = land_percentage
                setup.save()
            except AmortizationSetup.DoesNotExist:
                setup = AmortizationSetup(
                    property=property_obj,
                    total_value=total_value,
                    land_percentage=land_percentage,
                )
                setup.save()

            setup.initialize_components()
            messages.success(request, _("Default amortization components initialized."))
        else:
            messages.error(request, _("Invalid form data. Please check the values."))

    return redirect(
        reverse("property:detail", kwargs={"pk": pk}) + "#amortization-panel"
    )


# ─── Amortization asset CRUD ─────────────────────────────────────────────────


def create_amortization_asset(request: HttpRequest, property_pk: int) -> HttpResponse:
    """Create a new amortization asset (immobilisation) for a property."""
    property_obj = get_object_or_404(Property, pk=property_pk)

    if request.method == "POST":
        form = AmortizationAssetForm(request.POST, property_obj=property_obj)
        if form.is_valid():
            asset = form.save(commit=False)
            asset.property = property_obj
            asset.is_initial_component = False
            asset.save()
            messages.success(request, _("Immobilisation created successfully."))
            return redirect(
                reverse("property:detail", kwargs={"pk": property_pk})
                + "#amortization-panel"
            )
    else:
        form = AmortizationAssetForm(property_obj=property_obj)

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
        form = AmortizationAssetForm(
            request.POST, instance=asset, property_obj=property_obj
        )
        if form.is_valid():
            form.save()
            messages.success(request, _("Immobilisation updated successfully."))
            return redirect(
                reverse("property:detail", kwargs={"pk": property_pk})
                + "#amortization-panel"
            )
    else:
        form = AmortizationAssetForm(instance=asset, property_obj=property_obj)

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
        reverse("property:detail", kwargs={"pk": property_pk}) + "#amortization-panel"
    )


# ─── Global accounting dashboard ─────────────────────────────────────────────


def accounting_lmnp_reel(request: HttpRequest) -> HttpResponse:
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
    return render(request, "property/accounting_lmnp_reel.html", context)


# ─── Income & expenses report ─────────────────────────────────────────────────


def report_view(request: HttpRequest) -> HttpResponse:
    """Income & expenses report: filter by properties, date range, export to CSV."""
    today = datetime.date.today()
    default_start = datetime.date(today.year, 1, 1)
    default_end = datetime.date(today.year, 12, 31)

    initial = {"start_date": default_start, "end_date": default_end}

    if request.GET:
        form = PropertyReportFilterForm(request.GET, initial=initial)
    else:
        form = PropertyReportFilterForm(initial=initial)

    report_data: dict | None = None

    if form.is_bound and form.is_valid():
        selected_props = form.cleaned_data.get("properties")
        start_date = form.cleaned_data.get("start_date")
        end_date = form.cleaned_data.get("end_date")

        if selected_props:
            property_ids = list(selected_props.values_list("pk", flat=True))
        else:
            property_ids = list(
                Property.objects.filter(is_active=True).values_list("pk", flat=True)
            )

        report_data = get_income_expense_report(property_ids, start_date, end_date)

        # CSV export
        if request.GET.get("format") == "csv":
            response = HttpResponse(content_type="text/csv; charset=utf-8")
            filename = "income_expenses_report.csv"
            response["Content-Disposition"] = f'attachment; filename="{filename}"'
            writer = csv.writer(response)
            writer.writerow(
                [
                    "date",
                    "property",
                    "flow_type",
                    "management_category",
                    "amount",
                    "description",
                ]
            )
            for entry in report_data["entries"]:
                writer.writerow(
                    [
                        entry.entry_date.isoformat(),
                        entry.property.name,
                        entry.flow_type,
                        entry.management_category,
                        entry.amount.amount,
                        entry.description or "",
                    ]
                )
            return response

    context = {
        "form": form,
        "report": report_data,
    }
    return render(request, "property/report.html", context)
