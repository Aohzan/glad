"""Property index view."""

import datetime
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.db.models import Count
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from moneyed import Money

from property.models import Property
from property.services.monthly_flows import monthly_flows
from property.utils import iter_month_starts, month_start


def _current_lease(prop: Property, today: datetime.date):
    """The lease running today, from the prefetched leases."""
    for lease in prop.leases.all():
        if lease.start_date <= today and (
            lease.end_date is None or lease.end_date >= today
        ):
            return lease
    return None


def index(request: HttpRequest) -> HttpResponse:
    """Property index view."""
    properties = (
        Property.objects.order_by("-is_active", "name")
        .annotate(loans_count=Count("loans"))
        .prefetch_related("leases")
    )
    property_list: list[dict[str, Any]] = []

    total_gross_value: Money | None = None
    total_net_value: Money | None = None
    total_remaining: Money | None = None
    total_cashflow = Decimal(0)
    total_area = Decimal(0)
    today = datetime.date.today()

    for prop in properties:
        gross_value = prop.gross_value
        remaining = prop.total_remaining_loans
        net_value = Money(
            max(Decimal(0), gross_value.amount - remaining.amount),
            gross_value.currency,
        )
        cashflow = monthly_flows(prop, today).cashflow if prop.is_active else None

        if prop.is_active:
            if total_gross_value is None:
                total_gross_value = gross_value
                total_net_value = net_value
                total_remaining = remaining
            elif str(gross_value.currency) == str(total_gross_value.currency):
                total_gross_value += gross_value
                total_net_value += net_value  # type: ignore[operator]
                total_remaining += remaining  # type: ignore[operator]
            total_cashflow += cashflow or 0
            total_area += prop.floor_area or 0

        property_list.append(
            {
                "model": prop,
                "current_value": gross_value,
                "gross_value": gross_value,
                "net_value": net_value,
                "remaining": remaining,
                "cashflow": cashflow,
                "lease": _current_lease(prop, today),
                "loans_count": prop.loans_count,  # ty: ignore[unresolved-attribute]
                "progression": prop.get_progression(),
            }
        )

    properties_active = [p for p in properties if p.is_active]
    properties_months = []
    properties_gross_evolution = []
    properties_net_evolution = []

    now = datetime.date.today()
    earliest_date = None
    if properties_active:
        earliest_date = min(prop.buying_date for prop in properties_active)

    if earliest_date:
        chart_currency = (
            str(total_gross_value.currency) if total_gross_value is not None else None
        )

        for current_date in iter_month_starts(
            month_start(earliest_date), month_start(now)
        ):
            month_str = current_date.strftime("%b %Y")
            properties_months.append(month_str)

            month_properties = [
                p for p in properties_active if p.buying_date <= current_date
            ]

            month_property_net_total = Decimal(0)
            month_property_gross_total = Decimal(0)
            for property_item in month_properties:
                try:
                    net_value = property_item.net_value_at_date(current_date)
                    if net_value and (
                        chart_currency is None
                        or str(net_value.currency) == chart_currency
                    ):
                        month_property_net_total += net_value.amount

                    gross_value = property_item.get_value(
                        max_date=datetime.datetime.combine(
                            current_date,
                            datetime.time.max,
                        )
                    )
                    if gross_value and (
                        chart_currency is None
                        or str(gross_value.currency) == chart_currency
                    ):
                        month_property_gross_total += gross_value.amount
                except Exception:
                    pass

            properties_gross_evolution.append(float(month_property_gross_total))
            properties_net_evolution.append(float(month_property_net_total))

    context = {
        "properties": property_list,
        "inactive_properties_count": properties.filter(is_active=False).count(),
        "total_gross_value": total_gross_value,
        "total_net_value": total_net_value,
        "total_remaining": total_remaining,
        "currency": str(total_gross_value.currency)
        if total_gross_value is not None
        else settings.DEFAULT_CURRENCY,
        "total_cashflow": total_cashflow,
        "total_area": total_area,
        "active_count": sum(1 for p in property_list if p["model"].is_active),
        "loans_total_count": sum(
            p["loans_count"] for p in property_list if p["model"].is_active
        ),
        "properties_months": properties_months,
        "properties_gross_evolution": properties_gross_evolution,
        "properties_net_evolution": properties_net_evolution,
    }
    return render(request, "property/index.html", context)
