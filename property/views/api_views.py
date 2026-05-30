"""API views for the property app — JSON endpoints for the dashboard property cards."""

import datetime

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views import View

from property.models import Property
from property.services.cashflow import build_balance_sheet
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
                "address": prop.address or "",
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
            }
        )
