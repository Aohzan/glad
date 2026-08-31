"""API views for the property app — JSON endpoints for the dashboard property cards."""

import datetime
from decimal import Decimal, InvalidOperation

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.views import View

from property.models import Property
from property.models.scpi import SCPI
from property.services.cashflow import build_balance_sheet
from property.services.dvf_estimation import estimate_property_value
from property.services.geocoding import lookup_cadastral_parcel, search_addresses
from property.utils import month_end, month_start


@method_decorator(login_required, name="dispatch")
class PropertyDashboardCardApiView(View):
    """Return all data needed to render a single property card on the dashboard."""

    def get(self, request, pk: int):
        prop = Property.objects.filter(pk=pk, is_active=True).first()
        if prop is None:
            return JsonResponse({"error": "Not found"}, status=404)

        # Last calendar month date range
        today = datetime.date.today()
        first_of_this_month = today.replace(day=1)
        last_month_end = first_of_this_month - datetime.timedelta(days=1)
        last_month_start = last_month_end.replace(day=1)
        date_from = month_start(last_month_start)
        date_to = month_end(last_month_end)

        # Cashflow for last month
        cashflow = build_balance_sheet(prop, date_from, date_to)

        # Latest loan end date
        loans = list(prop.loans.all())
        loan_end_date = None
        if loans:
            dates = [loan.end_date for loan in loans if loan.end_date]
            if dates:
                loan_end_date = max(dates).isoformat()

        # Active lease
        lease = prop.active_lease
        lease_data = None
        if lease:
            lease_data = {
                "rent_amount": float(lease.rent_amount.amount),
                "charges_amount": float(lease.charges_amount.amount),
                "total_rent": float(lease.total_rent().amount),
                "currency": str(lease.rent_amount.currency),
                "tenant_name": lease.name,
            }

        return JsonResponse(
            {
                "pk": prop.pk,
                "name": prop.name,
                "address": prop.full_address,
                "property_type": prop.property_type,
                "property_type_display": dict(Property.PROPERTY_CHOICES).get(
                    prop.property_type, prop.property_type
                ),
                "icon": prop.icon,
                "currency": prop.currency,
                "gross_value": float(prop.gross_value.amount),
                "net_value": float(prop.net_value.amount),
                "buying_value_gross": float(prop.buying_value_gross.amount),
                "appreciation_percent": round(prop.appreciation_percent, 2),
                "floor_area": float(prop.floor_area) if prop.floor_area else None,
                "total_surface": float(prop.total_surface)
                if prop.total_surface
                else None,
                "number_of_rooms": prop.number_of_rooms,
                "loan_progress_percent": round(prop.loan_progress_percent, 1),
                "total_remaining_loans": float(prop.total_remaining_loans.amount),
                "loan_end_date": loan_end_date,
                "cashflow_last_month": {
                    "income": float(cashflow["total_income"]),
                    "expenses": float(cashflow["total_expenses"]),
                    "net": float(cashflow["net_cashflow"]),
                    "occupancy_rate": float(cashflow["occupancy_rate"]),
                },
                "active_lease": lease_data,
                "is_favorite": prop.is_favorite,
            }
        )


@method_decorator(login_required, name="dispatch")
class SCPIDashboardCardApiView(View):
    """Return data needed to render a single SCPI fund card on the dashboard."""

    def get(self, request, pk: int):
        from property.views.scpi_views import (
            _compute_fund_data,  # avoid circular import
        )

        fund = (
            SCPI.objects.prefetch_related("share_prices", "investments", "dividends")
            .filter(pk=pk)
            .first()
        )
        if fund is None:
            return JsonResponse({"error": "Not found"}, status=404)

        today = datetime.date.today()
        data = _compute_fund_data(fund, today)

        return JsonResponse(
            {
                "pk": fund.pk,
                "name": fund.name,
                "management_company": fund.management_company or "",
                "total_resale": float(data["total_resale"].amount)
                if data["total_resale"]
                else None,
                "total_estimated_value": float(data["total_estimated_value"].amount)
                if data["total_estimated_value"]
                else None,
                "total_invested": float(data["total_invested"].amount)
                if data["total_invested"]
                else None,
                "total_dividends": float(data["total_dividends"].amount)
                if data["total_dividends"]
                else None,
                "gain_pct": float(data["gain_pct"])
                if data["gain_pct"] is not None
                else None,
                "net_rentability": float(data["net_rentability"]),
                "currency": data["currency"],
            }
        )


@method_decorator(login_required, name="dispatch")
class AddressAutocompleteApiView(View):
    """Return address suggestions from the BAN API for autocomplete widgets."""

    def get(self, request):
        query = request.GET.get("q", "").strip()
        if len(query) < 3:
            return JsonResponse({"results": []})
        results = search_addresses(query, limit=5)
        return JsonResponse({"results": results})


@method_decorator(login_required, name="dispatch")
class CadastralLookupApiView(View):
    """Look up cadastral section/parcel for a property via IGN APICarto."""

    def get(self, request, pk: int):
        prop = get_object_or_404(Property, pk=pk)
        latitude = prop.latitude
        longitude = prop.longitude
        insee_code = prop.insee_code
        # Allow unsaved form coordinates (query params) so the lookup works
        # before the property is saved.
        try:
            lat_param = request.GET.get("lat")
            lon_param = request.GET.get("lon")
            if lat_param is not None:
                latitude = Decimal(lat_param)
            if lon_param is not None:
                longitude = Decimal(lon_param)
            insee_param = request.GET.get("insee")
            if insee_param:
                insee_code = insee_param
        except InvalidOperation, ValueError:
            return JsonResponse(
                {"error": "invalid_coordinates"},
                status=400,
            )
        if latitude is None or longitude is None:
            return JsonResponse(
                {"error": "missing_coordinates"},
                status=400,
            )
        result = lookup_cadastral_parcel(latitude, longitude, insee_code=insee_code)
        if result is None:
            return JsonResponse(
                {"error": "cadastral_not_found"},
                status=404,
            )
        return JsonResponse(result)


@method_decorator(login_required, name="dispatch")
class PropertyDvfEstimateApiView(View):
    """Return a DVF-based value estimation for a property."""

    def get(self, request, pk: int):
        prop = get_object_or_404(Property, pk=pk)
        result = estimate_property_value(prop)
        data: dict = {
            "comparable_count": result.comparable_count,
            "reason": result.reason,
            "total_mutations": result.total_mutations,
            "filtered_by_type": result.filtered_by_type,
            "filtered_by_date": result.filtered_by_date,
            "filtered_by_invalid": result.filtered_by_invalid,
        }
        if result.median_price_per_sqm is not None:
            data["median_price_per_sqm"] = str(result.median_price_per_sqm)
        if result.estimated_value is not None:
            data["estimated_value"] = float(result.estimated_value.amount)
            data["currency"] = str(result.estimated_value.currency)
        return JsonResponse(data)
